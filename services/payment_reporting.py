"""Read-only payment provenance for administrative cash reports.

No balance, entitlement, charge or purchase is changed here. Missing or
conflicting Stripe provenance stays unknown rather than becoming revenue.
"""
import re


def payment_mode_sql(cursor, alias="p"):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", alias):
        raise ValueError("invalid_reporting_alias")
    p = alias + "."
    cursor.execute("""SELECT table_name,column_name FROM information_schema.columns
        WHERE table_schema=current_schema() AND table_name IN ('stripe_events','shop_orders')""")
    columns = set(tuple(r) for r in cursor.fetchall())
    journal = "NULL::text"
    if {('stripe_events', 'livemode'), ('stripe_events', 'purchase_charge_id')} <= columns:
        journal = """(SELECT CASE WHEN COUNT(*)=0 THEN NULL
            WHEN COUNT(e.livemode)<>COUNT(*) THEN 'unknown'
            WHEN BOOL_AND(e.livemode) THEN 'live'
            WHEN NOT BOOL_OR(e.livemode) THEN 'test' ELSE 'unknown' END
            FROM stripe_events e WHERE e.purchase_charge_id=""" + p + """charge_id
            AND e.outcome IN ('granted','duplicate'))"""
    historical_test = "NULL::text"
    if {('shop_orders', 'charge_id'), ('shop_orders', 'provider_invoice_id')} <= columns:
        # Conservative historical exclusion only: never infer Live from a
        # currently selected key, a customer, or a live-looking ID.
        historical_test = "(SELECT 'test' FROM shop_orders o WHERE o.charge_id=" + p + "charge_id AND LEFT(o.provider_invoice_id,8)='cs_test_' LIMIT 1)"
    provider = "LOWER(COALESCE(" + p + "provider,''))"
    currency = "UPPER(COALESCE(" + p + "currency,''))"
    stripe_mode = ("CASE WHEN " + journal + "='live' AND " + historical_test + "='test' THEN 'unknown'"
                   " ELSE COALESCE(" + journal + "," + historical_test + ",'unknown') END")
    return ("(CASE WHEN " + provider + "='stripe' THEN (" + stripe_mode + ")"
            " WHEN " + provider + " IN ('dev','test','mock') OR " + currency + "='DEV' THEN 'test'"
            " WHEN " + provider + " IN ('telegram_stars','telegram_stars_subscription') AND " + currency + "='XTR' THEN 'live'"
            " ELSE 'unknown' END)")


def payment_amount_sql(alias="p"):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", alias):
        raise ValueError("invalid_reporting_alias")
    p = alias + "."
    return "(CASE WHEN LOWER(COALESCE(" + p + "provider,''))='stripe' THEN COALESCE(" + p + "amount,0)::numeric/100 ELSE COALESCE(" + p + "amount,0)::numeric END)"
