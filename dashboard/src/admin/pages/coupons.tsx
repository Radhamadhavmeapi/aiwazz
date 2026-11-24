import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

type Coupon = {
  id: number; code: string; description: string; kind: string; value: number; plans: string[]; periods: string[]; duration: string;
  cycles: number; max_redemptions: number | null; per_user_limit: number; starts_at: string | null; ends_at: string | null; active: boolean;
  rzp_offer_id: string; redemptions: number; state: string; summary: string;
};
type Red = { id: number; email: string; user_id: number | null; status: string; created_at: string };
const blank = { code: "", description: "", kind: "percent", value: "20", plans: [] as string[], periods: ["monthly", "yearly"], duration: "once", cycles: "1",
  max_redemptions: "", per_user_limit: "1", starts_on: "", ends_on: "", active: true, rzp_offer_id: "" };
const stateTone = (s: string) => (s === "active" ? "green" : s === "scheduled" ? "blue" : s === "inactive" ? "gray" : "amber");

function CouponForm({ f, setF, editing }: { f: typeof blank; setF: (f: typeof blank) => void; editing: boolean }) {
  const toggle = (k: "plans" | "periods", v: string) => setF({ ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] });
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Code" htmlFor="cp-code"><Input id="cp-code" value={f.code} disabled={editing} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} placeholder="LAUNCH20" className="font-mono" /></Field>
        <Field label="Razorpay offer id" htmlFor="cp-offer" hint="Create the offer in the Razorpay Dashboard"><Input id="cp-offer" value={f.rzp_offer_id} onChange={(e) => setF({ ...f, rzp_offer_id: e.target.value.trim() })} placeholder="offer_…" className="font-mono" /></Field>
      </div>
      <Field label="Description (internal)" htmlFor="cp-desc"><Input id="cp-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Type"><Select className="w-full" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="percent">% off</option><option value="fixed">₹ off</option></Select></Field>
        <Field label={f.kind === "percent" ? "Percent" : "Rupees"} htmlFor="cp-val"><Input id="cp-val" type="number" min={1} value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
        <Field label="Applies to"><Select className="w-full" value={f.duration} onChange={(e) => setF({ ...f, duration: e.target.value })}><option value="once">First payment</option><option value="cycles">N cycles</option></Select></Field>
      </div>
      {f.duration === "cycles" && <Field label="Cycles" htmlFor="cp-cyc"><Input id="cp-cyc" type="number" min={1} max={36} value={f.cycles} onChange={(e) => setF({ ...f, cycles: e.target.value })} className="w-28" /></Field>}
      <fieldset className="flex flex-wrap gap-x-4 gap-y-2 text-sm"><legend className="mb-1 text-xs font-medium">Plans (none = all)</legend>
        {["starter", "creator", "pro"].map((p) => <label key={p} className="flex items-center gap-1.5"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={f.plans.includes(p)} onChange={() => toggle("plans", p)} />{planName(p)}</label>)}
      </fieldset>
      <fieldset className="flex flex-wrap gap-x-4 gap-y-2 text-sm"><legend className="mb-1 text-xs font-medium">Billing</legend>
        {["monthly", "yearly"].map((p) => <label key={p} className="flex items-center gap-1.5 capitalize"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={f.periods.includes(p)} onChange={() => toggle("periods", p)} />{p}</label>)}
      </fieldset>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Max redemptions (empty = no limit)" htmlFor="cp-max"><Input id="cp-max" type="number" min={1} value={f.max_redemptions} onChange={(e) => setF({ ...f, max_redemptions: e.target.value })} /></Field>
        <Field label="Per user" htmlFor="cp-pu"><Input id="cp-pu" type="number" min={1} max={10} value={f.per_user_limit} onChange={(e) => setF({ ...f, per_user_limit: e.target.value })} /></Field>
        <Field label="Starts (IST)" htmlFor="cp-start"><Input id="cp-start" type="date" value={f.starts_on} onChange={(e) => setF({ ...f, starts_on: e.target.value })} /></Field>
        <Field label="Last day (IST)" htmlFor="cp-end"><Input id="cp-end" type="date" value={f.ends_on} onChange={(e) => setF({ ...f, ends_on: e.target.value })} /></Field>
      </div>
      <label className="flex items-center gap-2 text-sm"><Switch checked={f.active} onCheckedChange={(v) => setF({ ...f, active: v })} aria-label="Active" /> Active</label>
    </>
  );
}

function Referrals() {
  const { can } = useAdmin();
  const [cfg, setCfg] = useState<{ enabled: boolean; reward_chars_referrer: number; reward_chars_referred: number; require_paid: boolean; counts?: Record<string, number> } | null>(null);
  useEffect(() => void adminApi<typeof cfg>("/api/admin/settings/referrals").then(setCfg, () => undefined), []);
  if (!cfg) return null;
  return (
    <Section title="Referral program" description="Data model and settings are ready; the user-facing part stays off until you switch it on (feature flag).">
      <form className="grid max-w-xl gap-4 sm:grid-cols-2" onSubmit={async (e) => {
        e.preventDefault();
        try { const { counts: _c, ...body } = cfg; void _c; setCfg({ ...cfg, ...(await adminApi("/api/admin/settings/referrals", { method: "PUT", json: body })) }); toast.success("Saved"); } catch (err) { toast.error(errMsg(err)); }
      }}>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><Switch checked={cfg.enabled} disabled={!can("coupons.write")} onCheckedChange={(v) => setCfg({ ...cfg, enabled: v })} aria-label="Referrals on" /> Referral program on (shows referral links to users)</label>
        <Field label="Bonus characters for the referrer" htmlFor="rf1"><Input id="rf1" type="number" min={0} value={cfg.reward_chars_referrer} onChange={(e) => setCfg({ ...cfg, reward_chars_referrer: Number(e.target.value) })} /></Field>
        <Field label="Bonus characters for the new user" htmlFor="rf2"><Input id="rf2" type="number" min={0} value={cfg.reward_chars_referred} onChange={(e) => setCfg({ ...cfg, reward_chars_referred: Number(e.target.value) })} /></Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><Switch checked={cfg.require_paid} onCheckedChange={(v) => setCfg({ ...cfg, require_paid: v })} aria-label="Require paid" /> Reward only when the new user pays</label>
        {can("coupons.write") && <Button type="submit" size="sm" className="w-fit">Save</Button>}
        <p className="text-xs text-muted-foreground sm:col-span-2">Referrals so far: {Object.entries(cfg.counts ?? {}).map(([k, v]) => `${v} ${k}`).join(", ") || "none"}</p>
      </form>
    </Section>
  );
}

export default function CouponsPage() {
  const { can } = useAdmin();
  const [form, setForm] = useState<{ id: number | null; f: typeof blank } | null>(null);
  const [reds, setReds] = useState<Coupon | null>(null);
  const [reload, setReload] = useState(0);
  const toBody = (f: typeof blank) => ({
    ...f, value: f.kind === "fixed" ? Math.round(Number(f.value) * 100) : Number(f.value), cycles: Number(f.cycles) || 1,
    max_redemptions: f.max_redemptions ? Number(f.max_redemptions) : null, per_user_limit: Number(f.per_user_limit) || 1,
    starts_on: f.starts_on || null, ends_on: f.ends_on || null,
  });
  const fromCoupon = (c: Coupon): typeof blank => ({
    code: c.code, description: c.description, kind: c.kind, value: String(c.kind === "fixed" ? c.value / 100 : c.value), plans: c.plans, periods: c.periods,
    duration: c.duration, cycles: String(c.cycles), max_redemptions: c.max_redemptions ? String(c.max_redemptions) : "", per_user_limit: String(c.per_user_limit),
    starts_on: c.starts_at ? new Date(Date.parse(c.starts_at) + 5.5 * 3600_000).toISOString().slice(0, 10) : "",
    ends_on: c.ends_at ? new Date(Date.parse(c.ends_at) + 5.5 * 3600_000 - 1).toISOString().slice(0, 10) : "", active: c.active, rzp_offer_id: c.rzp_offer_id,
  });
  const cols: ColumnDef<Coupon, unknown>[] = [
    { id: "code", header: "Code", meta: { sortKey: "code" }, cell: ({ row: { original: c } }) => <div><p className="font-mono font-medium">{c.code}</p><p className="text-xs text-muted-foreground">{c.description}</p></div> },
    { id: "summary", header: "Discount", cell: ({ row: { original: c } }) => <div className="text-xs"><p>{c.summary}</p><p className="text-muted-foreground">{c.plans.length ? c.plans.map(planName).join(", ") : "All plans"} · {c.periods.join(", ")}</p></div> },
    { id: "uses", header: "Used", cell: ({ row: { original: c } }) => <span className="tabular">{c.redemptions}{c.max_redemptions ? ` / ${c.max_redemptions}` : ""}</span> },
    { id: "dates", header: "Valid", cell: ({ row: { original: c } }) => <span className="text-xs">{c.starts_at ? fmtDate(c.starts_at, false) : "now"} → {c.ends_at ? fmtDate(c.ends_at, false) : "no end"}</span> },
    { id: "offer", header: "Offer", cell: ({ row }) => row.original.rzp_offer_id ? <span className="font-mono text-xs">{row.original.rzp_offer_id}</span> : <Pill tone="amber">no offer id</Pill> },
    { id: "state", header: "State", cell: ({ row }) => <Pill tone={stateTone(row.original.state)}>{row.original.state}</Pill> },
  ];
  return (
    <AdminShell title="Coupons">
      <PageHeader title="Coupons & promotions" description="Discount codes are applied through Razorpay Offers (create the offer in the Razorpay Dashboard, paste its id here). AiWazz checks plan, billing period, dates and limits before checkout."
        actions={can("coupons.write") && <Button variant="brand" size="sm" onClick={() => setForm({ id: null, f: { ...blank } })}><Plus /> New coupon</Button>} />
      <Tabs defaultValue="coupons">
        <TabsList className="mb-4"><TabsTrigger value="coupons">Coupons</TabsTrigger><TabsTrigger value="referrals">Referrals</TabsTrigger></TabsList>
        <TabsContent value="coupons">
          <DataTable<Coupon> id="coupons" endpoint="/api/admin/coupons" columns={cols} exportName="coupons" reloadKey={reload} searchPlaceholder="Code…"
            onRowClick={(c) => (can("coupons.write") ? setForm({ id: c.id, f: fromCoupon(c) }) : setReds(c))} emptyTitle="No coupons yet" />
        </TabsContent>
        <TabsContent value="referrals"><Referrals /></TabsContent>
      </Tabs>
      <FormDialog open={!!form} onOpenChange={(o) => !o && setForm(null)} title={form?.id ? `Edit ${form.f.code}` : "New coupon"} wide submitLabel={form?.id ? "Save" : "Create"}
        disabled={!form?.f.code || !Number(form?.f.value)}
        onSubmit={async () => {
          await adminApi(form!.id ? `/api/admin/coupons/${form!.id}` : "/api/admin/coupons", { method: form!.id ? "PUT" : "POST", json: toBody(form!.f) });
          toast.success("Saved");
          setReload((n) => n + 1);
        }}>
        {form && <CouponForm f={form.f} setF={(f) => setForm({ ...form, f })} editing={!!form.id} />}
        {form?.id && <Button type="button" variant="link" size="sm" className="px-0" onClick={async () => setReds((await adminApi<{ items: Coupon[] }>(`/api/admin/coupons?q=${form.f.code}`)).items[0] ?? null)}>See redemptions</Button>}
      </FormDialog>
      <Sheet open={!!reds} onOpenChange={(o) => !o && setReds(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          <SheetHeader><SheetTitle className="font-mono">{reds?.code}</SheetTitle><SheetDescription>{reds?.summary}</SheetDescription></SheetHeader>
          {reds && <div className="px-4 pb-6"><DataTable<Red> id="redemptions" syncUrl={false} endpoint={`/api/admin/coupons/${reds.id}/redemptions`} searchPlaceholder={null} emptyTitle="Not used yet"
            columns={[
              { id: "email", header: "Customer", cell: ({ row }) => row.original.email || "–" },
              { id: "status", header: "Status", cell: ({ row }) => <Pill tone={row.original.status === "redeemed" ? "green" : "gray"}>{row.original.status}</Pill> },
              { id: "created_at", header: "When", cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at)}</span> },
            ]} /></div>}
        </SheetContent>
      </Sheet>
    </AdminShell>
  );
}
