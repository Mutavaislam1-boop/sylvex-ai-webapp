"""B11: the external uptime check (tools/ops_uptime_check.py), no network."""
import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ops_uptime_check as up  # noqa: E402

URL = "https://api.sylvex.ai/health/ready"
H = 3600


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(*outcomes):
    calls = list(outcomes)

    def opener(request, timeout):
        outcome = calls.pop(0) if len(calls) > 1 else calls[0]
        if isinstance(outcome, Exception):
            raise outcome
        return Response(*outcome)
    return opener


def test_probe_needs_200_and_ok_true():
    nap = lambda s: None  # noqa: E731
    assert up.probe(URL, opener_for((200, b'{"ok": true}')), nap) == (True, "ok")
    assert up.probe(URL, opener_for((200, b'{"ok": false}')), nap) == (False, "http_200")
    assert up.probe(URL, opener_for(urllib.error.HTTPError(URL, 503, "x", {}, None)), nap) == (False, "http_503")
    assert up.probe(URL, opener_for(TimeoutError()), nap) == (False, "TimeoutError")
    assert up.probe(URL, opener_for(TimeoutError(), (200, b'{"ok": true}')), nap) == (True, "ok")  # 2nd try


def scenario(results, send_ok=True):
    state, sent, codes = {}, [], []

    def send(text):
        sent.append(text)
        return (True, None) if send_ok else (False, "http_502")
    t = 0
    for ok in results:
        t += 300
        state, delivered = up.run(state, [URL], send, t, probe_fn=lambda u, ok=ok: (ok, "ok" if ok else "http_503"))
        codes.append(delivered)
    return state, sent, codes


def test_one_blip_is_silent_two_failures_alert_once_then_recover():
    state, sent, codes = scenario([True, False, True, False, False, False, False, True])
    assert len(sent) == 2 and all(codes)
    assert sent[0].startswith("🔴 SYLVEX P0: API недоступен") and "http_503" in sent[0]
    assert sent[1].startswith("✅ SYLVEX: API снова доступен") and "Недоступен был: 20 мин." in sent[1]
    assert state["sites"][URL]["state"] == "up"
    assert [d["event"] for d in state["_deliveries"]] == ["fire", "resolve"]


def test_reminder_every_six_hours_while_down():
    state, sent, _ = scenario([False, False])
    up.run(state, [URL], lambda t: sent.append(t) or (True, None), 600 + 6 * H, probe_fn=lambda u: (False, "http_503"))
    assert sent[-1].startswith("⏰ SYLVEX P0: API всё ещё недоступен")
    up.run(state, [URL], lambda t: sent.append(t) or (True, None), 900 + 6 * H, probe_fn=lambda u: (False, "http_503"))
    assert len(sent) == 2


def test_failed_delivery_is_retried_and_fails_the_run():
    state, sent, codes = scenario([False, False, False], send_ok=False)
    assert codes == [True, False, False]          # exit 1 -> GitHub's own e-mail as a fallback
    assert [d["ok"] for d in state["_deliveries"]] == [False, False]
    assert state["sites"][URL]["pending"] == "fire"
    up.run(state, [URL], lambda t: sent.append(t) or (True, None), 1200, probe_fn=lambda u: (False, "http_503"))
    assert state["sites"][URL]["pending"] is None and state["_deliveries"][-1]["ok"] is True


def test_test_mode_sends_one_message():
    sent = []
    state, delivered = up.run({}, [URL], lambda t: sent.append(t) or (True, None), 1, mode="test")
    assert delivered and len(sent) == 1 and sent[0].startswith("🧪 SYLVEX")


def test_the_bot_token_never_reaches_the_output(capsys):
    token = "123456:SECRET-TOKEN-VALUE"

    def opener(request, timeout):
        raise urllib.error.URLError(f"failed for {request.full_url}")
    send = up.telegram_sender(token, "42", opener)
    state, delivered = up.run({}, [URL], send, 1, mode="test")
    out = capsys.readouterr().out + json.dumps(state)
    assert not delivered and token not in out and "SECRET" not in out
    assert state["_deliveries"][0]["error"] == "URLError"


def test_not_configured_is_reported_not_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPS_UPTIME_STATE", str(tmp_path / "s.json"))
    monkeypatch.delenv("OPS_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(up, "probe", lambda url: (True, "ok"))
    assert up.main(["--mode", "check"]) == 0
    assert up.main(["--mode", "test"]) == 1
    saved = json.loads((tmp_path / "s.json").read_text())
    assert saved["_deliveries"][-1]["error"] == "not_configured"
