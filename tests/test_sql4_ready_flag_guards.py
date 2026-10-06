# Regression tests for the security audit's SQL-4 finding: six
# schema-migration helpers (ensure_user_events_table, ensure_payment_tables,
# ensure_user_profiles_table, ensure_user_referrals_table,
# ensure_elevenlabs_table, ensure_community_tables) re-ran their full DDL
# batch on every call, unlike ensure_prostudio_table()/ensure_admin_tables()/
# ensure_references_table()/ensure_generations_index(), which already use a
# module-level "ready" flag guarded by a threading.Lock() so the migration
# only ever runs once per process. Under webhook burst traffic (PayPal
# retries, concurrent Stars purchases) every call was paying for a DDL
# batch + COMMIT, holding a pooled DB connection longer than necessary
# exactly during payment-traffic spikes.
#
# Fix: the same double-checked-locking ready-flag pattern was added to all
# six functions, with the flag only ever set to True after a successful
# commit - a failed migration leaves it False so the next call can retry,
# instead of wrongly caching the failure forever.
#
# These tests run against a real embedded Postgres (pglite) via the same
# harness tests/test_ensure_prostudio_table_caching.py already uses, so
# they are skipped unless SYLVEX_TEST_NODE/SYLVEX_PGLITE_MODULE are set -
# matching that existing test's own convention exactly.
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "support"))


def _pglite_available():
    return bool(os.getenv("SYLVEX_TEST_NODE") and os.getenv("SYLVEX_PGLITE_MODULE"))


pytestmark = pytest.mark.skipif(
    not _pglite_available(),
    reason="Set SYLVEX_TEST_NODE and SYLVEX_PGLITE_MODULE to run real-SQL tests",
)

# function name -> (ready-flag attribute name, a table it creates, the max
# number of real DB connections one full, uncontended initialization needs).
# ensure_community_tables also calls ensure_user_profiles_table() as a
# side effect (preserved from the original, unguarded behavior) - each has
# its own independent guard, so a cold run of ensure_community_tables pays
# for two real connections (one per guard), not one.
TARGETS = [
    ("ensure_user_events_table", "_USER_EVENTS_SCHEMA_READY", "user_events", 1),
    ("ensure_payment_tables", "_PAYMENT_SCHEMA_READY", "purchases", 1),
    ("ensure_user_profiles_table", "_USER_PROFILES_SCHEMA_READY", "user_profiles", 1),
    ("ensure_user_referrals_table", "_USER_REFERRALS_SCHEMA_READY", "user_referrals", 1),
    ("ensure_elevenlabs_table", "_ELEVENLABS_SCHEMA_READY", "user_voice_settings", 1),
    ("ensure_community_tables", "_COMMUNITY_SCHEMA_READY", "community_posts", 2),
]


@pytest.fixture
def db(monkeypatch):
    from pglite_adapter import Database
    import main

    database = Database()
    monkeypatch.setattr(main, "DATABASE_URL", "pglite://test")
    monkeypatch.setattr(main, "db_connect", lambda *a, **k: database.connect())
    # Force a real first run for every target, regardless of what earlier
    # tests in this same process already marked ready.
    for _, flag_name, _, _ in TARGETS:
        monkeypatch.setattr(main, flag_name, False)

    yield database, main
    database.close()


def _table_exists(database, table_name):
    with database.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (table_name,))
            return cur.fetchone()[0] is not None


# ---------------------------------------------------------------------------
# First initialization + repeated calls: the DDL batch must actually run
# the first time (and really create the table), and must never run again
# for later calls in the same process.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("func_name,flag_name,table_name,max_connects", TARGETS)
def test_first_call_runs_ddl_and_later_calls_do_not(db, monkeypatch, func_name, flag_name, table_name, max_connects):
    database, main = db
    func = getattr(main, func_name)
    call_count = {"n": 0}
    real_db_connect = main.db_connect

    def counting_connect(*a, **k):
        call_count["n"] += 1
        return real_db_connect(*a, **k)

    monkeypatch.setattr(main, "db_connect", counting_connect)

    assert not _table_exists(database, table_name), "table must not pre-exist before the first call"

    func()
    first_call_connects = call_count["n"]
    assert 1 <= first_call_connects <= max_connects, (
        f"the first call must actually run the DDL batch (at most {max_connects} real "
        f"DB connections for {func_name}, got {first_call_connects})"
    )
    assert getattr(main, flag_name) is True, "the ready flag must be set after a successful first run"
    assert _table_exists(database, table_name), "the first call must have actually created the table"

    func()
    func()
    func()

    assert call_count["n"] == first_call_connects, (
        f"a process that already knows {func_name}'s schema is ready must never pay for "
        "another DB round trip just to re-run idempotent DDL"
    )


# ---------------------------------------------------------------------------
# Concurrent calls: many threads racing to initialize at once must still
# only run the DDL batch once (per independent guard - see TARGETS' note on
# ensure_community_tables), proving the lock actually serializes first-time
# initialization rather than letting every thread in to run DDL together.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("func_name,flag_name,table_name,max_connects", TARGETS)
def test_concurrent_calls_initialize_at_most_once(db, monkeypatch, func_name, flag_name, table_name, max_connects):
    database, main = db
    func = getattr(main, func_name)
    call_count = {"n": 0}
    lock = threading.Lock()
    real_db_connect = main.db_connect

    def counting_connect(*a, **k):
        with lock:
            call_count["n"] += 1
        return real_db_connect(*a, **k)

    monkeypatch.setattr(main, "db_connect", counting_connect)

    thread_count = 8
    barrier = threading.Barrier(thread_count)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            func()
        except Exception as exc:  # pragma: no cover - surfaced via `errors`
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"no thread should see an exception from a concurrent call: {errors}"
    assert call_count["n"] <= max_connects, (
        f"{thread_count} threads racing to initialize {func_name} concurrently must still only "
        f"run its DDL batch once (at most {max_connects} real DB connections total, got "
        f"{call_count['n']}) - the lock must actually serialize first-time initialization"
    )
    assert getattr(main, flag_name) is True
    assert _table_exists(database, table_name)


# ---------------------------------------------------------------------------
# Failure/retry: if the migration fails, the ready flag must NOT be set, so
# the next call is free to retry (rather than permanently caching a failed
# initialization as if it had succeeded).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "func_name,flag_name,table_name",
    [
        ("ensure_user_events_table", "_USER_EVENTS_SCHEMA_READY", "user_events"),
        ("ensure_payment_tables", "_PAYMENT_SCHEMA_READY", "purchases"),
    ],
)
def test_failed_first_call_does_not_mark_ready_and_next_call_retries(db, monkeypatch, func_name, flag_name, table_name):
    database, main = db
    func = getattr(main, func_name)
    real_db_connect = main.db_connect
    attempt = {"n": 0}

    def flaky_connect(*a, **k):
        attempt["n"] += 1
        conn = real_db_connect(*a, **k)
        if attempt["n"] == 1:
            # Simulate a transient failure partway through the migration
            # (e.g. a dropped connection mid-DDL-batch) on the very first
            # attempt only; every later attempt gets a fully working
            # connection.
            real_cursor = conn.cursor

            def failing_cursor():
                cur = real_cursor()
                def boom(sql, params=()):
                    raise RuntimeError("simulated transient DB failure")
                cur.execute = boom
                return cur

            conn.cursor = failing_cursor
        return conn

    monkeypatch.setattr(main, "db_connect", flaky_connect)

    with pytest.raises(RuntimeError, match="simulated transient DB failure"):
        func()
    assert getattr(main, flag_name) is False, (
        "a failed migration must never be cached as ready - the next call must be able to retry"
    )
    assert not _table_exists(database, table_name), "a failed migration must not have left a half-applied table"

    # The retry (now against a healthy connection) must succeed cleanly.
    func()
    assert getattr(main, flag_name) is True
    assert _table_exists(database, table_name)

    # And, as with the happy path, a further call must not reconnect again.
    connects_so_far = attempt["n"]
    func()
    assert attempt["n"] == connects_so_far
