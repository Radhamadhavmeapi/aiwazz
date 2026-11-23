"""AiWazz Voice API. Run: uvicorn main:app --host 127.0.0.1 --port 8100 --workers 1"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from routes.tts import router as tts_router
from settings import get_settings
from tts.jobs import JobManager
from tts.kokoro_engine import KokoroEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("voice-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    engine = KokoroEngine(torch_threads=s.torch_threads)
    jobs = JobManager(s, engine)
    app.state.jobs = jobs

    async def load():
        await asyncio.to_thread(engine.load)
        await jobs.worker()

    # Load the model in the background so /api/health answers (503 "loading") meanwhile.
    tasks = [asyncio.create_task(load()), asyncio.create_task(jobs.cleanup_loop())]
    yield
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t


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
    app.include_router(tts_router)
    return app


app = create_app()
