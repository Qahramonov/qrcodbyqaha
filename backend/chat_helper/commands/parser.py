"""Command parser: '.cmd args', '. cmd args', custom prefixes, quotes, case-insensitive names."""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    name: str
    raw_args: str
    args: list[str]
    prefix: str

    def arg(self, i: int, default: str = "") -> str:
        return self.args[i] if len(self.args) > i else default

    @property
    def first(self) -> str:
        return self.arg(0).lower()


_NAME_RE = re.compile(r"([^\W\d][\w]*)", re.UNICODE)


def parse(text: str | None, prefix: str = ".") -> ParsedCommand | None:
    if not text:
        return None
    stripped = text.lstrip()
    used_prefix = None
    for pfx in sorted({prefix, "/"} if prefix != "/" else {"/"}, key=len, reverse=True):
        if stripped.startswith(pfx):
            used_prefix = pfx
            break
    if used_prefix is None:
        return None
    rest = stripped[len(used_prefix):]
    # allow ". mute" (single space after prefix) but not "...." or ". . ."
    if rest.startswith(" "):
        rest = rest[1:]
        if rest.startswith(" "):
            return None
    m = _NAME_RE.match(rest)
    if not m:
        return None
    name = m.group(1).lower()
    if used_prefix == "/" and "@" in rest[m.end():m.end() + 1]:
        # /cmd@BotName -> drop the bot mention
        after = rest[m.end():]
        mention = re.match(r"@\w+", after)
        rest = rest[: m.end()] + (after[mention.end():] if mention else after)
    tail = rest[m.end():]
    if tail and not tail[0].isspace():
        return None  # ".com" style text glued to other symbols, e.g. ".com/path" -> not a command
    raw_args = tail.strip()
    return ParsedCommand(name=name, raw_args=raw_args, args=split_args(raw_args), prefix=used_prefix)


def split_args(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=True)
    except ValueError:
        return raw.split()


def split_pipe(raw: str) -> list[str]:
    return [p.strip() for p in raw.split("|")]
