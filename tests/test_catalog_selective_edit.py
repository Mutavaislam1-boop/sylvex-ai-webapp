"""Catalog replacement wire contract; no real provider or purchases."""
import asyncio
import pytest
import main
from services.catalog_video import is_catalog_video_edit, replacement_prompt
from services import video_router
from test_video_reference_routing import captured, _dispatch, START, VIDEO


def catalog_options(**extra):
    return dict(model="kling_motion_3_0", generation_mode="video_edit", input_video=VIDEO,
                start_image=START, duration=5, resolution="720p", sound=True,
                video_template={"id":"04", "catalog_type":"video_template", "duration":5,
                                "prompt":"Invent a different horror scene", "reference_video":VIDEO}, **extra)


def test_catalog_payload_is_selective_omni_edit_with_original_audio(captured):
    _dispatch("kling_motion_3_0", catalog_options())
    requests = [c for c in captured if c["json"] and "contents" in c["json"]]
    assert len(requests) == 1
    request = requests[0]
    assert request["url"].endswith("/omni-video/kling-3.0-omni")
    body = request["json"]
    media = {x["type"]:x for x in body["contents"] if "url" in x}
    assert set(media) == {"base_video", "refer_image"}
    assert media["base_video"] == {"type":"base_video", "url":VIDEO, "id":"video_1"}
    assert media["refer_image"] == {"type":"refer_image", "url":START, "id":"image_1"}
    prompt = next(x["text"] for x in body["contents"] if x["type"] == "prompt")
    assert "Invent a different" not in prompt
    assert "@video_1" in prompt and "@image_1" in prompt and "replace only" in prompt
    assert body["settings"]["audio"] == "original"
    assert body["settings"]["multi_shot"] is False
    assert "duration" not in body["settings"] and "aspect_ratio" not in body["settings"]


def test_refinement_is_explicit_and_catalog_description_is_not_a_prompt():
    text = replacement_prompt({"title":"New universe", "description":"Destroy the city", "user_prompt":"Replace the man on the left"})
    assert "man on the left" in text and "Destroy" not in text and "New universe" not in text


@pytest.mark.parametrize("seconds,accepted", [(12,True),(15.5,True),(16,False),(2,False)])
def test_catalog_uses_omni_limits_while_motion_keeps_its_own(monkeypatch, seconds, accepted):
    monkeypatch.setattr(main, "_reference_video_meta", lambda url:{"extension":".mp4", "duration":seconds,"width":720,"height":1280})
    result = asyncio.run(main.validate_reference_video_media({"video_options":catalog_options()}))
    assert (result is None) is accepted
    motion = catalog_options()
    motion.update(generation_mode="motion_control", character_orientation="image")
    assert not is_catalog_video_edit(motion)
    if seconds > 10:
        rejected = asyncio.run(main.validate_reference_video_media({"video_options":motion}))
        assert rejected and "3-10 seconds" in rejected["error"]


def test_standalone_base_video_settings_are_unchanged():
    opts = video_router._kling_omni_settings("kling-3.0-omni", {"sound":True}, has_video=True, base_video=True)
    assert opts["audio"] == "off"


def test_effects_are_not_character_replacement():
    opts = catalog_options()
    opts["video_template"]["catalog_type"] = "kling_effect"
    assert not is_catalog_video_edit(opts)


def test_catalog_cannot_submit_an_unverified_source(monkeypatch):
    monkeypatch.setattr(main, "_reference_video_meta", lambda url:{"extension":".mp4"})
    monkeypatch.setattr(main, "_catalog_reference_video_meta", lambda url:{})
    result = asyncio.run(main.validate_reference_video_media({"video_options":catalog_options()}))
    assert result and result["ok"] is False and "Cannot verify" in result["error"]


@pytest.mark.parametrize("fps,accepted", [(24,True),(60,True),(23,False),(61,False)])
def test_catalog_frame_rate_is_checked_without_converting_source(monkeypatch, fps, accepted):
    monkeypatch.setattr(main, "_reference_video_meta", lambda url:{"duration":6,"width":720,"height":1280,"extension":".mp4","fps":fps})
    result = asyncio.run(main.validate_reference_video_media({"video_options":catalog_options()}))
    assert (result is None) is accepted


def test_catalog_requires_appearance_before_pricing():
    options=catalog_options()
    options.pop('start_image')
    result=main.validate_video_feature_request({'video_options':options})
    assert result and result['ok'] is False and 'appearance image' in result['error']


def test_interrupted_submission_recovery_is_read_only_and_owner_scoped(monkeypatch):
    import os, uuid, json
    from contextlib import contextmanager
    import psycopg2
    url = os.getenv('SYLVEX_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set a disposable local PostgreSQL URL')
    schema = 'catalog_recovery_' + uuid.uuid4().hex
    connection = psycopg2.connect(url)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute('CREATE SCHEMA ' + schema)
        cursor.execute('CREATE TABLE '+schema+'.prostudio_generation_jobs(id TEXT, telegram_id BIGINT, request_json JSONB, created_at TIMESTAMPTZ DEFAULT NOW())')
        cursor.execute('INSERT INTO '+schema+'.prostudio_generation_jobs(id,telegram_id,request_json) VALUES (%s,%s,%s)',('same-job',777,json.dumps({'client_request_id':'interrupted-catalog'})))
    @contextmanager
    def connect(*args):
        c = psycopg2.connect(url)
        try:
            with c.cursor() as q:
                q.execute('SET search_path TO '+schema)
            yield c
        finally:
            c.close()
    monkeypatch.setattr(main, 'db_connection', connect)
    token = main.actor_id.set(777)
    try:
        assert asyncio.run(main.public_prostudio_request_job('interrupted-catalog')) == {'ok':True,'job_id':'same-job'}
        assert asyncio.run(main.public_prostudio_request_job('not-submitted')) == {'ok':True,'job_id':''}
        assert asyncio.run(main.public_prostudio_request_job('../invalid')).status_code == 400
        main.actor_id.set(888)
        assert asyncio.run(main.public_prostudio_request_job('interrupted-catalog')) == {'ok':True,'job_id':''}
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM '+schema+'.prostudio_generation_jobs')
            assert cursor.fetchone()[0] == 1
    finally:
        main.actor_id.reset(token)
        with connection.cursor() as cursor:
            cursor.execute('DROP SCHEMA '+schema+' CASCADE')
        connection.close()
