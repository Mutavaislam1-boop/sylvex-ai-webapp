"""Regression tests for a batch of money bugs found in a full Pro Studio
diagnostic sweep (security findings from the same sweep turned out to be
false positives once services/security.py's global SecurityMiddleware was
accounted for - see the session notes - so no security fix/test is here):

1. Seedance 1.5 Pro was only priced for duration==5; every other offered
   duration (4,6,7,8,9,10,11,12) silently produced 0 credits.
2. MiniMax Hailuo 2.3's price table was keyed on duration 6, but the model's
   only real short option (and default) is 5 - also 0 credits.
3. Kling 3.0 Turbo is billed unconditionally at the native_audio tier (its
   only tier), but the actual submit settings never requested audio from
   Kling, so the user paid for sound they never received.
4. FLUX.2 / FLUX.2 Turbo advertise simultaneous Character+Object reference
   support but only ever forwarded refs[0] to the provider, silently
   dropping every additional reference.
5. Qwen/BytePlus text models never receive the attached image for the
   "image_prompt" tool (with_text_media_attachment only forwards it for
   openai/gemini/grok), yet nothing stopped a user from picking that tool
   with those models - the model would answer as if it had seen the photo,
   and the user was billed for a real analysis that never happened.
6. gemini_text_request()'s own legacy-shorthand remap table (separate from
   TEXT_MODEL_VARIANTS's already-fixed default) still mapped the bare
   "gemini-3.1-flash" shorthand to a name missing its ".1".
"""
import services.video_router as video_router


def test_seedance_1_5_pro_priced_for_every_offered_duration():
    for duration in (4, 5, 6, 7, 8, 9, 10, 11, 12):
        for sound in (False, True):
            payload = {
                "model": "seedance_1_5_pro",
                "video_options": {
                    "model": "seedance_1_5_pro",
                    "resolution": "720p",
                    "duration": duration,
                    "sound": sound,
                },
            }
            result = video_router.estimate_video_generation_cost(payload)
            assert result["credits"] > 0, (duration, sound, result)


def test_seedance_1_5_pro_duration_5_price_unchanged():
    # Anchor: these exact values were already correct/live before the fix -
    # the fix must not change what duration=5 already charged.
    expected_no_sound = {"480p": 9, "720p": 20, "1080p": 44}
    expected_with_sound = {"480p": 18, "720p": 39, "1080p": 87}
    for resolution, credits in expected_no_sound.items():
        result = video_router.estimate_video_generation_cost({
            "model": "seedance_1_5_pro",
            "video_options": {"model": "seedance_1_5_pro", "resolution": resolution, "duration": 5, "sound": False},
        })
        assert result["credits"] == credits, (resolution, result)
    for resolution, credits in expected_with_sound.items():
        result = video_router.estimate_video_generation_cost({
            "model": "seedance_1_5_pro",
            "video_options": {"model": "seedance_1_5_pro", "resolution": resolution, "duration": 5, "sound": True},
        })
        assert result["credits"] == credits, (resolution, result)


def test_minimax_hailuo_2_3_priced_at_its_real_default_duration():
    result = video_router.estimate_video_generation_cost({
        "model": "minimax_hailuo_2_3",
        "video_options": {"model": "minimax_hailuo_2_3", "resolution": "720p", "duration": 5},
    })
    assert result["credits"] == 42, result
    result_10s = video_router.estimate_video_generation_cost({
        "model": "minimax_hailuo_2_3",
        "video_options": {"model": "minimax_hailuo_2_3", "resolution": "720p", "duration": 10},
    })
    assert result_10s["credits"] == 84, result_10s


def test_kling_3_0_turbo_audio_actually_requested_when_billed():
    provider_model = "kling-3.0-turbo"
    settings_on = video_router._kling_text_settings(provider_model, {"sound": True, "duration": 5, "resolution": "1080p"})
    assert settings_on["audio"] == "native", settings_on
    settings_off = video_router._kling_text_settings(provider_model, {"sound": False, "duration": 5, "resolution": "1080p"})
    assert settings_off["audio"] == "off", settings_off
    # Image-to-video path must behave the same way.
    image_settings_on = video_router._kling_image_settings(provider_model, {"sound": True, "duration": 5, "resolution": "1080p"})
    assert image_settings_on["audio"] == "native", image_settings_on


def test_kling_3_0_and_omni_audio_forwarding_unaffected():
    # The fix must not disturb the existing kling-3.0/kling-3.0-omni branch.
    settings = video_router._kling_text_settings("kling-3.0", {"sound": True, "duration": 5, "resolution": "1080p"})
    assert settings["audio"] == "native"
    assert settings["multi_shot"] is True


def test_flux_2_forwards_every_reference_not_only_the_first(monkeypatch):
    import main

    monkeypatch.setattr(main, "flux_headers", lambda: {"x-key": "test"})
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "task-1", "polling_url": "https://example.test/poll"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_provider_json", lambda response, provider, url: response.json())
    monkeypatch.setattr(main, "poll_flux_image", lambda *a, **kw: ([], {}))

    payload = {
        "image_options": {
            "characterReferences": ["https://x.test/char1.png", "https://x.test/char2.png"],
            "objectReferences": ["https://x.test/obj1.png"],
        }
    }
    main.call_flux_image("flux_2", "flux-2-pro", "https://api.bfl.ai/v1", "a cat", payload, "1024x1024")
    body = captured["json"]
    assert body["input_image"] == "https://x.test/char1.png"
    assert body["input_image_2"] == "https://x.test/char2.png"
    assert body["input_image_3"] == "https://x.test/obj1.png"


def test_flux_kontext_reference_forwarding_unaffected(monkeypatch):
    import main

    monkeypatch.setattr(main, "flux_headers", lambda: {"x-key": "test"})
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "task-1", "polling_url": "https://example.test/poll"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "safe_provider_json", lambda response, provider, url: response.json())
    monkeypatch.setattr(main, "poll_flux_image", lambda *a, **kw: ([], {}))

    payload = {"image_options": {"characterReferences": ["https://x.test/char1.png"]}}
    main.call_flux_image("flux_pro_kontext", "flux-kontext-pro", "https://api.bfl.ai/v1", "a cat", payload, "1024x1024")
    assert captured["json"]["input_image"] == "https://x.test/char1.png"
    assert "width" not in captured["json"]


def test_image_prompt_rejected_for_non_vision_providers():
    import main

    for model in ("qwen_plus", "byteplus_seed_2_lite"):
        result = main.text_generation({
            "prompt": "",
            "model": model,
            "attachment": {"url": "https://x.test/photo.png", "mime": "image/png"},
            "text_options": {"tool": "image_prompt"},
        })
        assert result["ok"] is False, (model, result)


def test_image_prompt_allowed_for_vision_providers_requires_image_attachment():
    import main

    result = main.text_generation({
        "prompt": "",
        "model": "gpt-5.5",
        "attachment": {},
        "text_options": {"tool": "image_prompt"},
    })
    assert result["ok"] is False
    assert "изображение" in result["error"].lower()
