"""Usage analytics for the Admin Console: which sections, tools, styles,
templates, references and models people use, per platform.

Events come from js/analytics.js (Mini Apps and website) and carry only
what counting needs: the event, a section, an item id and its kind, a model
id, how long a section stayed open, the platform and a random visitor id.
No prompts, files, names or other personal content are accepted - every
field is reduced to a short id. Generations and results are counted from
the generation jobs, not from client events.
"""
from __future__ import annotations

import re

EVENTS = ("section_open", "section_leave", "model_select", "tool_open", "item_select", "download")
SURFACES = ("website", "browser_miniapp", "telegram_miniapp")
KINDS = ("tool", "style", "template", "reference", "effect", "object", "photo", "video")
MAX_EVENTS = 30
MAX_DURATION_MS = 6 * 3600 * 1000
_ID = re.compile(r"[^a-z0-9_.:-]")
_VISITOR = re.compile(r"^[a-z0-9]{6,40}$")


def _id(value, limit=64):
    return _ID.sub("_", str(value or "").lower())[:limit].strip("_")


def clean_batch(body):
    """(visitor, surface, [events]) from a client batch; junk is dropped."""
    body = body if isinstance(body, dict) else {}
    visitor = str(body.get("visitor") or "").lower()
    visitor = visitor if _VISITOR.match(visitor) else ""
    surface = body.get("surface") if body.get("surface") in SURFACES else ""
    events = []
    for raw in (body.get("events") if isinstance(body.get("events"), list) else [])[:MAX_EVENTS]:
        if not isinstance(raw, dict) or raw.get("event") not in EVENTS:
            continue
        kind = _id(raw.get("kind"), 20)
        try:
            duration = int(raw.get("duration_ms") or 0)
        except (TypeError, ValueError):
            duration = 0
        events.append({
            "event": raw["event"], "section": _id(raw.get("section"), 40), "item": _id(raw.get("item")),
            "kind": kind if kind in KINDS else "", "model": _id(raw.get("model")),
            "duration_ms": max(0, min(duration, MAX_DURATION_MS)) if raw["event"] == "section_leave" else 0,
        })
    return visitor, surface, events


def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMP NOT NULL DEFAULT NOW(),
            surface TEXT NOT NULL DEFAULT '',
            visitor TEXT NOT NULL DEFAULT '',
            event TEXT NOT NULL,
            section TEXT NOT NULL DEFAULT '',
            item TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_at ON analytics_events (at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_event_at ON analytics_events (event, at)")


def record(cursor, visitor, surface, events):
    for e in events:
        cursor.execute("""
            INSERT INTO analytics_events (surface, visitor, event, section, item, kind, model, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (surface, visitor, e["event"], e["section"], e["item"], e["kind"], e["model"], e["duration_ms"]))
