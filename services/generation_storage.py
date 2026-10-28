"""Durable, leased persistence of already-generated media, never generation.

The outbox is inserted in the job-completion transaction. Provider URLs and
deterministic object keys survive a process exit; no provider generation or
billing operation belongs in this module.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from services.generation_media_state import MEDIA_FIELDS, align_media_metadata, merge_generation_result_fields

SCALAR_FIELDS = {
    'image_url': 'images', 'thumbnail_url': 'thumbs', 'thumb_url': 'thumbs',
    'video_url': 'videos', 'audio_url': 'audio', 'music_url': 'audio',
    'file_url': 'documents', 'svg_url': 'documents', 'svg_download_url': 'documents',
    'cover_url': 'images', 'artwork_url': 'images',
}
LIST_FIELDS = {
    'images': 'images', 'thumbnails': 'thumbs', 'videos': 'videos',
    'audio_urls': 'audio', 'audios': 'audio', 'files': 'documents',
    'svg_urls': 'documents',
}
MAX_DOWNLOAD_ATTEMPTS = 12
LEASE_SECONDS = 300


class LeaseLost(RuntimeError):
    pass


def media_plan(job_id, result, mode):
    """Choose each key before any upload; aliases share the same object."""
    plan = {}
    primary = {'image': 'images', 'video': 'videos', 'music': 'audio',
               'voice': 'audio'}.get(mode, 'documents')
    scalar = {**SCALAR_FIELDS, **dict.fromkeys(('result_url', 'full_url', 'url', 'song_url'), primary)}

    def add(source, category):
        if not isinstance(source, str) or not source.strip():
            return
        source = source.strip()
        identity = hashlib.sha256(source.encode()).hexdigest()
        if identity in plan:
            return
        fingerprint = hashlib.sha256((job_id + '\0' + source).encode()).hexdigest()
        suffix = Path(urlsplit(source).path).suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif', '.mp4',
                          '.webm', '.mov', '.mp3', '.wav', '.ogg', '.m4a', '.svg', '.pdf'}:
            suffix = {'images': '.png', 'thumbs': '.jpg', 'videos': '.mp4',
                      'audio': '.mp3'}.get(category, '.bin')
        job_hash = hashlib.sha256(job_id.encode()).hexdigest()
        plan[identity] = {'source': source, 'category': category,
                          'order': len(plan),
                          'key': f'generated/{category}/jobs/{job_hash}/{identity}{suffix}',
                          'fingerprint': fingerprint}

    for container in (result, result.get('metadata') or {}):
        if not isinstance(container, dict):
            continue
        for field, category in scalar.items():
            add(container.get(field), category)
        for field, category in LIST_FIELDS.items():
            for value in container.get(field) or [] if isinstance(container.get(field), list) else []:
                add(value, category)
    return plan


def replace_planned_media(result, plan):
    result = deepcopy(result)
    replacements = {entry['source']: entry['url'] for entry in plan.values() if entry.get('url')}
    fields = {*SCALAR_FIELDS, *LIST_FIELDS, 'result_url', 'full_url', 'url', 'song_url'}
    for container in (result, result.get('metadata') or {}):
        for field in fields:
            value = container.get(field)
            if isinstance(value, str):
                container[field] = replacements.get(value, value)
            elif isinstance(value, list):
                container[field] = [replacements.get(item, item) if isinstance(item, str) else item for item in value]
    return result


def storage_result_fields(result):
    # Storage owns output locations, not costs, history settings or a separate
    # thumbnail task's status. Empty source placeholders must not erase them.
    return {key: value for key, value in result.items()
            if key in MEDIA_FIELDS and key not in {'storage_status', 'thumbnail_status'} and value}


def ensure_table(cursor):
    cursor.execute('''CREATE TABLE IF NOT EXISTS prostudio_media_outbox (
        job_id TEXT PRIMARY KEY REFERENCES prostudio_generation_jobs(id),
        mode TEXT NOT NULL, source_json JSONB NOT NULL, progress_json JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(), lease_token TEXT,
        lease_until TIMESTAMPTZ, last_error TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_prostudio_media_outbox_ready
        ON prostudio_media_outbox (run_after, created_at) WHERE status IN ('pending', 'processing')''')


def enqueue(cursor, job_id, mode, result):
    plan = media_plan(job_id, result, mode)
    cursor.execute('''INSERT INTO prostudio_media_outbox(job_id,mode,source_json,progress_json)
        VALUES (%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT (job_id) DO NOTHING''',
        (job_id, mode, json.dumps(result, ensure_ascii=False), json.dumps(plan, ensure_ascii=False)))


class MediaOutbox:
    def __init__(self, connect):
        self.connect = connect

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                yield cursor
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def claim(self, job_id=None):
        token = uuid4().hex
        with self.transaction() as cursor:
            cursor.execute('''UPDATE prostudio_media_outbox o
                SET status='processing', attempts=attempts+1, lease_token=%s,
                    lease_until=NOW()+(%s * INTERVAL '1 second'), updated_at=NOW()
                WHERE job_id=(SELECT job_id FROM prostudio_media_outbox
                    WHERE ((status='pending' AND run_after<=NOW())
                        OR (status='processing' AND lease_until<NOW()))
                      AND (%s IS NULL OR job_id=%s)
                    ORDER BY run_after,created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING job_id,mode,source_json,progress_json,attempts''',
                (token, LEASE_SECONDS, job_id, job_id))
            row = cursor.fetchone()
        return dict(zip(('job_id', 'mode', 'source', 'plan', 'attempts'), row), token=token) if row else None

    def renew(self, job):
        with self.transaction() as cursor:
            cursor.execute('''UPDATE prostudio_media_outbox
                SET lease_until=NOW()+(%s * INTERVAL '1 second'),updated_at=NOW()
                WHERE job_id=%s AND lease_token=%s AND status='processing' AND lease_until>NOW()''',
                (LEASE_SECONDS, job['job_id'], job['token']))
            if not cursor.rowcount:
                raise LeaseLost('storage_lease_lost')

    def checkpoint(self, job):
        with self.transaction() as cursor:
            cursor.execute('''UPDATE prostudio_media_outbox SET progress_json=%s::jsonb,updated_at=NOW()
                WHERE job_id=%s AND lease_token=%s AND status='processing' AND lease_until>NOW()''',
                (json.dumps(job['plan'], ensure_ascii=False), job['job_id'], job['token']))
            if not cursor.rowcount:
                raise LeaseLost('storage_lease_lost')
            cursor.execute('SELECT status,result_json FROM prostudio_generation_jobs WHERE id=%s FOR UPDATE',
                           (job['job_id'],))
            current = cursor.fetchone()
            if not current or current[0] != 'completed':
                raise RuntimeError('storage_job_not_completed')
            fields = storage_result_fields(replace_planned_media(job['source'], job['plan']))
            fields['storage_recovery_version'] = 1
            merged = merge_generation_result_fields(current[1] or {}, fields)
            cursor.execute('UPDATE prostudio_generation_jobs SET result_json=%s::jsonb WHERE id=%s',
                           (json.dumps(merged, ensure_ascii=False), job['job_id']))

    def finish(self, job, result):
        # Claim and job result commit together; an expired worker cannot publish.
        with self.transaction() as cursor:
            cursor.execute('''SELECT job_id FROM prostudio_media_outbox
                WHERE job_id=%s AND lease_token=%s AND status='processing' AND lease_until>NOW() FOR UPDATE''',
                (job['job_id'], job['token']))
            if not cursor.fetchone():
                raise LeaseLost('storage_lease_lost')
            cursor.execute('SELECT status,result_json FROM prostudio_generation_jobs WHERE id=%s FOR UPDATE',
                           (job['job_id'],))
            current = cursor.fetchone()
            if not current or current[0] != 'completed':
                raise RuntimeError('storage_job_not_completed')
            fields = storage_result_fields(result)
            fields['storage_status'] = 'completed'
            fields['storage_recovery_version'] = 1
            merged = align_media_metadata(merge_generation_result_fields(current[1] or {}, fields))
            cursor.execute('UPDATE prostudio_generation_jobs SET result_json=%s::jsonb WHERE id=%s',
                           (json.dumps(merged, ensure_ascii=False), job['job_id']))
            cursor.execute('''UPDATE prostudio_media_outbox SET status='completed',progress_json=%s::jsonb,
                lease_token=NULL,lease_until=NULL,last_error='',updated_at=NOW() WHERE job_id=%s''',
                (json.dumps(job['plan'], ensure_ascii=False), job['job_id']))

    def fail(self, job, error):
        terminal = job['attempts'] > MAX_DOWNLOAD_ATTEMPTS
        delay = min(900, 15 * 2 ** min(job['attempts'] - 1, 6))
        # Type only: HTTP exception strings can contain signed source URLs.
        with self.transaction() as cursor:
            cursor.execute('''UPDATE prostudio_media_outbox SET status=%s,last_error=%s,
                run_after=NOW()+(%s * INTERVAL '1 second'),lease_token=NULL,lease_until=NULL,updated_at=NOW()
                WHERE job_id=%s AND lease_token=%s AND status='processing' AND lease_until>NOW()''',
                ('failed' if terminal else 'pending', type(error).__name__, delay, job['job_id'], job['token']))
            if not cursor.rowcount:
                raise LeaseLost('storage_lease_lost')
            cursor.execute("""UPDATE prostudio_generation_jobs
                SET result_json=jsonb_set(COALESCE(result_json,'{}'::jsonb),'{storage_status}',%s::jsonb)
                WHERE id=%s AND status='completed'""",
                (json.dumps('failed' if terminal else 'pending'), job['job_id']))

    def process(self, job, persist, verify):
        """persist(entry, verify_only) must adopt an existing key before download."""
        try:
            for entry in sorted(job['plan'].values(), key=lambda item: item.get('order', 0)):
                if not entry.get('url'):
                    self.renew(job)
                    entry['url'] = persist(entry, job['attempts'] > MAX_DOWNLOAD_ATTEMPTS)
                    self.checkpoint(job)
            result = replace_planned_media(job['source'], job['plan'])
            verify(result, job['mode'])
            self.finish(job, result)
            return 'completed'
        except LeaseLost:
            raise
        except Exception as exc:
            self.fail(job, exc)
            return 'failed' if job['attempts'] > MAX_DOWNLOAD_ATTEMPTS else 'pending'
