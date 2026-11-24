import type { ColumnDef } from "@tanstack/react-table";
import { Ban, Download, FileSpreadsheet, MoreHorizontal, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, inr, LoadingRows, PageHeader, Pill, Section, Stat } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, adminDownload, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

type Inv = {
  id: number; number: string; issued_at: string; user_id: number | null; buyer_name: string; buyer_email: string; buyer_gstin: string;
  buyer_state: string; plan: string; period: string; taxable_paise: number; cgst_paise: number; sgst_paise: number; igst_paise: number;
  total_paise: number; voided_at: string | null; type: string;
};
type CN = { id: number; number: string; invoice_number: string; kind: string; reason: string; issued_at: string; taxable_paise: number; cgst_paise: number; sgst_paise: number; igst_paise: number; total_paise: number };
type Report = {
  month: string; fy: string; sac: string;
  summary: { invoices: number; b2b: number; b2c: number; credit_notes: number; gross: Record<string, number>; credit: Record<string, number>; net: Record<string, number>; payments_received: number };
  sheets: Record<string, Record<string, unknown>[]>;
};

const dl = (url: string, name: string) => adminDownload(url, name).catch((e) => toast.error(errMsg(e)));
const thisMonth = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 7);

function InvoicesTab() {
  const { can } = useAdmin();
  const [voiding, setVoiding] = useState<Inv | null>(null);
  const [reason, setReason] = useState("");
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Inv, unknown>[] = [
    { id: "number", header: "Number", cell: ({ row: { original: i } }) => <div><p className="font-mono text-xs">{i.number}</p>{i.voided_at && <Pill tone="red">void</Pill>}</div> },
    { id: "issued_at", header: "Date", meta: { sortKey: "issued_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.issued_at, false)}</span> },
    { id: "buyer", header: "Buyer", cell: ({ row: { original: i } }) => <div className="max-w-[220px]"><p className="truncate">{i.buyer_name}</p><p className="truncate text-xs text-muted-foreground">{i.buyer_gstin || i.buyer_email}</p></div> },
    { id: "type", header: "Type", cell: ({ row }) => <Pill tone={row.original.type === "B2B" ? "blue" : "gray"}>{row.original.type}</Pill> },
    { id: "pos", header: "State", cell: ({ row }) => <span className="text-xs tabular">{row.original.buyer_state}</span> },
    { id: "plan", header: "Plan", cell: ({ row }) => <span className="text-xs">{planName(row.original.plan)} {row.original.period}</span> },
    { id: "tax", header: "Tax", meta: { className: "text-right" }, cell: ({ row: { original: i } }) => <span className="text-xs tabular">{i.igst_paise ? `IGST ${inr(i.igst_paise, 2)}` : `C+S ${inr(i.cgst_paise + i.sgst_paise, 2)}`}</span> },
    { id: "total", header: "Total", meta: { sortKey: "total", className: "text-right" }, cell: ({ row }) => <span className="tabular">{inr(row.original.total_paise, 2)}</span> },
    { id: "actions", header: "", cell: ({ row: { original: i } }) => (
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button size="icon-xs" variant="ghost" aria-label="Actions"><MoreHorizontal /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => dl(`/api/admin/invoices/${i.id}/pdf`, `${i.number.replaceAll("/", "-")}.pdf`)}><Download /> Download PDF</DropdownMenuItem>
          <DropdownMenuItem disabled={!can("billing.write")} onSelect={async () => {
            try { await adminApi(`/api/admin/invoices/${i.id}/regenerate`, { method: "POST" }); toast.success("PDF regenerated (same number)"); } catch (e) { toast.error(errMsg(e)); }
          }}><RefreshCw /> Regenerate PDF</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={!can("billing.write") || !!i.voided_at} className="text-danger focus:text-danger" onSelect={() => (setReason(""), setVoiding(i))}><Ban /> Void with credit note…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    ) },
  ];
  return (
    <>
      <DataTable<Inv> id="invoices" endpoint="/api/admin/invoices" columns={cols} exportName="invoices" reloadKey={reload}
        searchPlaceholder="AWZ/…, email or name" emptyTitle="No invoices yet" emptyHint="Every captured payment gets a GST invoice AWZ/<FY>/<n>."
        filters={[{ key: "type", label: "Type", options: [{ value: "B2B", label: "B2B (GSTIN)" }, { value: "B2C", label: "B2C" }] }]} />
      <FormDialog open={!!voiding} onOpenChange={(o) => !o && setVoiding(null)} title={`Void ${voiding?.number}`} destructive submitLabel="Void invoice"
        description="Issues a credit note (AWZ-CN/…) for the amount not yet credited. The invoice keeps its number (never renumbered). This doesn't refund money; refund in Payments if needed. Asks you to confirm it's you."
        disabled={reason.trim().length < 3}
        onSubmit={async () => { const r = await adminApi<{ credit_note: CN | null }>(`/api/admin/invoices/${voiding!.id}/void`, { json: { reason } }); toast.success(r.credit_note ? `Credit note ${r.credit_note.number}` : "Voided"); setReload((n) => n + 1); }}>
        <Field label="Reason (on the credit note)" htmlFor="void-reason"><Input id="void-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Issued in error" /></Field>
      </FormDialog>
    </>
  );
}

function CreditNotesTab() {
  const cols: ColumnDef<CN, unknown>[] = [
    { id: "number", header: "Number", cell: ({ row }) => <span className="font-mono text-xs">{row.original.number}</span> },
    { id: "issued_at", header: "Date", meta: { sortKey: "issued_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.issued_at, false)}</span> },
    { id: "invoice", header: "Against", cell: ({ row }) => <span className="font-mono text-xs">{row.original.invoice_number}</span> },
    { id: "kind", header: "Kind", cell: ({ row }) => <Pill tone={row.original.kind === "void" ? "red" : "amber"}>{row.original.kind}</Pill> },
    { id: "reason", header: "Reason", cell: ({ row }) => <span className="text-xs">{row.original.reason}</span> },
    { id: "total", header: "Credited", meta: { className: "text-right" }, cell: ({ row }) => <span className="tabular">{inr(row.original.total_paise, 2)}</span> },
    { id: "pdf", header: "", cell: ({ row: { original: c } }) => <Button size="xs" variant="outline" onClick={() => dl(`/api/admin/credit-notes/${c.id}/pdf`, `${c.number.replaceAll("/", "-")}.pdf`)}><Download /> PDF</Button> },
  ];
  return <DataTable<CN> id="credit-notes" endpoint="/api/admin/credit-notes" columns={cols} exportName="credit-notes" searchPlaceholder="AWZ-CN/… or invoice" emptyTitle="No credit notes" />;
}

function GstTab() {
  const { can } = useAdmin();
  const [month, setMonth] = useState(thisMonth());
  const [rep, setRep] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [sheet, setSheet] = useState("invoice_register");
  const load = useCallback(() => {
    setRep(null);
    setError("");
    adminApi<Report>(`/api/admin/gst/report?month=${month}`).then(setRep, (e) => setError(errMsg(e)));
  }, [month]);
  useEffect(load, [load]);
  const rows = rep?.sheets[sheet] ?? [];
  const r = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Month" htmlFor="gst-month"><Input id="gst-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-44" /></Field>
        {can("billing.export") && (
          <>
            <Button variant="outline" size="sm" onClick={() => dl(`/api/admin/gst/report?month=${month}&format=xlsx`, `aiwazz-gst-${month}.xlsx`)}><FileSpreadsheet /> Excel (all sheets)</Button>
            <Button variant="outline" size="sm" onClick={() => dl(`/api/admin/gst/report?month=${month}&format=csv&sheet=${sheet}`, `aiwazz-gst-${month}-${sheet}.csv`)}><Download /> CSV ({sheet.replaceAll("_", " ")})</Button>
          </>
        )}
      </div>
      {error ? <ErrorState message={error} onRetry={load} /> : !rep ? <LoadingRows rows={4} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Invoices" value={rep.summary.invoices} sub={`${rep.summary.b2b} B2B · ${rep.summary.b2c} B2C`} />
            <Stat label="Taxable (net)" value={r(rep.summary.net.taxable)} sub={`gross ${r(rep.summary.gross.taxable)}`} />
            <Stat label="CGST" value={r(rep.summary.net.cgst)} />
            <Stat label="SGST" value={r(rep.summary.net.sgst)} />
            <Stat label="IGST" value={r(rep.summary.net.igst)} />
            <Stat label="Credit notes" value={rep.summary.credit_notes} sub={`−${r(rep.summary.credit.total)}`} />
          </div>
          <Section title={`FY ${rep.fy} · SAC ${rep.sac}`} description="Place of supply = the buyer's state. Maharashtra (27) → CGST + SGST; other states → IGST. Net = invoices − credit notes.">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {Object.keys(rep.sheets).map((k) => (
                <Button key={k} size="xs" variant={k === sheet ? "default" : "outline"} onClick={() => setSheet(k)}>{k.replaceAll("_", " ")} ({rep.sheets[k].length})</Button>
              ))}
            </div>
            {!rows.length ? <p className="py-6 text-center text-sm text-muted-foreground">No rows this month.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="border-b text-left text-muted-foreground">{Object.keys(rows[0]).map((k) => <th key={k} className="px-2 py-2 font-medium whitespace-nowrap">{k.replaceAll("_", " ")}</th>)}</tr></thead>
                  <tbody>{rows.map((row, i) => <tr key={i} className="border-b last:border-0">{Object.values(row).map((v, j) => <td key={j} className="px-2 py-1.5 whitespace-nowrap tabular">{String(v ?? "")}</td>)}</tr>)}</tbody>
                </table>
              </div>
            )}
          </Section>
          <p className="text-xs text-muted-foreground">SAC 998439 is a placeholder until the CA confirms it (legal.json → sacCode). The "payments tds" sheet lists every payment received with refunds, for TDS reconciliation.</p>
        </>
      )}
    </div>
  );
}

export default function InvoicesPage() {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "invoices";
  return (
    <AdminShell title="Invoices">
      <PageHeader title="Invoices & GST" description="GST tax invoices (AWZ/<FY>/<n>) and credit notes (AWZ-CN/<FY>/<n>), never renumbered, plus the monthly GST report for the CA." />
      <Tabs value={tab} onValueChange={(t) => setSp({ tab: t }, { replace: true })}>
        <TabsList className="mb-4"><TabsTrigger value="invoices">Invoices</TabsTrigger><TabsTrigger value="credit-notes">Credit notes</TabsTrigger><TabsTrigger value="gst">GST reports</TabsTrigger></TabsList>
        <TabsContent value="invoices"><InvoicesTab /></TabsContent>
        <TabsContent value="credit-notes"><CreditNotesTab /></TabsContent>
        <TabsContent value="gst"><GstTab /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}

