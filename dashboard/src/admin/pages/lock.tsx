import { Check, Copy, Download, KeyRound, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { BrandIcon } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { Field } from "../components/page";

function Frame({ title, children, wide }: { title: string; children: React.ReactNode; wide?: boolean }) {
  const { me } = useAdmin();
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <main className="grid min-h-dvh place-items-center bg-background px-4 py-10">
      <div className={`w-full ${wide ? "max-w-lg" : "max-w-sm"} rounded-2xl border bg-surface p-6 shadow-sm sm:p-8`}>
        <div className="mb-6 flex items-center gap-3">
          <BrandIcon size={36} />
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">AiWazz admin</p>
            <h1 className="font-heading text-lg font-semibold">{title}</h1>
          </div>
        </div>
        {children}
        <div className="mt-6 flex items-center justify-between border-t pt-4 text-xs text-muted-foreground">
          <span className="truncate">
            {me?.user.email} · <span className="capitalize">{me?.user.role}</span>
          </span>
          <span className="flex gap-3">
            <a className="hover:text-foreground" href="/generate">App</a>
            <button type="button" className="hover:text-foreground" onClick={async () => (await logout(), navigate("/login"))}>
              Sign out
            </button>
          </span>
        </div>
      </div>
    </main>
  );
}

export function VerifyScreen() {
  const { refresh, me } = useAdmin();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [useBackup, setUseBackup] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/admin/mfa/verify", { json: { code } });
      await refresh();
    } catch (err) {
      setError(errMsg(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Frame title="Unlock the admin panel">
      <p className="mb-5 text-sm text-muted-foreground">
        {useBackup
          ? "Enter one of your backup codes. Each code works once."
          : "Open your authenticator app and enter the 6-digit code for AiWazz Admin."}{" "}
        The panel locks again after {me?.idle_minutes ?? 30} minutes without activity.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <Field label={useBackup ? "Backup code" : "2FA code"} htmlFor="mfa-code">
          <Input id="mfa-code" autoFocus value={code} onChange={(e) => setCode(e.target.value)}
            inputMode={useBackup ? "text" : "numeric"} autoComplete="one-time-code" placeholder={useBackup ? "xxxxx-xxxxx" : "123456"}
            className="h-11 text-center font-mono text-lg tracking-[0.3em]" maxLength={useBackup ? 11 : 6} required />
        </Field>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <Button type="submit" variant="brand" className="w-full" size="lg" disabled={busy || code.length < 6}>
          {busy ? <Loader2 className="animate-spin" /> : <LockKeyhole />} Unlock
        </Button>
      </form>
      <button type="button" onClick={() => (setUseBackup((b) => !b), setCode(""), setError(""))}
        className="mt-4 text-xs font-medium text-brand hover:underline">
        {useBackup ? "Use my authenticator app" : "Lost your phone? Use a backup code"}
      </button>
      {me && me.mfa.backup_codes_left <= 3 && (
        <p className="mt-3 text-xs text-warning">Only {me.mfa.backup_codes_left} backup codes left. Make new ones in Settings → Security.</p>
      )}
    </Frame>
  );
}

export function BackupCodes({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false);
  const text = `AiWazz admin backup codes (each works once)\n\n${codes.join("\n")}\n`;
  return (
    <div>
      <ol className="grid grid-cols-2 gap-2 rounded-xl border bg-surface-2/60 p-4 font-mono text-sm">
        {codes.map((c) => (
          <li key={c} className="tabular">{c}</li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={async () => {
          await navigator.clipboard.writeText(text).catch(() => undefined);
          setCopied(true);
        }}>
          {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => {
          const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
          Object.assign(document.createElement("a"), { href: url, download: "aiwazz-admin-backup-codes.txt" }).click();
          URL.revokeObjectURL(url);
        }}>
          <Download /> Download
        </Button>
      </div>
    </div>
  );
}

export function SetupScreen() {
  const { refresh, me } = useAdmin();
  const [step, setStep] = useState<"password" | "scan" | "codes">("password");
  const [password, setPassword] = useState("");
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const start = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSetup(await api("/api/admin/mfa/setup", { json: { password } }));
      setPassword("");
      setStep("scan");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };
  const enable = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ backup_codes: string[] }>("/api/admin/mfa/enable", { json: { code } });
      setCodes(r.backup_codes);
      setStep("codes");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  if (me && !me.mfa.configured)
    return (
      <Frame title="2FA isn't configured yet">
        <p className="text-sm text-muted-foreground">
          The server has no 2FA encryption key. On the server run <code className="font-mono">manage.py gen-admin-key</code> and
          restart the API.
        </p>
      </Frame>
    );

  return (
    <Frame title="Set up two-factor authentication" wide>
      <ol className="mb-5 flex gap-2 text-xs" aria-label="Steps">
        {(["password", "scan", "codes"] as const).map((s, i) => (
          <li key={s} className={`flex-1 rounded-full py-1 text-center font-medium ${step === s ? "bg-brand-gradient-strong text-white" : "bg-surface-2 text-muted-foreground"}`}>
            {i + 1}. {s === "password" ? "Password" : s === "scan" ? "Scan" : "Backup codes"}
          </li>
        ))}
      </ol>
      {step === "password" && (
        <form onSubmit={start} className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Every staff account needs 2FA before the admin panel opens. You'll need an authenticator app such as Google
            Authenticator, Microsoft Authenticator, 1Password or Aegis.
          </p>
          <Field label="Your account password" htmlFor="setup-pw">
            <Input id="setup-pw" type="password" autoComplete="current-password" autoFocus value={password}
              onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" variant="brand" className="w-full" disabled={busy || !password}>
            {busy ? <Loader2 className="animate-spin" /> : <KeyRound />} Continue
          </Button>
        </form>
      )}
      {step === "scan" && setup && (
        <form onSubmit={enable} className="space-y-4">
          <p className="text-sm text-muted-foreground">Scan this QR code with your authenticator app, then enter the 6-digit code it shows.</p>
          <div className="mx-auto w-fit rounded-xl border bg-white p-2" aria-label="QR code for your authenticator app"
            dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer font-medium">Can't scan? Enter the key by hand</summary>
            <p className="mt-2 font-mono break-all text-foreground select-all">{setup.secret.match(/.{1,4}/g)?.join(" ")}</p>
            <p className="mt-1">Account: {me?.user.email} · Type: time-based (TOTP), 6 digits, 30 seconds</p>
          </details>
          <Field label="6-digit code" htmlFor="setup-code">
            <Input id="setup-code" autoFocus inputMode="numeric" autoComplete="one-time-code" value={code}
              onChange={(e) => setCode(e.target.value)} maxLength={6} required className="h-11 text-center font-mono text-lg tracking-[0.3em]" />
          </Field>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" variant="brand" className="w-full" disabled={busy || code.length !== 6}>
            {busy ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Turn on 2FA
          </Button>
        </form>
      )}
      {step === "codes" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            2FA is on. Save these 10 backup codes somewhere safe (a password manager). Each works once if you lose your phone.
            <strong className="text-foreground"> They are shown only now.</strong>
          </p>
          <BackupCodes codes={codes} />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 size-4 accent-[var(--primary)]" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
            I saved my backup codes
          </label>
          <Button variant="brand" className="w-full" disabled={!saved} onClick={() => void refresh()}>
            Open the admin panel
          </Button>
        </div>
      )}
    </Frame>
  );
}
