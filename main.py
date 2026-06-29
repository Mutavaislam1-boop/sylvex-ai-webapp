import os
import pathlib
import json
import hmac
import hashlib
import urllib.parse
import asyncio
from uuid import uuid4
import requests
import psycopg2
from fastapi.responses import JSONResponse, RedirectResponse



from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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
DATABASE_URL = os.getenv("DATABASE_URL")
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
LEMONSQUEEZY_API_KEY = (
    os.getenv("LEMONSQUEEZY_API_KEY")
    or os.getenv("LEMONSQUEEYY_API_KEY")
)
LEMONSQUEEZY_BASE_URL = "https://api.lemonsqueezy.com/v1"
CRYPTO_API_KEY = os.getenv("CRYPTO_API_KEY") or os.getenv("CRIPTO_API_KEY")
CRYPTO_PAY_API_URL = "https://pay.crypt.bot/api"
HEYGEN_BASE_URL = "https://api.heygen.com/v3"
HEYGEN_VOICE_MODEL_ID = "starfish"
HEYGEN_DEFAULT_LANGUAGE = "ru"
HEYGEN_DEFAULT_SPEED = 1.0
HEYGEN_DEFAULT_OUTPUT_FORMAT = "mp3"

SHOP_ITEMS = {
    "sub_month": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 месяц",
        "plan_key": "month",
        "days": 30,
        "credits": 0,
        "usd": 5.0,
        "stars": 230,
    },
    "sub_year": {
        "kind": "subscription",
        "title": "SYLVEX Pro · 1 год",
        "plan_key": "year",
        "days": 365,
        "credits": 0,
        "usd": 59.0,
        "stars": 2751,
    },
    "pack_100": {"kind": "credits", "title": "100 ⚡", "credits": 100, "usd": 1.0, "stars": 46},
    "pack_500": {"kind": "credits", "title": "500 ⚡", "credits": 500, "usd": 5.0, "stars": 230},
    "pack_1000": {"kind": "credits", "title": "1000 ⚡", "credits": 1000, "usd": 10.0, "stars": 460},
    "pack_2000": {"kind": "credits", "title": "2000 ⚡", "credits": 2000, "usd": 20.0, "stars": 920},
    "pack_3000": {"kind": "credits", "title": "3000 ⚡", "credits": 3000, "usd": 30.0, "stars": 1380},
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

def lemonsqueezy_headers():
    if not LEMONSQUEEZY_API_KEY:
        return None

    return {
        "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def normalize_lemon_product(item: dict) -> dict:
    attributes = item.get("attributes") or {}
    description = attributes.get("description") or ""
    product_name = attributes.get("name") or "Lemon Squeezy product"
    price_formatted = attributes.get("price_formatted") or attributes.get("from_price_formatted") or ""

    return {
        "id": item.get("id"),
        "name": product_name,
        "slug": attributes.get("slug"),
        "description": description,
        "status": attributes.get("status"),
        "status_formatted": attributes.get("status_formatted"),
        "price": attributes.get("price"),
        "price_formatted": price_formatted,
        "checkout_url": attributes.get("buy_now_url"),
        "test_mode": bool(attributes.get("test_mode")),
        "thumb_url": attributes.get("thumb_url") or attributes.get("large_thumb_url"),
        "is_subscription": "/month" in price_formatted or "/year" in price_formatted,
    }


def fetch_lemon_products() -> list:
    headers = lemonsqueezy_headers()

    if not headers:
        return []

    response = requests.get(
        f"{LEMONSQUEEZY_BASE_URL}/products",
        headers=headers,
        timeout=30,
    )

    print("LEMON PRODUCTS STATUS:", response.status_code)

    if response.status_code >= 400:
        print("LEMON PRODUCTS ERROR:", response.text[:1000])
        raise RuntimeError(response.text)

    data = response.json()
    products = [normalize_lemon_product(item) for item in data.get("data", [])]

    return [
        product
        for product in products
        if product.get("status") == "published" and product.get("checkout_url")
    ]


def legacy_lemon_packages(products: list) -> dict:
    packages = {}

    for product in products:
        name = (product.get("name") or "").lower()
        price = int(product.get("price") or 0)
        url = product.get("checkout_url") or ""

        if "token" not in name:
            continue

        if price <= 52000:
            packages.setdefault("100", url)
        elif price <= 260000:
            packages.setdefault("500", url)
        else:
            packages.setdefault("1000", url)

    return packages


def shop_item(pack_id: str):
    return SHOP_ITEMS.get((pack_id or "").strip())


def shop_payload(provider: str, telegram_id: int, pack_id: str, item: dict) -> str:
    if item["kind"] == "subscription":
        return f"sylvex_{provider}_sub:{telegram_id}:{item['plan_key']}:{item['usd']:.2f}"
    return f"sylvex_{provider}_credits:{telegram_id}:{item['credits']}:{item['usd']:.2f}"


def bot_stars_payload(telegram_id: int, item: dict) -> str:
    if item["kind"] == "subscription":
        return f"sylvex_sub:{telegram_id}:{item['plan_key']}:{item['stars']}"
    return f"sylvex_stars:{telegram_id}:{item['credits']}:{item['stars']}"


def create_telegram_stars_invoice_link(telegram_id: int, pack_id: str, item: dict) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink",
        json={
            "title": item["title"],
            "description": f"Оплата {item['title']} в SYLVEX.",
            "payload": bot_stars_payload(telegram_id, item),
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
        conn.commit()
    finally:
        cursor.close()
        conn.close()


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


def activate_subscription(telegram_id: int, item: dict, provider: str, amount: int, currency: str, payload: str, charge_id: str):
    if not DATABASE_URL:
        return

    ensure_payment_tables()
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO subscriptions (
                telegram_id, subscription_type, payment_method, amount, currency, expires_at, status, charge_id
            )
            VALUES (
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP + (%s || ' days')::interval, 'active', %s
            )
            ON CONFLICT (charge_id) DO NOTHING
        """, (telegram_id, item["plan_key"], provider, amount, currency, item["days"], charge_id))
        cursor.execute("UPDATE users SET subscription = 'active' WHERE telegram_id = %s", (telegram_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def add_user_balance(telegram_id: int, credits: int):
    if not DATABASE_URL:
        return

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
    created = create_purchase_once(telegram_id, provider, credits, amount, currency, payload, charge_id)

    if not created:
        return False

    if item["kind"] == "subscription":
        activate_subscription(telegram_id, item, provider, amount, currency, payload, charge_id)
    else:
        add_user_balance(telegram_id, credits)

    return True


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
            return
        if status == "expired":
            return


def lemon_checkout_url(pack_id: str, item: dict) -> str:
    env_map = {
        "sub_month": os.getenv("LEMON_SUB_MONTH_URL", ""),
        "sub_year": os.getenv("LEMON_SUB_YEAR_URL", ""),
        "pack_100": os.getenv("LEMON_100_CREDITS_URL", ""),
        "pack_500": os.getenv("LEMON_500_CREDITS_URL", ""),
        "pack_1000": os.getenv("LEMON_1000_CREDITS_URL", ""),
        "pack_2000": os.getenv("LEMON_2000_CREDITS_URL", ""),
        "pack_3000": os.getenv("LEMON_3000_CREDITS_URL", ""),
    }
    if env_map.get(pack_id):
        return env_map[pack_id]

    products = fetch_lemon_products()
    target_price_cents = int(round(float(item["usd"]) * 100))
    words = [str(item.get("credits") or ""), item.get("plan_key") or "", item["title"].lower()]

    for product in products:
        name = (product.get("name") or "").lower()
        price = int(product.get("price") or 0)
        if price != target_price_cents:
            continue
        if item["kind"] == "subscription" and ("sub" in name or "pro" in name or item["plan_key"] in name):
            return product.get("checkout_url") or ""
        if item["kind"] == "credits" and str(item["credits"]) in name:
            return product.get("checkout_url") or ""

    for product in products:
        if int(product.get("price") or 0) == target_price_cents:
            return product.get("checkout_url") or ""

    return ""


def with_lemon_custom_data(url: str, telegram_id: int, pack_id: str) -> str:
    if not url:
        return ""

    params = {
        "checkout[custom][telegram_id]": str(telegram_id),
        "checkout[custom][pack_id]": pack_id,
    }
    separator = "&" if "?" in url else "?"
    return url + separator + urllib.parse.urlencode(params)


def verify_lemon_signature(raw_body: bytes, signature=None) -> bool:
    secret = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET") or os.getenv("LEMON_WEBHOOK_SECRET")
    if not secret:
        return True
    if not signature:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)

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
    try:
        products = fetch_lemon_products()
        packages = legacy_lemon_packages(products)

        return {
            "success": True,
            "source": "lemonsqueezy_api" if LEMONSQUEEZY_API_KEY else "env_links",
            "products": products,
            "packages": packages or {
                "100": os.getenv("LEMON_100_CREDITS_URL", ""),
                "500": os.getenv("LEMON_500_CREDITS_URL", ""),
                "1000": os.getenv("LEMON_1000_CREDITS_URL", "")
            }
        }
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "source": "lemonsqueezy_api",
                "error": str(exc),
                "products": [],
                "packages": {
                    "100": os.getenv("LEMON_100_CREDITS_URL", ""),
                    "500": os.getenv("LEMON_500_CREDITS_URL", ""),
                    "1000": os.getenv("LEMON_1000_CREDITS_URL", "")
                }
            }
        )

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

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            RETURNING telegram_id, username, first_name, balance, subscription, created_at
        """, (
            int(user_data["telegram_id"]),
            user_data.get("username"),
            user_data.get("first_name") or "Guest",
        ))
        row = cursor.fetchone()
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    subscription = row[4] or user_data.get("status") or "free"
    return {
        **user_data,
        "telegram_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "balance": row[3] or 0,
        "status": subscription,
        "created_at": row[5],
    }

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

def payment_url(pack_id: str, method: str = "card") -> str:
    params = urllib.parse.urlencode({
        "pack_id": pack_id or "",
        "method": method or "card",
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

@app.post("/api/public/payments/card/checkout")
async def public_card_checkout(request: Request):
    data = await request.json()
    pack_id = data.get("pack_id") or ""
    item = shop_item(pack_id)
    telegram_id = int(data.get("telegram_id") or 0)

    if not item:
        return JSONResponse({"ok": False, "error": "unknown_pack"}, status_code=400)
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "telegram_id_required"}, status_code=400)

    try:
        url = lemon_checkout_url(pack_id, item)
    except Exception as exc:
        print("LEMON CHECKOUT ERROR:", exc)
        return JSONResponse({"ok": False, "error": "card_not_configured"}, status_code=502)

    if not url:
        return JSONResponse({"ok": False, "error": "card_not_configured"}, status_code=404)

    return {
        "ok": True,
        "url": with_lemon_custom_data(url, telegram_id, pack_id),
        "pack_id": pack_id,
    }


@app.post("/api/public/payments/card/webhook")
async def public_card_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Signature") or request.headers.get("x-signature")

    if not verify_lemon_signature(raw_body, signature):
        return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=401)

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    meta = event.get("meta") or {}
    event_name = meta.get("event_name") or ""
    custom_data = meta.get("custom_data") or {}
    data = event.get("data") or {}
    attributes = data.get("attributes") or {}

    if event_name not in {"order_created", "subscription_created", "subscription_payment_success"}:
        return {"ok": True, "ignored": event_name}

    try:
        telegram_id = int(custom_data.get("telegram_id") or 0)
    except Exception:
        telegram_id = 0

    pack_id = custom_data.get("pack_id") or ""
    item = shop_item(pack_id)

    if not telegram_id or not item:
        return JSONResponse({"ok": False, "error": "missing_custom_data"}, status_code=400)

    amount = int(attributes.get("total") or attributes.get("subtotal") or round(item["usd"] * 100))
    currency = attributes.get("currency") or "USD"
    order_id = data.get("id") or attributes.get("identifier") or uuid4().hex
    payload = shop_payload("card", telegram_id, pack_id, item)

    finalize_shop_payment(
        telegram_id=telegram_id,
        provider="lemonsqueezy",
        item=item,
        amount=amount,
        currency=currency,
        payload=payload,
        charge_id=f"lemon_{order_id}",
    )

    return {"ok": True}

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

    try:
        invoice_url = create_telegram_stars_invoice_link(telegram_id, pack_id, item)
    except Exception as exc:
        print("STARS INVOICE ERROR:", exc)
        return JSONResponse({"ok": False, "error": "stars_invoice_failed", "detail": str(exc)}, status_code=502)

    return {
        "ok": True,
        "invoice_url": invoice_url,
        "pack_id": pack_id,
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
    except Exception as exc:
        print("USER SYNC FAILED:", exc)
        user = user_data

    return {"ok": True, "user": user}

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
