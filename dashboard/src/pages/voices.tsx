import { ArrowRight, Pause, Play } from "lucide-react";
import { Link } from "react-router";
import { AppShell } from "@/components/app-shell/app-shell";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LANGS, sampleUrl, VOICES } from "@/lib/voices";

export default function VoicesPage() {
  const { playing, toggle } = usePreviewPlayer();
  return (
    <AppShell title="Voices">
      <div className="mx-auto max-w-5xl space-y-8 p-3 sm:p-5 lg:p-6">
        <div>
          <h2 className="text-h2 font-semibold">Voices</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {VOICES.length} voices in {LANGS.length} languages. Every preview is real output, levelled to -14 LUFS.
          </p>
        </div>
        {LANGS.map((l) => (
          <section key={l.id} aria-labelledby={`lang-${l.id}`}>
            <h3 id={`lang-${l.id}`} className="font-sans text-sm font-medium text-muted-foreground">
              {l.label}
            </h3>
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {VOICES.filter((v) => v.lang === l.id).map((v) => {
                const on = playing === v.id;
                return (
                  <li
                    key={v.id}
                    className={cn(
                      "flex flex-col gap-4 rounded-2xl border bg-surface p-4 shadow-md transition-shadow",
                      on && "border-transparent shadow-brand-glow",
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggle(v.id, sampleUrl(v.id))}
                        aria-label={on ? `Stop ${v.name}` : `Play ${v.name} preview`}
                        aria-pressed={on}
                        className={cn(
                          "grid size-11 shrink-0 place-items-center rounded-full transition-[transform,background-color] duration-150 active:scale-95",
                          on ? "bg-foreground text-background" : "border bg-surface-2 text-foreground hover:bg-surface-3",
                        )}
                      >
                        {on ? <Pause className="size-4 fill-current" /> : <Play className="ml-0.5 size-4 fill-current" />}
                      </button>
                      <div className="min-w-0">
                        <p className="font-medium">{v.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {v.gender === "female" ? "Female" : "Male"} · {v.tone}
                        </p>
                      </div>
                      <span className="ml-auto font-mono text-[11px] text-subtle-foreground">{v.id}</span>
                    </div>
                    <Button asChild variant="outline" size="sm" className="self-start">
                      <Link to={`/generate?voice=${v.id}`}>
                        Use this voice <ArrowRight />
                      </Link>
                    </Button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </AppShell>
  );
}
