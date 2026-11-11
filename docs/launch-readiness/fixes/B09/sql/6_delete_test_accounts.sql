-- B09 — шаг 6: удаление ТОЛЬКО трёх тестовых Telegram ID 12345, 123456789, 900000001 (запись).
-- Состав по инвентаризации Production: users 3, user_events 1, user_profiles 1, user_referrals 1;
-- платёжных записей, генераций, кошельков и SYLVEX ID нет.
-- Одна транзакция. Любое расхождение (лишняя строка, связь с другим пользователем, неверное
-- число удалённых строк) вызывает ошибку — PostgreSQL откатывает всё, ничего не удаляется.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $delete_test_accounts$
DECLARE
  ids CONSTANT bigint[] := ARRAY[12345, 123456789, 900000001];
  n bigint;
BEGIN
  -- Защиты (до любого удаления)
  IF (SELECT COUNT(*) FROM users WHERE telegram_id = ANY(ids)) <> 3 THEN
    RAISE EXCEPTION 'expected exactly 3 test users';
  END IF;
  IF EXISTS (SELECT 1 FROM sylvex_accounts WHERE active_telegram_id = ANY(ids) OR merged_telegram_id = ANY(ids)
             OR storage_telegram_id = ANY(ids)) THEN
    RAISE EXCEPTION 'a test ID has a SYLVEX identity';
  END IF;
  IF to_regclass('admin_users') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM admin_users WHERE telegram_id = ANY(ids)) THEN RAISE EXCEPTION 'a test ID is an administrator'; END IF;
  END IF;
  IF to_regclass('referral_attributions') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM referral_attributions WHERE inviter_telegram_id = ANY(ids) OR invited_telegram_id = ANY(ids)) THEN
      RAISE EXCEPTION 'a test ID is linked to another user by referral';
    END IF;
  END IF;
  IF to_regclass('purchases') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM purchases WHERE telegram_id = ANY(ids)) THEN RAISE EXCEPTION 'a test ID has purchases'; END IF;
  END IF;
  IF to_regclass('subscription_agreements') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM subscription_agreements WHERE telegram_id = ANY(ids)) THEN RAISE EXCEPTION 'a test ID has Stars subscriptions'; END IF;
  END IF;
  IF to_regclass('prostudio_generation_jobs') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM prostudio_generation_jobs WHERE telegram_id = ANY(ids)) THEN RAISE EXCEPTION 'a test ID has generations'; END IF;
  END IF;
  IF to_regclass('sylvex_storage_ownership') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM sylvex_storage_ownership WHERE owner_key = ANY(ids)) THEN RAISE EXCEPTION 'a test ID owns stored files'; END IF;
  END IF;
  IF to_regclass('user_credit_wallets') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM user_credit_wallets WHERE telegram_id = ANY(ids)) THEN RAISE EXCEPTION 'a test ID has a credit wallet'; END IF;
  END IF;

  -- Удаление: точное число строк по инвентаризации, иначе откат
  DELETE FROM user_events WHERE telegram_id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'user_events: expected 1, got %', n; END IF;

  DELETE FROM user_profiles WHERE telegram_id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'user_profiles: expected 1, got %', n; END IF;

  DELETE FROM user_referrals WHERE telegram_id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'user_referrals: expected 1, got %', n; END IF;

  DELETE FROM users WHERE telegram_id = ANY(ids);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 3 THEN RAISE EXCEPTION 'users: expected 3, got %', n; END IF;

  RAISE NOTICE 'deleted: user_events 1, user_profiles 1, user_referrals 1, users 3';
END
$delete_test_accounts$;

-- Проверка внутри той же транзакции: всё 0
SELECT (SELECT COUNT(*) FROM users          WHERE telegram_id IN (12345, 123456789, 900000001)) AS users_left,
       (SELECT COUNT(*) FROM user_events    WHERE telegram_id IN (12345, 123456789, 900000001)) AS events_left,
       (SELECT COUNT(*) FROM user_profiles  WHERE telegram_id IN (12345, 123456789, 900000001)) AS profiles_left,
       (SELECT COUNT(*) FROM user_referrals WHERE telegram_id IN (12345, 123456789, 900000001)) AS referrals_left;
COMMIT;
