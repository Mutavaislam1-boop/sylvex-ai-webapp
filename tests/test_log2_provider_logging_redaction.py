# Regression tests for the security audit's LOG-2 finding:
# services/video_router.py's _log_provider_response() (used ~28 call sites)
# printed the full outbound request URL/payload and the full, unredacted
# inbound response headers. A signed SYLVEX media URL carries its HMAC
# signature in its query string (media_exp/media_sig - see
# services/media_access.py's sign_media_url()), so logging it verbatim is
# functionally equivalent to logging a working, unauthenticated bearer
# credential for up to MEDIA_URL_TTL_SECONDS (7 days by default); logging
# every response header verbatim risked echoing Set-Cookie, an
# Authorization echo, or a provider-specific session/secret header into
# application logs.
#
# Fix: _strip_url_query() drops the query string (and fragment) from any
# logged URL; _sanitize_debug_payload() applies it recursively to request/
# response payload dicts; _response_headers_dict() now copies through only
# an explicit allowlist of headers confirmed to carry no credential.
import services.video_router as video_router


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, text='{"ok": true}'):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


SIGNED_MEDIA_URL = (
    "https://sylvex.ai/api/public/storage/generated/references/preview/cat.png"
    "?media_exp=1999999999&media_sig=deadbeefcafef00d1234567890abcdef1234567890abcdef1234567890abcd"
)


def _printed_text(capsys):
    return capsys.readouterr().out


# ---------------------------------------------------------------------------
# _strip_url_query(): the core redaction primitive.
# ---------------------------------------------------------------------------

def test_strip_url_query_removes_signed_media_signature():
    stripped = video_router._strip_url_query(SIGNED_MEDIA_URL)
    assert "media_sig" not in stripped
    assert "media_exp" not in stripped
    assert stripped == "https://sylvex.ai/api/public/storage/generated/references/preview/cat.png"


def test_strip_url_query_handles_app_relative_signed_paths():
    relative = "/api/public/storage/generated/foo.png?media_exp=123&media_sig=abcdef"
    stripped = video_router._strip_url_query(relative)
    assert stripped == "/api/public/storage/generated/foo.png"


def test_strip_url_query_leaves_a_plain_url_unchanged():
    plain = "https://api.heygen.com/v3/videos"
    assert video_router._strip_url_query(plain) == plain


def test_strip_url_query_never_touches_ordinary_text():
    # A prompt that happens to contain '?' must never be mistaken for a URL.
    prompt = "a cat waking up? curious and stretching"
    assert video_router._strip_url_query(prompt) == prompt


def test_strip_url_query_ignores_non_string_values():
    assert video_router._strip_url_query(None) is None
    assert video_router._strip_url_query(42) == 42
    assert video_router._strip_url_query(["a", "b"]) == ["a", "b"]


# ---------------------------------------------------------------------------
# _sanitize_debug_payload(): recursive redaction of request/response bodies.
# ---------------------------------------------------------------------------

def test_sanitize_debug_payload_strips_signed_url_in_a_nested_field():
    payload = {"video_options": {"start_image": SIGNED_MEDIA_URL}, "prompt": "a cat"}
    sanitized = video_router._sanitize_debug_payload(payload)
    assert "media_sig" not in str(sanitized)
    assert sanitized["video_options"]["start_image"].endswith("cat.png")


def test_sanitize_debug_payload_strips_signed_urls_inside_a_list():
    payload = {"reference_images": [SIGNED_MEDIA_URL, "https://example.com/plain.png"]}
    sanitized = video_router._sanitize_debug_payload(payload)
    assert "media_sig" not in str(sanitized)
    assert sanitized["reference_images"][1] == "https://example.com/plain.png"


def test_sanitize_debug_payload_still_truncates_long_non_url_strings():
    payload = {"prompt": "x" * 500}
    sanitized = video_router._sanitize_debug_payload(payload)
    assert len(sanitized["prompt"]) < 500
    assert "500 chars" in sanitized["prompt"]


# ---------------------------------------------------------------------------
# _response_headers_dict(): explicit allowlist, not a blocklist.
# ---------------------------------------------------------------------------

def test_response_headers_dict_drops_sensitive_headers():
    response = _FakeResponse(headers={
        "Authorization": "Bearer sk-super-secret-token",
        "Set-Cookie": "session=abc123; HttpOnly",
        "Cookie": "session=abc123",
        "X-Api-Key": "sk-another-secret",
        "X-Heygen-Session-Token": "secret-session-token",
    })
    safe = video_router._response_headers_dict(response)
    assert safe == {}


def test_response_headers_dict_keeps_the_explicit_safe_allowlist():
    response = _FakeResponse(headers={
        "Content-Type": "application/json",
        "Content-Length": "128",
        "Retry-After": "5",
        "X-Request-Id": "req_abc123",
        "Authorization": "Bearer sk-super-secret-token",
    })
    safe = video_router._response_headers_dict(response)
    assert safe.get("Content-Type") == "application/json"
    assert safe.get("Content-Length") == "128"
    assert safe.get("Retry-After") == "5"
    assert safe.get("X-Request-Id") == "req_abc123"
    assert "Authorization" not in safe


def test_response_headers_dict_is_case_insensitive_for_the_allowlist():
    response = _FakeResponse(headers={"CONTENT-TYPE": "text/plain", "AUTHORIZATION": "Bearer secret"})
    safe = video_router._response_headers_dict(response)
    assert safe.get("CONTENT-TYPE") == "text/plain"
    assert "AUTHORIZATION" not in safe


# ---------------------------------------------------------------------------
# _log_provider_response(): the end-to-end integration the audit named.
# ---------------------------------------------------------------------------

def test_log_provider_response_redacts_signed_url_in_request_url(capsys):
    response = _FakeResponse()
    video_router._log_provider_response("sylvex-router", "SUBMIT", SIGNED_MEDIA_URL, {}, response, {"ok": True})
    out = _printed_text(capsys)
    assert "media_sig" not in out
    assert "media_exp" not in out


def test_log_provider_response_redacts_signed_url_in_request_payload(capsys):
    response = _FakeResponse()
    payload = {"video_options": {"start_image": SIGNED_MEDIA_URL}}
    video_router._log_provider_response("heygen", "CREATE_VIDEO", "https://api.heygen.com/v3/videos", payload, response, {})
    out = _printed_text(capsys)
    assert "media_sig" not in out


def test_log_provider_response_redacts_signed_url_in_json_response_body(capsys):
    response = _FakeResponse()
    data = {"echoed_input": {"start_image": SIGNED_MEDIA_URL}, "video_id": "vid_123"}
    video_router._log_provider_response("runway", "CREATE_TASK", "https://api.dev.runwayml.com/v1/image_to_video", {}, response, data)
    out = _printed_text(capsys)
    assert "media_sig" not in out
    assert "vid_123" in out  # non-sensitive data is still logged


def test_log_provider_response_omits_sensitive_headers_but_keeps_safe_ones(capsys):
    response = _FakeResponse(headers={
        "Authorization": "Bearer sk-super-secret-token",
        "Set-Cookie": "session=abc123; HttpOnly",
        "X-Api-Key": "sk-provider-secret",
        "Content-Type": "application/json",
        "X-Request-Id": "req_xyz789",
        "Retry-After": "10",
    })
    video_router._log_provider_response("kling", "SUBMIT", "https://api-singapore.klingai.com/v1/videos", {}, response, {})
    out = _printed_text(capsys)
    assert "sk-super-secret-token" not in out
    assert "abc123" not in out
    assert "sk-provider-secret" not in out
    assert "application/json" in out
    assert "req_xyz789" in out
    assert "10" in out  # Retry-After


def test_log_provider_response_still_reports_provider_status_and_body_preview(capsys):
    # Preserves the useful, non-sensitive debugging information the audit
    # explicitly asked to keep: provider name, status code, response body.
    response = _FakeResponse(status_code=502, text='{"error": "upstream failure"}')
    video_router._log_provider_response("minimax", "POLL", "https://api.minimax.io/v1/query/video_generation", {"task_id": "t1"}, response, {"ok": False})
    out = _printed_text(capsys)
    assert "MINIMAX POLL RESPONSE DEBUG" in out
    assert "502" in out
    assert "upstream failure" in out
    assert "t1" in out
