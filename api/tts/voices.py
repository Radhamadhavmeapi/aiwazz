"""Curated voice catalogue. Kokoro voice IDs start with <lang><gender>_ (e.g. hf_ = Hindi female)."""
from dataclasses import asdict, dataclass

LANGS = {
    "h": "Hindi",
    "a": "English (US)",
    "b": "English (UK)",
}


@dataclass(frozen=True)
class Voice:
    id: str
    engine: str
    lang: str
    name: str
    gender: str

    def to_dict(self) -> dict:
        return asdict(self) | {"lang_name": LANGS[self.lang]}


def _k(voice_id: str, name: str) -> Voice:
    return Voice(id=voice_id, engine="kokoro", lang=voice_id[0], name=name,
                 gender="female" if voice_id[1] == "f" else "male")


VOICES: dict[str, Voice] = {v.id: v for v in [
    _k("hf_alpha", "Alpha"), _k("hf_beta", "Beta"), _k("hm_omega", "Omega"), _k("hm_psi", "Psi"),
    _k("af_heart", "Heart"), _k("af_bella", "Bella"), _k("af_nicole", "Nicole"),
    _k("am_michael", "Michael"), _k("am_fenrir", "Fenrir"), _k("am_puck", "Puck"),
    _k("bf_emma", "Emma"), _k("bf_isabella", "Isabella"), _k("bm_george", "George"), _k("bm_fable", "Fable"),
]}

DEFAULT_VOICE = "hf_alpha"
