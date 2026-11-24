import type { ColumnDef } from "@tanstack/react-table";
import {
  ArrowLeft, Ban, Download, Eye, Gift, KeyRound, LogOut, Mail, MoreHorizontal, ShieldOff, Tags, Trash2, UserRoundSearch, Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { fmtDuration, timeAgo } from "@/lib/format";
import { auditColumns, AuditDetail, type AuditRow } from "./audit";
import { DataTable } from "../components/data-table";
import { FormDialog, useDialogs } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, inr, LoadingRows, num, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, adminDownload, errMsg } from "../lib/admin-api";
import { PLAN_OPTIONS, planName, planTone } from "../lib/plans";
import { statusTone } from "./users";

type Detail = {
  user: {
    id: number; email: string; name: string; role: string; plan: string; plan_until: string | null; status: string;
    created_at: string; last_active_at: string | null; last_login_at: string | null; tags: string[]; is_active: boolean;
    suspended_at: string | null; suspend_reason: string; billing: { name: string; gstin: string; state: string; address: string };
  };
  usage: { plan_name: string; allowance: number | null; used: number; reserved: number; remaining: number | null; unlimited: boolean; period_start: string; period_end: string };
  history: { month: string; chars: number }[];
  bonus: { id: number; chars: number; reason: string; created_at: string; current: boolean }[];
  lifetime: { generations: number; chars: number; revenue_paise: number };
  consent: { consent_at: string | null; terms_version: string | null; consent_ip: string | null; marketing_opt_in: boolean };
  can: { write: boolean; delete: boolean; impersonate: boolean; content: boolean; export: boolean };
};
type Gen = { id: string; status: string; voice: string; lang: string; style: string | null; chars: number; duration_sec: number | null; via: string; error: string | null; created_at: string };
type Billing = {
  subscriptions: { id: number; rzp_subscription_id: string; plan: string; period: string; status: string; current_start: string | null; current_end: string | null; cancel_at_period_end: boolean }[];
  payments: { id: number; rzp_payment_id: string; amount_paise: number; status: string; method: string; created_at: string }[];
  invoices: { id: number; number: string; issued_at: string; plan: string; period: string; total_paise: number }[];
};

function useJson<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    adminApi<T>(url).then(setData, (e) => setError(errMsg(e)));
  }, [url]);
  useEffect(load, [load]);
  return { data, error, load };
}

const REASONS = [
  { value: "abuse_report", label: "Abuse report" },
  { value: "support_consent", label: "Support request with the user's consent" },
  { value: "legal_request", label: "Legal request" },
];

function Generations({ uid, canContent }: { uid: number; canContent: boolean }) {
  const [reveal, setReveal] = useState<Gen | null>(null);
  const [reason, setReason] = useState("abuse_report");
  const [note, setNote] = useState("");
  const [shown, setShown] = useState<Record<string, { excerpt: string; audio_url: string | null }>>({});
  const cols: ColumnDef<Gen, unknown>[] = [
    { id: "created_at", header: "When", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at)}</span> },
    { id: "status", header: "Status", cell: ({ row }) => <Pill tone={row.original.status === "done" ? "green" : row.original.status === "error" ? "red" : "gray"}>{row.original.status}</Pill> },
    { id: "voice", header: "Voice", cell: ({ row }) => <span className="font-mono text-xs">{row.original.voice}{row.original.style ? ` · ${row.original.style}` : ""}</span> },
    { id: "chars", header: "Chars", meta: { sortKey: "chars", className: "text-right" }, cell: ({ row }) => <span className="tabular">{num(row.original.chars)}</span> },
    { id: "duration", header: "Audio", cell: ({ row }) => <span className="tabular text-xs">{fmtDuration(row.original.duration_sec)}</span> },
    { id: "via", header: "Via", cell: ({ row }) => <Pill>{row.original.via}</Pill> },
    { id: "content", header: "Script", cell: ({ row: { original: g } }) => shown[g.id] ? (
      <div className="max-w-xs space-y-1">
        <p className="text-xs">{shown[g.id].excerpt}</p>
        {shown[g.id].audio_url && <audio controls preload="none" src={shown[g.id].audio_url!} className="h-8 w-56" />}
      </div>
    ) : canContent ? (
      <Button size="xs" variant="outline" onClick={(e) => (e.stopPropagation(), setReveal(g))}><Eye /> View</Button>
    ) : <span className="text-xs text-muted-foreground">hidden</span> },
  ];
  return (
    <>
      <p className="mb-3 text-xs text-muted-foreground">Metadata only. Scripts and audio are hidden by default (Privacy Policy); viewing one needs a reason and is audited.</p>
      <DataTable<Gen> id="user-gens" syncUrl={false} endpoint={`/api/admin/users/${uid}/generations`} columns={cols} searchPlaceholder={null}
        exportName="generations" emptyTitle="No generations yet" />
      <FormDialog open={!!reveal} onOpenChange={(o) => !o && setReveal(null)} title="View script and audio"
        description="Only for a stated reason. This is recorded in the audit log with your name." submitLabel="View"
        onSubmit={async () => {
          const r = await adminApi<{ excerpt: string; audio_url: string | null }>(`/api/admin/generations/${reveal!.id}/reveal`, { json: { reason, note } });
          setShown((s) => ({ ...s, [reveal!.id]: r }));
        }}>
        <Field label="Reason"><Select value={reason} onChange={(e) => setReason(e.target.value)} className="w-full">{REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</Select></Field>
        <Field label="Reference (optional)" htmlFor="rv-note"><Input id="rv-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ticket #, report ID…" /></Field>
      </FormDialog>
    </>
  );
}

function Keys({ uid, canWrite }: { uid: number; canWrite: boolean }) {
  const { data, error, load } = useJson<{ items: { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null }[] }>(`/api/admin/users/${uid}/keys`);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingRows rows={3} />;
  if (!data.items.length) return <p className="py-6 text-center text-sm text-muted-foreground">No API keys</p>;
  return (
    <ul className="divide-y rounded-xl border bg-surface">
      {data.items.map((k) => (
        <li key={k.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
          <KeyRound className="size-4 text-muted-foreground" />
          <span className="font-medium">{k.name}</span><span className="font-mono text-xs text-muted-foreground">{k.prefix}…</span>
          <span className="text-xs text-muted-foreground">created {fmtDate(k.created_at, false)} · last used {k.last_used_at ? timeAgo(k.last_used_at) : "never"}</span>
          {k.revoked_at ? <Pill tone="gray" className="ml-auto">revoked</Pill> : canWrite && (
            <Button size="xs" variant="outline" className="ml-auto" onClick={async () => {
              try { await adminApi(`/api/admin/users/${uid}/keys/${k.id}`, { method: "DELETE" }); toast.success("Key revoked"); load(); } catch (e) { toast.error(errMsg(e)); }
            }}>Revoke</Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function Sessions({ uid, canWrite }: { uid: number; canWrite: boolean }) {
  const { data, error, load } = useJson<{ items: { id: number; created_at: string; last_seen_at: string; ip: string | null; user_agent: string | null; current: boolean }[] }>(`/api/admin/users/${uid}/sessions`);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingRows rows={3} />;
  return (
    <div className="space-y-3">
      {canWrite && data.items.length > 0 && (
        <Button size="sm" variant="outline" onClick={async () => {
          try { const r = await adminApi<{ sessions: number }>(`/api/admin/users/${uid}/sessions/revoke`, { method: "POST" }); toast.success(`Signed out of ${r.sessions} sessions`); load(); } catch (e) { toast.error(errMsg(e)); }
        }}><LogOut /> Sign out everywhere</Button>
      )}
      {!data.items.length ? <p className="py-6 text-center text-sm text-muted-foreground">No active sessions</p> : (
        <ul className="divide-y rounded-xl border bg-surface">
          {data.items.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
              <span className="font-mono text-xs">{s.ip ?? "?"}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{s.user_agent}</span>
              <span className="text-xs text-muted-foreground">seen {timeAgo(s.last_seen_at)}</span>
              {s.current ? <Pill tone="blue">this device</Pill> : canWrite && (
                <Button size="xs" variant="outline" onClick={async () => {
                  try { await adminApi(`/api/admin/users/${uid}/sessions/${s.id}`, { method: "DELETE" }); load(); } catch (e) { toast.error(errMsg(e)); }
                }}>Revoke</Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Notes({ uid, canWrite }: { uid: number; canWrite: boolean }) {
  const { data, error, load } = useJson<{ items: { id: number; body: string; author_email: string; created_at: string; mine: boolean }[] }>(`/api/admin/users/${uid}/notes`);
  const [body, setBody] = useState("");
  if (error) return <ErrorState message={error} onRetry={load} />;
  return (
    <div className="space-y-4">
      {canWrite && (
        <form className="space-y-2" onSubmit={async (e) => {
          e.preventDefault();
          try { await adminApi(`/api/admin/users/${uid}/notes`, { json: { body } }); setBody(""); load(); } catch (err) { toast.error(errMsg(err)); }
        }}>
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="Internal note (never shown to the user)" aria-label="New note" />
          <Button size="sm" type="submit" disabled={!body.trim()}>Add note</Button>
        </form>
      )}
      {!data ? <LoadingRows rows={2} /> : !data.items.length ? <p className="text-sm text-muted-foreground">No notes yet.</p> : (
        <ul className="space-y-2">
          {data.items.map((n) => (
            <li key={n.id} className="rounded-xl border bg-surface p-3 text-sm">
              <p className="whitespace-pre-wrap">{n.body}</p>
              <p className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">{n.author_email} · {timeAgo(n.created_at)}
                {canWrite && <button type="button" className="ml-auto hover:text-danger" aria-label="Delete note" onClick={async () => {
                  try { await adminApi(`/api/admin/users/${uid}/notes/${n.id}`, { method: "DELETE" }); load(); } catch (e) { toast.error(errMsg(e)); }
                }}><Trash2 className="size-3.5" /></button>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Timeline({ uid }: { uid: number }) {
  const { data, error, load } = useJson<{ items: { at: string; kind: string; text: string }[] }>(`/api/admin/users/${uid}/timeline`);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingRows rows={4} />;
  return (
    <ol className="relative space-y-3 border-l pl-5">
      {data.items.map((e, i) => (
        <li key={i} className="text-sm">
          <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full border-2 border-surface bg-brand-indigo" aria-hidden="true" />
          <p>{e.text}</p>
          <p className="text-xs text-muted-foreground"><span className="capitalize">{e.kind}</span> · {fmtDate(e.at)}</p>
        </li>
      ))}
    </ol>
  );
}

function BillingTab({ uid }: { uid: number }) {
  const { data, error, load } = useJson<Billing>(`/api/admin/users/${uid}/billing`);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingRows rows={4} />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Subscriptions">
        {!data.subscriptions.length ? <p className="text-sm text-muted-foreground">No subscriptions.</p> : (
          <ul className="divide-y text-sm">
            {data.subscriptions.map((s) => (
              <li key={s.id} className="py-2">
                <p className="flex items-center gap-2"><span className="font-medium">{planName(s.plan)} · {s.period}</span><Pill tone={s.status === "active" ? "green" : "gray"}>{s.status}</Pill>{s.cancel_at_period_end && <Pill tone="amber">cancels at period end</Pill>}</p>
                <p className="font-mono text-xs text-muted-foreground">{s.rzp_subscription_id} · {fmtDate(s.current_start, false)} → {fmtDate(s.current_end, false)}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Payments">
        {!data.payments.length ? <p className="text-sm text-muted-foreground">No payments.</p> : (
          <ul className="divide-y text-sm">
            {data.payments.map((x) => (
              <li key={x.id} className="flex items-center gap-2 py-2">
                <span className="font-mono text-xs">{x.rzp_payment_id}</span><span className="text-xs text-muted-foreground">{x.method}</span>
                <span className="ml-auto tabular">{inr(x.amount_paise, 2)}</span><Pill tone={x.status === "captured" ? "green" : x.status === "failed" ? "red" : "gray"}>{x.status}</Pill>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Invoices" className="lg:col-span-2">
        {!data.invoices.length ? <p className="text-sm text-muted-foreground">No invoices.</p> : (
          <ul className="divide-y text-sm">
            {data.invoices.map((i) => (
              <li key={i.id} className="flex items-center gap-3 py-2">
                <span className="font-mono text-xs">{i.number}</span><span className="text-xs text-muted-foreground">{fmtDate(i.issued_at, false)} · {planName(i.plan)} {i.period}</span>
                <span className="ml-auto tabular">{inr(i.total_paise, 2)}</span>
                <Button size="xs" variant="outline" onClick={() => adminDownload(`/api/billing/invoices/${i.id}/pdf`, `${i.number}.pdf`).catch((e) => toast.error(errMsg(e)))}><Download /> PDF</Button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

export default function UserDetailPage() {
  const { id = "" } = useParams();
  const uid = Number(id);
  const navigate = useNavigate();
  const { data, error, load } = useJson<Detail>(`/api/admin/users/${uid}`);
  const d = useDialogs<"plan" | "bonus" | "suspend" | "delete" | "impersonate" | "tags" | "reset">();
  const [plan, setPlan] = useState("creator");
  const [until, setUntil] = useState("");
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(false);
  const [chars, setChars] = useState("1000");
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState("");
  const [tags, setTags] = useState("");
  const [auditRow, setAuditRow] = useState<AuditRow | null>(null);
  const open = (k: Parameters<typeof d.show>[0]) => (setReason(""), setConfirm(""), d.show(k));

  if (error) return <AdminShell title="User"><ErrorState message={error} onRetry={load} /></AdminShell>;
  if (!data) return <AdminShell title="User"><LoadingRows rows={8} /></AdminShell>;
  const { user: u, usage, can } = data;
  const pctUsed = usage.allowance ? Math.min(100, ((usage.used + usage.reserved) / usage.allowance) * 100) : 0;
  const suspended = u.status === "suspended";

  return (
    <AdminShell title={u.email}>
      <Link to="/admin/users" className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Users</Link>
      <PageHeader
        title={u.email}
        description={<span className="flex flex-wrap items-center gap-2">#{u.id}{u.name && ` · ${u.name}`} · <Pill tone={planTone(u.plan)}>{planName(u.plan)}</Pill><Pill tone={statusTone(u.status)}>{u.status}</Pill>{u.role !== "user" && <Pill tone="blue">{u.role}</Pill>}{u.tags.map((t) => <Pill key={t}>{t}</Pill>)}</span>}
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm"><MoreHorizontal /> Actions</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuItem disabled={!can.write} onSelect={() => (setPlan(u.plan === "free" ? "creator" : u.plan), setUntil(u.plan_until?.slice(0, 10) ?? ""), open("plan"))}><Wallet /> Change plan / end date</DropdownMenuItem>
              <DropdownMenuItem disabled={!can.write} onSelect={() => open("bonus")}><Gift /> Bonus characters</DropdownMenuItem>
              <DropdownMenuItem disabled={!can.write} onSelect={() => (setTags(u.tags.join(", ")), open("tags"))}><Tags /> Edit tags</DropdownMenuItem>
              <DropdownMenuItem disabled={!can.write} onSelect={() => open("suspend")}>{suspended ? <ShieldOff /> : <Ban />} {suspended ? "Unsuspend" : "Suspend"}</DropdownMenuItem>
              <DropdownMenuItem disabled={!can.write} onSelect={() => open("reset")}><Mail /> Email password reset link</DropdownMenuItem>
              <DropdownMenuItem disabled title="Email verification isn't used while signup is invite-only"><Mail /> Resend verification (n/a)</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled={!can.impersonate || u.role !== "user"} onSelect={() => open("impersonate")}><UserRoundSearch /> View as user (read-only)</DropdownMenuItem>
              <DropdownMenuItem disabled={!can.export} onSelect={() => adminDownload(`/api/admin/users/${uid}/export`, `aiwazz-user-${uid}-export.json`).catch((e) => toast.error(errMsg(e)))}><Download /> Export data (DPDP)</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled={!can.delete || u.role === "owner"} className="text-danger focus:text-danger" onSelect={() => open("delete")}><Trash2 /> Delete user</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />
      {suspended && <p role="status" className="mb-4 rounded-xl border border-danger/30 bg-danger/5 p-3 text-sm">Suspended {fmtDate(u.suspended_at)}: {u.suspend_reason}</p>}

      <Tabs defaultValue="profile">
        <div className="-mx-3 mb-4 overflow-x-auto px-3">
          <TabsList>
            {["profile", "usage", "billing", "generations", "keys", "sessions", "consent", "notes", "activity", "audit"].map((t) => (
              <TabsTrigger key={t} value={t} className="capitalize">{t === "usage" ? "Plan & usage" : t === "billing" ? "Subscription & invoices" : t === "keys" ? "API keys" : t}</TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="profile">
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Account">
              <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">Signed up</dt><dd>{fmtDate(u.created_at)}</dd>
                <dt className="text-muted-foreground">Last login</dt><dd>{fmtDate(u.last_login_at)}</dd>
                <dt className="text-muted-foreground">Last active</dt><dd>{u.last_active_at ? timeAgo(u.last_active_at) : "–"}</dd>
                <dt className="text-muted-foreground">Lifetime</dt><dd>{num(data.lifetime.generations)} generations · {num(data.lifetime.chars)} characters · {inr(data.lifetime.revenue_paise)}</dd>
              </dl>
            </Section>
            <Section title="Billing details">
              <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">Name</dt><dd>{u.billing.name || "–"}</dd>
                <dt className="text-muted-foreground">GSTIN</dt><dd className="font-mono">{u.billing.gstin || "–"}</dd>
                <dt className="text-muted-foreground">State code</dt><dd>{u.billing.state || "–"}</dd>
                <dt className="text-muted-foreground">Address</dt><dd>{u.billing.address || "–"}</dd>
              </dl>
            </Section>
          </div>
        </TabsContent>
        <TabsContent value="usage">
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Current cycle" description={`${fmtDate(usage.period_start, false)} – ${fmtDate(usage.period_end, false)}`}>
              <p className="text-2xl font-semibold tabular">{num(usage.used)} <span className="text-sm font-normal text-muted-foreground">/ {usage.unlimited ? "unlimited" : num(usage.allowance)} characters</span></p>
              {!usage.unlimited && <div className="mt-3 h-2 rounded-full bg-surface-2"><div className="h-full rounded-full bg-brand-gradient" style={{ width: `${pctUsed}%` }} /></div>}
              <p className="mt-2 text-xs text-muted-foreground">{num(usage.reserved)} reserved by queued jobs · plan {usage.plan_name}{u.plan_until ? ` until ${fmtDate(u.plan_until, false)}` : ""}</p>
            </Section>
            <Section title="Last 6 months" description="Characters from successful jobs">
              <ul className="space-y-2">
                {data.history.map((h) => {
                  const max = Math.max(1, ...data.history.map((x) => x.chars));
                  return (
                    <li key={h.month} className="grid grid-cols-[64px_1fr_auto] items-center gap-3 text-xs">
                      <span className="text-muted-foreground">{h.month}</span>
                      <span className="h-2 rounded-full bg-surface-2"><span className="block h-full rounded-full bg-brand-indigo" style={{ width: `${(h.chars / max) * 100}%` }} /></span>
                      <span className="tabular">{num(h.chars)}</span>
                    </li>
                  );
                })}
              </ul>
            </Section>
            <Section title="Bonus characters" className="lg:col-span-2" actions={can.write && <Button size="sm" variant="outline" onClick={() => open("bonus")}><Gift /> Add</Button>}>
              {!data.bonus.length ? <p className="text-sm text-muted-foreground">None.</p> : (
                <ul className="divide-y text-sm">{data.bonus.map((b) => (
                  <li key={b.id} className="flex items-center gap-3 py-2"><span className={`tabular font-medium ${b.chars < 0 ? "text-danger" : ""}`}>{b.chars > 0 ? "+" : ""}{num(b.chars)}</span><span className="text-muted-foreground">{b.reason}</span><span className="ml-auto text-xs text-muted-foreground">{fmtDate(b.created_at, false)}{b.current ? " · this cycle" : ""}</span></li>
                ))}</ul>
              )}
            </Section>
          </div>
        </TabsContent>
        <TabsContent value="billing"><BillingTab uid={uid} /></TabsContent>
        <TabsContent value="generations"><Generations uid={uid} canContent={can.content} /></TabsContent>
        <TabsContent value="keys"><Keys uid={uid} canWrite={can.write} /></TabsContent>
        <TabsContent value="sessions"><Sessions uid={uid} canWrite={can.write} /></TabsContent>
        <TabsContent value="consent">
          <Section title="Consent records">
            <dl className="grid grid-cols-[180px_1fr] gap-y-2 text-sm">
              <dt className="text-muted-foreground">Accepted Terms / Privacy / AUP</dt><dd>{fmtDate(data.consent.consent_at)}</dd>
              <dt className="text-muted-foreground">Terms version</dt><dd>{data.consent.terms_version ?? "–"}</dd>
              <dt className="text-muted-foreground">IP at signup</dt><dd className="font-mono">{data.consent.consent_ip ?? "–"}</dd>
              <dt className="text-muted-foreground">Marketing emails</dt><dd>{data.consent.marketing_opt_in ? "Opted in" : "No"}</dd>
            </dl>
          </Section>
        </TabsContent>
        <TabsContent value="notes"><Notes uid={uid} canWrite={can.write} /></TabsContent>
        <TabsContent value="activity"><Timeline uid={uid} /></TabsContent>
        <TabsContent value="audit">
          <DataTable<AuditRow> id="user-audit" syncUrl={false} endpoint="/api/admin/audit" extraParams={{ target_type: "user", target_id: String(uid) }}
            columns={auditColumns} searchPlaceholder={null} onRowClick={setAuditRow} emptyTitle="No staff actions on this account" />
          <AuditDetail row={auditRow} onClose={() => setAuditRow(null)} />
        </TabsContent>
      </Tabs>

      <FormDialog {...d.props("plan")} title="Change plan" description="Takes effect now. Asks you to confirm it's you. For paying subscribers, change the subscription in Billing instead."
        onSubmit={async () => { await adminApi(`/api/admin/users/${uid}/plan`, { method: "PUT", json: { plan, until: plan === "free" ? null : until || null, reason, notify } }); toast.success("Plan changed"); load(); }}
        disabled={reason.trim().length < 3} submitLabel="Change plan">
        <Field label="Plan"><Select value={plan} onChange={(e) => setPlan(e.target.value)} className="w-full">{PLAN_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></Field>
        <Field label="Last day (India time, optional)" hint="Empty = no end date. After this day the account moves to Free automatically." htmlFor="pl-until">
          <Input id="pl-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} disabled={plan === "free"} /></Field>
        <Field label="Reason (audit log)" htmlFor="pl-reason"><Input id="pl-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Early-access friend: Creator free for 3 months" /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Email the user</label>
      </FormDialog>
      <FormDialog {...d.props("bonus")} title="Bonus characters" description="For this usage cycle only. Use a negative number to remove."
        onSubmit={async () => { await adminApi(`/api/admin/users/${uid}/bonus`, { json: { chars: Number(chars), reason } }); toast.success("Bonus saved"); load(); }}
        disabled={!Number(chars) || reason.trim().length < 3}>
        <Field label="Characters" htmlFor="bn-chars"><Input id="bn-chars" type="number" value={chars} onChange={(e) => setChars(e.target.value)} /></Field>
        <Field label="Reason (required)" htmlFor="bn-reason"><Input id="bn-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Sorry for yesterday's outage" /></Field>
      </FormDialog>
      <FormDialog {...d.props("tags")} title="Tags" description="Comma separated, e.g. early-access, agency"
        onSubmit={async () => { await adminApi(`/api/admin/users/${uid}/tags`, { method: "PUT", json: { tags: tags.split(",").map((t) => t.trim()).filter(Boolean) } }); load(); }}>
        <Field label="Tags" htmlFor="tg"><Input id="tg" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
      </FormDialog>
      <FormDialog {...d.props("suspend")} title={suspended ? "Unsuspend account" : "Suspend account"} destructive={!suspended}
        description={suspended ? "The user can sign in again." : "Signs the user out everywhere and blocks sign-in and API keys. They see a friendly message."}
        onSubmit={async () => { await adminApi(`/api/admin/users/${uid}/suspend`, { json: { suspend: !suspended, reason, message, notify: true } }); toast.success(suspended ? "Unsuspended" : "Suspended"); load(); }}
        disabled={reason.trim().length < 3} submitLabel={suspended ? "Unsuspend" : "Suspend"}>
        <Field label="Internal reason (audit log)" htmlFor="sp-reason"><Input id="sp-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        {!suspended && <Field label="Message to the user (optional, in the email)" htmlFor="sp-msg"><Textarea id="sp-msg" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} /></Field>}
      </FormDialog>
      <FormDialog {...d.props("reset")} title="Email a password reset link" description="Sends a one-time link (valid 1 hour) and signs the user out everywhere. You never see the link."
        onSubmit={async () => { const r = await adminApi<{ email: string }>(`/api/admin/users/${uid}/password-reset`, { method: "POST" }); toast.success(`Reset link: ${r.email}`); }} submitLabel="Send link" />
      <FormDialog {...d.props("impersonate")} title="View as this user" description="Read-only for 15 minutes: you can't generate, pay, change the password or delete anything. A banner shows the whole time; start and stop are audited."
        onSubmit={async () => { const r = await adminApi<{ redirect: string }>(`/api/admin/users/${uid}/impersonate`, { json: { reason } }); window.location.href = r.redirect; }}
        disabled={reason.trim().length < 3} submitLabel="Start viewing">
        <Field label="Reason (audit log)" htmlFor="im-reason"><Input id="im-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Support ticket: history looks empty" /></Field>
      </FormDialog>
      <FormDialog {...d.props("delete")} title="Delete this user" destructive submitLabel="Delete permanently"
        description="Deletes the account, history, audio, keys and sessions; cancels a live subscription. Invoices and payments are kept (8 years, tax law). Asks you to confirm it's you."
        onSubmit={async () => { const r = await adminApi<{ reference: string }>(`/api/admin/users/${uid}/delete`, { json: { confirm_email: confirm, reason } }); toast.success(`Deleted · ${r.reference}`); navigate("/admin/users"); }}
        disabled={confirm.trim().toLowerCase() !== u.email || reason.trim().length < 3}>
        <Field label={`Type ${u.email} to confirm`} htmlFor="del-confirm"><Input id="del-confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" /></Field>
        <Field label="Reason (audit log)" htmlFor="del-reason"><Input id="del-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="DPDP deletion request" /></Field>
      </FormDialog>
    </AdminShell>
  );
}
