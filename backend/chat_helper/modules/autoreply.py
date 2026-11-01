"""Smart Auto Reply: modes, keyword/regex/FAQ rules, welcome, business hours, handoff, per-chat lists."""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.parser import split_pipe
from ..commands.registry import registry
from ..core.timeutil import fmt_dt, human_duration, in_time_window, local_dt, parse_duration
from ..database.db import dumps, loads
from ..localization import on_off, tr
from ..security.sanitize import clip, esc
from ..services.settings import MODES

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)

TRIGGERS = ("keyword", "regex", "faq", "welcome", "offhours", "schedule", "any", "media")
MATCH_MODES = ("contains", "exact", "startswith", "word")

MODE_ALIASES = {
    "manual": "manual", "ручной": "manual", "qo'lda": "manual",
    "auto": "auto", "авто": "auto", "avto": "auto",
    "ai": "ai", "ии": "ai", "ии-режим": "ai",
    "afk": "afk", "афк": "afk",
    "silent": "silent", "тихий": "silent", "tinch": "silent",
    "business": "business", "бизнес": "business", "biznes": "business",
    "hybrid": "hybrid", "гибрид": "hybrid", "gibrid": "hybrid",
}

MODE_TITLES = {
    "manual": ("✋ Ручной — только команды", "✋ Qo'lda — faqat buyruqlar"),
    "auto": ("⚡️ Авто — правила и шаблоны", "⚡️ Avto — qoidalar va shablonlar"),
    "ai": ("🧠 AI — ответы ассистента", "🧠 AI — yordamchi javoblari"),
    "afk": ("💤 AFK — сообщение об отсутствии", "💤 AFK — yo'qlik haqida xabar"),
    "silent": ("🔕 Тихий — никаких автоответов", "🔕 Tinch — avtojavoblarsiz"),
    "business": ("💼 Бизнес — рабочие часы + правила", "💼 Biznes — ish vaqti + qoidalar"),
    "hybrid": ("🔀 Гибрид — правила, затем AI", "🔀 Gibrid — qoidalar, so'ng AI"),
}


def mode_title(mode: str, lang: str) -> str:
    return tr(lang, *MODE_TITLES.get(mode, (mode, mode)))


def fill(template: str, *, name: str, owner: str, tz_name: str) -> str:
    d = local_dt(None, tz_name)
    return (template.replace("{name}", name).replace("{owner}", owner)
            .replace("{time}", d.strftime("%H:%M")).replace("{date}", d.strftime("%d.%m.%Y")))


class AutoReplyService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._rule_cooldown: dict[tuple[int, int], float] = {}
        self._rules_cache: dict[int, list[dict[str, Any]]] = {}

    # ---- mode -----------------------------------------------------------------------
    async def set_mode(self, user_id: int, mode: str) -> str:
        if mode not in MODES:
            raise ValueError("invalid mode")
        active = await self.app.afk.active(user_id)
        if mode == "afk":
            if not active:
                await self.app.afk.enable(user_id, None)
            return mode
        if active:
            await self.app.afk.disable(user_id, notify=False, restore_mode=False)
        await self.app.settings.set(user_id, "mode", mode)
        self.app.events.emit("mode", user_id=user_id, mode=mode)
        return mode

    # ---- rules CRUD ------------------------------------------------------------------
    async def rules(self, user_id: int) -> list[dict[str, Any]]:
        if user_id not in self._rules_cache:
            rows = await self.app.db.fetchall(
                "SELECT * FROM autoresponse_rules WHERE user_id=? ORDER BY priority DESC, id ASC", (user_id,))
            for r in rows:
                r["chat_filter"] = loads(r.pop("chat_filter_json"), {})
                r["schedule"] = loads(r.pop("schedule_json"), {})
            self._rules_cache[user_id] = rows
        return self._rules_cache[user_id]

    def validate_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        trig = data.get("trigger_type", "keyword")
        if trig not in TRIGGERS:
            raise ValueError("invalid trigger_type")
        mode = data.get("match_mode", "contains")
        if mode not in MATCH_MODES:
            raise ValueError("invalid match_mode")
        pattern = (data.get("pattern") or "").strip()
        if trig in ("keyword", "faq", "regex") and not pattern:
            raise ValueError("pattern is required")
        if trig == "regex":
            if len(pattern) > 200:
                raise ValueError("regex too long")
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from None
        response = (data.get("response") or "").strip()
        if not response or len(response) > 3000:
            raise ValueError("response must be 1..3000 chars")
        cooldown = int(data.get("cooldown_sec", 300))
        if not 0 <= cooldown <= 7 * 86400:
            raise ValueError("cooldown_sec out of range")
        return {"name": (data.get("name") or pattern or trig)[:64], "trigger_type": trig, "pattern": pattern[:500],
                "match_mode": mode, "response": response, "enabled": 1 if data.get("enabled", True) else 0,
                "priority": max(-100, min(100, int(data.get("priority", 0)))), "cooldown_sec": cooldown,
                "chat_filter_json": dumps(data.get("chat_filter") or {}), "schedule_json": dumps(data.get("schedule") or {})}

    async def add_rule(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        v = self.validate_rule(data)
        limit = await self.app.subs.limit(user_id, "autoreply_rules")
        count = await self.app.db.fetchval("SELECT COUNT(*) FROM autoresponse_rules WHERE user_id=?", (user_id,), 0)
        if limit is not None and limit >= 0 and count >= limit:
            raise ValueError(f"rule limit reached for your plan ({limit})")
        now = int(time.time())
        rid = await self.app.db.execute(
            "INSERT INTO autoresponse_rules(user_id, name, trigger_type, pattern, match_mode, response, enabled, priority, "
            "cooldown_sec, chat_filter_json, schedule_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, v["name"], v["trigger_type"], v["pattern"], v["match_mode"], v["response"], v["enabled"], v["priority"],
             v["cooldown_sec"], v["chat_filter_json"], v["schedule_json"], now, now))
        self._rules_cache.pop(user_id, None)
        return await self.get_rule(user_id, rid)  # type: ignore[return-value]

    async def get_rule(self, user_id: int, rule_id: int) -> dict[str, Any] | None:
        for r in await self.rules(user_id):
            if r["id"] == rule_id:
                return r
        return None

    async def update_rule(self, user_id: int, rule_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        cur = await self.get_rule(user_id, rule_id)
        if cur is None:
            return None
        merged = {**cur, **data}
        v = self.validate_rule(merged)
        await self.app.db.execute(
            "UPDATE autoresponse_rules SET name=?, trigger_type=?, pattern=?, match_mode=?, response=?, enabled=?, priority=?, "
            "cooldown_sec=?, chat_filter_json=?, schedule_json=?, updated_at=? WHERE id=? AND user_id=?",
            (v["name"], v["trigger_type"], v["pattern"], v["match_mode"], v["response"], v["enabled"], v["priority"],
             v["cooldown_sec"], v["chat_filter_json"], v["schedule_json"], int(time.time()), rule_id, user_id))
        self._rules_cache.pop(user_id, None)
        return await self.get_rule(user_id, rule_id)

    async def delete_rule(self, user_id: int, rule_id: int) -> bool:
        n = await self.app.db.rowcount("DELETE FROM autoresponse_rules WHERE id=? AND user_id=?", (rule_id, user_id))
        self._rules_cache.pop(user_id, None)
        return n > 0

    # ---- matching --------------------------------------------------------------------
    @staticmethod
    def _match_text(rule: dict[str, Any], text: str) -> bool:
        t = (text or "").lower().strip()
        if not t:
            return False
        if rule["trigger_type"] == "regex":
            try:
                return re.search(rule["pattern"], text or "", re.IGNORECASE) is not None
            except re.error:
                return False
        keywords = [k.strip().lower() for k in rule["pattern"].split(",") if k.strip()]
        mode = rule["match_mode"]
        for k in keywords:
            if mode == "exact" and t == k:
                return True
            if mode == "startswith" and t.startswith(k):
                return True
            if mode == "contains" and k in t:
                return True
            if mode == "word" and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", t):
                return True
        return False

    def _chat_allowed(self, rule: dict[str, Any], chat_id: int, chat_tags: list[str]) -> bool:
        f = rule.get("chat_filter") or {}
        if f.get("chats") and chat_id not in f["chats"]:
            return False
        if f.get("exclude") and chat_id in f["exclude"]:
            return False
        if f.get("tags") and not set(f["tags"]) & set(chat_tags):
            return False
        return True

    def _schedule_ok(self, rule: dict[str, Any], tz_name: str) -> bool:
        sch = rule.get("schedule") or {}
        if not sch:
            return True
        if sch.get("days"):
            if local_dt(None, tz_name).isoweekday() not in sch["days"]:
                return False
        if sch.get("start") and sch.get("end"):
            return in_time_window(sch["start"], sch["end"], tz_name)
        return True

    def is_work_time(self, settings: dict[str, Any]) -> bool:
        tz_name = settings.get("timezone") or self.app.config.timezone
        if local_dt(None, tz_name).isoweekday() not in (settings.get("work_days") or [1, 2, 3, 4, 5]):
            return False
        return in_time_window(settings.get("work_start", "09:00"), settings.get("work_end", "18:00"), tz_name)

    async def match(self, user_id: int, chat_id: int, text: str, *, is_new_chat: bool, media_type: str | None,
                    settings: dict[str, Any], chat_tags: list[str], include_offhours: bool) -> dict[str, Any] | None:
        tz_name = settings.get("timezone") or self.app.config.timezone
        now = time.time()
        for rule in await self.rules(user_id):
            if not rule["enabled"] or not self._chat_allowed(rule, chat_id, chat_tags) or not self._schedule_ok(rule, tz_name):
                continue
            trig = rule["trigger_type"]
            ok = False
            if trig in ("keyword", "faq", "regex"):
                ok = self._match_text(rule, text)
            elif trig == "welcome":
                ok = is_new_chat
            elif trig == "offhours":
                ok = include_offhours and not self.is_work_time(settings)
            elif trig in ("schedule", "any"):
                ok = True
            elif trig == "media":
                types = (rule.get("schedule") or {}).get("types") or []
                ok = bool(media_type) and (not types or media_type in types)
            if not ok:
                continue
            key = (rule["id"], chat_id)
            if rule["cooldown_sec"] and now - self._rule_cooldown.get(key, 0) < rule["cooldown_sec"]:
                continue
            self._rule_cooldown[key] = now
            await self.app.db.execute("UPDATE autoresponse_rules SET hits=hits+1 WHERE id=?", (rule["id"],))
            return rule
        return None

    async def templates(self, user_id: int) -> list[dict[str, Any]]:
        return await self.app.db.fetchall("SELECT * FROM reply_templates WHERE user_id=? ORDER BY name", (user_id,))


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------

@registry.command("auto", "autoreply", aliases=["режим", "mode", "rejim"],
                  ru="Показать или сменить режим автоответчика (manual/auto/ai/afk/silent/business/hybrid)",
                  uz="Avtojavob rejimini ko'rish yoki o'zgartirish", syntax=".auto [режим]",
                  examples=[".auto", ".auto hybrid", ".auto тихий"], sandbox_safe=False)
async def cmd_auto(ctx: CommandContext) -> None:
    if not ctx.args:
        cur = ctx.settings["mode"]
        lines = [ctx.t("💬 <b>Режим автоответчика</b>", "💬 <b>Avtojavob rejimi</b>"), ""]
        for m in MODES:
            lines.append(("▶️ " if m == cur else "▫️ ") + mode_title(m, ctx.lang) + f"  <code>{ctx.prefix}auto {m}</code>")
        await ctx.answer("\n".join(lines), private=ctx.is_business)
        return
    mode = MODE_ALIASES.get(ctx.parsed.first)
    if not mode:
        raise UsageError(ctx.t("Неизвестный режим.", "Noma'lum rejim."))
    await ctx.app.autoreply.set_mode(ctx.user_id, mode)
    await ctx.answer(ctx.t("✅ Режим: {m}", "✅ Rejim: {m}", m=mode_title(mode, ctx.lang)), private=ctx.is_business)


@registry.command("reply", "autoreply", aliases=["ответ", "rule", "javob"],
                  ru="Правила автоответа по ключевым словам: add / list / del / on / off",
                  uz="Kalit so'zlar bo'yicha avtojavob qoidalari: add / list / del / on / off",
                  syntax=".reply add слова | ответ  ·  .reply list  ·  .reply del ID",
                  examples=[".reply add цена, прайс | Прайс-лист: example.com/price", ".reply list", ".reply del 3"])
async def cmd_reply(ctx: CommandContext) -> None:
    svc: AutoReplyService = ctx.app.autoreply
    sub = ctx.parsed.first
    if sub in ("", "list", "список", "ro'yxat"):
        rules = await svc.rules(ctx.user_id)
        if not rules:
            await ctx.answer(ctx.t("Правил пока нет. Добавить: <code>{p}reply add привет | Здравствуйте!</code>",
                                   "Qoidalar yo'q. Qo'shish: <code>{p}reply add salom | Assalomu alaykum!</code>", p=ctx.prefix),
                             private=ctx.is_business)
            return
        lines = [ctx.t("💬 <b>Правила автоответа</b>", "💬 <b>Avtojavob qoidalari</b>")]
        for r in rules[:40]:
            st = "🟢" if r["enabled"] else "⚪️"
            lines.append(f"{st} <b>#{r['id']}</b> [{r['trigger_type']}] {esc(clip(r['pattern'] or '', 40))} → "
                         f"{esc(clip(r['response'], 50))} · {r['hits']}×")
        await ctx.answer("\n".join(lines), private=ctx.is_business)
        return
    if sub in ("add", "добавить", "qo'sh"):
        body = ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else ""
        parts = split_pipe(body)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise UsageError()
        try:
            rule = await svc.add_rule(ctx.user_id, {"trigger_type": "keyword", "pattern": parts[0], "response": "|".join(parts[1:]).strip(),
                                                    "match_mode": "contains", "cooldown_sec": ctx.settings["autoreply_cooldown_sec"]})
        except ValueError as e:
            raise CommandError(f"⚠️ {esc(str(e))}") from None
        await ctx.answer(ctx.t("✅ Правило #{id} добавлено. Работает в режимах auto / business / hybrid.",
                               "✅ #{id} qoida qo'shildi. auto / business / hybrid rejimlarida ishlaydi.", id=rule["id"]),
                         private=ctx.is_business)
        return
    if sub in ("del", "delete", "удалить", "o'chir", "on", "off"):
        if len(ctx.args) < 2 or not ctx.args[1].lstrip("#").isdigit():
            raise UsageError()
        rid = int(ctx.args[1].lstrip("#"))
        if sub in ("on", "off"):
            ok = await svc.update_rule(ctx.user_id, rid, {"enabled": sub == "on"}) is not None
        else:
            ok = await svc.delete_rule(ctx.user_id, rid)
        if not ok:
            raise CommandError(ctx.t("Правило не найдено.", "Qoida topilmadi."))
        await ctx.answer("✅", private=ctx.is_business)
        return
    raise UsageError()


@registry.command("welcome", "autoreply", aliases=["приветствие", "salomlash"],
                  ru="Приветствие для новых собеседников: текст / on / off", uz="Yangi suhbatdoshlar uchun salomlashish",
                  syntax=".welcome [текст | on | off]", examples=[".welcome Привет, {name}! Я скоро отвечу.", ".welcome off"])
async def cmd_welcome(ctx: CommandContext) -> None:
    s = ctx.app.settings
    if not ctx.args:
        await ctx.answer(ctx.t("👋 Приветствие: {st}\n{txt}", "👋 Salomlashish: {st}\n{txt}",
                               st=on_off(ctx.lang, ctx.settings["welcome_enabled"]),
                               txt=esc(ctx.settings["welcome_text"] or "—")), private=ctx.is_business)
        return
    if ctx.parsed.first in ("on", "off", "вкл", "выкл"):
        await s.set(ctx.user_id, "welcome_enabled", ctx.parsed.first in ("on", "вкл"))
    else:
        await s.update(ctx.user_id, {"welcome_text": ctx.raw[:1000], "welcome_enabled": True})
    await ctx.answer(ctx.t("✅ Приветствие сохранено. Плейсхолдеры: {name}, {owner}, {time}.",
                           "✅ Salomlashish saqlandi. O'rinbosarlar: {name}, {owner}, {time}."), private=ctx.is_business)


@registry.command("work", "autoreply", aliases=["работа", "ish", "hours"],
                  ru="Рабочие часы и бизнес-режим: on / off / 9-18 / текст вне часов",
                  uz="Ish vaqti va biznes rejim: on / off / 9-18 / ish vaqtidan tashqari matn",
                  syntax=".work [on|off|ЧЧ:ММ-ЧЧ:ММ|text ...]", examples=[".work 09:00-18:00", ".work on", ".work text Сейчас нерабочее время, отвечу утром"])
async def cmd_work(ctx: CommandContext) -> None:
    sub = ctx.parsed.first
    s = ctx.app.settings
    if not sub:
        st = ctx.app.autoreply.is_work_time(ctx.settings)
        await ctx.answer(ctx.t("💼 Рабочие часы: {a}–{b}, дни {d}\nСейчас: {now}\nРежим: {m}",
                               "💼 Ish vaqti: {a}–{b}, kunlar {d}\nHozir: {now}\nRejim: {m}",
                               a=ctx.settings["work_start"], b=ctx.settings["work_end"],
                               d=",".join(map(str, ctx.settings["work_days"])),
                               now=ctx.t("рабочее время", "ish vaqti") if st else ctx.t("нерабочее время", "ish vaqtidan tashqari"),
                               m=mode_title(ctx.settings["mode"], ctx.lang)), private=ctx.is_business)
        return
    if sub in ("on", "вкл"):
        await ctx.app.autoreply.set_mode(ctx.user_id, "business")
    elif sub in ("off", "выкл"):
        await ctx.app.autoreply.set_mode(ctx.user_id, "manual")
    elif sub in ("text", "текст", "matn"):
        await s.set(ctx.user_id, "offhours_text", ctx.raw.split(None, 1)[1][:1000] if len(ctx.raw.split(None, 1)) > 1 else "")
    else:
        m = re.fullmatch(r"(\d{1,2}(?::\d{2})?)\s*-\s*(\d{1,2}(?::\d{2})?)", ctx.raw.strip())
        if not m:
            raise UsageError()
        a, b = (x if ":" in x else f"{x}:00" for x in m.groups())
        try:
            await s.update(ctx.user_id, {"work_start": a, "work_end": b})
        except ValueError as e:
            raise CommandError(f"⚠️ {esc(str(e))}") from None
    await ctx.answer("✅", private=ctx.is_business)


async def _chat_target(ctx: CommandContext) -> int:
    if ctx.is_business:
        return ctx.chat_id
    if ctx.args and ctx.args[-1].lstrip("-").isdigit():
        return int(ctx.args[-1])
    raise CommandError(ctx.t("Используйте команду в нужном чате или укажите ID чата.", "Buyruqni kerakli chatda ishlating yoki chat ID'sini kiriting."))


@registry.command("ignore", "autoreply", aliases=["игнор", "blacklist"],
                  ru="Не отвечать автоматически в этом чате (чёрный список)", uz="Bu chatda avtomatik javob bermaslik (qora ro'yxat)",
                  syntax=".ignore [chat_id]", examples=[".ignore"])
async def cmd_ignore(ctx: CommandContext) -> None:
    chat_id = await _chat_target(ctx)
    await ctx.app.chats.touch(ctx.user_id, chat_id)
    await ctx.app.chats.update(ctx.user_id, chat_id, {"ignored": True, "whitelisted": False})
    await ctx.answer(ctx.t("🚫 Чат в чёрном списке: автоответы, AI и AFK здесь отключены.",
                           "🚫 Chat qora ro'yxatda: avtojavob, AI va AFK bu yerda o'chirildi."), private=True)


@registry.command("allow", "autoreply", aliases=["разрешить", "whitelist", "ruxsat"],
                  ru="Разрешить автоответы в этом чате (белый список)", uz="Bu chatda avtojavobga ruxsat (oq ro'yxat)",
                  syntax=".allow [chat_id]", examples=[".allow"])
async def cmd_allow(ctx: CommandContext) -> None:
    chat_id = await _chat_target(ctx)
    await ctx.app.chats.touch(ctx.user_id, chat_id)
    await ctx.app.chats.update(ctx.user_id, chat_id, {"ignored": False, "whitelisted": True})
    await ctx.answer(ctx.t("✅ Чат в белом списке.", "✅ Chat oq ro'yxatda."), private=True)


@registry.command("mute", "autoreply", aliases=["заглушить", "jim"],
                  ru="Заглушить автоматизацию и уведомления в чате на время", uz="Chatda avtomatlashtirish va bildirishnomalarni vaqtincha o'chirish",
                  syntax=".mute [время|off]", examples=[".mute 2h", ".mute off"])
async def cmd_mute(ctx: CommandContext) -> None:
    chat_id = await _chat_target(ctx)
    await ctx.app.chats.touch(ctx.user_id, chat_id)
    arg = ctx.parsed.first
    if arg in ("off", "выкл"):
        await ctx.app.chats.update(ctx.user_id, chat_id, {"muted_until": None})
        await ctx.answer(ctx.t("🔔 Чат снова активен.", "🔔 Chat yana faol."), private=True)
        return
    dur = parse_duration(arg) if arg else 3600 * 24 * 365
    if not dur:
        raise UsageError()
    until = int(time.time()) + dur
    await ctx.app.chats.update(ctx.user_id, chat_id, {"muted_until": until})
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    await ctx.answer(ctx.t("🔕 Заглушено до {t}", "🔕 {t} gacha o'chirildi", t=fmt_dt(until, tz_name)), private=True)


@registry.command("pause", "autoreply", aliases=["пауза", "to'xtat"],
                  ru="Приостановить всю автоматизацию (автоответы, AI, AFK-ответы)", uz="Barcha avtomatlashtirishni to'xtatish",
                  syntax=".pause [время]", examples=[".pause", ".pause 1h"])
async def cmd_pause(ctx: CommandContext) -> None:
    await ctx.app.settings.set(ctx.user_id, "automation_paused", True)
    dur = parse_duration(ctx.parsed.first) if ctx.args else None
    if dur:
        await ctx.app.scheduler.add(ctx.user_id, "resume_automation", {}, int(time.time()) + dur,
                                    dedup_key=f"resume:{ctx.user_id}")
    await ctx.answer(ctx.t("⏸ Автоматизация на паузе{d}. Продолжить: {p}resume", "⏸ Avtomatlashtirish to'xtatildi{d}. Davom: {p}resume",
                           d=(" · " + human_duration(dur, ctx.lang)) if dur else "", p=ctx.prefix), private=ctx.is_business)


@registry.command("resume", "autoreply", aliases=["продолжить", "davom"],
                  ru="Возобновить автоматизацию", uz="Avtomatlashtirishni davom ettirish", syntax=".resume", examples=[".resume"])
async def cmd_resume(ctx: CommandContext) -> None:
    await ctx.app.settings.set(ctx.user_id, "automation_paused", False)
    await ctx.answer(ctx.t("▶️ Автоматизация возобновлена.", "▶️ Avtomatlashtirish davom etmoqda."), private=ctx.is_business)
