"""Background jobs started from the admin panel or the scheduler, each logged in task_runs (visible in admin).
Shell steps run as subprocesses (never through a shell string), one job of the same name at a time."""
import asyncio
import logging
from collections.abc import Awaitable, Callable

from db import utcnow
from models import TaskRun

log = logging.getLogger("aiwazz.jobs")
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
_running: dict[str, asyncio.Task] = {}


async def run_logged(sessionmaker, name: str, fn: Callable[[], Awaitable[str]]) -> str:
    async with sessionmaker() as db:
        run = TaskRun(task=name, started_at=utcnow())
        db.add(run)
        await db.commit()
        rid = run.id
    status, detail = "ok", ""
    try:
        detail = (await fn()) or ""
    except Exception as e:  # noqa: BLE001
        status, detail = "failed", f"{type(e).__name__}: {e}"
        log.exception("task %s failed", name)
    async with sessionmaker() as db:
        run = await db.get(TaskRun, rid)
        run.finished_at, run.status, run.detail = utcnow(), status, detail[:500]
        await db.commit()
    return status


async def run_cmd(*argv: str, timeout: int = 900, env: dict | None = None) -> str:
    import os
    proc = await asyncio.create_subprocess_exec(*argv, cwd=str(ROOT), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT, env={**os.environ, **(env or {})})
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        raise RuntimeError(f"{argv[0]} timed out after {timeout}s") from None
    text = out.decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:2])} exited {proc.returncode}: {text[-300:]}")
    return text[-300:]


def start(sessionmaker, name: str, fn: Callable[[], Awaitable[str]]) -> bool:
    """Start in the background unless a job with this name is already running. Returns False if it was."""
    t = _running.get(name)
    if t and not t.done():
        return False
    task = asyncio.get_running_loop().create_task(run_logged(sessionmaker, name, fn))
    _running[name] = task
    return True


def is_running(name: str) -> bool:
    t = _running.get(name)
    return bool(t and not t.done())
