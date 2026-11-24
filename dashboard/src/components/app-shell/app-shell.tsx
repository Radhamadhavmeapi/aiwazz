import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { Logo } from "@/components/brand/logo";
import { SiteFooter } from "@/components/site-footer";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CommandPalette } from "./command-palette";
import { NAV } from "./nav";
import { Sidebar, SidebarNav } from "./sidebar";
import { Topbar } from "./topbar";

const KEY = "aiwazz-sidebar";
const readCollapsed = () => {
  try {
    return localStorage.getItem(KEY) === "collapsed";
  } catch {
    return false;
  }
};

export function AppShell({
  title,
  children,
  onPickVoice,
}: {
  title: string;
  children: ReactNode;
  onPickVoice?: (id: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const navigate = useNavigate();

  const toggleSidebar = useCallback(() => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(KEY, c ? "expanded" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  }, []);

  // ⌘K / Ctrl+K palette, ⌘B sidebar, "G then <letter>" navigation.
  useEffect(() => {
    let pendingG = 0;
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") (e.preventDefault(), setCmdOpen((o) => !o));
      else if (mod && e.key.toLowerCase() === "b") (e.preventDefault(), toggleSidebar());
      const typing = (e.target as HTMLElement)?.closest("input, textarea, [contenteditable=true], [role=dialog]");
      if (typing || mod || e.altKey) return;
      if (e.key.toLowerCase() === "g") pendingG = Date.now();
      else if (Date.now() - pendingG < 800) {
        const item = NAV.find((n) => n.shortcut?.toLowerCase() === e.key.toLowerCase());
        if (item) navigate(`/${item.to}`);
        pendingG = 0;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, toggleSidebar]);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-foreground px-3 py-2 text-sm text-background focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 bg-surface p-0">
          <SheetHeader className="h-14 flex-row items-center border-b px-4">
            <SheetTitle asChild>
              <span>
                <Logo width={124} />
              </span>
            </SheetTitle>
            <SheetDescription className="sr-only">Main navigation</SheetDescription>
          </SheetHeader>
          <div className="p-3">
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={title} onMenu={() => setMobileOpen(true)} onCommand={() => setCmdOpen(true)} />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter className="mt-8 pb-24 lg:pb-5" />
      </div>

      <CommandPalette open={cmdOpen} onOpenChange={setCmdOpen} onPickVoice={onPickVoice} />
    </div>
  );
}
