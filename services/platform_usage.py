"""Which SYLVEX surfaces each person uses: the website, the Browser Mini App,
the Telegram Mini App and the Telegram bot.

SecurityMiddleware reports the surface of every authenticated request
(`surface_of`); the app records it here at most once per person, surface
and few minutes. The bot is not a web surface: a real Telegram id in
`users` means the person talks to the bot. Mass announcements choose their
audience by these surfaces; analytics splits by them.

Every function takes an open cursor; the caller commits.
"""
from __future__ import annotations

from urllib.parse import urlsplit

SURFACES = ("website", "browser_miniapp", "telegram_miniapp", "bot")
WEB_SURFACES = SURFACES[:3]


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_surface_usage (
            user_key BIGINT NOT NULL,
            surface TEXT NOT NULL,
            first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
            hits INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_key, surface)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_surface_usage_surface ON user_surface_usage(surface, last_seen DESC)")


def surface_of(auth_kind, origin, referer, website_origins):
    """The surface an authenticated request came from. Telegram initData is
    the Telegram Mini App; a web session is the website when it comes from a
    website page (or the Pro Studio embedded in it), else the Browser Mini
    App (the Mini App opened directly in a browser)."""
    if auth_kind == "telegram":
        return "telegram_miniapp"
    if auth_kind != "web":
        return None
    origin = (origin or "").rstrip("/")
    if origin and origin in website_origins:
        return "website"
    if "embed=web" in (referer or ""):
        return "website"
    try:
        ref = urlsplit(referer or "")
        if ref.scheme and f"{ref.scheme}://{ref.netloc}" in website_origins:
            return "website"
    except ValueError:
        pass
    return "browser_miniapp"


def record(cur, user_key, surface):
    if surface not in WEB_SURFACES or not user_key:
        return
    cur.execute("""
        INSERT INTO user_surface_usage (user_key, surface) VALUES (%s, %s)
        ON CONFLICT (user_key, surface) DO UPDATE SET last_seen = NOW(), hits = user_surface_usage.hits + 1
    """, (int(user_key), surface))


def surfaces_for(cur, user_keys):
    """{user_key: [surfaces]} including 'bot' for real Telegram ids."""
    from services.account_identity import real_telegram_id
    keys = [int(k) for k in user_keys if k]
    out = {k: [] for k in keys}
    if not keys:
        return out
    cur.execute("SELECT to_regclass('user_surface_usage')")
    if cur.fetchone()[0] is not None:
        cur.execute("SELECT user_key, surface FROM user_surface_usage WHERE user_key = ANY(%s::bigint[])", (keys,))
        for key, surface in cur.fetchall():
            out.setdefault(int(key), []).append(surface)
    for k in keys:
        if real_telegram_id(k):
            out[k].append("bot")
    return {k: [s for s in SURFACES if s in v] for k, v in out.items()}
