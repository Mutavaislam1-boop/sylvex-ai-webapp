"""Production timing instrumentation (from 82cba1a/919e2e4) localized the
remaining latency to specific queries once the event-loop-starvation and DB
pool leaks were already fixed:

  - GET /api/public/prostudio/gallery: select_prostudio_messages 5-8.5s for
    ~60 rows.
  - GET /api/web/session/me: get_user_state() ~3.7s total, get_account_summary()
    138-277ms per "simple" query.

None of the tables those queries hit (prostudio_messages, subscriptions,
purchases, user_events, generations, account_oauth) had an index that
covered their actual WHERE + ORDER BY, so every one of them was a full
table scan (+ sort, where ORDER BY is involved) instead of an index scan.
This file verifies the added indexes actually exist after the schema-setup
functions run, that the query planner uses them instead of falling back to
Seq Scan, and that the new ensure_generations_index() follows the same
once-per-process caching contract as ensure_prostudio_table() (see
test_ensure_prostudio_table_caching.py) plus safely no-ops when the
`generations` table - not owned by this codebase - doesn't exist.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)


@pytest.fixture
def db(monkeypatch):
    from pglite_adapter import Database
    import main

    database = Database()
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(main, "_PROSTUDIO_SCHEMA_READY", False)
    monkeypatch.setattr(main, "_GENERATIONS_INDEX_READY", False)
    yield database, main
    database.close()


def _index_names(database, table):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", (table,))
            return {row[0] for row in cur.fetchall()}


def _explain_uses_index(database, sql, params, index_name):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN {sql}", params)
            plan = "\n".join(row[0] for row in cur.fetchall())
    return index_name in plan, plan


# ---------------------------------------------------------------------------
# Gallery: /api/public/prostudio/gallery
# ---------------------------------------------------------------------------

def test_gallery_index_created_and_used(db):
    database, main = db
    main.ensure_prostudio_table()

    assert "idx_prostudio_messages_user_created" in _index_names(database, "prostudio_messages")

    with database.connect() as conn:
        with conn.cursor() as cur:
            # Enough rows, across enough distinct users, that the planner's
            # own cost estimates - not just index presence - favor the
            # index over a sequential scan (pglite/Postgres will happily
            # ignore an index on a handful of rows).
            for user in range(20):
                for i in range(50):
                    cur.execute(
                        """
                        INSERT INTO prostudio_messages
                            (conversation_id, telegram_id, mode, prompt, response_text, image_url, created_at)
                        VALUES (%s, %s, 'image', 'p', 'r', 'https://example.com/x.png', NOW() - (%s || ' minutes')::interval)
                        """,
                        (f"conv-{user}-{i}", 1000 + user, i),
                    )
            conn.commit()

    # Mirrors the exact WHERE/ORDER BY/LIMIT public_prostudio_gallery() runs.
    gallery_sql = """
        SELECT id FROM prostudio_messages
        WHERE telegram_id = %s
          AND (COALESCE(image_url, '') <> '' OR COALESCE(video_url, '') <> ''
               OR COALESCE(audio_url, '') <> '' OR COALESCE(response_text, '') <> '')
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
    """
    used, plan = _explain_uses_index(database, gallery_sql, (1005, 80, 0), "idx_prostudio_messages_user_created")
    assert used, f"gallery query did not use the new index:\n{plan}"


# ---------------------------------------------------------------------------
# get_user_state(): subscriptions / purchases / user_events / generations
# ---------------------------------------------------------------------------

def test_subscriptions_index_created_and_used(db):
    database, main = db
    main.ensure_payment_tables()
    assert "idx_subscriptions_user_expires" in _index_names(database, "subscriptions")

    with database.connect() as conn:
        with conn.cursor() as cur:
            for user in range(20):
                for i in range(20):
                    cur.execute(
                        """
                        INSERT INTO subscriptions (telegram_id, subscription_type, status, expires_at)
                        VALUES (%s, 'month', 'active', NOW() + (%s || ' days')::interval)
                        """,
                        (1000 + user, i),
                    )
            conn.commit()

    active_sql = """
        SELECT subscription_type, expires_at::timestamp FROM subscriptions
        WHERE telegram_id = %s AND status = 'active' AND expires_at::timestamp > NOW()
        ORDER BY expires_at::timestamp DESC LIMIT 1
    """
    used, plan = _explain_uses_index(database, active_sql, (1005,), "idx_subscriptions_user_expires")
    assert used, f"active-subscription query did not use the new index:\n{plan}"

    latest_sql = """
        SELECT subscription_type, expires_at::timestamp FROM subscriptions
        WHERE telegram_id = %s
        ORDER BY expires_at::timestamp DESC NULLS LAST, id DESC LIMIT 1
    """
    used, plan = _explain_uses_index(database, latest_sql, (1005,), "idx_subscriptions_user_expires")
    assert used, f"latest-subscription query did not use the new index:\n{plan}"


def test_purchases_index_created(db):
    database, main = db
    main.ensure_payment_tables()
    assert "idx_purchases_user_created" in _index_names(database, "purchases")


def test_user_events_index_created(db):
    database, main = db
    main.ensure_user_events_table()
    assert "idx_user_events_user_created" in _index_names(database, "user_events")


def test_generations_index_created_when_table_exists(db):
    database, main = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE generations (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    generation_type TEXT,
                    prompt TEXT,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()

    main.ensure_generations_index()
    assert "idx_generations_user_created" in _index_names(database, "generations")


def test_generations_index_noop_when_table_missing(db):
    """This process doesn't own the `generations` schema (it predates this
    webapp and is shared with the Telegram bot) - the guard must not error
    or create anything when the table isn't there."""
    database, main = db
    main.ensure_generations_index()  # must not raise
    assert main._GENERATIONS_INDEX_READY is True


def test_generations_index_runs_at_most_once_per_process(db, monkeypatch):
    database, main = db
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE generations (
                    id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()

    call_count = {"n": 0}
    real_db_connect = main.db_connect

    def counting_connect(*a, **k):
        call_count["n"] += 1
        return real_db_connect(*a, **k)

    monkeypatch.setattr(main, "db_connect", counting_connect)

    main.ensure_generations_index()
    assert call_count["n"] == 1
    main.ensure_generations_index()
    main.ensure_generations_index()
    assert call_count["n"] == 1, "a process that already knows the index exists must not re-checkout a connection"


# ---------------------------------------------------------------------------
# get_account_summary(): account_oauth
# ---------------------------------------------------------------------------

def test_account_oauth_index_created_and_used(db, monkeypatch):
    database, main = db
    from services import account_identity

    # account_identity imports db_connect directly from db_pool rather than
    # through main, so it needs its own patch onto the same pglite database.
    monkeypatch.setattr(account_identity, "db_connect", lambda *a, **k: database.connect())
    monkeypatch.setattr(account_identity, "_ACCOUNT_TABLES_READY", False)

    account_identity.ensure_account_tables("pglite://test")
    assert "idx_account_oauth_account_id" in _index_names(database, "account_oauth")

    with database.connect() as conn:
        with conn.cursor() as cur:
            for account_id in range(1, 21):
                cur.execute(
                    "INSERT INTO sylvex_accounts (account_id, active_telegram_id) VALUES (%s, %s)",
                    (account_id, 5000 + account_id),
                )
                cur.execute(
                    "INSERT INTO account_oauth (account_id, provider, subject, email) VALUES (%s, 'google', %s, 'x@example.com')",
                    (account_id, f"sub-{account_id}"),
                )
            conn.commit()

    used, plan = _explain_uses_index(
        database,
        "SELECT provider, email FROM account_oauth WHERE account_id = %s",
        (10,),
        "idx_account_oauth_account_id",
    )
    assert used, f"account_oauth lookup did not use the new index:\n{plan}"
