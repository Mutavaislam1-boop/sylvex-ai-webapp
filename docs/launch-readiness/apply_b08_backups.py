"""Fifteenth register update: B08 resumed - Railway Pro and the first volume backup.

The owner moved the workspace to Railway Pro (confirmed read-only: Pro,
volume backup limit 10) and confirmed in the dashboard a PostgreSQL backup
of 2.24 GB and an active schedule for the next one. Read-only API checks
(11.11): the Postgres mount config returns no backupSchedules field, and an
environment patch b097f3e3 (11:36:48Z, changes not readable) is still
staged, so Daily/Weekly rests on the owner's dashboard observation.

Restore from the new backup is NOT verified: a Railway volume-backup restore
remounts onto the same Postgres service (restore over Production). The C2
isolated restore (131 tables / 59 sequences) stays as proof of the method.

S5-05 and S6-10: Отложено -> Не проверено (owner resumed the work).
S5-03 unchanged. Nothing in Production changed.

Usage: python3 apply_b08_backups.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T12:30:00+00:00"
REQ = {x["id"]: x for x in d["requirements"]}

d["evidence_catalog"]["B08_BACKUPS"] = {
    "path": "fixes/B08/RESULT.md",
    "scope": "Railway Pro, первая копия тома Postgres 2,24 ГБ (владелец), расписание по панели владельца; "
             "восстановление новой копии не проверялось",
}
BACKUP_FACTS = {
    "railway_plan": "Pro (read-only check 11.11; volume backup limit 10)",
    "first_backup": "owner-confirmed in the Railway dashboard: PostgreSQL volume backup 2.24 GB",
    "schedule": "Daily + Weekly per the owner's dashboard; the API mount config shows no backupSchedules and "
                "environment patch b097f3e3 (11:36:48Z) is still staged - not independently confirmed",
    "retention_per_railway_docs": "daily 6 days, weekly 27 days, monthly 89 days",
    "restore_new_backup": "NOT verified: volume restore remounts onto the same Postgres service (over Production)",
    "restore_method_c2": "confirmed earlier: isolated restore 131 tables / 59 sequences (evidence BACKUP)",
}

s505 = REQ["S5-05"]
prev = s505["status"]
s505["status"] = "Не проверено"
s505["confirmed_scope"] = (
    "Railway Pro (лимит копий тома 10). Владелец подтвердил в панели копию тома Postgres 2,24 ГБ и активное "
    "расписание Daily и Weekly; через API расписание не видно (backupSchedules нет, staged-патч b097f3e3 не "
    "применён). Сроки по документации Railway: ежедневные 6 дней, еженедельные 27. Способ восстановления "
    "доказан ранее изолированным восстановлением C2 (131 таблица, 59 sequences). Восстановление новой копии "
    "не проверялось: восстановление копии тома Railway подменяет том того же сервиса Postgres.")
s505["open_subchecks"] = BACKUP_FACTS
s505["evidence_ids"] = list(dict.fromkeys(s505.get("evidence_ids", []) + ["B08_BACKUPS"]))
s505["next_action"] = ("Подтвердить первую плановую копию (Daily) в списке Backups и что патч b097f3e3 не держит "
                       "расписание неприменённым; затем одно восстановление новой копии в отдельную БД — только с "
                       "разрешения владельца на способ (PITR в новый сервис или временный тестовый Postgres).")
s505["assessed_on"] = "2026-11-11"
s505["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Не проверено", "previous_status": prev,
                        "evidence_id": "B08_BACKUPS",
                        "reason": "Владелец возобновил B08: Railway Pro, первая копия 2,24 ГБ, расписание Daily/Weekly "
                                  "в панели. Восстановление новой копии не проверено."})

s610 = REQ["S6-10"]
prev = s610["status"]
s610["status"] = "Не проверено"
s610["confirmed_scope"] = (
    "Откат приложения: Railway хранит прежние деплои (canRollback: true); миграции аддитивные, старые и новые "
    "wallet INSERT совместимы. Откат данных: появились копии тома Postgres (Pro, копия 2,24 ГБ, расписание по "
    "панели владельца). Восстановление данных из новой копии не проверялось; C2 доказал способ.")
s610["evidence_ids"] = list(dict.fromkeys(s610.get("evidence_ids", []) + ["B08_BACKUPS"]))
s610["next_action"] = "Закрывается вместе с S5-05 после восстановления новой копии в отдельную БД."
s610["assessed_on"] = "2026-11-11"
s610["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Не проверено", "previous_status": prev,
                        "evidence_id": "B08_BACKUPS",
                        "reason": "Работа возобновлена владельцем; копии есть, восстановление новой копии не проверено."})

s503 = REQ["S5-03"]
s503["evidence_ids"] = list(dict.fromkeys(s503.get("evidence_ids", []) + ["B08_BACKUPS"]))
s503["next_action"] = ("Перед изменением схемы — ручная копия тома (Backups → Backup now); статус закрывается "
                       "вместе с S5-05 после проверки восстановления новой копии.")
s503["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": s503["status"],
                        "previous_status": s503["status"], "evidence_id": "B08_BACKUPS",
                        "reason": "Копии тома доступны (Pro); статус не меняется до проверки восстановления."})

g = [g for g in d["launch_blocker_groups"] if g["id"] == "B08"][0]
g["closing_criterion"] = ("C2 restore proof сохранить. Автоматические копии тома Railway (Pro) включены владельцем; "
                          "для закрытия — первая плановая копия и одно восстановление новой копии в отдельную БД, "
                          "не поверх Production.")
g["production_progress"] = "Railway Pro; копия тома Postgres 2,24 ГБ; расписание Daily + Weekly (панель владельца)"
g["progress_evidence"] = "B08_BACKUPS"
g["awaiting"] = ("Подтверждение первой плановой копии и статуса патча b097f3e3; решение владельца о способе "
                 "проверки восстановления (PITR в новый сервис или временный тестовый Postgres; оба платные).")
d["backup_and_erasure_work"] = ("Web self-service erasure enabled by owner (B09-WEB); Telegram erasure OFF "
                                "(SYLVEX_ERASURE_TELEGRAM_READY=0); backup work resumed 11.11 on Railway Pro "
                                "(volume backups), restore of a new backup not verified")

d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B08 resumed: Railway Pro, first Postgres volume backup 2.24 GB, schedule per owner"
d["latest_work_phase"] = "B08_BACKUPS_ENABLED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
