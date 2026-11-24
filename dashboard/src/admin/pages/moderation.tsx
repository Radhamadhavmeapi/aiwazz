import type { ColumnDef } from "@tanstack/react-table";
import { Ban, FlaskConical, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type FlagRow = {
  id: number; source: string; user_id: number | null; email: string; generation_id: string | null; rule_name: string; category: string;
  severity: string; matched: string; detail: string; blocked: boolean; status: string; action: string; note: string; ticket_id: number | null; created_at: string;
};
type Rule = { id: number; name: string; category: string; kind: string; pattern: string; severity: string; action: string; active: boolean; hits_30d: number };
type Block = { id: number; kind: string; value: string; reason: string; created_at: string };
const sevTone = (s: string) => (s === "high" ? "red" : s === "medium" ? "amber" : "gray");
const SOURCE: Record<string, string> = { rule: "Rule match", volume: "Volume spike", multi_account: "Many accounts / IP", report: "Public report" };

function Flags() {
  const { can } = useAdmin();
  const [act, setAct] = useState<{ f: FlagRow; action: string } | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const open = (f: FlagRow, action: string) => (setNote(""), setMessage(""), setAct({ f, action }));
  const cols: ColumnDef<FlagRow, unknown>[] = [
    { id: "created_at", header: "When", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at)}</span> },
    { id: "what", header: "Signal", cell: ({ row: { original: f } }) => (
      <div className="max-w-xs"><p className="font-medium">{f.rule_name || SOURCE[f.source]}</p>
        <p className="text-xs text-muted-foreground">{SOURCE[f.source]}{f.matched && <> · matched “<span className="text-foreground">{f.matched}</span>”</>}{f.detail && ` · ${f.detail}`}</p></div>
    ) },
    { id: "user", header: "Account", cell: ({ row: { original: f } }) => f.user_id ? <Link to={`/admin/users/${f.user_id}`} className="text-xs hover:underline">{f.email}</Link>
      : f.ticket_id ? <Link to={`/admin/support/${f.ticket_id}`} className="text-xs text-brand hover:underline">report ticket</Link> : "–" },
    { id: "sev", header: "Severity", cell: ({ row: { original: f } }) => <span className="flex gap-1"><Pill tone={sevTone(f.severity)}>{f.severity}</Pill>{f.blocked && <Pill tone="red">blocked</Pill>}</span> },
    { id: "status", header: "Status", cell: ({ row: { original: f } }) => <Pill tone={f.status === "open" ? "amber" : f.status === "dismissed" ? "gray" : "green"}>{f.action || f.status}</Pill> },
    { id: "actions", header: "", cell: ({ row: { original: f } }) => can("moderation.write") && f.status === "open" ? (
      <div className="flex flex-wrap gap-1">
        {f.generation_id && f.user_id && <Button size="xs" variant="outline" asChild><Link to={`/admin/users/${f.user_id}`}>Review</Link></Button>}
        <Button size="xs" variant="ghost" onClick={() => open(f, "dismiss")}>Dismiss</Button>
        {f.user_id && <Button size="xs" variant="outline" onClick={() => open(f, "warn")}>Warn</Button>}
        {f.generation_id && <Button size="xs" variant="outline" onClick={() => open(f, "delete_audio")}>Delete audio</Button>}
        {f.user_id && <Button size="xs" variant="destructive" onClick={() => open(f, "suspend")}>Suspend</Button>}
        <Button size="xs" variant="ghost" onClick={() => open(f, "report_note")}>Note</Button>
      </div>
    ) : f.note ? <span className="text-xs text-muted-foreground">{f.note}</span> : null },
  ];
  const LABEL: Record<string, string> = { dismiss: "Dismiss flag", warn: "Warn the user", delete_audio: "Delete the audio", suspend: "Suspend the account", report_note: "Add a report note" };
  return (
    <>
      <p className="mb-3 text-xs text-muted-foreground">Scripts stay hidden: open the account → Generations → View (needs a reason, audited) to read one.</p>
      <DataTable<FlagRow> id="flags" endpoint="/api/admin/flags" columns={cols} reloadKey={reload} searchPlaceholder="Email, rule or term…" emptyTitle="Nothing flagged"
        filters={[
          { key: "status", label: "Status", options: [{ value: "open", label: "Open" }, { value: "dismissed", label: "Dismissed" }, { value: "actioned", label: "Actioned" }] },
          { key: "source", label: "Source", options: Object.entries(SOURCE).map(([value, label]) => ({ value, label })) },
          { key: "severity", label: "Severity", options: ["high", "medium", "low"].map((v) => ({ value: v, label: v })) },
        ]} />
      <FormDialog open={!!act} onOpenChange={(o) => !o && setAct(null)} title={act ? LABEL[act.action] : ""} destructive={act?.action === "suspend" || act?.action === "delete_audio"}
        submitLabel={act ? LABEL[act.action].split(" ")[0] : "OK"}
        onSubmit={async () => { await adminApi(`/api/admin/flags/${act!.f.id}/action`, { json: { action: act!.action, note, message } }); toast.success("Done"); setReload((n) => n + 1); }}>
        {act?.action === "warn" && <Field label="Email text (optional; a standard Acceptable Use reminder otherwise)" htmlFor="fw-msg"><Textarea id="fw-msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} /></Field>}
        <Field label="Note (audit log)" htmlFor="fl-note"><Input id="fl-note" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </FormDialog>
    </>
  );
}

const blankRule = { name: "", category: "scam", kind: "keywords", pattern: "", severity: "medium", action: "flag", active: true };

function Rules() {
  const { can } = useAdmin();
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState("");
  const [edit, setEdit] = useState<{ id: number | null; r: typeof blankRule } | null>(null);
  const [testText, setTestText] = useState("");
  const [testOut, setTestOut] = useState<{ rule: string; term: string; action?: string }[] | null>(null);
  const load = useCallback(() => {
    adminApi<{ items: Rule[] }>("/api/admin/moderation/rules").then((r) => setRules(r.items), (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!rules) return <LoadingRows rows={4} />;
  const write = can("moderation.write");
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <Section title="Rules" description="Checked on every script when it's submitted. Flag = allowed, queued for review. Block = refused with a friendly message."
        actions={write && <Button size="sm" variant="brand" onClick={() => setEdit({ id: null, r: { ...blankRule } })}><Plus /> New rule</Button>}>
        <ul className="divide-y">
          {rules.map((r) => (
            <li key={r.id} className="flex flex-wrap items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-1.5 font-medium">{r.name}<Pill tone={sevTone(r.severity)}>{r.severity}</Pill>
                  <Pill tone={r.action === "block" ? "red" : "amber"}>{r.action === "block" ? <><Ban className="size-3" /> block</> : "flag"}</Pill>
                  {!r.active && <Pill>off</Pill>}</p>
                <p className="mt-0.5 line-clamp-2 font-mono text-[11px] text-muted-foreground">{r.kind === "regex" ? `/${r.pattern}/i` : r.pattern}</p>
              </div>
              <span className="text-xs text-muted-foreground tabular">{r.hits_30d} hits / 30d</span>
              {write && (
                <span className="flex gap-1">
                  <Button size="icon-xs" variant="ghost" aria-label={`Edit ${r.name}`} onClick={() => setEdit({ id: r.id, r: { ...r } })}><Pencil /></Button>
                  <Button size="icon-xs" variant="ghost" aria-label={`Delete ${r.name}`} onClick={async () => {
                    if (!window.confirm(`Delete rule "${r.name}"?`)) return;
                    try { await adminApi(`/api/admin/moderation/rules/${r.id}`, { method: "DELETE" }); load(); } catch (e) { toast.error(errMsg(e)); }
                  }}><Trash2 /></Button>
                </span>
              )}
            </li>
          ))}
          {!rules.length && <li className="py-6 text-center text-sm text-muted-foreground">No rules.</li>}
        </ul>
      </Section>
      <Section title="Rule tester" description="Paste a script to see which active rules match. Nothing is stored.">
        <Textarea rows={6} value={testText} onChange={(e) => setTestText(e.target.value)} aria-label="Text to test" placeholder="Namaste, main RBI officer bol raha hoon…" />
        <Button size="sm" variant="outline" className="mt-2" disabled={!testText.trim()} onClick={async () => {
          try { setTestOut((await adminApi<{ matches: typeof testOut }>("/api/admin/moderation/test", { json: { text: testText } })).matches); } catch (e) { toast.error(errMsg(e)); }
        }}><FlaskConical /> Test</Button>
        {testOut && <ul className="mt-3 space-y-1 text-sm">{testOut.length ? testOut.map((m, i) => <li key={i}><span className="font-medium">{m.rule}</span>: “{m.term}” {m.action && <Pill tone={m.action === "block" ? "red" : "amber"}>{m.action}</Pill>}</li>) : <li className="text-muted-foreground">No rule matches.</li>}</ul>}
      </Section>
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? "Edit rule" : "New rule"} wide submitLabel="Save"
        disabled={!edit?.r.name.trim() || !edit?.r.pattern.trim()}
        onSubmit={async () => {
          await adminApi(edit!.id ? `/api/admin/moderation/rules/${edit!.id}` : "/api/admin/moderation/rules", { method: edit!.id ? "PUT" : "POST", json: edit!.r });
          toast.success("Saved");
          load();
        }}>
        {edit && (
          <>
            <Field label="Name" htmlFor="r-name"><Input id="r-name" value={edit.r.name} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, name: e.target.value } })} /></Field>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Field label="Category"><Select className="w-full" value={edit.r.category} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, category: e.target.value } })}>
                {["impersonation", "scam", "threat", "explicit", "other"].map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
              <Field label="Type"><Select className="w-full" value={edit.r.kind} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, kind: e.target.value } })}>
                <option value="keywords">Keywords</option><option value="regex">Regex</option></Select></Field>
              <Field label="Severity"><Select className="w-full" value={edit.r.severity} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, severity: e.target.value } })}>
                {["low", "medium", "high"].map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>
              <Field label="Action"><Select className="w-full" value={edit.r.action} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, action: e.target.value } })}>
                <option value="flag">Flag for review</option><option value="block">Block the job</option></Select></Field>
            </div>
            <Field label={edit.r.kind === "keywords" ? "Keywords / phrases, comma separated (whole words, any case)" : "Regular expression (case-insensitive)"} htmlFor="r-pat">
              <Textarea id="r-pat" rows={4} className="font-mono text-xs" value={edit.r.pattern} onChange={(e) => setEdit({ ...edit, r: { ...edit.r, pattern: e.target.value } })} /></Field>
            <label className="flex items-center gap-2 text-sm"><Switch checked={edit.r.active} onCheckedChange={(v) => setEdit({ ...edit, r: { ...edit.r, active: v } })} aria-label="Active" /> Active</label>
          </>
        )}
      </FormDialog>
    </div>
  );
}

function Blocklist() {
  const { can } = useAdmin();
  const [f, setF] = useState({ kind: "email", value: "", reason: "" });
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Block, unknown>[] = [
    { id: "kind", header: "Type", cell: ({ row }) => <Pill>{row.original.kind}</Pill> },
    { id: "value", header: "Value", cell: ({ row }) => <span className="font-mono text-xs">{row.original.value}</span> },
    { id: "reason", header: "Reason", cell: ({ row }) => <span className="text-xs">{row.original.reason || "–"}</span> },
    { id: "created_at", header: "Added", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at, false)}</span> },
    { id: "rm", header: "", cell: ({ row }) => can("moderation.write") && <Button size="xs" variant="ghost" onClick={async () => {
      try { await adminApi(`/api/admin/moderation/blocklist/${row.original.id}`, { method: "DELETE" }); setReload((n) => n + 1); } catch (e) { toast.error(errMsg(e)); }
    }}>Remove</Button> },
  ];
  return (
    <div className="space-y-4">
      {can("moderation.write") && (
        <Section title="Block an email, domain or IP" description="Blocked signups get a neutral error; blocked contact forms and invite requests are silently dropped.">
          <form className="flex flex-wrap items-end gap-2" onSubmit={async (e) => {
            e.preventDefault();
            try { await adminApi("/api/admin/moderation/blocklist", { json: f }); setF({ ...f, value: "", reason: "" }); setReload((n) => n + 1); } catch (err) { toast.error(errMsg(err)); }
          }}>
            <Select aria-label="Type" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="email">Email</option><option value="domain">Domain</option><option value="ip">IP / range</option></Select>
            <Input aria-label="Value" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} placeholder={f.kind === "ip" ? "203.0.113.0/24" : f.kind === "domain" ? "spam-domain.com" : "someone@example.com"} className="w-64" />
            <Input aria-label="Reason" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="Reason" className="w-56" />
            <Button type="submit" size="sm" disabled={f.value.trim().length < 3}><Ban /> Block</Button>
          </form>
        </Section>
      )}
      <DataTable<Block> id="blocklist" endpoint="/api/admin/moderation/blocklist" columns={cols} reloadKey={reload} searchPlaceholder="Search…" emptyTitle="Nothing blocked" />
    </div>
  );
}

export default function ModerationPage() {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "flags";
  return (
    <AdminShell title="Moderation">
      <PageHeader title="Moderation & trust" description="Automatic flags (rules on scripts, volume spikes, many accounts from one IP) and public misuse reports. Every action is audited." />
      <Tabs value={tab} onValueChange={(t) => setSp({ tab: t }, { replace: true })}>
        <TabsList className="mb-4"><TabsTrigger value="flags">Flags</TabsTrigger><TabsTrigger value="rules">Rules</TabsTrigger><TabsTrigger value="blocklist">Blocklist</TabsTrigger></TabsList>
        <TabsContent value="flags"><Flags /></TabsContent>
        <TabsContent value="rules"><Rules /></TabsContent>
        <TabsContent value="blocklist"><Blocklist /></TabsContent>
      </Tabs>
    </AdminShell>
  );
}
