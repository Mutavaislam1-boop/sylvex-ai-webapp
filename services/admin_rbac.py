"""Admin Console RBAC: one permission system for every admin surface.

Permissions are fine-grained dot names. A role gives a default set;
effective permissions = role defaults + grants - denies. The owner holds
every permission and cannot be narrowed. Each permission carries a risk
tier that decides what else an action needs (reason, confirmation, recent
re-authentication) - see require_* in services/admin_auth.py.

The legacy flat permission names used by the support bot and the
/api/admin/* v1 routes map onto these, so old callers keep working while
there is exactly one source of truth.
"""
from __future__ import annotations

LOW, MEDIUM, HIGH, CRITICAL = "low", "medium", "high", "critical"
RISK_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3}

PERMISSIONS = {
    "dashboard.view": LOW,
    "users.view": LOW,
    "users.edit": MEDIUM,
    "users.balance.adjust": HIGH,
    "users.subscription.edit": HIGH,
    "users.ban": HIGH,
    "users.delete": CRITICAL,
    "identity.technical": LOW,
    "support.notes": LOW,
    "payments.view": LOW,
    "payments.refund": CRITICAL,
    "analytics.view": LOW,
    "generations.view": LOW,
    "generations.cancel": MEDIUM,
    "generations.retry": HIGH,
    "generations.recover": MEDIUM,
    "generations.refund": CRITICAL,
    "models.view": LOW,
    "models.edit": CRITICAL,
    "pricing.edit": CRITICAL,
    "content.references.manage": MEDIUM,
    "sylvex_test.manage": MEDIUM,
    "messages.send": MEDIUM,
    "broadcast.create": MEDIUM,
    "broadcast.send": CRITICAL,
    "errors.view": LOW,
    "audit.view": LOW,
    "system.view": LOW,
    "system.manage": HIGH,
    "admins.view": LOW,
    "admins.create": CRITICAL,
    "admins.permissions.edit": CRITICAL,
}

OWNER = "owner"
ROLES = ("owner", "administrator", "finance", "support", "moderator", "analyst", "read_only")
# Who may manage whom: an admin only manages roles strictly below their own
# (the owner manages everyone, including other owners).
ROLE_RANK = {"owner": 100, "administrator": 80, "finance": 50, "support": 50, "moderator": 50, "analyst": 50,
             "read_only": 10}

_READ = {"dashboard.view", "users.view", "generations.view", "errors.view", "models.view", "analytics.view"}

ROLE_DEFAULTS = {
    "owner": set(PERMISSIONS),
    "administrator": {
        "dashboard.view", "users.view", "users.edit", "users.balance.adjust", "users.subscription.edit",
        "users.ban", "support.notes", "payments.view", "analytics.view", "generations.view",
        "generations.cancel", "generations.retry", "generations.recover", "generations.refund", "models.view",
        "models.edit", "content.references.manage", "sylvex_test.manage", "messages.send", "broadcast.create",
        "broadcast.send", "errors.view", "audit.view", "system.view", "admins.view",
    },
    "finance": {
        "dashboard.view", "users.view", "users.balance.adjust", "users.subscription.edit", "payments.view",
        "payments.refund", "generations.view", "generations.refund", "pricing.edit", "models.view",
        "analytics.view", "errors.view", "audit.view",
    },
    "support": {
        "dashboard.view", "users.view", "users.edit", "support.notes", "payments.view", "generations.view",
        "generations.cancel", "generations.recover", "messages.send", "errors.view",
    },
    "moderator": {
        "dashboard.view", "users.view", "users.ban", "support.notes", "generations.view",
        "content.references.manage",
    },
    "analyst": {"dashboard.view", "users.view", "payments.view", "generations.view", "models.view",
                "analytics.view", "errors.view"},
    "read_only": set(_READ),
}

# Legacy flat names (admin_users.permissions, support bot, main bot) ->
# the permissions they always meant.
LEGACY_TO_NEW = {
    "view_dashboard": {"dashboard.view"},
    "view_users": {"users.view"},
    "manage_balance": {"users.balance.adjust"},
    "manage_subscriptions": {"users.subscription.edit"},
    "message_users": {"messages.send", "broadcast.create", "broadcast.send"},
    "view_audit": {"audit.view"},
    "view_errors": {"errors.view"},
    "view_generations": {"generations.view"},
    "view_finance": {"payments.view"},
    "manage_references": {"content.references.manage"},
    "sylvex_test": {"sylvex_test.manage"},
}

# The Telegram bot channel (a shared service token + the sender's Telegram
# id) never performs Critical actions for anyone but the owner: those need
# the console, a session and step-up re-authentication.
BOT_CHANNEL_MAX_RISK_NON_OWNER = HIGH


def role_rank(role):
    return ROLE_RANK.get(role, 0)


def effective_permissions(role, grants=(), denies=()):
    if role == OWNER:
        return set(PERMISSIONS)
    perms = set(ROLE_DEFAULTS.get(role, set())) | {p for p in (grants or ()) if p in PERMISSIONS}
    return perms - set(denies or ())


def has_permission(actor, permission):
    return permission in actor.get("permissions_set", set())


def risk_of(permission):
    return PERMISSIONS.get(permission, CRITICAL)


def legacy_names(permissions):
    """Legacy names fully covered by a set of new permissions (for v1 /me)."""
    perms = set(permissions)
    return sorted(name for name, needed in LEGACY_TO_NEW.items() if needed <= perms)


def from_legacy(names):
    out = set()
    for name in names or ():
        if name == "all":
            out |= set(PERMISSIONS)
        out |= LEGACY_TO_NEW.get(name, set())
    return out


def exact_role_for_legacy(names):
    """(role, grants, denies) giving an old admin_users row exactly the
    permissions it had - no more (read_only defaults it never had are
    denied), no less."""
    wanted = from_legacy(names)
    base = ROLE_DEFAULTS["read_only"]
    return "read_only", sorted(wanted - base), sorted(base - wanted)


class EscalationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def check_admin_change(actor, target, new_role, new_grants, new_denies):
    """Raises EscalationError unless `actor` may set `target` (None for a new
    admin) to the given role/grants/denies. Last-owner protection needs the
    database and lives in admin_auth."""
    actor_role = actor["role"]
    if new_role not in ROLES:
        raise EscalationError("invalid_role")
    unknown = [p for p in list(new_grants or []) + list(new_denies or []) if p not in PERMISSIONS]
    if unknown:
        raise EscalationError("unknown_permission")
    if target is not None and target["admin_id"] == actor["admin_id"]:
        raise EscalationError("cannot_modify_self")
    if actor_role != OWNER:
        if target is not None and role_rank(target["role"]) >= role_rank(actor_role):
            raise EscalationError("target_role_not_below_actor")
        if role_rank(new_role) >= role_rank(actor_role):
            raise EscalationError("role_not_below_actor")
        resulting = effective_permissions(new_role, new_grants, new_denies)
        if not resulting <= actor["permissions_set"]:
            raise EscalationError("cannot_grant_unheld_permission")
