"""Sixth register update: S1-06 website XSS fix deployed (sylvex-website 3009404).

S1-06 moves from Ошибка to Не проверено, not to Подтверждено: no known
defect remains, but the SQL-injection review is still only a spot-check
and the live headers/script were not fetched from this session.

Usage: python3 apply_s106_deployed.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-10T10:35:00+00:00"
SITE = "30094047f0a90cf1181ab9a24441998b22f5b7ef"
R = {r["id"]: r for r in d["requirements"]}
r = R["S1-06"]
prev = r["status"]
r["status"] = "Не проверено"
r["confirmed_scope"] = (
    "Подтверждено: CSRF (Origin в middleware для всех изменяющих /api/web/* и веб-cookie; админка SameSite=Strict + "
    "CSRF-токен), XSS-1, XSS-4, CORS-2 в API 5dbcde1. XSS сайта УСТРАНЁН и развёрнут: sylvex-website 968e928 "
    "(экранирование account/profile.html, account/settings.html, аватар js/site.js) + 3009404 (site.js?v=s106-xss-20261109 "
    "на 30 страницах, Cache-Control: no-cache для страниц); деплой 589b9461 SUCCESS 10.11 10:23:47Z. Браузерная проверка "
    "с опасными символами: 0 выполненных и 0 внедрённых (до исправления 19 и 16). Живые заголовки из этой сессии не "
    "получены (сеть блокирует sylvex.ai). ОТДЕЛЬНО НЕ ПОДТВЕРЖДЕНО: SQL-инъекции — только точечная проверка без находок, "
    "81 место динамического SQL полностью не проверено.")
r["next_action"] = ("Отдельная ограниченная проверка SQL-инъекций по 81 месту динамического SQL; владельцу — проверить "
                    "заголовки сайта командой из fixes/S1-06/RESULT.md.")
r["assessed_on"] = "2026-11-10"
r["open_subchecks"] = {
    "website_xss": "fixed and deployed (sylvex-website 3009404, deployment 589b9461); live headers not fetched from this session",
    "sql_injection": "spot-check of high-risk patterns only: no findings; 81 dynamic SQL sites not fully reviewed",
}
if "S106_PRODUCTION" not in r["evidence_ids"]:
    r["evidence_ids"].append("S106_PRODUCTION")
r["history"].append({"date": "2026-11-10", "atUTC": NOW, "status": "Не проверено", "previous_status": prev,
                     "website_commit": SITE, "deployment": "589b9461-2401-4d73-8352-27daeb3ee961",
                     "reason": "XSS сайта устранён и развёрнут; SQLi остаётся непроверенной."})
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]
g["local_progress"] = "S1-07 подтверждён; S1-06: XSS сайта устранён и развёрнут (sylvex-website 3009404)"
g["awaiting"] = ("S1-06: проверка SQL-инъекций. S1-05/S7-09: подтверждение владельцем MFA третьего администратора и "
                 "Telegram-канала, read-only admin smoke. S5-08: privacy.")
d["evidence_catalog"]["S106_PRODUCTION"] = {"path": "fixes/S1-06/RESULT.md",
    "scope": "Деплой сайта 3009404 (589b9461) SUCCESS; экранирование и сброс кэша site.js; живые заголовки не получены из сессии"}
d["production_source_commits"]["sylvex-website"] = SITE
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S1-06 website XSS fix deployed (sylvex-website 3009404); SQL injection still unverified"
d["latest_work_phase"] = "S106_WEBSITE_XSS_DEPLOYED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
