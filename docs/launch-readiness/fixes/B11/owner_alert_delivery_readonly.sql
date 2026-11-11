-- B11 / S6-08: доставлены ли административные оповещения. ТОЛЬКО ЧТЕНИЕ.
-- Railway → Postgres → Query. Вывод агрегированный: без Telegram ID, сумм и ссылок на платежи.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

-- 1. Очередь за 30 дней по типам: сколько доставлено, сколько ждёт, сколько с ошибкой.
SELECT event_type,
       COUNT(*)                                             AS total,
       COUNT(*) FILTER (WHERE sent_at IS NOT NULL)          AS delivered,
       COUNT(*) FILTER (WHERE sent_at IS NULL)              AS pending,
       COUNT(*) FILTER (WHERE sent_at IS NULL AND last_error IS NOT NULL) AS failing,
       MAX(sent_at)                                         AS last_delivered
FROM subscription_events
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY event_type ORDER BY event_type;

-- 2. Тексты ошибок доставки (без получателя), если есть.
SELECT LEFT(last_error, 120) AS error, COUNT(*) AS n, MAX(attempts) AS max_attempts
FROM subscription_events
WHERE sent_at IS NULL AND last_error IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;

ROLLBACK;
