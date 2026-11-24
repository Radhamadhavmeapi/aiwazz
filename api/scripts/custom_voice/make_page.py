"""Build the owner-only sample page for phase 13 (served by /api/preview/custom-voice/).

Reads /root/voicelab/out/{eval.json,*stats*.json} + the 48 kHz MP3s, copies MP3s into
data/voices/hi_reel_narrator_m1/lab/ (gitignored, outside the web root) and writes index.html there.
Usage: api/.venv/bin/python api/scripts/custom_voice/make_page.py
"""
import html, json, shutil, subprocess, sys
from pathlib import Path

OUT = Path("/root/voicelab/out")
VOICE = Path(__file__).resolve().parents[3] / "data" / "voices" / "hi_reel_narrator_m1"
LAB = VOICE / "lab"
sys.path.insert(0, "/root/voicelab")
from common import SCRIPTS  # noqa: E402

e = html.escape
ev = json.loads((OUT / "eval.json").read_text())
cands = json.loads((OUT / "candidates.json").read_text())   # [{id, route, label, dir, note, stats}] written by hand per run

LAB.mkdir(parents=True, exist_ok=True)
for c in ("A", "B"):
    src = VOICE / f"voice_reference_{c}_{'13' if c == 'A' else '16'}s.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-b:a", "192k", str(LAB / f"narrator-{c}.mp3")], check=True)

rows_by_script = {k: [] for k in SCRIPTS}
for c in cands:
    for key in SCRIPTS:
        src = OUT / c["dir"] / f"{key}.mp3"
        if not src.exists():
            continue
        dst = LAB / c["id"] / f"{key}.mp3"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        m = ev.get(f"{c['dir']}/{key}", {})
        rows_by_script[key].append((c, m))


def pct(x):
    return f"{round(x * 100)}%" if isinstance(x, (int, float)) else "–"


summary = "".join(
    f"<tr><td><b>{e(c['label'])}</b><br><span class=muted>{e(c['route'])}</span></td><td>{e(c['similarity'])}</td>"
    f"<td>{e(c['clarity'])}</td><td>{e(c['speed'])}</td><td>{e(c['ram'])}</td></tr>" for c in cands)

sections = []
for key, (title, text) in SCRIPTS.items():
    items = "".join(f"""
    <div class="row" data-id="{e(c['id'])}/{key}">
      <div class="lbl"><b>{e(c['label'])}</b><span class="muted"> · similarity {pct(m.get('sim_full'))} · CER {pct(m.get('cer'))}</span></div>
      <audio controls preload="none" src="{e(c['id'])}/{key}.mp3"></audio>
      <div class="vote"><button type="button" data-v="up" aria-label="Good">👍</button><button type="button" data-v="down" aria-label="Not good">👎</button>
      <input type="text" placeholder="note" aria-label="Note"></div>
    </div>""" for c, m in rows_by_script[key])
    sections.append(f"""<section><h2>{e(title)}</h2><p class="script" lang="hi">{e(text)}</p>{items}</section>""")

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Custom voice samples</title>
<style>
:root{{--bg:#f4f6fb;--card:#fff;--fg:#070d25;--muted:#475569;--line:rgba(7,13,37,.1);--brand:#2d36db}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0a0a0b;--card:#14161e;--fg:#f4f6fb;--muted:#94a3b8;--line:rgba(244,246,251,.1);--brand:#8a90f7}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI","Noto Sans Devanagari",sans-serif}}
main{{max-width:860px;margin:0 auto;padding:20px 16px 80px}} h1{{font-size:1.5rem;margin:.2em 0}} h2{{font-size:1.15rem;margin:0 0 .3em}}
section,.box{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:16px 0}}
.muted{{color:var(--muted);font-size:.85em}} .script{{color:var(--muted);font-size:.95em;max-height:7.5em;overflow:auto}}
.row{{border-top:1px solid var(--line);padding:10px 0}} audio{{width:100%;height:40px;margin:6px 0}}
.vote{{display:flex;gap:6px}} .vote button{{border:1px solid var(--line);background:transparent;border-radius:10px;padding:4px 10px;font-size:16px;cursor:pointer}}
.vote button[aria-pressed=true]{{border-color:var(--brand);background:rgba(45,54,219,.12)}}
.vote input{{flex:1;min-width:0;border:1px solid var(--line);border-radius:10px;padding:4px 8px;background:transparent;color:inherit}}
table{{width:100%;border-collapse:collapse;font-size:.9em}} td,th{{text-align:left;padding:6px 4px;border-top:1px solid var(--line);vertical-align:top}}
.btn{{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:10px 14px;font-weight:600;cursor:pointer}}
</style></head><body><main>
<p class="muted">AiWazz · phase 13 · owner only · not indexed</p>
<h1>Veer, Energetic Reel (Hindi): pick a route</h1>
<p>Same 5 scripts through every candidate. Listen to the narrator first, then compare. 👍/👎 and notes stay in this browser;
press <b>Copy my picks</b> at the end and paste the result to Claude. Similarity is measured by a speaker encoder
(the narrator's own clips score 98% against each other); CER is the Whisper error rate on the output (lower is clearer).</p>
<div class="box"><h2>The narrator (reference)</h2>
<div class="row"><div class="lbl"><b>Clip A</b> <span class="muted">12.8 s, main reference</span></div><audio controls preload="none" src="narrator-A.mp3"></audio></div>
<div class="row"><div class="lbl"><b>Clip B</b> <span class="muted">15.7 s, backup reference</span></div><audio controls preload="none" src="narrator-B.mp3"></audio></div></div>
<div class="box"><h2>At a glance</h2><table><tr><th>Candidate</th><th>Sounds like narrator</th><th>Clarity</th><th>Speed on this CPU</th><th>RAM</th></tr>{summary}</table></div>
{''.join(sections)}
<div class="box"><button class="btn" id="copy" type="button">Copy my picks</button> <span id="copied" class="muted"></span></div>
</main><script>
const K="aiwazz-cv-votes";let s={{}};try{{s=JSON.parse(localStorage.getItem(K)||"{{}}")}}catch{{}}
const save=()=>{{try{{localStorage.setItem(K,JSON.stringify(s))}}catch{{}}}};
document.querySelectorAll(".row[data-id]").forEach(r=>{{const id=r.dataset.id,v=s[id]||{{}};
 r.querySelectorAll("button").forEach(b=>{{b.setAttribute("aria-pressed",String(v.v===b.dataset.v));b.onclick=()=>{{v.v=v.v===b.dataset.v?null:b.dataset.v;s[id]=v;save();
 r.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(v.v===x.dataset.v)))}}}});
 const i=r.querySelector("input");i.value=v.n||"";i.oninput=()=>{{v.n=i.value;s[id]=v;save()}}}});
document.getElementById("copy").onclick=async()=>{{const t=Object.entries(s).filter(([,v])=>v.v||v.n).map(([k,v])=>`${{k}}: ${{v.v==="up"?"👍":v.v==="down"?"👎":""}} ${{v.n||""}}`).join("\\n")||"(no votes yet)";
 try{{await navigator.clipboard.writeText(t);document.getElementById("copied").textContent="Copied."}}catch{{document.getElementById("copied").textContent=t}}}};
</script></body></html>"""
(LAB / "index.html").write_text(page)
print("wrote", LAB / "index.html", sum(len(v) for v in rows_by_script.values()), "samples")
