import { AudioLines, History, KeyRound, Mic2, Settings, type LucideIcon } from "lucide-react";

export type NavItem = { to: string; label: string; icon: LucideIcon; shortcut?: string };

export const NAV: NavItem[] = [
  { to: "generate", label: "Generate", icon: AudioLines, shortcut: "G" },
  { to: "history", label: "History", icon: History, shortcut: "H" },
  { to: "voices", label: "Voices", icon: Mic2, shortcut: "V" },
  { to: "api-keys", label: "API keys", icon: KeyRound, shortcut: "K" },
  { to: "settings", label: "Settings", icon: Settings, shortcut: "S" },
];
