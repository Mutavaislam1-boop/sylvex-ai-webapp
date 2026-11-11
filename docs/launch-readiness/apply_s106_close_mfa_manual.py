"""Eleventh register update: S1-06 confirmed live; S1-05 manual MFA checks.

- S1-06: live sylvex.ai (11.11 01:07Z): profile and settings HTTP/2 200 with
  Cache-Control: no-cache, both load /js/site.js?v=s106-xss-20261109 (200),
  and the three files are byte-identical to sylvex-website 3009404, the
  commit the XSS tests and the browser check passed on. With CSRF, SQLi and
  the rest already confirmed -> Подтверждено.
- S1-05: the owner's manual checks (11.11 00:57-01:04Z) are recorded; the
  re-authentication window and the main bot's /admin are not visible in the
  logs and the third admin's enrollment is deferred -> stays Не проверено.

Usage: python3 apply_s106_close_mfa_manual.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T01:15:00+00:00"
R = {r["id"]: r for r in d["requirements"]}
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B10"][0]

r = R["S1-06"]
prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "CSRF (Origin в middleware для изменяющих /api/web/* и веб-cookie; админка SameSite=Strict + CSRF-токен), XSS-1, "
    "XSS-4, CORS-2; SSRF/traversal/upload/identity (51 проверка). SQL-инъекции: полный статический обзор 129/109 мест, "
    "находок нет. XSS сайта устранён: sylvex-website 968e928 + 3009404, тесты и браузерная проверка 0/0. ЖИВАЯ ПРОВЕРКА "
    "11.11 01:07Z: /account/profile.html и /account/settings.html — HTTP/2 200, Cache-Control: no-cache; обе грузят "
    "/js/site.js?v=s106-xss-20261109 (200); все три файла побайтно совпадают с 3009404.")
r["open_subchecks"] = {
    "website_xss": "confirmed live: files byte-identical to tested 3009404, HTML no-cache, site.js version loaded",
    "sql_injection": "confirmed: full static review, no findings",
}
r["next_action"] = "Нет; пересмотр только при изменении сайта/security middleware или новой ошибке."
r["assessed_on"] = "2026-11-11"
r["blocker_ids"] = [b for b in r.get("blocker_ids", []) if b != "B10"]
if "S106_LIVE" not in r["evidence_ids"]:
    r["evidence_ids"].append("S106_LIVE")
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                     "website_commit": "30094047f0a90cf1181ab9a24441998b22f5b7ef",
                     "reason": "Живые заголовки и site.js подтверждены; файлы совпадают с протестированным коммитом."})
g["requirements"] = [x for x in g["requirements"] if x != "S1-06"]

r = R["S1-05"]
prev = r["status"]
r["confirmed_scope"] += (
    " РУЧНАЯ ПРОВЕРКА 11.11 (логи): вход в Mini App только с TOTP (401→200, трижды); «выйти везде» снимает "
    "подтверждение бота; бот поддержки без подтверждения отказывает (00:58:44–48, разделы не вызваны), после входа с "
    "TOTP работает (subscribers, top-spenders 200); критический PATCH admins в свежей TOTP-сессии — 200. НЕ ВИДНО В ЛОГАХ: "
    "окно повторного TOTP (reauth не вызывался — действия в пределах 5 мин после входа); /admin основного бота (бот "
    "не логирует команды; консоль по его кнопке на api.sylvex.ai получила только 401). ОТЛОЖЕНО владельцем: подключение "
    "2FA третьим администратором.")
r["open_subchecks"].update({
    "mfa_telegram_miniapp": "confirmed live 10.11 and 11.11 (401 without/wrong code, 200 with TOTP)",
    "mfa_support_bot": "confirmed live 11.11: refused without confirmation, allowed after Mini App TOTP",
    "mfa_main_bot": "not visible in logs: /admin outcome not logged; console via its button (api.sylvex.ai) only 401",
    "critical_reauth_totp": "not exercised live: Critical PATCH done within 5 min of the TOTP sign-in, no reauth request",
    "third_admin_totp": "deferred by owner decision (not done)",
    "mfa_bots": "superseded by mfa_support_bot / mfa_main_bot",
})
r["next_action"] = ("Одна проверка: через 6+ минут после входа выполнить критическое действие (сохранить администратора "
                    "без изменений) — должен появиться запрос кода, reauth 401→200; затем /admin в основном боте после "
                    "подтверждения кнопкой. Третий администратор — отложено.")
r["assessed_on"] = "2026-11-11"
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": prev,
                     "reason": "Ручные проверки Mini App, бота поддержки и выхода везде подтверждены логами; reauth и "
                               "основной бот не видны; третий администратор отложен."})
g["local_progress"] = ("S1-06, S1-07, S7-09 подтверждены; MFA в Production: Mini App и бот поддержки подтверждены "
                       "вживую")
g["awaiting"] = ("S1-05: окно повторного TOTP и /admin основного бота; третий администратор — отложено. "
                 "S5-08: privacy (с B09).")
d["evidence_catalog"]["S106_LIVE"] = {"path": "fixes/S1-06/LIVE_CHECK.md",
    "scope": "Живые заголовки и site.js sylvex.ai 11.11, побайтное совпадение с 3009404"}
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S1-06 confirmed live; S1-05 manual MFA checks recorded (third admin deferred)"
d["latest_work_phase"] = "B10_S106_CLOSED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"], "B10", g["requirements"])
