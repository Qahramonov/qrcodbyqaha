"""No-code automation: IF trigger AND conditions THEN actions. Validation, execution, dry-run, templates."""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import Message

from ..core.timeutil import in_time_window, local_dt, parse_hhmm
from ..database.db import dumps, loads
from ..localization import tr
from ..security.sanitize import clip, esc, wrap_untrusted
from ..services.settings import MODES

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

log = logging.getLogger(__name__)

TRIGGERS = {k: f"automation.trigger.{k}" for k in ("message", "keyword", "time", "media", "contact", "new_chat", "ai_class", "no_reply")}
CONDITIONS = ("time_window", "weekday", "mode", "chat_tag", "not_chat_tag", "afk")
ACTIONS = ("reply", "reply_template", "ai_reply", "set_mode", "afk_on", "afk_off", "notify", "tag", "timer", "remind", "handoff",
           "mark_read", "set_priority")
CHAT_ACTIONS = {"reply", "reply_template", "ai_reply", "tag", "handoff", "mark_read", "set_priority"}
AI_LABELS = ("urgent", "question", "order", "complaint", "greeting", "spam", "other")
MEDIA_TYPES = ("voice", "video_note", "audio", "video", "photo", "animation", "sticker", "document", "location", "contact")


class RuleError(ValueError):
    pass


def _validate_actions(actions: list[dict[str, Any]], depth: int = 0) -> list[dict[str, Any]]:
    if not isinstance(actions, list) or not 1 <= len(actions) <= 10:
        raise RuleError("actions: 1..10 items required")
    out = []
    for a in actions:
        t = a.get("type")
        if t not in ACTIONS:
            raise RuleError(f"unknown action: {t}")
        clean: dict[str, Any] = {"type": t}
        if t in ("reply", "notify"):
            text = str(a.get("text") or "").strip()
            if not text or len(text) > 2000:
                raise RuleError(f"{t}: text 1..2000 chars")
            clean["text"] = text
        elif t == "reply_template":
            clean["name"] = str(a.get("name") or "")[:40].lower()
            if not clean["name"]:
                raise RuleError("reply_template: name required")
        elif t == "set_mode":
            if a.get("mode") not in MODES:
                raise RuleError("set_mode: invalid mode")
            clean["mode"] = a["mode"]
        elif t == "afk_on":
            clean["reason"] = str(a.get("reason") or "")[:200]
            m = int(a.get("minutes") or 0)
            if not 0 <= m <= 7 * 1440:
                raise RuleError("afk_on: minutes 0..10080")
            clean["minutes"] = m
        elif t == "tag":
            tag = str(a.get("tag") or "").strip()[:32]
            if not tag:
                raise RuleError("tag: tag required")
            clean["tag"] = tag
        elif t in ("timer", "remind"):
            m = int(a.get("minutes") or 0)
            if not 1 <= m <= 7 * 1440:
                raise RuleError(f"{t}: minutes 1..10080")
            clean["minutes"] = m
            if t == "remind":
                clean["text"] = str(a.get("text") or "")[:500] or "⏰"
            else:
                if depth >= 1:
                    raise RuleError("timer: nested timers are not allowed")
                clean["then"] = _validate_actions(a.get("then") or [], depth + 1)
        elif t == "set_priority":
            v = int(a.get("value", 1))
            if not -5 <= v <= 5:
                raise RuleError("set_priority: -5..5")
            clean["value"] = v
        out.append(clean)
    return out


def validate_rule(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()[:64]
    if not name:
        raise RuleError("name is required")
    trig = data.get("trigger") or {}
    tt = trig.get("type")
    if tt not in TRIGGERS:
        raise RuleError("invalid trigger type")
    t: dict[str, Any] = {"type": tt}
    if tt == "keyword":
        kws = [str(k).strip().lower()[:64] for k in (trig.get("keywords") or []) if str(k).strip()]
        if not kws or len(kws) > 30:
            raise RuleError("keyword: 1..30 keywords")
        match = trig.get("match", "contains")
        if match not in ("contains", "word", "exact", "regex"):
            raise RuleError("keyword: invalid match")
        if match == "regex":
            for k in kws:
                try:
                    re.compile(k)
                except re.error:
                    raise RuleError(f"invalid regex: {k}") from None
        t.update({"keywords": kws, "match": match})
    elif tt == "time":
        hm = parse_hhmm(str(trig.get("at") or ""))
        if not hm:
            raise RuleError("time: at=HH:MM required")
        days = sorted({int(d) for d in (trig.get("days") or [1, 2, 3, 4, 5, 6, 7]) if 1 <= int(d) <= 7})
        t.update({"at": f"{hm[0]:02d}:{hm[1]:02d}", "days": days})
    elif tt == "media":
        types = [x for x in (trig.get("types") or []) if x in MEDIA_TYPES]
        if not types:
            raise RuleError("media: types required")
        t["types"] = types
    elif tt == "contact":
        ids = [int(x) for x in (trig.get("chat_ids") or []) if str(x).lstrip("-").isdigit()]
        if not ids or len(ids) > 100:
            raise RuleError("contact: 1..100 chat ids")
        t["chat_ids"] = ids
    elif tt == "ai_class":
        if trig.get("label") not in AI_LABELS:
            raise RuleError("ai_class: invalid label")
        t["label"] = trig["label"]
    elif tt == "no_reply":
        m = int(trig.get("minutes") or 0)
        if not 5 <= m <= 1440:
            raise RuleError("no_reply: minutes 5..1440")
        t["minutes"] = m
    conds = []
    for c in data.get("conditions") or []:
        ct = c.get("type")
        if ct not in CONDITIONS:
            raise RuleError(f"invalid condition: {ct}")
        cc: dict[str, Any] = {"type": ct}
        if ct == "time_window":
            if not parse_hhmm(str(c.get("start"))) or not parse_hhmm(str(c.get("end"))):
                raise RuleError("time_window: start/end HH:MM")
            cc.update({"start": c["start"], "end": c["end"]})
        elif ct == "weekday":
            cc["days"] = sorted({int(d) for d in (c.get("days") or []) if 1 <= int(d) <= 7}) or [1, 2, 3, 4, 5]
        elif ct == "mode":
            cc["in"] = [m for m in (c.get("in") or []) if m in MODES]
        elif ct in ("chat_tag", "not_chat_tag"):
            cc["tag"] = str(c.get("tag") or "")[:32]
        elif ct == "afk":
            cc["active"] = bool(c.get("active", True))
        conds.append(cc)
    if len(conds) > 10:
        raise RuleError("max 10 conditions")
    actions = _validate_actions(data.get("actions") or [])
    if tt == "time" and any(a["type"] in CHAT_ACTIONS for a in actions):
        raise RuleError("time trigger has no chat: chat actions are not allowed")
    cooldown = int(data.get("cooldown_sec", 60))
    if not 0 <= cooldown <= 7 * 86400:
        raise RuleError("cooldown_sec out of range")
    return {"name": name, "enabled": bool(data.get("enabled", True)), "trigger": t, "conditions": conds, "actions": actions,
            "cooldown_sec": cooldown, "template_id": data.get("template_id")}


class AutomationEngine:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._cache: dict[int, list[dict[str, Any]]] = {}
        self._cooldown: dict[tuple[int, int | None], float] = {}
        self._noreply_fired: dict[tuple[int, int], int] = {}

    # ---- CRUD -----------------------------------------------------------------------------
    async def rules(self, user_id: int) -> list[dict[str, Any]]:
        if user_id not in self._cache:
            rows = await self.app.db.fetchall("SELECT * FROM automation_rules WHERE user_id=? ORDER BY id", (user_id,))
            for r in rows:
                r["trigger"] = loads(r.pop("trigger_json"), {})
                r["conditions"] = loads(r.pop("conditions_json"), [])
                r["actions"] = loads(r.pop("actions_json"), [])
                r["enabled"] = bool(r["enabled"])
            self._cache[user_id] = rows
        return self._cache[user_id]

    async def get(self, user_id: int, rule_id: int) -> dict[str, Any] | None:
        return next((r for r in await self.rules(user_id) if r["id"] == rule_id), None)

    async def create(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        v = validate_rule(data)
        limit = await self.app.subs.limit(user_id, "automation_rules")
        n = len(await self.rules(user_id))
        if limit is not None and n >= limit:
            raise RuleError(f"automation limit reached for your plan ({limit})")
        now = int(time.time())
        rid = await self.app.db.execute(
            "INSERT INTO automation_rules(user_id, name, enabled, trigger_json, conditions_json, actions_json, cooldown_sec, template_id, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, v["name"], 1 if v["enabled"] else 0, dumps(v["trigger"]), dumps(v["conditions"]), dumps(v["actions"]),
             v["cooldown_sec"], v["template_id"], now, now))
        self._cache.pop(user_id, None)
        return await self.get(user_id, rid)  # type: ignore[return-value]

    async def update(self, user_id: int, rule_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        cur = await self.get(user_id, rule_id)
        if cur is None:
            return None
        v = validate_rule({**cur, **data})
        await self.app.db.execute(
            "UPDATE automation_rules SET name=?, enabled=?, trigger_json=?, conditions_json=?, actions_json=?, cooldown_sec=?, updated_at=? "
            "WHERE id=? AND user_id=?", (v["name"], 1 if v["enabled"] else 0, dumps(v["trigger"]), dumps(v["conditions"]),
                                         dumps(v["actions"]), v["cooldown_sec"], int(time.time()), rule_id, user_id))
        self._cache.pop(user_id, None)
        return await self.get(user_id, rule_id)

    async def delete(self, user_id: int, rule_id: int) -> bool:
        n = await self.app.db.rowcount("DELETE FROM automation_rules WHERE id=? AND user_id=?", (rule_id, user_id))
        self._cache.pop(user_id, None)
        return n > 0

    async def executions(self, user_id: int, rule_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if rule_id:
            return await self.app.db.fetchall("SELECT * FROM automation_executions WHERE user_id=? AND rule_id=? ORDER BY id DESC LIMIT ?",
                                              (user_id, rule_id, limit))
        return await self.app.db.fetchall("SELECT * FROM automation_executions WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))

    # ---- evaluation --------------------------------------------------------------------------
    @staticmethod
    def match_keyword(trig: dict[str, Any], text: str) -> bool:
        t = (text or "").lower()
        for k in trig["keywords"]:
            m = trig["match"]
            if (m == "contains" and k in t) or (m == "exact" and t.strip() == k) or \
               (m == "word" and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", t)):
                return True
            if m == "regex":
                try:
                    if re.search(k, text or "", re.IGNORECASE):
                        return True
                except re.error:
                    continue
        return False

    async def conditions_ok(self, user_id: int, rule: dict[str, Any], settings: dict[str, Any], chat_row: dict[str, Any] | None) -> bool:
        tz_name = settings.get("timezone") or self.app.config.timezone
        for c in rule["conditions"]:
            ct = c["type"]
            if ct == "time_window" and not in_time_window(c["start"], c["end"], tz_name):
                return False
            if ct == "weekday" and local_dt(None, tz_name).isoweekday() not in c["days"]:
                return False
            if ct == "mode" and c["in"] and settings["mode"] not in c["in"]:
                return False
            tags = (chat_row or {}).get("tags") or []
            if ct == "chat_tag" and c["tag"] not in tags:
                return False
            if ct == "not_chat_tag" and c["tag"] in tags:
                return False
            if ct == "afk" and bool(await self.app.afk.active(user_id)) != c["active"]:
                return False
        return True

    async def classify(self, user_id: int, text: str) -> str | None:
        if not text or not self.app.ai.available():
            return None
        try:
            res = await self.app.ai.complete(user_id, [{"role": "user", "content": wrap_untrusted(clip(text, 1500))}],
                                             system="Classify the message into exactly one label: " + ", ".join(AI_LABELS) +
                                                    ". Reply with the label only.", kind="classify", max_tokens=5)
            label = res.text.strip().lower().split()[0].strip(".,")
            return label if label in AI_LABELS else "other"
        except Exception:
            return None

    async def on_message(self, conn: "Conn", message: Message, settings: dict[str, Any], chat_row: dict[str, Any],
                         is_new: bool, mtype: str | None) -> list[str]:
        rules = [r for r in await self.rules(conn.user_id) if r["enabled"]]
        if not rules or self.app.runtime.is_module_paused("automation") or settings.get("automation_paused"):
            return []
        text = message.text or message.caption or ""
        fired: list[str] = []
        ai_label: str | None = None
        ai_checked = False
        for rule in rules:
            trig = rule["trigger"]
            tt = trig["type"]
            ok = False
            if tt == "message":
                ok = True
            elif tt == "keyword":
                ok = self.match_keyword(trig, text)
            elif tt == "media":
                ok = mtype in trig["types"]
            elif tt == "contact":
                ok = message.chat.id in trig["chat_ids"]
            elif tt == "new_chat":
                ok = is_new
            elif tt == "ai_class":
                if not ai_checked:
                    ai_label = await self.classify(conn.user_id, text)
                    ai_checked = True
                ok = ai_label == trig["label"]
            if not ok or not await self.conditions_ok(conn.user_id, rule, settings, chat_row):
                continue
            key = (rule["id"], message.chat.id)
            if rule["cooldown_sec"] and time.time() - self._cooldown.get(key, 0) < rule["cooldown_sec"]:
                continue
            self._cooldown[key] = time.time()
            await self.execute(rule, conn=conn, chat_id=message.chat.id, message=message, settings=settings, chat_row=chat_row)
            fired.append(rule["name"])
        return fired

    async def execute(self, rule: dict[str, Any], *, conn: "Conn | None", chat_id: int | None, message: Message | None,
                      settings: dict[str, Any], chat_row: dict[str, Any] | None, actions: list[dict[str, Any]] | None = None,
                      dry_run: bool = False) -> list[str]:
        app = self.app
        uid = rule["user_id"]
        done: list[str] = []
        status, detail = "ok", ""
        for a in actions or rule["actions"]:
            t = a["type"]
            try:
                if dry_run:
                    done.append(f"{t}:would_run")
                    continue
                if t in CHAT_ACTIONS and (chat_id is None or conn is None):
                    done.append(f"{t}:skipped(no chat)")
                    continue
                if t in ("reply", "reply_template", "ai_reply"):
                    why = app.pipeline.gate(conn, settings, chat_row or {"chat_id": chat_id}, False)
                    if why:
                        done.append(f"{t}:blocked({why})")
                        continue
                if t == "reply":
                    from ..modules.autoreply import fill
                    owner = await app.pipeline.owner_name(conn)
                    name = (chat_row or {}).get("title") or ""
                    ok = await app.pipeline.send_auto(conn, chat_id, fill(esc(a["text"]), name=esc(name), owner=esc(owner),
                                                                          tz_name=settings.get("timezone") or app.config.timezone),
                                                      message.message_id if message else None, "automation")
                    done.append(f"reply:{'sent' if ok else 'failed'}")
                elif t == "reply_template":
                    row = await app.db.fetchone("SELECT text FROM reply_templates WHERE user_id=? AND name=?", (uid, a["name"]))
                    if row:
                        ok = await app.pipeline.send_auto(conn, chat_id, esc(row["text"]), message.message_id if message else None, "automation")
                        done.append(f"reply_template:{'sent' if ok else 'failed'}")
                    else:
                        done.append("reply_template:missing")
                elif t == "ai_reply":
                    if message is not None and app.ai.available() and app.ai_auto is not None:
                        app.ai_auto.schedule(conn, message, {**settings, "mode": "ai"}, chat_row or {"chat_id": chat_id})
                        done.append("ai_reply:scheduled")
                    else:
                        done.append("ai_reply:unavailable")
                elif t == "set_mode":
                    await app.autoreply.set_mode(uid, a["mode"])
                    done.append(f"set_mode:{a['mode']}")
                elif t == "afk_on":
                    await app.afk.enable(uid, a.get("reason") or None, a["minutes"] * 60 if a.get("minutes") else None)
                    done.append("afk_on")
                elif t == "afk_off":
                    await app.afk.disable(uid, reason="automation")
                    done.append("afk_off")
                elif t == "notify":
                    title = (chat_row or {}).get("title")
                    body = a["text"] + (f"\n💬 {title}" if title else "")
                    await app.notifications.notify(uid, "automation", f"⚙️ {rule['name']}", body, push=True)
                    done.append("notify")
                elif t == "tag":
                    tags = list((chat_row or {}).get("tags") or [])
                    if a["tag"] not in tags:
                        tags.append(a["tag"])
                        await app.chats.update(uid, chat_id, {"tags": tags[:20]})
                    done.append(f"tag:{a['tag']}")
                elif t == "timer":
                    await app.scheduler.add(uid, "automation_delayed", {"rule_id": rule["id"], "chat_id": chat_id, "conn": conn.id if conn else None,
                                                                        "actions": a["then"]}, int(time.time()) + a["minutes"] * 60)
                    done.append(f"timer:{a['minutes']}m")
                elif t == "remind":
                    await app.scheduler.add(uid, "reminder", {"text": a["text"]}, int(time.time()) + a["minutes"] * 60)
                    done.append("remind")
                elif t == "handoff":
                    await app.chats.set_owner_pause(uid, chat_id, 60)
                    await app.notifications.notify(uid, "handoff", tr(settings["lang"], "engine.peredacha_vladeltsu"),
                                                   f"{(chat_row or {}).get('title') or chat_id}", level="warning", push=True)
                    done.append("handoff")
                elif t == "mark_read":
                    if conn.can("can_read_messages") and message is not None:
                        res = await app.sender.read(chat_id, message.message_id, conn.id)
                        done.append(f"mark_read:{'ok' if res.ok else res.kind}")
                    else:
                        done.append("mark_read:no_right")
                elif t == "set_priority":
                    await app.chats.update(uid, chat_id, {"priority": a["value"]})
                    done.append("set_priority")
            except Exception as e:
                status = "partial"
                detail = f"{t}: {type(e).__name__}"
                log.warning("automation action %s failed: %s", t, e)
        if not dry_run:
            await app.db.execute("INSERT INTO automation_executions(rule_id, user_id, chat_id, status, detail, created_at) VALUES (?,?,?,?,?,?)",
                                 (rule["id"], uid, chat_id, status, (detail or ", ".join(done))[:500], int(time.time())))
            await app.db.execute("UPDATE automation_rules SET run_count=run_count+1, last_run_at=? WHERE id=?", (int(time.time()), rule["id"]))
            await app.metrics.incr("automation_runs", uid)
            app.events.emit("automation", user_id=uid, rule=rule["name"], result=done)
        return done

    async def dry_run(self, user_id: int, rule: dict[str, Any], sample_text: str = "", media: str | None = None,
                      is_new: bool = False) -> dict[str, Any]:
        """APK 'test rule' button: evaluate trigger+conditions against a sample, never sends anything."""
        v = validate_rule(rule)
        trig = v["trigger"]
        tt = trig["type"]
        settings = await self.app.settings.all(user_id)
        matched = {"message": True, "keyword": self.match_keyword(trig, sample_text) if tt == "keyword" else False,
                   "media": media in trig.get("types", []), "new_chat": is_new, "contact": True,
                   "time": True, "no_reply": True, "ai_class": None}.get(tt, False)
        if tt == "ai_class":
            label = await self.classify(user_id, sample_text)
            matched = label == trig["label"]
        cond_ok = await self.conditions_ok(user_id, {**v, "user_id": user_id}, settings, {"tags": []})
        actions = await self.execute({**v, "id": 0, "user_id": user_id}, conn=None, chat_id=0, message=None, settings=settings,
                                     chat_row={"chat_id": 0}, dry_run=True)
        return {"trigger_matched": bool(matched), "conditions_ok": cond_ok, "would_fire": bool(matched) and cond_ok, "actions": actions}

    # ---- periodic triggers ---------------------------------------------------------------------
    async def tick_time(self) -> int:
        rows = await self.app.db.fetchall("SELECT DISTINCT user_id FROM automation_rules WHERE enabled=1 AND trigger_json LIKE '%\"time\"%'")
        fired = 0
        for r in rows:
            uid = r["user_id"]
            settings = await self.app.settings.all(uid)
            tz_name = settings.get("timezone") or self.app.config.timezone
            now = local_dt(None, tz_name)
            today_key = now.strftime("%Y-%m-%d")
            for rule in await self.rules(uid):
                trig = rule["trigger"]
                if not rule["enabled"] or trig["type"] != "time" or now.isoweekday() not in trig["days"]:
                    continue
                h, m = map(int, trig["at"].split(":"))
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                last = local_dt(rule["last_run_at"], tz_name).strftime("%Y-%m-%d") if rule.get("last_run_at") else None
                if 0 <= (now - target).total_seconds() < 300 and last != today_key:
                    if await self.conditions_ok(uid, rule, settings, None):
                        await self.execute(rule, conn=None, chat_id=None, message=None, settings=settings, chat_row=None)
                        rule["last_run_at"] = int(time.time())
                        fired += 1
        return fired

    async def tick_no_reply(self) -> int:
        rows = await self.app.db.fetchall("SELECT DISTINCT user_id FROM automation_rules WHERE enabled=1 AND trigger_json LIKE '%no_reply%'")
        fired = 0
        now = int(time.time())
        for r in rows:
            uid = r["user_id"]
            settings = await self.app.settings.all(uid)
            conn = await self.app.connections.primary_for_user(uid)
            for rule in await self.rules(uid):
                if not rule["enabled"] or rule["trigger"]["type"] != "no_reply":
                    continue
                mins = rule["trigger"]["minutes"]
                chats = await self.app.db.fetchall(
                    "SELECT * FROM chat_settings WHERE user_id=? AND unanswered>0 AND last_incoming_at <= ? AND last_incoming_at > ? "
                    "AND last_incoming_at > COALESCE(last_outgoing_at, 0)", (uid, now - mins * 60, now - mins * 60 - 86400))
                for chat in chats:
                    key = (rule["id"], chat["chat_id"])
                    if self._noreply_fired.get(key) == chat["last_incoming_at"]:
                        continue
                    self._noreply_fired[key] = chat["last_incoming_at"]
                    chat["tags"] = loads(chat.pop("tags_json", "[]"), [])
                    if await self.conditions_ok(uid, rule, settings, chat):
                        await self.execute(rule, conn=conn, chat_id=chat["chat_id"], message=None, settings=settings, chat_row=chat)
                        fired += 1
        return fired

    async def run_delayed(self, task: dict[str, Any]) -> None:
        p = task["payload"]
        uid = task["user_id"]
        rule = await self.get(uid, p.get("rule_id") or 0) or {"id": p.get("rule_id") or 0, "user_id": uid, "name": "delayed", "actions": []}
        conn = await self.app.connections.get(p["conn"]) if p.get("conn") else None
        if conn is not None and conn.user_id != uid:
            return
        chat_row = await self.app.chats.get(uid, p["chat_id"]) if p.get("chat_id") else None
        await self.execute(rule, conn=conn, chat_id=p.get("chat_id"), message=None, settings=await self.app.settings.all(uid),
                           chat_row=chat_row, actions=p.get("actions") or [])


def _k(tid: str, part: str) -> str:
    return f"automation.tpl.{tid}.{part}"


# Texts are translation keys; they are rendered in the owner's language when the template is listed or installed.
TEMPLATES: list[dict[str, Any]] = [
    {"id": "night_afk", "title": _k("night_afk", "title"), "description": _k("night_afk", "desc"),
     "rules": [{"name": _k("night_afk", "r1"), "trigger": {"type": "time", "at": "23:00"}, "actions": [{"type": "afk_on", "reason": _k("night_afk", "reason")}]},
               {"name": _k("night_afk", "r2"), "trigger": {"type": "time", "at": "08:00"}, "actions": [{"type": "afk_off"}]}]},
    {"id": "price_reply", "title": _k("price_reply", "title"), "description": _k("price_reply", "desc"),
     "rules": [{"name": _k("price_reply", "r1"), "trigger": {"type": "keyword", "keywords": ["цена", "прайс", "стоимость", "narx", "price"], "match": "contains"},
                "actions": [{"type": "reply", "text": _k("price_reply", "text")}], "cooldown_sec": 3600}]},
    {"id": "urgent_alert", "title": _k("urgent_alert", "title"), "description": _k("urgent_alert", "desc"),
     "rules": [{"name": _k("urgent_alert", "r1"), "trigger": {"type": "keyword", "keywords": ["срочно", "urgent", "shoshilinch", "asap"], "match": "contains"},
                "actions": [{"type": "notify", "text": _k("urgent_alert", "text")}, {"type": "set_priority", "value": 3}], "cooldown_sec": 600}]},
    {"id": "no_reply_reminder", "title": _k("no_reply_reminder", "title"), "description": _k("no_reply_reminder", "desc"),
     "rules": [{"name": _k("no_reply_reminder", "r1"), "trigger": {"type": "no_reply", "minutes": 60},
                "actions": [{"type": "notify", "text": _k("no_reply_reminder", "text")}]}]},
    {"id": "voice_notice", "title": _k("voice_notice", "title"), "description": _k("voice_notice", "desc"),
     "rules": [{"name": _k("voice_notice", "r1"), "trigger": {"type": "media", "types": ["voice", "video_note"]},
                "actions": [{"type": "notify", "text": _k("voice_notice", "text")}], "cooldown_sec": 300}]},
    {"id": "weekend", "title": _k("weekend", "title"), "description": _k("weekend", "desc"),
     "rules": [{"name": _k("weekend", "r1"), "trigger": {"type": "time", "at": "10:00", "days": [6]}, "actions": [{"type": "afk_on", "reason": _k("weekend", "reason")}]},
               {"name": _k("weekend", "r2"), "trigger": {"type": "time", "at": "09:00", "days": [1]},
                "actions": [{"type": "afk_off"}, {"type": "set_mode", "mode": "business"}]}]},
    {"id": "new_chat_welcome", "title": _k("new_chat_welcome", "title"), "description": _k("new_chat_welcome", "desc"),
     "rules": [{"name": _k("new_chat_welcome", "r1"), "trigger": {"type": "new_chat"},
                "actions": [{"type": "reply", "text": _k("new_chat_welcome", "text")}, {"type": "tag", "tag": "new"}]}]},
    {"id": "ai_questions", "title": _k("ai_questions", "title"), "description": _k("ai_questions", "desc"),
     "rules": [{"name": _k("ai_questions", "r1"), "trigger": {"type": "ai_class", "label": "question"}, "actions": [{"type": "ai_reply"}], "cooldown_sec": 120}]},
    {"id": "order_handoff", "title": _k("order_handoff", "title"), "description": _k("order_handoff", "desc"),
     "rules": [{"name": _k("order_handoff", "r1"), "trigger": {"type": "keyword", "keywords": ["заказ", "купить", "order", "buyurtma"], "match": "contains"},
                "actions": [{"type": "reply", "text": _k("order_handoff", "text")}, {"type": "handoff"}], "cooldown_sec": 1800}]},
]
_TEXT_FIELDS = ("title", "description", "name", "text", "reason")


def localize(obj: Any, lang: str) -> Any:
    """Deep copy of a template/rule with every translation-key text rendered in ``lang``."""
    from ..localization import has, tr
    if isinstance(obj, dict):
        return {k: (tr(lang, v) if k in _TEXT_FIELDS and isinstance(v, str) and has(v) else localize(v, lang)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(x, lang) for x in obj]
    return obj


def templates_for(lang: str) -> list[dict[str, Any]]:
    return localize(TEMPLATES, lang)


def triggers_for(lang: str) -> dict[str, str]:
    from ..localization import tr
    return {k: tr(lang, v) for k, v in TRIGGERS.items()}


async def install_template(engine: AutomationEngine, user_id: int, template_id: str, lang: str = "ru") -> list[dict[str, Any]]:
    tpl = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if tpl is None:
        raise RuleError("unknown template")
    out = []
    for r in localize(tpl["rules"], lang):
        out.append(await engine.create(user_id, {**r, "template_id": template_id}))
    return out
