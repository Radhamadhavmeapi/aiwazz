import { ArrowRight, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import { AppShell } from "@/components/app-shell/app-shell";
import { NAV } from "@/components/app-shell/nav";
import { Button } from "@/components/ui/button";

/** Empty state for screens that are designed in a later step. */
export default function Placeholder({ page }: { page: string }) {
  const item = NAV.find((n) => n.to === page)!;
  const Icon: LucideIcon = item.icon;
  return (
    <AppShell title={item.label}>
      <div className="grid min-h-[60dvh] place-items-center p-6">
        <div className="max-w-sm text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl border bg-surface text-brand shadow-md">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <h2 className="mt-5 text-h3 font-semibold">{item.label} is coming next</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            This screen gets built once the design is approved. For now, try the Generate screen.
          </p>
          <Button asChild variant="outline" className="mt-6">
            <Link to="/generate">
              Go to Generate <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </AppShell>
  );
}
