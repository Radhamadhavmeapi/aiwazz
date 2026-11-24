import { Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { errMsg, setStepUpHandler } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { Field } from "./page";

/** Password + 2FA re-auth for sensitive actions (valid 10 min). Opened automatically by adminApi(). */
export function StepUpDialog() {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resolver = useRef<((ok: boolean) => void) | null>(null);
  const { refresh, me } = useAdmin();

  useEffect(() => {
    setStepUpHandler(
      () =>
        new Promise<boolean>((resolve) => {
          resolver.current?.(false);
          resolver.current = resolve;
          setPassword("");
          setCode("");
          setError("");
          setOpen(true);
        }),
    );
    return () => setStepUpHandler(null);
  }, []);

  const close = (ok: boolean) => {
    setOpen(false);
    resolver.current?.(ok);
    resolver.current = null;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/admin/stepup", { json: { password, code } });
      void refresh();
      close(true);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close(false)}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-brand" aria-hidden="true" /> Confirm it's you
            </DialogTitle>
            <DialogDescription>
              This action is sensitive. Enter your password and a new code from your authenticator app. You won't be asked
              again for {me?.stepup_minutes ?? 10} minutes.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-4">
            <Field label="Password" htmlFor="su-pw">
              <Input id="su-pw" type="password" autoComplete="current-password" value={password} autoFocus
                onChange={(e) => setPassword(e.target.value)} required />
            </Field>
            <Field label="2FA code" htmlFor="su-code" hint="6-digit code (or a backup code)">
              <Input id="su-code" inputMode="numeric" autoComplete="one-time-code" value={code} className="font-mono tracking-widest"
                onChange={(e) => setCode(e.target.value)} required minLength={6} maxLength={32} />
            </Field>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => close(false)}>Cancel</Button>
            <Button type="submit" variant="brand" disabled={busy || !password || code.length < 6}>
              {busy && <Loader2 className="animate-spin" />} Confirm
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
