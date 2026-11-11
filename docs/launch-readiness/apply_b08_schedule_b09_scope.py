"""Sixteenth register update: B08 schedule evidence, B09 remaining scope.

B08: the owner confirmed in the Railway dashboard the 2.24 GB PostgreSQL
backup and the schedule ("Next backup in 1 hour"). The missing
backupSchedules field in the API mount config is not evidence that no
schedule exists. The first automatic backup and a restore from the new
source stay separate unconfirmed subchecks. No status changes.

B09: exact remaining scope of S7-04 and S8-08 from Production code and the
published documents (fixes/B09/REMAINING.md). No status changes.

Usage: python3 apply_b08_schedule_b09_scope.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T13:00:00+00:00"
REQ = {x["id"]: x for x in d["requirements"]}

# --- B08 ---
s505 = REQ["S5-05"]
s505["open_subchecks"]["schedule"] = (
    "owner-confirmed in the Railway dashboard: schedule active, 'Next backup in 1 hour' (11.11); the API mount "
    "config does not expose backupSchedules - not evidence of absence")
s505["open_subchecks"]["first_scheduled_backup"] = "NOT verified: the first automatic backup has not been observed yet"
s505["open_subchecks"]["restore_new_backup"] = (
    "NOT verified: no restore from the new source; volume restore remounts onto the same Postgres service, "
    "so it needs a separate approved method")
s505["confirmed_scope"] = (
    "Railway Pro (лимит копий тома 10). Владелец подтвердил в панели копию тома Postgres 2,24 ГБ и активное "
    "расписание («Next backup in 1 hour», 11.11). Отсутствие backupSchedules в конфигурации API не считается "
    "отсутствием расписания. Сроки по документации Railway: ежедневные 6 дней, еженедельные 27. Способ "
    "восстановления доказан ранее изолированным восстановлением C2 (131 таблица, 59 sequences). Не "
    "подтверждены: первая автоматическая копия и восстановление из нового источника.")
s505["next_action"] = ("Отдельно: (1) первая автоматическая копия в списке Backups; (2) одно восстановление новой "
                       "копии в отдельную БД способом, согласованным владельцем. Неприменённые изменения Railway "
                       "не публиковать, PITR и платные ресурсы без разрешения не подключать.")
s505["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": s505["status"],
                        "previous_status": s505["status"], "evidence_id": "B08_BACKUPS",
                        "reason": "Расписание подтверждено владельцем («Next backup in 1 hour»); первая автоматическая "
                                  "копия и восстановление из нового источника не подтверждены."})
g8 = [g for g in d["launch_blocker_groups"] if g["id"] == "B08"][0]
g8["production_progress"] = ("Railway Pro; копия тома Postgres 2,24 ГБ; расписание активно по панели владельца "
                             "(«Next backup in 1 hour»)")
g8["awaiting"] = ("Первая автоматическая копия; одно восстановление новой копии в отдельную БД (способ — решение "
                  "владельца, платные ресурсы только с разрешения).")

# --- B09 ---
d["evidence_catalog"]["B09_REMAINING"] = {
    "path": "fixes/B09/REMAINING.md",
    "scope": "Точный остаток S7-04/S8-08 по коду Production и опубликованным документам; без изменений",
}
s704 = REQ["S7-04"]
s704["open_subchecks"] = {
    "telegram_erasure": "defect: no Telegram erasure intake - accept_confirmed_request is called only with "
                        "ecosystem='website' (services/account_identity.py:1327); no bot /delete; "
                        "SYLVEX_ERASURE_TELEGRAM_READY=0 only gates intake; bot cache clear (forget_loop) exists",
    "native_stars": "not a defect of S7-04; tracked in S8-02",
}
s704["next_action"] = ("Решение владельца: разрешить приём запроса на удаление Telegram-аккаунта (через поддержку "
                       "или /delete) и включение SYLVEX_ERASURE_TELEGRAM_READY=1 с проверкой на тестовом аккаунте, "
                       "либо принять запуск с этим риском (статус остаётся «Ошибка»).")
s704["evidence_ids"] = list(dict.fromkeys(s704.get("evidence_ids", []) + ["B09_REMAINING"]))

s808 = REQ["S8-08"]
s808["open_subchecks"] = {
    "backups_retention": "compliant if Monthly stays off: daily 6 d, weekly 27 d (policy: up to 30 days)",
    "manual_backups": "manual 2.24 GB backup (11.11) and the C2 copy: no expiry - delete within 30 days of creation",
    "auto_update_backups": "retention undocumented - check in Backups",
    "platform_logs": "Railway log retention on Pro to be checked against the 30-day promise",
    "db_logs": "defect: prostudio_errors / prostudio_error_reports (telegram_id, prompt) have no cleanup",
    "support_records": "defect: support_threads / support_messages have no 12-months-after-closure cleanup",
    "restore_reapplies_erasure": "present: sylvex-erasure-journal (B09-WEB)",
    "bot_7day_expiry": "fixed (b5064bc0)",
    "telegram_erasure": "owner decision, see S7-04",
}
s808["next_action"] = ("Владелец: Monthly не включать, ручные копии удалять ≤ 30 дней, сверить срок логов Railway "
                       "Pro. С разрешения: плановая очистка логов ошибок в БД (30 дней) и закрытых обращений "
                       "(12 месяцев) либо отдельное решение по текстам документов. Telegram erasure — по S7-04.")
s808["evidence_ids"] = list(dict.fromkeys(s808.get("evidence_ids", []) + ["B09_REMAINING"]))
for r in (s704, s808):
    r["assessed_on"] = "2026-11-11"
    r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                         "evidence_id": "B09_REMAINING",
                         "reason": "Уточнён точный остаток по коду Production и документам; статус не меняется."})
g9 = [g for g in d["launch_blocker_groups"] if g["id"] == "B09"][0]
g9["awaiting"] = ("S7-04: приём запроса на удаление Telegram-аккаунта (решение владельца). S8-08: ручные копии "
                  "≤ 30 дней, срок логов Railway, очистка логов ошибок в БД (30 дней) и обращений (12 месяцев). "
                  "S5-08 — вместе с B09.")
g9["remaining_evidence"] = "B09_REMAINING"

d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B08 schedule owner-confirmed; B09 remaining scope of S7-04/S8-08 recorded"
d["latest_work_phase"] = "B09_SCOPED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
