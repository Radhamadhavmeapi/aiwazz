import { Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { BrandIcon } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

/** One-time password reset link (emailed by support from the admin panel). */
export default function ResetPasswordPage() {
  const [sp] = useSearchParams();
  const token = sp.get("token") ?? "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pw !== pw2) return setError("The passwords don't match");
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/reset-password", { json: { token, new_password: pw } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="grid min-h-dvh place-items-center bg-background px-4">
      <div className="w-full max-w-sm rounded-2xl border bg-surface p-6 shadow-sm sm:p-8">
        <BrandIcon size={36} />
        <h1 className="mt-4 font-heading text-xl font-semibold">Choose a new password</h1>
        {done ? (
          <p className="mt-3 text-sm text-muted-foreground">Done. You're signed out everywhere; <Link to="/login" className="font-medium text-brand hover:underline">sign in</Link> with your new password.</p>
        ) : !token ? (
          <p className="mt-3 text-sm text-muted-foreground">This link is incomplete. Ask support for a new one.</p>
        ) : (
          <form onSubmit={submit} className="mt-5 space-y-4">
            <div className="space-y-1.5"><Label htmlFor="np">New password</Label><Input id="np" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} minLength={10} required /></div>
            <div className="space-y-1.5"><Label htmlFor="np2">Repeat it</Label><Input id="np2" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required /></div>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <Button type="submit" variant="brand" className="w-full" disabled={busy || pw.length < 10}>{busy && <Loader2 className="animate-spin" />} Save password</Button>
          </form>
        )}
      </div>
    </main>
  );
}
