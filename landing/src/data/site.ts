import samples from "../../samples/samples.json";

export const SITE = {
  name: "AiWazz",
  url: "https://aiwazz.in",
  tagline: "Type it, hear it.",
  description:
    "AI voiceovers in Hindi, Hinglish & English. Paste your script, pick a natural voice and download a reel-ready MP3 or WAV in about a minute.",
  app: "https://login.aiwazz.in",
  signIn: "https://login.aiwazz.in/login",
  getInvite: "https://login.aiwazz.in/signup",
  getStarted: "https://login.aiwazz.in/signup",
  ogImage: "https://aiwazz.in/og-image.png",
};

export type Sample = { id: string; name: string; lang: "h" | "a" | "b"; gender: "female" | "male"; tone: string; text: string; duration: number };

const META: Record<string, { name: string; tone: string }> = {
  hf_alpha: { name: "Alpha", tone: "Warm, clear" },
  hf_beta: { name: "Beta", tone: "Bright, friendly" },
  hm_omega: { name: "Omega", tone: "Deep, calm" },
  hm_psi: { name: "Psi", tone: "Steady narrator" },
  af_heart: { name: "Heart", tone: "Warm, natural" },
  af_bella: { name: "Bella", tone: "Expressive" },
  af_nicole: { name: "Nicole", tone: "Soft, close" },
  am_michael: { name: "Michael", tone: "Confident" },
  am_fenrir: { name: "Fenrir", tone: "Bold" },
  am_puck: { name: "Puck", tone: "Playful" },
  bf_emma: { name: "Emma", tone: "Polished" },
  bf_isabella: { name: "Isabella", tone: "Elegant" },
  bm_george: { name: "George", tone: "Classic narrator" },
  bm_fable: { name: "Fable", tone: "Storyteller" },
};

type Raw = { voice: string; text: string; duration_sec: number };
const raw = samples as Record<string, Raw>;

export const VOICE_SAMPLES: Sample[] = Object.keys(META).map((id) => ({
  id,
  ...META[id],
  lang: id[0] as Sample["lang"],
  gender: id[1] === "f" ? "female" : "male",
  text: raw[id].text,
  duration: raw[id].duration_sec,
}));

export const DEMOS = {
  hi: { file: "demo-hi", voice: "Alpha · Hindi", text: raw["demo-hi"].text, duration: raw["demo-hi"].duration_sec },
  en: { file: "demo-en", voice: "Michael · English (US)", text: raw["demo-en"].text, duration: raw["demo-en"].duration_sec },
};

export const LANG_LABEL = { h: "Hindi", a: "English (US)", b: "English (UK)" } as const;

export const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export const FOOTER = {
  product: [
    { href: "/pricing/", label: "Pricing" },
    { href: "/text-to-speech/", label: "Text to speech" },
    { href: "/hindi-text-to-speech/", label: "Hindi text to speech" },
    { href: "/ai-voiceover-for-reels/", label: "AI voiceover for reels" },
  ],
  company: [
    { href: "/about/", label: "About" },
    { href: "/contact/", label: "Contact" },
    { href: "/grievance/", label: "Grievance" },
  ],
  learn: [
    { href: "/learn/getting-started/", label: "Getting started" },
    { href: "/learn/hindi-and-hinglish/", label: "Hindi & Hinglish" },
    { href: "/learn/api-quickstart/", label: "API quickstart" },
    { href: "/learn/troubleshooting/", label: "Troubleshooting" },
  ],
  legal: [
    { href: "/terms/", label: "Terms" },
    { href: "/privacy/", label: "Privacy" },
    { href: "/refund-policy/", label: "Refund policy" },
    { href: "/shipping-policy/", label: "Shipping & delivery" },
    { href: "/acceptable-use/", label: "Acceptable use" },
    { href: "/data-deletion/", label: "Data deletion" },
  ],
};

export const SEO_PAGES = [
  { href: "/text-to-speech/", label: "Text to speech" },
  { href: "/hindi-text-to-speech/", label: "Hindi text to speech" },
  { href: "/ai-voiceover-for-reels/", label: "AI voiceover for reels" },
];
