"""Shared helpers for the phase-13 custom voice tests (run from /root/voicelab, never in git)."""
import os, re, sys, threading, time, resource
from pathlib import Path

sys.path.insert(0, "/www/aiwazz/api")
from tts.text import normalize as aiwazz_normalize, split_text  # noqa: E402

LAB = Path("/root/voicelab")
OUT = LAB / "out"
VOICE = Path("/www/aiwazz/data/voices/hi_reel_narrator_m1")
REFS = {"A": VOICE / "voice_reference_A_13s.wav", "B": VOICE / "voice_reference_B_16s.wav"}
REF_TEXT = {
    "A": "एक गिलास गुनगुने पानी में एक चौथाई चम्मच पिंक सॉल्ट या सेंधा नमक मिलाओ। सोडियम ब्लड वॉल्यूम बढ़ाकर पानी को सीधा मसल सेल्स के अंदर खींचता है। यही देता है वो असली टाइट पंप। दो, इसमें एक बड़ा चम्मच शहद मिलाओ, या साथ में पका हुआ केला खाओ।",
    "B": "आधा ताज़ा नींबू निचोड़ो। इसमें मौजूद पोटैशियम और नेचुरल इलेक्ट्रोलाइट्स जिम के बीच में होने वाले मसल क्रैम्प्स को रोकते हैं, और आखिरी रेप तक फुल स्टैमिना रखते हैं। और अगर एक्स्ट्रा फोकस चाहिए, तो साथ में दो रुपये वाला ब्लैक कॉफ़ी शॉट ले लो। दिमाग एकदम सुपर शार्प और अलर्ट।",
}

SCRIPTS = {
    "1-hook": ("Hindi reel hook",
               "रुको! अगर तुम रोज़ जिम जाते हो और फिर भी बॉडी नहीं बन रही, तो गलती तुम्हारी मेहनत में नहीं, तुम्हारे प्लान में है। ये वीडियो पूरा देखना।"),
    "2-hinglish": ("Hinglish line",
                   "आज का workout plan बहुत simple है। बस तीन exercises, पंद्रह minute, और zero excuses। Let's go!"),
    "3-numbers": ("Numbers and ₹ amounts",
                  "सिर्फ़ ₹499 में पूरे महीने का diet plan, और पहले 100 लोगों को 20% की छूट। ये ऑफ़र 31 दिसंबर तक है, और 2,500 से ज़्यादा लोग इसे पहले ही ले चुके हैं।"),
    "4-full-reel": ("60-second full reel", """सुबह उठते ही फ़ोन उठाते हो? तो ये आदत आज ही बदलो, क्योंकि तुम्हारे दिन का पहला घंटा ही पूरे दिन का मूड तय करता है।

पहला काम: उठते ही एक गिलास पानी पियो। रात भर में बॉडी डिहाइड्रेट हो जाती है, और यही थकान की सबसे बड़ी वजह है।

दूसरा: दस मिनट धूप में चलो। सुबह की रोशनी तुम्हारी बॉडी क्लॉक को सेट करती है, जिससे रात को नींद जल्दी और गहरी आती है।

तीसरा: अपने दिन के तीन सबसे ज़रूरी काम एक कागज़ पर लिखो। बस तीन। जब लिस्ट छोटी होती है, तो काम सच में पूरे होते हैं।

और चौथा, सबसे ज़रूरी: पहले तीस मिनट फ़ोन को हाथ मत लगाओ। न रील्स, न मैसेज, न न्यूज़। ये तीस मिनट सिर्फ़ तुम्हारे हैं।

बस एक हफ़्ता ये रूटीन फ़ॉलो करो, और फ़र्क खुद महसूस करो। वीडियो सेव कर लो, और उस दोस्त को भेजो जो रोज़ सुबह लेट उठता है।"""),
    "5-calm": ("Calm, slow line",
               "रात को सोने से पहले, फ़ोन को दूर रख दो। एक गहरी साँस लो, धीरे से छोड़ो, और खुद से कहो: आज मैंने अपना बेस्ट दिया।"),
}

# ── Hindi numbers → words (for engines that can't read digits, and for fair CER) ──
_W = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस "
      "चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस "
      "इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन "
      "सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरेसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
      "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे "
      "इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे").split()
assert len(_W) == 100


def hi_num(n: int) -> str:
    if n < 100:
        return _W[n]
    for size, name in ((10**7, "करोड़"), (10**5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= size:
            q, r = divmod(n, size)
            return f"{hi_num(q)} {name}" + (f" {hi_num(r)}" if r else "")
    return str(n)


def expand_numbers(text: str) -> str:
    text = re.sub(r"(\d+)\s?%", lambda m: f"{m.group(1)} प्रतिशत", text)
    return re.sub(r"\d+", lambda m: hi_num(int(m.group(0))), text)


def prepare(text: str, digits_to_words: bool = True) -> list[list[str]]:
    """Production text path (₹/number normalize + sentence split) → paragraphs of sentences."""
    t = aiwazz_normalize(text, "h")
    if digits_to_words:
        t = expand_numbers(t)
    return split_text(t)


def spoken_text(text: str) -> str:
    """The reference text for CER: what should be heard (numbers as Hindi words)."""
    return " ".join(s for p in prepare(text) for s in p)


# ── safety + measurement ──
def mem_available_mb() -> int:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) // 1024
    return 0


def start_watchdog(floor_mb: int = 600):
    """Kill THIS process (never the API) if the server's available RAM drops below floor_mb."""
    state = {"min_avail": mem_available_mb()}

    def run():
        while True:
            a = mem_available_mb()
            state["min_avail"] = min(state["min_avail"], a)
            if a < floor_mb:
                print(f"\n!!! watchdog: MemAvailable {a} MB < {floor_mb} MB, aborting test to protect Kokoro", flush=True)
                os._exit(3)
            time.sleep(0.1)
    threading.Thread(target=run, daemon=True).start()
    return state


def peak_rss_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def require_free(mb: int):
    a = mem_available_mb()
    if a < mb:
        sys.exit(f"Not enough free RAM to start: {a} MB available, need {mb} MB")
    print(f"MemAvailable at start: {a} MB")


def postprocess(paragraph_clips, sr, out_base: Path, sentence_ms=250, paragraph_ms=600, lufs=-14.0):
    """Same as production: trim each sentence, fixed pauses, edges, two-pass loudness, WAV + MP3 48 kHz."""
    from tts import audio
    clips = [[audio.trim_silence(c, sr, -45.0, keep_ms=20) for c in para] for para in paragraph_clips]
    clips = [[c for c in para if c.size] for para in clips]
    joined = audio.join_segments([p for p in clips if p], sr, sentence_ms, paragraph_ms)
    joined = audio.trim_silence(joined, sr, -45.0, keep_ms=20)
    joined = audio.pad_edges(joined, sr, 80)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    audio.export(joined, sr, out_base, sample_rate=48000, mp3_bitrate="192k", target_lufs=lufs, true_peak=-1.0,
                 compressor=audio.Compressor(0.0, 2.0))
    return joined.size / sr
