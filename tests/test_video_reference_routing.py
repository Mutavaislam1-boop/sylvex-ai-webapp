"""Video reference inputs: every input reaches the provider or is rejected.

Audit (2026-10) traced start frame, end frame, uploaded image reference,
Character reference, Object reference and uploaded video through
_build_video_payload and each _call_<provider> with the HTTP layer mocked.
Silent drops found and fixed:
- HeyGen Video Agent: raw upload list shadowed the merged list, so
  Character/Object images never reached HeyGen.
- runway_seedance2*: the "seedance" name match sent these Runway models to
  the BytePlus adapter.
- Kling (one image slot), Runway/Luma/Veo/Sora/WAN/Grok/PixVerse/MiniMax (no
  reference slot), and video uploads to models without a video input: the
  extra inputs were dropped without telling anyone. They are now rejected by
  main.validate_video_feature_request() using the registry's
  reference_inputs, which this file checks against the adapters themselves.

No network: every provider HTTP call is captured by a fake.
"""
import asyncio
import json

import pytest

import main  # noqa: F401 - import-time side effect populates the capability registry
import services.video_router as video_router
from services import model_capabilities as mc

START = "https://cdn.test/START.png"
END = "https://cdn.test/END.png"
UPLOAD = "https://cdn.test/UPLOADREF.png"
CHAR = "https://cdn.test/CHARREF.png"
OBJ = "https://cdn.test/OBJREF.png"
VIDEO = "https://cdn.test/VIDEOREF.mp4"


class _Resp:
    status_code = 200
    ok = True
    headers = {"content-type": "application/json"}
    content = b"{}"

    def __init__(self):
        self._data = {
            "id": "task_1", "task_id": "task_1", "status": "processing", "name": "operations/x",
            "data": {"task_id": "task_1", "id": "task_1", "task_status": "submitted"},
            "Resp": {"video_id": 1}, "ErrCode": 0,
        }

    def json(self):
        return self._data

    @property
    def text(self):
        return json.dumps(self._data)

    def raise_for_status(self):
        return None


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def record(url, *args, **kwargs):
        calls.append({"url": str(url), "json": kwargs.get("json"), "data": kwargs.get("data"),
                      "files": str(kwargs.get("files"))[:4000]})
        return _Resp()

    monkeypatch.setattr(video_router.requests, "post", record)
    monkeypatch.setattr(video_router.requests, "get", record)
    monkeypatch.setattr(video_router, "_request_get", lambda url, headers: record(url))
    monkeypatch.setattr(video_router, "safe_get", lambda url, **kw: record(url))
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)
    monkeypatch.setattr(video_router.time, "sleep", lambda seconds: None)
    for name in dir(video_router):
        if name.endswith("_poll_until_ready"):
            monkeypatch.setattr(video_router, name, lambda *a, **k: {"ok": False, "status": "processing"})
    return calls


def _options(model, scenario):
    config = video_router.VIDEO_MODEL_CONFIG[model]
    opts = {
        "model": model, "duration": config["durations"][0],
        "characterId": "c1", "characterName": "Ann", "objectId": "o1", "objectName": "Hat",
        "characterReferences": [CHAR], "objectReferences": [OBJ],
        "reference_images": [UPLOAD], "referenceImageUrls": [UPLOAD],
    }
    if model == "kling_effects":
        opts.update(effect_scene="hug", video_effects=True, generation_mode="video_effects")
    if scenario == "frames":
        opts.update(start_image=START, end_image=END, generation_mode="image_to_video")
    elif scenario == "video":
        opts.update(input_video=VIDEO, video_url=VIDEO, reference_video=VIDEO, section="edit",
                    generation_mode="video_edit", video_input=True)
    return opts


def _dispatch(model, opts):
    payload = {"prompt": "a scene", "model": model, "provider": video_router.VIDEO_MODEL_CONFIG[model]["provider"],
               "video_options": opts, "skip_telegram": True}
    return asyncio.run(video_router.video_generation(payload))


def _sent(calls):
    return json.dumps(calls)


# ---------------------------------------------------------------- adapters

def test_seedance_payload_carries_every_reference_input(captured):
    _dispatch("seedance_2_0", _options("seedance_2_0", "frames"))
    content = next(c["json"]["content"] for c in captured if c["json"] and "content" in c["json"])
    images = [item["image_url"]["url"] for item in content if item.get("type") == "image_url"]
    assert {START, UPLOAD, CHAR, OBJ} <= set(images)
    assert all(item["role"] == "reference_image" for item in content if item.get("type") == "image_url")


def test_seedance_payload_carries_reference_video(captured):
    _dispatch("seedance_2_0", _options("seedance_2_0", "video"))
    content = next(c["json"]["content"] for c in captured if c["json"] and "content" in c["json"])
    videos = [item for item in content if item.get("type") == "video_url"]
    assert videos and videos[0]["video_url"]["url"] == VIDEO and videos[0]["role"] == "reference_video"


def test_heygen_video_agent_forwards_character_and_object_images(captured):
    _dispatch("heygen_v3_video_agent", _options("heygen_v3_video_agent", "refs_only"))
    sent = _sent(captured)
    for marker in ("UPLOADREF", "CHARREF", "OBJREF"):
        assert marker in sent, marker


def test_kling_omni_start_and_end_frames_use_frame_fields(captured):
    opts = _options("kling_o3_omni", "frames")
    opts.update(characterReferences=[], objectReferences=[], reference_images=[], referenceImageUrls=[])
    _dispatch("kling_o3_omni", opts)
    body = next(c["json"] for c in captured if c["json"] and "contents" in c["json"])
    by_type = {item["type"]: item["url"] for item in body["contents"] if "url" in item}
    assert by_type.get("first_frame") == START
    assert by_type.get("last_frame") == END


def test_kling_single_character_image_reaches_provider(captured):
    opts = _options("kling_3_0", "refs_only")
    opts.update(reference_images=[], referenceImageUrls=[], objectReferences=[])
    _dispatch("kling_3_0", opts)
    assert "CHARREF" in _sent(captured)


def test_kling_omni_edit_video_reaches_provider(captured):
    opts = _options("kling_o3_omni", "video")
    opts.update(characterReferences=[], objectReferences=[], reference_images=[], referenceImageUrls=[])
    _dispatch("kling_o3_omni", opts)
    assert "VIDEOREF" in _sent(captured)


def test_runway_seedance_models_route_to_runway_not_byteplus(captured, monkeypatch):
    seen = []
    monkeypatch.setattr(video_router, "_call_seedance", lambda *a, **k: seen.append("byteplus") or {"ok": False})
    real_runway = video_router._call_runway
    monkeypatch.setattr(video_router, "_call_runway", lambda *a, **k: seen.append("runway") or real_runway(*a, **k))
    _dispatch("runway_seedance2", _options("runway_seedance2", "frames"))
    assert seen == ["runway"]
    assert "START" in _sent(captured)


# ------------------------------------------- registry matches the adapters

def _uploaded_ref_reaches_provider(model, captured):
    captured.clear()
    opts = _options(model, "refs_only")
    opts.update(characterReferences=[], objectReferences=[])
    _dispatch(model, opts)
    return "UPLOADREF" in _sent(captured)


@pytest.mark.parametrize("model", sorted(video_router.VIDEO_MODEL_CONFIG))
def test_registry_image_slots_match_adapter(model, captured):
    limits = mc.get_capability(model).reference_inputs
    if limits.image_slots == 0:
        # Declared "no reference images": the adapter must indeed not use
        # them, otherwise the validator would reject a working input.
        assert not _uploaded_ref_reaches_provider(model, captured), model
    elif model not in {"heygen_cinematic_avatar"}:  # needs avatar ids to submit at all
        assert _uploaded_ref_reaches_provider(model, captured), model


@pytest.mark.parametrize("model", sorted(video_router.VIDEO_MODEL_CONFIG))
def test_registry_video_flag_never_claims_unforwarded_video(model, captured):
    limits = mc.get_capability(model).reference_inputs
    if not limits.accepts_video:
        return
    captured.clear()
    opts = _options(model, "video")
    opts.update(characterReferences=[], objectReferences=[], reference_images=[], referenceImageUrls=[])
    if model.startswith("kling_motion"):
        # Motion Control needs the character image next to the driving clip.
        opts["start_image"] = START
    result = _dispatch(model, opts)
    if model in {"heygen_cinematic_avatar"}:
        assert "avatar_id" in str(result.get("error") or "")
        return
    assert "VIDEOREF" in _sent(captured), model


# --------------------------------------------------------------- validator

def _request(model, **opts):
    return {"mode": "video", "model": model, "video_options": dict({"model": model}, **opts)}


def test_validator_rejects_reference_image_for_model_without_slot():
    error = main.validate_video_feature_request(_request("runway_gen4_5", start_image=START, reference_images=[UPLOAD]))
    assert error and error["error"] == "Selected model does not accept reference images"


def test_validator_rejects_kling_start_frame_plus_character_image():
    error = main.validate_video_feature_request(_request("kling_3_0", start_image=START, characterReferences=[CHAR]))
    assert error and "only one image" in error["error"]


def test_validator_rejects_video_for_model_without_video_input():
    error = main.validate_video_feature_request(_request("sora_2", input_video=VIDEO))
    assert error and error["error"] == "Selected model does not accept a reference video"


def test_validator_rejects_more_images_than_seedance_accepts():
    refs = [f"https://cdn.test/u{i}.png" for i in range(4)]
    error = main.validate_video_feature_request(_request(
        "seedance_2_0", start_image=START, reference_images=refs, referenceImageUrls=refs,
        characterReferences=[f"https://cdn.test/c{i}.png" for i in range(4)],
        objectReferences=[f"https://cdn.test/o{i}.png" for i in range(1)],
    ))
    assert error and "at most 9" in error["error"]


@pytest.mark.parametrize("model,opts", [
    ("seedance_2_0", {"start_image": START, "reference_images": [UPLOAD], "characterReferences": [CHAR], "objectReferences": [OBJ], "input_video": VIDEO}),
    ("kling_3_0", {"characterReferences": [CHAR]}),
    ("kling_3_0", {"start_image": START, "characterId": "c1", "characterName": "Ann"}),
    ("runway_gen4_5", {"start_image": START, "characterId": "c1", "characterName": "Ann"}),
    ("kling_motion_3_0", {"reference_video": VIDEO, "input_video": VIDEO, "start_image": START}),
    ("kling_o3_omni", {"input_video": VIDEO}),
    ("heygen_v3_video_agent", {"reference_images": [UPLOAD], "characterReferences": [CHAR]}),
])
def test_validator_accepts_inputs_the_adapter_forwards(model, opts):
    assert main.validate_video_feature_request(_request(model, **opts)) is None


# ------------------------------------------------------ upload limits data

def test_motion_control_video_limits_are_not_the_omni_limits():
    motion = mc.get_capability("kling_motion_3_0").reference_inputs
    omni = mc.get_capability("kling_o3_omni").reference_inputs
    assert motion.video_max_seconds == 30
    assert motion.video_max_seconds_by_orientation == {"video": 30, "image": 10}
    assert motion.video_min_px == 340
    assert omni.video_min_seconds == 3 and omni.video_max_seconds == 15.5
    assert omni.video_max_bytes == 200 * 1024 * 1024


def test_reference_inputs_are_served_by_capability_endpoint():
    data = mc.get_capability("kling_motion_2_6").to_dict()
    assert data["reference_inputs"]["video_extensions"] == [".mp4", ".mov"]
    assert data["reference_inputs"]["accepts_video"] is True
