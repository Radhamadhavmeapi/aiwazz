import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { setLockHandler } from "./admin-api";

export type AdminMe = {
  user: { id: number; email: string; role: string; name: string };
  perms: string[];
  mfa: { enrolled: boolean; unlocked: boolean; backup_codes_left: number; configured: boolean };
  stepup_until: string | null;
  idle_minutes: number;
  stepup_minutes: number;
  payments_env: "OFF" | "TEST" | "LIVE";
};
type State = { status: "loading" } | { status: "notfound" } | { status: "error" } | { status: "ok"; me: AdminMe };
type Ctx = { state: State; me: AdminMe | null; refresh: () => Promise<void>; can: (perm: string) => boolean };

const AdminContext = createContext<Ctx | null>(null);

export function AdminProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const refresh = useCallback(async () => {
    try {
      setState({ status: "ok", me: await api<AdminMe>("/api/admin/me") });
    } catch (e) {
      setState(e instanceof ApiError && e.status === 404 ? { status: "notfound" } : { status: "error" });
    }
  }, []);
  useEffect(() => void refresh(), [refresh]);
  // Any admin call that comes back "locked" (idle timeout, signed out elsewhere) re-checks the session → lock screen.
  useEffect(() => {
    setLockHandler(() => void refresh());
    return () => setLockHandler(null);
  }, [refresh]);
  const me = state.status === "ok" ? state.me : null;
  const can = useCallback((perm: string) => !!me?.perms.includes(perm), [me]);
  return <AdminContext.Provider value={{ state, me, refresh, can }}>{children}</AdminContext.Provider>;
}

export function useAdmin() {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin outside <AdminProvider>");
  return ctx;
}
