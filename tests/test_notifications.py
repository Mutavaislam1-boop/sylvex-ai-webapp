"""Unified notifications: Admin Console -> Telegram + Mini App bell + website
bell, website visitors, and the internal Contact SYLVEX inbox with personal
replies. Real SQL (PGlite); Telegram delivery is recorded, never sent."""
import asyncio
import base64

import pytest

from test_admin_console_auth import (  # noqa: F401  (fixtures)
    OWNER_TG, SUPPORT_TG, USER_TG, call, env, init_data, login, q, ready,
)

pytestmark = pytest.mark.skipif(not __import__("os").getenv("SYLVEX_PGLITE_MODULE"), reason="needs PGlite")

OTHER_TG = 7000000002


@pytest.fixture
def world(ready, monkeypatch):
    env = ready
    sent = []
    monkeypatch.setattr(env.main, "_telegram_deliver_status",
                        lambda chat, text, image=None, links=None: sent.append((chat, text, image, links)) or {"ok": True, "error": None})
    monkeypatch.setattr(env.main, "NOTIFICATIONS_SCHEMA_READY", False)
    conn = env.db.connect()
    cur = conn.cursor()
    for tid, name in ((USER_TG, "Alina"), (OTHER_TG, "Marat")):
        cur.execute("INSERT INTO users (telegram_id, first_name, balance) VALUES (%s, %s, 0)", (tid, name))
        env.ai.ensure_telegram_account(cur, tid)
    conn.commit()
    env.sent = sent
    env.account = lambda tid: q(env, "SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (tid,))[0][0]
    return env


async def user_get(env, path, uid=USER_TG):
    return await call(env, "GET", path, origin=None, headers={"X-Telegram-Init-Data": init_data(uid)})


async def user_post(env, path, body, uid=USER_TG):
    return await call(env, "POST", path, origin=None, json_body=body, headers={"X-Telegram-Init-Data": init_data(uid)})


async def admin(env, path, body, who=OWNER_TG):
    token, csrf = await login(env, who)
    return await call(env, "POST", path, cookie=token, csrf=csrf, json_body=body)


async def settle():
    for _ in range(5):
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_selected_message_reaches_bell_and_telegram_as_sylvex_team(world):
    env = world
    r = await admin(env, "/api/admin/messages/send", {
        "audience": "selected", "recipients": [f"a:{env.account(USER_TG)}"], "text": "New model is live",
        "links": [{"url": "https://sylvex.ai/store.html", "label": "Open Store"}]})
    assert r.status_code == 200, r.text
    assert r.json()["channels"] == ["telegram", "miniapp", "website"]  # nothing chosen = everywhere
    await settle()
    assert env.sent and env.sent[0][0] == USER_TG and env.sent[0][1] == "New model is live"
    r = await user_get(env, "/api/public/notifications?surface=miniapp")
    data = r.json()
    assert r.status_code == 200 and data["unread"] == 1
    item = data["items"][0]
    assert item["sender"] == "SYLVEX Team" and item["text"] == "New model is live" and not item["read"]
    assert item["links"] == [{"url": "https://sylvex.ai/store.html", "label": "Open Store"}]
    # The other user sees nothing.
    assert (await user_get(env, "/api/public/notifications?surface=miniapp", OTHER_TG)).json()["items"] == []
    # Read on one surface = read on the other (one history per account).
    r = await user_post(env, "/api/public/notifications/read", {"all": True})
    assert r.json()["marked"] == 1
    web = (await user_get(env, "/api/public/notifications?surface=website")).json()
    assert web["unread"] == 0 and web["items"][0]["read"] is True


@pytest.mark.asyncio
async def test_channel_choice_limits_where_it_shows(world):
    env = world
    r = await admin(env, "/api/admin/messages/send", {
        "audience": "selected", "recipients": [f"a:{env.account(USER_TG)}"], "text": "Mini App only", "channels": ["miniapp"]})
    assert r.status_code == 200, r.text
    await settle()
    assert env.sent == []  # no Telegram
    assert len((await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"]) == 1
    assert (await user_get(env, "/api/public/notifications?surface=website")).json()["items"] == []
    r = await admin(env, "/api/admin/messages/send", {
        "audience": "selected", "recipients": [f"t:{OTHER_TG}"], "text": "Telegram only", "channels": ["telegram"]})
    await settle()
    assert [c for c, *_ in env.sent] == [OTHER_TG]
    assert (await user_get(env, "/api/public/notifications?surface=miniapp", OTHER_TG)).json()["items"] == []


@pytest.mark.asyncio
async def test_send_to_everyone_needs_broadcast_permission_and_reaches_everyone(world):
    env = world
    r = await admin(env, "/api/admin/messages/send", {"audience": "all", "text": "Hello all"}, who=SUPPORT_TG)
    assert r.status_code == 403
    visitor = (await call(env, "POST", "/api/public/visitor/ping", origin=None, json_body={"path": "/"})).json()["visitor_id"]
    r = await admin(env, "/api/admin/messages/send", {"audience": "all", "text": "Hello all"})
    assert r.status_code == 200, r.text
    await settle()
    assert {USER_TG, OTHER_TG} <= {c for c, *_ in env.sent}
    for uid in (USER_TG, OTHER_TG):
        assert (await user_get(env, "/api/public/notifications?surface=miniapp", uid)).json()["unread"] == 1
    r = await call(env, "GET", f"/api/public/visitor/notifications?visitor_id={visitor}", origin=None)
    assert r.json()["unread"] == 1 and r.json()["items"][0]["sender"] == "SYLVEX Team"
    assert q(env, "SELECT COUNT(*) FROM admin_audit_events WHERE action = 'broadcast_sent'") == [[1]]


@pytest.mark.asyncio
async def test_visitor_contact_reply_lands_in_their_bell(world):
    env = world
    r = await call(env, "POST", "/api/public/visitor/ping", origin=None, json_body={"path": "/store.html"})
    visitor = r.json()["visitor_id"]
    assert visitor.startswith("v_")
    # An unknown id is never adopted: the server issues its own.
    assert (await call(env, "POST", "/api/public/visitor/ping", origin=None,
                       json_body={"visitor_id": "v_" + "x" * 30})).json()["visitor_id"] != "v_" + "x" * 30
    r = await call(env, "POST", "/api/public/visitor/contact", origin=None,
                   json_body={"visitor_id": visitor, "message": "Do you have team plans?", "topic": "sales", "email": "a@b.co"})
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]
    inbox = (await admin(env, "/api/admin/inbox/list", {})).json()
    assert inbox["unread"] == 1 and inbox["items"][0]["topic"] == "sales" and inbox["items"][0]["visitor_id"] == visitor
    detail = (await admin(env, "/api/admin/inbox/thread", {"thread_id": thread_id})).json()
    assert detail["messages"][0]["text"] == "Do you have team plans?" and detail["thread"]["admin_unread"] is False
    r = await admin(env, "/api/admin/inbox/reply", {"thread_id": thread_id, "text": "Yes - see the Business plan."})
    assert r.status_code == 200 and r.json()["telegram"] is False
    bell = (await call(env, "GET", f"/api/public/visitor/notifications?visitor_id={visitor}", origin=None)).json()
    assert bell["items"][0]["text"] == "Yes - see the Business plan." and bell["items"][0]["sender"] == "SYLVEX Team"
    assert (await admin(env, "/api/admin/inbox/list", {"status": "answered"})).json()["total"] == 1


@pytest.mark.asyncio
async def test_mini_app_contact_reply_goes_to_bell_and_telegram(world):
    env = world
    r = await user_post(env, "/api/public/contact", {"message": "My video failed", "topic": "support", "surface": "miniapp"})
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]
    r = await admin(env, "/api/admin/inbox/reply", {"thread_id": thread_id, "text": "Refunded, sorry!"})
    assert r.status_code == 200 and r.json()["telegram_sent"] is True
    assert env.sent[-1][0] == USER_TG and env.sent[-1][1].endswith("Refunded, sorry!") and "SYLVEX Team" in env.sent[-1][1]
    items = (await user_get(env, "/api/public/notifications?surface=website")).json()["items"]
    assert items[0]["kind"] == "reply" and items[0]["text"] == "Refunded, sorry!"
    # A follow-up continues the same thread and reopens it.
    r = await user_post(env, "/api/public/contact", {"message": "Thanks!"})
    assert r.json()["thread_id"] == thread_id
    assert (await admin(env, "/api/admin/inbox/list", {"status": "open"})).json()["total"] == 1


@pytest.mark.asyncio
async def test_sales_request_reaches_the_inbox_with_its_fields(world):
    env = world
    visitor = (await call(env, "POST", "/api/public/visitor/ping", origin=None, json_body={"path": "/store.html"})).json()["visitor_id"]
    sales = {"kind": "organization", "company": "Northwind Studio", "team_size": "11–50", "website": "https://northwind.studio",
             "needs": ["video", "api", "unknown"], "budget": "500-2000", "comment": "30 launches a month",
             "name": "Anna", "email": "Anna@Northwind.Studio", "phone": "@anna_nw"}
    r = await call(env, "POST", "/api/public/visitor/contact", origin=None, json_body={"visitor_id": visitor, "sales": sales})
    assert r.status_code == 200, r.text
    thread_id = r.json()["thread_id"]
    item = (await admin(env, "/api/admin/inbox/list", {})).json()["items"][0]
    assert item["topic"] == "sales" and item["email"] == "anna@northwind.studio"
    message = (await admin(env, "/api/admin/inbox/thread", {"thread_id": thread_id})).json()["messages"][0]
    assert message["sales"]["needs"] == ["video", "api"] and message["sales"]["company"] == "Northwind Studio"
    assert message["text"].startswith("Заявка в отдел продаж") and "Организация: Northwind Studio" in message["text"]
    # A signed-in Mini App user sends the same form; a broken one is refused.
    r = await user_post(env, "/api/public/contact", {"surface": "miniapp", "sales": dict(sales, kind="private", company="")})
    assert r.status_code == 200, r.text
    assert (await user_post(env, "/api/public/contact", {"sales": dict(sales, email="nope")})).status_code == 400


@pytest.mark.asyncio
async def test_contact_is_rate_limited_and_validated(world):
    env = world
    assert (await user_post(env, "/api/public/contact", {"message": "   "})).status_code == 400
    assert (await user_post(env, "/api/public/contact", {"message": "x" * 4001})).status_code == 400
    for i in range(5):
        assert (await user_post(env, "/api/public/contact", {"message": f"m{i}"})).status_code == 200
    r = await user_post(env, "/api/public/contact", {"message": "one more"})
    assert r.status_code == 429
    r = await call(env, "POST", "/api/public/visitor/contact", origin=None, json_body={"visitor_id": "v_unknown_visitor_123", "message": "hi"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_audience_shows_sources_and_status(world):
    env = world
    q(env, "CREATE TABLE IF NOT EXISTS app_presence (telegram_id BIGINT PRIMARY KEY, current_view TEXT, platform TEXT, "
           "last_seen TIMESTAMP NOT NULL DEFAULT NOW(), created_at TIMESTAMP NOT NULL DEFAULT NOW())")
    q(env, "INSERT INTO app_presence (telegram_id, current_view, platform) VALUES (%s, 'home', 'ios')", (USER_TG,))
    visitor = (await call(env, "POST", "/api/public/visitor/ping", origin=None, json_body={"path": "/"})).json()["visitor_id"]
    rows = {r["key"]: r for r in (await admin(env, "/api/admin/audience", {"limit": 200})).json()["items"]}
    alina = rows[f"a:{env.account(USER_TG)}"]
    assert alina["status"] == "registered" and set(alina["sources"]) == {"telegram", "miniapp"}
    assert rows[f"v:{visitor}"]["status"] == "visitor" and rows[f"v:{visitor}"]["sources"] == ["website"]
    only = (await admin(env, "/api/admin/audience", {"source": "website", "status": "visitor"})).json()
    assert [r["key"] for r in only["items"]] == [f"v:{visitor}"]
    found = (await admin(env, "/api/admin/audience", {"query": "alina"})).json()["items"]
    assert [r["key"] for r in found] == [f"a:{env.account(USER_TG)}"]


@pytest.mark.asyncio
async def test_message_validation_and_image_upload(world, monkeypatch):
    env = world
    base = {"audience": "selected", "recipients": [f"a:{env.account(USER_TG)}"], "text": "hi"}
    assert (await admin(env, "/api/admin/messages/send", {**base, "links": [{"url": "javascript:alert(1)"}]})).status_code == 400
    assert (await admin(env, "/api/admin/messages/send", {**base, "links": [{"url": f"https://a.co/{i}"} for i in range(6)]})).status_code == 400
    assert (await admin(env, "/api/admin/messages/send", {**base, "channels": ["email"]})).status_code == 400
    assert (await admin(env, "/api/admin/messages/send", {**base, "image_key": "generated/references/x.png"})).status_code == 400
    r = await admin(env, "/api/admin/messages/upload-image", {"content_base64": base64.b64encode(b"<html>").decode()})
    assert r.status_code == 400 and r.json()["detail"] == "unsupported_image"
    monkeypatch.setattr(env.main, "storage_put_bytes", lambda data, key, mime: "/webapp/" + key)
    monkeypatch.setattr(env.main, "storage_object_url", lambda key: "https://cdn.test/" + key)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()
    r = await admin(env, "/api/admin/messages/upload-image", {"content_base64": png})
    assert r.status_code == 200, r.text
    key = r.json()["image_key"]
    assert key.startswith("generated/messages/") and key.endswith(".png")
    r = await admin(env, "/api/admin/messages/send", {**base, "image_key": key})
    assert r.status_code == 200, r.text
    await settle()
    assert env.sent[-1][2] == "https://cdn.test/" + key
    item = (await user_get(env, "/api/public/notifications?surface=miniapp")).json()["items"][0]
    assert item["image_url"] == "https://cdn.test/" + key
