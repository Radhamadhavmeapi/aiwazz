import { Eye, EyeOff, Loader2, LogOut, Monitor, Moon, Sun, Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { AppShell } from "@/components/app-shell/app-shell";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme, type Theme } from "@/lib/theme";
import { fmtChars, useUsage } from "@/lib/usage";
import { cn } from "@/lib/utils";
import { passwordScore } from "@/lib/password";

function Card({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border bg-surface p-5 shadow-md sm:p-6">
      <h3 className="font-heading text-h3 font-semibold">{title}</h3>
      {desc && <p className="mt-1 text-sm text-muted-foreground">{desc}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const score = passwordScore(next);
  const mismatch = confirm.length > 0 && confirm !== next;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < 10) return setError("Use at least 10 characters");
    if (score < 2) return setError("Too easy to guess. Add length or mix in numbers and symbols.");
    if (next !== confirm) return setError("The new passwords don't match");
    setBusy(true);
    try {
      const r = await api<{ signed_out_sessions: number }>("/api/auth/password", { json: { current_password: current, new_password: next } });
      toast.success("Password changed", {
        description: r.signed_out_sessions ? `Signed out ${r.signed_out_sessions} other device${r.signed_out_sessions > 1 ? "s" : ""}.` : undefined,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't change the password");
    } finally {
      setBusy(false);
    }
  };

  const type = show ? "text" : "password";
  return (
    <form onSubmit={submit} className="max-w-md space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="pw-current">Current password</Label>
        <Input id="pw-current" type={type} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="pw-new">New password</Label>
          <button type="button" onClick={() => setShow((s) => !s)} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground" aria-pressed={show}>
            {show ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />} {show ? "Hide" : "Show"}
          </button>
        </div>
        <Input id="pw-new" type={type} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        <div className="grid grid-cols-4 gap-1" aria-hidden="true">
          {[1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className={cn("h-1 rounded-full", next && score >= i ? (score <= 1 ? "bg-danger" : score === 2 ? "bg-warning" : "bg-success") : "bg-surface-3")}
            />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="pw-confirm">Repeat new password</Label>
        <Input id="pw-confirm" type={type} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-invalid={mismatch} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy || !current || !next || !confirm}>
        {busy && <Loader2 className="animate-spin" />} Change password
      </Button>
      <p className="text-xs text-muted-foreground">Changing your password signs you out on all other devices.</p>
    </form>
  );
}

function DeleteAccount() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ reference: string }>("/api/auth/delete-account", { json: { password: pw, confirm } });
      try {
        sessionStorage.setItem("aiwazz-deleted-ref", r.reference); // shown on the login page (survives the auth redirect)
      } catch {
        /* toast still shows it */
      }
      await logout().catch(() => undefined);
      toast.success("Your account was deleted", { description: `Reference ${r.reference}. All voiceovers, API keys and sessions are gone.`, duration: 15000 });
      navigate("/login", { replace: true, state: { deletedRef: r.reference } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete the account");
      setBusy(false);
    }
  };

  return (
    <>
      <Button variant="outline" className="border-danger/40 text-danger hover:bg-danger/10 hover:text-danger" onClick={() => setOpen(true)}>
        <Trash2 /> Delete account
      </Button>
      <Dialog open={open} onOpenChange={(o) => (setOpen(o), o || (setPw(""), setConfirm(""), setError(null)))}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={submit} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Delete your account?</DialogTitle>
              <DialogDescription>
                This permanently deletes your account, all voiceovers and audio files, and your API keys. It can't be undone.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="del-pw">Your password</Label>
              <Input id="del-pw" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="del-confirm">
                Type <span className="font-mono">DELETE</span> to confirm
              </Label>
              <Input id="del-confirm" autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="destructive" disabled={busy || !pw || confirm !== "DELETE"}>
                {busy ? <Loader2 className="animate-spin" /> : <Trash2 />} Delete permanently
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const usage = useUsage();
  const pct = usage && usage.allowance ? Math.min(100, Math.round(((usage.used + usage.reserved) / usage.allowance) * 100)) : 0;

  const signOutOthers = async () => {
    setBusy(true);
    try {
      const r = await api<{ signed_out_sessions: number }>("/api/auth/logout-others", { method: "POST" });
      toast.success(r.signed_out_sessions ? `Signed out ${r.signed_out_sessions} other session${r.signed_out_sessions > 1 ? "s" : ""}` : "No other sessions were signed in");
    } catch (err) {
      toast.error("Couldn't sign out other devices", { description: err instanceof ApiError ? err.message : undefined });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell title="Settings">
      <div className="mx-auto max-w-3xl space-y-5 p-3 sm:p-5 lg:p-6">
        <h2 className="text-h2 font-semibold">Settings</h2>

        <Card title="Account">
          <dl className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Email</dt>
              <dd className="mt-1 truncate font-medium">{user?.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Role</dt>
              <dd className="mt-1 font-medium capitalize">{user?.role}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Member since</dt>
              <dd className="mt-1 font-medium">{user?.created_at ? new Date(user.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" }) : "–"}</dd>
            </div>
          </dl>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-5">
            <p className="max-w-md text-sm text-muted-foreground">Delete your account and everything in it: voiceovers, audio files and API keys.</p>
            <DeleteAccount />
          </div>
        </Card>

        <Card title="Billing">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {usage ? `${usage.plan_name} plan` : "Plan"}
                {usage?.unlimited && <span className="text-muted-foreground"> · unlimited (admin)</span>}
              </p>
              {usage && !usage.unlimited && usage.allowance !== null && (
                <div className="mt-2 max-w-sm">
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Characters used this month">
                    <div className="h-full rounded-full bg-brand-gradient" style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-1.5 font-mono text-xs text-muted-foreground tabular">
                    {fmtChars(usage.used)} / {fmtChars(usage.allowance)} characters used · resets{" "}
                    {new Date(usage.period_end).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                  </p>
                </div>
              )}
              <p className="mt-2 text-sm text-muted-foreground">Online upgrades, invoices and cancellation will be managed here once payments open.</p>
            </div>
            <Button asChild variant="outline" size="sm">
              <a href="https://aiwazz.in/pricing/" target="_blank" rel="noopener">
                See plans
              </a>
            </Button>
          </div>
        </Card>

        <Card title="Appearance" desc="Light is the default. Your choice is remembered on this device.">
          <ToggleGroup type="single" variant="outline" value={theme} onValueChange={(v) => v && setTheme(v as Theme)} aria-label="Theme">
            <ToggleGroupItem value="light" className="gap-2 px-4">
              <Sun className="size-4" /> Light
            </ToggleGroupItem>
            <ToggleGroupItem value="dark" className="gap-2 px-4">
              <Moon className="size-4" /> Dark
            </ToggleGroupItem>
          </ToggleGroup>
        </Card>

        <Card title="Password">
          <PasswordForm />
        </Card>

        <Card title="Sessions" desc="Signed in on a shared or lost device? Sign it out from here.">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={signOutOthers} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : <Monitor />} Sign out other devices
            </Button>
            <Button
              variant="ghost"
              onClick={async () => {
                await logout();
                navigate("/login", { replace: true });
              }}
            >
              <LogOut /> Sign out
            </Button>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
