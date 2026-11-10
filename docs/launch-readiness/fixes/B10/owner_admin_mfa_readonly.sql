-- B10 / S1-05: текущее состояние администраторов. ТОЛЬКО ЧТЕНИЕ.
-- Запускать в Railway → Postgres → Query (или psql) владельцем.
-- Секреты TOTP не выводятся: только факт включения.

-- 1. Активные администраторы, их роль и включён ли TOTP.
SELECT a.id                                   AS admin_id,
       a.role,
       a.status,
       a.totp_enabled_at IS NOT NULL          AS totp_enabled,
       s.active_telegram_id IS NOT NULL       AS has_telegram,
       a.last_login_at,
       a.last_activity_at
FROM admin_accounts a
LEFT JOIN sylvex_accounts s ON s.account_id = a.account_id
WHERE a.status = 'active'
ORDER BY a.id;

-- 2. Какими каналами каждый администратор реально входил за 30 дней
--    (web = пароль + TOTP; miniapp = только Telegram).
SELECT admin_id, channel, COUNT(*) AS sessions, MAX(created_at) AS last_session
FROM admin_sessions
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY admin_id, channel
ORDER BY admin_id, channel;

-- 3. Критические действия по каналам за 30 дней (bot / miniapp_legacy
--    не требуют повторного подтверждения).
SELECT channel, risk, COUNT(*) AS events, MAX(at) AS last_at
FROM admin_audit_events
WHERE at > NOW() - INTERVAL '30 days'
GROUP BY channel, risk
ORDER BY channel, risk;
