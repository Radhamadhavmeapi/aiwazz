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
  Sparkles,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell/app-shell";
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
import { cn } from "@/lib/utils";
import { langLabel, LANGS, sampleUrl, VOICES, type Lang } from "@/lib/voices";

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
  | { state: "queued"; position: number }
  | { state: "running"; progress: number }
  | { state: "done"; url: string; duration: number; voice: string; lufs: number | null; format: "mp3" | "wav" }
  | { state: "error"; message: string };

// ~14 chars/s of speech for Hindi, ~15 for English at speed 1.0
const estimateSeconds = (chars: number, speed: number) => Math.round(chars / 14.5 / speed);

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
  const [text, setText] = useState(SAMPLE_TEXT);
  const [lang, setLang] = useState<Lang>("h");
  const [voice, setVoice] = useState("hf_alpha");
  const [speed, setSpeed] = useState(1);
  const [transliterate, setTransliterate] = useState(false);
  const [format, setFormat] = useState<"mp3" | "wav">("mp3");
  const [normalize, setNormalize] = useState(true);
  const [lufs, setLufs] = useState(-14);
  const [loadingVoices, setLoadingVoices] = useState(true);
  const [job, setJob] = useState<Job>({ state: "idle" });
  const timers = useRef<number[]>([]);
  const editor = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setLoadingVoices(false), 450); // preview: skeleton state
    return () => clearTimeout(t);
  }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const voices = useMemo(() => VOICES.filter((v) => v.lang === lang), [lang]);
  const current = VOICES.find((v) => v.id === voice)!;
  const chars = text.length;
  const over = chars > MAX_CHARS;
  const busy = job.state === "queued" || job.state === "running";
  const canGenerate = chars > 0 && !over && !busy;

  const pickLang = (l: Lang) => {
    setLang(l);
    if (current.lang !== l) setVoice(VOICES.find((v) => v.lang === l)!.id);
    if (l !== "h") setTransliterate(false);
  };
  const pickVoice = useCallback((id: string) => {
    const v = VOICES.find((x) => x.id === id)!;
    setLang(v.lang);
    setVoice(id);
  }, []);

  // Preview only: simulates the API job lifecycle (queued → running → done).
  const generate = useCallback(() => {
    if (!canGenerate) {
      if (chars === 0) toast.error("Add some text first", { description: "Type or paste your script in the editor." });
      return;
    }
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
  }, [canGenerate, chars, lang, normalize, lufs, format]);

  // ⌘/Ctrl + Enter generates from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") (e.preventDefault(), generate());
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
            <textarea
              id="script"
              ref={editor}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type or paste your script… e.g. “Raat 11 baje customer ne call kiya…” or Devanagari: “रात 11 बजे…”"
              aria-describedby="char-count"
              aria-invalid={over}
              spellCheck={false}
              className="min-h-[240px] w-full flex-1 resize-y bg-transparent px-4 py-4 text-[15px] leading-7 outline-none placeholder:text-subtle-foreground focus-visible:outline-none sm:min-h-[320px] lg:min-h-[380px]"
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-xs text-muted-foreground">
              <span id="char-count" className={cn("font-mono tabular", over && "font-medium text-danger")} aria-live="polite">
                {chars.toLocaleString("en-IN")} / {MAX_CHARS.toLocaleString("en-IN")}
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="size-3.5" aria-hidden="true" />≈ <span className="font-mono tabular">{fmtTime(estimateSeconds(chars, speed))}</span>{" "}
                audio
              </span>
              {over && (
                <span className="flex items-center gap-1 text-danger">
                  <AlertCircle className="size-3.5" aria-hidden="true" />
                  {(chars - MAX_CHARS).toLocaleString("en-IN")} characters over the limit
                </span>
              )}
              <span className="ml-auto hidden items-center gap-1 sm:flex">
                <kbd className="rounded border bg-surface-2 px-1.5 font-mono text-[10px]">⌘</kbd>
                <kbd className="rounded border bg-surface-2 px-1.5 font-mono text-[10px]">↵</kbd> to generate
              </span>
            </div>
          </div>

          <ResultPanel job={job} onRetry={generate} reduce={!!reduce} />
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
              <div role="radiogroup" aria-label="Voice" className="grid gap-2">
                {loadingVoices
                  ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[62px] rounded-xl" />)
                  : voices.map((v) => <VoiceCard key={v.id} voice={v} checked={voice === v.id} onSelect={setVoice} />)}
              </div>
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
                    ? "“Raat 11 baje” → “रात 11 बजे”. English words stay as they are."
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
            <Button variant="brand" size="xl" className={cn("hidden w-full lg:flex", busy && "disabled:opacity-100")} aria-busy={busy} onClick={generate} disabled={!canGenerate} aria-keyshortcuts="Control+Enter Meta+Enter">
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
            </p>
            <p className="font-mono text-muted-foreground tabular">
              {chars.toLocaleString("en-IN")} chars · {speed.toFixed(2)}×
            </p>
          </div>
          <Button variant="brand" size="xl" className={cn("ml-auto flex-1 sm:flex-none", busy && "disabled:opacity-100")} aria-busy={busy} onClick={generate} disabled={!canGenerate}>
            {busy ? <AudioLines className="animate-pulse" /> : <Wand2 />}
            {busy ? "Generating…" : "Generate"}
          </Button>
        </div>
      </div>

      <PreviewStateBar current={job.state} onPick={showState} />
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
                {job.state === "queued" ? "Waiting in queue" : "Synthesizing voice"}
              </span>
              <span className="font-mono text-xs text-muted-foreground tabular">
                {job.state === "queued" ? `position ${job.position}` : `${Math.round(job.progress * 100)}%`}
              </span>
            </div>
            <LiveWaveform mode="active" bars={64} className="h-16" progress={job.state === "running" ? job.progress : 0} />
            <Progress value={job.state === "running" ? job.progress * 100 : 4} aria-label="Generation progress" className="h-1" />
            <p className="text-xs text-muted-foreground">
              {job.state === "queued"
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
  const v = VOICES.find((x) => x.id === job.voice)!;
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
        <Button asChild variant={job.format === "mp3" ? "default" : "outline"} size="sm">
          <a href={job.url} download>
            <Download /> MP3
          </a>
        </Button>
        <Button asChild variant={job.format === "wav" ? "default" : "outline"} size="sm">
          <a href={job.url} download>
            <Download /> WAV
          </a>
        </Button>
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
