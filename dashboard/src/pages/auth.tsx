import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Pause,
  Play,
  Ticket,
} from "lucide-react";
import {
  useId,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { SiteFooter } from "@/components/site-footer";
import { toast } from "sonner";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { LiveWaveform } from "@/components/brand/live-waveform";
import { BrandIcon, Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/app-shell/topbar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { safeNext, useAuth } from "@/lib/auth";
import { PREVIEW } from "@/lib/env";
import { passwordScore } from "@/lib/password";
import { cn } from "@/lib/utils";
import { sampleUrl } from "@/lib/voices";

type Mode = "login" | "signup";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const INVITE_RE = /^[A-Z0-9]{4}-[A-Z0-9]{4}$/;

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
  const color =
    score <= 1 ? "bg-danger" : score === 2 ? "bg-warning" : "bg-success";
  return (
    <div className="flex items-center gap-3" aria-live="polite">
      <div className="grid flex-1 grid-cols-4 gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={cn(
              "h-1 rounded-full transition-colors duration-200",
              show && score >= i ? color : "bg-surface-3",
            )}
          />
        ))}
      </div>
      <span className="w-16 text-right text-xs text-muted-foreground">
        {show ? STRENGTH[score] : " "}
      </span>
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
            <span className="font-mono text-xs text-muted-foreground">
              hf_alpha · Hindi · -14 LUFS
            </span>
            <button
              type="button"
              onClick={() => toggle("brand", sampleUrl("demo-hi"))}
              aria-label={on ? "Pause sample" : "Play a sample voiceover"}
              className="flex h-8 items-center gap-2 rounded-full border bg-surface-2 px-3 text-xs font-medium transition-colors hover:bg-surface-3"
            >
              {on ? (
                <Pause className="size-3.5 fill-current" />
              ) : (
                <Play className="size-3.5 fill-current" />
              )}
              {on ? "Playing" : "Hear it"}
            </button>
          </div>
          <LiveWaveform
            mode={on ? "active" : "idle"}
            bars={56}
            className="h-28"
          />
          <p
            className="mt-5 text-[15px] leading-7 text-muted-foreground"
            lang="hi"
          >
            “रात ग्यारह बजे कस्टमर का फ़ोन आया। ऑर्डर अभी तक नहीं पहुँचा था…”
          </p>
        </div>
        <p className="tagline mt-10 text-[28px] leading-tight text-foreground xl:text-[34px]">
          Type it, <span className="text-brand-gradient">hear it.</span>
        </p>
        <p className="mt-3 max-w-md text-muted-foreground">
          Natural AI voiceovers in Hindi, Hinglish &amp; English, ready for your
          next reel in about a minute.
        </p>
      </div>
      <p className="relative px-12 pb-8 text-xs text-subtle-foreground xl:px-16">
        © 2026 AiWazz
      </p>
    </div>
  );
}

/** Signup without a code: explain early access and collect an invite request (stored; support@ is emailed once mail is live). */
function RequestInvite({ onHaveCode }: { onHaveCode: () => void }) {
  const ids = { email: useId(), name: useId(), use: useId() };
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [useCase, setUseCase] = useState("");
  const [website, setWebsite] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const emailErr = !email
    ? "Enter your email"
    : !EMAIL_RE.test(email)
      ? "That doesn't look like an email address"
      : undefined;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (emailErr) return document.getElementById(ids.email)?.focus();
    setBusy(true);
    setError(null);
    try {
      if (!PREVIEW)
        await api("/api/auth/invite-request", {
          json: { email, name, use_case: useCase, website },
        });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (done)
    return (
      <div role="status" className="mt-8 rounded-2xl border bg-surface p-5">
        <CheckCircle2 className="size-6 text-success" aria-hidden="true" />
        <p className="mt-3 font-semibold">You're on the list</p>
        <p className="mt-1.5 text-sm leading-6 text-muted-foreground">
          Thanks! We let people in in small batches and will send an invite code
          to <span className="font-medium text-foreground">{email}</span> when a
          spot opens.
        </p>
        <button
          type="button"
          onClick={onHaveCode}
          className="mt-4 text-sm font-medium text-foreground underline underline-offset-4"
        >
          Already got a code? Create your account
        </button>
      </div>
    );

  return (
    <>
      <div className="mt-5 rounded-xl border bg-surface px-4 py-3.5 text-sm leading-6 text-muted-foreground">
        <p>
          Voices are generated on our own servers, one at a time, so we let
          people in in small batches to keep the queue short. Leave your email
          and we'll send you an invite code.
        </p>
      </div>
      <form onSubmit={submit} noValidate className="mt-6 space-y-5">
        <FieldRow
          label="Email"
          id={ids.email}
          error={touched ? emailErr : undefined}
        >
          <Input
            id={ids.email}
            type="email"
            autoComplete="email"
            inputMode="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value.trim())}
            onBlur={() => setTouched(true)}
            aria-invalid={touched && !!emailErr}
            aria-describedby={
              touched && emailErr ? `${ids.email}-err` : undefined
            }
            className="h-11"
          />
        </FieldRow>
        <FieldRow label="Name (optional)" id={ids.name}>
          <Input
            id={ids.name}
            autoComplete="name"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-11"
          />
        </FieldRow>
        <FieldRow
          label="What will you make? (optional)"
          id={ids.use}
          hint="For example: Hindi reels for my shop, YouTube explainers, course audio."
        >
          <Textarea
            id={ids.use}
            maxLength={500}
            rows={3}
            value={useCase}
            onChange={(e) => setUseCase(e.target.value)}
            aria-describedby={`${ids.use}-hint`}
          />
        </FieldRow>
        {/* honeypot: hidden from people and screen readers */}
        <input
          type="text"
          name="website"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          className="hidden"
        />
        <p className="text-xs leading-5 text-muted-foreground">
          We use your email only to send your invite. See our{" "}
          <a
            href="https://aiwazz.in/privacy/"
            target="_blank"
            rel="noopener"
            className="font-medium text-foreground underline underline-offset-2"
          >
            Privacy Policy
          </a>
          .
        </p>
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-sm text-danger"
          >
            <AlertCircle
              className="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <span>{error}</span>
          </div>
        )}
        <Button
          type="submit"
          variant="brand"
          size="xl"
          className="w-full"
          disabled={busy}
        >
          {busy ? <Loader2 className="animate-spin" /> : null}
          {busy ? "Sending…" : "Request an invite"}
          {!busy && <ArrowRight />}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Have an invite code?{" "}
        <button
          type="button"
          onClick={onHaveCode}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          Create your account
        </button>
      </p>
    </>
  );
}

export default function AuthPage({ mode }: { mode: Mode }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const auth = useAuth();
  const ids = { email: useId(), pw: useId(), invite: useId() };
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [invite, setInvite] = useState(() => {
    const raw = (
      new URLSearchParams(window.location.search).get("invite") ?? ""
    )
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "")
      .slice(0, 8);
    return raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
  });
  const [consent, setConsent] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const location = useLocation();
  const [deletedRef] = useState(() => {
    let ref =
      (location.state as { deletedRef?: string } | null)?.deletedRef ?? null;
    try {
      ref = ref ?? sessionStorage.getItem("aiwazz-deleted-ref");
      sessionStorage.removeItem("aiwazz-deleted-ref");
    } catch {
      /* ignore */
    }
    return ref;
  });
  const plan = params.get("plan");
  const planName =
    plan && ["starter", "creator", "pro"].includes(plan)
      ? plan[0].toUpperCase() + plan.slice(1)
      : null;
  const [showPw, setShowPw] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [server, setServer] = useState<{
    email?: string;
    pw?: string;
    invite?: string;
    consent?: string;
    form?: string;
  }>({});
  const signup = mode === "signup";
  // Signup has two views: "request" (default, no code yet) and "account" (?invite= present, or "I have a code").
  const [, setParams] = useSearchParams();
  const view: "request" | "account" =
    signup && !params.has("invite") ? "request" : "account";
  const showAccount = () =>
    setParams((p) => (p.set("invite", invite), p), { replace: true });
  const showRequest = () =>
    setParams((p) => (p.delete("invite"), p), { replace: true });
  const score = useMemo(() => passwordScore(pw), [pw]);

  const errors = {
    email: !email
      ? "Enter your email"
      : !EMAIL_RE.test(email)
        ? "That doesn't look like an email address"
        : undefined,
    pw: !pw
      ? "Enter your password"
      : signup && pw.length < 10
        ? "Use at least 10 characters"
        : signup && score < 2
          ? "Too easy to guess. Add length or mix in numbers and symbols."
          : undefined,
    invite: signup
      ? !invite
        ? "An invite code is required for now"
        : !INVITE_RE.test(invite)
          ? "Format: XXXX-XXXX"
          : undefined
      : undefined,
    consent:
      signup && !consent
        ? "Please accept the Terms, Privacy Policy and Acceptable Use Policy"
        : undefined,
  };
  // Client-side checks first; server messages (invalid invite, email taken, ...) override until edited.
  const show = (k: keyof typeof errors) =>
    server[k] ?? (touched[k] ? errors[k] : undefined);
  const edited = (k: keyof typeof errors) =>
    setServer((x) => ({ ...x, [k]: undefined, form: undefined }));
  const blur = (k: string) => () => setTouched((t) => ({ ...t, [k]: true }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched({ email: true, pw: true, invite: true, consent: true });
    if (Object.values(errors).some(Boolean)) {
      const first = errors.email
        ? ids.email
        : errors.pw
          ? ids.pw
          : errors.invite
            ? ids.invite
            : "consent";
      document.getElementById(first)?.focus();
      return;
    }
    setSubmitting(true);
    setServer({});
    try {
      const user = signup
        ? await auth.signup(email, pw, invite, marketing)
        : await auth.login(email, pw);
      toast.success(signup ? "Account created" : "Welcome back", {
        description: PREVIEW
          ? "Preview only: no account was created."
          : user.email,
      });
      navigate(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      const e =
        err instanceof ApiError
          ? err
          : new ApiError(0, "Something went wrong. Please try again.");
      const m = e.message;
      if (e.status === 409) setServer({ email: m });
      else if (signup && e.status === 422 && /invite/i.test(m))
        setServer({ invite: m });
      else if (
        signup &&
        e.status === 422 &&
        /password|characters|guess/i.test(m)
      )
        setServer({ pw: m });
      else if (signup && e.status === 422 && /Terms/i.test(m))
        setServer({ consent: m });
      else if (e.status === 422 && /email/i.test(m))
        setServer({ email: "That doesn't look like an email address" });
      else setServer({ form: m });
      setSubmitting(false);
    }
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
            {deletedRef && !signup && (
              <div
                role="status"
                className="mb-6 rounded-xl border bg-surface px-4 py-3 text-sm"
              >
                Your account was deleted. Reference:{" "}
                <span className="font-mono font-medium">{deletedRef}</span>
              </div>
            )}
            <h1 className="text-h2 font-semibold">
              {!signup
                ? "Welcome back"
                : view === "request"
                  ? "Get early access"
                  : "Create your account"}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {!signup
                ? "Sign in to generate voiceovers."
                : view === "request"
                  ? "AiWazz is invite-only while we're in early access."
                  : "Enter the invite code we sent you."}
            </p>
            {signup && view === "request" ? (
              <RequestInvite onHaveCode={showAccount} />
            ) : (
              <>
                {signup && planName && (
                  <p className="mt-3 rounded-xl border bg-surface px-3.5 py-2.5 text-xs leading-5 text-muted-foreground">
                    You picked the{" "}
                    <strong className="text-foreground">{planName}</strong>{" "}
                    plan. Online payments aren't open yet, so your account
                    starts on the Free plan; you can upgrade from Settings once
                    billing is live.
                  </p>
                )}

                <form onSubmit={submit} noValidate className="mt-8 space-y-5">
                  <FieldRow label="Email" id={ids.email} error={show("email")}>
                    <Input
                      id={ids.email}
                      type="email"
                      autoComplete="email"
                      inputMode="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => (
                        setEmail(e.target.value.trim()),
                        edited("email")
                      )}
                      onBlur={blur("email")}
                      aria-invalid={!!show("email")}
                      aria-describedby={
                        show("email") ? `${ids.email}-err` : undefined
                      }
                      className="h-11"
                    />
                  </FieldRow>

                  <FieldRow
                    label="Password"
                    id={ids.pw}
                    error={show("pw")}
                    hint={
                      signup ? (
                        <StrengthMeter score={score} show={pw.length > 0} />
                      ) : undefined
                    }
                  >
                    <div className="relative">
                      <Input
                        id={ids.pw}
                        type={showPw ? "text" : "password"}
                        autoComplete={
                          signup ? "new-password" : "current-password"
                        }
                        placeholder={
                          signup ? "At least 10 characters" : "Your password"
                        }
                        value={pw}
                        onChange={(e) => (setPw(e.target.value), edited("pw"))}
                        onBlur={blur("pw")}
                        aria-invalid={!!show("pw")}
                        aria-describedby={
                          show("pw")
                            ? `${ids.pw}-err`
                            : signup
                              ? `${ids.pw}-hint`
                              : undefined
                        }
                        className="h-11 pr-11"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPw((s) => !s)}
                        aria-label={showPw ? "Hide password" : "Show password"}
                        aria-pressed={showPw}
                        className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-muted-foreground hover:text-foreground"
                      >
                        {showPw ? (
                          <EyeOff className="size-4" />
                        ) : (
                          <Eye className="size-4" />
                        )}
                      </button>
                    </div>
                  </FieldRow>

                  {signup && (
                    <FieldRow
                      label="Invite code"
                      id={ids.invite}
                      error={show("invite")}
                      hint="Ask the admin for a code."
                      aside={
                        <Ticket
                          className="size-4 text-subtle-foreground"
                          aria-hidden="true"
                        />
                      }
                    >
                      <Input
                        id={ids.invite}
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="XXXX-XXXX"
                        maxLength={9}
                        value={invite}
                        onChange={(e) => {
                          const raw = e.target.value
                            .toUpperCase()
                            .replace(/[^A-Z0-9]/g, "")
                            .slice(0, 8);
                          setInvite(
                            raw.length > 4
                              ? `${raw.slice(0, 4)}-${raw.slice(4)}`
                              : raw,
                          );
                          edited("invite");
                        }}
                        onBlur={blur("invite")}
                        aria-invalid={!!show("invite")}
                        aria-describedby={
                          show("invite")
                            ? `${ids.invite}-err`
                            : `${ids.invite}-hint`
                        }
                        className="h-11 font-mono tracking-[0.2em] uppercase placeholder:tracking-[0.2em]"
                      />
                    </FieldRow>
                  )}

                  {signup && (
                    <div className="space-y-3">
                      <label className="flex items-start gap-2.5 text-sm leading-6 text-muted-foreground">
                        <input
                          id="consent"
                          type="checkbox"
                          checked={consent}
                          onChange={(e) => (
                            setConsent(e.target.checked),
                            setTouched((t) => ({ ...t, consent: true }))
                          )}
                          aria-invalid={!!show("consent")}
                          aria-describedby={
                            show("consent") ? "consent-err" : undefined
                          }
                          className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                        />
                        <span>
                          I agree to the{" "}
                          <a
                            href="https://aiwazz.in/terms/"
                            target="_blank"
                            rel="noopener"
                            className="font-medium text-foreground underline underline-offset-2"
                          >
                            Terms and Conditions
                          </a>
                          ,{" "}
                          <a
                            href="https://aiwazz.in/privacy/"
                            target="_blank"
                            rel="noopener"
                            className="font-medium text-foreground underline underline-offset-2"
                          >
                            Privacy Policy
                          </a>{" "}
                          and{" "}
                          <a
                            href="https://aiwazz.in/acceptable-use/"
                            target="_blank"
                            rel="noopener"
                            className="font-medium text-foreground underline underline-offset-2"
                          >
                            Acceptable Use Policy
                          </a>
                          .
                        </span>
                      </label>
                      {show("consent") && (
                        <p
                          id="consent-err"
                          role="alert"
                          className="-mt-1 pl-6.5 text-xs text-danger"
                        >
                          {show("consent")}
                        </p>
                      )}
                      <label className="flex items-start gap-2.5 text-sm leading-6 text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={marketing}
                          onChange={(e) => setMarketing(e.target.checked)}
                          className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
                        />
                        <span>Send me product updates (optional)</span>
                      </label>
                    </div>
                  )}
                  {server.form && (
                    <div
                      role="alert"
                      className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-sm text-danger"
                    >
                      <AlertCircle
                        className="mt-0.5 size-4 shrink-0"
                        aria-hidden="true"
                      />
                      <span>{server.form}</span>
                    </div>
                  )}
                  <Button
                    type="submit"
                    variant="brand"
                    size="xl"
                    className="w-full"
                    disabled={submitting}
                  >
                    {submitting ? <Loader2 className="animate-spin" /> : null}
                    {submitting
                      ? signup
                        ? "Creating account…"
                        : "Signing in…"
                      : signup
                        ? "Create account"
                        : "Sign in"}
                    {!submitting && <ArrowRight />}
                  </Button>
                </form>

                {signup && (
                  <p className="mt-6 text-center text-sm text-muted-foreground">
                    No code yet?{" "}
                    <button
                      type="button"
                      onClick={showRequest}
                      className="font-medium text-foreground underline-offset-4 hover:underline"
                    >
                      Request an invite
                    </button>
                  </p>
                )}
              </>
            )}

            <p
              className={cn(
                "text-center text-sm text-muted-foreground",
                signup ? "mt-3" : "mt-8",
              )}
            >
              {signup ? (
                <>
                  Already have an account?{" "}
                  <Link
                    to="/login"
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    Sign in
                  </Link>
                </>
              ) : (
                <>
                  New here?{" "}
                  <Link
                    to="/signup"
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    Request an invite
                  </Link>
                  {" · "}
                  <Link
                    to="/signup?invite="
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    I have a code
                  </Link>
                </>
              )}
            </p>
          </div>
        </main>
        <SiteFooter compact />
      </div>
      <BrandPanel />
    </div>
  );
}
