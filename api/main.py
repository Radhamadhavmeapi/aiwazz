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
from routes.tts import make_hooks
from routes.tts import router as tts_router
from settings import get_settings
from tts.jobs import JobManager
from tts.kokoro_engine import KokoroEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    jobs = JobManager(s, engine)
    jobs.on_start, jobs.on_finish = make_hooks(sessionmaker)
    app.state.jobs = jobs

    async def load():
        await asyncio.to_thread(engine.load)
        await jobs.worker()

    async def plan_sweep():
        """Hourly: ended time-limited plans go back to Free; invite requests older than 12 months are deleted."""
        from usage import expire_plans, purge_old_invite_requests
        while True:
            try:
                async with sessionmaker() as db:
                    if n := await expire_plans(db):
                        log.info("moved %d user(s) back to Free (plan ended)", n)
                    if n := await purge_old_invite_requests(db):
                        log.info("deleted %d invite request(s) older than 12 months", n)
            except Exception:  # noqa: BLE001
                log.exception("plan sweep failed")
            await asyncio.sleep(3600)

    # Load the model in the background so /api/health answers (503 "loading") meanwhile.
    tasks = [asyncio.create_task(load()), asyncio.create_task(jobs.cleanup_loop()), asyncio.create_task(plan_sweep())]
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    await app.state.redis.aclose()
    await engine_db.dispose()


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
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/audio/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    app.include_router(auth_router)
    app.include_router(tts_router)
    return app


app = create_app()
