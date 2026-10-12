"""Telegram Stars catalog: everything SYLVEX sells inside Telegram.

The one authoritative price list for the Telegram Mini App, the backend
Stars invoices and the polling bot's payment validation. Keep this file
byte-identical in sylvex-ai-webapp/services/telegram_catalog.py and
sylvex-ai-bot/app/database/telegram_catalog.py; it depends only on the
standard library.

Inside Telegram, Telegram Stars (XTR) is the only payment method. This
catalog is independent of the Website/Stripe catalog (shop_catalog.py),
which keeps its own USD prices.

Pricing: stars = ceil(usd * 499 / 5), with USD as the reference only
(never shown or charged in Telegram). Credits: $1 = 100 credits.
Every purchase is ONE Stars payment for a fixed term: a monthly plan buys
30 days, an annual plan 365 days. Nothing renews automatically (Telegram's
recurring Stars subscriptions only support a 30-day period, and SYLVEX
does not use them).

Telegram limits, checked with createInvoiceLink on the SYLVEX bot
(scripts/verify_stars_invoice_limits.py; invoice CREATION only - no payment
has been completed at these amounts):
  - one-time invoices: 10,000, 19,960, 23,952 and 95,808 Stars accepted;
    Telegram documents no one-time maximum;
  - recurring 30-day subscriptions: 10,000 Stars accepted, 10,001 rejected
    (SUBSCRIPTION_AMOUNT_INVALID), the documented subscription cap.
The 10,000 cap applies to recurring subscriptions only. A one-time product
is offered if its Stars price is within STARS_MAX_PER_INVOICE. Prices are
never changed or split to fit a limit; anything above it is simply
unavailable in Telegram.
"""
import os
import re

STARS_RATE_STARS = 499
STARS_RATE_CENTS = 500
CREDITS_PER_USD = 100

# Highest ONE-TIME Stars invoice amount SYLVEX offers. The default is the
# highest amount verified with createInvoiceLink (95,808 Stars, the Creator
# annual plan); it is not Telegram's maximum. To offer more, verify a larger
# amount with scripts/verify_stars_invoice_limits.py and raise this setting.
STARS_MAX_PER_INVOICE = int(os.getenv("STARS_MAX_PER_INVOICE", "95808"))

# Recurring Stars subscriptions (Telegram's documented and verified cap and
# its only billing period). SYLVEX sells no recurring products today; any
# recurring invoice must pass check_invoice_amount(..., subscription_period).
SUBSCRIPTION_PERIOD_SECONDS = 2592000
STARS_MAX_PER_SUBSCRIPTION = 10000

PROVIDER = "telegram_stars"
PLAN_DAYS = {"month": 30, "year": 365}

# id, display name, monthly USD reference, annual USD reference, monthly
# credits. Annual plans grant 12 x the monthly credits once.
PLANS = (
    ("starter", "Starter", 5, 48, 100),
    ("pro", "Pro", 10, 96, 300),
    ("max", "Max", 25, 240, 1000),
    ("ultra", "Ultra", 50, 480, 2500),
    ("creator", "Creator", 100, 960, 5500),
)
PACK_CREDITS = (100, 500, 1000, 2000, 3000, 4000, 5000, 10000, 20000)
CUSTOM_PRODUCT_ID = "credits_custom"
CUSTOM_MIN_CREDITS = 100
CUSTOM_MAX_CREDITS = 100_000


class CatalogError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def stars_for_cents(usd_cents: int) -> int:
    """ceil(usd * 499 / 5) in exact integer arithmetic, minimum 1."""
    return max(1, -(-int(usd_cents) * STARS_RATE_STARS // STARS_RATE_CENTS))


def max_cents_for_stars(limit: int) -> int:
    """Largest USD amount (cents) whose Stars price stays within limit."""
    return int(limit) * STARS_RATE_CENTS // STARS_RATE_STARS


def check_invoice_amount(stars, subscription_period=None) -> int:
    """The Stars amount of one invoice, or CatalogError if Telegram limits
    forbid it. One-time invoices are bounded by STARS_MAX_PER_INVOICE;
    recurring ones need the 30-day period and at most 10,000 Stars."""
    if isinstance(stars, bool) or not isinstance(stars, int) or stars < 1:
        raise CatalogError("invalid_amount")
    if subscription_period is None:
        if stars > STARS_MAX_PER_INVOICE:
            raise CatalogError("stars_amount_above_limit")
        return stars
    if subscription_period != SUBSCRIPTION_PERIOD_SECONDS:
        raise CatalogError("unsupported_subscription_period")
    if stars > STARS_MAX_PER_SUBSCRIPTION:
        raise CatalogError("subscription_amount_above_limit")
    return stars


def _with_availability(product: dict) -> dict:
    available = product["stars"] <= STARS_MAX_PER_INVOICE
    product["available"] = available
    product["unavailable_reason"] = None if available else "stars_amount_above_limit"
    return product


def _plan_product(plan, period: str) -> dict:
    plan_id, name, monthly_usd, annual_usd, monthly_credits = plan
    usd = monthly_usd if period == "month" else annual_usd
    return {
        "product_id": f"plan_{plan_id}_{period}",
        "kind": "subscription",
        "title": f"SYLVEX {name} · {'1 месяц' if period == 'month' else '12 месяцев'}",
        "plan_id": plan_id,
        "plan_name": name,
        "period": period,
        "plan_key": f"{plan_id}_{period}",
        "days": PLAN_DAYS[period],
        "usd_cents": usd * 100,
        "credits": monthly_credits if period == "month" else monthly_credits * 12,
        "stars": stars_for_cents(usd * 100),
    }


def _credits_product(credits: int, product_id: str) -> dict:
    cents = int(credits) * 100 // CREDITS_PER_USD
    return {
        "product_id": product_id,
        "kind": "credits",
        "title": f"{int(credits):,} ⚡ SYLVEX".replace(",", " "),
        "plan_key": None,
        "days": None,
        "usd_cents": cents,
        "credits": int(credits),
        "stars": stars_for_cents(cents),
    }


def _products() -> dict:
    products = {}
    for plan in PLANS:
        for period in ("month", "year"):
            product = _plan_product(plan, period)
            products[product["product_id"]] = product
    for credits in PACK_CREDITS:
        product = _credits_product(credits, f"pack_{credits}")
        products[product["product_id"]] = product
    return products


PRODUCTS = _products()


def custom_max_credits() -> int:
    """Largest custom amount whose Stars price fits the invoice limit."""
    return min(CUSTOM_MAX_CREDITS, max_cents_for_stars(STARS_MAX_PER_INVOICE) * CREDITS_PER_USD // 100)


def parse_custom_credits(raw) -> int:
    text = str(raw if raw is not None else "").strip().replace(" ", "").replace(" ", "")
    if not text:
        raise CatalogError("amount_required")
    if not re.fullmatch(r"\d{1,7}", text):
        raise CatalogError("invalid_amount")
    credits = int(text)
    if credits < CUSTOM_MIN_CREDITS or credits > CUSTOM_MAX_CREDITS:
        raise CatalogError("amount_out_of_range")
    return credits


def resolve(product_id: str, credits=None) -> dict:
    """The authoritative Telegram product for a purchase request.

    Raises CatalogError for an unknown product, a malformed custom amount or
    a product above the verified Stars invoice limit.
    """
    product_id = str(product_id or "").strip()
    if product_id == CUSTOM_PRODUCT_ID:
        product = _credits_product(parse_custom_credits(credits), CUSTOM_PRODUCT_ID)
    elif product_id in PRODUCTS:
        product = dict(PRODUCTS[product_id])
    else:
        raise CatalogError("unknown_product")
    product = _with_availability(product)
    if not product["available"]:
        raise CatalogError(product["unavailable_reason"])
    return product


def pack_stars(credits: int):
    """Stars price of a fixed credit package, or None if not sold."""
    product = PRODUCTS.get(f"pack_{int(credits)}")
    return product["stars"] if product and product["stars"] <= STARS_MAX_PER_INVOICE else None


def public_catalog() -> dict:
    products = []
    for product_id in PRODUCTS:
        product = _with_availability(dict(PRODUCTS[product_id]))
        products.append({key: product.get(key) for key in (
            "product_id", "kind", "title", "credits", "stars", "plan_id", "period", "plan_key", "days",
            "available", "unavailable_reason")})
    return {
        "currency": "XTR",
        "provider": PROVIDER,
        "credits_per_usd": CREDITS_PER_USD,
        "stars_rate": {"stars": STARS_RATE_STARS, "usd_cents": STARS_RATE_CENTS},
        "stars_max_per_invoice": STARS_MAX_PER_INVOICE,
        "products": products,
        "custom": {
            "product_id": CUSTOM_PRODUCT_ID,
            "min_credits": CUSTOM_MIN_CREDITS,
            "max_credits": custom_max_credits(),
        },
        "renewal": "none",
    }
