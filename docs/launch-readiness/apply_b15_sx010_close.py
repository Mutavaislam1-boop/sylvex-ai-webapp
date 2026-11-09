"""Third register update: B15 deployed to Production; SX-010/B14 closed by the owner.

Usage: python3 apply_b15_sx010_close.py REGISTER.json OUT.json
Run after apply_b13_b16_s808_sx010.py. Only the records named here change.
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-09T22:05:00+00:00"
DAY = "2026-11-09"
API = "5dbcde12ad3b827e77a48e2e08a49b338c3868ce"
WORKERS = "dde6deafbb044f0f27657b9e08b4ae9d5d02f500"
R = {r["id"]: r for r in d["requirements"]}
G = {g["id"]: g for g in d["launch_blocker_groups"]}
assert len(R) == 79

def add_ev(r, ev):
    if ev not in r["evidence_ids"]:
        r["evidence_ids"].append(ev)

def set_status(r, status, scope, next_action, reason, **extra):
    prev = r["status"]
    r["status"] = status
    r["confirmed_scope"] = scope
    r["next_action"] = next_action
    r["assessed_on"] = DAY
    r["history"].append({"date": DAY, "atUTC": NOW, "status": status, "previous_status": prev, **extra, "reason": reason})

B15_DEPLOY = ("B15 в Production: API 5dbcde1 (деплой be0686d8) и 5 workers dde6dea (c5c8fb40, fe64902c, 70345486, "
              "142d6925, 9caab3df), все SUCCESS 09.11 21:39–21:47Z; до выкатки активных генераций не было; после — "
              "без новых ошибок и 5xx.")

# --- B15 -----------------------------------------------------------------------
set_status(R["S3-07"], "Подтверждено",
    "Серверные состояния queued → processing → provider_processing → completed/failed проверены на реальной PostgreSQL: "
    "финальный статус не перезаписывается; completed фиксируется вместе со списанием; принятое провайдером задание "
    "после 480 с остаётся provider_processing (фоновое ожидание) и завершается один раз. " + B15_DEPLOY +
    " Клиентский контракт опроса не менялся.",
    "Не требуется. Перепроверять только при изменении машины состояний.",
    "B15 развёрнут; адресные тесты состояний PASS.", api_commit=API, workers_commit=WORKERS)
set_status(R["S3-08"], "Подтверждено",
    "Сбой БД или падение процесса не оставляют failed со списанием: списание атомарно с completed; результат "
    "сохраняется контрольной точкой и восстанавливается после перезапуска; списание по старому порядку возвращается "
    "один раз; восстановленные задания попадают в историю и Telegram. " + B15_DEPLOY,
    "Не требуется в принятом объёме.",
    "B15 развёрнут; тесты сбоев и восстановления PASS.", api_commit=API, workers_commit=WORKERS)
set_status(R["S3-09"], "Не проверено",
    "Локальная матрица таймаутов пройдена: один вызов провайдера, ограниченные опросы; после 480 с принятое задание "
    "ждёт в фоне до 25 мин и завершается одним списанием или одним возвратом; поздний результат после возврата "
    "доставляется без списания. " + B15_DEPLOY + " Поведение Kling после 480 с НЕ подтверждено реальной генерацией.",
    "Подтвердить на первой естественной генерации видео дольше 480 с по логам (JOB_PROVIDER_BACKGROUND_WAIT, "
    "BACKGROUND_PROVIDER_JOB_COMPLETED). Платные тестовые генерации не запускать.",
    "Исправление развёрнуто; ожидается подтверждение реальной генерацией.", api_commit=API, workers_commit=WORKERS)
r = R["S7-07"]
r["confirmed_scope"] = ("Серверная часть: задание не зависает (фоновое ожидание ограничено 25 мин, затем возврат и "
    "одно уведомление); уведомление о неудаче не отправляется, пока провайдер работает. " + B15_DEPLOY +
    " Полный UX ошибок провайдера/хранилища в клиентах не проверялся.")
r["next_action"] = "Только клиентский UX ошибок и терминальных экранов; серверную часть B15 не повторять."
r["assessed_on"] = DAY
r["history"].append({"date": DAY, "atUTC": NOW, "status": r["status"], "reason": "Серверная часть B15 развёрнута; статус не меняется до проверки клиентов."})
r = R["S4-01"]
r["confirmed_scope"] = r["confirmed_scope"] + (" B15: R2 SQL-восстановление 11/11 на текущем коде; поздние и восстановленные "
    "результаты проходят через ту же R2-очередь. Все типы медиа end-to-end по-прежнему не приняты.")
r["assessed_on"] = DAY
for rid in ("S3-07", "S3-08", "S3-09", "S7-07", "S4-01"):
    add_ev(R[rid], "B15_PRODUCTION")
for rid in ("S3-07", "S3-08"):
    R[rid]["blocker_ids"] = [b for b in R[rid]["blocker_ids"] if b != "B15"]
g = G["B15"]
g["requirements"] = ["S3-09", "S4-01", "S7-07"]
g["production_progress"] = ("Атомарное списание, контрольная точка, поздние результаты и фоновое ожидание после 480 с "
                            "в Production (API 5dbcde1, workers dde6dea), все 6 деплоев SUCCESS.")
g["progress_evidence"] = "B15_PRODUCTION"
g["awaiting"] = ("S3-09: подтверждение на реальной генерации видео дольше 480 с (без платных тестов); S4-01: все типы "
                 "медиа end-to-end; S7-07: клиентский UX ошибок.")
g["closing_criterion"] = ("Закрыто S3-07/S3-08. Остаток: реальное подтверждение фонового ожидания Kling, приёмка всех "
                          "типов медиа в R2 и клиентский UX ошибок. B15 не возобновлять без новой ошибки.")

# --- SX-010 / B14: closed by the owner -------------------------------------------
SX = ("Даты новых покупок и подписок работают, подтверждено владельцем. Исторические 72 записи без даты по решению "
      "владельца не восстанавливаются и повторно не проверяются; они видны в режиме «365 дней» группой "
      "«Дата неизвестна», без вымышленных дат.")
for rid, lead in {"S2-14": "", "S7-01": "Вход/сессии/раздельное скачивание ранее приняты. ",
                  "S7-02": "Web-сессия, общий баланс и документы Mini App подтверждены. "}.items():
    r = R[rid]
    r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B14"]
    set_status(r, "Подтверждено", lead + SX, "Не требуется.", "SX-010 закрыт владельцем.")
snap = G.pop("B14")
d["launch_blocker_groups"] = [x for x in d["launch_blocker_groups"] if x["id"] != "B14"]
d["closed_issues"].append({"id": "SX-010", "former_blocker": "B14", "status": "CLOSED_BY_OWNER_DECISION",
    "closedAtUTC": NOW, "api_commit": "60eb6c2d83ae9b7a887e54a822001b1adca89434",
    "bot_commit": "d3987200484795b9d828de293d68a2675a302690", "evidence_id": "SX010_PRODUCTION",
    "scope": SX, "historical_rows_restored": False, "closed_blocker_snapshot": snap})

d["evidence_catalog"]["B15_PRODUCTION"] = {"path": "fixes/B15-production/RESULT.md",
    "scope": "Деплой API 5dbcde1 и 5 workers dde6dea, SUCCESS; тесты 31/31 и регрессия без новых падений; Kling >480 с live не подтверждён"}

d["production_role_commits"]["api"] = API
for k in ("worker", "worker2", "worker3", "worker4", "worker5"):
    d["production_role_commits"][k] = WORKERS
d["production_source_commits"]["sylvex-ai-webapp"] = API
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["assessed_on"] = DAY
d["last_controlled_change"] = ("B15 deployed: API 5dbcde1 + 5 workers dde6dea, all SUCCESS; SX-010 closed by owner. "
                               "No paid generations or purchases")
d["last_updated_atUTC"] = NOW
d["latest_work_phase"] = "B15_DEPLOYED_SX010_CLOSED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
