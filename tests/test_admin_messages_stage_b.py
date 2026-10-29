"""Admin Console, messages: inbox statuses (new / in progress / waiting for
the person / closed), assignee, search and filters, attachments allowed per
conversation, the sales department, review stats and replies, and
announcements by surface and plan with a preview and a delivery log. Real
SQL (PGlite); Telegram is recorded, never sent."""
import asyncio
import base64

import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    ADMIN_TG, FINANCE_TG, OWNER_TG, SUPPORT_TG, USER_TG, call, env, init_data, login, q, ready,
)

pytestmark = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

OTHER_TG = 7000000002
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


@pytest.fixture
def world(ready, monkeypatch):
    env = ready
    sent = []

    def deliver(chat, text, image=None, links=None):
        sent.append((chat, text))
        return {"ok": False, "error": "Forbidden: bot was blocked by the user"} if chat == OTHER_TG else {"ok": True, "error": None}
    monkeypatch.setattr(env.main, "_telegram_deliver_status", deliver)
    monkeypatch.setattr(env.main, "storage_put_bytes", lambda content, key, mime: f"https://cdn.test/{key}")
    for flag in ("NOTIFICATIONS_SCHEMA_READY", "_PAYMENT_SCHEMA_READY", "_PROSTUDIO_SCHEMA_READY"):
        monkeypatch.setattr(env.main, flag, False)
    env.main._ACCESS_CACHE.clear()
    env.main._SURFACE_SEEN.clear()
    conn = env.db.connect()
    cur = conn.cursor()
    for tid, name in ((USER_TG, "Alina"), (OTHER_TG, "Marat")):
        cur.execute("INSERT INTO users (telegram_id, first_name, username, balance) VALUES (%s, %s, %s, 0)",
                    (tid, name, name.lower()))
        env.ai.ensure_telegram_account(cur, tid)
    conn.commit()
    env.sent = sent
    env.account = lambda tid: q(env, "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (tid,))[0][0]
    return env


async def admin(env, path, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", path, cookie=token, csrf=csrf, json_body=body)


async def user_get(env, path, uid=USER_TG):
    return await call(env, "GET", path, origin=None, headers={"X-Telegram-Init-Data": init_data(uid)})


async def user_post(env, path, body, uid=USER_TG):
    return await call(env, "POST", path, origin=None, json_body=body, headers={"X-Telegram-Init-Data": init_data(uid)})


async def settle():
    for _ in range(10):
        await asyncio.sleep(0.02)


async def contact(env, text, uid=USER_TG, topic="support"):
    r = await user_post(env, "/api/public/contact", {"message": text, "topic": topic, "surface": "miniapp"}, uid)
    assert r.status_code == 200, r.text
    return r.json()["thread_id"]


# --- inbox ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_statuses_assignee_and_counts(world):
    env = world
    thread = await contact(env, "My video failed")
    await contact(env, "Hello", uid=OTHER_TG)
    data = (await admin(env, "/api/admin/inbox/list", {})).json()
    assert data["counts"]["open"] == 2 and data["counts"]["unread"] == 2 and data["unread"] == 2
    # Taking it: in progress, assigned to me.
    r = await admin(env, "/api/admin/inbox/assign", {"thread_id": thread, "admin_id": "me"}, who=SUPPORT_TG)
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    mine = (await admin(env, "/api/admin/inbox/list", {"assignee": "me"}, who=SUPPORT_TG)).json()
    assert [i["id"] for i in mine["items"]] == [thread] and mine["items"][0]["assignee_name"]
    assert (await admin(env, "/api/admin/inbox/list", {"assignee": "none"})).json()["total"] == 1
    # Replying makes it "waiting for the person"; them writing again keeps it with us.
    r = await admin(env, "/api/admin/inbox/reply", {"thread_id": thread, "text": "We are on it"}, who=SUPPORT_TG)
    assert r.status_code == 200
    assert q(env, "SELECT status, first_reply_at IS NOT NULL FROM support_threads WHERE id = %s", (thread,)) == [["answered", True]]
    await contact(env, "Thanks, still broken")
    assert q(env, "SELECT status FROM support_threads WHERE id = %s", (thread,)) == [["open"]]
    r = await admin(env, "/api/admin/inbox/status", {"thread_id": thread, "status": "in_progress"})
    assert r.status_code == 200
    await contact(env, "Any news?")
    assert q(env, "SELECT status FROM support_threads WHERE id = %s", (thread,)) == [["in_progress"]]
    # Every change is in the audit log.
    actions = {r[0] for r in q(env, "SELECT action FROM admin_audit_events")}
    assert {"support_assigned", "support_status_changed", "support_reply_sent"} <= actions


@pytest.mark.asyncio
async def test_giving_a_conversation_to_someone_else_needs_support_manage(world):
    env = world
    thread = await contact(env, "Help")
    support_admin = q(env, "SELECT a.id FROM admin_accounts a JOIN sylvex_accounts s ON s.account_id = a.account_id "
                           "WHERE s.active_telegram_id = %s", (SUPPORT_TG,))[0][0]
    # Finance cannot answer at all; support may give it to a colleague.
    assert (await admin(env, "/api/admin/inbox/assign", {"thread_id": thread, "admin_id": "me"}, who=FINANCE_TG)).status_code == 403
    r = await admin(env, "/api/admin/inbox/assign", {"thread_id": thread, "admin_id": support_admin}, who=ADMIN_TG)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_search_and_filters(world):
    env = world
    await contact(env, "Payment did not arrive")
    await contact(env, "Need a team plan", uid=OTHER_TG, topic="sales")
    found = (await admin(env, "/api/admin/inbox/list", {"query": "payment"})).json()["items"]
    assert len(found) == 1 and found[0]["topic"] == "support"
    assert len((await admin(env, "/api/admin/inbox/list", {"query": "marat"})).json()["items"]) == 1
    assert len((await admin(env, "/api/admin/inbox/list", {"query": str(env.account(USER_TG))})).json()["items"]) == 1
    convs = (await admin(env, "/api/admin/inbox/list", {"exclude_topic": "sales"})).json()
    assert [i["topic"] for i in convs["items"]] == ["support"] and convs["unread_by"] == {"sales": 1, "conversations": 1}
    sales = (await admin(env, "/api/admin/inbox/list", {"topic": "sales", "unread": True})).json()["items"]
    assert len(sales) == 1


@pytest.mark.asyncio
async def test_attachments_only_when_allowed_and_only_your_own(world):
    env = world
    thread = await contact(env, "Screenshot of the error?")
    assert (await user_get(env, "/api/public/contact/state")).json()["attachments_allowed"] is False
    r = await user_post(env, "/api/public/contact/upload", {"content_base64": PNG, "name": "err.png"})
    assert r.status_code == 403 and "attachments_not_allowed" in r.text
    # Support may answer but not change the window; managing it is support.manage.
    assert (await admin(env, "/api/admin/inbox/attachments", {"thread_id": thread, "allowed": True}, who=FINANCE_TG)).status_code == 403
    r = await admin(env, "/api/admin/inbox/attachments", {"thread_id": thread, "allowed": True}, who=SUPPORT_TG)
    assert r.status_code == 200, r.text
    assert (await user_get(env, "/api/public/contact/state")).json()["attachments_allowed"] is True
    r = await user_post(env, "/api/public/contact/upload", {"content_base64": base64.b64encode(b"MZ\x90").decode()})
    assert r.status_code == 400 and "unsupported_file" in r.text
    up = (await user_post(env, "/api/public/contact/upload", {"content_base64": PNG, "name": "err.png"})).json()["attachment"]
    assert "key" not in up and up["id"].endswith(".png") and up["mime"] == "image/png"
    # A made-up name or a path is refused; an id always means the sender's own folder.
    for bad in ({"id": "../a1/x.png"}, {"id": "generated/support-uploads/a1/" + up["id"]}):
        r = await user_post(env, "/api/public/contact", {"message": "x", "attachments": [bad]})
        assert r.status_code in (400, 403), r.text
    r = await user_post(env, "/api/public/contact", {"message": "Here it is", "attachments": [up]})
    assert r.status_code == 200, r.text
    detail = (await admin(env, "/api/admin/inbox/thread", {"thread_id": thread})).json()
    files = detail["messages"][-1]["attachments"]
    assert files[0]["name"] == "err.png" and files[0]["url"]
    assert files[0]["key"] == f"generated/support-uploads/a{env.account(USER_TG)}/{up['id']}"
    assert detail["thread"]["attachments_allowed"] is True


# --- reviews ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_stats_filters_and_reply(world):
    env = world
    env.main.ensure_notification_tables()
    conn = env.db.connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO project_reviews (person_key, account_id, user_key, rating, body, surface) VALUES "
                "(%s, %s, %s, 2, 'Slow video', 'miniapp'), ('t:7000000002', NULL, %s, 5, '', 'website')",
                (f"a:{env.account(USER_TG)}", env.account(USER_TG), USER_TG, OTHER_TG))
    conn.commit()
    data = (await admin(env, "/api/admin/reviews/list", {})).json()
    s = data["summary"]
    assert s["count"] == 2 and s["average"] == 3.5 and s["with_comment"] == 1 and s["answered"] == 0
    assert s["by_surface"]["miniapp"] == {"count": 1, "average": 2.0}
    assert s["last_30_days"]["count"] == 2
    low = (await admin(env, "/api/admin/reviews/list", {"with_text": "yes", "surface": "miniapp"})).json()["items"]
    assert [r["rating"] for r in low] == [2]
    review_id = low[0]["id"]
    r = await admin(env, "/api/admin/reviews/reply", {"review_id": review_id, "text": "Thank you! Fixed today."})
    assert r.status_code == 200, r.text
    await settle()
    assert r.json()["delivery"]["telegram"] == "sent" and env.sent[-1][0] == USER_TG
    bell = (await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"]
    assert bell[0]["text"] == "Thank you! Fixed today."
    after = (await admin(env, "/api/admin/reviews/list", {"replied": "yes"})).json()
    assert after["items"][0]["reply"] == "Thank you! Fixed today." and after["items"][0]["replied_by_name"]
    assert after["summary"]["answered"] == 1
    # The reply lives in the person's conversation too.
    convo = (await admin(env, "/api/admin/users/conversation", {"sylvex_user_id": str(env.account(USER_TG))})).json()
    assert [m["text"] for m in convo["messages"]] == ["Thank you! Fixed today."]


# --- announcements ------------------------------------------------------------

@pytest.mark.asyncio
async def test_surfaces_are_recorded_from_real_requests(world):
    env = world
    await user_get(env, "/api/public/notifications?surface=miniapp")
    await settle()
    assert q(env, "SELECT user_key, surface FROM user_surface_usage") == [[USER_TG, "telegram_miniapp"]]


def test_surface_detection():
    from services.platform_usage import surface_of
    site = ("https://sylvex.ai",)
    assert surface_of("telegram", "", "", site) == "telegram_miniapp"
    assert surface_of("web", "https://sylvex.ai", "", site) == "website"
    assert surface_of("web", "", "https://app.test/webapp/index.html?embed=web", site) == "website"
    assert surface_of("web", "", "https://app.test/webapp/index.html", site) == "browser_miniapp"
    assert surface_of("service", "", "", site) is None


@pytest.mark.asyncio
async def test_segment_by_surface_and_plan_with_preview_and_log(world):
    env = world
    env.main.ensure_payment_tables()
    env.main.ensure_notification_tables()
    q(env, "INSERT INTO user_surface_usage (user_key, surface) VALUES (%s, 'telegram_miniapp')", (USER_TG,))
    q(env, "INSERT INTO subscriptions (telegram_id, subscription_type, status, expires_at) "
           "VALUES (%s, 'pro_month', 'active', NOW() + INTERVAL '10 days')", (OTHER_TG,))
    body = {"audience": "segment", "segment": {"surfaces": ["telegram_miniapp"]}, "text": "New tools in the Mini App"}
    # Preparing needs broadcast.create; support cannot.
    assert (await admin(env, "/api/admin/messages/preview", body, who=SUPPORT_TG)).status_code == 403
    preview = (await admin(env, "/api/admin/messages/preview", body)).json()
    assert preview["people"] == 1 and preview["channels"] == ["miniapp"] and preview["telegram_recipients"] == 0
    # By plan: paid users via the bot.
    paid = {"audience": "segment", "segment": {"plans": ["pro"]}, "channels": ["telegram"], "text": "Pro news"}
    preview = (await admin(env, "/api/admin/messages/preview", paid)).json()
    assert preview["people"] == 1 and preview["telegram_recipients"] == 1
    free = (await admin(env, "/api/admin/messages/preview", {"audience": "segment", "segment": {"plans": ["free"]}})).json()
    assert free["people"] >= 1
    assert (await admin(env, "/api/admin/messages/preview", {"audience": "segment", "segment": {}})).status_code == 400
    # Sending: the bell for the Mini App segment, Telegram for the plan
    # segment with the refusal counted by reason.
    r = await admin(env, "/api/admin/messages/send", body)
    assert r.status_code == 200 and r.json()["bell_recipients"] == 1, r.text
    assert len((await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"]) == 1
    assert (await user_get(env, "/api/public/notifications?surface=miniapp", OTHER_TG)).json()["items"] == []
    r = await admin(env, "/api/admin/messages/send", paid)
    assert r.status_code == 200 and r.json()["telegram_recipients"] == 1
    await settle()
    log = (await admin(env, "/api/admin/messages/history", {})).json()["items"]
    assert log[0]["segment"] == {"surfaces": [], "plans": ["pro"]}
    assert log[0]["telegram_failed"] == 1 and log[0]["telegram_errors"] == {"blocked": 1} and log[0]["admin_name"]
    assert log[1]["segment"]["surfaces"] == ["telegram_miniapp"]
