"""TTS job queues + audio file storage.

Kokoro queue: one synthesis at a time (6 GB RAM, no swap). Clone (studio) voices run in two stages: Kokoro reads the
script with the voice's `source_voice` in the Kokoro queue, then the job moves to a separate one-at-a-time clone queue
that sends each sentence to the voice-clone worker (its own process). Kokoro jobs never wait for a conversion.
"""
import asyncio
import json
import logging
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import soundfile as sf

from settings import Settings

from . import audio
from .clone_client import CloneClient, CloneError
from .kokoro_engine import KokoroEngine
from .text import normalize, split_text

log = logging.getLogger(__name__)
ID_RE = re.compile(r"^[0-9a-f]{32}$")
FORMATS = ("mp3", "wav")
TRIM_KEEP_MS = 20  # tail kept after each sentence (soft word endings), before fades + padding


@dataclass
class TTSRequest:
    text: str
    engine: str
    voice: str
    lang: str
    speed: float
    format: str
    loudness_lufs: float | None  # None = no normalisation
    sentence_pause_ms: int | None = None   # None = settings default (a style sets its own)
    paragraph_pause_ms: int | None = None
    source_voice: str | None = None        # clone jobs: Kokoro voice to read with; `voice` is the clone voice id


@dataclass
class Job:
    id: str
    req: TTSRequest
    user_id: int | None = None       # owner (None only in tests/tools)
    status: str = "queued"           # queued → running → done | error
    created_at: float = field(default_factory=time.time)
    progress: float = 0.0            # 0..1 (sentences synthesized)
    error: str | None = None
    result: dict | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    stage: str | None = None         # clone jobs: "speech" (Kokoro) → "studio-queue" → "studio" (conversion)
    estimate_sec: int | None = None  # clone jobs: rough compute time, shown in the UI
    clips: list | None = field(default=None, repr=False)   # clone jobs between the two stages
    timing: dict = field(default_factory=dict)


class QueueFull(Exception):
    pass


class TooManyPending(Exception):
    """This user already has the maximum number of jobs waiting."""


Hook = Callable[[Job], Awaitable[None]]
MAX_PENDING_PER_USER = 3
MAX_CLONE_JOBS = 5                   # clone jobs in either stage (the conversion is ~1x realtime on this CPU)
CLONE_UNAVAILABLE = "The studio voice is unavailable right now. Nothing was charged; please try again in a few minutes."


class JobManager:
    def __init__(self, settings: Settings, engine: KokoroEngine, cloner: CloneClient | None = None):
        self.s = settings
        self.engine = engine
        self.cloner = cloner
        self.clone_queue: asyncio.Queue[Job] = asyncio.Queue()
        self.clone_pending: list[str] = []
        self.clone_running: str | None = None
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.pending: list[str] = []                     # ids waiting, in order
        self.jobs: OrderedDict[str, Job] = OrderedDict()  # recent jobs (status lookups)
        self.running: str | None = None
        # Operations (admin → Queue & jobs): paused = jobs wait; maintenance = new jobs are refused (routes/tts.py).
        self.resume_event = asyncio.Event()
        self.resume_event.set()
        self.maintenance = False
        self.maintenance_message = ""
        self.on_start: Hook | None = None   # e.g. mark the DB row "running"
        self.on_finish: Hook | None = None  # e.g. store result/error in the DB
        self.s.audio_dir.mkdir(parents=True, exist_ok=True)

    # ---- public API -------------------------------------------------------
    def clone_jobs(self) -> int:
        return sum(1 for j in self.jobs.values() if j.req.source_voice and j.status in ("queued", "running"))

    def check_capacity(self, user_id: int | None, clone: bool = False) -> None:
        """Raise before any DB row is created if the job can't be queued."""
        if len(self.pending) + (1 if self.running else 0) >= self.s.max_queue:
            raise QueueFull()
        if clone and self.clone_jobs() >= MAX_CLONE_JOBS:
            raise QueueFull()
        if user_id is not None and sum(1 for j in self.pending if self.jobs.get(j) and self.jobs[j].user_id == user_id) >= MAX_PENDING_PER_USER:
            raise TooManyPending()

    def submit(self, req: TTSRequest, job_id: str | None = None, user_id: int | None = None,
               estimate_sec: int | None = None) -> Job:
        self.check_capacity(user_id, clone=bool(req.source_voice))
        job = Job(id=job_id or secrets.token_hex(16), req=req, user_id=user_id, estimate_sec=estimate_sec,
                  stage="speech" if req.source_voice else None)
        self.jobs[job.id] = job
        while len(self.jobs) > 500:
            self.jobs.popitem(last=False)
        self.pending.append(job.id)
        self.queue.put_nowait(job)
        return job

    def position(self, job: Job) -> int:
        """Place in line: 1 = runs next (after the current job), 0 = not waiting."""
        try:
            return self.pending.index(job.id) + 1
        except ValueError:
            return 0

    def status(self, job: Job) -> dict:
        d = {"id": job.id, "status": job.status, "progress": round(job.progress, 3)}
        if job.status == "queued":
            d["position"] = self.position(job)
        if job.stage:
            d["stage"] = job.stage
            if job.stage == "studio-queue":
                d["position"] = self.clone_pending.index(job.id) + 1 if job.id in self.clone_pending else 0
        if job.estimate_sec is not None:
            d["estimate_sec"] = job.estimate_sec
        if job.error:
            d["error"] = job.error
        if job.result:
            d.update(job.result)
        return d

    def audio_path(self, audio_id: str, fmt: str) -> Path | None:
        if not ID_RE.match(audio_id) or fmt not in FORMATS:
            return None
        p = self.s.audio_dir / f"{audio_id}.{fmt}"
        return p if p.is_file() else None

    # ---- worker -----------------------------------------------------------
    @property
    def paused(self) -> bool:
        return not self.resume_event.is_set()

    def set_paused(self, paused: bool) -> None:
        (self.resume_event.clear if paused else self.resume_event.set)()

    async def cancel(self, job_id: str, reason: str = "Cancelled by support. Nothing was charged.") -> bool:
        """Cancel a waiting job (running jobs can't be interrupted). The DB row becomes an error → not counted."""
        job = self.jobs.get(job_id)
        if job is None or job.status != "queued" or job_id not in self.pending:
            return False
        self.pending.remove(job_id)
        job.status, job.error = "error", reason
        await self._finish_hooks(job)
        return True

    async def worker(self) -> None:
        while True:
            job = await self.queue.get()
            await self.resume_event.wait()          # queue paused: the next job waits here (still "queued")
            if job.status != "queued" or job.id not in self.pending:   # cancelled while waiting
                self.queue.task_done()
                continue
            self.pending.remove(job.id)
            self.running, job.status = job.id, "running"
            t0 = time.perf_counter()
            await self._hook(self.on_start, job)
            handed_off = False
            try:
                if job.req.source_voice:   # clone job: speech here, conversion in the clone queue
                    job.clips = await asyncio.to_thread(self._synth_clips, job, 0.4)
                    if not job.clips:
                        raise ValueError("No speech was produced for this text")
                    job.stage = "studio-queue"
                    self.clone_pending.append(job.id)
                    self.clone_queue.put_nowait(job)
                    handed_off = True
                else:
                    job.result = await asyncio.to_thread(self._process, job)
                    job.status = "done"
                    log.info("job %s done: %.1fs audio in %.1fs", job.id,
                             job.result["duration_sec"], time.perf_counter() - t0)
            except Exception as e:  # report to client, keep worker alive
                log.exception("job %s failed", job.id)
                job.status = "error"
                job.error = str(e) if isinstance(e, (audio.AudioError, ValueError)) else "Synthesis failed"
            finally:
                self.running = None
                if not handed_off:
                    await self._finish_hooks(job)
                self.queue.task_done()

    async def clone_worker(self) -> None:
        """Second stage of clone jobs, one at a time, independent of the Kokoro queue."""
        while True:
            job = await self.clone_queue.get()
            self.clone_pending.remove(job.id)
            self.clone_running, job.stage = job.id, "studio"
            try:
                job.result = await asyncio.to_thread(self._clone_finish, job)
                job.status = "done"
                log.info("clone job %s done: %.1fs audio, timing %s", job.id, job.result["duration_sec"], job.timing)
            except CloneError as e:
                log.error("clone job %s failed: %s", job.id, e)
                job.status, job.error = "error", CLONE_UNAVAILABLE
            except Exception as e:
                log.exception("clone job %s failed", job.id)
                job.status = "error"
                job.error = str(e) if isinstance(e, (audio.AudioError, ValueError)) else "Synthesis failed"
            finally:
                self.clone_running, job.clips = None, None
                await self._finish_hooks(job)
                self.clone_queue.task_done()

    async def _finish_hooks(self, job: Job) -> None:
        await self._hook(self.on_finish, job)
        job.done_event.set()

    async def _hook(self, hook: Hook | None, job: Job) -> None:
        if hook is None:
            return
        try:
            await hook(job)
        except Exception:  # a DB hiccup must never kill the worker
            log.exception("job hook failed for %s", job.id)

    def _synth_clips(self, job: Job, share: float) -> list[list]:
        """Kokoro, sentence by sentence → [[clip, …] per paragraph], trimmed. Progress goes 0 → `share`."""
        r, s, sr = job.req, self.s, self.engine.sample_rate
        t0 = time.perf_counter()
        paragraphs = split_text(normalize(r.text, r.lang))
        total = sum(len(p) for p in paragraphs) or 1
        done, clips = 0, []
        for para in paragraphs:
            row = []
            for sentence in para:
                a = self.engine.synthesize(sentence, r.source_voice or r.voice, r.lang, r.speed)
                # Tight per-sentence trim so pauses between sentences are exactly what we insert.
                a = audio.trim_silence(a, sr, s.silence_threshold_db, keep_ms=TRIM_KEEP_MS)
                if a.size:
                    row.append(a)
                done += 1
                job.progress = done / total * share
            if row:
                clips.append(row)
        job.timing["synth_sec"] = round(time.perf_counter() - t0, 2)
        return clips

    def _clone_finish(self, job: Job) -> dict:
        """Convert every sentence in the worker (retry the whole conversion once), then the usual post-processing."""
        if self.cloner is None or not self.cloner.configured:
            raise CloneError("clone worker not configured")
        t0 = time.perf_counter()
        sr_in, total = self.engine.sample_rate, sum(len(row) for row in job.clips) or 1
        for attempt in (1, 2):
            try:
                out, out_sr, done = [], None, 0
                for row in job.clips:
                    conv = []
                    for a in row:
                        y, out_sr = self.cloner.convert(a, sr_in, job.req.voice)
                        y = audio.trim_silence(y, out_sr, self.s.silence_threshold_db, keep_ms=TRIM_KEEP_MS)
                        if y.size:
                            conv.append(y)
                        done += 1
                        job.progress = 0.4 + 0.55 * done / total
                    if conv:
                        out.append(conv)
                break
            except CloneError as e:
                if attempt == 2:
                    raise
                log.warning("clone job %s: %s, retrying once", job.id, e)
                job.progress = 0.4
                time.sleep(3)
        job.timing["convert_sec"] = round(time.perf_counter() - t0, 2)
        if not out:
            raise ValueError("No speech was produced for this text")
        return self._finish(job, out, out_sr, sum(job.timing.values()))

    def _process(self, job: Job) -> dict:
        clips = self._synth_clips(job, 0.9)
        return self._finish(job, clips, self.engine.sample_rate, job.timing["synth_sec"])

    def _finish(self, job: Job, clips: list[list], sr: int, work_sec: float) -> dict:
        """Join with pauses, trim, pad edges, loudness + export WAV/MP3, write metadata."""
        r, s = job.req, self.s
        t0 = time.perf_counter()
        joined = audio.join_segments(clips, sr,
                                     s.sentence_pause_ms if r.sentence_pause_ms is None else r.sentence_pause_ms,
                                     s.paragraph_pause_ms if r.paragraph_pause_ms is None else r.paragraph_pause_ms)
        joined = audio.trim_silence(joined, sr, s.silence_threshold_db, keep_ms=TRIM_KEEP_MS)
        if joined.size == 0:
            raise ValueError("No speech was produced for this text")
        # Edges: fade, then digital silence so lead/tail total ≈ edge_silence_ms (clean, gain-independent).
        joined = audio.pad_edges(joined, sr, max(0, s.edge_silence_ms - TRIM_KEEP_MS))

        base = s.audio_dir / job.id
        loud = audio.export(joined, sr, base, sample_rate=s.sample_rate, mp3_bitrate=s.mp3_bitrate,
                            target_lufs=r.loudness_lufs, true_peak=s.true_peak_db,
                            compressor=audio.Compressor(s.compressor_threshold_rel_db, s.compressor_ratio)
                            if s.compressor else None)
        duration = round(sf.info(str(base.with_suffix(".wav"))).duration, 2)
        job.progress = 1.0
        result = {
            "url": f"/api/audio/{job.id}?format={r.format}",
            "urls": {f: f"/api/audio/{job.id}?format={f}" for f in FORMATS},
            "duration_sec": duration,
            "compute_sec": round(work_sec + time.perf_counter() - t0, 2),
            "timing": job.timing | {"post_sec": round(time.perf_counter() - t0, 2)},
            "loudness": asdict(loud),
        }
        meta = {"id": job.id, "created_at": job.created_at, "request": asdict(r) | {"text": r.text[:200]},
                **result}
        base.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False))
        return result

    # ---- retention --------------------------------------------------------
    def cleanup(self) -> int:
        cutoff = time.time() - self.s.audio_retention_days * 86400
        removed = 0
        for p in self.s.audio_dir.iterdir():
            if p.is_file() and p.suffix in (".wav", ".mp3", ".json") and p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        return removed

    async def cleanup_loop(self) -> None:
        while True:
            try:
                n = await asyncio.to_thread(self.cleanup)
                if n:
                    log.info("retention: removed %d old audio files", n)
            except Exception:
                log.exception("retention cleanup failed")
            await asyncio.sleep(3600)
