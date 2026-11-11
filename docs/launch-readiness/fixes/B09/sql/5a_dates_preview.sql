-- B09 — шаг 5a: исходные даты регистрации 19 пользователей (только чтение).
-- Ожидаемо: total = 19, valid_dates = 19, invalid_dates = 0, future_dates = 0.
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE sylvex_safe_timestamp(u.created_at::text) IS NOT NULL)            AS valid_dates,
       COUNT(*) FILTER (WHERE sylvex_safe_timestamp(u.created_at::text) IS NULL)                AS invalid_dates,
       COUNT(*) FILTER (WHERE sylvex_safe_timestamp(u.created_at::text) > NOW())                AS future_dates,
       MIN(sylvex_safe_timestamp(u.created_at::text)) AS oldest, MAX(sylvex_safe_timestamp(u.created_at::text)) AS newest
FROM users u
WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
  AND u.telegram_id NOT IN (12345, 123456789, 900000001)
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
  AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram');
