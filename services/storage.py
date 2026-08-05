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
        import psycopg2
        with _registry_lock:
            conn = psycopg2.connect(DATABASE_URL)
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
    parts = [part for part in value.split("/") if part and part not in {".", ".."}]
    return "/".join(parts)


def generated_key(category: str, filename: str) -> str:
    return normalize_key(f"generated/{category}/{pathlib.Path(filename).name}")


def object_url(key: str) -> str:
    clean = normalize_key(key)
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in clean.split("/"))
    if r2_enabled():
        if R2_PUBLIC_BASE_URL:
            return f"{R2_PUBLIC_BASE_URL}/{encoded}"
        prefix = WEBAPP_URL if WEBAPP_URL else ""
        return f"{prefix}/api/public/storage/{encoded}"
    if clean.startswith("generated/"):
        return "/webapp/" + clean
    return "/webapp/generated/" + encoded


def key_from_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    path = urllib.parse.unquote(urllib.parse.urlparse(raw).path)
    marker = "/api/public/storage/"
    if marker in path:
        return normalize_key(path.split(marker, 1)[1])
    if R2_PUBLIC_BASE_URL and raw.startswith(R2_PUBLIC_BASE_URL + "/"):
        return normalize_key(raw[len(R2_PUBLIC_BASE_URL) + 1 :])
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
        path = LOCAL_GENERATED_DIR.parent / clean
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
        target = LOCAL_GENERATED_DIR.parent / clean
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
    path = LOCAL_GENERATED_DIR.parent / clean
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
        path = LOCAL_GENERATED_DIR.parent / clean
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
    body = (LOCAL_GENERATED_DIR.parent / clean).open("rb")
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
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
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
