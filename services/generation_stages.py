"""Confirmed stages of one Pro Studio generation job, for the progress UI.

The worker installs a reporter for the job it runs (``reporting``); provider
code anywhere below it, including provider pollers running in threads, calls
``report`` or ``report_provider_state`` when a stage really happened. Each
stage is recorded once, on a background thread, so reporting never blocks a
provider call or the worker loop. Without a reporter (bot, scripts, tests)
every call is a no-op.

Stages, in order: ``sent`` (the request went to the AI provider),
``accepted`` (the provider took it as a task), ``processing`` (the provider
says the task is running). ``received`` and the final outcome come from the
job row itself.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
import threading

STAGES = ("sent", "accepted", "processing")

# Raw provider task states that mean the model is working on the task, as
# opposed to waiting in the provider's queue. Lower-cased before matching.
RUNNING_STATES = frozenset({
    "processing", "running", "in_progress", "generating", "dreaming",
    "rendering", "streaming", "dubbing",
})

_reporter: ContextVar = ContextVar("sylvex_generation_stage_reporter", default=None)
_writer = ThreadPoolExecutor(max_workers=2, thread_name_prefix="generation-stage")


@contextmanager
def reporting(record):
    """Report stages of the current job through ``record(stage)``."""
    seen = set()
    lock = threading.Lock()

    def submit(stage):
        with lock:
            if stage in seen:
                return
            seen.add(stage)
        _writer.submit(record, stage)

    token = _reporter.set(submit)
    try:
        yield
    finally:
        _reporter.reset(token)


def report(stage: str) -> None:
    if stage not in STAGES:
        return
    submit = _reporter.get()
    if submit is None:
        return
    # A provider reporting the task as running has also accepted it.
    if stage == "processing":
        submit("accepted")
    submit(stage)


def report_provider_state(state) -> None:
    """Record ``processing`` when the provider's own task state says so."""
    if str(state or "").strip().lower() in RUNNING_STATES:
        report("processing")
