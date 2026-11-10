"""Creates admins the way production has them since Admin Console Phase 2:
an admin_accounts row bound to the user's SYLVEX account (admin_users no
longer grants anything)."""
import json


def make_admin(cur, telegram_id, *, role=None, legacy=None, grants=(), denies=(), status="active"):
    """`legacy` takes the old flat permission names and reproduces exactly
    that access; otherwise `role` (+ grants/denies). Returns admin id."""
    from services import admin_rbac
    from services.account_identity import ensure_telegram_account

    account_id = ensure_telegram_account(cur, telegram_id)
    if legacy is not None:
        role, grants, denies = admin_rbac.exact_role_for_legacy(legacy)
    cur.execute("""
        INSERT INTO admin_accounts (account_id, role, grants, denies, status)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (account_id) DO UPDATE SET role = EXCLUDED.role, grants = EXCLUDED.grants,
            denies = EXCLUDED.denies, status = EXCLUDED.status
        RETURNING id
    """, (account_id, role or "read_only", json.dumps(list(grants)), json.dumps(list(denies)), status))
    return int(cur.fetchone()[0])


def audit_rows(cur, action=None):
    sql = ("SELECT actor_account_id, action, target_account_id, target_ref, before, after, reason, channel, risk "
           "FROM admin_audit_events")
    params = ()
    if action:
        sql += " WHERE action = %s"
        params = (action,)
    cur.execute(sql + " ORDER BY id", params)
    out = []
    for row in cur.fetchall():
        row = list(row)
        for i in (4, 5):
            if isinstance(row[i], str):
                row[i] = json.loads(row[i])
        out.append(dict(zip(("actor_account_id", "action", "target_account_id", "target_ref", "before", "after",
                             "reason", "channel", "risk"), row)))
    return out


# --- MFA (B10): how production admins look once TOTP is enforced on the
# Telegram channels - an enrolled authenticator and, for bot / v1 initData
# calls, a fresh Telegram confirmation.
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def enable_mfa(cur, admin_id=None, *, confirmed=True, secret=TEST_TOTP_SECRET):
    """Enrolls the test authenticator for one admin (or every active one) and,
    unless confirmed=False, records a Telegram confirmation made just now."""
    from services import admin_auth

    encrypted = admin_auth._fernet().encrypt(secret.encode()).decode()
    where, params = ("id = %s", (admin_id,)) if admin_id else ("status = 'active'", ())
    cur.execute(f"""
        UPDATE admin_accounts SET totp_secret_enc = %s, totp_pending_enc = NULL, totp_enabled_at = NOW(),
            totp_last_step = NULL, totp_failures = 0, totp_locked_until = NULL,
            telegram_confirmed_at = CASE WHEN %s THEN NOW() ELSE NULL END
        WHERE {where}
    """, (encrypted, bool(confirmed)) + params)


def fresh_totp(cur, telegram_id, secret=TEST_TOTP_SECRET):
    """The current code for the admin behind telegram_id. Clears the
    one-use-per-step marker first, so a test may sign the same admin in
    several times within one 30-second step (replay protection itself is
    covered in test_admin_telegram_mfa.py)."""
    from services import admin_auth

    cur.execute("""
        UPDATE admin_accounts SET totp_last_step = NULL
        WHERE account_id = (SELECT account_id FROM sylvex_accounts WHERE active_telegram_id = %s)
    """, (int(telegram_id),))
    return admin_auth.totp_code(secret)[0]
