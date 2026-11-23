"""Text preparation: normalise whitespace and split into paragraphs → sentences."""
import re

# Sentence end: . ! ? and the Devanagari danda (।) / double danda (॥), plus any closing quotes/brackets.
_SENT_END = re.compile(r"(?:(?<=[.!?।॥])|(?<=[.!?।॥][\"'”’)\]]))\s+")
_CLAUSE = re.compile(r"(?<=[,;:])\s+")
_PARA = re.compile(r"\n\s*\n+")
# Kokoro truncates input above 510 phonemes; keep each piece well below that.
MAX_PIECE = 250


def _wrap_words(s: str, limit: int) -> list[str]:
    out, cur = [], ""
    for word in s.split(" "):
        if cur and len(cur) + 1 + len(word) > limit:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    return out


def _limit(s: str) -> list[str]:
    if len(s) <= MAX_PIECE:
        return [s]
    pieces: list[str] = []
    for clause in _CLAUSE.split(s):
        pieces.extend(_wrap_words(clause, MAX_PIECE) if len(clause) > MAX_PIECE else [clause])
    return [p for p in pieces if p]


def split_text(text: str) -> list[list[str]]:
    """Return paragraphs, each a list of non-empty sentences (each ≤ MAX_PIECE chars where possible)."""
    paragraphs = []
    for para in _PARA.split(text.strip()):
        para = re.sub(r"\s+", " ", para).strip()
        sentences = [p for raw in _SENT_END.split(para) if (s := raw.strip()) for p in _limit(s)]
        if sentences:
            paragraphs.append(sentences)
    return paragraphs


# ── Numbers and currency (espeak drops "₹" and reads "2,00,000" digit by digit in Hindi) ──
_RUPEE = re.compile(r"(?:₹|\bRs\.?|\bINR)\s?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def normalize(text: str, lang: str) -> str:
    """₹499 → "499 रुपये" / "499 rupees"; 2,00,000 → 200000 (read as "दो लाख"); Hindi 12.5 → "12 दशमलव 5"."""
    hindi = lang == "h"
    text = _RUPEE.sub(lambda m: f"{m.group(1)} {'रुपये' if hindi else 'rupees'}", text)
    text = _DIGIT_COMMA.sub("", text)
    if hindi:
        text = _DECIMAL.sub(" दशमलव ", text)
    return text
