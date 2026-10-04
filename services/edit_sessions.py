"""Private Edit canvases. Each read and write is scoped to the verified owner."""
import json
import math
import re

from services.media_access import sign_media_url


def validate_session(session_id, state):
    if not re.fullmatch(r"edit-[A-Za-z0-9_-]{1,100}", session_id):
        raise ValueError("invalid_edit_session")
    if not isinstance(state, dict) or state.get("sessionId") != session_id:
        raise ValueError("invalid_edit_state")
    try:
        encoded = json.dumps(state, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("invalid_edit_state")
    if len(encoded.encode()) > 4 * 1024 * 1024:
        raise ValueError("edit_session_too_large")
    nodes = state.get("chain")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 500:
        raise ValueError("invalid_edit_chain")
    seen = set()
    for node in nodes:
        if not isinstance(node, dict) or not re.fullmatch(r"edit-node-\d+", str(node.get("id", ""))):
            raise ValueError("invalid_edit_node")
        if node["id"] in seen or (node.get("parentId") and node["parentId"] not in seen):
            raise ValueError("invalid_edit_connection")
        seen.add(node["id"])
        if node.get("status") not in {"ready", "pending", "failed"}:
            raise ValueError("invalid_edit_status")
        for key in ("x", "y", "slotWidth", "slotHeight"):
            value = node.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e9:
                raise ValueError("invalid_edit_geometry")
        if min(node["slotWidth"], node["slotHeight"]) <= 0:
            raise ValueError("invalid_edit_geometry")
    if state.get("activeNodeId") not in seen:
        raise ValueError("invalid_edit_active_node")
    def check(value, field=""):
        if isinstance(value, dict):
            for key, child in value.items():
                check(child, key)
        elif isinstance(value, list):
            for child in value:
                check(child, field)
        elif field in {"url", "preview", "sourceUrl", "sourcePreview", "resultUrl", "beforeUrl"}:
            if not isinstance(value, str) or (value and not value.startswith(("https://", "http://", "/"))) or value.startswith("//"):
                raise ValueError("invalid_edit_image_url")
    check(state)
    return encoded


def refresh_media(value, field=""):
    if isinstance(value, dict):
        return {key: refresh_media(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [refresh_media(child, field) for child in value]
    if isinstance(value, str) and field in {"url", "preview", "sourceUrl", "sourcePreview", "resultUrl", "beforeUrl"}:
        return sign_media_url(value)
    return value


def save(connect, owner, session_id, state):
    encoded = validate_session(session_id, state)
    title = str(state.get("sourceName") or "Рабочая область Edit")[:160]
    preview = next((node.get("url", "") for node in reversed(state["chain"]) if node.get("status") == "ready"), "")
    count = sum(node.get("status") == "ready" and bool(node.get("parentId")) for node in state["chain"])
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO prostudio_edit_sessions (telegram_id, id, title, preview_url, result_count, state_json)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (telegram_id, id) DO UPDATE SET title=EXCLUDED.title,
                preview_url=EXCLUDED.preview_url, result_count=EXCLUDED.result_count,
                state_json=EXCLUDED.state_json, updated_at=NOW()""", (owner, session_id, title, preview, count, encoded))


def list_sessions(connect, owner, offset=0):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, title, preview_url, result_count, updated_at FROM prostudio_edit_sessions
                WHERE telegram_id=%s ORDER BY updated_at DESC, id LIMIT 50 OFFSET %s""", (owner, max(0, offset)))
            return [{"id": row[0], "title": row[1], "preview_url": sign_media_url(row[2]), "count": row[3], "updatedAt": row[4].isoformat()} for row in cur.fetchall()]


def get(connect, owner, session_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state_json FROM prostudio_edit_sessions WHERE telegram_id=%s AND id=%s", (owner, session_id))
            row = cur.fetchone()
    if not row:
        return None
    state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return refresh_media(state)
