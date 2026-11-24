import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { timeAgo } from "@/lib/format";
import { CategoryBars, PlanDonut, TimeChart } from "../components/charts";
import { ErrorState, inr, LoadingRows, num, PageHeader, Pill, Section, Stat } from "../components/page";
import { AdminShell } from "../components/shell";
import { adminApi, errMsg } from "../lib/admin-api";

type Series = { date: string; value: number }[];
type Overview = {
  kpis: {
    mrr_paise: number; mrr_trend: number | null; arr_paise: number; paying: number; paying_trend: number | null;
    signups: { today: number; d7: number; d30: number }; signups_trend: number | null; total_users: number;
    free_to_paid_pct: number; trial_to_paid_pct: number | null; churn_logo_pct: number; churn_revenue_pct: number;
    arpu_paise: number; net_revenue_month_paise: number; net_revenue_trend: number | null; chars_today: number;
    chars_today_trend: number | null; chars_month: number; generations_today: number; generations_trend: number | null;
    avg_queue_wait_sec: number | null; failed_jobs_24h: number; failed_payments_7d: number;
  };
  charts: { revenue: Series; signups: Series; generations: Series; chars_by_plan: { plan: string; value: number }[]; plan_mix: { plan: string; value: number }[] };
  lists: {
    signups: { id: number; email: string; plan: string; created_at: string }[];
    payments: { id: number; rzp_payment_id: string; amount_paise: number; status: string; user_id: number | null; created_at: string }[];
    support: { id: number; subject: string; from: string; created_at: string; to: string }[];
    flagged: { id: number; rule: string; severity: string; user_id: number; created_at: string }[];
    alerts: { key: string; title: string; detail?: string; level: string }[];
  };
};

const pctStr = (n: number | null) => (n == null ? "n/a" : `${n.toFixed(n < 10 ? 1 : 0)}%`);
const compact = (n: number) => (n >= 100000 ? `${(n / 100000).toFixed(1)}L` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

function ListCard({ title, to, empty, children, count }: { title: string; to: string; empty: string; children: React.ReactNode; count: number }) {
  return (
    <Section title={title} actions={<Link to={to} className="text-xs font-medium text-brand hover:underline">View all</Link>}>
      {count ? <ul className="-my-1 divide-y">{children}</ul> : <p className="py-4 text-center text-xs text-muted-foreground">{empty}</p>}
    </Section>
  );
}

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    adminApi<Overview>("/api/admin/overview").then(setData, (e) => setError(errMsg(e)));
  }, []);
  useEffect(load, [load]);
  const k = data?.kpis;
  return (
    <AdminShell title="Overview">
      <PageHeader title="Overview" description="Live numbers. Trends compare with the previous period (30 days, last month or yesterday)."
        actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw /> Refresh</Button>} />
      {error ? <ErrorState message={error} onRetry={load} /> : !data || !k ? <LoadingRows rows={8} /> : (
        <div className="space-y-6">
          {data.lists.alerts.length > 0 && (
            <div role="alert" className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
              {data.lists.alerts.map((a) => <p key={a.key}><strong>{a.title}</strong>{a.detail ? ` · ${a.detail}` : ""}</p>)}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="MRR (excl. GST)" value={inr(k.mrr_paise)} trend={k.mrr_trend} sub="vs 30 days ago" />
            <Stat label="ARR" value={inr(k.arr_paise)} sub="MRR × 12" />
            <Stat label="Paying subscriptions" value={num(k.paying)} trend={k.paying_trend} />
            <Stat label="ARPU" value={inr(k.arpu_paise)} sub="per paying user / month" />
            <Stat label="Net revenue this month" value={inr(k.net_revenue_month_paise)} trend={k.net_revenue_trend} sub="after refunds, incl. GST" />
            <Stat label="Churn (30 days)" value={pctStr(k.churn_logo_pct)} sub={`revenue ${pctStr(k.churn_revenue_pct)}`} />
            <Stat label="New signups" value={num(k.signups.today)} sub={`today · ${k.signups.d7} in 7d · ${k.signups.d30} in 30d`} trend={k.signups_trend} />
            <Stat label="Free → paid" value={pctStr(k.free_to_paid_pct)} sub={`trial → paid ${pctStr(k.trial_to_paid_pct)}`} />
            <Stat label="Characters today" value={compact(k.chars_today)} trend={k.chars_today_trend} sub={`${compact(k.chars_month)} this month`} />
            <Stat label="Generations today" value={num(k.generations_today)} trend={k.generations_trend} sub="vs yesterday" />
            <Stat label="Avg queue wait (24h)" value={k.avg_queue_wait_sec == null ? "–" : `${k.avg_queue_wait_sec.toFixed(1)} s`} />
            <Stat label="Failures" value={<span className={k.failed_jobs_24h || k.failed_payments_7d ? "text-danger" : ""}>{k.failed_jobs_24h} / {k.failed_payments_7d}</span>} sub="jobs 24h / payments 7d" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Section title="Revenue" description="Captured payments per day (30 days, incl. GST)" className="lg:col-span-2">
              <TimeChart data={data.charts.revenue} kind="bar" label="Revenue" fmt={(n) => inr(n)} />
            </Section>
            <Section title="Plan mix" description="Customers by current plan">
              <PlanDonut data={data.charts.plan_mix} />
            </Section>
            <Section title="Signups" description="New accounts per day">
              <TimeChart data={data.charts.signups} label="Signups" />
            </Section>
            <Section title="Generations" description="Jobs per day">
              <TimeChart data={data.charts.generations} kind="bar" label="Generations" />
            </Section>
            <Section title="Characters by plan" description="This month, successful jobs">
              <CategoryBars data={data.charts.chars_by_plan} label="Characters by plan" fmt={compact} />
            </Section>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <ListCard title="Latest signups" to="/admin/users" empty="No signups yet" count={data.lists.signups.length}>
              {data.lists.signups.map((u) => (
                <li key={u.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <Link to={`/admin/users/${u.id}`} className="truncate hover:underline">{u.email}</Link>
                  <span className="shrink-0 text-xs text-muted-foreground">{timeAgo(u.created_at)}</span>
                </li>
              ))}
            </ListCard>
            <ListCard title="Latest payments" to="/admin/payments" empty="No payments yet" count={data.lists.payments.length}>
              {data.lists.payments.map((x) => (
                <li key={x.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="truncate font-mono text-xs">{x.rzp_payment_id}</span>
                  <span className="flex shrink-0 items-center gap-2"><span className="tabular">{inr(x.amount_paise)}</span>
                    <Pill tone={x.status === "captured" ? "green" : x.status === "failed" ? "red" : "gray"}>{x.status}</Pill></span>
                </li>
              ))}
            </ListCard>
            <ListCard title="Open support" to="/admin/support" empty="Inbox zero" count={data.lists.support.length}>
              {data.lists.support.map((m) => (
                <li key={m.id} className="py-2 text-sm">
                  <Link to={m.to} className="line-clamp-1 hover:underline">{m.subject}</Link>
                  <p className="truncate text-xs text-muted-foreground">{m.from} · {timeAgo(m.created_at)}</p>
                </li>
              ))}
            </ListCard>
            <ListCard title="Flagged content" to="/admin/moderation" empty="Nothing flagged" count={data.lists.flagged.length}>
              {data.lists.flagged.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="truncate">{f.rule}</span>
                  <Pill tone={f.severity === "high" ? "red" : "amber"}>{f.severity}</Pill>
                </li>
              ))}
            </ListCard>
          </div>
        </div>
      )}
    </AdminShell>
  );
}
