"""Controlled PostgreSQL load test for the SYLVEX Pro Studio worker pool.

Run only against a worker configured with PROSTUDIO_MOCK_GENERATION=1:

    LOAD_TEST_ENABLED=1 PROSTUDIO_MOCK_GENERATION=1 \
    TEST_WORKERS=5 TEST_WORKER_CONCURRENCY=3 python stress_test.py

The script has no HTTP endpoint and never calls an AI provider or Telegram.
"""

import concurrent.futures
import json
import os
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Dict, Iterable, List
from uuid import uuid4

from dotenv import load_dotenv
from psycopg2.extras import Json
from db_pool import close_db_pool, db_connect, start_db_pool


load_dotenv()

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"processing", "provider_processing"}
POLL_INTERVAL_SECONDS = 0.25
TEST_TIMEOUT_SECONDS = 600


def enabled(name: str) -> bool:
    return str(os.getenv(name, "0")).strip().lower() in {"1", "true", "yes", "on"}


def bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def test_user_count() -> int:
    return bounded_env_int("TEST_USERS", 15, 1, 1000)


def test_worker_count() -> int:
    return bounded_env_int("TEST_WORKERS", 5, 1, 100)


def test_worker_concurrency() -> int:
    return bounded_env_int("TEST_WORKER_CONCURRENCY", 3, 1, 20)


def database_url() -> str:
    return str(os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()


def ensure_safe_to_run() -> None:
    if not enabled("LOAD_TEST_ENABLED"):
        raise RuntimeError("Load test is disabled. Set LOAD_TEST_ENABLED=1 explicitly.")
    if not enabled("PROSTUDIO_MOCK_GENERATION"):
        raise RuntimeError(
            "Refusing to enqueue jobs without PROSTUDIO_MOCK_GENERATION=1. "
            "The sylvex-worker service must use the same setting."
        )
    if not database_url():
        raise RuntimeError("DATABASE_URL or DATABASE_PUBLIC_URL is required.")


def table_exists() -> bool:
    with db_connect(database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.prostudio_generation_jobs')")
            row = cursor.fetchone()
            return bool(row and row[0])


def build_test_jobs(count: int) -> List[dict]:
    # Telegram IDs are positive in production. Negative, run-scoped IDs cannot
    # belong to real Telegram users and remain unique between parallel runs.
    run_component = int(time.time_ns() % 1_000_000_000_000)
    base_telegram_id = -(8_000_000_000_000_000 + run_component * 1000)
    jobs = []
    for index in range(count):
        job_id = "loadtest-" + uuid4().hex
        telegram_id = base_telegram_id - index - 1
        payload = {
            "telegram_id": telegram_id,
            "mode": "image",
            "category": "image",
            "model": "mock-load-test",
            "provider": "mock",
            "prompt": "SYLVEX controlled Pro Studio load test",
            "conversation_id": "",
            "load_test": True,
            "mock": True,
            "load_test_job_id": job_id,
        }
        jobs.append({"id": job_id, "telegram_id": telegram_id, "payload": payload})
    return jobs


def insert_job(job: dict, start_gate: threading.Event) -> str:
    start_gate.wait()
    with db_connect(database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO prostudio_generation_jobs (
                    id, telegram_id, conversation_id, mode, model, provider,
                    prompt, status, request_json
                ) VALUES (%s, %s, NULL, 'image', 'mock-load-test', 'mock', %s, 'queued', %s)
                """,
                (
                    job["id"],
                    job["telegram_id"],
                    "SYLVEX controlled Pro Studio load test",
                    Json(job["payload"]),
                ),
            )
    return str(job["id"])


def enqueue_jobs_concurrently(jobs: List[dict]) -> List[str]:
    start_gate = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(jobs), 32)) as executor:
        futures = [executor.submit(insert_job, job, start_gate) for job in jobs]
        start_gate.set()
        return [future.result() for future in futures]


def fetch_jobs(job_ids: Iterable[str]) -> List[dict]:
    ids = list(job_ids)
    with db_connect(database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, telegram_id, status, attempts, created_at, locked_at, completed_at,
                       provider, COALESCE(result_json, '{}'::jsonb), COALESCE(error_json, '{}'::jsonb)
                FROM prostudio_generation_jobs
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "telegram_id": int(row[1] or 0),
            "status": str(row[2] or ""),
            "attempts": int(row[3] or 0),
            "created_at": row[4],
            "locked_at": row[5],
            "completed_at": row[6],
            "provider": str(row[7] or ""),
            "result": row[8] if isinstance(row[8], dict) else {},
            "error": row[9] if isinstance(row[9], dict) else {},
        }
        for row in rows
    ]


def seconds_between(start: datetime, end: datetime):
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def average(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(sum(clean) / len(clean), 3) if clean else 0.0


def wait_for_terminal_statuses(job_ids: List[str]) -> tuple:
    started = time.monotonic()
    deadline = started + TEST_TIMEOUT_SECONDS
    max_processing = 0
    rows = []
    while time.monotonic() < deadline:
        rows = fetch_jobs(job_ids)
        processing = sum(1 for row in rows if row["status"] in ACTIVE_STATUSES)
        max_processing = max(max_processing, processing)
        if len(rows) == len(job_ids) and all(row["status"] in TERMINAL_STATUSES for row in rows):
            return rows, max_processing, time.monotonic() - started
        time.sleep(POLL_INTERVAL_SECONDS)
    statuses = Counter(row["status"] for row in rows)
    raise TimeoutError(
        "Load test timed out after {} seconds; statuses={}".format(
            TEST_TIMEOUT_SECONDS,
            dict(statuses),
        )
    )


def build_summary(
    job_ids: List[str],
    rows: List[dict],
    max_processing: int,
    duration: float,
    workers: int = 5,
    worker_concurrency: int = 3,
) -> Dict[str, object]:
    id_counts = Counter(job_ids)
    duplicate_ids = {job_id for job_id, count in id_counts.items() if count > 1}
    duplicate_ids.update(row["id"] for row in rows if row["attempts"] > 1)
    queue_times = [seconds_between(row["created_at"], row["locked_at"]) for row in rows]
    processing_times = [seconds_between(row["locked_at"], row["completed_at"]) for row in rows]
    return {
        "total": len(rows),
        "completed": sum(1 for row in rows if row["status"] == "completed"),
        "failed": sum(1 for row in rows if row["status"] in {"failed", "cancelled"}),
        "max_processing": max_processing,
        "test_workers": workers,
        "test_worker_concurrency": worker_concurrency,
        "expected_capacity": workers * worker_concurrency,
        "total_duration": round(duration, 3),
        "duplicate_job_ids": sorted(duplicate_ids),
        "average_queue_time": average(queue_times),
        "average_processing_time": average(processing_times),
    }


def error_value(payload: dict, *keys: str):
    source = payload if isinstance(payload, dict) else {}
    for key in keys:
        value = source.get(key)
        if value not in (None, "", {}, []):
            return value
    return ""


def failed_job_details(rows: List[dict]) -> List[dict]:
    details = []
    for row in rows:
        if row["status"] not in {"failed", "cancelled"}:
            continue
        error = row.get("error") or {}
        result = row.get("result") or {}
        provider = error_value(error, "provider") or error_value(result, "provider") or row.get("provider") or ""
        worker_provider_error = (
            error_value(error, "provider_error", "raw_error", "details", "detail", "traceback")
            or error_value(result, "provider_error", "raw_error", "error", "message")
            or error_value(error, "error", "message")
            or ""
        )
        details.append({
            "job_id": row["id"],
            "telegram_id": row.get("telegram_id", 0),
            "status": row["status"],
            "error": error_value(error, "error", "message", "detail") or error or "unknown error",
            "worker/provider error": {
                "provider": provider,
                "error": worker_provider_error,
                "attempts": row.get("attempts", 0),
                "error_payload": error,
            },
        })
    return details


def validate_mock_results(rows: List[dict]) -> List[str]:
    return [
        row["id"]
        for row in rows
        if row["status"] == "completed" and not bool((row.get("result") or {}).get("mock"))
    ]


def main() -> int:
    ensure_safe_to_run()
    start_db_pool(database_url())
    try:
        if not table_exists():
            raise RuntimeError("Table prostudio_generation_jobs does not exist. Deploy the application first.")

        count = test_user_count()
        workers = test_worker_count()
        worker_concurrency = test_worker_concurrency()
        expected_capacity = workers * worker_concurrency
        jobs = build_test_jobs(count)
        test_started = time.monotonic()
        job_ids = enqueue_jobs_concurrently(jobs)
        rows, max_processing, _ = wait_for_terminal_statuses(job_ids)
        summary = build_summary(
            job_ids, rows, max_processing, time.monotonic() - test_started,
            workers, worker_concurrency,
        )
        non_mock_results = validate_mock_results(rows)
        failures = failed_job_details(rows)

        print("STRESS_TEST_RESULT")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False))
        for failure in failures:
            print("FAILED_JOB")
            print(json.dumps(failure, ensure_ascii=False, indent=2, default=str))

        errors = []
        if summary["total"] != count:
            errors.append("not all jobs were returned")
        if summary["completed"] != count:
            errors.append("not all jobs completed")
        if summary["duplicate_job_ids"]:
            errors.append("duplicate processing was detected")
        if non_mock_results:
            errors.append("completed jobs without mock=true: {}".format(non_mock_results))
        minimum_parallelism = 1 if count == 1 else 2
        if summary["max_processing"] < minimum_parallelism:
            errors.append(
                "parallel processing was not confirmed: max_processing={}, expected_capacity={}".format(
                    summary["max_processing"], expected_capacity,
                )
            )
        if errors:
            print("STRESS_TEST_FAILED: " + "; ".join(errors), file=sys.stderr)
            return 1
        print("STRESS_TEST_PASSED")
        return 0
    finally:
        close_db_pool()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STRESS_TEST_ERROR: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)
