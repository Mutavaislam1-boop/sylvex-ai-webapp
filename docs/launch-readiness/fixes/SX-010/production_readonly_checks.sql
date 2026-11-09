-- SX-010 / B14: four read-only checks of purchases without a date.
--
-- * SELECT only, inside one READ ONLY transaction that ends with ROLLBACK.
-- * Output is aggregated: no telegram_id, charge_id, payload, order id,
--   name, e-mail or per-user amount is returned.
-- * Nothing is restored here. A date counts as "restorable" only when it
--   comes from a record written by the payment itself (see query 3).
--
-- "Undated" = purchases.created_at is NULL or an empty string. The column is
-- TIMESTAMP in the API schema and TEXT in the bot schema; every check works
-- on both.
--
-- The SX-010 fix reached Production at 2026-11-08 20:37 UTC (API 60eb6c2d)
-- and 20:39 UTC (bot d3987200). Query 4 uses 20:37 UTC.

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

-- 1. Schema of purchases.created_at and of every date source used below,
--    plus the database time zone (TIMESTAMP columns are compared as UTC).
SELECT want.tbl, want.col,
       c.data_type,
       c.column_default,
       c.is_nullable,
       CASE WHEN c.column_name IS NULL THEN 'MISSING' ELSE 'ok' END AS present,
       CASE WHEN want.tbl = 'purchases' AND want.col = 'charge_id' THEN
            (SELECT COUNT(*) FROM pg_indexes x
              WHERE x.schemaname = current_schema() AND x.tablename = 'purchases'
                AND x.indexdef ILIKE 'CREATE UNIQUE INDEX%' AND x.indexdef ILIKE '%(charge_id)%')
       END AS unique_indexes,
       current_setting('TimeZone') AS db_timezone
  FROM (VALUES ('purchases','created_at'), ('purchases','charge_id'), ('purchases','payload'),
               ('shop_orders','paid_at'), ('shop_orders','charge_id'),
               ('payment_inbox','paid_at'), ('payment_inbox','received_at'),
               ('subscription_payments','created_at'), ('subscription_events','created_at'),
               ('subscriptions','created_at'), ('subscriptions','starts_at'),
               ('paypal_orders','paypal_capture_id'), ('paypal_orders','updated_at')) AS want(tbl, col)
  LEFT JOIN information_schema.columns c
         ON c.table_schema = current_schema() AND c.table_name = want.tbl AND c.column_name = want.col
 ORDER BY want.tbl, want.col;

-- 2. What the undated purchases are: by provider / status / currency.
--    Expected total for completed rows on 07.11: 72.
SELECT COALESCE(provider, '(all)')                                              AS provider,
       COALESCE(status, '(all)')                                                AS status,
       COALESCE(currency, '(all)')                                              AS currency,
       COUNT(*)                                                                 AS undated_rows,
       COUNT(*) FILTER (WHERE created_at IS NULL)                               AS null_created_at,
       COUNT(*) FILTER (WHERE created_at IS NOT NULL)                           AS empty_string_created_at,
       COUNT(DISTINCT charge_id)                                                AS distinct_charge_ids,
       COUNT(*) FILTER (WHERE charge_id IS NULL OR charge_id = '')              AS without_charge_id,
       COUNT(*) FILTER (WHERE payload ~ '^sylvex_order:[0-9a-f]{32}$')          AS payload_names_shop_order,
       COUNT(*) FILTER (WHERE payload LIKE 'stripe_invoice:%')                  AS payload_names_stripe_invoice
  FROM purchases
 WHERE NULLIF(btrim(created_at::text), '') IS NULL
 GROUP BY GROUPING SETS ((provider, status, currency), ())
 ORDER BY (provider IS NULL), provider, status, currency;

-- 3. For every undated purchase: which records written by the payment itself
--    hold its time, whether they agree, and how many rows are restorable.
--    Primary sources (written by the payment, keyed by charge_id or order id):
--      shop_orders.paid_at             set in the same transaction as the purchase
--      payment_inbox.paid_at           payment time reported by Telegram (epoch)
--      subscription_payments.created_at  same transaction (Stars subscriptions)
--      subscription_events.created_at  same transaction, key 'purchase:<charge_id>'
--    Secondary (counted, never used alone): subscriptions.created_at/starts_at,
--      paypal_orders.updated_at, payment_inbox.received_at.
--    Buckets b1..b7 are disjoint; per group b1+..+b7 = undated_rows.
WITH dup AS (
       SELECT charge_id, COUNT(*) AS n FROM purchases
        WHERE charge_id IS NOT NULL AND charge_id <> '' GROUP BY charge_id),
     u AS (
       SELECT p.id, p.provider, p.status, NULLIF(p.charge_id, '') AS charge_id,
              substring(p.payload FROM '^sylvex_order:([0-9a-f]{32})$') AS payload_order_id
         FROM purchases p
        WHERE NULLIF(btrim(p.created_at::text), '') IS NULL),
     s AS (
       SELECT u.id, u.provider, u.status, COALESCE(dup.n, 0) AS dup_n,
              oc.order_id AS oc_id, EXTRACT(EPOCH FROM oc.paid_at) AS oc_t,
              op.order_id AS op_id, EXTRACT(EPOCH FROM op.paid_at) AS op_t,
              i.paid_at::double precision                          AS in_t,
              EXTRACT(EPOCH FROM sp.created_at)                    AS sp_t,
              EXTRACT(EPOCH FROM se.created_at)                    AS se_t,
              (sub.d IS NOT NULL)                                  AS has_sub_date,
              (pp.updated_at IS NOT NULL)                          AS has_paypal,
              (i.received_at IS NOT NULL)                          AS has_inbox_received
         FROM u
         LEFT JOIN dup ON dup.charge_id = u.charge_id
         LEFT JOIN shop_orders oc ON oc.charge_id = u.charge_id AND oc.paid_at IS NOT NULL
         LEFT JOIN shop_orders op ON op.order_id = u.payload_order_id AND op.paid_at IS NOT NULL
         LEFT JOIN payment_inbox i ON i.charge_id = u.charge_id
         LEFT JOIN subscription_payments sp ON sp.charge_id = u.charge_id
         LEFT JOIN subscription_events se ON se.event_key = 'purchase:' || u.charge_id
         LEFT JOIN LATERAL (
                SELECT 1 AS d FROM subscriptions x
                 WHERE x.charge_id = u.charge_id
                   AND (x.created_at::text ~ '^\d{4}-\d{2}-\d{2}' OR x.starts_at::text ~ '^\d{4}-\d{2}-\d{2}')
                 LIMIT 1) sub ON TRUE
         LEFT JOIN LATERAL (
                SELECT y.updated_at FROM paypal_orders y
                 WHERE u.charge_id IN (y.paypal_capture_id, y.paypal_order_id) LIMIT 1) pp ON TRUE),
     t AS (
       SELECT s.*,
              (oc_id IS NOT NULL AND op_id IS NOT NULL AND oc_id <> op_id)      AS order_conflict,
              (SELECT COUNT(v) FROM unnest(ARRAY[COALESCE(oc_t, op_t), in_t, sp_t, se_t]) v) AS n_primary,
              (SELECT MAX(v) - MIN(v) FROM unnest(ARRAY[COALESCE(oc_t, op_t), in_t, sp_t, se_t]) v) AS spread_s
         FROM s)
SELECT COALESCE(provider, '(all)') AS provider,
       COALESCE(status, '(all)')   AS status,
       COUNT(*)                                                                         AS undated_rows,
       COUNT(*) FILTER (WHERE dup_n > 1)                                                AS b1_charge_id_shared,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND order_conflict)                            AS b2_two_different_orders,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND NOT order_conflict AND n_primary >= 2 AND spread_s <= 300) AS b3_two_plus_sources_agree,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND NOT order_conflict AND n_primary >= 2 AND spread_s > 300)  AS b4_sources_disagree,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND NOT order_conflict AND n_primary = 1)      AS b5_single_source,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND NOT order_conflict AND n_primary = 0
                          AND (has_sub_date OR has_paypal OR has_inbox_received))       AS b6_secondary_only,
       COUNT(*) FILTER (WHERE dup_n <= 1 AND NOT order_conflict AND n_primary = 0
                          AND NOT (has_sub_date OR has_paypal OR has_inbox_received))   AS b7_no_source,
       COUNT(*) FILTER (WHERE oc_id IS NOT NULL)                                        AS src_order_by_charge_id,
       COUNT(*) FILTER (WHERE op_id IS NOT NULL)                                        AS src_order_by_payload,
       COUNT(*) FILTER (WHERE in_t IS NOT NULL)                                         AS src_inbox_paid_at,
       COUNT(*) FILTER (WHERE sp_t IS NOT NULL)                                         AS src_subscription_payment,
       COUNT(*) FILTER (WHERE se_t IS NOT NULL)                                         AS src_subscription_event,
       COUNT(*) FILTER (WHERE has_sub_date)                                             AS sec_subscriptions_date,
       COUNT(*) FILTER (WHERE has_paypal)                                               AS sec_paypal_updated_at,
       COUNT(*) FILTER (WHERE has_inbox_received)                                       AS sec_inbox_received_at,
       ROUND(MAX(spread_s)::numeric, 1)                                                 AS max_spread_seconds
  FROM t
 GROUP BY GROUPING SETS ((provider, status), ())
 ORDER BY (provider IS NULL), provider, status;

-- 4. Is anything still written without a date after the fix went live?
--    Expected: undated_after_first_dated_post_deploy_row = 0 and
--    paid_orders_after_deploy_with_undated_purchase = 0.
WITH d AS (
       SELECT id,
              NULLIF(btrim(created_at::text), '') IS NULL AS undated,
              CASE WHEN created_at::text ~ '^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}'
                   THEN replace(substring(created_at::text FROM 1 FOR 19), 'T', ' ')::timestamp END AS ts
         FROM purchases),
     first_new AS (SELECT MIN(id) AS id FROM d WHERE ts >= TIMESTAMP '2026-11-08 20:37:00')
SELECT (SELECT COUNT(*) FROM d WHERE undated)                                          AS undated_total,
       (SELECT COUNT(*) FROM d WHERE NOT undated AND ts IS NULL)                       AS dated_but_unparseable,
       (SELECT COUNT(*) FROM d WHERE ts >= TIMESTAMP '2026-11-08 20:37:00')            AS dated_rows_since_deploy,
       (SELECT COUNT(*) FROM d, first_new WHERE d.undated AND d.id > first_new.id)     AS undated_after_first_dated_post_deploy_row,
       (SELECT COUNT(*) FROM shop_orders o JOIN purchases q ON q.charge_id = o.charge_id
         WHERE o.paid_at >= TIMESTAMP '2026-11-08 20:37:00'
           AND NULLIF(btrim(q.created_at::text), '') IS NULL)                          AS paid_orders_after_deploy_with_undated_purchase,
       (SELECT MAX(ts) FROM d)                                                         AS latest_purchase_time;

ROLLBACK;
