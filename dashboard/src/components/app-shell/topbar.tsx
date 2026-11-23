import { CircleHelp, KeyRound, LogOut, Menu, Moon, Search, Settings, Sun, User } from "lucide-react";
import { useNavigate } from "react-router";
import { BrandIcon } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { fmtChars, useUsage } from "@/lib/usage";
import { useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label={label}>
          {theme === "dark" ? <Sun /> : <Moon />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function Topbar({ title, onMenu, onCommand }: { title: string; onMenu: () => void; onCommand: () => void }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const usage = useUsage();
  const low = usage && usage.remaining !== null && usage.allowance ? usage.remaining / usage.allowance < 0.1 : false;
  const initial = (user?.email[0] ?? "?").toUpperCase();
  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };
  return (
    <header className="glass sticky top-0 z-30 flex h-14 items-center gap-2 border-b px-3 sm:px-5">
      <Button variant="ghost" size="icon-sm" className="md:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu />
      </Button>
      <BrandIcon size={28} className="md:hidden" />
      <h1 className="ml-1 text-sm font-medium md:ml-0">{title}</h1>

      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={onCommand}
          className="hidden h-8 w-56 items-center gap-2 rounded-lg border bg-surface-2/70 px-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground lg:flex"
        >
          <Search className="size-3.5" />
          Search or jump to…
          <kbd className="ml-auto rounded border bg-surface px-1.5 font-mono text-[10px]">⌘K</kbd>
        </button>
        <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={onCommand} aria-label="Open command palette">
          <Search />
        </Button>

        <a
          href="/settings"
          className="hidden items-center gap-2 rounded-lg border px-2.5 py-1 transition-colors hover:bg-surface-2 sm:flex"
          title={usage ? `${usage.plan_name} plan · characters this month` : "Characters this month"}
        >
          <span className={`size-1.5 rounded-full ${low ? "bg-warning" : "bg-success"}`} aria-hidden="true" />
          <span className="font-mono text-xs tabular">
            {!usage ? (
              <span className="text-muted-foreground">…</span>
            ) : usage.unlimited ? (
              <>
                ∞ <span className="text-muted-foreground">characters</span>
              </>
            ) : (
              <>
                {fmtChars(usage.remaining ?? 0)} <span className="text-muted-foreground">characters left</span>
              </>
            )}
          </span>
        </a>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild variant="ghost" size="icon-sm">
              <a href="https://aiwazz.in/learn/" target="_blank" rel="noopener" aria-label="Help and guides">
                <CircleHelp />
              </a>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Help and guides</TooltipContent>
        </Tooltip>

        <ThemeToggle />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Account menu"
              className="ml-1 grid size-8 place-items-center rounded-full bg-brand-gradient-strong text-xs font-semibold text-white ring-2 ring-background transition-transform hover:scale-105"
            >
              {initial}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <p className="truncate text-sm font-medium">{user?.email}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/settings")}>
              <User /> Account
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("/api-keys")}>
              <KeyRound /> API keys
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("/settings")}>
              <Settings /> Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={signOut}>
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
