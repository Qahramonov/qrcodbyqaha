"""AI Control Center, Smart Auto Reply rules, Automation Builder, Command Manager."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...ai.service import AIError
from ...automation.engine import ACTIONS, AI_LABELS, CONDITIONS, MEDIA_TYPES, RuleError, install_template, templates_for, triggers_for
from ...services.settings import MODES
from ..deps import APIError, Principal, get_app, principal, super_admin

router = APIRouter()


def _ai_error(e: AIError) -> APIError:
    status = {"not_configured": 503, "quota": 429, "user_budget": 429, "global_budget": 429, "busy": 503}.get(e.code, 502)
    return APIError(status, f"ai_{e.code}", str(e))


# ---- providers / usage -------------------------------------------------------------------

@router.get("/ai/providers", tags=["ai"])
async def providers(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": app.ai.providers_status(), "default": app.config.ai_default_provider, "available": app.ai.available(),
            "stt": app.ai.available("stt"), "tts": app.ai.available("tts")}


@router.post("/ai/providers/check", tags=["ai"])
async def providers_check(p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.ai.check_providers()


class AISystemPatch(BaseModel):
    disabled: list[str] | None = None
    default_provider: str | None = None
    global_daily_budget_usd: float | None = Field(default=None, ge=0, le=1000)
    user_daily_budget_usd: float | None = Field(default=None, ge=0, le=100)


@router.patch("/ai/system", tags=["ai"])
async def ai_system(body: AISystemPatch, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if body.disabled is not None:
        app.ai.disabled = {x for x in body.disabled if x in app.ai.providers}
    if body.default_provider is not None:
        if body.default_provider != "auto" and body.default_provider not in app.ai.providers:
            raise APIError(422, "invalid_provider", "Unknown provider")
        app.config.ai_default_provider = body.default_provider
    if body.global_daily_budget_usd is not None:
        app.config.ai_global_daily_budget_usd = body.global_daily_budget_usd
    if body.user_daily_budget_usd is not None:
        app.config.ai_user_daily_budget_usd = body.user_daily_budget_usd
    app.runtime.extra["ai"] = {"disabled": sorted(app.ai.disabled), "default": app.config.ai_default_provider,
                               "global_budget": app.config.ai_global_daily_budget_usd, "user_budget": app.config.ai_user_daily_budget_usd}
    await app.runtime.save()
    await app.audit.log("ai.system_update", actor_id=p.user_id, actor_type="app", **body.model_dump(exclude_none=True))
    return {"ok": True, "state": app.runtime.extra["ai"]}


@router.get("/ai/usage", tags=["ai"])
async def usage(scope: str = "self", p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    # the global scope exists only for the super admin; everyone else always gets their own usage
    return await app.ai.usage_summary(None if scope == "global" and p.is_super else p.user_id)


# ---- profiles ---------------------------------------------------------------------------------

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    provider: str = "auto"
    model: str | None = Field(default=None, max_length=80)
    mode: str = "friendly"
    system_prompt: str | None = Field(default=None, max_length=4000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=600, ge=50, le=4000)
    language: str = Field(default="auto", max_length=8)


@router.get("/ai/profiles", tags=["ai"])
async def profiles(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.ai.profiles(p.user_id)}


@router.post("/ai/profiles", tags=["ai"])
async def create_profile(body: ProfileIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.ai.create_profile(p.user_id, body.model_dump())


@router.patch("/ai/profiles/{pid}", tags=["ai"])
async def update_profile(pid: int, body: dict[str, Any], p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    row = await app.ai.update_profile(p.user_id, pid, body)
    if row is None:
        raise APIError(404, "not_found", "Profile not found")
    return row


@router.post("/ai/profiles/{pid}/activate", tags=["ai"])
async def activate_profile(pid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.ai.activate_profile(p.user_id, pid):
        raise APIError(404, "not_found", "Profile not found")
    return {"ok": True}


@router.delete("/ai/profiles/{pid}", tags=["ai"])
async def delete_profile(pid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.ai.delete_profile(p.user_id, pid):
        raise APIError(404, "not_found", "Profile not found")
    return {"ok": True}


class PlaygroundIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    profile_id: int | None = None
    profile: ProfileIn | None = None


@router.post("/ai/playground", tags=["ai"])
async def playground(body: PlaygroundIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    profile = None
    if body.profile is not None:
        profile = body.profile.model_dump()
    elif body.profile_id:
        profile = next((x for x in await app.ai.profiles(p.user_id) if x["id"] == body.profile_id), None)
        if profile is None:
            raise APIError(404, "not_found", "Profile not found")
    try:
        r = await app.ai.playground(p.user_id, body.prompt, await app.settings.all(p.user_id), profile)
    except AIError as e:
        raise _ai_error(e) from None
    return {"text": r.text, "provider": r.provider, "model": r.model, "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "cost_usd": r.cost, "latency_ms": r.latency_ms, "estimated_tokens_in": max(1, len(body.prompt) // 4)}


class CompareIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    targets: list[dict[str, str]] | None = None


@router.post("/ai/compare", tags=["ai"])
async def compare(body: CompareIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return {"items": await app.ai.compare(p.user_id, body.prompt, await app.settings.all(p.user_id), body.targets)}
    except AIError as e:
        raise _ai_error(e) from None


class MemoryIn(BaseModel):
    content: str = Field(min_length=2, max_length=1000)


@router.get("/ai/memory", tags=["ai"])
async def memory(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.ai.memory.list(p.user_id, 300), "long_memory": await app.settings.get(p.user_id, "ai_long_memory")}


@router.post("/ai/memory", tags=["ai"])
async def add_memory(body: MemoryIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    limit = await app.subs.limit(p.user_id, "ai_memory_facts")
    if limit is not None and await app.ai.memory.count(p.user_id) >= limit:
        raise APIError(429, "limit_reached", f"Fact limit {limit}")
    await app.settings.set(p.user_id, "ai_long_memory", True)
    return {"id": await app.ai.memory.remember(p.user_id, body.content, source="app")}


@router.delete("/ai/memory/{mid}", tags=["ai"])
async def delete_memory(mid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"deleted": await app.ai.memory.forget(p.user_id, memory_id=mid)}


@router.delete("/ai/memory", tags=["ai"])
async def clear_memory(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    n = await app.ai.memory.clear_all(p.user_id)
    await app.audit.log("ai.memory_clear", actor_id=p.user_id, actor_type="app")
    return {"deleted": n}


@router.get("/ai/drafts", tags=["ai"])
async def drafts(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.db.fetchall("SELECT * FROM ai_drafts WHERE user_id=? ORDER BY id DESC LIMIT 100", (p.user_id,))}


@router.post("/ai/drafts/{did}/{action}", tags=["ai"])
async def draft_action(did: int, action: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if action not in ("send", "alt", "rej"):
        raise APIError(404, "not_found", "Unknown action")
    try:
        return {"result": await app.ai_auto.decide_draft(p.user_id, did, action)}
    except AIError as e:
        raise _ai_error(e) from None


# ---- smart auto reply ------------------------------------------------------------------------

class ModeIn(BaseModel):
    mode: str


@router.put("/autoreply/mode", tags=["autoreply"])
async def set_mode(body: ModeIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if body.mode not in MODES:
        raise APIError(422, "invalid_mode", "Unknown mode")
    if body.mode in ("ai", "hybrid") and not app.ai.available():
        raise APIError(503, "ai_not_configured", "AI provider is not configured")
    await app.autoreply.set_mode(p.user_id, body.mode)
    return {"mode": body.mode}


@router.get("/autoreply/rules", tags=["autoreply"])
async def ar_rules(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.autoreply.rules(p.user_id), "mode": await app.settings.get(p.user_id, "mode"), "modes": list(MODES)}


@router.post("/autoreply/rules", tags=["autoreply"])
async def ar_create(body: dict[str, Any], p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.autoreply.add_rule(p.user_id, body)


@router.patch("/autoreply/rules/{rid}", tags=["autoreply"])
async def ar_update(rid: int, body: dict[str, Any], p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    row = await app.autoreply.update_rule(p.user_id, rid, body)
    if row is None:
        raise APIError(404, "not_found", "Rule not found")
    return row


@router.delete("/autoreply/rules/{rid}", tags=["autoreply"])
async def ar_delete(rid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.autoreply.delete_rule(p.user_id, rid):
        raise APIError(404, "not_found", "Rule not found")
    return {"ok": True}


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=3000)


@router.get("/autoreply/templates", tags=["autoreply"])
async def tpl_list(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.autoreply.templates(p.user_id)}


@router.post("/autoreply/templates", tags=["autoreply"])
async def tpl_save(body: TemplateIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.db.execute("INSERT INTO reply_templates(user_id, name, text, created_at) VALUES (?,?,?,?) ON CONFLICT(user_id, name) "
                         "DO UPDATE SET text=excluded.text", (p.user_id, body.name.lower(), body.text, int(time.time())))
    return {"ok": True}


@router.delete("/autoreply/templates/{name}", tags=["autoreply"])
async def tpl_delete(name: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"deleted": await app.db.rowcount("DELETE FROM reply_templates WHERE user_id=? AND name=?", (p.user_id, name.lower()))}


# ---- automation builder ----------------------------------------------------------------------

@router.get("/automation/schema", tags=["automation"])
async def automation_schema(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"triggers": triggers_for((await app.settings.all(p.user_id))["lang"]), "conditions": list(CONDITIONS), "actions": list(ACTIONS), "ai_labels": list(AI_LABELS),
            "media_types": list(MEDIA_TYPES), "modes": list(MODES)}


@router.get("/automation/rules", tags=["automation"])
async def auto_rules(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.automation.rules(p.user_id)}


@router.post("/automation/rules", tags=["automation"])
async def auto_create(body: dict[str, Any], p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.automation.create(p.user_id, body)
    except RuleError as e:
        raise APIError(422, "invalid_rule", str(e)) from None


@router.patch("/automation/rules/{rid}", tags=["automation"])
async def auto_update(rid: int, body: dict[str, Any], p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        row = await app.automation.update(p.user_id, rid, body)
    except RuleError as e:
        raise APIError(422, "invalid_rule", str(e)) from None
    if row is None:
        raise APIError(404, "not_found", "Rule not found")
    return row


@router.delete("/automation/rules/{rid}", tags=["automation"])
async def auto_delete(rid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.automation.delete(p.user_id, rid):
        raise APIError(404, "not_found", "Rule not found")
    return {"ok": True}


class TestRuleIn(BaseModel):
    rule: dict[str, Any]
    sample_text: str = Field(default="", max_length=2000)
    media: str | None = None
    is_new: bool = False


@router.post("/automation/test", tags=["automation"])
async def auto_test(body: TestRuleIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.automation.dry_run(p.user_id, body.rule, body.sample_text, body.media, body.is_new)
    except RuleError as e:
        raise APIError(422, "invalid_rule", str(e)) from None


@router.get("/automation/templates", tags=["automation"])
async def auto_templates(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": templates_for((await app.settings.all(p.user_id))["lang"])}


@router.post("/automation/templates/{tid}/install", tags=["automation"])
async def auto_install(tid: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return {"items": await install_template(app.automation, p.user_id, tid, (await app.settings.all(p.user_id))["lang"])}
    except RuleError as e:
        raise APIError(422, "invalid_rule", str(e)) from None


@router.get("/automation/executions", tags=["automation"])
async def auto_exec(rule_id: int | None = None, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.automation.executions(p.user_id, rule_id, 200)}


# ---- commands --------------------------------------------------------------------------------

@router.get("/commands", tags=["commands"])
async def commands(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    stats = {r["command_id"]: r for r in await app.db.fetchall("SELECT * FROM command_registry")}
    mine = {r["command_id"]: r for r in await app.db.fetchall(
        "SELECT command_id, COUNT(*) AS calls, SUM(1-ok) AS errors FROM command_history WHERE user_id=? GROUP BY command_id", (p.user_id,))}
    disabled = set(s.get("disabled_commands") or [])
    items = []
    for spec in sorted(app.registry.visible(admin=p.is_super), key=lambda x: (x.category, x.id)):
        d = spec.to_dict(s["lang"], s["prefix"])
        g = stats.get(spec.id, {})
        d.update({"enabled_for_me": spec.id not in disabled, "enabled_global": bool(g.get("enabled_global", 1)),
                  "min_plan": g.get("min_plan", spec.min_plan), "calls_total": g.get("calls", 0), "errors_total": g.get("errors", 0),
                  "last_error": g.get("last_error") if p.is_admin else None, "calls_mine": (mine.get(spec.id) or {}).get("calls", 0)})
        items.append(d)
    return {"items": items, "prefix": s["prefix"], "count": len(items)}


class CmdToggle(BaseModel):
    enabled: bool


@router.patch("/commands/{cid}", tags=["commands"])
async def toggle_cmd(cid: str, body: CmdToggle, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    spec = app.registry.resolve(cid, admin=p.is_super)
    if spec is None:
        raise APIError(404, "not_found", "Command not found")
    disabled = set(await app.settings.get(p.user_id, "disabled_commands") or [])
    disabled.discard(spec.id) if body.enabled else disabled.add(spec.id)
    await app.settings.set(p.user_id, "disabled_commands", sorted(disabled))
    return {"id": spec.id, "enabled": body.enabled}


class CmdGlobal(BaseModel):
    enabled: bool | None = None
    min_plan: str | None = None


@router.patch("/commands/{cid}/global", tags=["commands"])
async def global_cmd(cid: str, body: CmdGlobal, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    spec = app.registry.resolve(cid, admin=True)
    if spec is None:
        raise APIError(404, "not_found", "Command not found")
    await app.executor.set_global(spec.id, body.enabled, body.min_plan)
    await app.audit.log("command.global", actor_id=p.user_id, actor_type="app", target_type="command", target_id=spec.id, **body.model_dump(exclude_none=True))
    return {"ok": True}


class PrefixIn(BaseModel):
    prefix: str = Field(min_length=1, max_length=3)


@router.put("/commands/prefix", tags=["commands"])
async def set_prefix(body: PrefixIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return {"prefix": await app.settings.set(p.user_id, "prefix", body.prefix)}
    except ValueError as e:
        raise APIError(422, "invalid_prefix", str(e)) from None


class CmdTest(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


@router.post("/commands/test", tags=["commands"])
async def test_cmd(body: CmdTest, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.executor.sandbox(p.user_id, body.text, await app.settings.all(p.user_id))


class CustomIn(BaseModel):
    name: str = Field(min_length=2, max_length=24)
    description: str = Field(default="", max_length=200)
    actions: list[dict[str, Any]]


@router.get("/commands/custom", tags=["commands"])
async def custom_list(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.custom_commands.list(p.user_id)}


@router.post("/commands/custom", tags=["commands"])
async def custom_save(body: CustomIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.custom_commands.save(p.user_id, body.name, body.actions, body.description)
    except ValueError as e:
        raise APIError(422, "invalid_command", str(e)) from None


@router.delete("/commands/custom/{name}", tags=["commands"])
async def custom_delete(name: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.custom_commands.delete(p.user_id, name):
        raise APIError(404, "not_found", "Custom command not found")
    return {"ok": True}
