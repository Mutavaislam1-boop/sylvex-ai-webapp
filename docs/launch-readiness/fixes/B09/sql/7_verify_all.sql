-- B09 — шаг 7: итоговая проверка (только чтение), после шагов 6 и 5.
-- Ожидаемо: missing = 0, test_users = 0, test_account_identity = 1 с исходной датой.
-- Сравнить с 4c-0: users_total = ДО − 3; user_events_total, user_profiles_total, user_referrals_total = ДО − 1;
-- sylvex_accounts_total = ДО + 19. Любое другое отличие — сообщить до продолжения.
SELECT (SELECT COUNT(*) FROM users u
        WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
          AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
          AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram')) AS missing,
       (SELECT COUNT(*) FROM users WHERE telegram_id IN (12345, 123456789, 900000001)) AS test_users,
       (SELECT COUNT(*) FROM sylvex_accounts WHERE active_telegram_id = 7772859187 AND origin = 'telegram') AS test_account_identity,
       (SELECT created_at FROM sylvex_accounts WHERE active_telegram_id = 7772859187) AS test_account_created_at;

SELECT (SELECT COUNT(*) FROM users) AS users_total, (SELECT COUNT(*) FROM user_events) AS user_events_total,
       (SELECT COUNT(*) FROM user_profiles) AS user_profiles_total, (SELECT COUNT(*) FROM user_referrals) AS user_referrals_total,
       (SELECT COUNT(*) FROM sylvex_accounts) AS sylvex_accounts_total;
