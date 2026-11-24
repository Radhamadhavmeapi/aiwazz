import { AlertCircle, Clock, Code2, Download, History as HistoryIcon, Pause, Play, RefreshCw, Search, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { AppShell } from "@/components/app-shell/app-shell";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { daysLeft, fmtDuration, timeAgo } from "@/lib/format";
import { downloadUrl, getHistory, type HistoryItem } from "@/lib/tts";
import { STYLES } from "@/lib/styles";
import { cn } from "@/lib/utils";
import { findVoice, langLabel, useVoices, type Lang } from "@/lib/voices";

function Row({ it, onDeleted }: { it: HistoryItem; onDeleted: (id: string) => void }) {
  const { playing, toggle } = usePreviewPlayer();
  useVoices();
  const v = findVoice(it.voice);
  const on = playing === it.id;
  const busy = it.status === "queued" || it.status === "running";
  const left = daysLeft(it.created_at);

  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <button
          type="button"
          disabled={!it.available}
          onClick={() => it.urls && toggle(it.id, it.urls.mp3)}
          aria-label={on ? "Pause" : `Play: ${it.text_excerpt}`}
          aria-pressed={on}
          className={cn(
            "mt-0.5 grid size-10 shrink-0 place-items-center rounded-full border transition-colors disabled:opacity-40",
            on ? "border-transparent bg-foreground text-background" : "bg-surface-2 text-muted-foreground hover:bg-surface-3 hover:text-foreground",
          )}
        >
          {on ? <Pause className="size-4 fill-current" /> : <Play className="ml-0.5 size-4 fill-current" />}
        </button>
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm leading-6" lang={it.lang === "h" ? "hi" : "en"}>
            {it.text_excerpt}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>
              {v?.name ?? it.voice} · {langLabel(it.lang as Lang)}
            </span>
            <span aria-hidden="true">·</span>
            <span className="font-mono tabular">{fmtDuration(it.duration_sec)}</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">{it.speed.toFixed(2)}×</span>
            {it.style && (
              <>
                <span aria-hidden="true">·</span>
                <span>{STYLES.find((st) => st.id === it.style)?.name ?? it.style}</span>
              </>
            )}
            {it.output_lufs != null && (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">{it.output_lufs.toFixed(1)} LUFS</span>
              </>
            )}
            <span aria-hidden="true">·</span>
            <time dateTime={it.created_at} title={new Date(it.created_at).toLocaleString()}>
              {timeAgo(it.created_at)}
            </time>
            {it.via_api && (
              <Badge variant="outline" className="gap-1 font-normal">
                <Code2 className="size-3" /> API
              </Badge>
            )}
          </p>
          {it.status === "error" && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-danger">
              <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" /> {it.error || "Generation failed"}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2 pl-[52px] sm:pl-0">
        {!busy && (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Delete from history"
            title="Delete from history"
            onClick={async () => {
              if (!window.confirm("Delete this voiceover and its audio files?")) return;
              try {
                await api(`/api/history/${it.id}`, { method: "DELETE" });
                onDeleted(it.id);
                toast.success("Deleted from history");
              } catch (e) {
                toast.error("Couldn't delete", { description: e instanceof ApiError ? e.message : undefined });
              }
            }}
          >
            <Trash2 />
          </Button>
        )}
        {busy && <Badge variant="secondary">In progress</Badge>}
        {it.status === "done" && !it.available && (
          <Badge variant="outline" className="font-normal text-muted-foreground">
            Expired
          </Badge>
        )}
        {it.available && it.urls && (
          <>
            <span className="hidden items-center gap-1 text-xs text-subtle-foreground md:flex" title="Audio is kept for 7 days">
              <Clock className="size-3.5" aria-hidden="true" />
              {left <= 1 ? "Expires today" : `${left} days left`}
            </span>
            {(["mp3", "wav"] as const).map((f) => (
              <Button key={f} asChild variant={it.format === f ? "default" : "outline"} size="sm">
                <a href={downloadUrl(it.urls![f])} download aria-label={`Download ${f.toUpperCase()}`}>
                  <Download /> {f.toUpperCase()}
                </a>
              </Button>
            ))}
          </>
        )}
      </div>
    </li>
  );
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    setError(null);
    getHistory(50).then(setItems, (e) => setError(e instanceof ApiError ? e.message : "Couldn't load your history."));
  }, []);
  useEffect(load, [load]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (items ?? []).filter((it) => !needle || it.text_excerpt.toLowerCase().includes(needle) || it.voice.includes(needle));
  }, [items, q]);

  return (
    <AppShell title="History">
      <div className="mx-auto max-w-5xl space-y-5 p-3 sm:p-5 lg:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-h2 font-semibold">History</h2>
            <p className="mt-1 text-sm text-muted-foreground">Your last 50 voiceovers. Audio files are kept for 7 days.</p>
          </div>
          <div className="relative sm:w-64">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle-foreground" aria-hidden="true" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search scripts…" aria-label="Search history" className="h-9 pl-9" />
          </div>
        </div>

        <div className="rounded-2xl border bg-surface shadow-md">
          {error ? (
            <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
              <AlertCircle className="size-6 text-danger" aria-hidden="true" />
              <p className="text-sm">{error}</p>
              <Button variant="outline" size="sm" onClick={load}>
                <RefreshCw /> Try again
              </Button>
            </div>
          ) : items === null ? (
            <ul className="divide-y" aria-busy="true" aria-label="Loading history">
              {Array.from({ length: 5 }, (_, i) => (
                <li key={i} className="flex items-center gap-3 p-4">
                  <Skeleton className="size-10 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/3" />
                  </div>
                </li>
              ))}
            </ul>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
              <span className="grid size-12 place-items-center rounded-2xl border bg-surface-2 text-brand">
                <HistoryIcon className="size-5" aria-hidden="true" />
              </span>
              <p className="font-medium">No voiceovers yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">Everything you generate shows up here, ready to play and download for 7 days.</p>
              <Button asChild variant="brand" className="mt-2">
                <Link to="/generate">
                  <Wand2 /> Generate your first
                </Link>
              </Button>
            </div>
          ) : shown.length === 0 ? (
            <p className="px-6 py-12 text-center text-sm text-muted-foreground">No voiceovers match “{q}”.</p>
          ) : (
            <ul className="divide-y">
              {shown.map((it) => (
                <Row key={it.id} it={it} onDeleted={(id) => setItems((xs) => (xs ?? []).filter((x) => x.id !== id))} />
              ))}
            </ul>
          )}
        </div>
      </div>
    </AppShell>
  );
}
