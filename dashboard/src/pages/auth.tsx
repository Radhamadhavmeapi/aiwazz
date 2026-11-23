import { ArrowRight, Eye, EyeOff, Loader2, Pause, Play, Ticket } from "lucide-react";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { LiveWaveform } from "@/components/brand/live-waveform";
import { BrandIcon, Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/app-shell/topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { sampleUrl } from "@/lib/voices";

type Mode = "login" | "signup";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const INVITE_RE = /^[A-Z0-9]{4}-[A-Z0-9]{4}$/;

/** 0–4. Length matters most; character variety helps; obvious patterns cap the score. */
export function passwordScore(pw: string): number {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 10) s++;
  if (pw.length >= 14) s++;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (kinds >= 3) s++;
  if (pw.length >= 18 || (kinds === 4 && pw.length >= 12)) s++;
  if (/^(.)\1+$/.test(pw) || /(password|qwerty|123456|aiwazz)/i.test(pw)) s = Math.min(s, 1);
  return Math.min(4, s);
}
const STRENGTH = ["Too short", "Weak", "Okay", "Good", "Strong"];

function FieldRow({
  label,
  error,
  hint,
  children,
  id,
  aside,
}: {
  label: string;
  error?: string;
  hint?: ReactNode;
  children: ReactNode;
  id: string;
  aside?: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        {aside}
      </div>
      {children}
      {error ? (
        <p id={`${id}-err`} className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <div id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

function StrengthMeter({ score, show }: { score: number; show: boolean }) {
  const color = score <= 1 ? "bg-danger" : score === 2 ? "bg-warning" : "bg-success";
  return (
    <div className="flex items-center gap-3" aria-live="polite">
      <div className="grid flex-1 grid-cols-4 gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={cn("h-1 rounded-full transition-colors duration-200", show && score >= i ? color : "bg-surface-3")}
          />
        ))}
      </div>
      <span className="w-16 text-right text-xs text-muted-foreground">{show ? STRENGTH[score] : " "}</span>
    </div>
  );
}

function BrandPanel() {
  const { playing, toggle } = usePreviewPlayer();
  const on = playing === "brand";
  return (
    <div className="relative hidden overflow-hidden border-l bg-surface lg:flex lg:flex-col">
      {/* soft brand glows (decorative) */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-40 -left-32 size-[520px] rounded-full opacity-[0.16] blur-3xl"
        style={{ background: "var(--brand-sky)" }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-40 -bottom-48 size-[520px] rounded-full opacity-[0.12] blur-3xl"
        style={{ background: "var(--brand-violet)" }}
      />
      <div className="relative flex flex-1 flex-col justify-center px-12 xl:px-16">
        <BrandIcon size={72} decorative className="mb-8" />
        <div className="glass rounded-2xl border p-6 shadow-lg">
          <div className="mb-5 flex items-center justify-between">
            <span className="font-mono text-xs text-muted-foreground">hf_alpha · Hindi · -14 LUFS</span>
            <button
              type="button"
              onClick={() => toggle("brand", sampleUrl("demo-hi"))}
              aria-label={on ? "Pause sample" : "Play a sample voiceover"}
              className="flex h-8 items-center gap-2 rounded-full border bg-surface-2 px-3 text-xs font-medium transition-colors hover:bg-surface-3"
            >
              {on ? <Pause className="size-3.5 fill-current" /> : <Play className="size-3.5 fill-current" />}
              {on ? "Playing" : "Hear it"}
            </button>
          </div>
          <LiveWaveform mode={on ? "active" : "idle"} bars={56} className="h-28" />
          <p className="mt-5 text-[15px] leading-7 text-muted-foreground" lang="hi">
            “रात ग्यारह बजे कस्टमर का फ़ोन आया। ऑर्डर अभी तक नहीं पहुँचा था…”
          </p>
        </div>
        <p className="tagline mt-10 text-[28px] leading-tight text-foreground xl:text-[34px]">
          Type it, <span className="text-brand-gradient">hear it.</span>
        </p>
        <p className="mt-3 max-w-md text-muted-foreground">
          Natural AI voiceovers in Hindi, Hinglish &amp; English, ready for your next reel in about a minute.
        </p>
      </div>
      <p className="relative px-12 pb-8 text-xs text-subtle-foreground xl:px-16">© 2026 AiWazz</p>
    </div>
  );
}

export default function AuthPage({ mode }: { mode: Mode }) {
  const navigate = useNavigate();
  const ids = { email: useId(), pw: useId(), invite: useId() };
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [invite, setInvite] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const signup = mode === "signup";
  const score = useMemo(() => passwordScore(pw), [pw]);

  const errors = {
    email: !email ? "Enter your email" : !EMAIL_RE.test(email) ? "That doesn't look like an email address" : undefined,
    pw: !pw
      ? "Enter your password"
      : signup && pw.length < 10
        ? "Use at least 10 characters"
        : signup && score < 2
          ? "Too easy to guess. Add length or mix in numbers and symbols."
          : undefined,
    invite: signup ? (!invite ? "An invite code is required for now" : !INVITE_RE.test(invite) ? "Format: XXXX-XXXX" : undefined) : undefined,
  };
  const show = (k: keyof typeof errors) => (touched[k] ? errors[k] : undefined);
  const blur = (k: string) => () => setTouched((t) => ({ ...t, [k]: true }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched({ email: true, pw: true, invite: true });
    if (Object.values(errors).some(Boolean)) {
      const first = errors.email ? ids.email : errors.pw ? ids.pw : ids.invite;
      document.getElementById(first)?.focus();
      return;
    }
    setSubmitting(true);
    setTimeout(() => {
      // Preview: no backend yet.
      setSubmitting(false);
      toast.success(signup ? "Account created" : "Welcome back", { description: "Preview only: no account was created." });
      navigate("/generate");
    }, 900);
  };

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col">
        <header className="flex h-16 items-center justify-between px-5 sm:px-8">
          <Logo width={136} priority />
          <ThemeToggle />
        </header>

        {/* compact brand strip on phones/tablets */}
        <div className="mx-5 rounded-2xl border bg-surface p-4 sm:mx-8 lg:hidden">
          <LiveWaveform mode="idle" bars={40} className="h-12" />
          <p className="tagline mt-3 text-center text-lg">
            Type it, <span className="text-brand-gradient">hear it.</span>
          </p>
        </div>

        <main className="flex flex-1 items-start justify-center px-5 pt-8 pb-12 sm:px-8 lg:items-center lg:py-10">
          <div className="w-full max-w-[380px]">
            <h1 className="text-h2 font-semibold">{signup ? "Create your account" : "Welcome back"}</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {signup ? "AiWazz is invite-only while we're in early access." : "Sign in to generate voiceovers."}
            </p>

            <form onSubmit={submit} noValidate className="mt-8 space-y-5">
              <FieldRow label="Email" id={ids.email} error={show("email")}>
                <Input
                  id={ids.email}
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value.trim())}
                  onBlur={blur("email")}
                  aria-invalid={!!show("email")}
                  aria-describedby={show("email") ? `${ids.email}-err` : undefined}
                  className="h-11"
                />
              </FieldRow>

              <FieldRow
                label="Password"
                id={ids.pw}
                error={show("pw")}
                hint={signup ? <StrengthMeter score={score} show={pw.length > 0} /> : undefined}
              >
                <div className="relative">
                  <Input
                    id={ids.pw}
                    type={showPw ? "text" : "password"}
                    autoComplete={signup ? "new-password" : "current-password"}
                    placeholder={signup ? "At least 10 characters" : "Your password"}
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    onBlur={blur("pw")}
                    aria-invalid={!!show("pw")}
                    aria-describedby={show("pw") ? `${ids.pw}-err` : signup ? `${ids.pw}-hint` : undefined}
                    className="h-11 pr-11"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((s) => !s)}
                    aria-label={showPw ? "Hide password" : "Show password"}
                    aria-pressed={showPw}
                    className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-muted-foreground hover:text-foreground"
                  >
                    {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </FieldRow>

              {signup && (
                <FieldRow
                  label="Invite code"
                  id={ids.invite}
                  error={show("invite")}
                  hint="Ask the admin for a code."
                  aside={<Ticket className="size-4 text-subtle-foreground" aria-hidden="true" />}
                >
                  <Input
                    id={ids.invite}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="XXXX-XXXX"
                    maxLength={9}
                    value={invite}
                    onChange={(e) => {
                      const raw = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
                      setInvite(raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw);
                    }}
                    onBlur={blur("invite")}
                    aria-invalid={!!show("invite")}
                    aria-describedby={show("invite") ? `${ids.invite}-err` : `${ids.invite}-hint`}
                    className="h-11 font-mono tracking-[0.2em] uppercase placeholder:tracking-[0.2em]"
                  />
                </FieldRow>
              )}

              <Button type="submit" variant="brand" size="xl" className="w-full" disabled={submitting}>
                {submitting ? <Loader2 className="animate-spin" /> : null}
                {submitting ? (signup ? "Creating account…" : "Signing in…") : signup ? "Create account" : "Sign in"}
                {!submitting && <ArrowRight />}
              </Button>
            </form>

            <p className="mt-8 text-center text-sm text-muted-foreground">
              {signup ? "Already have an account? " : "Have an invite? "}
              <Link to={signup ? "/login" : "/signup"} className="font-medium text-foreground underline-offset-4 hover:underline">
                {signup ? "Sign in" : "Create an account"}
              </Link>
            </p>
          </div>
        </main>
      </div>
      <BrandPanel />
    </div>
  );
}
