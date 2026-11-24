import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Select } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg, qs } from "../lib/admin-api";

type Entry = { time: string; level: string; message: string; source: string };
const tone = (l: string) => (l === "ERROR" || l === "CRITICAL" ? "text-danger" : l === "WARNING" ? "text-warning" : "text-muted-foreground");

export default function LogsPage() {
  const [level, setLevel] = useState("WARNING");
  const [q, setQ] = useState("");
  const [rid, setRid] = useState("");
  const [access, setAccess] = useState(false);
  const [items, setItems] = useState<Entry[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    adminApi<{ items: Entry[] }>(`/api/admin/logs${qs({ level, q, request_id: rid, access: access || undefined, limit: 500 })}`).then((r) => setItems(r.items), (e) => setError(errMsg(e)));
  }, [level, q, rid, access]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  return (
    <AdminShell title="Logs">
      <PageHeader title="Logs" description="voice-api log (newest first). Secrets (API keys, Razorpay ids, passwords, tokens) are redacted. Every response carries an X-Request-ID you can search for."
        actions={<Button size="sm" variant="outline" onClick={load}><RefreshCw /> Refresh</Button>} />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select aria-label="Level" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">All levels</option><option value="INFO">Info and up</option><option value="WARNING">Warnings and errors</option><option value="ERROR">Errors only</option>
        </Select>
        <Input aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search text…" className="h-9 w-56" />
        <Input aria-label="Request ID" value={rid} onChange={(e) => setRid(e.target.value.trim())} placeholder="Request ID" className="h-9 w-40 font-mono" />
        <label className="flex items-center gap-2 text-sm"><Switch checked={access} onCheckedChange={setAccess} aria-label="Include access log" /> Access log</label>
      </div>
      <div className="rounded-xl border bg-surface shadow-sm">
        {error ? <ErrorState message={error} onRetry={load} /> : !items ? <LoadingRows /> : !items.length ? <EmptyState title="No matching log lines" hint="Try a lower level or clear the search." /> : (
          <ol className="divide-y font-mono text-xs">
            {items.map((e, i) => (
              <li key={i} className="grid gap-1 p-2.5 sm:grid-cols-[150px_64px_1fr]">
                <time className="text-muted-foreground tabular">{new Date(e.time).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
                <span className={cn("font-semibold", tone(e.level))}>{e.level}</span>
                <pre className="overflow-x-auto break-words whitespace-pre-wrap">{e.message}</pre>
              </li>
            ))}
          </ol>
        )}
      </div>
    </AdminShell>
  );
}
