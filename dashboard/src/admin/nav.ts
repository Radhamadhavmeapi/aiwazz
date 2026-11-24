import {
  Activity, BadgePercent, BookA, ChartColumn, CreditCard, FileText, Gauge, History, Inbox, KeyRound, LayoutDashboard,
  ListOrdered, Mail, MailPlus, Megaphone, Mic2, Repeat, Scale, ScrollText, Settings, ShieldAlert, Tags, UserCog, Users,
  type LucideIcon,
} from "lucide-react";

export type AdminNavItem = { to: string; label: string; icon: LucideIcon; perm: string; keywords?: string };
export type AdminNavGroup = { label: string; items: AdminNavItem[] };

export const ADMIN_NAV: AdminNavGroup[] = [
  {
    label: "Insights",
    items: [
      { to: "", label: "Overview", icon: LayoutDashboard, perm: "overview.read", keywords: "home kpi mrr" },
      { to: "analytics", label: "Analytics", icon: ChartColumn, perm: "analytics.read", keywords: "funnel cohort" },
    ],
  },
  {
    label: "Customers",
    items: [
      { to: "users", label: "Users", icon: Users, perm: "users.read" },
      { to: "invites", label: "Invites & waitlist", icon: MailPlus, perm: "invites.read", keywords: "requests" },
      { to: "support", label: "Support inbox", icon: Inbox, perm: "support.read", keywords: "messages grievance" },
      { to: "moderation", label: "Moderation", icon: ShieldAlert, perm: "moderation.read", keywords: "flags abuse" },
    ],
  },
  {
    label: "Billing",
    items: [
      { to: "subscriptions", label: "Subscriptions", icon: Repeat, perm: "billing.read" },
      { to: "payments", label: "Payments", icon: CreditCard, perm: "billing.read", keywords: "refunds dunning webhooks" },
      { to: "invoices", label: "Invoices", icon: FileText, perm: "billing.read", keywords: "gst credit notes" },
      { to: "plans", label: "Plans & pricing", icon: Tags, perm: "plans.read" },
      { to: "coupons", label: "Coupons", icon: BadgePercent, perm: "coupons.read", keywords: "referrals promotions" },
    ],
  },
  {
    label: "Product",
    items: [
      { to: "voices", label: "Voices & styles", icon: Mic2, perm: "voices.read", keywords: "voice lab preview" },
      { to: "pronunciations", label: "Pronunciations", icon: BookA, perm: "voices.read" },
      { to: "api", label: "API & usage", icon: KeyRound, perm: "api.read", keywords: "keys" },
      { to: "queue", label: "Queue & jobs", icon: ListOrdered, perm: "queue.read", keywords: "maintenance" },
      { to: "announcements", label: "Announcements", icon: Megaphone, perm: "announcements.read", keywords: "changelog banner" },
      { to: "email", label: "Email", icon: Mail, perm: "email.read", keywords: "templates" },
    ],
  },
  {
    label: "System",
    items: [
      { to: "health", label: "System health", icon: Gauge, perm: "system.read", keywords: "backups pm2 ssl" },
      { to: "logs", label: "Logs", icon: ScrollText, perm: "logs.read" },
      { to: "compliance", label: "Compliance", icon: Scale, perm: "compliance.read", keywords: "dpdp legal" },
      { to: "settings", label: "Settings", icon: Settings, perm: "settings.read", keywords: "security flags" },
      { to: "team", label: "Team & roles", icon: UserCog, perm: "team.read", keywords: "staff" },
      { to: "audit", label: "Audit log", icon: History, perm: "audit.read" },
    ],
  },
];

export const ADMIN_ITEMS = ADMIN_NAV.flatMap((g) => g.items);
export const adminPath = (to: string) => (to ? `/admin/${to}` : "/admin");
export { Activity };
