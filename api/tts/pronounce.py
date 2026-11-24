"""Pronunciation fixes, applied to the script before synthesis (characters are always counted on the original text).

Priority (first match wins, each piece of text is replaced at most once):
  1. inline syntax in the script:  [word](say-as)
  2. `pronunciations` sent with the request (API)
  3. the user's own list (Settings → Pronunciations)
  4. the global list (admin)
Matching is case-insensitive and whole-word (a word is not matched inside a longer word; works for symbols too).
Replaced text is protected: Hinglish transliteration only converts the parts that were not replaced.
"""
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

MAX_WORD = 64
MAX_SAY_AS = 128
MAX_PER_REQUEST = 100
MAX_PER_USER = 500
INLINE = re.compile(r"\[([^\[\]\n]{1,64})\]\(([^()\n]{1,128})\)")
_WORDCH = r"[\wऀ-ॿ]"


@dataclass(frozen=True)
class Entry:
    word: str
    say_as: str


@dataclass
class Piece:
    text: str
    fixed: bool   # True = replaced by a pronunciation (never transliterated or replaced again)


def clean_word(word: str) -> str:
    return " ".join(word.split())


def check_entry(word: str, say_as: str) -> str | None:
    """Problem with an entry, or None if it is fine."""
    w, s = clean_word(word), " ".join(say_as.split())
    if not w or not s:
        return "Both the word and how to say it are needed"
    if len(w) > MAX_WORD or len(s) > MAX_SAY_AS:
        return f"Keep the word under {MAX_WORD} and the pronunciation under {MAX_SAY_AS} characters"
    if any(c in w + s for c in "[]()\n"):
        return "Brackets and line breaks aren't allowed here"
    if w.lower() == s.lower():
        return "The pronunciation is the same as the word"
    return None


def _merge(entries: Iterable[Entry]) -> dict[str, str]:
    """lowercase word → say-as; earlier entries win."""
    out: dict[str, str] = {}
    for e in entries:
        k = clean_word(e.word).lower()
        if k and k not in out:
            out[k] = " ".join(e.say_as.split())
    return out


def _pattern(words: Iterable[str]) -> re.Pattern | None:
    words = sorted(words, key=len, reverse=True)   # longest first: "GST number" before "GST"
    if not words:
        return None
    alt = "|".join(r"\s+".join(re.escape(part) for part in w.split(" ")) for w in words)
    return re.compile(rf"(?<!{_WORDCH})(?:{alt})(?!{_WORDCH})", re.IGNORECASE)


def apply(text: str, entries: Iterable[Entry] = ()) -> list[Piece]:
    """Split the script into pieces: replaced (fixed) and untouched text."""
    pieces: list[Piece] = []
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            pieces.append(Piece(text[pos:m.start()], False))
        say = " ".join(m.group(2).split())
        pieces.append(Piece(say, True) if say else Piece(m.group(1), False))
        pos = m.end()
    if pos < len(text):
        pieces.append(Piece(text[pos:], False))

    table = _merge(entries)
    pat = _pattern(table)
    if pat is None:
        return pieces
    out: list[Piece] = []
    for p in pieces:
        if p.fixed:
            out.append(p)
            continue
        pos = 0
        for m in pat.finditer(p.text):
            if m.start() > pos:
                out.append(Piece(p.text[pos:m.start()], False))
            out.append(Piece(table[" ".join(m.group(0).split()).lower()], True))
            pos = m.end()
        if pos < len(p.text):
            out.append(Piece(p.text[pos:], False))
    return out


_PH = re.compile("\ue000(\\d+)\ue001")


def render(pieces: list[Piece], convert: Callable[[str], str] | None = None) -> str:
    """Join the pieces; `convert` (e.g. Hinglish → Devanagari) runs on the untouched text only. It sees the whole
    script at once (replaced parts become private-use placeholders), so sentence context is kept."""
    if convert is None:
        return "".join(p.text for p in pieces)
    fixed: list[str] = []
    marked = []
    for p in pieces:
        if p.fixed:
            marked.append(f"\ue000{len(fixed)}\ue001")
            fixed.append(p.text)
        else:
            marked.append(p.text.replace("\ue000", "").replace("\ue001", ""))
    return _PH.sub(lambda m: fixed[int(m.group(1))], convert("".join(marked)))


def strip_inline(text: str) -> str:
    """The script as a person reads it: [word](say-as) → word (used for the history excerpt)."""
    return INLINE.sub(lambda m: m.group(1), text)


# Seeded into the global list by the migration (admin can edit). ₹ is built in (tts/text.normalize), by language.
SEED = [Entry("AiWazz", "Ai Wazz"), Entry("GST", "G S T"), Entry("UPI", "U P I"), Entry("API", "A P I")]
