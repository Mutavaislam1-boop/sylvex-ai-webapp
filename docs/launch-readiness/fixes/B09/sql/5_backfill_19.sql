-- B09 — шаг 5: SYLVEX ID для 19 Telegram-пользователей (запись). Выполнять ПОСЛЕ шага 6.
-- ОДНА команда DO, атомарна: при любом несоответствии — ошибка и полный откат, ничего не записано.
-- Только INSERT в sylvex_accounts через существующий распределитель sylvex_allocate_telegram_account_id().
-- created_at — ТОЛЬКО действительная исходная дата users.created_at (без подстановки NOW()):
-- если хоть у одного из 19 дата не читается или в будущем — остановка.
DO $backfill_19$
DECLARE
  expected CONSTANT int := 19;
  n bigint;
BEGIN
  PERFORM set_config('lock_timeout', '5s', true);
  PERFORM set_config('statement_timeout', '60s', true);

  IF EXISTS (SELECT 1 FROM users WHERE telegram_id IN (12345, 123456789, 900000001)) THEN
    RAISE EXCEPTION 'STOP: run step 6 first (test users still present)';
  END IF;

  -- Кандидаты: Telegram-пользователи без SYLVEX ID (то же условие, что backfill_telegram_accounts()).
  SELECT COUNT(*) INTO n FROM users u
  WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram');
  IF n <> expected THEN RAISE EXCEPTION 'STOP: expected % users without a SYLVEX ID, found %', expected, n; END IF;

  SELECT COUNT(*) INTO n FROM users u
  WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram')
    AND (sylvex_safe_timestamp(u.created_at::text) IS NULL OR sylvex_safe_timestamp(u.created_at::text) > NOW());
  IF n <> 0 THEN RAISE EXCEPTION 'STOP: % users have no valid original registration date', n; END IF;

  INSERT INTO sylvex_accounts (account_id, active_telegram_id, origin, created_at)
  SELECT sylvex_allocate_telegram_account_id(), u.telegram_id, 'telegram', sylvex_safe_timestamp(u.created_at::text)
  FROM users u
  WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
    AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id AND a.origin = 'telegram')
    AND sylvex_safe_timestamp(u.created_at::text) IS NOT NULL
  ORDER BY u.telegram_id;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> expected THEN RAISE EXCEPTION 'STOP: inserted %, expected %', n, expected; END IF;
END
$backfill_19$;
