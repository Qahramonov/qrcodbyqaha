"""Per-user settings with a typed schema (used by the bot panel, commands and the Android app)."""
from __future__ import annotations

import time
from typing import Any

from ..database.db import Database, dumps, loads

MODES = ("manual", "auto", "ai", "afk", "silent", "business", "hybrid")
STYLES = ("friendly", "professional", "funny", "smart", "short", "creative", "custom")
MSG_THEMES = ("classic", "minimal", "fancy", "emoji")
ANIM_TYPES = ("typewriter", "fast", "reverse", "wave", "glitch", "matrix", "dots", "progress", "countdown", "pulse", "heart",
              "slide", "rainbow", "counter", "reveal", "custom")

# key -> (type, default, extra)   extra: choices / (min,max) / maxlen
SCHEMA: dict[str, tuple[str, Any, Any]] = {
    "lang": ("choice", "ru", ("ru", "uz")),
    "prefix": ("str", ".", 3),
    "timezone": ("str", "", 64),
    "mode": ("choice", "manual", MODES),
    "automation_paused": ("bool", False, None),
    "delete_commands": ("bool", True, None),
    "owner_pause_minutes": ("int", 15, (0, 1440)),
    "notify_important": ("bool", True, None),
    "notify_new_chats": ("bool", False, None),
    "notify_disconnect": ("bool", True, None),
    "important_keywords": ("list", ["срочно", "важно", "urgent", "asap", "shoshilinch", "muhim"], 50),
    "msg_theme": ("choice", "classic", MSG_THEMES),
    # AFK
    "afk_cooldown_min": ("int", 30, (1, 1440)),
    "afk_auto_off": ("bool", True, None),
    "afk_ai": ("bool", False, None),
    "afk_notify_summary": ("bool", True, None),
    "afk_text_morning": ("str", "", 600),
    "afk_text_day": ("str", "", 600),
    "afk_text_evening": ("str", "", 600),
    "afk_text_night": ("str", "", 600),
    # Smart auto reply
    "autoreply_cooldown_sec": ("int", 300, (10, 86400)),
    "max_auto_replies_per_chat_day": ("int", 20, (1, 500)),
    "welcome_enabled": ("bool", False, None),
    "welcome_text": ("str", "", 1000),
    "work_start": ("str", "09:00", 5),
    "work_end": ("str", "18:00", 5),
    "work_days": ("list", [1, 2, 3, 4, 5], 7),
    "offhours_text": ("str", "", 1000),
    "handoff_keywords": ("list", ["оператор", "человек", "operator", "odam"], 30),
    # AI
    "ai_style": ("choice", "friendly", STYLES),
    "ai_language": ("str", "auto", 16),
    "ai_confirm": ("bool", False, None),
    "ai_debounce_sec": ("int", 6, (0, 60)),
    "ai_reply_limit_per_chat_day": ("int", 30, (1, 500)),
    "ai_disclosure": ("str", "🤖 AI", 120),   # "🤖 AI" = localized default (common.ai_disclosure)
    "ai_store_history": ("bool", True, None),
    "ai_context_messages": ("int", 12, (0, 40)),
    "ai_long_memory": ("bool", False, None),
    "ai_memory_ttl_days": ("int", 30, (1, 365)),
    "ai_auto_transcribe": ("bool", False, None),
    "ai_daily_summary": ("bool", False, None),
    "ai_priority_detection": ("bool", True, None),
    # Privacy
    "history_retention_days": ("int", 7, (0, 90)),
    "store_previews": ("bool", True, None),
    # Profile clock
    "clock_enabled": ("bool", False, None),
    "clock_field": ("choice", "bio", ("bio", "last_name")),
    "clock_format": ("str", "🕒 {time}", 64),
    "clock_interval_min": ("int", 30, (15, 1440)),
    # Games
    "games_enabled": ("bool", True, None),
    "duel_min_delay": ("int", 2, (1, 10)),
    "duel_max_delay": ("int", 6, (2, 20)),
    "game_timeout_sec": ("int", 120, (30, 900)),
    # Media
    "media_enabled": ("bool", True, None),
    "disabled_commands": ("list", [], 400),
    # v3: chat controls, mute, animations, activity
    "controls_place": ("choice", "chat", ("chat", "dm")),
    "mute_confirmed": ("bool", False, None),
    "chat_activity": ("bool", False, None),
    "anim_speed": ("choice", "fast", ("slow", "normal", "fast", "turbo")),
    "anim_type": ("choice", "typewriter", ANIM_TYPES),
    "anim_repeats": ("int", 1, (1, 3)),
    "favorite_commands": ("list", [], 12),
    "auto_prev_mode": ("choice", "auto", MODES),
}

USER_EDITABLE = set(SCHEMA)


class SettingsError(ValueError):
    pass


def coerce(key: str, value: Any) -> Any:
    if key not in SCHEMA:
        raise SettingsError(f"unknown setting: {key}")
    typ, _default, extra = SCHEMA[key]
    if typ == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str) and value.lower() in ("1", "true", "on", "yes", "да", "ha"):
            return True
        if isinstance(value, str) and value.lower() in ("0", "false", "off", "no", "нет", "yo'q"):
            return False
        raise SettingsError(f"{key}: expected boolean")
    if typ == "int":
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise SettingsError(f"{key}: expected integer") from None
        lo, hi = extra
        if not lo <= v <= hi:
            raise SettingsError(f"{key}: must be between {lo} and {hi}")
        return v
    if typ == "choice":
        if value not in extra:
            raise SettingsError(f"{key}: must be one of {', '.join(extra)}")
        return value
    if typ == "str":
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise SettingsError(f"{key}: expected string")
        if len(value) > extra:
            raise SettingsError(f"{key}: too long (max {extra})")
        if key == "prefix":
            v = value.strip() or "."
            if any(c.isalnum() or c.isspace() for c in v):
                raise SettingsError("prefix: use 1-3 symbols like . ! / -")
            return v
        if key in ("work_start", "work_end"):
            from ..core.timeutil import parse_hhmm
            hm = parse_hhmm(value)
            if not hm:
                raise SettingsError(f"{key}: expected HH:MM")
            return f"{hm[0]:02d}:{hm[1]:02d}"
        if key == "ai_disclosure" and not value.strip():
            raise SettingsError("ai_disclosure: AI disclosure text cannot be empty")
        if key == "timezone" and value:
            from ..core.timeutil import tz
            import datetime as _dt
            if tz(value) is _dt.timezone.utc and value.upper() not in ("UTC", "ETC/UTC"):
                raise SettingsError("timezone: unknown IANA timezone")
        return value
    if typ == "list":
        if not isinstance(value, list):
            raise SettingsError(f"{key}: expected list")
        if len(value) > extra:
            raise SettingsError(f"{key}: too many items")
        if key == "work_days":
            out = sorted({int(x) for x in value if str(x).isdigit() and 1 <= int(x) <= 7})
            return out
        return [str(x)[:64] for x in value]
    raise SettingsError(f"{key}: unsupported type")  # pragma: no cover


def schema_for_api() -> list[dict[str, Any]]:
    out = []
    for key, (typ, default, extra) in SCHEMA.items():
        item: dict[str, Any] = {"key": key, "type": typ, "default": default}
        if typ == "choice":
            item["choices"] = list(extra)
        elif typ == "int":
            item["min"], item["max"] = extra
        elif typ in ("str", "list"):
            item["max_len"] = extra
        out.append(item)
    return out


class SettingsService:
    def __init__(self, db: Database, default_lang: str = "ru", default_prefix: str = ".",
                 default_tz: str = "Asia/Tashkent") -> None:
        self.db = db
        self._cache: dict[int, dict[str, Any]] = {}
        self.default_lang = default_lang
        self.default_prefix = default_prefix
        self.default_tz = default_tz

    def defaults(self) -> dict[str, Any]:
        d = {k: (v[1].copy() if isinstance(v[1], list) else v[1]) for k, v in SCHEMA.items()}
        d["lang"] = self.default_lang
        d["prefix"] = self.default_prefix
        d["timezone"] = self.default_tz
        return d

    async def all(self, user_id: int) -> dict[str, Any]:
        if user_id in self._cache:
            return dict(self._cache[user_id])
        data = self.defaults()
        for row in await self.db.fetchall("SELECT key, value_json FROM user_settings WHERE user_id=?", (user_id,)):
            if row["key"] in SCHEMA:
                data[row["key"]] = loads(row["value_json"], data[row["key"]])
        if not data.get("timezone"):
            data["timezone"] = self.default_tz
        self._cache[user_id] = data
        return dict(data)

    async def get(self, user_id: int, key: str) -> Any:
        return (await self.all(user_id))[key]

    async def set(self, user_id: int, key: str, value: Any) -> Any:
        v = coerce(key, value)
        await self.db.execute(
            "INSERT INTO user_settings(user_id, key, value_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (user_id, key, dumps(v), int(time.time())))
        if user_id in self._cache:
            self._cache[user_id][key] = v
        return v

    async def update(self, user_id: int, values: dict[str, Any]) -> dict[str, Any]:
        clean = {k: coerce(k, v) for k, v in values.items()}
        now = int(time.time())
        async with self.db.transaction() as tx:
            for k, v in clean.items():
                await tx.execute(
                    "INSERT INTO user_settings(user_id, key, value_json, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(user_id, key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                    (user_id, k, dumps(v), now))
        self._cache.pop(user_id, None)
        return await self.all(user_id)

    async def reset(self, user_id: int) -> None:
        await self.db.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
        self._cache.pop(user_id, None)

    def invalidate(self, user_id: int | None = None) -> None:
        if user_id is None:
            self._cache.clear()
        else:
            self._cache.pop(user_id, None)
