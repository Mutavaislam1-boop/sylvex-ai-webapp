"""Fourth register update: restore the S1-10 / B02 closure of 8 Nov 2026.

The register received on 9 Nov was the 13:07 UTC snapshot of 8 Nov, taken
before the remaining S1-10 dependency fixes were deployed and accepted the
same day (S1-10 = Подтверждено, B02 closed as LR-001). This restores that
record; each commit is verified as an ancestor of the current Production.

Usage: python3 apply_s110_restore.py REGISTER.json OUT.json
"""
import json, sys
from collections import Counter

SRC, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(SRC, encoding="utf-8"))
NOW = "2026-11-09T22:20:00+00:00"
R = {r["id"]: r for r in d["requirements"]}
G = {g["id"]: g for g in d["launch_blocker_groups"]}
r = R["S1-10"]
prev = r["status"]
r["status"] = "Подтверждено"
r["confirmed_scope"] = (
    "Все прежние dependency findings S1-10 закрыты и внедрены 08.11: certifi 2026.10.23 / Pillow 13.0.0; "
    "pyasn1 0.6.5 / pypdf 6.21.4 (API c7d3e18b, workers 079b4dec → 6b7cd54b); основной бот 13551664 "
    "(aiogram 3.29.1, aiohttp 3.14.4, pyasn1, requests, python-dotenv); support-бот f9cd89ec (aiogram 3.29.1, "
    "aiohttp 3.14.4, python-dotenv 1.2.3). 8 сервисов SUCCESS/Online. Все коммиты входят в текущий Production: "
    "API 5dbcde1, workers dde6dea, бот b7e1b90, support-бот f9cd89ec. Ограничение: pip check внутри "
    "Production-контейнеров не выполнялся.")
r["blocker_ids"] = [b for b in r["blocker_ids"] if b != "B02"]
r["next_action"] = "Не требуется. Новые advisory рассматривать отдельно, по мере появления."
r["assessed_on"] = "2026-11-09"
r["history"].append({"date": "2026-11-09", "atUTC": NOW, "status": "Подтверждено", "previous_status": prev,
                     "reason": "Восстановлено закрытие 08.11 (реестр был получен из снимка 13:07 08.11); коммиты сверены с текущим Production."})
if "B02" in G:
    snap = G["B02"]
    d["launch_blocker_groups"] = [g for g in d["launch_blocker_groups"] if g["id"] != "B02"]
    d["closed_issues"].append({"id": "LR-001", "former_blocker": "B02", "status": "CLOSED_DEPLOYED_AND_CONTROL_CHECKED",
        "closedAtUTC": "2026-11-08T19:50:00+00:00",
        "commits": {"api": "c7d3e18b", "workers": "6b7cd54b", "main_telegram_bot": "13551664", "support_bot": "f9cd89ec"},
        "scope": "Все прежние dependency findings S1-10; pip check в Production-контейнерах не выполнялся.",
        "closed_blocker_snapshot": snap})
d["production_source_commits"]["silvex-support-bot"] = "f9cd89ec007540ac4acefc8f3720d604b27c8d03"
d["counts"] = {k: Counter(x["status"] for x in d["requirements"]).get(k, 0) for k in d["status_vocabulary"]}
assert sum(d["counts"].values()) == 79
d["last_updated_atUTC"] = NOW
d["last_controlled_change"] = d["last_controlled_change"] + "; S1-10/B02 closure of 08.11 restored"
json.dump(d, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("counts", d["counts"])
