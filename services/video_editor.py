"""Server side of the SYLVEX Video Editor (Quick Access → Video).

The editor's project format is SYLVEX-owned (webapp/js/video-editor/
project.js). This module stores those projects, measures media for
pricing, and provides the editing transcript (timestamped speech) through
OpenAI transcription. No editing-engine (IMG.LY) data lives here.
"""
from __future__ import annotations

import json
import math
import os
import re
import secrets
import subprocess
import tempfile
import uuid
from decimal import Decimal, ROUND_CEILING
from typing import Optional

import requests

from services import video_probe
from services.media_access import sign_media_url
from services.safe_io import safe_get
from services.storage import generated_key, key_from_url, put_bytes as storage_put_bytes, read_bytes as storage_read_bytes

PROJECT_SCHEMA = "sylvex.video-project"
PROJECT_ID_RE = re.compile(r"project_[A-Za-z0-9_]{4,80}")
SHARE_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,64}")
MAX_PROJECT_BYTES = 4 * 1024 * 1024
MAX_MEDIA_BYTES = 200 * 1024 * 1024
MEDIA_KINDS = {"video", "audio", "image"}

# --------------------------------------------------------------- pricing
# SYLVEX rule: provider cost + 50%, in credits (1 credit = $0.01), rounded up.
MARKUP = Decimal("1.5")


def sylvex_credits(cost_usd: Decimal) -> int:
    return int((Decimal(cost_usd) * MARKUP * 100).to_integral_value(rounding=ROUND_CEILING))


# Runway video upscaler (model magnific_video_upscaler_creative), billed by
# Runway per output frame: 0.7 credits at 720p/1K, 0.9 at 2K, 1.2 at 4K
# ($0.01 per Runway credit). Overridable when Runway changes its rates.
ENHANCE_RATES = {
    "720p": Decimal(os.getenv("RUNWAY_UPSCALE_USD_PER_FRAME_720P") or "0.007"),
    "1k": Decimal(os.getenv("RUNWAY_UPSCALE_USD_PER_FRAME_1K") or "0.007"),
    "2k": Decimal(os.getenv("RUNWAY_UPSCALE_USD_PER_FRAME_2K") or "0.009"),
    "4k": Decimal(os.getenv("RUNWAY_UPSCALE_USD_PER_FRAME_4K") or "0.012"),
}
# Output presets by their short side, smallest first.
ENHANCE_PRESETS = (("720p", 720), ("1k", 1080), ("2k", 1440), ("4k", 2160))
# What the editor offers: the user picks a result, never a resolution code.
ENHANCE_LEVELS = {
    "clean": {"label": "Очистка", "hint": "Чище картинка, разрешение как у исходника"},
    "2x": {"label": "Улучшение ×2", "hint": "Вдвое больше деталей и разрешения"},
    "4k": {"label": "Максимум 4K", "hint": "Самое высокое качество"},
}
ENHANCE_MAX_SECONDS = max(1, int(os.getenv("VIDEO_ENHANCE_MAX_SECONDS") or 20))
# OpenAI whisper-1: $0.006 per minute of audio.
TRANSCRIBE_USD_PER_MINUTE = Decimal(os.getenv("OPENAI_TRANSCRIBE_USD_PER_MINUTE") or "0.006")
TRANSCRIBE_MAX_SECONDS = 30 * 60


def enhance_resolution(level: str, width, height) -> str:
    """Runway output preset for an editor level and the source size."""
    if level not in ENHANCE_LEVELS:
        return ""
    if level == "4k":
        return "4k"
    try:
        side = min(int(width or 0), int(height or 0))
    except (TypeError, ValueError):
        side = 0
    if side <= 0:
        return ""
    target = side * (2 if level == "2x" else 1)
    for name, size in ENHANCE_PRESETS:
        if size >= target:
            return name
    return "4k"


def enhance_cost_info(meta: dict, level: str) -> dict:
    """Price of enhancing a video measured by the server (duration, fps,
    size): Runway's per-output-frame rate for the chosen preset + 50%."""
    meta = meta or {}
    resolution = enhance_resolution(level, meta.get("width"), meta.get("height"))
    rate = ENHANCE_RATES.get(resolution)
    duration = float(meta.get("duration") or 0)
    fps = float(meta.get("fps") or 0)
    if rate is None or duration <= 0 or fps <= 0:
        return {"credits": 0, "cost_usd": 0, "generation_cost": "", "pricing_available": False}
    frames = math.ceil(duration * fps)
    cost = rate * frames
    credits = sylvex_credits(cost)
    return {"credits": credits, "cost_credits": credits, "cost_usd": float(cost * MARKUP), "provider_cost_usd": float(cost),
            "generation_cost": f"{credits} ⚡", "pricing_available": True, "frames": frames, "level": level,
            "resolution": resolution, "model_label": "SYLVEX Enhance"}


def transcribe_credits(duration_seconds: float) -> int:
    minutes = Decimal(str(max(0.0, float(duration_seconds or 0)))) / Decimal(60)
    return max(1, sylvex_credits(TRANSCRIBE_USD_PER_MINUTE * minutes))


# ----------------------------------------------------------------- media

def _ffmpeg() -> str:
    return video_probe._ffmpeg_binary()


def load_media_bytes(url: str, max_bytes: int = MAX_MEDIA_BYTES) -> bytes:
    """Bytes of a project media file: SYLVEX storage first, otherwise a
    guarded HTTPS download (no private network targets)."""
    key = key_from_url(url)
    if key:
        return storage_read_bytes(key)
    if not str(url or "").startswith("https://"):
        raise ValueError("media_url_not_allowed")
    response = safe_get(url, timeout=90, max_bytes=max_bytes)
    if response.status_code >= 400:
        raise ValueError("media_download_failed")
    return response.content


def probe_media(content: bytes, suffix: str = ".mp4") -> dict:
    ffmpeg = _ffmpeg()
    if not ffmpeg or not content:
        return {}
    handle = tempfile.NamedTemporaryFile(suffix=suffix or ".mp4", delete=False)
    try:
        handle.write(content)
        handle.close()
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-protocol_whitelist", "file", "-i", handle.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60, check=False,
        )
        stderr = (completed.stderr or b"").decode("utf-8", "ignore")
        meta = video_probe.parse_ffmpeg_info(stderr)
        meta.update(video_probe.parse_ffmpeg_stream_info(stderr))
        return meta
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def probe_media_url(url: str) -> dict:
    content = load_media_bytes(url)
    return probe_media(content, video_probe.url_extension(url) or ".mp4")


def cut_video_segment(content: bytes, suffix: str, start: float, end: Optional[float]) -> bytes:
    """Frame-accurate H.264/AAC MP4 of [start, end) of a video."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_unavailable")
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, "source" + (suffix or ".mp4"))
        target = os.path.join(folder, "segment.mp4")
        with open(source, "wb") as handle:
            handle.write(content)
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file", "-y",
                   "-ss", f"{max(0.0, start):.3f}", "-i", source]
        if end is not None:
            command += ["-t", f"{max(0.1, end - start):.3f}"]
        command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", target]
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600, check=False)
        if completed.returncode != 0 or not os.path.exists(target):
            raise RuntimeError("video_cut_failed")
        with open(target, "rb") as handle:
            return handle.read()


def prepare_enhance_source(url: str, start=None, end=None) -> dict:
    """Measures the clip to enhance on the server (the price depends on its
    real duration, frame rate and size) and, when only part of the file is
    used on the timeline, cuts exactly that part so only it is enhanced and
    paid for. Returns {url, meta, start, end}; raises ValueError(code)."""
    content = load_media_bytes(url)
    suffix = video_probe.url_extension(url) or ".mp4"
    meta = probe_media(content, suffix)
    duration = float(meta.get("duration") or 0)
    if duration <= 0 or not meta.get("width") or not meta.get("fps"):
        raise ValueError("enhance_source_unreadable")
    try:
        begin = min(max(0.0, float(start or 0)), duration)
        finish = min(max(begin, float(duration if end in (None, "") else end)), duration)
    except (TypeError, ValueError):
        raise ValueError("enhance_source_unreadable")
    if finish - begin < 0.5:
        raise ValueError("enhance_segment_too_short")
    if finish - begin > ENHANCE_MAX_SECONDS + 0.05:
        raise ValueError("enhance_too_long")
    whole = begin <= 0.05 and finish >= duration - 0.05
    if whole and suffix in {".mp4", ".mov", ".m4v"}:
        return {"url": url, "meta": meta, "start": 0.0, "end": duration}
    segment = cut_video_segment(content, suffix, begin, None if whole else finish)
    segment_meta = probe_media(segment, ".mp4")
    if not float(segment_meta.get("duration") or 0) or not segment_meta.get("fps"):
        raise ValueError("enhance_source_unreadable")
    stored = storage_put_bytes(segment, generated_key("video-inputs", f"{uuid.uuid4().hex}.mp4"), "video/mp4")
    return {"url": stored, "meta": segment_meta, "start": round(begin, 3), "end": round(finish, 3)}


def estimate_enhance(url: str, start=None, end=None) -> dict:
    """Prices of every level, shown before the user confirms; the job
    re-measures the exact cut it enhances."""
    content = load_media_bytes(url)
    meta = probe_media(content, video_probe.url_extension(url) or ".mp4")
    duration = float(meta.get("duration") or 0)
    if duration <= 0 or not meta.get("fps"):
        raise ValueError("enhance_source_unreadable")
    try:
        begin = min(max(0.0, float(start or 0)), duration)
        finish = min(max(begin, float(duration if end in (None, "") else end)), duration)
    except (TypeError, ValueError):
        raise ValueError("enhance_source_unreadable")
    if finish - begin < 0.5:
        raise ValueError("enhance_segment_too_short")
    if finish - begin > ENHANCE_MAX_SECONDS + 0.05:
        raise ValueError("enhance_too_long")
    segment = dict(meta, duration=finish - begin)
    levels = []
    for level, info in ENHANCE_LEVELS.items():
        cost = enhance_cost_info(segment, level)
        if cost.get("pricing_available"):
            levels.append({"id": level, "label": info["label"], "hint": info["hint"], "credits": cost["credits"],
                           "resolution": cost["resolution"], "frames": cost["frames"]})
    return {"duration": round(finish - begin, 3), "fps": meta.get("fps"), "width": meta.get("width"),
            "height": meta.get("height"), "levels": levels}


def extract_speech_audio(content: bytes, suffix: str) -> bytes:
    """Mono 16 kHz MP3 of the speech track (small enough for the provider's
    25 MB limit for long recordings)."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_unavailable")
    with tempfile.TemporaryDirectory() as folder:
        source = os.path.join(folder, "source" + (suffix or ".mp4"))
        target = os.path.join(folder, "speech.mp3")
        with open(source, "wb") as handle:
            handle.write(content)
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file", "-y", "-i", source,
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "mp3", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300, check=False,
        )
        if completed.returncode != 0 or not os.path.exists(target):
            raise RuntimeError("audio_extract_failed")
        with open(target, "rb") as handle:
            return handle.read()


def transcribe_segments(audio: bytes, api_key: str, api_base: str, language: str = "") -> dict:
    """Timestamped speech segments from OpenAI (verbose_json, segment level)."""
    data = {
        "model": os.getenv("OPENAI_TRANSCRIBE_SEGMENTS_MODEL", "whisper-1"),
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
    }
    if language and re.fullmatch(r"[a-z]{2}", language):
        data["language"] = language
    response = requests.post(
        f"{api_base}/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("speech.mp3", audio, "audio/mpeg")},
        data=data,
        timeout=300,
    )
    if response.status_code >= 400:
        return {"ok": False, "error": f"transcription_failed:{response.status_code}"}
    payload = response.json()
    segments = []
    for item in payload.get("segments") or []:
        try:
            start, end = float(item.get("start")), float(item.get("end"))
        except (TypeError, ValueError):
            continue
        text = str(item.get("text") or "").strip()
        if text and end > start:
            segments.append({"start": round(start, 2), "end": round(end, 2), "text": text[:500]})
    return {"ok": True, "segments": segments, "language": str(payload.get("language") or ""), "duration": float(payload.get("duration") or 0)}


# --------------------------------------------------------------- projects

def _safe_url(value) -> bool:
    return isinstance(value, str) and (value == "" or (value.startswith(("https://", "http://", "/")) and not value.startswith("//")))


def validate_project(project_id: str, project) -> str:
    if not PROJECT_ID_RE.fullmatch(str(project_id or "")):
        raise ValueError("invalid_video_project")
    if not isinstance(project, dict) or project.get("schema") != PROJECT_SCHEMA or project.get("id") != project_id:
        raise ValueError("invalid_video_project")
    try:
        encoded = json.dumps(project, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("invalid_video_project")
    if len(encoded.encode()) > MAX_PROJECT_BYTES:
        raise ValueError("video_project_too_large")
    media = project.get("media")
    if not isinstance(media, dict) or len(media) > 300:
        raise ValueError("invalid_video_project")
    for item in media.values():
        if not isinstance(item, dict) or item.get("kind") not in MEDIA_KINDS:
            raise ValueError("invalid_video_media")
        for field in ("url", "poster"):
            if not _safe_url(item.get(field, "")):
                raise ValueError("invalid_video_media_url")
    for key, limit in (("videoClips", 300), ("audioClips", 300), ("texts", 500)):
        if not isinstance(project.get(key), list) or len(project[key]) > limit:
            raise ValueError("invalid_video_project")
    return encoded


def _refresh_media_urls(project: dict) -> dict:
    for item in (project.get("media") or {}).values():
        if isinstance(item, dict):
            for field in ("url", "poster"):
                if item.get(field):
                    item[field] = sign_media_url(item[field])
    return project


def _preview(project: dict) -> str:
    for clip in project.get("videoClips") or []:
        media = (project.get("media") or {}).get(clip.get("mediaId")) or {}
        if media.get("poster"):
            return media["poster"]
        if media.get("kind") == "image" and media.get("url"):
            return media["url"]
    return ""


def save_project(connect, owner: int, project_id: str, project: dict) -> str:
    encoded = validate_project(project_id, project)
    title = str(project.get("name") or "Видеопроект")[:160]
    preview = _preview(project)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO prostudio_video_projects
                (telegram_id, id, title, preview_url, share_token, state_json)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (telegram_id, id) DO UPDATE SET
                  title=EXCLUDED.title, preview_url=EXCLUDED.preview_url,
                  state_json=EXCLUDED.state_json, updated_at=NOW()
                RETURNING share_token""", (owner, project_id, title, preview, secrets.token_urlsafe(24), encoded))
            row = cur.fetchone()
    return row[0] if row else ""


def list_projects(connect, owner: int, limit: int = 30) -> list:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, title, preview_url, updated_at FROM prostudio_video_projects
                WHERE telegram_id=%s ORDER BY updated_at DESC, id LIMIT %s""", (owner, max(1, min(int(limit or 30), 100))))
            return [{"id": row[0], "title": row[1], "preview_url": sign_media_url(row[2]) if row[2] else "",
                     "updated_at": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3]} for row in cur.fetchall()]


def get_project(connect, owner: int, project_id: str, token: str = "") -> Optional[dict]:
    """The owner's project, or any project when its share token matches (the
    "Open in browser" link from Telegram)."""
    if not PROJECT_ID_RE.fullmatch(str(project_id or "")):
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            if token and SHARE_TOKEN_RE.fullmatch(token):
                cur.execute("""SELECT state_json, share_token, telegram_id FROM prostudio_video_projects
                    WHERE id=%s AND share_token=%s ORDER BY updated_at DESC LIMIT 1""", (project_id, token))
            else:
                cur.execute("""SELECT state_json, share_token, telegram_id FROM prostudio_video_projects
                    WHERE telegram_id=%s AND id=%s""", (owner, project_id))
            row = cur.fetchone()
    if not row:
        return None
    project = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return {"project": _refresh_media_urls(project), "shareToken": row[1] if int(row[2]) == int(owner) else "", "owner": int(row[2]) == int(owner)}


def delete_project(connect, owner: int, project_id: str) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prostudio_video_projects WHERE telegram_id=%s AND id=%s", (owner, project_id))
            return cur.rowcount > 0
