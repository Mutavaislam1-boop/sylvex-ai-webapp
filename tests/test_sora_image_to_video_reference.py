"""_call_sora built its multipart form from only model/prompt/size/seconds,
never reading body.get("start_image") - so an image-to-video Sora request
silently dropped the uploaded reference image and OpenAI generated a plain
text-to-video clip instead of animating the user's image."""
import services.video_router as video_router


class _FakeResponse:
    status_code = 200
    text = '{"id": "video_123", "status": "queued"}'


def test_sora_attaches_the_start_image_as_input_reference(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "sora-2")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)
    monkeypatch.setattr(video_router, "_read_media_bytes", lambda url, media_type: (b"fake-image-bytes", "image/png"))

    captured = {}

    def fake_request_form(url, headers, data, files=None):
        captured["data"] = data
        captured["files"] = files
        return _FakeResponse()

    monkeypatch.setattr(video_router, "_request_form", fake_request_form)

    payload = {"video_options": {"start_image": "https://example.com/frame.png"}}
    result = video_router._call_sora("sora_2", "a cat waking up", payload)

    assert "files" in captured, f"request must actually be sent, got: {result}"
    assert captured["files"] is not None, "reference image must be attached to the request"
    filename, content, mime_type = captured["files"]["input_reference"]
    assert content == b"fake-image-bytes"
    assert mime_type == "image/png"
    assert result.get("status") == "processing"


def test_sora_text_to_video_without_an_image_sends_no_files(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "sora-2")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_form(url, headers, data, files=None):
        captured["files"] = files
        return _FakeResponse()

    monkeypatch.setattr(video_router, "_request_form", fake_request_form)

    payload = {"video_options": {}}
    video_router._call_sora("sora_2", "a dog running in a field", payload)

    assert captured["files"] is None


def test_sora_returns_a_clear_error_when_the_reference_image_cannot_be_read(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "sora-2")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)
    monkeypatch.setattr(video_router, "_read_media_bytes", lambda url, media_type: (b"", ""))

    called = {"request_sent": False}

    def fake_request_form(*args, **kwargs):
        called["request_sent"] = True
        return _FakeResponse()

    monkeypatch.setattr(video_router, "_request_form", fake_request_form)

    payload = {"video_options": {"start_image": "https://example.com/broken.png"}}
    result = video_router._call_sora("sora_2", "a cat waking up", payload)

    assert result.get("ok") is False
    assert not called["request_sent"]
