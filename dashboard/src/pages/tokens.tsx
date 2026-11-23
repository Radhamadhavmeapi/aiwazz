import { ArrowLeft, Download, Wand2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { WaveformPlayer } from "@/components/audio/waveform-player";
import { VoiceCard } from "@/components/audio/voice-card";
import { LiveWaveform } from "@/components/brand/live-waveform";
import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/app-shell/topbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useTheme } from "@/lib/theme";
import { sampleUrl, VOICES } from "@/lib/voices";

const COLORS: { name: string; v: string; note?: string }[] = [
  { name: "background", v: "--background" },
  { name: "surface", v: "--surface", note: "cards, sidebar" },
  { name: "surface-2", v: "--surface-2", note: "inputs, popovers" },
  { name: "surface-3", v: "--surface-3", note: "hover" },
  { name: "foreground", v: "--foreground" },
  { name: "muted-foreground", v: "--muted-foreground" },
  { name: "subtle-foreground", v: "--subtle-foreground" },
  { name: "brand-violet", v: "--brand-violet" },
  { name: "brand-cyan", v: "--brand-cyan" },
  { name: "brand-text", v: "--brand-text" },
  { name: "danger", v: "--danger" },
  { name: "success", v: "--success" },
  { name: "warning", v: "--warning" },
];

// WCAG contrast of a CSS color against the page background, computed in the browser.
function useContrast(fg: string, bg = "--background") {
  const { theme } = useTheme();
  const [r, setR] = useState<number | null>(null);
  useEffect(() => {
    const probe = document.createElement("canvas").getContext("2d")!;
    const rgb = (cssVar: string) => {
      probe.fillStyle = "#000";
      probe.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
      const h = probe.fillStyle as string; // normalized #rrggbb
      return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
    };
    const lum = (c: number[]) => {
      const [a, b, d] = c.map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
      return 0.2126 * a + 0.7152 * b + 0.0722 * d;
    };
    const [l1, l2] = [lum(rgb(fg)), lum(rgb(bg))].sort((a, b) => b - a);
    setR((l1 + 0.05) / (l2 + 0.05));
  }, [fg, bg, theme]);
  return r;
}

function Swatch({ name, v, note }: { name: string; v: string; note?: string }) {
  const ratio = useContrast(v);
  const { theme } = useTheme();
  const [hex, setHex] = useState("");
  useEffect(() => setHex(getComputedStyle(document.documentElement).getPropertyValue(v).trim()), [v, theme]);
  const textual = !["--background", "--surface", "--surface-2", "--surface-3"].includes(v);
  return (
    <div className="overflow-hidden rounded-xl border bg-surface">
      <div className="h-16 border-b" style={{ background: `var(${v})` }} />
      <div className="space-y-0.5 p-3">
        <p className="text-sm font-medium">{name}</p>
        <p className="font-mono text-xs text-muted-foreground">{hex}</p>
        <p className="text-xs text-subtle-foreground">
          {note ?? (textual && ratio ? `${ratio.toFixed(1)}:1 on background${ratio >= 4.5 ? " · AA" : ""}` : " ")}
        </p>
      </div>
    </div>
  );
}

function Section({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-h3 font-semibold">{title}</h2>
        {desc && <p className="mt-1 text-sm text-muted-foreground">{desc}</p>}
      </div>
      {children}
    </section>
  );
}

export default function TokensPage() {
  const [voice, setVoice] = useState("hf_alpha");
  const [sw, setSw] = useState(true);
  const [speed, setSpeed] = useState([1]);
  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      <header className="mb-10 flex items-center gap-3">
        <Button asChild variant="ghost" size="icon-sm" aria-label="Back to preview index">
          <Link to="/">
            <ArrowLeft />
          </Link>
        </Button>
        <Logo />
        <span className="text-sm text-muted-foreground">/ Design tokens</span>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>

      <div className="space-y-14">
        <Section title="Color" desc="Neutral zinc base, one accent (violet → cyan) used sparingly. Toggle the theme to see light mode.">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {COLORS.map((c) => (
              <Swatch key={c.v} {...c} />
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex h-20 items-end rounded-xl bg-brand-gradient p-3">
              <span className="font-mono text-xs text-black/80">brand-gradient · decorative only</span>
            </div>
            <div className="flex h-20 items-end rounded-xl bg-brand-gradient-strong p-3">
              <span className="font-mono text-xs text-white">brand-gradient-strong · behind white text (≥ 4.5:1)</span>
            </div>
          </div>
        </Section>

        <Section title="Typography" desc="Geist for UI, Geist Mono for numbers, codes and keys. Tight tracking on large headings.">
          <div className="space-y-5 rounded-2xl border bg-surface p-6">
            <p className="text-display font-semibold">AI voiceovers</p>
            <p className="text-h1 font-semibold">Hindi, Hinglish &amp; English</p>
            <p className="text-h2 font-semibold">Generate a voiceover</p>
            <p className="text-h3 font-medium">Voice settings</p>
            <p className="max-w-prose text-[15px] leading-7">
              Body 15/28. Pick a voice, paste your script, and get a clean, loudness-normalized file for your reel.
            </p>
            <p className="text-sm text-muted-foreground">Small 14: secondary text and descriptions.</p>
            <p className="text-xs text-subtle-foreground">Caption 12: meta, hints.</p>
            <p className="font-mono text-sm tabular">
              00:42 · -14.0 LUFS · aiw_live_7f3a…c91e · <span lang="hi">नमस्ते दोस्तों</span>
            </p>
          </div>
        </Section>

        <div className="grid gap-14 lg:grid-cols-2">
          <Section title="Radius">
            <div className="flex flex-wrap items-end gap-4">
              {[
                ["sm", "6"],
                ["md", "8"],
                ["lg", "10"],
                ["xl", "14"],
                ["2xl", "20"],
              ].map(([n, px]) => (
                <div key={n} className="text-center">
                  <div className="size-16 border bg-surface-2" style={{ borderRadius: `var(--radius-${n})` }} />
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    {n} · {px}px
                  </p>
                </div>
              ))}
            </div>
          </Section>
          <Section title="Elevation">
            <div className="flex flex-wrap gap-4">
              {["sm", "md", "lg"].map((s) => (
                <div key={s} className="grid size-24 place-items-center rounded-xl border bg-surface" style={{ boxShadow: `var(--shadow-${s})` }}>
                  <span className="font-mono text-xs text-muted-foreground">shadow-{s}</span>
                </div>
              ))}
              <div className="grid size-24 place-items-center rounded-xl bg-surface shadow-brand-glow">
                <span className="font-mono text-xs text-muted-foreground">brand-glow</span>
              </div>
            </div>
          </Section>
        </div>

        <Section title="Buttons" desc="One brand button per screen (the main action). Everything else is neutral.">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="brand" size="xl">
              <Wand2 /> Generate voiceover
            </Button>
            <Button variant="brand">Brand</Button>
            <Button>Primary</Button>
            <Button variant="outline">
              <Download /> Outline
            </Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="link">Link</Button>
            <Button variant="destructive">Delete</Button>
            <Button disabled>Disabled</Button>
          </div>
        </Section>

        <Section title="Form controls">
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="t-email">Email</Label>
              <Input id="t-email" placeholder="you@example.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="t-err">With error</Label>
              <Input id="t-err" defaultValue="not-an-email" aria-invalid />
              <p className="text-xs text-danger">That doesn't look like an email address</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="t-dis">Disabled</Label>
              <Input id="t-dis" disabled placeholder="Disabled" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="t-key">API key (mono)</Label>
              <Input id="t-key" readOnly value="aiw_live_7f3a2b…c91e" className="font-mono" />
            </div>
            <div className="flex items-center justify-between rounded-xl border bg-surface p-3">
              <Label htmlFor="t-sw">Transliterate Hinglish</Label>
              <Switch id="t-sw" checked={sw} onCheckedChange={setSw} />
            </div>
            <div className="space-y-3 rounded-xl border bg-surface p-3">
              <div className="flex justify-between">
                <Label>Speed</Label>
                <span className="font-mono text-xs text-muted-foreground">{speed[0].toFixed(2)}×</span>
              </div>
              <Slider min={0.7} max={1.3} step={0.05} value={speed} onValueChange={setSpeed} aria-label="Speed" />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="outline">Hindi</Badge>
            <Badge variant="destructive">Error</Badge>
          </div>
        </Section>

        <Section title="Voice cards" desc="Radio cards with a separate preview button. Samples were generated by our own API.">
          <div role="radiogroup" aria-label="Voice" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {VOICES.filter((v) => v.lang === "h").map((v) => (
              <VoiceCard key={v.id} voice={v} checked={voice === v.id} onSelect={setVoice} name="tokens-voice" />
            ))}
          </div>
        </Section>

        <Section title="Waveform" desc="Signature element: idle, generating (with progress) and the player.">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border bg-surface p-5">
              <p className="mb-3 font-mono text-xs text-muted-foreground">idle</p>
              <LiveWaveform mode="idle" bars={48} className="h-20" />
            </div>
            <div className="rounded-2xl border bg-surface p-5">
              <p className="mb-3 font-mono text-xs text-muted-foreground">generating · 60%</p>
              <LiveWaveform mode="active" bars={48} className="h-20" progress={0.6} />
            </div>
          </div>
          <div className="rounded-2xl border bg-surface p-5">
            <WaveformPlayer url={sampleUrl("demo-hi")} label="sample" />
          </div>
        </Section>

        <Section title="Feedback" desc="Toasts (sonner), skeletons and empty states. No blank screens.">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => toast.success("Voiceover ready", { description: "Saved to History for 7 days." })}>
              Success toast
            </Button>
            <Button variant="outline" onClick={() => toast.error("Generation failed", { description: "The voice engine is restarting." })}>
              Error toast
            </Button>
            <Button variant="outline" onClick={() => toast("Queued", { description: "You're 2nd in line." })}>
              Info toast
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-16 rounded-xl" />
            <Skeleton className="h-16 rounded-xl" />
            <Skeleton className="h-16 rounded-xl" />
          </div>
        </Section>
      </div>
    </div>
  );
}
