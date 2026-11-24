"""AiWazz Voice API. Run: uvicorn main:app --host 127.0.0.1 --port 8100 --workers 1"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy import update

from auth.routes import router as auth_router
from db import make_engine, make_sessionmaker, utcnow
from models import Generation
from billing.routes import router as billing_router
from routes.tts import make_hooks
from routes.tts import router as tts_router
from routes.pronunciations import router as pronunciations_router
from routes.preview import router as preview_router
from admin.routes import ROUTERS as ADMIN_ROUTERS
from settings import get_settings
from tts.jobs import JobManager
from tts.clone_client import CloneClient
from tts.clone_voices import load_clone_voices
from tts.kokoro_engine import KokoroEngine

import contextvars
import secrets as _secrets

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = REQUEST_ID.get()
        return True


_handler = logging.StreamHandler()
_handler.addFilter(_RequestIdFilter())
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(rid)s]: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("voice-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    engine_db = make_engine(s.database_url)
    sessionmaker = make_sessionmaker(engine_db)
    app.state.sessionmaker = sessionmaker
    app.state.redis = getattr(app.state, "redis", None) or Redis.from_url(s.redis_url, decode_responses=True)

    # Jobs that were queued/running when the process stopped can't resume (the queue is in memory).
    async with sessionmaker() as db:
        res = await db.execute(
            update(Generation).where(Generation.status.in_(("queued", "running")))
            .values(status="error", error="Interrupted by a server restart. Please generate again.", finished_at=utcnow())
        )
        await db.commit()
        if res.rowcount:
            log.info("marked %d interrupted jobs as failed", res.rowcount)

    engine = KokoroEngine(torch_threads=s.torch_threads)
    cloner = CloneClient(s.clone_url, s.clone_secret, s.clone_timeout_sec) if s.clone_secret else None
    jobs = JobManager(s, engine, cloner)
    app.state.clone_voices = load_clone_voices(s.data_dir / "voices") if cloner else {}
    jobs.on_start, jobs.on_finish = make_hooks(sessionmaker)
    app.state.jobs = jobs
    from admin import settings_store
    async with sessionmaker() as db:     # queue pause / maintenance survive restarts
        ops = await settings_store.get(db, "ops")
    jobs.set_paused(bool(ops.get("queue_paused")))
    jobs.maintenance, jobs.maintenance_message = bool(ops.get("maintenance")), ops.get("message", "")
    async with sessionmaker() as db:     # runtime limits saved in admin → Settings (only if they were ever saved)
        from models import AppSetting
        if await db.get(AppSetting, "limits"):
            from admin.routes.governance import apply_limits
            apply_limits(await settings_store.get(db, "limits"))

    async def load():
        await asyncio.to_thread(engine.load)
        await jobs.worker()

    # Load the model in the background so /api/health answers (503 "loading") meanwhile.
    import scheduler
    tasks = [asyncio.create_task(load()), asyncio.create_task(jobs.cleanup_loop()), asyncio.create_task(jobs.clone_worker())]
    if not s.debug or s.env == "development":      # tests drive tasks directly
        tasks += scheduler.start(sessionmaker, app)
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    await app.state.redis.aclose()
    await engine_db.dispose()


async def _count_request(request: Request, status: int) -> None:
    """Per-endpoint request/error counters for admin → API & usage (Redis hash per UTC day, 32-day expiry)."""
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/admin") or path == "/api/health":
        return
    route = request.scope.get("route")
    tmpl = getattr(route, "path", None) or "other"
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    try:
        s = get_settings()
        key = f"{s.redis_prefix}reqstats:{utcnow():%Y%m%d}"
        async with redis.pipeline(transaction=False) as pipe:
            pipe.hincrby(key, f"{request.method} {tmpl}|{status // 100}xx", 1)
            pipe.expire(key, 32 * 86400)
            await pipe.execute()
    except Exception:  # noqa: BLE001 - statistics must never break a request
        pass


def create_app() -> FastAPI:
    s = get_settings()
    dev = s.debug
    app = FastAPI(
        title="AiWazz Voice API",
        lifespan=lifespan,
        docs_url="/api/docs" if dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if dev else None,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        rid = _secrets.token_hex(6)
        REQUEST_ID.set(rid)
        try:
            resp = await call_next(request)
        except Exception:
            log.exception("unhandled error on %s %s", request.method, request.url.path)
            raise
        resp.headers["X-Request-ID"] = rid
        if resp.status_code >= 500 and request.url.path != "/api/health":   # health is 503 while the model loads
            log.error("%s %s → %d", request.method, request.url.path, resp.status_code)
        await _count_request(request, resp.status_code)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/audio/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    app.include_router(auth_router)
    app.include_router(tts_router)
    app.include_router(billing_router)
    app.include_router(pronunciations_router)
    app.include_router(preview_router)
    for r in ADMIN_ROUTERS:
        app.include_router(r)
    return app


app = create_app()
