"""B09 erasure load test. ISOLATED database and in-memory storage only.

Builds a synthetic schema (the regression-test tables plus Production-like
indexes), seeds background users and N accounts with G generations each,
accepts N confirmed deletions at once and runs W simulated API instances
(process_pending loops) while registrations, generations and ordinary API
writes run in parallel. Reports per-request time, Postgres CPU/memory,
lock waits, errors and a correctness check.

Refuses to run unless the DSN host is local and the database name contains
"erasure_load_test". No real account, R2 object or payment is touched.

  python tools/erasure_load_test.py --dsn postgresql://u:p@sx001c3-postgres:5432/erasure_load_test_x \
      --accounts 5 --generations 500 --instances 2 --deadline 900
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

MEDIA = "https://media.example.invalid/api/public/storage/"
SUBJECT_ACCOUNT0, SUBJECT_UID0 = 110626030000, 900000100000
BACKGROUND_ACCOUNT0, BACKGROUND_UID0 = 110626500000, 900000500000


def refuse_unless_isolated(dsn):
    parsed = urllib.parse.urlparse(dsn)
    if parsed.hostname not in ("127.0.0.1", "localhost", "sx001c3-postgres") or "erasure_load_test" not in parsed.path:
        raise SystemExit("refusing: load tests run only on a local database named *erasure_load_test*")


class Storage:
    """Thread-safe in-memory object store with R2-like latency."""

    def __init__(self, keys, latency):
        self.objects, self.latency, self.lock = set(keys), latency, threading.Lock()
        self.deletes = 0

    def key_from_url(self, value):
        return value[len(MEDIA):].split("?", 1)[0] if value.startswith(MEDIA) else ""

    def delete(self, key):
        time.sleep(self.latency)
        with self.lock:
            self.objects.discard(key); self.deletes += 1

    def absent(self, key):
        time.sleep(self.latency)
        with self.lock:
            return key not in self.objects


class Stripe:
    def __init__(self):
        self.calls, self.lock = 0, threading.Lock()

    def request(self, method, path, params=None, idempotency_key=None):
        with self.lock:
            self.calls += 1
        return {"id": path.rsplit("/", 1)[-1], "status": "canceled"}


SCHEMA_SQL = """
CREATE TABLE users(telegram_id BIGINT PRIMARY KEY,username TEXT,first_name TEXT,balance INTEGER,subscription TEXT);
CREATE TABLE sylvex_accounts(account_id BIGINT PRIMARY KEY,active_telegram_id BIGINT,storage_telegram_id BIGINT,origin TEXT,
    merged_telegram_id BIGINT,merged_into_account_id BIGINT,merged_at TIMESTAMP,session_generation INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE account_emails(account_id BIGINT PRIMARY KEY,email TEXT,password_hash TEXT);
CREATE TABLE prostudio_messages(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,conversation_id TEXT,prompt TEXT,image_url TEXT,
    metadata_json JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX idx_msgs_owner ON prostudio_messages(telegram_id,conversation_id,created_at DESC);
CREATE TABLE prostudio_resources(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,photos_json TEXT);
CREATE TABLE prostudio_generation_jobs(id TEXT PRIMARY KEY,telegram_id BIGINT,mode TEXT,status TEXT,cost INTEGER,
    prompt TEXT,request_json JSONB,result_json JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX idx_jobs_owner ON prostudio_generation_jobs(telegram_id,mode,updated_at DESC);
CREATE TABLE prostudio_media_outbox(job_id TEXT PRIMARY KEY REFERENCES prostudio_generation_jobs(id),status TEXT);
CREATE TABLE generation_reservations(generation_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT,credits INTEGER);
CREATE TABLE purchases(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,credits INTEGER,amount INTEGER);
CREATE TABLE payment_inbox(charge_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT);
CREATE TABLE sylvex_storage_objects(object_key TEXT PRIMARY KEY,file_url TEXT);
CREATE TABLE stripe_subscriptions(subscription_id TEXT PRIMARY KEY,telegram_id BIGINT,status TEXT);
CREATE INDEX idx_stripe_subs_owner ON stripe_subscriptions(telegram_id);
CREATE TABLE community_posts(id BIGSERIAL PRIMARY KEY,telegram_id BIGINT,body TEXT,media_url TEXT);
"""


def inline_image(kb):
    return "data:image/png;base64," + base64.b64encode(os.urandom(kb * 768)).decode()


def seed(cur, args, rnd):
    cur.execute(SCHEMA_SQL)
    keys, shared, subject_keys = [], set(), {}
    users, accounts, emails, jobs, msgs, outbox, posts, subs, objects = [], [], [], [], [], [], [], [], []
    # Background population: other users, their work and community posts.
    for b in range(args.background_users):
        uid, acc = BACKGROUND_UID0 + b, BACKGROUND_ACCOUNT0 + b
        users.append((uid, "bg%d" % b, "Background", 1000, "pro"))
        accounts.append((acc, uid, uid, "website"))
        emails.append((acc, "bg%d@example.invalid" % b, "fake-hash"))
        for j in range(args.background_jobs):
            ref, out = "generated/references/bg-%d-%d-%s.png" % (b, j, uuid4().hex[:8]), "generated/images/bg-%d-%d-%s.png" % (b, j, uuid4().hex[:8])
            keys += [ref, out]
            request = {"prompt": "background prompt %d" % j, "references": [MEDIA + ref]}
            if rnd.random() < args.inline_share:
                request["inline"] = inline_image(args.inline_kb)
            jid = "bg-%d-%d" % (b, j)
            jobs.append((jid, uid, "image", "completed", 0, "bg", json.dumps(request), json.dumps({"images": [MEDIA + out]})))
            msgs.append((uid, "c%d" % b, "bg message", MEDIA + out, json.dumps({"job": jid})))
            if j % 10 == 0:
                outbox.append((jid, "delivered"))
        posts.append((uid, "post by bg%d" % b, MEDIA + keys[-1]))
    # Accounts that confirm deletion: G generations each (reference upload +
    # result), half of them legacy (no recorded owner, account older than the
    # ownership start), 1% of results also referenced by another user.
    for s in range(args.accounts):
        uid, acc = SUBJECT_UID0 + s, SUBJECT_ACCOUNT0 + s
        users.append((uid, "s%d" % s, "Subject", 5408, "pro"))
        accounts.append((acc, uid, uid, "website"))
        emails.append((acc, "s%d@example.invalid" % s, "fake-hash"))
        subs.append(("sub_s%d" % s, uid, "active"))
        own = subject_keys.setdefault(uid, [])
        for g in range(args.generations):
            ref, out = "generated/references/s-%d-%d-%s.png" % (s, g, uuid4().hex[:8]), "generated/images/s-%d-%d-%s.png" % (s, g, uuid4().hex[:8])
            own += [ref, out]; keys += [ref, out]
            request = {"prompt": "subject prompt %d" % g, "references": [MEDIA + ref]}
            if rnd.random() < args.inline_share:
                request["inline"] = inline_image(args.inline_kb)
            jid = "s-%d-%d" % (s, g)
            jobs.append((jid, uid, "image", "completed", 0, "subject", json.dumps(request), json.dumps({"images": [MEDIA + out]})))
            msgs.append((uid, "s%d" % s, "subject message", MEDIA + out, json.dumps({"job": jid})))
            if rnd.random() < 0.01:
                shared.add(out)
                other = BACKGROUND_UID0 + rnd.randrange(args.background_users)
                msgs.append((other, "remix", "remix of a public image", MEDIA + out, json.dumps({})))
    objects = [(k, MEDIA + k) for k in keys]
    execute_values(cur, "INSERT INTO users VALUES %s", users, page_size=1000)
    execute_values(cur, "INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin) VALUES %s", accounts, page_size=1000)
    execute_values(cur, "INSERT INTO account_emails VALUES %s", emails, page_size=1000)
    execute_values(cur, "INSERT INTO prostudio_generation_jobs(id,telegram_id,mode,status,cost,prompt,request_json,result_json) VALUES %s",
                   jobs, page_size=200)
    execute_values(cur, "INSERT INTO prostudio_messages(telegram_id,conversation_id,prompt,image_url,metadata_json) VALUES %s", msgs, page_size=1000)
    execute_values(cur, "INSERT INTO prostudio_media_outbox VALUES %s", outbox, page_size=1000)
    execute_values(cur, "INSERT INTO community_posts(telegram_id,body,media_url) VALUES %s", posts, page_size=1000)
    execute_values(cur, "INSERT INTO stripe_subscriptions VALUES %s", subs, page_size=1000)
    execute_values(cur, "INSERT INTO sylvex_storage_objects VALUES %s", objects, page_size=2000)
    return keys, shared, subject_keys


class Sampler(threading.Thread):
    def __init__(self, connect, interval=0.5):
        super().__init__(daemon=True)
        self.connect, self.interval, self.stop = connect, interval, threading.Event()
        self.cpu, self.mem, self.lock_waits, self.locks_held, self.active = [], [], [], [], []

    def run(self):
        conn = self.connect(); conn.autocommit = True
        procs = {}
        while not self.stop.is_set():
            cpu = rss = 0.0
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"] != "postgres":
                    continue
                try:
                    if proc.pid not in procs:
                        procs[proc.pid] = proc; proc.cpu_percent(None)
                    cpu += procs[proc.pid].cpu_percent(None)
                    rss += proc.memory_full_info().uss
                except psutil.Error:
                    pass
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FILTER (WHERE NOT granted), COUNT(*) FROM pg_locks")
                waiting, held = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE state='active' AND backend_type='client backend'")
                active = cur.fetchone()[0]
            self.cpu.append(cpu); self.mem.append(rss / 2**20); self.lock_waits.append(waiting)
            self.locks_held.append(held); self.active.append(active)
            self.stop.wait(self.interval)
        conn.close()

    def summary(self):
        def stats(values):
            values = sorted(values) or [0]
            return {"avg": round(sum(values) / len(values), 1), "p95": round(values[int(len(values) * .95) - 1 if len(values) > 1 else 0], 1),
                    "max": round(values[-1], 1)}
        return {"postgres_cpu_percent": stats(self.cpu), "postgres_uss_mb": stats(self.mem),
                "lock_waits": stats(self.lock_waits), "locks_held": stats(self.locks_held),
                "active_backends": stats(self.active), "samples": len(self.cpu)}


class UserLoad(threading.Thread):
    """Registrations, generations and ordinary writes by other users."""

    def __init__(self, kind, connect, args, stop):
        super().__init__(daemon=True)
        self.kind, self.connect, self.args, self.stop = kind, connect, args, stop
        self.latencies, self.errors = [], []

    def run(self):
        rnd = random.Random(hash(self.kind) & 0xffff)
        n = 0
        while not self.stop.is_set():
            n += 1
            started = time.monotonic()
            try:
                with self.connect() as conn, conn.cursor() as cur:
                    uid = BACKGROUND_UID0 + rnd.randrange(self.args.background_users)
                    if self.kind == "registration":
                        acc, new_uid = 110627000000 + rnd.randrange(10**6), 900010000000 + rnd.randrange(10**8)
                        cur.execute("INSERT INTO users VALUES(%s,NULL,NULL,0,'free') ON CONFLICT DO NOTHING", (new_uid,))
                        cur.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin) "
                                    "VALUES(%s,%s,%s,'website') ON CONFLICT DO NOTHING", (acc, new_uid, new_uid))
                        cur.execute("INSERT INTO account_emails VALUES(%s,%s,'h') ON CONFLICT DO NOTHING", (acc, "n%d@example.invalid" % acc))
                    elif self.kind == "generation":
                        jid = "load-%s" % uuid4().hex
                        cur.execute("INSERT INTO generation_reservations VALUES(%s,%s,'reserved',10)", (jid, uid))
                        cur.execute("INSERT INTO prostudio_generation_jobs(id,telegram_id,mode,status,cost,prompt,request_json,result_json) "
                                    "VALUES(%s,%s,'image','queued',10,'load',%s,'{}')", (jid, uid, json.dumps({"references": []})))
                        cur.execute("UPDATE prostudio_generation_jobs SET status='completed',result_json=%s WHERE id=%s",
                                    (json.dumps({"images": [MEDIA + "generated/images/load-%s.png" % jid]}), jid))
                        cur.execute("UPDATE generation_reservations SET status='settled' WHERE generation_id=%s", (jid,))
                    else:
                        cur.execute("SELECT id FROM prostudio_generation_jobs WHERE telegram_id=%s AND mode='image' "
                                    "ORDER BY updated_at DESC LIMIT 20", (uid,))
                        rows = cur.fetchall()
                        cur.execute("INSERT INTO prostudio_messages(telegram_id,conversation_id,prompt,image_url) VALUES(%s,'api','hi',%s)",
                                    (uid, MEDIA + "generated/images/api-%s.png" % uuid4().hex))
                        if rows:
                            cur.execute("UPDATE prostudio_generation_jobs SET updated_at=NOW() WHERE id=%s", (rows[0][0],))
            except Exception as exc:  # noqa: BLE001 - every failure is a finding
                self.errors.append(type(exc).__name__ + ": " + str(exc).splitlines()[0][:160])
            self.latencies.append((time.monotonic() - started) * 1000)
            self.stop.wait(0.02)

    def summary(self):
        values = sorted(self.latencies) or [0]
        pick = lambda q: round(values[min(len(values) - 1, int(len(values) * q))], 1)
        return {"operations": len(self.latencies), "errors": len(self.errors), "error_samples": sorted(set(self.errors))[:5],
                "p50_ms": pick(.5), "p95_ms": pick(.95), "p99_ms": pick(.99), "max_ms": round(values[-1], 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--accounts", type=int, default=2)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--background-users", type=int, default=200)
    parser.add_argument("--background-jobs", type=int, default=50)
    parser.add_argument("--inline-share", type=float, default=0.03)
    parser.add_argument("--inline-kb", type=int, default=150)
    parser.add_argument("--instances", type=int, default=2, help="simulated API instances running the processor")
    parser.add_argument("--storage-latency-ms", type=float, default=5)
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--reference-index", action="store_true", help="install and backfill the reference index first")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--seed", type=int, default=9)
    args = parser.parse_args()
    refuse_unless_isolated(args.dsn)

    from services import account_erasure as erasure, account_erasure_guards as guards, account_erasure_runner as runner
    schema = "erasure_load_" + uuid4().hex[:10]
    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute('CREATE SCHEMA "%s"' % schema)

    def connect(*_a, **_k):
        return psycopg2.connect(args.dsn, options="-c search_path=" + schema)

    erasure.db_connect = connect
    journal_dir = Path(tempfile.mkdtemp(prefix="erasure-load-journal-")) / "ledger"
    os.environ["SYLVEX_ERASURE_JOURNAL_DIR"] = str(journal_dir)
    os.environ["SYLVEX_ERASURE_ACCEPTING"] = "1"
    journal = erasure.Journal(journal_dir)
    rnd = random.Random(args.seed)
    report = {"args": vars(args) | {"dsn": "<isolated>"}, "schema": schema}
    try:
        started = time.monotonic()
        with connect() as conn, conn.cursor() as cur:
            keys, shared, subject_keys = seed(cur, args, rnd)
            # Half of the accounts predate ownership recording; the rest have
            # an ownership record for every key (written by current code).
            erasure.ensure_schema(cur)
            guards.install(cur)
            for s, (uid, own) in enumerate(sorted(subject_keys.items())):
                if s % 2:
                    execute_values(cur, "INSERT INTO sylvex_storage_ownership(object_key,owner_key,source_kind) VALUES %s",
                                   [(k, uid, "load") for k in own], page_size=2000)
                else:
                    cur.execute("UPDATE sylvex_accounts SET created_at='2020-01-01' WHERE active_telegram_id=%s", (uid,))
            cur.execute("ANALYZE")
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())),"
                        "(SELECT COUNT(*) FROM prostudio_generation_jobs),(SELECT COUNT(*) FROM prostudio_messages),"
                        "pg_size_pretty(pg_total_relation_size('prostudio_generation_jobs'))")
            size, jobs, msgs, job_size = cur.fetchone()
        report["dataset"] = {"database_size": size, "jobs": jobs, "messages": msgs, "jobs_table": job_size,
                             "objects": len(keys), "subject_keys": sum(map(len, subject_keys.values())),
                             "shared_subject_keys": len(shared), "seed_s": round(time.monotonic() - started, 1)}
        if args.reference_index:
            began = time.monotonic()
            with connect() as conn, conn.cursor() as cur:
                guards.install_reference_index(cur)
            done = guards.backfill_reference_index("synthetic", batch=500, wait_for_older=False)
            report["reference_index"] = {"backfill_s": round(time.monotonic() - began, 1), **done}
        store, stripe = Storage(keys, args.storage_latency_ms / 1000), Stripe()

        # In-flight counter: how many heavy passes run at the same moment.
        inflight = {"now": 0, "max": 0}
        gate = threading.Lock()
        original = runner.process_request

        def counted(*a, **k):
            with gate:
                inflight["now"] += 1; inflight["max"] = max(inflight["max"], inflight["now"])
            try:
                return original(*a, **k)
            finally:
                with gate:
                    inflight["now"] -= 1
        runner.process_request = counted

        sampler = Sampler(connect); sampler.start()
        stop_users = threading.Event()
        load = [UserLoad(kind, connect, args, stop_users) for kind in ("registration", "generation", "api", "api")]
        for worker in load:
            worker.start()
        time.sleep(3)  # baseline latency of user traffic before deletions
        accepted_at = time.monotonic()
        with connect() as conn, conn.cursor() as cur:
            ids = [erasure.accept_confirmed_request(cur, SUBJECT_ACCOUNT0 + s, journal=journal)["request_id"] for s in range(args.accounts)]
        errors, finished = [], {}
        stop_workers = threading.Event()

        def instance():
            while not stop_workers.is_set():
                try:
                    results = runner.process_pending("synthetic", storage=store, journal=journal, stripe=stripe, limit=10)
                except Exception as exc:  # noqa: BLE001
                    errors.append(type(exc).__name__ + ": " + str(exc)[:160]); results = []
                for item in results:
                    if item.get("hold_code") and item["hold_code"] not in ("media_remaining", "LockNotAvailable"):
                        errors.append("hold:" + item["hold_code"])
                if not results:
                    stop_workers.wait(0.5)
        workers = [threading.Thread(target=instance, daemon=True) for _ in range(args.instances)]
        for worker in workers:
            worker.start()
        progress = []
        while time.monotonic() - accepted_at < args.deadline:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT request_id::text,state FROM sylvex_erasure_requests")
                states = dict(cur.fetchall())
            elapsed = time.monotonic() - accepted_at
            for rid, state in states.items():
                if state == "complete" and rid not in finished:
                    finished[rid] = round(elapsed, 1)
            progress.append((round(elapsed, 1), store.deletes, len(finished)))
            if len(finished) == len(ids):
                break
            time.sleep(1)
        stop_workers.set()
        for worker in workers:
            worker.join(timeout=120)
        time.sleep(2)
        stop_users.set()
        for worker in load:
            worker.join(timeout=30)
        sampler.stop.set(); sampler.join(timeout=10)

        # Correctness: deleted exactly the confirming accounts' unshared keys.
        all_subject = {k for own in subject_keys.values() for k in own}
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE telegram_id>=%s AND telegram_id<%s",
                        (SUBJECT_UID0, SUBJECT_UID0 + args.accounts))
            subject_jobs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM prostudio_generation_jobs WHERE id LIKE 'bg-%%'")
            background_jobs = cur.fetchone()[0]
            cur.execute("SELECT balance FROM users WHERE telegram_id>=%s AND telegram_id<%s", (SUBJECT_UID0, SUBJECT_UID0 + args.accounts))
            balances = [row[0] for row in cur.fetchall()]
        complete = len(finished) == len(ids)
        remaining_subject = (all_subject - shared) & store.objects
        report["result"] = {
            "requests": len(ids), "completed": len(finished), "all_complete": complete,
            "per_request_s": sorted(finished.values()),
            "total_s": max(finished.values()) if complete else None,
            "objects_deleted": store.deletes and len(all_subject - store.objects),
            "keys_per_s": round(len(all_subject - store.objects) / max(1e-9, progress[-1][0]), 1) if progress else 0,
            "max_parallel_passes": inflight["max"], "processor_errors": len(errors), "processor_error_samples": sorted(set(errors))[:8],
        }
        report["correctness"] = {
            "shared_keys_kept": shared <= store.objects,
            "background_objects_kept": (set(keys) - all_subject) <= store.objects,
            "background_jobs_kept": background_jobs == args.background_users * args.background_jobs,
            "unshared_subject_keys_left": len(remaining_subject),
            "subject_jobs_left": subject_jobs, "subject_balances_zero": all(b == 0 for b in balances) if complete else None,
            "stripe_cancel_calls": stripe.calls,
        }
        report["postgres"] = sampler.summary()
        report["user_traffic"] = {worker.kind + "#" + str(i): worker.summary() for i, worker in enumerate(load)}
        report["progress_tail"] = progress[-3:]
    finally:
        if not args.keep:
            with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
                cur.execute('DROP SCHEMA "%s" CASCADE' % schema)
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
