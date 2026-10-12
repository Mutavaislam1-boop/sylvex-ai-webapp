"""Durable ingestion of confirmed Telegram Stars payments.

Keep this file byte-identical in sylvex-ai-webapp/services/payment_inbox.py
and sylvex-ai-bot/app/database/payment_inbox.py. Standard library only; the
database is reached through a DB-API `connect` callable (psycopg2).

A confirmed payment (a successful_payment update) is first made durable, and
only then acknowledged to Telegram:

1. payment_inbox (PostgreSQL), keyed by the unique telegram_payment_charge_id,
   holding everything needed to process it later (user, payload/order,
   amount, currency, subscription fields, raw update);
2. if the database is unreachable: an optional on-disk spool
   (PAYMENT_SPOOL_DIR; fsync'ed, atomic rename) that is drained into
   payment_inbox when the database is back;
3. if neither works: nothing is acknowledged - the polling bot does not
   advance its getUpdates offset and the webhook answers 503 - so Telegram
   keeps the update and delivers it again.

Processing (shop_orders.finalize_order: payment record, credits, subscription
and administration events in ONE transaction) is idempotent by charge id, so
an inbox row can be replayed any number of times - after a crash, restart,
outage, duplicate delivery or concurrent bot/webhook processing - and grants
exactly once. replay() processes pending rows; reconcile_star_transactions()
compares Telegram's own Star transaction history (getStarTransactions) with
the inbox and ingests any confirmed payment whose update was never received.
"""
import json
import os
import re

STATUS_PENDING = "pending"
STATUS_PROCESSED = "processed"
STATUS_REJECTED = "rejected"
ORDER_PAYLOAD_PREFIX = "sylvex_order:"
_ORDER_ID_RE = re.compile(r"[0-9a-f]{32}")

INBOX_DDL = (
    """CREATE TABLE IF NOT EXISTS payment_inbox (
           charge_id TEXT PRIMARY KEY,
           telegram_id BIGINT,
           invoice_payload TEXT NOT NULL,
           order_id TEXT,
           amount INTEGER NOT NULL,
           currency TEXT NOT NULL,
           is_recurring BOOLEAN,
           is_first_recurring BOOLEAN,
           subscription_expiration_date BIGINT,
           paid_at BIGINT,
           provider_payment_charge_id TEXT,
           raw TEXT,
           source TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'pending',
           result TEXT,
           attempts INTEGER NOT NULL DEFAULT 0,
           last_error TEXT,
           received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
           next_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
           processed_at TIMESTAMP
       )""",
    "CREATE INDEX IF NOT EXISTS idx_payment_inbox_pending ON payment_inbox (next_attempt_at) WHERE status = 'pending'",
    """CREATE TABLE IF NOT EXISTS payment_reconcile_state (
           name TEXT PRIMARY KEY,
           next_offset INTEGER NOT NULL DEFAULT 0,
           updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
       )""",
)

RECORD_FIELDS = ("charge_id", "telegram_id", "invoice_payload", "order_id", "amount", "currency", "is_recurring",
                 "is_first_recurring", "subscription_expiration_date", "paid_at", "provider_payment_charge_id", "raw")
_COLUMNS = RECORD_FIELDS + ("source", "status", "result", "attempts", "last_error")


def ensure_inbox_tables(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            for statement in INBOX_DDL:
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def order_id_from_payload(payload):
    text = str(payload or "")
    if not text.startswith(ORDER_PAYLOAD_PREFIX):
        return None
    order_id = text[len(ORDER_PAYLOAD_PREFIX):]
    return order_id if _ORDER_ID_RE.fullmatch(order_id) else None


def _int_or_none(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def payment_record(payer_id, payment, paid_at=None, raw=None):
    """A storable record of a successful_payment (dict), or None if it is not
    a Telegram Stars payment with a charge id."""
    payment = payment or {}
    charge_id = str(payment.get("telegram_payment_charge_id") or "")
    if payment.get("currency") != "XTR" or not charge_id:
        return None
    payload = str(payment.get("invoice_payload") or "")
    return {
        "charge_id": charge_id,
        "telegram_id": _int_or_none(payer_id),
        "invoice_payload": payload,
        "order_id": order_id_from_payload(payload),
        "amount": int(payment.get("total_amount") or 0),
        "currency": "XTR",
        "is_recurring": bool(payment.get("is_recurring")) if payment.get("is_recurring") is not None else None,
        "is_first_recurring": bool(payment.get("is_first_recurring")) if payment.get("is_first_recurring") is not None else None,
        "subscription_expiration_date": _int_or_none(payment.get("subscription_expiration_date")),
        "paid_at": _int_or_none(paid_at),
        "provider_payment_charge_id": str(payment.get("provider_payment_charge_id") or "") or None,
        "raw": raw if raw is None or isinstance(raw, str) else json.dumps(raw, default=str),
    }


def recurring_fields(record):
    """The shop_orders.finalize_order(recurring=...) argument of a record."""
    return {"is_recurring": record.get("is_recurring"), "is_first_recurring": record.get("is_first_recurring"),
            "subscription_expiration_date": record.get("subscription_expiration_date"), "paid_at": record.get("paid_at")}


def store(connect, record, source):
    """Persist a record (idempotent by charge id). Raises if the database is
    unavailable. Returns True if new, False if it was already stored."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO payment_inbox (" + ", ".join(RECORD_FIELDS) + ", source) VALUES ("
                + ", ".join(["%s"] * (len(RECORD_FIELDS) + 1)) + ") ON CONFLICT (charge_id) DO NOTHING RETURNING charge_id",
                tuple(record.get(field) for field in RECORD_FIELDS) + (source,),
            )
            created = cur.fetchone() is not None
        conn.commit()
        return created
    finally:
        conn.close()


class Spool:
    """On-disk fallback for when the database is unreachable. Each payment is
    one JSON file, written to a temporary name, fsync'ed and atomically
    renamed. Durable across restarts only if the directory is on persistent
    storage (e.g. a mounted volume)."""

    def __init__(self, directory):
        self.directory = str(directory or "").strip() or None

    @property
    def enabled(self):
        return bool(self.directory)

    def _name(self, charge_id):
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(charge_id))[:150]
        return os.path.join(self.directory, f"payment-{safe}.json")

    def write(self, record, source):
        os.makedirs(self.directory, exist_ok=True)
        final = self._name(record["charge_id"])
        tmp = final + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(dict(record, source=source), handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
        dir_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return final

    def entries(self):
        if not self.enabled or not os.path.isdir(self.directory):
            return []
        out = []
        for name in sorted(os.listdir(self.directory)):
            if not (name.startswith("payment-") and name.endswith(".json")):
                continue
            path = os.path.join(self.directory, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    out.append((path, json.load(handle)))
            except (OSError, ValueError):
                continue  # a torn temporary write never has the final name
        return out

    def remove(self, path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def record_durably(connect, record, source, spool=None):
    """Make a confirmed payment durable before it is acknowledged.
    Returns "db", "spool", or None (nothing durable: do NOT acknowledge)."""
    try:
        store(connect, record, source)
        return "db"
    except Exception:
        pass
    if spool is not None and spool.enabled:
        try:
            spool.write(record, source)
            return "spool"
        except Exception:
            pass
    return None


def drain_spool(connect, spool):
    """Move spooled payments into payment_inbox (file removed only after the
    row is committed). Returns the number moved."""
    moved = 0
    for path, data in (spool.entries() if spool is not None else []):
        record = {field: data.get(field) for field in RECORD_FIELDS}
        store(connect, record, str(data.get("source") or "spool") + "+spool")
        spool.remove(path)
        moved += 1
    return moved


def _row(row):
    return dict(zip(_COLUMNS, row)) if row else None


def get(connect, charge_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT " + ", ".join(_COLUMNS) + " FROM payment_inbox WHERE charge_id = %s", (str(charge_id),))
            return _row(cur.fetchone())
    finally:
        conn.close()


def claim_pending(connect, limit=50, legacy_sources=(), lease_seconds=120):
    """Claim pending rows for processing (safe with several processes: rows
    are locked with SKIP LOCKED and leased). Order payments can be processed
    by any service; other (legacy) payloads only by their own source."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join(_COLUMNS) + " FROM payment_inbox WHERE status = 'pending' "
                "AND next_attempt_at <= CURRENT_TIMESTAMP AND (order_id IS NOT NULL OR source = ANY(%s)) "
                "ORDER BY received_at LIMIT %s FOR UPDATE SKIP LOCKED",
                (list(legacy_sources), int(limit)),
            )
            rows = [_row(row) for row in cur.fetchall()]
            if rows:
                cur.execute(
                    "UPDATE payment_inbox SET attempts = attempts + 1, "
                    "next_attempt_at = CURRENT_TIMESTAMP + (%s || ' seconds')::interval WHERE charge_id = ANY(%s)",
                    (int(lease_seconds), [row["charge_id"] for row in rows]),
                )
        conn.commit()
        return rows
    finally:
        conn.close()


def _mark(connect, charge_id, status, result):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE payment_inbox SET status = %s, result = %s, last_error = NULL, "
                "processed_at = CASE WHEN %s = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END WHERE charge_id = %s",
                (status, str(result or "")[:200], status, str(charge_id)),
            )
        conn.commit()
    finally:
        conn.close()


def _mark_failed(connect, charge_id, error):
    """Retry later: 5 s doubling, at most 5 minutes."""
    try:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE payment_inbox SET last_error = %s, next_attempt_at = CURRENT_TIMESTAMP "
                    "+ (LEAST(300, 5 * POWER(2, LEAST(attempts, 6)))::int || ' seconds')::interval "
                    "WHERE charge_id = %s AND status = 'pending'",
                    (str(error or "")[:300], str(charge_id)),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # the row stays pending and is retried after its lease anyway


DONE_STATUSES = {"granted": STATUS_PROCESSED, "duplicate": STATUS_PROCESSED, "processed": STATUS_PROCESSED,
                 "rejected": STATUS_REJECTED}


def process(connect, record, handler):
    """Run handler(record) -> {"status": ...} for a stored record and mark the
    row. granted/duplicate/processed -> processed, rejected -> rejected,
    anything else (e.g. "retry") stays pending. An exception keeps the row
    pending for replay and is returned as {"status": "error"}."""
    try:
        result = handler(record) or {}
    except Exception as exc:
        _mark_failed(connect, record["charge_id"], f"{type(exc).__name__}: {exc}")
        return {"status": "error", "error": type(exc).__name__}
    status = DONE_STATUSES.get(result.get("status"))
    try:
        if status:
            _mark(connect, record["charge_id"], status, result.get("reason") or result.get("status"))
        else:
            _mark_failed(connect, record["charge_id"], result.get("reason") or result.get("status") or "retry")
    except Exception:
        pass  # processing is idempotent: a replay re-runs it and marks it then
    return result


def replay(connect, handler, spool=None, limit=50, legacy_sources=()):
    """Recover pending payments: drain the spool, then process pending rows.
    Returns counts; raises nothing (an unavailable database is retried on
    the next call)."""
    counts = {"spooled": 0, "processed": 0, "rejected": 0, "pending": 0, "error": None}
    try:
        if spool is not None and spool.enabled:
            counts["spooled"] = drain_spool(connect, spool)
        rows = claim_pending(connect, limit, legacy_sources)
    except Exception as exc:
        counts["error"] = type(exc).__name__
        return counts
    for row in rows:
        status = DONE_STATUSES.get(process(connect, row, handler).get("status"))
        counts[{STATUS_PROCESSED: "processed", STATUS_REJECTED: "rejected"}.get(status, "pending")] += 1
    return counts


def pending_count(connect):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM payment_inbox WHERE status = 'pending'")
            return int(cur.fetchone()[0])
    finally:
        conn.close()


# ------------------------------------------------ reconciliation with Telegram


def record_from_star_transaction(tx):
    """A record for an incoming invoice payment from Telegram's Star
    transaction history (getStarTransactions), or None. The transaction id is
    the payment's telegram_payment_charge_id. A renewal's expiration is the
    payment date plus its subscription period; whether it was the first
    payment of a subscription is not reported there."""
    source = tx.get("source") or {}
    if source.get("type") != "user":
        return None
    if source.get("transaction_type") not in (None, "invoice_payment"):
        return None
    payload = source.get("invoice_payload")
    user = source.get("user") or {}
    if not payload or not tx.get("id") or not user.get("id"):
        return None
    period = _int_or_none(source.get("subscription_period"))
    date = _int_or_none(tx.get("date"))
    return {
        "charge_id": str(tx["id"]),
        "telegram_id": int(user["id"]),
        "invoice_payload": str(payload),
        "order_id": order_id_from_payload(payload),
        "amount": int(tx.get("amount") or 0),
        "currency": "XTR",
        "is_recurring": True if period else None,
        "is_first_recurring": None,
        "subscription_expiration_date": (date + period) if (date and period) else None,
        "paid_at": date,
        "provider_payment_charge_id": None,
        "raw": json.dumps(tx, default=str),
    }


def _known_charge(cur, charge_id):
    cur.execute("SELECT 1 FROM payment_inbox WHERE charge_id = %s UNION ALL "
                "SELECT 1 FROM purchases WHERE charge_id = %s LIMIT 1", (charge_id, charge_id))
    return cur.fetchone() is not None


def reconcile_star_transactions(connect, fetch_page, page_size=100, max_pages=20, settle_seconds=600, now=None):
    """Ingest confirmed payments that Telegram recorded but SYLVEX never
    received (e.g. an update lost after Telegram stopped redelivering it).

    fetch_page(offset, limit) -> list of StarTransaction dicts (Telegram
    returns them in chronological order). A cursor in payment_reconcile_state
    remembers how many transactions were already examined; transactions newer
    than settle_seconds are left for the next run so a live update normally
    arrives first. Returns {"examined", "ingested"}."""
    import time as _time
    now = now or int(_time.time())
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO payment_reconcile_state (name, next_offset) VALUES ('star_transactions', 0) "
                        "ON CONFLICT (name) DO NOTHING")
            cur.execute("SELECT next_offset FROM payment_reconcile_state WHERE name = 'star_transactions'")
            offset = int(cur.fetchone()[0])
        conn.commit()
    finally:
        conn.close()
    examined = ingested = 0
    for _ in range(max_pages):
        page = list(fetch_page(offset, page_size) or [])
        if not page:
            break
        refunded = {str(tx.get("id")) for tx in page if (tx.get("receiver") or {}).get("type") == "user"}
        settled = []
        for tx in page:
            if _int_or_none(tx.get("date")) and _int_or_none(tx.get("date")) > now - settle_seconds:
                break
            settled.append(tx)
        conn = connect()
        try:
            with conn.cursor() as cur:
                for tx in settled:
                    record = record_from_star_transaction(tx)
                    if record and record["charge_id"] not in refunded and not _known_charge(cur, record["charge_id"]):
                        cur.execute(
                            "INSERT INTO payment_inbox (" + ", ".join(RECORD_FIELDS) + ", source) VALUES ("
                            + ", ".join(["%s"] * (len(RECORD_FIELDS) + 1)) + ") ON CONFLICT (charge_id) DO NOTHING",
                            tuple(record.get(field) for field in RECORD_FIELDS) + ("reconcile",),
                        )
                        ingested += 1
                offset += len(settled)
                cur.execute("UPDATE payment_reconcile_state SET next_offset = %s, updated_at = CURRENT_TIMESTAMP "
                            "WHERE name = 'star_transactions'", (offset,))
            conn.commit()
        finally:
            conn.close()
        examined += len(settled)
        if len(settled) < len(page) or len(page) < page_size:
            break
    return {"examined": examined, "ingested": ingested}
