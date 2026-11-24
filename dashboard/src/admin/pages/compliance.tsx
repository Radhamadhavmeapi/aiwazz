import type { ColumnDef } from "@tanstack/react-table";
import { Download, Eye, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, adminDownload, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Dsr = { id: number; kind: string; email: string; user_id: number | null; status: string; details: string; notes: string; received_at: string; due_at: string; completed_at: string | null; overdue: boolean };
type Consent = { id: number; email: string; consent_at: string | null; terms_version: string | null; consent_ip: string | null; marketing_opt_in: boolean };
type Del = { id: number; reference: string; generations_deleted: number; created_at: string };
const KIND: Record<string, string> = { access: "Access / export", correction: "Correction", deletion: "Deletion", grievance: "Grievance" };

function Requests() {
  const { can } = useAdmin();
  const [create, setCreate] = useState(false);
  const [f, setF] = useState({ kind: "access", email: "", details: "" });
  const [edit, setEdit] = useState<Dsr | null>(null);
  const [status, setStatus] = useState("in_progress");
  const [notes, setNotes] = useState("");
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Dsr, unknown>[] = [
    { id: "received_at", header: "Received", meta: { sortKey: "received_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.received_at, false)}</span> },
    { id: "kind", header: "Request", cell: ({ row }) => <Pill tone={row.original.kind === "deletion" ? "red" : "blue"}>{KIND[row.original.kind]}</Pill> },
    { id: "email", header: "Person", cell: ({ row: { original: d } }) => d.user_id ? <Link to={`/admin/users/${d.user_id}`} className="text-xs hover:underline" onClick={(e) => e.stopPropagation()}>{d.email}</Link> : <span className="text-xs">{d.email} (no account)</span> },
    { id: "due_at", header: "Due", meta: { sortKey: "due_at" }, cell: ({ row: { original: d } }) => <span className={`text-xs ${d.overdue ? "font-semibold text-danger" : ""}`}>{fmtDate(d.due_at, false)}{d.overdue ? " · overdue" : ""}</span> },
    { id: "status", header: "Status", cell: ({ row }) => <Pill tone={row.original.status === "done" ? "green" : row.original.status === "rejected" ? "gray" : "amber"}>{row.original.status.replace("_", " ")}</Pill> },
    { id: "act", header: "", cell: ({ row: { original: d } }) => d.user_id && d.kind === "access" && can("users.export") ? (
      <Button size="xs" variant="outline" onClick={(e) => (e.stopPropagation(), adminDownload(`/api/admin/users/${d.user_id}/export`, `aiwazz-user-${d.user_id}-export.json`).catch((er) => toast.error(errMsg(er))))}><Download /> Export data</Button>
    ) : d.user_id && d.kind === "deletion" ? <Button size="xs" variant="outline" asChild><Link to={`/admin/users/${d.user_id}`}>Open to delete</Link></Button> : null },
  ];
  return (
    <>
      <p className="mb-3 text-xs text-muted-foreground">DPDP Act 2023 requests. Due dates: 30 days (access, correction, deletion), 15 days (grievance). Access = one-click JSON export with audio links still valid.</p>
      <DataTable<Dsr> id="dsr" endpoint="/api/admin/dsr" columns={cols} reloadKey={reload} exportName="dsr" searchPlaceholder="Email…" emptyTitle="No requests"
        onRowClick={can("compliance.write") ? (d) => (setStatus(d.status), setNotes(d.notes), setEdit(d)) : undefined}
        filters={[{ key: "status", label: "Status", options: [{ value: "open", label: "Open" }, { value: "done", label: "Done" }, { value: "rejected", label: "Rejected" }] },
                  { key: "kind", label: "Kind", options: Object.entries(KIND).map(([value, label]) => ({ value, label })) }]}
        toolbar={can("compliance.write") && <Button size="sm" variant="brand" onClick={() => setCreate(true)}><Plus /> Log a request</Button>} />
      <FormDialog open={create} onOpenChange={setCreate} title="Log a data request" disabled={!f.email.includes("@")}
        onSubmit={async () => { await adminApi("/api/admin/dsr", { json: f }); toast.success("Logged"); setF({ kind: "access", email: "", details: "" }); setReload((n) => n + 1); }}>
        <Field label="Kind"><Select className="w-full" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Email of the person" htmlFor="dsr-email"><Input id="dsr-email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Details" htmlFor="dsr-det"><Textarea id="dsr-det" rows={3} value={f.details} onChange={(e) => setF({ ...f, details: e.target.value })} placeholder="Received by email on … (ticket AWZ-T-…)" /></Field>
      </FormDialog>
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={`${edit ? KIND[edit.kind] : ""}: ${edit?.email}`} description={edit?.details}
        onSubmit={async () => { await adminApi(`/api/admin/dsr/${edit!.id}`, { method: "PATCH", json: { status, notes } }); toast.success("Updated"); setReload((n) => n + 1); }}>
        <Field label="Status"><Select className="w-full" value={status} onChange={(e) => setStatus(e.target.value)}><option value="new">New</option><option value="in_progress">In progress</option><option value="done">Done</option><option value="rejected">Rejected</option></Select></Field>
        <Field label="Notes" htmlFor="dsr-notes"><Textarea id="dsr-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      </FormDialog>
    </>
  );
}

function Consents() {
  const cols: ColumnDef<Consent, unknown>[] = [
    { id: "email", header: "Account", cell: ({ row }) => <Link to={`/admin/users/${row.original.id}`} className="text-xs hover:underline">{row.original.email}</Link> },
    { id: "consent_at", header: "Accepted", meta: { sortKey: "consent_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.consent_at)}</span> },
    { id: "terms", header: "Terms version", cell: ({ row }) => <span className="text-xs">{row.original.terms_version ?? "–"}</span> },
    { id: "ip", header: "IP", cell: ({ row }) => <span className="font-mono text-xs">{row.original.consent_ip ?? "–"}</span> },
    { id: "mk", header: "Marketing", cell: ({ row }) => <Pill tone={row.original.marketing_opt_in ? "green" : "gray"}>{row.original.marketing_opt_in ? "opted in" : "no"}</Pill> },
  ];
  return <DataTable<Consent> id="consents" endpoint="/api/admin/compliance/consents" columns={cols} exportName="consents" searchPlaceholder="Email or terms version…"
    filters={[{ key: "marketing", label: "Marketing", options: [{ value: "yes", label: "Opted in" }, { value: "no", label: "Not opted in" }] }]} />;
}

function Deletions() {
  const cols: ColumnDef<Del, unknown>[] = [
    { id: "reference", header: "Reference", cell: ({ row }) => <span className="font-mono text-xs">{row.original.reference}</span> },
    { id: "created_at", header: "Deleted", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at)}</span> },
    { id: "gens", header: "Generations removed", cell: ({ row }) => <span className="tabular">{row.original.generations_deleted}</span> },
  ];
  return (
    <>
      <p className="mb-3 text-xs text-muted-foreground">No email addresses are kept after deletion; searching an email matches its fingerprint (SHA-256), so you can confirm a deletion to the person.</p>
      <DataTable<Del> id="deletions" endpoint="/api/admin/compliance/deletions" columns={cols} searchPlaceholder="Reference or the deleted email…" emptyTitle="No deletions" />
    </>
  );
}

function PolicyHistory() {
  const [d, setD] = useState<{ items: { commit: string; date: string; author: string; message: string }[]; current: { effectiveDate: string; lastUpdated: string } } | null>(null);
  useEffect(() => void adminApi<typeof d>("/api/admin/compliance/policy-history").then(setD, () => undefined), []);
  if (!d) return <LoadingRows rows={5} />;
  return (
    <Section title="Policy versions" description={`Current: effective ${d.current.effectiveDate}, last updated ${d.current.lastUpdated}. Every change to legal/ is a git commit.`}>
      <ol className="divide-y text-sm">{d.items.map((c) => (
        <li key={c.commit} className="flex flex-wrap gap-3 py-2"><span className="w-24 shrink-0 text-xs text-muted-foreground">{c.date}</span><span className="font-mono text-xs">{c.commit}</span><span className="min-w-0 flex-1">{c.message}</span></li>
      ))}</ol>
    </Section>
  );
}

function LegalEditor() {
  const { can } = useAdmin();
  const [text, setText] = useState("");
  const [orig, setOrig] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ errors: string[]; changes: { path: string; before: unknown; after: unknown }[] } | null>(null);
  const load = useCallback(() => adminApi<{ data: object }>("/api/admin/legal").then((r) => { const t = JSON.stringify(r.data, null, 2); setText(t); setOrig(t); }, (e) => setError(errMsg(e))), []);
  useEffect(() => void load(), [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  const parsed = (() => { try { return JSON.parse(text); } catch { return null; } })();
  const write = can("legal.write");
  return (
    <Section title="Company & legal data (legal/legal.json)" description="Name, address, GSTIN, emails, grievance officer, dates… used by every legal page, invoices and the footer. Plans are edited in Plans & pricing. Saving validates, shows the changes, commits to git and rebuilds aiwazz.in (asks you to confirm it's you)."
      actions={write && <Button size="sm" variant="brand" disabled={!parsed || text === orig} onClick={async () => {
        try { setPreview(await adminApi("/api/admin/legal/preview", { json: { data: parsed } })); } catch (e) { toast.error(errMsg(e)); }
      }}><Eye /> Review changes</Button>}>
      <Textarea aria-label="legal.json" rows={24} value={text} disabled={!write} onChange={(e) => setText(e.target.value)} className="font-mono text-xs" spellCheck={false} />
      {!parsed && <p className="mt-2 text-sm text-danger">That isn't valid JSON yet.</p>}
      <FormDialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)} title="Review legal data changes" wide submitLabel="Save and publish"
        disabled={!preview || preview.errors.length > 0 || !preview.changes.length}
        onSubmit={async () => { const r = await adminApi<{ commit: string; landing_rebuild: string }>("/api/admin/legal", { method: "PUT", json: { data: parsed } }); toast.success(`Saved (commit ${r.commit}); landing ${r.landing_rebuild}`); load(); }}>
        {preview?.errors.length ? <ul className="space-y-1 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">{preview.errors.map((e) => <li key={e}>{e}</li>)}</ul> : null}
        <div className="max-h-80 overflow-auto rounded-lg border">
          <table className="w-full text-xs"><thead><tr className="border-b text-left text-muted-foreground"><th className="p-2">Field</th><th className="p-2">Before</th><th className="p-2">After</th></tr></thead>
            <tbody className="font-mono">{preview?.changes.map((c) => <tr key={c.path} className="border-b align-top last:border-0"><td className="p-2 font-sans">{c.path}</td><td className="p-2 break-all text-danger">{JSON.stringify(c.before) ?? "–"}</td><td className="p-2 break-all text-success">{JSON.stringify(c.after) ?? "–"}</td></tr>)}</tbody></table>
        </div>
      </FormDialog>
    </Section>
  );
}

export default function CompliancePage() {
  return (
    <AdminShell title="Compliance">
      <PageHeader title="Compliance (DPDP & legal)" description="Data-subject requests with due dates, consent records, the deletion log, policy history and the company/legal data editor." />
      <Tabs defaultValue="requests">
        <TabsList className="mb-4 flex-wrap"><TabsTrigger value="requests">Requests</TabsTrigger><TabsTrigger value="consents">Consents</TabsTrigger><TabsTrigger value="deletions">Deletion log</TabsTrigger><TabsTrigger value="history">Policy history</TabsTrigger><TabsTrigger value="legal">Company data</TabsTrigger></TabsList>
        <TabsContent value="requests"><Requests /></TabsContent>
        <TabsContent value="consents"><Consents /></TabsContent>
        <TabsContent value="deletions"><Deletions /></TabsContent>
        <TabsContent value="history"><PolicyHistory /></TabsContent>
        <TabsContent value="legal"><LegalEditor /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}
