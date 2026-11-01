"""AI orchestration: provider routing + fallback, timeouts, concurrency queue, quotas, budgets,
cost accounting, profiles, playground and model comparison."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..core.timeutil import today
from ..database.db import Database
from .memory import AIMemory
from .prompts import assistant_system
from .providers.adapters import AnthropicProvider, EchoProvider, GeminiProvider, OpenAIProvider
from .providers.base import AIResult, ImageInput, Provider, ProviderError

log = logging.getLogger(__name__)

# Estimated USD per 1M tokens (input, output). Estimates only — override via AI_PRICES in runtime settings.
PRICES: list[tuple[str, float, float]] = [
    ("gpt-5-nano", 0.05, 0.40), ("gpt-5-mini", 0.25, 2.00), ("gpt-5", 1.25, 10.0),
    ("gpt-4.1-nano", 0.10, 0.40), ("gpt-4.1-mini", 0.40, 1.60), ("gpt-4.1", 2.0, 8.0),
    ("gpt-4o-mini", 0.15, 0.60), ("gpt-4o", 2.5, 10.0),
    ("gemini-2.5-flash-lite", 0.10, 0.40), ("gemini-2.5-flash", 0.30, 2.50), ("gemini-2.5-pro", 1.25, 10.0),
    ("gemini", 0.30, 2.50),
    ("claude-haiku", 1.0, 5.0), ("claude-sonnet", 3.0, 15.0), ("claude-opus", 5.0, 25.0),
    ("whisper", 0.0, 0.0), ("echo", 0.0, 0.0),
]
STT_PRICE_PER_MIN = 0.006


class AIError(Exception):
    """User-facing AI error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    m = (model or "").lower()
    for prefix, pin, pout in PRICES:
        if m.startswith(prefix):
            return round(prompt_tokens / 1e6 * pin + completion_tokens / 1e6 * pout, 6)
    return round(prompt_tokens / 1e6 * 1.0 + completion_tokens / 1e6 * 3.0, 6)


class AIService:
    def __init__(self, db: Database, config: Any, quotas: Any, subs: Any, metrics: Any, events: Any, settings: Any) -> None:
        self.db = db
        self.config = config
        self.quotas = quotas
        self.subs = subs
        self.metrics = metrics
        self.events = events
        self.settings = settings
        self.memory = AIMemory(db)
        self.providers: dict[str, Provider] = {}
        self.sem = asyncio.Semaphore(max(1, config.ai_max_concurrency))
        self.waiting = 0
        self.in_flight = 0
        self.disabled: set[str] = set()
        self._build_providers()

    def _build_providers(self) -> None:
        c = self.config
        t = float(c.ai_timeout)
        self.providers = {
            "openai": OpenAIProvider(c.openai_api_key, c.openai_model, t, c.openai_base_url, c.openai_stt_model,
                                     c.openai_tts_model, c.openai_tts_voice),
            "gemini": GeminiProvider(c.gemini_api_key, c.gemini_model, t),
            "anthropic": AnthropicProvider(c.anthropic_api_key, c.anthropic_model, t),
            "compatible": OpenAIProvider(c.compat_api_key, c.compat_model, t, c.compat_base_url, name="compatible", compat=True),
        }
        if not c.compat_base_url:
            self.providers["compatible"].api_key = ""

    def register(self, provider: Provider) -> None:
        """Plug in an additional provider (extension point)."""
        self.providers[provider.name] = provider

    def enable_test_provider(self, mode: str = "ok") -> None:
        self.providers["echo"] = EchoProvider(mode, "echo-1")

    async def close(self) -> None:
        for p in self.providers.values():
            await p.close()

    # ---- availability ------------------------------------------------------------
    def configured(self, kind: str = "chat") -> list[Provider]:
        return [p for n, p in self.providers.items() if p.configured() and kind in p.supports and n not in self.disabled]

    def available(self, kind: str | None = None) -> bool:
        return bool(self.configured(kind or "chat"))

    def providers_status(self) -> list[dict[str, Any]]:
        return [{**p.info(), "disabled": n in self.disabled} for n, p in self.providers.items()]

    def order(self, kind: str, preferred: str | None = None) -> list[Provider]:
        provs = self.configured(kind)
        names = [p.name for p in provs]
        first = preferred if preferred and preferred != "auto" else self.config.ai_default_provider
        if first in names:
            provs.sort(key=lambda p: 0 if p.name == first else 1)
        return provs

    async def check_providers(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, p in self.providers.items():
            if not p.configured():
                out[name] = {"configured": False}
                continue
            t0 = time.monotonic()
            try:
                models = await asyncio.wait_for(p.list_models(), timeout=20)
                out[name] = {"configured": True, "ok": True, "latency_ms": int((time.monotonic() - t0) * 1000),
                             "models": models[:30], "model": p.model}
            except Exception as e:
                out[name] = {"configured": True, "ok": False, "error": str(e)[:200]}
        out["ok"] = any(v.get("ok") for v in out.values() if isinstance(v, dict))
        return out

    # ---- budgets & quotas -----------------------------------------------------------
    async def spent_today(self, user_id: int) -> float:
        return float(await self.db.fetchval("SELECT cost_usd FROM ai_costs WHERE user_id=? AND day=?", (user_id, today()), 0.0))

    async def _precheck(self, user_id: int, charge: bool) -> None:
        if not charge:
            return
        if await self.spent_today(0) >= self.config.ai_global_daily_budget_usd:
            raise AIError("global_budget", "Global daily AI budget reached")
        is_super = int(user_id) == int(self.config.super_admin_id)
        if not is_super and await self.spent_today(user_id) >= self.config.ai_user_daily_budget_usd:
            raise AIError("user_budget", "Your daily AI budget is used up")
        limit = await self.subs.limit(user_id, "ai_requests_day")
        ok, _used = await self.quotas.consume(f"ai:{user_id}", limit)
        if not ok:
            raise AIError("quota", f"Daily AI request limit reached ({limit})")

    async def _record(self, user_id: int, res: AIResult | None, kind: str, ok: bool, error: str | None, provider: str,
                      model: str | None, latency: int) -> None:
        now = int(time.time())
        pt = res.prompt_tokens if res else 0
        ct = res.completion_tokens if res else 0
        cost = res.cost if res else 0.0
        await self.db.execute(
            "INSERT INTO ai_usage(user_id, provider, model, kind, prompt_tokens, completion_tokens, cost_usd, latency_ms, ok, error, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (user_id, provider, model, kind, pt, ct, cost, latency, 1 if ok else 0, error, now))
        if ok:
            for uid in {0, int(user_id)}:
                await self.db.execute(
                    "INSERT INTO ai_costs(user_id, day, requests, tokens, cost_usd) VALUES (?,?,1,?,?) ON CONFLICT(user_id, day) "
                    "DO UPDATE SET requests=requests+1, tokens=tokens+excluded.tokens, cost_usd=cost_usd+excluded.cost_usd",
                    (uid, today(), pt + ct, cost))
            await self.metrics.incr("ai_requests", user_id)
            await self.metrics.incr("ai_tokens", user_id, pt + ct)
            await self.metrics.incr("ai_cost_usd", user_id, cost)
            await self.metrics.incr(f"ai_provider:{provider}")
        else:
            await self.metrics.incr("ai_errors", user_id)
        self.events.emit("ai_request", user_id=user_id, kind=kind, ok=ok, provider=provider, ms=latency,
                         level="info" if ok else "warning")

    # ---- core call -----------------------------------------------------------------
    async def complete(self, user_id: int, messages: list[dict[str, Any]], *, system: str | None = None, kind: str = "chat",
                       provider: str | None = None, model: str | None = None, max_tokens: int = 600,
                       temperature: float | None = None, images: list[ImageInput] | None = None, charge: bool = True,
                       timeout: float | None = None) -> AIResult:
        need = "vision" if images else "chat"
        provs = self.order(need, provider)
        if not provs:
            raise AIError("not_configured", "No AI provider configured")
        await self._precheck(user_id, charge)
        timeout = timeout or float(self.config.ai_timeout)
        last_err: Exception | None = None
        self.waiting += 1
        try:
            await asyncio.wait_for(self.sem.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            self.waiting -= 1
            raise AIError("busy", "AI queue is busy, try again later") from None
        self.waiting -= 1
        self.in_flight += 1
        try:
            for i, p in enumerate(provs):
                use_model = model if (model and i == 0) else (model if model and p.name == provider else None)
                t0 = time.monotonic()
                try:
                    res = await asyncio.wait_for(p.chat(messages, system=system, model=use_model, max_tokens=max_tokens,
                                                        temperature=temperature, images=images), timeout=timeout)
                    res.cost = estimate_cost(res.model, res.prompt_tokens, res.completion_tokens)
                    if not res.text:
                        raise ProviderError(p.name, "empty response")
                    await self._record(user_id, res, kind, True, None, p.name, res.model, res.latency_ms)
                    if i > 0:
                        res.extra["fallback_from"] = provs[0].name
                    return res
                except asyncio.TimeoutError:
                    last_err = ProviderError(p.name, "timeout")
                except ProviderError as e:
                    last_err = e
                except Exception as e:  # network errors
                    last_err = ProviderError(p.name, f"{type(e).__name__}")
                await self._record(user_id, None, kind, False, str(last_err)[:300], p.name, use_model or p.model,
                                   int((time.monotonic() - t0) * 1000))
                log.warning("AI provider %s failed: %s", p.name, str(last_err)[:200])
        finally:
            self.in_flight -= 1
            self.sem.release()
        raise AIError("provider_error", f"All AI providers failed: {last_err}")

    async def transcribe(self, user_id: int, audio: bytes, filename: str, mime: str, duration: int = 0,
                         language: str | None = None) -> AIResult:
        provs = self.order("stt")
        if not provs:
            raise AIError("not_configured", "No speech-to-text provider configured")
        await self._precheck(user_id, True)
        last: Exception | None = None
        for p in provs:
            t0 = time.monotonic()
            try:
                async with self.sem:
                    res = await asyncio.wait_for(p.transcribe(audio, filename, mime, language), timeout=float(self.config.ai_timeout) * 2)
                res.cost = round(max(1, duration) / 60 * STT_PRICE_PER_MIN, 6) if p.name == "openai" else \
                    estimate_cost(res.model, res.prompt_tokens, res.completion_tokens)
                await self._record(user_id, res, "stt", True, None, p.name, res.model, int((time.monotonic() - t0) * 1000))
                await self.metrics.incr("stt_seconds", user_id, duration)
                return res
            except Exception as e:
                last = e
                await self._record(user_id, None, "stt", False, str(e)[:300], p.name, None, int((time.monotonic() - t0) * 1000))
        raise AIError("provider_error", f"Speech recognition failed: {last}")

    async def tts(self, user_id: int, text: str, voice: str | None = None) -> bytes:
        provs = self.order("tts")
        if not provs:
            raise AIError("not_configured", "No text-to-speech provider configured")
        await self._precheck(user_id, True)
        p = provs[0]
        t0 = time.monotonic()
        try:
            async with self.sem:
                audio = await asyncio.wait_for(p.tts(text, voice), timeout=float(self.config.ai_timeout))
        except Exception as e:
            await self._record(user_id, None, "tts", False, str(e)[:300], p.name, None, int((time.monotonic() - t0) * 1000))
            raise AIError("provider_error", f"TTS failed: {e}") from None
        res = AIResult(text="", provider=p.name, model=getattr(p, "tts_model", None), cost=round(len(text) / 1e6 * 15.0, 6))
        await self._record(user_id, res, "tts", True, None, p.name, res.model, int((time.monotonic() - t0) * 1000))
        return audio

    # ---- profiles --------------------------------------------------------------------
    async def profiles(self, user_id: int) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM ai_profiles WHERE user_id=? ORDER BY is_active DESC, id", (user_id,))

    async def active_profile(self, user_id: int) -> dict[str, Any] | None:
        return await self.db.fetchone("SELECT * FROM ai_profiles WHERE user_id=? AND is_active=1 LIMIT 1", (user_id,))

    def validate_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        from ..services.settings import STYLES
        name = str(data.get("name") or "").strip()[:40]
        if not name:
            raise ValueError("name is required")
        provider = data.get("provider") or "auto"
        if provider != "auto" and provider not in self.providers:
            raise ValueError("unknown provider")
        mode = data.get("mode") or "friendly"
        if mode not in STYLES:
            raise ValueError("invalid mode")
        temp = data.get("temperature")
        if temp is not None:
            temp = float(temp)
            if not 0 <= temp <= 2:
                raise ValueError("temperature must be 0..2")
        mt = int(data.get("max_tokens") or 600)
        if not 50 <= mt <= 4000:
            raise ValueError("max_tokens must be 50..4000")
        return {"name": name, "provider": provider, "model": (data.get("model") or None) and str(data["model"])[:80],
                "mode": mode, "system_prompt": (data.get("system_prompt") or "")[:4000] or None, "temperature": temp,
                "max_tokens": mt, "language": str(data.get("language") or "auto")[:8]}

    async def create_profile(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        v = self.validate_profile(data)
        limit = await self.subs.limit(user_id, "ai_profiles")
        n = await self.db.fetchval("SELECT COUNT(*) FROM ai_profiles WHERE user_id=?", (user_id,), 0)
        if limit is not None and n >= limit:
            raise ValueError(f"profile limit reached ({limit})")
        now = int(time.time())
        pid = await self.db.execute(
            "INSERT INTO ai_profiles(user_id, name, provider, model, mode, system_prompt, temperature, max_tokens, language, is_active, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, v["name"], v["provider"], v["model"], v["mode"], v["system_prompt"], v["temperature"], v["max_tokens"],
             v["language"], 1 if n == 0 else 0, now, now))
        return await self.db.fetchone("SELECT * FROM ai_profiles WHERE id=?", (pid,))  # type: ignore[return-value]

    async def update_profile(self, user_id: int, pid: int, data: dict[str, Any]) -> dict[str, Any] | None:
        cur = await self.db.fetchone("SELECT * FROM ai_profiles WHERE id=? AND user_id=?", (pid, user_id))
        if not cur:
            return None
        v = self.validate_profile({**cur, **data})
        await self.db.execute("UPDATE ai_profiles SET name=?, provider=?, model=?, mode=?, system_prompt=?, temperature=?, max_tokens=?, "
                              "language=?, updated_at=? WHERE id=? AND user_id=?",
                              (v["name"], v["provider"], v["model"], v["mode"], v["system_prompt"], v["temperature"], v["max_tokens"],
                               v["language"], int(time.time()), pid, user_id))
        return await self.db.fetchone("SELECT * FROM ai_profiles WHERE id=?", (pid,))

    async def activate_profile(self, user_id: int, pid: int) -> bool:
        if not await self.db.fetchval("SELECT 1 FROM ai_profiles WHERE id=? AND user_id=?", (pid, user_id)):
            return False
        async with self.db.transaction() as tx:
            await tx.execute("UPDATE ai_profiles SET is_active=0 WHERE user_id=?", (user_id,))
            await tx.execute("UPDATE ai_profiles SET is_active=1 WHERE id=? AND user_id=?", (pid, user_id))
        return True

    async def delete_profile(self, user_id: int, pid: int) -> bool:
        return await self.db.rowcount("DELETE FROM ai_profiles WHERE id=? AND user_id=?", (pid, user_id)) > 0

    async def effective(self, user_id: int, settings: dict[str, Any]) -> dict[str, Any]:
        prof = await self.active_profile(user_id) or {}
        style = prof.get("mode") or settings.get("ai_style", "friendly")
        return {"provider": prof.get("provider") or "auto", "model": prof.get("model"), "style": style,
                "custom": prof.get("system_prompt"), "temperature": prof.get("temperature"),
                "max_tokens": prof.get("max_tokens") or 600,
                "language": prof.get("language") if prof.get("language") not in (None, "auto") else settings.get("ai_language", "auto")}

    # ---- assistant helpers --------------------------------------------------------
    async def ask(self, user_id: int, prompt: str, settings: dict[str, Any], *, task_system: str | None = None,
                  context: list[dict[str, Any]] | None = None, images: list[ImageInput] | None = None, kind: str = "chat",
                  max_tokens: int | None = None) -> AIResult:
        eff = await self.effective(user_id, settings)
        system = assistant_system(eff["style"], eff["language"], eff["custom"], task_system)
        msgs = list(context or []) + [{"role": "user", "content": prompt}]
        return await self.complete(user_id, msgs, system=system, kind=kind, provider=eff["provider"], model=eff["model"],
                                   max_tokens=max_tokens or eff["max_tokens"], temperature=eff["temperature"], images=images)

    async def playground(self, user_id: int, text: str, settings: dict[str, Any], profile: dict[str, Any] | None = None) -> AIResult:
        if profile:
            system = assistant_system(profile.get("mode", "friendly"), profile.get("language", "auto"), profile.get("system_prompt"))
            return await self.complete(user_id, [{"role": "user", "content": text}], system=system, kind="playground",
                                       provider=profile.get("provider"), model=profile.get("model"),
                                       max_tokens=int(profile.get("max_tokens") or 600), temperature=profile.get("temperature"))
        return await self.ask(user_id, text, settings, kind="playground")

    async def compare(self, user_id: int, text: str, settings: dict[str, Any], targets: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        eff = await self.effective(user_id, settings)
        system = assistant_system(eff["style"], eff["language"], eff["custom"])
        if not targets:
            targets = [{"provider": p.name, "model": p.model} for p in self.configured("chat")[:2]]
        if not targets:
            raise AIError("not_configured", "No AI provider configured")

        async def run(t: dict[str, str]) -> dict[str, Any]:
            try:
                r = await self.complete(user_id, [{"role": "user", "content": text}], system=system, kind="compare",
                                        provider=t.get("provider"), model=t.get("model"), max_tokens=eff["max_tokens"])
                return {"provider": r.provider, "model": r.model, "text": r.text, "latency_ms": r.latency_ms, "tokens": r.tokens,
                        "cost": r.cost}
            except Exception as e:
                return {"provider": t.get("provider"), "model": t.get("model"), "error": str(e)[:200]}
        return list(await asyncio.gather(*(run(t) for t in targets[:3])))

    async def usage_summary(self, user_id: int | None, days: int = 30) -> dict[str, Any]:
        uid = 0 if user_id is None else user_id
        row = await self.db.fetchone("SELECT requests, tokens, cost_usd FROM ai_costs WHERE user_id=? AND day=?", (uid, today()))
        series = await self.metrics.series("ai_requests", days, uid)
        cost_series = await self.metrics.series("ai_cost_usd", days, uid)
        by_provider = await self.db.fetchall(
            "SELECT provider, COUNT(*) AS requests, SUM(prompt_tokens+completion_tokens) AS tokens, SUM(cost_usd) AS cost, "
            "SUM(1-ok) AS errors FROM ai_usage WHERE (?=0 OR user_id=?) AND created_at > ? GROUP BY provider",
            (uid, uid, int(time.time()) - days * 86400))
        limit = await self.subs.limit(user_id, "ai_requests_day") if user_id else None
        return {"today_requests": (row or {}).get("requests", 0), "today_tokens": (row or {}).get("tokens", 0),
                "today_cost": float((row or {}).get("cost_usd", 0.0)), "daily_limit": limit,
                "daily_budget_usd": self.config.ai_global_daily_budget_usd if uid == 0 else self.config.ai_user_daily_budget_usd,
                "requests_series": series, "cost_series": cost_series, "by_provider": by_provider,
                "queue": {"waiting": self.waiting, "in_flight": self.in_flight, "max_concurrency": self.config.ai_max_concurrency},
                "cost_note": "Costs are estimates based on public per-token prices."}
