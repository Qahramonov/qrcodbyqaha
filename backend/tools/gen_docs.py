"""Generate docs/COMMANDS.md and docs/API.md from the live code (command registry + FastAPI routes)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from chat_helper.app import build_app  # noqa: E402
from chat_helper.commands.registry import CATEGORIES  # noqa: E402
from chat_helper.config import load_settings  # noqa: E402
from chat_helper.localization import tr  # noqa: E402

STATUS_RU = {"IMPLEMENTED": "✅ реализовано", "REQUIRES_API_KEY": "🔑 нужен AI-ключ", "LIMITED_BY_TELEGRAM": "⚠️ ограничено Telegram",
             "NOT_SUPPORTED": "⛔ не поддерживается Bot API", "REQUIRES_PERMISSION": "🔐 нужно право"}


def commands_md(registry) -> str:
    out = ["# Chat helper — команды / buyruqlar", "",
           "> Файл сгенерирован автоматически из Command Registry (`backend/tools/gen_docs.py`). "
           f"Всего команд: **{len(registry)}**. Префикс по умолчанию `.` (меняется в настройках: `.` `!` `-` `,`).", "",
           "Команды выполняет **только владелец** бизнес-аккаунта: в любом подключённом чате или в личном чате с ботом. "
           "Пробел после префикса допустим (`. afk`), регистр не важен, у команд есть русские/узбекские алиасы.", ""]
    head = ["| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |", "|---|---|---|---|---|---|---|"]

    def row(s) -> str:
        aliases = ", ".join("." + a for a in s.aliases[:4])
        rights = ", ".join(s.rights) or "—"
        deps = (" · deps: " + ", ".join(s.deps)) if s.deps else ""
        return (f"| `.{s.id}`<br><sub>{aliases}</sub> | {s.ru} | {s.uz} | `{s.syntax_for('ru')}` | `{(s.examples_for('ru') or [''])[0]}` | "
                f"{STATUS_RU.get(s.status, s.status)} | {s.min_plan}; {rights}{deps} |")

    for cat, specs in registry.by_category().items():
        specs = [s for s in specs if not s.admin_only]
        if not specs:
            continue
        emoji, key = CATEGORIES.get(cat, ("•", cat))
        out += [f"## {emoji} {tr('ru', key)} / {tr('uz', key)}", "", *head]
        out += [row(s) for s in sorted(specs, key=lambda x: x.id)]
        out.append("")
    admin_specs = sorted((s for s in registry.commands.values() if s.admin_only), key=lambda x: x.id)
    if admin_specs:
        out += ["## 👑 Только Super Admin / faqat Super Admin", "",
                "> Эти команды существуют только для владельца бота (`SUPER_ADMIN_ID`). Для всех остальных они невидимы: "
                "их нет в `.help`, меню и подсказках, а вызов отвечает так же, как неизвестная команда.", "", *head]
        out += [row(s) for s in admin_specs]
        out.append("")
    out += ["## Примечания", "",
            "- `.online` — не поддерживается: Bot API не меняет статус «в сети». Подделок не делаем.",
            "- `.clock` — меняет профиль не чаще 1 раза в 15 минут (лимиты Telegram), с откатом при FloodWait.",
            "- `.timer` — удаляет только то, что разрешает Bot API; это не защищённые «исчезающие» сообщения.",
            "- Медиа: вход до 20 МБ (лимит скачивания Bot API), результат до 50 МБ (лимит отправки).",
            "- Ответ в бизнес-чате возможен, только если собеседник писал за последние 24 часа; иначе результат приходит вам в личку.", ""]
    return "\n".join(out)


def api_md(api) -> str:
    from fastapi.openapi.utils import get_openapi
    spec = get_openapi(title=api.title, version=api.version, routes=api.routes)
    out = ["# Chat helper Control API (v1)", "",
           "> Сгенерировано из OpenAPI (`backend/tools/gen_docs.py`). Живая документация: `http://127.0.0.1:8787/api/docs`.", "",
           "**Базовый адрес:** `http://127.0.0.1:8787/api/v1` (по умолчанию слушает только localhost).", "",
           "**Аутентификация:** одноразовый код из Telegram (`/app`) → `POST /auth/pair` → `access_token` (1 ч) + `refresh_token` (30 дн., ротация). "
           "Все запросы, кроме `/health`, `/auth/pair`, `/auth/refresh`: `Authorization: Bearer <access_token>`.", "",
           "**Ошибки:** `{\"error\": {\"code\": \"...\", \"message\": \"...\"}}` · 401 токен · 403 роль · 404 не найдено/чужое · 409 конфликт · 422 валидация · 429 лимит (`Retry-After`).", "",
           "**Роли:** `user` — только свои данные; `super_admin` (ID из `SUPER_ADMIN_ID`) — всё. "
           "Роль вычисляется на сервере; передача чужого Telegram ID в запросе ничего не даёт.", ""]
    by_tag: dict[str, list[str]] = {}
    for path, methods in sorted(spec.get("paths", {}).items()):
        for method, op in methods.items():
            tag = (op.get("tags") or ["other"])[0]
            by_tag.setdefault(tag, []).append(f"| `{method.upper()}` | `{path.replace('/api/v1', '')}` | {op.get('summary', '')} |")
    for tag in sorted(by_tag):
        out += [f"## {tag}", "", "| Метод | Путь | Описание |", "|---|---|---|", *by_tag[tag], ""]
    out.append(f"Всего эндпоинтов: **{sum(len(v) for v in by_tag.values())}**.")
    return "\n".join(out)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_settings(None, data_dir=Path(tmp))
        app, _ = await build_app(cfg, with_bot=False)
        try:
            from chat_helper.api.server import create_api
            (ROOT / "docs").mkdir(exist_ok=True)
            (ROOT / "docs" / "COMMANDS.md").write_text(commands_md(app.registry), encoding="utf-8")
            (ROOT / "docs" / "API.md").write_text(api_md(create_api(app)), encoding="utf-8")
        finally:
            await app.db.close()
    print("docs generated")


if __name__ == "__main__":
    asyncio.run(main())
