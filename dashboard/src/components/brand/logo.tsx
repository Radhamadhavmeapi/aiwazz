import { useId } from "react";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-7 shrink-0", className)}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8b5cf6" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" className="fill-surface-2" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" fill="none" stroke="var(--border-strong)" />
      <g fill={`url(#${id})`}>
        <rect x="7" y="12" width="3" height="8" rx="1.5" />
        <rect x="12" y="8" width="3" height="16" rx="1.5" />
        <rect x="17" y="5" width="3" height="22" rx="1.5" />
        <rect x="22" y="10" width="3" height="12" rx="1.5" />
      </g>
    </svg>
  );
}

export function Logo({ className, collapsed = false }: { className?: string; collapsed?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      {!collapsed && (
        <span className="text-[15px] font-semibold tracking-[-0.02em]">
          AiWazz <span className="text-muted-foreground font-medium">Voice</span>
        </span>
      )}
    </span>
  );
}
