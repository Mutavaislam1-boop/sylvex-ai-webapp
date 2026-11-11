"""Ninth register update: S7-09 after the finance fix (API 9a6dedc).

Production logs (11.11, 00:42:11-00:42:34Z, the owner's iPhone session):
Mini App sign-in with TOTP (401 then 200), auth/me, dashboard, users/search,
inbox/list and four POST /api/admin/finance - all 200; no Traceback since the
deploy (abfd8437). The owner also reported Generations and Errors opening,
but neither the app log nor the Railway proxy log has any request to
/api/admin/generations*, /api/admin/errors or /api/admin/error-reports after
the deploy, so those two sections are not confirmed -> S7-09 moves from
Ошибка to Не проверено, not to Подтверждено.

Usage: python3 apply_s709_finance.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T00:50:00+00:00"
API = "9a6dedc4265e0aec56856e41dfd61666033ae193"
r = {x["id"]: x for x in d["requirements"]}["S7-09"]
prev = r["status"]
r["status"] = "Не проверено"
r["confirmed_scope"] = (
    "RBAC маршрутов админки подтверждён тестами. Ошибка 500 раздела платежей УСТРАНЕНА: API 9a6dedc (деплой "
    "abfd8437 SUCCESS 10.11 15:15:41Z) читает purchases.created_at (TEXT в Production) безопасно, невозможные даты — "
    "без даты, без ошибки. ПОДТВЕРЖДЕНО ЛОГАМИ 11.11 00:42Z (сессия владельца с TOTP): POST /api/admin/finance ×4 — "
    "200 (30 дней и всё время), dashboard, users/search, inbox/list — 200; Traceback после деплоя нет. "
    "НЕ ПОДТВЕРЖДЕНО ЛОГАМИ: разделы «Генерации» и «Ошибки» — владелец сообщил, что открываются, но запросов к "
    "/api/admin/generations*, /api/admin/errors и /api/admin/error-reports после деплоя нет ни в журнале приложения, "
    "ни в журнале прокси Railway.")
r["open_subchecks"] = {
    "rbac": "confirmed by tests",
    "payments_section": "fixed and confirmed live: /api/admin/finance 200 x4 on 11.11 00:42Z (API 9a6dedc)",
    "users_dashboard_inbox": "confirmed live: 200 with a TOTP session",
    "generations_section": "owner-reported; no /api/admin/generations* request in Railway logs after deploy",
    "errors_section": "owner-reported; no /api/admin/errors or /api/admin/error-reports request in Railway logs after deploy",
}
r["next_action"] = ("Открыть в консоли «Генерации» и «Ошибки» (только просмотр) и сразу сообщить время; сверка "
                    "логов на /api/admin/generations, /generations/stats, /errors, /error-reports (200, без Traceback).")
r["assessed_on"] = "2026-11-11"
for e in ("S709_FINANCE",):
    if e not in r["evidence_ids"]:
        r["evidence_ids"].append(e)
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Не проверено", "previous_status": prev,
                     "api_commit": API, "deployment": "abfd8437-3617-4744-a2a7-d6b02208a745",
                     "reason": "Ошибка финансов устранена и подтверждена логами; генерации и ошибки в логах не найдены."})
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]
g["awaiting"] = ("S1-05: живая проверка ботов, Critical reauth и TOTP третьего администратора. S7-09: подтверждение "
                 "логами разделов «Генерации» и «Ошибки». S1-06: живые заголовки сайта. S5-08: privacy (с B09).")
d["evidence_catalog"]["S709_FINANCE"] = {"path": "fixes/S7-09-finance/RESULT.md",
    "scope": "Причина и исправление 500 /api/admin/finance (TEXT created_at), тесты, деплой abfd8437, логи 11.11 00:42Z"}
d["production_source_commits"]["sylvex-ai-webapp"] = API
d["production_role_commits"]["api"] = API
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S7-09 finance 500 fixed (API 9a6dedc) and confirmed live; generations/errors unconfirmed"
d["latest_work_phase"] = "S709_FINANCE_FIX"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
