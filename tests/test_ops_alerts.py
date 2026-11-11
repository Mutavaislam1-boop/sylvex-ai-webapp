"""B11: operational alerts inside the API (services/ops_alerts.py).

Real SQL (PGlite). Telegram is a fake sender: no message leaves the test.
The detectors only read: generation jobs and provider circuits are compared
before and after every cycle.
"""
import asyncio
import json

import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    ADMIN_TG, ORIGIN, OWNER_TG, _cookie, call, env, login, q, ready,
)

CIRCUITS_DDL = """CREATE TABLE IF NOT EXISTS prostudio_provider_circuits (
    provider TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'CLOSED', failure_count INTEGER NOT NULL DEFAULT 0,
    opened_until TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""


class Telegram:
    def __init__(self):
        self.sent, self.fail = [], False

    def __call__(self, text):
        if self.fail:
            return False, "Bad Gateway"
        self.sent.append(text)
        return True, None


@pytest.fixture
def ops(ready, monkeypatch):
    env = ready
    monkeypatch.setattr(env.main, "_PROSTUDIO_SCHEMA_READY", False)
    env.main.ensure_prostudio_table()
    q(env, CIRCUITS_DDL)
    env.tg = Telegram()
    return env


def job(env, job_id, status, *, age_min=10, heartbeat_min=None, attempts=0, wait_min=None, done_min=None,
        prompt="SECRET_PROMPT_DO_NOT_LEAK", uid=7000000001):
    def ago(minutes):
        return "NULL" if minutes is None else f"NOW() - INTERVAL '{int(minutes)} minutes'"
    wait = "NULL" if wait_min is None else f"NOW() + INTERVAL '{int(wait_min)} minutes'"
    q(env, f"""INSERT INTO prostudio_generation_jobs (id, telegram_id, mode, status, prompt, attempts, created_at,
               heartbeat_at, provider_wait_until, completed_at, updated_at)
               VALUES (%s, %s, 'image', %s, %s, %s, {ago(age_min)}, {ago(heartbeat_min)}, {wait}, {ago(done_min)}, NOW())""",
      (job_id, uid, status, prompt, attempts))


def cycle(env):
    from services import ops_alerts
    conn = env.db.connect()
    cur = conn.cursor()
    result = ops_alerts.evaluate(cur, env.tg, max_attempts=3)
    conn.commit()
    return result


def snapshot(env):
    return (q(env, "SELECT id, status, attempts, heartbeat_at, updated_at FROM prostudio_generation_jobs ORDER BY id"),
            q(env, "SELECT provider, state, failure_count, updated_at FROM prostudio_provider_circuits ORDER BY provider"))


def deliveries(env):
    return q(env, "SELECT alert_key, event, ok, error FROM ops_alert_deliveries ORDER BY id")


def test_stalled_queue_alerts_once_then_recovers(ops):
    env = ops
    job(env, "q1", "queued", age_min=12)
    job(env, "q2", "queued", age_min=7)
    job(env, "q_new", "queued", age_min=1)                    # too young
    job(env, "q_wait", "queued", age_min=30, wait_min=10)     # waiting for a provider on purpose
    job(env, "q_spent", "queued", age_min=30, attempts=3)     # no attempts left
    before = snapshot(env)
    assert cycle(env)["sent"] == [("workers_stalled", "fire")]
    assert "генерации не обрабатываются" in env.tg.sent[0] and "2 заданий" in env.tg.sent[0]
    assert cycle(env)["sent"] == [] and len(env.tg.sent) == 1   # no repeat while it lasts
    assert snapshot(env) == before                             # nothing in the jobs changed
    q(env, "UPDATE prostudio_generation_jobs SET status = 'completed' WHERE id IN ('q1', 'q2')")
    assert cycle(env)["sent"] == []                            # clear, but not long enough yet
    q(env, "UPDATE ops_alert_state SET last_seen_at = NOW() - INTERVAL '6 minutes', "
           "first_seen_at = NOW() - INTERVAL '20 minutes'")
    assert cycle(env)["sent"] == [("workers_stalled", "resolve")]
    assert env.tg.sent[-1].startswith("✅ SYLVEX: восстановлено") and "Длилось: 20 мин." in env.tg.sent[-1]
    assert [d[:3] for d in deliveries(env)] == [["workers_stalled", "fire", True], ["workers_stalled", "resolve", True]]


def test_a_failed_delivery_is_recorded_and_retried(ops):
    env = ops
    job(env, "q1", "queued", age_min=12)
    env.tg.fail = True
    result = cycle(env)
    assert result["sent"] == [] and result["failed"] == [("workers_stalled", "fire")]
    assert q(env, "SELECT notify_pending FROM ops_alert_state") == [["fire"]]
    env.tg.fail = False
    assert cycle(env)["sent"] == [("workers_stalled", "fire")] and len(env.tg.sent) == 1
    assert deliveries(env) == [["workers_stalled", "fire", False, "Bad Gateway"], ["workers_stalled", "fire", True, None]]


def test_reminder_while_it_lasts(ops):
    env = ops
    job(env, "q1", "queued", age_min=12)
    cycle(env)
    q(env, "UPDATE ops_alert_state SET last_notified_at = NOW() - INTERVAL '7 hours'")
    assert cycle(env)["sent"] == [("workers_stalled", "reminder")]
    assert env.tg.sent[-1].startswith("⏰ SYLVEX P0, всё ещё")
    assert cycle(env)["sent"] == []


def test_worker_dying_mid_job(ops):
    env = ops
    job(env, "p_ok", "processing", heartbeat_min=1)
    job(env, "p_waiting", "provider_processing", heartbeat_min=60)   # background wait: not a dead worker
    assert cycle(env)["sent"] == []
    job(env, "p_dead", "processing", heartbeat_min=15)
    assert cycle(env)["sent"] == [("workers_stale_jobs", "fire")]
    assert "1 заданий в работе без сигнала воркера" in env.tg.sent[0]


def test_mass_generation_failures_need_count_and_ratio(ops):
    env = ops
    for i in range(4):
        job(env, f"f{i}", "failed", done_min=2)
    job(env, "c_user", "cancelled", done_min=2)                       # a user's cancel is no failure
    assert "generation_failures" not in dict(cycle(env)["sent"])       # 4 < 5
    for i in range(16):
        job(env, f"ok{i}", "completed", done_min=3)
    job(env, "f4", "timeout", done_min=1)
    assert cycle(env)["sent"] == []                                    # 5 of 21: 24 % < 50 %
    q(env, "DELETE FROM prostudio_generation_jobs WHERE id LIKE 'ok%%' AND id <> 'ok0'")
    assert cycle(env)["sent"] == [("generation_failures", "fire")]     # 5 of 6
    assert "5 ошибок из 6" in env.tg.sent[0]
    q(env, "UPDATE prostudio_generation_jobs SET completed_at = NOW() - INTERVAL '2 hours'")  # old news
    q(env, "UPDATE ops_alert_state SET last_seen_at = NOW() - INTERVAL '6 minutes'")
    assert cycle(env)["sent"] == [("generation_failures", "resolve")]


def test_provider_circuit_per_provider(ops):
    env = ops
    q(env, "INSERT INTO prostudio_provider_circuits (provider, state, failure_count) VALUES "
           "('kling', 'OPEN', 5), ('openai', 'CLOSED', 0), ('runway', 'HALF_OPEN', 5)")
    before = snapshot(env)
    assert sorted(cycle(env)["sent"]) == [("provider_circuit:kling", "fire"), ("provider_circuit:runway", "fire")]
    assert snapshot(env) == before
    q(env, "UPDATE prostudio_provider_circuits SET state = 'CLOSED' WHERE provider = 'kling'")
    q(env, "UPDATE ops_alert_state SET last_seen_at = NOW() - INTERVAL '6 minutes' WHERE alert_key = 'provider_circuit:kling'")
    assert cycle(env)["sent"] == [("provider_circuit:kling", "resolve")]


def test_messages_carry_no_user_data(ops):
    env = ops
    job(env, "q1", "queued", age_min=12, uid=7000000123, prompt="SECRET_PROMPT_DO_NOT_LEAK")
    for i in range(5):
        job(env, f"f{i}", "failed", done_min=1, uid=7000000123)
    cycle(env)
    text = "\n".join(env.tg.sent)
    assert "7000000123" not in text and "SECRET_PROMPT" not in text and len(env.tg.sent) == 2


@pytest.mark.asyncio
async def test_status_endpoint_needs_a_totp_session_and_shows_deliveries(ops):
    env = ops
    job(env, "q1", "queued", age_min=12)
    cycle(env)
    q(env, "CREATE TABLE subscription_events (id BIGSERIAL PRIMARY KEY, event_type TEXT, telegram_id BIGINT, "
           "sent_at TIMESTAMPTZ, last_error TEXT, created_at TIMESTAMPTZ DEFAULT NOW())")
    q(env, "INSERT INTO subscription_events (event_type, telegram_id, sent_at, last_error) VALUES "
           "('payment_error', 7000000123, NOW(), NULL), ('subscription_purchased', 7000000123, NULL, 'Forbidden: bot was blocked')")
    assert (await call(env, "GET", "/api/admin/v2/ops/alerts")).status_code == 401
    token, _ = await login(env, OWNER_TG)
    r = await call(env, "GET", "/api/admin/v2/ops/alerts", cookie=token)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["alerts"][0]["alert_key"] == "workers_stalled" and data["alerts"][0]["state"] == "firing"
    assert data["deliveries"][0]["ok"] is True
    pn = data["payment_notifications"]
    assert (pn["delivered"], pn["pending"], pn["failing"]) == (1, 1, 1)
    assert pn["errors"] == [{"error": "Forbidden: bot was blocked", "count": 1}]
    assert "7000000123" not in r.text                              # aggregates only
    assert data["config"]["enabled"] is False                      # off until OPS_ALERTS_ENABLED=1


@pytest.mark.asyncio
async def test_test_message_is_owner_only_and_recorded(ops, monkeypatch):
    env = ops
    sent = []
    monkeypatch.setattr(env.main, "ops_alert_send", lambda text: sent.append(text) or (True, None))
    admin, admin_csrf = await login(env, ADMIN_TG)
    r = await call(env, "POST", "/api/admin/v2/ops/alerts/test", cookie=admin, csrf=admin_csrf)
    assert r.status_code == 403 and r.json()["detail"] == "owner_access_required" and sent == []
    owner, owner_csrf = await login(env, OWNER_TG)
    assert (await call(env, "POST", "/api/admin/v2/ops/alerts/test", cookie=owner)).status_code == 403   # no CSRF
    r = await call(env, "POST", "/api/admin/v2/ops/alerts/test", cookie=owner, csrf=owner_csrf)
    assert r.status_code == 200 and r.json()["delivered"] is True and len(sent) == 1
    assert sent[0].startswith("🧪 SYLVEX: тестовое оповещение")
    assert q(env, "SELECT alert_key, event, ok FROM ops_alert_deliveries") == [["test", "test", True]]
    assert q(env, "SELECT action FROM admin_audit_events WHERE action = 'ops_alert_test'") == [["ops_alert_test"]]


def test_database_unreachable_is_reported_once_and_recovery_too(ready, monkeypatch):
    env = ready
    main = env.main
    sent, calls = [], {"n": 0}

    def cycle_fn():
        calls["n"] += 1
        if calls["n"] <= 4:
            raise RuntimeError("database down")
        return {"sent": [], "failed": []}

    async def fake_sleep(_):
        if calls["n"] >= 6:
            raise asyncio.CancelledError

    monkeypatch.setattr(main, "run_ops_alerts_cycle", cycle_fn)
    monkeypatch.setattr(main, "ops_alert_send", lambda text: sent.append(text) or (True, None))
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.ops_alerts_worker_loop())
    assert len(sent) == 2                                          # one alert after 3 failures, one recovery
    assert "база данных недоступна" in sent[0] and sent[1].startswith("✅ SYLVEX: восстановлено")


def test_alerts_are_off_by_default(ready):
    assert ready.main.OPS_ALERTS_ENABLED is False
