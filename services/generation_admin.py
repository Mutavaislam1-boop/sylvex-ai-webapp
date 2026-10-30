"""What the Admin Console shows about one generation job: the stages it
really went through, where it failed, and a technical log without secrets.

Stages (Pro Studio jobs, every mode):

    received    the job row exists (SYLVEX accepted the request)
    checked     parameters and balance passed - a job row is only created
                after both checks, so this is confirmed by the row as well
    sent        the request went to the AI provider       (stage_json)
    accepted    the provider took it as a task             (stage_json)
    processing  the provider says the task is running      (stage_json)
    result      the provider returned the result           (stage_json)
    stored      the files were saved to R2                 (media outbox)
    ready       the result is available to the user       (completed_at)

A stage is "done" only when it was recorded, or when a later stage proves it
happened (a completed job was necessarily sent to its provider); such a
stage has no time of its own. A failed job is marked failed at the first
stage that never happened; later stages stay "pending", never "done".
"""
from __future__ import annotations

import re

STAGES = ("received", "checked", "sent", "accepted", "processing", "result", "stored", "ready")
PROVIDER_STAGES = ("sent", "accepted", "processing", "result")
FAILED = {"failed", "cancelled", "canceled", "timeout", "timed_out"}
ACTIVE = {"queued", "processing", "provider_processing"}
# Modes whose result is text: nothing is stored as a file.
TEXT_MODES = {"text", "chat", "pro", "lite"}

_SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|authorization|x-api-key|signature)"
                r"(\"?\s*[:=]\s*\"?)[^\s\"&,;]{4,}"), r"\1\2***"),
    (re.compile(r"(?i)([?&](?:token|key|sig|signature|media_sig|x-amz-signature|x-amz-credential|access_token|api_key)=)[^&\s\"]+"), r"\1***"),
    (re.compile(r"\b(?:sk|rk|pk)[-_](?:live|test|proj)?[-_]?[A-Za-z0-9]{12,}"), "***"),
    (re.compile(r"\b(?:xai|r8|hf|ghp|gho|glpat)[-_][A-Za-z0-9]{12,}"), "***"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"), "***"),
    (re.compile(r"\b[0-9]{6,12}:[A-Za-z0-9_-]{30,}"), "***"),  # Telegram bot token
]
_EXTERNAL_ID_KEYS = ("provider_task_id", "external_task_id", "task_id", "taskId", "request_id", "requestId",
                     "prediction_id", "operation_name", "operation_id", "generation_task_id", "provider_job_id")


def redact(value, limit=2000) -> str:
    """A technical text with keys, tokens, passwords and signed URL
    parameters masked."""
    text = str(value if value is not None else "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text[:limit]


def _epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value.timestamp())
    except AttributeError:
        return None


def _find_key(obj, keys, depth=0):
    if depth > 4:
        return ""
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()[:200]
        for value in obj.values():
            found = _find_key(value, keys, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj[:20]:
            found = _find_key(value, keys, depth + 1)
            if found:
                return found
    return ""


def storage_state(mode, status, result, outbox):
    """("done" | "failed" | "running" | "pending" | "not_needed", epoch, detail)."""
    outbox = outbox or {}
    if str(mode or "").lower() in TEXT_MODES:
        return "not_needed", None, ""
    if outbox.get("status") == "completed":
        return "done", _epoch(outbox.get("updated_at")), ""
    if outbox.get("status") == "failed":
        return "failed", _epoch(outbox.get("updated_at")), outbox.get("last_error") or ""
    if outbox.get("status") in ("pending", "processing"):
        return "running", None, outbox.get("last_error") or ""
    if (result or {}).get("storage_status") == "completed":
        return "done", None, ""
    if (result or {}).get("storage_status") == "failed":
        return "failed", None, ""
    return "pending", None, ""


def timeline(job, outbox=None):
    """[{key, state, at, seconds}] for one job row (dict with status, mode,
    stage_json, created_at, completed_at, result_json)."""
    status = str(job.get("status") or "").lower()
    recorded = job.get("stage_json") if isinstance(job.get("stage_json"), dict) else {}
    created = _epoch(job.get("created_at"))
    completed = _epoch(job.get("completed_at"))
    times = {"received": created, "checked": created}
    for stage in PROVIDER_STAGES:
        if isinstance(recorded.get(stage), (int, float)):
            times[stage] = float(recorded[stage])
    done = {stage for stage in times if times[stage] is not None}
    if status == "completed":
        times["ready"] = completed
        done |= {"received", "checked", "sent", "accepted", "processing", "result", "ready"}
    store_state, store_at, store_detail = storage_state(job.get("mode"), status, job.get("result_json"), outbox)
    if store_state == "done":
        done.add("stored")
        times["stored"] = store_at
    # Every stage before a confirmed one happened too.
    order = [s for s in STAGES if s != "stored"]
    confirmed = [order.index(s) for s in done if s in order]
    if confirmed:
        done |= set(order[:max(confirmed) + 1])
    failed_stage = ""
    if status in FAILED:
        failed_stage = next((s for s in order if s not in done), "ready")
    rows, previous = [], None
    for stage in STAGES:
        if stage == "stored":
            state = {"done": "done", "failed": "failed", "running": "running", "not_needed": "skipped"}.get(store_state, "pending")
            if status in FAILED:
                state = "pending"
        elif stage in done:
            state = "done"
        elif stage == failed_stage:
            state = "failed"
        elif status in ACTIVE and not any(s in done for s in order[order.index(stage):]):
            first_open = next((s for s in order if s not in done), "")
            state = "running" if stage == first_open else "pending"
        else:
            state = "pending"
        at = times.get(stage) if state == "done" else (completed if state == "failed" and stage != "stored" else times.get(stage))
        seconds = round(at - previous, 2) if at is not None and previous is not None and at >= previous else None
        if at is not None and state == "done" and stage != "stored":
            previous = at
        rows.append({"key": stage, "state": state, "at": at, "seconds": seconds,
                     "detail": redact(store_detail, 200) if stage == "stored" and store_detail else ""})
    return rows, failed_stage


def technical_log(job, outbox=None, failed_stage=""):
    """The fields the job card's "Technical log" shows - no secrets, no
    prompt (the prompt is shown separately to those allowed to see it)."""
    result = job.get("result_json") if isinstance(job.get("result_json"), dict) else {}
    error = job.get("error_json") if isinstance(job.get("error_json"), dict) else {}
    request = job.get("request_json") if isinstance(job.get("request_json"), dict) else {}
    response = job.get("response_json") if isinstance(job.get("response_json"), dict) else {}
    created, completed = _epoch(job.get("created_at")), _epoch(job.get("completed_at"))
    stages = [row for row in timeline(job, outbox)[0] if row["state"] == "done" and row["at"] is not None]
    current = next((row["key"] for row in reversed(timeline(job, outbox)[0]) if row["state"] in ("done", "running", "failed")), "")
    store_state, _, store_detail = storage_state(job.get("mode"), job.get("status"), result, outbox)
    return {
        "job_id": job.get("id"),
        "user_id": job.get("telegram_id"),
        "source": request.get("source") or request.get("client_source") or ("media_block" if request.get("media_block_id") else "pro_studio"),
        "platform": request.get("client_surface") or "",
        "mode": job.get("mode") or "",
        "model": job.get("model") or result.get("model") or "",
        "provider": job.get("provider") or result.get("provider") or error.get("provider") or "",
        "provider_model": result.get("provider_model") or "",
        "current_stage": failed_stage or current,
        "error_code": redact(error.get("error_code") or error.get("code") or (error.get("error") if re.fullmatch(r"[a-z0-9_.-]{2,80}", str(error.get("error") or "")) else ""), 120),
        "technical_message": redact(error.get("detail") or error.get("message") or error.get("error") or error.get("raw") or "", 1500),
        "external_task_id": redact(_find_key(result, _EXTERNAL_ID_KEYS) or _find_key(response, _EXTERNAL_ID_KEYS) or _find_key(error, _EXTERNAL_ID_KEYS), 200),
        "attempts": int(job.get("attempts") or 0),
        "duration_seconds": round(completed - created, 2) if created and completed and completed >= created else None,
        "stage_times": {row["key"]: row["at"] for row in stages},
        "storage": store_state,
        "storage_error": redact(store_detail, 200),
        "storage_attempts": int((outbox or {}).get("attempts") or 0),
    }
