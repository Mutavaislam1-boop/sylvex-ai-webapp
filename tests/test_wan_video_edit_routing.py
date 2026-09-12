"""wan_2_7_edit's real provider model is Alibaba's dedicated video-editing
model (VACE, "wan2.1-vace-plus" by default) - a genuinely different model
family from wan2.6/wan2.7 text/image-to-video, not just a naming variant.
_call_wan's is_27 = provider_model.startswith("wan2.7") check was False
for this model's default provider model, so it fell into the
image-to-video branch, which discards the uploaded input_video and
requires a first-frame image this edit mode's UI never collects
(start_image is always false for it) - every real edit attempt failed
with "Wan image-to-video requires a first-frame image" even though a
video was uploaded."""
import services.video_router as video_router


def test_wan_2_7_edit_builds_a_video_edit_body_from_the_uploaded_video(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "wan2.1-vace-plus")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"output": {"task_id": "wan-edit-1", "task_status": "PENDING"}}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {
        "video_options": {
            "input_video": "https://example.com/source.mp4",
        },
    }
    result = video_router._call_wan("wan_2_7_edit", "make it look like winter", payload)

    assert "body" in captured, f"request must actually be sent, got error instead: {result}"
    body = captured["body"]
    assert body["model"] == "wan2.1-vace-plus"
    assert body["input"]["video_url"] == "https://example.com/source.mp4"
    assert "img_url" not in body["input"], "must not be routed through the image-to-video body"


def test_wan_2_7_edit_without_an_input_video_returns_a_clear_error(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "wan2.1-vace-plus")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    result = video_router._call_wan("wan_2_7_edit", "make it look like winter", {"video_options": {}})

    assert result.get("ok") is False
    # The user-facing "error" field goes through translate_provider_error,
    # which falls back to a generic localized message for detail strings it
    # doesn't recognize (same as the neighboring first-frame-image error) -
    # the original detail survives in "raw_error".
    assert "video" in (result.get("raw_error") or "").lower()


def test_wan_2_7_image_to_video_is_unaffected(monkeypatch):
    """Regular wan_2_7 image-to-video (not the edit variant) must keep
    routing through the is_27-with-media branch exactly as before."""
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "wan2.7-t2v")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        class _Resp:
            status_code = 200
            text = '{"output": {"task_id": "wan-i2v-1", "task_status": "PENDING"}}'
        return _Resp()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {"video_options": {"start_image": "https://example.com/frame.png"}}
    video_router._call_wan("wan_2_7", "a dog running", payload)

    body = captured["body"]
    assert body["model"] == video_router.os.getenv("WAN_2_7_I2V_MODEL", "wan2.7-i2v")
    assert body["input"]["media"][0]["type"] == "first_frame"
