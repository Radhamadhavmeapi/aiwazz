"""Hinglish (Roman Hindi) → Devanagari for the Hindi voices, keeping English words as they are.

Kokoro's Hindi pipeline (espeak-ng "hi") reads Devanagari natively and switches to English pronunciation
for words in Latin script, so the goal is: Hindi words → Devanagari, English words → untouched.

Per word, in order:
  1. lexicon of common Hinglish words (correct spelling, incl. nasalisation: nahi → नहीं, main → मैं)
  2. brand names / acronyms (AiWazz, YouTube, OTP) → kept
  3. common English words (wordfreq zipf ≥ 3.5) → kept
  4. ambiguous words (to, do, main, par, log, …) → Hindi if the sentence is mostly Hindi, else English
  5. anything else → phonetic rules (casual romanisation, aims at correct pronunciation, not perfect spelling)
"""
import re
from functools import lru_cache

# ── Lexicon: common words whose casual spelling the rules would get wrong (or that look English). ──
_LEX_SRC = """
main mai mein=मैं|mujhe mujhko=मुझे|mera=मेरा|meri=मेरी|mere=मेरे|hum ham=हम|humein hame hamein=हमें|hamara humara=हमारा
hamari humari=हमारी|hamare humare=हमारे|tum=तुम|tumhe tumhein=तुम्हें|tumhara=तुम्हारा|tumhari=तुम्हारी|tumhare=तुम्हारे
aap ap=आप|aapka apka=आपका|aapki apki=आपकी|aapke apke=आपके|aapko apko=आपको|ye yeh=ये|wo woh vo voh=वो|yah=यह|vah=वह
is=इस|us=उस|iska=इसका|iski=इसकी|iske=इसके|uska=उसका|uski=उसकी|uske=उसके|isko ise=इसे|usko use=उसे|inka=इनका|unka=उनका
unki=उनकी|unke=उनके|inhe inhein=इन्हें|unhe unhein=उन्हें|unhone=उन्होंने|maine=मैंने|humne hamne=हमने|tumne=तुमने|aapne apne=आपने
apna=अपना|apni=अपनी|koi=कोई|kuch kuchh=कुछ|sab=सब|sabhi=सभी|sabko=सबको|log=लोग|logon logo=लोगों|khud=ख़ुद
hai h=है|hain=हैं|hu hun hoon=हूँ|ho=हो|tha=था|thi=थी|the=थे|hoga=होगा|hogi=होगी|honge=होंगे|hona=होना|hota=होता
hoti=होती|hote=होते|hua=हुआ|hui=हुई|hue huye=हुए|raha=रहा|rahi=रही|rahe=रहे|gaya=गया|gayi gai=गई|gaye=गए|diya=दिया
di=दी|diye=दिए|liya=लिया|li=ली|liye=लिए|kiya=किया|ki=की|kiye=किए|kar=कर|karo=करो|karna=करना|karne=करने|karte=करते
karta=करता|karti=करती|karein karen=करें|karenge=करेंगे|karunga=करूँगा|sakta=सकता|sakti=सकती|sakte=सकते|chahiye=चाहिए
chahte=चाहते|chahta=चाहता|chahti=चाहती|pata=पता|dekho=देखो|dekhiye=देखिए|dekhna=देखना|dekha=देखा|suno=सुनो|suniye=सुनिए
bolo=बोलो|bola=बोला|boli=बोली|bataya=बताया|batao=बताओ|bataiye=बताइए|aaya aya=आया|aayi ayi=आई|aaye aye=आए|aana=आना
jana=जाना|jao=जाओ|jaye jaaye=जाए|jayega jaayega=जाएगा|mila=मिला|mili=मिली|mile=मिले|milega=मिलेगा|milegi=मिलेगी
ka=का|ke=के|ko=को|se=से|me=में|mein=में|par pe=पर|tak=तक|liye=लिए|saath sath=साथ|bina=बिना|wala=वाला|wali=वाली|wale=वाले
aur or=और|ya=या|lekin=लेकिन|par=पर|magar=मगर|kyunki kyuki kyonki=क्योंकि|to toh=तो|bhi=भी|hi=ही|na=ना|nahi nahin nai=नहीं
mat=मत|haan han ha=हाँ|ji=जी|jee=जी|bas=बस|sirf=सिर्फ़|bahut bohot bohat=बहुत|zyada jyada=ज़्यादा|kam=कम|thoda=थोड़ा|thodi=थोड़ी
kya=क्या|kyu kyun kyon=क्यों|kaise kese=कैसे|kaisa=कैसा|kaisi=कैसी|kab=कब|kahan kaha=कहाँ|kaun kon=कौन|kitna=कितना
kitni=कितनी|kitne=कितने|jab=जब|tab=तब|jaise=जैसे|agar=अगर|phir fir=फिर|abhi=अभी|ab=अब|kabhi=कभी|hamesha=हमेशा
aaj aj=आज|kal=कल|parso=परसों|raat=रात|din=दिन|subah=सुबह|sham shaam=शाम|dopahar=दोपहर|baje=बजे|ghanta=घंटा|ghante=घंटे
minute=मिनट|saal=साल|mahina=महीना|hafte=हफ़्ते|pehle pahle=पहले|baad=बाद|jaldi=जल्दी|der=देर|waqt=वक़्त|samay=समय
ek=एक|do=दो|teen=तीन|char chaar=चार|paanch panch=पाँच|chhe=छह|saat=सात|aath=आठ|nau=नौ|das=दस|gyarah=ग्यारह|barah=बारह
sau=सौ|hazaar hazar=हज़ार|lakh=लाख|crore karod=करोड़|pehla=पहला|pehli=पहली|dusra doosra=दूसरा|teesra=तीसरा
accha acha achha=अच्छा|acchi achi=अच्छी|acche ache=अच्छे|bura=बुरा|bada=बड़ा|badi=बड़ी|bade=बड़े|chota chhota=छोटा
choti chhoti=छोटी|naya=नया|nayi nai=नई|purana=पुराना|sach=सच|sahi=सही|galat=ग़लत|khush=ख़ुश|aasan asan=आसान|mushkil=मुश्किल
dost=दोस्त|dosto doston=दोस्तों|bhai=भाई|behen=बहन|yaar=यार|ghar=घर|paisa=पैसा|paise=पैसे|kaam=काम|baat=बात|baatein=बातें
cheez=चीज़|cheezein=चीज़ें|tarah=तरह|tarika=तरीक़ा|zindagi=ज़िंदगी|duniya=दुनिया|desh=देश|shehar shahar=शहर|log=लोग
khana=खाना|paani=पानी|chai=चाय|dukaan dukan=दुकान|sawal=सवाल|jawab=जवाब|madad=मदद|zaroor jaroor=ज़रूर|shukriya=शुक्रिया
dhanyavaad dhanyavad=धन्यवाद|namaste=नमस्ते|swagat=स्वागत|bilkul=बिल्कुल|sabse=सबसे|isliye=इसलिए|matlab=मतलब|yahan=यहाँ
wahan=वहाँ|andar=अंदर|bahar=बाहर|upar=ऊपर|neeche niche=नीचे|aage=आगे|peeche piche=पीछे|paas=पास|door=दूर|sath=साथ
lagta=लगता|lagti=लगती|lagta=लगता|laga=लगा|lage=लगे|socho=सोचो|socha=सोचा|samjho=समझो|samjha=समझा|maloom=मालूम
ne=ने|bataunga=बताऊँगा|batayenge=बताएँगे|dikhaunga=दिखाऊँगा|sunaunga=सुनाऊँगा|aaunga aunga=आऊँगा|jaunga=जाऊँगा
milunga=मिलूँगा|karungi=करूँगी|chuno=चुनो|likho=लिखो|padho=पढ़ो|banao=बनाओ|banaya=बनाया|banaye banaen=बनाएँ|banana=बनाना|dikhao=दिखाओ|dikhaya=दिखाया|samjhao=समझाओ
chalo=चलो|chalte=चलते|chalega=चलेगा|ruko=रुको|lo=लो|do=दो|dijiye=दीजिए|lijiye=लीजिए|kijiye=कीजिए|aaiye aiye=आइए
kahani kahaani=कहानी|zaroorat jarurat=ज़रूरत|khabar=ख़बर|aawaz awaz awaaz=आवाज़|shabd=शब्द|pyaar pyar=प्यार|dil=दिल|sapna=सपना|khushi=ख़ुशी|dard=दर्द|zaruri jaruri=ज़रूरी|khaas khas=ख़ास|asli=असली|nakli=नक़ली
"""

LEXICON: dict[str, str] = {}
for _group in re.split(r"[|\n]", _LEX_SRC):
    _group = _group.strip()
    if "=" not in _group:
        continue
    _keys, _dev = _group.rsplit("=", 1)
    for _k in _keys.split():
        LEXICON.setdefault(_k.lower(), _dev.strip())

# Words that are also common English words: decided by the rest of the sentence.
AMBIGUOUS = {"to", "do", "main", "par", "log", "is", "us", "me", "hi", "he", "the", "ho", "or", "use", "door", "die",
             "ban", "sun", "man", "bus", "bas", "tab", "jab", "ab", "kal", "din", "na", "ye", "die", "pe", "ki", "ka", "char"}

# ── Phonetic rules for everything else ──────────────────────────────────────────────────────────
_CONS = [  # longest first
    ("chh", "छ"), ("kh", "ख"), ("gh", "घ"), ("ch", "च"), ("jh", "झ"), ("th", "थ"), ("dh", "ध"), ("ph", "फ"), ("bh", "भ"),
    ("sh", "श"), ("ng", "ंग"), ("k", "क"), ("g", "ग"), ("c", "क"), ("j", "ज"), ("t", "त"), ("d", "द"), ("n", "न"), ("p", "प"),
    ("b", "ब"), ("m", "म"), ("y", "य"), ("r", "र"), ("l", "ल"), ("v", "व"), ("w", "व"), ("s", "स"), ("h", "ह"),
    ("f", "फ़"), ("z", "ज़"), ("q", "क़"), ("x", "क्स"),
]
_VOW = [  # (roman, independent, matra)
    ("aa", "आ", "ा"), ("ai", "ऐ", "ै"), ("au", "औ", "ौ"), ("ee", "ई", "ी"), ("ii", "ई", "ी"), ("oo", "ऊ", "ू"),
    ("uu", "ऊ", "ू"), ("a", "अ", ""), ("i", "इ", "ि"), ("u", "उ", "ु"), ("e", "ए", "े"), ("o", "ओ", "ो"),
]
_VIRAMA = "्"


def rules(word: str) -> str:
    """Casual Roman Hindi → Devanagari by sound (e.g. 'dosto' → दोस्तो, 'kahani' → कहानी)."""
    w = word.lower()
    out: list[str] = []
    i, prev_cons = 0, False
    while i < len(w):
        # vowels
        for rom, ind, mat in _VOW:
            if w.startswith(rom, i):
                last = i + len(rom) == len(w)
                if prev_cons:
                    if rom == "a" and last:
                        out.append("ा")                       # final -a is long: kiya → किया, accha → अच्छा
                    elif rom == "i" and last:
                        out.append("ी")                       # final -i is long: bhi → भी, kahani → कहानी
                    else:
                        out.append(mat)
                else:
                    out.append(ind)
                i += len(rom)
                prev_cons = False
                break
        else:
            for rom, dev in _CONS:
                if w.startswith(rom, i):
                    if prev_cons and not dev.startswith("ं"):
                        out.append(_VIRAMA)                   # consonant cluster: dosto → दोस्तो
                    out.append(dev)
                    i += len(rom)
                    prev_cons = True                          # "ng" (ंग) also ends in a consonant: bataunga → …ंगा
                    break
            else:
                out.append(w[i])                              # unexpected char: keep
                i += 1
                prev_cons = False
    return "".join(out)


@lru_cache(maxsize=20000)
def _english_zipf(word: str) -> float:
    try:
        from wordfreq import zipf_frequency
    except ImportError:  # pragma: no cover
        return 0.0
    return zipf_frequency(word, "en")


def _is_brand(word: str) -> bool:
    # AiWazz, YouTube, iPhone, OTP, UPI: mixed case or all caps (2+ letters) → keep as written
    return any(c.isupper() for c in word[1:]) or (len(word) >= 2 and word.isupper())


_WORD = re.compile(r"[A-Za-z]+")
_SENT_SPLIT = re.compile(r"([.!?।\n]+)")


def _english_compound(lw: str) -> bool:
    """voiceover, livestream, smartphone: two common English words glued together."""
    return any(_english_zipf(lw[:i]) >= 4.0 and _english_zipf(lw[i:]) >= 4.0 for i in range(3, len(lw) - 2))


def _classify(word: str) -> str:
    lw = word.lower()
    if _is_brand(word):
        return "keep"
    if lw in AMBIGUOUS:
        return "ambiguous"
    if lw in LEXICON:
        return "hindi"
    if _english_zipf(lw) >= 3.5 or (len(lw) >= 7 and _english_compound(lw)):
        return "english"
    return "hindi"


def _convert_sentence(sentence: str) -> str:
    words = _WORD.findall(sentence)
    kinds = [_classify(w) for w in words]
    hindi = sum(k == "hindi" for k in kinds)
    english = sum(k == "english" for k in kinds)
    ambiguous_is_hindi = hindi >= english
    it = iter(kinds)

    def repl(m: re.Match) -> str:
        w, kind = m.group(0), next(it)
        lw = w.lower()
        if kind == "keep" or kind == "english" or (kind == "ambiguous" and not ambiguous_is_hindi):
            return w
        return LEXICON.get(lw) or rules(lw)

    return _WORD.sub(repl, sentence)


def to_devanagari(text: str) -> str:
    """Convert Roman Hindi words to Devanagari; leave English words, brands, numbers, Devanagari and punctuation."""
    if not _WORD.search(text):
        return text
    # split keeps the separators (odd indexes), so the text is preserved exactly apart from converted words
    parts = _SENT_SPLIT.split(text)
    return "".join(p if i % 2 else _convert_sentence(p) for i, p in enumerate(parts))


def latin_share(text: str) -> float:
    """Share of letters that are Latin (used by the UI hint 'looks like Hinglish')."""
    latin = sum(c.isascii() and c.isalpha() for c in text)
    dev = sum("ऀ" <= c <= "ॿ" for c in text)
    return latin / (latin + dev) if latin + dev else 0.0
