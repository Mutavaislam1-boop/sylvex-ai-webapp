"""Eighth register update: B10 MFA in Production (API ba96d8c, support bot
a75bf83, main bot 55e57da).

Only what Production logs prove is recorded:
- S1-05: TOTP is now required on the Telegram Mini App and was confirmed
  live (owner sign-in: 401 without / with a wrong code, then 200). The bot
  channels and the Critical re-authentication are deployed and tested but
  not yet exercised in Production, and the third admin's TOTP state is not
  observed -> stays Не проверено.
- S7-09: read-only console smoke with a TOTP session passed, but the
  payments section (POST /api/admin/finance) fails with HTTP 500 in
  Production (text >= timestamp) -> Ошибка (pre-existing, not MFA).
- S1-06 and S5-08: no new evidence, unchanged.

Usage: python3 apply_b10_mfa_production.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-10T13:45:00+00:00"
API, SUPPORT, BOT = ("ba96d8ce2fcb710c4e613ea2d392cecc2db5d3c1", "a75bf83abb5de146fef26042c82a8d729cb8247e",
                     "55e57dad01fffc6c627f637621cebaefd96b9aca")
R = {r["id"]: r for r in d["requirements"]}

r = R["S1-05"]
prev = r["status"]
r["status"] = "Не проверено"
r["confirmed_scope"] = (
    "MFA внедрена во всех Telegram-каналах и развёрнута: API ba96d8c (b6d1aa8b), support bot a75bf83 (e8e1a456), "
    "main bot 55e57da (7a88fa18), все SUCCESS 10.11. Mini App: initData + TOTP; без TOTP — сессия только для "
    "подключения; боты и v1 — подтверждение TOTP в Mini App ≤30 мин, Critical ≤5 мин; Critical в консоли — "
    "только повторный TOTP. ПОДТВЕРЖДЕНО В PRODUCTION: вход владельца в Telegram Mini App с TOTP — 8 ответов 401 "
    "(без кода/неверный код), затем 200 в 13:28:37Z; миграция mfa_at/telegram_confirmed_at применилась без ошибок; "
    "браузерный вход с TOTP — как раньше. Тестами (не повторялись): 17 адресных + 240 регрессионных, перебор всех "
    "/api/admin/* без обходов. НЕ ПОДТВЕРЖДЕНО В PRODUCTION: отказ ботов без подтверждения (разделы бота поддержки и "
    "/admin основного бота после деплоя не вызывались), повторный TOTP для Critical (reauth не вызывался), "
    "подключение TOTP третьим администратором.")
r["open_subchecks"] = {
    "rbac": "confirmed: tests on 5dbcde1/ba96d8c; no admin access without active admin_accounts row",
    "mfa_web": "confirmed: TOTP mandatory for browser login",
    "mfa_telegram_miniapp": "confirmed live 10.11: owner sign-in 401 without/wrong code, 200 with TOTP (13:28:37Z)",
    "mfa_bots": "deployed and tested; not exercised in Production yet (support bot section, main bot /admin)",
    "critical_reauth_totp": "deployed and tested; not exercised in Production yet",
    "third_admin_totp": "not observed: enrollment by the third admin pending",
}
r["next_action"] = ("Ручная проверка по fixes/B10-MFA/PRODUCTION_CHECK.md (разделы 1–4) без /addbalance и без "
                    "изменения данных; затем сверка логов и закрытие.")
r["assessed_on"] = "2026-11-10"
if "B10_MFA_PRODUCTION" not in r["evidence_ids"]:
    r["evidence_ids"].append("B10_MFA_PRODUCTION")
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": r["status"], "previous_status": prev,
                     "api_commit": API, "support_bot_commit": SUPPORT, "main_bot_commit": BOT,
                     "reason": "TOTP в Telegram Mini App подтверждён в Production; боты, Critical reauth и третий "
                               "администратор ещё не проверены вживую."})

r = R["S7-09"]
prev = r["status"]
r["status"] = "Ошибка"
r["confirmed_scope"] = (
    "RBAC маршрутов админки подтверждён тестами (102 на 5dbcde1; 240 регрессии на ba96d8c). Read-only smoke в "
    "Production 10.11 в сессии с TOTP: /api/admin/dashboard, /api/admin/inbox/list, /api/admin/users/search — 200. "
    "ОШИБКА: раздел платежей не работает — POST /api/admin/finance → 500 (13:28:54Z), "
    "psycopg2 UndefinedFunction 'text >= timestamp without time zone' в admin_finance/_sync (main.py:13707, "
    "p.created_at). Не связано с MFA (код не менялся), ранее отложено владельцем; не исправлялось.")
r["open_subchecks"] = {
    "rbac": "confirmed by tests",
    "readonly_smoke": "partially confirmed live: dashboard, inbox, user search 200 with a TOTP session",
    "payments_section": "error: /api/admin/finance HTTP 500 in Production (text >= timestamp)",
    "generations_errors_sections": "not exercised live yet",
}
r["next_action"] = ("Исправить /api/admin/finance (сравнение purchases.created_at как timestamp) отдельной задачей "
                    "с разрешения владельца; затем read-only smoke разделов генераций и ошибок.")
r["assessed_on"] = "2026-11-10"
if "B10_MFA_PRODUCTION" not in r["evidence_ids"]:
    r["evidence_ids"].append("B10_MFA_PRODUCTION")
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": "Ошибка", "previous_status": prev,
                     "api_commit": API,
                     "reason": "Read-only smoke частично прошёл; раздел платежей отвечает 500 в Production."})

g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]
g["local_progress"] = ("S1-07 подтверждён; S1-06: XSS устранён, SQLi подтверждена; MFA во всех Telegram-каналах "
                       "развёрнута (API ba96d8c, support a75bf83, main bot 55e57da), вход в Mini App с TOTP "
                       "подтверждён в Production")
g["awaiting"] = ("S1-05: живая проверка ботов, Critical reauth и TOTP третьего администратора. S7-09: ошибка 500 "
                 "/api/admin/finance + smoke генераций/ошибок. S1-06: живые заголовки сайта. S5-08: privacy (с B09).")
d["evidence_catalog"]["B10_MFA_PRODUCTION"] = {"path": "fixes/B10-MFA/PRODUCTION_CHECK.md",
    "scope": "Логи Railway после деплоя MFA: вход в Mini App 401→200 с TOTP, read-only smoke консоли, 500 финансов; "
             "что не проверено вживую и безопасный сценарий"}
d["evidence_catalog"]["B10_MFA_IMPLEMENTATION"] = {"path": "fixes/B10-MFA/RESULT.md",
    "scope": "Реализация MFA, защищённые маршруты, тесты, план развёртывания и инструкция администраторов"}
d["production_source_commits"]["sylvex-ai-webapp"] = API
d["production_source_commits"]["sylvex-ai-bot"] = BOT
d["production_source_commits"]["silvex-support-bot"] = SUPPORT
d["production_role_commits"]["api"] = API
d["production_role_commits"]["main_telegram_bot"] = BOT
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = ("B10 MFA deployed (API ba96d8c, support a75bf83, main bot 55e57da); Mini App TOTP "
                               "confirmed live; S7-09 finance 500 recorded")
d["latest_work_phase"] = "B10_MFA_PRODUCTION"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
