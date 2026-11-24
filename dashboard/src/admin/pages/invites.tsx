import type { ColumnDef } from "@tanstack/react-table";
import { Check, Copy, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { planName } from "../lib/plans";

type Invite = { id: number; label: string; email: string; role: string; uses: number; max_uses: number; expires_at: string | null; plan: string | null; plan_until: string | null; status: string; created_at: string };
type Req = { id: number; email: string; name: string; use_case: string; status: string; created_at: string; registered: boolean };
type Issued = { email?: string; code: string; signup_url: string; email_status?: string };

const tone = (s: string) => (s === "active" || s === "invited" ? "green" : s === "revoked" || s === "declined" ? "red" : s === "new" ? "blue" : "gray");

function CopyLine({ value }: { value: string }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-lg border bg-surface-2/60 p-2">
      <code className="min-w-0 flex-1 truncate font-mono text-xs">{value}</code>
      <Button type="button" size="xs" variant="outline" onClick={async () => { await navigator.clipboard.writeText(value).catch(() => undefined); setOk(true); }}>
        {ok ? <Check /> : <Copy />} {ok ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

function IssuedDialog({ issued, onClose }: { issued: Issued[] | null; onClose: () => void }) {
  return (
    <FormDialog open={!!issued} onOpenChange={(o) => !o && onClose()} title="Invite codes (shown once)" wide submitLabel="Done" onSubmit={async () => undefined}
      description="Copy them now: only a hash is stored. While mail is off, send the link yourself (WhatsApp, email).">
      {issued?.map((i) => (
        <div key={i.code} className="space-y-1">
          {i.email && <p className="text-xs font-medium">{i.email} {i.email_status && <span className="text-muted-foreground">· email {i.email_status}</span>}</p>}
          <CopyLine value={i.signup_url} />
        </div>
      ))}
    </FormDialog>
  );
}

function InvitesTab({ onIssued }: { onIssued: (i: Issued[]) => void }) {
  const { can } = useAdmin();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ label: "", uses: "1", days: "14", role: "user", plan: "", plan_until: "" });
  const [reload, setReload] = useState(0);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const cols: ColumnDef<Invite, unknown>[] = [
    { id: "label", header: "Label", cell: ({ row: { original: i } }) => <div><p className="font-medium">{i.label || "–"}</p>{i.email && <p className="text-xs text-muted-foreground">{i.email}</p>}</div> },
    { id: "status", header: "Status", cell: ({ row }) => <Pill tone={tone(row.original.status)}>{row.original.status}</Pill> },
    { id: "uses", header: "Uses", cell: ({ row }) => <span className="tabular">{row.original.uses}/{row.original.max_uses}</span> },
    { id: "role", header: "Role", cell: ({ row }) => <span className="capitalize">{row.original.role}</span> },
    { id: "plan", header: "Starts on", cell: ({ row: { original: i } }) => i.plan ? <span className="text-xs">{planName(i.plan)}{i.plan_until ? ` until ${fmtDate(i.plan_until, false)}` : ""}</span> : <span className="text-xs text-muted-foreground">Free</span> },
    { id: "expires_at", header: "Expires", meta: { sortKey: "expires_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.expires_at, false)}</span> },
    { id: "created_at", header: "Created", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at, false)}</span> },
    { id: "actions", header: "", cell: ({ row: { original: i } }) => i.status === "active" && can("invites.write") ? (
      <Button size="xs" variant="outline" onClick={async () => {
        try { await adminApi(`/api/admin/invites/${i.id}/revoke`, { method: "POST" }); setReload((n) => n + 1); } catch (e) { toast.error(errMsg(e)); }
      }}>Revoke</Button>
    ) : null },
  ];
  return (
    <>
      <DataTable<Invite> id="invites" endpoint="/api/admin/invites" columns={cols} exportName="invites" reloadKey={reload}
        searchPlaceholder="Label or email…" emptyTitle="No invites yet"
        filters={[{ key: "status", label: "Status", options: ["active", "used", "expired", "revoked"].map((v) => ({ value: v, label: v })) }]}
        toolbar={can("invites.write") && <Button size="sm" variant="brand" onClick={() => setOpen(true)}><Plus /> New invite</Button>} />
      <FormDialog open={open} onOpenChange={setOpen} title="New invite" submitLabel="Create"
        description="Early-access friends: pick a plan + end date and their account starts on it (e.g. Creator free for 3 months)."
        onSubmit={async () => {
          const r = await adminApi<Issued>("/api/admin/invites", { json: { label: f.label, uses: Number(f.uses), days: Number(f.days), role: f.role, plan: f.plan, plan_until: f.plan && f.plan_until ? f.plan_until : null } });
          onIssued([r]);
          setReload((n) => n + 1);
        }}>
        <Field label="Label" htmlFor="inv-label"><Input id="inv-label" value={f.label} onChange={set("label")} placeholder="Riya (Instagram)" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Uses" htmlFor="inv-uses"><Input id="inv-uses" type="number" min={1} max={1000} value={f.uses} onChange={set("uses")} /></Field>
          <Field label="Valid for (days)" htmlFor="inv-days"><Input id="inv-days" type="number" min={1} max={365} value={f.days} onChange={set("days")} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts on plan"><Select className="w-full" value={f.plan} onChange={set("plan")}><option value="">Free</option><option value="starter">Starter</option><option value="creator">Creator</option><option value="pro">Pro</option></Select></Field>
          <Field label="Plan's last day" htmlFor="inv-until"><Input id="inv-until" type="date" value={f.plan_until} onChange={set("plan_until")} disabled={!f.plan} /></Field>
        </div>
        {can("roles.write") && (
          <Field label="Role" hint="Staff roles must set up 2FA on first visit to /admin."><Select className="w-full" value={f.role} onChange={set("role")}>
            {["user", "admin", "support", "finance", "viewer"].map((r) => <option key={r} value={r}>{r}</option>)}
          </Select></Field>
        )}
      </FormDialog>
    </>
  );
}

function WaitlistTab({ onIssued }: { onIssued: (i: Issued[]) => void }) {
  const { can } = useAdmin();
  const [reload, setReload] = useState(0);
  const [approve, setApprove] = useState<Req[] | null>(null);
  const [plan, setPlan] = useState("");
  const [until, setUntil] = useState("");
  const [sendEmail, setSendEmail] = useState(true);
  const reject = async (r: Req) => {
    const email = window.confirm(`Decline ${r.email}? OK = also send a polite email, Cancel = keep the request.`);
    if (!email) return;
    try { await adminApi(`/api/admin/invite-requests/${r.id}/reject`, { json: { send_email: true } }); setReload((n) => n + 1); } catch (e) { toast.error(errMsg(e)); }
  };
  const cols: ColumnDef<Req, unknown>[] = [
    { id: "email", header: "Email", meta: { sortKey: "email" }, cell: ({ row: { original: r } }) => <div><p className="font-medium">{r.email}</p>{r.name && <p className="text-xs text-muted-foreground">{r.name}</p>}</div> },
    { id: "use_case", header: "Use case", cell: ({ row }) => <p className="line-clamp-2 max-w-sm text-xs">{row.original.use_case || "–"}</p> },
    { id: "status", header: "Status", cell: ({ row: { original: r } }) => <span className="flex gap-1"><Pill tone={tone(r.status)}>{r.status}</Pill>{r.registered && <Pill tone="green">signed up</Pill>}</span> },
    { id: "created_at", header: "Requested", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at, false)}</span> },
    { id: "actions", header: "", cell: ({ row: { original: r } }) => can("invites.write") && r.status !== "invited" ? (
      <span className="flex gap-1.5">
        <Button size="xs" variant="outline" onClick={() => setApprove([r])}>Approve</Button>
        {r.status === "new" && <Button size="xs" variant="ghost" onClick={() => reject(r)}>Decline</Button>}
      </span>
    ) : null },
  ];
  return (
    <>
      <DataTable<Req> id="waitlist" endpoint="/api/admin/invite-requests" columns={cols} exportName="waitlist" reloadKey={reload}
        searchPlaceholder="Email, name, use case…" emptyTitle="No invite requests yet" emptyHint={'People who use "Request an invite" on the signup page show up here.'}
        filters={[{ key: "status", label: "Status", options: [{ value: "new", label: "New" }, { value: "invited", label: "Invited" }, { value: "declined", label: "Declined" }] }]}
        bulkActions={can("invites.write") ? (rows) => <Button size="xs" variant="outline" onClick={() => setApprove(rows)}>Approve {rows.length}</Button> : undefined} />
      <FormDialog open={!!approve} onOpenChange={(o) => !o && setApprove(null)} title={`Approve ${approve?.length ?? 0} request${approve?.length === 1 ? "" : "s"}`}
        description="Creates a single-use invite (14 days) per person and emails it (logged while mail is off; you'll get the links to share)."
        submitLabel="Approve" onSubmit={async () => {
          const body = { plan, plan_until: plan && until ? until : null, send_email: sendEmail };
          if (approve!.length === 1) onIssued([await adminApi<Issued>(`/api/admin/invite-requests/${approve![0].id}/approve`, { json: body })]);
          else {
            const r = await adminApi<{ approved: Issued[]; skipped: string[] }>("/api/admin/invite-requests/bulk-approve", { json: { ...body, ids: approve!.map((x) => x.id) } });
            onIssued(r.approved);
            if (r.skipped.length) toast.info(`Skipped (already invited): ${r.skipped.join(", ")}`);
          }
          setReload((n) => n + 1);
        }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts on plan"><Select className="w-full" value={plan} onChange={(e) => setPlan(e.target.value)}><option value="">Free</option><option value="starter">Starter</option><option value="creator">Creator</option><option value="pro">Pro</option></Select></Field>
          <Field label="Plan's last day" htmlFor="ap-until"><Input id="ap-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} disabled={!plan} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)} /> Email the invite</label>
      </FormDialog>
    </>
  );
}

function SignupModeTab() {
  const { can } = useAdmin();
  const [mode, setMode] = useState<string | null>(null);
  useEffect(() => void adminApi<{ signup_mode: string }>("/api/admin/settings/signup").then((r) => setMode(r.signup_mode), () => setMode("invite")), []);
  const MODES = [
    { v: "invite", t: "Invite-only", d: "An invite code is required. The signup page shows \"Request an invite\". (Current owner decision.)" },
    { v: "open", t: "Open", d: "Anyone can sign up; invite codes still work for plans and staff roles." },
    { v: "closed", t: "Closed", d: "No new accounts, even with a code. Existing users can sign in." },
  ];
  return (
    <Section title="Signup mode" description="Changing it asks you to confirm it's you and is audited.">
      <div className="grid gap-3 md:grid-cols-3">
        {MODES.map((m) => (
          <button key={m.v} type="button" disabled={!can("settings.write") || mode === m.v}
            onClick={async () => {
              try { await adminApi("/api/admin/settings/signup", { method: "PUT", json: { signup_mode: m.v } }); setMode(m.v); toast.success(`Signup is now ${m.t.toLowerCase()}`); } catch (e) { toast.error(errMsg(e)); }
            }}
            className={`rounded-xl border p-4 text-left transition-colors ${mode === m.v ? "border-brand-indigo bg-brand-indigo/5 ring-1 ring-brand-indigo" : "hover:bg-surface-2"} disabled:cursor-default`}>
            <p className="font-medium">{m.t} {mode === m.v && <Pill tone="blue" className="ml-1">current</Pill>}</p>
            <p className="mt-1 text-xs text-muted-foreground">{m.d}</p>
          </button>
        ))}
      </div>
    </Section>
  );
}

export default function InvitesPage() {
  const [sp, setSp] = useSearchParams();
  const [issued, setIssued] = useState<Issued[] | null>(null);
  const tab = sp.get("tab") ?? "invites";
  return (
    <AdminShell title="Invites & waitlist">
      <PageHeader title="Invites & waitlist" description="Create invite codes (optionally with a free plan for early-access friends), review invite requests, set the signup mode." />
      <Tabs value={tab} onValueChange={(t) => setSp({ tab: t }, { replace: true })}>
        <TabsList className="mb-4"><TabsTrigger value="invites">Invites</TabsTrigger><TabsTrigger value="waitlist">Waitlist</TabsTrigger><TabsTrigger value="mode">Signup mode</TabsTrigger></TabsList>
        <TabsContent value="invites"><InvitesTab onIssued={setIssued} /></TabsContent>
        <TabsContent value="waitlist"><WaitlistTab onIssued={setIssued} /></TabsContent>
        <TabsContent value="mode"><SignupModeTab /></TabsContent>
      </Tabs>
      <IssuedDialog issued={issued} onClose={() => setIssued(null)} />
    </AdminShell>
  );
}
