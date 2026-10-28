"""Unified SYLVEX notifications, website visitors and the in-app contact inbox.

One notification history per person, shared by the Telegram Mini App and the
website (read on one = read on the other):

- A *person* is a live SYLVEX account (key "a:<account_id>"), a Telegram user
  with no SYLVEX account yet ("t:<telegram_id>"), or an anonymous website
  visitor ("v:<visitor_id>", a random id the server issues to the browser).
- user_notifications holds what was sent (always shown as "SYLVEX Team"),
  user_notification_recipients one row per person with its read state.
  A row is matched by account_id when the person has an account, so the same
  row is seen from the Mini App (Telegram initData) and from the website
  (web session) of that account.
- support_threads / support_messages: messages users send from the internal
  "Contact SYLVEX" popup, and the admins' personal replies.

Every function takes an open cursor; the caller commits.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from collections import OrderedDict

from services.account_identity import STORAGE_ID_FLOOR, real_telegram_id

SENDER_NAME = "SYLVEX Team"
SURFACES = ("miniapp", "website")
CHANNELS = ("telegram", "miniapp", "website")
TOPICS = ("support", "sales", "admin", "general")
MAX_TEXT = 4000
MAX_LINKS = 5
VISITOR_RE = re.compile(r"^v_[A-Za-z0-9_-]{16,64}$")
URL_RE = re.compile(r"^https?://[^\s<>\"']{3,2000}$", re.I)
EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$")
CONTACT_PER_10_MIN = 5
CONTACT_PER_IP_HOUR = 20


class NotificationError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS site_visitors (
            visitor_id TEXT PRIMARY KEY,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            visits INTEGER NOT NULL DEFAULT 1,
            surface TEXT NOT NULL DEFAULT 'website',
            last_path TEXT,
            account_id BIGINT,
            ip_hash TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_site_visitors_last_seen ON site_visitors(last_seen DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_site_visitors_account ON site_visitors(account_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_notifications (
            id BIGSERIAL PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'broadcast',
            body TEXT NOT NULL,
            image_key TEXT,
            links JSONB NOT NULL DEFAULT '[]'::jsonb,
            surfaces JSONB NOT NULL DEFAULT '[]'::jsonb,
            channels JSONB NOT NULL DEFAULT '[]'::jsonb,
            audience TEXT NOT NULL DEFAULT 'selected',
            recipients_count INTEGER NOT NULL DEFAULT 0,
            telegram_targets INTEGER NOT NULL DEFAULT 0,
            telegram_sent INTEGER NOT NULL DEFAULT 0,
            admin_id BIGINT,
            thread_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_notification_recipients (
            id BIGSERIAL PRIMARY KEY,
            notification_id BIGINT NOT NULL REFERENCES user_notifications(id) ON DELETE CASCADE,
            account_id BIGINT,
            user_key BIGINT,
            visitor_id TEXT,
            read_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unr_account ON user_notification_recipients(account_id, notification_id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unr_user_key ON user_notification_recipients(user_key, notification_id DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unr_visitor ON user_notification_recipients(visitor_id, notification_id DESC)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS support_threads (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT,
            user_key BIGINT,
            visitor_id TEXT,
            email TEXT,
            topic TEXT NOT NULL DEFAULT 'support',
            surface TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            admin_unread BOOLEAN NOT NULL DEFAULT TRUE,
            ip_hash TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_support_threads_last ON support_threads(last_message_at DESC)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id BIGSERIAL PRIMARY KEY,
            thread_id BIGINT NOT NULL REFERENCES support_threads(id) ON DELETE CASCADE,
            direction TEXT NOT NULL,
            body TEXT NOT NULL,
            image_key TEXT,
            links JSONB NOT NULL DEFAULT '[]'::jsonb,
            admin_id BIGINT,
            notification_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_support_messages_thread ON support_messages(thread_id, id)")
    # A structured request (Store -> Contact sales) keeps its fields next to the text.
    cur.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS details JSONB")


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


def _json_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value or [])


def _json_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def clean_text(text):
    text = str(text or "").strip()
    if not text:
        raise NotificationError("message_required")
    if len(text) > MAX_TEXT:
        raise NotificationError("message_too_long")
    return text


def clean_links(links):
    out = []
    for item in links or []:
        if isinstance(item, str):
            item = {"url": item}
        if not isinstance(item, dict):
            raise NotificationError("invalid_link")
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        if not URL_RE.match(url):
            raise NotificationError("invalid_link")
        label = str(item.get("label") or "").strip()[:60]
        out.append({"url": url, "label": label})
    if len(out) > MAX_LINKS:
        raise NotificationError("too_many_links")
    return out


def clean_channels(channels):
    """Admin's channel choice; nothing selected means everywhere."""
    chosen = [c for c in CHANNELS if c in set(channels or [])]
    unknown = set(channels or []) - set(CHANNELS)
    if unknown:
        raise NotificationError("invalid_channel")
    return chosen or list(CHANNELS)


def clean_image_key(key):
    key = str(key or "").strip()
    if not key:
        return None
    if not re.fullmatch(r"[A-Za-z0-9/_.-]{1,300}", key) or ".." in key or "/messages/" not in f"/{key}":
        raise NotificationError("invalid_image")
    return key


def new_visitor_id():
    return "v_" + secrets.token_urlsafe(24)


def valid_visitor_id(visitor_id):
    return bool(visitor_id and VISITOR_RE.match(str(visitor_id)))


class _Limiter:
    """In-process burst guard for anonymous traffic (new visitor ids)."""

    def __init__(self, limit, seconds):
        self.limit, self.seconds, self.items = limit, seconds, OrderedDict()

    def allow(self, key):
        now = time.monotonic()
        count, start = self.items.pop(key, (0, now))
        if now - start >= self.seconds:
            count, start = 0, now
        self.items[key] = (count + 1, start)
        while len(self.items) > 20000:
            self.items.popitem(last=False)
        return count < self.limit


new_visitor_limiter = _Limiter(60, 3600)


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

def account_for_key(cur, user_key):
    """The live SYLVEX account whose users.telegram_id storage key is
    `user_key` (a real Telegram id or a website storage key), or None."""
    if not user_key:
        return None
    cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s", (int(user_key),))
    row = cur.fetchone()
    return int(row[0]) if row else None


def _account_row(cur, account_id):
    cur.execute("SELECT account_id, active_telegram_id FROM sylvex_accounts WHERE account_id = %s", (int(account_id),))
    row = cur.fetchone()
    if row and row[1] is None:  # retired by a merge: follow it
        cur.execute("SELECT merged_into_account_id FROM sylvex_accounts WHERE account_id = %s", (int(account_id),))
        nxt = cur.fetchone()
        if nxt and nxt[0]:
            return _account_row(cur, nxt[0])
        return None
    return (int(row[0]), int(row[1])) if row else None


def resolve_person(cur, key):
    """'a:<id>' | 't:<telegram id>' | 'v:<visitor id>' -> person dict with
    account_id / user_key / visitor_id / telegram_chat (real chat or None)."""
    key = str(key or "").strip()
    kind, _, value = key.partition(":")
    if kind == "a" and value.isdigit():
        row = _account_row(cur, value)
        if row:
            return {"key": f"a:{row[0]}", "account_id": row[0], "user_key": row[1], "visitor_id": None,
                    "telegram_chat": real_telegram_id(row[1])}
    elif kind == "t" and value.isdigit():
        tid = int(value)
        account_id = account_for_key(cur, tid)
        if account_id:
            return resolve_person(cur, f"a:{account_id}")
        cur.execute("SELECT 1 FROM users WHERE telegram_id = %s", (tid,))
        if cur.fetchone() or real_telegram_id(tid):
            return {"key": f"t:{tid}", "account_id": None, "user_key": tid, "visitor_id": None,
                    "telegram_chat": real_telegram_id(tid)}
    elif kind == "v" and valid_visitor_id(value):
        cur.execute("SELECT account_id FROM site_visitors WHERE visitor_id = %s", (value,))
        row = cur.fetchone()
        if row:
            if row[0]:
                person = resolve_person(cur, f"a:{row[0]}")
                if person:
                    return person
            return {"key": f"v:{value}", "account_id": None, "user_key": None, "visitor_id": value,
                    "telegram_chat": None}
    return None


# --------------------------------------------------------------------------
# Website visitors
# --------------------------------------------------------------------------

def touch_visitor(cur, visitor_id, *, path="", account_id=None, ip_hash=None, surface="website"):
    """Records a website visit and returns the visitor id to keep (a fresh
    server-issued one when the browser had none or an unknown one)."""
    path = str(path or "")[:300]
    if valid_visitor_id(visitor_id):
        cur.execute("""
            UPDATE site_visitors SET last_seen = NOW(), visits = visits + 1, last_path = %s,
                account_id = COALESCE(%s, account_id)
            WHERE visitor_id = %s RETURNING visitor_id
        """, (path, account_id, visitor_id))
        if cur.fetchone():
            return visitor_id
    if not new_visitor_limiter.allow(ip_hash or "unknown"):
        raise NotificationError("rate_limited", 429)
    visitor_id = new_visitor_id()
    cur.execute("""
        INSERT INTO site_visitors (visitor_id, surface, last_path, account_id, ip_hash)
        VALUES (%s, %s, %s, %s, %s)
    """, (visitor_id, surface, path, account_id, ip_hash))
    return visitor_id


def visitor_exists(cur, visitor_id):
    if not valid_visitor_id(visitor_id):
        return False
    cur.execute("SELECT 1 FROM site_visitors WHERE visitor_id = %s", (visitor_id,))
    return cur.fetchone() is not None


# --------------------------------------------------------------------------
# Reading notifications (users)
# --------------------------------------------------------------------------

def _identity_clause(account_id, user_key, visitor_id):
    """WHERE fragment matching every recipient row that belongs to this
    person, whichever surface the row was addressed from."""
    parts, params = [], []
    if account_id:
        parts.append("r.account_id = %s")
        params.append(account_id)
        parts.append("r.visitor_id IN (SELECT visitor_id FROM site_visitors WHERE account_id = %s)")
        params.append(account_id)
    if user_key:
        parts.append("(r.account_id IS NULL AND r.user_key = %s)")
        params.append(int(user_key))
    if visitor_id:
        parts.append("r.visitor_id = %s")
        params.append(visitor_id)
    if not parts:
        return "FALSE", []
    return "(" + " OR ".join(parts) + ")", params


def list_for(cur, *, surface, account_id=None, user_key=None, visitor_id=None, limit=30, image_url=None):
    if surface not in SURFACES:
        raise NotificationError("invalid_surface")
    where, params = _identity_clause(account_id, user_key, visitor_id)
    surface_json = json.dumps([surface])
    cur.execute(f"""
        SELECT r.id AS rid, n.id AS nid, n.kind AS kind, n.body AS body, n.image_key AS image_key,
               n.links AS links, n.created_at AS created_at, r.read_at AS read_at
        FROM user_notification_recipients r JOIN user_notifications n ON n.id = r.notification_id
        WHERE {where} AND n.surfaces @> %s::jsonb
        ORDER BY n.id DESC, r.id DESC LIMIT %s
    """, params + [surface_json, max(1, min(int(limit or 30), 100))])
    items, seen = [], set()
    for rid, nid, kind, body, image_key, links, created_at, read_at in cur.fetchall():
        if nid in seen:  # same message reached the person by two keys
            continue
        seen.add(nid)
        items.append({"id": int(rid), "notification_id": int(nid), "kind": kind, "sender": SENDER_NAME,
                      "text": body, "image_url": image_url(image_key) if (image_key and image_url) else None,
                      "links": _json_list(links), "created_at": _iso(created_at), "read": read_at is not None})
    cur.execute(f"""
        SELECT COUNT(DISTINCT n.id) FROM user_notification_recipients r
        JOIN user_notifications n ON n.id = r.notification_id
        WHERE {where} AND n.surfaces @> %s::jsonb AND r.read_at IS NULL
    """, params + [surface_json])
    return items, int(cur.fetchone()[0] or 0)


def mark_read(cur, *, account_id=None, user_key=None, visitor_id=None, notification_ids=None):
    """Marks this person's rows read (all of them, or those notifications);
    shared by every surface, so reading in the Mini App clears the website."""
    where, params = _identity_clause(account_id, user_key, visitor_id)
    extra = ""
    if notification_ids:
        ids = [int(i) for i in notification_ids if str(i).isdigit()][:200]
        if not ids:
            return 0
        extra = " AND r.notification_id = ANY(%s::bigint[])"
        params = params + [ids]
    cur.execute(f"UPDATE user_notification_recipients r SET read_at = NOW() WHERE {where} AND r.read_at IS NULL{extra}",
                params)
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


# --------------------------------------------------------------------------
# Sending (admins)
# --------------------------------------------------------------------------

def create_notification(cur, *, text, links, image_key, surfaces, channels, audience, admin_id, kind="broadcast",
                        thread_id=None):
    cur.execute("""
        INSERT INTO user_notifications (kind, body, image_key, links, surfaces, channels, audience, admin_id, thread_id)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s) RETURNING id
    """, (kind, text, image_key, json.dumps(links), json.dumps(list(surfaces)), json.dumps(list(channels)),
          audience, admin_id, thread_id))
    return int(cur.fetchone()[0])


def add_recipients(cur, notification_id, people):
    for p in people:
        cur.execute("""
            INSERT INTO user_notification_recipients (notification_id, account_id, user_key, visitor_id)
            VALUES (%s, %s, %s, %s)
        """, (notification_id, p.get("account_id"), p.get("user_key"), p.get("visitor_id")))
    return len(people)


def add_everyone(cur, notification_id, surfaces):
    """Recipient rows for everyone, in a few set-based statements: every live
    account (only those that use Telegram when the message is Mini App only),
    Telegram users without an account, and - when the website is a target -
    anonymous website visitors."""
    total = 0
    only_miniapp = list(surfaces) == ["miniapp"]
    cur.execute(f"""
        INSERT INTO user_notification_recipients (notification_id, account_id, user_key)
        SELECT %s, s.account_id, s.active_telegram_id FROM sylvex_accounts s
        WHERE s.active_telegram_id IS NOT NULL {"AND s.active_telegram_id < %s" if only_miniapp else ""}
    """, (notification_id, STORAGE_ID_FLOOR) if only_miniapp else (notification_id,))
    total += max(cur.rowcount or 0, 0)
    cur.execute("""
        INSERT INTO user_notification_recipients (notification_id, user_key)
        SELECT %s, u.telegram_id FROM users u
        WHERE u.telegram_id > 0 AND u.telegram_id < %s
          AND NOT EXISTS (SELECT 1 FROM sylvex_accounts s WHERE s.active_telegram_id = u.telegram_id)
    """, (notification_id, STORAGE_ID_FLOOR))
    total += max(cur.rowcount or 0, 0)
    if "website" in surfaces:
        cur.execute("""
            INSERT INTO user_notification_recipients (notification_id, visitor_id)
            SELECT %s, v.visitor_id FROM site_visitors v WHERE v.account_id IS NULL
        """, (notification_id,))
        total += max(cur.rowcount or 0, 0)
    return total


def telegram_chats_for_everyone(cur):
    cur.execute("SELECT telegram_id FROM users WHERE telegram_id > 0 AND telegram_id < %s ORDER BY telegram_id",
                (STORAGE_ID_FLOOR,))
    return [int(r[0]) for r in cur.fetchall()]


def set_delivery_counts(cur, notification_id, *, recipients=None, telegram_targets=None, telegram_sent=None):
    sets, params = [], []
    for column, value in (("recipients_count", recipients), ("telegram_targets", telegram_targets),
                          ("telegram_sent", telegram_sent)):
        if value is not None:
            sets.append(f"{column} = %s")
            params.append(int(value))
    if sets:
        cur.execute(f"UPDATE user_notifications SET {', '.join(sets)} WHERE id = %s", params + [notification_id])


def history(cur, limit=50, offset=0):
    cur.execute("""
        SELECT n.id, n.kind, n.body, n.image_key, n.links, n.channels, n.audience, n.recipients_count,
               n.telegram_targets, n.telegram_sent, n.admin_id, n.created_at,
               (SELECT COUNT(*) FROM user_notification_recipients r WHERE r.notification_id = n.id AND r.read_at IS NOT NULL)
        FROM user_notifications n ORDER BY n.id DESC LIMIT %s OFFSET %s
    """, (max(1, min(int(limit or 50), 100)), max(0, int(offset or 0))))
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM user_notifications")
    total = int(cur.fetchone()[0] or 0)
    return [{"id": int(r[0]), "kind": r[1], "text": r[2], "has_image": bool(r[3]), "links": _json_list(r[4]),
             "channels": _json_list(r[5]), "audience": r[6], "recipients": int(r[7] or 0),
             "telegram_targets": int(r[8] or 0), "telegram_sent": int(r[9] or 0), "admin_id": r[10],
             "created_at": _iso(r[11]), "read": int(r[12] or 0)} for r in rows], total


# --------------------------------------------------------------------------
# Contact SYLVEX (users -> admins)
# --------------------------------------------------------------------------

def _thread_where(person, alias=""):
    a = f"{alias}." if alias else ""
    if person.get("account_id"):
        return f"{a}account_id = %s", person["account_id"]
    if person.get("user_key"):
        return f"{a}account_id IS NULL AND {a}user_key = %s", person["user_key"]
    return f"{a}account_id IS NULL AND {a}user_key IS NULL AND {a}visitor_id = %s", person["visitor_id"]


# --------------------------------------------------------------------------
# Sales request (Store -> Contact sales): a short form in steps. Only the
# listed choices are kept; the text an admin reads is built from the fields.
# --------------------------------------------------------------------------

SALES_KINDS = {"organization": "Организация", "private": "Частное лицо"}
SALES_TEAM = ("1–10", "11–50", "51–200", "200+")
SALES_NEEDS = {"images": "Изображения", "video": "Видео", "voice": "Голос и музыка", "text": "Тексты",
               "api": "API и интеграция", "team": "Доступ для команды"}
SALES_BUDGETS = {"lt100": "До $100", "100-500": "$100–500", "500-2000": "$500–2000", "2000+": "Больше $2000",
                 "unknown": "Пока не знает"}


def _short(value, limit):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def clean_sales_request(raw):
    """The sales request as the form sends it -> the fields kept, or an error."""
    if not isinstance(raw, dict):
        raise NotificationError("invalid_sales_request")
    kind = str(raw.get("kind") or "")
    if kind not in SALES_KINDS:
        raise NotificationError("invalid_sales_request")
    organization = kind == "organization"
    company = _short(raw.get("company"), 120) if organization else ""
    if organization and not company:
        raise NotificationError("invalid_sales_request")
    team = str(raw.get("team_size") or "") if organization else ""
    website = _short(raw.get("website"), 200) if organization else ""
    if website and not URL_RE.match(website):
        website = ""
    needs = [need for need in SALES_NEEDS if need in (raw.get("needs") or [])]
    if not needs:
        raise NotificationError("invalid_sales_request")
    budget = str(raw.get("budget") or "")
    name = _short(raw.get("name"), 80)
    email = str(raw.get("email") or "").strip().lower()[:254]
    if not name or not EMAIL_RE.match(email):
        raise NotificationError("invalid_sales_request")
    comment = clean_text(raw.get("comment") or "")[:1500] if str(raw.get("comment") or "").strip() else ""
    return {
        "kind": kind, "company": company, "team_size": team if team in SALES_TEAM else "", "website": website,
        "needs": needs, "budget": budget if budget in SALES_BUDGETS else "", "comment": comment,
        "name": name, "email": email, "phone": _short(raw.get("phone"), 60),
    }


def sales_request_text(details):
    """The request as the message text (previews, Telegram, the thread)."""
    lines = ["Заявка в отдел продаж", "Заявитель: " + SALES_KINDS[details["kind"]]]
    if details["company"]:
        lines.append("Организация: " + details["company"])
    if details["team_size"]:
        lines.append("Команда: " + details["team_size"])
    if details["website"]:
        lines.append("Сайт: " + details["website"])
    lines.append("Интересует: " + ", ".join(SALES_NEEDS[need] for need in details["needs"]))
    if details["budget"]:
        lines.append("Бюджет в месяц: " + SALES_BUDGETS[details["budget"]])
    lines.append("Контакт: " + details["name"] + " · " + details["email"] + (" · " + details["phone"] if details["phone"] else ""))
    if details["comment"]:
        lines += ["", details["comment"]]
    return "\n".join(lines)


def submit_contact(cur, person, *, message, topic="support", email="", surface="", ip_hash=None, sales=None):
    """Stores a user's message; continues their latest unclosed thread. A
    sales request (Store -> Contact sales) comes as its fields instead."""
    details = None
    if sales is not None:
        details = clean_sales_request(sales)
        message, topic, email = sales_request_text(details), "sales", details["email"]
    message = clean_text(message)
    topic = topic if topic in TOPICS else "support"
    surface = surface if surface in ("miniapp", "website", "telegram") else None
    email = str(email or "").strip().lower()[:254]
    if email and not EMAIL_RE.match(email):
        raise NotificationError("invalid_email")
    where, value = _thread_where(person)
    t_where, _ = _thread_where(person, "t")
    cur.execute(f"""
        SELECT COUNT(*) FROM support_messages m JOIN support_threads t ON t.id = m.thread_id
        WHERE {t_where} AND m.direction = 'in' AND m.created_at > NOW() - INTERVAL '10 minutes'
    """, (value,))
    if int(cur.fetchone()[0] or 0) >= CONTACT_PER_10_MIN:
        raise NotificationError("too_many_messages", 429)
    if ip_hash and not person.get("account_id"):
        cur.execute("""
            SELECT COUNT(*) FROM support_messages m JOIN support_threads t ON t.id = m.thread_id
            WHERE t.ip_hash = %s AND m.direction = 'in' AND m.created_at > NOW() - INTERVAL '1 hour'
        """, (ip_hash,))
        if int(cur.fetchone()[0] or 0) >= CONTACT_PER_IP_HOUR:
            raise NotificationError("too_many_messages", 429)
    cur.execute(f"SELECT id FROM support_threads WHERE {where} AND status <> 'closed' ORDER BY id DESC LIMIT 1",
                (value,))
    row = cur.fetchone()
    if row:
        thread_id = int(row[0])
        cur.execute("""
            UPDATE support_threads SET status = 'open', admin_unread = TRUE, topic = %s, surface = COALESCE(%s, surface),
                email = COALESCE(NULLIF(%s, ''), email), updated_at = NOW(), last_message_at = NOW()
            WHERE id = %s
        """, (topic, surface, email, thread_id))
    else:
        cur.execute("""
            INSERT INTO support_threads (account_id, user_key, visitor_id, email, topic, surface, ip_hash)
            VALUES (%s, %s, %s, NULLIF(%s, ''), %s, %s, %s) RETURNING id
        """, (person.get("account_id"), person.get("user_key"), person.get("visitor_id"), email, topic, surface,
              ip_hash))
        thread_id = int(cur.fetchone()[0])
    cur.execute("INSERT INTO support_messages (thread_id, direction, body, details) VALUES (%s, 'in', %s, %s::jsonb) RETURNING id",
                (thread_id, message, json.dumps(details, ensure_ascii=False) if details else None))
    return thread_id, int(cur.fetchone()[0])


def thread_person(cur, thread_id):
    cur.execute("SELECT account_id, user_key, visitor_id FROM support_threads WHERE id = %s", (int(thread_id),))
    row = cur.fetchone()
    if not row:
        raise NotificationError("thread_not_found", 404)
    account_id, user_key, visitor_id = row
    if account_id:
        person = resolve_person(cur, f"a:{account_id}")
        if person:
            return person
    if user_key:
        return {"key": f"t:{user_key}", "account_id": None, "user_key": int(user_key), "visitor_id": None,
                "telegram_chat": real_telegram_id(user_key)}
    return {"key": f"v:{visitor_id}", "account_id": None, "user_key": None, "visitor_id": visitor_id,
            "telegram_chat": None}


def list_threads(cur, *, status="", limit=50, offset=0):
    params, where = [], ""
    if status in ("open", "answered", "closed"):
        where, params = "WHERE t.status = %s", [status]
    cur.execute(f"""
        SELECT t.id, t.account_id, t.user_key, t.visitor_id, t.email, t.topic, t.surface, t.status, t.admin_unread,
               t.created_at, t.last_message_at,
               (SELECT body FROM support_messages m WHERE m.thread_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_body,
               (SELECT direction FROM support_messages m WHERE m.thread_id = t.id ORDER BY m.id DESC LIMIT 1) AS last_dir,
               (SELECT COUNT(*) FROM support_messages m WHERE m.thread_id = t.id) AS messages
        FROM support_threads t {where}
        ORDER BY t.admin_unread DESC, t.last_message_at DESC LIMIT %s OFFSET %s
    """, params + [max(1, min(int(limit or 50), 100)), max(0, int(offset or 0))])
    rows = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) FROM support_threads t {where}", params)
    total = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM support_threads WHERE admin_unread = TRUE")
    unread = int(cur.fetchone()[0] or 0)
    items = [{"id": int(r[0]), "account_id": r[1], "user_key": r[2], "visitor_id": r[3], "email": r[4],
              "topic": r[5], "surface": r[6], "status": r[7], "admin_unread": bool(r[8]),
              "created_at": _iso(r[9]), "last_message_at": _iso(r[10]), "last_message": str(r[11] or "")[:300],
              "last_direction": r[12], "messages": int(r[13] or 0)} for r in rows]
    return items, total, unread


def thread_detail(cur, thread_id, *, image_url=None):
    cur.execute("""
        SELECT id, account_id, user_key, visitor_id, email, topic, surface, status, admin_unread, created_at,
               last_message_at FROM support_threads WHERE id = %s
    """, (int(thread_id),))
    r = cur.fetchone()
    if not r:
        raise NotificationError("thread_not_found", 404)
    thread = {"id": int(r[0]), "account_id": r[1], "user_key": r[2], "visitor_id": r[3], "email": r[4],
              "topic": r[5], "surface": r[6], "status": r[7], "admin_unread": bool(r[8]),
              "created_at": _iso(r[9]), "last_message_at": _iso(r[10])}
    cur.execute("""
        SELECT id, direction, body, image_key, links, admin_id, created_at, details FROM support_messages
        WHERE thread_id = %s ORDER BY id
    """, (int(thread_id),))
    messages = [{"id": int(m[0]), "direction": m[1], "text": m[2],
                 "image_url": image_url(m[3]) if (m[3] and image_url) else None, "links": _json_list(m[4]),
                 "admin_id": m[5], "created_at": _iso(m[6]), "sales": _json_dict(m[7])} for m in cur.fetchall()]
    cur.execute("UPDATE support_threads SET admin_unread = FALSE WHERE id = %s", (int(thread_id),))
    thread["admin_unread"] = False  # opening the thread reads it
    return thread, messages


def record_reply(cur, thread_id, *, text, links, image_key, admin_id, notification_id):
    cur.execute("""
        INSERT INTO support_messages (thread_id, direction, body, image_key, links, admin_id, notification_id)
        VALUES (%s, 'out', %s, %s, %s::jsonb, %s, %s) RETURNING id
    """, (int(thread_id), text, image_key, json.dumps(links), admin_id, notification_id))
    message_id = int(cur.fetchone()[0])
    cur.execute("""
        UPDATE support_threads SET status = 'answered', admin_unread = FALSE, updated_at = NOW(), last_message_at = NOW()
        WHERE id = %s
    """, (int(thread_id),))
    return message_id


def set_thread_status(cur, thread_id, status):
    if status not in ("open", "answered", "closed"):
        raise NotificationError("invalid_status")
    cur.execute("UPDATE support_threads SET status = %s, updated_at = NOW() WHERE id = %s RETURNING id",
                (status, int(thread_id)))
    if not cur.fetchone():
        raise NotificationError("thread_not_found", 404)


def inbox_unread(cur):
    cur.execute("SELECT COUNT(*) FROM support_threads WHERE admin_unread = TRUE")
    return int(cur.fetchone()[0] or 0)


# --------------------------------------------------------------------------
# Audience (admins): registered accounts + visitors, with their sources
# --------------------------------------------------------------------------

def _table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s)", (name,))
    return cur.fetchone()[0] is not None


def audience(cur, *, source="", status="", query="", limit=50, offset=0):
    """Everyone who used the Telegram bot, the Mini App or the website.

    Status: "registered" = has a SYLVEX account (Telegram users get one
    automatically on first contact), "visitor" = seen without an account
    (anonymous website visitors, or Telegram ids with no account).
    Sources per person: telegram (real Telegram id in users), miniapp (opened
    the Mini App: app_presence), website (email / Google / Apple login, or a
    tracked website visit)."""
    has_profiles = _table_exists(cur, "user_profiles")
    has_emails = _table_exists(cur, "account_emails")
    has_oauth = _table_exists(cur, "account_oauth")
    has_presence = _table_exists(cur, "app_presence")
    name_expr = "COALESCE(p.display_name, u.first_name, '')" if has_profiles else "COALESCE(u.first_name, '')"
    profiles_join = "LEFT JOIN user_profiles p ON p.telegram_id = s.active_telegram_id" if has_profiles else ""
    email_join = "LEFT JOIN account_emails e ON e.account_id = s.account_id" if has_emails else ""
    email_expr = "e.email" if has_emails else "NULL::text"
    oauth_expr = "EXISTS (SELECT 1 FROM account_oauth o WHERE o.account_id = s.account_id)" if has_oauth else "FALSE"
    presence_join = "LEFT JOIN app_presence ap ON ap.telegram_id = s.active_telegram_id" if has_presence else ""
    ap_seen = "ap.last_seen" if has_presence else "NULL::timestamp"
    ap_has = "ap.telegram_id IS NOT NULL" if has_presence else "FALSE"
    tg_profiles_join = "LEFT JOIN user_profiles p ON p.telegram_id = u.telegram_id" if has_profiles else ""
    tg_presence_join = "LEFT JOIN app_presence ap ON ap.telegram_id = u.telegram_id" if has_presence else ""
    sql = f"""
        WITH people AS (
            SELECT 'a:' || s.account_id AS pkey, s.account_id AS account_id, s.active_telegram_id AS user_key,
                   NULL::text AS visitor_id, {name_expr} AS pname, COALESCE(u.username, '') AS username,
                   {email_expr} AS email,
                   (s.active_telegram_id < {int(STORAGE_ID_FLOOR)} AND u.telegram_id IS NOT NULL) AS src_telegram,
                   ({ap_has}) AS src_miniapp,
                   ({email_expr} IS NOT NULL OR {oauth_expr} OR sv.account_id IS NOT NULL) AS src_website,
                   TRUE AS registered,
                   GREATEST({ap_seen}, sv.last_seen) AS last_seen, s.created_at AS since
            FROM sylvex_accounts s
            LEFT JOIN users u ON u.telegram_id = s.active_telegram_id
            {profiles_join} {email_join} {presence_join}
            LEFT JOIN (SELECT account_id, MAX(last_seen) AS last_seen FROM site_visitors
                       WHERE account_id IS NOT NULL GROUP BY account_id) sv ON sv.account_id = s.account_id
            WHERE s.active_telegram_id IS NOT NULL
            UNION ALL
            SELECT 't:' || u.telegram_id, NULL::bigint, u.telegram_id, NULL::text,
                   {name_expr}, COALESCE(u.username, ''), NULL::text,
                   TRUE, ({ap_has}), FALSE, FALSE, {ap_seen}, NULL::timestamp
            FROM users u {tg_profiles_join} {tg_presence_join}
            WHERE u.telegram_id > 0 AND u.telegram_id < {int(STORAGE_ID_FLOOR)}
              AND NOT EXISTS (SELECT 1 FROM sylvex_accounts s2 WHERE s2.active_telegram_id = u.telegram_id)
            UNION ALL
            SELECT 'v:' || v.visitor_id, NULL::bigint, NULL::bigint, v.visitor_id, '', '', NULL::text,
                   FALSE, FALSE, TRUE, FALSE, v.last_seen, v.first_seen
            FROM site_visitors v WHERE v.account_id IS NULL
        )
        SELECT pkey, account_id, user_key, visitor_id, pname, username, email, src_telegram, src_miniapp,
               src_website, registered, last_seen, since
        FROM people WHERE {{where}}
    """
    conditions, params = ["TRUE"], []
    if source == "telegram":
        conditions.append("src_telegram")
    elif source == "miniapp":
        conditions.append("src_miniapp")
    elif source == "website":
        conditions.append("src_website")
    if status == "registered":
        conditions.append("registered")
    elif status == "visitor":
        conditions.append("NOT registered")
    q = str(query or "").strip().lstrip("@")[:100]
    if q:
        like = f"%{q.lower()}%"
        conditions.append("(LOWER(COALESCE(pname, '')) LIKE %s OR LOWER(COALESCE(username, '')) LIKE %s "
                          "OR LOWER(COALESCE(email, '')) LIKE %s OR pkey LIKE %s OR CAST(account_id AS TEXT) = %s "
                          "OR CAST(user_key AS TEXT) = %s)")
        params += [like, like, like, f"%{q}%", q, q]
    where = " AND ".join(conditions)
    cur.execute(sql.replace("{where}", where) + " ORDER BY last_seen DESC NULLS LAST, since DESC NULLS LAST LIMIT %s OFFSET %s",
                params + [max(1, min(int(limit or 50), 200)), max(0, int(offset or 0))])
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM (" + sql.replace("{where}", where) + ") c", params)
    total = int(cur.fetchone()[0] or 0)
    items = []
    for (pkey, account_id, user_key, visitor_id, name, username, email, src_tg, src_mini, src_web, registered,
         last_seen, since) in rows:
        status_label = "registered" if registered else "visitor"
        sources = [s for s, on in (("telegram", src_tg), ("miniapp", src_mini), ("website", src_web)) if on]
        if not sources:
            sources = ["telegram"] if real_telegram_id(user_key) else ["website"]
        items.append({"key": pkey, "sylvex_user_id": str(account_id) if account_id else None,
                      "telegram_id": real_telegram_id(user_key), "visitor_id": visitor_id,
                      "name": name or "", "username": username or "", "email": email,
                      "sources": sources, "status": status_label, "last_seen": _iso(last_seen),
                      "since": _iso(since)})
    return items, total
