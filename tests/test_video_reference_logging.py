"""Every rejected video-reference request leaves one structured
VIDEO_REFERENCE_REJECTED record (entry point, model, provider, duration,
size, container/MIME, dimensions, SYLVEX validation result, provider HTTP
status/code and a sanitized provider message), so the unexplained
"3-1000 seconds" rule is traceable next time it happens. No network."""
import asyncio
import json

import main
from services import video_probe


def _records(capsys):
    out = capsys.readouterr().out
    return [json.loads(line.split("VIDEO_REFERENCE_REJECTED: ", 1)[1]) for line in out.splitlines() if "VIDEO_REFERENCE_REJECTED: " in line]


FIELDS = {"entry_point", "model", "provider", "inputs", "duration", "bytes", "container", "mime", "width", "height",
          "sylvex_validation", "provider_http_status", "provider_error_code", "provider_error"}


def test_provider_rejection_record_is_complete_and_sanitized(monkeypatch, capsys):
    monkeypatch.setattr(main, "_reference_video_meta", lambda url: {"extension": ".mp4", "duration": 20, "width": 720, "height": 1280, "bytes": 9000})
    payload = {"model": "kling_o3_omni", "video_options": {"model": "kling_o3_omni", "input_video": "https://cdn.x/a.mp4"}}
    result = {"ok": False, "provider": "kling", "status_code": 400, "code": 1201,
              "raw_error": "Video duration must be 3-1000 seconds https://cdn.kling.ai/x?token=SECRETSECRETSECRETSECRETSECRETSECRETSECRET Bearer sk-abcdefghijklmnop"}
    main.log_video_reference_failure("prostudio_job", payload, result)
    (record,) = _records(capsys)
    assert set(record) == FIELDS
    assert record["provider_http_status"] == 400 and record["provider_error_code"] == "1201"
    assert record["duration"] == 20 and record["container"] == ".mp4" and record["width"] == 720
    assert "3-1000 seconds" in record["provider_error"]
    assert "https://" not in record["provider_error"] and "SECRET" not in record["provider_error"] and "sk-" not in record["provider_error"]


def test_requests_without_reference_inputs_are_not_logged(capsys):
    assert main.log_video_reference_failure("prostudio_job", {"video_options": {"model": "sora_2"}}, {"ok": False}) is None
    assert _records(capsys) == []


def test_sylvex_validation_rejection_is_logged_at_generate(monkeypatch, capsys):
    payload = {"mode": "video", "model": "sora_2", "video_options": {"model": "sora_2", "input_video": "https://cdn/v.mp4"}}
    error = main.validate_video_feature_request(payload)
    assert error
    main.log_video_reference_failure("prostudio_generate", payload, None, error["error"])
    (record,) = _records(capsys)
    assert record["entry_point"] == "prostudio_generate" and record["sylvex_validation"] == error["error"]
    assert record["inputs"]["video"] is True


def test_upload_rejection_of_a_video_is_logged(capsys):
    main._log_upload_media_rejected("unsupported_extension", "video", ".mkv", "video/x-matroska", 0, 400)
    (record,) = _records(capsys)
    assert record["entry_point"] == "upload_media" and record["sylvex_validation"] == "unsupported_extension"
    assert record["container"] == ".mkv" and record["mime"] == "video/x-matroska"


def test_generate_route_and_worker_call_the_logger():
    import inspect
    source = inspect.getsource(main)
    assert 'log_video_reference_failure, "prostudio_generate"' in source
    assert 'log_video_reference_failure, "prostudio_job"' in source
