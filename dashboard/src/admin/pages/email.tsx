import type { ColumnDef } from "@tanstack/react-table";
import { Loader2, RotateCcw, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { DataTable } from "../components/data-table";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Tpl = { key: string; name: string; variables: string[]; customized: boolean; subject: string; body: string; default_subject: string; default_body: string };
type Log = { id: number; to: string; template: string; subject: string; status: string; message_id: string; created_at: string };
type Sup = { id: string; email: string; reason: string; note: string; created_at: string };

function Templates() {
  const { can } = useAdmin();
  const [items, setItems] = useState<Tpl[] | null>(null);
  const [mailOn, setMailOn] = useState(false);
  const [sel, setSel] = useState<string>("welcome");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<{ subject: string; html: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => adminApi<{ items: Tpl[]; mail_enabled: boolean }>("/api/admin/email/templates").then((r) => (setItems(r.items), setMailOn(r.mail_enabled)), (e) => setError(errMsg(e))), []);
  useEffect(() => void load(), [load]);
  const cur = items?.find((t) => t.key === sel);
  useEffect(() => { if (cur) (setSubject(cur.subject), setBody(cur.body)); }, [cur?.key, cur?.subject, cur?.body]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!cur) return;
    const t = setTimeout(() => adminApi<{ subject: string; html: string }>("/api/admin/email/preview", { json: { key: cur.key, subject, body } }).then(setPreview, () => undefined), 300);
    return () => clearTimeout(t);
  }, [cur, subject, body]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!items || !cur) return <LoadingRows rows={6} />;
  const write = can("email.write");
  const dirty = subject !== cur.subject || body !== cur.body;
  const run = async (k: string, fn: () => Promise<unknown>) => { setBusy(k); try { await fn(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); } };
  return (
    <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
      <nav aria-label="Templates" className="flex gap-1 overflow-x-auto lg:flex-col">
        {items.map((t) => (
          <button key={t.key} type="button" onClick={() => setSel(t.key)}
            className={cn("shrink-0 rounded-lg px-3 py-2 text-left text-sm", t.key === sel ? "bg-surface-2 font-medium" : "text-muted-foreground hover:bg-surface-2/60")}>
            {t.name} {t.customized && <span className="ml-1 size-1.5 rounded-full bg-brand-indigo inline-block align-middle" aria-label="customized" />}
          </button>
        ))}
      </nav>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title={cur.name} description={<>Variables: {cur.variables.map((v) => <code key={v} className="mr-1 font-mono">{`{{${v}}}`}</code>)}</>}>
          <div className="space-y-3">
            <Field label="Subject" htmlFor="tpl-subj"><Input id="tpl-subj" value={subject} disabled={!write} onChange={(e) => setSubject(e.target.value)} /></Field>
            <Field label="Body (plain text; blank line = new paragraph; links become clickable)" htmlFor="tpl-body"><Textarea id="tpl-body" rows={14} value={body} disabled={!write} onChange={(e) => setBody(e.target.value)} className="font-mono text-xs" /></Field>
            {write && (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={!dirty || busy === "save"} onClick={() => run("save", async () => { await adminApi(`/api/admin/email/templates/${cur.key}`, { method: "PUT", json: { subject, body } }); toast.success("Saved"); await load(); })}>{busy === "save" && <Loader2 className="animate-spin" />} Save</Button>
                <Button size="sm" variant="outline" disabled={!cur.customized} onClick={() => run("reset", async () => { await adminApi(`/api/admin/email/templates/${cur.key}`, { method: "DELETE" }); toast.success("Back to the default text"); await load(); })}><RotateCcw /> Reset to default</Button>
                <Button size="sm" variant="outline" disabled={dirty || busy === "test"} onClick={() => run("test", async () => { const r = await adminApi<{ status: string; to: string }>("/api/admin/email/test-send", { json: { key: cur.key } }); toast.success(`Test to ${r.to}: ${r.status}`); })}><Send /> Send me a test</Button>
              </div>
            )}
            {!mailOn && <p className="text-xs text-warning">Mail is off on the server: emails are logged (status "disabled") but not delivered.</p>}
          </div>
        </Section>
        <Section title="Live preview" description={preview ? `Subject: ${preview.subject}` : "…"}>
          {preview && <iframe title="Email preview" sandbox="" srcDoc={preview.html} className="h-[480px] w-full rounded-lg border bg-white" />}
        </Section>
      </div>
    </div>
  );
}

function LogTab() {
  const cols: ColumnDef<Log, unknown>[] = [
    { id: "created_at", header: "When", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at)}</span> },
    { id: "to", header: "To", cell: ({ row }) => <span className="text-xs">{row.original.to}</span> },
    { id: "template", header: "Template", cell: ({ row }) => <span className="font-mono text-xs">{row.original.template}</span> },
    { id: "subject", header: "Subject", cell: ({ row }) => <span className="line-clamp-1 text-xs">{row.original.subject}</span> },
    { id: "status", header: "Status", cell: ({ row }) => <Pill tone={row.original.status === "sent" ? "green" : row.original.status === "failed" || row.original.status === "bounced" ? "red" : "gray"}>{row.original.status}</Pill> },
    { id: "mid", header: "Message-ID", cell: ({ row }) => <span className="font-mono text-[10px] text-muted-foreground">{row.original.message_id || "–"}</span> },
  ];
  return <DataTable<Log> id="email-log" endpoint="/api/admin/email/log" columns={cols} exportName="email-log" searchPlaceholder="Address, subject, Message-ID…" emptyTitle="Nothing sent yet"
    filters={[{ key: "status", label: "Status", options: ["sent", "disabled", "failed", "suppressed", "bounced"].map((v) => ({ value: v, label: v })) }]} />;
}

function Suppressions() {
  const { can } = useAdmin();
  const [f, setF] = useState({ email: "", reason: "manual", note: "" });
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Sup, unknown>[] = [
    { id: "email", header: "Email", cell: ({ row }) => row.original.email },
    { id: "reason", header: "Reason", cell: ({ row }) => <Pill>{row.original.reason.replace("_", " ")}</Pill> },
    { id: "note", header: "Note", cell: ({ row }) => <span className="text-xs">{row.original.note || "–"}</span> },
    { id: "created_at", header: "Added", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at, false)}</span> },
    { id: "rm", header: "", cell: ({ row }) => can("email.write") && <Button size="xs" variant="ghost" onClick={async () => {
      try { await adminApi(`/api/admin/email/suppressions/${encodeURIComponent(row.original.email)}`, { method: "DELETE" }); setReload((n) => n + 1); } catch (e) { toast.error(errMsg(e)); }
    }}>Remove</Button> },
  ];
  return (
    <div className="space-y-4">
      {can("email.write") && (
        <Section title="Never email this address">
          <form className="flex flex-wrap gap-2" onSubmit={async (e) => {
            e.preventDefault();
            try { await adminApi("/api/admin/email/suppressions", { json: f }); setF({ email: "", reason: "manual", note: "" }); setReload((n) => n + 1); } catch (err) { toast.error(errMsg(err)); }
          }}>
            <Input aria-label="Email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} placeholder="someone@example.com" className="w-64" />
            <Select aria-label="Reason" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })}><option value="manual">Manual</option><option value="hard_bounce">Hard bounce</option><option value="unsubscribe">Unsubscribed</option></Select>
            <Input aria-label="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Note" className="w-56" />
            <Button type="submit" size="sm" disabled={!f.email.includes("@")}>Add</Button>
          </form>
          <p className="mt-2 text-xs text-muted-foreground">Bounces are added here by hand until the mail server is live (automatic bounce processing comes with it).</p>
        </Section>
      )}
      <DataTable<Sup> id="suppressions" endpoint="/api/admin/email/suppressions" columns={cols} reloadKey={reload} searchPlaceholder="Search…" emptyTitle="No suppressed addresses" />
    </div>
  );
}

export default function EmailPage() {
  return (
    <AdminShell title="Email">
      <PageHeader title="Email" description="Transactional email templates with the brand layout, the sending log and the suppression list. Sent from our own mail server once it's live." />
      <Tabs defaultValue="templates">
        <TabsList className="mb-4"><TabsTrigger value="templates">Templates</TabsTrigger><TabsTrigger value="log">Sending log</TabsTrigger><TabsTrigger value="suppressions">Suppression list</TabsTrigger></TabsList>
        <TabsContent value="templates"><Templates /></TabsContent>
        <TabsContent value="log"><LogTab /></TabsContent>
        <TabsContent value="suppressions"><Suppressions /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}
