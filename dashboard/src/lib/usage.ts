import { useEffect, useState } from "react";
import { api } from "./api";
import { PREVIEW } from "./env";

export type Usage = {
  plan: string;
  plan_name: string;
  /** End of a time-limited plan (ISO, UTC); null for open-ended plans. */
  plan_until: string | null;
  unlimited: boolean;
  allowance: number | null;
  used: number;
  reserved: number;
  remaining: number | null;
  period_start: string;
  period_end: string;
  api_access: boolean;
};

const listeners = new Set<() => void>();
/** Call after a generation finishes so usage displays refresh. */
export const refreshUsage = () => listeners.forEach((f) => f());

export function useUsage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  useEffect(() => {
    if (PREVIEW) return;
    const load = () => void api<Usage>("/api/usage").then(setUsage, () => undefined);
    load();
    listeners.add(load);
    return () => void listeners.delete(load);
  }, []);
  return usage;
}

export const fmtChars = (n: number) => n.toLocaleString("en-IN");
