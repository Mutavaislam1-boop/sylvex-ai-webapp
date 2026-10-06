# Regression tests for the security audit's JOB-1 finding: on any
# transient provider failure, run_with_provider_retry() (provider_resilience.py)
# simply re-invokes the whole dispatch - which, for most provider adapters,
# submits a brand-new request to the paid provider with no way for the
# provider to recognize it as a retry of the SAME job. SYLVEX's own job
# state/billing stays consistent either way (a single settle_generation
# call per job_id), but the provider itself can be billed/occupied twice
# for one user job.
#
# Fix: send a stable, job-identity-derived idempotency value on the two
# provider submission paths confirmed (via each provider's own official
# documentation - never guessed) to support client-supplied retry
# deduplication:
#   - OpenAI Sora (_call_sora): an `Idempotency-Key` header, following the
#     exact pattern _call_heygen_direct_video already established for
#     HeyGen's own confirmed-supported /v3/videos endpoint.
#   - PixVerse (_call_pixverse / _pixverse_headers): the `Ai-trace-id`
#     header PixVerse's own docs already require on every request - fixed
#     from a fresh random uuid4() on every call (which defeated the
#     provider's own documented dedup behavior on a retry) to the job's
#     stable identity, reused across retries of the same job.
#
# Every other provider adapter in services/video_router.py and
# services/audio_router.py was traced and left untouched: no official
# documentation confirming idempotency-key support was found for Kling,
# Runway (video or voice), Luma, Minimax, Veo, Gemini video, Lyria (Google
# music), Wan (DashScope explicitly documents the opposite - "you need
# your own idempotency"), Hedra, Seedance (BytePlus Ark), or ElevenLabs -
# adding a header those providers don't interpret would be a no-op at best
# and is explicitly out of scope per this fix's instructions.
import services.video_router as video_router


class _FakeJsonResponse:
    def __init__(self, status_code=200, text='{"video_id": "vid_123", "status": "processing"}'):
        self.status_code = status_code
        self.text = text


class _FakeFormResponse:
    status_code = 200
    text = '{"id": "video_123", "status": "queued"}'


# ---------------------------------------------------------------------------
# Sora (OpenAI): Idempotency-Key header.
# ---------------------------------------------------------------------------

def _call_sora_capturing_headers(monkeypatch, payload):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")
    monkeypatch.setattr(video_router, "_provider_model_for_video", lambda model_id: "sora-2")
    monkeypatch.setattr(video_router, "_public_input_url", lambda url: url)

    captured = {}

    def fake_request_form(url, headers, data, files=None):
        captured["headers"] = headers
        return _FakeFormResponse()

    monkeypatch.setattr(video_router, "_request_form", fake_request_form)
    video_router._call_sora("sora_2", "a cat waking up", payload)
    return captured["headers"]


def test_sora_same_job_id_reuses_the_same_idempotency_key_across_retries(monkeypatch):
    payload = {"job_id": "job-abc", "generation_id": "job-abc", "video_options": {}}
    headers_attempt_1 = _call_sora_capturing_headers(monkeypatch, payload)
    headers_attempt_2 = _call_sora_capturing_headers(monkeypatch, payload)

    assert headers_attempt_1["Idempotency-Key"] == "job-abc"
    assert headers_attempt_1["Idempotency-Key"] == headers_attempt_2["Idempotency-Key"], (
        "a retry of the same job must send the exact same Idempotency-Key, or OpenAI "
        "has no way to recognize it as a retry rather than a brand-new paid job"
    )


def test_sora_different_jobs_get_different_idempotency_keys(monkeypatch):
    headers_job_1 = _call_sora_capturing_headers(monkeypatch, {"job_id": "job-one", "video_options": {}})
    headers_job_2 = _call_sora_capturing_headers(monkeypatch, {"job_id": "job-two", "video_options": {}})

    assert headers_job_1["Idempotency-Key"] != headers_job_2["Idempotency-Key"], (
        "two unrelated jobs must never collide on the same idempotency key, or the second "
        "job's real submission would be silently deduplicated away as a 'retry' of the first"
    )


def test_sora_sends_no_idempotency_key_when_the_payload_has_no_job_identity(monkeypatch):
    headers = _call_sora_capturing_headers(monkeypatch, {"video_options": {}})
    assert "Idempotency-Key" not in headers


# ---------------------------------------------------------------------------
# PixVerse: Ai-trace-id header.
# ---------------------------------------------------------------------------

def _call_pixverse_capturing_headers(monkeypatch, payload):
    monkeypatch.setattr(video_router, "_get_env", lambda *names: "test-key")

    captured = {}

    def fake_request_json(url, headers, body):
        captured["headers"] = headers
        return _FakeJsonResponse()

    monkeypatch.setattr(video_router, "_request_json", fake_request_json)
    video_router._call_pixverse("pixverse_v6", "a cat waking up", payload)
    return captured["headers"]


def test_pixverse_same_job_id_reuses_the_same_trace_id_across_retries(monkeypatch):
    payload = {"job_id": "job-xyz", "generation_id": "job-xyz", "video_options": {}}
    headers_attempt_1 = _call_pixverse_capturing_headers(monkeypatch, payload)
    headers_attempt_2 = _call_pixverse_capturing_headers(monkeypatch, payload)

    assert headers_attempt_1["Ai-trace-id"] == "job-xyz"
    assert headers_attempt_1["Ai-trace-id"] == headers_attempt_2["Ai-trace-id"], (
        "PixVerse's own docs document Ai-trace-id as the request's dedup key - a retry "
        "that generates a fresh random one every time defeats that protection entirely "
        "and looks like a brand-new video to PixVerse"
    )


def test_pixverse_different_jobs_get_different_trace_ids(monkeypatch):
    headers_job_1 = _call_pixverse_capturing_headers(monkeypatch, {"job_id": "job-one", "video_options": {}})
    headers_job_2 = _call_pixverse_capturing_headers(monkeypatch, {"job_id": "job-two", "video_options": {}})

    assert headers_job_1["Ai-trace-id"] != headers_job_2["Ai-trace-id"], (
        "two unrelated jobs must never collide on the same Ai-trace-id - PixVerse's docs "
        "say reusing a trace id is the most common cause of a video stuck in 'Generating'"
    )


def test_pixverse_without_job_identity_falls_back_to_a_fresh_random_trace_id(monkeypatch):
    # Preserves the original behavior for any caller that has no job
    # identity to key off (e.g. an ad-hoc/test invocation): still get a
    # usable, distinct Ai-trace-id, never a reused hardcoded placeholder.
    headers_attempt_1 = _call_pixverse_capturing_headers(monkeypatch, {"video_options": {}})
    headers_attempt_2 = _call_pixverse_capturing_headers(monkeypatch, {"video_options": {}})

    assert headers_attempt_1["Ai-trace-id"]
    assert headers_attempt_1["Ai-trace-id"] != headers_attempt_2["Ai-trace-id"]


def test_pixverse_image_upload_and_poll_headers_are_unaffected(monkeypatch):
    # The fix only threads a job-derived trace id into the one call site
    # that actually submits a generation. _pixverse_headers()'s other
    # callers (image upload, status poll) must keep their original
    # fresh-uuid4()-per-call behavior untouched.
    first = video_router._pixverse_headers("test-key", content_type="")
    second = video_router._pixverse_headers("test-key", content_type="")
    assert first["Ai-trace-id"] != second["Ai-trace-id"]
