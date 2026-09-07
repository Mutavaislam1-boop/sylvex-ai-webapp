"""Shared object storage for SYLVEX.

Production uses Cloudflare R2 through its S3-compatible API. Development falls
back to webapp/generated when the required R2 variables are not configured.
"""
from __future__ import annotations

import mimetypes
import os
import pathlib
import tempfile
import threading
import urllib.parse
from functools import lru_cache
from typing import BinaryIO, Iterator, Optional

from dotenv import load_dotenv
from db_pool import db_connect
from services.safe_io import safe_local_path
from services.security import SecurityError
from services.media_access import sign_media_url


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
LOCAL_GENERATED_DIR = ROOT_DIR / "webapp" / "generated"
load_dotenv(ROOT_DIR / ".env")


def _env(name: str) -> str:
    return str(os.getenv(name) or "").strip().replace("\u2028", "").replace("\ufeff", "")


R2_BUCKET = _env("R2_BUCKET")
R2_ENDPOINT = _env("R2_ENDPOINT").rstrip("/")
R2_ACCESS_KEY_ID = _env("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = _env("R2_SECRET_ACCESS_KEY")
R2_PUBLIC_BASE_URL = _env("R2_PUBLIC_BASE_URL").rstrip("/")
WEBAPP_URL = _env("WEBAPP_URL").rstrip("/")
DATABASE_URL = _env("DATABASE_PUBLIC_URL") or _env("DATABASE_URL")
_registry_lock = threading.Lock()
_registry_ready = False


def _record_object(key: str, url: str, content_type: str, size: int) -> None:
    global _registry_ready
    if not DATABASE_URL:
        return
    try:
        with _registry_lock:
            conn = db_connect(DATABASE_URL)
            cursor = conn.cursor()
            if not _registry_ready:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sylvex_storage_objects (
                        object_key TEXT PRIMARY KEY,
                        file_url TEXT NOT NULL,
                        content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                        size_bytes BIGINT NOT NULL DEFAULT 0,
                        storage_backend TEXT NOT NULL DEFAULT 'r2',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                _registry_ready = True
            cursor.execute("""
                INSERT INTO sylvex_storage_objects
                    (object_key, file_url, content_type, size_bytes, storage_backend, updated_at)
                VALUES (%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (object_key) DO UPDATE SET
                    file_url=EXCLUDED.file_url,
                    content_type=EXCLUDED.content_type,
                    size_bytes=EXCLUDED.size_bytes,
                    storage_backend=EXCLUDED.storage_backend,
                    updated_at=NOW()
            """, (key, url, content_type, int(size or 0), "r2" if r2_enabled() else "local"))
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as exc:
        print("STORAGE REGISTRY WRITE FAILED:", type(exc).__name__)


def r2_enabled() -> bool:
    return bool(R2_BUCKET and R2_ENDPOINT and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


@lru_cache(maxsize=1)
def r2_client():
    if not r2_enabled():
        return None
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
    )


def normalize_key(key: str) -> str:
    value = urllib.parse.unquote(str(key or "")).replace("\\", "/").lstrip("/")
    if any(part.startswith(".") for part in value.split("/") if part):
        raise SecurityError("invalid_storage_key", 400)
    parts = [part for part in value.split("/") if part]
    return "/".join(parts)


def generated_key(category: str, filename: str) -> str:
    return normalize_key(f"generated/{category}/{pathlib.Path(filename).name}")


def object_url(key: str) -> str:
    clean = normalize_key(key)
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in clean.split("/"))
    # Application proxy enforces expiry even when R2 is configured.
    if r2_enabled():
        return sign_media_url(f"{WEBAPP_URL}/api/public/storage/{encoded}")
    return sign_media_url("/webapp/" + encoded if clean.startswith("generated/") else "/webapp/generated/" + encoded)


def key_from_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.netloc:
        allowed = {urllib.parse.urlparse(base).netloc for base in (R2_PUBLIC_BASE_URL, WEBAPP_URL, _env("LEGACY_R2_PUBLIC_BASE_URL")) if base}
        if parsed.netloc not in allowed:
            return ""
    path = urllib.parse.unquote(parsed.path)
    marker = "/api/public/storage/"
    if marker in path:
        return normalize_key(path.split(marker, 1)[1])
    for base in (R2_PUBLIC_BASE_URL, _env("LEGACY_R2_PUBLIC_BASE_URL").rstrip("/")):
        if base and raw.startswith(base + "/"):
            return normalize_key(urllib.parse.urlparse(raw[len(base) + 1:]).path)
    if path.startswith("/webapp/generated/"):
        return normalize_key(path[len("/webapp/") :])
    if path.startswith("/generated/"):
        return normalize_key(path.lstrip("/"))
    return ""


def put_bytes(data: bytes, key: str, content_type: str = "", cache_control: str = "public, max-age=31536000, immutable") -> str:
    clean = normalize_key(key)
    if not clean or not data:
        return ""
    mime = content_type or mimetypes.guess_type(clean)[0] or "application/octet-stream"
    if r2_enabled():
        r2_client().put_object(Bucket=R2_BUCKET, Key=clean, Body=data, ContentType=mime, CacheControl=cache_control)
    else:
        path = safe_local_path(LOCAL_GENERATED_DIR.parent, clean)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    url = object_url(clean)
    _record_object(clean, url, mime, len(data))
    return url


def put_file(path: pathlib.Path | str, key: str, content_type: str = "", remove_local: bool = False) -> str:
    source = pathlib.Path(path)
    clean = normalize_key(key)
    mime = content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    try:
        if r2_enabled():
            with source.open("rb") as handle:
                r2_client().upload_fileobj(handle, R2_BUCKET, clean, ExtraArgs={"ContentType": mime, "CacheControl": "public, max-age=31536000, immutable"})
            url = object_url(clean)
            _record_object(clean, url, mime, source.stat().st_size)
            return url
        target = safe_local_path(LOCAL_GENERATED_DIR.parent, clean)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())
        url = object_url(clean)
        _record_object(clean, url, mime, source.stat().st_size)
        return url
    finally:
        if remove_local and r2_enabled():
            source.unlink(missing_ok=True)


def get_object(key: str) -> tuple[BinaryIO, str, Optional[int]]:
    clean = key_from_url(key) or normalize_key(key)
    if r2_enabled():
        response = r2_client().get_object(Bucket=R2_BUCKET, Key=clean)
        return response["Body"], response.get("ContentType") or mimetypes.guess_type(clean)[0] or "application/octet-stream", response.get("ContentLength")
    path = safe_local_path(LOCAL_GENERATED_DIR.parent, clean)
    return path.open("rb"), mimetypes.guess_type(path.name)[0] or "application/octet-stream", path.stat().st_size


def iter_object(body: BinaryIO, chunk_size: int = 1024 * 1024, max_bytes: Optional[int] = None) -> Iterator[bytes]:
    remaining = max_bytes
    try:
        while True:
            if remaining is not None and remaining <= 0:
                break
            chunk = body.read(min(chunk_size, remaining) if remaining is not None else chunk_size)
            if not chunk:
                break
            yield chunk
            if remaining is not None:
                remaining -= len(chunk)
    finally:
        body.close()


def get_object_range(key: str, range_header: str = "") -> tuple[BinaryIO, str, int, int, int, int]:
    clean = key_from_url(key) or normalize_key(key)
    mime = mimetypes.guess_type(clean)[0] or "application/octet-stream"
    if r2_enabled():
        head = r2_client().head_object(Bucket=R2_BUCKET, Key=clean)
        total = int(head.get("ContentLength") or 0)
        mime = head.get("ContentType") or mime
    else:
        path = safe_local_path(LOCAL_GENERATED_DIR.parent, clean)
        total = path.stat().st_size
    start, end = 0, max(0, total - 1)
    if range_header.startswith("bytes="):
        raw_start, _, raw_end = range_header[6:].partition("-")
        if raw_start:
            start = min(max(0, int(raw_start)), max(0, total - 1))
        if raw_end:
            end = min(max(start, int(raw_end)), max(0, total - 1))
    length = max(0, end - start + 1)
    if r2_enabled():
        response = r2_client().get_object(Bucket=R2_BUCKET, Key=clean, Range=f"bytes={start}-{end}")
        return response["Body"], response.get("ContentType") or mime, length, total, start, end
    body = (safe_local_path(LOCAL_GENERATED_DIR.parent, clean)).open("rb")
    body.seek(start)
    return body, mime, length, total, start, end


def read_bytes(key_or_url: str) -> bytes:
    key = key_from_url(key_or_url) or normalize_key(key_or_url)
    body, _, _ = get_object(key)
    try:
        return body.read()
    finally:
        body.close()


def delete(key_or_url: str) -> bool:
    key = key_from_url(key_or_url) or normalize_key(key_or_url)
    if not key:
        return False
    if r2_enabled():
        r2_client().delete_object(Bucket=R2_BUCKET, Key=key)
    else:
        (LOCAL_GENERATED_DIR.parent / key).unlink(missing_ok=True)
    if DATABASE_URL:
        try:
            conn = db_connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sylvex_storage_objects WHERE object_key=%s", (key,))
            conn.commit(); cursor.close(); conn.close()
        except Exception:
            pass
    return True


def exists(key_or_url: str) -> bool:
    key = key_from_url(key_or_url) or normalize_key(key_or_url)
    try:
        if r2_enabled():
            r2_client().head_object(Bucket=R2_BUCKET, Key=key)
            return True
        return (LOCAL_GENERATED_DIR.parent / key).is_file()
    except Exception:
        return False


def temporary_file_from_url(url: str, suffix: str = "") -> pathlib.Path:
    data = read_bytes(url)
    handle = tempfile.NamedTemporaryFile(prefix="sylvex-", suffix=suffix, delete=False)
    try:
        handle.write(data)
        return pathlib.Path(handle.name)
    finally:
        handle.close()
