"""Reference/edit video metadata and per-model limit checks.

Uploaded videos are probed once at upload time (the bytes are already in
memory) with the bundled ffmpeg, and the result is stored next to the file
as "<key>.probe.json". At generation time the server reads that sidecar and
checks it against the selected model's reference_inputs limits
(services/model_capabilities.py) - the same limits Pro Studio checks before
upload, so a client that skips its own check still cannot send a video the
model rejects. Videos without a sidecar (results of earlier generations,
uploads made before this existed) are only checked by extension.

No limit lives here: every number comes from the model's registry entry.
"""
import json
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.parse
from typing import Optional

PROBE_SUFFIX = ".probe.json"

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_SIZE_RE = re.compile(r"Stream #\S+.*?Video:.*?\b(\d{2,5})x(\d{2,5})\b")
_ROTATION_RE = re.compile(r"(?:displaymatrix: rotation of|rotate\s*:)\s*(-?\d+(?:\.\d+)?)")


def _ffmpeg_binary() -> str:
    import shutil
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return str(imageio_ffmpeg.get_ffmpeg_exe() or "")
    except Exception:
        return ""


def parse_ffmpeg_info(stderr: str) -> dict:
    """Duration and display width/height from `ffmpeg -i` output. A 90/270
    degree display rotation (phone portrait clips) swaps width and height,
    because providers judge the frame as it is shown."""
    meta: dict = {}
    duration = _DURATION_RE.search(stderr or "")
    if duration:
        hours, minutes, seconds = duration.groups()
        meta["duration"] = round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)
    size = _VIDEO_SIZE_RE.search(stderr or "")
    if size:
        width, height = int(size.group(1)), int(size.group(2))
        rotation = _ROTATION_RE.search(stderr or "")
        if rotation and round(abs(float(rotation.group(1)))) % 180 == 90:
            width, height = height, width
        meta["width"], meta["height"] = width, height
    return meta


def probe_video_bytes(content: bytes, suffix: str) -> Optional[dict]:
    """{"duration", "width", "height", "bytes", "extension"} for an uploaded
    video, or None when ffmpeg is unavailable or cannot read it (the upload
    is then accepted exactly as before; only the extension/size checks
    apply later)."""
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg or not content:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=suffix or ".mp4", delete=False)
    try:
        handle.write(content)
        handle.close()
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-protocol_whitelist", "file", "-i", handle.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30, check=False,
        )
        meta = parse_ffmpeg_info((completed.stderr or b"").decode("utf-8", "ignore"))
    except Exception as exc:
        print("VIDEO PROBE FAILED:", type(exc).__name__)
        return None
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    if not meta:
        return None
    meta["bytes"] = len(content)
    meta["extension"] = (suffix or "").lower()
    return meta


def url_extension(url: str) -> str:
    path = urllib.parse.urlparse(str(url or "")).path
    return pathlib.PurePosixPath(path).suffix.lower()


def _fmt(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def reference_video_limit_error(limits, meta: dict, *, orientation: str = "image") -> Optional[str]:
    """First limit the video breaks for this model, or None. `limits` is the
    model's ReferenceInputLimits; checks that have no value in the registry
    are skipped, so a model with no known limit is never restricted here."""
    if limits is None:
        return None
    extension = str(meta.get("extension") or "").lower()
    allowed = tuple(str(ext).lower() for ext in (limits.video_extensions or ()))
    if allowed and extension and extension not in allowed:
        return "Reference video must be " + "/".join(ext.lstrip(".").upper() for ext in allowed) + " for the selected model"
    size = meta.get("bytes")
    if limits.video_max_bytes and isinstance(size, (int, float)) and size > limits.video_max_bytes:
        return f"Reference video must be at most {limits.video_max_bytes // (1024 * 1024)} MB for the selected model"
    duration = meta.get("duration")
    max_seconds = limits.video_max_seconds
    by_orientation = limits.video_max_seconds_by_orientation or {}
    key = str(orientation or "image").lower()
    if key in by_orientation:
        max_seconds = by_orientation[key]
    if isinstance(duration, (int, float)) and duration > 0:
        too_short = limits.video_min_seconds is not None and duration < limits.video_min_seconds
        too_long = max_seconds is not None and duration > max_seconds
        if too_short or too_long:
            low = _fmt(limits.video_min_seconds) if limits.video_min_seconds is not None else "0"
            high = _fmt(max_seconds) if max_seconds is not None else "any"
            return f"Reference video must be {low}-{high} seconds for the selected model (got {_fmt(round(duration, 2))} s)"
    width, height = meta.get("width"), meta.get("height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        for side in (width, height):
            if (limits.video_min_px is not None and side < limits.video_min_px) or (limits.video_max_px is not None and side > limits.video_max_px):
                low = limits.video_min_px if limits.video_min_px is not None else 0
                high = limits.video_max_px if limits.video_max_px is not None else "any"
                return f"Reference video width and height must be {low}-{high} px for the selected model (got {width}x{height})"
        ratio = width / height
        if (limits.video_min_ratio is not None and ratio < limits.video_min_ratio) or (limits.video_max_ratio is not None and ratio > limits.video_max_ratio):
            low = _fmt(limits.video_min_ratio) if limits.video_min_ratio is not None else "0"
            high = _fmt(limits.video_max_ratio) if limits.video_max_ratio is not None else "any"
            return f"Reference video aspect ratio must be {low}-{high} for the selected model (got {width}x{height})"
        if limits.video_max_area is not None and width * height > limits.video_max_area:
            return f"Reference video frame area must be at most {limits.video_max_area} px for the selected model (got {width}x{height})"
    return None


def sidecar_key(object_key: str) -> str:
    return f"{object_key}{PROBE_SUFFIX}"


def encode_sidecar(meta: dict) -> bytes:
    return json.dumps(meta, separators=(",", ":")).encode("utf-8")


def decode_sidecar(raw: bytes) -> Optional[dict]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Structured record of every rejected video-reference request, so the next
# occurrence of an unexplained limit (e.g. the reported "3-1000 seconds")
# shows where it came from: SYLVEX validation, upload, or the provider.

_URL_RE = re.compile(r"https?://\S+|data:[^\s,]+,[A-Za-z0-9+/=]+")
_SECRET_RE = re.compile(r"(?i)(bearer\s+|bot)[A-Za-z0-9:_\-\.]{12,}|\b(sk|key|token|secret)[-_][A-Za-z0-9_\-]{8,}|\b[A-Za-z0-9_\-]{40,}\b")


def sanitize_provider_message(message, limit: int = 300) -> str:
    """Provider error text safe for logs: URLs (Telegram file URLs embed the
    bot token), bearer tokens and key-like strings removed, length capped."""
    text = str(message or "")
    text = _URL_RE.sub("<url>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    text = " ".join(text.split())
    return text[:limit]


def log_video_reference_event(entry_point: str, *, model: str = "", provider: str = "", meta: Optional[dict] = None,
                              validation: Optional[str] = None, provider_status=None, provider_error_code=None,
                              provider_error=None, inputs: Optional[dict] = None) -> dict:
    meta = meta or {}
    record = {
        "entry_point": entry_point,
        "model": model or "",
        "provider": provider or "",
        "inputs": inputs or {},
        "duration": meta.get("duration"),
        "bytes": meta.get("bytes"),
        "container": meta.get("extension") or "",
        "mime": meta.get("mime") or "",
        "width": meta.get("width"),
        "height": meta.get("height"),
        "sylvex_validation": validation or "passed",
        "provider_http_status": provider_status,
        "provider_error_code": sanitize_provider_message(provider_error_code, 80) if provider_error_code not in (None, "") else None,
        "provider_error": sanitize_provider_message(provider_error) if provider_error else None,
    }
    print("VIDEO_REFERENCE_REJECTED:", json.dumps(record, ensure_ascii=False, default=str))
    return record
