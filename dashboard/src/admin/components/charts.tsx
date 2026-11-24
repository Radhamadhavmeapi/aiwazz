// Admin charts (Recharts, loaded only in the admin bundle). Palette validated with the dataviz validator
// (light on #fff, dark on #0e0f14): categorical order indigo · teal · violet · rose, single series = indigo.
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTheme } from "@/lib/theme";

const LIGHT = ["#2D36DB", "#0A9180", "#7420DD", "#C2387F"];
const DARK = ["#5B63F2", "#139C8B", "#9A62EE", "#C9548E"];

export function useChartColors() {
  const { theme } = useTheme();
  const dark = theme === "dark";
  return {
    series: dark ? DARK : LIGHT,
    grid: dark ? "#1f2230" : "#e8ecf4",
    axis: dark ? "#94a3b8" : "#475569",
    surface: dark ? "#0e0f14" : "#ffffff",
  };
}

type Point = { date: string; value: number };
const shortDate = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function Tip({ active, payload, label, fmt }: { active?: boolean; payload?: { value: number; payload: Record<string, unknown> }[]; label?: string; fmt: (n: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-surface px-2.5 py-1.5 text-xs shadow-md">
      <p className="text-muted-foreground">{label && /^\d{4}-\d{2}-\d{2}$/.test(label) ? shortDate(label) : label}</p>
      <p className="font-medium tabular">{fmt(payload[0].value)}</p>
    </div>
  );
}

export function TimeChart({ data, kind = "area", fmt = (n) => n.toLocaleString("en-IN"), height = 180, label }: {
  data: Point[]; kind?: "area" | "bar"; fmt?: (n: number) => string; height?: number; label: string;
}) {
  const c = useChartColors();
  const total = data.reduce((a, b) => a + b.value, 0);
  const common = (
    <>
      <CartesianGrid vertical={false} stroke={c.grid} />
      <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={28} />
      <YAxis tick={{ fill: c.axis, fontSize: 11 }} axisLine={false} tickLine={false} width={44} allowDecimals={false} tickFormatter={(v) => fmt(v)} />
      <Tooltip content={<Tip fmt={fmt} />} cursor={kind === "bar" ? { fill: c.grid } : { stroke: c.axis, strokeDasharray: "3 3" }} />
    </>
  );
  return (
    <figure aria-label={`${label}: ${fmt(total)} over ${data.length} days`}>
      <ResponsiveContainer width="100%" height={height}>
        {kind === "bar" ? (
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            {common}
            <Bar dataKey="value" fill={c.series[0]} radius={[4, 4, 0, 0]} maxBarSize={18} />
          </BarChart>
        ) : (
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            {common}
            <Area type="monotone" dataKey="value" stroke={c.series[0]} strokeWidth={2} fill={c.series[0]} fillOpacity={0.12}
              activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }} />
          </AreaChart>
        )}
      </ResponsiveContainer>
      <figcaption className="sr-only">{data.map((d) => `${d.date}: ${fmt(d.value)}`).join(", ")}</figcaption>
    </figure>
  );
}

/** Horizontal bars, one series, labelled categories (e.g. characters by plan). */
export function CategoryBars({ data, fmt = (n) => n.toLocaleString("en-IN"), label }: {
  data: { plan: string; value: number }[]; fmt?: (n: number) => string; label: string;
}) {
  const c = useChartColors();
  const max = Math.max(1, ...data.map((d) => d.value));
  if (!data.length) return <p className="py-8 text-center text-xs text-muted-foreground">No data yet</p>;
  return (
    <ul className="space-y-2.5" aria-label={label}>
      {data.map((d) => (
        <li key={d.plan} className="grid grid-cols-[80px_1fr_auto] items-center gap-3 text-xs">
          <span className="text-muted-foreground">{d.plan}</span>
          <span className="h-2.5 rounded-full bg-surface-2">
            <span className="block h-full rounded-full" style={{ width: `${(d.value / max) * 100}%`, background: c.series[0] }} />
          </span>
          <span className="font-medium tabular">{fmt(d.value)}</span>
        </li>
      ))}
    </ul>
  );
}

const PLAN_ORDER = ["Free", "Starter", "Creator", "Pro"];

/** Plan mix donut: colour follows the plan (fixed order), legend + direct values, never colour alone. */
export function PlanDonut({ data }: { data: { plan: string; value: number }[] }) {
  const c = useChartColors();
  const total = data.reduce((a, b) => a + b.value, 0);
  const color = (plan: string) => c.series[Math.max(0, PLAN_ORDER.indexOf(plan)) % 4];
  if (!total) return <p className="py-8 text-center text-xs text-muted-foreground">No customers yet</p>;
  return (
    <div className="flex items-center gap-4">
      <div className="size-32 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="plan" innerRadius="62%" outerRadius="100%" stroke={c.surface} strokeWidth={2} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.plan} fill={color(d.plan)} />)}
            </Pie>
            <Tooltip content={<Tip fmt={(n) => `${n} users`} />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-1.5 text-xs" aria-label="Plan mix">
        {[...data].sort((a, b) => PLAN_ORDER.indexOf(a.plan) - PLAN_ORDER.indexOf(b.plan)).map((d) => (
          <li key={d.plan} className="flex items-center gap-2">
            <span className="size-2.5 rounded-sm" style={{ background: color(d.plan) }} aria-hidden="true" />
            <span className="w-14">{d.plan}</span>
            <span className="font-medium tabular">{d.value}</span>
            <span className="text-muted-foreground tabular">{Math.round((d.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
