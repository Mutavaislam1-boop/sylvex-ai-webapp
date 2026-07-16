# =====================================================
# АВТОДОКУМЕНТАЦИЯ SYLVEX: tests/check_audio_api.py
# Этот файл подписан русскими пояснениями для быстрой навигации по проекту.
# Комментарии описывают назначение блоков и не меняют работу приложения.
# =====================================================
#!/usr/bin/env python3
"""
Temporary Audio API smoke test.

This script is intentionally standalone: it does not import or change the app
backend. It reads .env, checks credits/models/endpoints when available, submits a
short music generation request, polls task status, and prints full JSON results.

Useful env overrides:
  AUDIO_API_BASE_URL=https://...
  AUDIO_API_AUTH_HEADER=Authorization
  AUDIO_API_AUTH_SCHEME=Bearer
  AUDIO_API_GENERATE_PATH=/...
  AUDIO_API_POLL_PATH=/tasks/{task_id}
  AUDIO_API_MODEL=...
  AUDIO_API_GENERATE_PAYLOAD_JSON='{"prompt":"..."}'
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


# =====================================================
# PYTHON-БЛОК: load_dotenv
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# =====================================================
# PYTHON-БЛОК: pretty
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def pretty(title: str, data: Any) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


# =====================================================
# PYTHON-БЛОК: safe_json
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def safe_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return {
            "ok": False,
            "error": "Non-JSON response",
            "body": text,
        }


# =====================================================
# PYTHON-БЛОК: normalize_base_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


# =====================================================
# PYTHON-БЛОК: join_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def join_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return base_url.rstrip("/") + path


# =====================================================
# PYTHON-БЛОК: auth_headers
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def auth_headers(api_key: str) -> dict[str, str]:
    header = os.getenv("AUDIO_API_AUTH_HEADER", "Authorization")
    scheme = os.getenv("AUDIO_API_AUTH_SCHEME", "Bearer")
    value = api_key if not scheme else f"{scheme} {api_key}"
    return {
        header: value,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# =====================================================
# PYTHON-БЛОК: request_json
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers=auth_headers(api_key),
        method=method.upper(),
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            parsed = safe_json(raw)
            return {
                "ok": 200 <= res.status < 300,
                "method": method.upper(),
                "url": url,
                "status_code": res.status,
                "headers": dict(res.headers.items()),
                "elapsed_sec": round(time.time() - started, 3),
                "json": parsed,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "method": method.upper(),
            "url": url,
            "status_code": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "elapsed_sec": round(time.time() - started, 3),
            "json": safe_json(raw),
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": method.upper(),
            "url": url,
            "status_code": None,
            "elapsed_sec": round(time.time() - started, 3),
            "error": repr(exc),
        }


# =====================================================
# PYTHON-БЛОК: first_ok
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def first_ok(
    title: str,
    base_url: str,
    api_key: str,
    candidates: list[str],
) -> dict[str, Any] | None:
    last = None
    for path in candidates:
        result = request_json("GET", join_url(base_url, path), api_key)
        pretty(f"{title}: {path}", result)
        last = result
        if result.get("ok"):
            return result
    return last


# =====================================================
# ФОНОВАЯ ЗАДАЧА: pick_task_id
# Обрабатывает job после нажатия пользователем кнопки генерации: запускает провайдера, ждёт результат и сохраняет итог.
# =====================================================
def pick_task_id(data: Any) -> str:
    keys = ("task_id", "taskId", "id", "generation_id", "generationId", "job_id", "jobId")
    queue = [data]
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value:
                    return str(value)
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return ""


# =====================================================
# PYTHON-БЛОК: pick_result_url
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def pick_result_url(data: Any) -> str:
    keys = (
        "result_url",
        "audio_url",
        "music_url",
        "url",
        "download_url",
        "output_url",
    )
    queue = [data]
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return ""


# =====================================================
# PYTHON-БЛОК: pick_status
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def pick_status(data: Any) -> str:
    keys = ("status", "state", "task_status", "generation_status")
    queue = [data]
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value:
                    return str(value).lower()
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return ""


# =====================================================
# PYTHON-БЛОК: default_payload
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def default_payload() -> dict[str, Any]:
    raw = os.getenv("AUDIO_API_GENERATE_PAYLOAD_JSON", "").strip()
    if raw:
        return json.loads(raw)

    model = os.getenv("AUDIO_API_MODEL", "musicgen")
    prompt = os.getenv(
        "AUDIO_API_TEST_PROMPT",
        "Short upbeat electronic intro, clean mix, 10 seconds.",
    )
    duration = int(os.getenv("AUDIO_API_TEST_DURATION", "10"))
    return {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "instrumental": True,
    }


# =====================================================
# PYTHON-БЛОК: main
# Выполняет отдельный шаг backend-логики SYLVEX.
# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App.
# =====================================================
def main() -> int:
    load_dotenv(ROOT / ".env")

    api_key = os.getenv("AUDIO_API_KEY", "").strip()
    if not api_key:
        print("AUDIO_API_KEY is not configured", file=sys.stderr)
        return 2

    base_url = normalize_base_url(
        os.getenv("AUDIO_API_BASE_URL", "https://api.audioapi.ai/v1").strip()
    )
    print("Audio API test")
    print("base_url:", base_url)
    print("api_key_configured:", bool(api_key))

    balance_paths = [
        os.getenv("AUDIO_API_BALANCE_PATH", "").strip(),
        "/balance",
        "/credits",
        "/user/credits",
        "/account/balance",
        "/account/credits",
    ]
    model_paths = [
        os.getenv("AUDIO_API_MODELS_PATH", "").strip(),
        "/models",
        "/audio/models",
        "/music/models",
    ]
    endpoint_paths = [
        os.getenv("AUDIO_API_ENDPOINTS_PATH", "").strip(),
        "/endpoints",
        "/health",
        "/",
    ]

    balance_paths = [path for path in balance_paths if path]
    model_paths = [path for path in model_paths if path]
    endpoint_paths = [path for path in endpoint_paths if path]

    first_ok("BALANCE/CREDITS CHECK", base_url, api_key, balance_paths)
    first_ok("MODELS CHECK", base_url, api_key, model_paths)
    first_ok("ENDPOINTS CHECK", base_url, api_key, endpoint_paths)

    payload = default_payload()
    generate_candidates = [
        os.getenv("AUDIO_API_GENERATE_PATH", "").strip(),
        "/music/generate",
        "/music/generations",
        "/audio/generations",
        "/generations",
    ]
    generate_candidates = [path for path in generate_candidates if path]

    submit_result = None
    for path in generate_candidates:
        url = join_url(base_url, path)
        pretty("GENERATE REQUEST PAYLOAD " + path, payload)
        submit_result = request_json("POST", url, api_key, payload, timeout=120)
        pretty("GENERATE RESPONSE " + path, submit_result)
        if submit_result.get("ok"):
            break

    if not submit_result:
        print("No generate endpoint candidates were configured", file=sys.stderr)
        return 3

    submit_json = submit_result.get("json")
    task_id = pick_task_id(submit_json)
    result_url = pick_result_url(submit_json)
    pretty("TASK SUMMARY AFTER SUBMIT", {
        "task_id": task_id,
        "status": pick_status(submit_json),
        "result_url": result_url,
    })

    if result_url:
        return 0

    if not task_id:
        print("No task_id found in generation response", file=sys.stderr)
        return 4

    poll_template = os.getenv("AUDIO_API_POLL_PATH", "").strip()
    poll_candidates = [
        poll_template.format(task_id=urllib.parse.quote(task_id)) if poll_template else "",
        f"/tasks/{urllib.parse.quote(task_id)}",
        f"/music/tasks/{urllib.parse.quote(task_id)}",
        f"/generations/{urllib.parse.quote(task_id)}",
        f"/music/generations/{urllib.parse.quote(task_id)}",
    ]
    poll_candidates = [path for path in poll_candidates if path]
    max_attempts = int(os.getenv("AUDIO_API_POLL_ATTEMPTS", "20"))
    sleep_sec = float(os.getenv("AUDIO_API_POLL_SLEEP_SEC", "5"))

    last_poll = None
    for attempt in range(1, max_attempts + 1):
        for path in poll_candidates:
            last_poll = request_json("GET", join_url(base_url, path), api_key)
            status = pick_status(last_poll.get("json"))
            result_url = pick_result_url(last_poll.get("json"))
            pretty(f"POLL RESPONSE attempt={attempt} path={path}", {
                "response": last_poll,
                "task_id": task_id,
                "status": status,
                "result_url": result_url,
            })

            if last_poll.get("ok") and result_url:
                pretty("FINAL RESULT", {
                    "task_id": task_id,
                    "status": status or "completed",
                    "result_url": result_url,
                    "full_response": last_poll.get("json"),
                })
                return 0

            if last_poll.get("ok"):
                break

        if attempt < max_attempts:
            time.sleep(sleep_sec)

    pretty("FINAL RESULT NOT READY", {
        "task_id": task_id,
        "last_poll": last_poll,
    })
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
