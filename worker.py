"""Standalone background worker for SYLVEX Pro Studio.

This process deliberately does not start FastAPI or Uvicorn. It reuses the
existing queue, generation, billing, storage and Telegram delivery logic from
``main.py``.
"""

import asyncio
import signal

from dotenv import load_dotenv


load_dotenv()

from main import (  # noqa: E402
    BOT_TOKEN,
    DATABASE_URL,
    PROSTUDIO_WORKER_CONCURRENCY,
    PROSTUDIO_WORKER_ENABLED,
    SUBSCRIPTION_REMINDER_WORKER_ENABLED,
    prostudio_generation_worker_loop,
    subscription_reminder_worker_loop,
)


async def run_worker() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL or DATABASE_PUBLIC_URL is required for worker")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required for worker Telegram delivery and reminders")

    tasks: list[asyncio.Task] = []
    if PROSTUDIO_WORKER_ENABLED:
        tasks.append(
            asyncio.create_task(
                prostudio_generation_worker_loop(),
                name="prostudio-generation-worker",
            )
        )
    if SUBSCRIPTION_REMINDER_WORKER_ENABLED:
        tasks.append(
            asyncio.create_task(
                subscription_reminder_worker_loop(),
                name="subscription-reminder-worker",
            )
        )

    if not tasks:
        raise RuntimeError(
            "Worker has no enabled tasks. Set PROSTUDIO_WORKER_ENABLED=1 and/or "
            "SUBSCRIPTION_REMINDER_WORKER_ENABLED=1"
        )

    print(
        "SYLVEX WORKER STARTED:",
        {
            "prostudio": PROSTUDIO_WORKER_ENABLED,
            "prostudio_concurrency": PROSTUDIO_WORKER_CONCURRENCY,
            "subscription_reminders": SUBSCRIPTION_REMINDER_WORKER_ENABLED,
        },
    )
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals = []
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, shutdown_event.set)
            installed_signals.append(signal_name)
        except (NotImplementedError, RuntimeError):
            pass

    shutdown_waiter = asyncio.create_task(shutdown_event.wait(), name="worker-shutdown-waiter")
    cancellation_requested = False
    try:
        done, _ = await asyncio.wait(
            [*tasks, shutdown_waiter],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if shutdown_waiter not in done:
            for task in done:
                if task is not shutdown_waiter:
                    task.result()
        cancellation_requested = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        shutdown_waiter.cancel()
        await asyncio.gather(shutdown_waiter, return_exceptions=True)
        if not cancellation_requested:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for signal_name in installed_signals:
            loop.remove_signal_handler(signal_name)


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("SYLVEX WORKER STOPPED")
