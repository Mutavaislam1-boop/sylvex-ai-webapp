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
    "content.publish": HIGH,
    "sylvex_test.manage": MEDIUM,
    "messages.send": MEDIUM,
    "support.manage": MEDIUM,
    "broadcast.create": MEDIUM,
    "broadcast.send": CRITICAL,
    "errors.view": LOW,
    "logs.technical": MEDIUM,
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
        "models.edit", "content.references.manage", "content.publish", "sylvex_test.manage", "messages.send",
        "support.manage", "broadcast.create", "broadcast.send", "errors.view", "logs.technical", "audit.view",
        "system.view", "admins.view",
    },
    "finance": {
        "dashboard.view", "users.view", "users.balance.adjust", "users.subscription.edit", "payments.view",
        "payments.refund", "generations.view", "generations.refund", "pricing.edit", "models.view",
        "analytics.view", "errors.view", "audit.view",
    },
    "support": {
        "dashboard.view", "users.view", "users.edit", "support.notes", "payments.view", "generations.view",
        "generations.cancel", "generations.recover", "messages.send", "support.manage", "errors.view",
        "logs.technical",
    },
    "moderator": {
        "dashboard.view", "users.view", "users.ban", "support.notes", "generations.view",
        "content.references.manage", "content.publish", "messages.send", "support.manage",
    },
    "analyst": {"dashboard.view", "users.view", "payments.view", "generations.view", "models.view",
                "analytics.view", "errors.view"},
    "read_only": set(_READ),
}

# What each permission allows and where, shown next to it in the console
# (EN source text, RU translation). `why` explains its risk tier.
PERMISSION_INFO = {
    "dashboard.view": ("See the dashboard: totals of users, generations, payments and errors.",
                       "Просмотр дашборда: итоги по пользователям, генерациям, платежам и ошибкам.",
                       "Read only, totals without personal data.", "Только чтение, сводные числа без личных данных."),
    "users.view": ("Find users and open their cards: profile, balance, subscription, history.",
                   "Поиск пользователей и просмотр карточки: профиль, баланс, подписка, история.",
                   "Read only, but shows personal data.", "Только чтение, но видны личные данные."),
    "users.edit": ("Edit a user's profile fields and support notes.",
                   "Изменение полей профиля пользователя и заметок поддержки.",
                   "Changes user data, nothing financial.", "Меняет данные пользователя, без денег."),
    "users.balance.adjust": ("Add or remove credits (Users → card → Credits). Always with a reason.",
                             "Начисление и списание кредитов (Пользователи → карточка → Кредиты). Всегда с причиной.",
                             "Moves value: credits are spent on paid generations.", "Двигает ценность: кредиты тратятся на платные генерации."),
    "users.subscription.edit": ("Grant, extend or cancel a subscription free of charge.",
                                "Бесплатная выдача, продление или отмена подписки.",
                                "Changes what a user is entitled to.", "Меняет то, на что пользователь имеет право."),
    "users.ban": ("Block and unblock users. A blocked user loses access to generations, purchases and the bot.",
                  "Блокировка и разблокировка пользователей. Заблокированный теряет доступ к генерациям, покупкам и боту.",
                  "Cuts a person off from the product.", "Отключает человека от продукта."),
    "users.delete": ("Delete a user account and its data.", "Удаление аккаунта пользователя и его данных.",
                     "Irreversible.", "Необратимо."),
    "identity.technical": ("See technical identifiers (storage keys, aliases) in cards.",
                           "Просмотр технических идентификаторов (ключи хранения, алиасы) в карточках.",
                           "Read only, internal ids.", "Только чтение, внутренние id."),
    "support.notes": ("Write internal notes about a user.", "Внутренние заметки о пользователе.",
                      "Internal text only.", "Только внутренний текст."),
    "payments.view": ("See payments, purchases, subscriptions and finance figures.",
                      "Просмотр платежей, покупок, подписок и финансовых показателей.",
                      "Read only, financial data.", "Только чтение, финансовые данные."),
    "payments.refund": ("Refund a payment through its provider.", "Возврат платежа через платёжного провайдера.",
                        "Sends real money back; cannot be undone.", "Возвращает реальные деньги; отменить нельзя."),
    "analytics.view": ("See usage analytics: pages, tools, models, platforms, funnels.",
                       "Просмотр аналитики: страницы, инструменты, модели, платформы, воронки.",
                       "Read only, aggregated.", "Только чтение, агрегированные данные."),
    "generations.view": ("See generations, their stages and results (Generations).",
                         "Просмотр генераций, их этапов и результатов (Генерации).",
                         "Read only.", "Только чтение."),
    "generations.cancel": ("Cancel a running generation.", "Отмена выполняющейся генерации.",
                           "Stops one user's job.", "Останавливает задачу одного пользователя."),
    "generations.retry": ("Retry a generation at the platform's cost.", "Повтор генерации за счёт платформы.",
                          "Spends money on the AI provider.", "Тратит деньги у ИИ-провайдера."),
    "generations.recover": ("Recover a finished result that did not reach the user.",
                            "Восстановление готового результата, который не дошёл до пользователя.",
                            "Re-delivers an existing result.", "Повторно отдаёт уже готовый результат."),
    "generations.refund": ("Return the credits of a failed generation.", "Возврат кредитов за неудачную генерацию.",
                           "Moves value back to the user.", "Возвращает ценность пользователю."),
    "models.view": ("See AI models, providers and their status.", "Просмотр ИИ-моделей, провайдеров и их состояния.",
                    "Read only.", "Только чтение."),
    "models.edit": ("Turn models on and off for users, change model settings.",
                    "Включение и отключение моделей для пользователей, настройки моделей.",
                    "Affects every user's generations at once.", "Затрагивает генерации всех пользователей сразу."),
    "pricing.edit": ("Change prices and tariffs.", "Изменение цен и тарифов.",
                     "Changes what everyone pays.", "Меняет, сколько платят все."),
    "content.references.manage": ("Create and edit Media blocks: tools, video templates, photos, references, styles (drafts).",
                                  "Создание и редактирование блоков Media: инструменты, видеошаблоны, фото, референсы, стили (черновики).",
                                  "Drafts are invisible to users until published.", "Черновики не видны пользователям до публикации."),
    "content.publish": ("Publish, unpublish and delete Media blocks on the site and in the Mini Apps.",
                        "Публикация, снятие с публикации и удаление блоков Media на сайте и в Mini App.",
                        "Changes what every user sees.", "Меняет то, что видят все пользователи."),
    "sylvex_test.manage": ("Manage SYLVEX test accounts and test runs.", "Управление тестовыми аккаунтами и прогонами SYLVEX.",
                           "Test environment only.", "Только тестовое окружение."),
    "messages.send": ("Write to a user and answer conversations (Messages, user card).",
                      "Сообщения пользователю и ответы в обращениях (Сообщения, карточка пользователя).",
                      "Speaks to a user on behalf of SYLVEX.", "Говорит с пользователем от имени SYLVEX."),
    "support.manage": ("Manage conversations: status, assignee, attachments, reviews, sales requests.",
                       "Управление обращениями: статус, ответственный, вложения, отзывы, заявки отдела продаж.",
                       "Organises support work; no money involved.", "Организация поддержки; без денег."),
    "broadcast.create": ("Prepare announcements to many users.", "Подготовка объявлений для многих пользователей.",
                         "Draft only.", "Только черновик."),
    "broadcast.send": ("Send announcements to many or all users on every platform.",
                       "Отправка объявлений многим или всем пользователям на всех платформах.",
                       "Reaches everyone at once and cannot be recalled.", "Доходит до всех сразу и не отзывается."),
    "errors.view": ("See errors and user error reports.", "Просмотр ошибок и жалоб пользователей на ошибки.",
                    "Read only.", "Только чтение."),
    "logs.technical": ("See technical logs of generations: stages, provider task ids, error codes (never secrets).",
                       "Просмотр технических логов генераций: этапы, id задач провайдера, коды ошибок (без секретов).",
                       "Read only, but shows internal details.", "Только чтение, но видны внутренние детали."),
    "audit.view": ("See the admin audit log.", "Просмотр журнала действий администрации.",
                   "Read only.", "Только чтение."),
    "system.view": ("See system status and configuration (no secrets).", "Просмотр состояния системы и конфигурации (без секретов).",
                    "Read only.", "Только чтение."),
    "system.manage": ("Change system settings.", "Изменение системных настроек.",
                      "Can affect the whole service.", "Может затронуть весь сервис."),
    "admins.view": ("See the list of admins and their roles.", "Просмотр списка администраторов и их ролей.",
                    "Read only.", "Только чтение."),
    "admins.create": ("Add new admins (owner only).", "Добавление новых администраторов (только владелец).",
                      "Gives someone access to the console.", "Даёт человеку доступ к админке."),
    "admins.permissions.edit": ("Change admins' roles and permissions (owner only).",
                                "Изменение ролей и прав администраторов (только владелец).",
                                "Decides who can do everything else.", "Решает, кто может всё остальное."),
}

RISK_INFO = {
    LOW: ("Low: read only. No extra confirmation.", "Низкий: только просмотр. Без дополнительных подтверждений."),
    MEDIUM: ("Medium: changes data of one user or a draft, nothing financial.",
             "Средний: меняет данные одного пользователя или черновик, без денег."),
    HIGH: ("High: money, access or what users see. Needs a reason, saved in the audit log.",
           "Высокий: деньги, доступ или то, что видят пользователи. Нужна причина, она сохраняется в журнале."),
    CRITICAL: ("Critical: irreversible or affects everyone. Needs a reason, confirmation and a fresh sign-in check.",
               "Критический: необратимо или затрагивает всех. Нужны причина, подтверждение и свежая проверка входа."),
}


# Short names for chips and lists (EN, RU).
PERMISSION_LABELS = {
    "dashboard.view": ("Dashboard", "Дашборд"),
    "users.view": ("View users", "Просмотр пользователей"),
    "users.edit": ("Edit profiles", "Изменение профилей"),
    "users.balance.adjust": ("Credits", "Кредиты"),
    "users.subscription.edit": ("Subscriptions", "Подписки"),
    "users.ban": ("Block users", "Блокировка"),
    "users.delete": ("Delete accounts", "Удаление аккаунтов"),
    "identity.technical": ("Technical IDs", "Технические ID"),
    "support.notes": ("Support notes", "Заметки поддержки"),
    "payments.view": ("Finance", "Финансы"),
    "payments.refund": ("Payment refunds", "Возвраты платежей"),
    "analytics.view": ("Analytics", "Аналитика"),
    "generations.view": ("View generations", "Просмотр генераций"),
    "generations.cancel": ("Cancel generations", "Отмена генераций"),
    "generations.retry": ("Retry generations", "Повтор генераций"),
    "generations.recover": ("Recover results", "Восстановление результатов"),
    "generations.refund": ("Generation refunds", "Возврат за генерации"),
    "models.view": ("View models", "Просмотр моделей"),
    "models.edit": ("Manage models", "Управление моделями"),
    "pricing.edit": ("Prices", "Цены"),
    "content.references.manage": ("Media: edit", "Media: редактирование"),
    "content.publish": ("Media: publish", "Media: публикация"),
    "sylvex_test.manage": ("Test accounts", "Тестовые аккаунты"),
    "messages.send": ("Messages", "Сообщения"),
    "support.manage": ("Manage requests", "Управление обращениями"),
    "broadcast.create": ("Prepare announcements", "Подготовка рассылок"),
    "broadcast.send": ("Mass announcements", "Массовые рассылки"),
    "errors.view": ("Errors", "Ошибки"),
    "logs.technical": ("Technical logs", "Технические логи"),
    "audit.view": ("Audit log", "Журнал аудита"),
    "system.view": ("System status", "Состояние системы"),
    "system.manage": ("System settings", "Настройки системы"),
    "admins.view": ("View admins", "Просмотр админов"),
    "admins.create": ("Add admins", "Добавление админов"),
    "admins.permissions.edit": ("Admin access", "Права админов"),
}


def permission_catalog():
    """Permissions with risk, description and why, in both languages."""
    out = {}
    for name, risk in PERMISSIONS.items():
        en, ru, why_en, why_ru = PERMISSION_INFO.get(name, (name, name, "", ""))
        label_en, label_ru = PERMISSION_LABELS.get(name, (name, name))
        out[name] = {"risk": risk, "label": {"en": label_en, "ru": label_ru}, "description": {"en": en, "ru": ru},
                     "why": {"en": why_en, "ru": why_ru}}
    return out


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
    admin) to the given role/grants/denies. Only the owner assigns and
    changes admin roles; the owner role itself is never handed out through
    the console. Last-owner protection needs the database and lives in
    admin_auth."""
    if new_role not in ROLES:
        raise EscalationError("invalid_role")
    unknown = [p for p in list(new_grants or []) + list(new_denies or []) if p not in PERMISSIONS]
    if unknown:
        raise EscalationError("unknown_permission")
    if target is not None and target["admin_id"] == actor["admin_id"]:
        raise EscalationError("cannot_modify_self")
    if actor["role"] != OWNER:
        raise EscalationError("owner_access_required")
    if new_role == OWNER and (target is None or target["role"] != OWNER):
        raise EscalationError("owner_role_not_assignable")
