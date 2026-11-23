import { Check, Pause, Play } from "lucide-react";
import { usePreviewPlayer } from "@/components/audio/preview-player";
import { cn } from "@/lib/utils";
import { sampleUrl, type Voice } from "@/lib/voices";

function EqBars({ on }: { on: boolean }) {
  return (
    <span aria-hidden="true" className="flex h-3 items-end gap-[2px]">
      {[0.55, 1, 0.7, 0.85].map((h, i) => (
        <span
          key={i}
          className={cn("w-[3px] rounded-full bg-brand-gradient", on && "animate-[eq_900ms_ease-in-out_infinite]")}
          style={{ height: `${h * 100}%`, animationDelay: `${i * 120}ms` }}
        />
      ))}
    </span>
  );
}

/**
 * Voice option: a real radio input (keyboard: arrows within the group) plus a separate
 * preview button, so there is no interactive element nested inside another.
 */
export function VoiceCard({
  voice,
  checked,
  onSelect,
  name = "voice",
}: {
  voice: Voice;
  checked: boolean;
  onSelect: (id: string) => void;
  name?: string;
}) {
  const { playing, toggle } = usePreviewPlayer();
  const isPlaying = playing === voice.id;

  return (
    <div
      className={cn(
        "group relative flex items-center gap-3 rounded-xl border bg-surface p-3 transition-[border-color,background-color,box-shadow] duration-150",
        checked ? "border-transparent shadow-brand-glow" : "hover:border-border-strong hover:bg-surface-2",
      )}
    >
      <input
        id={`voice-${voice.id}`}
        type="radio"
        name={name}
        value={voice.id}
        checked={checked}
        onChange={() => onSelect(voice.id)}
        className="peer sr-only"
      />
      <label
        htmlFor={`voice-${voice.id}`}
        className="absolute inset-0 cursor-pointer rounded-xl peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring"
      >
        <span className="sr-only">
          {voice.name}, {voice.gender}, {voice.tone}
        </span>
      </label>

      <span
        aria-hidden="true"
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg border font-mono text-[13px] font-medium",
          checked ? "border-transparent bg-brand-gradient-strong text-white" : "bg-surface-2 text-muted-foreground",
        )}
      >
        {checked ? <Check className="size-4" /> : voice.name.slice(0, 2)}
      </span>
      <span aria-hidden="true" className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-medium">
          {voice.name}
          {isPlaying && <EqBars on />}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {voice.gender === "female" ? "Female" : "Male"} · {voice.tone}
        </span>
      </span>
      <button
        type="button"
        onClick={() => toggle(voice.id, sampleUrl(voice.id))}
        aria-label={isPlaying ? `Stop ${voice.name} preview` : `Play ${voice.name} preview`}
        aria-pressed={isPlaying}
        className={cn(
          "relative z-10 grid size-8 shrink-0 place-items-center rounded-full border transition-colors duration-150",
          isPlaying
            ? "border-transparent bg-foreground text-background"
            : "bg-surface-2 text-muted-foreground hover:bg-surface-3 hover:text-foreground",
        )}
      >
        {isPlaying ? <Pause className="size-3.5 fill-current" /> : <Play className="ml-0.5 size-3.5 fill-current" />}
      </button>
    </div>
  );
}
