"""Business bot rights model + Permission Inspector.

Maps every Chat helper capability to the official ``BusinessBotRights`` flags (Bot API 9.0+),
explains what is missing and how to fix it in Telegram settings.
"""
from __future__ import annotations

from typing import Any

from ..localization import tr

RIGHT_FLAGS = (
    "can_reply", "can_read_messages", "can_delete_sent_messages", "can_delete_all_messages",
    "can_edit_name", "can_edit_bio", "can_edit_profile_photo", "can_edit_username",
    "can_change_gift_settings", "can_view_gifts_and_stars", "can_convert_gifts_to_stars",
    "can_transfer_and_upgrade_gifts", "can_transfer_stars", "can_manage_stories",
)

RIGHT_TITLES: dict[str, tuple[str, str]] = {
    "can_reply": ("Отвечать на сообщения", "Xabarlarga javob berish"),
    "can_read_messages": ("Отмечать сообщения прочитанными", "Xabarlarni o'qilgan deb belgilash"),
    "can_delete_sent_messages": ("Удалять сообщения бота", "Bot xabarlarini o'chirish"),
    "can_delete_all_messages": ("Удалять все сообщения", "Barcha xabarlarni o'chirish"),
    "can_edit_name": ("Менять имя", "Ismni o'zgartirish"),
    "can_edit_bio": ("Менять био", "Bio'ni o'zgartirish"),
    "can_edit_profile_photo": ("Менять фото профиля", "Profil rasmini o'zgartirish"),
    "can_edit_username": ("Менять username", "Username'ni o'zgartirish"),
    "can_change_gift_settings": ("Настройки подарков", "Sovg'a sozlamalari"),
    "can_view_gifts_and_stars": ("Просмотр подарков и Stars", "Sovg'alar va Stars'ni ko'rish"),
    "can_convert_gifts_to_stars": ("Конвертация подарков", "Sovg'alarni konvertatsiya qilish"),
    "can_transfer_and_upgrade_gifts": ("Передача подарков", "Sovg'alarni o'tkazish"),
    "can_transfer_stars": ("Передача Stars", "Stars o'tkazish"),
    "can_manage_stories": ("Управление историями", "Hikoyalarni boshqarish"),
}

# Capabilities used by Chat helper -> required rights (all must be present).
CAPABILITIES: dict[str, dict[str, Any]] = {
    "reply": {"rights": ["can_reply"], "ru": "Автоответы, AFK, AI-ответы, результаты команд в чате",
              "uz": "Avtojavoblar, AFK, AI-javoblar, chatdagi buyruq natijalari"},
    "edit_own": {"rights": ["can_reply"], "ru": "Редактирование ваших сообщений-команд (результат на месте)",
                 "uz": "Buyruq xabarlaringizni tahrirlash (natija joyida)"},
    "typing": {"rights": ["can_reply"], "ru": "Статусы «печатает…», «записывает…»",
               "uz": "«yozmoqda…», «yozib olmoqda…» holatlari"},
    "read": {"rights": ["can_read_messages"], "ru": "Отметка входящих как прочитанных",
             "uz": "Kiruvchi xabarlarni o'qilgan deb belgilash"},
    "delete_bot": {"rights": ["can_delete_sent_messages"], "ru": "Удаление сообщений, отправленных ботом (.timer)",
                   "uz": "Bot yuborgan xabarlarni o'chirish (.timer)"},
    "delete_any": {"rights": ["can_delete_all_messages"], "ru": "Удаление ваших команд из чата после выполнения",
                   "uz": "Bajarilgandan keyin buyruqlaringizni chatdan o'chirish"},
    "profile_name": {"rights": ["can_edit_name"], "ru": "Команда .name и часы в фамилии",
                     "uz": ".name buyrug'i va familiyadagi soat"},
    "profile_bio": {"rights": ["can_edit_bio"], "ru": "Команда .bio и часы в био", "uz": ".bio buyrug'i va bio'dagi soat"},
    "profile_photo": {"rights": ["can_edit_profile_photo"], "ru": "Команда .avatar", "uz": ".avatar buyrug'i"},
}

# Dangerous rights that Chat helper never needs and recommends to keep OFF.
DANGEROUS = ("can_transfer_stars", "can_transfer_and_upgrade_gifts", "can_convert_gifts_to_stars",
             "can_change_gift_settings", "can_edit_username")


def rights_from_obj(rights: Any) -> dict[str, bool]:
    """Normalize aiogram BusinessBotRights / dict / None to a dict of booleans."""
    out = {k: False for k in RIGHT_FLAGS}
    if rights is None:
        return out
    if hasattr(rights, "model_dump"):
        data = rights.model_dump()
    elif isinstance(rights, dict):
        data = rights
    else:
        data = {}
    for k in RIGHT_FLAGS:
        out[k] = bool(data.get(k))
    return out


def has(rights: dict[str, bool], capability: str) -> bool:
    cap = CAPABILITIES.get(capability)
    if not cap:
        return False
    return all(rights.get(r) for r in cap["rights"])


def connection_status(is_enabled: bool, rights: dict[str, bool], paused: bool = False) -> str:
    """Connected | Disabled | Limited | Missing Permission | Reconnection Required."""
    if not is_enabled:
        return "disabled"
    if not rights.get("can_reply"):
        return "missing_permission"
    if paused:
        return "limited"
    core = ("can_read_messages", "can_delete_sent_messages")
    if not all(rights.get(r) for r in core):
        return "limited"
    return "connected"


STATUS_TITLES = {
    "connected": ("🟢 Подключено", "🟢 Ulangan"),
    "disabled": ("⚫️ Отключено", "⚫️ Uzilgan"),
    "limited": ("🟡 Ограничено", "🟡 Cheklangan"),
    "missing_permission": ("🟠 Не хватает прав", "🟠 Huquqlar yetarli emas"),
    "reconnection_required": ("🔴 Требуется переподключение", "🔴 Qayta ulanish kerak"),
}


def status_title(status: str, lang: str) -> str:
    ru, uz = STATUS_TITLES.get(status, (status, status))
    return tr(lang, ru, uz)


FIX_HINT = (
    "Telegram → Настройки → Telegram для бизнеса → Чат-боты → Chat helper → включите нужные разрешения.",
    "Telegram → Sozlamalar → Telegram Business → Chat-botlar → Chat helper → kerakli ruxsatlarni yoqing.",
)


def inspect(rights: dict[str, bool], is_enabled: bool, lang: str = "ru", paused: bool = False) -> dict[str, Any]:
    caps = []
    for name, cap in CAPABILITIES.items():
        missing = [r for r in cap["rights"] if not rights.get(r)]
        caps.append({
            "capability": name,
            "available": is_enabled and not missing,
            "description": cap["uz" if lang == "uz" else "ru"],
            "missing_rights": missing,
            "missing_titles": [tr(lang, *RIGHT_TITLES[r]) for r in missing],
        })
    dangerous_on = [r for r in DANGEROUS if rights.get(r)]
    status = connection_status(is_enabled, rights, paused)
    advice = []
    if not is_enabled:
        advice.append(tr(lang, "Подключение выключено. Откройте Telegram → Настройки → Telegram для бизнеса → Чат-боты и подключите Chat helper заново.",
                         "Ulanish o'chirilgan. Telegram → Sozlamalar → Telegram Business → Chat-botlar orqali Chat helper'ni qayta ulang."))
    if any(c["missing_rights"] for c in caps):
        advice.append(tr(lang, *FIX_HINT))
    if dangerous_on:
        advice.append(tr(lang, "Chat helper не использует финансовые права (Stars, подарки). Рекомендуем их выключить: ",
                         "Chat helper moliyaviy huquqlardan (Stars, sovg'alar) foydalanmaydi. Ularni o'chirib qo'yish tavsiya etiladi: ")
                      + ", ".join(tr(lang, *RIGHT_TITLES[r]) for r in dangerous_on))
    advice.append(tr(lang, "Бот может отвечать только в чатах, где собеседник писал за последние 24 часа (правило Telegram).",
                     "Bot faqat suhbatdosh so'nggi 24 soat ichida yozgan chatlarda javob bera oladi (Telegram qoidasi)."))
    return {
        "status": status,
        "status_title": status_title(status, lang),
        "rights": {r: rights.get(r, False) for r in RIGHT_FLAGS},
        "rights_titles": {r: tr(lang, *RIGHT_TITLES[r]) for r in RIGHT_FLAGS},
        "capabilities": caps,
        "dangerous_enabled": dangerous_on,
        "advice": advice,
    }


def explain_command_failure(required: list[str], rights: dict[str, bool], lang: str) -> str | None:
    missing = [r for r in required if not rights.get(r)]
    if not missing:
        return None
    names = ", ".join(tr(lang, *RIGHT_TITLES.get(r, (r, r))) for r in missing)
    return tr(lang, "🔐 Не хватает прав бизнес-бота: {names}.\n{hint}", "🔐 Biznes-bot huquqlari yetarli emas: {names}.\n{hint}",
              names=names, hint=tr(lang, *FIX_HINT))
