"""Unicode helpers: grapheme clusters (approximation of UAX #29 sufficient for chat text), RTL effects."""
from __future__ import annotations

import unicodedata

ZWJ = "‍"
VS = ("︎", "️")
KEYCAP = "⃣"
RLO, PDF = "‮", "‬"


def _is_extender(ch: str) -> bool:
    cp = ord(ch)
    return (unicodedata.combining(ch) > 0 or ch in VS or ch == KEYCAP or 0x1F3FB <= cp <= 0x1F3FF   # skin tones
            or 0xE0020 <= cp <= 0xE007F                                                              # tag sequences (flags)
            or unicodedata.category(ch) in ("Mn", "Me"))


def _is_regional(ch: str) -> bool:
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def graphemes(text: str) -> list[str]:
    """Split text into user-perceived characters: base + combining marks, emoji ZWJ sequences, flags, keycaps."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        cl = text[i]
        i += 1
        if _is_regional(cl) and i < n and _is_regional(text[i]):
            cl += text[i]
            i += 1
        while i < n:
            ch = text[i]
            if _is_extender(ch):
                cl += ch
                i += 1
            elif ch == ZWJ and i + 1 < n:
                cl += ch + text[i + 1]
                i += 2
            else:
                break
        out.append(cl)
    return out


def reverse_graphemes(text: str) -> str:
    """Visual right-to-left: reverse user-perceived characters (emoji and accents stay intact)."""
    return "".join(reversed(graphemes(text)))


def rlo(text: str) -> str:
    """Wrap text in RIGHT-TO-LEFT OVERRIDE so clients render it right to left."""
    return RLO + text + PDF
