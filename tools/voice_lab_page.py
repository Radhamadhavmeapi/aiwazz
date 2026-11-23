#!/usr/bin/env python3
"""Render the hidden Voice Lab page (login.aiwazz.in/preview/voice-lab/) from samples/manifest.json
(track A, written by api/scripts/voice_lab.py) and an optional tracks.json (tracks B/C notes).
Notes (👍/👎 + text) are stored only in the viewer's browser (localStorage), no backend.
Usage: python3 tools/voice_lab_page.py /www/wwwroot/login.aiwazz.in/preview/voice-lab
(copy the Noto Sans Devanagari woff2 to <dir>/fonts/noto-deva.woff2 so Hindi renders on every device)
"""
import html
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
man = json.loads((root / "samples" / "manifest.json").read_text())
extra = json.loads((root / "tracks.json").read_text()) if (root / "tracks.json").exists() else {"B": [], "C": ""}
e = html.escape

TRACKS = {
    "A1": ("Track A1 · Indian-English accent", "The four Hindi voices reading the whole test set through the Hindi pipeline, including the English lines."),
    "A2": ("Track A2 · New voices from blends", "Weighted mixes of existing Kokoro style vectors: new, distinct speakers with no new model and no extra RAM."),
    "A3": ("Track A3 · Tone presets", "No new model: speed, pause length and loudness tuned per use case."),
}

def card(c):
    voices = " + ".join(f"{v['voice']} {round(v['weight'] * 100)}%" for v in c["voices"])
    return f"""
<article class="card" data-id="{e(c['id'])}">
  <div class="head"><h3>{e(c['name'])}</h3><span class="mono">{e(c['id'])}</span></div>
  <p class="desc">{e(c['description'])}</p>
  <audio controls preload="none" src="samples/{e(c['id'])}.mp3"></audio>
  <p class="meta mono">{e(voices)} · speed {c['preset']['speed']} · {c['duration_sec']} s · RTF {c['rtf']} · peak {c['peak_rss_mb']} MB · {c['output_lufs']} LUFS</p>
  <p class="meta">Licence: {e(c['licence'])}</p>
  <div class="vote"><button type="button" data-v="up" aria-pressed="false">👍</button><button type="button" data-v="down" aria-pressed="false">👎</button>
  <input type="text" placeholder="Your note (saved in this browser only)" aria-label="Note for {e(c['name'])}"></div>
</article>"""

sections = []
for key, (title, intro) in TRACKS.items():
    cards = "".join(card(c) for c in man["candidates"] if c["track"] == key)
    if cards:
        sections.append(f'<section><h2>{e(title)}</h2><p class="intro">{e(intro)}</p><div class="grid">{cards}</div></section>')
if extra.get("B"):
    rows = "".join(f"<tr><td><a href='{e(m['url'])}' target='_blank' rel='noopener'>{e(m['repo'])}</a></td><td>{e(m['licence'])}</td><td>{e(m['size'])}</td><td>{e(m['notes'])}</td><td><strong>{e(m['verdict'])}</strong></td></tr>" for m in extra["B"])
    sections.append(f"<section><h2>Track B · Open Indian TTS models</h2><p class='intro'>Checked against the limits (commercial licence, CPU without AVX2, ≤ 2.5 GB RAM, ≤ 3× real time). No samples unless a model passes.</p><div class='tw'><table><thead><tr><th>Model</th><th>Licence</th><th>Size</th><th>Notes</th><th>Verdict</th></tr></thead><tbody>{rows}</tbody></table></div></section>")
if extra.get("C"):
    sections.append(f"<section><h2>Track C · Paid API option</h2><div class='note'>{extra['C']}</div></section>")

tests = "".join(f"<li><span class='tag'>{e(k)}</span> <span lang='{'en' if k == 'Indian English' else 'hi'}'>{e(t)}</span></li>" for k, t in man["test_set"])
page = f"""<!doctype html>
<html lang="en" class="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Voice Lab · AiWazz (private preview)</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
@font-face{{font-family:"Noto Sans Devanagari";src:url(fonts/noto-deva.woff2) format("woff2");font-weight:100 900;font-display:swap;unicode-range:U+0900-097F,U+1CD0-1CF9,U+200C-200D,U+20A8,U+20B9,U+25CC,U+A830-A839,U+A8E0-A8FF}}
:root{{--bg:#f4f6fb;--s:#fff;--s2:#eef1f7;--b:rgb(7 13 37/.09);--fg:#070d25;--mu:#475569;--su:#566377;--br:#2d36db;--g:linear-gradient(135deg,#51b2f6,#2d36db 50%,#7420dd)}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI","Noto Sans Devanagari",sans-serif}}
.wrap{{max-width:1120px;margin:0 auto;padding:40px 16px 80px}}h1{{font:700 2.2rem/1.1 Poppins,ui-sans-serif,system-ui;letter-spacing:-.03em;margin:.3rem 0}}
h2{{font:600 1.35rem/1.3 Poppins,ui-sans-serif,system-ui;margin:2.5rem 0 .3rem}}h3{{margin:0;font-size:1rem}}.eyebrow{{font:12px/1 ui-monospace,monospace;color:var(--br);text-transform:uppercase;letter-spacing:.08em}}
.intro,.desc,.meta{{color:var(--mu)}}.meta{{font-size:12px;margin:.35rem 0 0}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--su)}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));margin-top:1rem}}.card{{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:16px;box-shadow:0 8px 24px -12px rgb(7 13 37/.12)}}
.head{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}}audio{{width:100%;margin-top:10px}}.vote{{display:flex;gap:6px;margin-top:10px}}
.vote button{{border:1px solid var(--b);background:var(--s2);border-radius:10px;padding:4px 10px;cursor:pointer;font-size:16px}}.vote button[aria-pressed=true]{{background:var(--fg);border-color:var(--fg)}}
.vote input{{flex:1;min-width:0;border:1px solid var(--b);border-radius:10px;padding:6px 10px;font:inherit;font-size:13px;background:var(--s2);color:var(--fg)}}
.box{{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:16px 20px;margin-top:1.2rem}}.tag{{display:inline-block;font-size:11px;background:var(--s2);border:1px solid var(--b);border-radius:999px;padding:0 8px;margin-right:6px;color:var(--mu)}}
ul.tests{{list-style:none;padding:0;margin:.5rem 0 0}}ul.tests li{{margin:.4rem 0}}.tw{{overflow-x:auto;border:1px solid var(--b);border-radius:14px;background:var(--s);margin-top:1rem}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--b);vertical-align:top}}th{{background:var(--s2)}}.note{{background:var(--s);border:1px solid var(--b);border-radius:14px;padding:16px 20px}}
.bar{{height:4px;border-radius:4px;background:var(--g);margin:1rem 0 0;max-width:180px}}a{{color:var(--br)}}
</style></head><body><main class="wrap">
<p class="eyebrow">Private preview · noindex · nothing here is in the product</p>
<h1>Voice Lab</h1><div class="bar"></div>
<p class="intro">Candidate Indian voices, Indian-English accent and tone presets. Every sample uses the same post-processing as production (trim, pauses, compressor, -14 LUFS unless noted, MP3 48 kHz). Rate them with 👍/👎 and a note; your notes stay in this browser.</p>
<div class="box"><strong>Test set</strong> (same text for every candidate)<ul class="tests">{tests}</ul></div>
{''.join(sections)}
<p class="intro" style="margin-top:3rem">Full findings: <code>content/VOICE-LAB-REPORT.md</code> in the repo.</p>
</main>
<script>
const K = "aiwazz-voicelab";
let s = {{}}; try {{ s = JSON.parse(localStorage.getItem(K) || "{{}}"); }} catch {{}}
const save = () => {{ try {{ localStorage.setItem(K, JSON.stringify(s)); }} catch {{}} }};
document.querySelectorAll(".card").forEach((c) => {{
  const id = c.dataset.id; const st = (s[id] ||= {{}});
  const btns = c.querySelectorAll(".vote button"); const inp = c.querySelector(".vote input");
  const paint = () => btns.forEach((b) => b.setAttribute("aria-pressed", String(st.v === b.dataset.v)));
  btns.forEach((b) => b.addEventListener("click", () => {{ st.v = st.v === b.dataset.v ? null : b.dataset.v; paint(); save(); }}));
  inp.value = st.n || ""; inp.addEventListener("input", () => {{ st.n = inp.value; save(); }}); paint();
}});
document.addEventListener("play", (ev) => document.querySelectorAll("audio").forEach((a) => a !== ev.target && a.pause()), true);
</script></body></html>"""
(root / "index.html").write_text(page)
print(f"wrote {root / 'index.html'} ({len(man['candidates'])} samples)")
