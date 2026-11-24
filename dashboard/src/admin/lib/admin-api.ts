// Admin API client. Wraps api() with the admin panel's two server signals:
//   401 + X-Admin-Lock: setup|verify  → the panel locks (2FA setup / code needed)
//   403 + X-Step-Up: required         → ask for password + 2FA code, then retry the same request once
import { api, ApiError, csrfToken, messageFrom } from "@/lib/api";

type Init = { method?: string; json?: unknown };
type LockReason = "setup" | "verify";

let onLock: ((r: LockReason) => void) | null = null;
let askStepUp: (() => Promise<boolean>) | null = null;
export const setLockHandler = (fn: typeof onLock) => void (onLock = fn);
export const setStepUpHandler = (fn: typeof askStepUp) => void (askStepUp = fn);

function signal(e: unknown): "lock" | "stepup" | null {
  if (!(e instanceof ApiError) || !e.headers) return null;
  if (e.status === 401 && e.headers.get("x-admin-lock")) {
    onLock?.(e.headers.get("x-admin-lock") as LockReason);
    return "lock";
  }
  if (e.status === 403 && e.headers.get("x-step-up")) return "stepup";
  return null;
}

export async function adminApi<T = unknown>(path: string, init: Init = {}): Promise<T> {
  try {
    return await api<T>(path, init);
  } catch (e) {
    if (signal(e) === "stepup" && askStepUp && (await askStepUp())) return api<T>(path, init);
    throw e;
  }
}

/** Download a server-generated file (CSV export, PDF) with the same lock/step-up handling. */
export async function adminDownload(path: string, fallbackName: string, init: Init = {}): Promise<void> {
  const go = async () => {
    const method = init.method ?? "GET";
    const headers: Record<string, string> = {};
    if (method !== "GET") headers["X-CSRF-Token"] = await csrfToken();
    if (init.json !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { method, headers, credentials: "same-origin", body: init.json !== undefined ? JSON.stringify(init.json) : undefined });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new ApiError(res.status, messageFrom(body, res.status), undefined, res.headers);
    }
    const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };
  try {
    await go();
  } catch (e) {
    if (signal(e) === "stepup" && askStepUp && (await askStepUp())) return go();
    throw e;
  }
}

export const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}
