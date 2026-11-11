-- B09 — шаг 4c: проверка перед удалением (только чтение). Выполнить сразу перед шагом 6.
-- Ожидаемо: строки 4c-1 ровно как в инвентаризации; 4c-2 = 0 везде; 4c-3 — только users, user_events,
-- user_profiles, user_referrals.

-- 4c-0. Снимок ДО (сохранить: после шагов 6 и 5 сверяется в 7_verify_all.sql)
SELECT (SELECT COUNT(*) FROM users) AS users_total, (SELECT COUNT(*) FROM user_events) AS user_events_total,
       (SELECT COUNT(*) FROM user_profiles) AS user_profiles_total, (SELECT COUNT(*) FROM user_referrals) AS user_referrals_total,
       (SELECT COUNT(*) FROM sylvex_accounts) AS sylvex_accounts_total;

-- 4c-1. Кому принадлежат строки (по каждому ID)
SELECT t.telegram_id,
       (SELECT COUNT(*) FROM users          WHERE telegram_id = t.telegram_id) AS users,
       (SELECT COUNT(*) FROM user_events    WHERE telegram_id = t.telegram_id) AS user_events,
       (SELECT COUNT(*) FROM user_profiles  WHERE telegram_id = t.telegram_id) AS user_profiles,
       (SELECT COUNT(*) FROM user_referrals WHERE telegram_id = t.telegram_id) AS user_referrals
FROM (VALUES (12345::bigint), (123456789::bigint), (900000001::bigint)) AS t(telegram_id)
ORDER BY t.telegram_id;

-- 4c-2. Связи с ДРУГИМИ пользователями через реферальный код тестового аккаунта (должно быть 0)
SELECT
  (SELECT COUNT(*) FROM referral_attributions WHERE inviter_telegram_id IN (12345, 123456789, 900000001)) AS invited_by_test_ids,
  (SELECT COUNT(*) FROM referral_attributions WHERE invited_telegram_id IN (12345, 123456789, 900000001)) AS test_ids_invited,
  (SELECT COUNT(*) FROM referral_attributions ra JOIN user_referrals ur ON ur.code = ra.referral_code
     WHERE ur.telegram_id IN (12345, 123456789, 900000001)) AS uses_of_test_codes;

-- 4c-3. Расширенная инвентаризация: все столбцы, в имени которых есть telegram / inviter / invited / referr,
--       плюс прежний список владельцев. Показывает только совпадения.
SELECT * FROM (
  SELECT c.table_name, c.column_name,
         (xpath('/row/n/text()', query_to_xml(format(
              'SELECT COUNT(*) AS n FROM %I WHERE %I::text IN (''12345'',''123456789'',''900000001'')',
              c.table_name, c.column_name), false, true, '')))[1]::text::bigint AS rows
  FROM information_schema.columns c
  JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
  WHERE c.table_schema = current_schema()
    AND c.data_type IN ('bigint','integer','numeric','text','character varying')
    AND (c.column_name LIKE '%telegram%' OR c.column_name LIKE 'inviter%' OR c.column_name LIKE 'invited%'
         OR c.column_name LIKE 'referr%'
         OR c.column_name IN ('user_key','user_id','requester_id','sender_id','recipient_id','addressee_id','actor_id',
                              'owner_key','subject_key'))
) found WHERE rows > 0 ORDER BY table_name, column_name;
