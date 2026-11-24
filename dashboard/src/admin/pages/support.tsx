import { AlertTriangle, ArrowLeft, Clock, Loader2, Lock, Mail, MessageSquarePlus, Send, User as UserIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useList } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { EmptyState, ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Ticket = {
  id: number; reference: string; kind: string; status: string; priority: string; assignee_id: number | null; assignee: string;
  subject: string; name: string; email: string; user_id: number | null; created_at: string; updated_at: string; preview: string;
  acknowledged_at: string | null; ack_due_at: string | null; resolve_due_at: string | null; overdue: string | null;
};
type Msg = { id: number; direction: "in" | "out" | "note"; author_email: string; body: string; email_status: string; created_at: string };
type Detail = { ticket: Ticket; messages: Msg[]; user: { id: number; email: string; plan: string; status: string } | null; staff: { id: number; email: string }[]; mail_enabled: boolean };
type Canned = { id: number; title: string; body: string };

const KIND: Record<string, string> = { contact: "Contact", invite_request: "Invite request", grievance: "Grievance", abuse: "Misuse report", billing: "Billing" };
const statusTone = (s: string) => (s === "new" ? "blue" : s === "open" ? "amber" : s === "waiting" ? "gray" : "green");
const prioTone = (p: string) => (p === "urgent" ? "red" : p === "high" ? "amber" : "gray");

function Inbox() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const status = sp.get("status") ?? "open_all";
  const kind = sp.get("kind") ?? "";
  const assignee = sp.get("assignee") ?? "";
  const [q, setQ] = useState("");
  const [counts, setCounts] = useState<{ by_status: Record<string, number>; overdue: number; mine: number } | null>(null);
  useEffect(() => void adminApi<typeof counts>("/api/admin/tickets/counts").then(setCounts, () => undefined), []);
  const { data, error, loading, reload } = useList<Ticket>("/api/admin/tickets", { status, kind, assignee, q, size: 50 });
  const set = (k: string, v: string) => setSp((p) => (v ? p.set(k, v) : p.delete(k), p), { replace: true });
  const VIEWS = [
    ["open_all", "Open", (counts?.by_status.new ?? 0) + (counts?.by_status.open ?? 0) + (counts?.by_status.waiting ?? 0)],
    ["new", "New", counts?.by_status.new], ["waiting", "Waiting", counts?.by_status.waiting], ["overdue", "Overdue", counts?.overdue],
    ["resolved", "Resolved", counts?.by_status.resolved],
  ] as const;
  return (
    <AdminShell title="Support inbox">
      <PageHeader title="Support inbox" description="Contact form, invite requests, grievances and misuse reports in one place. Replies go out from support@aiwazz.in, threaded." />
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {VIEWS.map(([v, label, n]) => (
          <Button key={v} size="sm" variant={status === v ? "default" : "outline"} onClick={() => set("status", v)}>
            {v === "overdue" && <AlertTriangle className={cn(n ? "text-danger" : "")} />}{label}{n ? <span className="tabular opacity-70">{n}</span> : null}
          </Button>
        ))}
        <Select aria-label="Kind" value={kind} onChange={(e) => set("kind", e.target.value)}>
          <option value="">All kinds</option>{Object.entries(KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select aria-label="Assignee" value={assignee} onChange={(e) => set("assignee", e.target.value)}>
          <option value="">Anyone</option><option value="me">Mine{counts?.mine ? ` (${counts.mine})` : ""}</option><option value="none">Unassigned</option>
        </Select>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" aria-label="Search tickets" className="h-9 w-full sm:ml-auto sm:w-56" />
      </div>
      <div className="rounded-xl border bg-surface shadow-sm">
        {error ? <ErrorState message={error} onRetry={reload} /> : !data && loading ? <LoadingRows /> : !data?.items.length ? (
          <EmptyState title="Nothing here" hint="New messages from aiwazz.in/contact/ and invite requests appear here." />
        ) : (
          <ul className="divide-y">
            {data.items.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => navigate(`/admin/support/${t.id}`)} className="flex w-full items-start gap-3 p-3 text-left hover:bg-surface-2/60 focus-visible:bg-surface-2/60 focus-visible:outline-none sm:p-4">
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", t.status === "new" ? "bg-brand-indigo" : "bg-transparent")} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="truncate font-medium">{t.subject}</span>
                      <Pill tone={statusTone(t.status)}>{t.status}</Pill>
                      {t.kind !== "contact" && <Pill tone={t.kind === "grievance" || t.kind === "abuse" ? "red" : "gray"}>{KIND[t.kind]}</Pill>}
                      {t.priority !== "normal" && <Pill tone={prioTone(t.priority)}>{t.priority}</Pill>}
                      {t.overdue && <Pill tone="red"><Clock className="size-3" /> {t.overdue} overdue</Pill>}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">{t.name || t.email} · {t.preview}</p>
                  </div>
                  <div className="shrink-0 text-right text-xs text-muted-foreground">
                    <p>{timeAgo(t.updated_at)}</p>
                    <p className="font-mono text-[10px]">{t.reference}</p>
                    {t.assignee && <p className="truncate">{t.assignee.split("@")[0]}</p>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </AdminShell>
  );
}

function TicketView() {
  const { id = "" } = useParams();
  const { can } = useAdmin();
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [body, setBody] = useState("");
  const [note, setNote] = useState(false);
  const [after, setAfter] = useState("waiting");
  const [busy, setBusy] = useState(false);
  const [canned, setCanned] = useState<Canned[]>([]);
  const [cannedOpen, setCannedOpen] = useState(false);
  const [newCanned, setNewCanned] = useState({ title: "", body: "" });
  const load = useCallback(() => {
    setError("");
    adminApi<Detail>(`/api/admin/tickets/${id}`).then(setD, (e) => setError(errMsg(e)));
  }, [id]);
  useEffect(load, [load]);
  useEffect(() => void adminApi<{ items: Canned[] }>("/api/admin/canned-replies").then((r) => setCanned(r.items), () => undefined), []);
  const patch = async (json: Record<string, unknown>) => {
    try { await adminApi(`/api/admin/tickets/${id}`, { method: "PATCH", json }); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (error) return <AdminShell title="Ticket"><ErrorState message={error} onRetry={load} /></AdminShell>;
  if (!d) return <AdminShell title="Ticket"><LoadingRows rows={6} /></AdminShell>;
  const t = d.ticket;
  const write = can("support.write");
  const send = async () => {
    setBusy(true);
    try {
      const r = await adminApi<{ email_status: string }>(`/api/admin/tickets/${id}/reply`, { json: { body, note, status: note ? undefined : after } });
      toast.success(note ? "Note added" : r.email_status === "sent" ? "Reply sent" : `Reply saved (email ${r.email_status})`);
      setBody("");
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <AdminShell title={t.reference}>
      <Link to="/admin/support" className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Inbox</Link>
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-4">
          <div>
            <h1 className="font-heading text-xl font-semibold">{t.subject}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
              <span className="font-mono text-xs">{t.reference}</span> · {KIND[t.kind]} · from {t.name ? `${t.name} <${t.email}>` : t.email}
            </p>
          </div>
          {t.kind === "grievance" && (
            <div className={cn("rounded-xl border p-3 text-sm", t.overdue ? "border-danger/40 bg-danger/5" : "border-warning/30 bg-warning/5")}>
              <p className="font-medium">Grievance timelines (IT Rules / DPDP)</p>
              <p className="text-xs text-muted-foreground">Acknowledge by {fmtDate(t.ack_due_at)} {t.acknowledged_at ? `· done ${fmtDate(t.acknowledged_at)}` : ""} · resolve by {fmtDate(t.resolve_due_at)}</p>
              {!t.acknowledged_at && write && <Button size="xs" variant="outline" className="mt-2" onClick={() => patch({ acknowledged: true })}>Mark acknowledged</Button>}
            </div>
          )}
          <ol className="space-y-3">
            {d.messages.map((m) => (
              <li key={m.id} className={cn("rounded-xl border p-3.5 text-sm", m.direction === "out" && "border-brand-indigo/25 bg-brand-indigo/5 sm:ml-8",
                m.direction === "note" && "border-dashed border-warning/40 bg-warning/5")}>
                <p className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {m.direction === "note" ? <Lock className="size-3" /> : m.direction === "out" ? <Send className="size-3" /> : <Mail className="size-3" />}
                  <span className="font-medium text-foreground">{m.direction === "in" ? m.author_email : m.author_email}</span>
                  {m.direction === "note" && "internal note"}
                  {m.direction === "out" && m.email_status && <Pill tone={m.email_status === "sent" ? "green" : "amber"}>email {m.email_status}</Pill>}
                  <span className="ml-auto">{fmtDate(m.created_at)}</span>
                </p>
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
              </li>
            ))}
          </ol>
          {write && (
            <Section>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Button size="xs" variant={note ? "outline" : "default"} onClick={() => setNote(false)}><Send /> Reply</Button>
                <Button size="xs" variant={note ? "default" : "outline"} onClick={() => setNote(true)}><Lock /> Internal note</Button>
                {!note && canned.length > 0 && (
                  <Select aria-label="Insert canned reply" value="" onChange={(e) => { const c = canned.find((x) => String(x.id) === e.target.value); if (c) setBody((b) => (b ? `${b}\n\n` : "") + c.body); }}>
                    <option value="">Canned reply…</option>{canned.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
                  </Select>
                )}
                <Button size="xs" variant="ghost" onClick={() => setCannedOpen(true)}><MessageSquarePlus /> New canned</Button>
              </div>
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} aria-label={note ? "Internal note" : "Reply"}
                placeholder={note ? "Only staff see this." : `Reply to ${t.email} (from support@aiwazz.in)`} />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {!note && (
                  <Select aria-label="Status after sending" value={after} onChange={(e) => setAfter(e.target.value)}>
                    <option value="waiting">Then: waiting for customer</option><option value="open">Then: keep open</option><option value="resolved">Then: resolved</option>
                  </Select>
                )}
                <Button size="sm" variant="brand" className="ml-auto" disabled={busy || !body.trim()} onClick={send}>{busy && <Loader2 className="animate-spin" />} {note ? "Add note" : "Send reply"}</Button>
              </div>
              {!note && !d.mail_enabled && <p className="mt-2 text-xs text-warning">Mail is off on the server: replies are saved and logged but not delivered yet.</p>}
            </Section>
          )}
        </div>
        <aside className="space-y-4">
          <Section title="Ticket">
            <div className="space-y-3 text-sm">
              <Field label="Status"><Select className="w-full" value={t.status} disabled={!write} onChange={(e) => patch({ status: e.target.value })}>
                {["new", "open", "waiting", "resolved"].map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
              <Field label="Priority"><Select className="w-full" value={t.priority} disabled={!write} onChange={(e) => patch({ priority: e.target.value })}>
                {["low", "normal", "high", "urgent"].map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
              <Field label="Assignee"><Select className="w-full" value={t.assignee_id ?? ""} disabled={!write}
                onChange={(e) => patch(e.target.value ? { assignee_id: Number(e.target.value) } : { unassign: true })}>
                <option value="">Unassigned</option>{d.staff.map((s) => <option key={s.id} value={s.id}>{s.email}</option>)}</Select></Field>
              <p className="text-xs text-muted-foreground">Created {fmtDate(t.created_at)}</p>
            </div>
          </Section>
          <Section title="Customer">
            {d.user ? (
              <div className="space-y-1 text-sm">
                <Link to={`/admin/users/${d.user.id}`} className="inline-flex items-center gap-1.5 font-medium text-brand hover:underline"><UserIcon className="size-4" /> {d.user.email}</Link>
                <p className="text-xs text-muted-foreground">Plan {d.user.plan} · {d.user.status}</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">No account with {t.email}.</p>}
            {t.kind === "invite_request" && <Link to="/admin/invites?tab=waitlist" className="mt-2 block text-xs text-brand hover:underline">Open the waitlist to approve</Link>}
            {t.kind === "abuse" && <Link to="/admin/moderation" className="mt-2 block text-xs text-brand hover:underline">Open Moderation</Link>}
          </Section>
        </aside>
      </div>
      <FormDialog open={cannedOpen} onOpenChange={setCannedOpen} title="New canned reply" disabled={!newCanned.title.trim() || !newCanned.body.trim()}
        onSubmit={async () => {
          const c = await adminApi<Canned>("/api/admin/canned-replies", { json: newCanned });
          setCanned((x) => [...x, c]);
          setNewCanned({ title: "", body: "" });
        }}>
        <Field label="Title" htmlFor="cn-t"><Input id="cn-t" value={newCanned.title} onChange={(e) => setNewCanned({ ...newCanned, title: e.target.value })} /></Field>
        <Field label="Text" htmlFor="cn-b"><Textarea id="cn-b" rows={5} value={newCanned.body} onChange={(e) => setNewCanned({ ...newCanned, body: e.target.value })} /></Field>
      </FormDialog>
    </AdminShell>
  );
}

export default function SupportPage() {
  return (
    <Routes>
      <Route index element={<Inbox />} />
      <Route path=":id" element={<TicketView />} />
    </Routes>
  );
}
