"""Run in Railway: python tests/r2_smoke_test.py"""
import pathlib
import sys
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from services.storage import delete, exists, generated_key, put_bytes, read_bytes, r2_enabled


def main() -> None:
    if not r2_enabled():
        raise SystemExit("R2 is not configured; smoke test aborted")
    payload = b"SYLVEX R2 upload/read/delete smoke test"
    key = generated_key("tests", f"smoke-{uuid4().hex}.txt")
    url = put_bytes(payload, key, "text/plain", "no-store")
    try:
        if not exists(key):
            raise RuntimeError("uploaded object is not visible in R2")
        if read_bytes(key) != payload:
            raise RuntimeError("downloaded object differs from uploaded payload")
        print({"ok": True, "bucket_object": key, "url": url, "read": True})
    finally:
        deleted = delete(key)
        print({"deleted": deleted, "still_exists": exists(key)})


if __name__ == "__main__":
    main()
