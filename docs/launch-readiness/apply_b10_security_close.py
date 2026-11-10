"""Seventh register update: B10 security review (SQL injection, admin MFA/access).

Only confirmed results are recorded:
- S1-06: the SQL-injection subcheck is confirmed by a full static review of
  every non-literal SQL call in API 5dbcde1 / workers dde6dea (no findings).
  The status stays Не проверено: the live site response (headers / site.js
  version) has still not been observed from this session.
- S1-05 / S7-09: 102 admin auth/RBAC tests pass on 5dbcde1 (the earlier run
  hit the 150 s limit). MFA is enforced only for browser login; the Telegram
  channels (Mini App v2/v1, bot) are single-factor by design. Status stays
  Не проверено pending the owner's decision and DB/admin smoke evidence.

Usage: python3 apply_b10_security_close.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-10T14:00:00+00:00"
API, WORKERS = "5dbcde1", "dde6dea"
R = {r["id"]: r for r in d["requirements"]}

r = R["S1-06"]
r["confirmed_scope"] = (
    "Подтверждено: CSRF (Origin в middleware для всех изменяющих /api/web/* и веб-cookie; админка SameSite=Strict + "
    "CSRF-токен), XSS-1, XSS-4, CORS-2 в API 5dbcde1. XSS сайта УСТРАНЁН и развёрнут: sylvex-website 968e928 + 3009404; "
    "деплой 589b9461 SUCCESS, Railway HTTP-лог 10.11 10:31Z: /account/profile.html и /account/settings.html → 200 с "
    "этого деплоя. SQL-инъекции ПОДТВЕРЖДЕНЫ полным статическим обзором: все 129 нелитеральных вызовов execute в API "
    "5dbcde1 (main.py + services; прочие модули — 0) и 109 в воркерах dde6dea (подмножество API) — значения только через "
    "%s, имена колонок из констант/белых списков, идентификаторы через ident()/sql.Identifier; находок нет. "
    "НЕ НАБЛЮДАЛОСЬ: живые заголовки ответа сайта (Cache-Control: no-cache) и загрузка site.js?v=s106-xss-20261109.")
r["next_action"] = ("Владельцу — одна проверка заголовков сайта командой из fixes/S1-06/RESULT.md; при ожидаемом "
                    "ответе S1-06 можно перевести в Подтверждено без новых тестов.")
r["assessed_on"] = "2026-11-10"
r["open_subchecks"] = {
    "website_xss": "fixed and deployed (sylvex-website 3009404, deployment 589b9461, pages 200 in Railway HTTP log); "
                   "live response headers / site.js version not observed",
    "sql_injection": "confirmed: full static review of 129 non-literal SQL calls (API 5dbcde1) and 109 (workers dde6dea); no findings",
}
for e in ("B10_SECURITY",):
    if e not in r["evidence_ids"]:
        r["evidence_ids"].append(e)
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "api_commit": API, "workers_commit": WORKERS,
                     "reason": "SQLi подтверждена полным статическим обзором (находок нет); открыт только живой ответ сайта."})

ADMIN_FACTS = (
    "Код API 5dbcde1 (admin_auth.py/admin_rbac.py не менялись с оценки 07.11): 102 теста auth/RBAC/TOTP/service-token "
    "PASS на реальном SQL (PGlite), 121 с. Браузерный вход: email+пароль+TOTP обязателен, 5 ошибок → блок 15 мин, "
    "Critical — повторный TOTP ≤5 мин. Telegram-каналы однофакторные по дизайну: Mini App v2 (initData ≤3600 с, "
    "Critical — свежий initData), Mini App v1 и бот (Critical без повторного подтверждения; бот — только владелец; "
    "среди v1 Critical: models.edit, broadcast.send, admins.permissions.edit). Без активной записи admin_accounts доступа "
    "нет ни в одном канале. MFA выполнена только для браузерного входа. По данным Codex 07.11: 3 active admins, TOTP у 2 "
    "(текущее состояние БД из этой сессии не прочитано).")
r = R["S1-05"]
r["confirmed_scope"] = ADMIN_FACTS
r["next_action"] = ("Решение владельца: принять Telegram-аккаунт (с облачным паролем Telegram у всех админов) как фактор "
                    "Mini App/бота или заказать TOTP/повторное подтверждение для Telegram-каналов; выполнить "
                    "fixes/B10/owner_admin_mfa_readonly.sql.")
r["assessed_on"] = "2026-11-10"
r["open_subchecks"] = {
    "rbac": "confirmed: 102 admin tests pass on 5dbcde1; no admin access without active admin_accounts row",
    "mfa_web": "confirmed: TOTP mandatory for browser login",
    "mfa_telegram_channels": "not met by design: Mini App v2/v1 and bot are single-factor (Telegram account); owner decision required",
    "current_admin_state": "not observed: DB read blocked in this session; owner query fixes/B10/owner_admin_mfa_readonly.sql",
}
r["evidence_ids"] = [e for e in r["evidence_ids"]] + (["B10_SECURITY"] if "B10_SECURITY" not in r["evidence_ids"] else [])
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "api_commit": API,
                     "reason": "RBAC и TOTP браузера подтверждены (102 PASS); Telegram-каналы без второго фактора — решение владельца."})

r = R["S7-09"]
r["confirmed_scope"] = ("RBAC маршрутов админки подтверждён: 102 теста admin auth/RBAC/users/messages/recover-job/"
                        "extended endpoints PASS на API 5dbcde1 (ранее лимит 150 с). Реальный read-only admin smoke "
                        "в Production не выполнялся (нужен вход администратора; сеть сессии блокирует сайт и API).")
r["next_action"] = "Read-only admin smoke владельцем/администратором (просмотр пользователей, платежей, генераций, ошибок) без изменений."
r["assessed_on"] = "2026-11-10"
if "B10_SECURITY" not in r["evidence_ids"]:
    r["evidence_ids"].append("B10_SECURITY")
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "api_commit": API, "reason": "102 admin-теста PASS; живой read-only smoke не выполнен."})

g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]
g["local_progress"] = ("S1-07 подтверждён; S1-06: XSS устранён и развёрнут, SQLi подтверждена полным статическим обзором; "
                       "S1-05/S7-09: RBAC и TOTP браузера подтверждены 102 тестами")
g["awaiting"] = ("S1-06: живые заголовки сайта (команда владельца). S1-05: решение владельца по MFA Telegram-каналов + "
                 "read-only SQL по администраторам. S7-09: read-only admin smoke. S5-08: privacy (вместе с B09).")
d["evidence_catalog"]["B10_SECURITY"] = {"path": "fixes/B10/RESULT.md",
    "scope": "Полный статический обзор SQL (API 5dbcde1, воркеры dde6dea); 102 admin auth/RBAC теста PASS; каналы входа и MFA"}
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B10 review: SQL injection confirmed (static), admin RBAC tests pass; Telegram-channel MFA awaits owner"
d["latest_work_phase"] = "B10_SECURITY_REVIEW"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
