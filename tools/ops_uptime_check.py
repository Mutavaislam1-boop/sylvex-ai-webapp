#!/usr/bin/env python3
"""External uptime check for the SYLVEX API (B11).

Runs OUTSIDE Railway (GitHub Actions, .github/workflows/ops-uptime.yml), so
the administrator hears about the API or its database being down even when
every SYLVEX service is down. Standard library only.

- Probes each URL (default https://api.sylvex.ai/health/ready, which also
  checks the database): HTTP 200 with {"ok": true}, two tries 10 s apart.
- DOWN after FAIL_THRESHOLD failed runs in a row (default 2: with a run every
  5 min that is 5-10 min of downtime, no alert on a single blip); one alert,
  a reminder every REMINDER_SECONDS while down, one recovery message with
  the downtime.
- A message that could not be sent stays pending and is retried next run;
  the run then exits 1, so GitHub's own failure e-mail is a fallback channel.
- Every attempt is kept in the state file (last 50) and printed; the bot
  token never appears in output (errors are reduced to their type / code).

Environment: OPS_TELEGRAM_BOT_TOKEN, OPS_TELEGRAM_CHAT_ID (GitHub secrets),
OPS_UPTIME_URLS (comma separated, optional), OPS_UPTIME_STATE (path).
Usage: ops_uptime_check.py [--mode check|test]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URLS = ("https://api.sylvex.ai/health/ready",)
FAIL_THRESHOLD = int(os.getenv("OPS_UPTIME_FAIL_THRESHOLD", "2") or 2)
REMINDER_SECONDS = int(os.getenv("OPS_UPTIME_REMINDER_SECONDS", "21600") or 21600)
TIMEOUT = 15
RETRY_PAUSE = 10


def probe(url, opener=urllib.request.urlopen, sleep=time.sleep, tries=2):
    """(ok, detail) - healthy only for HTTP 200 with {"ok": true}."""
    detail = ""
    for attempt in range(tries):
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": "sylvex-ops-uptime"}), timeout=TIMEOUT) as r:
                body = r.read(2048)
                if r.status == 200 and json.loads(body or b"{}").get("ok") is True:
                    return True, "ok"
                detail = f"http_{r.status}"
        except urllib.error.HTTPError as exc:
            detail = f"http_{exc.code}"
        except Exception as exc:  # timeout, DNS, TLS, refused, bad JSON
            detail = type(exc).__name__
        if attempt + 1 < tries:
            sleep(RETRY_PAUSE)
    return False, detail


def telegram_sender(token, chat_id, opener=urllib.request.urlopen):
    def send(text):
        if not token or not chat_id:
            return False, "not_configured"
        data = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            with opener(request, timeout=TIMEOUT) as r:
                ok = r.status == 200 and json.loads(r.read() or b"{}").get("ok") is True
                return ok, None if ok else f"http_{r.status}"
        except urllib.error.HTTPError as exc:
            return False, f"http_{exc.code}"
        except Exception as exc:
            return False, type(exc).__name__  # never the URL: it holds the token
    return send


def _minutes(seconds):
    return max(1, int(seconds // 60))


def text_for(event, url, detail, downtime):
    host = url.split("/")[2] if "//" in url else url
    if event == "resolve":
        return f"✅ SYLVEX: API снова доступен ({host}).\nНедоступен был: {_minutes(downtime)} мин."
    if event == "test":
        return "🧪 SYLVEX: тест внешней проверки доступности. Канал работает."
    head = "🔴 SYLVEX P0: API недоступен" if event == "fire" else "⏰ SYLVEX P0: API всё ещё недоступен"
    return f"{head} ({host}).\nПроверка /health/ready: {detail}. Недоступен: {_minutes(downtime)} мин.\nПроверено извне Railway."


def step(state, url, ok, detail, now):
    """Advance one URL's state; returns the event to notify (or None)."""
    s = state.setdefault(url, {"state": "up", "failures": 0, "down_since": None, "last_notified": None,
                               "pending": None, "detail": ""})
    if ok:
        s["failures"] = 0
        if s["state"] == "down":
            s["state"], s["pending"] = "up", "resolve"
            s["downtime"] = now - (s["down_since"] or now)
            s["down_since"] = None
    else:
        s["failures"] += 1
        s["detail"] = detail
        if s["failures"] == 1:
            s["first_failure"] = now
        if s["state"] == "up" and s["failures"] >= FAIL_THRESHOLD:
            s["state"], s["pending"] = "down", "fire"
            s["down_since"] = s.get("first_failure") or now
        elif s["state"] == "down" and not s["pending"] and now - (s["last_notified"] or 0) >= REMINDER_SECONDS:
            s["pending"] = "reminder"
    return s["pending"]


def run(state, urls, send, now, probe_fn=probe, mode="check"):
    """One run. Returns (state, all_delivered)."""
    log = state.setdefault("_deliveries", [])
    sites = state.setdefault("sites", {})
    delivered_all = True

    def deliver(url, event, text):
        nonlocal delivered_all
        ok, error = send(text)
        log.append({"at": int(now), "url": url, "event": event, "ok": bool(ok), "error": error})
        del log[:-50]
        print(json.dumps({"ops_uptime_delivery": {"url": url, "event": event, "ok": bool(ok), "error": error}}))
        delivered_all = delivered_all and ok
        return ok

    if mode == "test":
        deliver("test", "test", text_for("test", "test", "", 0))
        return state, delivered_all
    for url in urls:
        ok, detail = probe_fn(url)
        print(json.dumps({"ops_uptime_probe": {"url": url, "ok": ok, "detail": detail}}))
        event = step(sites, url, ok, detail, now)
        if event:
            s = sites[url]
            downtime = s.get("downtime", 0) if event == "resolve" else now - (s["down_since"] or now)
            if deliver(url, event, text_for(event, url, s.get("detail", ""), downtime)):
                s["pending"], s["last_notified"] = None, now
    return state, delivered_all


def main(argv=None):
    args = argparse.ArgumentParser()
    args.add_argument("--mode", choices=("check", "test"), default="check")
    mode = args.parse_args(argv).mode
    path = os.getenv("OPS_UPTIME_STATE", ".ops-uptime/state.json")
    urls = [u.strip() for u in (os.getenv("OPS_UPTIME_URLS") or ",".join(DEFAULT_URLS)).split(",") if u.strip()]
    try:
        with open(path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    send = telegram_sender(os.getenv("OPS_TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("OPS_TELEGRAM_CHAT_ID", "").strip())
    state, delivered = run(state, urls, send, time.time(), mode=mode)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            for url, s in state.get("sites", {}).items():
                f.write(f"- {url}: {s['state']} (failures {s['failures']})\n")
            for d in state.get("_deliveries", [])[-5:]:
                f.write(f"- delivery {d['event']} {d['url']}: {'ok' if d['ok'] else d['error']}\n")
    return 0 if delivered else 1


if __name__ == "__main__":
    sys.exit(main())
