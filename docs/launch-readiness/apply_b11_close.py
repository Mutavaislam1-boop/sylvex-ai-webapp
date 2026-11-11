"""Fourteenth register update: S6-08 confirmed, B11 closed.

The owner confirmed (11.11) that the test message of the external uptime
check (GitHub Actions run 43011351746, mode=test, ok=true) arrived in
Telegram. The check run 43011517260 probed /health/ready ok with no
message. Together with the in-app P0 alerts (enabled 02:01Z, test delivery
01:53:10Z received, no false alarms), S6-08 is confirmed and B11 closed.

Also re-applies the two stage 1/4 inline register edits made after
apply_b11_implementation.py (API commit, S6-08 history), so the chain in
README.md reproduces REGISTER.json.

Usage: python3 apply_b11_close.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T11:45:00+00:00"
API = "7a35c7f9d79c772d6035a9f39bae040d37f9d992"
MAIN = "b654563da9bfb8f7e836863e682473eeeae7d22c"

r = {x["id"]: x for x in d["requirements"]}["S6-08"]
prev = r["status"]

# stage 1 / stage 4 inline edits (idempotent)
d["production_role_commits"]["api"] = API
deps = {h.get("deployment") for h in r["history"]}
if "122adaec-1161-4e05-b0c7-e5ab7f8aa8f1" not in deps:
    r["history"].append({"date": "2026-11-11", "atUTC": "2026-11-11T01:45:00+00:00", "status": "Не проверено",
                         "previous_status": "Не проверено", "api_commit": API,
                         "deployment": "122adaec-1161-4e05-b0c7-e5ab7f8aa8f1",
                         "reason": "Этап 1: код оповещений в Production, выключен; получатель не подтверждён."})
if "e508bab5-84dc-4336-80db-d76d6c97d9b8" not in deps:
    r["history"].append({"date": "2026-11-11", "atUTC": "2026-11-11T02:10:00+00:00", "status": "Не проверено",
                         "previous_status": "Не проверено", "deployment": "e508bab5-84dc-4336-80db-d76d6c97d9b8",
                         "reason": "Тест доставки подтверждён; встроенные оповещения включены без ложных тревог; "
                                   "внешняя проверка не включена."})

r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "Встроенные оповещения P0 в Production: API 7a35c7f, деплой e508bab5, OPS_ALERTS_ENABLED=1 с 11.11 02:01Z. "
    "Они срабатывают, если воркеры не забирают задания 5 мин, задание processing без heartbeat 10 мин, массовые "
    "ошибки генераций (≥5 и ≥50% за 15 мин), circuit провайдера не CLOSED или API не видит БД. Одно сообщение, "
    "напоминание раз в 6 ч, восстановление; журнал ops_alert_deliveries. Получатель — чат владельца …0565, тот же, "
    "что у платёжных уведомлений (same_chat_as_payments=true). Тест 01:53:10Z доставлен (ok=true) и получен "
    "владельцем; ложных тревог нет. Внешняя проверка вне Railway (GitHub Actions ops-uptime, main b654563, каждые "
    "5 мин): /health/ready — API и БД; тревога после 2 неудач, напоминания, восстановление, письмо GitHub как "
    "запасной канал. Тест-запуск 43011351746 ok=true, владелец подтвердил получение; check-запуск 43011517260 — "
    "ok, без сообщений. Платёжные (Telegram Stars) — существующая очередь subscription_events, тот же отправитель "
    "(BOT_TOKEN API) и чат, что и подтверждённый тест. Реальных платёжных ошибок не наблюдалось, искусственные не "
    "создавались. Вне объёма: Stripe (тестовый режим, B07); боты и простой воркеров при пустой очереди не "
    "отслеживаются (fixes/B11/IMPLEMENTATION.md, «Ограничения»).")
r["open_subchecks"] = {
    "payment_alerts_code": "present: subscription_events outbox (Telegram Stars payment_error/attention, management_error)",
    "payment_alerts_delivery": "same sender (API BOT_TOKEN) and chat …0565 as the confirmed test (same_chat_as_payments=true); no real payment-error event observed, none created",
    "service_down_alerts": "confirmed: GitHub Actions ops-uptime on main b654563; test run 43011351746 delivered, received by the owner; check run 43011517260 ok",
    "generation_alerts": "confirmed: workers_stalled, workers_stale_jobs, generation_failures, provider_circuit in Production (enabled 02:01Z)",
    "stripe_alerts": "out of scope: Stripe in test mode (B07)",
    "implementation": "API 7a35c7f in Production; in-app alerts ENABLED 11.11 02:01Z (deployment e508bab5)",
    "alert_delivery": "confirmed live: in-app test 01:53:10Z and external test 11:22Z delivered (ok=true), both received by the owner",
    "false_alarms": "none: in-app ~7 cycles 02:01-02:07Z; external check run 11:23Z ok without a message",
}
r["evidence_ids"] = list(dict.fromkeys(r.get("evidence_ids", []) + ["B11_IMPLEMENTATION"]))
r["blocker_ids"] = [b for b in r.get("blocker_ids", []) if b != "B11"]
r["next_action"] = "Нет; пересмотр при изменении ops_alerts/ops-uptime, получателя или при пропущенном сбое."
r["assessed_on"] = "2026-11-11"
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                     "api_commit": API, "github_main_commit": MAIN,
                     "github_runs": ["43011351746", "43011517260"],
                     "reason": "Внешняя проверка опубликована, тест доставлен и получен владельцем; "
                               "встроенные оповещения работают без ложных тревог. B11 закрыт."})

g = [g for g in d["launch_blocker_groups"] if g["id"] == "B11"][0]
d["launch_blocker_groups"] = [x for x in d["launch_blocker_groups"] if x["id"] != "B11"]
d["closed_issues"].append({
    "id": "B11-ALERTS",
    "former_blocker": "B11",
    "status": "CLOSED_DEPLOYED_AND_CONTROL_CHECKED",
    "closedAtUTC": NOW,
    "api_commit": API,
    "api_deployment": "e508bab5",
    "github_main_commit": MAIN,
    "evidence_id": "B11_IMPLEMENTATION",
    "scope": "Оповещения P0 в Telegram владельцу: воркеры, задания, ошибки генераций, провайдеры, БД (в API) и "
             "недоступность API/БД (GitHub Actions вне Railway). Дедуп, напоминания, восстановление, журнал доставки.",
    "owner_confirmed": "Test messages received in Telegram: in-app 01:53:10Z and external (GitHub Actions) 11:22Z",
    "closed_blocker_snapshot": {k: v for k, v in g.items()},
})
d["github_main_commits"]["sylvex-ai-webapp"] = MAIN

d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "S6-08 confirmed, B11 closed: external uptime check live, test delivered and received"
d["latest_work_phase"] = "B11_CLOSED"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"], "groups", [x["id"] for x in d["launch_blocker_groups"]])
