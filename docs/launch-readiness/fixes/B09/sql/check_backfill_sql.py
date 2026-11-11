"""Run the B09 backfill SQL against an isolated local schema built by the app code."""
import os, sys, uuid, pathlib
import psycopg2
sys.path.insert(0, sys.argv[1])  # repo root (b09-release)
SQL = pathlib.Path(sys.argv[2])
DSN = "postgresql://sylvex:sylvex@sx001c3-postgres:5432/policy_erasure_test_local"
schema = "backfill_sql_" + uuid.uuid4().hex[:10]
with psycopg2.connect(DSN) as c, c.cursor() as cur:
    cur.execute(f'CREATE SCHEMA "{schema}"')
conn_factory = lambda *a, **k: psycopg2.connect(DSN, options=f"-c search_path={schema}")
from services import account_identity as ai, account_erasure as er, account_erasure_guards as guards
ai.db_connect = conn_factory
er.db_connect = conn_factory
conn = conn_factory(); cur = conn.cursor()
cur.execute("""CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
               balance INTEGER DEFAULT 0, subscription TEXT, created_at TEXT)""")
cur.execute("CREATE TABLE purchases(id SERIAL PRIMARY KEY, telegram_id BIGINT, amount INT)")
cur.execute("CREATE TABLE subscriptions(id SERIAL PRIMARY KEY, telegram_id BIGINT, plan TEXT, expires_at TEXT)")
# 22 pre-trigger Telegram users (one is the test account) with text dates in several formats
olds = [7772859187] + [7000000100 + i for i in range(21)]
fmts = ["2026-10-21 11:45:24", "2026-10-01T08:00:00", "2026-09-15 10:00:00.123456", "", "not-a-date", None]
for i, tid in enumerate(olds):
    cur.execute("INSERT INTO users VALUES(%s,'u','U',%s,'pro',%s)", (tid, 317 if tid == 7772859187 else 10 + i, fmts[i % len(fmts)]))
cur.execute("INSERT INTO purchases(telegram_id,amount) VALUES(7772859187,100)")
cur.execute("INSERT INTO subscriptions(telegram_id,plan,expires_at) VALUES(7772859187,'pro_month','2026-12-01')")
conn.commit()
ai.ensure_account_tables("x", connect=conn_factory)  # schema, allocator, safe timestamp, trigger (after the old users)
cur = conn_factory().cursor(); c2 = cur.connection
# a user that already has an ID (via trigger), a merged alias, and a website storage key
cur.execute("INSERT INTO users(telegram_id, created_at) VALUES(7000000900,'2026-11-05')")
cur.execute("SELECT account_id FROM sylvex_accounts WHERE active_telegram_id=7000000900"); existing = cur.fetchone()[0]
cur.execute("INSERT INTO users(telegram_id, created_at) VALUES(7000000901,'2026-10-01')")
cur.execute("UPDATE sylvex_accounts SET active_telegram_id=NULL, merged_telegram_id=7000000901, merged_at=NOW() WHERE active_telegram_id=7000000901")
cur.execute("INSERT INTO users(telegram_id, created_at) VALUES(900000000123,'2026-10-01')")  # storage key: never a Telegram id
er.ensure_schema(cur); guards.install(cur)
c2.commit()
def run(name):
    k = conn_factory(); k.autocommit = True; kc = k.cursor(); out = []
    kc.execute((SQL / name).read_text())
    try: out = kc.fetchall()
    except psycopg2.ProgrammingError: pass
    k.close(); return out
def q(sql):
    k = conn_factory(); kc = k.cursor(); kc.execute(sql); r = kc.fetchall(); k.close(); return r
before = q("SELECT account_id, active_telegram_id, origin, created_at FROM sylvex_accounts ORDER BY account_id")
money = q("SELECT (SELECT array_agg(balance ORDER BY telegram_id) FROM users), (SELECT COUNT(*) FROM purchases), (SELECT COUNT(*) FROM subscriptions)")
p = run("1_preview.sql"); print("preview", p)
assert p[0][0] == 22 and p[0][1] == 1
# Railway may run the whole file as one batch; psycopg2 returns the last result
k = conn_factory(); k.autocommit = True; kc = k.cursor()
kc.execute("SELECT 1")  # warm
text = (SQL / "2_backfill.sql").read_text()
body = text.split("BEGIN;", 1)[1].rsplit("COMMIT;", 1)[0]
kc.execute("BEGIN;"); kc.execute(body.split("WITH todo", 1)[0]); kc.execute("WITH todo" + body.split("WITH todo", 1)[1])
inserted = kc.fetchone()[0]; kc.execute("COMMIT;"); k.close()
print("inserted", inserted); assert inserted == 22
v = run("3_verify.sql"); print("verify last", v)
assert q("SELECT COUNT(*) FROM sylvex_accounts WHERE origin='telegram' AND active_telegram_id=ANY(ARRAY[%s])" % ",".join(map(str, olds)))[0][0] == 22
m = q("""SELECT COUNT(*) FROM users u WHERE u.telegram_id>0 AND u.telegram_id<900000000000
         AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id=u.telegram_id)
         AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id=u.telegram_id AND a.origin='telegram')""")[0][0]
assert m == 0, m
after = {r[0]: r for r in q("SELECT account_id, active_telegram_id, origin, created_at FROM sylvex_accounts")}
assert all(after[r[0]] == r for r in before), "an existing row changed"
assert after[existing][1] == 7000000900
assert q("SELECT COUNT(*) FROM sylvex_accounts WHERE active_telegram_id=900000000123")[0][0] == 0
assert q("SELECT (SELECT array_agg(balance ORDER BY telegram_id) FROM users), (SELECT COUNT(*) FROM purchases), (SELECT COUNT(*) FROM subscriptions)") == money
tc = q("SELECT created_at FROM sylvex_accounts WHERE active_telegram_id=7772859187")[0][0]
assert str(tc) == "2026-10-21 11:45:24", tc
junk = q("SELECT created_at::date = NOW()::date FROM sylvex_accounts WHERE active_telegram_id=7000000103")[0][0]  # '' -> NOW()
assert junk is True
ids = q("SELECT account_id::text FROM sylvex_accounts WHERE origin='telegram' AND active_telegram_id=7772859187")[0][0]
assert ids[2:6] == "0626" and ids[6:8] == "99", ids
# erasure intake now finds the test account
cur = conn_factory().cursor()
from services import telegram_erasure as tge
acc, tid = tge.check_scope(cur, 7772859187); print("check_scope ok", acc, tid)
cur.connection.rollback(); cur.connection.close()
# rerun is a no-op
k = conn_factory(); k.autocommit = True; kc = k.cursor(); kc.execute("BEGIN;"); kc.execute("WITH todo" + body.split("WITH todo", 1)[1])
assert kc.fetchone()[0] == 0; kc.execute("COMMIT;"); k.close()
with psycopg2.connect(DSN) as c, c.cursor() as cur2:
    cur2.execute(f'DROP SCHEMA "{schema}" CASCADE')
print("ALL OK")
