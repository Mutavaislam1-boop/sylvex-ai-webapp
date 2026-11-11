-- B09 / S7-04 — шаг 3: проверка (только чтение). Ожидаемо: missing = 0, test_account = 1 строка origin 'telegram'.
SELECT COUNT(*) AS missing
FROM users u
WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram');

SELECT a.origin, (a.merged_telegram_id IS NULL AND a.merged_into_account_id IS NULL AND a.merged_at IS NULL) AS not_merged,
       a.storage_telegram_id IS NULL AS no_storage_key, a.created_at, length(a.account_id::text) AS id_digits,
       substr(a.account_id::text, 3, 4) = '0626' AND substr(a.account_id::text, 7, 2) = '99' AS telegram_id_format
FROM sylvex_accounts a WHERE a.active_telegram_id = 7772859187;
