"""Seventeenth register update: B09 fixes prepared in branches (not deployed).

S7-04: support-assisted deletion of a Telegram account
(claude/b09-telegram-erasure 9810451). S8-08: scheduled retention of error
logs, closed support conversations and finished erasure fences
(claude/b09-retention 216965d). Tests pass; Production unchanged; statuses
unchanged until deployment and a live check (fixes/B09/FIX_PLAN.md).

Usage: python3 apply_b09_fixes_prepared.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T15:00:00+00:00"
REQ = {x["id"]: x for x in d["requirements"]}
d["evidence_catalog"]["B09_FIX_PLAN"] = {
    "path": "fixes/B09/FIX_PLAN.md",
    "scope": "Исправления S7-04 и S8-08 в ветках, тесты, сверка сроков Railway и план развёртывания; не развёрнуто",
}
s704 = REQ["S7-04"]
s704["open_subchecks"]["telegram_erasure"] = (
    "fix prepared, not deployed: claude/b09-telegram-erasure 9810451 - support intake (users.delete, fresh TOTP, "
    "one-time code to the account's own Telegram chat, retyped ID, audit) into the B09-WEB processor; "
    "deploy needs SYLVEX_ERASURE_ENABLED=1 on the main bot and SYLVEX_ERASURE_TELEGRAM_READY=1 on the API")
s704["next_action"] = ("Развёртывание по fixes/B09/FIX_PLAN.md (шаги 1, 3, 4) с разрешения владельца; затем одна "
                       "проверка на тестовом Telegram-аккаунте владельца.")
s808 = REQ["S8-08"]
s808["open_subchecks"]["db_logs"] = ("fix prepared, not deployed: claude/b09-retention 216965d - prostudio_errors / "
                                     "prostudio_error_reports older than 30 days")
s808["open_subchecks"]["support_records"] = ("fix prepared, not deployed: closed conversations 12 months after "
                                             "closure, own attachments; unresolved payment review keeps them")
s808["open_subchecks"]["erasure_fences"] = "fix prepared: finished sylvex_active_operations older than 1 day"
s808["open_subchecks"]["manual_backups"] = ("manual 2.24 GB backup (11.11): delete by 11.12.2026; C2 copy within "
                                            "30 days of creation")
s808["next_action"] = ("Развёртывание по fixes/B09/FIX_PLAN.md (шаги 1-2: предпросмотр, затем DATA_RETENTION_ENABLED=1) "
                       "с разрешения владельца; владелец: срок логов Railway Pro, копии Auto Update, ручные копии.")
for r in (s704, s808):
    r["evidence_ids"] = list(dict.fromkeys(r.get("evidence_ids", []) + ["B09_FIX_PLAN"]))
    r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                         "evidence_id": "B09_FIX_PLAN",
                         "reason": "Исправление подготовлено в ветке и протестировано; не развёрнуто, статус не меняется."})
g9 = [g for g in d["launch_blocker_groups"] if g["id"] == "B09"][0]
g9["local_progress"] = ("Исправления в ветках: claude/b09-telegram-erasure 9810451 (S7-04), claude/b09-retention "
                        "216965d (S8-08); тесты пройдены, объединяются без конфликтов")
g9["awaiting"] = ("Разрешение владельца на развёртывание (FIX_PLAN шаги 1-4) и живая проверка; владелец: срок логов "
                  "Railway Pro, копии Auto Update, удаление ручной копии до 11.12.2026. S5-08 — вместе с B09.")
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B09 fixes for S7-04 and S8-08 prepared in branches; not deployed"
d["latest_work_phase"] = "B09_FIXES_PREPARED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
