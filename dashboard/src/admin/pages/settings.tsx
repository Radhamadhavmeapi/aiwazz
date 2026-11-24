import { KeyRound, Loader2, LogOut, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { ErrorState, Field, LoadingRows, PageHeader, Section } from "../components/page";
import { AdminShell } from "../components/shell";
import { BackupCodes } from "./lock";
import { SettingsExtra, SETTINGS_TABS } from "./settings-extra";

type Security = {
  ip_allowlist: { enabled: boolean; cidrs: string[] }; your_ip: string; idle_minutes: number; stepup_minutes: number;
  session_days: number; impersonate_minutes: number;
};

function SecurityTab() {
  const { can, me, refresh } = useAdmin();
  const [data, setData] = useState<Security | null>(null);
  const [error, setError] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [cidrs, setCidrs] = useState("");
  const [busy, setBusy] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const load = useCallback(() => {
    setError("");
    adminApi<Security>("/api/admin/settings/security").then((d) => {
      setData(d);
      setEnabled(d.ip_allowlist.enabled);
      setCidrs(d.ip_allowlist.cidrs.join("\n"));
    }, (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingRows rows={4} />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Your 2FA" description="Authenticator app (TOTP) + single-use backup codes.">
        <p className="flex items-center gap-2 text-sm"><ShieldCheck className="size-4 text-success" /> 2FA is on · {me?.mfa.backup_codes_left ?? 0} backup codes left</p>
        {codes ? (
          <div className="mt-4"><p className="mb-2 text-xs text-muted-foreground">New codes (the old ones stopped working). Shown only now.</p><BackupCodes codes={codes} /></div>
        ) : (
          <Button className="mt-4" variant="outline" size="sm" disabled={busy === "codes"} onClick={() => run("codes", async () => {
            const r = await adminApi<{ backup_codes: string[] }>("/api/admin/mfa/backup-codes", { method: "POST" });
            setCodes(r.backup_codes);
            void refresh();
          })}>
            {busy === "codes" ? <Loader2 className="animate-spin" /> : <KeyRound />} Make new backup codes
          </Button>
        )}
        <p className="mt-3 text-xs text-muted-foreground">Lost your phone and all codes? The owner (or someone with server access) runs <code className="font-mono">manage.py reset-2fa --email …</code>.</p>
      </Section>
      <Section title="Admin sessions" description={`The panel locks after ${data.idle_minutes} min without activity; sensitive actions ask for your password + 2FA again (valid ${data.stepup_minutes} min).`}>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={!!busy} onClick={() => run("mine", async () => {
            const r = await adminApi<{ sessions: number }>("/api/admin/sessions/sign-out-admin", { json: { scope: "mine" } });
            toast.success(`Locked ${r.sessions} other admin session${r.sessions === 1 ? "" : "s"}`);
          })}><LogOut /> Lock my other admin sessions</Button>
          {can("roles.write") && (
            <Button variant="outline" size="sm" disabled={!!busy} onClick={() => run("all", async () => {
              const r = await adminApi<{ sessions: number }>("/api/admin/sessions/sign-out-admin", { json: { scope: "all_staff" } });
              toast.success(`Locked ${r.sessions} staff session${r.sessions === 1 ? "" : "s"}`);
            })}><LogOut /> Lock every staff session</Button>
          )}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">App sessions last {data.session_days} days; "view as user" lasts {data.impersonate_minutes} min.</p>
      </Section>
      <Section title="Admin IP allowlist" description="Off by default (your IP changes). When on, the admin panel answers 404 to every other address." className="lg:col-span-2">
        <div className="space-y-4">
          <label className="flex items-center gap-3 text-sm">
            <Switch checked={enabled} onCheckedChange={setEnabled} disabled={!can("settings.write")} aria-label="Enable IP allowlist" />
            Only allow these IPs / ranges
          </label>
          <Field label="IPs or CIDR ranges, one per line" htmlFor="cidrs" hint={<>Your current IP: <span className="font-mono">{data.your_ip}</span>. Saving a list without it is refused, so you can't lock yourself out.</>}>
            <Textarea id="cidrs" rows={4} value={cidrs} onChange={(e) => setCidrs(e.target.value)} className="font-mono text-sm" placeholder={"203.0.113.7\n198.51.100.0/24"} disabled={!can("settings.write")} />
          </Field>
          {can("settings.write") && (
            <Button size="sm" disabled={busy === "ip"} onClick={() => run("ip", async () => {
              await adminApi("/api/admin/settings/security", { method: "PUT", json: { enabled, cidrs: cidrs.split(/\s+/).filter(Boolean) } });
              toast.success("Saved");
              load();
            })}>{busy === "ip" && <Loader2 className="animate-spin" />} Save</Button>
          )}
        </div>
      </Section>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AdminShell title="Settings">
      <PageHeader title="Settings" description="Security, general settings, limits, feature flags, payments and integrations. Every change is audited." />
      <Tabs defaultValue="security">
        <TabsList className="mb-4 flex-wrap">
          <TabsTrigger value="security">Security</TabsTrigger>
          {SETTINGS_TABS.map((t) => <TabsTrigger key={t.id} value={t.id}>{t.label}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="security"><SecurityTab /></TabsContent>
        {SETTINGS_TABS.map((t) => <TabsContent key={t.id} value={t.id}><SettingsExtra tab={t.id} /></TabsContent>)}
      </Tabs>
    </AdminShell>
  );
}
