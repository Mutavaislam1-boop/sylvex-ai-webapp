"""Private Edit canvases. Each read and write is scoped to the verified owner."""
import json
import math
import re
from urllib.parse import quote

from services.media_access import media_key, sign_media_url
from services.edit_sketch import validate_sketch


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
    sketch = state.get('sketch')
    if sketch is not None:
        validate_sketch(sketch)
    if not isinstance(nodes, list) or len(nodes) > 500 or (not nodes and sketch is None):
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
    if (nodes and state.get("activeNodeId") not in seen) or (not nodes and state.get("activeNodeId")):
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


def canonicalize_media(value, field=""):
    """Persist stable object paths instead of repeating expiring signatures."""
    if isinstance(value, dict):
        return {key: canonicalize_media(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [canonicalize_media(child, field) for child in value]
    if isinstance(value, str) and field in {"url", "preview", "sourceUrl", "sourcePreview", "resultUrl", "beforeUrl"}:
        key = media_key(value)
        if key:
            return "/api/public/storage/" + quote(key, safe="/")
    return value


def save(connect, owner, session_id, state):
    stable_state = canonicalize_media(state)
    encoded = validate_session(session_id, stable_state)
    title = str(stable_state.get("historyTitle") or stable_state.get("sourceName") or ("Sketch drawing" if stable_state.get('sketch') else "Edit workspace"))[:160]
    preview = next((node.get("url", "") for node in reversed(stable_state["chain"]) if node.get("status") == "ready"), "")
    count = sum(node.get("status") == "ready" and bool(node.get("parentId")) for node in stable_state["chain"])
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
            cur.execute("""SELECT id, title, preview_url, result_count, updated_at,
                       state_json @> '{"pinned": true}'::jsonb AS pinned
                FROM prostudio_edit_sessions WHERE telegram_id=%s
                ORDER BY pinned DESC, updated_at DESC, id LIMIT 50 OFFSET %s""", (owner, max(0, offset)))
            return [{"id": row[0], "title": row[1], "preview_url": sign_media_url(row[2]), "count": row[3],
                     "updatedAt": row[4].isoformat(), "pinned": bool(row[5])} for row in cur.fetchall()]


def get(connect, owner, session_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state_json FROM prostudio_edit_sessions WHERE telegram_id=%s AND id=%s", (owner, session_id))
            row = cur.fetchone()
    if not row:
        return None
    state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return refresh_media(state)


def delete(connect, owner, session_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prostudio_edit_sessions WHERE telegram_id=%s AND id=%s", (owner, session_id))
            return cur.rowcount > 0
