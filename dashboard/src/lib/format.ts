const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "2 min ago", "yesterday", … from an ISO timestamp. */
export function timeAgo(iso: string, now = Date.now()): string {
  const s = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(s);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}

export const fmtDuration = (sec: number | null | undefined) =>
  sec == null ? "–" : `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/** Days left before generated audio is deleted (kept 7 days). */
export const daysLeft = (iso: string, keepDays = 7) =>
  Math.max(0, Math.ceil((new Date(iso).getTime() + keepDays * 86400_000 - Date.now()) / 86400_000));
