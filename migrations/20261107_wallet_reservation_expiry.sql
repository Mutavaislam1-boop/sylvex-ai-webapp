-- Additive compatibility for rolling API/worker deployments. No balance backfill.
-- Run once before deploying the wallet fix, in a transaction with a lock timeout.
ALTER TABLE generation_reservations
    ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION wallet_reservation_capture_expiry()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.subscription_credits > 0 AND NEW.subscription_expires_at IS NULL THEN
        SELECT subscription_expires_at INTO NEW.subscription_expires_at
          FROM user_credit_wallets WHERE telegram_id = NEW.telegram_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS wallet_reservation_capture_expiry ON generation_reservations;
CREATE TRIGGER wallet_reservation_capture_expiry
    BEFORE INSERT ON generation_reservations FOR EACH ROW
    EXECUTE FUNCTION wallet_reservation_capture_expiry();
