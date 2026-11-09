"""Explicit erasure scope. Unknown ownership/schema is held for review.

No table is classified merely because its name contains "user". Retained
financial rows stay unchanged; creative payloads must not be retained with them.
"""

# The value names existing, authenticated owner columns. Matching is by the
# confirmed business storage key, never a customer-supplied Telegram id.
PERSONAL = {
    "assistant_attachments": ("telegram_id",),
    "assistant_messages": ("telegram_id",),
    "assistant_conversations": ("telegram_id",),
    "prostudio_character_history": ("telegram_id",),
    "prostudio_conversation_meta": ("telegram_id",),
    "prostudio_drafts": ("telegram_id",),
    "prostudio_edit_sessions": ("telegram_id",),
    "prostudio_error_reports": ("telegram_id",),
    "prostudio_errors": ("telegram_id",),
    "prostudio_generation_shares": ("owner_telegram_id",),
    "prostudio_grid_projects": ("telegram_id",),
    "prostudio_messages": ("telegram_id",),
    "prostudio_resources": ("telegram_id",),
    "prostudio_video_projects": ("telegram_id",),
    "prostudio_visual_user_state": ("telegram_id",),
    "generations": ("telegram_id",),
    "user_ai_settings": ("telegram_id",),
    "user_voice_settings": ("telegram_id",),
    "user_profiles": ("telegram_id",),
    "user_events": ("telegram_id",),
    "user_surface_usage": ("user_key",),
    "user_referrals": ("telegram_id",),
    "app_presence": ("telegram_id",),
    "sylvex_request_limits": ("user_id",),
    "sylvex_test_requests": ("requester_id", "requester_account_id"),
    "review_prompts": ("account_id", "user_key"),
    "project_reviews": ("account_id", "user_key"),
    "user_notification_recipients": ("account_id", "user_key"),
}

# These records involve another person's rights or an unresolved support/legal
# matter. They need an explicit case decision, not a cascade into another user's
# messages, or an automatic claim that every copy has been erased.
REVIEW = {
    "community_posts": ("telegram_id",),
    "community_comments": ("telegram_id",),
    "community_messages": ("sender_id", "recipient_id"),
    "community_friendships": ("requester_id", "addressee_id"),
    "community_notifications": ("telegram_id", "actor_id"),
    "community_likes": ("telegram_id",),
    "community_comment_likes": ("telegram_id",),
    "support_threads": ("account_id", "user_key"),
    "admin_accounts": ("account_id",),
    "admin_users": ("telegram_id", "account_id"),
    "admin_messages": ("user_telegram_id",),
}

# Required payment evidence and disputes are handled separately, with their
# statutory retention basis. Erasure never reverses/refunds/grants a payment.
FINANCIAL = frozenset({
    "generation_charges", "generation_reservations", "purchases", "shop_orders",
    "subscriptions", "subscription_agreements", "subscription_payments",
    "subscription_events", "subscription_reminders", "stripe_customers",
    "stripe_subscriptions", "stripe_events", "stripe_catalog", "paypal_orders",
    "paypal_subscriptions", "payment_inbox", "payment_reconcile_state",
    "referral_attributions",
    # Added after the erasure release (SX-002, LB-006/014): reservation and
    # payment-review evidence, retained with the other financial records.
    "bot_generation_operations", "financial_review_cases", "financial_review_events",
    "financial_review_resolutions", "payment_refund_requests",
})

SPECIAL = frozenset({
    "users", "sylvex_accounts", "account_emails", "account_oauth",
    "account_link_codes", "account_deletion_codes", "account_pending_registrations",
    "account_rate_limit_attempts", "prostudio_generation_jobs", "prostudio_media_outbox",
    "prostudio_provider_slots", "prostudio_provider_circuit_probes", "site_visitors",
    "analytics_events", "support_messages", "user_access_blocks",
    "admin_sessions", "admin_audit_events", "admin_audit_log",
    "sylvex_tg_session_revocations", "sylvex_storage_objects",
    "sylvex_storage_ownership", "sylvex_erasure_requests", "sylvex_erasure_media",
    "sylvex_erasure_retained_rows",
    "sylvex_active_operations", "sylvex_erasure_runtime", "sylvex_direct_uploads",
    # The credit wallet (LR-002) is not payment evidence: the erasure removes
    # the remaining balance together with the account (owner decision 08.11).
    "user_credit_wallets",
})

SHARED_CATALOG = frozenset({
    "prostudio_references", "prostudio_voice_avatars", "prostudio_visual_stats",
    "user_notifications", "model_states", "prostudio_provider_circuits",
    "admin_schema_migrations",
})

ACCOUNT_COLUMNS = frozenset({"account_id", "requester_account_id"})
OWNER_COLUMNS = frozenset({
    "telegram_id", "owner_telegram_id", "user_key", "user_id", "requester_id",
    "sender_id", "recipient_id", "requester_id", "addressee_id", "actor_id",
    "user_telegram_id", "account_id", "requester_account_id",
})

# Terminal is deliberately explicit: an unknown job/payment status is a hold.
TERMINAL_JOBS = ("completed", "failed", "canceled", "cancelled", "rejected")
TERMINAL_OUTBOX = ("done", "complete", "completed", "failed", "cancelled", "canceled")
TERMINAL_PAYMENTS = ("processed", "completed", "duplicate", "rejected")

# A retention exception is individually identified, reviewed and time-bounded.
# Financial evidence above is not opted out through this interface.
RETENTION_BASES = frozenset({
    "legal_obligation", "active_dispute", "specific_security_incident",
    "other_participant_rights",
})
