"""Concrete adapters: OpenAI, OpenAI-compatible, Google Gemini, Anthropic Claude."""
from __future__ import annotations

import base64
import time
from typing import Any

from .base import AIResult, ImageInput, Provider, ProviderError

REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def _flatten(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        content = m.get("content") or ""
        if out and out[-1]["role"] == role and isinstance(content, str) and isinstance(out[-1]["content"], str):
            out[-1]["content"] += "\n" + content
        else:
            out.append({"role": role, "content": content})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(conversation continues)"})
    return out


class OpenAIProvider(Provider):
    name = "openai"
    supports = frozenset({"chat", "vision", "stt", "tts"})

    def __init__(self, api_key: str, model: str, timeout: float = 60.0, base_url: str = "https://api.openai.com/v1",
                 stt_model: str = "whisper-1", tts_model: str = "tts-1", tts_voice: str = "alloy", name: str | None = None,
                 compat: bool = False) -> None:
        super().__init__(api_key, model, timeout, base_url or "https://api.openai.com/v1")
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.tts_voice = tts_voice
        self.compat = compat
        if name:
            self.name = name
        if compat:
            self.supports = frozenset({"chat", "vision"})

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def chat(self, messages, *, system=None, model=None, max_tokens=600, temperature=None, images=None) -> AIResult:
        model = model or self.model
        msgs: list[dict[str, Any]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        flat = _flatten(messages)
        if images and flat:
            parts: list[dict[str, Any]] = [{"type": "text", "text": flat[-1]["content"] or "Describe the image."}]
            for img in images:
                parts.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{base64.b64encode(img.data).decode()}"}})
            flat[-1] = {"role": "user", "content": parts}
        msgs += flat
        body: dict[str, Any] = {"model": model, "messages": msgs}
        reasoning = (not self.compat) and model.startswith(REASONING_PREFIXES)
        if self.compat:
            body["max_tokens"] = max_tokens
        else:
            body["max_completion_tokens"] = max_tokens * (4 if reasoning else 1)
        if temperature is not None and not reasoning:
            body["temperature"] = temperature
        t0 = time.monotonic()
        r = await self.client.post(f"{self.base_url}/chat/completions", json=body, headers=self.headers)
        self._raise_for(r)
        data = r.json()
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(self.name, "malformed response") from None
        usage = data.get("usage") or {}
        return AIResult(text=text.strip(), provider=self.name, model=data.get("model") or model,
                        prompt_tokens=int(usage.get("prompt_tokens") or 0), completion_tokens=int(usage.get("completion_tokens") or 0),
                        latency_ms=int((time.monotonic() - t0) * 1000))

    async def transcribe(self, audio, filename, mime, language=None, model=None) -> AIResult:
        if self.compat:
            return await super().transcribe(audio, filename, mime, language, model)
        t0 = time.monotonic()
        data = {"model": model or self.stt_model}
        if language and language != "auto":
            data["language"] = language
        r = await self.client.post(f"{self.base_url}/audio/transcriptions", headers=self.headers,
                                   data=data, files={"file": (filename, audio, mime)})
        self._raise_for(r)
        text = (r.json() or {}).get("text", "")
        return AIResult(text=text.strip(), provider=self.name, model=data["model"], latency_ms=int((time.monotonic() - t0) * 1000))

    async def tts(self, text, voice=None) -> bytes:
        if self.compat:
            return await super().tts(text, voice)
        r = await self.client.post(f"{self.base_url}/audio/speech", headers=self.headers,
                                   json={"model": self.tts_model, "voice": voice or self.tts_voice, "input": text[:4000],
                                         "response_format": "opus"})
        self._raise_for(r)
        return r.content

    async def list_models(self) -> list[str]:
        r = await self.client.get(f"{self.base_url}/models", headers=self.headers)
        self._raise_for(r)
        return sorted(m.get("id", "") for m in (r.json().get("data") or []))[:200]


class GeminiProvider(Provider):
    name = "gemini"
    supports = frozenset({"chat", "vision", "stt"})
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key}

    def _contents(self, messages: list[dict[str, Any]], extra_parts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        contents = []
        for m in _flatten(messages):
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"] or " "}]})
        if extra_parts:
            if not contents:
                contents.append({"role": "user", "parts": []})
            contents[-1]["parts"] = extra_parts + contents[-1]["parts"]
        return contents

    async def _generate(self, model: str, body: dict[str, Any]) -> tuple[str, dict[str, Any], int]:
        t0 = time.monotonic()
        r = await self.client.post(f"{self.BASE}/models/{model}:generateContent", json=body, headers=self.headers)
        self._raise_for(r)
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(self.name, f"no candidates ({block or 'empty'})", retryable=False)
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text.strip(), data.get("usageMetadata") or {}, int((time.monotonic() - t0) * 1000)

    async def chat(self, messages, *, system=None, model=None, max_tokens=600, temperature=None, images=None) -> AIResult:
        model = model or self.model
        extra = [{"inline_data": {"mime_type": i.mime, "data": base64.b64encode(i.data).decode()}} for i in (images or [])]
        gen: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if temperature is not None:
            gen["temperature"] = temperature
        if "2.5-flash" in model:
            gen["thinkingConfig"] = {"thinkingBudget": 0}
        body: dict[str, Any] = {"contents": self._contents(messages, extra), "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        text, usage, ms = await self._generate(model, body)
        return AIResult(text=text, provider=self.name, model=model, prompt_tokens=int(usage.get("promptTokenCount") or 0),
                        completion_tokens=int(usage.get("candidatesTokenCount") or 0), latency_ms=ms)

    async def transcribe(self, audio, filename, mime, language=None, model=None) -> AIResult:
        model = model or self.model
        prompt = "Transcribe this audio verbatim. Output only the transcript text in the original language."
        body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
                                                         {"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 2000, **({"thinkingConfig": {"thinkingBudget": 0}} if "2.5-flash" in model else {})}}
        text, usage, ms = await self._generate(model, body)
        return AIResult(text=text, provider=self.name, model=model, prompt_tokens=int(usage.get("promptTokenCount") or 0),
                        completion_tokens=int(usage.get("candidatesTokenCount") or 0), latency_ms=ms)

    async def list_models(self) -> list[str]:
        r = await self.client.get(f"{self.BASE}/models", headers=self.headers)
        self._raise_for(r)
        return sorted(m.get("name", "").replace("models/", "") for m in (r.json().get("models") or []))[:200]


class AnthropicProvider(Provider):
    name = "anthropic"
    supports = frozenset({"chat", "vision"})
    BASE = "https://api.anthropic.com/v1"

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    async def chat(self, messages, *, system=None, model=None, max_tokens=600, temperature=None, images=None) -> AIResult:
        model = model or self.model
        msgs = _flatten(messages) or [{"role": "user", "content": "Hello"}]
        if images:
            blocks: list[dict[str, Any]] = [{"type": "image", "source": {"type": "base64", "media_type": i.mime,
                                                                        "data": base64.b64encode(i.data).decode()}} for i in images]
            blocks.append({"type": "text", "text": msgs[-1]["content"] or "Describe the image."})
            msgs[-1] = {"role": "user", "content": blocks}
        body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": msgs}
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = max(0.0, min(1.0, temperature))
        t0 = time.monotonic()
        r = await self.client.post(f"{self.BASE}/messages", json=body, headers=self.headers)
        self._raise_for(r)
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
        usage = data.get("usage") or {}
        return AIResult(text=text.strip(), provider=self.name, model=data.get("model") or model,
                        prompt_tokens=int(usage.get("input_tokens") or 0), completion_tokens=int(usage.get("output_tokens") or 0),
                        latency_ms=int((time.monotonic() - t0) * 1000))

    async def list_models(self) -> list[str]:
        r = await self.client.get(f"{self.BASE}/models", headers=self.headers)
        self._raise_for(r)
        return sorted(m.get("id", "") for m in (r.json().get("data") or []))[:200]


class EchoProvider(Provider):
    """Offline deterministic provider used by tests and the 'demo' mode (never configured by default)."""
    name = "echo"
    supports = frozenset({"chat", "vision", "stt", "tts"})

    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, messages, *, system=None, model=None, max_tokens=600, temperature=None, images=None) -> AIResult:
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if isinstance(last, list):
            last = " ".join(p.get("text", "") for p in last if isinstance(p, dict))
        if self.api_key == "fail":
            raise ProviderError(self.name, "simulated failure", 500)
        if self.api_key == "slow":
            import asyncio
            await asyncio.sleep(5)
        text = f"echo: {str(last)[:max_tokens]}"
        return AIResult(text=text, provider=self.name, model=model or self.model, prompt_tokens=len(str(last)) // 4 + 1,
                        completion_tokens=len(text) // 4 + 1, latency_ms=1)

    async def transcribe(self, audio, filename, mime, language=None, model=None) -> AIResult:
        return AIResult(text=f"transcript of {len(audio)} bytes", provider=self.name, model="echo-stt")

    async def tts(self, text, voice=None) -> bytes:
        raise ProviderError(self.name, "tts not available offline", retryable=False)
