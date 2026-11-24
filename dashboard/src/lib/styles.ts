// Speaking styles. Mirrors GET /api/styles (api/tts/styles.py). A style sets pace, pauses and loudness;
// the voice stays your choice (suggestedVoice is only a hint). Never call these "emotions".
export type Style = {
  id: string;
  name: string;
  description: string;
  speed: number;
  pauses: string;
  lufs: number;
  suggestedVoice: string;
};

export const STYLES: Style[] = [
  {
    id: "energetic-reel",
    name: "Energetic reel",
    description: "Quick pace and short pauses for hooks, reels and Shorts.",
    speed: 1.12,
    pauses: "short pauses",
    lufs: -14,
    suggestedVoice: "hf_beta",
  },
  {
    id: "calm-narrator",
    name: "Calm narrator",
    description:
      "Slower pace with longer pauses for stories, courses and explainers.",
    speed: 0.92,
    pauses: "long pauses",
    lufs: -16,
    suggestedVoice: "hm_psi",
  },
  {
    id: "ad-announcer",
    name: "Ad announcer",
    description: "Brisk and punchy for offers, ads and announcements.",
    speed: 1.05,
    pauses: "tight pauses",
    lufs: -14,
    suggestedVoice: "hm_omega",
  },
  {
    id: "friendly-explainer",
    name: "Friendly explainer",
    description: "Natural pace and even pauses for everyday videos.",
    speed: 1.0,
    pauses: "even pauses",
    lufs: -14,
    suggestedVoice: "hf_alpha",
  },
];
