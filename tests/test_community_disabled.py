"""Retired Mini App community: no database, network, purchases or deletions."""
import ast
import os
from pathlib import Path
import re
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import main


PREFIX = "/api/public/community"
METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
LEGACY_CASES = sorted({
    (method, re.sub(r"\{[^}]+\}", "7", route.path))
    for route in main.app.routes
    if getattr(route, "path", "").startswith(PREFIX + "/")
    and "legacy_path" not in route.path
    for method in route.methods
})


@pytest.fixture
def client():
    # The router proves that every old HTTP handler is unreachable, even
    # for a caller already admitted by the unchanged security middleware.
    with patch.object(main, "db_connect", side_effect=AssertionError("Database must not be called")), \
         patch.object(main, "ensure_community_tables", side_effect=AssertionError("Legacy handler called")):
        admitted_app = FastAPI()
        admitted_app.router.routes = list(main.app.routes)
        yield TestClient(admitted_app)


@pytest.mark.parametrize("method,path", LEGACY_CASES)
def test_old_community_handlers_cannot_run(client, method, path):
    response = client.request(method, path, json={"body": "synthetic", "telegram_id": 123})
    assert response.status_code == 410
    assert response.json() == {"ok": False, "error": "community_unavailable"}


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("path", [PREFIX, PREFIX + "/", PREFIX + "/old-client/unknown"])
def test_retired_namespace_is_closed(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 410
    if method != "HEAD":
        assert response.json()["error"] == "community_unavailable"


def test_similarly_named_noncommunity_path_is_not_intercepted(client):
    assert client.get(PREFIX + "-other").status_code == 404


def test_other_public_routes_and_static_scripts_remain_available(client):
    assert client.get("/health/live").status_code == 200
    for path in ("/webapp/", "/webapp/cabinet.html", "/js/ui.js", "/js/user.js", "/js/cabinet.js"):
        assert client.get(path).status_code == 200


def test_complete_app_keeps_unauthenticated_requests_rejected_before_database():
    with patch.object(main, "db_connect", side_effect=AssertionError("Database must not be called")):
        response = TestClient(main.app).get(PREFIX + "/feed")
    assert response.status_code == 401


def test_only_backend_change_is_terminal_community_route():
    reference = os.getenv("COMMUNITY_BASE_SOURCE")
    if not reference:
        pytest.skip("Pass exact prior source for source-preservation check")
    old = ast.parse((Path(reference) / "main.py").read_text())
    new = ast.parse(Path(main.__file__).read_text())
    added = [node for node in new.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "community_unavailable"]
    assert len(added) == 1
    new.body.remove(added[0])
    assert ast.dump(new, include_attributes=False) == ast.dump(old, include_attributes=False)
    assert LEGACY_CASES  # Real registered handlers, rather than invented routes.
