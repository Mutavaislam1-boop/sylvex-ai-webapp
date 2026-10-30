"""Project reviews: the "How do you like SYLVEX?" prompt and its answers.

When the prompt shows is counted in successful generations, never in time:
first after FIRST_AT of them (or after a purchase or subscription, once there
are AFTER_PURCHASE of them); closed with × it comes back AFTER_CLOSE
generations later, "Remind me later" AFTER_LATER later; "Don't show again"
or a sent review ends it. The state belongs to the SYLVEX account, so the
answer holds in the Mini App and on the website alike.
"""
import re

FIRST_AT = 5
AFTER_PURCHASE = 2
AFTER_CLOSE = 10
AFTER_LATER = 25
MAX_TEXT = 1500
SURFACES = ("miniapp", "website")
ACTIONS = ("shown", "close", "later", "never", "send")
FINAL = ("answered", "never")


class ReviewError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS review_prompts (
            person_key TEXT PRIMARY KEY,
            account_id BIGINT,
            user_key BIGINT,
            status TEXT NOT NULL DEFAULT 'waiting',
            next_at INTEGER,
            shows INTEGER NOT NULL DEFAULT 0,
            closes INTEGER NOT NULL DEFAULT 0,
            laters INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_reviews (
            id BIGSERIAL PRIMARY KEY,
            person_key TEXT NOT NULL,
            account_id BIGINT,
            user_key BIGINT,
            rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            body TEXT NOT NULL DEFAULT '',
            surface TEXT,
            generations INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_project_reviews_created ON project_reviews(created_at DESC)")
    # An admin's answer to a review (it reaches the person like any message).
    cur.execute("ALTER TABLE project_reviews ADD COLUMN IF NOT EXISTS reply_body TEXT")
    cur.execute("ALTER TABLE project_reviews ADD COLUMN IF NOT EXISTS replied_at TIMESTAMP")
    cur.execute("ALTER TABLE project_reviews ADD COLUMN IF NOT EXISTS replied_by BIGINT")


def successful_generations(cur, user_key):
    cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE telegram_id = %s AND status = 'completed'",
                (int(user_key),))
    return int(cur.fetchone()[0] or 0)


def has_paid(cur, user_key):
    cur.execute("SELECT 1 FROM purchases WHERE telegram_id = %s AND status = 'completed' LIMIT 1", (int(user_key),))
    if cur.fetchone():
        return True
    cur.execute("SELECT 1 FROM subscriptions WHERE telegram_id = %s LIMIT 1", (int(user_key),))
    return bool(cur.fetchone())


def _row(cur, person_key):
    cur.execute("SELECT status, next_at, shows, closes, laters FROM review_prompts WHERE person_key = %s",
                (person_key,))
    return cur.fetchone()


def is_due(cur, person, user_key):
    """Whether the prompt should show now."""
    row = _row(cur, person["key"])
    if row and row[0] in FINAL:
        return False
    generations = successful_generations(cur, user_key)
    if row and row[1] is not None:
        return generations >= int(row[1])
    threshold = AFTER_PURCHASE if generations >= AFTER_PURCHASE and has_paid(cur, user_key) else FIRST_AT
    return generations >= threshold


def _upsert(cur, person, user_key, **changes):
    cur.execute("""
        INSERT INTO review_prompts (person_key, account_id, user_key) VALUES (%s, %s, %s)
        ON CONFLICT (person_key) DO NOTHING
    """, (person["key"], person.get("account_id"), int(user_key)))
    sets = ", ".join(f"{column} = {expression}" for column, expression in changes.items())
    cur.execute(f"UPDATE review_prompts SET {sets}, updated_at = NOW() WHERE person_key = %s", (person["key"],))


def record(cur, person, user_key, action, *, rating=None, text="", surface=""):
    """One answer to the prompt. Returns the review id for a sent review."""
    if action not in ACTIONS:
        raise ReviewError("invalid_action")
    row = _row(cur, person["key"])
    if row and row[0] in FINAL and action != "shown":
        raise ReviewError("already_answered", 409)
    generations = successful_generations(cur, user_key)
    if action == "shown":
        _upsert(cur, person, user_key, shows="shows + 1")
        return None
    if action == "close":
        _upsert(cur, person, user_key, closes="closes + 1", next_at=str(generations + AFTER_CLOSE))
        return None
    if action == "later":
        _upsert(cur, person, user_key, laters="laters + 1", status="'later'", next_at=str(generations + AFTER_LATER))
        return None
    if action == "never":
        _upsert(cur, person, user_key, status="'never'")
        return None
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ReviewError("invalid_rating")
    if not 1 <= rating <= 5:
        raise ReviewError("invalid_rating")
    body = re.sub(r"[ \t]+", " ", str(text or "")).strip()
    if len(body) > MAX_TEXT:
        raise ReviewError("review_too_long")
    surface = surface if surface in SURFACES else None
    cur.execute("""
        INSERT INTO project_reviews (person_key, account_id, user_key, rating, body, surface, generations)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (person["key"], person.get("account_id"), int(user_key), rating, body, surface, generations))
    review_id = int(cur.fetchone()[0])
    _upsert(cur, person, user_key, status="'answered'")
    return review_id


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)


def admin_list(cur, *, rating=0, surface="", with_text=None, replied=None, days=0, limit=50, offset=0):
    """Reviews for the Admin Console, newest first, with filters (stars,
    where it was left, with/without a comment, answered or not, last N days)
    and the summary: stars, average overall / per surface / last 30 days,
    answered, and how the prompt itself was met."""
    conditions, params = [], []
    if int(rating or 0) in (1, 2, 3, 4, 5):
        conditions.append("rating = %s")
        params.append(int(rating))
    if surface in SURFACES:
        conditions.append("surface = %s")
        params.append(surface)
    if with_text is True:
        conditions.append("body <> ''")
    elif with_text is False:
        conditions.append("body = ''")
    if replied is True:
        conditions.append("replied_at IS NOT NULL")
    elif replied is False:
        conditions.append("replied_at IS NULL")
    if int(days or 0) > 0:
        conditions.append("created_at >= NOW() - (%s * INTERVAL '1 day')")
        params.append(min(int(days), 3650))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cur.execute(f"""
        SELECT id, account_id, user_key, rating, body, surface, generations, created_at, reply_body, replied_at, replied_by
        FROM project_reviews {where} ORDER BY id DESC LIMIT %s OFFSET %s
    """, params + [max(1, min(int(limit or 50), 100)), max(0, int(offset or 0))])
    items = [{"id": int(r[0]), "account_id": r[1], "user_key": r[2], "rating": int(r[3]), "text": r[4] or "",
              "surface": r[5], "generations": int(r[6] or 0), "created_at": _iso(r[7]), "reply": r[8] or "",
              "replied_at": _iso(r[9]), "replied_by": r[10]} for r in cur.fetchall()]
    cur.execute(f"SELECT COUNT(*) FROM project_reviews {where}", params)
    total = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT rating, COUNT(*) FROM project_reviews GROUP BY rating")
    by_rating = {str(star): 0 for star in range(1, 6)}
    for star, count in cur.fetchall():
        by_rating[str(int(star))] = int(count)
    count = sum(by_rating.values())
    average = round(sum(int(star) * n for star, n in by_rating.items()) / count, 2) if count else 0
    cur.execute("SELECT COALESCE(surface, 'unknown') AS surface, COUNT(*) AS n, AVG(rating) AS avg_rating "
                "FROM project_reviews GROUP BY 1")
    by_surface = {str(r[0]): {"count": int(r[1]), "average": round(float(r[2] or 0), 2)} for r in cur.fetchall()}
    cur.execute("""
        SELECT COUNT(*) AS n, AVG(rating) AS avg_rating FROM project_reviews
        WHERE created_at >= NOW() - INTERVAL '30 days'
    """)
    month_count, month_avg = cur.fetchone()
    cur.execute("SELECT COUNT(*) FILTER (WHERE body <> '') AS with_comment, "
                "COUNT(*) FILTER (WHERE replied_at IS NOT NULL) AS answered FROM project_reviews")
    with_comment, answered = (int(v or 0) for v in cur.fetchone())
    cur.execute("""
        SELECT COALESCE(SUM(shows), 0) AS shows, COALESCE(SUM(closes), 0) AS closes,
               COALESCE(SUM(laters), 0) AS laters, COUNT(*) FILTER (WHERE status = 'never') AS never
        FROM review_prompts
    """)
    shows, closes, laters, never = (int(v or 0) for v in cur.fetchone())
    summary = {"count": count, "average": average, "by_rating": by_rating, "by_surface": by_surface,
               "last_30_days": {"count": int(month_count or 0), "average": round(float(month_avg or 0), 2)},
               "with_comment": with_comment, "answered": answered,
               "shows": shows, "closes": closes, "laters": laters, "never": never}
    return items, total, summary


def review_owner(cur, review_id):
    cur.execute("SELECT account_id, user_key, rating, replied_at FROM project_reviews WHERE id = %s", (int(review_id),))
    row = cur.fetchone()
    if not row:
        raise ReviewError("review_not_found", 404)
    return {"account_id": row[0], "user_key": row[1], "rating": int(row[2]), "replied_at": row[3]}


def record_reply(cur, review_id, text, admin_id):
    cur.execute("UPDATE project_reviews SET reply_body = %s, replied_at = NOW(), replied_by = %s WHERE id = %s",
                (text, admin_id, int(review_id)))
