"""Runtime configuration.

All secrets (BOT_TOKEN, AI keys) come ONLY from the environment / ``.env`` file.
Nothing secret is ever hard-coded, logged or shipped to the Android app.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

try:  # python-dotenv is optional at import time (tests run without .env)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]


def _bool(v: Any, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(v: Any, default: int) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _float(v: Any, default: float) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


class Settings(BaseModel):
    # --- Telegram -----------------------------------------------------------------
    bot_token: str = ""
    super_admin_id: int = 8053614984
    owner_username: str = "libPM"
    bot_name: str = "Chat helper"
    polling_timeout: int = 30

    # --- Paths ----------------------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    db_path: Path | None = None
    log_level: str = "INFO"
    timezone: str = "Asia/Tashkent"

    # --- Behaviour ------------------------------------------------------------------
    default_lang: str = "ru"
    command_prefix: str = "."

    # --- Local API for the Android app ---------------------------------------------
    api_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8787
    api_remote_enabled: bool = False
    api_ssl_certfile: str = ""
    api_ssl_keyfile: str = ""
    access_token_ttl: int = 3600
    refresh_token_ttl: int = 30 * 24 * 3600
    pairing_code_ttl: int = 300
    secret_key: str = ""

    # --- AI providers ---------------------------------------------------------------
    ai_default_provider: str = "auto"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5-mini"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    compat_name: str = "compatible"
    compat_api_key: str = ""
    compat_base_url: str = ""
    compat_model: str = ""
    ai_timeout: int = 60
    ai_max_concurrency: int = 3
    ai_global_daily_budget_usd: float = 2.0
    ai_user_daily_budget_usd: float = 0.25

    # --- Media ------------------------------------------------------------------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    media_max_input_mb: int = 20
    media_max_duration: int = 180
    media_max_reverse_video: int = 60
    media_timeout: int = 120
    media_concurrency: int = 1
    media_font: str = ""

    # --- Data retention / backups -------------------------------------------------
    history_retention_days: int = 7
    log_retention_days: int = 30
    backup_keep: int = 7
    backup_interval_hours: int = 24

    # --- Payments (Telegram Stars) ------------------------------------------------
    payments_enabled: bool = False

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("command_prefix")
    @classmethod
    def _prefix(cls, v: str) -> str:
        v = (v or ".").strip()
        if not v or len(v) > 3 or any(c.isalnum() or c.isspace() for c in v):
            return "."
        return v

    @field_validator("default_lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        return v if v in ("ru", "uz") else "ru"

    # ------------------------------------------------------------------------------
    @property
    def database_path(self) -> Path:
        return self.db_path or (self.data_dir / "chat_helper.db")

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def assets_dir(self) -> Path:
        return PROJECT_DIR / "assets"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.tmp_dir, self.logs_dir, self.backups_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:  # pragma: no cover - some Android storages ignore chmod
            pass

    def load_or_create_secret(self) -> str:
        """Server-side pepper for token hashing. Generated once, never leaves the device."""
        if self.secret_key:
            return self.secret_key
        self.ensure_dirs()
        path = self.data_dir / "secret.key"
        if path.exists():
            self.secret_key = path.read_text().strip()
        else:
            self.secret_key = secrets.token_hex(32)
            path.write_text(self.secret_key)
            try:
                os.chmod(path, 0o600)
            except OSError:  # pragma: no cover
                pass
        return self.secret_key

    def secret_values(self) -> list[str]:
        """Values that must be redacted from every log line."""
        vals = [self.bot_token, self.openai_api_key, self.gemini_api_key,
                self.anthropic_api_key, self.compat_api_key, self.secret_key]
        return [v for v in vals if v and len(v) >= 8]

    def public_summary(self) -> dict[str, Any]:
        """Safe, secret-free description for diagnostics / API."""
        return {
            "bot_token_configured": bool(self.bot_token),
            "super_admin_id": self.super_admin_id,
            "api": {"host": self.api_host, "port": self.api_port,
                    "remote": self.api_remote_enabled,
                    "tls": bool(self.api_ssl_certfile and self.api_ssl_keyfile)},
            "ai": {
                "openai": bool(self.openai_api_key), "gemini": bool(self.gemini_api_key),
                "anthropic": bool(self.anthropic_api_key),
                "compatible": bool(self.compat_api_key and self.compat_base_url),
                "default": self.ai_default_provider,
            },
            "media": {"max_input_mb": self.media_max_input_mb, "max_duration": self.media_max_duration,
                      "timeout": self.media_timeout, "concurrency": self.media_concurrency},
            "retention_days": self.history_retention_days,
            "payments_enabled": self.payments_enabled,
            "timezone": self.timezone,
        }


_ENV_MAP: dict[str, tuple[str, Any]] = {
    "BOT_TOKEN": ("bot_token", str),
    "SUPER_ADMIN_ID": ("super_admin_id", int),
    "OWNER_USERNAME": ("owner_username", str),
    "POLLING_TIMEOUT": ("polling_timeout", int),
    "DATA_DIR": ("data_dir", Path),
    "DB_PATH": ("db_path", Path),
    "LOG_LEVEL": ("log_level", str),
    "TIMEZONE": ("timezone", str),
    "DEFAULT_LANG": ("default_lang", str),
    "COMMAND_PREFIX": ("command_prefix", str),
    "API_ENABLED": ("api_enabled", bool),
    "API_HOST": ("api_host", str),
    "API_PORT": ("api_port", int),
    "API_REMOTE_ENABLED": ("api_remote_enabled", bool),
    "API_SSL_CERTFILE": ("api_ssl_certfile", str),
    "API_SSL_KEYFILE": ("api_ssl_keyfile", str),
    "ACCESS_TOKEN_TTL": ("access_token_ttl", int),
    "REFRESH_TOKEN_TTL": ("refresh_token_ttl", int),
    "PAIRING_CODE_TTL": ("pairing_code_ttl", int),
    "SECRET_KEY": ("secret_key", str),
    "AI_DEFAULT_PROVIDER": ("ai_default_provider", str),
    "OPENAI_API_KEY": ("openai_api_key", str),
    "OPENAI_BASE_URL": ("openai_base_url", str),
    "OPENAI_MODEL": ("openai_model", str),
    "OPENAI_STT_MODEL": ("openai_stt_model", str),
    "OPENAI_TTS_MODEL": ("openai_tts_model", str),
    "OPENAI_TTS_VOICE": ("openai_tts_voice", str),
    "GEMINI_API_KEY": ("gemini_api_key", str),
    "GEMINI_MODEL": ("gemini_model", str),
    "ANTHROPIC_API_KEY": ("anthropic_api_key", str),
    "ANTHROPIC_MODEL": ("anthropic_model", str),
    "COMPAT_NAME": ("compat_name", str),
    "COMPAT_API_KEY": ("compat_api_key", str),
    "COMPAT_BASE_URL": ("compat_base_url", str),
    "COMPAT_MODEL": ("compat_model", str),
    "AI_TIMEOUT": ("ai_timeout", int),
    "AI_MAX_CONCURRENCY": ("ai_max_concurrency", int),
    "AI_GLOBAL_DAILY_BUDGET_USD": ("ai_global_daily_budget_usd", float),
    "AI_USER_DAILY_BUDGET_USD": ("ai_user_daily_budget_usd", float),
    "FFMPEG_BIN": ("ffmpeg_bin", str),
    "FFPROBE_BIN": ("ffprobe_bin", str),
    "MEDIA_MAX_INPUT_MB": ("media_max_input_mb", int),
    "MEDIA_MAX_DURATION": ("media_max_duration", int),
    "MEDIA_MAX_REVERSE_VIDEO": ("media_max_reverse_video", int),
    "MEDIA_TIMEOUT": ("media_timeout", int),
    "MEDIA_CONCURRENCY": ("media_concurrency", int),
    "MEDIA_FONT": ("media_font", str),
    "HISTORY_RETENTION_DAYS": ("history_retention_days", int),
    "LOG_RETENTION_DAYS": ("log_retention_days", int),
    "BACKUP_KEEP": ("backup_keep", int),
    "BACKUP_INTERVAL_HOURS": ("backup_interval_hours", int),
    "PAYMENTS_ENABLED": ("payments_enabled", bool),
}


def load_settings(env_file: str | os.PathLike[str] | None = None, **overrides: Any) -> Settings:
    """Build settings from ``.env`` + process environment + explicit overrides."""
    if load_dotenv is not None:
        path = Path(env_file) if env_file else Path(os.environ.get("CHAT_HELPER_ENV", BACKEND_DIR / ".env"))
        if path.exists():
            load_dotenv(path, override=False)
    values: dict[str, Any] = {}
    defaults = Settings()
    for env, (field, typ) in _ENV_MAP.items():
        raw = os.environ.get(env)
        if raw is None or raw == "":
            continue
        if typ is bool:
            values[field] = _bool(raw, getattr(defaults, field))
        elif typ is int:
            values[field] = _int(raw, getattr(defaults, field))
        elif typ is float:
            values[field] = _float(raw, getattr(defaults, field))
        elif typ is Path:
            p = Path(raw).expanduser()
            values[field] = p if p.is_absolute() else (BACKEND_DIR / p)
        else:
            values[field] = raw.strip()
    values.update(overrides)
    s = Settings(**values)
    # Never listen publicly unless remote mode is explicitly enabled — and then only over TLS:
    # pairing codes and bearer tokens must not cross a network in plain HTTP.
    loopback = s.api_host in ("127.0.0.1", "localhost", "::1")
    if not loopback and not (s.api_remote_enabled and s.api_ssl_certfile and s.api_ssl_keyfile):
        s.api_host = "127.0.0.1"
    s.media_concurrency = max(1, min(s.media_concurrency, 4))
    s.ai_max_concurrency = max(1, min(s.ai_max_concurrency, 10))
    return s


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(s: Settings) -> None:
    global _settings
    _settings = s


def new_secret() -> str:
    return secrets.token_hex(32)


__all__ = ["Settings", "load_settings", "get_settings", "set_settings", "BACKEND_DIR", "PROJECT_DIR", "Field"]
