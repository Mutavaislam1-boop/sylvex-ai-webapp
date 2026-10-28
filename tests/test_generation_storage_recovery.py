"""Crash/restart contracts with actual local PostgreSQL and an atomic fake R2.

No provider requests, charges, production database, or actual R2 writes.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock

import pytest
from botocore.exceptions import ClientError
import main
from services import generation_storage as gs, storage
from test_generation_result_postgres_roundtrip import result_database


class ProcessExit(BaseException):
    pass


class AtomicR2:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.lock = Lock()
        self.exit_after_put = False

    def head_object(self, Bucket, Key):
        with self.lock:
            if Key not in self.objects:
                raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
            return deepcopy(self.objects[Key]['head'])

    def put_object(self, **request):
        assert request['IfNoneMatch'] == '*'
        content = request['Body'].read()
        assert len(content) == request['ContentLength']
        with self.lock:
            key = request['Key']
            if key in self.objects:
                raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
            self.objects[key] = {'body': content, 'head': {
                'Metadata': request['Metadata'], 'ContentLength': len(content),
                'ContentType': request['ContentType']}}
            self.writes.append(key)
        if self.exit_after_put:
            self.exit_after_put = False
            raise ProcessExit()
        return {}


@pytest.fixture
def fake_r2(monkeypatch):
    fake = AtomicR2()
    monkeypatch.setattr(storage, 'r2_enabled', lambda: True)
    monkeypatch.setattr(storage, 'r2_client', lambda: fake)
    monkeypatch.setattr(storage, '_record_object', lambda *a: None)
    monkeypatch.setattr(storage, 'object_url', lambda key: 'https://storage.example.test/api/public/storage/' + key)
    monkeypatch.setattr(main, 'r2_enabled', lambda: True)
    monkeypatch.setattr(main, 'storage_key_from_url', lambda value: value.partition('/api/public/storage/')[2])
    monkeypatch.setattr(main, 'storage_exists', storage.exists)
    # storage.exists also normalizes the URL, independently of main's alias.
    monkeypatch.setattr(storage, 'key_from_url', lambda value: value.partition('/api/public/storage/')[2])
    downloads = []
    fail_sources = set()

    def download(url, path, **kwargs):
        assert url.startswith('https://provider.example.test/')
        downloads.append(url)
        if url in fail_sources:
            raise RuntimeError('synthetic temporary download failure')
        path.write_bytes(b'synthetic media:' + url.encode())
        return {'headers': {'content-type': 'image/png'}, 'url': url}

    monkeypatch.setattr(main, 'safe_download_to_file', download)
    fake.downloads = downloads
    fake.fail_sources = fail_sources
    return fake


def completed(db, count=4):
    db.query("INSERT INTO prostudio_generation_jobs(id,status,cost) VALUES ('recover-job','processing',19)")
    urls = [f'https://provider.example.test/result-{i}.png' for i in range(count)]
    result = {'ok': True, 'type': 'image', 'images': urls, 'image_url': urls[0],
              'result_url': urls[0], 'full_url': urls[0], 'cost_credits': 19,
              'storage_status': 'pending', 'metadata': {'image_url': urls[0]}}
    assert main.update_prostudio_generation_job('recover-job', 'completed', result)
    # Tests explicitly make scheduled work due rather than racing the VM clock
    # against the completion transaction's CURRENT_TIMESTAMP.
    ready(db)
    return gs.MediaOutbox(db.connect), urls


def expire(db):
    db.query("UPDATE prostudio_media_outbox SET lease_until=NOW()-INTERVAL '1 second',run_after=NOW()-INTERVAL '1 second'")


def ready(db):
    db.query("UPDATE prostudio_media_outbox SET run_after=NOW()-INTERVAL '1 second'")


def test_completion_and_outbox_are_atomic(result_database, monkeypatch):
    db = result_database
    db.query("INSERT INTO prostudio_generation_jobs(id,status,cost) VALUES ('atomic-job','processing',19)")
    def failed_enqueue(*args):
        raise RuntimeError('synthetic database interruption')
    monkeypatch.setattr(gs, 'enqueue', failed_enqueue)
    assert not main.update_prostudio_generation_job('atomic-job','completed',
        {'ok':True,'type':'image','images':['https://provider.example.test/a.png'],'storage_status':'pending'})
    assert db.query('SELECT status,result_json,cost FROM prostudio_generation_jobs') == [('processing',None,19)]
    assert db.query('SELECT count(*) FROM prostudio_media_outbox') == [(0,)]


def test_restart_before_first_claim_preserves_four_outputs_and_history(result_database, fake_r2):
    db = result_database
    _, urls = completed(db)
    # A different queue instance stands in for a fresh worker process.
    queue = gs.MediaOutbox(db.connect)
    main.update_prostudio_generation_job('recover-job','completed',
        {'images':urls,'cost_credits':19,'metadata':{'style':'cinematic','input_images':['user-ref']}})
    assert queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media) == 'completed'
    status, result, cost = db.query('SELECT status,result_json,cost FROM prostudio_generation_jobs')[0]
    assert status == 'completed' and cost == 19 and result['storage_status'] == 'completed'
    assert len(result['images']) == 4 and len(set(result['images'])) == 4
    assert result['metadata']['result_images'] == result['images']
    assert result['metadata']['style'] == 'cinematic' and result['metadata']['input_images'] == ['user-ref']
    assert len(fake_r2.writes) == len(fake_r2.downloads) == 4
    assert db.query('SELECT status FROM prostudio_media_outbox') == [('completed',)]
    assert not queue.claim()


def test_crash_after_put_before_checkpoint_adopts_object_without_provider_redownload(result_database, fake_r2):
    db = result_database
    queue, urls = completed(db, 1)
    fake_r2.exit_after_put = True
    with pytest.raises(ProcessExit):
        queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media)
    assert len(fake_r2.writes) == len(fake_r2.downloads) == 1
    assert db.query('SELECT status FROM prostudio_media_outbox') == [('processing',)]
    expire(db)
    recovered = gs.MediaOutbox(db.connect)
    assert recovered.process(recovered.claim(), main._persist_outbox_media, main.verify_persisted_generation_media) == 'completed'
    assert len(fake_r2.writes) == len(fake_r2.downloads) == 1
    assert db.query('SELECT status,cost FROM prostudio_generation_jobs') == [('completed',19)]


def test_partial_batch_retries_only_missing_outputs(result_database, fake_r2):
    db = result_database
    queue, urls = completed(db)
    fake_r2.fail_sources.add(urls[1])
    assert queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media) == 'pending'
    progress = db.query('SELECT progress_json FROM prostudio_media_outbox')[0][0]
    assert sum(bool(entry.get('url')) for entry in progress.values()) == 1
    partial = db.query('SELECT result_json FROM prostudio_generation_jobs')[0][0]
    assert partial['images'][0].startswith('https://storage.example.test/')
    assert partial['images'][1:] == urls[1:]
    # Completed files remain usable even while another item is retrying.
    history = main.overlay_stored_history_media({'images':urls, 'metadata':{'style':'own-style'}}, partial)
    assert history['images'] == partial['images'] and history['metadata']['style'] == 'own-style'
    assert db.query('SELECT status,cost FROM prostudio_generation_jobs') == [('completed',19)]
    fake_r2.fail_sources.clear()
    ready(db)
    assert queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media) == 'completed'
    assert len(fake_r2.writes) == 4 and fake_r2.downloads.count(urls[0]) == 1
    assert len(set(fake_r2.writes)) == 4


def test_five_workers_claim_once_and_expired_owner_cannot_commit(result_database, fake_r2):
    db = result_database
    queue, _ = completed(db, 1)
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = list(pool.map(lambda _: gs.MediaOutbox(db.connect).claim(), range(5)))
    owned = [job for job in jobs if job]
    assert len(owned) == 1
    old = owned[0]
    expire(db)
    new = queue.claim()
    assert new['token'] != old['token']
    with pytest.raises(gs.LeaseLost):queue.checkpoint(old)
    with pytest.raises(gs.LeaseLost):queue.finish(old, {'images':['stale']})
    assert queue.process(new, main._persist_outbox_media, main.verify_persisted_generation_media) == 'completed'


def test_last_attempt_crash_still_allows_verification_only_recovery(result_database, fake_r2):
    db = result_database
    queue, _ = completed(db, 1)
    db.query('UPDATE prostudio_media_outbox SET attempts=%s', (gs.MAX_DOWNLOAD_ATTEMPTS-1,))
    fake_r2.exit_after_put = True
    with pytest.raises(ProcessExit):
        queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media)
    expire(db)
    recovered = queue.claim()
    assert recovered['attempts'] > gs.MAX_DOWNLOAD_ATTEMPTS
    assert queue.process(recovered, main._persist_outbox_media, main.verify_persisted_generation_media) == 'completed'
    assert len(fake_r2.downloads) == len(fake_r2.writes) == 1


def test_exhausted_downloads_keep_source_and_generation_completed(result_database, fake_r2):
    db = result_database
    queue, urls = completed(db, 1)
    db.query('UPDATE prostudio_media_outbox SET attempts=%s', (gs.MAX_DOWNLOAD_ATTEMPTS,))
    assert queue.process(queue.claim(), main._persist_outbox_media, main.verify_persisted_generation_media) == 'failed'
    assert fake_r2.downloads == fake_r2.writes == []
    status, result, cost = db.query('SELECT status,result_json,cost FROM prostudio_generation_jobs')[0]
    assert status == 'completed' and cost == 19 and result['storage_status'] == 'failed'
    source, progress = db.query('SELECT source_json,progress_json FROM prostudio_media_outbox')[0]
    assert source['images'] == urls and len(progress) == 1


def test_conditional_put_never_overwrites_other_identity(fake_r2, tmp_path):
    source = tmp_path/'one.png';source.write_bytes(b'first media')
    key = 'generated/images/jobs/own-test/result.png'
    first = storage.put_generated_file_once(source,key,'own-fingerprint','image/png')
    source.write_bytes(b'different media')
    assert storage.put_generated_file_once(source,key,'own-fingerprint','image/png') == first
    with pytest.raises(RuntimeError, match='identity_mismatch'):
        storage.put_generated_file_once(source,key,'foreign-fingerprint','image/png')
    assert fake_r2.objects[key]['body'] == b'first media'
    assert fake_r2.writes == [key]


def test_lost_old_worker_put_cannot_overwrite_winner(fake_r2, tmp_path, monkeypatch):
    source = tmp_path/'one.png';source.write_bytes(b'first media')
    key = 'generated/images/jobs/own-test/race.png'
    # Simulate both workers observing missing before the first PUT commits.
    original = storage.find_generated_object
    calls = 0
    def missing_first_two(*args):
        nonlocal calls
        calls += 1
        return '' if calls == 1 else original(*args)
    monkeypatch.setattr(storage,'find_generated_object',missing_first_two)
    storage.put_generated_file_once(source,key,'same-job','image/png')
    source.write_bytes(b'stale worker data')
    # Force a stale negative HEAD; the server's atomic precondition is final.
    calls = 0
    assert storage.put_generated_file_once(source,key,'same-job','image/png')
    assert fake_r2.objects[key]['body'] == b'first media' and fake_r2.writes == [key]


def test_actual_process_exit_and_fresh_process_resume_without_duplicate_file(result_database, tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    db = result_database
    completed(db)
    schema = db.query('SELECT current_schema()')[0][0]
    script = r'''
import os,sys
from pathlib import Path
import psycopg2
from psycopg2 import sql
from services.generation_storage import MediaOutbox
schema,root,action=sys.argv[1:]
root=Path(root)
def connect():
    conn=psycopg2.connect(os.environ['SYLVEX_RESULT_TEST_DB'])
    with conn.cursor() as cur:cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
    return conn
queue=MediaOutbox(connect)
def persist(entry,verify_only):
    path=root/entry['fingerprint']
    if not path.exists():
        assert not verify_only
        path.write_bytes(b'synthetic generated file')
        with (root/'download-count').open('a') as counter:counter.write('1\n')
    if action=='crash':os._exit(73)
    return 'https://storage.example.test/'+entry['key']
def verify(result,mode):
    assert len(result['images'])==4
    assert all(url.startswith('https://storage.example.test/') for url in result['images'])
assert queue.process(queue.claim(),persist,verify)=='completed'
'''
    command = [sys.executable, '-c', script, schema, str(tmp_path)]
    before = subprocess.run([*command, 'crash'], capture_output=True, text=True, timeout=20)
    assert before.returncode == 73, before.stderr
    assert db.query('SELECT status FROM prostudio_media_outbox') == [('processing',)]
    assert len((tmp_path/'download-count').read_text().splitlines()) == 1
    expire(db)
    after = subprocess.run([*command, 'recover'], capture_output=True, text=True, timeout=20)
    assert after.returncode == 0, after.stderr
    assert len((tmp_path/'download-count').read_text().splitlines()) == 4
    assert db.query('SELECT status,cost FROM prostudio_generation_jobs') == [('completed',19)]
    assert db.query('SELECT status FROM prostudio_media_outbox') == [('completed',)]


@pytest.mark.asyncio
async def test_graceful_stop_drains_current_storage_claim(monkeypatch):
    import asyncio
    import threading
    started = threading.Event();release = threading.Event();finished = []
    class Queue:
        def process(self,*args):
            started.set()
            assert release.wait(5)
            finished.append(True)
            return 'completed'
        def renew(self,*args):pass
    task = asyncio.create_task(main._run_media_outbox_claim(Queue(), {'job_id':'synthetic'}))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), 'Shutdown must wait for the current claimed persistence operation'
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished == [True]
    finally:
        release.set()
        await asyncio.gather(task,return_exceptions=True)
