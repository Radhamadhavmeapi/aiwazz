import type { ColumnDef } from "@tanstack/react-table";
import { Download, Gauge, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, num, PageHeader, Pill, Section, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Key = { id: number; name: string; prefix: string; user_id: number; email: string; created_at: string; last_used_at: string | null; revoked_at: string | null; requests_24h: number; requests_30d: number; rpm_override: number | null };
type Usage = {
  top: { user_id: number; email: string; chars: number; generations: number; api_generations: number }[];
  endpoints: { endpoint: string; total: number; "4xx": number; "5xx": number; error_rate: number }[];
  default_rpm: number; overrides: { id: number; scope: string; target_id: number; rpm: number; note: string; created_at: string }[];
};
type Spec = { info: { title: string; version: string }; paths: Record<string, Record<string, { summary?: string; description?: string }>> };

function Keys({ onLimit }: { onLimit: (k: Key) => void }) {
  const { can } = useAdmin();
  const [reload, setReload] = useState(0);
  const cols: ColumnDef<Key, unknown>[] = [
    { id: "key", header: "Key", cell: ({ row: { original: k } }) => <div><p className="font-medium">{k.name}</p><p className="font-mono text-[11px] text-muted-foreground">{k.prefix}…</p></div> },
    { id: "owner", header: "Owner", cell: ({ row }) => <Link to={`/admin/users/${row.original.user_id}`} className="text-xs hover:underline">{row.original.email}</Link> },
    { id: "created_at", header: "Created", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs">{fmtDate(row.original.created_at, false)}</span> },
    { id: "last_used", header: "Last used", meta: { sortKey: "last_used" }, cell: ({ row }) => <span className="text-xs">{row.original.last_used_at ? fmtDate(row.original.last_used_at) : "never"}</span> },
    { id: "req", header: "Requests 24h / 30d", meta: { className: "text-right" }, cell: ({ row }) => <span className="tabular">{num(row.original.requests_24h)} / {num(row.original.requests_30d)}</span> },
    { id: "limit", header: "Limit", cell: ({ row }) => row.original.rpm_override ? <Pill tone="blue">{row.original.rpm_override}/min</Pill> : <span className="text-xs text-muted-foreground">default</span> },
    { id: "status", header: "", cell: ({ row: { original: k } }) => k.revoked_at ? <Pill>revoked</Pill> : can("api.write") && (
      <span className="flex gap-1">
        <Button size="xs" variant="ghost" onClick={() => onLimit(k)}><Gauge /> Limit</Button>
        <Button size="xs" variant="outline" onClick={async () => {
          if (!window.confirm(`Revoke ${k.prefix}… (${k.email})? Scripts using it stop working.`)) return;
          try { await adminApi(`/api/admin/api-keys/${k.id}/revoke`, { method: "POST" }); setReload((n) => n + 1); } catch (e) { toast.error(errMsg(e)); }
        }}>Revoke</Button>
      </span>
    ) },
  ];
  return <DataTable<Key> id="api-keys" endpoint="/api/admin/api-keys" columns={cols} reloadKey={reload} exportName="api-keys" searchPlaceholder="Email, key prefix or name…"
    filters={[{ key: "status", label: "Status", options: [{ value: "active", label: "Active" }, { value: "revoked", label: "Revoked" }] }]} emptyTitle="No API keys" />;
}

function UsageTab({ reloadKey }: { reloadKey: number }) {
  const { can } = useAdmin();
  const [u, setU] = useState<Usage | null>(null);
  const [error, setError] = useState("");
  const [rpm, setRpm] = useState(60);
  const load = useCallback(() => adminApi<Usage>("/api/admin/api/usage").then((d) => (setU(d), setRpm(d.default_rpm)), (e) => setError(errMsg(e))), []);
  useEffect(() => void load(), [load, reloadKey]);
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!u) return <LoadingRows rows={6} />;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Section title="Top consumers (30 days)" description="Characters from successful jobs; API = made with an API key.">
        {!u.top.length ? <p className="text-sm text-muted-foreground">No usage yet.</p> : (
          <table className="w-full text-sm"><thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">User</th><th className="text-right">Characters</th><th className="text-right">Jobs</th><th className="text-right">via API</th></tr></thead>
            <tbody>{u.top.map((t) => <tr key={t.user_id} className="border-b last:border-0"><td className="py-2"><Link to={`/admin/users/${t.user_id}`} className="hover:underline">{t.email}</Link></td>
              <td className="text-right tabular">{num(t.chars)}</td><td className="text-right tabular">{t.generations}</td><td className="text-right tabular">{t.api_generations}</td></tr>)}</tbody></table>
        )}
      </Section>
      <Section title="Endpoints (7 days)" description="Requests and error rates per public endpoint (admin calls excluded).">
        {!u.endpoints.length ? <p className="text-sm text-muted-foreground">No requests counted yet.</p> : (
          <table className="w-full text-sm"><thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">Endpoint</th><th className="text-right">Requests</th><th className="text-right">4xx</th><th className="text-right">5xx</th><th className="text-right">Errors</th></tr></thead>
            <tbody>{u.endpoints.map((e) => <tr key={e.endpoint} className="border-b last:border-0"><td className="py-1.5 font-mono text-xs">{e.endpoint}</td><td className="text-right tabular">{num(e.total)}</td>
              <td className="text-right tabular">{e["4xx"]}</td><td className={`text-right tabular ${e["5xx"] ? "text-danger" : ""}`}>{e["5xx"]}</td><td className="text-right tabular">{e.error_rate}%</td></tr>)}</tbody></table>
        )}
      </Section>
      <Section title="Rate limits" description="Requests per minute per API key. Overrides win over the default; a key override wins over a user override." className="xl:col-span-2">
        <form className="mb-4 flex items-end gap-2" onSubmit={async (e) => {
          e.preventDefault();
          try { await adminApi("/api/admin/settings/limits/api", { method: "PUT", json: { api_rpm: rpm } }); toast.success("Saved"); load(); } catch (err) { toast.error(errMsg(err)); }
        }}>
          <Field label="Default (per key, per minute)" htmlFor="rpm"><Input id="rpm" type="number" min={1} max={10000} className="w-32" value={rpm} disabled={!can("api.write")} onChange={(e) => setRpm(Number(e.target.value))} /></Field>
          {can("api.write") && <Button type="submit" size="sm">Save</Button>}
        </form>
        {!u.overrides.length ? <p className="text-sm text-muted-foreground">No overrides. Use “Limit” on a key to add one.</p> : (
          <ul className="divide-y text-sm">{u.overrides.map((o) => (
            <li key={o.id} className="flex items-center gap-3 py-2"><Pill>{o.scope}</Pill><span className="font-mono text-xs">#{o.target_id}</span><span className="tabular">{o.rpm}/min</span>
              <span className="flex-1 truncate text-xs text-muted-foreground">{o.note}</span>
              {can("api.write") && <Button size="icon-xs" variant="ghost" aria-label="Remove override" onClick={async () => {
                try { await adminApi(`/api/admin/api/rate-overrides/${o.id}`, { method: "DELETE" }); load(); } catch (e) { toast.error(errMsg(e)); }
              }}><Trash2 /></Button>}</li>
          ))}</ul>
        )}
      </Section>
    </div>
  );
}

function Docs() {
  const [spec, setSpec] = useState<Spec | null>(null);
  const [error, setError] = useState("");
  useEffect(() => void adminApi<Spec>("/api/admin/api/openapi").then(setSpec, (e) => setError(errMsg(e))), []);
  if (error) return <ErrorState message={error} />;
  if (!spec) return <LoadingRows rows={6} />;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(spec, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: "aiwazz-openapi.json" }).click();
    URL.revokeObjectURL(url);
  };
  return (
    <Section title={`${spec.info.title} ${spec.info.version}`} description="Public docs are off in production; staff read the OpenAPI description here." actions={<Button size="sm" variant="outline" onClick={download}><Download /> openapi.json</Button>}>
      <ul className="divide-y text-sm">
        {Object.entries(spec.paths).sort().flatMap(([path, ops]) => Object.entries(ops).map(([m, op]) => (
          <li key={`${m}${path}`} className="flex items-baseline gap-3 py-1.5">
            <span className="w-16 shrink-0 font-mono text-xs font-semibold uppercase">{m}</span><span className="font-mono text-xs">{path}</span>
            <span className="truncate text-xs text-muted-foreground">{op.summary}</span>
          </li>
        )))}
      </ul>
    </Section>
  );
}

export default function ApiPage() {
  const [limit, setLimit] = useState<Key | null>(null);
  const [scope, setScope] = useState("key");
  const [rpm, setRpm] = useState("30");
  const [note, setNote] = useState("");
  const [bump, setBump] = useState(0);
  return (
    <AdminShell title="API & usage">
      <PageHeader title="API & usage" description="Every API key across users with request counts, rate-limit overrides, top consumers and endpoint error rates." />
      <Tabs defaultValue="keys">
        <TabsList className="mb-4"><TabsTrigger value="keys">API keys</TabsTrigger><TabsTrigger value="usage">Usage & limits</TabsTrigger><TabsTrigger value="docs">API docs</TabsTrigger></TabsList>
        <TabsContent value="keys"><Keys onLimit={(k) => (setScope("key"), setRpm(String(k.rpm_override ?? 30)), setNote(""), setLimit(k))} /></TabsContent>
        <TabsContent value="usage"><UsageTab reloadKey={bump} /></TabsContent>
        <TabsContent value="docs"><Docs /></TabsContent>
      </Tabs>
      <FormDialog open={!!limit} onOpenChange={(o) => !o && setLimit(null)} title="Rate-limit override" disabled={!(Number(rpm) >= 1)}
        description={`${limit?.prefix}… · ${limit?.email}`}
        onSubmit={async () => {
          await adminApi("/api/admin/api/rate-overrides", { json: { scope, target_id: scope === "key" ? limit!.id : limit!.user_id, rpm: Number(rpm), note } });
          toast.success("Override saved");
          setBump((n) => n + 1);
        }}>
        <Field label="Applies to"><Select className="w-full" value={scope} onChange={(e) => setScope(e.target.value)}><option value="key">This key</option><option value="user">All keys of {limit?.email}</option></Select></Field>
        <Field label="Requests per minute" htmlFor="ov-rpm"><Input id="ov-rpm" type="number" min={1} max={10000} value={rpm} onChange={(e) => setRpm(e.target.value)} /></Field>
        <Field label="Note" htmlFor="ov-note"><Input id="ov-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Bulk pipeline, agreed by email" /></Field>
      </FormDialog>
    </AdminShell>
  );
}
