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
    cloner = CloneClient(s.clone_url, s.clone_secret, s.clone_timeout_sec) if s.clone_secret else None
    jobs = JobManager(s, engine, cloner)
    app.state.clone_voices = load_clone_voices(s.data_dir / "voices") if cloner else {}
    jobs.on_start, jobs.on_finish = make_hooks(sessionmaker)
    app.state.jobs = jobs

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
    app.include_router(billing_router)
    app.include_router(pronunciations_router)
    app.include_router(preview_router)
    for r in ADMIN_ROUTERS:
        app.include_router(r)
    return app


app = create_app()
