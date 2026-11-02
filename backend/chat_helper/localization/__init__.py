"""Localization Manager: JSON catalogs with translation keys (``locales/<lang>.json``).

* Code never contains user-facing text, only keys: ``tr(lang, "afk.afk_vklyuchen", d=...)``.
* Every language is a flat ``{key: text}`` JSON file; placeholders use ``{name}`` (str.format).
* Russian (``ru``) is the reference catalog; tests guarantee every key exists in every shipped language with the
  same placeholders, that Uzbek texts contain no Cyrillic, and that every key used in the code exists.
* Adding a language = copying ``ru.json`` to ``<lang>.json``, translating it and adding the code to ``LANGS``.
"""
from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).with_name("locales")
LANGS = ("ru", "uz")
DEFAULT_LANG = "ru"
_catalogs: dict[str, dict[str, str]] = {}


def load(force: bool = False) -> dict[str, dict[str, str]]:
    if _catalogs and not force:
        return _catalogs
    _catalogs.clear()
    for path in sorted(LOCALES_DIR.glob("*.json")):
        _catalogs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return _catalogs


def catalog(lang: str) -> dict[str, str]:
    return load().get(lang, {})


def has(key: str, lang: str = DEFAULT_LANG) -> bool:
    return key in catalog(lang)


def tr(lang: str | None, key: str, **kw: Any) -> str:
    """Translate ``key`` into ``lang`` (falls back to the reference catalog, then to the key itself)."""
    cats = load()
    text = cats.get(lang or DEFAULT_LANG, {}).get(key)
    if text is None:
        text = cats.get(DEFAULT_LANG, {}).get(key, key)
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def p(lang: str | None, key: str, **kw: Any) -> str:
    """Shared phrases (``common.*`` keys)."""
    return tr(lang, "common." + key, **kw)


def on_off(lang: str | None, v: bool | None) -> str:
    return ("🟢 " + p(lang, "on")) if v else ("⚪️ " + p(lang, "off"))
