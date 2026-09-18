"""One-time cleanup: delete ONLY the 4 explicitly-approved Website test
accounts and their directly-related data (identity rows + their synthetic
storage-telegram_id's business data). Never touches Telegram-only users or
any already-merged account.

Reuses this codebase's own authoritative "which tables hold business data
for one telegram_id" logic (services/account_identity.py's
_SECONDARY_ID_COLUMNS + _telegram_id_columns()) - the exact same functions
the real Connect-Telegram merge path already relies on - instead of a
hand-maintained table list that could drift or miss something.

Safety model:
  - Defaults to DRY RUN: prints exactly what would be deleted (per table,
    per account) and rolls back. Nothing is committed unless you pass
    --execute.
  - Refuses to run at all unless the live DB contains exactly the 4
    approved (account_id, email) pairs below, each with merged_at IS NULL
    and a storage id inside the synthetic Website range (>=900000000000,
    never a real Telegram id).
  - Everything is one transaction: if anything unexpected happens partway
    through, nothing is committed.

Run from the sylvex-ai-webapp repo root (needs services/account_identity.py
importable) with DB connectivity, e.g. via `railway run`:

    DATABASE_PUBLIC_URL=... python3 scripts/cleanup_approved_test_accounts.py            # dry run
    DATABASE_PUBLIC_URL=... python3 scripts/cleanup_approved_test_accounts.py --execute  # actually deletes + resets the sequence
"""
import os
import sys

# Lives one level under the repo root (scripts/); add the repo root itself
# (the current working directory, per the "run from repo root" instruction
# above) so `services.account_identity` resolves regardless of how this
# script is invoked.
sys.path.insert(0, os.getcwd())
import psycopg2

# --- exactly what was approved - nothing else is in scope ---
APPROVED = [
    (10002, "mutavaislam0@gmail.com"),
    (10003, "mutavaislam5@gmail.com"),
    (10004, "mutavaislam6@gmail.com"),
    (10006, "mutavaislam7@gmail.com"),
]
STORAGE_ID_FLOOR = 900000000000  # sylvex_web_storage_seq START value


def main():
    execute = "--execute" in sys.argv
    dsn = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_PUBLIC_URL (or DATABASE_URL) in the environment.")

    from services.account_identity import _SECONDARY_ID_COLUMNS, _telegram_id_columns

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # --- Safety check 1: exactly these 4, unmerged, emails match ---
        cur.execute(
            """
            SELECT sa.account_id, sa.active_telegram_id, ae.email, sa.merged_at
            FROM sylvex_accounts sa
            JOIN account_emails ae ON ae.account_id = sa.account_id
            WHERE sa.account_id = ANY(%s)
            """,
            ([a for a, _ in APPROVED],),
        )
        found = {row[0]: row for row in cur.fetchall()}

        problems = []
        for account_id, email in APPROVED:
            row = found.get(account_id)
            if row is None:
                problems.append(f"account_id {account_id}: not found")
                continue
            _, storage_id, db_email, merged_at = row
            if db_email != email:
                problems.append(f"account_id {account_id}: email mismatch (db={db_email!r}, expected={email!r})")
            if merged_at is not None:
                problems.append(f"account_id {account_id}: merged_at is set ({merged_at}) - REFUSING (already merged with Telegram)")
            if storage_id < STORAGE_ID_FLOOR:
                problems.append(f"account_id {account_id}: active_telegram_id={storage_id} looks like a REAL Telegram id, not a synthetic storage id - REFUSING")

        if problems:
            print("SAFETY CHECK FAILED - nothing touched:")
            for p in problems:
                print(" -", p)
            conn.rollback()
            return 1

        print("Safety check passed: all 4 approved accounts found, unmerged, storage ids in range.")
        print()

        account_ids = [a for a, _ in APPROVED]
        storage_ids = [found[a][1] for a in account_ids]

        # --- Report exactly what will be deleted, table by table ---
        plan = []

        def count_and_plan(label, query, params):
            cur.execute(query, params)
            n = cur.fetchone()[0]
            if n:
                plan.append((label, n))

        count_and_plan("account_oauth", "SELECT COUNT(*) FROM account_oauth WHERE account_id = ANY(%s)", (account_ids,))
        count_and_plan("account_link_codes", "SELECT COUNT(*) FROM account_link_codes WHERE account_id = ANY(%s)", (account_ids,))
        count_and_plan("account_emails", "SELECT COUNT(*) FROM account_emails WHERE account_id = ANY(%s)", (account_ids,))

        secondary_tables = []
        for table, column in _SECONDARY_ID_COLUMNS:
            cur.execute("SELECT to_regclass(%s)", (table,))
            if cur.fetchone()[0] is None:
                continue
            secondary_tables.append((table, column))
        for table, column in _telegram_id_columns(cur):
            if table == "users":
                continue
            secondary_tables.append((table, column))

        for table, column in secondary_tables:
            cur.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" = ANY(%s)',
                (storage_ids,),
            )
            n = cur.fetchone()[0]
            if n:
                plan.append((f"{table}.{column}", n))

        count_and_plan("users", "SELECT COUNT(*) FROM users WHERE telegram_id = ANY(%s)", (storage_ids,))
        count_and_plan("sylvex_accounts", "SELECT COUNT(*) FROM sylvex_accounts WHERE account_id = ANY(%s)", (account_ids,))

        print("Rows that would be deleted:")
        for label, n in plan:
            print(f"  {label}: {n}")
        print()

        if not execute:
            print("DRY RUN - nothing deleted, nothing committed. Re-run with --execute to actually delete + reset the sequence.")
            conn.rollback()
            return 0

        # --- Actually delete, same order as above ---
        cur.execute("DELETE FROM account_oauth WHERE account_id = ANY(%s)", (account_ids,))
        cur.execute("DELETE FROM account_link_codes WHERE account_id = ANY(%s)", (account_ids,))
        cur.execute("DELETE FROM account_emails WHERE account_id = ANY(%s)", (account_ids,))
        for table, column in secondary_tables:
            cur.execute(f'DELETE FROM "{table}" WHERE "{column}" = ANY(%s)', (storage_ids,))
        cur.execute("DELETE FROM users WHERE telegram_id = ANY(%s)", (storage_ids,))
        cur.execute("DELETE FROM sylvex_accounts WHERE account_id = ANY(%s)", (account_ids,))

        cur.execute("ALTER SEQUENCE sylvex_website_id_seq RESTART WITH 1")

        conn.commit()
        print("Committed: 4 accounts and their related data deleted; sylvex_website_id_seq reset to 1.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
