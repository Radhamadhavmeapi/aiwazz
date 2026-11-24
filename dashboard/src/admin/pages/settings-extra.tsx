import { CheckCircle2, Circle, Loader2, Rocket } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, Pill, Section, Select } from "../components/page";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type All = {
  general: { product_name: string; support_email: string; signup_mode: string };
  limits: { api_rpm: number; max_chars: number; queue_per_user: number; retention_days: number };
  flags: { premium_voices: boolean; hinglish_default: boolean; referrals: boolean; open_signup: boolean };
  payments: { mode: string; checklist: { key: string; label: string; ok: boolean }[]; ready_for_live: boolean; live_approved: boolean; approved_by: string | null; approved_at: string | null };
  integrations: { name: string; status: string; detail: string }[];
};

export const SETTINGS_TABS = [
  { id: "general", label: "General" }, { id: "limits", label: "Limits" }, { id: "flags", label: "Feature flags" },
  { id: "payments", label: "Payments" }, { id: "integrations", label: "Integrations" },
];

function useAll() {
  const [d, setD] = useState<All | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => adminApi<All>("/api/admin/settings/all").then(setD, (e) => setError(errMsg(e))), []);
  useEffect(() => void load(), [load]);
  return { d, setD, error, load };
}

export function SettingsExtra({ tab }: { tab: string }) {
  const { can, me } = useAdmin();
  const { d, error, load } = useAll();
  const [busy, setBusy] = useState(false);
  const [g, setG] = useState<All["general"] | null>(null);
  const [l, setL] = useState<All["limits"] | null>(null);
  const [f, setF] = useState<All["flags"] | null>(null);
  const [live, setLive] = useState(false);
  const [confirm, setConfirm] = useState("");
  useEffect(() => { if (d) (setG(d.general), setL(d.limits), setF(d.flags)); }, [d]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!d || !g || !l || !f) return <LoadingRows rows={4} />;
  const write = can("settings.write");
  const save = async (url: string, json: unknown, method = "PUT") => {
    setBusy(true);
    try { await adminApi(url, { method, json }); toast.success("Saved"); await load(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const SaveBtn = ({ onClick }: { onClick: () => void }) => write ? <Button size="sm" onClick={onClick} disabled={busy}>{busy && <Loader2 className="animate-spin" />} Save</Button> : null;
  if (tab === "general") return (
    <Section title="General" description="Changing these asks you to confirm it's you.">
      <div className="grid max-w-xl gap-4">
        <Field label="Product name" htmlFor="g-name"><Input id="g-name" value={g.product_name} disabled={!write} onChange={(e) => setG({ ...g, product_name: e.target.value })} /></Field>
        <Field label="Support email" htmlFor="g-email"><Input id="g-email" value={g.support_email} disabled={!write} onChange={(e) => setG({ ...g, support_email: e.target.value })} /></Field>
        <Field label="Signup mode" hint="Invite-only is the current owner decision."><Select className="w-full" value={g.signup_mode} disabled={!write} onChange={(e) => setG({ ...g, signup_mode: e.target.value })}>
          <option value="invite">Invite-only</option><option value="open">Open</option><option value="closed">Closed</option></Select></Field>
        <SaveBtn onClick={() => save("/api/admin/settings/general", g)} />
      </div>
    </Section>
  );
  if (tab === "limits") return (
    <Section title="Limits" description="Apply immediately (they override api/.env for the running API).">
      <div className="grid max-w-xl gap-4 sm:grid-cols-3">
        <Field label="Max characters per voiceover" htmlFor="l-chars"><Input id="l-chars" type="number" min={100} max={20000} value={l.max_chars} disabled={!write} onChange={(e) => setL({ ...l, max_chars: Number(e.target.value) })} /></Field>
        <Field label="Waiting jobs per user" htmlFor="l-q"><Input id="l-q" type="number" min={1} max={20} value={l.queue_per_user} disabled={!write} onChange={(e) => setL({ ...l, queue_per_user: Number(e.target.value) })} /></Field>
        <Field label="Audio kept (days)" htmlFor="l-ret" hint="The Privacy Policy says 7 days; change both together."><Input id="l-ret" type="number" min={1} max={90} value={l.retention_days} disabled={!write} onChange={(e) => setL({ ...l, retention_days: Number(e.target.value) })} /></Field>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">API rate limit ({l.api_rpm}/min per key) lives in API & usage.</p>
      <div className="mt-4"><SaveBtn onClick={() => save("/api/admin/settings/limits", { max_chars: l.max_chars, queue_per_user: l.queue_per_user, retention_days: l.retention_days })} /></div>
    </Section>
  );
  if (tab === "flags") {
    const FLAGS: [keyof All["flags"], string, string][] = [
      ["hinglish_default", "Hinglish on by default", "New scripts start with “Transliterate Hinglish” switched on (Hindi voices)."],
      ["premium_voices", "Premium voices", "Allows voices to require a plan (Voices & styles → Plan needed)."],
      ["referrals", "Referral program", "Shows referral links to users (settings in Coupons → Referrals)."],
      ["open_signup", "Open signup", "Anyone can sign up without an invite (same as Signup mode = Open)."],
    ];
    return (
      <Section title="Feature flags" description="Changing flags asks you to confirm it's you.">
        <ul className="max-w-2xl divide-y">{FLAGS.map(([k, t, desc]) => (
          <li key={k} className="flex items-start gap-3 py-3"><Switch checked={f[k]} disabled={!write} onCheckedChange={(v) => setF({ ...f, [k]: v })} aria-label={t} />
            <div><p className="text-sm font-medium">{t}</p><p className="text-xs text-muted-foreground">{desc}</p></div></li>
        ))}</ul>
        <div className="mt-2"><SaveBtn onClick={() => save("/api/admin/settings/flags", f)} /></div>
      </Section>
    );
  }
  if (tab === "payments") {
    const p = d.payments;
    return (
      <Section title="Payments mode" description="TEST or LIVE follows the Razorpay keys on the server (set with manage.py set-secret; keys never pass through this panel).">
        <p className="mb-4 flex items-center gap-2 text-sm">Current mode: <Pill tone={p.mode === "LIVE" ? "green" : p.mode === "TEST" ? "amber" : "gray"}>{p.mode}</Pill>
          {p.live_approved ? <span className="text-xs text-muted-foreground">LIVE approved by {p.approved_by} on {fmtDate(p.approved_at)}</span> : <span className="text-xs text-muted-foreground">LIVE not approved yet</span>}</p>
        <ol className="mb-4 space-y-2 text-sm">{p.checklist.map((c) => (
          <li key={c.key} className="flex items-center gap-2">{c.ok ? <CheckCircle2 className="size-4 text-success" /> : <Circle className="size-4 text-muted-foreground" />}{c.label}</li>
        ))}</ol>
        <p className="mb-3 text-xs text-muted-foreground">Going LIVE: finish the checklist in TEST mode, approve here (owner), then put the live keys on the server with manage.py set-secret and restart. With live keys but no approval, checkout stays closed.</p>
        {me?.user.role === "owner" && (
          <Button size="sm" variant={p.live_approved ? "outline" : "brand"} onClick={() => (setConfirm(""), setLive(true))}><Rocket /> {p.live_approved ? "Withdraw LIVE approval" : "Approve going LIVE"}</Button>
        )}
        <FormDialog open={live} onOpenChange={setLive} title={p.live_approved ? "Withdraw LIVE approval" : "Approve LIVE payments"} submitLabel="Confirm"
          disabled={!p.live_approved && confirm !== "GO LIVE"} description="Asks you to confirm it's you. Audited."
          onSubmit={async () => { await adminApi("/api/admin/settings/payments/live", { json: { approve: !p.live_approved, confirm } }); toast.success("Updated"); await load(); }}>
          {!p.live_approved && <Field label="Type GO LIVE" htmlFor="golive"><Input id="golive" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>}
        </FormDialog>
      </Section>
    );
  }
  return (
    <Section title="Integrations" description="Status only: secrets are never shown, only whether they're set.">
      <ul className="divide-y">{d.integrations.map((i) => (
        <li key={i.name} className="flex flex-wrap items-center gap-3 py-3 text-sm"><span className="w-56 font-medium">{i.name}</span>
          <Pill tone={["on", "configured", "set", "LIVE", "TEST"].includes(i.status) ? "green" : "gray"}>{i.status}</Pill>
          <span className="text-xs text-muted-foreground">{i.detail}</span></li>
      ))}</ul>
    </Section>
  );
}
