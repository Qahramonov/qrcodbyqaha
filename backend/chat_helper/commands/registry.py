"""Command Registry: every command is declared once with full metadata and a real handler."""
from __future__ import annotations

import re

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..localization import has, tr

Handler = Callable[[Any], Awaitable[None]]

CATEGORIES: dict[str, tuple[str, str]] = {
    # id: (emoji, translation key)
    "afk": ("💤", "registry.categories.afk"),
    "ai": ("🧠", "registry.categories.ai_assistent"),
    "voice": ("🎙", "registry.categories.voice_studio"),
    "media": ("🎬", "registry.categories.media_studio"),
    "games": ("🎮", "registry.categories.igry"),
    "text": ("⌨️", "registry.categories.tekstovye_instrumenty"),
    "profile": ("👤", "registry.categories.profil"),
    "autoreply": ("💬", "registry.categories.avtootvetchik"),
    "chat": ("🎛", "registry.categories.upravlenie_chatom"),
    "system": ("⚙️", "registry.categories.sistema"),
}

_CYRILLIC = re.compile("[\u0400-\u04ff]")

PLAN_RANK = {"free": 0, "plus": 1, "pro": 2, "vip": 3}

# readiness statuses (feature matrix)
IMPLEMENTED = "IMPLEMENTED"
REQUIRES_API_KEY = "REQUIRES_API_KEY"
REQUIRES_PERMISSION = "REQUIRES_PERMISSION"
LIMITED_BY_TELEGRAM = "LIMITED_BY_TELEGRAM"
NOT_SUPPORTED = "NOT_SUPPORTED"


@dataclass
class CommandSpec:
    id: str
    category: str
    handler: Handler
    aliases: list[str] = field(default_factory=list)
    syntax: str = ""
    examples: list[str] = field(default_factory=list)
    rights: list[str] = field(default_factory=list)       # business rights required in business chats
    deps: list[str] = field(default_factory=list)         # ffmpeg | ai | ai_stt | ai_tts | network
    min_plan: str = "free"
    rate: tuple[int, int] = (20, 60)                      # calls per window seconds
    where: str = "any"                                    # any | business | private
    admin_only: bool = False
    needs_reply: bool = False
    sandbox_safe: bool = False                            # can run in APK "test" mode without sending
    status: str = IMPLEMENTED
    module: str = ""

    @property
    def name(self) -> str:
        return self.id

    # texts live in the localization catalogs: cmd.<id>.desc / cmd.<id>.notes
    def describe(self, lang: str) -> str:
        return tr(lang, f"cmd.{self.id}.desc")

    def notes(self, lang: str) -> str:
        return tr(lang, f"cmd.{self.id}.notes") if has(f"cmd.{self.id}.notes") else ""

    def syntax_for(self, lang: str) -> str:
        return tr(lang, f"cmd.{self.id}.syntax") if has(f"cmd.{self.id}.syntax") else self.syntax

    def examples_for(self, lang: str) -> list[str]:
        if has(f"cmd.{self.id}.examples"):
            return [x for x in tr(lang, f"cmd.{self.id}.examples").split("\n") if x]
        return list(self.examples)

    @property
    def ru(self) -> str:
        return self.describe("ru")

    @property
    def uz(self) -> str:
        return self.describe("uz")

    def aliases_for(self, lang: str) -> list[str]:
        """Aliases worth showing to a user of ``lang``: Cyrillic aliases are Russian words, shown to Russian users only
        (every alias keeps working for everyone)."""
        if lang == "ru":
            return list(self.aliases)
        return [a for a in self.aliases if not _CYRILLIC.search(a)]

    def to_dict(self, lang: str = "ru", prefix: str = ".") -> dict[str, Any]:
        return {
            "id": self.id, "name": prefix + self.id, "aliases": [prefix + a for a in self.aliases_for(lang)],
            "all_aliases": [prefix + a for a in self.aliases],
            "category": self.category, "description": self.describe(lang), "description_ru": self.ru,
            "description_uz": self.uz,
            "syntax": self.syntax_for(lang).replace(".", prefix, 1) if self.syntax_for(lang).startswith(".") else self.syntax_for(lang),
            "examples": self.examples_for(lang), "rights": self.rights, "deps": self.deps, "min_plan": self.min_plan,
            "rate": {"limit": self.rate[0], "window": self.rate[1]}, "where": self.where,
            "admin_only": self.admin_only, "needs_reply": self.needs_reply, "sandbox_safe": self.sandbox_safe,
            "status": self.status, "notes": self.notes(lang),
            "module": self.module or self.category,
        }


class Registry:
    def __init__(self) -> None:
        self.commands: dict[str, CommandSpec] = {}
        self._lookup: dict[str, str] = {}

    def add(self, spec: CommandSpec) -> CommandSpec:
        cid = spec.id.lower()
        if cid in self.commands:
            raise ValueError(f"duplicate command id {cid}")
        if not spec.module:
            spec.module = spec.category
        self.commands[cid] = spec
        for name in [cid, *spec.aliases]:
            key = name.lower()
            if key in self._lookup and self._lookup[key] != cid:
                raise ValueError(f"alias collision: {key} ({self._lookup[key]} vs {cid})")
            self._lookup[key] = cid
        return spec

    def command(self, id: str, category: str, **kw: Any) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self.add(CommandSpec(id=id, category=category, handler=fn, **kw))
            return fn
        return deco

    def resolve(self, name: str) -> CommandSpec | None:
        cid = self._lookup.get(name.lower())
        return self.commands.get(cid) if cid else None

    def by_category(self) -> dict[str, list[CommandSpec]]:
        out: dict[str, list[CommandSpec]] = {c: [] for c in CATEGORIES}
        for spec in self.commands.values():
            out.setdefault(spec.category, []).append(spec)
        return out

    def suggestions(self, name: str, n: int = 3) -> list[str]:
        import difflib
        return difflib.get_close_matches(name.lower(), list(self._lookup), n=n, cutoff=0.6)

    def __len__(self) -> int:
        return len(self.commands)


registry = Registry()
