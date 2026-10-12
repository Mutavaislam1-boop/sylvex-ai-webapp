"""Check which Telegram Stars amounts the Bot API accepts for invoice links.

Creates invoice links with createInvoiceLink and reports, per amount,
whether Telegram ACCEPTED THE INVOICE CREATION or the error it returned.
Acceptance only means Telegram will create such an invoice; it says nothing
about a payment ever completing at that amount.

Safe by construction:
  - nothing is sent to any chat and the links are never printed or stored;
  - the payload "sylvex_limit_check:..." is refused at pre-checkout by both
    the polling bot and the webapp's Stars webhook, so even an opened link
    cannot be paid, and no credits or subscriptions can be granted.

Run where BOT_TOKEN is set, e.g. `railway run python3 scripts/verify_stars_invoice_limits.py`.
Defaults check one-time amounts 10000 19960 23952 95808 and the 30-day
subscription cap (10000 accepted, 10001 refused). Then set
STARS_MAX_PER_INVOICE to the highest accepted one-time amount you want to
offer.
"""
import argparse
import json
import os
import sys
import uuid

import requests

API = "https://api.telegram.org/bot{token}/createInvoiceLink"
DEFAULT_AMOUNTS = (10000, 19960, 23952, 95808)
SUBSCRIPTION_PERIOD = 2592000  # the only period Telegram supports (30 days)


def create_link(session, token: str, amount: int, subscription: bool) -> dict:
    payload = {
        "title": "SYLVEX limit check",
        "description": "Not for sale. Used only to verify the Stars invoice limit.",
        "payload": f"sylvex_limit_check:{amount}:{uuid.uuid4().hex[:8]}",
        "currency": "XTR",
        "prices": [{"label": "Limit check", "amount": int(amount)}],
    }
    if subscription:
        payload["subscription_period"] = SUBSCRIPTION_PERIOD
    response = session.post(API.format(token=token), json=payload, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {}
    accepted = bool(body.get("ok")) and bool(body.get("result"))
    return {
        "amount": int(amount),
        "type": "subscription_30_days" if subscription else "one_time",
        "invoice_creation": "accepted" if accepted else "rejected",
        "http_status": response.status_code,
        "error": None if accepted else (body.get("description") or f"http_{response.status_code}"),
    }


def run(token: str, amounts, check_subscriptions: bool, session=None) -> list:
    session = session or requests.Session()
    results = [create_link(session, token, amount, False) for amount in amounts]
    if check_subscriptions:
        results += [create_link(session, token, amount, True) for amount in (10000, 10001)]
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify Telegram Stars invoice limits without payments.")
    parser.add_argument("amounts", nargs="*", type=int, default=list(DEFAULT_AMOUNTS))
    parser.add_argument("--no-subscriptions", action="store_true", help="skip the 30-day subscription cap check")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args(argv)
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("BOT_TOKEN is not set.", file=sys.stderr)
        return 2
    results = run(token, args.amounts, not args.no_subscriptions)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['type']:<22} {r['amount']:>7} ⭐  invoice creation {r['invoice_creation']}"
                  + (f"  ({r['error']})" if r["error"] else ""))
    accepted = [r["amount"] for r in results if r["type"] == "one_time" and r["invoice_creation"] == "accepted"]
    print(f"\nHighest one-time amount accepted for invoice creation: {max(accepted) if accepted else 'none'}"
          "\n(Invoice creation only; no payment was attempted.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
