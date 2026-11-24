"""Speaking styles: named presets for pace, pauses and loudness (from the Voice Lab A3 presets, owner-approved 24 Nov 2026).

A style never changes the voice; `suggested_voice` is only a hint shown in the dashboard. Product wording: "styles",
never "emotions" (the model has no emotion control; a style is pace + pauses + loudness).
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    description: str
    speed: float
    sentence_pause_ms: int
    paragraph_pause_ms: int
    loudness_lufs: float
    suggested_voice: str

    def to_dict(self) -> dict:
        return asdict(self)


STYLES: dict[str, Style] = {s.id: s for s in [
    Style("energetic-reel", "Energetic reel", "Quick pace and short pauses for hooks, reels and Shorts.",
          1.12, 150, 400, -14.0, "hf_beta"),
    Style("calm-narrator", "Calm narrator", "Slower pace with longer pauses for stories, courses and explainers.",
          0.92, 400, 900, -16.0, "hm_psi"),
    Style("ad-announcer", "Ad announcer", "Brisk and punchy for offers, ads and announcements.",
          1.05, 200, 500, -14.0, "hm_omega"),
    Style("friendly-explainer", "Friendly explainer", "Natural pace and even pauses for everyday videos.",
          1.0, 250, 600, -14.0, "hf_alpha"),
]}
