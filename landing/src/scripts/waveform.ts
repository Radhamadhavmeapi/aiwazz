// <aiwazz-wave bars="56" mode="idle|active|static" for="demo-hi">: brand-gradient bar waveform on canvas.
// Same look as the dashboard's LiveWaveform. Pauses off-screen / hidden tab; static with reduced motion.
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

class AiwazzWave extends HTMLElement {
  static observedAttributes = ["mode"];
  private canvas = document.createElement("canvas");
  private ctx = this.canvas.getContext("2d")!;
  private raf = 0;
  private visible = false;
  private seeds: { p: number; s: number; env: number }[] = [];
  private levels = new Float32Array(0);
  private colors = { stops: ["#51b2f6", "#2d36db", "#7420dd"] };
  private w = 0;
  private h = 0;
  private ro?: ResizeObserver;
  private io?: IntersectionObserver;

  connectedCallback() {
    this.canvas.setAttribute("aria-hidden", "true");
    this.canvas.style.cssText = "display:block;width:100%;height:100%";
    this.append(this.canvas);
    const n = Number(this.getAttribute("bars") || 48);
    this.seeds = Array.from({ length: n }, (_, i) => ({
      p: Math.random() * Math.PI * 2,
      s: 0.6 + Math.random() * 0.9,
      env: Math.sin((i / (n - 1)) * Math.PI) ** 0.8,
    }));
    this.levels = new Float32Array(n).fill(0.3);
    this.readColors();
    this.ro = new ResizeObserver(() => (this.resize(), this.start()));
    this.ro.observe(this);
    this.io = new IntersectionObserver(([e]) => ((this.visible = e.isIntersecting), this.start()));
    this.io.observe(this);
    window.addEventListener("aiwazz:theme", this.onTheme);
    document.addEventListener("visibilitychange", this.onVis);
  }
  disconnectedCallback() {
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    this.io?.disconnect();
    window.removeEventListener("aiwazz:theme", this.onTheme);
    document.removeEventListener("visibilitychange", this.onVis);
  }
  attributeChangedCallback() {
    this.start();
  }
  private onTheme = () => (this.readColors(), this.start());
  private onVis = () => this.start();
  private readColors() {
    const css = getComputedStyle(document.documentElement);
    this.colors.stops = ["--brand-sky", "--brand-indigo", "--brand-violet"].map((v, i) => css.getPropertyValue(v).trim() || this.colors.stops[i]);
  }
  private resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const r = this.getBoundingClientRect();
    this.w = r.width;
    this.h = r.height;
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  private start() {
    cancelAnimationFrame(this.raf);
    if (this.w) this.raf = requestAnimationFrame(this.draw);
  }
  private draw = (t: number) => {
    const mode = this.getAttribute("mode") || "idle";
    const still = mode === "static" || reduced();
    const { ctx, w, h, seeds, levels } = this;
    const n = seeds.length;
    ctx.clearRect(0, 0, w, h);
    const g = ctx.createLinearGradient(0, 0, w, 0);
    this.colors.stops.forEach((c, i, a) => g.addColorStop(i / (a.length - 1), c));
    ctx.fillStyle = g;
    const gap = w / n;
    const bw = Math.max(2, gap * 0.55);
    const time = t / 1000;
    for (let i = 0; i < n; i++) {
      const { p, s, env } = seeds[i];
      const target = still
        ? 0.25 + 0.6 * env * (0.6 + 0.4 * Math.sin(i * 1.7 + p))
        : mode === "active"
          ? 0.15 + 0.85 * env * Math.abs(Math.sin(time * 3.2 * s + p) * 0.7 + Math.sin(time * 7.1 * s + p * 2) * 0.3)
          : 0.18 + 0.5 * env * (0.55 + 0.45 * Math.sin(time * 1.1 * s + p));
      levels[i] += (target - levels[i]) * (still ? 1 : 0.18);
      const bh = Math.max(bw, levels[i] * h * 0.92);
      ctx.beginPath();
      ctx.roundRect(i * gap + (gap - bw) / 2, (h - bh) / 2, bw, bh, bw / 2);
      ctx.fill();
    }
    if (!still && this.visible && !document.hidden) this.raf = requestAnimationFrame(this.draw);
  };
}
customElements.define("aiwazz-wave", AiwazzWave);
