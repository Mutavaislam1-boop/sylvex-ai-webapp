"""Offline erasure replay before a restored database is allowed to serve traffic.

Use the journal kept outside the restored backup. No application traffic or
background workers may run during replay. Default mode only reports readiness.
"""
from __future__ import annotations

import hashlib

from services import account_erasure as core
from services import account_erasure_guards as guards
from services import account_erasure_runner as runner


def _advance_sequence(cur, name, value):
    cur.execute("SELECT to_regclass(%s)", (name,))
    if cur.fetchone()[0] is None:
        return
    cur.execute("SELECT last_value,is_called FROM " + core.ident(name))
    current, called = cur.fetchone()
    if int(value) > int(current) or (int(value) == int(current) and not called):
        # Sequences are monotonic even if later replay fails. Skipping an ID
        # cannot grant access; reusing an erased identity could.
        cur.execute("SELECT setval(%s,%s,true)", (name,int(value)))


def _reserve_identity(cur, record, schema):
    account, uid = record["account_id"], record["subject_key"]
    cur.execute("SELECT active_telegram_id,origin FROM sylvex_accounts WHERE account_id=%s FOR UPDATE", (account,))
    existing = cur.fetchone()
    if existing and (uid is not None and int(existing[0] or 0) != uid or existing[1] != record["ecosystem"]):
        raise core.ErasureError("erasure_restore_identity_conflict",503)
    if uid is not None:
        cur.execute("SELECT 1 FROM sylvex_accounts WHERE active_telegram_id=%s AND account_id<>%s LIMIT 1", (uid,account))
        if cur.fetchone():
            raise core.ErasureError("erasure_restore_identity_conflict",503)
    if not existing:
        if uid is None:
            # A mixed legacy scope cannot be reconstructed from an ID alone.
            raise core.ErasureError("erasure_restore_scope_requires_review",503)
        cur.execute("INSERT INTO sylvex_accounts(account_id,active_telegram_id,storage_telegram_id,origin,session_generation) "
                    "VALUES(%s,%s,%s,%s,1)", (account,uid,uid if record["ecosystem"]=="website" else None,record["ecosystem"]))
    else:
        cur.execute("UPDATE sylvex_accounts SET session_generation=session_generation+1 WHERE account_id=%s", (account,))
    text = str(account)
    if len(text)==12 and text[2:6]=="0626" and 11<=int(text[:2])<=99 and 1<=int(text[8:])<=9999:
        sequence = "sylvex_telegram_id_seq" if text[6:8]=="99" else "sylvex_website_id_seq"
        _advance_sequence(cur,sequence,(int(text[:2])-11)*9999+int(text[8:]))
    elif account < core.WEB_STORAGE_FLOOR:
        _advance_sequence(cur,"sylvex_account_id_seq",account)
    if uid is not None and uid>=core.WEB_STORAGE_FLOOR:
        _advance_sequence(cur,"sylvex_web_storage_seq",uid)
    if uid is not None and record["ecosystem"]=="telegram":
        cur.execute("CREATE TABLE IF NOT EXISTS sylvex_tg_session_revocations(telegram_id BIGINT PRIMARY KEY,generation INTEGER NOT NULL DEFAULT 0)")
        cur.execute("INSERT INTO sylvex_tg_session_revocations VALUES(%s,1) ON CONFLICT(telegram_id) DO UPDATE "
                    "SET generation=sylvex_tg_session_revocations.generation+1", (uid,))


def readiness(database_url, *, journal=None):
    """No destructive work. Missing/reverted SQL state refuses restored startup."""
    journal = journal or core.Journal()
    holds=[]
    records=list(journal.records())
    external_ids={record["request_id"] for record in records}
    with core.transaction(database_url) as cur:
        has_requests=core._has_requests(cur)
        for record in records:
            row=core.request_row(cur,record["request_id"]) if has_requests else None
            if not row or row["account_id"]!=record["account_id"] or row["subject_key"]!=record["subject_key"]:
                holds.append({"request_id":record["request_id"],"hold_code":"erasure_restore_replay_required"})
            elif record["completed_at"] and row["state"]!="complete":
                holds.append({"request_id":record["request_id"],"hold_code":"erasure_restore_replay_required"})
        if has_requests:
            cur.execute("SELECT request_id FROM sylvex_erasure_requests WHERE NOT(request_id=ANY(%s::uuid[]))",(sorted(external_ids),))
            for (request_id,) in cur.fetchall():
                holds.append({"request_id":str(request_id),"hold_code":"erasure_journal_missing_or_mismatched"})
    return {"ready":not holds,"holds":holds}


def replay(database_url, *, storage=None, journal=None, apply=False, batch_size=50):
    journal=journal or core.Journal()
    if not apply:
        return readiness(database_url,journal=journal)
    storage=storage or runner.ObjectStore()
    records=sorted(journal.records(),key=lambda item:item["requested_at"])  # validate all, then replay in time order
    results=[]
    for record in records:
        request_id=record["request_id"]
        with core.transaction(database_url) as cur:
            core.ensure_schema(cur)
            guards.require_installed(cur)
            cur.execute("SELECT pg_advisory_xact_lock(61180,hashtext(%s))",(str(record["account_id"]),))
            row=core.request_row(cur,request_id,lock=True)
            if row and (row["account_id"]!=record["account_id"] or row["subject_key"]!=record["subject_key"]):
                raise core.ErasureError("erasure_restore_identity_conflict",503)
            if not row:
                runner._internal(cur,request_id)
                _reserve_identity(cur,record,core.columns(cur))
                cur.execute("INSERT INTO sylvex_erasure_requests(request_id,account_id,subject_key,ecosystem,state,requested_at,hold_code) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                            (request_id,record["account_id"],record["subject_key"],record["ecosystem"],
                             "queued" if record["subject_key"] else "scope_review",record["requested_at"],
                             "" if record["subject_key"] else "legacy_scope_requires_review"))
            if record["ecosystem"]=="telegram":
                # Offline replay explicitly requires every role to be stopped;
                # none of the previous process's in-memory state survives.
                cur.execute("UPDATE sylvex_erasure_requests SET telegram_caches_cleared_at=NOW() WHERE request_id=%s",(request_id,))
        plan=core.plan_request(database_url,request_id,storage=storage,journal=journal)
        decisions=journal.decisions(request_id)
        if decisions and not plan["complete"]:
            with core.transaction(database_url) as cur:
                request=core.request_row(cur,request_id,lock=True)
                runner._lock_scope(cur,request) if request["subject_key"] else None
                cur.execute("SELECT object_key,state FROM sylvex_erasure_media WHERE request_id=%s",(request_id,))
                for key,state in cur.fetchall():
                    decision=decisions.get(hashlib.sha256(key.encode()).hexdigest())
                    if decision=="shared":
                        cur.execute("UPDATE sylvex_erasure_media SET state='shared',proof_kind='journal_shared' WHERE request_id=%s AND object_key=%s",(request_id,key))
                    elif decision=="delete" and state not in ("deleted","shared"):
                        cur.execute("UPDATE sylvex_erasure_media SET state='owned',proof_kind='journal_replay' WHERE request_id=%s AND object_key=%s",(request_id,key))
        result=runner.process_request(database_url,request_id,storage=storage,journal=journal,apply=True,batch_size=batch_size)
        results.append(result)
    # Previously completed requests must complete again before reopening any
    # service. Pending requests may remain blocked, with their access frozen.
    status=readiness(database_url,journal=journal)
    return {**status,"results":results}
