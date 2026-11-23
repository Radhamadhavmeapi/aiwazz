import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

/** One shared <audio> for voice previews: starting one preview stops the previous one. */
type Ctx = { playing: string | null; toggle: (id: string, url: string) => void; stop: () => void };
const PreviewContext = createContext<Ctx | null>(null);

export function PreviewPlayerProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => {
    const a = new Audio();
    a.preload = "none";
    a.onended = () => setPlaying(null);
    a.onerror = () => {
      setPlaying(null);
      toast.error("Couldn't play this preview", { description: "Check your connection and try again." });
    };
    audio.current = a;
    return () => a.pause();
  }, []);

  const stop = useCallback(() => {
    audio.current?.pause();
    setPlaying(null);
  }, []);

  const toggle = useCallback(
    (id: string, url: string) => {
      const a = audio.current!;
      if (playing === id) return stop();
      a.src = url;
      a.currentTime = 0;
      a.play().then(
        () => setPlaying(id),
        () => setPlaying(null),
      );
      setPlaying(id);
    },
    [playing, stop],
  );

  return <PreviewContext.Provider value={{ playing, toggle, stop }}>{children}</PreviewContext.Provider>;
}

export function usePreviewPlayer() {
  const ctx = useContext(PreviewContext);
  if (!ctx) throw new Error("usePreviewPlayer must be used inside <PreviewPlayerProvider>");
  return ctx;
}
