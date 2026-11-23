import { useEffect, useRef } from "react";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

type Props = {
  /** "idle" = slow breathing, "active" = energetic (generating), "static" = no animation */
  mode?: "idle" | "active" | "static";
  bars?: number;
  className?: string;
  /** 0..1 portion of bars drawn in full gradient (rest muted), e.g. synthesis progress */
  progress?: number;
};

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/**
 * Canvas bar waveform in the brand gradient: the signature visual.
 * Pauses when off-screen or the tab is hidden; static under prefers-reduced-motion.
 */
export function LiveWaveform({ mode = "idle", bars = 48, className, progress = 1 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const { theme } = useTheme();
  const state = useRef({ mode, progress });
  state.current = { mode, progress };
  const startRef = useRef<() => void>(() => {});

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const css = getComputedStyle(document.documentElement);
    const violet = css.getPropertyValue("--brand-violet").trim() || "#8b5cf6";
    const cyan = css.getPropertyValue("--brand-cyan").trim() || "#22d3ee";
    const muted = css.getPropertyValue("--border-strong").trim() || "rgba(255,255,255,.14)";
    // Per-bar random phase/speed so it never looks like a loop.
    const seeds = Array.from({ length: bars }, (_, i) => ({
      p: Math.random() * Math.PI * 2,
      s: 0.6 + Math.random() * 0.9,
      env: Math.sin((i / (bars - 1)) * Math.PI) ** 0.8, // taller in the middle
    }));
    const levels = new Float32Array(bars).fill(0.3);
    let raf = 0;
    let visible = true;
    let w = 0;
    let h = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const r = canvas.getBoundingClientRect();
      w = r.width;
      h = r.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (t: number) => {
      const { mode: m, progress: prog } = state.current;
      const still = m === "static" || reducedMotion();
      ctx.clearRect(0, 0, w, h);
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0, violet);
      grad.addColorStop(1, cyan);
      const gap = w / bars;
      const bw = Math.max(2, gap * 0.55);
      const time = t / 1000;
      for (let i = 0; i < bars; i++) {
        const { p, s, env } = seeds[i];
        let target: number;
        if (still) target = 0.25 + 0.6 * env * (0.6 + 0.4 * Math.sin(i * 1.7 + p));
        else if (m === "active")
          target = 0.15 + 0.85 * env * Math.abs(Math.sin(time * 3.2 * s + p) * 0.7 + Math.sin(time * 7.1 * s + p * 2) * 0.3);
        else target = 0.18 + 0.5 * env * (0.55 + 0.45 * Math.sin(time * 1.1 * s + p));
        levels[i] += (target - levels[i]) * (still ? 1 : 0.18);
        const bh = Math.max(bw, levels[i] * h * 0.92);
        const x = i * gap + (gap - bw) / 2;
        ctx.fillStyle = i / bars < prog ? grad : muted;
        ctx.beginPath();
        ctx.roundRect(x, (h - bh) / 2, bw, bh, bw / 2);
        ctx.fill();
      }
      if (!still && visible && !document.hidden) raf = requestAnimationFrame(draw);
    };

    const start = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(draw);
    };
    startRef.current = start;
    const ro = new ResizeObserver(() => {
      resize();
      start();
    });
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible) start();
    });
    io.observe(canvas);
    const onVis = () => !document.hidden && start();
    document.addEventListener("visibilitychange", onVis);
    resize();
    start();
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [bars, theme]);

  // The loop stops itself when static; restart it on mode/progress changes.
  useEffect(() => startRef.current(), [mode, progress]);

  return <canvas ref={ref} aria-hidden="true" className={cn("block h-24 w-full", className)} />;
}
