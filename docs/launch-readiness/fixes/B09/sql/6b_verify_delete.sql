-- B09 — шаг 6b: проверка после шага 6 (только чтение). Ожидаемо: 0, 0, 0, 0.
SELECT (SELECT COUNT(*) FROM users          WHERE telegram_id IN (12345, 123456789, 900000001)) AS users_left,
       (SELECT COUNT(*) FROM user_events    WHERE telegram_id IN (12345, 123456789, 900000001)) AS events_left,
       (SELECT COUNT(*) FROM user_profiles  WHERE telegram_id IN (12345, 123456789, 900000001)) AS profiles_left,
       (SELECT COUNT(*) FROM user_referrals WHERE telegram_id IN (12345, 123456789, 900000001)) AS referrals_left;
