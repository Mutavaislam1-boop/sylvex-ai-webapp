"""Confirmed generation stages for the ThoughtLine progress UI.

The worker installs a reporter per job; provider code reports a stage only
when it really happened (request sent, provider task accepted, provider says
the task is running). The job endpoint returns those stages plus the row's
own received / ready / failed times. Nothing here may change a job's status,
result or billing.
"""
import asyncio
import os

import pytest

import main
import services.video_router as video_router
from services import generation_stages

DATABASE = os.getenv("SYLVEX_TEST_DATABASE_URL")


def collect():
    seen = []
    return seen, generation_stages.reporting(seen.append)


def drain():
    generation_stages._writer.submit(lambda: None).result(timeout=5)


def test_without_a_reporter_every_call_is_a_no_op():
    generation_stages.report("sent")
    generation_stages.report_provider_state("processing")


def test_each_stage_is_recorded_once_and_processing_implies_accepted():
    seen, scope = collect()
    with scope:
        generation_stages.report("sent")
        generation_stages.report("sent")
        generation_stages.report_provider_state("RUNNING")
        generation_stages.report_provider_state("processing")
        generation_stages.report("unknown")
    drain()
    assert seen == ["sent", "accepted", "processing"]


@pytest.mark.parametrize("state", ["queued", "submitted", "pending", "", None, "succeed", "waiting"])
def test_queued_or_unknown_provider_states_are_not_processing(state):
    seen, scope = collect()
    with scope:
        generation_stages.report_provider_state(state)
    drain()
    assert seen == []


def test_the_reporter_reaches_provider_threads_and_off_loop_coroutines():
    seen, scope = collect()

    async def provider():
        generation_stages.report("accepted")

    async def scenario():
        with scope:
            await asyncio.to_thread(generation_stages.report, "sent")
            await main.run_provider_coroutine_off_loop(provider)

    asyncio.run(scenario())
    drain()
    assert seen == ["sent", "accepted"]


def test_kling_poll_reports_processing_only_for_a_running_task(monkeypatch):
    class Response:
        status_code = 200

    for state, expected in (("submitted", []), ("processing", ["accepted", "processing"])):
        monkeypatch.setattr(video_router, "_request_get", lambda *a, **k: Response())
        monkeypatch.setattr(video_router, "_safe_provider_json_response", lambda *a, **k: {"code": 0, "data": {"task_status": state}})
        monkeypatch.setattr(video_router, "_kling_poll_attempt_settings", lambda *a: (1, 0))
        seen, scope = collect()
        with scope:
            video_router._kling_poll_until_ready("task-1", {})
        drain()
        assert seen == expected


def test_job_progress_lists_only_confirmed_stages_in_order():
    progress = main.prostudio_job_progress(
        "provider_processing", {"accepted": 12.5, "sent": 11.0, "junk": 1, "processing": "x"}, 10.0, None, 20.0,
    )
    assert list(progress["stages"].items()) == [("received", 10.0), ("sent", 11.0), ("accepted", 12.5)]
    assert progress["server_time"] == 20.0


def test_job_progress_marks_ready_only_for_a_completed_status():
    assert main.prostudio_job_progress("completed", {"sent": 11.0}, 10.0, 30.0, 31.0)["stages"] == {"received": 10.0, "sent": 11.0, "ready": 30.0}
    # A completed row whose result is still being held reads as processing.
    assert "ready" not in main.prostudio_job_progress("provider_processing", {}, 10.0, 30.0, 31.0)["stages"]
    assert main.prostudio_job_progress("failed", None, 10.0, 15.0, 16.0)["stages"] == {"received": 10.0, "failed": 15.0}
    assert main.prostudio_job_progress("queued", None, 10.0, None, 10.5)["stages"] == {"received": 10.0}


def test_the_worker_reports_sent_before_dispatch_and_accepted_with_the_task():
    source = open(main.__file__, encoding="utf-8").read()
    assert 'generation_stages.report("sent")\n            return await dispatch_prostudio_provider_request(' in source
    assert 'generation_stages.report("accepted")\n        update_prostudio_generation_job(job_id, "provider_processing", result=result)' in source
    assert "generation_stages.reporting(\n            lambda stage: record_prostudio_job_stage(job_id, stage)\n        )" in source


@pytest.fixture
def jobs_db(monkeypatch):
    if not DATABASE:
        pytest.skip("Set SYLVEX_TEST_DATABASE_URL to a disposable PostgreSQL database")
    import psycopg2

    def run(sql, params=None, fetch=False):
        conn = psycopg2.connect(DATABASE)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    run("DROP TABLE IF EXISTS prostudio_generation_jobs")
    run("CREATE TABLE prostudio_generation_jobs(id TEXT PRIMARY KEY, status TEXT, stage_json JSONB DEFAULT '{}'::jsonb)")
    run("INSERT INTO prostudio_generation_jobs(id, status) VALUES ('active', 'provider_processing'), ('done', 'completed')")
    monkeypatch.setattr(main, "DATABASE_URL", DATABASE)
    return run


def test_a_stage_is_written_once_and_never_on_a_finished_job(jobs_db):
    main.record_prostudio_job_stage("active", "sent")
    first = jobs_db("SELECT stage_json FROM prostudio_generation_jobs WHERE id='active'", fetch=True)[0][0]
    main.record_prostudio_job_stage("active", "sent")
    main.record_prostudio_job_stage("active", "accepted")
    main.record_prostudio_job_stage("active", "bogus")
    main.record_prostudio_job_stage("done", "sent")
    rows = dict(jobs_db("SELECT id, stage_json FROM prostudio_generation_jobs", fetch=True))
    assert set(rows["active"]) == {"sent", "accepted"}
    assert rows["active"]["sent"] == first["sent"]
    assert rows["done"] == {}
