import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { Skeleton } from "@/components/ui/skeleton";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export const fmtTime = (s: number) => {
  const m = Math.floor(s / 60);
  return `${m}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
};

/** Waveform player (wavesurfer.js): gradient progress, keyboard accessible, mono timecode. */
export function WaveformPlayer({ url, className, label = "audio" }: { url: string; className?: string; label?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const { theme } = useTheme();
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);

  useEffect(() => {
    const css = getComputedStyle(document.documentElement);
    const v = (n: string) => css.getPropertyValue(n).trim();
    setReady(false);
    const w = WaveSurfer.create({
      container: box.current!,
      url,
      height: 56,
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      cursorWidth: 0,
      normalize: true,
      dragToSeek: true,
      waveColor: v("--border-strong"),
      progressColor: [v("--brand-violet"), v("--brand-cyan")],
    });
    w.on("ready", (d) => {
      setDur(d);
      setReady(true);
    });
    w.on("timeupdate", setTime);
    w.on("play", () => setPlaying(true));
    w.on("pause", () => setPlaying(false));
    w.on("finish", () => setPlaying(false));
    ws.current = w;
    return () => w.destroy();
  }, [url, theme]);

  return (
    <div className={cn("flex items-center gap-4", className)}>
      <button
        type="button"
        onClick={() => ws.current?.playPause()}
        disabled={!ready}
        aria-label={playing ? `Pause ${label}` : `Play ${label}`}
        className="grid size-11 shrink-0 place-items-center rounded-full bg-foreground text-background shadow-md transition-transform duration-150 hover:scale-105 active:scale-95 disabled:opacity-50"
      >
        {playing ? <Pause className="size-[18px] fill-current" /> : <Play className="ml-0.5 size-[18px] fill-current" />}
      </button>
      <div className="relative min-w-0 flex-1">
        {!ready && <Skeleton className="absolute inset-x-0 top-1/2 h-10 -translate-y-1/2" />}
        <div
          ref={box}
          className={cn("transition-opacity duration-200", ready ? "opacity-100" : "opacity-0")}
          role="slider"
          tabIndex={ready ? 0 : -1}
          aria-label={`Seek ${label}`}
          aria-valuemin={0}
          aria-valuemax={Math.round(dur)}
          aria-valuenow={Math.round(time)}
          aria-valuetext={`${fmtTime(time)} of ${fmtTime(dur)}`}
          onKeyDown={(e) => {
            const w = ws.current;
            if (!w) return;
            if (e.key === " " || e.key === "Enter") (e.preventDefault(), w.playPause());
            if (e.key === "ArrowRight") (e.preventDefault(), w.setTime(Math.min(dur, w.getCurrentTime() + 2)));
            if (e.key === "ArrowLeft") (e.preventDefault(), w.setTime(Math.max(0, w.getCurrentTime() - 2)));
          }}
        />
      </div>
      <span className="shrink-0 font-mono text-xs text-muted-foreground tabular">
        {fmtTime(time)} <span className="text-subtle-foreground">/ {fmtTime(dur)}</span>
      </span>
    </div>
  );
}
