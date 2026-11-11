-- B09 / S7-04 — шаг 1: предпросмотр (только чтение).
-- Те же условия, что count_telegram_accounts_missing() / backfill_telegram_accounts().
SELECT COUNT(*)                                                    AS missing,
       COUNT(*) FILTER (WHERE u.telegram_id = 7772859187)          AS test_account_missing,
       COUNT(*) FILTER (WHERE sylvex_safe_timestamp(u.created_at::text) IS NULL) AS without_readable_created_at,
       MIN(sylvex_safe_timestamp(u.created_at::text))              AS oldest_created_at,
       MAX(sylvex_safe_timestamp(u.created_at::text))              AS newest_created_at
FROM users u
WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram');
