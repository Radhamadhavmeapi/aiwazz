import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-heading text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, description, actions, children, className }: {
  title?: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={cn("rounded-xl border bg-surface p-4 shadow-sm sm:p-5", className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, hint, icon: Icon = Inbox, action }: { title: string; hint?: ReactNode; icon?: typeof Inbox; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center">
      <div className="grid size-10 place-items-center rounded-full bg-surface-2 text-muted-foreground">
        <Icon className="size-5" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-xs text-muted-foreground">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <AlertTriangle className="size-5 text-warning" aria-hidden="true" />
      <p className="text-sm">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw /> Try again
        </Button>
      )}
    </div>
  );
}

export function LoadingRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function Stat({ label, value, sub, trend, className }: {
  label: string; value: ReactNode; sub?: ReactNode; trend?: number | null; className?: string;
}) {
  const t = trend == null || !isFinite(trend) ? null : trend;
  return (
    <div className={cn("rounded-xl border bg-surface p-4 shadow-sm", className)}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1.5 font-heading text-2xl font-semibold tracking-tight tabular">{value}</p>
      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
        {t !== null && (
          <span className={cn("font-medium tabular", t > 0 ? "text-success" : t < 0 ? "text-danger" : "")}>
            {t > 0 ? "▲" : t < 0 ? "▼" : "•"} {Math.abs(t).toFixed(t !== 0 && Math.abs(t) < 10 ? 1 : 0)}%
          </span>
        )}
        {sub}
      </div>
    </div>
  );
}

const TONES: Record<string, string> = {
  green: "bg-success/12 text-success border-success/25",
  amber: "bg-warning/12 text-warning border-warning/30",
  red: "bg-danger/10 text-danger border-danger/25",
  blue: "bg-brand-indigo/10 text-brand border-brand-indigo/25",
  gray: "bg-surface-2 text-muted-foreground border-border",
};

export function Pill({ tone = "gray", children, className }: { tone?: keyof typeof TONES | string; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap", TONES[tone] ?? TONES.gray, className)}>
      {children}
    </span>
  );
}

/** Native select with the app's input styling (accessible, works well on phones). */
export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-9 rounded-lg border border-input bg-surface px-2.5 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
        className,
      )}
    />
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export const fmtDate = (iso: string | null | undefined, withTime = true) =>
  !iso
    ? "–"
    : new Date(iso).toLocaleString("en-IN", {
        day: "numeric", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
        timeZone: "Asia/Kolkata",
      });

export const inr = (paise: number | null | undefined, decimals = 0) =>
  paise == null ? "–" : `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals === 0 ? 0 : 2 })}`;

export const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("en-IN"));
