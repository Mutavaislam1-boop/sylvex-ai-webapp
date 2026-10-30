"""Media constructor: admins build AI tools, video templates, photo
references (modes A / B / C) and styles with their own upload fields; the
models and limits come from the capability registry, the price from the
central tariff, and a published block runs as an ordinary Pro Studio
generation. Unit checks plus real SQL through the API (PGlite)."""
import json

import pytest

from services import media_blocks as mb

MODELS = [
    {"id": "seedream_5_0", "generation": "image", "accepts_images": True, "max_images": 10, "accepts_video": False, "start_frame": False},
    {"id": "imagen_4_fast", "generation": "image", "accepts_images": False, "max_images": 0, "accepts_video": False, "start_frame": False},
    {"id": "kling_o3_omni", "generation": "video", "accepts_images": True, "max_images": 4, "accepts_video": True, "start_frame": True},
    {"id": "veo_text", "generation": "video", "accepts_images": False, "max_images": 0, "accepts_video": False, "start_frame": False},
]


def block(**kw):
    base = {"id": 7, "block_type": "photo", "name": "Neon", "preview_url": "https://cdn/x.png", "source_url": "https://cdn/ref.png",
            "prompt": "neon portrait", "model": "seedream_5_0",
            "config": mb.clean_config({"ref_mode": "C", "fields": [{"label": "Your photo"}]}, kw.get("block_type", "photo"))}
    base.update(kw)
    return base


def codes(b):
    return {c for c, _ in mb.problems(b, MODELS)}


def test_config_is_cleaned_and_defaults_follow_the_block_type():
    cfg = mb.clean_config({"fields": [{"key": "Фото!", "label": " Face ", "accept": "exe"}, {"key": "x"}, {"key": "x"}],
                           "placements": ["video_styles", "nope"]}, "tool")
    assert [f["key"] for f in cfg["fields"]] == ["file_1", "x", "x_3"]
    assert cfg["fields"][0]["accept"] == "image" and cfg["fields"][0]["label"] == "Face"
    assert cfg["placements"] == []  # a tool never goes to the video catalog
    assert mb.clean_config({}, "tool")["placements"] == ["ai_tools"]  # not given: its own catalog
    assert mb.clean_config({}, "video")["generation"] == "video"
    assert mb.clean_config({}, "style")["ref_mode"] == "C"
    with pytest.raises(mb.BlockError):
        mb.clean_config({}, "banner")


def test_readiness_checks():
    assert codes(block()) == set()
    assert "cover_required" in codes(block(preview_url=""))
    assert "model_unknown" in codes(block(model="nope"))
    assert "model_wrong_type" in codes(block(model="kling_o3_omni"))
    assert "model_no_image_input" in codes(block(model="imagen_4_fast"))
    b = block()
    b["config"] = mb.clean_config({"ref_mode": "B", "fields": [{"label": "Photo"}]}, "photo")
    assert "prompt_required" in codes(dict(b, prompt=""))
    b["config"]["fields"] = []
    assert "upload_field_required" in codes(b)
    b["config"]["fields"] = [{"key": f"f{i}", "label": "x", "accept": "image", "required": True, "input": "reference"} for i in range(11)]
    assert "too_many_images" in codes(b)
    v = block(block_type="video", model="kling_o3_omni", source_url="", prompt="dance",
              config=mb.clean_config({"fields": [{"label": "Person 1"}, {"label": "Person 2"}]}, "video"))
    assert codes(v) == {"reference_video_required"}
    assert "model_no_video_input" in codes(dict(v, model="veo_text", source_url="https://cdn/v.mp4"))


def test_modes_a_b_c_decide_what_reaches_the_model():
    uploads = {"file_1": "https://up/me.png"}
    for mode, refs, prompt in (("A", ["https://cdn/ref.png", "https://up/me.png"], mb.DEFAULT_A_PROMPT),
                               ("B", ["https://up/me.png"], "neon portrait"),
                               ("C", ["https://cdn/ref.png", "https://up/me.png"], "neon portrait")):
        b = block(prompt="" if mode == "A" else "neon portrait",
                  config=mb.clean_config({"ref_mode": mode, "fields": [{"label": "Your photo"}]}, "photo"))
        p = mb.generation_payload(b, uploads)
        assert p["mode"] == "image" and p["model"] == "seedream_5_0" and p["prompt"] == prompt
        assert p["image_options"]["referenceImageUrls"] == refs, mode
    with pytest.raises(mb.BlockError) as err:
        mb.generation_payload(block(), {})
    assert err.value.code == "upload_required"


def test_video_template_payload_uses_the_catalog_video_and_each_person():
    v = block(block_type="video", model="kling_o3_omni", source_url="https://cdn/dance.mp4", prompt="dance",
              config=mb.clean_config({"fields": [{"key": "a", "label": "Person 1"}, {"key": "b", "label": "Person 2"}],
                                      "aspect": "9:16", "duration": 5}, "video"))
    p = mb.generation_payload(v, {"a": "https://up/1.png", "b": "https://up/2.png"})
    opts = p["video_options"]
    assert p["mode"] == "video" and opts["video_template"]["reference_video"] == "https://cdn/dance.mp4"
    assert opts["reference_images"] == ["https://up/1.png", "https://up/2.png"] and opts["video_template"]["input_count"] == 2
    assert opts["video_template"]["preferred_model"] == "kling_o3_omni" and opts["ratio"] == "9:16"


def test_published_blocks_join_the_existing_catalogs():
    photo = mb.public_view(block(), 30)
    video = mb.public_view(block(id=8, block_type="video", model="kling_o3_omni", source_url="https://cdn/v.mp4",
                                 config=mb.clean_config({"fields": [{"label": "Person 1"}, {"label": "Person 2"}]}, "video")), 90)
    templates = mb.join_catalogs([photo, video], video_templates=[{"id": "builtin_1"}])
    assert [t["id"] for t in templates] == ["media_block_8", "builtin_1"]
    assert templates[0]["input_count"] == 2 and templates[0]["cost_credits"] == 90 and templates[0]["prompt"] == ""
    assert templates[0]["media_block"]["fields"][1]["label"] == "Person 2"
    catalog = mb.join_catalogs([photo, video], quick_catalog={"references": [{"id": "r1"}], "styles": []})
    assert [i["id"] for i in catalog["references"]] == ["media_block_7", "r1"] and catalog["styles"] == []
    # The admin's prompt stays on the server.
    assert "prompt" not in photo and catalog["references"][0]["prompt"] == ""


def test_an_explicitly_empty_placement_blocks_publishing():
    b = block()
    b["config"] = mb.clean_config({"ref_mode": "C", "fields": [{"label": "Photo"}], "placements": []}, "photo")
    assert b["config"]["placements"] == [] and "placement_required" in codes(b)


def test_model_catalog_reads_the_registry():
    caps = {
        "seedream_5_0": {"category": "image", "character": {"visual_reference": {"visual_mode": "real_multi_image", "max_count": 10}}},
        "imagen_4_fast": {"category": "image", "character": {"visual_reference": {"visual_mode": "unsupported"}}},
        "kling_o3_omni": {"category": "video", "reference_inputs": {"image_slots": 4, "accepts_video": True}, "start_frame": True},
        "avatar_x": {"category": "video", "avatar": True},
        "suno": {"category": "music"},
    }
    cat = {m["id"]: m for m in mb.model_catalog(caps, seedream={"seedream_5_0": {"max_references": 10}}, image_available={"seedream_5_0"})}
    assert set(cat) == {"seedream_5_0", "imagen_4_fast", "kling_o3_omni"}
    assert cat["seedream_5_0"]["max_images"] == 10 and cat["seedream_5_0"]["available"] is True
    assert cat["imagen_4_fast"]["accepts_images"] is False and cat["imagen_4_fast"]["available"] is False
    assert cat["kling_o3_omni"]["accepts_video"] and cat["kling_o3_omni"]["label"] == "Kling O3 Omni"


# --- through the API ---------------------------------------------------------

pglite = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

from test_admin_console_auth import (  # noqa: E402,F401  (fixtures)
    OWNER_TG, SUPPORT_TG, USER_TG, call, env, init_data, login, q, ready,
)


@pytest.fixture
def world(ready, monkeypatch):
    env = ready
    monkeypatch.setattr(env.main, "REFERENCES_SCHEMA_READY", False)
    monkeypatch.setitem(env.main.MEDIA_BLOCK_VIEWS_CACHE, "value", None)
    monkeypatch.setattr(env.main, "_media_models", lambda: MODELS)
    priced = []
    monkeypatch.setattr(env.main, "calculate_generation_price",
                        lambda payload: priced.append(payload) or {"credits": 30, "pricing_available": True})
    runs = []

    async def fake_generate(request):
        runs.append((await request.json(), request.state.telegram_id))
        return {"ok": True, "job_id": "job-1", "status": "queued"}
    monkeypatch.setattr(env.main, "public_prostudio_generate", fake_generate)
    env.runs, env.priced = runs, priced
    return env


async def admin(env, path, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", path, cookie=token, csrf=csrf, json_body=body)


DRAFT = {"block_type": "photo", "name": "Neon portrait", "description": "Your photo in neon", "prompt": "neon portrait",
         "model": "seedream_5_0", "preview_url": "https://cdn.example/cover.png", "source_url": "https://cdn.example/ref.png",
         "config": {"ref_mode": "C", "fields": [{"key": "me", "label": "Your photo", "purpose": "the face"}]}}


@pglite
@pytest.mark.asyncio
async def test_build_check_publish_and_run(world):
    env = world
    # Support has no Media rights.
    assert (await admin(env, "/api/admin/references/create", DRAFT, who=SUPPORT_TG)).status_code == 403
    r = await admin(env, "/api/admin/references/create", dict(DRAFT, published=True))
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["published"] is False and item["block_type"] == "photo" and item["kind"] == "photo"
    assert item["config"]["fields"][0]["key"] == "me"
    # The check shows the live price and what is missing.
    check = (await admin(env, "/api/admin/media/check", dict(DRAFT, preview_url=""))).json()
    assert check["cost"] == 30 and {p["code"] for p in check["problems"]} == {"cover_required"}
    assert check["preview"]["fields"][0]["label"] == "Your photo"
    # Not ready: publishing is refused with the reasons.
    await admin(env, "/api/admin/references/update", {"id": item["id"], "preview_url": ""})
    r = await admin(env, "/api/admin/references/publish", {"id": item["id"], "published": True})
    assert r.status_code == 409 and r.json()["problems"][0]["code"] == "cover_required"
    await admin(env, "/api/admin/references/update", {"id": item["id"], "preview_url": "https://cdn.example/cover.png"})
    r = await admin(env, "/api/admin/references/publish", {"id": item["id"], "published": True})
    assert r.status_code == 200, r.text
    assert q(env, "SELECT risk FROM admin_audit_events WHERE action = 'reference_published'") == [["high"]]
    # Published: in its catalog with the tariff price, not in the old list.
    items = (await call(env, "GET", "/api/public/media-blocks?placement=photo_references", origin=None)).json()["items"]
    assert [(i["name"], i["cost"], i["fields"][0]["key"]) for i in items] == [("Neon portrait", 30, "me")]
    assert (await call(env, "GET", "/api/public/prostudio/references", origin=None)).json()["items"] == []
    # ... and inside the catalog the apps already show, leading it.
    refs = (await call(env, "GET", "/api/public/prostudio/quick-image-catalog", origin=None)).json()["catalog"]["references"]
    assert refs[0]["id"] == f"media_block_{item['id']}" and refs[0]["media_block"]["cost"] == 30
    # Running it: one ordinary generation for the caller, built on the server.
    headers = {"X-Telegram-Init-Data": init_data(USER_TG)}
    r = await call(env, "POST", f"/api/public/media-blocks/{item['id']}/generate", origin=None, headers=headers, json_body={"uploads": {}})
    assert r.status_code == 400 and r.json()["missing"] == ["me"]
    r = await call(env, "POST", f"/api/public/media-blocks/{item['id']}/generate", origin=None, headers=headers,
                   json_body={"uploads": {"me": "https://images.example/me.png"}, "prompt": "ignore the admin"})
    assert r.status_code == 200 and r.json()["job_id"] == "job-1", r.text
    sent, uid = env.runs[-1]
    assert uid == USER_TG and sent["prompt"] == "neon portrait" and sent["model"] == "seedream_5_0"
    assert sent["telegram_id"] == USER_TG and sent["source"] == "media_block"
    assert sent["image_options"]["referenceImageUrls"][-1] == "https://images.example/me.png"
    # Unpublished: gone for users.
    await admin(env, "/api/admin/references/publish", {"id": item["id"], "published": False})
    r = await call(env, "POST", f"/api/public/media-blocks/{item['id']}/generate", origin=None, headers=headers,
                   json_body={"uploads": {"me": "https://images.example/me.png"}})
    assert r.status_code == 404
    # The catalogs drop it at once (no stale cache).
    refs = (await call(env, "GET", "/api/public/prostudio/quick-image-catalog", origin=None)).json()["catalog"]["references"]
    assert not any(i.get("media_block") for i in refs)


@pglite
@pytest.mark.asyncio
async def test_catalog_lists_registry_models_and_places(world):
    data = (await admin(world, "/api/admin/media/catalog", {})).json()
    assert {m["id"] for m in data["models"]} == {m["id"] for m in MODELS}
    assert {p["id"] for p in data["placements"]} >= {"ai_tools", "video_styles", "photo_references", "image_styles"}
    assert data["ref_modes"] == ["A", "B", "C"]
