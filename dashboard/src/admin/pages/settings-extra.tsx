// General, limits, feature flags, payments and integrations tabs arrive in A7.
export const SETTINGS_TABS: { id: string; label: string }[] = [];
export function SettingsExtra({ tab }: { tab: string }) {
  return <p className="text-sm text-muted-foreground">{tab}</p>;
}
