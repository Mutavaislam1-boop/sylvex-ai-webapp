"""Second register update: B13, B16, S8-08 7-day part, SX-010/B14 (partial), bot b7e1b90.

Usage: python3 apply_b13_b16_s808_sx010.py REGISTER.json OUT.json
Run after apply_b09_s705.py. Only the records named here change.
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-09T18:10:00+00:00"
DAY = "2026-11-09"
WATCH = "Assess exact impacted behavior first; never reset whole register"
BOT = "b7e1b906f5beb702683b9556c0f1e2590638347d"

def watch(repo, scope, blob):
    return {"repository": repo, "scope": scope, "git_blob": blob, "action_on_change": WATCH}

def set_watch(r, repo, scope, blob):
    for w in r["reopen_watch"]:
        if w["repository"] == repo and w["scope"] == scope:
            w["git_blob"] = blob
            return
    r["reopen_watch"].append(watch(repo, scope, blob))

def add_ev(r, ev):
    if ev not in r["evidence_ids"]:
        r["evidence_ids"].append(ev)

def hist(r, reason, **extra):
    r["history"].append({"date": DAY, "atUTC": NOW, "status": r["status"], **extra, "reason": reason})

R = {r["id"]: r for r in d["requirements"]}
G = {g["id"]: g for g in d["launch_blocker_groups"]}
assert len(R) == 79

# --- B13 / S1-09: closed ------------------------------------------------------
r = R["S1-09"]; prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "Сайт 806ac3ed: HSTS (только sylvex.ai), минимальный CSP (frame-ancestors self + Telegram Web, object-src none, "
    "base-uri self), nosniff, Referrer-Policy. API 36b56ef1: nosniff и Referrer-Policy для страниц и статики Mini App; "
    "/api/* без изменений. Живые заголовки (HTTP/2 200) подтвердил владелец; работу сайта, Pro Studio, входа и Mini App "
    "в Telegram проверил владелец. Claude живые заголовки не проверял: сеть сессии блокирует sylvex.ai.")
r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B13"]
add_ev(r, "S109_PRODUCTION")
r["next_action"] = "Не требуется. CSP для скриптов/стилей не ужесточать без отдельной проверки источников."
r["assessed_on"] = DAY
set_watch(r, "sylvex-ai-webapp", "services/security.py", "69000820f64ba008a1443cc047afddc3238427cf")
set_watch(r, "sylvex-website", "serve.py", "a7f265f5fca603349b9753668dee62093cef6820")
hist(r, "B13 закрыт: заголовки и работа страниц подтверждены владельцем.", previous_status=prev,
     website_commit="806ac3ed7638110b983e5fe475ab98d0729ac110", api_commit="36b56ef1593ab2f4e14315a41f66af84fa9f10d5",
     owner_confirmed_atUTC="2026-11-08T22:04:14+00:00")

# --- B16 / S8-06: closed ------------------------------------------------------
r = R["S8-06"]; prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "Восстановлены ровно 20 файлов публикации 0a1d43fb побайтово, тексты не правились (API a4dadb3b, деплой 227e07e1 "
    "SUCCESS). Владелец подтвердил HTTP 200 для documents-data.js, privacy.html, ai-acceptable-use.html и работу "
    "раздела «Документы» в Telegram Mini App.")
r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B16"]
add_ev(r, "B16_PRODUCTION")
r["next_action"] = "Не требуется. Тексты документов не менять без отдельного решения."
r["assessed_on"] = DAY
set_watch(r, "sylvex-ai-webapp", "webapp/js/documents-data.js", "d84a0fb560c6a5ff53ae563335a86f258e4be827")
set_watch(r, "sylvex-ai-webapp", "webapp/payments-refunds.html", "70736674af0d8108889a5b247c0b57da11990c83")
set_watch(r, "sylvex-ai-webapp", "webapp/ai-acceptable-use.html", "e0bb800eee56746c4aba5e14ed5af63ede2c3e76")
set_watch(r, "sylvex-ai-webapp", "webapp/privacy.html", "7e533f3814a1a966be2645d206186c8a19f39328")
hist(r, "B16 закрыт: три адреса HTTP 200 и документы в Mini App подтверждены владельцем.", previous_status=prev,
     api_commit="a4dadb3bb0cc179b665b353f06ba13498fb70759", owner_confirmed_atUTC="2026-11-08T22:12:14+00:00")

# --- SX-010 / B14: deployed, NOT closed ---------------------------------------
SX010 = ("SX-010 частично: код внедрён (API 60eb6c2d, 20:37Z 08.11; бот d3987200, 20:39Z; оба сохранены в текущем "
         "Production: API ccde13e, бот b7e1b90). Новые покупки получают дату во всех 5 местах записи; повтор платежа "
         "сохраняет первую дату; покупки без даты видны в режиме «365 дней» группой «Дата неизвестна», без вымышленных "
         "дат. Тесты: API 14/14, бот 3/3. Не сделано: проверка после деплоя, 4 read-only SQL-запроса "
         "(production_readonly_checks.sql), восстановление дат 72 старых записей из достоверного источника.")
for rid, lead in {
    "S2-14": "",
    "S7-01": "Вход/сессии/раздельное скачивание ранее приняты; сайт Online. ",
    "S7-02": "Web-сессия и общий баланс ранее подтверждены; документы Mini App восстановлены (B16 закрыт). ",
}.items():
    r = R[rid]
    r["confirmed_scope"] = lead + SX010
    add_ev(r, "SX010_PRODUCTION")
    if rid == "S7-02":
        r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B16"]
        add_ev(r, "B16_PRODUCTION")
    r["next_action"] = ("Закрыть SX-010: выполнить 4 read-only SQL-запроса, проверить историю после деплоя, "
                        "отдельно решить восстановление старых дат. Новые покупки для теста не делать.")
    r["assessed_on"] = DAY
    hist(r, "SX-010 внедрён, но не проверен после деплоя; статус не меняется." +
         (" B16 снят с блокеров." if rid == "S7-02" else ""),
         api_commit="60eb6c2d83ae9b7a887e54a822001b1adca89434", bot_commit="d3987200484795b9d828de293d68a2675a302690")
G["B14"]["production_progress"] = ("Код SX-010 в Production с 08.11 20:37Z (API 60eb6c2d, бот d3987200), сохранён в "
                                   "ccde13e / b7e1b90. Проверка после деплоя, 4 read-only SQL и восстановление дат "
                                   "72 записей не выполнены.")
G["B14"]["progress_evidence"] = "SX010_PRODUCTION"
G["B14"]["awaiting"] = ("Результаты production_readonly_checks.sql (Claude не имеет доступа к значениям переменных "
                        "Postgres), проверка истории владельцем, затем решение о восстановлении старых дат.")

# --- S8-08 7-day part: fixed; requirement NOT closed ----------------------------
r = R["S8-08"]
r["confirmed_scope"] = (
    "7-дневное автоудаление истории бота устранено: бот b5064bc0 (деплой b2bc13ec, 08.11 22:24Z), сохранено в b7e1b90. "
    "Ручная «Очистить историю» работает. Тест на PostgreSQL: записи 30 и 400 дней сохраняются. Владелец подтвердил "
    "«Мой кабинет» без «7 дней». Ранее удалённые ботом записи восстановить нельзя. Не обеспечены: жизненный цикл "
    "backup, логов и обращений в поддержку. Удаление Telegram-аккаунтов — отдельное отложенное решение владельца.")
add_ev(r, "S808_7DAY_PRODUCTION")
r["next_action"] = ("Отдельно: сроки хранения backup/логов/поддержки. Telegram erasure не разрабатывать до решения "
                    "владельца (SYLVEX_ERASURE_TELEGRAM_READY=0).")
r["assessed_on"] = DAY
set_watch(r, "sylvex-ai-bot", "app/database/db.py", "0482106715089dfed59cf54b9da5e061dab1458c")
set_watch(r, "sylvex-ai-bot", "app/bot/main.py", "4ca0eb32f45cbb0df6f98dfc922ae1b1a78e2052")
hist(r, "7-дневная часть закрыта и подтверждена владельцем; требование частично, статус не меняется.",
     bot_commit="b5064bc0bdc3abff9bee6b95c2663c93e712a1ef", owner_confirmed_atUTC="2026-11-08T22:37:18+00:00")

# --- S7-04: bot commit b7e1b90 -------------------------------------------------
r = R["S7-04"]
r["confirmed_scope"] = (
    "Бот b7e1b90 (деплой f7837266, SUCCESS 08.11 23:18Z): Database connected, Bot started, сверка оплат запущена; "
    "3 TelegramConflictError только во время смены экземпляра. Сохранены SX-002, LB-003, LB-006/014, SX-010 и S8-08. "
    "Код координации Telegram erasure есть, но выключен. Открыто: удаление Telegram-аккаунтов (отложенное решение "
    "владельца) и native Stars приёмка (S8-02).")
r["next_action"] = "Telegram erasure — отложенное решение владельца, не разрабатывать сейчас; native Stars учитывать в S8-02."
r["assessed_on"] = DAY
set_watch(r, "sylvex-ai-bot", "app/bot/main.py", "4ca0eb32f45cbb0df6f98dfc922ae1b1a78e2052")
hist(r, "Production бота обновлён до b7e1b90; статус не меняется.", bot_commit=BOT)

# --- S4-07: wording only (7-day part is fixed) --------------------------------
r = R["S4-07"]
r["confirmed_scope"] = r["confirmed_scope"].replace(
    "7-дневная автоочистка истории в Telegram-боте не входит и остаётся в B09 (S8-08).",
    "7-дневная автоочистка истории в Telegram-боте устранена (S8-08); удаление Telegram-аккаунтов — отложенное решение владельца.")

# --- groups: B13, B16 closed; B09 narrowed --------------------------------------
def close(gid, issue_id, at, extra):
    snap = G[gid]
    d["launch_blocker_groups"] = [g for g in d["launch_blocker_groups"] if g["id"] != gid]
    d["closed_issues"].append({"id": issue_id, "former_blocker": gid, "status": "CLOSED_DEPLOYED_AND_CONTROL_CHECKED",
                               "closedAtUTC": at, **extra, "closed_blocker_snapshot": snap})

close("B13", "LR-004", "2026-11-08T21:52:16+00:00", {
    "website_commit": "806ac3ed7638110b983e5fe475ab98d0729ac110",
    "api_commit": "36b56ef1593ab2f4e14315a41f66af84fa9f10d5",
    "evidence_id": "S109_PRODUCTION",
    "scope": "Минимальный совместимый набор заголовков сайта и Mini App; встраивание Telegram сохранено.",
    "owner_confirmed": "headers HTTP/2 200; site, Pro Studio, login and Telegram Mini App working"})
close("B16", "LR-003", "2026-11-08T22:12:14+00:00", {
    "api_commit": "a4dadb3bb0cc179b665b353f06ba13498fb70759",
    "api_deployment": "227e07e1",
    "evidence_id": "B16_PRODUCTION",
    "scope": "Ровно 20 утверждённых статических файлов документации Mini App, тексты без правок.",
    "owner_confirmed": "3 URLs HTTP 200; Documents section in Telegram Mini App works"})

g = G["B09"]
g["title"] = "Не закрыты оставшиеся deletion/retention обязательства (Telegram и backup/log/support)"
g["closing_criterion"] = (
    "Закрыто: Website и Browser Mini App (B09-WEB), 7-дневное автоудаление истории бота (S8-08, b5064bc0). "
    "Остаток: сроки хранения backup/логов/поддержки. Удаление Telegram-аккаунтов — отложенное решение владельца, "
    "SYLVEX_ERASURE_TELEGRAM_READY=0; не разрабатывать и не запускать удаления для теста.")
g["deferred_owner_decision"] = "Telegram account erasure"
g["closed_parts"] = ["B09-WEB", "S8-08 7-day history expiry"]

# --- evidence ------------------------------------------------------------------
d["evidence_catalog"].update({
    "S109_PRODUCTION": {"path": "fixes/S1-09-production/RESULT.md",
                        "scope": "Сайт 806ac3ed и API 36b56ef1 SUCCESS; заголовки и страницы подтверждены владельцем"},
    "B16_PRODUCTION": {"path": "fixes/B16-production/RESULT.md",
                       "scope": "API a4dadb3b SUCCESS; 3 адреса HTTP 200 и документы в Mini App подтверждены владельцем"},
    "S808_7DAY_PRODUCTION": {"path": "fixes/S8-08-production/RESULT.md",
                             "scope": "Бот b5064bc0 SUCCESS; 7-дневное удаление убрано; «Мой кабинет» подтверждён владельцем"},
    "SX010_PRODUCTION": {"path": "fixes/SX-010-production/RESULT.md",
                         "scope": "Код внедрён (API 60eb6c2d, бот d3987200); проверка после деплоя и SQL не выполнены — частично"},
})

# --- metadata ------------------------------------------------------------------
d["production_role_commits"]["main_telegram_bot"] = BOT
d["production_source_commits"]["sylvex-ai-bot"] = BOT
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["assessed_on"] = DAY
d["last_controlled_change"] = ("Register catch-up: B13 and B16 closed; S8-08 7-day part fixed (requirement open); "
                               "SX-010 deployed, verification pending; bot b7e1b90. No code or Production change")
d["last_updated_atUTC"] = NOW
d["latest_work_phase"] = "REGISTER_CATCH_UP_B13_B16_S808_SX010"

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
