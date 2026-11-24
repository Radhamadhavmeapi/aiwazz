import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink, MoreHorizontal, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, PageHeader, Pill, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

export type Sub = {
  id: number; rzp_subscription_id: string; user_id: number | null; email: string; plan: string; period: string; status: string;
  current_start: string | null; current_end: string | null; next_charge_at: string | null; cancel_at_period_end: boolean;
  pending_plan: string | null; pending_period: string | null; created_at: string; dashboard_url: string;
};
const STATUSES = ["created", "authenticated", "active", "pending", "halted", "paused", "cancelled", "completed"];
export const subTone = (s: string) => (s === "active" ? "green" : s === "pending" || s === "halted" ? "amber" : s === "cancelled" ? "red" : "gray");

type Action = { kind: "cancel" | "pause" | "change"; sub: Sub } | null;

export default function SubscriptionsPage() {
  const { can } = useAdmin();
  const [action, setAction] = useState<Action>(null);
  const [reason, setReason] = useState("");
  const [atEnd, setAtEnd] = useState(true);
  const [plan, setPlan] = useState("creator");
  const [period, setPeriod] = useState("monthly");
  const [reload, setReload] = useState(0);
  const open = (kind: "cancel" | "pause" | "change", sub: Sub) => (setReason(""), setAtEnd(true), setPlan(sub.plan), setPeriod(sub.period), setAction({ kind, sub }));
  const done = (msg: string) => (toast.success(msg), setReload((n) => n + 1));
  const cols: ColumnDef<Sub, unknown>[] = [
    { id: "customer", header: "Customer", cell: ({ row: { original: s } }) => (
      <div className="min-w-0">{s.user_id ? <Link to={`/admin/users/${s.user_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{s.email}</Link> : <span className="text-muted-foreground">deleted account</span>}
        <p className="font-mono text-[11px] text-muted-foreground">{s.rzp_subscription_id}</p></div>
    ) },
    { id: "plan", header: "Plan", cell: ({ row: { original: s } }) => (
      <div>{planName(s.plan)} <span className="text-xs text-muted-foreground">· {s.period}</span>
        {s.pending_plan && <p className="text-[11px] text-warning">→ {planName(s.pending_plan)} {s.pending_period} at period end</p>}</div>
    ) },
    { id: "status", header: "Status", cell: ({ row: { original: s } }) => <span className="flex flex-wrap gap-1"><Pill tone={subTone(s.status)}>{s.status}</Pill>{s.cancel_at_period_end && <Pill tone="amber">ends</Pill>}</span> },
    { id: "cycle", header: "Current cycle", cell: ({ row: { original: s } }) => <span className="text-xs whitespace-nowrap">{fmtDate(s.current_start, false)} → {fmtDate(s.current_end, false)}</span> },
    { id: "current_end", header: "Next charge", meta: { sortKey: "current_end" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{row.original.next_charge_at ? fmtDate(row.original.next_charge_at, false) : "–"}</span> },
    { id: "actions", header: "", cell: ({ row: { original: s } }) => (
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button size="icon-xs" variant="ghost" aria-label="Actions" onClick={(e) => e.stopPropagation()}><MoreHorizontal /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild><a href={s.dashboard_url} target="_blank" rel="noopener noreferrer"><ExternalLink /> Open in Razorpay</a></DropdownMenuItem>
          <DropdownMenuItem disabled={!can("billing.write")} onSelect={async () => {
            try { await adminApi(`/api/admin/subscriptions/${s.id}/sync`, { method: "POST" }); done("Synced from Razorpay"); } catch (e) { toast.error(errMsg(e)); }
          }}><RefreshCw /> Sync from Razorpay</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={!can("billing.write") || s.status !== "active"} onSelect={() => open("change", s)}>Change plan…</DropdownMenuItem>
          <DropdownMenuItem disabled={!can("billing.write") || !["active", "paused"].includes(s.status)} onSelect={() => open("pause", s)}>{s.status === "paused" ? "Resume…" : "Pause…"}</DropdownMenuItem>
          <DropdownMenuItem disabled={!can("billing.write") || ["cancelled", "completed", "expired"].includes(s.status)} className="text-danger focus:text-danger" onSelect={() => open("cancel", s)}>Cancel…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ) },
  ];
  const sub = action?.sub;
  return (
    <AdminShell title="Subscriptions">
      <PageHeader title="Subscriptions" description="Razorpay subscriptions. Upgrades apply now (Razorpay prorates); downgrades at the end of the period. Cancel and plan changes ask you to confirm it's you." />
      <DataTable<Sub> id="subscriptions" endpoint="/api/admin/subscriptions" columns={cols} exportName="subscriptions" reloadKey={reload}
        searchPlaceholder="sub_… or email" emptyTitle="No subscriptions yet" emptyHint="They appear when a customer starts checkout."
        filters={[
          { key: "status", label: "Status", options: STATUSES.map((v) => ({ value: v, label: v })) },
          { key: "plan", label: "Plan", options: ["starter", "creator", "pro"].map((v) => ({ value: v, label: planName(v) })) },
          { key: "period", label: "Period", options: [{ value: "monthly", label: "Monthly" }, { value: "yearly", label: "Yearly" }] },
        ]} />
      <FormDialog open={action?.kind === "cancel"} onOpenChange={(o) => !o && setAction(null)} title="Cancel subscription" destructive submitLabel="Cancel subscription"
        description={`${sub?.email} · ${planName(sub?.plan)} ${sub?.period}`} disabled={reason.trim().length < 3}
        onSubmit={async () => { await adminApi(`/api/admin/subscriptions/${sub!.id}/cancel`, { json: { at_period_end: atEnd, reason } }); done("Cancelled"); }}>
        <Field label="When">
          <Select className="w-full" value={atEnd ? "end" : "now"} onChange={(e) => setAtEnd(e.target.value === "end")}>
            <option value="end">At the end of the period (keeps access until {fmtDate(sub?.current_end, false)})</option>
            <option value="now">Now (access ends immediately; refund separately if needed)</option>
          </Select>
        </Field>
        <Field label="Reason (audit log)" htmlFor="sc-reason"><Input id="sc-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
      <FormDialog open={action?.kind === "pause"} onOpenChange={(o) => !o && setAction(null)} title={sub?.status === "paused" ? "Resume subscription" : "Pause subscription"}
        submitLabel={sub?.status === "paused" ? "Resume" : "Pause"} disabled={reason.trim().length < 3}
        description="Razorpay stops (or restarts) charging. Usage limits follow the plan as usual."
        onSubmit={async () => { await adminApi(`/api/admin/subscriptions/${sub!.id}/pause`, { json: { pause: sub!.status !== "paused", reason } }); done("Updated"); }}>
        <Field label="Reason (audit log)" htmlFor="sp-reason"><Input id="sp-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
      <FormDialog open={action?.kind === "change"} onOpenChange={(o) => !o && setAction(null)} title="Change plan" submitLabel="Change plan" disabled={reason.trim().length < 3}
        description="Higher plan (or monthly → yearly): now, Razorpay charges the prorated difference. Lower plan: from the next billing date. Works for card mandates; UPI AutoPay needs cancel + new subscription."
        onSubmit={async () => { const r = await adminApi<{ applies: string }>(`/api/admin/subscriptions/${sub!.id}/change-plan`, { json: { plan, period, reason } }); done(r.applies === "now" ? "Changed now" : "Scheduled for the period end"); }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Plan"><Select className="w-full" value={plan} onChange={(e) => setPlan(e.target.value)}>{["starter", "creator", "pro"].map((p) => <option key={p} value={p}>{planName(p)}</option>)}</Select></Field>
          <Field label="Billing"><Select className="w-full" value={period} onChange={(e) => setPeriod(e.target.value)}><option value="monthly">Monthly</option><option value="yearly">Yearly</option></Select></Field>
        </div>
        <Field label="Reason (audit log)" htmlFor="cp-reason"><Input id="cp-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
    </AdminShell>
  );
}
