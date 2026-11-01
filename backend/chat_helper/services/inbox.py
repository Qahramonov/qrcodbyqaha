"""Smart Inbox: chat priority detection, important-message alerts, unanswered tracking, daily digest."""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..localization import tr
from ..security.sanitize import clip, esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)

_URGENT_PUNCT = re.compile(r"!{2,}|\?{2,}")


def priority_score(text: str, keywords: list[str], unanswered: int, chat_priority: int, is_new: bool) -> tuple[int, list[str]]:
    t = (text or "").lower()
    score, reasons = 0, []
    hits = [k for k in keywords if k and k.lower() in t]
    if hits:
        score += 5
        reasons.append("keyword:" + ",".join(hits[:3]))
    if "?" in t:
        score += 1
        reasons.append("question")
    if _URGENT_PUNCT.search(t):
        score += 1
        reasons.append("emphasis")
    if text and text.isupper() and len(text) > 8:
        score += 1
        reasons.append("caps")
    if unanswered >= 3:
        score += min(3, unanswered - 2)
        reasons.append(f"unanswered:{unanswered}")
    if chat_priority:
        score += chat_priority * 2
        reasons.append(f"chat_priority:{chat_priority}")
    if is_new:
        score += 1
        reasons.append("new_chat")
    return score, reasons


class InboxService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._last_alert: dict[tuple[int, int], float] = {}

    async def on_incoming(self, user_id: int, chat_row: dict[str, Any], text: str, settings: dict[str, Any],
                          is_new: bool) -> int:
        chat_id = chat_row["chat_id"]
        score, reasons = priority_score(text, settings.get("important_keywords") or [], chat_row.get("unanswered", 0),
                                        chat_row.get("priority", 0), is_new)
        await self.app.chats.set_priority_score(user_id, chat_id, score)
        muted = (chat_row.get("muted_until") or 0) > time.time()
        lang = settings["lang"]
        title = esc(chat_row.get("title") or chat_id)
        if is_new and settings.get("notify_new_chats") and not muted:
            await self.app.notifications.notify(user_id, "new_chat", tr(lang, "Новый собеседник", "Yangi suhbatdosh"),
                                                tr(lang, "{t} написал(а) впервые", "{t} birinchi marta yozdi", t=title), push=True)
        if any(r.startswith("keyword:") for r in reasons) and settings.get("notify_important") and not muted:
            key = (user_id, chat_id)
            if time.time() - self._last_alert.get(key, 0) > 600:
                self._last_alert[key] = time.time()
                body = clip(text or "", 300) if settings.get("store_previews", True) else ""
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=tr(lang, "💡 Варианты ответа", "💡 Javob variantlari"), callback_data=f"hint:{chat_id}"),
                    InlineKeyboardButton(text=tr(lang, "🔕 Заглушить 2ч", "🔕 2 soat jim"), callback_data=f"cmute:{chat_id}"),
                ]])
                await self.app.notifications.notify(user_id, "important", tr(lang, "Важное сообщение", "Muhim xabar"),
                                                    f"{title}: {body}", level="warning")
                await self.app.sender.send_text(
                    user_id, tr(lang, "❗️ <b>Важное сообщение</b> от {t}\n\n{b}", "❗️ <b>Muhim xabar</b> {t} dan\n\n{b}",
                                t=title, b=esc(body)), markup=kb)
        return score

    async def unanswered(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        return await self.app.db.fetchall(
            "SELECT chat_id, title, username, unanswered, last_incoming_at, last_preview, priority_score, priority "
            "FROM chat_settings WHERE user_id=? AND unanswered>0 ORDER BY priority DESC, priority_score DESC, last_incoming_at DESC LIMIT ?",
            (user_id, limit))

    async def digest_text(self, user_id: int, lang: str, use_ai: bool = False) -> str:
        rows = await self.unanswered(user_id, 15)
        if not rows:
            return tr(lang, "📭 Неотвеченных чатов нет. Отличная работа!", "📭 Javobsiz chatlar yo'q. Ajoyib!")
        lines = [tr(lang, "📬 <b>Smart Inbox — ждут ответа ({n})</b>", "📬 <b>Smart Inbox — javob kutmoqda ({n})</b>", n=len(rows))]
        for r in rows:
            mark = "🔥" if r["priority_score"] >= 5 else "•"
            prev = f" — <i>{esc(clip(r['last_preview'] or '', 60))}</i>" if r.get("last_preview") else ""
            lines.append(f"{mark} {esc(r['title'] or r['chat_id'])} ({r['unanswered']}){prev}")
        text = "\n".join(lines)
        if use_ai and self.app.ai.available():
            try:
                material = "\n".join(f"{r['title']}: {r['last_preview'] or ''} (unanswered {r['unanswered']})" for r in rows)
                res = await self.app.ai.complete(
                    user_id, [{"role": "user", "content": material}], kind="summary",
                    system=tr(lang, "Кратко (3-5 пунктов) подскажи владельцу, кому ответить в первую очередь и почему. Не выдумывай фактов.",
                              "Egasiga 3-5 bandda kimga birinchi navbatda javob berish kerakligini qisqacha ayting. Faktlarni to'qimang."),
                    max_tokens=300)
                text += "\n\n🧠 " + esc(res.text)
            except Exception as e:  # AI optional
                log.info("digest AI failed: %s", type(e).__name__)
        return text
