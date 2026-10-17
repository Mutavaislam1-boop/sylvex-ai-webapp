"""Read-only account usage analytics for the SYLVEX website dashboard.

The dashboard is derived from the same immutable charge and confirmed-payment
records used by billing. It never estimates a charge or mutates a balance.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone


PERIODS = {
    "1d": {"days": 1, "bucket": "hour", "steps": 24},
    "7d": {"days": 7, "bucket": "day", "steps": 7},
    "30d": {"days": 30, "bucket": "day", "steps": 30},
    "365d": {"days": 365, "bucket": "month", "steps": 12},
}
CATEGORIES = ("image", "video", "music", "voice", "text")


def category_for_mode(mode: str) -> str:
    value = str(mode or "").lower().replace("-", "_")
    if "video" in value or value in {"animate", "lip_sync", "lipsync", "avatar"}:
        return "video"
    if "music" in value or value in {"song", "suno"}:
        return "music"
    if any(token in value for token in ("voice", "speech", "tts", "dubbing", "clone", "audio", "podcast")):
        return "voice"
    if any(token in value for token in ("text", "chat", "assistant", "realtime")):
        return "text"
    return "image"


def _utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value):
    parsed = _utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed else ""


def _floor(value: datetime, bucket: str) -> datetime:
    value = value.astimezone(timezone.utc)
    if bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if bucket == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_shift(value: datetime, amount: int) -> datetime:
    index = value.year * 12 + value.month - 1 + amount
    return value.replace(year=index // 12, month=index % 12 + 1, day=1)


def _bucket_sequence(period: str, now: datetime):
    config = PERIODS[period]
    end = _floor(now, config["bucket"])
    values = []
    for index in range(config["steps"]):
        offset = index - config["steps"] + 1
        if config["bucket"] == "hour":
            values.append(end + timedelta(hours=offset))
        elif config["bucket"] == "day":
            values.append(end + timedelta(days=offset))
        else:
            values.append(_month_shift(end, offset))
    return values


def build_usage_snapshot(grouped_charges, recent_charges, purchases, subscriptions, balance, period="30d", now=None):
    if period not in PERIODS:
        raise ValueError("invalid_period")
    now = _utc(now or datetime.now(timezone.utc))
    config = PERIODS[period]
    buckets = _bucket_sequence(period, now)
    timeline = {
        item: {"at": _iso(item), "credits": 0, "requests": 0, "categories": {key: 0 for key in CATEGORIES}}
        for item in buckets
    }
    category_totals = {key: {"category": key, "credits": 0, "requests": 0} for key in CATEGORIES}
    models = defaultdict(lambda: {"credits": 0, "requests": 0, "providers": set(), "categories": set()})

    total_credits = 0
    total_requests = 0
    for bucket, mode, model, provider, credits, requests in grouped_charges:
        stamp = _utc(bucket)
        if stamp is None:
            continue
        stamp = _floor(stamp, config["bucket"])
        category = category_for_mode(mode)
        credits, requests = max(0, int(credits or 0)), max(0, int(requests or 0))
        total_credits += credits
        total_requests += requests
        category_totals[category]["credits"] += credits
        category_totals[category]["requests"] += requests
        if stamp in timeline:
            timeline[stamp]["credits"] += credits
            timeline[stamp]["requests"] += requests
            timeline[stamp]["categories"][category] += credits
        label = str(model or "Unknown model").strip() or "Unknown model"
        models[label]["credits"] += credits
        models[label]["requests"] += requests
        if provider:
            models[label]["providers"].add(str(provider))
        models[label]["categories"].add(category)

    model_rows = [{
        "model": name,
        "credits": value["credits"],
        "requests": value["requests"],
        "provider": ", ".join(sorted(value["providers"])),
        "category": next(iter(value["categories"])) if len(value["categories"]) == 1 else "mixed",
    } for name, value in models.items()]
    model_rows.sort(key=lambda item: (-item["credits"], -item["requests"], item["model"].lower()))

    activity = []
    for generation_id, mode, model, provider, credits, created_at in recent_charges:
        activity.append({
            "id": str(generation_id or ""), "category": category_for_mode(mode),
            "model": str(model or "Unknown model"), "provider": str(provider or ""),
            "credits": max(0, int(credits or 0)), "created_at": _iso(created_at),
        })

    payment_items, payment_currencies = [], defaultdict(int)
    payment_credits = 0
    payment_timeline = {item: 0 for item in buckets}
    for payment_id, provider, credits, amount, currency, status, created_at, subscription_type in purchases:
        credits = max(0, int(credits or 0))
        amount = max(0, int(amount or 0))
        currency = str(currency or "").upper()
        stamp = _utc(created_at)
        payment_credits += credits
        if currency:
            payment_currencies[currency] += amount
        if stamp:
            key = _floor(stamp, config["bucket"])
            if key in payment_timeline:
                payment_timeline[key] += credits
        payment_items.append({
            "id": int(payment_id), "provider": str(provider or ""), "credits": credits,
            "amount": amount, "currency": currency, "status": str(status or "completed"),
            "created_at": _iso(created_at), "kind": "subscription" if subscription_type else "credits",
            "plan": str(subscription_type or ""),
        })

    subscription_items = []
    for row in subscriptions:
        sub_id, plan, method, amount, currency, status, starts_at, expires_at, created_at = row
        expiry = _utc(expires_at)
        subscription_items.append({
            "id": int(sub_id), "plan": str(plan or ""), "provider": str(method or ""),
            "amount": max(0, int(amount or 0)), "currency": str(currency or "").upper(),
            "status": str(status or ""), "starts_at": _iso(starts_at), "expires_at": _iso(expires_at),
            "created_at": _iso(created_at), "active": str(status or "").lower() == "active" and bool(expiry and expiry > now),
        })

    current_subscription = next((item for item in subscription_items if item["active"]), None)
    return {
        "period": period,
        "bucket": config["bucket"],
        "generated_at": _iso(now),
        "summary": {
            "balance": max(0, int(balance or 0)), "spent_credits": total_credits,
            "generation_requests": total_requests, "added_credits": payment_credits,
            "payments": len(payment_items), "active_subscription": current_subscription,
            "payment_amounts": dict(sorted(payment_currencies.items())),
        },
        "timeline": list(timeline.values()),
        "payment_timeline": [{"at": _iso(key), "credits": value} for key, value in payment_timeline.items()],
        "categories": [category_totals[key] for key in CATEGORIES],
        "models": model_rows,
        "activity": activity,
        "payments": payment_items,
        "subscriptions": subscription_items,
    }


def load_usage_snapshot(connect, telegram_id, period="30d"):
    if period not in PERIODS:
        raise ValueError("invalid_period")
    config = PERIODS[period]
    now = datetime.now(timezone.utc)
    start_at = _bucket_sequence(period, now)[0]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT date_trunc(%s, created_at), mode, model, provider,
                          COALESCE(SUM(credits), 0), COUNT(*)
                     FROM generation_charges
                    WHERE telegram_id = %s
                      AND created_at >= %s
                    GROUP BY 1, 2, 3, 4 ORDER BY 1""",
                (config["bucket"], int(telegram_id), start_at),
            )
            grouped = cur.fetchall()
            cur.execute(
                """SELECT generation_id, mode, model, provider, credits, created_at
                     FROM generation_charges
                    WHERE telegram_id = %s
                      AND created_at >= %s
                    ORDER BY created_at DESC LIMIT 250""",
                (int(telegram_id), start_at),
            )
            recent = cur.fetchall()
            cur.execute(
                """SELECT p.id, p.provider, p.credits, p.amount, p.currency, p.status,
                          NULLIF(p.created_at::text, '')::timestamptz,
                          s.subscription_type
                     FROM purchases p
                     LEFT JOIN subscriptions s ON s.charge_id = p.charge_id
                    WHERE p.telegram_id = %s
                      AND NULLIF(p.created_at::text, '')::timestamptz >= %s
                      AND p.status = 'completed'
                    ORDER BY NULLIF(p.created_at::text, '')::timestamptz DESC LIMIT 250""",
                (int(telegram_id), start_at),
            )
            purchases = cur.fetchall()
            cur.execute(
                """SELECT id, subscription_type, payment_method, amount, currency, status,
                          NULLIF(starts_at::text, '')::timestamp,
                          NULLIF(expires_at::text, '')::timestamp,
                          NULLIF(created_at::text, '')::timestamptz
                     FROM subscriptions WHERE telegram_id = %s
                    ORDER BY NULLIF(created_at::text, '')::timestamptz DESC LIMIT 50""",
                (int(telegram_id),),
            )
            subscriptions = cur.fetchall()
            cur.execute("SELECT COALESCE(balance, 0) FROM users WHERE telegram_id = %s", (int(telegram_id),))
            row = cur.fetchone()
        return build_usage_snapshot(grouped, recent, purchases, subscriptions, row[0] if row else 0, period, now)
    finally:
        conn.close()
