"""Custom (clone) voices, phase 13. One folder per voice, outside git:

    data/voices/<id>/voice.json         this config (schema = CloneVoice below)
    data/voices/<id>/<reference wav>     reference clip (reference_path, relative to the folder)
    data/voices/<id>/tone_color.pt       cached tone colour, written by `voiceclone.prepare` (worker reads it)

A clone voice can only be selected when it also has an active (not revoked) row in `voice_consents`
(manage.py add-voice-consent). `is_public = false` voices are usable by admins (the owner) only.
Route A (chosen 24 Nov 2026): Kokoro `source_voice` → OpenVoice v2 tone colour conversion in the worker.
"""
import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloneVoice:
    id: str
    name: str
    lang: str = "h"
    gender: str = "male"
    tags: tuple[str, ...] = ()
    tier: str = "studio"
    reference_path: str = ""          # relative to the voice folder
    reference_text: str = ""          # optional transcript of the reference clip
    source_voice: str = "hm_omega"    # Kokoro voice that is converted
    tau: float = 0.3                  # OpenVoice conversion strength
    default_style: str | None = "energetic-reel"
    style_speed: dict = field(default_factory=dict)   # style id → speed for this voice (e.g. energetic-reel 1.08)
    default_speed: float = 1.0        # when neither a style nor a speed is given
    max_chars: int = 1500
    rtf: float = 1.9                  # measured compute ÷ audio on this CPU (Kokoro + conversion), for estimates
    chars_per_sec: float = 13.0       # Hindi speech at speed 1.0, for estimates
    is_public: bool = False
    engine: str = "clone"

    def speed_for(self, style_id: str | None, style_speed: float | None) -> float:
        if style_id and style_id in self.style_speed:
            return float(self.style_speed[style_id])
        return style_speed if style_speed is not None else self.default_speed

    def estimate_sec(self, chars: int, speed: float) -> int:
        """Rough compute time for a job (audio length × measured speed), rounded up to 10 s."""
        audio = chars / (self.chars_per_sec * max(speed, 0.5))
        return int(-(-(audio * self.rtf + 3) // 10) * 10)

    def to_public_dict(self) -> dict:
        from .voices import LANGS
        return {"id": self.id, "engine": self.engine, "lang": self.lang, "name": self.name, "gender": self.gender,
                "lang_name": LANGS[self.lang], "tags": list(self.tags), "tier": self.tier, "is_public": self.is_public,
                "default_style": self.default_style, "style_speed": dict(self.style_speed), "max_chars": self.max_chars,
                "preview_url": f"/api/voices/{self.id}/preview",
                "seconds_per_char": round(self.rtf / self.chars_per_sec, 4)}


def load_clone_voices(voices_dir: Path) -> dict[str, CloneVoice]:
    """Read every data/voices/*/voice.json. Bad files are logged and skipped (never crash the API)."""
    out: dict[str, CloneVoice] = {}
    if not voices_dir.is_dir():
        return out
    known = {f.name for f in fields(CloneVoice)}
    for cfg in sorted(voices_dir.glob("*/voice.json")):
        try:
            raw = json.loads(cfg.read_text(encoding="utf-8"))
            raw = {k: v for k, v in raw.items() if k in known}
            raw["tags"] = tuple(raw.get("tags", ()))
            v = CloneVoice(**raw)
            if v.id != cfg.parent.name:
                raise ValueError(f"id '{v.id}' must match its folder name")
            out[v.id] = v
        except Exception:
            log.exception("skipping bad clone voice config %s", cfg)
    return out


def voice_dir(voices_dir: Path, voice: CloneVoice) -> Path:
    return voices_dir / voice.id


def as_dict(v: CloneVoice) -> dict:
    return asdict(v)
