"""Thirteenth register update: B11 implementation ready on a branch (not
deployed). S6-08 stays Не проверено.

Usage: python3 apply_b11_implementation.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-11T03:00:00+00:00"
r = {x["id"]: x for x in d["requirements"]}["S6-08"]
r["open_subchecks"]["implementation"] = (
    "ready on claude/b11-ops-alerts 7a35c7f, not deployed: in-app detectors (workers stalled/dead, mass generation "
    "failures, provider circuits, DB unreachable) + external GitHub Actions uptime check of /health/ready; dedup, "
    "reminders, recovery, delivery log; 19 targeted tests + 119 regression")
r["next_action"] = ("Разрешение владельца на развёртывание по fixes/B11/IMPLEMENTATION.md: API (выключено), проверка "
                    "доставки и получателя через /api/admin/v2/ops/alerts, согласованная тест-отправка, включение, "
                    "секреты GitHub и тест внешней проверки.")
r["assessed_on"] = "2026-11-11"
if "B11_IMPLEMENTATION" not in r["evidence_ids"]:
    r["evidence_ids"].append("B11_IMPLEMENTATION")
r["history"].append({"date": "2026-11-11", "atUTC": NOW, "status": r["status"], "previous_status": r["status"],
                     "branch_commit": "7a35c7f9d79c772d6035a9f39bae040d37f9d992",
                     "reason": "Оповещения P0 реализованы и протестированы в ветке; не развёрнуто, доставка не подтверждена."})
g = [g for g in d["launch_blocker_groups"] if g["id"] == "B11"][0]
g["local_progress"] = ("Инвентаризация 11.11; реализация оповещений P0 в ветке claude/b11-ops-alerts (7a35c7f), "
                       "тесты пройдены, не развёрнуто")
g["awaiting"] = "Разрешение на развёртывание; согласование получателя; секреты GitHub для внешней проверки."
d["evidence_catalog"]["B11_IMPLEMENTATION"] = {"path": "fixes/B11/IMPLEMENTATION.md",
    "scope": "События, каналы, тесты, план развёртывания и ограничения системы оповещений P0"}
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = "B11 P0 alerts implemented on claude/b11-ops-alerts (not deployed)"
d["latest_work_phase"] = "B11_IMPLEMENTATION"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
