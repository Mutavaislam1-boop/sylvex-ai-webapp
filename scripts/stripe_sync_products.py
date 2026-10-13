"""Create or reuse every SYLVEX Stripe product and price, then print the IDs.

Idempotent: plan and pack products have fixed Stripe product ids
(sylvex_plan_pro, sylvex_pack_1000, ...) and every price has a lookup key
(sylvex_plan_pro_month, sylvex_pack_1000, ...), so running it again reuses
what exists and creates only what is missing. It never deletes or archives
anything; a price whose amount changed is replaced by a new price that takes
over the lookup key, while the old one stays active for its subscribers.

The backend runs the same sync on startup and before the first checkout,
so this script is optional. Use it to create the catalog ahead of time or
to see the resulting IDs. With DATABASE_URL (or DATABASE_PUBLIC_URL) set,
it also stores the mapping the backend reads (table stripe_catalog).

Run from the sylvex-ai-webapp repo root, e.g. via `railway run`:

    STRIPE_SECRET_KEY=sk_test_... python3 scripts/stripe_sync_products.py
    STRIPE_SECRET_KEY=... DATABASE_PUBLIC_URL=... python3 scripts/stripe_sync_products.py --output stripe_ids.json
"""
import argparse
import json
import os
import sys

# Lives one level under the repo root (scripts/); add the repo root so
# `services.*` resolves when run from there.
sys.path.insert(0, os.getcwd())

from services import stripe_billing  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", help="also write the mapping to this JSON file")
    args = parser.parse_args(argv)

    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        print("STRIPE_SECRET_KEY is not set.", file=sys.stderr)
        return 2
    client = stripe_billing.StripeClient(key)
    mapping = stripe_billing.sync_catalog(client)

    database_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if database_url:
        import psycopg2

        def connect():
            return psycopg2.connect(database_url)

        stripe_billing.ensure_tables(connect)
        stripe_billing.save_catalog(connect, mapping, client.livemode)

    print(f"Stripe {'LIVE' if client.livemode else 'test'} mode")
    print(f"{'lookup key':<30} {'Stripe product':<26} {'Stripe price':<32} status")
    for lookup_key, entry in mapping.items():
        print(f"{lookup_key:<30} {entry['stripe_product_id'] or '-':<26} {entry['stripe_price_id'] or '-':<32} {entry['price_status']}")
    statuses = [entry["price_status"] for entry in mapping.values()]
    print(f"\ncreated {statuses.count('created')}, replaced {statuses.count('replaced')}, "
          f"reused {statuses.count('reused')}, unavailable {statuses.count('product_inactive')}"
          + (", saved to stripe_catalog" if database_url else ""))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump({"livemode": client.livemode, "products": mapping}, handle, indent=2, ensure_ascii=False)
    return 1 if statuses.count("product_inactive") else 0


if __name__ == "__main__":
    sys.exit(main())
