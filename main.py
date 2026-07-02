import os
import pathlib
import json
import hmac
import hashlib
import urllib.parse
import asyncio
from typing import Optional
from uuid import uuid4
import requests
import psycopg2
from dotenv import load_dotenv
from fastapi.responses import JSONResponse, RedirectResponse



from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()

BASE_DIR = pathlib.Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
app.mount("/image", StaticFiles(directory="image"), name="image")
app.mount("/assets", StaticFiles(directory="webapp/assets"), name="assets")
app.mount("/js", StaticFiles(directory="webapp/js"), name="js")
app.mount("/css", StaticFiles(directory="webapp/css"), name="css")


BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
print("MINIAPP DATABASE:", DATABASE_URL)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sylvex-ai-webapp-production.up.railway.app")
PAYMENT_WEBAPP_URL = os.getenv("PAYMENT_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/payments")
SHOP_WEBAPP_URL = os.getenv("SHOP_WEBAPP_URL", WEBAPP_URL.rstrip("/") + "/webapp/index.html?view=shop")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS-API-KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_DEFAULT_VOICE_NAME = "Rachel"
ELEVENLABS_DEFAULT_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = (os.getenv("PAYPAL_MODE") or "sandbox").strip().lower()
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")
PAYPAL_API_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"
PAYPAL_PRO_MONTHLY_PLAN_ID = os.getenv("PAYPAL_PRO_MONTHLY_PLAN_ID", "P-2JN99488MP781262CNJDGCZI")
PAYPAL_PRO_YEARLY_PLAN_ID = os.getenv("PAYPAL_PRO_YEARLY_PLAN_ID", "P-0YT1496917791881BNJDGRMY")
CRYPTO_API_KEY = os.getenv("CRYPTO_API_KEY") or os.getenv("CRIPTO_API_KEY")
CRYPTO_PAY_API_URL = "https://pay.crypt.bot/api"
HEYGEN_BASE_URL = "https://api.heygen.com/v3"
HEYGEN_VOICE_MODEL_ID = "starfish"
HEYGEN_DEFAULT_LANGUAGE = "ru"
HEYGEN_DEFAULT_SPEED = 1.0
HEYGEN_DEFAULT_OUTPUT_FORMAT = "mp3"
DEV_TELEGRAM_ID = int(os.getenv("DEV_TELEGRAM_ID", "7932380565"))
SUBSCRIPTION_BONUS_CREDITS = int(os.getenv("SUBSCRIPTION_BONUS_CREDITS", "100"))

SHOP_ITEMS = {
    "sub_month": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 месяц",
        "plan_key": "month",
        "days": 30,
        "credits": 0,
        "bonus_credits": SUBSCRIPTION_BONUS_CREDITS,
        "usd": 5.0,
        "stars": 230,
    },
    "sub_year": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 год",
        "plan_key": "year",
        "days": 365,
        "credits": 0,
        "bonus_credits": SUBSCRIPTION_BONUS_CREDITS,
        "usd": 59.0,
        "stars": 2751,
    },
    "pack_100": {"kind": "credits", "title": "100 ⚡", "credits": 100, "usd": 1.0, "stars": 46},
    "pack_500": {"kind": "credits", "title": "500 ⚡", "credits": 500, "usd": 5.0, "stars": 230},
    "pack_1000": {"kind": "credits", "title": "1000 ⚡", "credits": 1000, "usd": 10.0, "stars": 460},
    "pack_2000": {"kind": "credits", "title": "2000 ⚡", "credits": 2000, "usd": 20.0, "stars": 920},
    "pack_3000": {"kind": "credits", "title": "3000 ⚡", "credits": 3000, "usd": 30.0, "stars": 1380},
    "pack_4000": {"kind": "credits", "title": "4000 ⚡", "credits": 4000, "usd": 40.0, "stars": 1840},
    "pack_5000": {"kind": "credits", "title": "5000 ⚡", "credits": 5000, "usd": 50.0, "stars": 2300},
}


def design(title: str, body: str) -> str:
    return f"""
<pre>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷{title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{body}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐SYLVEX AI creator bot • top ai creation platform©️
</pre>
<a href="https://t.me/sylvexai_bot">Official Bot</a>
"""

def shop_item(pack_id: str):
    return SHOP_ITEMS.get((pack_id or "").strip())


def shop_payload(provider: str, telegram_id: int, pack_id: str, item: dict) -> str:
    if item["kind"] == "subscription":
        return f"sylvex_{provider}_sub:{telegram_id}:{item['plan_key']}:{item['usd']:.2f}"
    return f"sylvex_{provider}_credits:{telegram_id}:{item['credits']}:{item['usd']:.2f}"


def bot_stars_payload(telegram_id: int, item: dict, charge_id: str = None) -> str:
    if item["kind"] == "subscription":
        payload = f"sylvex_sub:{telegram_id}:{item['plan_key']}:{item['stars']}"
    else:
        payload = f"sylvex_stars:{telegram_id}:{item['credits']}:{item['stars']}"
    if charge_id:
        payload = f"{payload}:{charge_id}"
    return payload


def parse_shop_payload(payload: str) -> dict:
    if not payload or not isinstance(payload, str):
        return {}

    parts = payload.split(":")
    if not parts:
        return {}

    result = {
        "kind": None,
        "provider": None,
        "plan_key": None,
        "credits": 0,
        "charge_id": None,
    }

    key = parts[0] or ""
    if key.startswith("sylvex_") and key.endswith("_sub"):
        result["kind"] = "subscription"
        result["provider"] = key[len("sylvex_"):-len("_sub")]
    elif key.startswith("sylvex_") and key.endswith("_credits"):
        result["kind"] = "credits"
        result["provider"] = key[len("sylvex_"):-len("_credits")]
    elif key == "sylvex_sub":
        result["kind"] = "subscription"
    elif key == "sylvex_stars":
        result["kind"] = "credits"
    else:
        return {}

    if result["kind"] == "subscription":
        if len(parts) >= 3:
            result["plan_key"] = parts[2]
        if len(parts) >= 5:
            result["charge_id"] = parts[4]
    else:
        if len(parts) >= 3:
            try:
                result["credits"] = int(parts[2] or 0)
            except Exception:
                result["credits"] = 0
        if len(parts) >= 5:
            result["charge_id"] = parts[4]

    return result


def _has_subscription_purchase(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 1
            FROM purchases
            WHERE telegram_id = %s
              AND payload LIKE 'sylvex_%%sub:%%'
            LIMIT 1
        """, (telegram_id,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def _restore_active_subscription(telegram_id: int) -> bool:
    if not DATABASE_URL or not telegram_id:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT provider, payload, amount, currency, charge_id, created_at
            FROM purchases
            WHERE telegram_id = %s
              AND payload LIKE 'sylvex_%%sub:%%'
            ORDER BY created_at DESC
            LIMIT 1
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    item = SHOP_ITEMS.get("sub_month")
    charge_id = None
    provider = "recovery"
    amount = 0
    currency = "REC"
    payload = None

    if row:
        payload_str = row[1] or ""
        parsed = parse_shop_payload(payload_str)
        plan_key = parsed.get("plan_key") or "month"
        item = SHOP_ITEMS.get(f"sub_{plan_key}") or SHOP_ITEMS.get("sub_month")
        charge_id = row[4] or f"recovery_sub_{telegram_id}_{int(row[5].timestamp()) if row[5] else 0}"
        provider = row[0] or "telegram_stars"
        amount = row[2] or 0
        currency = row[3] or "USD"
        payload = payload_str
    else:
        item = SHOP_ITEMS.get("sub_month")
        charge_id = f"recovery_sub_month_{telegram_id}"
        payload = bot_stars_payload(telegram_id, item, charge_id)

    if not item or not charge_id:
        return False

    inserted = activate_subscription(
        telegram_id=telegram_id,
        item=item,
        provider=provider,
        amount=amount,
        currency=currency,
        payload=payload,
        charge_id=charge_id,
    )

    if inserted and item.get("bonus_credits"):
        add_user_balance(telegram_id, int(item["bonus_credits"]))
        log_user_event(
            telegram_id=telegram_id,
            source="system",
            event_type="subscription_restored",
            event_name=f"restore_{item.get('plan_key')}",
            payload={
                "subscription_type": item.get("plan_key"),
                "charge_id": charge_id,
            },
        )
        log_user_event(
            telegram_id=telegram_id,
            source="system",
            event_type="credits_added",
            event_name="subscription_bonus_restored",
            payload={
                "credits": int(item["bonus_credits"]),
                "charge_id": charge_id,
            },
        )
    return inserted


def create_telegram_stars_invoice_link(telegram_id: int, pack_id: str, item: dict, charge_id: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
        json={
            "title": item["title"],
            "description": f"Оплата {item['title']} в SYLVEX.",
            "payload": bot_stars_payload(telegram_id, item, charge_id),
            "provider_token": "",
            "currency": "XTR",
            "prices": [
                {
                    "label": item["title"],
                    "amount": int(item["stars"]),
                }
            ],
        },
        timeout=30,
    )

    data = response.json()
    if response.status_code >= 400 or not data.get("ok"):
        raise RuntimeError(str(data))

    return data["result"]


def crypto_pay_request(method: str, payload=None):
    if not CRYPTO_API_KEY:
        raise RuntimeError("CRYPTO_API_KEY / CRIPTO_API_KEY is not configured")

    response = requests.post(
        f"{CRYPTO_PAY_API_URL}/{method}",
        headers={
            "Crypto-Pay-API-Token": CRYPTO_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload or {},
        timeout=30,
    )
    data = response.json()
    if response.status_code >= 400 or not data.get("ok"):
        raise RuntimeError(str(data))
    return data.get("result")


def crypto_invoice_url(invoice: dict) -> str:
    return (
        invoice.get("mini_app_invoice_url")
        or invoice.get("bot_invoice_url")
        or invoice.get("web_app_invoice_url")
        or ""
    )


def create_crypto_invoice(telegram_id: int, pack_id: str, item: dict) -> dict:
    invoice = crypto_pay_request(
        "createInvoice",
        {
            "asset": "USDT",
            "amount": f"{item['usd']:.2f}",
            "description": f"SYLVEX {item['title']}",
            "payload": shop_payload("crypto", telegram_id, pack_id, item),
            "expires_in": 1800,
        },
    )
    if not crypto_invoice_url(invoice):
        raise RuntimeError("Crypto Pay did not return invoice URL")
    return invoice


def get_crypto_invoice(invoice_id: int):
    result = crypto_pay_request("getInvoices", {"invoice_ids": str(invoice_id)})
    if isinstance(result, dict):
        items = result.get("items") or []
        if items:
            return items[0]
        if result.get("invoice_id"):
            return result
    return None


def ensure_user_events_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_events (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_name TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def ensure_payment_tables():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            provider TEXT NOT NULL,
            credits INTEGER DEFAULT 0,
            amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            payload TEXT,
            charge_id TEXT UNIQUE,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            subscription_type TEXT,
            payment_method TEXT,
            amount INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            starts_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            status TEXT DEFAULT 'active',
            charge_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paypal_orders (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            pack_id TEXT NOT NULL,
            purchase_type TEXT NOT NULL,
            paypal_order_id TEXT UNIQUE NOT NULL,
            paypal_capture_id TEXT UNIQUE,
            amount INTEGER NOT NULL,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'created',
            checkout_url TEXT,
            payload TEXT,
            raw_event JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS paypal_subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            pack_id TEXT NOT NULL DEFAULT 'sub_month',
            plan_id TEXT NOT NULL,
            paypal_subscription_id TEXT UNIQUE NOT NULL,
            amount INTEGER NOT NULL DEFAULT 500,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'pending',
            payload TEXT,
            raw_event JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _sanitize_event_payload(value, max_text=512, max_items=20, depth=3):
    if depth <= 0:
        return None
    if isinstance(value, dict):
        sanitized = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= max_items:
                break
            sanitized[str(k)] = _sanitize_event_payload(v, max_text, max_items, depth - 1)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_event_payload(v, max_text, max_items, depth - 1) for v in value[:max_items]]
    if isinstance(value, str):
        return value if len(value) <= max_text else value[:max_text] + '…'
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:max_text]


def log_user_event(
    telegram_id: int,
    source: str,
    event_type: str,
    event_name: str = "",
    payload: Optional[dict] = None,
):
    if not DATABASE_URL or not telegram_id or not source or not event_type:
        return

    ensure_user_events_table()
    try:
        payload = payload or {}
        sanitized = _sanitize_event_payload(payload)
        payload_str = json.dumps(sanitized, ensure_ascii=False)

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO user_events (telegram_id, source, event_type, event_name, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (telegram_id, source, event_type, event_name or None, payload_str),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        print("LOG EVENT FAILED:", exc)


def _to_iso(v):
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:
        try:
            return str(v)
        except Exception:
            return None


def ensure_user_profiles_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            telegram_id BIGINT PRIMARY KEY,
            display_name TEXT,
            custom_avatar_url TEXT,
            theme_preference JSONB DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_user_profile(telegram_id: int) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_profiles_table()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT display_name, custom_avatar_url, theme_preference
            FROM user_profiles
            WHERE telegram_id = %s
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return {}

    theme = row[2] or {}
    if isinstance(theme, str):
        try:
            theme = json.loads(theme)
        except Exception:
            theme = {}

    return {
        "display_name": row[0],
        "custom_avatar_url": row[1],
        "theme_preference": theme,
    }


def save_user_profile(telegram_id: int, display_name=None, custom_avatar_url=None, theme_preference=None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    ensure_user_profiles_table()

    theme_json = None
    if theme_preference is not None:
        theme_json = json.dumps(theme_preference if isinstance(theme_preference, dict) else {}, ensure_ascii=False)

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_profiles (telegram_id, display_name, custom_avatar_url, theme_preference, updated_at)
            VALUES (
                %s,
                %s,
                %s,
                COALESCE(%s::jsonb, '{}'::jsonb),
                NOW()
            )
            ON CONFLICT (telegram_id) DO UPDATE
            SET display_name = COALESCE(EXCLUDED.display_name, user_profiles.display_name),
                custom_avatar_url = COALESCE(EXCLUDED.custom_avatar_url, user_profiles.custom_avatar_url),
                theme_preference = COALESCE(EXCLUDED.theme_preference, user_profiles.theme_preference),
                updated_at = NOW()
        """, (telegram_id, display_name, custom_avatar_url, theme_json))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return get_user_profile(telegram_id)


def ensure_user_referrals_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_referrals (
            telegram_id BIGINT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            activated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def referral_code_for(telegram_id: int) -> str:
    digest = hashlib.sha1(f"sylvex:{telegram_id}".encode("utf-8")).hexdigest()[:10]
    return f"sylvex_{digest}"


def get_referral_state(telegram_id: int, activate: bool = False) -> dict:
    if not telegram_id:
        return {}

    code = referral_code_for(telegram_id)
    link = f"https://t.me/sylvexai_bot?start={code}"

    if not DATABASE_URL:
        return {
            "ok": True,
            "telegram_id": telegram_id,
            "code": code,
            "link": link,
            "referrals_count": 0,
            "tokens_earned": 0,
            "activated_at": None,
        }

    ensure_user_exists(telegram_id)
    ensure_user_referrals_table()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_referrals (telegram_id, code, activated_at)
            VALUES (%s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (telegram_id) DO UPDATE
            SET activated_at = CASE
                WHEN %s AND user_referrals.activated_at IS NULL THEN NOW()
                ELSE user_referrals.activated_at
            END
            RETURNING activated_at
        """, (telegram_id, code, activate, activate))
        row = cursor.fetchone()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "code": code,
        "link": link,
        "referrals_count": 0,
        "tokens_earned": 0,
        "activated_at": _to_iso(row[0]) if row and row[0] else None,
    }


def get_user_state(telegram_id: int, username: str = None, first_name: str = None) -> dict:
    if not DATABASE_URL or not telegram_id:
        return {}

    ensure_user_exists(telegram_id)
    if username or first_name:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE users
                SET username = COALESCE(%s, username),
                    first_name = COALESCE(%s, first_name)
                WHERE telegram_id = %s
            """, (username, first_name, telegram_id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, username, first_name, balance, subscription, created_at
            FROM users
            WHERE telegram_id = %s
        """, (telegram_id,))
        user_row = cursor.fetchone()
        if not user_row:
            return {}

        cursor.execute("""
            SELECT subscription_type, expires_at::timestamp
            FROM subscriptions
            WHERE telegram_id = %s
              AND status = 'active'
              AND expires_at::timestamp > NOW()
            ORDER BY expires_at::timestamp DESC
            LIMIT 1
        """, (telegram_id,))
        active_sub = cursor.fetchone()

        if active_sub:
            cursor.execute("""
                UPDATE users
                SET subscription = COALESCE(%s, 'active')
                WHERE telegram_id = %s
            """, (active_sub[0], telegram_id))
            conn.commit()
        elif (str(user_row[4] or '').lower() == 'active' or _has_subscription_purchase(telegram_id)):
            restored = _restore_active_subscription(telegram_id)
            if restored:
                cursor.execute("""
                    SELECT subscription_type, expires_at::timestamp
                    FROM subscriptions
                    WHERE telegram_id = %s
                      AND status = 'active'
                      AND expires_at::timestamp > NOW()
                    ORDER BY expires_at::timestamp DESC
                    LIMIT 1
                """, (telegram_id,))
                active_sub = cursor.fetchone()
                if active_sub:
                    cursor.execute("""
                        UPDATE users
                        SET subscription = COALESCE(%s, 'active')
                        WHERE telegram_id = %s
                    """, (active_sub[0], telegram_id))
                    conn.commit()

        cursor.execute("""
            SELECT COUNT(*)
            FROM generations
            WHERE telegram_id = %s
        """, (telegram_id,))
        total_generations = cursor.fetchone()[0] or 0

        try:
            cursor.execute("""
                SELECT COALESCE(SUM(credits), 0)
                FROM purchases
                WHERE telegram_id = %s
                  AND status = 'completed'
                  AND COALESCE(credits, 0) < 0
            """, (telegram_id,))
            tokens_spent = abs(cursor.fetchone()[0] or 0)
        except Exception:
            tokens_spent = 0

        cursor.execute("""
            SELECT event_type, event_name, source, payload, created_at
            FROM user_events
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (telegram_id,))
        events = cursor.fetchall()

        cursor.execute("""
            SELECT provider, credits, amount, currency, payload, charge_id, status, created_at
            FROM purchases
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (telegram_id,))
        purchases = cursor.fetchall()

        cursor.execute("""
            SELECT generation_type, prompt, status, created_at
            FROM generations
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (telegram_id,))
        generations = cursor.fetchall()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    profile = get_user_profile(telegram_id)
    subscription_status = "active" if active_sub else "free"
    result = {
        "telegram_id": user_row[0],
        "username": user_row[1],
        "first_name": user_row[2],
        "balance": user_row[3] or 0,
        "status": "active" if active_sub else (user_row[4] or "free"),
        "subscription_status": subscription_status,
        "subscription_plan": active_sub[0] if active_sub else None,
        "subscription_expires_at": _to_iso(active_sub[1]) if active_sub and active_sub[1] else None,
        "display_name": profile.get("display_name"),
        "custom_avatar_url": profile.get("custom_avatar_url"),
        "theme_preference": profile.get("theme_preference") or {},
        "created_at": user_row[5],
        "total_generations": total_generations,
        "generations_count": total_generations,
        "tokens_spent": tokens_spent,
        "referrals_count": 0,
        "last_actions": [
            {
                "event_type": row[0],
                "event_name": row[1],
                "source": row[2],
                "payload": row[3],
                "created_at": _to_iso(row[4]) if row[4] else None,
            }
            for row in events
        ],
        "last_purchases": [
            {
                "provider": row[0],
                "credits": row[1],
                "amount": row[2],
                "currency": row[3],
                "payload": row[4],
                "charge_id": row[5],
                "status": row[6],
                "created_at": _to_iso(row[7]) if row[7] else None,
            }
            for row in purchases
        ],
        "last_generations": [
            {
                "generation_type": row[0],
                "prompt": row[1],
                "status": row[2],
                "created_at": _to_iso(row[3]) if row[3] else None,
            }
            for row in generations
        ],
    }
    return result


def create_purchase_once(telegram_id: int, provider: str, credits: int, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO purchases (telegram_id, provider, credits, amount, currency, payload, charge_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed')
            ON CONFLICT (charge_id) DO NOTHING
        """, (telegram_id, provider, credits, amount, currency, payload, charge_id))
        created = cursor.rowcount > 0
        conn.commit()
        return created
    finally:
        cursor.close()
        conn.close()


def activate_subscription(telegram_id: int, item: dict, provider: str, amount: int, currency: str, payload: str, charge_id: str) -> bool:
    if not DATABASE_URL:
        return False

    ensure_user_exists(telegram_id)
    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE telegram_id = %s
              AND status = 'active'
        """, (telegram_id,))
        cursor.execute("""
            INSERT INTO subscriptions (
                telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id
            )
            VALUES (
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP + (%s || ' days')::interval, 'active', %s
            )
            ON CONFLICT (charge_id) DO NOTHING
        """, (telegram_id, item["plan_key"], provider, amount, currency, item["days"], charge_id))
        inserted = cursor.rowcount > 0
        cursor.execute("UPDATE users SET subscription = %s WHERE telegram_id = %s", (item.get("plan_key") or "active", telegram_id))
        conn.commit()
        return inserted
    finally:
        cursor.close()
        conn.close()




def ensure_user_exists(telegram_id: int):
    if not DATABASE_URL or not telegram_id:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (telegram_id, first_name, balance, subscription)
            VALUES (%s, 'Developer', 0, 'free')
            ON CONFLICT (telegram_id) DO NOTHING
        """, (telegram_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def add_user_balance(telegram_id: int, credits: int):
    if not DATABASE_URL or not telegram_id or not credits:
        return

    ensure_user_exists(telegram_id)
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s",
            (credits, telegram_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def finalize_shop_payment(telegram_id: int, provider: str, item: dict, amount: int, currency: str, payload: str, charge_id: str):
    credits = int(item.get("credits") or 0)
    bonus_credits = int(item.get("bonus_credits") or 0)
    created = create_purchase_once(telegram_id, provider, credits or bonus_credits, amount, currency, payload, charge_id)

    if not created:
        return False

    log_user_event(
        telegram_id=telegram_id,
        source="payment",
        event_type="payment_success",
        event_name="payment_success",
        payload={
            "provider": provider,
            "pack_id": item.get("plan_key") or f"credits_{credits}",
            "amount": amount,
            "currency": currency,
            "charge_id": charge_id,
            "payload": payload,
        },
    )

    if item["kind"] == "subscription":
        activated = activate_subscription(telegram_id, item, provider, amount, currency, payload, charge_id)
        if activated:
            log_user_event(
                telegram_id=telegram_id,
                source="payment",
                event_type="subscription_activated",
                event_name=f"activate_{item.get('plan_key')}",
                payload={
                    "subscription_type": item.get("plan_key"),
                    "expires_in_days": item.get("days"),
                    "charge_id": charge_id,
                },
            )
        if bonus_credits:
            add_user_balance(telegram_id, bonus_credits)
            log_user_event(
                telegram_id=telegram_id,
                source="payment",
                event_type="credits_added",
                event_name="subscription_bonus_credits",
                payload={
                    "credits": bonus_credits,
                    "charge_id": charge_id,
                },
            )
    else:
        add_user_balance(telegram_id, credits)
        log_user_event(
            telegram_id=telegram_id,
            source="payment",
            event_type="credits_added",
            event_name="credits_purchase",
            payload={
                "credits": credits,
                "charge_id": charge_id,
            },
        )

    return True


def reset_developer_subscription(telegram_id: int, reset_credits: bool = False) -> dict:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_payment_tables()
    ensure_user_exists(telegram_id)

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE telegram_id = %s
              AND status = 'active'
        """, (telegram_id,))
        cancelled = cursor.rowcount

        if reset_credits:
            cursor.execute("""
                UPDATE users
                SET subscription = 'free', balance = 0
                WHERE telegram_id = %s
            """, (telegram_id,))
        else:
            cursor.execute("""
                UPDATE users
                SET subscription = 'free'
                WHERE telegram_id = %s
            """, (telegram_id,))

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "cancelled_subscriptions": cancelled,
        "reset_credits": reset_credits,
    }


async def poll_crypto_invoice(invoice_id: int, telegram_id: int, pack_id: str):
    item = shop_item(pack_id)
    if not item:
        return

    for _ in range(90):
        await asyncio.sleep(20)
        try:
            invoice = get_crypto_invoice(invoice_id)
        except Exception as exc:
            print("MINIAPP CRYPTO POLL ERROR:", exc)
            return
        if not invoice:
            return
        status = invoice.get("status")
        if status == "paid":
            finalize_shop_payment(
                telegram_id=telegram_id,
                provider="crypto_pay",
                item=item,
                amount=int(round(float(invoice.get("amount") or 0) * 100)),
                currency=invoice.get("asset") or "USDT",
                payload=invoice.get("payload") or "",
                charge_id=f"crypto_invoice_{invoice_id}",
            )
            # Sync user state after successful crypto payment so frontend/bot read updated state
            try:
                sync_user_to_db({
                    "telegram_id": telegram_id,
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("CRYPTO POLL: sync failed", exc)
            return
        if status == "expired":
            return


def paypal_configured() -> bool:
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


def paypal_access_token(api_base: str = None) -> str:
    if not paypal_configured():
        raise RuntimeError("PayPal credentials are not configured")

    base = api_base or PAYPAL_API_BASE
    response = requests.post(
        f"{base}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=30,
    )
    if response.status_code >= 400:
        print("PAYPAL TOKEN ERROR:", response.status_code, response.text[:1000])
        raise RuntimeError("PayPal token request failed")

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("PayPal token response did not include access_token")
    return token


def paypal_headers(api_base: str = None) -> dict:
    return {
        "Authorization": f"Bearer {paypal_access_token(api_base)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def paypal_return_url(telegram_id: int, pack_id: str, status: str) -> str:
    params = urllib.parse.urlencode({
        "view": "shop",
        "payment": status,
        "provider": "paypal",
        "pack_id": pack_id or "",
        "telegram_id": str(telegram_id or ""),
    })
    return SHOP_WEBAPP_URL + ("&" if "?" in SHOP_WEBAPP_URL else "?") + params


def paypal_purchase_type(item: dict) -> str:
    return "subscription" if item.get("kind") == "subscription" else "tokens"


def create_paypal_order(telegram_id: int, pack_id: str, item: dict) -> dict:
    amount_value = f"{float(item['usd']):.2f}"
    payload = shop_payload("paypal", telegram_id, pack_id, item)
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": pack_id,
                "custom_id": payload,
                "description": item.get("title") or "SYLVEX purchase",
                "amount": {
                    "currency_code": "USD",
                    "value": amount_value,
                },
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "brand_name": "SYLVEX",
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW",
                    "return_url": paypal_return_url(telegram_id, pack_id, "success"),
                    "cancel_url": paypal_return_url(telegram_id, pack_id, "cancel"),
                }
            }
        },
    }
    response = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        headers={**paypal_headers(), "PayPal-Request-Id": f"sylvex-{telegram_id}-{pack_id}-{uuid4().hex}"},
        json=body,
        timeout=30,
    )
    if response.status_code >= 400:
        print("PAYPAL ORDER ERROR:", response.status_code, response.text[:1000])
        raise RuntimeError("PayPal order request failed")
    return response.json()


def paypal_approve_url(order: dict) -> str:
    for link in order.get("links") or []:
        if link.get("rel") in {"approve", "payer-action"} and link.get("href"):
            return link["href"]
    return ""


def save_paypal_order(telegram_id: int, pack_id: str, item: dict, order: dict, checkout_url: str):
    if not DATABASE_URL:
        return

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paypal_orders (
                telegram_id, pack_id, purchase_type, paypal_order_id, amount, currency, status, checkout_url, payload, raw_event
            )
            VALUES (%s, %s, %s, %s, %s, 'USD', %s, %s, %s, %s::jsonb)
            ON CONFLICT (paypal_order_id) DO UPDATE
            SET checkout_url = EXCLUDED.checkout_url,
                status = EXCLUDED.status,
                raw_event = EXCLUDED.raw_event,
                updated_at = CURRENT_TIMESTAMP
        """, (
            telegram_id,
            pack_id,
            paypal_purchase_type(item),
            order.get("id"),
            int(round(float(item["usd"]) * 100)),
            (order.get("status") or "created").lower(),
            checkout_url,
            shop_payload("paypal", telegram_id, pack_id, item),
            json.dumps(order),
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def verify_paypal_webhook(headers, event: dict) -> bool:
    if not PAYPAL_WEBHOOK_ID:
        print("PAYPAL WEBHOOK: PAYPAL_WEBHOOK_ID is not configured")
        return False

    required = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
    }
    if not all(required.values()):
        return False

    body = {
        **required,
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    bases = [PAYPAL_API_BASE]
    alternate = "https://api-m.paypal.com" if PAYPAL_API_BASE != "https://api-m.paypal.com" else "https://api-m.sandbox.paypal.com"
    bases.append(alternate)
    for base in bases:
        try:
            response = requests.post(
                f"{base}/v1/notifications/verify-webhook-signature",
                headers=paypal_headers(base),
                json=body,
                timeout=30,
            )
        except Exception as exc:
            print("PAYPAL WEBHOOK VERIFY ERROR:", base, exc)
            continue
        if response.status_code >= 400:
            print("PAYPAL WEBHOOK VERIFY ERROR:", base, response.status_code, response.text[:1000])
            continue
        if response.json().get("verification_status") == "SUCCESS":
            return True
    return False


def paypal_capture_details(resource: dict) -> dict:
    order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    capture_id = resource.get("id")
    amount = resource.get("amount") or {}
    return {
        "order_id": order_id,
        "capture_id": capture_id,
        "status": resource.get("status") or "",
        "amount": int(round(float(amount.get("value") or 0) * 100)),
        "currency": amount.get("currency_code") or "USD",
    }


def finalize_paypal_capture(event: dict) -> bool:
    resource = event.get("resource") or {}
    details = paypal_capture_details(resource)
    order_id = details["order_id"]
    capture_id = details["capture_id"]
    if not order_id or not capture_id:
        return False
    if (details["status"] or "").upper() != "COMPLETED":
        return False
    if not DATABASE_URL:
        return False

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, pack_id, amount, currency, status, payload
            FROM paypal_orders
            WHERE paypal_order_id = %s
        """, (order_id,))
        row = cursor.fetchone()
        if not row:
            return False

        telegram_id, pack_id, stored_amount, stored_currency, status, payload = row
        if status == "completed":
            return False
        item = shop_item(pack_id)
        if not item:
            return False

        charge_id = f"paypal_capture_{capture_id}"
        created = finalize_shop_payment(
            telegram_id=int(telegram_id),
            provider="paypal",
            item=item,
            amount=details["amount"] or stored_amount,
            currency=details["currency"] or stored_currency or "USD",
            payload=payload or shop_payload("paypal", int(telegram_id), pack_id, item),
            charge_id=charge_id,
        )
        cursor.execute("""
            UPDATE paypal_orders
            SET paypal_capture_id = COALESCE(paypal_capture_id, %s),
                status = CASE WHEN %s THEN 'completed' ELSE status END,
                raw_event = %s::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE paypal_order_id = %s
        """, (capture_id, created, json.dumps(event), order_id))
        conn.commit()
        if created:
            try:
                sync_user_to_db({
                    "telegram_id": int(telegram_id),
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("PAYPAL WEBHOOK: sync failed", exc)
        return created
    finally:
        cursor.close()
        conn.close()


def paypal_subscription_pack_for_plan(plan_id: str, plan_type: str = "") -> str:
    normalized_type = (plan_type or "").strip().lower()
    if plan_id == PAYPAL_PRO_MONTHLY_PLAN_ID or normalized_type in {"month", "monthly"}:
        return "sub_month"
    if plan_id == PAYPAL_PRO_YEARLY_PLAN_ID or normalized_type in {"year", "yearly", "annual"}:
        return "sub_year"
    return ""


def save_paypal_subscription(telegram_id: int, subscription_id: str, plan_id: str, plan_type: str = "") -> bool:
    if not DATABASE_URL:
        return False

    pack_id = paypal_subscription_pack_for_plan(plan_id, plan_type)
    item = shop_item(pack_id)
    if not item or not pack_id:
        return False

    ensure_payment_tables()
    ensure_user_exists(telegram_id)
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paypal_subscriptions (
                telegram_id, pack_id, plan_id, paypal_subscription_id, amount, currency, status, payload
            )
            VALUES (%s, %s, %s, %s, %s, 'USD', 'pending', %s)
            ON CONFLICT (paypal_subscription_id) DO UPDATE
            SET telegram_id = EXCLUDED.telegram_id,
                pack_id = EXCLUDED.pack_id,
                plan_id = EXCLUDED.plan_id,
                status = CASE
                    WHEN paypal_subscriptions.status = 'active' THEN paypal_subscriptions.status
                    ELSE 'pending'
                END,
                updated_at = CURRENT_TIMESTAMP
        """, (
            telegram_id,
            pack_id,
            plan_id,
            subscription_id,
            int(round(float(item["usd"]) * 100)),
            shop_payload("paypal_subscription", telegram_id, pack_id, item),
        ))
        conn.commit()
        return True
    finally:
        cursor.close()
        conn.close()


def paypal_subscription_id_from_event(event: dict) -> str:
    resource = event.get("resource") or {}
    event_type = event.get("event_type") or ""
    if event_type.startswith("BILLING.SUBSCRIPTION."):
        return resource.get("id") or ""
    return (
        resource.get("billing_agreement_id")
        or resource.get("billing_subscription_id")
        or resource.get("subscription_id")
        or resource.get("supplementary_data", {}).get("related_ids", {}).get("billing_agreement_id")
        or ""
    )


def paypal_subscription_payment_details(event: dict) -> dict:
    resource = event.get("resource") or {}
    amount = resource.get("amount") or {}
    if "total" in amount:
        value = amount.get("total")
        currency = amount.get("currency") or "USD"
    else:
        value = amount.get("value")
        currency = amount.get("currency_code") or "USD"
    charge_id = resource.get("id") or paypal_subscription_id_from_event(event)
    try:
        cents = int(round(float(value or 5.0) * 100))
    except Exception:
        cents = 500
    return {"amount": cents, "currency": currency, "charge_id": charge_id}


def activate_paypal_subscription_from_event(event: dict) -> bool:
    subscription_id = paypal_subscription_id_from_event(event)
    if not subscription_id or not DATABASE_URL:
        return False

    details = paypal_subscription_payment_details(event)
    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT telegram_id, pack_id, amount, currency, status, payload
            FROM paypal_subscriptions
            WHERE paypal_subscription_id = %s
        """, (subscription_id,))
        row = cursor.fetchone()
        if not row:
            return False

        telegram_id, pack_id, stored_amount, stored_currency, status, payload = row
        item = shop_item(pack_id or "sub_month")
        if not item:
            return False

        event_type = event.get("event_type") or ""
        if status == "active":
            cursor.execute("""
                SELECT expires_at
                FROM subscriptions
                WHERE telegram_id = %s
                  AND status = 'active'
                ORDER BY expires_at DESC
                LIMIT 1
            """, (telegram_id,))
            active_row = cursor.fetchone()
            if active_row and active_row[0]:
                cursor.execute("SELECT CURRENT_TIMESTAMP + INTERVAL '7 days'")
                renewal_window = cursor.fetchone()[0]
                if active_row[0] > renewal_window:
                    return False

        charge_prefix = "paypal_sale" if event_type == "PAYMENT.SALE.COMPLETED" else "paypal_subscription"
        charge_source = details["charge_id"] or subscription_id
        charge_id = f"{charge_prefix}_{charge_source}"
        created = finalize_shop_payment(
            telegram_id=int(telegram_id),
            provider="paypal_subscription",
            item=item,
            amount=details["amount"] or stored_amount,
            currency=details["currency"] or stored_currency or "USD",
            payload=payload or shop_payload("paypal_subscription", int(telegram_id), pack_id, item),
            charge_id=charge_id,
        )
        cursor.execute("""
            UPDATE paypal_subscriptions
            SET status = CASE WHEN %s THEN 'active' ELSE status END,
                raw_event = %s::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE paypal_subscription_id = %s
        """, (created, json.dumps(event), subscription_id))
        conn.commit()
        if created:
            try:
                sync_user_to_db({
                    "telegram_id": int(telegram_id),
                    "username": None,
                    "first_name": None,
                    "status": "free",
                    "balance": 0,
                })
            except Exception as exc:
                print("PAYPAL SUBSCRIPTION WEBHOOK: sync failed", exc)
        return created
    finally:
        cursor.close()
        conn.close()

def save_kling_settings_to_db(data):
    print("SAVE_KLING_FUNCTION_STARTED")
    duration_raw = str(data.get("duration", "5"))
    duration = int(duration_raw.split()[0])

    sound = 1 if data.get("sound") else 0
    prompt_enhance = 1 if data.get("prompt_enhance") else 0

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO user_ai_settings (
        telegram_id,
        kling_model,
        kling_mode,
        kling_ratio,
        kling_quality,
        kling_duration,
        kling_sound,
        kling_prompt_enhance
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (telegram_id) DO UPDATE SET
        kling_model = EXCLUDED.kling_model,
        kling_mode = EXCLUDED.kling_mode,
        kling_ratio = EXCLUDED.kling_ratio,
        kling_quality = EXCLUDED.kling_quality,
        kling_duration = EXCLUDED.kling_duration,
        kling_sound = EXCLUDED.kling_sound,
        kling_prompt_enhance = EXCLUDED.kling_prompt_enhance
    """, (
        int(data.get("telegram_id")),
        data.get("model"),
        data.get("mode"),
        data.get("ratio"),
        data.get("quality"),
        duration,
        sound,
        prompt_enhance
    ))

    conn.commit()

@app.get("/")
async def root():
    return RedirectResponse("/webapp/index.html")


@app.get("/cabinet")
async def cabinet():
    return RedirectResponse("/webapp/index.html")

@app.get("/shop")
async def shop():
    return RedirectResponse("/webapp/index.html?view=shop")

@app.get("/payments")
async def payments():
    return FileResponse(WEBAPP_DIR / "payments.html")

@app.get("/elevenlabs")
async def elevenlabs_page():
    return FileResponse(WEBAPP_DIR / "elevenlabs.html")

@app.get("/heygen-voice")
async def heygen_voice_page():
    return FileResponse(WEBAPP_DIR / "heygen-voice.html")

def ensure_elevenlabs_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_voice_settings (
            telegram_id BIGINT,
            provider TEXT DEFAULT 'elevenlabs',
            voice_id TEXT,
            voice_name TEXT,
            model_id TEXT,
            stability REAL DEFAULT 0.5,
            similarity_boost REAL DEFAULT 0.75,
            style REAL DEFAULT 0.0,
            speed REAL DEFAULT 1.0,
            speaker_boost INTEGER DEFAULT 1,
            language TEXT DEFAULT 'ru',
            output_format TEXT DEFAULT 'mp3_44100_128',
            updated_at TEXT,
            PRIMARY KEY (telegram_id, provider)
        )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def default_elevenlabs_settings() -> dict:
    return {
        "voice_id": ELEVENLABS_DEFAULT_VOICE_ID,
        "voice_name": ELEVENLABS_DEFAULT_VOICE_NAME,
        "model_id": ELEVENLABS_DEFAULT_MODEL_ID,
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "speed": 1.0,
        "speaker_boost": True,
        "language": "ru",
        "output_format": ELEVENLABS_DEFAULT_OUTPUT_FORMAT,
    }

def elevenlabs_headers(content_type: str = "application/json") -> dict:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    if content_type:
        headers["Content-Type"] = content_type
    return headers

def fetch_elevenlabs_models() -> list:
    response = requests.get(
        f"{ELEVENLABS_BASE_URL}/v1/models",
        headers=elevenlabs_headers(None),
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)

    data = response.json()
    models = data if isinstance(data, list) else data.get("models", [])
    result = []
    for model in models:
        model_id = model.get("model_id") or model.get("id")
        if not model_id:
            continue
        if model.get("can_do_text_to_speech", True) is False:
            continue
        result.append({
            "model_id": model_id,
            "name": model.get("name") or model_id,
        })
    return result

def fetch_elevenlabs_voices(limit: int = 80) -> list:
    voices = []
    next_page_token = None

    while len(voices) < limit:
        params = {"page_size": min(100, limit - len(voices))}
        if next_page_token:
            params["next_page_token"] = next_page_token

        response = requests.get(
            f"{ELEVENLABS_BASE_URL}/v2/voices",
            headers=elevenlabs_headers(None),
            params=params,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text)

        data = response.json()
        page_voices = data.get("voices") or data.get("data") or []
        voices.extend(page_voices)
        next_page_token = data.get("next_page_token") or data.get("next_cursor")

        if not next_page_token or not data.get("has_more", bool(next_page_token)):
            break

    result = []
    for voice in voices[:limit]:
        labels = voice.get("labels") or {}
        fine_tuning = voice.get("fine_tuning") or {}
        voice_id = voice.get("voice_id")
        if not voice_id:
            continue
        result.append({
            "voice_id": voice_id,
            "name": voice.get("name") or "Voice",
            "category": voice.get("category") or labels.get("category") or "",
            "gender": labels.get("gender") or labels.get("sex") or "",
            "language": labels.get("language") or labels.get("accent") or voice.get("language") or "multilingual",
            "preview_url": voice.get("preview_url") or voice.get("sample_url") or "",
            "is_owner": voice.get("is_owner"),
            "sharing_enabled": voice.get("sharing") is not None,
            "fine_tuning_state": fine_tuning.get("state"),
        })
    return result

def get_elevenlabs_settings_from_db(telegram_id: int) -> dict:
    defaults = default_elevenlabs_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT
            voice_id,
            voice_name,
            model_id,
            stability,
            similarity_boost,
            style,
            speed,
            speaker_boost,
            language,
            output_format
        FROM user_voice_settings
        WHERE telegram_id = %s
          AND provider = 'elevenlabs'
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return defaults

    return {
        "voice_id": row[0] or defaults["voice_id"],
        "voice_name": row[1] or defaults["voice_name"],
        "model_id": row[2] or defaults["model_id"],
        "stability": row[3] if row[3] is not None else defaults["stability"],
        "similarity_boost": row[4] if row[4] is not None else defaults["similarity_boost"],
        "style": row[5] if row[5] is not None else defaults["style"],
        "speed": row[6] if row[6] is not None else defaults["speed"],
        "speaker_boost": bool(row[7]),
        "language": row[8] or defaults["language"],
        "output_format": row[9] or defaults["output_format"],
    }

def save_elevenlabs_settings_to_db(data: dict):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_elevenlabs_table()
    print("ELEVENLABS SETTINGS SAVE REQUEST:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": data.get("model_id"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "speed": data.get("speed"),
        "speaker_boost": data.get("speaker_boost"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
    })
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO user_voice_settings (
            telegram_id,
            provider,
            voice_id,
            voice_name,
            model_id,
            stability,
            similarity_boost,
            style,
            speed,
            speaker_boost,
            language,
            output_format,
            updated_at
        ) VALUES (%s, 'elevenlabs', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()::TEXT)
        ON CONFLICT (telegram_id, provider) DO UPDATE SET
            voice_id = EXCLUDED.voice_id,
            voice_name = EXCLUDED.voice_name,
            model_id = EXCLUDED.model_id,
            stability = EXCLUDED.stability,
            similarity_boost = EXCLUDED.similarity_boost,
            style = EXCLUDED.style,
            speed = EXCLUDED.speed,
            speaker_boost = EXCLUDED.speaker_boost,
            language = EXCLUDED.language,
            output_format = EXCLUDED.output_format,
            updated_at = EXCLUDED.updated_at
        """, (
            int(data.get("telegram_id")),
            data.get("voice_id") or ELEVENLABS_DEFAULT_VOICE_ID,
            data.get("voice_name") or ELEVENLABS_DEFAULT_VOICE_NAME,
            data.get("model_id") or ELEVENLABS_DEFAULT_MODEL_ID,
            float(data.get("stability", 0.5)),
            float(data.get("similarity_boost", 0.75)),
            float(data.get("style", 0.0)),
            float(data.get("speed", 1.0)),
            1 if data.get("speaker_boost", True) else 0,
            data.get("language") or "ru",
            data.get("output_format") or ELEVENLABS_DEFAULT_OUTPUT_FORMAT,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def default_heygen_voice_settings() -> dict:
    return {
        "voice_id": "",
        "voice_name": "Auto",
        "model_id": HEYGEN_VOICE_MODEL_ID,
        "language": HEYGEN_DEFAULT_LANGUAGE,
        "speed": HEYGEN_DEFAULT_SPEED,
        "output_format": HEYGEN_DEFAULT_OUTPUT_FORMAT,
    }

def heygen_headers() -> dict:
    if not HEYGEN_API_KEY:
        raise RuntimeError("HEYGEN_API_KEY is not configured")

    return {
        "x-api-key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def fetch_heygen_voice_page(
    voice_type: str = "public",
    language: str = "",
    gender: str = "",
    token: str = "",
    limit: int = 100,
) -> dict:
    params = {
        "type": voice_type,
        "engine": HEYGEN_VOICE_MODEL_ID,
        "limit": limit,
    }

    if language:
        params["language"] = language
    if gender:
        params["gender"] = gender
    if token:
        params["token"] = token

    response = requests.get(
        f"{HEYGEN_BASE_URL}/voices",
        headers=heygen_headers(),
        params=params,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(response.text)

    data = response.json()
    return {
        "voices": data.get("data") or [],
        "has_more": data.get("has_more", False),
        "next_token": data.get("next_token"),
    }

def fetch_heygen_voices(limit: int = 100) -> list:
    voices = []

    for voice_type in ("public", "private"):
        token = ""
        while len(voices) < limit:
            page = fetch_heygen_voice_page(
                voice_type=voice_type,
                token=token,
                limit=min(100, limit - len(voices)),
            )
            voices.extend(page["voices"])
            if not page["has_more"] or not page["next_token"]:
                break
            token = page["next_token"]

        if len(voices) >= limit:
            break

    result = []
    seen = set()
    for voice in voices[:limit]:
        voice_id = voice.get("voice_id")
        if not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        result.append({
            "voice_id": voice_id,
            "name": voice.get("name") or "Voice",
            "language": voice.get("language") or "",
            "gender": voice.get("gender") or "",
            "type": voice.get("type") or "",
            "preview_audio_url": voice.get("preview_audio_url") or "",
            "support_pause": bool(voice.get("support_pause")),
            "support_locale": bool(voice.get("support_locale")),
        })
    return result

def get_heygen_voice_settings_from_db(telegram_id: int) -> dict:
    defaults = default_heygen_voice_settings()
    if not DATABASE_URL or not telegram_id:
        return defaults

    ensure_elevenlabs_table()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT
            voice_id,
            voice_name,
            model_id,
            speed,
            language,
            output_format
        FROM user_voice_settings
        WHERE telegram_id = %s
          AND provider = 'heygen_voice'
        """, (telegram_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return defaults

    return {
        "voice_id": row[0] or defaults["voice_id"],
        "voice_name": row[1] or defaults["voice_name"],
        "model_id": row[2] or defaults["model_id"],
        "speed": row[3] if row[3] is not None else defaults["speed"],
        "language": row[4] or defaults["language"],
        "output_format": row[5] or defaults["output_format"],
    }

def save_heygen_voice_settings_to_db(data: dict):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    ensure_elevenlabs_table()
    print("HEYGEN VOICE SETTINGS SAVE REQUEST:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": HEYGEN_VOICE_MODEL_ID,
        "speed": data.get("speed"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
    })
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO user_voice_settings (
            telegram_id,
            provider,
            voice_id,
            voice_name,
            model_id,
            speed,
            language,
            output_format,
            updated_at
        ) VALUES (%s, 'heygen_voice', %s, %s, %s, %s, %s, %s, NOW()::TEXT)
        ON CONFLICT (telegram_id, provider) DO UPDATE SET
            voice_id = EXCLUDED.voice_id,
            voice_name = EXCLUDED.voice_name,
            model_id = EXCLUDED.model_id,
            speed = EXCLUDED.speed,
            language = EXCLUDED.language,
            output_format = EXCLUDED.output_format,
            updated_at = EXCLUDED.updated_at
        """, (
            int(data.get("telegram_id")),
            data.get("voice_id") or "",
            data.get("voice_name") or "HeyGen Voice",
            HEYGEN_VOICE_MODEL_ID,
            float(data.get("speed", HEYGEN_DEFAULT_SPEED)),
            data.get("language") or HEYGEN_DEFAULT_LANGUAGE,
            data.get("output_format") or HEYGEN_DEFAULT_OUTPUT_FORMAT,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def safe_log_elevenlabs_preview(data: dict, payload: dict):
    print("ELEVENLABS PREVIEW REQUEST BODY:", {
        "telegram_id": data.get("telegram_id"),
        "voice_id": data.get("voice_id"),
        "voice_name": data.get("voice_name"),
        "model_id": data.get("model_id"),
        "stability": data.get("stability"),
        "similarity_boost": data.get("similarity_boost"),
        "style": data.get("style"),
        "speed": data.get("speed"),
        "speaker_boost": data.get("speaker_boost"),
        "language": data.get("language"),
        "output_format": data.get("output_format"),
        "text_length": len(data.get("text") or ""),
    })
    print("ELEVENLABS PREVIEW PAYLOAD:", {
        "text_length": len(payload.get("text") or ""),
        "model_id": payload.get("model_id"),
        "voice_settings": payload.get("voice_settings"),
    })

@app.get("/api/elevenlabs/bootstrap")
async def elevenlabs_bootstrap(telegram_id: int = 0):
    warnings = []
    try:
        models = fetch_elevenlabs_models()
    except Exception as exc:
        print("ELEVENLABS MODELS LOAD FAILED:", exc)
        warnings.append(f"models: {exc}")
        models = [{
            "model_id": ELEVENLABS_DEFAULT_MODEL_ID,
            "name": "Eleven Multilingual v2",
        }]

    try:
        voices = fetch_elevenlabs_voices()
    except Exception as exc:
        print("ELEVENLABS VOICES LOAD FAILED:", exc)
        warnings.append(f"voices: {exc}")
        voices = [{
            "voice_id": ELEVENLABS_DEFAULT_VOICE_ID,
            "name": ELEVENLABS_DEFAULT_VOICE_NAME,
            "category": "premade",
            "gender": "female",
            "language": "multilingual",
            "preview_url": "",
        }]

    return {
        "success": True,
        "models": models,
        "voices": voices,
        "settings": get_elevenlabs_settings_from_db(telegram_id),
        "defaults": default_elevenlabs_settings(),
        "warnings": warnings,
        "api_available": not warnings,
    }

@app.post("/api/elevenlabs/settings")
async def save_elevenlabs_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)

    save_elevenlabs_settings_to_db(data)
    return {"success": True, "message": "ElevenLabs settings saved"}

@app.post("/api/elevenlabs/preview")
async def elevenlabs_preview(request: Request):
    data = await request.json()
    voice_id = data.get("voice_id") or ELEVENLABS_DEFAULT_VOICE_ID
    model_id = data.get("model_id") or ELEVENLABS_DEFAULT_MODEL_ID
    output_format = data.get("output_format") or ELEVENLABS_DEFAULT_OUTPUT_FORMAT
    text = (data.get("text") or "SYLVEX voice preview.").strip()[:220]

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": float(data.get("stability", 0.5)),
            "similarity_boost": float(data.get("similarity_boost", 0.75)),
            "style": float(data.get("style", 0.0)),
            "speed": float(data.get("speed", 1.0)),
            "use_speaker_boost": bool(data.get("speaker_boost", True)),
        },
    }

    safe_log_elevenlabs_preview(data, payload)
    print("ELEVENLABS PREVIEW SELECTED VOICE:", voice_id)
    print("ELEVENLABS PREVIEW SELECTED MODEL:", model_id)

    try:
        response = requests.post(
            f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}",
            headers=elevenlabs_headers(),
            params={"output_format": output_format},
            json=payload,
            timeout=60,
        )
    except Exception as exc:
        print("ELEVENLABS PREVIEW REQUEST FAILED:", repr(exc))
        return JSONResponse({
            "success": False,
            "error": str(exc),
        }, status_code=502)

    content_type = response.headers.get("content-type", "")
    print("ELEVENLABS PREVIEW HTTP STATUS:", response.status_code)
    print("ELEVENLABS PREVIEW CONTENT-TYPE:", content_type)

    if response.status_code >= 400:
        print("ELEVENLABS PREVIEW ERROR RESPONSE:", response.text[:2000])
        return JSONResponse({
            "success": False,
            "error": response.text,
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
        }, status_code=502)

    if not response.content:
        print("ELEVENLABS PREVIEW EMPTY AUDIO RESPONSE")
        return JSONResponse({
            "success": False,
            "error": "ElevenLabs returned empty audio",
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
        }, status_code=502)

    if "audio" not in content_type and "octet-stream" not in content_type:
        print("ELEVENLABS PREVIEW NON-AUDIO RESPONSE:", response.text[:2000])
        return JSONResponse({
            "success": False,
            "error": "ElevenLabs returned non-audio response",
            "elevenlabs_status": response.status_code,
            "elevenlabs_content_type": content_type,
            "body": response.text[:2000],
        }, status_code=502)

    print("ELEVENLABS PREVIEW AUDIO BYTES:", len(response.content))
    return Response(
        content=response.content,
        media_type=content_type.split(";")[0] if content_type else "audio/mpeg",
        headers={"Cache-Control": "no-store"}
    )

@app.get("/api/heygen-voice/bootstrap")
async def heygen_voice_bootstrap(telegram_id: int = 0):
    warnings = []
    try:
        voices = fetch_heygen_voices()
    except Exception as exc:
        print("HEYGEN VOICE LOAD FAILED:", exc)
        warnings.append(str(exc))
        voices = []

    return {
        "success": True,
        "model": {
            "model_id": HEYGEN_VOICE_MODEL_ID,
            "name": "HeyGen Starfish",
        },
        "voices": voices,
        "settings": get_heygen_voice_settings_from_db(telegram_id),
        "defaults": default_heygen_voice_settings(),
        "warnings": warnings,
        "api_available": not warnings,
    }

@app.post("/api/heygen-voice/settings")
async def save_heygen_voice_settings(request: Request):
    data = await request.json()
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JSONResponse({"success": False, "error": "telegram_id is required"}, status_code=400)
    if not data.get("voice_id"):
        return JSONResponse({"success": False, "error": "voice_id is required"}, status_code=400)

    save_heygen_voice_settings_to_db(data)
    return {"success": True, "message": "HeyGen Voice settings saved"}

@app.get("/api/public/config")
async def public_config():
    return {
        "ok": True,
        "webapp_url": WEBAPP_URL,
        "payment_webapp_url": PAYMENT_WEBAPP_URL,
        "shop_webapp_url": SHOP_WEBAPP_URL
    }

@app.get("/api/payment-links")
async def payment_links():
    products = []
    for pack_id, item in SHOP_ITEMS.items():
        products.append({
            "id": pack_id,
            "pack_id": pack_id,
            "name": item["title"],
            "description": "Подписка SYLVEX Pro" if item["kind"] == "subscription" else f"{item['credits']} токенов SYLVEX",
            "price": int(round(float(item["usd"]) * 100)),
            "price_formatted": f"${float(item['usd']):.2f}",
            "is_subscription": item["kind"] == "subscription",
            "purchase_type": paypal_purchase_type(item),
        })

    return {
        "success": True,
        "source": "paypal",
        "products": products,
        "packages": {},
    }

@app.post("/save-settings")
async def save_settings(request: Request):
    data = await request.json()
    print("SETTINGS RECEIVED:", data)

    save_kling_settings_to_db(data)
    title = "✅ НАСТРОЙКИ KLING СОХРАНЕНЫ"

    print("SETTINGS SAVED TO POSTGRES")

    telegram_id = data.get("telegram_id")
    message_id = data.get("message_id")

    body = (
        f"Модель: {data.get('model')}\n"
        f"Режим: {data.get('mode')}\n"
        f"Формат: {data.get('ratio')}\n"
        f"Качество: {data.get('quality')}\n"
        f"Длительность: {data.get('duration')}\n"
        f"Звук: {'Вкл' if data.get('sound') else 'Выкл'}\n"
        f"Prompt Enhance: {'Вкл' if data.get('prompt_enhance') else 'Выкл'}\n\n"
        "Теперь отправьте описание видео."
    )

    text = design(title, body)

    return {
        "success": True,
        "message": "✅ Настройки Kling сохранены"
    }

def verify_telegram_init_data(init_data: str) -> bool:
    if not init_data or not BOT_TOKEN:
        return False

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False

    data_check = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated_hash, received_hash)

def fallback_public_user(payload: dict) -> dict:
    unsafe = payload.get("initDataUnsafe") or {}
    tg_user = unsafe.get("user") or {}
    return {
        "telegram_id": tg_user.get("id") or 0,
        "username": tg_user.get("username"),
        "first_name": tg_user.get("first_name") or "Guest",
        "last_name": tg_user.get("last_name"),
        "language_code": tg_user.get("language_code"),
        "photo_url": tg_user.get("photo_url"),
        "is_premium": bool(tg_user.get("is_premium")),
        "status": "premium" if tg_user.get("is_premium") else "free",
        "balance": 0,
        "created_at": None,
    }

def sync_user_to_db(user_data: dict) -> dict:
    if not DATABASE_URL or not user_data.get("telegram_id"):
        return user_data

    return get_user_state(
        telegram_id=int(user_data["telegram_id"]),
        username=user_data.get("username"),
        first_name=user_data.get("first_name") or "Guest",
    )

def save_generation(telegram_id: int, generation_type: str, prompt: str, status: str = "done"):
    if not DATABASE_URL or not telegram_id:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generations (telegram_id, generation_type, prompt, status)
            VALUES (%s, %s, %s, %s)
        """, (telegram_id, generation_type, prompt, status))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("GENERATION SAVE FAILED:", exc)

def ensure_prostudio_table():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prostudio_messages (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            telegram_id BIGINT NOT NULL,
            mode TEXT,
            prompt TEXT,
            response_text TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_prostudio_messages_user_conv
        ON prostudio_messages (telegram_id, conversation_id, created_at DESC)
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def save_prostudio_message(payload: dict, result: dict) -> str:
    conversation_id = payload.get("conversation_id") or str(uuid4())
    telegram_id = int(payload.get("telegram_id") or 0)
    if not DATABASE_URL or not telegram_id:
        return conversation_id

    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prostudio_messages (
                conversation_id,
                telegram_id,
                mode,
                prompt,
                response_text,
                image_url
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            conversation_id,
            telegram_id,
            payload.get("mode") or "text",
            payload.get("prompt") or "",
            result.get("text") or "",
            result.get("image_url") or "",
        ))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO MESSAGE SAVE FAILED:", exc)

    return conversation_id

def payment_url(pack_id: str, method: str = "paypal") -> str:
    params = urllib.parse.urlencode({
        "pack_id": pack_id or "",
        "method": method or "paypal",
    })
    return PAYMENT_WEBAPP_URL + ("&" if "?" in PAYMENT_WEBAPP_URL else "?") + params

@app.get("/api/public/prostudio/conversations")
async def public_prostudio_conversations(
    telegram_id: int = 0,
    conversation_id: str = "",
):
    if not DATABASE_URL or not telegram_id:
        return {"ok": True, "conversations": [], "messages": []}

    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        if conversation_id:
            cursor.execute("""
                SELECT prompt, response_text, image_url, created_at
                FROM prostudio_messages
                WHERE telegram_id = %s
                  AND conversation_id = %s
                ORDER BY created_at ASC, id ASC
            """, (telegram_id, conversation_id))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            messages = []
            for prompt, response_text, image_url, created_at in rows:
                if prompt:
                    messages.append({
                        "role": "user",
                        "prompt": prompt,
                        "created_at": created_at,
                    })
                messages.append({
                    "role": "assistant",
                    "response_text": response_text or "",
                    "image_url": image_url or "",
                    "created_at": created_at,
                })
            return {"ok": True, "messages": messages}

        cursor.execute("""
            SELECT
                conversation_id,
                COALESCE(NULLIF(MAX(prompt), ''), 'Chat') AS title,
                MAX(created_at) AS updated_at
            FROM prostudio_messages
            WHERE telegram_id = %s
            GROUP BY conversation_id
            ORDER BY updated_at DESC
            LIMIT 30
        """, (telegram_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {
            "ok": True,
            "conversations": [
                {
                    "id": row[0],
                    "title": (row[1] or "Chat")[:64],
                    "updated_at": row[2],
                }
                for row in rows
            ],
        }
    except Exception as exc:
        print("PROSTUDIO CONVERSATIONS FAILED:", exc)
        return {"ok": True, "conversations": [], "messages": []}

@app.delete("/api/public/prostudio/conversations")
async def delete_public_prostudio_conversation(
    telegram_id: int = 0,
    conversation_id: str = "",
):
    if not DATABASE_URL or not telegram_id or not conversation_id:
        return {"ok": True}

    try:
        ensure_prostudio_table()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM prostudio_messages
            WHERE telegram_id = %s
              AND conversation_id = %s
        """, (telegram_id, conversation_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print("PROSTUDIO CONVERSATION DELETE FAILED:", exc)

    return {"ok": True}

@app.post("/api/public/payments/paypal/create-order")
async def public_paypal_create_order(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or data.get("package") or data.get("plan") or ""
    purchase_type = data.get("type") or data.get("purchase_type") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or data.get("user_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    expected_type = paypal_purchase_type(item)
    if purchase_type and purchase_type not in {expected_type, item.get("kind")}:
        return JSONResponse({"ok": False, "error": "purchase_type_mismatch"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "user_id_required"}, status_code=400)
    if not paypal_configured():
        return JSONResponse({"ok": False, "error": "paypal_not_configured"}, status_code=502)

    try:
        order = create_paypal_order(telegram_id, pack_id, item)
    except Exception as exc:
        print("PAYPAL CREATE ORDER ERROR:", exc)
        return JSONResponse({"ok": False, "error": "paypal_not_configured"}, status_code=502)

    checkout_url = paypal_approve_url(order)
    if not order.get("id") or not checkout_url:
        return JSONResponse({"ok": False, "error": "paypal_checkout_url_missing"}, status_code=502)

    save_paypal_order(telegram_id, pack_id, item, order, checkout_url)
    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="paypal_order_created",
        payload={
            "pack_id": pack_id,
            "paypal_order_id": order.get("id"),
            "url": checkout_url,
        },
    )

    return {
        "ok": True,
        "url": checkout_url,
        "approval_url": checkout_url,
        "paypal_order_id": order.get("id"),
        "pack_id": pack_id,
        "type": expected_type,
    }


@app.post("/api/public/payments/paypal/subscription-created")
async def public_paypal_subscription_created(request: Request):
    data = await request.json()
    subscription_id = (data.get("subscription_id") or data.get("subscriptionID") or "").strip()
    plan_id = (data.get("plan_id") or "").strip()
    plan_type = (data.get("plan_type") or "").strip().lower()
    telegram_id = int(data.get("telegram_id") or data.get("user_id") or 0)
    pack_id = paypal_subscription_pack_for_plan(plan_id, plan_type)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "user_id_required"}, status_code=400)
    if not subscription_id:
        return JSONResponse({"ok": False, "error": "subscription_id_required"}, status_code=400)
    if not pack_id:
        return JSONResponse({"ok": False, "error": "unknown_plan"}, status_code=400)

    saved = save_paypal_subscription(telegram_id, subscription_id, plan_id, plan_type)
    if not saved:
        return JSONResponse({"ok": False, "error": "subscription_save_failed"}, status_code=500)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="paypal_subscription_created",
        event_name="paypal_subscription_created",
        payload={
            "subscription_id": subscription_id,
            "plan_id": plan_id,
            "plan_type": plan_type,
            "pack_id": pack_id,
        },
    )
    return {"ok": True, "status": "pending", "subscription_id": subscription_id, "pack_id": pack_id}


@app.post("/api/public/payments/paypal/webhook")
async def public_paypal_webhook(request: Request):
    raw_body = await request.body()
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    if not verify_paypal_webhook(request.headers, event):
        return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=401)

    event_type = event.get("event_type") or ""
    if event_type in {"BILLING.SUBSCRIPTION.ACTIVATED", "PAYMENT.SALE.COMPLETED"}:
        created = activate_paypal_subscription_from_event(event)
        return {"ok": True, "created": created}

    if event_type != "PAYMENT.CAPTURE.COMPLETED":
        return {"ok": True, "ignored": event_type}

    created = finalize_paypal_capture(event)
    if not created:
        created = activate_paypal_subscription_from_event(event)
    return {"ok": True, "created": created}

@app.post("/api/public/payments/stars/invoice")
async def public_stars_invoice(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    charge_id = f"stars_{uuid4().hex}"
    try:
        invoice_url = create_telegram_stars_invoice_link(telegram_id, pack_id, item, charge_id)
    except Exception as exc:
        print("STARS INVOICE ERROR:", exc)
        return JSONResponse({"ok": False, "error": "stars_invoice_failed", "detail": str(exc)}, status_code=502)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="stars_invoice_created",
        payload={
            "pack_id": pack_id,
            "charge_id": charge_id,
            "invoice_url": invoice_url,
        },
    )

    return {
        "ok": True,
        "invoice_url": invoice_url,
        "pack_id": pack_id,
        "charge_id": charge_id,
    }

@app.post("/api/public/payments/stars/confirm")
async def public_stars_confirm(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    charge_id = data.get("charge_id") or ""
    telegram_id = int(data.get("telegram_id") or 0)

    item = shop_item(pack_id)
    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    if not charge_id:
        return JSONResponse({"ok": False, "error": "charge_id_required"}, status_code=400)

    payload = bot_stars_payload(telegram_id, item, charge_id)
    created = finalize_shop_payment(
        telegram_id=telegram_id,
        provider="telegram_stars",
        item=item,
        amount=int(item.get("stars") or 0),
        currency="XTR",
        payload=payload,
        charge_id=charge_id,
    )

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Telegram User",
        "status": "free",
        "balance": 0,
    })

    return {
        "ok": True,
        "created": created,
        "user": user,
        "pack_id": pack_id,
        "charge_id": charge_id,
    }

# Developer payment endpoint for simulating successful payments (dev only)
@app.post("/api/public/payments/dev/success")
async def public_dev_payment(request: Request):
    data = await request.json()

    telegram_id = int(data.get("telegram_id") or 0)
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)

    if telegram_id != DEV_TELEGRAM_ID:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)

    created = finalize_shop_payment(
        telegram_id=telegram_id,
        provider="developer",
        item=item,
        amount=0,
        currency="DEV",
        payload=f"developer:{pack_id}",
        charge_id=f"developer_{pack_id}_{uuid4().hex}",
    )

    print("DEV PAYMENT:", {
        "telegram_id": telegram_id,
        "pack_id": pack_id,
        "created": created,
        "kind": item["kind"],
        "plan": item.get("plan_key"),
        "bonus_credits": item.get("bonus_credits", 0),
    })

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Developer",
        "status": "free",
        "balance": 0,
    })

    print("DEV PAYMENT USER:", {
        "telegram_id": user.get("telegram_id"),
        "status": user.get("status"),
        "subscription_plan": user.get("subscription_plan"),
        "subscription_expires_at": user.get("subscription_expires_at"),
        "balance": user.get("balance"),
    })

    return {
        "ok": True,
        "created": created,
        "kind": item["kind"],
        "plan": item.get("plan_key"),
        "bonus_credits": item.get("bonus_credits", 0),
        "user": user,
        "message": "Developer payment completed"
    }


# Developer reset endpoint for resetting developer subscription (dev only)
@app.post("/api/public/payments/dev/reset")
async def public_dev_reset(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    reset_credits = bool(data.get("reset_credits", False))

    if telegram_id != DEV_TELEGRAM_ID:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        reset_result = reset_developer_subscription(telegram_id, reset_credits=reset_credits)
    except Exception as exc:
        print("DEV RESET ERROR:", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)

    user = sync_user_to_db({
        "telegram_id": telegram_id,
        "username": data.get("username") or None,
        "first_name": data.get("first_name") or "Developer",
        "status": "free",
        "balance": 0,
    })

    print("DEV RESET:", {
        "telegram_id": telegram_id,
        **reset_result,
    })

    return {
        "ok": True,
        **reset_result,
        "user": user,
        "message": "Developer subscription reset completed"
    }

@app.post("/api/public/payments/crypto/invoice")
async def public_crypto_invoice(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    try:
        invoice = create_crypto_invoice(telegram_id, pack_id, item)
    except Exception as exc:
        print("CRYPTO INVOICE ERROR:", exc)
        return JSONResponse({"ok": False, "error": "crypto_not_configured", "detail": str(exc)}, status_code=502)

    invoice_id = int(invoice.get("invoice_id"))
    asyncio.create_task(poll_crypto_invoice(invoice_id, telegram_id, pack_id))

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="payment_invoice_created",
        event_name="crypto_invoice_created",
        payload={
            "pack_id": pack_id,
            "invoice_id": invoice_id,
            "url": crypto_invoice_url(invoice),
        },
    )

    return {
        "ok": True,
        "url": crypto_invoice_url(invoice),
        "invoice_id": invoice_id,
        "status": invoice.get("status"),
        "pack_id": pack_id,
    }

@app.post("/api/public/telegram/sync")
async def public_telegram_sync(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    user_data = fallback_public_user(payload)

    # Telegram clients provide signed initData. In browser/dev preview we still
    # return optimistic initDataUnsafe fields so the Mini App can render.
    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data", "user": user_data}, status_code=401)

    try:
        user = sync_user_to_db(user_data)
        log_user_event(
            telegram_id=user_data.get("telegram_id"),
            source="mini_app",
            event_type="sync",
            event_name="user_sync",
            payload={
                "subscription_plan": user.get("subscription_plan"),
                "subscription_expires_at": user.get("subscription_expires_at"),
                "status": user.get("status"),
                "balance": user.get("balance"),
            },
        )
    except Exception as exc:
        print("USER SYNC FAILED:", exc)
        user = user_data

    return {"ok": True, "user": user}


@app.post("/api/public/telegram/profile")
async def public_telegram_profile(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    telegram_id = int(payload.get("telegram_id") or 0)

    if not telegram_id:
        user_data = fallback_public_user(payload)
        telegram_id = int(user_data.get("telegram_id") or 0)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)

    profile = save_user_profile(
        telegram_id=telegram_id,
        display_name=payload.get("display_name"),
        custom_avatar_url=payload.get("custom_avatar_url"),
        theme_preference=payload.get("theme_preference"),
    )
    user = sync_user_to_db({"telegram_id": telegram_id})
    user.update(profile)

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="profile",
        event_name="profile_update",
        payload={
            "has_display_name": bool(payload.get("display_name")),
            "has_custom_avatar": bool(payload.get("custom_avatar_url")),
            "theme_preference": payload.get("theme_preference") or {},
        },
    )

    return {"ok": True, "profile": profile, "user": user}


@app.get("/api/public/telegram/referrals")
async def public_telegram_referrals(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)
    return get_referral_state(int(telegram_id), activate=False)


@app.post("/api/public/telegram/referrals")
async def public_activate_referrals(request: Request):
    payload = await request.json()
    init_data = payload.get("initData") or ""
    telegram_id = int(payload.get("telegram_id") or 0)

    if not telegram_id:
        user_data = fallback_public_user(payload)
        telegram_id = int(user_data.get("telegram_id") or 0)

    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if init_data and BOT_TOKEN and not verify_telegram_init_data(init_data):
        return JSONResponse({"ok": False, "error": "invalid_init_data"}, status_code=401)

    state = get_referral_state(int(telegram_id), activate=bool(payload.get("activate", True)))
    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type="referral",
        event_name="referral_link_activated",
        payload={"code": state.get("code")},
    )
    return state


@app.post("/api/public/events")
async def public_log_event(request: Request):
    data = await request.json()
    telegram_id = int(data.get("telegram_id") or 0)
    event_type = data.get("event_type") or "event"
    event_name = data.get("event_name") or ""
    payload = data.get("payload") or {}

    log_user_event(
        telegram_id=telegram_id,
        source="mini_app",
        event_type=event_type,
        event_name=event_name,
        payload=payload,
    )

    return {"ok": True}


@app.get("/api/public/events")
async def public_get_events(telegram_id: int = 0):
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    if not DATABASE_URL:
        return JSONResponse({"ok": False, "error": "database_not_configured"}, status_code=500)

    ensure_user_events_table()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, source, event_type, event_name, payload, created_at
            FROM user_events
            WHERE telegram_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (telegram_id,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    events = [
        {
            "id": row[0],
            "source": row[1],
            "event_type": row[2],
            "event_name": row[3],
            "payload": row[4],
            "created_at": _to_iso(row[5]) if row[5] else None,
        }
        for row in rows
    ]

    return {"ok": True, "events": events}


def openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

def text_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    history = payload.get("history") or []
    mode = payload.get("mode") or "text"
    model = payload.get("model") or "gpt-4o-mini"
    attachment = payload.get("attachment") or {}

    messages = [
        {
            "role": "system",
            "content": (
                "You are SYLVEX Pro Studio inside a Telegram Mini App. "
                "Help users create images, videos, music, voiceovers, text, and plans. "
                "Be concise, practical, and production-ready."
            )
        }
    ]
    for item in history[-10:]:
        role = item.get("role") if item.get("role") in ("user", "assistant") else "user"
        content = item.get("content")
        if content:
            messages.append({"role": role, "content": content})
    if attachment:
        prompt = (prompt + f"\n\nAttachment: {attachment.get('name')} ({attachment.get('mime')})").strip()
    messages.append({"role": "user", "content": f"Mode: {mode}\nPrompt: {prompt}"})

    if not OPENAI_API_KEY:
        return {
            "ok": True,
            "type": "text",
            "text": "SYLVEX Pro Studio is connected. Add OPENAI_API_KEY to enable live generation.\n\nPrompt: " + prompt
        }

    response = requests.post(
        f"{OPENAI_API_BASE}/chat/completions",
        headers=openai_headers(),
        data=json.dumps({"model": model if model != "gpt-image-1" else "gpt-4o-mini", "messages": messages}),
        timeout=60,
    )
    if response.status_code >= 400:
        return {"ok": False, "error": response.text}
    data = response.json()
    return {
        "ok": True,
        "type": "text",
        "text": data.get("choices", [{}])[0].get("message", {}).get("content", "")
    }

def image_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    if not OPENAI_API_KEY:
        return {
            "ok": True,
            "type": "text",
            "text": "Image generation is ready. Add OPENAI_API_KEY to generate images.\n\nPrompt: " + prompt
        }

    response = requests.post(
        f"{OPENAI_API_BASE}/images/generations",
        headers=openai_headers(),
        data=json.dumps({"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024"}),
        timeout=120,
    )
    if response.status_code >= 400:
        return {"ok": False, "error": response.text}

    data = response.json().get("data", [{}])[0]
    if data.get("url"):
        return {"ok": True, "type": "image", "image_url": data["url"]}
    if data.get("b64_json"):
        return {"ok": True, "type": "image", "image_url": "data:image/png;base64," + data["b64_json"]}
    return {"ok": False, "error": "No image returned"}

@app.post("/api/public/prostudio/generate")
async def public_prostudio_generate(request: Request):
    payload = await request.json()
    mode = (payload.get("mode") or "text").lower()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt and not payload.get("attachment"):
        return JSONResponse({"ok": False, "error": "Prompt or attachment is required"}, status_code=400)

    result = image_generation(payload) if mode == "image" else text_generation(payload)
    if not result.get("ok"):
        return JSONResponse(result, status_code=502)

    save_generation(int(payload.get("telegram_id") or 0), mode, prompt or "[attachment]")
    result["conversation_id"] = save_prostudio_message(payload, result)
    return result

@app.post("/api/public/prostudio/transcribe")
async def public_prostudio_transcribe(request: Request):
    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        return JSONResponse({"ok": False, "error": "File is required"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "Empty file"}, status_code=400)
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}

    response = requests.post(
        f"{OPENAI_API_BASE}/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": (
            getattr(file, "filename", None) or "voice.webm",
            content,
            getattr(file, "content_type", None) or "audio/webm",
        )},
        data={"model": os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")},
        timeout=120,
    )
    if response.status_code >= 400:
        return JSONResponse({"ok": False, "error": response.text}, status_code=502)
    return {"ok": True, "text": response.json().get("text", "")}

@app.get("/api/cabinet/{telegram_id}")
async def get_cabinet(telegram_id: int):

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        telegram_id,
        username,
        first_name,
        balance,
        subscription,
        total_generations,
        created_at
    FROM users
    WHERE telegram_id = %s
    """, (telegram_id,))

    user = cursor.fetchone()

    cursor.execute("""
    SELECT
        generation_type,
        prompt,
        status,
        created_at
    FROM generations
    WHERE telegram_id = %s
    ORDER BY id DESC
    LIMIT 10
    """, (telegram_id,))

    generations = cursor.fetchall()

    cursor.close()
    conn.close()

    if not user:
        return JSONResponse(
            {
                "success": False
            }
        )

    return {
        "success": True,
        "user": {
            "telegram_id": user[0],
            "username": user[1],
            "first_name": user[2],
            "balance": user[3],
            "subscription": user[4],
            "total_generations": user[5],
            "created_at": user[6]
        },
        "generations": [
            {
                "generation_type": row[0],
                "prompt": row[1],
                "status": row[2],
                "created_at": row[3]
            }
            for row in generations
        ]
    }
