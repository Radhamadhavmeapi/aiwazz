import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertCircle,
  AudioLines,
  Check,
  ChevronDown,
  Clock,
  Copy,
  Download,
  Eraser,
  Gauge,
  Info,
  Languages,
  BookA,
  Pause,
  Play,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell/app-shell";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { VoiceCard } from "@/components/audio/voice-card";
import { fmtTime, WaveformPlayer } from "@/components/audio/waveform-player";
import { LiveWaveform } from "@/components/brand/live-waveform";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import { PREVIEW } from "@/lib/env";
import { fmtDuration, timeAgo } from "@/lib/format";
import { refreshUsage } from "@/lib/usage";
import {
  createJob,
  downloadUrl,
  getHistory,
  INLINE_PRON,
  latinShare,
  loadDraft,
  pollJob,
  readAs,
  rememberedJob,
  rememberJob,
  saveDraft,
  type Format,
  type HistoryItem,
  type JobStatus,
} from "@/lib/tts";
import { STYLES } from "@/lib/styles";
import { cn } from "@/lib/utils";
import { findVoice, langLabel, LANGS, sampleUrl, studioEstimate, useVoices, VOICES, type Lang, type Voice } from "@/lib/voices";

const MAX_CHARS = 5000;
const SAMPLE_TEXT =
  "रात ग्यारह बजे कस्टमर का फ़ोन आया। ऑर्डर अभी तक नहीं पहुँचा था। हमने दस मिनट में वजह ढूँढी, और अगली सुबह पार्सल उसके दरवाज़े पर था।";
const LOUDNESS = [
  { v: -14, label: "-14", hint: "Reels, Shorts, TikTok" },
  { v: -16, label: "-16", hint: "Podcasts, Spotify" },
  { v: -18, label: "-18", hint: "Quieter, more dynamic" },
  { v: -23, label: "-23", hint: "Broadcast (EBU R128)" },
];

type Job =
  | { state: "idle" }
  | { state: "queued"; position: number; studio?: StudioProgress }
  | { state: "running"; progress: number; studio?: StudioProgress }
  | { state: "done"; url: string; urls?: Record<Format, string>; duration: number; voice: string; lufs: number | null; format: Format }
  | { state: "error"; message: string };

/** Clone (studio) jobs: stage from the API ("speech" → "studio-queue" → "studio") + rough total time. */
type StudioProgress = { stage?: string; estimate?: number };

// ~14 chars/s of speech for Hindi, ~15 for English at speed 1.0
const estimateSeconds = (chars: number, speed: number) => Math.round(chars / 14.5 / speed);
/** "about 2 min" / "40 s" for wait times. */
const fmtWait = (sec: number) => (sec < 60 ? `${Math.max(10, Math.round(sec / 10) * 10)} s` : `${Math.round(sec / 60)} min`);

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={htmlFor} className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {label}
        </Label>
        {hint && <span className="text-xs text-subtle-foreground">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export default function GeneratePage() {
  const reduce = useReducedMotion();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [draft] = useState(loadDraft);
  const allVoices = useVoices();
  const wantedVoice = useRef<string | null>(params.get("voice") ?? draft.voice ?? null);
  const initialVoice = VOICES.find((v) => v.id === (params.get("voice") ?? draft.voice))?.id ?? "hf_alpha";
  const [text, setText] = useState(draft.text ?? SAMPLE_TEXT);
  const [lang, setLang] = useState<Lang>(VOICES.find((v) => v.id === initialVoice)!.lang);
  const [voice, setVoice] = useState(initialVoice);
  const [speed, setSpeed] = useState(draft.speed ?? 1);
  const [transliterate, setTransliterate] = useState(draft.transliterate ?? false);
  const [readAsPreview, setReadAsPreview] = useState<string | null>(null);
  const [style, setStyle] = useState<string | null>(STYLES.some((st) => st.id === draft.style) ? draft.style! : null);
  const [format, setFormat] = useState<Format>(draft.format ?? "mp3");
  const [normalize, setNormalize] = useState(draft.normalize ?? true);
  const [lufs, setLufs] = useState(draft.loudness_lufs ?? -14);
  const [loadingVoices, setLoadingVoices] = useState(PREVIEW);
  const [job, setJob] = useState<Job>({ state: "idle" });
  const [recentKey, setRecentKey] = useState(0);
  const timers = useRef<number[]>([]);
  const editor = useRef<HTMLTextAreaElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const poll = useRef<AbortController | null>(null);
  const lastReq = useRef<{ voice: string; format: Format; lufs: number | null }>({ voice, format, lufs: normalize ? lufs : null });

  useEffect(() => {
    if (!PREVIEW) return;
    const t = window.setTimeout(() => setLoadingVoices(false), 450); // preview: skeleton state
    return () => clearTimeout(t);
  }, []);
  useEffect(() => () => (timers.current.forEach(clearTimeout), poll.current?.abort()), []);

  // Keep the draft (script + settings) in this browser between visits.
  useEffect(() => {
    const t = window.setTimeout(() => saveDraft({ text, voice, speed, format, normalize, loudness_lufs: lufs, transliterate, style }), 400);
    return () => clearTimeout(t);
  }, [text, voice, speed, format, normalize, lufs, transliterate, style]);

  // Live preview of what the voice will actually read: pronunciations ([word](say-as), your list, global list)
  // and the Hinglish → Devanagari conversion. Shown only when something changes.
  const translitOn = transliterate && lang === "h";
  useEffect(() => {
    if (PREVIEW || !text.trim() || text.length > MAX_CHARS) return setReadAsPreview(null);
    const t = window.setTimeout(() => {
      readAs(text, translitOn).then((r) => setReadAsPreview(r.changed ? r.text : null), () => setReadAsPreview(null));
    }, 500);
    return () => clearTimeout(t);
  }, [text, translitOn]);
  // [word](say-as) highlighted behind the textarea (same font/padding/wrapping, scroll kept in sync)
  const highlighted = useMemo(() => {
    const out: React.ReactNode[] = [];
    let pos = 0;
    for (const m of text.matchAll(INLINE_PRON)) {
      out.push(text.slice(pos, m.index));
      out.push(
        <mark key={m.index} className="rounded-sm bg-brand/15 text-transparent ring-1 ring-brand/35">
          {m[0]}
        </mark>,
      );
      pos = m.index + m[0].length;
    }
    if (!out.length) return null;
    out.push(text.slice(pos) + "\n");
    return out;
  }, [text]);
  const currentStyle = STYLES.find((st) => st.id === style) ?? null;
  const pickStyle = (id: string | null) => {
    setStyle(id);
    const st = STYLES.find((x) => x.id === id);
    const own = id ? findVoice(voice)?.studio?.styleSpeed[id] : undefined; // e.g. Veer reads Energetic reel at 1.08×
    if (st) (setSpeed(own ?? st.speed), setNormalize(true), setLufs(st.lufs));
  };
  const looksHinglish = !PREVIEW && lang === "h" && !transliterate && text.trim().length > 12 && latinShare(text) > 0.6;

  const toJob = useCallback((u: JobStatus): Job => {
    const studio = u.stage ? { stage: u.stage, estimate: u.estimate_sec } : undefined;
    if (u.status === "queued") return { state: "queued", position: u.position || 1, studio };
    if (u.status === "running") return { state: "running", progress: u.progress, studio };
    if (u.status === "error") return { state: "error", message: u.error || "Something went wrong while generating." };
    const r = lastReq.current;
    return {
      state: "done",
      url: u.urls?.mp3 ?? u.url!,
      urls: u.urls,
      duration: u.duration_sec ?? 0,
      voice: r.voice,
      lufs: u.loudness?.target_lufs ?? r.lufs,
      format: r.format,
    };
  }, []);

  const authFailed = useCallback(() => {
    toast.error("Your session ended", { description: "Please sign in again." });
    navigate("/login?next=%2Fgenerate", { replace: true });
  }, [navigate]);

  // Follow a job until it finishes (also resumes after navigating away and back).
  const track = useCallback(
    async (id: string) => {
      poll.current?.abort();
      const ac = new AbortController();
      poll.current = ac;
      rememberJob(id);
      try {
        const s = await pollJob(id, (u) => setJob(toJob(u)), ac.signal);
        rememberJob(null);
        setRecentKey((k) => k + 1);
        refreshUsage();
        if (s.status === "done") toast.success("Voiceover ready", { description: "Saved to History for 7 days." });
        else toast.error("Generation failed", { description: s.error });
      } catch (e) {
        if (ac.signal.aborted) return;
        rememberJob(null);
        if (e instanceof ApiError && e.status === 401) return authFailed();
        setJob({ state: "error", message: e instanceof ApiError ? e.message : "Lost track of this voiceover. Check History." });
      }
    },
    [toJob, authFailed],
  );

  useEffect(() => {
    if (PREVIEW) return;
    const id = rememberedJob();
    if (id) {
      setJob({ state: "queued", position: 1 });
      void track(id);
    }
  }, [track]);

  const voices = useMemo(() => allVoices.filter((v) => v.lang === lang), [allVoices, lang]);
  const current: Voice = allVoices.find((v) => v.id === voice) ?? VOICES[0];
  const maxChars = current.studio?.maxChars ?? MAX_CHARS;
  const chars = text.length;
  const over = chars > maxChars;
  const busy = job.state === "queued" || job.state === "running";
  const canGenerate = chars > 0 && !over && !busy;

  const pickLang = (l: Lang) => {
    setLang(l);
    if (current.lang !== l) setVoice(VOICES.find((v) => v.lang === l)!.id);
    if (l !== "h") setTransliterate(false);
  };
  const pickVoice = useCallback((id: string) => {
    const v = findVoice(id);
    if (!v) return;
    setLang(v.lang);
    setVoice(id);
    const st = v.studio?.defaultStyle ? STYLES.find((x) => x.id === v.studio!.defaultStyle) : undefined;
    if (st) {
      // A studio voice brings its own style + pace (Veer: Energetic reel at 1.08×); still changeable below.
      setStyle(st.id);
      setSpeed(v.studio!.styleSpeed[st.id] ?? st.speed);
      setNormalize(true);
      setLufs(st.lufs);
    }
  }, []);
  // Studio voices arrive from the API after the first render: restore one picked via ?voice= or the saved draft.
  useEffect(() => {
    const id = wantedVoice.current;
    if (id && findVoice(id)?.studio) {
      wantedVoice.current = null;
      if (voice !== id) pickVoice(id);
    }
  }, [allVoices, voice, pickVoice]);

  const generate = useCallback(async () => {
    if (!canGenerate) {
      if (chars === 0) toast.error("Add some text first", { description: "Type or paste your script in the editor." });
      return;
    }
    if (!PREVIEW) {
      lastReq.current = { voice, format, lufs: normalize ? lufs : null };
      setJob({ state: "queued", position: 1 });
      try {
        const s = await createJob({ text, voice, lang, speed, format, normalize, loudness_lufs: lufs, transliterate: translitOn, style });
        setJob(toJob(s));
        if (s.status === "queued" || s.status === "running") void track(s.id);
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(0, "Couldn't start this voiceover.");
        if (err.status === 401) return authFailed();
        setJob({ state: "error", message: err.message });
        toast.error(err.status === 429 ? "Please wait a moment" : "Couldn't start this voiceover", { description: err.message });
      }
      return;
    }
    // Preview only: simulates the API job lifecycle (queued → running → done).
    timers.current.forEach(clearTimeout);
    const at = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));
    setJob({ state: "queued", position: 2 });
    at(900, () => setJob({ state: "queued", position: 1 }));
    for (let i = 0; i <= 20; i++) at(1800 + i * 140, () => setJob({ state: "running", progress: i / 20 }));
    at(1800 + 21 * 140, () => {
      const demo = lang === "h" ? "demo-hi" : "demo-en";
      setJob({
        state: "done",
        url: sampleUrl(demo),
        duration: lang === "h" ? 11.23 : 7.5,
        voice: lang === "h" ? "hf_alpha" : "am_michael",
        lufs: normalize ? lufs : null,
        format,
      });
      toast.success("Voiceover ready", { description: "Saved to History for 7 days." });
    });
  }, [canGenerate, chars, lang, normalize, lufs, format, text, voice, speed, translitOn, style, toJob, track, authFailed]);

  // ⌘/Ctrl + Enter generates from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") (e.preventDefault(), void generate());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [generate]);

  // Preview-only state switcher, so every state can be reviewed.
  const showState = (s: Job["state"]) => {
    timers.current.forEach(clearTimeout);
    if (s === "idle") setJob({ state: "idle" });
    if (s === "queued") setJob({ state: "queued", position: 2 });
    if (s === "running") setJob({ state: "running", progress: 0.45 });
    if (s === "done")
      setJob({ state: "done", url: sampleUrl("demo-hi"), duration: 11.23, voice: "hf_alpha", lufs: -14, format: "mp3" });
    if (s === "error") {
      setJob({ state: "error", message: "The voice engine is restarting. Your text is safe. Try again in a few seconds." });
      toast.error("Generation failed", { description: "The voice engine is restarting. Try again in a few seconds." });
    }
  };

  return (
    <AppShell title="Generate" onPickVoice={pickVoice}>
      <div className="mx-auto grid max-w-[1400px] gap-5 p-3 sm:p-5 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-6 lg:p-6 lg:pb-24">
        {/* ── Editor + result ─────────────────────────────────────────── */}
        <section aria-label="Script" className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-col rounded-2xl border bg-surface shadow-md">
            <div className="flex items-center gap-2 border-b px-4 py-2.5">
              <span className="text-sm font-medium">Script</span>
              <Badge variant="outline" className="font-normal text-muted-foreground">
                {langLabel(lang)}
              </Badge>
              <div className="ml-auto flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon-sm" onClick={() => setText(SAMPLE_TEXT)} aria-label="Insert sample script">
                      <Sparkles />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Insert sample script</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setText("");
                        editor.current?.focus();
                      }}
                      aria-label="Clear script"
                      disabled={!text}
                    >
                      <Eraser />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Clear</TooltipContent>
                </Tooltip>
              </div>
            </div>
            <label htmlFor="script" className="sr-only">
              Script text
            </label>
            <div className="relative flex flex-1 flex-col">
              {highlighted && (
                <div
                  ref={backdrop}
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 overflow-hidden px-4 py-4 text-[15px] leading-7 break-words whitespace-pre-wrap text-transparent [scrollbar-gutter:stable]"
                >
                  {highlighted}
                </div>
              )}
            <textarea
              id="script"
              ref={editor}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onScroll={(e) => {
                if (backdrop.current) backdrop.current.scrollTop = e.currentTarget.scrollTop;
              }}
              placeholder="Type or paste your script… e.g. “Raat 11 baje customer ne call kiya…” or Devanagari: “रात 11 बजे…”"
              aria-describedby="char-count"
              aria-invalid={over}
              spellCheck={false}
              className="relative min-h-[240px] w-full flex-1 resize-y bg-transparent px-4 py-4 text-[15px] leading-7 outline-none [scrollbar-gutter:stable] placeholder:text-subtle-foreground focus-visible:outline-none sm:min-h-[320px] lg:min-h-[380px]"
            />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-xs text-muted-foreground">
              <span id="char-count" className={cn("font-mono tabular", over && "font-medium text-danger")} aria-live="polite">
                {chars.toLocaleString("en-IN")} / {maxChars.toLocaleString("en-IN")}
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="size-3.5" aria-hidden="true" />≈ <span className="font-mono tabular">{fmtTime(estimateSeconds(chars, speed))}</span>{" "}
                audio
                {current.studio && chars > 0 && (
                  <>
                    {" "}· about <span className="font-mono tabular">{fmtWait(studioEstimate(current, chars, speed))}</span> to make
                  </>
                )}
              </span>
              {over && (
                <span className="flex items-center gap-1 text-danger">
                  <AlertCircle className="size-3.5" aria-hidden="true" />
                  {(chars - maxChars).toLocaleString("en-IN")} characters over the limit
                  {current.studio && ` (${current.name} is a studio voice: up to ${maxChars.toLocaleString("en-IN")} per voiceover)`}
                </span>
              )}
              <span className="flex items-center gap-3">
                <a href="https://aiwazz.in/learn/writing-scripts/" target="_blank" rel="noopener" className="underline-offset-2 hover:text-foreground hover:underline">
                  Script tips
                </a>
                <a href="https://aiwazz.in/learn/hindi-and-hinglish/" target="_blank" rel="noopener" className="underline-offset-2 hover:text-foreground hover:underline">
                  Hindi guide
                </a>
                <Link to="/settings#pronunciations" className="flex items-center gap-1 underline-offset-2 hover:text-foreground hover:underline" title="Fix how a word is said: [word](say it as) in the script, or your list in Settings">
                  <BookA className="size-3.5" aria-hidden="true" /> Pronunciations
                </Link>
              </span>
              <span className="ml-auto hidden items-center gap-1 sm:flex">
                <kbd className="rounded border bg-surface-2 px-1.5 font-mono text-[10px]">⌘</kbd>
                <kbd className="rounded border bg-surface-2 px-1.5 font-mono text-[10px]">↵</kbd> to generate
              </span>
            </div>
          </div>

          {looksHinglish && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-brand/30 bg-brand/5 px-4 py-3 text-sm">
              <Languages className="size-4 shrink-0 text-brand" aria-hidden="true" />
              <span className="min-w-0 flex-1">Looks like Hinglish in Roman letters. Turn on transliteration so the Hindi voice reads it naturally.</span>
              <Button size="sm" variant="outline" onClick={() => setTransliterate(true)}>
                Turn on
              </Button>
            </div>
          )}
          {readAsPreview && (
            <div className="rounded-xl border bg-surface px-4 py-3">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Will be read as</p>
              <p className="mt-1.5 line-clamp-4 text-[15px] leading-7" lang={lang === "h" ? "hi" : "en"}>
                {readAsPreview}
              </p>
            </div>
          )}
          {current.studio && (
            <p className="flex items-start gap-2 rounded-xl border bg-surface px-4 py-3 text-xs leading-5 text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden="true" />
              <span>
                <span className="font-medium text-foreground">{current.name}</span> is a studio voice
                {current.studio.isPublic ? "" : " (private to your account)"}. It takes about 2½ times as long as the other
                voices on our CPU: a 60-second reel ≈ 2½ minutes. Up to {maxChars.toLocaleString("en-IN")} characters per voiceover.
              </span>
            </p>
          )}
          <ResultPanel job={job} onRetry={() => void generate()} reduce={!!reduce} />
          {!PREVIEW && <RecentList refreshKey={recentKey} />}
        </section>

        {/* ── Settings panel ─────────────────────────────────────────── */}
        <aside aria-label="Voice settings" className="flex flex-col gap-5 lg:sticky lg:top-20 lg:self-start">
          <div className="space-y-6 rounded-2xl border bg-surface p-4 shadow-md sm:p-5">
            <Field label="Language">
              <ToggleGroup
                type="single"
                value={lang}
                onValueChange={(v) => v && pickLang(v as Lang)}
                variant="outline"
                className="grid w-full grid-cols-3"
                aria-label="Language"
              >
                {LANGS.map((l) => (
                  <ToggleGroupItem key={l.id} value={l.id} className="h-9 text-xs data-[state=on]:bg-surface-3 data-[state=on]:text-foreground">
                    {l.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Field>

            <Field label="Voice" hint={`${voices.length} voices`}>
              <div role="radiogroup" aria-label="Voice" className="grid grid-cols-[minmax(0,1fr)] gap-2">
                {loadingVoices
                  ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[62px] rounded-xl" />)
                  : voices.map((v) => <VoiceCard key={v.id} voice={v} checked={voice === v.id} onSelect={pickVoice} />)}
              </div>
            </Field>

            <Field label="Style" hint={currentStyle ? undefined : "optional"}>
              <ToggleGroup
                type="single"
                value={style ?? ""}
                onValueChange={(v) => pickStyle(v || null)}
                variant="outline"
                className="grid w-full grid-cols-2"
                aria-label="Speaking style"
              >
                {STYLES.map((st) => (
                  <ToggleGroupItem key={st.id} value={st.id} className="h-9 text-xs data-[state=on]:border-brand/50 data-[state=on]:bg-brand/10 data-[state=on]:text-foreground">
                    {st.name}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              <p className="text-xs leading-5 text-muted-foreground">
                {currentStyle ? (
                  <>
                    {currentStyle.description} {(current.studio?.styleSpeed[currentStyle.id] ?? currentStyle.speed).toFixed(2)}×,{" "}
                    {currentStyle.pauses}, {currentStyle.lufs} LUFS.{" "}
                    {!current.studio && voice !== currentStyle.suggestedVoice && (
                      <button type="button" className="font-medium text-brand underline-offset-2 hover:underline" onClick={() => pickVoice(currentStyle.suggestedVoice)}>
                        Try it with {VOICES.find((v) => v.id === currentStyle.suggestedVoice)!.name}
                      </button>
                    )}
                  </>
                ) : (
                  "Sets pace, pauses and loudness in one tap. Works with every voice; tap again to turn it off."
                )}
              </p>
            </Field>

            <Field label="Speed" htmlFor="speed" hint={`${speed.toFixed(2)}×`}>
              <Slider
                id="speed"
                min={0.7}
                max={1.3}
                step={0.05}
                value={[speed]}
                onValueChange={([v]) => setSpeed(v)}
                aria-label="Speed"
                aria-valuetext={`${speed.toFixed(2)} times`}
              />
              <div className="flex justify-between font-mono text-[11px] text-subtle-foreground">
                <span>0.7×</span>
                <button type="button" className="rounded hover:text-foreground" onClick={() => setSpeed(1)}>
                  1.0×
                </button>
                <span>1.3×</span>
              </div>
            </Field>

            <div className="flex items-start justify-between gap-4 rounded-xl border bg-surface-2/50 p-3">
              <div className="space-y-1">
                <Label htmlFor="translit" className="flex items-center gap-2 text-sm">
                  <Languages className="size-4 text-brand" aria-hidden="true" />
                  Transliterate Hinglish
                </Label>
                <p id="translit-hint" className="text-xs leading-5 text-muted-foreground">
                  {lang === "h"
                    ? "Type Hindi in Roman letters: “Raat 11 baje” → “रात 11 बजे”. English words stay as they are."
                    : "Available for Hindi voices."}
                </p>
              </div>
              <Switch
                id="translit"
                checked={transliterate}
                onCheckedChange={setTransliterate}
                disabled={lang !== "h"}
                aria-describedby="translit-hint"
              />
            </div>

            <Collapsible>
              <CollapsibleTrigger className="group flex w-full items-center justify-between rounded-lg text-xs font-medium tracking-wide text-muted-foreground uppercase hover:text-foreground">
                <span className="flex items-center gap-2">
                  <Gauge className="size-3.5" aria-hidden="true" />
                  Output &amp; loudness
                </span>
                <span className="flex items-center gap-2 font-mono normal-case tracking-normal">
                  {format.toUpperCase()} · {normalize ? `${lufs} LUFS` : "off"}
                  <ChevronDown className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </span>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-5 pt-4">
                <Field label="Format" hint="48 kHz">
                  <ToggleGroup
                    type="single"
                    value={format}
                    onValueChange={(v) => v && setFormat(v as "mp3" | "wav")}
                    variant="outline"
                    className="grid w-full grid-cols-2"
                    aria-label="Format"
                  >
                    <ToggleGroupItem value="mp3" className="h-9 text-xs data-[state=on]:bg-surface-3">
                      MP3 · 192 kbps
                    </ToggleGroupItem>
                    <ToggleGroupItem value="wav" className="h-9 text-xs data-[state=on]:bg-surface-3">
                      WAV · 16-bit
                    </ToggleGroupItem>
                  </ToggleGroup>
                </Field>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="normalize" className="text-sm">
                      Loudness normalization
                    </Label>
                    <Switch id="normalize" checked={normalize} onCheckedChange={setNormalize} />
                  </div>
                  <ToggleGroup
                    type="single"
                    value={String(lufs)}
                    onValueChange={(v) => v && setLufs(Number(v))}
                    variant="outline"
                    disabled={!normalize}
                    className="grid w-full grid-cols-4"
                    aria-label="Loudness target (LUFS)"
                  >
                    {LOUDNESS.map((o) => (
                      <ToggleGroupItem key={o.v} value={String(o.v)} className="h-9 font-mono text-xs data-[state=on]:bg-surface-3" title={o.hint}>
                        {o.label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                  <p className="flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">
                    <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    {normalize
                      ? `${LOUDNESS.find((o) => o.v === lufs)?.hint}. Peaks kept under -1 dBTP, silence trimmed to 100 ms.`
                      : "Raw voice level. Silence is still trimmed."}
                  </p>
                </div>
              </CollapsibleContent>
            </Collapsible>

            {/* Desktop generate button; mobile uses the sticky bar below */}
            <Button variant="brand" size="xl" className={cn("hidden w-full lg:flex", busy && "disabled:opacity-100")} aria-busy={busy} onClick={() => void generate()} disabled={!canGenerate} aria-keyshortcuts="Control+Enter Meta+Enter">
              {busy ? <AudioLines className="animate-pulse" /> : <Wand2 />}
              {busy ? "Generating…" : "Generate voiceover"}
            </Button>
          </div>
        </aside>
      </div>

      {/* Mobile sticky action bar */}
      <div className="glass fixed inset-x-0 bottom-0 z-30 border-t p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
        <div className="flex items-center gap-3">
          <div className="min-w-0 text-xs">
            <p className="truncate font-medium">
              {current.name} · {langLabel(lang)}
              {currentStyle && ` · ${currentStyle.name}`}
            </p>
            <p className="font-mono text-muted-foreground tabular">
              {chars.toLocaleString("en-IN")} chars · {speed.toFixed(2)}×
            </p>
          </div>
          <Button variant="brand" size="xl" className={cn("ml-auto flex-1 sm:flex-none", busy && "disabled:opacity-100")} aria-busy={busy} onClick={() => void generate()} disabled={!canGenerate}>
            {busy ? <AudioLines className="animate-pulse" /> : <Wand2 />}
            {busy ? "Generating…" : "Generate"}
          </Button>
        </div>
      </div>

      {PREVIEW && <PreviewStateBar current={job.state} onPick={showState} />}
    </AppShell>
  );
}

function ResultPanel({ job, onRetry, reduce }: { job: Job; onRetry: () => void; reduce: boolean }) {
  const anim = reduce
    ? {}
    : { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -6 }, transition: { duration: 0.2 } };
  return (
    <div className="rounded-2xl border bg-surface shadow-md" aria-live="polite">
      <AnimatePresence mode="wait" initial={false}>
        {job.state === "idle" && (
          <motion.div key="idle" {...anim} className="flex flex-col items-center gap-3 px-6 py-10 text-center">
            <LiveWaveform mode="static" bars={32} className="h-10 max-w-[220px] opacity-60" />
            <p className="text-sm font-medium">Your voiceover will appear here</p>
            <p className="max-w-sm text-xs leading-5 text-muted-foreground">
              Pick a voice, press <span className="font-mono">Generate</span>. A 60-second script takes about a minute on our CPU.
            </p>
          </motion.div>
        )}

        {(job.state === "queued" || job.state === "running") && (
          <motion.div key="busy" {...anim} className="space-y-4 p-5">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
                  <span className="relative inline-flex size-2 rounded-full bg-primary" />
                </span>
                {job.studio?.stage === "studio-queue"
                  ? "Waiting for the studio voice"
                  : job.studio?.stage === "studio"
                    ? "Converting to the studio voice"
                    : job.state === "queued"
                      ? "Waiting in queue"
                      : "Synthesizing voice"}
              </span>
              <span className="font-mono text-xs text-muted-foreground tabular">
                {job.state === "queued" ? `position ${job.position}` : `${Math.round(job.progress * 100)}%`}
              </span>
            </div>
            <LiveWaveform mode="active" bars={64} className="h-16" progress={job.state === "running" ? job.progress : 0} />
            <Progress value={job.state === "running" ? job.progress * 100 : 4} aria-label="Generation progress" className="h-1" />
            <p className="text-xs text-muted-foreground">
              {job.studio?.estimate
                ? `Studio voice: about ${fmtWait(job.studio.estimate)} in total once it starts. You can leave this page; it keeps going and lands in History.`
                : job.state === "queued"
                  ? "One voiceover is rendered at a time. Yours starts right after the current one."
                  : "Splitting sentences, synthesizing, then leveling to your loudness target…"}
            </p>
          </motion.div>
        )}

        {job.state === "done" && <DoneView key="done" job={job} anim={anim} />}

        {job.state === "error" && (
          <motion.div key="error" {...anim} className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-danger/10 text-danger">
              <AlertCircle className="size-[18px]" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">Couldn’t generate this voiceover</p>
              <p className="text-xs leading-5 text-muted-foreground">{job.message}</p>
            </div>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DoneView({ job, anim }: { job: Extract<Job, { state: "done" }>; anim: object }) {
  const [copied, setCopied] = useState(false);
  useVoices();
  const v = findVoice(job.voice) ?? { name: job.voice, lang: "h" as Lang };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(new URL(job.url, location.href).href);
      setCopied(true);
      toast.success("Link copied");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy the link");
    }
  };
  return (
    <motion.div {...anim} className="space-y-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Check className="size-4 text-success" aria-hidden="true" /> Ready
        </span>
        <span className="text-xs text-muted-foreground">
          {v.name} · {langLabel(v.lang)}
        </span>
        <span className="ml-auto flex gap-1.5 font-mono text-[11px] text-muted-foreground">
          <span className="rounded-md border px-1.5 py-0.5 tabular">{fmtTime(job.duration)}</span>
          <span className="rounded-md border px-1.5 py-0.5 tabular">{job.lufs !== null ? `${job.lufs} LUFS` : "raw level"}</span>
          <span className="rounded-md border px-1.5 py-0.5">48 kHz</span>
        </span>
      </div>
      <WaveformPlayer url={job.url} label="voiceover" />
      <div className="flex flex-wrap gap-2">
        {(["mp3", "wav"] as const).map((f) => (
          <Button key={f} asChild variant={job.format === f ? "default" : "outline"} size="sm">
            <a href={job.urls ? downloadUrl(job.urls[f]) : job.url} download>
              <Download /> {f.toUpperCase()}
            </a>
          </Button>
        ))}
        <Button variant="ghost" size="sm" onClick={copy}>
          {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy link"}
        </Button>
      </div>
    </motion.div>
  );
}

function PreviewStateBar({ current, onPick }: { current: Job["state"]; onPick: (s: Job["state"]) => void }) {
  const states: Job["state"][] = ["idle", "queued", "running", "done", "error"];
  return (
    <div className="glass mx-3 mb-28 flex flex-wrap items-center justify-center gap-1 rounded-2xl border p-1 text-xs shadow-lg sm:mx-5 lg:fixed lg:bottom-5 lg:left-1/2 lg:z-40 lg:mx-0 lg:mb-0 lg:-translate-x-1/2 lg:flex-nowrap lg:rounded-full">
      <span className="w-full px-2 py-1 text-center text-subtle-foreground lg:w-auto lg:py-0">Preview states</span>
      {states.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          aria-pressed={current === s}
          className={cn(
            "rounded-full px-2.5 py-1 capitalize transition-colors",
            current === s ? "bg-foreground text-background" : "text-muted-foreground hover:bg-surface-3 hover:text-foreground",
          )}
        >
          {s === "idle" ? "empty" : s}
        </button>
      ))}
    </div>
  );
}

function RecentList({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const { playing, toggle } = usePreviewPlayer();
  useEffect(() => {
    getHistory(3).then(setItems, () => setItems([]));
  }, [refreshKey]);
  if (items && items.length === 0) return null;
  return (
    <section aria-labelledby="recent-title" className="rounded-2xl border bg-surface shadow-md">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <h2 id="recent-title" className="font-sans text-sm font-medium">Recent</h2>
        <Link to="/history" className="text-xs text-muted-foreground hover:text-foreground">
          View all
        </Link>
      </div>
      <ul className="divide-y">
        {items === null
          ? Array.from({ length: 2 }, (_, i) => (
              <li key={i} className="p-3">
                <Skeleton className="h-9" />
              </li>
            ))
          : items.map((it) => {
              const v = findVoice(it.voice);
              const on = playing === it.id;
              return (
                <li key={it.id} className="flex items-center gap-3 px-4 py-2.5">
                  <button
                    type="button"
                    disabled={!it.available}
                    onClick={() => it.urls && toggle(it.id, it.urls.mp3)}
                    aria-label={on ? "Pause" : `Play: ${it.text_excerpt}`}
                    className="grid size-8 shrink-0 place-items-center rounded-full border bg-surface-2 text-muted-foreground transition-colors hover:bg-surface-3 hover:text-foreground disabled:opacity-40"
                  >
                    {on ? <Pause className="size-3.5 fill-current" /> : <Play className="ml-0.5 size-3.5 fill-current" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{it.text_excerpt}</p>
                    <p className="text-xs text-muted-foreground">
                      {v?.name ?? it.voice} · {it.status === "done" ? fmtDuration(it.duration_sec) : it.status} · {timeAgo(it.created_at)}
                    </p>
                  </div>
                </li>
              );
            })}
      </ul>
    </section>
  );
}
