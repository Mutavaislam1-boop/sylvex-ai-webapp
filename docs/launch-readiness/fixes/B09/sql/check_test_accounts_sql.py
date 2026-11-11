import sys, uuid, pathlib, psycopg2
sys.path.insert(0, sys.argv[1]); SQL = pathlib.Path(sys.argv[2])
DSN = "postgresql://sylvex:sylvex@sx001c3-postgres:5432/policy_erasure_test_local"
schema = "b19_" + uuid.uuid4().hex[:8]
with psycopg2.connect(DSN) as c, c.cursor() as cur: cur.execute(f'CREATE SCHEMA "{schema}"')
cf = lambda *a, **k: psycopg2.connect(DSN, options=f"-c search_path={schema}")
from services import account_identity as ai, account_erasure as er, account_erasure_guards as guards
ai.db_connect = cf; er.db_connect = cf
k = cf(); cur = k.cursor()
cur.execute("CREATE TABLE users(telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT, balance INT DEFAULT 0, subscription TEXT, created_at TEXT)")
cur.execute("CREATE TABLE user_credit_wallets(telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE, purchased_credits INT)")
cur.execute("CREATE TABLE purchases(id SERIAL, telegram_id BIGINT)")
tests = [12345, 123456789, 900000001]; others = [7772859187] + [7000000200 + i for i in range(18)]
for t in tests + others: cur.execute("INSERT INTO users(telegram_id, balance, created_at) VALUES(%s,%s,'2026-10-02 09:00:00')", (t, 317 if t == 7772859187 else 3))
cur.execute("INSERT INTO user_credit_wallets VALUES (12345,0),(7772859187,10)"); cur.execute("INSERT INTO purchases(telegram_id) VALUES (7772859187)")
k.commit(); ai.ensure_account_tables("x", connect=cf)
k = cf(); cur = k.cursor(); er.ensure_schema(cur); guards.install(cur); k.commit()
def run_file(name, fetch=True):
    k = cf(); k.autocommit = True; c = k.cursor(); c.execute((SQL / name).read_text()); r = None
    try: r = c.fetchall()
    except psycopg2.ProgrammingError: pass
    k.close(); return r
def q(s):
    k = cf(); c = k.cursor(); c.execute(s); r = c.fetchall(); k.close(); return r
print("preview", run_file("1_preview.sql")[0][:2])
body = (SQL / "5_backfill_19.sql").read_text().split("BEGIN;",1)[1].rsplit("COMMIT;",1)[0]
k = cf(); k.autocommit = True; c = k.cursor(); c.execute("BEGIN"); c.execute(body.split("WITH todo",1)[0]); c.execute("WITH todo"+body.split("WITH todo",1)[1])
n = c.fetchone()[0]; c.execute("COMMIT"); k.close(); print("inserted", n); assert n == 19
assert q("SELECT COUNT(*) FROM sylvex_accounts WHERE active_telegram_id IN (12345,123456789,900000001)")[0][0] == 0
inv = run_file("4_test_accounts_inventory.sql"); print("inventory", [r for r in inv if r[3]])
run_file("6_delete_test_accounts.sql")
v = run_file("7_verify_all.sql")[0]; print("verify", v)
assert v[0] == 0 and v[1] == 0 and v[2] == 1 and str(v[3]) == "2026-10-02 09:00:00"
assert q("SELECT COUNT(*) FROM user_credit_wallets WHERE telegram_id=12345")[0][0] == 0
assert q("SELECT COUNT(*) FROM user_credit_wallets WHERE telegram_id=7772859187")[0][0] == 1
assert q("SELECT balance FROM users WHERE telegram_id=7772859187")[0][0] == 317 and q("SELECT COUNT(*) FROM purchases")[0][0] == 1
# guard: a test ID with a SYLVEX identity must abort the whole delete
k = cf(); c = k.cursor(); c.execute("INSERT INTO users(telegram_id) VALUES (12345)"); k.commit()
c.execute("SELECT sylvex_ensure_telegram_account(12345)"); k.commit(); k.close()
try:
    run_file("6_delete_test_accounts.sql"); raise SystemExit("guard did not fire")
except psycopg2.Error as e: print("guard ok:", str(e).splitlines()[0])
assert q("SELECT COUNT(*) FROM users WHERE telegram_id=12345")[0][0] == 1
with psycopg2.connect(DSN) as c2, c2.cursor() as cc: cc.execute(f'DROP SCHEMA "{schema}" CASCADE')
print("ALL OK")
