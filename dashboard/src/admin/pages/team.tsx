import { Crown, KeyRound, ShieldCheck, ShieldOff, UserMinus, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { timeAgo } from "@/lib/format";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Staff = { id: number; email: string; name: string; role: string; active: boolean; mfa: boolean; last_login_at: string | null; last_action_at: string | null; you: boolean };
type Team = { staff: Staff[]; invites: { id: number; email: string; role: string; expires_at: string; label: string }[]; roles: Record<string, string[]> };
const ROLE_INFO: Record<string, string> = {
  owner: "Everything, including roles, ownership and secrets", admin: "Everything except roles, ownership and secrets",
  support: "Users (read), invites, support inbox, moderation", finance: "Billing, invoices, GST exports, refunds", viewer: "Read-only dashboards",
};

export default function TeamPage() {
  const { can } = useAdmin();
  const [t, setT] = useState<Team | null>(null);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState(false);
  const [inv, setInv] = useState({ email: "", role: "support" });
  const [issued, setIssued] = useState<{ signup_url: string; email_status: string } | null>(null);
  const [act, setAct] = useState<{ kind: "role" | "active" | "2fa" | "owner"; s: Staff } | null>(null);
  const [role, setRole] = useState("support");
  const [reason, setReason] = useState("");
  const load = useCallback(() => adminApi<Team>("/api/admin/team").then(setT, (e) => setError(errMsg(e))), []);
  useEffect(() => void load(), [load]);
  const owner = can("roles.write");
  const open = (kind: "role" | "active" | "2fa" | "owner", s: Staff) => (setRole(s.role), setReason(""), setAct({ kind, s }));
  return (
    <AdminShell title="Team & roles">
      <PageHeader title="Team & roles" description="Staff accounts and what each role can do. Every staff member must set up 2FA before the admin panel opens for them."
        actions={owner && <Button size="sm" variant="brand" onClick={() => (setInv({ email: "", role: "support" }), setInvite(true))}><UserPlus /> Invite staff</Button>} />
      {error ? <ErrorState message={error} onRetry={load} /> : !t ? <LoadingRows rows={5} /> : (
        <div className="space-y-4">
          <Section title="Staff">
            <ul className="divide-y">
              {t.staff.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-1.5 font-medium"><Link to={`/admin/users/${s.id}`} className="hover:underline">{s.email}</Link>{s.you && <Pill tone="blue">you</Pill>}</p>
                    <p className="text-xs text-muted-foreground">last login {s.last_login_at ? timeAgo(s.last_login_at) : "never"} · last admin action {s.last_action_at ? timeAgo(s.last_action_at) : "never"} · <Link to={`/admin/audit?q=${encodeURIComponent(s.email)}`} className="hover:underline">audit trail</Link></p>
                  </div>
                  <Pill tone={s.role === "owner" ? "blue" : "gray"}>{s.role === "owner" && <Crown className="size-3" />}{s.role}</Pill>
                  <Pill tone={s.mfa ? "green" : "amber"}>{s.mfa ? <><ShieldCheck className="size-3" /> 2FA</> : <><ShieldOff className="size-3" /> no 2FA yet</>}</Pill>
                  {!s.active && <Pill tone="red">deactivated</Pill>}
                  {owner && !s.you && s.role !== "owner" && (
                    <span className="flex flex-wrap gap-1">
                      <Button size="xs" variant="outline" onClick={() => open("role", s)}>Change role</Button>
                      {s.mfa && <Button size="xs" variant="ghost" onClick={() => open("2fa", s)}><KeyRound /> Reset 2FA</Button>}
                      <Button size="xs" variant="ghost" onClick={() => open("active", s)}><UserMinus /> {s.active ? "Deactivate" : "Reactivate"}</Button>
                      {s.role === "admin" && s.mfa && can("ownership.transfer") && <Button size="xs" variant="ghost" onClick={() => open("owner", s)}><Crown /> Make owner</Button>}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </Section>
          {t.invites.length > 0 && (
            <Section title="Pending staff invites">
              <ul className="divide-y text-sm">{t.invites.map((i) => <li key={i.id} className="flex gap-3 py-2"><span className="flex-1">{i.email || i.label}</span><Pill>{i.role}</Pill><span className="text-xs text-muted-foreground">expires {fmtDate(i.expires_at, false)}</span></li>)}</ul>
            </Section>
          )}
          <Section title="Roles">
            <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(t.roles).map(([r, perms]) => (
                <li key={r} className="rounded-xl border p-3"><p className="font-medium capitalize">{r}</p><p className="text-xs text-muted-foreground">{ROLE_INFO[r]}</p>
                  <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted-foreground">{perms.length} permissions</summary><p className="mt-1 font-mono text-[10px] leading-relaxed">{perms.join(" · ")}</p></details></li>
              ))}
            </ul>
          </Section>
        </div>
      )}
      <FormDialog open={invite} onOpenChange={setInvite} title="Invite a staff member" disabled={!inv.email.includes("@")} submitLabel="Create invite"
        description="They sign up with the link (valid 7 days), then must set up 2FA at /admin before anything opens."
        onSubmit={async () => { setIssued(await adminApi("/api/admin/team/invite", { json: inv })); load(); }}>
        <Field label="Email" htmlFor="ti-email"><Input id="ti-email" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} /></Field>
        <Field label="Role"><Select className="w-full" value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}>{["admin", "support", "finance", "viewer"].map((r) => <option key={r} value={r}>{r}: {ROLE_INFO[r]}</option>)}</Select></Field>
      </FormDialog>
      <FormDialog open={!!issued} onOpenChange={(o) => !o && setIssued(null)} title="Staff invite created" submitLabel="Done" onSubmit={async () => undefined}
        description={`Email ${issued?.email_status}. Share this link yourself if mail is off (shown once):`}>
        <code className="block rounded-lg border bg-surface-2/60 p-2 font-mono text-xs break-all select-all">{issued?.signup_url}</code>
      </FormDialog>
      <FormDialog open={!!act} onOpenChange={(o) => !o && setAct(null)} destructive={act?.kind !== "role"}
        title={act?.kind === "role" ? `Change role: ${act.s.email}` : act?.kind === "2fa" ? `Reset 2FA for ${act?.s.email}` : act?.kind === "owner" ? `Make ${act?.s.email} the owner` : `${act?.s.active ? "Deactivate" : "Reactivate"} ${act?.s.email}`}
        description={act?.kind === "owner" ? "You become an admin. Type their email to confirm. Asks you to confirm it's you." : act?.kind === "2fa" ? "They'll set up 2FA again on their next visit (lost phone)." : "Asks you to confirm it's you. Their admin sessions lock."}
        disabled={(act?.kind === "active" && reason.trim().length < 3) || (act?.kind === "owner" && reason.trim().toLowerCase() !== act?.s.email)}
        onSubmit={async () => {
          const s = act!.s;
          if (act!.kind === "role") await adminApi(`/api/admin/team/${s.id}/role`, { method: "PUT", json: { role } });
          else if (act!.kind === "2fa") await adminApi(`/api/admin/team/${s.id}/reset-2fa`, { method: "POST" });
          else if (act!.kind === "owner") await adminApi("/api/admin/team/transfer-ownership", { json: { user_id: s.id, confirm_email: reason } });
          else await adminApi(`/api/admin/team/${s.id}/active`, { json: { active: !s.active, reason } });
          toast.success("Done");
          if (act!.kind === "owner") window.location.reload(); else load();
        }}>
        {act?.kind === "role" && <Field label="Role"><Select className="w-full" value={role} onChange={(e) => setRole(e.target.value)}>{["admin", "support", "finance", "viewer", "user"].map((r) => <option key={r} value={r}>{r === "user" ? "user (remove from staff)" : r}</option>)}</Select></Field>}
        {act?.kind === "active" && <Field label="Reason (audit log)" htmlFor="ta-reason"><Input id="ta-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
        {act?.kind === "owner" && <Field label="Their email" htmlFor="to-email"><Input id="to-email" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
      </FormDialog>
    </AdminShell>
  );
}

