"""Private, server-confirmed persistence for Pro Studio Grid projects."""
from __future__ import annotations

import json
import math
import re
from urllib.parse import quote

from services.media_access import media_key, sign_media_url


PROJECT_ID_RE = re.compile(r"grid_project_[A-Za-z0-9_-]{1,120}")
NODE_ID_RE = re.compile(r"grid_[A-Za-z0-9_-]{1,160}")
ALLOWED_TYPES = {"task", "text", "image", "video", "music", "voice", "montage"}
ALLOWED_STATUSES = {"IDLE", "READY", "WAITING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
MEDIA_FIELDS = {
    "url", "preview", "preview_url", "image_url", "video_url", "audio_url",
    "source_url", "thumbnail_url", "thumb_url", "media_url", "result_url",
    "reference_url", "referenceImageUrls", "reference_image_urls",
    "referenceImages", "reference_images", "images", "videos", "files",
}


def _safe_url(value: str) -> bool:
    return not value or (
        isinstance(value, str)
        and value.startswith(("https://", "http://", "/"))
        and not value.startswith("//")
    )


def _walk(value, field=""):
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, key)
    elif isinstance(value, list):
        for child in value:
            _walk(child, field)
    elif field in MEDIA_FIELDS and not _safe_url(value):
        raise ValueError("invalid_grid_media_url")


def validate_project(project_id, state):
    if not PROJECT_ID_RE.fullmatch(str(project_id or "")):
        raise ValueError("invalid_grid_project")
    if not isinstance(state, dict) or state.get("projectId") != project_id:
        raise ValueError("invalid_grid_state")
    try:
        encoded = json.dumps(state, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("invalid_grid_state")
    if len(encoded.encode()) > 8 * 1024 * 1024:
        raise ValueError("grid_project_too_large")
    nodes, edges = state.get("nodes"), state.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not nodes or len(nodes) > 200 or len(edges) > 800:
        raise ValueError("invalid_grid_graph")
    ids = set()
    for node in nodes:
        node_id = str(node.get("id") or "") if isinstance(node, dict) else ""
        if not NODE_ID_RE.fullmatch(node_id) or node_id in ids:
            raise ValueError("invalid_grid_node")
        if node.get("type") not in ALLOWED_TYPES or str(node.get("status") or "IDLE").upper() not in ALLOWED_STATUSES:
            raise ValueError("invalid_grid_node")
        for key in ("x", "y"):
            value = node.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e7:
                raise ValueError("invalid_grid_geometry")
        ids.add(node_id)
    edge_ids = set()
    adjacency = {node_id: [] for node_id in ids}
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("invalid_grid_edge")
        edge_id = str(edge.get("id") or "")
        source = str(edge.get("from") or edge.get("source_node_id") or "")
        target = str(edge.get("to") or edge.get("target_node_id") or "")
        if not edge_id or edge_id in edge_ids or source not in ids or target not in ids or source == target:
            raise ValueError("invalid_grid_edge")
        edge_ids.add(edge_id)
        adjacency[source].append(target)
    # Stored projects must remain DAGs. This also prevents an invalid cloud
    # snapshot from making the client workflow scheduler wait forever.
    visiting, visited = set(), set()

    def visit(node_id):
        if node_id in visiting:
            raise ValueError("invalid_grid_cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in adjacency[node_id]:
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in ids:
        visit(node_id)
    _walk(state)
    return encoded


def _refresh_media(value, field=""):
    if isinstance(value, dict):
        return {key: _refresh_media(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [_refresh_media(child, field) for child in value]
    if isinstance(value, str) and field in MEDIA_FIELDS:
        return sign_media_url(value)
    return value


def _canonicalize_media(value, field=""):
    """Remove expiring capabilities before a Grid project is persisted.

    The private project row is the authorization boundary. It should retain
    stable object paths, while every authenticated read receives newly signed
    browser/provider URLs from ``_refresh_media``.
    """
    if isinstance(value, dict):
        return {key: _canonicalize_media(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [_canonicalize_media(child, field) for child in value]
    if isinstance(value, str) and field in MEDIA_FIELDS:
        key = media_key(value)
        if key:
            return "/api/public/storage/" + quote(key, safe="/")
    return value


def _preview(state):
    for node in reversed(state.get("nodes") or []):
        output = node.get("output") or {}
        if output.get("preview_url") or output.get("url"):
            return output.get("preview_url") or output.get("url")
        items = output.get("items") or []
        if items:
            item = items[int(output.get("selected_index") or 0)] if len(items) > int(output.get("selected_index") or 0) else items[0]
            return item.get("preview_url") or item.get("url") or ""
    return ""


def save(connect, owner, project_id, state):
    validate_project(project_id, state)
    stable_state = _canonicalize_media(state)
    encoded = validate_project(project_id, stable_state)
    title = str(stable_state.get("title") or "Grid project")[:160]
    preview = _preview(stable_state)
    node_count = len(stable_state.get("nodes") or [])
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO prostudio_grid_projects
                (telegram_id, id, title, preview_url, node_count, state_json)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (telegram_id, id) DO UPDATE SET
                  title=EXCLUDED.title, preview_url=EXCLUDED.preview_url,
                  node_count=EXCLUDED.node_count, state_json=EXCLUDED.state_json,
                  updated_at=NOW()""", (owner, project_id, title, preview, node_count, encoded))


def list_projects(connect, owner, offset=0):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,title,preview_url,node_count,updated_at,
                       state_json @> '{"pinned": true}'::jsonb AS pinned
                FROM prostudio_grid_projects WHERE telegram_id=%s
                ORDER BY pinned DESC,updated_at DESC,id LIMIT 50 OFFSET %s""", (owner, max(0, int(offset or 0))))
            return [{"id": row[0], "title": row[1], "preview_url": sign_media_url(row[2]),
                     "node_count": row[3], "updated_at": row[4].isoformat(), "pinned": bool(row[5])} for row in cur.fetchall()]


def get(connect, owner, project_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state_json FROM prostudio_grid_projects WHERE telegram_id=%s AND id=%s", (owner, project_id))
            row = cur.fetchone()
    if not row:
        return None
    state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return _refresh_media(state)


def delete(connect, owner, project_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prostudio_grid_projects WHERE telegram_id=%s AND id=%s", (owner, project_id))
            return cur.rowcount > 0
