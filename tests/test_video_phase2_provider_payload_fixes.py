"""Regression tests for the Pro Studio A-Z audit's Phase 2 provider-payload fixes.

Prior to this fix:
- _call_runway never sent any sound/audio field for any Runway model, and
  never sent end_image under any field name, despite several models
  declaring sound:True / end_image:True with working-looking UI toggles.
- kling_2_5_turbo declared end_image:True but was excluded from
  _kling_supports_last_frame()'s allowlist, so its end-frame image was
  silently dropped.
"""
import services.video_router as video_router


def _fake_response(body):
    class _Resp:
        status_code = 200
        text = "{}"
    return _Resp()


def test_runway_sends_generate_audio_only_when_model_supports_sound(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "veo3.1")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        return _fake_response(body)

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {
        "video_options": {
            "model": "runway_veo3_1",
            "sound": True,
            "start_image": "https://example.com/start.png",
            "duration": 8,
        }
    }
    video_router._call_runway("runway_veo3_1", "a cat", payload)
    assert captured["body"]["generate_audio"] is True


def test_runway_sends_end_image_as_prompt_image_array_with_last_position(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "seedance2")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        return _fake_response(body)

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {
        "video_options": {
            "model": "runway_seedance2",
            "start_image": "https://example.com/start.png",
            "end_image": "https://example.com/end.png",
            "duration": 5,
        }
    }
    video_router._call_runway("runway_seedance2", "a cat", payload)
    prompt_image = captured["body"]["promptImage"]
    assert isinstance(prompt_image, list)
    assert {"uri": "https://example.com/start.png", "position": "first"} in prompt_image
    assert {"uri": "https://example.com/end.png", "position": "last"} in prompt_image


def test_runway_omits_end_image_when_model_does_not_declare_support(monkeypatch):
    # runway_gen4_5 declares end_image:False - an end_image value must never
    # be sent even if somehow present in the payload.
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "gen4.5")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        return _fake_response(body)

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {
        "video_options": {
            "model": "runway_gen4_5",
            "start_image": "https://example.com/start.png",
            "end_image": "https://example.com/end.png",
            "duration": 5,
        }
    }
    video_router._call_runway("runway_gen4_5", "a cat", payload)
    assert captured["body"]["promptImage"] == "https://example.com/start.png"


def test_kling_2_5_turbo_end_frame_is_no_longer_dead_code():
    assert video_router._kling_supports_last_frame("kling-2.5-turbo") is True


def test_grok_call_includes_resolution_field(monkeypatch):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "grok-video-1")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_json(url, headers, body):
        captured["body"] = body
        return _fake_response(body)

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)

    payload = {"video_options": {"model": "grok_video", "resolution": "720p", "duration": 5}}
    video_router._call_grok("grok_video", "a rocket", payload)
    assert captured["body"]["resolution"] == "720p"
