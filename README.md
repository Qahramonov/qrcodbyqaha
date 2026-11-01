# Chat helper

Telegram Business-бот и Android-приложение **Chat helper Control**. Работает целиком на телефоне в Termux (Android 14, ARM64, Python 3.13): без ПК, VPS, root и Docker.

*Telegram Business boti va **Chat helper Control** Android ilovasi. To'liq telefonda, Termux ichida ishlaydi.*

| | |
|---|---|
| 📖 Руководство (RU) | [docs/README_RU.md](docs/README_RU.md) |
| 📖 Qo'llanma (UZ) | [docs/README_UZ.md](docs/README_UZ.md) |
| 👤 Настройка владельца | [docs/OWNER_SETUP.md](docs/OWNER_SETUP.md) |
| 📱 Termux и APK | [docs/INSTALL_ANDROID.md](docs/INSTALL_ANDROID.md) |
| ⌨️ Команды (141) | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 🔌 API (135 эндпоинтов) | [docs/API.md](docs/API.md) |
| 🏗 Архитектура | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 🔐 Безопасность | [docs/SECURITY.md](docs/SECURITY.md) |
| ✅ Статус функций | [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) |
| 🧪 Результаты тестов | [docs/TEST_REPORT.md](docs/TEST_REPORT.md) |
| 🛠 Проблемы | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |

## Быстрый старт

```bash
cd ~/Chat_helper
bash scripts/install_termux.sh   # зависимости, .env, база, тесты
nano backend/.env                # BOT_TOKEN=... из @BotFather (Business Mode → ON)
./scripts/start.sh               # бот + локальный API (127.0.0.1:8787) в фоне
```

Затем в Telegram: подключите бота (Настройки → Telegram для бизнеса → Чат-боты), отправьте ему `/start`, а `/app` выдаст код для входа в приложение `dist/Chat_helper_Control.apk`.

## Структура

```
backend/     Python-бот + FastAPI (main.py, chat_helper/, tools/, requirements.txt, .env.example)
android/     Chat helper Control (Java, без AndroidX), build_apk.sh, Gradle-проект, Robolectric-стенд
tests/       pytest для backend
scripts/     install_termux, start, stop, restart, status, run_tests, backup, restore, run_android_tests
docs/        документация RU/UZ
dist/        Chat_helper_Control.apk
```

Токен бота хранится только в `backend/.env` и никогда не попадает в код, APK, логи или документацию.
