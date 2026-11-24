"""Small in-process scheduler (one API worker): periodic tasks, each idempotent and logged in task_runs.

  plan-sweep   hourly   ended time-limited plans → Free; invite requests older than 12 months deleted
  dunning      hourly   failed-renewal reminders (day 0/3/7) and downgrade after the grace period
Later phases register more with every(...)."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from admin.jobs import run_logged

log = logging.getLogger("aiwazz.scheduler")


@dataclass
class Task:
    name: str
    interval: int                     # seconds
    fn: Callable                      # async (sessionmaker, app) -> str
    first_delay: int = 30
    log_ok: bool = True               # False: only failures are written to task_runs (very frequent tasks)


TASKS: list[Task] = []


def every(name: str, seconds: int, first_delay: int = 30, log_ok: bool = True):
    def deco(fn: Callable[..., Awaitable[str]]):
        TASKS.append(Task(name, seconds, fn, first_delay, log_ok))
        return fn
    return deco


async def _loop(t: Task, sessionmaker, app) -> None:
    await asyncio.sleep(t.first_delay)
    while True:
        if t.log_ok:
            await run_logged(sessionmaker, t.name, lambda: t.fn(sessionmaker, app))
        else:
            try:
                await t.fn(sessionmaker, app)
            except Exception:  # noqa: BLE001
                await run_logged(sessionmaker, t.name, lambda: t.fn(sessionmaker, app))
        await asyncio.sleep(t.interval)


def start(sessionmaker, app) -> list[asyncio.Task]:
    import tasks  # noqa: F401  (registers the task functions)
    return [asyncio.create_task(_loop(t, sessionmaker, app)) for t in TASKS]
