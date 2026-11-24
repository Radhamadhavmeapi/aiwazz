import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { timeAgo } from "@/lib/format";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { Field, fmtDate, inr, num, PageHeader, Pill, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { PLAN_OPTIONS, planName, planTone } from "../lib/plans";

export type UserRow = {
  id: number; email: string; name: string; role: string; plan: string; plan_until: string | null; status: string;
  created_at: string; last_active_at: string | null; chars_this_month: number; revenue_paise: number; tags: string[];
};

export const statusTone = (s: string) => (s === "active" ? "green" : s === "suspended" ? "red" : "gray");

const columns: ColumnDef<UserRow, unknown>[] = [
  { id: "email", header: "Email", meta: { sortKey: "email" }, cell: ({ row: { original: u } }) => (
    <div className="min-w-0 max-w-[260px]">
      <p className="truncate font-medium">{u.email}</p>
      <p className="truncate text-xs text-muted-foreground">#{u.id}{u.name ? ` · ${u.name}` : ""}{u.role !== "user" ? ` · ${u.role}` : ""}</p>
    </div>
  ) },
  { id: "plan", header: "Plan", meta: { sortKey: "plan" }, cell: ({ row: { original: u } }) => (
    <div><Pill tone={planTone(u.plan)}>{planName(u.plan)}</Pill>{u.plan_until && <p className="mt-0.5 text-[11px] text-muted-foreground">until {fmtDate(u.plan_until, false)}</p>}</div>
  ) },
  { id: "status", header: "Status", cell: ({ row }) => <Pill tone={statusTone(row.original.status)}>{row.original.status}</Pill> },
  { id: "created_at", header: "Signed up", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at, false)}</span> },
  { id: "last_active", header: "Last active", meta: { sortKey: "last_active" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap text-muted-foreground">{row.original.last_active_at ? timeAgo(row.original.last_active_at) : "never"}</span> },
  { id: "chars", header: "Chars (month)", meta: { sortKey: "chars", className: "text-right" }, cell: ({ row }) => <span className="tabular">{num(row.original.chars_this_month)}</span> },
  { id: "revenue", header: "Revenue", meta: { sortKey: "revenue", className: "text-right" }, cell: ({ row }) => <span className="tabular">{inr(row.original.revenue_paise)}</span> },
  { id: "tags", header: "Tags", cell: ({ row }) => <div className="flex flex-wrap gap-1">{row.original.tags.map((t) => <Pill key={t}>{t}</Pill>)}</div> },
];

function BulkBar({ rows, done }: { rows: UserRow[]; done: () => void }) {
  const [mode, setMode] = useState<"tag" | "plan" | "email" | null>(null);
  const [tag, setTag] = useState("");
  const [tagOp, setTagOp] = useState("tag_add");
  const [plan, setPlan] = useState("creator");
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const ids = rows.map((r) => r.id);
  const go = async (json: Record<string, unknown>) => {
    const r = await adminApi<{ affected: number; mail_enabled: boolean }>("/api/admin/users/bulk", { json: { ids, ...json } });
    toast.success(`Done: ${r.affected} affected${json.action === "email" && !r.mail_enabled ? " (mail is off: logged, not sent)" : ""}`);
    done();
  };
  return (
    <>
      <Button size="xs" variant="outline" onClick={() => setMode("tag")}>Tag</Button>
      <Button size="xs" variant="outline" onClick={() => setMode("plan")}>Change plan</Button>
      <Button size="xs" variant="outline" onClick={() => setMode("email")}>Send email</Button>
      <FormDialog open={mode === "tag"} onOpenChange={(o) => setMode(o ? "tag" : null)} title={`Tag ${rows.length} users`}
        onSubmit={() => go({ action: tagOp, tag })} disabled={!tag.trim()} submitLabel="Apply">
        <Field label="Action"><Select value={tagOp} onChange={(e) => setTagOp(e.target.value)} className="w-full"><option value="tag_add">Add tag</option><option value="tag_remove">Remove tag</option></Select></Field>
        <Field label="Tag" htmlFor="bulk-tag"><Input id="bulk-tag" value={tag} onChange={(e) => setTag(e.target.value)} placeholder="early-access" /></Field>
      </FormDialog>
      <FormDialog open={mode === "plan"} onOpenChange={(o) => setMode(o ? "plan" : null)} title={`Change plan for ${rows.length} users`}
        description="Staff accounts are skipped. Asks you to confirm it's you." onSubmit={() => go({ action: "plan", plan, until: until || null, reason })}
        disabled={reason.trim().length < 3} submitLabel="Change plan">
        <Field label="Plan"><Select value={plan} onChange={(e) => setPlan(e.target.value)} className="w-full">{PLAN_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></Field>
        <Field label="Last day (optional, India time)" htmlFor="bulk-until"><Input id="bulk-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} disabled={plan === "free"} /></Field>
        <Field label="Reason (audit log)" htmlFor="bulk-reason"><Input id="bulk-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Early access batch 2" /></Field>
      </FormDialog>
      <FormDialog open={mode === "email"} onOpenChange={(o) => setMode(o ? "email" : null)} title={`Email ${rows.length} users`}
        description="Sent from support@ with the brand layout (logged; not delivered while mail is off)." onSubmit={() => go({ action: "email", subject, message })}
        disabled={!subject.trim() || !message.trim()} submitLabel="Send">
        <Field label="Subject" htmlFor="bulk-subj"><Input id="bulk-subj" value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
        <Field label="Message" htmlFor="bulk-msg"><Textarea id="bulk-msg" rows={6} value={message} onChange={(e) => setMessage(e.target.value)} /></Field>
      </FormDialog>
    </>
  );
}

export default function UsersPage() {
  const navigate = useNavigate();
  const { can } = useAdmin();
  return (
    <AdminShell title="Users">
      <PageHeader title="Users" description="Every account. Click a row for plan, billing, generations (metadata), keys, sessions, notes and the activity timeline." />
      <DataTable<UserRow> id="users" endpoint="/api/admin/users" columns={columns} exportName="users" searchPlaceholder="Email, name or ID…"
        onRowClick={(u) => navigate(`/admin/users/${u.id}`)}
        filters={[
          { key: "plan", label: "Plan", options: PLAN_OPTIONS },
          { key: "status", label: "Status", options: [{ value: "active", label: "Active" }, { value: "suspended", label: "Suspended" }, { value: "disabled", label: "Disabled" }] },
          { key: "role", label: "Role", options: [{ value: "user", label: "Customers" }, { value: "staff", label: "Staff" }] },
        ]}
        bulkActions={can("users.bulk") ? (rows, done) => <BulkBar rows={rows} done={done} /> : undefined}
        emptyTitle="No users yet" />
    </AdminShell>
  );
}
