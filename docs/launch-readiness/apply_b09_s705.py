"""Update REGISTER.json for B09 (Website + Browser Mini App) and S7-05 only.

Usage: python3 apply_b09_s705.py REGISTER.json OUT.json
Everything else in the register is left as it is.
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-09T17:40:00+00:00"
DAY = "2026-11-09"
API = "ccde13ebcb8772ae48cec7f99ded0f38002b1efe"
WORKERS = "8b08994a889919c44c04a6b8d5f7423ab7458d2a"
ERASURE_API = "cdfc928fb1c21d054e4cc3c4f7eec4f3413fc45a"
SITE = "821d15193e3b788ace8f6d75ea966c806aee98af"
WATCH = "Assess exact impacted behavior first; never reset whole register"

def watch(repo, scope, blob):
    return {"repository": repo, "scope": scope, "git_blob": blob, "action_on_change": WATCH}

R = {r["id"]: r for r in d["requirements"]}
assert len(R) == 79

# --- S7-05 -----------------------------------------------------------------
r = R["S7-05"]
prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "В пределах ранее проверенного функционала, без нового общего аудита. GF-004/005/006 остаются принятыми. "
    "Подтверждённая ошибка main.py:5511 (record_prostudio_job_stage передавал stage= в prostudio_error и сам падал "
    "TypeError, из-за чего готовый результат провайдера помечался failed) исправлена и внедрена: API ccde13e, "
    "5 workers 8b08994. Целевые тесты 6/6 PASS в API и workers; новых падений в регрессии нет "
    "(36 старых падений тестовых заглушек — отдельная задача). 14 R2-тестов на изолированной PostgreSQL и имитации R2: "
    "12 PASS, 2 FAIL из-за устаревших тестов, проверено, что это не дефекты. Сценарий replace-character/действие видео "
    "повторно не проверялся."
)
if "S705_PRODUCTION" not in r["evidence_ids"]:
    r["evidence_ids"].append("S705_PRODUCTION")
r["next_action"] = ("Не требуется в принятом объёме. Старые тестовые заглушки чинить отдельной задачей; "
                    "replace-character проверять только при отдельном запросе.")
r["assessed_on"] = DAY
r["reopen_watch"] = [
    watch("sylvex-ai-webapp", "webapp/js/cabinet.js", "ec6b8dc66ef4f3d83bc998a38e72bc553db9f5d8"),
    watch("sylvex-ai-webapp", "webapp/index.html", "ba1fb6a9b418e5f4a302146be50b9d52f666d9f7"),
    watch("sylvex-ai-webapp", "main.py (API)", "6a323e66d07bf1d89482c46619bac6a6623db6b3"),
    watch("sylvex-ai-webapp", "main.py (workers)", "56bff908adc3313e8567ecdc17ac81954357aac7"),
]
r["history"].append({"date": DAY, "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                     "api_commit": API, "workers_commit": WORKERS,
                     "reason": "Исправление main.py:5511 внедрено; целевые и R2-тесты пройдены; закрыто владельцем в пределах ранее проверенного функционала."})

# --- B09: Website + Browser Mini App -----------------------------------------
B09_WEB_SCOPE = ("Website и Browser Mini App: необратимое самостоятельное удаление веб-аккаунта по коду подтверждения, "
                 "очистка медиа в R2, отмена подписки, повторная регистрация. Ручной тест владельца пройден. "
                 "Удаление через Telegram не включено (SYLVEX_ERASURE_TELEGRAM_READY=0).")
erasure_watch = [
    watch("sylvex-ai-webapp", "services/account_erasure.py", "00dd2b0fbd925be3b86964f30eebdb20bc032df9"),
    watch("sylvex-ai-webapp", "services/account_erasure_runner.py", "220fb38c4ba9f4817714c2acb6b375c413901e10"),
    watch("sylvex-ai-webapp", "services/account_erasure_guards.py", "46d00c07c424e15ef64c3f8ddc700b18ea4b751d"),
    watch("sylvex-ai-webapp", "services/account_erasure_policy.py", "a07298abe86a2650ffb76d52595eaa36ab925d8f"),
    watch("sylvex-website", "js/api.js", "450ad175a516a28f68f63471f5db7defb8d11493"),
    watch("sylvex-website", "account/settings.html", "44183673a1b4738d732bfe9096716ea6a74a9725"),
]
updated_blobs = {"services/storage.py": "2c36a5f1333442fecac8bf0e8894b7231991a2d2",
                 "services/generation_storage.py": "e0612bfc2e5d7260a34efa9cdb43daeeb1ca4199"}

for rid, scope in {
    "S4-07": "Website и Browser Mini App: удаление аккаунта очищает файлы пользователя в R2 по установленным правилам. "
             "7-дневная автоочистка истории в Telegram-боте не входит и остаётся в B09 (S8-08).",
    "S5-07": "Website и Browser Mini App: удаление аккаунта работает по установленным правилам, ручной тест владельца "
             "пройден, повторная регистрация после удаления работает. Telegram erasure не включён и остаётся в B09.",
}.items():
    r = R[rid]
    prev = r["status"]
    r["status"] = "Подтверждено"
    r["confirmed_scope"] = scope
    r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B09"]
    if "B09_WEB_PRODUCTION" not in r["evidence_ids"]:
        r["evidence_ids"].append("B09_WEB_PRODUCTION")
    r["next_action"] = "Не требуется для Website/Browser Mini App. Telegram-часть закрывается в B09 отдельно."
    r["assessed_on"] = DAY
    for w in r["reopen_watch"]:
        if w["scope"] in updated_blobs:
            w["git_blob"] = updated_blobs[w["scope"]]
    have = {(w["repository"], w["scope"]) for w in r["reopen_watch"]}
    r["reopen_watch"] += [w for w in erasure_watch if (w["repository"], w["scope"]) not in have]
    r["history"].append({"date": DAY, "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                         "api_commit": ERASURE_API, "website_commit": SITE,
                         "reason": "B09 закрыт для Website и Browser Mini App; ручной тест владельца пройден."})

for g in d["launch_blocker_groups"]:
    if g["id"] == "B09":
        g["requirements"] = [x for x in g["requirements"] if x not in ("S4-07", "S5-07")]
        g["closing_criterion"] = (
            "Website и Browser Mini App закрыты (B09-WEB). Остаток: Telegram-бот (7-дневная очистка истории, "
            "Telegram erasure), backup/log/support lifecycle. SYLVEX_ERASURE_TELEGRAM_READY остаётся 0 до отдельного "
            "решения владельца; не запускать удаления для теста.")
        g["partially_closed_by"] = "B09-WEB"

d["closed_issues"].append({
    "id": "B09-WEB",
    "former_blocker": "B09",
    "status": "CLOSED_DEPLOYED_AND_CONTROL_CHECKED",
    "closedAtUTC": NOW,
    "scope": B09_WEB_SCOPE,
    "closed_requirements": ["S4-07", "S5-07"],
    "remaining_in_B09": ["S5-08", "S7-04", "S8-08"],
    "api_commit": ERASURE_API,
    "api_erasure_commits": ["b382c76e8fc22006f24e382ae731adcde764c414", "521c18605b0f83dd8b13614172387ebf92a8c91a",
                            "3d9d4b193ebe29a8b4fb2482b310b783ad5c8138", "3ade6cf1909081da5ac6aa145b2b98dbe8d43f1c", ERASURE_API],
    "website_commit": SITE,
    "reference_index": "backfilled 49/49 tables, 1462 entries",
    "telegram_erasure": "disabled (SYLVEX_ERASURE_TELEGRAM_READY=0)",
    "evidence_id": "B09_WEB_PRODUCTION",
    "owner_manual_test": "passed",
})

d["evidence_catalog"]["B09_WEB_PRODUCTION"] = {
    "path": "fixes/B09-production/RESULT.md",
    "scope": "Web erasure и оптимизация внедрены с разрешения владельца; ручной тест владельца пройден; нагрузка только на изолированной базе; Telegram erasure выключен"}
d["evidence_catalog"]["S705_PRODUCTION"] = {
    "path": "fixes/S7-05-production/RESULT.md",
    "scope": "Исправление main.py:5511 в API и 5 workers; целевые тесты 6/6; 14 R2-тестов 12 PASS / 2 устаревших; без платных генераций"}

# --- metadata ----------------------------------------------------------------
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["production_role_commits"]["api"] = API
for k in ("worker", "worker2", "worker3", "worker4", "worker5"):
    d["production_role_commits"][k] = WORKERS
d["production_source_commits"]["sylvex-ai-webapp"] = API
d["production_source_commits"]["sylvex-website"] = SITE
d["backup_and_erasure_work"] = ("Web self-service erasure enabled by owner (B09-WEB); Telegram erasure OFF "
                                "(SYLVEX_ERASURE_TELEGRAM_READY=0); backup work not resumed")
d["assessed_on"] = DAY
d["last_controlled_change"] = ("B09 closed for Website and Browser Mini App; S7-05 fix main.py:5511 deployed to API "
                               "ccde13e and 5 workers 8b08994; no paid generations or purchases")
d["last_updated_atUTC"] = NOW
d["latest_work_phase"] = "B09_WEB_AND_S7_05_CLOSED"

json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
