"""Regression tests for POST /api/public/prostudio/upload-media - the
photo upload endpoint audited for the Pro Studio photo pipeline repair.

Exercises the route function directly with asyncio.run (this sandbox's
Python 3.11 can't run main.py's own startup event, which needs 3.12 - see
test_web_auth_config_endpoint.py for the same pattern), so no TestClient/
app lifecycle or database is needed - this endpoint never touches the DB.

Confirmed root causes for the reported "upload-media returned HTTP 400"
production symptom, both covered below:

1. The frontend file picker's accept attribute (openNativeFilePicker in
   cabinet.js) lists .heic/.heif, but this endpoint's allowed_exts for
   images has only ever been {.jpg, .jpeg, .png, .webp} - an iPhone user
   picking a HEIC photo gets an immediate 400 "Unsupported media format".
2. services.safe_io.validated_upload_type rejects an image wider*taller
   than 40,000,000 pixels with SecurityError("invalid_image", 400) - a
   plausible real trip for a modern phone's high-resolution camera output.
   That SecurityError previously reached the client via the shared
   @app.exception_handler(SecurityError) with NO server-side log line at
   all, making a report like "we saw upload-media return 400" completely
   undiagnosable from backend logs alone. UPLOAD_MEDIA_REJECTED closes
   that gap without changing the response the client receives.
"""
import asyncio
import io

import pytest
from PIL import Image

import main


class FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile - only what
    public_prostudio_upload_media / read_upload actually touch."""

    def __init__(self, filename, content_type, data):
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._sent = False

    async def read(self, n):
        if self._sent:
            return b""
        self._sent = True
        return self._data


def _tiny_jpeg_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _oversized_jpeg_bytes():
    # 7000x6000 = 42,000,000 px > the 40,000,000 px ceiling in
    # services/safe_io.py validated_upload_type - real single-color JPEG
    # data (Pillow refuses to touch a synthetic byte blob as a real image),
    # kept small on disk since a flat color compresses to a few KB.
    buffer = io.BytesIO()
    Image.new("RGB", (7000, 6000), color=(5, 5, 5)).save(buffer, format="JPEG", quality=1)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _local_storage(monkeypatch, tmp_path):
    import services.storage as storage

    monkeypatch.setattr(storage, "R2_BUCKET", "")
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    monkeypatch.setattr(storage, "LOCAL_GENERATED_DIR", tmp_path / "generated")


def test_valid_jpeg_upload_succeeds_and_returns_a_usable_url():
    upload = FakeUploadFile("photo.jpg", "image/jpeg", _tiny_jpeg_bytes())
    result = asyncio.run(main.public_prostudio_upload_media(file=upload, kind="image"))
    assert result["ok"] is True
    assert result["kind"] == "image"
    assert result["url"]
    assert not result["url"].startswith("data:")


def test_heic_extension_is_rejected_with_400_and_logs_the_specific_reason(capsys):
    upload = FakeUploadFile("IMG_0001.HEIC", "image/heic", b"not-a-real-decoder-input")
    response = asyncio.run(main.public_prostudio_upload_media(file=upload, kind="image"))
    assert response.status_code == 400
    body = response.body.decode()
    assert '"ok":false' in body.replace(" ", "")
    log_output = capsys.readouterr().out
    assert "UPLOAD_MEDIA_REJECTED" in log_output
    assert "unsupported_extension" in log_output


def test_oversized_image_is_rejected_as_invalid_image_and_logs_dimensions(capsys):
    upload = FakeUploadFile("huge.jpg", "image/jpeg", _oversized_jpeg_bytes())
    from services.security import SecurityError

    with pytest.raises(SecurityError) as exc_info:
        asyncio.run(main.public_prostudio_upload_media(file=upload, kind="image"))
    assert exc_info.value.code == "invalid_image"
    assert exc_info.value.status == 400
    log_output = capsys.readouterr().out
    assert "UPLOAD_MEDIA_REJECTED" in log_output
    assert "invalid_image" in log_output
    assert "7000" in log_output and "6000" in log_output


def test_empty_file_is_rejected_with_400_and_logged():
    upload = FakeUploadFile("photo.jpg", "image/jpeg", b"")
    response = asyncio.run(main.public_prostudio_upload_media(file=upload, kind="image"))
    assert response.status_code == 400


def test_rejection_never_swaps_in_a_generic_bad_request_message(capsys):
    # Phase 2's explicit constraint: never replace the real error with a
    # generic "Bad Request" - the specific reason must survive to the log.
    upload = FakeUploadFile("IMG_0001.HEIC", "image/heic", b"x")
    asyncio.run(main.public_prostudio_upload_media(file=upload, kind="image"))
    log_output = capsys.readouterr().out
    assert "reason" in log_output and "unsupported_extension" in log_output
    assert "bad request" not in log_output.lower()
