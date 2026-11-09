"""Bounded erasure execution for a previously confirmed request.

Default entrypoint is a plan; applying is explicit. Storage failures retain the
manifest and never produce complete=True. No payment or model dispatcher here.
"""
from __future__ import annotations

import re
from pathlib import Path

from services import account_erasure as core
from services import account_erasure_policy as policy

SAFE_KEY = re.compile(r"^[A-Za-z0-9_./~+-]+$")
OWNED_PROOFS = frozenset({"recorded_owner", "verified_upload_record", "verified_generation_provenance", "journal_replay",
                          "account_reference"})
# Every object the application writes to R2 is under generated/ (uploads,
# references, results, support attachments). Anything else is not attributed
# to an account automatically.
ACCOUNT_MEDIA_PREFIX = "generated/"


class ObjectStore:
    def __init__(self):
        from services import storage
        self.storage = storage

    def key_from_url(self, value):
        return self.storage.key_from_url(value)

    def _local(self, key):
        from services.safe_io import safe_local_path
        root = self.storage.LOCAL_GENERATED_DIR.parent.resolve()
        relative = Path(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise core.ErasureError("erasure_storage_key_requires_review")
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise core.ErasureError("erasure_local_symlink_requires_review")
        return safe_local_path(root, key)

    def delete(self, key):
        if self.storage.normalize_key(key) != key:
            raise core.ErasureError("erasure_storage_key_requires_review")
        if self.storage.r2_enabled():
            self.storage.r2_client().delete_object(Bucket=self.storage.R2_BUCKET, Key=key)
        else:
            self._local(key).unlink(missing_ok=True)

    def absent(self, key):
        if not self.storage.r2_enabled():
            return not self._local(key).exists()
        try:
            self.storage.r2_client().head_object(Bucket=self.storage.R2_BUCKET, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code") or "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return True
            # AccessDenied, timeout and transport failure are NOT not-found.
            raise
        return False


def _lock_scope(cur, request):
    cur.execute("SELECT pg_advisory_xact_lock(61180,hashtext(%s))", (str(request["account_id"]),))
    core._subject_lock(cur, request["subject_key"])


def _internal(cur, request_id):
    cur.execute("SELECT set_config('sylvex.erasure_request',%s,true)", (str(request_id),))


def _shared_reference(cur, key, schema, request):
    # Reference triggers take the same per-key SHARED lock before any insert
    # or update, including a reference to a not-yet-registered upload. The
    # executor holds EXCLUSIVE while checking and deleting this one object.
    tables = set(policy.PERSONAL) | set(policy.REVIEW) | policy.SHARED_CATALOG | {
        "prostudio_generation_jobs", "support_messages",
    }
    for table in sorted(tables & set(schema)):
        where, params = "TRUE", []
        if table in policy.PERSONAL or table == "prostudio_generation_jobs":
            owned, owner_params = core.owner_clause(table, schema, request)
            where, params = "NOT " + owned, owner_params
        cur.execute("SELECT 1 FROM " + core.ident(table) + " t WHERE " + where +
                    " AND %s=ANY(sylvex_erasure_reference_keys(to_jsonb(t))) LIMIT 1", params+[key])
        if cur.fetchone():
            return True
    if {"prostudio_media_outbox", "prostudio_generation_jobs"} <= set(schema):
        cur.execute("SELECT 1 FROM prostudio_media_outbox o JOIN prostudio_generation_jobs j ON j.id=o.job_id "
                    "WHERE j.telegram_id<>%s AND %s=ANY(sylvex_erasure_reference_keys(to_jsonb(o))) LIMIT 1",
                    (request["subject_key"],key))
        if cur.fetchone():
            return True
    return False


def attribute_account_media(cur, schema, request):
    """Self-service attribution of manifest keys with no recorded owner.

    The manifest holds only keys referenced by this account's own records. A
    key is the account's when no other owner is recorded and no other
    account, shared catalog or review record references it; the executor
    repeats this check under the exclusive per-key lock before deleting.
    Anything else is kept (state 'shared') and never deleted.
    """
    cur.execute("SELECT object_key FROM sylvex_erasure_media WHERE request_id=%s AND state='review' ORDER BY object_key",
                (str(request["request_id"]),))
    for (key,) in cur.fetchall():
        cur.execute("SELECT pg_advisory_xact_lock_shared(61182,hashtext(%s))", (key,))
        cur.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key=%s", (key,))
        owner = cur.fetchone()
        if owner and int(owner[0]) != int(request["subject_key"]):
            state, proof = "shared", "other_owner"
        elif _shared_reference(cur, key, schema, request):
            state, proof = "shared", "other_reference"
        elif SAFE_KEY.fullmatch(key) and key.startswith(ACCOUNT_MEDIA_PREFIX) and ".." not in key.split("/"):
            state, proof = "owned", "account_reference"
        else:
            state, proof = "shared", "unattributed_retained"
        cur.execute("UPDATE sylvex_erasure_media SET state=%s,proof_kind=%s,approved_by='self_service',updated_at=NOW() "
                    "WHERE request_id=%s AND object_key=%s AND state='review'", (state,proof,str(request["request_id"]),key))


def approve_media_ownership(database_url, request_id, key, *, proof_kind, reviewed_by):
    """Internal operator decision after checking provenance, not a user route."""
    if proof_kind not in OWNED_PROOFS - {"recorded_owner","journal_replay"} or not str(reviewed_by).strip():
        raise core.ErasureError("erasure_ownership_evidence_required")
    with core.transaction(database_url) as cur:
        request = core.request_row(cur, request_id, lock=True)
        if not request or request["subject_key"] is None or request["state"] == "complete":
            raise core.ErasureError("erasure_scope_requires_review")
        _lock_scope(cur, request)
        cur.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key=%s", (key,))
        row = cur.fetchone()
        if row and int(row[0]) != int(request["subject_key"]):
            raise core.ErasureError("erasure_other_owner")
        cur.execute("UPDATE sylvex_erasure_media SET state='owned',proof_kind=%s,approved_by=%s,updated_at=NOW() "
                    "WHERE request_id=%s AND object_key=%s AND state='review'",
                    (proof_kind,str(reviewed_by).strip()[:100],str(request_id),key))
        if cur.rowcount != 1:
            raise core.ErasureError("erasure_manifest_item_not_reviewable")


def approve_row_retention(database_url, request_id, table, identity, *, basis, reviewed_by, expires_at):
    """Specific lawful exception. A table-wide or permanent hold is refused."""
    if table not in policy.REVIEW or basis not in policy.RETENTION_BASES or not str(reviewed_by).strip():
        raise core.ErasureError("erasure_retention_evidence_required")
    with core.transaction(database_url) as cur:
        request = core.request_row(cur, request_id, lock=True)
        if not request or request["subject_key"] is None or request["state"] == "complete":
            raise core.ErasureError("erasure_scope_requires_review")
        _lock_scope(cur, request)
        schema = core.columns(cur)
        rows = core.owned_rows(cur, table, schema, request)
        if not any(core.row_identity(row) == identity for row in rows):
            raise core.ErasureError("erasure_retention_row_changed")
        cur.execute("SELECT %s::timestamptz>NOW()", (expires_at,))
        if not cur.fetchone()[0]:
            raise core.ErasureError("erasure_retention_expiry_required")
        cur.execute("INSERT INTO sylvex_erasure_retained_rows(request_id,table_name,row_identity,basis,approved_by,expires_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(request_id,table_name,row_identity) DO UPDATE "
                    "SET basis=EXCLUDED.basis,approved_by=EXCLUDED.approved_by,expires_at=EXCLUDED.expires_at",
                    (str(request_id),table,identity,basis,str(reviewed_by).strip()[:100],expires_at))


def _related_scope_hold(cur, schema, request):
    uid = request["subject_key"]
    # Staff privileges and second factors require an explicit handover before
    # a request can be reported complete. A retention approval is not a way
    # to keep an active administrator session or authentication credential.
    for row in core.owned_rows(cur,"admin_accounts",schema,request):
        if row.get("status")=="active" or row.get("totp_secret_enc") or row.get("totp_pending_enc"):
            return "privileged_access_requires_review"
    for row in core.owned_rows(cur,"admin_users",schema,request):
        if row.get("active") is not False and row.get("active")!=0:
            return "privileged_access_requires_review"
    if {"prostudio_resources", "prostudio_visual_user_state"} <= set(schema):
        cur.execute("SELECT 1 FROM prostudio_visual_user_state v JOIN prostudio_resources r ON r.id=v.resource_id "
                    "WHERE r.telegram_id=%s AND v.telegram_id<>%s LIMIT 1", (uid,uid))
        if cur.fetchone():
            return "resource_in_use_by_other_account"
    if {"prostudio_resources", "prostudio_character_history"} <= set(schema) and "character_id" in schema["prostudio_character_history"]:
        cur.execute("SELECT 1 FROM prostudio_character_history h JOIN prostudio_resources r ON r.id=h.character_id "
                    "WHERE r.telegram_id=%s AND h.telegram_id<>%s LIMIT 1", (uid,uid))
        if cur.fetchone():
            return "resource_in_use_by_other_account"
    if {"prostudio_generation_shares", "prostudio_generation_jobs"} <= set(schema):
        cur.execute("SELECT 1 FROM prostudio_generation_shares s JOIN prostudio_generation_jobs j ON j.id=s.job_id "
                    "WHERE j.telegram_id=%s AND s.owner_telegram_id<>%s LIMIT 1", (uid,uid))
        if cur.fetchone():
            return "job_shared_by_other_account"
    if "prostudio_generation_jobs" in schema:
        for table in ("prostudio_character_history","prostudio_error_reports","prostudio_errors","sylvex_test_requests"):
            if table not in schema or "job_id" not in schema[table]:
                continue
            owned,params=core.owner_clause(table,schema,request,alias="t")
            cur.execute("SELECT 1 FROM "+core.ident(table)+" t JOIN prostudio_generation_jobs j ON j.id=t.job_id "
                        "WHERE j.telegram_id=%s AND NOT "+owned+" LIMIT 1",[uid]+params)
            if cur.fetchone():
                return "job_in_use_by_other_account"
    return ""


def _check_reviewed_rows(cur, schema, request):
    for table in policy.REVIEW:
        for row in core.owned_rows(cur, table, schema, request):
            cur.execute("SELECT 1 FROM sylvex_erasure_retained_rows WHERE request_id=%s AND table_name=%s "
                        "AND row_identity=%s AND expires_at>NOW()", (str(request["request_id"]),table,core.row_identity(row)))
            if not cur.fetchone():
                return "third_party_or_legal_scope_requires_review"
    return _related_scope_hold(cur, schema, request)


def _purge_personal(cur, schema, request):
    uid, account = request["subject_key"], request["account_id"]
    # Child rows first; no unscoped cascade or DELETE users.
    if {"prostudio_media_outbox", "prostudio_generation_jobs"} <= set(schema):
        cur.execute("DELETE FROM prostudio_media_outbox o USING prostudio_generation_jobs j "
                    "WHERE o.job_id=j.id AND j.telegram_id=%s", (uid,))
    for table in ("prostudio_provider_slots", "prostudio_provider_circuit_probes"):
        if table in schema and "prostudio_generation_jobs" in schema:
            cur.execute("DELETE FROM " + core.ident(table) + " p USING prostudio_generation_jobs j "
                        "WHERE p.job_id=j.id AND j.telegram_id=%s", (uid,))
    if {"prostudio_visual_stats", "prostudio_resources"} <= set(schema):
        cur.execute("DELETE FROM prostudio_visual_stats s USING prostudio_resources r WHERE s.resource_id=r.id AND r.telegram_id=%s", (uid,))
    ordered = [table for table in policy.PERSONAL if table != "prostudio_resources"] + ["prostudio_resources"]
    for table in ordered:
        if table in schema:
            where, params = core.owner_clause(table, schema, request)
            cur.execute("DELETE FROM " + core.ident(table) + " WHERE " + where, params)
    if "prostudio_generation_jobs" in schema:
        # Minimal billed job evidence may be needed to reconcile its charge.
        # Free, uncharged work has no accounting reason to remain.
        fields = schema["prostudio_generation_jobs"]
        assignments = []
        for name in ("prompt",):
            if name in fields:
                assignments.append(core.ident(name) + "=''")
        for name in ("request_json", "response_json", "result_json", "error_json", "stage_json"):
            if name in fields:
                assignments.append(core.ident(name) + "='{}'::jsonb")
        if assignments:
            cur.execute("UPDATE prostudio_generation_jobs SET " + ",".join(assignments) + " WHERE telegram_id=%s", (uid,))
        if "cost" in fields:
            cur.execute("DELETE FROM prostudio_generation_jobs j WHERE j.telegram_id=%s AND COALESCE(j.cost,0)=0" +
                        (" AND NOT EXISTS(SELECT 1 FROM generation_charges c WHERE c.generation_id=j.id)" if "generation_charges" in schema else ""), (uid,))
    emails = []
    if "account_emails" in schema:
        cur.execute("SELECT email FROM account_emails WHERE account_id=%s", (account,))
        emails.extend(row[0] for row in cur.fetchall() if row[0])
    if "account_oauth" in schema:
        cur.execute("SELECT email FROM account_oauth WHERE account_id=%s", (account,))
        emails.extend(row[0] for row in cur.fetchall() if row[0])
    if emails and "account_pending_registrations" in schema:
        cur.execute("DELETE FROM account_pending_registrations WHERE email=ANY(%s)", (emails,))
    for table in ("account_deletion_codes", "account_link_codes", "account_oauth", "account_emails"):
        if table in schema:
            cur.execute("DELETE FROM " + core.ident(table) + " WHERE account_id=%s", (account,))
    if "site_visitors" in schema:
        assignments = ["account_id=NULL"]
        if "ip_hash" in schema["site_visitors"]:
            assignments.append("ip_hash=NULL")
        cur.execute("UPDATE site_visitors SET " + ",".join(assignments) + " WHERE account_id=%s", (account,))
    if "users" in schema:
        assignments = [core.ident(name) + "=NULL" for name in ("username", "first_name", "language_code") if name in schema["users"]]
        # Owner decision 08.11: the remaining credits and the subscription end
        # with the account; nothing is restored by a later registration.
        if "balance" in schema["users"]:
            assignments.append("balance=0")
        if "subscription" in schema["users"]:
            assignments.append("subscription='free'")
        if assignments:
            cur.execute("UPDATE users SET " + ",".join(assignments) + " WHERE telegram_id=%s", (uid,))
    if "user_credit_wallets" in schema:
        cur.execute("DELETE FROM user_credit_wallets WHERE telegram_id=%s", (uid,))
    if "subscriptions" in schema and "status" in schema["subscriptions"]:
        # The payment rows stay as financial records; only the entitlement ends.
        cur.execute("UPDATE subscriptions SET status='canceled' WHERE telegram_id=%s AND status='active'", (uid,))
    cur.execute("DELETE FROM sylvex_direct_uploads WHERE owner_key=%s", (uid,))
    cur.execute("DELETE FROM sylvex_storage_ownership WHERE owner_key=%s", (uid,))


def process_request(database_url, request_id, *, storage=None, journal=None, apply=False, batch_size=50, self_service=False):
    storage, journal = storage or ObjectStore(), journal or core.Journal()
    plan = core.plan_request(database_url, request_id, storage=storage, journal=journal, self_service=self_service)
    if not apply or plan["complete"] or plan.get("hold_code") or plan["state"] not in ("queued", "purging"):
        return plan
    with core.transaction(database_url) as cur:
        request = core.request_row(cur, request_id, lock=True)
        _lock_scope(cur, request)
        schema = core.columns(cur)
        hold = core.work_in_flight(cur, schema, request) or _check_reviewed_rows(cur, schema, request)
        if hold:
            return {**core.receipt(request), "hold_code": hold}
        cur.execute("UPDATE sylvex_erasure_requests SET state='purging',updated_at=NOW() WHERE request_id=%s", (str(request_id),))

    # Freeze first, then rebuild the manifest from the stable private scope.
    # An already-started metadata write may have committed between the first
    # plan and this subject lock. No key may be lost before SQL row erasure.
    frozen=core.plan_request(database_url,request_id,storage=storage,journal=journal,self_service=self_service)
    if frozen.get('hold_code'):
        return frozen

    processed = 0
    while processed < max(1, min(int(batch_size),500)):
        key = None
        try:
            with core.transaction(database_url) as cur:
                request = core.request_row(cur, request_id, lock=True)
                _lock_scope(cur, request)
                cur.execute("SELECT object_key,proof_kind FROM sylvex_erasure_media WHERE request_id=%s "
                            "AND state IN ('owned','deleting') ORDER BY object_key LIMIT 1 FOR UPDATE", (str(request_id),))
                item = cur.fetchone()
                if not item:
                    break
                key, proof = item
                if not SAFE_KEY.fullmatch(key) or proof not in OWNED_PROOFS:
                    raise core.ErasureError("erasure_storage_key_requires_review")
                cur.execute("SELECT pg_advisory_xact_lock(61182,hashtext(%s))", (key,))
                schema = core.columns(cur)
                cur.execute("SELECT owner_key FROM sylvex_storage_ownership WHERE object_key=%s", (key,))
                owner = cur.fetchone()
                shared = bool(owner and int(owner[0]) != int(request["subject_key"])) or _shared_reference(cur,key,schema,request)
                if shared:
                    journal.append_decision(request_id,key,"shared")
                    cur.execute("UPDATE sylvex_erasure_media SET state='shared',proof_kind='other_reference',updated_at=NOW() "
                                "WHERE request_id=%s AND object_key=%s", (str(request_id),key))
                else:
                    # Fsync the authorized key HASH before destructive I/O.
                    # This evidence survives a restore of an older database.
                    journal.append_decision(request_id,key,"delete")
                    cur.execute("UPDATE sylvex_erasure_media SET state='deleting',attempts=attempts+1,updated_at=NOW() "
                                "WHERE request_id=%s AND object_key=%s", (str(request_id),key))
                    storage.delete(key)
                    if not storage.absent(key):
                        raise core.ErasureError("erasure_object_still_present",503)
                    if "sylvex_storage_objects" in schema:
                        cur.execute("DELETE FROM sylvex_storage_objects WHERE object_key=%s", (key,))
                    cur.execute("UPDATE sylvex_erasure_media SET state='deleted',last_error='',updated_at=NOW() "
                                "WHERE request_id=%s AND object_key=%s", (str(request_id),key))
            processed += 1
        except Exception as exc:
            code = exc.code if isinstance(exc, core.ErasureError) else type(exc).__name__
            with core.transaction(database_url) as cur:
                cur.execute("UPDATE sylvex_erasure_media SET attempts=attempts+1,last_error=%s,updated_at=NOW() "
                            "WHERE request_id=%s AND object_key=%s", (code,str(request_id),key))
            return {"accepted":True,"complete":False,"request_id":str(request_id),"state":"purging",
                    "hold_code":code if isinstance(exc,core.ErasureError) else "media_retry_required"}

    with core.transaction(database_url) as cur:
        request = core.request_row(cur, request_id, lock=True)
        _lock_scope(cur, request)
        schema = core.columns(cur)
        cur.execute("SELECT 1 FROM sylvex_erasure_media WHERE request_id=%s AND state IN ('review','owned','deleting') LIMIT 1", (str(request_id),))
        if cur.fetchone():
            return {**core.receipt(request),"hold_code":"media_remaining"}
        hold = core.work_in_flight(cur,schema,request) or _check_reviewed_rows(cur,schema,request)
        if hold:
            return {**core.receipt(request),"hold_code":hold}
        if core.unknown_owned_tables(schema):
            return {**core.receipt(request),"hold_code":"unclassified_owned_table"}
        _internal(cur,request_id)
        _purge_personal(cur,schema,request)
        cur.execute("SELECT object_key,state FROM sylvex_erasure_media WHERE request_id=%s",(str(request_id),))
        for key,state in cur.fetchall():
            journal.append_decision(request_id,key,"shared" if state=="shared" else "delete")
        record = journal.read(request_id)
        if not record or record["account_id"] != request["account_id"] or record["subject_key"] != request["subject_key"]:
            raise core.ErasureError("erasure_journal_missing_or_mismatched",503)
        record["completed_at"] = record["completed_at"] or core.utc_now()
        journal.write(record)
        cur.execute("UPDATE sylvex_erasure_requests SET state='complete',completed_at=%s,hold_code='',updated_at=NOW() "
                    "WHERE request_id=%s", (record["completed_at"],str(request_id)))
    return {"accepted":True,"complete":True,"request_id":str(request_id),"state":"complete"}


# Stripe subscription states that can still renew or be charged.
RENEWING_STRIPE = ("active", "trialing", "past_due", "unpaid", "incomplete", "paused")


def cancel_renewals(database_url, request, *, stripe=None):
    """Stop automatic renewal for the confirmed subject before data removal.

    Immediate cancellation (access already ended at confirmation); no refund
    and no payment row is changed. Already-cancelled or missing subscriptions
    count as done. Idempotent: only still-renewing rows are contacted.
    """
    uid = request.get("subject_key")
    if not uid:
        return 0
    with core.transaction(database_url) as cur:
        schema = core.columns(cur)
        if "stripe_subscriptions" not in schema:
            return 0
        cur.execute("SELECT subscription_id FROM stripe_subscriptions WHERE telegram_id=%s AND status=ANY(%s) "
                    "ORDER BY subscription_id", (int(uid), list(RENEWING_STRIPE)))
        ids = [row[0] for row in cur.fetchall()]
    if not ids:
        return 0
    if stripe is None:
        import os
        from services import stripe_billing
        key = os.getenv("STRIPE_SECRET_KEY", "")
        if not key:
            raise core.ErasureError("renewal_cancel_unavailable", 503)
        stripe = stripe_billing.StripeClient(key)
    for subscription_id in ids:
        try:
            stripe.request("DELETE", "/subscriptions/" + str(subscription_id),
                           idempotency_key="erasure-cancel-" + str(subscription_id))
        except Exception as exc:
            if getattr(exc, "status", None) != 404:
                raise core.ErasureError("renewal_cancel_retry", 503) from exc
        with core.transaction(database_url) as cur:
            cur.execute("UPDATE stripe_subscriptions SET status='canceled' WHERE subscription_id=%s", (str(subscription_id),))
    return len(ids)


def process_pending(database_url, *, storage=None, journal=None, stripe=None, limit=5):
    """Self-service erasure: run every confirmed request without operator steps.

    Holds that protect other people or in-flight work (another account's
    reference, a running job, staff access) stay held and are retried on the
    next pass; nothing outside the confirmed subject is touched.

    Runs only while intake is on (SYLVEX_ERASURE_ACCEPTING): enabling the
    fences alone never processes requests left from an earlier activation.
    """
    if not core.accepting():
        return []
    with core.transaction(database_url) as cur:
        if not core._has_requests(cur):
            return []
        # Held requests are re-planned on every pass: a hold is recomputed
        # from current data and stays until its condition is gone.
        cur.execute("SELECT request_id FROM sylvex_erasure_requests "
                    "WHERE subject_key IS NOT NULL "
                    "AND state IN ('queued','purging','waiting_work','scope_review','media_review') "
                    "ORDER BY requested_at LIMIT %s", (max(1, int(limit)),))
        ids = [str(row[0]) for row in cur.fetchall()]
    results = []
    for request_id in ids:
        with core.transaction(database_url) as cur:
            request = core.request_row(cur, request_id)
        try:
            cancel_renewals(database_url, request, stripe=stripe)
            result = process_request(database_url, request_id, storage=storage, journal=journal, apply=True, self_service=True)
        except core.ErasureError as exc:
            result = {"request_id": request_id, "complete": False, "hold_code": exc.code}
        except Exception as exc:
            result = {"request_id": request_id, "complete": False, "hold_code": type(exc).__name__}
        with core.transaction(database_url) as cur:
            cur.execute("SELECT state||':'||proof_kind,COUNT(*) FROM sylvex_erasure_media WHERE request_id=%s GROUP BY 1",
                        (request_id,))
            media = dict(cur.fetchall())
        # Counts only: no account, key or content leaves the database.
        results.append({"request_id": request_id, "complete": bool(result.get("complete")),
                        "state": result.get("state", ""), "hold_code": result.get("hold_code", ""), "media": media})
    return results
