"""Inline keyboard helpers."""
from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from ..localization import p


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Rows of (label, data). data prefixes: ``url:`` link (http/https/tg://), ``copy:`` copy-to-clipboard text,
    anything else is callback data (≤ 64 bytes)."""
    out = []
    for row in rows:
        btns = []
        for text, data in row:
            if data.startswith("url:"):
                btns.append(InlineKeyboardButton(text=text, url=data[4:]))
            elif data.startswith("copy:"):
                btns.append(InlineKeyboardButton(text=text, copy_text=CopyTextButton(text=data[5:256])))
            else:
                btns.append(InlineKeyboardButton(text=text, callback_data=data[:64]))
        if btns:
            out.append(btns)
    return InlineKeyboardMarkup(inline_keyboard=out)


def nav(lang: str, back: str = "m:home") -> list[tuple[str, str]]:
    row = [(p(lang, "back"), back)]
    if back != "m:home":
        row.append((p(lang, "home"), "m:home"))
    return row


def toggle(label: str, value: bool, data: str) -> tuple[str, str]:
    return (("🟢 " if value else "⚪️ ") + label, data)


def grid(items: list[tuple[str, str]], cols: int = 2) -> list[list[tuple[str, str]]]:
    return [items[i:i + cols] for i in range(0, len(items), cols)]


def paginate(items: list, page: int, per_page: int) -> tuple[list, int, int]:
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    return items[page * per_page:(page + 1) * per_page], page, pages


def pager(prefix: str, page: int, pages: int) -> list[tuple[str, str]]:
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(("◀️", f"{prefix}:{page - 1}"))
    row.append((f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        row.append(("▶️", f"{prefix}:{page + 1}"))
    return row


def without_tg_links(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Fallback when a client/server rejects tg:// buttons: drop them, keep everything else."""
    rows = []
    for row in markup.inline_keyboard:
        kept = [b for b in row if not (b.url or "").startswith("tg://")]
        if kept:
            rows.append(kept)
    return InlineKeyboardMarkup(inline_keyboard=rows)
