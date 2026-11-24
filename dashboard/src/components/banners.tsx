import { Info, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Banner = { id: string; level: "info" | "warning"; text: string; dismissible?: boolean };
const KEY = "aiwazz-dismissed-banners";

/** Maintenance / paused queue and announcements from the admin panel (GET /api/banners), refreshed every 2 min. */
export function Banners() {
  const [items, setItems] = useState<Banner[]>([]);
  const [dismissed, setDismissed] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; }
  });
  useEffect(() => {
    const load = () => fetch("/api/banners", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : { banners: [] }))
      .then((d) => setItems(d.banners ?? []), () => undefined);
    load();
    const t = setInterval(load, 120_000);
    return () => clearInterval(t);
  }, []);
  const show = items.filter((b) => !(b.dismissible && dismissed.includes(b.id)));
  if (!show.length) return null;
  return (
    <div className="space-y-px">
      {show.map((b) => (
        <div key={b.id} role="status" className={cn("flex items-start gap-2 px-4 py-2 text-sm sm:px-6",
          b.level === "warning" ? "bg-warning/15 text-foreground" : "bg-brand-indigo/8 text-foreground")}>
          {b.level === "warning" ? <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" /> : <Info className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />}
          <p className="flex-1">{b.text}</p>
          {b.dismissible && (
            <button type="button" aria-label="Dismiss" className="text-muted-foreground hover:text-foreground" onClick={() => {
              const next = [...dismissed, b.id];
              setDismissed(next);
              try { localStorage.setItem(KEY, JSON.stringify(next.slice(-50))); } catch { /* ignore */ }
            }}><X className="size-4" /></button>
          )}
        </div>
      ))}
    </div>
  );
}
