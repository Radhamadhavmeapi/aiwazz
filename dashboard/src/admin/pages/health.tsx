import { CheckCircle2, CircleAlert, Download, HardDrive, Loader2, RefreshCw, RotateCw, ShieldCheck } from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Stat } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, adminDownload, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type Proc = { name: string; status: string; restarts: number; uptime_sec: number; memory: number; cpu: number; ours: boolean };
type Health = {
  host: { cpu_percent: number; cores: number; load: number[]; uptime_sec: number; memory_total: number; memory_available: number; swap: string; disk_total: number; disk_used: number; disk_free: number; disk_percent: number };
  api: { pid: number; rss: number; engine_ready: boolean; queue: number };
  processes: Proc[];
  database: { ok: boolean; version?: string; uptime_sec?: number; size_bytes?: number; error?: string };
  redis: { ok: boolean; ping_ms?: number; used_memory?: string; error?: string };
  ssl: { host: string; ok: boolean; expires_at?: string | null; days_left: number | null; error?: string }[];
  mail: { enabled: boolean; queue: { installed: boolean; size: number | null }; dns: Record<string, boolean>; dkim_selector: string; checked_at: string };
  storage: { audio_bytes: number; audio_files: number; retention_days: number; cleanup: string };
  backups: { dir: string; count: number; latest: { name: string; size: number; created_at: string } | null; last_run: { status: string; started_at: string; detail: string } | null; retention_days: number; encrypted: boolean };
  watchdog: { checked_at: string; api_ok: boolean; detail: string; fails: number } | null;
  alerts: { key: string; level: string; title: string; detail: string }[];
};
type Backups = { items: { name: string; size: number; created_at: string }[]; configured: boolean; running: boolean; dir: string; runs: { task: string; status: string; started_at: string; detail: string }[] };

const gb = (b: number) => `${(b / 1e9).toFixed(1)} GB`;
const mb = (b: number) => `${(b / 1e6).toFixed(0)} MB`;
const dur = (s: number) => (s >= 86400 ? `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h` : s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : `${Math.floor(s / 60)}m`);
const Ok = ({ ok, label }: { ok: boolean; label?: string }) => ok
  ? <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="size-4" /> {label ?? "OK"}</span>
  : <span className="inline-flex items-center gap-1 text-danger"><CircleAlert className="size-4" /> {label ?? "Problem"}</span>;

export default function HealthPage() {
  const { can, me } = useAdmin();
  const [h, setH] = useState<Health | null>(null);
  const [b, setB] = useState<Backups | null>(null);
  const [error, setError] = useState("");
  const [restart, setRestart] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => {
    setError("");
    adminApi<Health>("/api/admin/system").then(setH, (e) => setError(errMsg(e)));
    if (can("backups.read")) adminApi<Backups>("/api/admin/backups").then(setB, () => undefined);
  }, [can]);
  useEffect(load, [load]);
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  return (
    <AdminShell title="System health">
      <PageHeader title="System health" description="This server (OpenVZ, 4 threads, 6 GB RAM, no swap), AiWazz processes, database, Redis, certificates, mail, storage and backups."
        actions={<>
          {can("system.read") && <Button size="sm" variant="outline" disabled={busy === "alerts"} onClick={() => run("alerts", async () => { await adminApi("/api/admin/system/alerts/check", { method: "POST" }); load(); })}>{busy === "alerts" ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Check alerts now</Button>}
          <Button size="sm" variant="outline" onClick={load}><RefreshCw /> Refresh</Button>
        </>} />
      {error ? <ErrorState message={error} onRetry={load} /> : !h ? <LoadingRows rows={8} /> : (
        <div className="space-y-4">
          {h.alerts.length > 0 ? (
            <div role="alert" className="space-y-1 rounded-xl border border-danger/30 bg-danger/5 p-3 text-sm">
              {h.alerts.map((a) => <p key={a.key}><strong>{a.title}</strong> · {a.detail}</p>)}
              <p className="text-xs text-muted-foreground">Owner and admins get an email when an alert starts or clears (once mail is on).</p>
            </div>
          ) : <p className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/5 p-3 text-sm"><CheckCircle2 className="size-4 text-success" /> No active alerts. Checked every 5 minutes.</p>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="CPU" value={`${h.host.cpu_percent}%`} sub={`load ${h.host.load.join(" / ")} · ${h.host.cores} threads`} />
            <Stat label="Memory available" value={gb(h.host.memory_available)} sub={`of ${gb(h.host.memory_total)} · ${h.host.swap.split(" (")[0]} swap`} />
            <Stat label="voice-api RSS" value={mb(h.api.rss)} sub={`engine ${h.api.engine_ready ? "ready" : "loading"} · ${h.api.queue} waiting`} />
            <Stat label="Disk" value={`${h.host.disk_percent}%`} sub={`${gb(h.host.disk_free)} free of ${gb(h.host.disk_total)}`} />
            <Stat label="Server uptime" value={dur(h.host.uptime_sec)} />
            <Stat label="Audio storage" value={mb(h.storage.audio_bytes)} sub={`${h.storage.audio_files} files · kept ${h.storage.retention_days} days`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <Section title="Processes (PM2)">
              <ul className="divide-y text-sm">
                {h.processes.filter((p) => p.ours).map((p) => (
                  <li key={p.name} className="flex flex-wrap items-center gap-3 py-2">
                    <span className="w-32 shrink-0 font-mono text-xs">{p.name}</span>
                    <Pill tone={p.status === "online" ? "green" : p.status === "stopped" && p.name === "aiwazz-watchdog" ? "gray" : "red"}>{p.status}</Pill>
                    <span className="min-w-0 text-xs text-muted-foreground">{p.status === "online" ? `up ${dur(p.uptime_sec)} · ` : ""}{mb(p.memory)} · {p.restarts} restarts</span>
                    {can("system.write") && <Button size="xs" variant="outline" className="ml-auto" onClick={() => (setReason(""), setRestart(p.name))}><RotateCw /> Restart</Button>}
                  </li>
                ))}
              </ul>
              {h.watchdog && <p className="mt-2 text-xs text-muted-foreground">Watchdog: API {h.watchdog.api_ok ? "healthy" : `down (${h.watchdog.detail})`} · checked {fmtDate(h.watchdog.checked_at)}</p>}
            </Section>
            <Section title="Services">
              <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">MariaDB</dt><dd><Ok ok={h.database.ok} label={h.database.ok ? `${h.database.version} · ${h.database.size_bytes ? mb(h.database.size_bytes) : ""}` : h.database.error} /></dd>
                <dt className="text-muted-foreground">Redis</dt><dd><Ok ok={h.redis.ok} label={h.redis.ok ? `${h.redis.ping_ms} ms${h.redis.used_memory ? ` · ${h.redis.used_memory}` : ""}` : h.redis.error} /></dd>
                {h.ssl.map((s) => (
                  <Fragment key={s.host}><dt className="truncate text-muted-foreground">{s.host}</dt>
                    <dd>{s.ok ? <Ok ok={(s.days_left ?? 0) >= 14} label={`SSL ${s.days_left} days left`} /> : <span className="text-xs text-muted-foreground">{s.host.startsWith("mail.") ? "not set up yet" : s.error}</span>}</dd></Fragment>
                ))}
              </dl>
            </Section>
            <Section title="Mail">
              <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">Sending</dt><dd>{h.mail.enabled ? <Ok ok label="on" /> : <span className="text-warning">off (AIWAZZ_MAIL_ENABLED)</span>}</dd>
                <dt className="text-muted-foreground">Queue</dt><dd>{h.mail.queue.installed ? `${h.mail.queue.size} waiting` : <span className="text-muted-foreground">Postfix not installed yet</span>}</dd>
                {(["spf", "dkim", "dmarc"] as const).map((k) => (
                  <Fragment key={k}><dt className="text-muted-foreground uppercase">{k}</dt><dd><Ok ok={!!h.mail.dns[k]} label={h.mail.dns[k] ? "record found" : `no record${k === "dkim" ? ` (${h.mail.dkim_selector}._domainkey)` : ""}`} /></dd></Fragment>
                ))}
              </dl>
            </Section>
            {can("backups.read") && (
              <Section title="Backups" description={`Daily (after 02:00 IST) encrypted dump of the database + legal/config files (not audio), kept ${h.backups.retention_days} days in ${h.backups.dir}.`}
                actions={<HardDrive className="size-4 text-muted-foreground" />}>
                {!b?.configured ? <p className="text-sm text-warning">Not configured: run <code className="font-mono">manage.py gen-backup-key</code> on the server.</p> : (
                  <div className="space-y-3 text-sm">
                    <p>Latest: {b.items[0] ? <><span className="font-mono text-xs">{b.items[0].name}</span> · {mb(b.items[0].size)} · {fmtDate(b.items[0].created_at)}</> : "none yet"}</p>
                    <div className="flex flex-wrap gap-2">
                      {can("system.write") && <Button size="xs" variant="outline" disabled={b.running || busy === "backup"} onClick={() => run("backup", async () => { await adminApi("/api/admin/backups/run", { method: "POST" }); toast.success("Backup started"); setTimeout(load, 4000); })}>{b.running ? <Loader2 className="animate-spin" /> : <HardDrive />} Back up now</Button>}
                      {can("system.write") && b.items[0] && <Button size="xs" variant="outline" disabled={busy === "verify"} onClick={() => run("verify", async () => { const r = await adminApi<{ ok: boolean; tables: number }>("/api/admin/backups/verify", { method: "POST" }); toast[r.ok ? "success" : "error"](r.ok ? `Backup OK: decrypts, ${r.tables} tables, dump complete` : "Backup check failed"); })}>{busy === "verify" ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Verify latest</Button>}
                      {me?.user.role === "owner" && b.items[0] && <Button size="xs" variant="outline" onClick={() => adminDownload("/api/admin/backups/latest/download", b.items[0].name).catch((e) => toast.error(errMsg(e)))}><Download /> Download latest</Button>}
                    </div>
                    <ul className="divide-y text-xs">{b.runs.slice(0, 5).map((r, i) => <li key={i} className="flex gap-2 py-1"><Pill tone={r.status === "ok" ? "green" : r.status === "failed" ? "red" : "gray"}>{r.status}</Pill><span>{fmtDate(r.started_at)}</span><span className="truncate text-muted-foreground">{r.detail}</span></li>)}</ul>
                    <p className="text-xs text-muted-foreground">Restore steps: docs/RESTORE.md. The passphrase must also be stored off the server.</p>
                  </div>
                )}
              </Section>
            )}
          </div>
        </div>
      )}
      <FormDialog open={!!restart} onOpenChange={(o) => !o && setRestart(null)} title={`Restart ${restart}`} destructive submitLabel="Restart"
        description={restart === "voice-api" ? "Waiting jobs are lost (users see “interrupted, generate again”) and the engine reloads (~20 s). Asks you to confirm it's you." : "Asks you to confirm it's you."}
        disabled={reason.trim().length < 3}
        onSubmit={async () => { const r = await adminApi<{ message: string }>(`/api/admin/system/processes/${restart}/restart`, { json: { reason } }); toast.success(r.message); setTimeout(load, 8000); }}>
        <Field label="Reason (audit log)" htmlFor="rs-reason"><Input id="rs-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </FormDialog>
    </AdminShell>
  );
}
