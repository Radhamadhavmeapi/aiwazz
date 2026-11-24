import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CategoryBars, TimeChart, useChartColors } from "../components/charts";
import { ErrorState, inr, LoadingRows, num, PageHeader, Section, Stat } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";

type Pt = { date: string; value: number };
type Item = { id: string; name: string; value: number };
type A = {
  range: { start: string; end: string };
  totals: Record<string, number>; previous: Record<string, number> | null;
  series: Record<string, Pt[]>; funnel: { step: string; value: number }[];
  popularity: { voices: Item[]; styles: Item[]; languages: Item[] };
  hinglish_pct: number | null; avg_script_chars: number | null; api_vs_web: { api: number; web: number }; rtf: number | null;
  chars_by_plan: Item[]; revenue_by_plan: Item[]; revenue_by_state: Item[];
  top_users: { user_id: number; email: string; chars: number; generations: number }[];
  cohorts: { week: string; size: number; retention: (number | null)[] }[]; visits_note: string;
};

const ist = (offsetDays = 0) => new Date(Date.now() + 5.5 * 3600_000 - offsetDays * 86400_000).toISOString().slice(0, 10);
const trend = (a: A, k: string) => (a.previous ? (a.previous[k] ? ((a.totals[k] - a.previous[k]) / a.previous[k]) * 100 : a.totals[k] ? 100 : null) : null);

function Funnel({ steps }: { steps: A["funnel"] }) {
  const c = useChartColors();
  const top = Math.max(1, steps[0]?.value || 0, ...steps.map((s) => s.value));
  return (
    <ol className="space-y-3">
      {steps.map((s, i) => {
        const prev = i > 0 ? steps[i - 1].value : null;
        return (
          <li key={s.step} className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm">
            <span className="text-xs text-muted-foreground">{s.step}</span>
            <span className="h-6 rounded-md bg-surface-2"><span className="block h-full rounded-md" style={{ width: `${Math.max(2, (s.value / top) * 100)}%`, background: c.series[0] }} /></span>
            <span className="w-28 text-right tabular"><span className="font-medium">{num(s.value)}</span>
              {prev ? <span className="ml-1 text-xs text-muted-foreground">{Math.round((s.value / prev) * 100)}%</span> : null}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Cohorts({ rows }: { rows: A["cohorts"] }) {
  const width = Math.max(...rows.map((r) => r.retention.length), 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <caption className="sr-only">Weekly retention: share of each signup cohort that made a voiceover in week N</caption>
        <thead><tr className="text-left text-muted-foreground"><th className="py-1 pr-2 font-medium">Signup week</th><th className="pr-2 font-medium">Users</th>
          {Array.from({ length: width }, (_, i) => <th key={i} className="px-1 text-center font-medium">W{i}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.week}>
              <td className="py-1 pr-2 whitespace-nowrap">{new Date(`${r.week}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</td>
              <td className="pr-2 tabular">{r.size}</td>
              {Array.from({ length: width }, (_, i) => {
                const v = r.retention[i];
                return (
                  <td key={i} className="p-0.5">
                    {v == null || !r.size ? <span className="block h-7" /> : (
                      <span className="grid h-7 place-items-center rounded tabular"
                        style={{ background: `color-mix(in oklab, var(--primary) ${Math.round(6 + v * 0.54)}%, transparent)`, color: "var(--foreground)" }}>{v}%</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalyticsPage() {
  const [start, setStart] = useState(ist(29));
  const [end, setEnd] = useState(ist(0));
  const [compare, setCompare] = useState(true);
  const [a, setA] = useState<A | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    adminApi<A>(`/api/admin/analytics?start=${start}&end=${end}&compare=${compare}`).then(setA, (e) => setError(errMsg(e)));
  }, [start, end, compare]);
  useEffect(load, [load]);
  const preset = (days: number) => (setStart(ist(days - 1)), setEnd(ist(0)));
  return (
    <AdminShell title="Analytics">
      <PageHeader title="Analytics" description="From the nightly metrics_daily aggregation plus live numbers for today. No third-party trackers: visits come from the server's own access log." />
      <div className="mb-4 flex flex-wrap items-end gap-2">
        {[7, 30, 90].map((d) => <Button key={d} size="sm" variant="outline" onClick={() => preset(d)}>Last {d} days</Button>)}
        <label className="text-xs">From <Input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} className="mt-1 h-9 w-40" /></label>
        <label className="text-xs">To <Input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className="mt-1 h-9 w-40" /></label>
        <label className="flex h-9 items-center gap-2 text-sm"><Switch checked={compare} onCheckedChange={setCompare} aria-label="Compare with the previous period" /> Compare with previous period</label>
      </div>
      {error ? <ErrorState message={error} onRetry={load} /> : !a ? <LoadingRows rows={8} /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Visitors" value={num(a.totals.visitors)} trend={trend(a, "visitors")} sub={`${num(a.totals.page_views)} page views`} />
            <Stat label="Signups" value={num(a.totals.signups)} trend={trend(a, "signups")} />
            <Stat label="Voiceovers" value={num(a.totals.generations_done)} trend={trend(a, "generations_done")} sub={`${num(a.totals.active_users)} user-days active`} />
            <Stat label="Characters" value={num(a.totals.chars)} trend={trend(a, "chars")} />
            <Stat label="Revenue" value={inr(a.totals.revenue_paise)} trend={trend(a, "revenue_paise")} sub={a.totals.refunds_paise ? `−${inr(a.totals.refunds_paise)} refunds` : "incl. GST"} />
            <Stat label="Hinglish toggle" value={a.hinglish_pct == null ? "–" : `${a.hinglish_pct}%`} sub={`avg script ${a.avg_script_chars ?? "–"} chars`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <Section title="Funnel" description="Landing visit → signup → first voiceover → first payment (within the range)."><Funnel steps={a.funnel} /><p className="mt-3 text-xs text-muted-foreground">{a.visits_note}</p></Section>
            <Section title="Signups per day"><TimeChart data={a.series.signups} label="Signups" /></Section>
            <Section title="Voiceovers per day"><TimeChart data={a.series.generations_done} kind="bar" label="Voiceovers" /></Section>
            <Section title="Revenue per day" description="Captured payments, incl. GST"><TimeChart data={a.series.revenue_paise} kind="bar" label="Revenue" fmt={(n) => inr(n)} minMax={100000} /></Section>
          </div>
          <Section title="Weekly cohort retention" description="Share of each week's new users who made at least one voiceover in week 0, 1, 2… after signing up (staff excluded)."><Cohorts rows={a.cohorts} /></Section>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <Section title="Voices"><CategoryBars data={a.popularity.voices.map((v) => ({ plan: v.name.split(" (")[0], value: v.value }))} label="Voice popularity" /></Section>
            <Section title="Styles"><CategoryBars data={a.popularity.styles.map((v) => ({ plan: v.name, value: v.value }))} label="Style popularity" /></Section>
            <Section title="Languages & channel">
              <CategoryBars data={a.popularity.languages.map((v) => ({ plan: v.name, value: v.value }))} label="Languages" />
              <p className="mt-4 text-xs text-muted-foreground">API {num(a.api_vs_web.api)} · web {num(a.api_vs_web.web)}{a.rtf ? ` · real-time factor ${a.rtf}×` : ""}</p>
            </Section>
            <Section title="Characters by plan"><CategoryBars data={a.chars_by_plan.map((v) => ({ plan: v.name, value: v.value }))} label="Characters by plan" /></Section>
            <Section title="Revenue by plan"><CategoryBars data={a.revenue_by_plan.map((v) => ({ plan: v.name, value: v.value }))} label="Revenue by plan" fmt={(n) => inr(n)} /></Section>
            <Section title="Taxable revenue by state" description="Place of supply (GST)">
              {!a.revenue_by_state.length ? <p className="text-sm text-muted-foreground">No paid invoices in this range.</p> : (
                <ul className="divide-y text-sm">{a.revenue_by_state.map((s) => <li key={s.id} className="flex justify-between py-1.5"><span>{s.name} ({s.id})</span><span className="tabular">{inr(s.value, 2)}</span></li>)}</ul>
              )}
            </Section>
          </div>
          <Section title="Top users by characters">
            {!a.top_users.length ? <p className="text-sm text-muted-foreground">No usage in this range.</p> : (
              <table className="w-full text-sm"><thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">User</th><th className="text-right">Characters</th><th className="text-right">Voiceovers</th></tr></thead>
                <tbody>{a.top_users.map((u) => <tr key={u.user_id} className="border-b last:border-0"><td className="py-1.5">{u.email.startsWith("user #") ? u.email : <Link to={`/admin/users/${u.user_id}`} className="hover:underline">{u.email}</Link>}</td>
                  <td className="text-right tabular">{num(u.chars)}</td><td className="text-right tabular">{u.generations}</td></tr>)}</tbody></table>
            )}
          </Section>
        </div>
      )}
    </AdminShell>
  );
}
