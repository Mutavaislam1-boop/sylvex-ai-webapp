"""scripts/verify_stars_invoice_limits.py against a fake Bot API: reports
invoice-creation acceptance per amount, never prints links, and uses a
payload that no handler accepts for payment."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "verify_stars_invoice_limits", Path(__file__).resolve().parent.parent / "scripts" / "verify_stars_invoice_limits.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


class FakeBotApi:
    """Accepts one-time invoices up to one_time_max and subscriptions up to 10,000."""

    def __init__(self, one_time_max):
        self.one_time_max = one_time_max
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        amount = json["prices"][0]["amount"]
        limit = 10000 if "subscription_period" in json else self.one_time_max
        ok = amount <= limit
        body = {"ok": True, "result": "https://t.me/$secret-link"} if ok else {"ok": False, "error_code": 400, "description": "Bad Request: STARS_AMOUNT_INVALID"}
        return type("R", (), {"status_code": 200 if ok else 400, "json": lambda self: body})()


def test_reports_acceptance_per_amount_and_never_the_links(capsys, monkeypatch):
    api = FakeBotApi(one_time_max=25000)
    results = script.run("123:TOKEN", script.DEFAULT_AMOUNTS, True, session=api)
    assert [(r["type"], r["amount"], r["invoice_creation"]) for r in results] == [
        ("one_time", 10000, "accepted"), ("one_time", 19960, "accepted"), ("one_time", 23952, "accepted"),
        ("one_time", 95808, "rejected"), ("subscription_30_days", 10000, "accepted"), ("subscription_30_days", 10001, "rejected")]
    assert results[3]["error"] == "Bad Request: STARS_AMOUNT_INVALID"
    for call in api.calls:
        assert call["currency"] == "XTR" and call["payload"].startswith("sylvex_limit_check:")
        assert "provider_token" not in call
    assert [c.get("subscription_period") for c in api.calls[-2:]] == [2592000, 2592000]
    monkeypatch.setenv("BOT_TOKEN", "123:TOKEN")
    monkeypatch.setattr(script.requests, "Session", lambda: api)
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "Highest one-time amount accepted for invoice creation: 23952" in out
    assert "no payment was attempted" in out and "t.me" not in out


def test_reports_the_verified_production_results(capsys, monkeypatch):
    # The results Telegram returned for the SYLVEX bot: every one-time amount
    # accepted, the 30-day subscription capped at 10,000 Stars.
    api = FakeBotApi(one_time_max=10**9)
    results = script.run("123:TOKEN", script.DEFAULT_AMOUNTS, True, session=api)
    assert [(r["type"], r["amount"], r["invoice_creation"]) for r in results] == [
        ("one_time", 10000, "accepted"), ("one_time", 19960, "accepted"), ("one_time", 23952, "accepted"),
        ("one_time", 95808, "accepted"), ("subscription_30_days", 10000, "accepted"), ("subscription_30_days", 10001, "rejected")]
    monkeypatch.setenv("BOT_TOKEN", "123:TOKEN")
    monkeypatch.setattr(script.requests, "Session", lambda: api)
    assert script.main([]) == 0
    assert "Highest one-time amount accepted for invoice creation: 95808" in capsys.readouterr().out


def test_requires_a_bot_token(monkeypatch, capsys):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert script.main([]) == 2
