"""Eighteenth register update: S8-08 retention live in Production.

DATA_RETENTION_ENABLED=1 set by the owner (API deployment b9801cfd, commit
b244195, 14:15Z on 11.11). First pass (DATA_RETENTION log line): 372
prostudio_errors + 4 prostudio_error_reports older than 30 days removed,
exactly the owner's preview; 0 support conversations, 0 support messages,
0 finished erasure fences. The loop's immediate follow-up pass removed
nothing (no second line, no DATA_RETENTION_FAILED). No errors after start.
S8-08 stays 'Ошибка': Telegram erasure (S7-04), Railway log retention and
manual / Auto Update backup retention remain open.

Usage: python3 apply_s808_retention_live.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T14:30:00+00:00"
r = {x["id"]: x for x in d["requirements"]}["S8-08"]
sub = r["open_subchecks"]
sub["db_logs"] = ("confirmed live: retention on since 11.11 14:15Z (API b244195, deployment b9801cfd); first pass "
                  "removed 372 prostudio_errors + 4 prostudio_error_reports older than 30 days (= owner preview); "
                  "follow-up pass removed nothing; every 6 h")
sub["support_records"] = ("confirmed live rule: closed conversations 12 months after closure; first pass found 0 "
                          "eligible (none removed); unresolved payment review keeps them")
sub["erasure_fences"] = "confirmed live rule: finished entries older than 1 day; first pass found 0"
sub["platform_logs"] = "open: Railway log retention on Pro not documented - owner to check against the 30-day promise"
sub["auto_update_backups"] = "open: retention of Railway 'Auto Update' backups not documented - check in Backups"
r["confirmed_scope"] = (r["confirmed_scope"].rstrip(".") + ". Сроки хранения в БД действуют с 11.11 14:15Z: "
                        "логи ошибок 30 дней (первый проход удалил 376 записей), закрытые обращения 12 месяцев "
                        "(подходящих нет), служебные отметки 1 сутки. Платежи, кредиты, генерации и обращения "
                        "не затронуты.")
r["next_action"] = ("Остаток: S7-04 (удаление Telegram-аккаунтов); владелец — срок логов Railway Pro, копии "
                    "Auto Update, удаление ручной копии до 11.12.2026; Monthly не включать.")
r["evidence_ids"] = list(dict.fromkeys(r.get("evidence_ids", []) + ["B09_FIX_PLAN"]))
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "api_commit": "b244195551e10c0babc460a3ca8c3b20e4e0e32c", "deployment": "b9801cfd",
                     "reason": "Очистка по срокам включена; первый проход удалил 372 + 4 записи логов ошибок старше "
                               "30 дней; обращений и отметок к удалению нет. Статус не меняется: S7-04, логи Railway "
                               "и копии открыты."})
d["production_role_commits"]["api"] = "b244195551e10c0babc460a3ca8c3b20e4e0e32c"
g9 = [g for g in d["launch_blocker_groups"] if g["id"] == "B09"][0]
g9["production_progress"] = ("API b244195 в Production (31b00d21, затем b9801cfd с DATA_RETENTION_ENABLED=1): "
                             "очистка по срокам действует; удаление Telegram-аккаунтов развернуто, выключено")
g9["awaiting"] = ("S7-04: включение (бот SYLVEX_ERASURE_ENABLED=1, затем API SYLVEX_ERASURE_TELEGRAM_READY=1) и "
                  "проверка на тестовом Telegram-аккаунте; владелец: срок логов Railway Pro, копии Auto Update, "
                  "ручная копия до 11.12.2026. S5-08 — вместе с B09.")
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S8-08 retention live: 376 error-log rows older than 30 days removed"
d["latest_work_phase"] = "S808_RETENTION_LIVE"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
