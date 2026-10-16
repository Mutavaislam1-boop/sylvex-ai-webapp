"""Quick Access video editor: engine settings come from the server, the
IMG.LY licence stays in the environment and only signed-in users get it."""
import asyncio
import json
from types import SimpleNamespace

import main


class FakeRequest:
    def __init__(self, telegram_id):
        self.state = SimpleNamespace(telegram_id=telegram_id)


def _call(telegram_id):
    response = asyncio.run(main.public_video_editor_config(FakeRequest(telegram_id)))
    return response.status_code, json.loads(response.body), response.headers


def test_requires_a_signed_in_user():
    status, body, _ = _call(0)
    assert status == 401 and body == {"ok": False, "error": "login_required"}


def test_trial_mode_without_a_licence(monkeypatch):
    monkeypatch.delenv("IMGLY_LICENSE_KEY", raising=False)
    monkeypatch.delenv("IMGLY_ENGINE_MODULE_URL", raising=False)
    monkeypatch.delenv("IMGLY_ENGINE_BASE_URL", raising=False)
    status, body, headers = _call(42)
    version = main.IMGLY_ENGINE_VERSION
    assert status == 200 and headers["cache-control"] == "no-store"
    assert body == {
        "ok": True,
        "engine": "imgly",
        "version": version,
        "moduleUrl": f"https://cdn.img.ly/packages/imgly/cesdk-engine/{version}/index.js",
        "baseURL": f"https://cdn.img.ly/packages/imgly/cesdk-engine/{version}/assets",
        "license": "",
        "trial": True,
        "userId": "sylvex-42",
    }


def test_licence_and_hosts_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("IMGLY_LICENSE_KEY", " test-licence ")
    monkeypatch.setenv("IMGLY_ENGINE_MODULE_URL", "https://assets.example/engine/index.js")
    monkeypatch.setenv("IMGLY_ENGINE_BASE_URL", "https://assets.example/engine/assets")
    status, body, _ = _call(7)
    assert status == 200
    assert body["license"] == "test-licence" and body["trial"] is False
    assert body["moduleUrl"] == "https://assets.example/engine/index.js"
    assert body["baseURL"] == "https://assets.example/engine/assets"


def test_no_licence_value_is_hard_coded_in_the_frontend():
    import re
    from pathlib import Path
    root = Path(__file__).parent.parent / "webapp" / "js" / "video-editor"
    files = list(root.rglob("*.js"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"licen[sc]e\s*[:=]\s*['\"`][^'\"`]", text, re.I), path
