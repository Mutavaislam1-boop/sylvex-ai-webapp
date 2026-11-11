"""Twelfth register update: MFA manual checks as their own evidence; B11
inventory of critical alerts. No status changes.

- S1-05: evidence B10_MFA_MANUAL (owner's manual checks of 10-11.11 in the
  Railway logs); the third admin's enrollment stays deferred.
- S6-08: what exists (Telegram Stars payment alerts via the
  subscription_events outbox, admin security alerts, health check and
  restart policy) and what is missing (service down, generation failures,
  Stripe, reviews/erasure); delivery is not confirmed -> Не проверено.

Usage: python3 apply_b11_inventory.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T01:40:00+00:00"
R = {r["id"]: r for r in d["requirements"]}

d["evidence_catalog"]["B10_MFA_MANUAL"] = {
    "path": "fixes/B10-MFA/PRODUCTION_CHECK.md",
    "scope": "Ручные проверки MFA владельца 10–11.11 по логам Railway: вход в Mini App только с TOTP; «выйти везде» "
             "снимает подтверждение ботов; бот поддержки без подтверждения отказывает, после — работает; критическое "
             "действие в свежей TOTP-сессии. Не видно: окно повторного TOTP, /admin основного бота. Третий "
             "администратор — отложено."}
r = R["S1-05"]
if "B10_MFA_MANUAL" not in r["evidence_ids"]:
    r["evidence_ids"].append("B10_MFA_MANUAL")
r["open_subchecks"]["third_admin_totp"] = "deferred by owner decision (not done)"

r = R["S6-08"]
r["confirmed_scope"] = (
    "Есть в Production-коде (API 9a6dedc, боты 55e57da/a75bf83): платёжные оповещения Telegram Stars через очередь "
    "subscription_events — payment_error, payment_attention, management_error и события подписок — в "
    "SUBSCRIPTION_ADMIN_CHAT_ID (не задан → ADMIN_ID API) от основного бота, с повторами и last_error, без влияния на "
    "оплату (тесты Codex test_stars_subscriptions); оповещения безопасности админки (новое устройство, 3 неверных кода) "
    "администратору и SUPERADMIN; healthcheck /health/ready и restart ON_FAILURE. НЕТ: оповещений о падении/"
    "недоступности сервисов (вебхуков Railway нет), о массовых ошибках генераций/провайдерах/зависших заданиях, о "
    "неудачных платежах Stripe (тестовый режим, B07), о разборах возвратов и erasure. ДОСТАВКА НЕ ПОДТВЕРЖДЕНА: успех "
    "не логируется, ошибки только в БД; получатель ADMIN_ID API не наблюдался.")
r["open_subchecks"] = {
    "payment_alerts_code": "present: subscription_events outbox (Telegram Stars payment_error/attention, management_error)",
    "payment_alerts_delivery": "not confirmed: owner SQL fixes/B11/owner_alert_delivery_readonly.sql + receipt in Telegram",
    "service_down_alerts": "missing: no Railway webhooks, no code; Railway account email notifications unknown",
    "generation_alerts": "missing: no admin alert on generation failures / provider circuit / stuck jobs",
    "stripe_alerts": "missing (Stripe in test mode, see B07)",
}
r["next_action"] = ("Подтвердить доставку: SQL fixes/B11/owner_alert_delivery_readonly.sql и получатель сообщений "
                    "основного бота; проверить письма Railway о сбоях. Затем решение владельца по недостающим "
                    "оповещениям (падение сервисов, генерации).")
r["assessed_on"] = "2026-11-11"
if "B11_ALERTS" not in r["evidence_ids"]:
    r["evidence_ids"].append("B11_ALERTS")
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "reason": "Инвентаризация оповещений: платёжные и безопасности есть, падений сервисов и "
                               "генераций нет; доставка не подтверждена."})
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B11"][0]
g["local_progress"] = ("Инвентаризация 11.11: платёжные (Telegram Stars) и security-оповещения есть; нет оповещений о "
                       "падении сервисов и генерациях; доставка не подтверждена")
g["awaiting"] = ("Владелец: SQL доставки и получатель сообщений основного бота, письма Railway; решение по недостающим "
                 "оповещениям.")
d["evidence_catalog"]["B11_ALERTS"] = {"path": "fixes/B11/RESULT.md",
    "scope": "Инвентаризация критических оповещений и каналов (код Production, Railway), что есть/нет, что подтвердить"}
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B10 MFA manual evidence recorded; B11 alert inventory (no status change)"
d["latest_work_phase"] = "B11_INVENTORY"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
