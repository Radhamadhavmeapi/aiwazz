import type { ColumnDef } from "@tanstack/react-table";
import { ExternalLink, Loader2, RotateCcw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, inr, PageHeader, Pill, Section } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Pay = {
  id: number; rzp_payment_id: string; user_id: number | null; email: string; amount_paise: number; status: string; method: string;
  error: string; refunded_paise: number; created_at: string; dashboard_url: string;
  invoice: { id: number; number: string; taxable_paise: number; cgst_paise: number; sgst_paise: number; igst_paise: number } | null;
};
type RefundRow = { id: number; rzp_refund_id: string | null; payment_id: number; email: string; amount_paise: number; reason: string; status: string; created_at: string; processed_at: string | null; credit_note_id: number | null };
type Dunning = { id: number; email: string; user_id: number | null; subscription: string; plan: string; sub_status: string; started_at: string; grace_until: string; failures: number; last_error: string; emails_sent: number[]; status: string };
type Hook = { id: string; event: string; received_at: string; signature_ok: boolean; status: string; note: string; replays: number };

const payTone = (s: string) => (s === "captured" ? "green" : s === "failed" ? "red" : s === "refunded" ? "amber" : "gray");

function PaymentsTab() {
  const { can } = useAdmin();
  const [refund, setRefund] = useState<Pay | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Pay, unknown>[] = [
    { id: "created_at", header: "Date (IST)", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at)}</span> },
    { id: "payment", header: "Payment", cell: ({ row: { original: x } }) => (
      <div><a href={x.dashboard_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-mono text-xs hover:underline" onClick={(e) => e.stopPropagation()}>{x.rzp_payment_id}<ExternalLink className="size-3" /></a>
        {x.user_id ? <p className="text-xs"><Link to={`/admin/users/${x.user_id}`} className="text-muted-foreground hover:underline">{x.email}</Link></p> : <p className="text-xs text-muted-foreground">deleted account</p>}</div>
    ) },
    { id: "amount", header: "Amount", meta: { sortKey: "amount", className: "text-right" }, cell: ({ row: { original: x } }) => (
      <div className="text-right"><p className="tabular">{inr(x.amount_paise, 2)}</p>{x.refunded_paise > 0 && <p className="text-[11px] text-warning tabular">−{inr(x.refunded_paise, 2)} refunded</p>}</div>
    ) },
    { id: "gst", header: "GST split", cell: ({ row: { original: x } }) => x.invoice ? (
      <div className="text-[11px] leading-tight text-muted-foreground tabular"><p className="font-mono text-foreground">{x.invoice.number}</p>
        <p>{inr(x.invoice.taxable_paise, 2)} + {x.invoice.igst_paise ? `IGST ${inr(x.invoice.igst_paise, 2)}` : `CGST ${inr(x.invoice.cgst_paise, 2)} + SGST ${inr(x.invoice.sgst_paise, 2)}`}</p></div>
    ) : <span className="text-xs text-muted-foreground">–</span> },
    { id: "method", header: "Method", cell: ({ row }) => <span className="text-xs uppercase">{row.original.method || "–"}</span> },
    { id: "status", header: "Status", cell: ({ row: { original: x } }) => <div><Pill tone={payTone(x.status)}>{x.status}</Pill>{x.error && <p className="mt-0.5 max-w-[180px] truncate text-[11px] text-danger" title={x.error}>{x.error}</p>}</div> },
    { id: "actions", header: "", cell: ({ row: { original: x } }) => can("billing.refund") && x.status === "captured" ? (
      <Button size="xs" variant="outline" onClick={(e) => (e.stopPropagation(), setAmount(""), setReason(""), setRefund(x))}><Undo2 /> Refund</Button>
    ) : null },
  ];
  const left = refund ? refund.amount_paise - refund.refunded_paise : 0;
  return (
    <>
      <DataTable<Pay> id="payments" endpoint="/api/admin/payments" columns={cols} exportName="payments" reloadKey={reload}
        searchPlaceholder="pay_…, email or invoice no." emptyTitle="No payments yet"
        filters={[
          { key: "status", label: "Status", options: ["captured", "failed", "refunded", "authorized"].map((v) => ({ value: v, label: v })) },
          { key: "method", label: "Method", options: ["upi", "card", "netbanking", "wallet"].map((v) => ({ value: v, label: v.toUpperCase() })) },
        ]} />
      <FormDialog open={!!refund} onOpenChange={(o) => !o && setRefund(null)} title="Refund payment" destructive submitLabel="Refund"
        description={`${refund?.rzp_payment_id} · up to ${inr(left, 2)} can be refunded. A GST credit note is created automatically when Razorpay confirms. Asks you to confirm it's you.`}
        disabled={reason.trim().length < 3 || (!!amount && !(Number(amount) > 0))}
        onSubmit={async () => {
          await adminApi(`/api/admin/payments/${refund!.id}/refund`, { json: { amount_paise: amount ? Math.round(Number(amount) * 100) : null, reason } });
          toast.success("Refund requested; status updates by webhook");
          setReload((n) => n + 1);
        }}>
        <Field label="Amount in ₹ (empty = full remaining)" htmlFor="rf-amt"><Input id="rf-amt" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={(left / 100).toFixed(2)} /></Field>
        <Field label="Reason (audit log + Razorpay note)" htmlFor="rf-reason"><Input id="rf-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
    </>
  );
}

function RefundsTab() {
  const cols: ColumnDef<RefundRow, unknown>[] = [
    { id: "created_at", header: "Requested", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at)}</span> },
    { id: "id", header: "Refund", cell: ({ row: { original: r } }) => <div><p className="font-mono text-xs">{r.rzp_refund_id ?? "–"}</p><p className="text-xs text-muted-foreground">{r.email}</p></div> },
    { id: "amount", header: "Amount", meta: { className: "text-right" }, cell: ({ row }) => <span className="tabular">{inr(row.original.amount_paise, 2)}</span> },
    { id: "reason", header: "Reason", cell: ({ row }) => <span className="text-xs">{row.original.reason}</span> },
    { id: "status", header: "Status", cell: ({ row: { original: r } }) => <Pill tone={r.status === "processed" ? "green" : r.status === "failed" ? "red" : "amber"}>{r.status}</Pill> },
    { id: "cn", header: "Credit note", cell: ({ row: { original: r } }) => r.credit_note_id ? <Link className="text-xs text-brand hover:underline" to="/admin/invoices?tab=credit-notes">view</Link> : "–" },
  ];
  return <DataTable<RefundRow> id="refunds" endpoint="/api/admin/refunds" columns={cols} exportName="refunds" searchPlaceholder={null} emptyTitle="No refunds" />;
}

function DunningTab() {
  const { can } = useAdmin();
  const [cfg, setCfg] = useState<{ grace_days: number; dunning_emails: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => void adminApi<{ grace_days: number; dunning_emails: boolean }>("/api/admin/settings/billing").then(setCfg, () => undefined), []);
  const cols: ColumnDef<Dunning, unknown>[] = [
    { id: "started_at", header: "Failed since", meta: { sortKey: "started_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.started_at)}</span> },
    { id: "customer", header: "Customer", cell: ({ row: { original: d } }) => <div>{d.user_id ? <Link to={`/admin/users/${d.user_id}`} className="hover:underline">{d.email}</Link> : "–"}<p className="font-mono text-[11px] text-muted-foreground">{d.subscription} · {d.plan}</p></div> },
    { id: "failures", header: "Failures", cell: ({ row: { original: d } }) => <div><span className="tabular">{d.failures}</span><p className="max-w-[200px] truncate text-[11px] text-muted-foreground" title={d.last_error}>{d.last_error}</p></div> },
    { id: "emails", header: "Emails (day)", cell: ({ row }) => <span className="text-xs tabular">{row.original.emails_sent.join(", ") || "–"}</span> },
    { id: "grace", header: "Grace until", cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.grace_until)}</span> },
    { id: "status", header: "Status", cell: ({ row: { original: d } }) => <Pill tone={d.status === "open" ? "amber" : d.status === "resolved" ? "green" : "red"}>{d.status}</Pill> },
  ];
  return (
    <div className="space-y-4">
      <Section title="Dunning settings" description="After a failed renewal the customer keeps paid access for the grace period, gets emails on day 0, 3 and 7, then moves to Free. Razorpay retries the charge itself.">
        {cfg && (
          <form className="flex flex-wrap items-end gap-4" onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try { setCfg(await adminApi("/api/admin/settings/billing", { method: "PUT", json: cfg })); toast.success("Saved"); } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
          }}>
            <Field label="Grace period (days)" htmlFor="grace"><Input id="grace" type="number" min={0} max={30} className="w-28" value={cfg.grace_days} disabled={!can("billing.write")} onChange={(e) => setCfg({ ...cfg, grace_days: Number(e.target.value) })} /></Field>
            <label className="flex h-9 items-center gap-2 text-sm"><Switch checked={cfg.dunning_emails} disabled={!can("billing.write")} onCheckedChange={(v) => setCfg({ ...cfg, dunning_emails: v })} aria-label="Reminder emails" /> Reminder emails</label>
            {can("billing.write") && <Button type="submit" size="sm" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Save</Button>}
          </form>
        )}
      </Section>
      <DataTable<Dunning> id="dunning" endpoint="/api/admin/dunning" columns={cols} searchPlaceholder={null} emptyTitle="No failed renewals"
        filters={[{ key: "status", label: "Status", options: ["open", "resolved", "downgraded"].map((v) => ({ value: v, label: v })) }]} />
    </div>
  );
}

function WebhooksTab() {
  const { can } = useAdmin();
  const [open, setOpen] = useState<(Hook & { payload?: string | null }) | null>(null);
  const [reload, setReload] = useState(0);
  const show = useCallback(async (h: Hook) => {
    try { setOpen(await adminApi(`/api/admin/webhooks/${encodeURIComponent(h.id)}`)); } catch (e) { toast.error(errMsg(e)); }
  }, []);
  const cols: ColumnDef<Hook, unknown>[] = [
    { id: "received_at", header: "Received", meta: { sortKey: "received_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.received_at)}</span> },
    { id: "event", header: "Event", cell: ({ row }) => <span className="font-mono text-xs">{row.original.event}</span> },
    { id: "sig", header: "Signature", cell: ({ row }) => <Pill tone={row.original.signature_ok ? "green" : "red"}>{row.original.signature_ok ? "valid" : "invalid"}</Pill> },
    { id: "status", header: "Result", cell: ({ row: { original: h } }) => <div><Pill tone={h.status === "processed" ? "green" : h.status === "failed" || h.status === "rejected" ? "red" : "gray"}>{h.status}</Pill>
      {h.replays > 0 && <span className="ml-1 text-[11px] text-muted-foreground">replayed {h.replays}×</span>}</div> },
    { id: "note", header: "Note", cell: ({ row }) => <p className="max-w-sm truncate text-xs text-muted-foreground" title={row.original.note}>{row.original.note}</p> },
  ];
  return (
    <>
      <DataTable<Hook> id="webhooks" endpoint="/api/admin/webhooks" columns={cols} reloadKey={reload} searchPlaceholder="Event or id…" onRowClick={show}
        emptyTitle="No webhook events yet" emptyHint="Razorpay sends them to https://login.aiwazz.in/api/billing/webhook once the webhook is configured."
        filters={[{ key: "status", label: "Result", options: ["processed", "failed", "ignored", "rejected"].map((v) => ({ value: v, label: v })) }]} />
      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle className="font-mono text-base">{open?.event}</SheetTitle>
            <SheetDescription>{open?.id} · {fmtDate(open?.received_at)}</SheetDescription>
          </SheetHeader>
          {open && (
            <div className="space-y-4 px-4 pb-6">
              <p className="text-sm">{open.note || "–"}</p>
              {can("billing.write") && open.signature_ok && (
                <Button size="sm" variant="outline" onClick={async () => {
                  try { const r = await adminApi<Hook>(`/api/admin/webhooks/${encodeURIComponent(open.id)}/replay`, { method: "POST" }); toast.success(`Replayed: ${r.status}`); setReload((n) => n + 1); setOpen(null); } catch (e) { toast.error(errMsg(e)); }
                }}><RotateCcw /> Replay (idempotent)</Button>
              )}
              <pre className="max-h-[60vh] overflow-auto rounded-lg border bg-surface-2/60 p-3 font-mono text-[11px] whitespace-pre-wrap break-all">{(() => {
                try { return JSON.stringify(JSON.parse(open.payload ?? ""), null, 2); } catch { return open.payload ?? ""; }
              })()}</pre>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

export default function PaymentsPage() {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "payments";
  return (
    <AdminShell title="Payments">
      <PageHeader title="Payments" description="Every Razorpay payment (including failed), refunds with automatic credit notes, failed renewals (dunning) and the webhook log." />
      <Tabs value={tab} onValueChange={(t) => setSp({ tab: t }, { replace: true })}>
        <TabsList className="mb-4"><TabsTrigger value="payments">Payments</TabsTrigger><TabsTrigger value="refunds">Refunds</TabsTrigger><TabsTrigger value="dunning">Dunning</TabsTrigger><TabsTrigger value="webhooks">Webhooks</TabsTrigger></TabsList>
        <TabsContent value="payments"><PaymentsTab /></TabsContent>
        <TabsContent value="refunds"><RefundsTab /></TabsContent>
        <TabsContent value="dunning"><DunningTab /></TabsContent>
        <TabsContent value="webhooks"><WebhooksTab /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}
