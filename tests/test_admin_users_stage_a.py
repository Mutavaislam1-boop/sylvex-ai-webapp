"""Admin Console, users and staff: writing to one user with the real
delivery result, blocking and unblocking (enforced on every protected
route), assigning roles from the user card (owner only), reason presets
and the "you received" award cards. Real SQL (PGlite); Telegram is
recorded, never sent."""
import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    ADMIN_TG, FINANCE_TG, OWNER_TG, SUPPORT_TG, USER_TG, call, env, init_data, login, q, ready,
)

pytestmark = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

OTHER_TG = 7000000002


@pytest.fixture
def world(ready, monkeypatch):
    env = ready
    sent = []
    env.telegram_answer = {"ok": True, "error": None}
    monkeypatch.setattr(env.main, "_telegram_deliver_status",
                        lambda chat, text, image=None, links=None: sent.append((chat, text)) or env.telegram_answer)
    for flag in ("NOTIFICATIONS_SCHEMA_READY", "_PAYMENT_SCHEMA_READY", "_PROSTUDIO_SCHEMA_READY"):
        monkeypatch.setattr(env.main, flag, False)
    env.main._ACCESS_CACHE.clear()
    conn = env.db.connect()
    cur = conn.cursor()
    for tid, name in ((USER_TG, "Alina"), (OTHER_TG, "Marat")):
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, %s, 10)", (tid, name))
        env.ai.ensure_telegram_account(cur, tid)
    conn.commit()
    env.sent = sent
    env.account = lambda tid: q(env, "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (tid,))[0][0]
    return env


async def admin(env, path, body, who=OWNER_TG, method="POST"):
    token, csrf = await login(env, who)
    return await call(env, method, path, cookie=token, csrf=csrf, json_body=body)


async def user_get(env, path, uid=USER_TG):
    return await call(env, "GET", path, origin=None, headers={"X-Telegram-Init-Data": init_data(uid)})


async def user_post(env, path, body, uid=USER_TG):
    return await call(env, "POST", path, origin=None, json_body=body, headers={"X-Telegram-Init-Data": init_data(uid)})


def target(env, tid=USER_TG):
    return {"sylvex_user_id": str(env.account(tid))}


# --- writing to one user ------------------------------------------------------

@pytest.mark.asyncio
async def test_write_to_user_reaches_every_surface_and_records_the_bot_answer(world):
    env = world
    r = await admin(env, "/api/admin/users/message/send", dict(target(env), text="Your refund is done"))
    assert r.status_code == 200, r.text
    delivery = r.json()["delivery"]
    assert delivery["channels"] == ["website", "miniapp", "telegram"] and delivery["telegram"] == "sent"
    assert env.sent == [(USER_TG, "💬 SYLVEX Team\n\nYour refund is done")]
    for surface in ("miniapp", "website"):
        items = (await user_get(env, f"/api/public/notifications?surface={surface}")).json()["items"]
        assert [i["text"] for i in items] == ["Your refund is done"]
    # The message lives in Messages too, so the whole conversation is in one place.
    convo = (await admin(env, "/api/admin/users/conversation", target(env))).json()
    assert [m["text"] for m in convo["messages"]] == ["Your refund is done"]
    assert convo["messages"][0]["delivery"]["telegram"] == "sent" and convo["messages"][0]["author"]
    assert convo["channels"] == {"website": True, "miniapp": True, "telegram": True}
    inbox = (await admin(env, "/api/admin/inbox/list", {})).json()
    assert inbox["total"] == 1
    assert q(env, "SELECT COUNT(*) FROM admin_audit_events WHERE action = 'message_sent'") == [[1]]


@pytest.mark.asyncio
async def test_a_refused_telegram_delivery_is_reported_with_its_reason(world):
    env = world
    env.telegram_answer = {"ok": False, "error": "Forbidden: bot was blocked by the user"}
    r = await admin(env, "/api/admin/users/message/send", dict(target(env), text="Hello", channels=["telegram"]))
    assert r.status_code == 200, r.text
    delivery = r.json()["delivery"]
    assert delivery["telegram"] == "failed" and "blocked" in delivery["telegram_error"]
    # Telegram only: nothing in the bell.
    assert (await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"] == []
    convo = (await admin(env, "/api/admin/users/conversation", target(env))).json()
    assert convo["messages"][0]["delivery"]["telegram"] == "failed"


@pytest.mark.asyncio
async def test_writing_needs_the_messages_permission(world):
    env = world
    r = await admin(env, "/api/admin/users/message/send", dict(target(env), text="Hi"), who=FINANCE_TG)
    assert r.status_code == 403
    assert env.sent == []


# --- blocking -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_block_stops_protected_routes_but_keeps_status_and_contact(world):
    env = world
    assert (await user_get(env, "/api/public/account/status")).json() == {"ok": True, "blocked": False}
    r = await admin(env, "/api/admin/users/block", dict(target(env), reason="Spam", note="3 reports"))
    assert r.status_code == 200, r.text
    assert r.json()["block"]["reason"] == "Spam"
    status = (await user_get(env, "/api/public/account/status")).json()
    assert status["blocked"] is True and status["reason"] == "Spam" and status["since"]
    blocked = await user_get(env, "/api/public/prostudio/conversations")
    assert blocked.status_code == 403 and "account_blocked" in blocked.text
    # Still reachable: the bell and the contact form (to appeal).
    assert (await user_get(env, "/api/public/notifications?surface=miniapp")).status_code == 200
    assert (await user_post(env, "/api/public/contact", {"message": "Why?", "topic": "support"})).status_code == 200
    # Someone else is not affected.
    assert (await user_get(env, "/api/public/prostudio/conversations", OTHER_TG)).status_code != 403
    # The card shows the active block, who set it and the history.
    detail = (await admin(env, "/api/admin/users/detail", target(env))).json()
    assert detail["block"]["reason"] == "Spam" and detail["block"]["note"] == "3 reports"
    assert detail["block"]["admin_name"]
    assert any(h["action"] == "user_blocked" for h in detail["admin_history"])
    # Blocked twice is refused; unblocking needs a reason and restores access.
    assert (await admin(env, "/api/admin/users/block", dict(target(env), reason="Again"))).status_code == 409
    assert (await admin(env, "/api/admin/users/unblock", target(env))).status_code == 400
    r = await admin(env, "/api/admin/users/unblock", dict(target(env), reason="Appeal accepted"))
    assert r.status_code == 200, r.text
    assert (await user_get(env, "/api/public/account/status")).json()["blocked"] is False
    assert (await user_get(env, "/api/public/prostudio/conversations")).status_code != 403
    history = (await admin(env, "/api/admin/users/detail", target(env))).json()["block_history"]
    assert history[0]["lift_reason"] == "Appeal accepted" and history[0]["active"] is False


@pytest.mark.asyncio
async def test_block_needs_permission_reason_and_never_hits_the_owner(world):
    env = world
    assert (await admin(env, "/api/admin/users/block", dict(target(env), reason="x"), who=SUPPORT_TG)).status_code == 403
    assert (await admin(env, "/api/admin/users/block", target(env))).status_code == 400
    r = await admin(env, "/api/admin/users/block", dict(target(env, OWNER_TG), reason="x"), who=ADMIN_TG)
    assert r.status_code == 409 and r.json()["detail"] == "owner_cannot_be_blocked"


@pytest.mark.asyncio
async def test_search_shows_source_and_block_and_filters_by_source(world):
    env = world
    env.main.ensure_payment_tables()
    await admin(env, "/api/admin/users/block", dict(target(env), reason="Spam"))
    items = (await admin(env, "/api/admin/users/search", {"query": "Alina"})).json()["items"]
    assert items[0]["blocked"] is True and items[0]["source"] == "telegram"
    assert (await admin(env, "/api/admin/users/search", {"query": "Alina", "source": "website"})).json()["items"] == []
    found = (await admin(env, "/api/admin/users/search", {"query": "", "source": "telegram"})).json()["items"]
    assert {USER_TG, OTHER_TG} <= {i["telegram_id"] for i in found}


# --- reasons and award cards ----------------------------------------------------

@pytest.mark.asyncio
async def test_credits_with_a_preset_reason_show_one_award_card(world):
    env = world
    r = await admin(env, "/api/admin/users/balance", dict(target(env), delta=50, reason_code="error_compensation",
                                                         note="Video #12 failed"))
    assert r.status_code == 200 and r.json()["balance"] == 60
    row = q(env, "SELECT reason, after->>'reason_code' AS code, after->>'note' AS note FROM admin_audit_events "
                 "WHERE action = 'balance_changed'")
    assert row == [["Компенсация ошибки", "error_compensation", "Video #12 failed"]]
    awards = (await user_get(env, "/api/public/notifications/awards")).json()["items"]
    assert len(awards) == 1
    assert awards[0]["award"] == {"type": "credits", "amount": 50, "reason_code": "error_compensation"}
    # The bell is unchanged: an award is not a bell message.
    assert (await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"] == []
    # Seen once on any surface, never again.
    await user_post(env, "/api/public/notifications/read", {"ids": [awards[0]["notification_id"]]})
    assert (await user_get(env, "/api/public/notifications/awards")).json()["items"] == []
    # A debit is not an award; an internal reason is not shown to the user.
    await admin(env, "/api/admin/users/balance", dict(target(env), delta=-5, reason_code="other", reason="Fix"))
    await admin(env, "/api/admin/users/balance", dict(target(env), delta=5, reason_code="test"))
    awards = (await user_get(env, "/api/public/notifications/awards")).json()["items"]
    assert [a["award"]["amount"] for a in awards] == [5] and awards[0]["award"]["reason_code"] is None


@pytest.mark.asyncio
async def test_a_gifted_subscription_shows_an_award_card(world):
    env = world
    r = await admin(env, "/api/admin/users/subscription", dict(target(env), action="extend", days=30, reason_code="gift"))
    assert r.status_code == 200, r.text
    awards = (await user_get(env, "/api/public/notifications/awards")).json()["items"]
    assert awards[0]["award"]["type"] == "subscription" and awards[0]["award"]["days"] == 30
    assert awards[0]["award"]["reason_code"] == "gift"


# --- roles from the user card -----------------------------------------------------

@pytest.mark.asyncio
async def test_only_the_owner_assigns_roles_and_never_the_owner_role(world):
    env = world
    body = dict(target(env), role="moderator", reason_code="hire")
    r = await admin(env, "/api/admin/v2/users/role", body, who=ADMIN_TG)
    assert r.status_code == 403
    r = await admin(env, "/api/admin/v2/users/role", dict(body, role="owner"))
    assert r.status_code == 403 and r.json()["detail"] == "owner_role_not_assignable"
    r = await admin(env, "/api/admin/v2/users/role", body)
    assert r.status_code == 200, r.text
    assert r.json()["admin"]["role"] == "moderator"
    # The Admins section sees the same row.
    admins = (await admin(env, "/api/admin/v2/admins", None, method="GET")).json()["items"]
    assert any(a["sylvex_user_id"] == str(env.account(USER_TG)) and a["role"] == "moderator" for a in admins)
    detail = (await admin(env, "/api/admin/users/detail", target(env))).json()
    assert detail["staff"]["role"] == "moderator"
    awards = (await user_get(env, "/api/public/notifications/awards")).json()["items"]
    assert awards[0]["award"]["type"] == "role" and awards[0]["award"]["role"] == "moderator"
    # Removing the role revokes the admin.
    r = await admin(env, "/api/admin/v2/users/role", dict(target(env), role="", reason_code="offboarding"))
    assert r.status_code == 200 and r.json()["admin"]["status"] == "revoked"
    # A reason is required.
    assert (await admin(env, "/api/admin/v2/users/role", dict(target(env), role="analyst"))).status_code == 400


@pytest.mark.asyncio
async def test_permission_catalog_explains_every_permission_and_risk(world):
    env = world
    data = (await admin(env, "/api/admin/v2/permissions", None, method="GET")).json()
    catalog = data["catalog"]
    assert set(catalog) == set(env.main.admin_rbac.PERMISSIONS)
    for name, p in catalog.items():
        assert p["description"]["en"] and p["description"]["ru"] != name and p["risk"] in data["risk_info"]
    assert data["risk_info"]["critical"]["ru"]
