-- LB-006/014 additive journal only; no historical balance or purchase updates.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS financial_review_events(
 provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,event_id TEXT NOT NULL,
 event_type TEXT NOT NULL,payload JSONB NOT NULL,payload_hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','processed')),
 attempts INTEGER NOT NULL DEFAULT 0,last_error_class TEXT,
 received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 processed_at TIMESTAMPTZ,case_id TEXT,PRIMARY KEY(provider,livemode,event_id));
CREATE INDEX IF NOT EXISTS financial_review_events_pending ON financial_review_events(next_attempt_at)WHERE status='pending';
CREATE TABLE IF NOT EXISTS financial_review_cases(
 case_id TEXT PRIMARY KEY,provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,
 charge_id TEXT NOT NULL,currency TEXT NOT NULL,telegram_id BIGINT,purchase_id BIGINT,order_id TEXT,
 payment_refs TEXT[] NOT NULL DEFAULT '{}',source TEXT,
 facts JSONB NOT NULL DEFAULT '{}',risk_hash TEXT NOT NULL,
 review_revision INTEGER NOT NULL DEFAULT 0,resolved_revision INTEGER NOT NULL DEFAULT 0,
 mapping_conflict BOOLEAN NOT NULL DEFAULT FALSE,manual_mapping_verified BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(provider,livemode,charge_id));
CREATE INDEX IF NOT EXISTS financial_review_cases_pending ON financial_review_cases(telegram_id,updated_at)WHERE review_revision>resolved_revision;
CREATE INDEX IF NOT EXISTS financial_review_cases_refs ON financial_review_cases USING GIN(payment_refs);
CREATE TABLE IF NOT EXISTS financial_review_resolutions(
 resolution_id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES financial_review_cases(case_id),
 review_revision INTEGER NOT NULL,telegram_id BIGINT,purchase_id BIGINT,
 operator TEXT NOT NULL,evidence TEXT NOT NULL,decision TEXT NOT NULL,
 source TEXT,credits INTEGER NOT NULL DEFAULT 0 CHECK(credits>=0),
 balance_before INTEGER,balance_after INTEGER,request_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(case_id,review_revision));
CREATE TABLE IF NOT EXISTS payment_refund_requests(
 request_id TEXT PRIMARY KEY,provider TEXT NOT NULL,livemode BOOLEAN NOT NULL,
 charge_id TEXT NOT NULL,telegram_id BIGINT NOT NULL,purchase_id BIGINT NOT NULL,
 amount BIGINT NOT NULL CHECK(amount>0),currency TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('dispatching','pending_reconciliation','confirmed','not_refunded')),
 operator TEXT NOT NULL,evidence TEXT NOT NULL,last_error_class TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(provider,livemode,charge_id));
COMMIT;
