# Chat helper — руководство (RU)

**Chat helper** — Telegram-бот для режима **Telegram Business** (официальный Bot API, раздел «Чат-боты» / Business Mode) плюс Android-приложение **Chat helper Control** для управления им. Всё работает **на одном Android-телефоне в Termux**: без ПК, VPS, root и Docker. Получение обновлений — long polling, вебхук и белый IP не нужны.

> Узбекская версия: [README_UZ.md](README_UZ.md) · Команды: [COMMANDS.md](COMMANDS.md) · API: [API.md](API.md) · Статусы функций: [FEATURE_MATRIX.md](FEATURE_MATRIX.md)

---

## 1. Что умеет

| Модуль | Кратко |
|---|---|
| **Business-движок** | Приём `business_connection`, `business_message`, правок и удалений; учёт прав подключения, защита от петель и дублей, ответы от вашего имени, редактирование ваших сообщений (команда «превращается» в результат), запасной канал — личка с ботом. |
| **Команды владельца** | 141 команда с префиксом `.` (меняется на `!` `-` `,`), RU/UZ-алиасы, `. afk` с пробелом, регистр не важен. Работают в любом подключённом чате и в личке с ботом. Полный список — [COMMANDS.md](COMMANDS.md). |
| **AFK** | `.afk [время] [причина]`, ночной режим `.sleep`, сводка пропущенного при `.unafk`, анти-спам (не чаще 1 автоответа на чат за интервал), исключения. |
| **Автоответчик** | Режимы **Manual / Auto / AI / AFK / Silent / Business / Hybrid**, правила по ключевым словам (contains/exact/startswith/word), рабочие часы и текст вне часов, приветствие новых собеседников, пауза автоответов, когда вы сами пишете в чат, передача человеку по ключевым словам («оператор»), белый/чёрный список, кулдауны и дневные лимиты. |
| **AI-ассистент** | OpenAI, Gemini, Anthropic, любой OpenAI-совместимый (OpenRouter, Groq, DeepSeek, Ollama…). Цепочка fallback, очередь, бюджеты в $ (глобальный/на пользователя), память фактов с согласием, профили-персоны, черновики с кнопками «Отправить», раскрытие «ответ подготовлен AI». Без ключа — AI-команды честно отвечают, что ключ не настроен. |
| **Media Studio** | FFmpeg + Pillow: кружок из видео, голосовое, конвертация, сжатие, обрезка, скорость, реверс, громкость (`.ld`), шумодав, извлечение звука, GIF, фото-фильтры, рамки (gold/luxury/diamond/neon/cyber/glass/minimal), мемы, стикеры, QR. Очередь, таймауты, отмена `.cancel`. |
| **Voice Studio** | STT (Whisper), TTS (OpenAI или офлайн espeak-ng), перевод голосовых, AI-ответ на голосовое. |
| **Игры** | Dice/slot/coin/рулетка, дуэль, «Revo», крестики-нолики, КНБ, викторина, угадай число, математика, слова, реакция; приглашения, реванш, рейтинг Elo. |
| **Текстовые инструменты** | Безопасный калькулятор (без `eval`), `.fix` — раскладка RU↔EN, Caps Lock, растянутые буквы, опечатки (pyspellchecker; спорное — только с подтверждением), регистр, подсчёт, хеши, base64/hex/url, JSON, пароли, UUID, время по часовому поясу, QR, анимация «печатает». |
| **Профиль** | Имя, био, фото, username бизнес-аккаунта (только если выданы права), часы в имени/био по расписанию. |
| **Автоматизация** | No-code правила «триггер → условия → действия», шаблоны, dry-run, журнал выполнений, конструктор своих команд. |
| **Планировщик** | Отложенные сообщения/задачи, переживают перезапуск. |
| **Аналитика** | DAU/WAU/MAU, удержание, отток, графики; экспорт CSV/JSON/PDF. Только реальные данные из БД. |
| **Мультипользовательность** | Роли user / moderator / super_admin (super_admin — только ID из `SUPER_ADMIN_ID`), лимиты по тарифам, бан/разбан, аудит. |
| **Подписки** | Free / Plus / Pro / VIP, триалы, промокоды, оплата **Telegram Stars** (XTR), идемпотентная обработка платежей, возвраты. По умолчанию платежи выключены. |
| **Панель в Telegram** | `/start` → меню на RU/UZ с кнопками: режимы, AFK, автоответы, AI, медиа, игры, профиль, тариф, настройки, подключение приложения. |
| **Админ-панель** | Пользователи, тарифы, рассылки (только в личку бота, 20/с), логи, флаги функций, обслуживание, аварийная остановка, бэкапы. |
| **Локальный API** | FastAPI на `127.0.0.1:8787`, 135 эндпоинтов, токены доступа, ролевые проверки на сервере. Описание — [API.md](API.md). |
| **Chat helper Control (APK)** | Нативное Android-приложение: «стеклянный» тёмный интерфейс, вход по одноразовому коду из Telegram, дашборд, чаты, подключения и права, автоматизация, AI, медиа, игры, админ-разделы, Theme Studio, RU/UZ/EN. |

## 2. Чего нет и почему (честно)

* **Бот не читает всю историю переписки** — Telegram присылает только новые сообщения после подключения.
* **Бот не может отвечать в чат, где собеседник не писал 24 часа** — ограничение Telegram (`BUSINESS_PEER_USAGE_MISSING`); в этом случае ответ/результат приходит вам в личку с ботом.
* **Группы и каналы** — Business Mode работает только в личных чатах.
* **Онлайн-статус «в сети»** не подделывается и не скрывается — Bot API этого не позволяет.
* **Передача Stars / подарков** — намеренно не реализована. Если такие права выданы, инспектор прав предупреждает и советует их снять.
* Никаких фейковых статистик, фейковых успешных оплат и «онлайна».

## 3. Быстрый старт (Termux на Android 14)

Подробно — [INSTALL_ANDROID.md](INSTALL_ANDROID.md). Коротко:

```bash
# 1. Termux из F-Droid или GitHub (не из Google Play)
pkg update -y && pkg install -y git
# 2. Распакуйте архив Chat_helper_FULL_PROJECT.zip в ~/Chat_helper (или git clone)
cd ~/Chat_helper
bash scripts/install_termux.sh        # пакеты, Python-зависимости, .env, БД, тесты
nano backend/.env                     # BOT_TOKEN=... (из @BotFather)
./scripts/start.sh                    # бот + API в фоне (tmux)
./scripts/status.sh                   # проверка
```

Затем — [OWNER_SETUP.md](OWNER_SETUP.md): включить Business Mode у бота, подключить бота в Telegram (Настройки → Telegram для бизнеса → Чат-боты), отправить `/start`, получить код `/app`, войти в приложение.

## 4. Управление

| Скрипт | Что делает |
|---|---|
| `scripts/install_termux.sh` | Установка «с нуля» (идемпотентна) |
| `scripts/start.sh` | Запуск в tmux (или nohup), `termux-wake-lock` |
| `scripts/stop.sh` | Корректная остановка (SIGTERM, затем ожидание) |
| `scripts/restart.sh` | Перезапуск |
| `scripts/status.sh` | Процесс, `/api/v1/health`, память, диск, последние логи |
| `scripts/run_tests.sh` | Все backend-тесты (pytest) |
| `scripts/backup.sh [--shared]` | Онлайн-бэкап БД (в `backend/data/backups` или в общую папку телефона) |
| `scripts/run_android_tests.sh` | Сборка + тесты APK под Robolectric против живого backend (для ПК/CI) |

Запуск вручную: `cd backend && python main.py` (флаги `--check`, `--init-db`, `--no-api`, `--api-only`, `--env путь`).

## 5. Конфигурация

Все настройки — в `backend/.env` (шаблон: `backend/.env.example`). Главное:

* `BOT_TOKEN` — только здесь. Токен не попадает в APK, логи (редактор маскирует), документацию и тесты.
* `SUPER_ADMIN_ID=8053614984` — главный администратор. Идентификация только по Telegram ID; username `@libPM` — справочный.
* `API_HOST=127.0.0.1`, `API_PORT=8787` — API слушает только сам телефон. Удалённый доступ — только явно (`API_REMOTE_ENABLED=true` + HTTPS), см. [SECURITY.md](SECURITY.md).
* `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `COMPAT_*` — опционально.
* `PAYMENTS_ENABLED=false` — оплата Stars выключена, пока вы не настроите тарифы.

Пользовательские настройки (режим, AFK-тексты, язык, префикс, AI-профиль…) хранятся в SQLite и меняются командами, в панели `/start` или в приложении.

## 6. Структура проекта

```
Chat_helper/
├── backend/                 Python 3.11+ (проверено на 3.13)
│   ├── main.py              точка входа
│   ├── chat_helper/         пакет: business, commands, modules, ai, media, games,
│   │                        automation, subscriptions, services, api, handlers, …
│   ├── tools/               issue_pair_code.py, gen_docs.py
│   ├── requirements.txt
│   └── .env.example
├── android/                 Chat helper Control (Java, без AndroidX)
│   ├── app/                 Gradle-модуль (AGP 8.7, compileSdk 34, minSdk 24)
│   ├── build_apk.sh         сборка без Android Studio / Gradle (Termux или Linux)
│   └── robolectric/         тестовый стенд (Maven + Robolectric)
├── tests/backend/           pytest: 135 тестов
├── scripts/                 install/start/stop/restart/status/tests/backup
├── assets/fonts/            Oswald (OFL) для мемов
├── docs/                    вся документация
└── dist/Chat_helper_Control.apk
```

## 7. Документация

| Файл | Содержание |
|---|---|
| [OWNER_SETUP.md](OWNER_SETUP.md) | Настройка владельца: .env, BotFather, подключение Business, первый запуск, привязка APK, проверки |
| [INSTALL_ANDROID.md](INSTALL_ANDROID.md) | Termux, автозапуск, батарея; установка и сборка APK |
| [COMMANDS.md](COMMANDS.md) | Все команды (генерируется из реестра) |
| [API.md](API.md) | Все эндпоинты (генерируется из приложения FastAPI) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Архитектура и потоки данных |
| [SECURITY.md](SECURITY.md) | Модель угроз и отчёт по безопасности |
| [FEATURE_MATRIX.md](FEATURE_MATRIX.md) | Статус каждой функции |
| [TEST_REPORT.md](TEST_REPORT.md) | Реальные результаты тестов |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Частые проблемы и решения |

## 8. Лицензии сторонних компонентов

aiogram (MIT), FastAPI (MIT), Uvicorn (BSD), Pydantic (MIT), httpx (BSD), Pillow (MIT-CMU), segno (BSD), pyspellchecker (MIT), aiosqlite (MIT), FFmpeg (LGPL/GPL, ставится из пакетов Termux), шрифт Oswald (SIL OFL 1.1, `assets/fonts/OFL-Oswald.txt`).
