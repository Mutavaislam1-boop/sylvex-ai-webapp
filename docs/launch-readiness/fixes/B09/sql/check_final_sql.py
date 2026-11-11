import sys, uuid, pathlib, re, psycopg2
def stmts(text): return [x for x in re.sub(r"--[^\n]*", "", text).split(";") if x.strip()]
sys.path.insert(0, sys.argv[1]); SQL = pathlib.Path(sys.argv[2])
DSN = "postgresql://sylvex:sylvex@sx001c3-postgres:5432/policy_erasure_test_local"
from services import account_identity as ai, account_erasure as er, account_erasure_guards as guards
def build(extra=None):
    schema = "fin_" + uuid.uuid4().hex[:8]
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
    tests = [12345, 123456789, 900000001]; others = [7772859187] + [7000000300 + i for i in range(18)]
    for t in tests + others: cur.execute("INSERT INTO users(telegram_id, created_at) VALUES(%s,'2026-10-03 10:00:00')", (t,))
    cur.execute("INSERT INTO user_events(telegram_id, source, event_type) VALUES (123456789,'t','x'),(7772859187,'m','y'),(7000000300,'m','z')")
    cur.execute("INSERT INTO user_profiles VALUES (12345,'test'),(7772859187,'real')")
    cur.execute("INSERT INTO user_referrals VALUES (900000001,'TESTCODE'),(7772859187,'REALCODE')")
    cur.execute("INSERT INTO purchases(telegram_id) VALUES (7772859187)")
    cur.execute("INSERT INTO user_credit_wallets VALUES (7772859187, 5)")
    if extra: cur.execute(extra)
    k.commit(); ai.ensure_account_tables("x", connect=cf)
    k = cf(); c = k.cursor(); er.ensure_schema(c); guards.install(c); k.commit()
    return schema, cf
def runf(cf, name):
    k = cf(); k.autocommit = True; c = k.cursor(); c.execute((SQL / name).read_text()); r = None
    try: r = c.fetchall()
    except psycopg2.ProgrammingError: pass
    k.close(); return r
def q(cf, s):
    k = cf(); c = k.cursor(); c.execute(s); r = c.fetchall(); k.close(); return r
def drop(schema):
    with psycopg2.connect(DSN) as c, c.cursor() as cur: cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
# success path: 4c -> 6 -> 5 -> 7
schema, cf = build()
snap = q(cf, stmts((SQL/"4c_precheck_test_ids.sql").read_text())[0])[0]; print("before", snap)
k = cf(); c = k.cursor(); c.execute((SQL/"4c_precheck_test_ids.sql").read_text().split("-- 4c-2")[1].split("-- 4c-3")[0].split("\n",1)[1]); print("4c-2", c.fetchall()); k.close()
found = runf(cf, "4c_precheck_test_ids.sql"); print("4c-3", found)
runf(cf, "6_delete_test_accounts.sql")
body = (SQL / "5_backfill_19.sql").read_text().split("BEGIN;",1)[1].rsplit("COMMIT;",1)[0]
k = cf(); k.autocommit = True; c = k.cursor(); c.execute("BEGIN"); c.execute(body.split("WITH todo",1)[0]); c.execute("WITH todo"+body.split("WITH todo",1)[1]); n = c.fetchone()[0]; c.execute("COMMIT"); k.close()
print("inserted", n); assert n == 19
v = q(cf, stmts((SQL/"7_verify_all.sql").read_text())[0])[0]; print("verify", v)
after = runf(cf, "7_verify_all.sql")[0]; print("after", after)
assert v[0] == 0 and v[1] == 0 and v[2] == 1
assert after == (snap[0]-3, snap[1]-1, snap[2]-1, snap[3]-1, snap[4]+19), (snap, after)
assert q(cf, "SELECT COUNT(*) FROM user_events WHERE telegram_id IN (7772859187,7000000300)")[0][0] == 2
assert q(cf, "SELECT code FROM user_referrals")[0][0] == "REALCODE" and q(cf, "SELECT COUNT(*) FROM purchases")[0][0] == 1
drop(schema)
# guard: another user joined with a test code -> abort, nothing deleted
schema, cf = build("INSERT INTO referral_attributions VALUES (7000000301, 900000001, 'TESTCODE')")
try: runf(cf, "6_delete_test_accounts.sql"); raise SystemExit("referral guard did not fire")
except psycopg2.Error as e: print("referral guard:", str(e).splitlines()[0])
assert q(cf, "SELECT COUNT(*) FROM users WHERE telegram_id IN (12345,123456789,900000001)")[0][0] == 3
drop(schema)
# guard: an unexpected extra row -> abort, nothing deleted
schema, cf = build("INSERT INTO user_events(telegram_id, source, event_type) VALUES (12345,'t','extra')")
try: runf(cf, "6_delete_test_accounts.sql"); raise SystemExit("count guard did not fire")
except psycopg2.Error as e: print("count guard:", str(e).splitlines()[0])
assert q(cf, "SELECT COUNT(*) FROM user_events WHERE telegram_id IN (12345,123456789)")[0][0] == 2
drop(schema)
print("ALL OK")
