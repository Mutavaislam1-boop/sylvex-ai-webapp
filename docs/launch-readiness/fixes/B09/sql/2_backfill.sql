-- B09 / S7-04 — шаг 2: SYLVEX ID для Telegram-пользователей без него (запись).
-- Повторяет services/account_identity.backfill_telegram_accounts() одной транзакцией:
--   * только INSERT в sylvex_accounts, только для users.telegram_id без строки;
--   * ID из существующего распределителя sylvex_allocate_telegram_account_id() (SS 0626 99 NNNN);
--   * created_at = первоначальная дата users.created_at (sylvex_safe_timestamp), иначе NOW();
--   * существующие строки и ID не меняются (NOT EXISTS + ON CONFLICT DO NOTHING);
--   * users, балансы, подписки, платежи, генерации не затрагиваются.
-- Ожидаемо: inserted = 22. Если значение другое — выполнить ROLLBACK вместо COMMIT.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
WITH todo AS (
    SELECT u.telegram_id, u.created_at FROM users u
    WHERE u.telegram_id > 0 AND u.telegram_id < 900000000000
      AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.active_telegram_id = u.telegram_id)
      AND NOT EXISTS (SELECT 1 FROM sylvex_accounts a WHERE a.merged_telegram_id = u.telegram_id
                      AND a.origin = 'telegram')
    ORDER BY u.telegram_id
), ins AS (
    INSERT INTO sylvex_accounts (account_id, active_telegram_id, origin, created_at)
    SELECT sylvex_allocate_telegram_account_id(), todo.telegram_id, 'telegram',
           COALESCE(sylvex_safe_timestamp(todo.created_at::text), NOW())
    FROM todo
    ON CONFLICT (active_telegram_id) DO NOTHING
    RETURNING account_id
)
SELECT COUNT(*) AS inserted FROM ins;
COMMIT;
