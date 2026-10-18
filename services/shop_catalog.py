"""Server-authoritative USD Store catalog (Website: Stripe; Crypto Pay).

Every purchasable product, its USD price, the credits it grants and (for
plans) the subscription it activates are defined here. Clients only send a
product id, plus a USD amount for a custom purchase; nothing they send about
credits is trusted. Orders snapshot these values when created (see
services/shop_orders.py), so a paid order always grants what was quoted.

Telegram Stars prices are NOT here: everything sold inside Telegram comes
from services/telegram_catalog.py, the separate Telegram catalog.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation

CREDITS_PER_USD = 100
CUSTOM_MIN_CENTS = 100
CUSTOM_MAX_CENTS = 100_000

# Crypto Pay limits are configurable: they are not confirmed per invoice.
CRYPTO_MIN_CENTS = int(round(float(os.getenv("CRYPTO_MIN_USD", "1")) * 100))
CRYPTO_MAX_CENTS = int(round(float(os.getenv("CRYPTO_MAX_USD", "1000")) * 100))

# Provider ids as stored on orders and purchases. Stars orders are created
# only from services/telegram_catalog.py.
PROVIDER_STARS = "telegram_stars"
PROVIDER_CRYPTO = "crypto_pay"
PROVIDERS = (PROVIDER_STARS, PROVIDER_CRYPTO)
# Website-only card payments (services/stripe_billing.py). Not offered in
# the Telegram Mini App: Telegram requires Stars for digital goods there.
PROVIDER_STRIPE = "stripe"

# id, display name, monthly USD, annual USD, monthly credits. Annual plans
# grant 12 x the monthly credits once, on the confirmed payment.
PLANS = (
    ("starter", "Starter", 5, 48, 100),
    ("pro", "Pro", 10, 96, 300),
    ("max", "Max", 25, 240, 1000),
    ("ultra", "Ultra", 50, 480, 2500),
    ("creator", "Creator", 100, 960, 5500),
)
PLAN_DAYS = {"month": 30, "year": 365}

CREDIT_PACK_USD = (5, 10, 20, 30, 40, 50, 100, 200)
CUSTOM_PRODUCT_ID = "credits_custom"
PLAN_NAMES = {plan[0]: plan[1] for plan in PLANS}


# ---------------------------------------------------------------------------
# Generation examples shown on Store cards.
#
# Each category shows how many of its cheapest user-selectable generation a
# balance covers, priced by the live price engine (main.py
# store_generation_examples() -> calculate_generation_price). The candidate
# lists are the models the Mini App lets a user pick (webapp/js/cabinet.js
# IMAGE_MODEL_LIST, VIDEO_MODELS, MUSIC_MODEL_LIST, VOICE_MODEL_LIST,
# TEXT_MODEL_LIST; tests/test_store_examples.py keeps them in sync).
# Video additionally keeps only general text/image-to-video models (the
# capability registry's avatar, edit, motion, effects and lip-sync models
# need an avatar or a source clip). Voice leaves out speech-to-speech, which
# converts an uploaded recording rather than reading text.
EXAMPLE_VIDEO_SECONDS = 5
EXAMPLE_VOICE_CHARS = 1000
EXAMPLE_TEXT_INPUT_TOKENS = 1000
EXAMPLE_TEXT_OUTPUT_TOKENS = 1000
EXAMPLE_MUSIC_SECONDS = {'google_lyria_3_clip': 30}
EXAMPLE_VOICE_EXCLUDED = ("elevenlabs_english_sts_v2", "elevenlabs_multilingual_sts_v2")

EXAMPLE_IMAGE_MODELS = (
    ('seedream_5_0_lite', 'Seedream 5.0 Lite'),
    ('ideogram_3_0', 'Ideogram 3.0'),
    ('ideogram_4_0', 'Ideogram 4.0'),
    ('recraft_v4_1', 'Recraft V4.1'),
    ('recraft_v3', 'Recraft V3'),
    ('recraft_v4_1_pro', 'Recraft V4.1 Pro'),
    ('seedream_4_5', 'Seedream 4.5'),
    ('seedream_5_0_pro', 'Seedream 5.0 Pro'),
    ('seedream_4_0', 'Seedream 4.0'),
    ('gpt_image_1', 'GPT Image 1'),
    ('gpt_image_2', 'GPT Image 2'),
    ('flux_pro_kontext', 'FLUX Pro Text'),
    ('flux_2', 'FLUX.2'),
    ('flux_2_turbo', 'FLUX.2 Turbo'),
    ('qwen_image', 'Qwen Image'),
    ('qwen_image_2_pro', 'Qwen Image 2 Pro'),
    ('qwen_image_2', 'Qwen Image 2'),
    ('nano_banana_2', 'Nano Banana 2'),
    ('nano_banana_2_lite', 'Nano Banana 2 Lite'),
    ('nano_banana_pro', 'Nano Banana Pro'),
    ('grok_pro', 'Grok Pro'),
    ('grok', 'Grok'),
)

EXAMPLE_VIDEO_MODELS = (
    ('heygen_v3_video_agent', 'HeyGen V3 Video Agent'),
    ('heygen_avatar_iv', 'HeyGen Avatar IV'),
    ('heygen_avatar_v', 'HeyGen Avatar V'),
    ('heygen_avatar_iii', 'HeyGen Avatar III'),
    ('heygen_image_video', 'HeyGen Image Video'),
    ('heygen_cinematic_avatar', 'HeyGen Cinematic Avatar'),
    ('luma_ray_v3_2', 'Luma Ray v3.2'),
    ('pixverse_v6', 'PixVerse v6'),
    ('wan_2_6', 'Wan 2.6'),
    ('wan_2_7', 'Wan 2.7'),
    ('wan_2_7_edit', 'Wan 2.7 Edit'),
    ('veo_3_1', 'Veo 3.1'),
    ('veo_3_1_fast', 'Veo 3.1 Fast'),
    ('grok_video', 'Grok Video'),
    ('grok_video_edit', 'Grok Video Edit'),
    ('runway_gen4_5', 'Runway Gen-4.5'),
    ('runway_gen4_turbo', 'Runway Gen-4 Turbo'),
    ('runway_aleph2', 'Runway Aleph 2.0'),
    ('runway_happyhorse_1_0', 'Runway HappyHorse 1.0'),
    ('kling_3_0_turbo', 'Kling 3.0 Turbo'),
    ('kling_3_0', 'Kling 3.0'),
    ('kling_o3_omni', 'Kling 3.0 Omni'),
    ('kling_o3_edit', 'Kling 3.0 Omni Edit'),
    ('kling_motion_2_6', 'Kling Motion 2.6'),
    ('kling_motion_3_0', 'Kling Motion 3.0'),
    ('kling_effects', 'Kling Video Effects'),
    ('kling_o1', 'Kling O1'),
    ('kling_2_6', 'Kling 2.6'),
    ('kling_2_5_turbo', 'Kling 2.5 Turbo'),
    ('kling_2_1', 'Kling 2.1'),
    ('kling_2_1_master', 'Kling 2.1 Master'),
    ('kling_2_0_master', 'Kling 2.0 Master'),
    ('kling_1_6', 'Kling 1.6'),
    ('kling_1_5', 'Kling 1.5'),
    ('kling_1_0', 'Kling 1.0'),
    ('kling_lip_sync', 'Kling Lip Sync'),
    ('seedance_1_5_pro', 'Seedance 1.5 Pro'),
    ('seedance_2_fast', 'Seedance 2.0 Fast'),
    ('seedance_2_0', 'Seedance 2.0'),
    ('gemini_omni_flash', 'Gemini Omni Flash'),
)

EXAMPLE_MUSIC_MODELS = (
    ('suno_chirp_3_5', 'Suno Chirp v3.5'),
    ('suno_chirp_4_0', 'Suno Chirp v4.0'),
    ('suno_chirp_4_5', 'Suno Chirp v4.5'),
    ('suno_chirp_4_5_plus', 'Suno Chirp v4.5 Plus'),
    ('suno_chirp_5', 'Suno Chirp v5'),
    ('suno_chirp_5_5', 'Suno Chirp v5.5'),
    ('suno_chirp_6', 'Suno Chirp v6'),
    ('suno_chirp_6_mini', 'Suno Chirp v6 Mini'),
    ('elevenlabs_music', 'ElevenLabs Music'),
    ('minimax_music_2_5', 'MiniMax Music 2.5'),
    ('google_lyria_3_clip', 'Google Lyria 3 Clip'),
    ('google_lyria_3_pro', 'Google Lyria 3 Pro'),
    ('google_lyria_realtime', 'Google Lyria RealTime'),
)

EXAMPLE_VOICE_MODELS = (
    ('elevenlabs_eleven_v3', 'ElevenLabs Eleven v3'),
    ('gemini_3_1_flash_tts_preview', 'Gemini 3.1 Flash TTS Preview'),
    ('gemini_2_5_flash_preview_tts', 'Gemini 2.5 Flash Preview TTS'),
    ('gemini_2_5_pro_preview_tts', 'Gemini 2.5 Pro Preview TTS'),
    ('elevenlabs_multilingual_v2', 'ElevenLabs Multilingual v2'),
    ('elevenlabs_flash_v2_5', 'ElevenLabs Flash v2.5'),
    ('elevenlabs_flash_v2', 'ElevenLabs Flash v2'),
    ('elevenlabs_turbo_v2_5', 'ElevenLabs Turbo v2.5'),
    ('elevenlabs_turbo_v2', 'ElevenLabs Turbo v2'),
    ('elevenlabs_english_sts_v2', 'ElevenLabs English STS v2'),
    ('elevenlabs_multilingual_sts_v2', 'ElevenLabs Multilingual STS v2'),
    ('runway_eleven_multilingual_v2', 'Runway Eleven Multilingual v2'),
)

EXAMPLE_TEXT_MODELS = (
    ('gpt-5.6', 'GPT-5.6'),
    ('gpt-5.5', 'GPT-5.5'),
    ('gpt-5', 'GPT-5'),
    ('gpt-5-mini', 'GPT-5 mini'),
    ('gpt-4.1', 'GPT-4.1'),
    ('gpt-4.1-mini', 'GPT-4.1 mini'),
    ('gpt-4o', 'GPT-4o'),
    ('gpt-4o-mini', 'GPT-4o mini'),
    ('gemini_3_1_pro', 'Gemini 3.1 Pro'),
    ('gemini_3_1_flash', 'Gemini 3.1 Flash'),
    ('gemini_2_5_pro', 'Gemini 2.5 Pro'),
    ('gemini_2_5_flash', 'Gemini 2.5 Flash'),
    ('grok_4_1', 'Grok 4.1'),
    ('grok_4_fast', 'Grok 4 Fast'),
    ('grok_3', 'Grok 3'),
    ('qwen_plus', 'Qwen Plus'),
    ('qwen_turbo', 'Qwen Turbo'),
    ('qwen_max', 'Qwen Max'),
    ('byteplus_seed_2_lite', 'BytePlus Seed 2.0 Lite'),
)


def pack_id_for_usd(usd: int) -> str:
    return f"pack_{int(usd) * CREDITS_PER_USD}"


def _plan_product(plan, period: str) -> dict:
    plan_id, name, monthly_usd, annual_usd, monthly_credits = plan
    usd = monthly_usd if period == "month" else annual_usd
    credits = monthly_credits if period == "month" else monthly_credits * 12
    term = "1 месяц" if period == "month" else "12 месяцев"
    return {
        "product_id": f"plan_{plan_id}_{period}",
        "kind": "subscription",
        "title": f"SYLVEX {name} · {term}",
        "plan_id": plan_id,
        "plan_name": name,
        "period": period,
        "plan_key": f"{plan_id}_{period}",
        "days": PLAN_DAYS[period],
        "usd_cents": usd * 100,
        "credits": credits,
    }


def _pack_product(usd_cents: int, product_id: str) -> dict:
    credits = usd_cents * CREDITS_PER_USD // 100
    return {
        "product_id": product_id,
        "kind": "credits",
        "title": f"{credits:,} ⚡ SYLVEX".replace(",", " "),
        "plan_key": None,
        "days": None,
        "usd_cents": usd_cents,
        "credits": credits,
    }


def _fixed_products() -> dict:
    products = {}
    for plan in PLANS:
        for period in ("month", "year"):
            product = _plan_product(plan, period)
            products[product["product_id"]] = product
    for usd in CREDIT_PACK_USD:
        product = _pack_product(usd * 100, pack_id_for_usd(usd))
        products[product["product_id"]] = product
    return products


FIXED_PRODUCTS = _fixed_products()


class CatalogError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_usd_cents(raw) -> int:
    """Custom amount in USD -> cents. At most two decimals, within range."""
    text = str(raw if raw is not None else "").strip().replace(",", ".")
    if not text:
        raise CatalogError("amount_required")
    if not re.fullmatch(r"\d{1,7}(\.\d{1,2})?", text):
        raise CatalogError("invalid_amount")
    try:
        cents = int((Decimal(text) * 100).to_integral_exact())
    except (InvalidOperation, ArithmeticError):
        raise CatalogError("invalid_amount")
    if cents < CUSTOM_MIN_CENTS or cents > CUSTOM_MAX_CENTS:
        raise CatalogError("amount_out_of_range")
    return cents


def resolve_product(product_id: str, usd=None) -> dict:
    """The authoritative USD product for a purchase request."""
    product_id = str(product_id or "").strip()
    if product_id == CUSTOM_PRODUCT_ID:
        product = _pack_product(parse_usd_cents(usd), CUSTOM_PRODUCT_ID)
    elif product_id in FIXED_PRODUCTS:
        product = dict(FIXED_PRODUCTS[product_id])
    else:
        raise CatalogError("unknown_product")
    return product


def provider_availability(product: dict) -> dict:
    """Which USD payment methods may sell this product, and why not."""
    crypto_ok = CRYPTO_MIN_CENTS <= product["usd_cents"] <= CRYPTO_MAX_CENTS
    return {
        PROVIDER_CRYPTO: {"available": crypto_ok, "reason": None if crypto_ok else "crypto_amount_out_of_range"},
    }


def plan_label(plan_key: str) -> str:
    """Human label for a subscriptions.subscription_type value."""
    key = str(plan_key or "").strip().lower()
    if key == "year":
        return "1 год"
    if key in {"month", ""}:
        return "1 месяц"
    plan_id, _, period = key.rpartition("_")
    names = PLAN_NAMES
    if plan_id in names and period in PLAN_DAYS:
        return f"{names[plan_id]} · {'1 месяц' if period == 'month' else '12 месяцев'}"
    return key


def plan_product_name(plan_key: str) -> str:
    """"SYLVEX Pro" for the legacy month/year plans, else "SYLVEX <Plan>"."""
    key = str(plan_key or "").strip().lower()
    names = PLAN_NAMES
    plan_id = key.rpartition("_")[0]
    return f"SYLVEX {names[plan_id]}" if plan_id in names else "SYLVEX Pro"


def public_catalog() -> dict:
    products = []
    for product_id in FIXED_PRODUCTS:
        product = resolve_product(product_id)
        products.append({
            **{key: product[key] for key in ("product_id", "kind", "title", "usd_cents", "credits", "plan_key", "days")},
            **({"plan_id": product["plan_id"], "period": product["period"]} if product["kind"] == "subscription" else {}),
            "providers": provider_availability(product),
        })
    return {
        "credits_per_usd": CREDITS_PER_USD,
        "products": products,
        "custom": {
            "product_id": CUSTOM_PRODUCT_ID,
            "min_cents": CUSTOM_MIN_CENTS,
            "max_cents": CUSTOM_MAX_CENTS,
            "crypto_min_cents": max(CUSTOM_MIN_CENTS, CRYPTO_MIN_CENTS),
            "crypto_max_cents": min(CUSTOM_MAX_CENTS, CRYPTO_MAX_CENTS),
        },
        "renewal": "manual",
    }
