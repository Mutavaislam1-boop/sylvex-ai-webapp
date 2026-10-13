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
