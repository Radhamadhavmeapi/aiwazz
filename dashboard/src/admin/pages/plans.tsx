import { ArrowDown, ArrowUp, Eye, Loader2, Star } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, inr, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

type Plan = { id: string; name: string; priceMonthly: number; characters: number; features: string[]; visibility?: string; sortOrder?: number; popular?: boolean };
type Data = {
  plans: Plan[]; yearlyDiscountPercent: number; gstRatePercent: number;
  versions: { id: number; plan: string; period: string; taxable_paise: number; total_paise: number; rzp_plan_id: string; active: boolean; created_at: string; subscribers: number }[];
  env_plan_ids: Record<string, { id: string; subscribers: number }>; landing_job_running: boolean;
};
type Preview = { errors: string[]; changes: { path: string; before: unknown; after: unknown }[]; price_changes: { plan: string; period: string; before_paise: number | null; after_paise: number }[]; note: string };

export default function PlansPage() {
  const { can } = useAdmin();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [disc, setDisc] = useState(20);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    setError("");
    adminApi<Data>("/api/admin/plans").then((d) => {
      setData(d);
      setPlans(d.plans.map((p, i) => ({ ...p, sortOrder: p.sortOrder ?? i, visibility: p.visibility ?? "public" })));
      setDisc(d.yearlyDiscountPercent);
    }, (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  const edit = can("plans.write");
  const set = (i: number, patch: Partial<Plan>) => setPlans((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const move = (i: number, d: number) => setPlans((ps) => {
    const order = [...ps].sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0)).map((p) => p.id);
    const k = order.indexOf(ps[i].id);
    const t = k + d;
    if (t < 0 || t >= order.length) return ps;
    [order[k], order[t]] = [order[t], order[k]];
    return ps.map((p) => ({ ...p, sortOrder: order.indexOf(p.id) }));
  });
  const body = () => ({ plans: plans.map((p) => ({ ...p, features: p.features.map((f) => f.trim()).filter(Boolean) })), yearlyDiscountPercent: disc });
  const doPreview = async () => {
    setBusy(true);
    try { setPreview(await adminApi<Preview>("/api/admin/plans/preview", { json: body() })); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  if (error) return <AdminShell title="Plans & pricing"><ErrorState message={error} onRetry={load} /></AdminShell>;
  if (!data) return <AdminShell title="Plans & pricing"><LoadingRows rows={8} /></AdminShell>;
  const yearlyPm = (m: number) => Math.round(m * (1 - disc / 100));
  return (
    <AdminShell title="Plans & pricing">
      <PageHeader title="Plans & pricing" description="Prices are per month in whole rupees, excl. 18% GST. Saving updates legal/legal.json (committed to git), rebuilds aiwazz.in/pricing/, and creates new Razorpay plan versions for changed prices. Existing subscribers keep their price."
        actions={edit && <Button variant="brand" size="sm" onClick={doPreview} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Eye />} Preview changes</Button>} />
      {data.landing_job_running && <p role="status" className="mb-4 rounded-xl border border-brand-indigo/30 bg-brand-indigo/5 p-3 text-sm">The landing page is being rebuilt with the last change…</p>}
      <div className="mb-4 flex items-end gap-3">
        <Field label="Yearly discount (%)" htmlFor="disc"><Input id="disc" type="number" min={0} max={90} className="w-28" value={disc} disabled={!edit} onChange={(e) => setDisc(Number(e.target.value))} /></Field>
        <p className="pb-2 text-xs text-muted-foreground">Yearly price = 12 × round(monthly × (1 − discount)).</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[...plans].sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0)).map((p) => {
          const i = plans.findIndex((x) => x.id === p.id);
          return (
            <Section key={p.id} className={p.popular ? "ring-2 ring-brand-indigo" : ""} title={`${p.id}`}
              actions={<span className="flex gap-1">
                <Button size="icon-xs" variant="ghost" aria-label="Move left" disabled={!edit} onClick={() => move(i, -1)}><ArrowUp className="-rotate-90" /></Button>
                <Button size="icon-xs" variant="ghost" aria-label="Move right" disabled={!edit} onClick={() => move(i, 1)}><ArrowDown className="-rotate-90" /></Button>
              </span>}>
              <div className="space-y-3">
                <Field label="Name" htmlFor={`n-${p.id}`}><Input id={`n-${p.id}`} value={p.name} disabled={!edit} onChange={(e) => set(i, { name: e.target.value })} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="₹ / month" htmlFor={`p-${p.id}`}><Input id={`p-${p.id}`} type="number" min={0} value={p.priceMonthly} disabled={!edit || p.id === "free"} onChange={(e) => set(i, { priceMonthly: Number(e.target.value) })} /></Field>
                  <Field label="Characters / month" htmlFor={`c-${p.id}`}><Input id={`c-${p.id}`} type="number" min={100} value={p.characters} disabled={!edit} onChange={(e) => set(i, { characters: Number(e.target.value) })} /></Field>
                </div>
                {p.id !== "free" && <p className="text-xs text-muted-foreground">Yearly: ₹{(yearlyPm(p.priceMonthly) * 12).toLocaleString("en-IN")} (₹{yearlyPm(p.priceMonthly)}/mo) + GST</p>}
                <Field label="Features (one per line)" htmlFor={`f-${p.id}`}><Textarea id={`f-${p.id}`} rows={5} value={p.features.join("\n")} disabled={!edit} onChange={(e) => set(i, { features: e.target.value.split("\n") })} className="text-xs" /></Field>
                <div className="flex flex-wrap items-center gap-2">
                  <Select aria-label="Visibility" value={p.visibility} disabled={!edit || p.id === "free"} onChange={(e) => set(i, { visibility: e.target.value })}>
                    <option value="public">Public</option><option value="hidden">Hidden</option><option value="legacy">Legacy</option>
                  </Select>
                  <Button size="sm" variant={p.popular ? "default" : "outline"} disabled={!edit} onClick={() => setPlans((ps) => ps.map((x) => ({ ...x, popular: x.id === p.id ? !p.popular : false })))}>
                    <Star /> {p.popular ? "Most popular" : "Mark popular"}
                  </Button>
                </div>
              </div>
            </Section>
          );
        })}
      </div>
      <Section title="Razorpay plan versions" description="Razorpay plans can't be edited, so each price change adds a version. 'Active' = offered to new subscribers; older versions keep their subscribers (grandfathered)." className="mt-6">
        {!data.versions.length && !Object.keys(data.env_plan_ids).length ? (
          <p className="text-sm text-muted-foreground">No Razorpay plans yet. They're created when the Razorpay keys are set (manage.py billing-create-plans) or when a price changes here.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">Plan</th><th>Charge (incl. GST)</th><th>Razorpay id</th><th>Subscribers</th><th>Status</th><th>Created</th></tr></thead>
              <tbody>
                {data.versions.map((v) => (
                  <tr key={v.id} className="border-b last:border-0"><td className="py-2">{planName(v.plan)} · {v.period}</td><td className="tabular">{inr(v.total_paise, 2)}</td>
                    <td className="font-mono text-xs">{v.rzp_plan_id || <span className="text-warning">not created yet</span>}</td><td className="tabular">{v.subscribers}</td>
                    <td><Pill tone={v.active ? "green" : "gray"}>{v.active ? "active" : "grandfathered"}</Pill></td><td className="text-xs">{fmtDate(v.created_at, false)}</td></tr>
                ))}
                {Object.entries(data.env_plan_ids).map(([k, v]) => (
                  <tr key={k} className="border-b last:border-0"><td className="py-2">{k.replace("_", " · ")}</td><td>–</td><td className="font-mono text-xs">{v.id}</td><td className="tabular">{v.subscribers}</td><td><Pill>from api/.env</Pill></td><td>–</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <FormDialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)} title="Review changes" wide submitLabel="Save and publish"
        disabled={!preview || preview.errors.length > 0 || preview.changes.length === 0}
        description="Saving asks you to confirm it's you, commits legal.json, and rebuilds the pricing page (a few minutes)."
        onSubmit={async () => {
          const r = await adminApi<{ commit: string; landing_rebuild: string }>("/api/admin/plans", { method: "PUT", json: body() });
          toast.success(`Saved (commit ${r.commit}); landing rebuild ${r.landing_rebuild}`);
          load();
        }}>
        {preview?.errors.length ? (
          <ul className="space-y-1 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">{preview.errors.map((e) => <li key={e}>{e}</li>)}</ul>
        ) : null}
        {preview && !preview.changes.length && <p className="text-sm text-muted-foreground">Nothing changed.</p>}
        {preview?.changes.length ? (
          <div className="max-h-72 overflow-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-left text-muted-foreground"><th className="p-2">Field</th><th className="p-2">Before</th><th className="p-2">After</th></tr></thead>
              <tbody className="font-mono">{preview.changes.map((c) => (
                <tr key={c.path} className="border-b last:border-0 align-top"><td className="p-2 font-sans">{c.path}</td>
                  <td className="p-2 break-all text-danger">{JSON.stringify(c.before) ?? "–"}</td><td className="p-2 break-all text-success">{JSON.stringify(c.after) ?? "–"}</td></tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
        {preview?.price_changes.length ? (
          <p className="text-sm">New Razorpay plan versions: {preview.price_changes.map((x) => `${planName(x.plan)} ${x.period} ${inr(x.after_paise)}`).join(", ")}. {preview.note}</p>
        ) : null}
      </FormDialog>
    </AdminShell>
  );
}

