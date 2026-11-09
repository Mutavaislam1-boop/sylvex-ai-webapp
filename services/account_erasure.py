"""Confirmed account erasure, distinct from login removal.

This module never cancels a payment, refunds credits, calls a model or guesses
ownership from a filename. Durable receipts and an external replay journal
precede destructive work. Unresolved scope, work or media ownership is a hold.
"""
from __future__ import annotations

from contextlib import contextmanager
import contextvars
import fcntl
from functools import wraps
import inspect
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import re
from urllib.parse import quote
from uuid import UUID, uuid4

from db_pool import db_connect
from services import account_erasure_policy as policy

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def ident(value):
    if not IDENTIFIER.fullmatch(value):
        raise ErasureError("erasure_schema_requires_review")
    return '"' + value + '"'

WEB_STORAGE_FLOOR = 900000000000
SCHEMA_VERSION = 1
_storage_cursor = contextvars.ContextVar("sylvex_erasure_storage_cursor", default=None)
_media_job = contextvars.ContextVar("sylvex_erasure_media_job", default=None)
REQUEST_COLUMNS = (
    "request_id, account_id, subject_key, ecosystem, state, requested_at, "
    "completed_at, hold_code, updated_at"
)


class ErasureError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Journal:
    """Restricted, fsynced records outside the database being restored.

    The configured directory must live on durable storage in production. The
    restore entrypoint must replay this directory before serving any traffic.
    Records contain identifiers and a decision, never prompts, email or media.
    """

    def __init__(self, directory=None):
        value = directory or os.getenv("SYLVEX_ERASURE_JOURNAL_DIR", "")
        if not value or not Path(value).is_absolute():
            raise ErasureError("erasure_journal_not_configured", 503)
        self.path = Path(value)
        if self.path.is_symlink():
            raise ErasureError("erasure_journal_unsafe", 503)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ErasureError("erasure_journal_unsafe", 503)

    @staticmethod
    def _validate(record):
        allowed = {"version", "request_id", "account_id", "subject_key", "ecosystem",
                   "requested_at", "completed_at"}
        optional = {"decisions_sha256", "decisions_count"}
        inventory = {"inventory_reviewed_at", "inventory_evidence_sha256"}
        if not allowed <= set(record) or set(record) - allowed - optional - inventory or record["version"] != SCHEMA_VERSION:
            raise ErasureError("erasure_journal_invalid", 503)
        if optional & set(record):
            if not optional <= set(record) or type(record["decisions_count"]) is not int or record["decisions_count"] < 0:
                raise ErasureError("erasure_journal_invalid", 503)
            if not re.fullmatch(r"[a-f0-9]{64}",record["decisions_sha256"]):
                raise ErasureError("erasure_journal_invalid", 503)
        if inventory & set(record):
            if not inventory <= set(record) or not re.fullmatch(r"[a-f0-9]{64}",record["inventory_evidence_sha256"]):
                raise ErasureError("erasure_journal_invalid",503)
            datetime.fromisoformat(record["inventory_reviewed_at"])
        UUID(str(record["request_id"]))
        if type(record["account_id"]) is not int or record["account_id"] <= 0:
            raise ErasureError("erasure_journal_invalid", 503)
        if record["subject_key"] is not None and (
            type(record["subject_key"]) is not int or record["subject_key"] <= 0
        ):
            raise ErasureError("erasure_journal_invalid", 503)
        if record["ecosystem"] not in ("website", "telegram"):
            raise ErasureError("erasure_journal_invalid", 503)
        datetime.fromisoformat(record["requested_at"])
        if record["completed_at"]:
            datetime.fromisoformat(record["completed_at"])

    @contextmanager
    def _lock(self, *, exclusive):
        fd = os.open(self.path/".journal-lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

    def read(self, request_id):
        with self._lock(exclusive=False):
            return self._read_record(request_id)

    def _read_record(self, request_id, *, check_decisions=True):
        target = self.path / (str(UUID(str(request_id))) + ".json")
        try:
            fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                raw = handle.read(4097)
            if len(raw) > 4096 or target.stat().st_mode & 0o077:
                raise ErasureError("erasure_journal_invalid", 503)
            wrapper = json.loads(raw)
            record = wrapper["record"]
            expected = hashlib.sha256(self._bytes(record)).hexdigest()
            if wrapper["sha256"] != expected:
                raise ErasureError("erasure_journal_invalid", 503)
            self._validate(record)
            if check_decisions:
                decisions = self._decisions(request_id)
                if decisions["count"] != record.get("decisions_count",0) or (
                    "decisions_sha256" in record and decisions["sha256"] != record["decisions_sha256"]
                ):
                    raise ErasureError("erasure_journal_invalid",503)
            return record
        except FileNotFoundError:
            return None
        except ErasureError:
            raise
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise ErasureError("erasure_journal_invalid", 503) from exc

    @staticmethod
    def _bytes(record):
        return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()

    def write(self, record):
        with self._lock(exclusive=True):
            self._write_record(record)

    def _write_record(self, record):
        self._validate(record)
        request_id = str(UUID(str(record["request_id"])))
        prior = self._read_record(request_id,check_decisions=False)
        if prior and any(prior[k] != record[k] for k in (
            "request_id", "account_id", "subject_key", "ecosystem", "requested_at"
        )):
            raise ErasureError("erasure_journal_identity_changed", 503)
        if prior and prior["completed_at"] and not record["completed_at"]:
            raise ErasureError("erasure_journal_decision_reversed", 503)
        wrapper = {"record": record, "sha256": hashlib.sha256(self._bytes(record)).hexdigest()}
        target = self.path / (request_id + ".json")
        temporary = self.path / ("pending-" + uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(wrapper, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            parent = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _decisions(self, request_id, *, prefix_count=None):
        target = self.path/(str(UUID(str(request_id)))+".decisions")
        digest = hashlib.sha256()
        result, count, prefix_sha256 = {}, 0, digest.hexdigest() if prefix_count == 0 else None
        try:
            fd = os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
        except FileNotFoundError:
            return {"objects":result,"sha256":digest.hexdigest(),"count":0,"prefix_sha256":prefix_sha256}
        with os.fdopen(fd,"rb") as handle:
            if stat.S_IMODE(os.fstat(handle.fileno()).st_mode)&0o077:
                raise ErasureError("erasure_journal_invalid",503)
            for line in handle:
                if len(line)>1024 or not line.endswith(b"\n"):
                    raise ErasureError("erasure_journal_invalid",503)
                try:
                    item=json.loads(line)
                    if set(item)!={"key_hash","decision"} or not re.fullmatch(r"[a-f0-9]{64}",item["key_hash"]) or item["decision"] not in ("delete","shared"):
                        raise ValueError()
                    previous=result.get(item["key_hash"])
                    if previous and previous!=item["decision"]:
                        raise ValueError()
                except (ValueError,TypeError,KeyError) as exc:
                    raise ErasureError("erasure_journal_invalid",503) from exc
                result[item["key_hash"]]=item["decision"]
                digest.update(line);count+=1
                if count == prefix_count:
                    prefix_sha256 = digest.hexdigest()
        return {"objects":result,"sha256":digest.hexdigest(),"count":count,"prefix_sha256":prefix_sha256}

    def _recover(self, request_id):
        """Recover only a valid fsynced append after its older root checkpoint.

        An incomplete line, missing prefix or conflicting decision remains a
        hard hold. The decision is durable before destructive I/O, so keeping
        a valid appended decision is safer than truncating it after a crash.
        Caller owns the exclusive journal lock.
        """
        record = self._read_record(request_id, check_decisions=False)
        if record is None:
            return None
        count = record.get("decisions_count", 0)
        prior_digest = record.get("decisions_sha256", hashlib.sha256(b"").hexdigest())
        summary = self._decisions(request_id, prefix_count=count)
        if summary["count"] < count or summary["prefix_sha256"] != prior_digest:
            raise ErasureError("erasure_journal_invalid", 503)
        if summary["count"] != count:
            record.update(decisions_count=summary["count"], decisions_sha256=summary["sha256"])
            self._write_record(record)
        return record

    def recover(self, request_id):
        with self._lock(exclusive=True):
            return self._recover(request_id)

    def decisions(self, request_id):
        with self._lock(exclusive=False):
            self._read_record(request_id)
            return self._decisions(request_id)["objects"]

    def append_decision(self, request_id, key, decision):
        if decision not in ("delete","shared"):
            raise ErasureError("erasure_journal_invalid",503)
        key_hash=hashlib.sha256(key.encode()).hexdigest()
        with self._lock(exclusive=True):
            record=self._recover(request_id)
            if record is None:
                raise ErasureError("erasure_journal_missing_or_mismatched",503)
            previous=self._decisions(request_id)["objects"].get(key_hash)
            if previous:
                if previous!=decision:
                    raise ErasureError("erasure_replay_scope_changed")
                return
            target=self.path/(str(UUID(str(request_id)))+".decisions")
            fd=os.open(target,os.O_CREAT|os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW,0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode)&0o077:
                    raise ErasureError("erasure_journal_unsafe",503)
                line=json.dumps({"key_hash":key_hash,"decision":decision},sort_keys=True,separators=(",",":")).encode()+b"\n"
                if os.write(fd,line)!=len(line):
                    raise ErasureError("erasure_journal_write_incomplete",503)
                os.fsync(fd)
            finally:
                os.close(fd)
            summary=self._decisions(request_id)
            record.update(decisions_sha256=summary["sha256"],decisions_count=summary["count"])
            self._write_record(record)

    def records(self):
        for file in sorted(self.path.glob("*.json")):
            record = self.recover(file.stem)
            if record is not None:
                yield record


def ensure_schema(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS sylvex_storage_objects (
        object_key TEXT PRIMARY KEY, file_url TEXT NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
        size_bytes BIGINT NOT NULL DEFAULT 0, storage_backend TEXT NOT NULL DEFAULT 'r2',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sylvex_direct_uploads (
        object_key TEXT PRIMARY KEY, owner_key BIGINT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ,
        reconciled_at TIMESTAMPTZ, reviewed_by TEXT NOT NULL DEFAULT '',
        evidence_ref TEXT NOT NULL DEFAULT '')""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sylvex_erasure_requests (
            request_id UUID PRIMARY KEY,
            account_id BIGINT UNIQUE NOT NULL,
            subject_key BIGINT,
            ecosystem TEXT NOT NULL CHECK (ecosystem IN ('website','telegram')),
            state TEXT NOT NULL CHECK (state IN
                ('queued','scope_review','waiting_work','media_review','purging','complete')),
            requested_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            hold_code TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE sylvex_erasure_requests ADD COLUMN IF NOT EXISTS telegram_caches_cleared_at TIMESTAMPTZ")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS erasure_subject_key ON sylvex_erasure_requests(subject_key) WHERE subject_key IS NOT NULL")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sylvex_erasure_media (
            request_id UUID NOT NULL REFERENCES sylvex_erasure_requests(request_id),
            object_key TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('review','owned','shared','deleting','deleted')),
            proof_kind TEXT NOT NULL DEFAULT '',
            approved_by TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(request_id,object_key)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sylvex_storage_ownership (
            object_key TEXT PRIMARY KEY,
            owner_key BIGINT NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source_kind TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sylvex_erasure_retained_rows (
            request_id UUID NOT NULL REFERENCES sylvex_erasure_requests(request_id),
            table_name TEXT NOT NULL,
            row_identity TEXT NOT NULL,
            basis TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(request_id,table_name,row_identity)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sylvex_active_operations (
            operation_id UUID PRIMARY KEY, subject_key BIGINT NOT NULL,
            generation_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','finished')),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ,
            process_id TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS erasure_media_pending ON sylvex_erasure_media(request_id,object_key) WHERE state IN ('owned','deleting')")
    cur.execute("CREATE INDEX IF NOT EXISTS erasure_media_deleted_key ON sylvex_erasure_media(object_key) WHERE state IN ('deleting','deleted')")
    cur.execute("CREATE INDEX IF NOT EXISTS erasure_active_subject ON sylvex_active_operations(subject_key,generation_id) WHERE state='active'")
    cur.execute("CREATE INDEX IF NOT EXISTS erasure_storage_owner ON sylvex_storage_ownership(owner_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS erasure_direct_owner ON sylvex_direct_uploads(owner_key) WHERE reconciled_at IS NULL")


def _row(cur, query, params=()):
    cur.execute(query, params)
    row = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], row)) if row else None


def request_row(cur, request_id, *, lock=False):
    return _row(cur, "SELECT " + REQUEST_COLUMNS +
                " FROM sylvex_erasure_requests WHERE request_id=%s" +
                (" FOR UPDATE" if lock else ""), (str(UUID(str(request_id))),))


def _subject_lock(cur, subject_key, *, shared=False):
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    cur.execute("SELECT " + function + "(61181,hashtext(%s))", (str(int(subject_key)),))


def _has_requests(cur):
    cur.execute("SELECT to_regclass('sylvex_erasure_requests')")
    return cur.fetchone()[0] is not None


def pending_account(database_url, account_id):
    """Always a live lookup: a per-worker TTL would admit revoked work."""
    if not database_url or not account_id:
        return False
    with db_connect(database_url) as conn:
        with conn.cursor() as cur:
            if not _has_requests(cur):
                return False
            cur.execute("SELECT 1 FROM sylvex_erasure_requests WHERE account_id=%s", (int(account_id),))
            return cur.fetchone() is not None


def blocked_subject(cur, subject_key):
    if not subject_key or not _has_requests(cur):
        return False
    cur.execute("SELECT 1 FROM sylvex_erasure_requests WHERE subject_key=%s", (int(subject_key),))
    return cur.fetchone() is not None


def accept_confirmed_request(cur, account_id, *, ecosystem="website", journal=None):
    """Caller must verify the current deletion confirmation BEFORE this call.

    The caller commits. The journal is durable first, so a database restore
    cannot silently undo a verified erasure decision. Legacy mixed scope is
    held for verification; it never authorizes erasing the other ecosystem.
    """
    if os.getenv("SYLVEX_ERASURE_ACCEPTING", "").lower() not in ("1","true","yes") or not enabled():
        raise ErasureError("erasure_intake_not_ready",503)
    if ecosystem == "telegram" and os.getenv("SYLVEX_ERASURE_TELEGRAM_READY", "").lower() not in ("1","true","yes"):
        raise ErasureError("erasure_telegram_client_not_ready",503)
    journal = journal or Journal()
    from services.account_erasure_guards import require_installed
    require_installed(cur,verify_coverage=True)
    cur.execute("SELECT pg_advisory_xact_lock(61180,hashtext(%s))", (str(int(account_id)),))
    cur.execute("SELECT account_id,active_telegram_id,storage_telegram_id,origin,merged_telegram_id,merged_into_account_id,merged_at "
                "FROM sylvex_accounts WHERE account_id=%s FOR UPDATE", (int(account_id),))
    row = cur.fetchone()
    if not row:
        raise ErasureError("account_not_found", 404)
    account, active, storage, origin, merged, into, merged_at = row
    existing = _row(cur, "SELECT " + REQUEST_COLUMNS + " FROM sylvex_erasure_requests WHERE account_id=%s", (int(account_id),))
    if existing:
        return receipt(existing)
    scope_ok = (origin == ecosystem and not merged and not into and not merged_at
                and active and (storage is None or int(storage) == int(active)))
    if ecosystem == "website":
        scope_ok = scope_ok and int(active or 0) >= WEB_STORAGE_FLOOR
    else:
        scope_ok = scope_ok and 0 < int(active or 0) < WEB_STORAGE_FLOOR
    subject = int(active) if scope_ok else None
    if subject:
        _subject_lock(cur, subject)
    request_id = str(uuid4())
    record = {"version": SCHEMA_VERSION, "request_id": request_id,
              "account_id": int(account), "subject_key": subject,
              "ecosystem": ecosystem, "requested_at": utc_now(), "completed_at": None}
    journal.write(record)
    state = "queued" if scope_ok else "scope_review"
    cur.execute("INSERT INTO sylvex_erasure_requests(request_id,account_id,subject_key,ecosystem,state,requested_at,hold_code) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (request_id, account, subject, ecosystem, state, record["requested_at"], "" if scope_ok else "legacy_scope_requires_review"))
    # Preserve the account and identities until the full manifest is ready.
    # Revocation is monotonic and part of this same transaction.
    cur.execute("UPDATE sylvex_accounts SET session_generation=session_generation+1 WHERE account_id=%s", (account,))
    if subject and ecosystem == "telegram":
        cur.execute("CREATE TABLE IF NOT EXISTS sylvex_tg_session_revocations (telegram_id BIGINT PRIMARY KEY,generation INTEGER NOT NULL DEFAULT 0)")
        cur.execute("INSERT INTO sylvex_tg_session_revocations(telegram_id,generation) VALUES(%s,1) "
                    "ON CONFLICT(telegram_id) DO UPDATE SET generation=sylvex_tg_session_revocations.generation+1", (subject,))
    return {"accepted": True, "complete": False, "request_id": request_id, "state": state}


def receipt(row):
    return {"accepted": True, "complete": row["state"] == "complete",
            "request_id": str(row["request_id"]), "state": row["state"]}


@contextmanager
def transaction(database_url):
    conn = db_connect(database_url)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def columns(cur):
    cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema=current_schema()")
    result = {}
    for table, column in cur.fetchall():
        result.setdefault(table, set()).add(column)
    return result


def owner_clause(table, schema, request, *, alias=None):
    owner_columns = policy.PERSONAL.get(table) or policy.REVIEW.get(table)
    if table == "prostudio_generation_jobs":
        owner_columns = ("telegram_id",)
    elif table == "site_visitors":
        owner_columns = ("account_id",)
    if not owner_columns:
        raise ErasureError("erasure_schema_requires_review")
    predicates, params = [], []
    qualifier = ident(alias)+"." if alias else ""
    for column in owner_columns:
        if column in schema.get(table, set()):
            value = request["account_id"] if column in policy.ACCOUNT_COLUMNS else request["subject_key"]
            if value is not None:
                predicates.append(qualifier + ident(column) + "::text=%s")
                params.append(str(value))
    if not predicates:
        raise ErasureError("erasure_schema_requires_review")
    return "COALESCE((" + " OR ".join(predicates) + "),FALSE)", params


def streamed_json(cur,query,params=()):
    # A named cursor bounds both libpq and Python memory. The control cursor
    # remains available for manifest/retention decisions in this transaction.
    with cur.connection.cursor(name="erasure_rows_"+uuid4().hex) as scan:
        scan.itersize=100
        scan.execute(query,params)
        for row in scan:
            yield row[0]


def owned_rows(cur, table, schema, request):
    if table not in schema:
        return
    where, params = owner_clause(table, schema, request)
    yield from streamed_json(cur,"SELECT to_jsonb(t) FROM " + ident(table) + " t WHERE " + where,params)


def _manifest_keys(cur,request,keys):
    if not keys:
        return
    cur.execute("INSERT INTO sylvex_erasure_media(request_id,object_key,state,proof_kind) "
                "SELECT %s,k,CASE WHEN o.owner_key=%s THEN 'owned' WHEN o.owner_key IS NOT NULL THEN 'shared' ELSE 'review' END," 
                "CASE WHEN o.owner_key=%s THEN 'recorded_owner' WHEN o.owner_key IS NOT NULL THEN 'other_owner' ELSE '' END "
                "FROM unnest(%s::text[]) AS k LEFT JOIN sylvex_storage_ownership o ON o.object_key=k "
                "ON CONFLICT(request_id,object_key) DO NOTHING",
                (str(request['request_id']),request['subject_key'],request['subject_key'],sorted(keys)))


def _manifest_rows(cur,request,rows,schema,storage):
    batch=[]
    for row in rows:
        batch.append(row)
        if len(batch)==100:
            _manifest_keys(cur,request,media_keys(cur,batch,schema,storage));batch=[]
    if batch:
        _manifest_keys(cur,request,media_keys(cur,batch,schema,storage))


def row_identity(row):
    # Row-level exceptions are tied to exactly the reviewed contents. A later
    # change invalidates the exception and requires a fresh decision.
    data = json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def unknown_owned_tables(schema):
    known = set(policy.PERSONAL) | set(policy.REVIEW) | policy.FINANCIAL | policy.SPECIAL | policy.SHARED_CATALOG
    return sorted(table for table, fields in schema.items()
                  if table not in known and fields & policy.OWNER_COLUMNS)


def work_in_flight(cur, schema, request):
    uid = request["subject_key"]
    if "sylvex_direct_uploads" in schema:
        cur.execute("SELECT CASE WHEN expires_at>NOW() THEN 'direct_upload_capability_active' "
                    "ELSE 'direct_upload_reconciliation_required' END FROM sylvex_direct_uploads "
                    "WHERE owner_key=%s AND reconciled_at IS NULL LIMIT 1", (uid,))
        row=cur.fetchone()
        if row:
            return row[0]
    if "sylvex_active_operations" in schema:
        cur.execute("SELECT 1 FROM sylvex_active_operations WHERE subject_key=%s AND state='active' LIMIT 1", (uid,))
        if cur.fetchone():
            return "operation_in_flight"
    if "prostudio_generation_jobs" in schema:
        cur.execute("SELECT 1 FROM prostudio_generation_jobs WHERE telegram_id=%s "
                    "AND (status IS NULL OR NOT(status=ANY(%s))) LIMIT 1", (uid, list(policy.TERMINAL_JOBS)))
        if cur.fetchone():
            return "generation_in_flight"
    if {"prostudio_generation_jobs", "prostudio_media_outbox"} <= set(schema):
        cur.execute("SELECT 1 FROM prostudio_media_outbox o JOIN prostudio_generation_jobs j ON j.id=o.job_id "
                    "WHERE j.telegram_id=%s AND (o.status IS NULL OR NOT(o.status=ANY(%s))) LIMIT 1",
                    (uid, list(policy.TERMINAL_OUTBOX)))
        if cur.fetchone():
            return "media_in_flight"
    if "generation_reservations" in schema:
        cur.execute("SELECT 1 FROM generation_reservations WHERE telegram_id=%s AND status='reserved' LIMIT 1", (uid,))
        if cur.fetchone():
            return "credit_reservation_in_flight"
    if "assistant_messages" in schema and "status" in schema["assistant_messages"]:
        cur.execute("SELECT 1 FROM assistant_messages WHERE telegram_id=%s AND status=ANY(%s) LIMIT 1",
                    (uid, ["pending", "queued", "processing", "running"]))
        if cur.fetchone():
            return "assistant_operation_in_flight"
    if "payment_inbox" in schema:
        cur.execute("SELECT 1 FROM payment_inbox WHERE telegram_id=%s "
                    "AND (status IS NULL OR NOT(status=ANY(%s))) LIMIT 1", (uid, list(policy.TERMINAL_PAYMENTS)))
        if cur.fetchone():
            return "payment_in_flight"
    if {"prostudio_provider_slots", "prostudio_generation_jobs"} <= set(schema):
        cur.execute("SELECT 1 FROM prostudio_provider_slots s JOIN prostudio_generation_jobs j ON j.id=s.job_id "
                    "WHERE j.telegram_id=%s AND s.lease_until>NOW() LIMIT 1", (uid,))
        if cur.fetchone():
            return "provider_lease_in_flight"
    return ""


def _strings(value, depth=0, *, strict=False):
    if depth > 40:
        raise ErasureError("erasure_metadata_requires_review")
    if isinstance(value, dict):
        for name,item in value.items():
            yield from _strings(item, depth + 1,strict=str(name).endswith('_json'))
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, depth + 1)
    elif isinstance(value, str):
        yield value
        if value[:1] in ("{", "["):
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                if strict:
                    raise ErasureError("erasure_metadata_requires_review") from None
            else:
                yield from _strings(decoded, depth + 1)
        for url in re.findall(r"https?://[^\s<>\"'\]\)]+", value):
            yield url


def media_keys(cur, records, schema, storage):
    strings = {s for row in records for s in _strings(row)}
    keys = set()
    for value in strings:
        key = storage.key_from_url(value)
        if key:
            keys.add(key)
    if "sylvex_storage_objects" in schema and strings:
        # Bare image_key/attachment keys are checked against the registry;
        # arbitrary prompt strings do not become object deletion commands.
        cur.execute("SELECT object_key FROM sylvex_storage_objects WHERE object_key=ANY(%s)", (list(strings),))
        keys.update(row[0] for row in cur.fetchall())
    return keys


def plan_request(database_url, request_id, *, storage, journal=None):
    """Read/record scope and holds. No content, file or payment is deleted."""
    journal = journal or Journal()
    with transaction(database_url) as cur:
        from services.account_erasure_guards import require_installed
        require_installed(cur,verify_coverage=True)
        request = request_row(cur, request_id, lock=True)
        if not request:
            raise ErasureError("erasure_request_not_found", 404)
        record = journal.read(request_id)
        if not record or record["account_id"] != request["account_id"] or record["subject_key"] != request["subject_key"]:
            raise ErasureError("erasure_journal_missing_or_mismatched", 503)
        if request["state"] == "complete" or request["subject_key"] is None:
            return receipt(request)
        _subject_lock(cur, request["subject_key"])
        if request["ecosystem"] == "telegram":
            cur.execute("SELECT telegram_caches_cleared_at FROM sylvex_erasure_requests WHERE request_id=%s",(str(request_id),))
            if not cur.fetchone()[0]:
                return {**receipt(request),"hold_code":"telegram_cache_clear_pending"}
        schema = columns(cur)
        unknown = unknown_owned_tables(schema)
        hold = "unclassified_owned_table" if unknown else work_in_flight(cur, schema, request)
        if hold:
            state = "purging" if request["state"] == "purging" else "scope_review" if unknown else "waiting_work"
            cur.execute("UPDATE sylvex_erasure_requests SET state=%s,hold_code=%s,updated_at=NOW() WHERE request_id=%s",
                        (state, hold, str(request_id)))
            return {**receipt({**request, "state": state}), "hold_code": hold}
        inventory_hold = False
        if "inventory_evidence_sha256" not in record:
            created = None
            if "created_at" in schema.get("sylvex_accounts",set()):
                cur.execute("SELECT created_at FROM sylvex_accounts WHERE account_id=%s",(request["account_id"],))
                row=cur.fetchone()
                created=row[0] if row else None
            cur.execute("SELECT ownership_started_at FROM sylvex_erasure_runtime WHERE singleton=TRUE")
            since=cur.fetchone()[0]
            # Prior uploads without a recorded owner cannot be found merely
            # by searching filenames. Require an explicit legacy inventory.
            if created is None or (created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created)<since:
                inventory_hold = True
        from services.account_erasure_runner import _related_scope_hold
        related_hold=_related_scope_hold(cur,schema,request)
        review=set()
        for table in list(policy.PERSONAL) + ["prostudio_generation_jobs", "site_visitors"]:
            _manifest_rows(cur,request,owned_rows(cur,table,schema,request),schema,storage)
        if {"prostudio_media_outbox", "prostudio_generation_jobs"} <= set(schema):
            rows=streamed_json(cur,"SELECT to_jsonb(o) FROM prostudio_media_outbox o JOIN prostudio_generation_jobs j ON j.id=o.job_id "
                               "WHERE j.telegram_id=%s",(request["subject_key"],))
            _manifest_rows(cur,request,rows,schema,storage)
        for table in policy.REVIEW:
            for row in owned_rows(cur, table, schema, request):
                cur.execute("SELECT 1 FROM sylvex_erasure_retained_rows WHERE request_id=%s AND table_name=%s "
                            "AND row_identity=%s AND expires_at>NOW()", (str(request_id), table, row_identity(row)))
                if not cur.fetchone():
                    review.add(table)
        batch=[]
        for key in streamed_json(cur,"SELECT object_key FROM sylvex_storage_ownership WHERE owner_key=%s",(request["subject_key"],)):
            batch.append(key)
            if len(batch)==100:
                _manifest_keys(cur,request,set(batch));batch=[]
        _manifest_keys(cur,request,set(batch))
        cur.execute("SELECT 1 FROM sylvex_erasure_media WHERE request_id=%s AND state='review' LIMIT 1", (str(request_id),))
        media_review = bool(cur.fetchone())
        state = "purging" if request["state"] == "purging" else "scope_review" if inventory_hold or related_hold or review else "media_review" if media_review else "queued"
        hold = "legacy_media_inventory_requires_review" if inventory_hold else related_hold if related_hold else "third_party_or_legal_scope_requires_review" if review else "object_ownership_requires_review" if media_review else ""
        cur.execute("UPDATE sylvex_erasure_requests SET state=%s,hold_code=%s,updated_at=NOW() WHERE request_id=%s",
                    (state, hold, str(request_id)))
        return {**receipt({**request, "state": state}), "hold_code": hold}


# Set by activate_runtime() when the configured erasure runtime is not usable
# (guards, schema or journal). The process then runs exactly as with erasure
# off: no fences that would need missing tables, no intake.
_RUNTIME_BLOCK = ""


def configured():
    return bool(os.getenv("SYLVEX_ERASURE_JOURNAL_DIR")) or os.getenv("SYLVEX_ERASURE_ENABLED", "").lower() in ("1", "true", "yes")


def enabled():
    return configured() and not _RUNTIME_BLOCK


def runtime_block():
    return _RUNTIME_BLOCK


def accepting():
    return os.getenv("SYLVEX_ERASURE_ACCEPTING", "").lower() in ("1", "true", "yes")


def activate_runtime(database_url):
    """API startup: install the schema and write fences once, then validate.

    Idempotent; guards are only (re)installed when missing or incomplete, with
    a short lock timeout. Any failure disables erasure for this process and is
    reported, instead of stopping the API. Nothing is erased here.
    """
    global _RUNTIME_BLOCK
    if not configured():
        _RUNTIME_BLOCK = ""
        return {"enabled": False, "configured": False}
    try:
        if not database_url:
            raise ErasureError("erasure_database_unavailable", 503)
        from services import account_erasure_guards as guards
        installed = False
        with transaction(database_url) as cur:
            cur.execute("SET LOCAL lock_timeout='5s'")
            ensure_schema(cur)
            try:
                guards.require_installed(cur, verify_coverage=True)
            except ErasureError:
                guards.install(cur)
                guards.require_installed(cur, verify_coverage=True)
                installed = True
        _RUNTIME_BLOCK = ""
        validate_runtime(database_url)
        # Aggregate counts only (no ids): lets the operator see requests left
        # from an earlier activation before intake/processing is switched on.
        with transaction(database_url) as cur:
            cur.execute("SELECT state,COUNT(*) FROM sylvex_erasure_requests GROUP BY state ORDER BY state")
            requests = {state: count for state, count in cur.fetchall()}
        return {"enabled": True, "configured": True, "guards_installed_now": installed,
                "accepting": accepting(), "requests_by_state": requests}
    except Exception as exc:
        _RUNTIME_BLOCK = exc.code if isinstance(exc, ErasureError) else type(exc).__name__
        return {"enabled": False, "configured": True, "error": _RUNTIME_BLOCK}


def _reserved_before(cur, uid, generation_id, requested_at):
    if "created_at" not in columns(cur).get("generation_reservations",set()):
        return False
    cur.execute("SELECT 1 FROM generation_reservations WHERE telegram_id=%s AND generation_id=%s "
                "AND status='reserved' AND created_at<=%s",(uid,str(generation_id),requested_at))
    return cur.fetchone() is not None


@contextmanager
def subject_operation(subject_key,generation_id):
    """Bind an owner already verified by a self-authenticating server route."""
    from services.security import actor_id
    token=actor_id.set(int(subject_key or 0))
    try:
        with operation_scope(generation_id):
            yield
    finally:
        actor_id.reset(token)


@contextmanager
def operation_scope(generation_id):
    """Track a provider scope without changing its tariff, reserve or charge.

    No guessed TTL ends an operation. A crashed scope remains a review hold
    until reconciled, rather than permitting premature irreversible erasure.
    """
    from services.security import actor_id
    uid = int(actor_id.get() or 0)
    database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
    if not enabled() or not uid:
        yield
        return
    if not database_url:
        raise ErasureError("erasure_database_unavailable", 503)
    operation_id = str(uuid4())
    with transaction(database_url) as cur:
        from services.account_erasure_guards import require_installed
        require_installed(cur)
        _subject_lock(cur, uid, shared=True)
        if blocked_subject(cur, uid):
            cur.execute("SELECT 1 FROM sylvex_active_operations o JOIN sylvex_erasure_requests r ON r.subject_key=o.subject_key "
                        "WHERE o.subject_key=%s AND o.generation_id=%s AND o.state='active' "
                        "AND o.started_at<=r.requested_at AND r.state NOT IN ('purging','complete') LIMIT 1", (uid,str(generation_id)))
            existing=bool(cur.fetchone())
            if not existing:
                cur.execute("SELECT requested_at,state FROM sylvex_erasure_requests WHERE subject_key=%s",(uid,))
                queued=cur.fetchone()
                if not queued or queued[1] in ('purging','complete') or not _reserved_before(cur,uid,generation_id,queued[0]):
                    raise ErasureError("account_erasure_in_progress")
        cur.execute("INSERT INTO sylvex_active_operations(operation_id,subject_key,generation_id,state,process_id) "
                    "VALUES(%s,%s,%s,'active',%s)", (operation_id,uid,str(generation_id),str(os.getpid())))
    try:
        yield
    finally:
        try:
            with transaction(database_url) as cur:
                cur.execute("UPDATE sylvex_active_operations SET state='finished',finished_at=NOW() WHERE operation_id=%s", (operation_id,))
        except Exception as exc:
            # Never turn a successful paid response into a second paid retry.
            # The still-active record holds erasure for operator reconciliation.
            print("ERASURE_OPERATION_FINISH_PENDING:", type(exc).__name__)


@contextmanager
def media_job_scope(connect, job_id):
    if not enabled():
        yield
        return
    from services.security import actor_id
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM prostudio_generation_jobs WHERE id=%s", (str(job_id),))
            row = cur.fetchone()
            if not row:
                raise ErasureError("erasure_media_job_not_found")
            uid = int(row[0])
    finally:
        conn.close()
    actor_token = actor_id.set(uid)
    job_token = _media_job.set(str(job_id))
    try:
        yield
    finally:
        _media_job.reset(job_token)
        actor_id.reset(actor_token)


def _existing_media_job(cur, uid, request):
    job_id = _media_job.get()
    if not job_id or request["state"] in ("purging", "complete"):
        return False
    cur.execute("SELECT 1 FROM prostudio_generation_jobs j JOIN prostudio_media_outbox o ON o.job_id=j.id "
                "WHERE j.id=%s AND j.telegram_id=%s AND j.created_at<=%s AND o.status IN ('pending','processing')",
                (job_id,uid,request["requested_at"]))
    return cur.fetchone() is not None


def _existing_paid_operation(cur, uid, request):
    if request["state"] in ("purging", "complete"):
        return False
    from services.billing_safety import current_billing_scope
    scope = current_billing_scope()
    if not scope:
        return False
    cur.execute("SELECT MIN(started_at) FROM sylvex_active_operations WHERE subject_key=%s AND generation_id=%s "
                "AND state='active'", (uid,scope["generation_id"]))
    started=cur.fetchone()[0]
    return bool(started and (started<=request["requested_at"] or _reserved_before(cur,uid,scope["generation_id"],request["requested_at"])))


def storage_write(function):
    """Fence the existing storage operation; do not change its upload method."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        from services.security import actor_id
        uid = int(actor_id.get() or 0)
        if not enabled() or not uid:
            return function(*args, **kwargs)
        if _storage_cursor.get() is not None:
            return function(*args, **kwargs)
        values = signature.bind(*args, **kwargs).arguments
        key = str(values.get("key") or "")
        # Use the storage module's own normalization, exactly as its operation.
        key = function.__globals__["normalize_key"](key)
        database_url = function.__globals__.get("DATABASE_URL")
        if not database_url:
            raise ErasureError("erasure_database_unavailable", 503)
        with transaction(database_url) as cur:
            from services.account_erasure_guards import require_installed
            require_installed(cur)
            _subject_lock(cur, uid, shared=True)
            request = _row(cur, "SELECT " + REQUEST_COLUMNS + " FROM sylvex_erasure_requests WHERE subject_key=%s", (uid,))
            if request and not (_existing_media_job(cur, uid, request) or _existing_paid_operation(cur, uid, request)):
                raise ErasureError("account_erasure_in_progress")
            cur.execute("SELECT pg_advisory_xact_lock_shared(61182,hashtext(%s))", (key,))
            cur.execute("SELECT 1 FROM sylvex_erasure_media WHERE object_key=%s AND state IN ('deleting','deleted') LIMIT 1", (key,))
            if cur.fetchone():
                raise ErasureError("erased_media_write")
            operation_id = str(uuid4())
            cur.execute("INSERT INTO sylvex_active_operations(operation_id,subject_key,generation_id,state,process_id) "
                        "VALUES(%s,%s,%s,'active',%s)", (operation_id,uid,"storage:"+key,str(os.getpid())))
            cur.execute("SELECT to_regclass('sylvex_storage_objects')")
            has_registry = cur.fetchone()[0] is not None
            registered = False
            if has_registry:
                cur.execute("SELECT 1 FROM sylvex_storage_objects WHERE object_key=%s", (key,))
                registered = cur.fetchone() is not None
            # A durable intent precedes the upload, so a crash between object
            # PUT and registry write cannot lose the key. Adoption alone is
            # not proof of ownership of an older object.
            if not registered and function.__name__ != "register_existing_object":
                cur.execute("INSERT INTO sylvex_storage_ownership(object_key,owner_key,source_kind) VALUES(%s,%s,%s) "
                            "ON CONFLICT(object_key) DO NOTHING", (key,uid,"media_job" if _media_job.get() else "authenticated_upload"))
            cur.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key=%s", (key,))
            owner = cur.fetchone()
            if owner and int(owner[0]) != uid:
                raise ErasureError("storage_ownership_conflict")
            cur.connection.commit()
            # The active operation remains durable across this commit. The
            # shared lock now protects network/registry completion, without
            # opening a second pooled connection inside an upload.
            _subject_lock(cur, uid, shared=True)
            cur.execute("SELECT pg_advisory_xact_lock_shared(61182,hashtext(%s))", (key,))
            cur.execute("SELECT 1 FROM sylvex_active_operations WHERE operation_id=%s AND state='active'", (operation_id,))
            if not cur.fetchone():
                raise ErasureError("erasure_operation_requires_review")
            cur.execute("SELECT 1 FROM sylvex_erasure_requests WHERE subject_key=%s AND state IN ('purging','complete')", (uid,))
            if cur.fetchone():
                raise ErasureError("account_erasure_in_progress")
            token = _storage_cursor.set((cur,uid))
            try:
                result = function(*args, **kwargs)
                cur.execute("UPDATE sylvex_active_operations SET state='finished',finished_at=NOW() WHERE operation_id=%s", (operation_id,))
                return result
            finally:
                _storage_cursor.reset(token)
    return wrapped


def storage_registry_cursor():
    context = _storage_cursor.get()
    return context[0] if context else None


def check_subject_access(database_url, subject_key, *, account_id=None):
    """Uncached access fence, including a legacy account with no safe uid scope."""
    if not database_url or (not subject_key and not account_id):
        return
    with transaction(database_url) as cur:
        if not _has_requests(cur):
            return
        cur.execute("SELECT 1 FROM sylvex_erasure_requests WHERE subject_key=%s OR account_id=%s LIMIT 1",
                    (int(subject_key) if subject_key else None,int(account_id) if account_id else None))
        if cur.fetchone():
            raise ErasureError("account_erasure_in_progress",403)


def validate_runtime(database_url):
    """Activation is explicit; it does not install guards or execute erasure."""
    if not database_url:
        raise ErasureError("erasure_database_unavailable",503)
    if os.getenv("SYLVEX_ERASURE_ACCEPTING", "").lower() in ("1","true","yes") and not os.getenv("SYLVEX_ERASURE_JOURNAL_DIR"):
        raise ErasureError("erasure_journal_not_configured",503)
    with transaction(database_url) as cur:
        from services.account_erasure_guards import require_installed
        require_installed(cur,verify_coverage=True)
    # API owns the journal volume; worker-only roles may use the DB fences
    # without mounting that volume. Restore runbook stops ALL roles first.
    if os.getenv("SYLVEX_ERASURE_JOURNAL_DIR"):
        from services.account_erasure_restore import readiness
        if not readiness(database_url)["ready"]:
            raise ErasureError("erasure_restore_replay_required",503)


def register_direct_upload(database_url, owner, key, expires):
    """Record the owner BEFORE a reusable presigned PUT leaves the API.

    Expiry prevents a new request from starting; it is not evidence that an
    already-started transfer ended. Erasure holds for explicit reconciliation.
    """
    if not enabled():
        return
    with transaction(database_url) as cur:
        from services.account_erasure_guards import require_installed
        require_installed(cur)
        _subject_lock(cur,owner,shared=True)
        if blocked_subject(cur,owner):
            raise ErasureError("account_erasure_in_progress",403)
        cur.execute("INSERT INTO sylvex_direct_uploads(object_key,owner_key,expires_at) VALUES(%s,%s,to_timestamp(%s))",
                    (key,int(owner),int(expires)))
        cur.execute("INSERT INTO sylvex_storage_ownership(object_key,owner_key,source_kind) VALUES(%s,%s,'direct_upload_capability')",
                    (key,int(owner)))


def finish_direct_upload(database_url, owner, key):
    if not enabled():
        return
    with transaction(database_url) as cur:
        cur.execute("UPDATE sylvex_direct_uploads SET completed_at=NOW() WHERE object_key=%s AND owner_key=%s",(key,int(owner)))


def reconcile_direct_upload(database_url, key, *, reviewed_by, evidence_ref):
    """Internal operator action after expiry AND verified transfer quiescence.

    A HEAD response, client completion or an elapsed timeout alone does not
    prove that no reusable upload is still in progress. Keep the evidence in
    the restricted support/operations record, not in public application logs.
    """
    if not str(reviewed_by).strip() or not str(evidence_ref).strip():
        raise ErasureError("erasure_upload_evidence_required")
    with transaction(database_url) as cur:
        cur.execute("SELECT owner_key,expires_at<=NOW() FROM sylvex_direct_uploads WHERE object_key=%s FOR UPDATE",(key,))
        row=cur.fetchone()
        if not row or not row[1]:
            raise ErasureError("direct_upload_capability_active")
        _subject_lock(cur,row[0])
        cur.execute("UPDATE sylvex_direct_uploads SET reconciled_at=NOW(),reviewed_by=%s,evidence_ref=%s WHERE object_key=%s",
                    (str(reviewed_by).strip()[:100],str(evidence_ref).strip()[:200],key))


def approve_legacy_inventory(database_url, request_id, *, reviewed_by, evidence_ref, journal=None):
    """Explicit support/operator attestation, never inferred from key names.

    Proven additional keys must first be included in the reviewed manifest.
    Per-key ownership and sharing checks still apply after this decision.
    """
    if not str(reviewed_by).strip() or not str(evidence_ref).strip():
        raise ErasureError("erasure_inventory_evidence_required")
    journal=journal or Journal()
    with transaction(database_url) as cur:
        request=request_row(cur,request_id,lock=True)
        if not request or request["subject_key"] is None or request["state"]=="complete":
            raise ErasureError("erasure_scope_requires_review")
        _subject_lock(cur,request["subject_key"])
        record=journal.read(request_id)
        if not record or record["account_id"]!=request["account_id"] or record["subject_key"]!=request["subject_key"]:
            raise ErasureError("erasure_journal_missing_or_mismatched",503)
        record.update(inventory_reviewed_at=utc_now(),inventory_evidence_sha256=hashlib.sha256(
            (str(reviewed_by).strip()+"\0"+str(evidence_ref).strip()).encode()).hexdigest())
        journal.write(record)
