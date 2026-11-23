import { LogOut, Moon, Sun } from "lucide-react";
import { useNavigate } from "react-router";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { langLabel, VOICES } from "@/lib/voices";
import { NAV } from "./nav";

export function CommandPalette({
  open,
  onOpenChange,
  onPickVoice,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onPickVoice?: (id: string) => void;
}) {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const { logout } = useAuth();
  const run = (fn: () => void) => () => {
    onOpenChange(false);
    fn();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Command palette" description="Jump to a page or run an action">
      <CommandInput placeholder="Type a command or search voices…" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {NAV.map(({ to, label, icon: Icon, shortcut }) => (
            <CommandItem key={to} onSelect={run(() => navigate(`/${to}`))}>
              <Icon />
              {label}
              {shortcut && <CommandShortcut>G {shortcut}</CommandShortcut>}
            </CommandItem>
          ))}
        </CommandGroup>
        {onPickVoice && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Voices">
              {VOICES.map((v) => (
                <CommandItem key={v.id} value={`voice ${v.name} ${langLabel(v.lang)} ${v.gender}`} onSelect={run(() => onPickVoice(v.id))}>
                  <span className="grid size-5 place-items-center rounded bg-surface-3 font-mono text-[10px]">{v.name.slice(0, 2)}</span>
                  {v.name}
                  <span className="text-muted-foreground">· {langLabel(v.lang)}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem onSelect={run(toggle)}>
            {theme === "dark" ? <Sun /> : <Moon />}
            Switch to {theme === "dark" ? "light" : "dark"} theme
          </CommandItem>
          <CommandItem onSelect={run(() => logout().then(() => navigate("/login", { replace: true })))}>
            <LogOut />
            Sign out
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
