# Chat helper v3

Бот для **Telegram Business** («Автоматизация чатов», официальный Bot API) и приложение **Chat helper Control**. Бот и API
работают целиком на телефоне в Termux (Android 14, ARM64, Python 3.13): без ПК, VPS, root и Docker. Telegram Premium не нужен.

*Telegram Business («Chatlarni avtomatlashtirish») uchun bot va **Chat helper Control** ilovasi. To'liq telefonda, Termux ichida ishlaydi.*

| | |
|---|---|
| 📖 Руководство (RU) · Qo'llanma (UZ) | [docs/README_RU.md](docs/README_RU.md) · [docs/README_UZ.md](docs/README_UZ.md) |
| 📱 Установка в Termux, обновление с v1 | [docs/INSTALL_TERMUX.md](docs/INSTALL_TERMUX.md) · [docs/MIGRATION_V1_TO_V3.md](docs/MIGRATION_V1_TO_V3.md) |
| 🔗 Подключение к Telegram Business | [docs/TELEGRAM_BUSINESS.md](docs/TELEGRAM_BUSINESS.md) |
| 🎛 Карточки управления (Mute, Protect…) | [docs/CHAT_CONTROLS.md](docs/CHAT_CONTROLS.md) |
| 🔐 Права бота · Super Admin и безопасность | [docs/PERMISSIONS.md](docs/PERMISSIONS.md) · [docs/ADMIN_SECURITY.md](docs/ADMIN_SECURITY.md) |
| ⌨️ Команды (160) · 🔌 API (159) | [docs/COMMANDS.md](docs/COMMANDS.md) · [docs/API.md](docs/API.md) |
| 🌐 Локализация RU/UZ | [docs/LOCALIZATION.md](docs/LOCALIZATION.md) |
| 📲 Приложение v3 (Flutter) · дизайн | [docs/BUILD_FLUTTER.md](docs/BUILD_FLUTTER.md) · [docs/FIGMA_DESIGN.md](docs/FIGMA_DESIGN.md) |
| ✅ Статус функций · 🧪 Тесты | [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |

## Быстрый старт

```bash
cd ~/Chat_helper
bash scripts/install_termux.sh   # зависимости, .env, база
nano backend/.env                # BOT_TOKEN=... из @BotFather (Business Mode → ON), SUPER_ADMIN_ID=...
./scripts/start.sh               # бот + локальный API (127.0.0.1:8787) в фоне
./scripts/status.sh              # проверка;  ./scripts/stop.sh — остановить
```

Затем в Telegram: Настройки → Изм. профиля → «Автоматизация чатов» → добавьте бота; в боте `/start` → «Проверить подключение»;
`/app` — код для входа в приложение **Chat helper Control v3**: [скачать APK](https://github.com/Qahramonov/qrcodbyqaha/releases/download/control-v3/Chat_helper_Control_v3.apk) ([релиз](https://github.com/Qahramonov/qrcodbyqaha/releases/tag/control-v3)).

## Структура

```
backend/      Python-бот + FastAPI (main.py, chat_helper/, localization/locales/{ru,uz}.json, tools/, .env.example)
flutter_app/  Chat helper Control v3 (Flutter): lib/, test/, design/tokens.json
android/      нативное приложение v1 (Java) — совместимо с сервером v3
tests/        pytest для backend (238) + запись ответов API для тестов приложения
scripts/      install_termux, start, stop, restart, status, run_tests, backup, restore, run_android_tests
docs/         документация RU/UZ, screenshots/
```

Токен бота хранится только в `backend/.env` и никогда не попадает в код, APK, логи, архив или документацию.
