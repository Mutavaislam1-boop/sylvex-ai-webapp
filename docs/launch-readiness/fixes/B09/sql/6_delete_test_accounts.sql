-- B09 — шаг 6: удаление ТОЛЬКО трёх тестовых Telegram ID (запись).
-- ШАБЛОН: список DELETE заполняется точно по результату 4_test_accounts_inventory.sql
-- (каждая таблица с rows > 0 проверяется вручную). Динамического удаления по всем
-- таблицам нет намеренно: столбец user_id/actor_id в чужой таблице может значить другое.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- Защита: остановиться, если хоть один ID оказался не тестовым.
DO $guard$
BEGIN
  IF (SELECT COUNT(*) FROM users WHERE telegram_id IN (12345, 123456789, 900000001)) > 3 THEN
    RAISE EXCEPTION 'unexpected users rows';
  END IF;
  IF EXISTS (SELECT 1 FROM sylvex_accounts WHERE active_telegram_id IN (12345, 123456789, 900000001)
             OR merged_telegram_id IN (12345, 123456789, 900000001)
             OR storage_telegram_id IN (12345, 123456789, 900000001)) THEN
    RAISE EXCEPTION 'a test ID has a SYLVEX identity - review first';
  END IF;
  -- Администратор: без SYLVEX ID строки admin_accounts быть не может (проверено выше);
  -- остаётся старая таблица admin_users с telegram_id.
  IF to_regclass('admin_users') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM admin_users WHERE telegram_id IN (12345, 123456789, 900000001)) THEN
      RAISE EXCEPTION 'a test ID is an administrator';
    END IF;
  END IF;
  IF to_regclass('prostudio_generation_jobs') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM prostudio_generation_jobs WHERE telegram_id IN (12345, 123456789, 900000001)
               AND status NOT IN ('completed','failed','canceled','cancelled','rejected')) THEN
      RAISE EXCEPTION 'a test ID has a generation in progress';
    END IF;
  END IF;
  IF to_regclass('sylvex_storage_ownership') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM sylvex_storage_ownership WHERE owner_key IN (12345, 123456789, 900000001)) THEN
      RAISE EXCEPTION 'a test ID owns stored files - decide on R2 objects first';
    END IF;
  END IF;
END
$guard$;

-- Строки по инвентаризации (пример; заменяется точным списком):
-- DELETE FROM app_presence        WHERE telegram_id::text IN ('12345','123456789','900000001');
-- DELETE FROM user_profiles       WHERE telegram_id IN (12345, 123456789, 900000001);
-- ... по одной строке на каждую таблицу из шага 4 ...
-- Платёжные таблицы (category = financial) — только по отдельному решению владельца.

-- Последним: сами пользователи (user_credit_wallets удаляется каскадно).
DELETE FROM users WHERE telegram_id IN (12345, 123456789, 900000001);

-- Перед COMMIT: повторить 4b — для трёх ID должно быть rows = 0 везде, кроме оставленных платёжных.
-- Если что-то не так — ROLLBACK.
COMMIT;
