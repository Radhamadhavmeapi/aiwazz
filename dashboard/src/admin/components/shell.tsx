import { Bell, Lock, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Search, ShieldCheck, SquareArrowOutUpRight } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";
import { ThemeToggle } from "@/components/app-shell/topbar";
import { BrandIcon, Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator,
} from "@/components/ui/command";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { adminApi } from "../lib/admin-api";
import { useAdmin } from "../lib/admin-context";
import { ADMIN_NAV, adminPath } from "../nav";

const KEY = "aiwazz-admin-sidebar";

function Nav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { can } = useAdmin();
  return (
    <nav aria-label="Admin" className="flex flex-col gap-4">
      {ADMIN_NAV.map((g) => {
        const items = g.items.filter((i) => can(i.perm));
        if (!items.length) return null;
        return (
          <div key={g.label}>
            {!collapsed && <p className="mb-1 px-2.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{g.label}</p>}
            <div className="flex flex-col gap-0.5">
              {items.map(({ to, label, icon: Icon }) => {
                const link = (
                  <NavLink key={to} to={adminPath(to)} end={to === ""} onClick={onNavigate}
                    className={({ isActive }) => cn(
                      "relative flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors duration-150",
                      isActive ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground",
                      collapsed && "justify-center px-0",
                    )}>
                    {({ isActive }) => (
                      <>
                        {isActive && <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-brand-gradient" />}
                        <Icon className={cn("size-4 shrink-0", isActive && "text-brand")} aria-hidden="true" />
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
                ) : link;
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

type Hit = { type: string; id: string; label: string; sub?: string; to: string };
type Note = { id: string; title: string; sub?: string; to: string; level: "info" | "warning" | "danger" };

function Palette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate();
  const { can } = useAdmin();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) return setHits([]);
    const t = setTimeout(() => {
      adminApi<{ items: Hit[] }>(`/api/admin/search?q=${encodeURIComponent(q.trim())}`).then((r) => setHits(r.items), () => setHits([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);
  const go = (to: string) => (onOpenChange(false), setQ(""), navigate(to));
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Admin search" description="Search users, payments, invoices or jump to a page">
      <CommandInput placeholder="Email, user ID, pay_…, sub_…, AWZ/… or a page" value={q} onValueChange={setQ} />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        {hits.length > 0 && (
          <>
            <CommandGroup heading="Results">
              {hits.map((h) => (
                <CommandItem key={`${h.type}-${h.id}`} value={`${q} ${h.type} ${h.label} ${h.id}`} onSelect={() => go(h.to)}>
                  <span className="w-20 shrink-0 text-xs text-muted-foreground capitalize">{h.type}</span>
                  <span className="truncate">{h.label}</span>
                  {h.sub && <span className="ml-auto truncate text-xs text-muted-foreground">{h.sub}</span>}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}
        <CommandGroup heading="Pages">
          {ADMIN_NAV.flatMap((g) => g.items).filter((i) => can(i.perm)).map(({ to, label, icon: Icon, keywords }) => (
            <CommandItem key={to} value={`${label} ${keywords ?? ""}`} onSelect={() => go(adminPath(to))}>
              <Icon /> {label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}

function Bell_() {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const navigate = useNavigate();
  const load = useCallback(() => {
    adminApi<{ items: Note[] }>("/api/admin/notifications").then((r) => setNotes(r.items), () => setNotes([]));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);
  const n = notes?.length ?? 0;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={n ? `${n} notifications` : "Notifications"} className="relative">
          <Bell />
          {n > 0 && <span className="absolute top-1 right-1 size-2 rounded-full bg-danger ring-2 ring-surface" aria-hidden="true" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {!notes ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">Loading…</p>
        ) : !n ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">All clear. Alerts, open messages and flags show up here.</p>
        ) : (
          notes.slice(0, 12).map((x) => (
            <DropdownMenuItem key={x.id} onSelect={() => navigate(x.to)} className="flex-col items-start gap-0.5">
              <span className={cn("text-sm font-medium", x.level === "danger" && "text-danger", x.level === "warning" && "text-warning")}>{x.title}</span>
              {x.sub && <span className="text-xs text-muted-foreground">{x.sub}</span>}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function EnvBadge({ env }: { env: "OFF" | "TEST" | "LIVE" }) {
  const label = env === "OFF" ? "Payments off" : env === "TEST" ? "TEST payments" : "LIVE payments";
  return (
    <span title="Razorpay mode" className={cn(
      "hidden items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium sm:inline-flex",
      env === "LIVE" ? "border-success/30 bg-success/10 text-success" : env === "TEST" ? "border-warning/30 bg-warning/10 text-warning" : "text-muted-foreground",
    )}>
      <span className={cn("size-1.5 rounded-full", env === "LIVE" ? "bg-success" : env === "TEST" ? "bg-warning" : "bg-muted-foreground")} aria-hidden="true" />
      {label}
    </span>
  );
}

export function AdminShell({ title, children }: { title: string; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(KEY) === "collapsed"; } catch { return false; }
  });
  const [mobile, setMobile] = useState(false);
  const [cmd, setCmd] = useState(false);
  const { me, refresh } = useAdmin();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const toggle = useCallback(() => setCollapsed((c) => {
    try { localStorage.setItem(KEY, c ? "expanded" : "collapsed"); } catch { /* ignore */ }
    return !c;
  }), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") (e.preventDefault(), setCmd((o) => !o));
      else if (mod && e.key.toLowerCase() === "b") (e.preventDefault(), toggle());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
  useEffect(() => void (document.title = `${title} · AiWazz admin`), [title]);

  const lock = async () => {
    await api("/api/admin/lock", { method: "POST" }).catch(() => undefined);
    await refresh();
  };

  return (
    <div className="flex min-h-dvh">
      <a href="#admin-main" className="sr-only z-50 rounded-lg bg-foreground px-3 py-2 text-sm text-background focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to content
      </a>
      <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col border-r bg-surface/60 transition-[width] duration-200 ease-out md:flex", collapsed ? "w-[60px]" : "w-60")}>
        <div className={cn("flex h-14 items-center gap-2 px-4", collapsed && "justify-center px-0")}>
          {collapsed ? <BrandIcon size={28} /> : (
            <>
              <Logo width={120} />
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">Admin</span>
            </>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-2.5 py-2">
          <Nav collapsed={collapsed} />
        </div>
        <div className={cn("border-t p-2.5", collapsed && "flex justify-center")}>
          <button type="button" onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
            className={cn("flex h-8 items-center gap-2 rounded-lg px-2 text-xs text-muted-foreground hover:bg-surface-2 hover:text-foreground", collapsed ? "w-8 justify-center px-0" : "w-full")}>
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
            {!collapsed && <>Collapse <kbd className="ml-auto font-mono text-[10px] text-subtle-foreground">⌘B</kbd></>}
          </button>
        </div>
      </aside>

      <Sheet open={mobile} onOpenChange={setMobile}>
        <SheetContent side="left" className="w-72 overflow-y-auto bg-surface p-0">
          <SheetHeader className="h-14 flex-row items-center gap-2 border-b px-4">
            <SheetTitle asChild><span><Logo width={116} /></span></SheetTitle>
            <SheetDescription className="sr-only">Admin navigation</SheetDescription>
          </SheetHeader>
          <div className="p-3"><Nav onNavigate={() => setMobile(false)} /></div>
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass sticky top-0 z-30 flex h-14 items-center gap-2 border-b px-3 sm:px-5">
          <Button variant="ghost" size="icon-sm" className="md:hidden" onClick={() => setMobile(true)} aria-label="Open menu"><Menu /></Button>
          <BrandIcon size={26} className="md:hidden" />
          <p className="ml-1 truncate text-sm font-medium md:ml-0">{title}</p>
          <div className="ml-auto flex items-center gap-1.5">
            <button type="button" onClick={() => setCmd(true)}
              className="hidden h-8 w-64 items-center gap-2 rounded-lg border bg-surface-2/70 px-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground lg:flex">
              <Search className="size-3.5" /> Search users, payments, invoices…
              <kbd className="ml-auto rounded border bg-surface px-1.5 font-mono text-[10px]">⌘K</kbd>
            </button>
            <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setCmd(true)} aria-label="Search"><Search /></Button>
            {me && <EnvBadge env={me.payments_env} />}
            <Bell_ />
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" aria-label="Account menu"
                  className="ml-1 grid size-8 place-items-center rounded-full bg-brand-gradient-strong text-xs font-semibold text-white ring-2 ring-background">
                  {(me?.user.email[0] ?? "?").toUpperCase()}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60">
                <DropdownMenuLabel className="font-normal">
                  <p className="truncate text-sm font-medium">{me?.user.email}</p>
                  <p className="flex items-center gap-1 text-xs text-muted-foreground capitalize"><ShieldCheck className="size-3" /> {me?.user.role} · 2FA on</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => (window.location.href = "/generate")}><SquareArrowOutUpRight /> Back to the app</DropdownMenuItem>
                <DropdownMenuItem onSelect={lock}><Lock /> Lock admin panel</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={async () => (await logout(), navigate("/login", { replace: true }))}><LogOut /> Sign out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main id="admin-main" className="mx-auto w-full max-w-[1400px] flex-1 px-3 py-6 sm:px-6 lg:px-8">{children}</main>
        <footer className="px-6 pb-6 text-center text-xs text-muted-foreground">© 2026 AiWazz · RADHAMADHAV WEBSTORE LLP</footer>
      </div>
      <Palette open={cmd} onOpenChange={setCmd} />
    </div>
  );
}
