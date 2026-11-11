"""Tenth register update: S7-09 confirmed.

The Generations and Errors requests were not missing from Railway: the
owner opened those sections at 00:50:56-00:51:09Z on 11.11, after the
previous log check (up to 00:47Z). Same iPhone session, all 200, no
Traceback since the deploy abfd8437 (API 9a6dedc):
  /api/admin/generations, /api/admin/generations/stats x2 (Generations),
  /api/admin/error-reports (Errors, default tab).
Together with users, dashboard, inbox and finance (00:42Z) and RBAC/MFA
tests, S7-09 is confirmed.

Usage: python3 apply_s709_close.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T01:00:00+00:00"
r = {x["id"]: x for x in d["requirements"]}["S7-09"]
prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "Production API 9a6dedc (деплой abfd8437), сессия владельца с TOTP, все ответы 200, Traceback после деплоя нет. "
    "Пользователи: /api/admin/users/search, dashboard, inbox/list (11.11 00:42Z). Платежи: /api/admin/finance ×4 "
    "(30 дней и всё время, 00:42Z) — ошибка 500 устранена. Генерации: /api/admin/generations и "
    "/api/admin/generations/stats ×2 (00:51:00Z). Ошибки: /api/admin/error-reports (00:51:09Z, вкладка по "
    "умолчанию). Права доступа: RBAC-тесты и перебор всех /api/admin/* без обходов; вход только с 2FA подтверждён "
    "вживую. Консоль Production (index-DMVHZO2L.js) использует именно эти маршруты, ответы не кэшируются "
    "(POST, no-store). Ранее «отсутствие» запросов объяснялось временем: разделы открыты после выборки логов до "
    "00:47Z. Вкладка «Автоматические» (/api/admin/errors) отдельно не открывалась.")
r["open_subchecks"] = {
    "rbac": "confirmed by tests",
    "users_section": "confirmed live 11.11 00:42Z",
    "payments_section": "fixed and confirmed live: /api/admin/finance 200 x4 (API 9a6dedc)",
    "generations_section": "confirmed live: /api/admin/generations, /generations/stats x2 - 200 at 00:51:00Z",
    "errors_section": "confirmed live: /api/admin/error-reports 200 at 00:51:09Z; the auto tab (/api/admin/errors) not opened",
}
r["next_action"] = "Нет; пересмотр только при изменении кода админки или новой ошибке."
r["assessed_on"] = "2026-11-11"
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                     "api_commit": "9a6dedc4265e0aec56856e41dfd61666033ae193",
                     "reason": "Генерации и ошибки найдены в логах (00:51Z, 200); все разделы S7-09 подтверждены."})
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]
g["requirements"] = [x for x in g["requirements"] if x != "S7-09"]
r["blocker_ids"] = [b for b in r.get("blocker_ids", []) if b != "B10"]  # as for S1-07
g["awaiting"] = ("S1-05: живая проверка ботов, Critical reauth и TOTP третьего администратора. S1-06: живые "
                 "заголовки сайта. S5-08: privacy (с B09).")
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S7-09 confirmed: users, payments, generations and errors sections live with TOTP"
d["latest_work_phase"] = "S709_CONFIRMED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"], "B10", g["requirements"])
