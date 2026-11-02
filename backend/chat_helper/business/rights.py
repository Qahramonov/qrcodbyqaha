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

# Titles follow the Telegram «Chat automation» permissions screen (2026 clients).
RIGHT_TITLES: dict[str, str] = {
    "can_reply": "rights.right_titles.otvety_soobscheniya",
    "can_read_messages": "rights.right_titles.otmetki_prochtenii",
    "can_delete_sent_messages": "rights.right_titles.udalenie_ishodyaschih_soobscheniya_bota",
    "can_delete_all_messages": "rights.right_titles.udalenie_vhodyaschih_vse_soobscheniya",
    "can_edit_name": "rights.right_titles.menyat_imya",
    "can_edit_bio": "rights.right_titles.menyat_bio",
    "can_edit_profile_photo": "rights.right_titles.menyat_foto_profilya",
    "can_edit_username": "rights.right_titles.menyat_username",
    "can_change_gift_settings": "rights.right_titles.nastroyki_podarkov",
    "can_view_gifts_and_stars": "rights.right_titles.prosmotr_podarkov_stars",
    "can_convert_gifts_to_stars": "rights.right_titles.konvertatsiya_podarkov",
    "can_transfer_and_upgrade_gifts": "rights.right_titles.peredacha_podarkov",
    "can_transfer_stars": "rights.right_titles.peredacha_stars",
    "can_manage_stories": "rights.right_titles.upravlenie_istoriyami",
}

# Capabilities used by Chat helper -> required rights (all must be present).
CAPABILITIES: dict[str, dict[str, Any]] = {
    "reply": {"rights": ["can_reply"], "title": "rights.cap.reply"},
    "edit_own": {"rights": ["can_reply"], "title": "rights.cap.edit_own"},
    "typing": {"rights": ["can_reply"], "title": "rights.cap.typing"},
    "read": {"rights": ["can_read_messages"], "title": "rights.cap.read"},
    "delete_bot": {"rights": ["can_delete_sent_messages"], "title": "rights.cap.delete_bot"},
    "delete_any": {"rights": ["can_delete_all_messages"], "title": "rights.cap.delete_any"},
    "profile_name": {"rights": ["can_edit_name"], "title": "rights.cap.profile_name"},
    "profile_bio": {"rights": ["can_edit_bio"], "title": "rights.cap.profile_bio"},
    "profile_photo": {"rights": ["can_edit_profile_photo"], "title": "rights.cap.profile_photo"},
    "mute": {"rights": ["can_delete_all_messages"], "title": "rights.cap.mute"},
    "protect": {"rights": ["can_reply"], "title": "rights.cap.protect"},
    "controls": {"rights": ["can_reply"], "title": "rights.cap.controls"},
}


def command_dependencies(registry: Any) -> dict[str, list[str]]:
    """right -> commands that need it in business chats (from the Command Registry)."""
    out: dict[str, list[str]] = {r: [] for r in RIGHT_FLAGS}
    for spec in registry.commands.values():
        if spec.admin_only:
            continue
        for r in spec.rights:
            out.setdefault(r, []).append(spec.id)
    return {k: sorted(v) for k, v in out.items()}

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
    "connected": ("rights.status_titles.podklyucheno"),
    "disabled": ("rights.status_titles.otklyucheno"),
    "limited": ("rights.status_titles.ogranicheno"),
    "missing_permission": ("rights.status_titles.hvataet_prav"),
    "reconnection_required": ("rights.status_titles.trebuetsya_perepodklyuchenie"),
}


def status_title(status: str, lang: str) -> str:
    key = STATUS_TITLES.get(status)
    return tr(lang, key) if key else status


def right_title(right: str, lang: str) -> str:
    key = RIGHT_TITLES.get(right)
    return tr(lang, key) if key else right


FIX_HINT = "rights.fix_hint.telegram_nastroyki_izm_avtomatizatsiya_chatov"


def inspect(rights: dict[str, bool], is_enabled: bool, lang: str = "ru", paused: bool = False) -> dict[str, Any]:
    caps = []
    for name, cap in CAPABILITIES.items():
        missing = [r for r in cap["rights"] if not rights.get(r)]
        caps.append({
            "capability": name,
            "available": is_enabled and not missing,
            "description": tr(lang, cap["title"]),
            "missing_rights": missing,
            "missing_titles": [right_title(r, lang) for r in missing],
        })
    dangerous_on = [r for r in DANGEROUS if rights.get(r)]
    status = connection_status(is_enabled, rights, paused)
    advice = []
    if not is_enabled:
        advice.append(tr(lang, "rights.podklyuchenie_vyklyucheno_otkroyte_telegram_nast"))
    if any(c["missing_rights"] for c in caps):
        advice.append(tr(lang, FIX_HINT))
    if dangerous_on:
        advice.append(tr(lang, "rights.chat_helper_ispolzuet_finansovye_prava")
                      + ", ".join(right_title(r, lang) for r in dangerous_on))
    advice.append(tr(lang, "rights.bot_mozhet_otvechat_tolko_chatah"))
    return {
        "status": status,
        "status_title": status_title(status, lang),
        "rights": {r: rights.get(r, False) for r in RIGHT_FLAGS},
        "rights_titles": {r: right_title(r, lang) for r in RIGHT_FLAGS},
        "capabilities": caps,
        "dangerous_enabled": dangerous_on,
        "advice": advice,
    }


def explain_command_failure(required: list[str], rights: dict[str, bool], lang: str) -> str | None:
    missing = [r for r in required if not rights.get(r)]
    if not missing:
        return None
    names = ", ".join(right_title(r, lang) for r in missing)
    return tr(lang, "rights.hvataet_prav_biznes_bota",
              names=names, hint=tr(lang, FIX_HINT))
