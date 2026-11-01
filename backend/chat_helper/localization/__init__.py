"""Localization (Russian + Uzbek).

Texts live next to the code that uses them via ``tr(lang, ru, uz)`` so both languages are always
provided together. Shared phrases are defined in ``PHRASES``.
"""
from __future__ import annotations

from typing import Any

LANGS = ("ru", "uz")


def tr(lang: str | None, ru: str, uz: str, **kw: Any) -> str:
    s = uz if lang == "uz" else ru
    return s.format(**kw) if kw else s


PHRASES: dict[str, tuple[str, str]] = {
    "back": ("⬅️ Назад", "⬅️ Orqaga"),
    "home": ("🏠 Главная", "🏠 Bosh sahifa"),
    "on": ("включено", "yoqilgan"),
    "off": ("выключено", "o'chirilgan"),
    "yes": ("Да", "Ha"),
    "no": ("Нет", "Yo'q"),
    "confirm": ("✅ Подтвердить", "✅ Tasdiqlash"),
    "cancel": ("✖️ Отмена", "✖️ Bekor qilish"),
    "saved": ("✅ Сохранено", "✅ Saqlandi"),
    "error": ("⚠️ Ошибка", "⚠️ Xatolik"),
    "not_allowed": ("⛔ Недостаточно прав.", "⛔ Huquq yetarli emas."),
    "unknown_cmd": ("❓ Неизвестная команда: {cmd}\nСписок: {prefix}help", "❓ Noma'lum buyruq: {cmd}\nRo'yxat: {prefix}help"),
    "usage": ("ℹ️ Использование: {syntax}", "ℹ️ Foydalanish: {syntax}"),
    "need_reply": ("↩️ Ответьте этой командой на сообщение.", "↩️ Ushbu buyruq bilan xabarga javob bering."),
    "need_media": ("🎞 Ответьте командой на медиа (голосовое, аудио, видео, кружок или фото).",
                   "🎞 Buyruq bilan mediaga javob bering (ovozli, audio, video, dumaloq video yoki rasm)."),
    "rate_limited": ("⏳ Слишком часто. Попробуйте через {sec} с.", "⏳ Juda tez. {sec} soniyadan so'ng urinib ko'ring."),
    "plan_required": ("💎 Команда доступна на тарифе {plan} и выше.", "💎 Buyruq {plan} va undan yuqori tarifda mavjud."),
    "module_off": ("⏸ Модуль «{module}» сейчас выключен.", "⏸ «{module}» moduli hozir o'chirilgan."),
    "emergency": ("🛑 Включён аварийный режим. Автоматизация остановлена.", "🛑 Favqulodda rejim yoqilgan. Avtomatlashtirish to'xtatildi."),
    "requires_ai": ("🧠 AI-провайдер не настроен. Администратор должен добавить API-ключ в .env.",
                    "🧠 AI provayderi sozlanmagan. Administrator .env faylga API kalitini qo'shishi kerak."),
    "done": ("✅ Готово", "✅ Tayyor"),
}


def p(lang: str | None, key: str, **kw: Any) -> str:
    ru, uz = PHRASES.get(key, (key, key))
    return tr(lang, ru, uz, **kw)


def on_off(lang: str | None, v: bool | None) -> str:
    return ("🟢 " + p(lang, "on")) if v else ("⚪️ " + p(lang, "off"))
