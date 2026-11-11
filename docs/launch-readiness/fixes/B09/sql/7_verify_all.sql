-- B09 — шаг 7: итоговая проверка (только чтение).
-- Ожидаемо: missing = 0 (19 получили SYLVEX ID, 3 тестовых удалены), test_users = 0,
-- у 7772859187 одна строка origin 'telegram' с исходной датой.
SELECT (SELECT COUNT(*) FROM users u
        WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
          AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
          AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram')) AS missing,
       (SELECT COUNT(*) FROM users WHERE telegram_id IN (12345, 123456789, 900000001)) AS test_users,
       (SELECT COUNT(*) FROM sylvex_accounts WHERE active_telegram_id = 7772859187 AND origin = 'telegram') AS test_account_identity,
       (SELECT created_at FROM sylvex_accounts WHERE active_telegram_id = 7772859187) AS test_account_created_at;
