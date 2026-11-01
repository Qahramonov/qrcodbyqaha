"""Command Registry: every command is declared once with full metadata and a real handler."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

Handler = Callable[[Any], Awaitable[None]]

CATEGORIES: dict[str, tuple[str, str, str]] = {
    # id: (emoji, ru, uz)
    "afk": ("💤", "AFK", "AFK"),
    "ai": ("🧠", "AI-ассистент", "AI yordamchi"),
    "voice": ("🎙", "Voice Studio", "Voice Studio"),
    "media": ("🎬", "Media Studio", "Media Studio"),
    "games": ("🎮", "Игры", "O'yinlar"),
    "text": ("⌨️", "Текстовые инструменты", "Matn vositalari"),
    "profile": ("👤", "Профиль", "Profil"),
    "autoreply": ("💬", "Автоответчик", "Avtojavob"),
    "chat": ("🎛", "Управление чатом", "Chatni boshqarish"),
    "system": ("⚙️", "Система", "Tizim"),
}

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
    ru: str = ""
    uz: str = ""
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
    notes_ru: str = ""
    notes_uz: str = ""
    module: str = ""

    @property
    def name(self) -> str:
        return self.id

    def describe(self, lang: str) -> str:
        return self.uz if lang == "uz" and self.uz else self.ru

    def to_dict(self, lang: str = "ru", prefix: str = ".") -> dict[str, Any]:
        return {
            "id": self.id, "name": prefix + self.id, "aliases": [prefix + a for a in self.aliases],
            "category": self.category, "description": self.describe(lang), "description_ru": self.ru,
            "description_uz": self.uz, "syntax": self.syntax.replace(".", prefix, 1) if self.syntax.startswith(".") else self.syntax,
            "examples": self.examples, "rights": self.rights, "deps": self.deps, "min_plan": self.min_plan,
            "rate": {"limit": self.rate[0], "window": self.rate[1]}, "where": self.where,
            "admin_only": self.admin_only, "needs_reply": self.needs_reply, "sandbox_safe": self.sandbox_safe,
            "status": self.status, "notes": self.notes_uz if lang == "uz" and self.notes_uz else self.notes_ru,
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
