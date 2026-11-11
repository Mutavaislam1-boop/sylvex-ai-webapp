"""Railway-editor style: every file is sent as ONE statement in autocommit mode."""
import sys, uuid, pathlib, re, psycopg2
sys.path.insert(0, sys.argv[1]); SQL = pathlib.Path(sys.argv[2])
DSN = "postgresql://sylvex:sylvex@sx001c3-postgres:5432/policy_erasure_test_local"
from services import account_identity as ai, account_erasure as er, account_erasure_guards as guards
def stmts(text): return [x for x in re.sub(r"--[^\n]*", "", text).split(";\n") if x.strip()]
def build(dates=None, extra=None):
    schema = "rw_" + uuid.uuid4().hex[:8]
    with psycopg2.connect(DSN) as c, c.cursor() as cur: cur.execute(f'CREATE SCHEMA "{schema}"')
    cf = lambda *a, **k: psycopg2.connect(DSN, options=f"-c search_path={schema}")
    ai.db_connect = cf; er.db_connect = cf; ai._ACCOUNT_TABLES_READY = False
    k = cf(); cur = k.cursor()
    cur.execute("CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, balance INT DEFAULT 0, subscription TEXT, created_at TEXT)")
    cur.execute("CREATE TABLE user_events(id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, source TEXT, event_type TEXT)")
    cur.execute("CREATE TABLE user_profiles(telegram_id BIGINT PRIMARY KEY, display_name TEXT)")
    cur.execute("CREATE TABLE user_referrals(telegram_id BIGINT PRIMARY KEY, code TEXT UNIQUE NOT NULL)")
    cur.execute("CREATE TABLE referral_attributions(invited_telegram_id BIGINT PRIMARY KEY, inviter_telegram_id BIGINT NOT NULL, referral_code TEXT NOT NULL)")
    cur.execute("CREATE TABLE purchases(id SERIAL, telegram_id BIGINT)")
    cur.execute("CREATE TABLE user_credit_wallets(telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE, purchased_credits INT)")
    others = [7772859187] + [7000000400 + i for i in range(18)]
    for t in [12345, 123456789, 900000001]: cur.execute("INSERT INTO users(telegram_id, created_at) VALUES(%s,'2026-10-01')", (t,))
    for i, t in enumerate(others):
        d = (dates or {}).get(t, "2026-10-21 11:45:24" if t == 7772859187 else f"2026-10-{(i % 20) + 1:02d} 08:00:00")
        cur.execute("INSERT INTO users(telegram_id, balance, created_at) VALUES(%s,%s,%s)", (t, 317 if t == 7772859187 else 1, d))
    cur.execute("INSERT INTO user_events(telegram_id, source, event_type) VALUES (123456789,'t','x'),(7772859187,'m','y')")
    cur.execute("INSERT INTO user_profiles VALUES (12345,'test'),(7772859187,'real')")
    cur.execute("INSERT INTO user_referrals VALUES (900000001,'TESTCODE'),(7772859187,'REALCODE')")
    cur.execute("INSERT INTO purchases(telegram_id) VALUES (7772859187)"); cur.execute("INSERT INTO user_credit_wallets VALUES (7772859187, 5)")
    if extra: cur.execute(extra)
    k.commit(); ai.ensure_account_tables("x", connect=cf)
    k = cf(); c = k.cursor(); er.ensure_schema(c); guards.install(c); k.commit()
    return schema, cf
def one(cf, text):
    k = cf(); k.autocommit = True; c = k.cursor()
    try:
        c.execute(text)
        return c.fetchall() if c.description else None
    finally: k.close()
def file_stmts(cf, name): return [one(cf, s) for s in stmts((SQL / name).read_text())]
def q(cf, s): return one(cf, s)
def drop(schema):
    with psycopg2.connect(DSN) as c, c.cursor() as cur: cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
def expect_stop(cf, name, label):
    try: one(cf, (SQL / name).read_text()); raise SystemExit(label + ": no STOP")
    except psycopg2.Error as e: print(label, "->", str(e).splitlines()[0])
# A. success path
schema, cf = build()
before = file_stmts(cf, "4c_precheck_test_ids.sql")[0][0]; print("4c-0", before)
one(cf, (SQL / "6_delete_test_accounts.sql").read_text())
print("6b", file_stmts(cf, "6b_verify_delete.sql")[0])
print("5a", file_stmts(cf, "5a_dates_preview.sql")[0])
one(cf, (SQL / "5_backfill_19.sql").read_text())
v, after = [r[0] for r in file_stmts(cf, "7_verify_all.sql")]; print("7", v, after)
assert v[:3] == (0, 0, 1) and str(v[3]) == "2026-10-21 11:45:24"
assert after == (before[0]-3, before[1]-1, before[2]-1, before[3]-1, before[4]+19)
assert q(cf, "SELECT COUNT(*) FROM sylvex_accounts WHERE created_at::date = NOW()::date")[0][0] == 0
assert q(cf, "SELECT balance FROM users WHERE telegram_id=7772859187")[0][0] == 317
drop(schema)
# B. one invalid date -> step 5 stops, nothing inserted
schema, cf = build(dates={7000000405: "not-a-date"})
one(cf, (SQL / "6_delete_test_accounts.sql").read_text())
expect_stop(cf, "5_backfill_19.sql", "invalid date")
assert q(cf, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 0
drop(schema)
# C. step 5 before step 6 -> stops
schema, cf = build()
expect_stop(cf, "5_backfill_19.sql", "order")
assert q(cf, "SELECT COUNT(*) FROM sylvex_accounts")[0][0] == 0
drop(schema)
# D. an extra related row -> step 6 stops, nothing deleted
schema, cf = build(extra="INSERT INTO user_events(telegram_id, source, event_type) VALUES (12345,'t','new')")
expect_stop(cf, "6_delete_test_accounts.sql", "extra row")
assert q(cf, "SELECT COUNT(*) FROM users WHERE telegram_id IN (12345,123456789,900000001)")[0][0] == 3
drop(schema)
# E. referral link to a real user -> step 6 stops
schema, cf = build(extra="INSERT INTO referral_attributions VALUES (7000000401, 900000001, 'TESTCODE')")
expect_stop(cf, "6_delete_test_accounts.sql", "referral")
assert q(cf, "SELECT COUNT(*) FROM user_referrals")[0][0] == 2
drop(schema)
# F. a future date -> step 5 stops
schema, cf = build(dates={7000000402: "2099-01-01 00:00:00"})
one(cf, (SQL / "6_delete_test_accounts.sql").read_text())
expect_stop(cf, "5_backfill_19.sql", "future date")
drop(schema)
print("ALL OK")
