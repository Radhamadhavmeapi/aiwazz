// One shared <audio> for all samples. Buttons: [data-play="demo-hi"]. Cards: [data-sample-card="demo-hi"].
// While playing: card gets data-playing="true", matching <aiwazz-wave for="..."> switches to "active".
const audio = new Audio();
audio.preload = "none";
let current: string | null = null;

function mark(id: string | null) {
  document.querySelectorAll<HTMLElement>("[data-sample-card]").forEach((c) => (c.dataset.playing = String(c.dataset.sampleCard === id)));
  document.querySelectorAll<HTMLButtonElement>("[data-play]").forEach((b) => {
    const on = b.dataset.play === id;
    b.setAttribute("aria-pressed", String(on));
    const name = b.dataset.name || "sample";
    b.setAttribute("aria-label", on ? `Pause ${name}` : `Play ${name}`);
  });
  document.querySelectorAll("aiwazz-wave[for]").forEach((w) => w.setAttribute("mode", w.getAttribute("for") === id ? "active" : "idle"));
}

function stop() {
  audio.pause();
  current = null;
  mark(null);
}

document.addEventListener("click", (e) => {
  const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-play]");
  if (!btn) return;
  const id = btn.dataset.play!;
  if (current === id) return stop();
  audio.src = `/samples/${id}.mp3`;
  current = id;
  mark(id);
  audio.play().catch(stop);
});
audio.addEventListener("ended", stop);
audio.addEventListener("error", stop);
