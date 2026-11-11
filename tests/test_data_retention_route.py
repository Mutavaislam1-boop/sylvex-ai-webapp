"""B09 / S8-08: the read-only retention preview route (PGlite, synthetic rows)."""
import pytest

from test_admin_console_auth import OWNER_TG, call, env, login, q, ready  # noqa: F401  (fixtures)


@pytest.mark.asyncio
async def test_preview_needs_a_session_and_changes_nothing(ready):
    env = ready
    r = await call(env, "GET", "/api/admin/v2/retention")
    assert r.status_code == 401
    q(env, "CREATE TABLE prostudio_errors(id SERIAL PRIMARY KEY, telegram_id BIGINT, created_at TIMESTAMP DEFAULT NOW())")
    q(env, "INSERT INTO prostudio_errors(telegram_id, created_at) VALUES (1, NOW() - INTERVAL '45 days'), (2, NOW())")
    token, _ = await login(env, OWNER_TG)
    r = await call(env, "GET", "/api/admin/v2/retention", cookie=token)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is False and data["error_logs"] == {"prostudio_errors": 1}
    assert data["rules"] == {"error_log_days": 30, "support_closed_months": 12}
    assert q(env, "SELECT COUNT(*) FROM prostudio_errors") == [[2]]
