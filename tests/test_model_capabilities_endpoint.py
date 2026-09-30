"""GET /api/public/prostudio/model-capabilities - the new Phase 1 Batch 1
endpoint (see /root/.claude/plans/splendid-moseying-starlight.md). Exercises
the route function directly (same pattern as
tests/test_web_auth_config_endpoint.py - this sandbox's Python 3.11 can't run
main.py's own startup event) plus its public-route registration and
conditional-GET (If-None-Match/304) behavior.
"""
import asyncio

import main
from services.security import PUBLIC_GETS


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = _FakeHeaders({k.lower(): v for k, v in (headers or {}).items()})


def test_route_is_registered_as_public_get():
    assert "/api/public/prostudio/model-capabilities" in PUBLIC_GETS


def test_returns_ok_with_version_and_models():
    response = asyncio.run(main.public_prostudio_model_capabilities(_FakeRequest()))
    assert response.status_code == 200
    assert response.headers["etag"] == f'"{main.MODEL_CAPABILITIES_VERSION}"'
    import json
    body = json.loads(bytes(response.body))
    assert body["ok"] is True
    assert body["version"] == main.MODEL_CAPABILITIES_VERSION
    assert "kling_2_6" in body["models"]
    assert "nano_banana_pro" in body["models"]


def test_matching_if_none_match_returns_304_with_no_body():
    request = _FakeRequest({"If-None-Match": f'"{main.MODEL_CAPABILITIES_VERSION}"'})
    response = asyncio.run(main.public_prostudio_model_capabilities(request))
    assert response.status_code == 304
    assert bytes(response.body) == b""


def test_stale_if_none_match_returns_200_with_full_body():
    request = _FakeRequest({"If-None-Match": '"stale-version-value"'})
    response = asyncio.run(main.public_prostudio_model_capabilities(request))
    assert response.status_code == 200


def test_missing_if_none_match_returns_200():
    response = asyncio.run(main.public_prostudio_model_capabilities(_FakeRequest()))
    assert response.status_code == 200


def test_version_is_stable_across_repeated_calls():
    r1 = asyncio.run(main.public_prostudio_model_capabilities(_FakeRequest()))
    r2 = asyncio.run(main.public_prostudio_model_capabilities(_FakeRequest()))
    assert r1.headers["etag"] == r2.headers["etag"]
