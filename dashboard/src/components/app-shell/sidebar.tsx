import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router";
import { BrandIcon, Logo } from "@/components/brand/logo";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { NAV } from "./nav";

export function SidebarNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon }) => {
        const link = (
          <NavLink
            key={to}
            to={`/${to}`}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "group relative flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm font-medium transition-colors duration-150",
                isActive
                  ? "bg-surface-2 text-foreground"
                  : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground",
                collapsed && "justify-center px-0",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-brand-gradient" />
                )}
                <Icon className={cn("size-[18px] shrink-0", isActive && "text-brand")} aria-hidden="true" />
                {collapsed ? <span className="sr-only">{label}</span> : label}
              </>
            )}
          </NavLink>
        );
        return collapsed ? (
          <Tooltip key={to}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">{label}</TooltipContent>
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r bg-surface/60 transition-[width] duration-200 ease-out md:flex",
        collapsed ? "w-[68px]" : "w-60",
      )}
    >
      <div className={cn("flex h-14 items-center px-4", collapsed && "justify-center px-0")}>
        {collapsed ? <BrandIcon size={32} /> : <Logo width={124} />}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <SidebarNav collapsed={collapsed} />
      </div>
      <div className={cn("border-t p-3", collapsed && "flex justify-center")}>
        {!collapsed && (
          <div className="mb-3 rounded-xl border bg-surface-2/60 p-3">
            <p className="text-xs font-medium">Personal plan</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Unlimited · CPU queue</p>
          </div>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className={cn(
            "flex h-8 items-center gap-2 rounded-lg px-2 text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground",
            collapsed ? "w-8 justify-center px-0" : "w-full",
          )}
        >
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          {!collapsed && (
            <>
              Collapse <kbd className="ml-auto font-mono text-[10px] text-subtle-foreground">⌘B</kbd>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
