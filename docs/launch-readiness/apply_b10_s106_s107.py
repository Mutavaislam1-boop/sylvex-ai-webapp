"""Fifth register update: B10 — S1-07 confirmed; S1-06 website XSS recorded, fix ready locally.

Usage: python3 apply_b10_s106_s107.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-09T23:00:00+00:00"
DAY = "2026-11-09"
R = {r["id"]: r for r in d["requirements"]}
G = {g["id"]: g for g in d["launch_blocker_groups"]}

def update(r, status, scope, next_action, reason, evidence):
    prev = r["status"]
    r.update(status=status, confirmed_scope=scope, next_action=next_action, assessed_on=DAY)
    if evidence not in r["evidence_ids"]:
        r["evidence_ids"].append(evidence)
    r["history"].append({"date": DAY, "atUTC": NOW, "status": status, "previous_status": prev, "reason": reason})

update(R["S1-07"], "Подтверждено",
    "Сверено с Production API 5dbcde1: (1) квоты на пользователя и операцию в PostgreSQL для всех платных POST "
    "через middleware (provider 12/мин и 200/сутки, отдельная квота загрузок) — действуют для всех процессов; "
    "(2) отдельная квота создания объектов; (3) RATE-1: блокировка после неудачных входов/запросов и лимиты отправки "
    "кодов — в PostgreSQL. IP-лимит 1200/мин хранится в памяти одного экземпляра API (действует, пока API один). "
    "Файлы лимитов после проверок Codex не менялись.",
    "Не требуется. При масштабировании API на несколько экземпляров перенести IP-лимит в общее хранилище.",
    "Исправления Codex RATE-1 и квоты сверены с Production; IP-лимит процессный.", "B10_REVIEW")
update(R["S1-06"], "Ошибка",
    "Подтверждено в Production API 5dbcde1: CSRF (проверка Origin в middleware для всех изменяющих запросов "
    "/api/web/* и веб-cookie; админка — SameSite=Strict + CSRF-токен), XSS-1 (account-auth.js Mini App, "
    "переписан с сохранением экранирования), XSS-4 (проверка origin/source сообщений), CORS-2. "
    "ДЕФЕКТ (низкая серьёзность, свои данные): сайт 821d151 вставлял данные аккаунта в innerHTML без экранирования "
    "— account/profile.html, account/settings.html, аватар в js/site.js; воспроизведено в Chromium. Исправление "
    "готово локально: sylvex-website 968e928 (ветка claude/s106-account-escape), не развёрнуто. "
    "SQL-инъекции: только точечная проверка рискованных шаблонов без находок; все 81 место динамического SQL не "
    "проверялись.",
    "Развернуть sylvex-website 968e928 (fast-forward main) по согласованию, затем «Подтверждено» для XSS/CSRF. "
    "Проверку SQL-инъекций держать отдельно незакрытой.",
    "Пробел XSS на сайте найден и исправлен локально; SQLi не подтверждена полностью.", "S106_LOCAL")
R["S1-06"]["open_subchecks"] = {
    "website_xss": "fix 968e928 ready locally, not deployed",
    "sql_injection": "spot-check of high-risk patterns only (sorting, SET with request keys): no findings; 81 dynamic SQL sites not fully reviewed",
}
g = G["B10"]
g["local_progress"] = "S1-07 подтверждён; S1-06: XSS сайта исправлен локально (sylvex-website 968e928)"
g["awaiting"] = ("S1-06: развёртывание сайта 968e928; отдельная проверка SQL-инъекций. S1-05/S7-09: подтверждение "
                 "владельцем MFA третьего администратора и Telegram-канала, read-only admin smoke. S5-08: privacy.")
g["requirements"] = [x for x in g["requirements"] if x != "S1-07"]
for r_id in ("S1-07",):
    R[r_id]["blocker_ids"] = [b for b in R[r_id]["blocker_ids"] if b != "B10"]
d["evidence_catalog"]["B10_REVIEW"] = {"path": "fixes/S1-06/RESULT.md",
    "scope": "Сверка исправлений Codex CSRF/RATE-1/XSS-1/XSS-4/CORS-2/квот с Production API 5dbcde1; без новых прогонов"}
d["evidence_catalog"]["S106_LOCAL"] = {"path": "fixes/S1-06/RESULT.md",
    "scope": "XSS сайта воспроизведён в Chromium и исправлен локально (968e928); тесты 4/4, набор сайта без новых падений; не развёрнуто"}
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B10: S1-07 confirmed; S1-06 website XSS fixed locally (968e928, not deployed). No code or Production change"
d["latest_work_phase"] = "B10_S107_CONFIRMED_S106_FIX_READY"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
