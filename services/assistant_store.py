"""SYLVEX Assistant conversation/message persistence.

Guest (unauthenticated) conversations are never persisted here at all - see
the telegram_id-falsy short-circuit in main.py's assistant endpoints, which
keep guest chat state entirely client-side per the product spec. Every
function below takes `connect` (a zero-arg callable returning a context-
managed DB connection, e.g. `lambda: db_connect(DATABASE_URL)`) as its
first argument, matching services/billing_safety.py's convention, so tests
can inject the same pglite-backed connection the rest of the suite already
uses.

Ownership is enforced here, not just in main.py: every read/update/delete
takes the caller's telegram_id and filters by it in SQL, so a conversation
id alone is never sufficient to reach another account's data even if a
caller forgets the check upstream.
"""
import json
from uuid import uuid4


def ensure_assistant_tables(connect):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assistant_conversations (
                    id TEXT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    title TEXT DEFAULT '',
                    pinned BOOLEAN DEFAULT FALSE,
                    last_mode TEXT DEFAULT 'guide',
                    preview TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_assistant_conversations_owner
                ON assistant_conversations (telegram_id, pinned DESC, updated_at DESC)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    telegram_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    attachments_json JSONB DEFAULT '[]'::jsonb,
                    actions_json JSONB DEFAULT '[]'::jsonb,
                    mode TEXT DEFAULT 'guide',
                    intent TEXT DEFAULT '',
                    status TEXT DEFAULT 'completed',
                    error TEXT DEFAULT '',
                    client_request_id TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_assistant_messages_conversation
                ON assistant_messages (conversation_id, created_at ASC, id ASC)
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_messages_client_request
                ON assistant_messages (conversation_id, client_request_id)
                WHERE client_request_id <> ''
            """)
        conn.commit()


def _isoformat(value):
    # psycopg2 against real Postgres returns a datetime object here; the
    # pglite test adapter returns a plain string - accept either.
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _row_to_conversation(row):
    return {
        "id": row[0], "telegram_id": row[1], "title": row[2], "pinned": bool(row[3]),
        "last_mode": row[4], "preview": row[5],
        "created_at": _isoformat(row[6]),
        "updated_at": _isoformat(row[7]),
    }


def _row_to_message(row):
    return {
        "id": row[0], "conversation_id": row[1], "role": row[2], "content": row[3],
        "attachments": row[4] or [], "actions": row[5] or [], "mode": row[6], "intent": row[7],
        "status": row[8], "error": row[9],
        "created_at": _isoformat(row[10]),
    }


def derive_title(text):
    text = (text or "").strip().replace("\n", " ")
    if not text:
        return "New conversation"
    return text[:57] + "..." if len(text) > 60 else text


def create_conversation(connect, telegram_id, title=""):
    conversation_id = uuid4().hex
    title = title or "New conversation"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO assistant_conversations (id, telegram_id, title) VALUES (%s, %s, %s) "
                "RETURNING id, telegram_id, title, pinned, last_mode, preview, created_at, updated_at",
                (conversation_id, telegram_id, title),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_conversation(row)


def list_conversations(connect, telegram_id, search="", limit=100):
    search = (search or "").strip()
    with connect() as conn:
        with conn.cursor() as cur:
            if search:
                cur.execute(
                    "SELECT id, telegram_id, title, pinned, last_mode, preview, created_at, updated_at "
                    "FROM assistant_conversations WHERE telegram_id = %s AND title ILIKE %s "
                    "ORDER BY pinned DESC, updated_at DESC LIMIT %s",
                    (telegram_id, "%" + search + "%", limit),
                )
            else:
                cur.execute(
                    "SELECT id, telegram_id, title, pinned, last_mode, preview, created_at, updated_at "
                    "FROM assistant_conversations WHERE telegram_id = %s "
                    "ORDER BY pinned DESC, updated_at DESC LIMIT %s",
                    (telegram_id, limit),
                )
            rows = cur.fetchall()
    return [_row_to_conversation(row) for row in rows]


def has_any_conversation(connect, telegram_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM assistant_conversations WHERE telegram_id = %s LIMIT 1", (telegram_id,))
            return cur.fetchone() is not None


def get_conversation_owner(connect, conversation_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM assistant_conversations WHERE id = %s", (conversation_id,))
            row = cur.fetchone()
    return int(row[0]) if row else None


def get_conversation(connect, conversation_id, telegram_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, telegram_id, title, pinned, last_mode, preview, created_at, updated_at "
                "FROM assistant_conversations WHERE id = %s AND telegram_id = %s",
                (conversation_id, telegram_id),
            )
            conv_row = cur.fetchone()
            if not conv_row:
                return None
            cur.execute(
                "SELECT id, conversation_id, role, content, attachments_json, actions_json, mode, intent, "
                "status, error, created_at FROM assistant_messages "
                "WHERE conversation_id = %s ORDER BY created_at ASC, id ASC",
                (conversation_id,),
            )
            message_rows = cur.fetchall()
    conversation = _row_to_conversation(conv_row)
    conversation["messages"] = [_row_to_message(row) for row in message_rows]
    return conversation


def update_conversation(connect, conversation_id, telegram_id, title=None, pinned=None):
    sets, params = [], []
    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if pinned is not None:
        sets.append("pinned = %s")
        params.append(bool(pinned))
    if not sets:
        return get_conversation_owner(connect, conversation_id) == telegram_id
    sets.append("updated_at = NOW()")
    params.extend([conversation_id, telegram_id])
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE assistant_conversations SET {', '.join(sets)} WHERE id = %s AND telegram_id = %s RETURNING id",
                params,
            )
            updated = cur.fetchone() is not None
        conn.commit()
    return updated


def delete_conversation(connect, conversation_id, telegram_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM assistant_conversations WHERE id = %s AND telegram_id = %s RETURNING id",
                (conversation_id, telegram_id),
            )
            deleted = cur.fetchone() is not None
            if deleted:
                cur.execute("DELETE FROM assistant_messages WHERE conversation_id = %s", (conversation_id,))
        conn.commit()
    return deleted


def touch_conversation(connect, conversation_id, preview="", last_mode=None):
    sets = ["updated_at = NOW()"]
    params = []
    if preview:
        sets.append("preview = %s")
        params.append(preview[:160])
    if last_mode:
        sets.append("last_mode = %s")
        params.append(last_mode)
    params.append(conversation_id)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE assistant_conversations SET {', '.join(sets)} WHERE id = %s", params)
        conn.commit()


def find_reply_for_client_request_id(connect, conversation_id, client_request_id):
    """Idempotent-retry lookup: if `client_request_id` was already processed
    for this conversation, return the assistant reply that followed it
    instead of letting the caller regenerate (and, for AI mode, re-bill)
    it. Returns None if this is a genuinely new request."""
    if not client_request_id:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at FROM assistant_messages "
                "WHERE conversation_id = %s AND client_request_id = %s AND role = 'user'",
                (conversation_id, client_request_id),
            )
            user_row = cur.fetchone()
            if not user_row:
                return None
            cur.execute(
                "SELECT id, conversation_id, role, content, attachments_json, actions_json, mode, intent, "
                "status, error, created_at FROM assistant_messages "
                "WHERE conversation_id = %s AND role = 'assistant' AND created_at >= %s "
                "ORDER BY created_at ASC, id ASC LIMIT 1",
                (conversation_id, user_row[1]),
            )
            reply_row = cur.fetchone()
    return _row_to_message(reply_row) if reply_row else None


def add_message(connect, conversation_id, telegram_id, role, content, attachments=None,
                 actions=None, mode="guide", intent="", status="completed", error="",
                 client_request_id=""):
    message_id = uuid4().hex
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO assistant_messages (id, conversation_id, telegram_id, role, content, "
                "attachments_json, actions_json, mode, intent, status, error, client_request_id) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s) "
                "RETURNING id, conversation_id, role, content, attachments_json, actions_json, mode, "
                "intent, status, error, created_at",
                (
                    message_id, conversation_id, telegram_id, role, content,
                    json.dumps(attachments or []), json.dumps(actions or []),
                    mode, intent, status, error, client_request_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_message(row)
