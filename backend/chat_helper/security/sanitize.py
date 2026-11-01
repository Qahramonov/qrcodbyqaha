"""Input sanitization: HTML escaping, safe file names/paths, prompt-injection hardening."""
from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def safe_filename(name: str, default: str = "file") -> str:
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    name = _SAFE_NAME.sub("_", name).strip("._")[:80]
    return name or default


def safe_join(base: Path, *parts: str) -> Path:
    """Join paths and guarantee the result stays inside ``base`` (path traversal protection)."""
    base_r = base.resolve()
    target = base_r.joinpath(*parts).resolve()
    if base_r != target and base_r not in target.parents:
        raise ValueError("path traversal blocked")
    return target


_INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|above|system)",
    r"(reveal|show|print|repeat) (your |the )?(system prompt|instructions|hidden prompt)",
    r"you are now (?:dan|in developer mode)",
    r"игнорируй (все )?(предыдущие|прошлые) (инструкции|указания)",
    r"(покажи|выведи|раскрой) (свой |системный )?(промпт|инструкции)",
    r"oldingi (ko'rsatmalarni|buyruqlarni) e'tiborsiz",
]
_INJ = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def injection_score(text: str) -> int:
    return len(_INJ.findall(text or ""))


def wrap_untrusted(text: str, label: str = "message") -> str:
    """Wrap third-party text so the model treats it as data, never as instructions."""
    t = (text or "").replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"<<<{label}\n{t}\n{label}>>>"


def clip(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: n - 1] + "…"
