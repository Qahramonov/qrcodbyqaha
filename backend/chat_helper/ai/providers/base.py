"""AI provider adapter interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class ProviderError(Exception):
    def __init__(self, provider: str, message: str, status: int | None = None, retryable: bool = True) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status
        self.retryable = retryable


@dataclass
class AIResult:
    text: str
    provider: str
    model: str | None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ImageInput:
    data: bytes
    mime: str = "image/jpeg"


class Provider:
    name = "base"
    supports: frozenset[str] = frozenset({"chat"})

    def __init__(self, api_key: str, model: str, timeout: float = 60.0, base_url: str = "") -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=15.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _raise_for(self, r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                data = r.json()
                msg = (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else data.get("error") or data
            except Exception:
                msg = r.text[:300]
            retry = r.status_code in (408, 409, 429) or r.status_code >= 500
            raise ProviderError(self.name, f"HTTP {r.status_code}: {str(msg)[:300]}", r.status_code, retryable=retry)

    async def chat(self, messages: list[dict[str, Any]], *, system: str | None = None, model: str | None = None,
                   max_tokens: int = 600, temperature: float | None = None, images: list[ImageInput] | None = None) -> AIResult:
        raise NotImplementedError

    async def transcribe(self, audio: bytes, filename: str, mime: str, language: str | None = None, model: str | None = None) -> AIResult:
        raise ProviderError(self.name, "speech-to-text not supported", retryable=False)

    async def tts(self, text: str, voice: str | None = None) -> bytes:
        raise ProviderError(self.name, "text-to-speech not supported", retryable=False)

    async def list_models(self) -> list[str]:
        return [self.model]

    def info(self) -> dict[str, Any]:
        return {"name": self.name, "configured": self.configured(), "model": self.model, "supports": sorted(self.supports),
                "base_url": self.base_url or None}
