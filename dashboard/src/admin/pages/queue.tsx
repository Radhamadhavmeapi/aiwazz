import type { ColumnDef } from "@tanstack/react-table";
import { Pause, Play, RotateCcw, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useChartColors } from "../components/charts";
import { DataTable } from "../components/data-table";
import { FormDialog } from "../components/form-dialog";
import { ErrorState, Field, fmtDate, LoadingRows, PageHeader, Pill, Section, Stat } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";

type J = { id: string; where: string; status: string; stage: string | null; progress: number; user_id: number | null; email: string; chars: number; voice: string; waiting_sec: number; position: number | null };
type Q = { running: J[]; waiting: J[]; paused: boolean; maintenance: boolean; message: string; engine_ready: boolean; max_queue: number;
  throughput: { hour: string; done: number; error: number }[]; rtf_7d: number | null };
type Fail = { id: string; user_id: number; email: string; voice: string; chars: number; error: string | null; created_at: string; retryable: boolean };

function Throughput({ data }: { data: Q["throughput"] }) {
  const c = useChartColors();
  if (!data.length) return <p className="py-8 text-center text-xs text-muted-foreground">No jobs in the last 24 hours</p>;
  return (
    <figure aria-label="Jobs per hour, last 24 hours">
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis dataKey="hour" tickFormatter={(h: string) => h.slice(11, 13)} tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} width={32} />
          <Tooltip contentStyle={{ background: c.surface, border: `1px solid ${c.grid}`, borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="done" name="Done" stackId="a" fill={c.series[0]} radius={[0, 0, 0, 0]} maxBarSize={16} />
          <Bar dataKey="error" name="Failed" stackId="a" fill={c.series[3]} radius={[4, 4, 0, 0]} maxBarSize={16} />
        </BarChart>
      </ResponsiveContainer>
      <figcaption className="mt-1 flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: c.series[0] }} /> Done</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: c.series[3] }} /> Failed</span>
      </figcaption>
    </figure>
  );
}

export default function QueuePage() {
  const { can } = useAdmin();
  const [q, setQ] = useState<Q | null>(null);
  const [error, setError] = useState("");
  const [ops, setOps] = useState(false);
  const [form, setForm] = useState({ queue_paused: false, maintenance: false, message: "" });
  const [reload, setReload] = useState(0);
  const load = useCallback(() => adminApi<Q>("/api/admin/queue").then((d) => (setQ(d), setError("")), (e) => setError(errMsg(e))), []);
  useEffect(() => {
    void load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);
  const failCols: ColumnDef<Fail, unknown>[] = [
    { id: "created_at", header: "When", meta: { sortKey: "created_at" }, cell: ({ row }) => <span className="text-xs whitespace-nowrap">{fmtDate(row.original.created_at)}</span> },
    { id: "user", header: "User", cell: ({ row }) => <Link to={`/admin/users/${row.original.user_id}`} className="text-xs hover:underline">{row.original.email}</Link> },
    { id: "voice", header: "Voice", cell: ({ row }) => <span className="font-mono text-xs">{row.original.voice}</span> },
    { id: "chars", header: "Chars", cell: ({ row }) => <span className="tabular">{row.original.chars}</span> },
    { id: "error", header: "Error", cell: ({ row }) => <span className="text-xs text-danger">{row.original.error}</span> },
    { id: "retry", header: "", cell: ({ row: { original: f } }) => can("queue.write") && f.retryable ? (
      <Button size="xs" variant="outline" onClick={async () => {
        try { await adminApi(`/api/admin/queue/${f.id}/retry`, { method: "POST" }); toast.success("Queued again"); setReload((n) => n + 1); load(); } catch (e) { toast.error(errMsg(e)); }
      }}><RotateCcw /> Retry</Button>
    ) : !f.retryable ? <span className="text-[11px] text-muted-foreground" title="Scripts aren't stored; after a restart the user generates again">not retryable</span> : null },
  ];
  const fmtWait = (s: number) => (s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);
  return (
    <AdminShell title="Queue & jobs">
      <PageHeader title="Queue & jobs" description="Live queue (refreshes every 3 s). Cancelling a waiting job frees its reserved characters; nothing is charged."
        actions={can("maintenance.write") && <Button size="sm" variant="outline" onClick={() => (q && setForm({ queue_paused: q.paused, maintenance: q.maintenance, message: q.message }), setOps(true))}><Wrench /> Pause / maintenance</Button>} />
      {error && <ErrorState message={error} onRetry={load} />}
      {!q ? <LoadingRows rows={6} /> : (
        <div className="space-y-4">
          {(q.paused || q.maintenance) && (
            <div role="status" className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
              {q.maintenance ? <>Maintenance mode is on: new jobs are refused. {q.message && `Banner: “${q.message}”`}</> : "The queue is paused: new jobs wait until you resume."}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Engine" value={q.engine_ready ? "Ready" : "Loading"} />
            <Stat label="Running" value={q.running.length} />
            <Stat label="Waiting" value={q.waiting.length} sub={`max ${q.max_queue}`} />
            <Stat label="Real-time factor (7d)" value={q.rtf_7d == null ? "–" : `${q.rtf_7d}×`} sub="compute ÷ audio (lower is faster)" />
          </div>
          <Section title="Now">
            {!q.running.length && !q.waiting.length ? <p className="py-4 text-center text-sm text-muted-foreground">The queue is empty.</p> : (
              <ul className="divide-y">
                {[...q.running, ...q.waiting].map((j) => (
                  <li key={j.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                    <Pill tone={j.where === "running" || j.where === "studio" ? "green" : "gray"}>{j.where === "queue" ? `#${j.position}` : j.where}</Pill>
                    <span className="min-w-0 flex-1 truncate">{j.user_id ? <Link to={`/admin/users/${j.user_id}`} className="hover:underline">{j.email}</Link> : j.email}
                      <span className="ml-2 font-mono text-xs text-muted-foreground">{j.voice} · {j.chars} chars</span></span>
                    {(j.where === "running" || j.where === "studio") && (
                      <span className="flex w-32 items-center gap-2"><span className="h-1.5 flex-1 rounded-full bg-surface-2"><span className="block h-full rounded-full bg-brand-gradient" style={{ width: `${Math.round(j.progress * 100)}%` }} /></span><span className="text-xs tabular">{Math.round(j.progress * 100)}%</span></span>
                    )}
                    <span className="text-xs text-muted-foreground tabular">{fmtWait(j.waiting_sec)}</span>
                    {j.where === "queue" && can("queue.write") && (
                      <Button size="xs" variant="ghost" onClick={async () => {
                        try { await adminApi(`/api/admin/queue/${j.id}/cancel`, { method: "POST" }); toast.success("Cancelled"); load(); } catch (e) { toast.error(errMsg(e)); }
                      }}><X /> Cancel</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Throughput" description="Jobs per hour, last 24 hours (IST)"><Throughput data={q.throughput} /></Section>
          <div>
            <h2 className="mb-2 text-sm font-semibold">Failed jobs</h2>
            <DataTable<Fail> id="failed-jobs" endpoint="/api/admin/queue/failures" columns={failCols} reloadKey={reload} searchPlaceholder={null} emptyTitle="No failed jobs" exportName="failed-jobs" />
          </div>
        </div>
      )}
      <FormDialog open={ops} onOpenChange={setOps} title="Pause queue / maintenance" submitLabel="Apply"
        description="Both show a banner to users. Pause: jobs wait and start when you resume. Maintenance: new jobs are refused (running ones finish). Asks you to confirm it's you."
        onSubmit={async () => { await adminApi("/api/admin/queue/ops", { method: "PUT", json: form }); toast.success("Applied"); load(); }}>
        <label className="flex items-center gap-2 text-sm"><Switch checked={form.queue_paused} onCheckedChange={(v) => setForm({ ...form, queue_paused: v })} aria-label="Pause queue" />{form.queue_paused ? <Pause className="size-4" /> : <Play className="size-4" />} Pause the queue</label>
        <label className="flex items-center gap-2 text-sm"><Switch checked={form.maintenance} onCheckedChange={(v) => setForm({ ...form, maintenance: v })} aria-label="Maintenance mode" /><Wrench className="size-4" /> Maintenance mode</label>
        <Field label="Banner text (optional)" htmlFor="ops-msg"><Input id="ops-msg" value={form.message} maxLength={300} onChange={(e) => setForm({ ...form, message: e.target.value })} placeholder="Back at 10:30 IST, thanks for waiting!" /></Field>
      </FormDialog>
    </AdminShell>
  );
}
