"""AI Twin (AI-двойник): a per-user persona that answers in the owner's style.

* Modes: ``auto`` (send, always labelled as AI), ``manual`` (draft with Send/Another/Reject buttons),
  ``draft`` (suggestion only, nothing can be sent from it), ``disabled``.
* Style learning uses **only examples the owner explicitly provided** (``.twin learn`` / panel); stored per user,
  never mixed with other users' data, deletable at any time.
* The twin never claims to be human when asked and auto replies carry the AI disclosure line.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..database.db import dumps, loads
from .prompts import LANG_NAMES, SAFETY, STYLE_PROMPTS

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

MODES = ("auto", "manual", "draft", "disabled")
LENGTHS = ("short", "medium", "long")
PERSONAS = ("neutral", "male", "female")
STYLES = ("friendly", "professional", "funny", "smart", "short", "creative")
MAX_EXAMPLES = 30

DEFAULTS: dict[str, Any] = {
    "mode": "disabled", "name": None, "language": "auto", "manner": None, "style": "friendly", "formality": 50, "humor": 30,
    "length": "medium", "emoji": 30, "slang": 10, "profanity_filter": True, "reply_delay_sec": 0, "active_from": None,
    "active_to": None, "model": None, "custom_prompt": None, "persona": "neutral", "examples": [], "consent_at": None,
}
LIMITS = {"formality": (0, 100), "humor": (0, 100), "emoji": (0, 100), "slang": (0, 100), "reply_delay_sec": (0, 300)}


def _level(v: int, words: tuple[str, str, str]) -> str:
    return words[0] if v < 34 else (words[1] if v < 67 else words[2])


def twin_system(p: dict[str, Any], owner_name: str, language: str, extra_note: str | None = None) -> str:
    lang = p["language"] if p["language"] != "auto" else language
    length = {"short": "1-2 short sentences", "medium": "1-4 sentences", "long": "up to 6 sentences"}[p["length"]]
    persona = {"male": "Use masculine grammatical forms where the language needs gender.",
               "female": "Use feminine grammatical forms where the language needs gender.", "neutral": ""}[p["persona"]]
    parts = [
        f"You are the AI twin of {owner_name}" + (f" (twin name: {p['name']})" if p.get("name") else "") +
        ". You reply in a private Telegram chat in the owner's personal voice and style while they are busy.",
        STYLE_PROMPTS.get(p["style"], ""),
        f"Formality: {_level(p['formality'], ('casual', 'neutral', 'formal'))}. Humor: {_level(p['humor'], ('none', 'light', 'playful'))}. "
        f"Emoji: {_level(p['emoji'], ('almost never', 'sometimes', 'often'))}. Slang: {_level(p['slang'], ('avoid', 'a little', 'natural'))}.",
        f"Reply in {LANG_NAMES.get(lang, LANG_NAMES['auto'])}. Length: {length}. No Markdown.",
        persona,
        "Never use profanity, even if the other person does." if p["profanity_filter"] else "",
        "If someone asks whether they talk to a human or a bot, say honestly that this is the owner's AI assistant.",
        "If the message needs the owner's personal decision, money, meetings or promises, say the owner will answer personally.",
    ]
    if p.get("manner"):
        parts.append("Manner described by the owner: " + str(p["manner"])[:500])
    if p.get("examples"):
        parts.append("Examples of how the owner writes (style reference only, do not copy facts):\n- " +
                     "\n- ".join(str(e)[:300] for e in p["examples"][-15:]))
    if extra_note:
        parts.append("Context: " + extra_note)
    if p.get("custom_prompt"):
        parts.append("Owner's custom instructions:\n" + str(p["custom_prompt"])[:2000])
    parts.append(SAFETY)
    return "\n\n".join(x for x in parts if x)


class TwinService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app

    async def get(self, user_id: int) -> dict[str, Any]:
        row = await self.app.db.fetchone("SELECT * FROM ai_twin_profiles WHERE user_id=?", (user_id,))
        if row is None:
            return dict(DEFAULTS)
        out = dict(DEFAULTS)
        for k in DEFAULTS:
            if k == "examples":
                out[k] = loads(row.get("examples_json"), []) or []
            elif k in row:
                out[k] = row[k]
        out["profanity_filter"] = bool(out["profanity_filter"])
        return out

    async def update(self, user_id: int, **values: Any) -> dict[str, Any]:
        cur = await self.get(user_id)
        for k, v in values.items():
            if k not in DEFAULTS or k in ("examples", "consent_at"):
                raise ValueError(f"field not editable: {k}")
            if k == "mode" and v not in MODES:
                raise ValueError("invalid mode")
            if k == "length" and v not in LENGTHS:
                raise ValueError("invalid length")
            if k == "persona" and v not in PERSONAS:
                raise ValueError("invalid persona")
            if k == "style" and v not in STYLES:
                raise ValueError("invalid style")
            if k == "language" and v not in LANG_NAMES:
                raise ValueError("invalid language")
            if k in LIMITS:
                lo, hi = LIMITS[k]
                v = max(lo, min(hi, int(v)))
            if k in ("active_from", "active_to") and v is not None:
                hh, _, mm = str(v).partition(":")
                if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
                    raise ValueError("time must be HH:MM")
                v = f"{int(hh):02d}:{int(mm):02d}"
            if k in ("name", "manner", "model"):
                v = (str(v).strip()[:60] or None) if v is not None else None
            if k == "custom_prompt":
                v = (str(v).strip()[:2000] or None) if v is not None else None
            if k == "profanity_filter":
                v = bool(v)
            cur[k] = v
        await self._save(user_id, cur)
        return cur

    async def _save(self, user_id: int, p: dict[str, Any]) -> None:
        cols = [k for k in DEFAULTS if k != "examples"]
        vals = [(1 if p[k] else 0) if k == "profanity_filter" else p[k] for k in cols]
        await self.app.db.execute(
            f"INSERT INTO ai_twin_profiles(user_id, {', '.join(cols)}, examples_json, updated_at) VALUES (?, {', '.join('?' * len(cols))}, ?, ?) "
            f"ON CONFLICT(user_id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols)}, examples_json=excluded.examples_json, "
            "updated_at=excluded.updated_at", (user_id, *vals, dumps(p["examples"]), int(time.time())))

    async def add_example(self, user_id: int, text: str) -> int:
        """Voluntarily provided example of the owner's writing (explicit consent is recorded)."""
        text = (text or "").strip()
        if not 2 <= len(text) <= 500:
            raise ValueError("example must be 2..500 characters")
        p = await self.get(user_id)
        p["examples"] = (p["examples"] + [text])[-MAX_EXAMPLES:]
        p["consent_at"] = p.get("consent_at") or int(time.time())
        await self._save(user_id, p)
        await self.app.audit.log("ai_twin.example_added", actor_id=user_id, target_type="ai_twin", target_id=user_id)
        return len(p["examples"])

    async def clear_examples(self, user_id: int) -> None:
        p = await self.get(user_id)
        p["examples"], p["consent_at"] = [], None
        await self._save(user_id, p)

    def is_active_now(self, p: dict[str, Any], tz_name: str) -> bool:
        if not p.get("active_from") or not p.get("active_to"):
            return True
        from ..core.timeutil import local_dt
        now = local_dt(None, tz_name).strftime("%H:%M")
        a, b = p["active_from"], p["active_to"]
        return a <= now < b if a <= b else (now >= a or now < b)

    async def preview(self, user_id: int, incoming: str, settings: dict[str, Any]) -> str:
        """Playground: what the twin would answer (nothing is sent anywhere)."""
        from ..security.sanitize import wrap_untrusted
        p = await self.get(user_id)
        owner = (await self.app.users.get(user_id) or {}).get("first_name") or "Owner"
        eff = await self.app.ai.effective(user_id, settings)
        res = await self.app.ai.complete(user_id, [{"role": "user", "content": wrap_untrusted(incoming)}],
                                         system=twin_system(p, owner, eff["language"]), kind="twin_preview", provider=eff["provider"],
                                         model=p.get("model") or eff["model"], max_tokens=300, temperature=eff["temperature"])
        return res.text.strip()
