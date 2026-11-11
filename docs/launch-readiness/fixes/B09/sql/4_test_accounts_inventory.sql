-- B09 — шаг 4: инвентаризация трёх тестовых Telegram ID (только чтение).
-- 12345, 123456789, 900000001 подтверждены владельцем как тестовые.

-- 4a. Сами пользователи
SELECT telegram_id, username, first_name, balance, subscription, created_at
FROM users WHERE telegram_id IN (12345, 123456789, 900000001) ORDER BY telegram_id;

-- 4b. Все строки во всех таблицах, где столбец-владелец равен одному из ID.
--     category: financial = платёжные записи (по умолчанию НЕ удаляются), identity, admin, other.
SELECT c.table_name, c.column_name,
       CASE WHEN c.table_name IN ('generation_charges','generation_reservations','purchases','shop_orders','subscriptions',
                 'subscription_agreements','subscription_payments','subscription_events','subscription_reminders',
                 'stripe_customers','stripe_subscriptions','stripe_events','stripe_catalog','paypal_orders',
                 'paypal_subscriptions','payment_inbox','payment_reconcile_state','referral_attributions',
                 'bot_generation_operations','financial_review_cases','financial_review_events',
                 'financial_review_resolutions','payment_refund_requests') THEN 'financial'
            WHEN c.table_name IN ('sylvex_accounts','account_emails','account_oauth','account_link_codes','account_deletion_codes') THEN 'identity'
            WHEN c.table_name LIKE 'admin\_%' THEN 'admin'
            ELSE 'other' END AS category,
       (xpath('/row/n/text()', query_to_xml(format(
            'SELECT COUNT(*) AS n FROM %I WHERE %I::text IN (''12345'',''123456789'',''900000001'')',
            c.table_name, c.column_name), false, true, '')))[1]::text::bigint AS rows
FROM information_schema.columns c
JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'
WHERE c.table_schema = current_schema()
  AND c.column_name IN ('telegram_id','owner_telegram_id','user_key','user_id','requester_id','sender_id','recipient_id',
                        'addressee_id','actor_id','user_telegram_id','owner_key','subject_key','active_telegram_id',
                        'merged_telegram_id','storage_telegram_id','admin_telegram_id','referrer_id','referred_id')
  AND c.data_type IN ('bigint','integer','numeric','text','character varying')
ORDER BY rows DESC, c.table_name, c.column_name;
