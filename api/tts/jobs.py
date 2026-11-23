"""Single-worker TTS job queue (one synthesis at a time: 6 GB RAM, no swap) + audio file storage."""
import asyncio
import json
import logging
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import soundfile as sf

from settings import Settings

from . import audio
from .kokoro_engine import KokoroEngine
from .text import split_text

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


@dataclass
class Job:
    id: str
    req: TTSRequest
    status: str = "queued"           # queued → running → done | error
    created_at: float = field(default_factory=time.time)
    progress: float = 0.0            # 0..1 (sentences synthesized)
    error: str | None = None
    result: dict | None = None
    done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class QueueFull(Exception):
    pass


class JobManager:
    def __init__(self, settings: Settings, engine: KokoroEngine):
        self.s = settings
        self.engine = engine
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.pending: list[str] = []                     # ids waiting, in order
        self.jobs: OrderedDict[str, Job] = OrderedDict()  # recent jobs (status lookups)
        self.running: str | None = None
        self.s.audio_dir.mkdir(parents=True, exist_ok=True)

    # ---- public API -------------------------------------------------------
    def submit(self, req: TTSRequest) -> Job:
        if len(self.pending) + (1 if self.running else 0) >= self.s.max_queue:
            raise QueueFull()
        job = Job(id=secrets.token_hex(16), req=req)
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
    async def worker(self) -> None:
        while True:
            job = await self.queue.get()
            self.pending.remove(job.id)
            self.running, job.status = job.id, "running"
            t0 = time.perf_counter()
            try:
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
                job.done_event.set()
                self.queue.task_done()

    def _process(self, job: Job) -> dict:
        r, s, sr = job.req, self.s, self.engine.sample_rate
        t0 = time.perf_counter()
        paragraphs = split_text(r.text)
        total = sum(len(p) for p in paragraphs) or 1
        done, clips = 0, []
        for para in paragraphs:
            row = []
            for sentence in para:
                a = self.engine.synthesize(sentence, r.voice, r.lang, r.speed)
                # Tight per-sentence trim so pauses between sentences are exactly what we insert.
                a = audio.trim_silence(a, sr, s.silence_threshold_db, keep_ms=TRIM_KEEP_MS)
                if a.size:
                    row.append(a)
                done += 1
                job.progress = done / total * 0.9
            if row:
                clips.append(row)
        joined = audio.join_segments(clips, sr, s.sentence_pause_ms, s.paragraph_pause_ms)
        joined = audio.trim_silence(joined, sr, s.silence_threshold_db, keep_ms=TRIM_KEEP_MS)
        if joined.size == 0:
            raise ValueError("No speech was produced for this text")
        # Edges: fade, then digital silence so lead/tail total ≈ edge_silence_ms (clean, gain-independent).
        joined = audio.pad_edges(joined, sr, max(0, s.edge_silence_ms - TRIM_KEEP_MS))
        synth_sec = time.perf_counter() - t0

        base = s.audio_dir / job.id
        loud = audio.export(joined, sr, base, sample_rate=s.sample_rate, mp3_bitrate=s.mp3_bitrate,
                            target_lufs=r.loudness_lufs, true_peak=s.true_peak_db)
        duration = round(sf.info(str(base.with_suffix(".wav"))).duration, 2)
        job.progress = 1.0
        result = {
            "url": f"/api/audio/{job.id}?format={r.format}",
            "urls": {f: f"/api/audio/{job.id}?format={f}" for f in FORMATS},
            "duration_sec": duration,
            "compute_sec": round(time.perf_counter() - t0, 2),
            "timing": {"synth_sec": round(synth_sec, 2), "post_sec": round(time.perf_counter() - t0 - synth_sec, 2)},
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
