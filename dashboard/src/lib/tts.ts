import { api } from "./api";

export type Format = "mp3" | "wav";

/** GET /api/tts/jobs/{id} and POST /api/tts responses. */
export type JobStatus = {
  id: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  position?: number;
  error?: string;
  url?: string;
  urls?: Record<Format, string>;
  duration_sec?: number;
  compute_sec?: number;
  loudness?: { target_lufs: number | null; output_lufs: number | null; output_true_peak: number | null };
};

export type TTSParams = {
  text: string;
  voice: string;
  lang: string;
  speed: number;
  format: Format;
  normalize: boolean;
  loudness_lufs: number;
  transliterate?: boolean;
};

export type HistoryItem = {
  id: string;
  status: JobStatus["status"];
  voice: string;
  lang: string;
  speed: number;
  format: Format;
  loudness_target: number | null;
  output_lufs: number | null;
  text_excerpt: string;
  text_chars: number;
  duration_sec: number | null;
  error: string | null;
  via_api: boolean;
  created_at: string;
  available: boolean;
  urls: Record<Format, string> | null;
};

export const createJob = (p: TTSParams) => api<JobStatus>("/api/tts", { json: p });
export const getJob = (id: string) => api<JobStatus>(`/api/tts/jobs/${encodeURIComponent(id)}`);
export const getHistory = (limit = 50) => api<{ items: HistoryItem[] }>(`/api/history?limit=${limit}`).then((r) => r.items);
export const downloadUrl = (url: string) => `${url}${url.includes("?") ? "&" : "?"}download=true`;

/** Poll a job until done/error. Faster while running (progress bar), slower while queued. */
export async function pollJob(id: string, onUpdate: (s: JobStatus) => void, signal: AbortSignal): Promise<JobStatus> {
  for (;;) {
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    const s = await getJob(id);
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    onUpdate(s);
    if (s.status === "done" || s.status === "error") return s;
    await new Promise((r) => setTimeout(r, s.status === "running" ? 700 : 1500));
  }
}

// Current job survives navigation within the tab (sessionStorage), so Generate can resume polling.
const JOB_KEY = "aiwazz-current-job";
export const rememberJob = (id: string | null) => {
  try {
    if (id) sessionStorage.setItem(JOB_KEY, id);
    else sessionStorage.removeItem(JOB_KEY);
  } catch {
    /* ignore */
  }
};
export const rememberedJob = () => {
  try {
    return sessionStorage.getItem(JOB_KEY);
  } catch {
    return null;
  }
};

// Draft script + settings persist per browser (localStorage), never sent anywhere until Generate.
const DRAFT_KEY = "aiwazz-draft";
export type Draft = Partial<Omit<TTSParams, "lang">>;
export const loadDraft = (): Draft => {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}");
  } catch {
    return {};
  }
};
export const saveDraft = (d: Draft) => {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  } catch {
    /* ignore */
  }
};

export const transliterate = (text: string) => api<{ text: string; latin_share: number }>("/api/transliterate", { json: { text } });

/** Share of letters in Latin script (client-side, for the "looks like Hinglish" hint). */
export function latinShare(text: string): number {
  let latin = 0;
  let dev = 0;
  for (const c of text) {
    if (/[A-Za-z]/.test(c)) latin++;
    else if (c >= "\u0900" && c <= "\u097f") dev++;
  }
  return latin + dev ? latin / (latin + dev) : 0;
}
