"""Standalone background worker for SYLVEX Pro Studio.

This process deliberately does not start FastAPI or Uvicorn. It reuses the
existing queue, generation, billing, storage and Telegram delivery logic from
``main.py``.
"""

import asyncio

from dotenv import load_dotenv


load_dotenv()

from main import (  # noqa: E402
    BOT_TOKEN,
    DATABASE_URL,
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
            "subscription_reminders": SUBSCRIPTION_REMINDER_WORKER_ENABLED,
        },
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("SYLVEX WORKER STOPPED")
