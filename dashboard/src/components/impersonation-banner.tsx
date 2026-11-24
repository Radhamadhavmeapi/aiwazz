import { Eye } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Shown on every page while a staff member views the app as this user (read-only, time-limited, audited). */
export function ImpersonationBanner() {
  const { user } = useAuth();
  const imp = user?.impersonation;
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!imp) return;
    const tick = () => {
      const s = Math.max(0, Math.round((new Date(imp.until).getTime() - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) window.location.href = "/admin/users";
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [imp]);
  if (!imp) return null;
  const stop = async () => {
    const r = await api<{ redirect?: string }>("/api/admin/impersonate/stop", { method: "POST" }).catch(() => ({ redirect: "/admin/users" }));
    window.location.href = r.redirect ?? "/admin/users";
  };
  return (
    <div role="status" className="sticky top-0 z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-warning px-3 py-2 text-center text-sm font-medium text-black">
      <Eye className="size-4" aria-hidden="true" />
      <span>Read-only view as <strong>{user?.email}</strong> (staff: {imp.by}) · ends in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span>
      <button type="button" onClick={stop} className="rounded-md bg-black/85 px-2.5 py-0.5 text-xs font-semibold text-white hover:bg-black">Stop viewing</button>
    </div>
  );
}
