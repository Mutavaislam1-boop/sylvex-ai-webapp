"""Admin Console stage D: the stages a generation really went through and
its technical log (no secrets), generation statistics, usage analytics
(ids only, per platform) and turning models off for users."""
import pytest

from services import generation_admin as ga
from services import model_control as mc
from services import usage_analytics as ua


def job(**kw):
    base = {"id": "j1", "status": "completed", "mode": "image", "created_at": 100.0, "completed_at": 110.0,
            "stage_json": {"sent": 101.0, "accepted": 102.0, "processing": 103.0, "result": 108.0}, "result_json": {}}
    base.update(kw)
    return base


def states(rows):
    return {r["key"]: r["state"] for r in rows}


def test_a_completed_job_shows_every_confirmed_stage_with_its_time():
    rows, failed = ga.timeline(job(), {"status": "completed", "updated_at": 115.0})
    assert failed == "" and all(r["state"] == "done" for r in rows)
    by = {r["key"]: r for r in rows}
    assert by["sent"]["seconds"] == 1.0 and by["result"]["seconds"] == 5.0 and by["stored"]["at"] == 115.0


def test_a_failed_job_fails_at_the_first_stage_that_never_happened():
    rows, failed = ga.timeline(job(status="failed", stage_json={"sent": 101.0}))
    assert failed == "accepted"
    s = states(rows)
    assert s["sent"] == "done" and s["accepted"] == "failed"
    # Nothing after the failure is shown as done.
    assert s["processing"] == s["result"] == s["stored"] == s["ready"] == "pending"


def test_old_jobs_without_recorded_stages_are_not_given_fake_times():
    rows, _ = ga.timeline(job(stage_json={}))
    by = {r["key"]: r for r in rows}
    assert by["sent"]["state"] == "done" and by["sent"]["at"] is None  # proven by the result, time unknown
    assert by["stored"]["state"] == "pending"  # never claimed without evidence


def test_a_running_job_marks_only_the_next_stage_as_running():
    rows, failed = ga.timeline(job(status="provider_processing", completed_at=None, stage_json={"sent": 101.0, "accepted": 102.0}))
    s = states(rows)
    assert failed == "" and s["processing"] == "running" and s["result"] == "pending" and s["ready"] == "pending"


def test_text_results_need_no_storage():
    assert states(ga.timeline(job(mode="text"))[0])["stored"] == "skipped"


def test_the_technical_log_hides_secrets():
    log = ga.technical_log(job(status="failed", error_json={
        "error": "provider_timeout", "message": "Bearer sk-live-ABCDEFGHIJKLMNOPQRS failed at https://x/y.png?media_sig=abc123&x=1 api_key=supersecret1",
        "task_id": "task-42"}, request_json={"client_surface": "website", "media_block_id": 7}))
    assert log["error_code"] == "provider_timeout" and log["external_task_id"] == "task-42"
    assert "sk-live" not in log["technical_message"] and "abc123" not in log["technical_message"] and "supersecret1" not in log["technical_message"]
    assert log["platform"] == "website" and log["source"] == "media_block"


def test_analytics_batches_keep_ids_only():
    visitor, surface, events = ua.clean_batch({"visitor": "v1abcdef", "surface": "telegram_miniapp", "events": [
        {"event": "item_select", "item": "Photo 09 <script>", "kind": "style", "prompt": "my secret prompt"},
        {"event": "section_leave", "section": "media", "duration_ms": 10 ** 12},
        {"event": "keylogger", "section": "x"},
    ] + [{"event": "download"}] * 40})
    assert visitor == "v1abcdef" and surface == "telegram_miniapp"
    assert len(events) == 29  # the batch is capped at 30, the unknown event dropped
    assert events[0]["item"] == "photo_09__script" and "prompt" not in events[0]
    assert events[1]["duration_ms"] == ua.MAX_DURATION_MS
    assert ua.clean_batch({"visitor": "x", "surface": "evil", "events": []})[:2] == ("", "")


def test_provider_state_is_never_assumed(monkeypatch):
    monkeypatch.delenv("KLING_API_KEY", raising=False)
    monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
    assert mc.configured("kling") is False and mc.configured("someone-new") is None
    monkeypatch.setenv("KLING_ACCESS_KEY", "x")
    assert mc.configured("kling") is True
    assert mc.provider_state(None, 0, 0, 0) == "no_data"
    assert mc.provider_state(True, 0, 0, 0) == "no_data"
    assert mc.provider_state(False, 5, 0, 5) == "not_configured"
    # Real successful generations win over the key check.
    assert mc.provider_state(False, 5, 5, 0) == "working"
    # Every name the integration reads counts, the dashed ones included.
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("GROK-API-KEY", "x")
    assert mc.configured("grok") is True
    assert mc.configured("recraft") in (True, False) and mc.configured("ideogram") in (True, False)
    assert mc.provider_state(True, 10, 3, 7) == "errors"
    assert mc.provider_state(True, 10, 9, 1) == "working"
    assert mc.norm("Qwen-Image-2-Pro") == "qwen_image_2_pro"


# --- through the API ---------------------------------------------------------

pglite = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

from test_admin_console_auth import (  # noqa: E402,F401  (fixtures)
    OWNER_TG, SUPPORT_TG, USER_TG, call, env, init_data, login, q, ready,
)


@pytest.fixture
def world(ready, monkeypatch):
    env = ready
    monkeypatch.setattr(env.main, "ANALYTICS_SCHEMA_READY", False)
    monkeypatch.setattr(env.main, "_PROSTUDIO_SCHEMA_READY", False)
    monkeypatch.setitem(env.main.MODEL_STATES_CACHE, "value", None)
    return env


async def admin(env, path, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", path, cookie=token, csrf=csrf, json_body=body)


@pglite
@pytest.mark.asyncio
async def test_usage_events_are_counted_per_platform(world):
    env = world
    for surface, visitor in (("website", "vweb0001"), ("telegram_miniapp", "vtg00001"), ("telegram_miniapp", "vtg00002")):
        r = await call(env, "POST", "/api/public/analytics/events", origin=None, json_body={"visitor": visitor, "surface": surface, "events": [
            {"event": "section_open", "section": "home"}, {"event": "section_open", "section": "media"},
            {"event": "item_select", "item": "photo_09", "kind": "style"}, {"event": "section_leave", "section": "media", "duration_ms": 4000},
        ]})
        assert r.status_code == 200 and r.json()["stored"] == 4, r.text
    # Analysts see it; support does not.
    assert (await admin(env, "/api/admin/analytics", {"days": 7}, who=SUPPORT_TG)).status_code == 403
    data = (await admin(env, "/api/admin/analytics", {"days": 7})).json()
    platforms = {p["key"]: p for p in data["platforms"]}
    assert platforms["website"]["visitors"] == 1 and platforms["telegram_miniapp"]["visitors"] == 2
    media = next(s for s in data["sections"] if s["key"] == "media")
    assert media["opens"] == 3 and media["avg_seconds"] == 4.0
    assert next(t for t in data["tools"] if t["key"] == "photo_09")["selects"] == 3
    assert {"from": "home", "to": "media", "count": 3} in data["transitions"]
    only_web = (await admin(env, "/api/admin/analytics", {"days": 7, "platform": "website"})).json()
    assert [p["key"] for p in only_web["platforms"] if p["opens"]] == ["website"]


@pglite
@pytest.mark.asyncio
async def test_a_model_turned_off_takes_no_generations_until_turned_on(world):
    env = world
    r = await admin(env, "/api/admin/models/toggle", {"model": "nano_banana_pro", "disabled": True})
    assert r.status_code == 400 and r.json()["detail"] == "reason_required"
    assert (await admin(env, "/api/admin/models/toggle", {"model": "nano_banana_pro", "disabled": True, "reason": "x"}, who=SUPPORT_TG)).status_code == 403
    r = await admin(env, "/api/admin/models/toggle", {"model": "Nano-Banana-Pro", "disabled": True, "reason": "provider outage"})
    assert r.status_code == 200, r.text
    assert (await call(env, "GET", "/api/public/models/status", origin=None)).json()["disabled"] == ["nano_banana_pro"]
    headers = {"X-Telegram-Init-Data": init_data(USER_TG)}
    r = await call(env, "POST", "/api/public/prostudio/generate", origin=None, headers=headers,
                   json_body={"mode": "image", "category": "image", "prompt": "x", "model": "nano_banana_pro"})
    assert r.status_code == 409 and r.json()["error"] == "model_disabled"
    assert q(env, "SELECT action, risk FROM admin_audit_events WHERE action LIKE 'model_%'") == [["model_disabled", "critical"]]
    r = await admin(env, "/api/admin/models/toggle", {"model": "nano_banana_pro", "disabled": False})
    assert r.status_code == 200
    assert (await call(env, "GET", "/api/public/models/status", origin=None)).json()["disabled"] == []


@pglite
@pytest.mark.asyncio
async def test_job_card_and_statistics(world):
    env = world
    env.main.ensure_prostudio_table()
    q(env, """INSERT INTO prostudio_generation_jobs (id, telegram_id, mode, model, provider, prompt, status, request_json, error_json, stage_json, created_at, completed_at)
              VALUES ('j-ok', %s, 'image', 'seedream_5_0', 'bytedance', 'p', 'completed', '{"client_surface":"website"}', '{}',
                      jsonb_build_object('sent', EXTRACT(EPOCH FROM NOW()) - 9, 'result', EXTRACT(EPOCH FROM NOW()) - 2), NOW() - INTERVAL '10 seconds', NOW()),
                     ('j-bad', %s, 'image', 'seedream_5_0', 'bytedance', 'p', 'failed', '{"client_surface":"telegram_miniapp"}',
                      '{"error":"provider_rejected","message":"token=abcdefgh1234 refused"}', jsonb_build_object('sent', EXTRACT(EPOCH FROM NOW()) - 5), NOW() - INTERVAL '6 seconds', NOW())""",
      (USER_TG, USER_TG))
    d = (await admin(env, "/api/admin/generations/detail", {"id": "j-bad"})).json()["item"]
    assert d["failed_stage"] == "accepted" and d["log"]["error_code"] == "provider_rejected"
    assert "abcdefgh1234" not in d["log"]["technical_message"]
    s = (await admin(env, "/api/admin/generations/stats", {"days": 7})).json()
    assert (s["total"], s["completed"], s["failed"]) == (2, 1, 1)
    assert s["failed_by_stage"] == [{"key": "accepted", "count": 1}]
    assert {p["key"] for p in s["by_platform"]} == {"website", "telegram_miniapp"}
    assert len(s["days"]) >= 7  # every day of the period, zeros included
    web = (await admin(env, "/api/admin/generations", {"days": 7, "platform": "website"})).json()
    assert [i["id"] for i in web["items"]] == ["j-ok"] and web["items"][0]["platform"] == "website"
