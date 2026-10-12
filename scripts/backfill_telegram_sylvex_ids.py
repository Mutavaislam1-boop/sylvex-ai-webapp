"""One-time backfill: give every existing Telegram-only user a SYLVEX ID.

New Telegram users get one automatically (the `users` AFTER INSERT trigger
created by services/account_identity.ensure_account_tables at webapp
startup); this covers users created before that trigger existed.

What it writes: one `sylvex_accounts` row per real users.telegram_id that
has none (origin 'telegram', ID SS 0626 99 NNNN from
sylvex_allocate_telegram_account_id()). It never changes an existing row,
never touches website accounts or their IDs, and never touches business
data (balances, generations, payments).

Safety model:
  - Defaults to DRY RUN: reports how many users would get an ID and rolls
    back. Nothing is written unless you pass --execute.
  - Refuses to run until the webapp has deployed the identity schema
    (origin column + allocator function + users trigger).
  - Small batches, each its own short transaction, with a pause between
    them, so `users` and `sylvex_accounts` are never locked for long.
    Safe to stop and rerun at any time: it only picks up users still
    missing an ID.

Run from the sylvex-ai-webapp repo root with DB connectivity, e.g. via
`railway run`:

    DATABASE_PUBLIC_URL=... python3 scripts/backfill_telegram_sylvex_ids.py            # dry run
    DATABASE_PUBLIC_URL=... python3 scripts/backfill_telegram_sylvex_ids.py --execute  # writes
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
import psycopg2

BATCH_SIZE = 500
PAUSE_SECONDS = 0.2


def schema_ready(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'sylvex_accounts' AND column_name = 'origin'"
    )
    if not cur.fetchone():
        return False
    cur.execute("SELECT 1 FROM pg_proc WHERE proname = 'sylvex_allocate_telegram_account_id'")
    if not cur.fetchone():
        return False
    cur.execute("SELECT 1 FROM pg_trigger WHERE tgname = 'sylvex_users_ensure_account' AND NOT tgisinternal")
    return bool(cur.fetchone())


def run(conn, execute, batch_size=BATCH_SIZE, pause=PAUSE_SECONDS, log=print):
    from services.account_identity import backfill_telegram_accounts, count_telegram_accounts_missing

    cur = conn.cursor()
    try:
        if not schema_ready(cur):
            conn.rollback()
            log("Identity schema not deployed yet (origin column, allocator or users trigger missing). "
                "Deploy the webapp first; nothing was changed.")
            return None
        missing = count_telegram_accounts_missing(cur)
        conn.rollback()
        log(f"Telegram-only users without a SYLVEX ID: {missing}")
        if not execute:
            log("Dry run - nothing written. Rerun with --execute to assign IDs.")
            return {"missing": missing, "created": 0}
        created = 0
        while True:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            batch = backfill_telegram_accounts(cur, batch_size)
            conn.commit()
            created += batch
            if batch:
                log(f"Assigned {created} so far")
            if not batch:
                break
            time.sleep(pause)
        remaining = count_telegram_accounts_missing(cur)
        conn.rollback()
        log(f"Done: {created} SYLVEX IDs assigned, {remaining} users still without one.")
        return {"missing": missing, "created": created, "remaining": remaining}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def main():
    execute = "--execute" in sys.argv
    dsn = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_PUBLIC_URL (or DATABASE_URL) in the environment.")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        result = run(conn, execute)
    finally:
        conn.close()
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
