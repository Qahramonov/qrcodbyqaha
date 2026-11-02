# Chat helper v3 — руководство (RU)

**Chat helper** — бот для **Telegram Business** («Автоматизация чатов», официальный Bot API) и приложение **Chat helper Control**
для управления им. Бот и API работают **на одном Android-телефоне в Termux** (Android 14, ARM64, Python 3.13): без ПК, VPS, root
и Docker; обновления — long polling.

> Узбекская версия: [README_UZ.md](README_UZ.md) · Команды: [COMMANDS.md](COMMANDS.md) · API: [API.md](API.md) ·
> Статусы функций: [FEATURE_MATRIX.md](FEATURE_MATRIX.md) · Отчёт о тестах: [TEST_REPORT.md](TEST_REPORT.md)

## 1. Главное в v3

* **Без подключения — без функций.** Пока бот не подключён в «Автоматизации чатов», работают только `/start`, `/help`, `/connect`,
  проверка подключения, инструкция, язык и поддержка. Новый мастер подключения с инфографикой RU/UZ. Telegram Premium **не нужен**.
* **Карточки управления в чате** — `.mute`, `.protect`, `.nogif`, `.nomute`, `.afk`, `.re`… отвечают сообщением с кнопками,
  которые может нажимать только владелец ([CHAT_CONTROLS.md](CHAT_CONTROLS.md)).
* **Mute по-настоящему:** удаление новых входящих через `deleteBusinessMessages` (право «Удаление входящих»), подтверждение,
  таймеры 10м/1ч/1д, типы, белый список, отчёт.
* **Animation Engine** (`.a`, 16 типов, 4 скорости), **`.re`** (повтор каждые 5 с до 2 минут), **`.r`** (RTL), `.sum`, `.ball`,
  `.morse`, `.ptext` (OCR ru/uz/en), `.remind`/`.remindf`, `.qr` (создать/распознать), `.info`, `.gif`, `.wtm`, `.geo`, `.mad`, `.g`…
* **AI**: `.ai` (алиас `.gpt`), **AI-двойник** — отвечает в вашей манере, учится только на примерах, которые вы добавили сами,
  ответы подписываются «🤖 AI»; режимы Auto / Manual / Draft / Disabled.
* **Один администратор** — Super Admin (`SUPER_ADMIN_ID`). Для всех остальных админ-раздел **не существует**: нет кнопок, команд,
  а API отвечает как на несуществующий адрес ([ADMIN_SECURITY.md](ADMIN_SECURITY.md)).
* **Полная локализация RU/UZ** из JSON-каталогов ([LOCALIZATION.md](LOCALIZATION.md)).
* **Новое приложение Chat helper Control v3** на Flutter: 40 экранов, «liquid glass» дизайн ([BUILD_FLUTTER.md](BUILD_FLUTTER.md),
  [FIGMA_DESIGN.md](FIGMA_DESIGN.md)).

## 2. Возможности

| Модуль | Кратко |
|---|---|
| Business-движок | `business_connection`, `business_message`, правки, удаления, права `BusinessBotRights`, защита от петель и дублей, ответы от вашего имени, запасной канал — личка с ботом |
| Команды | 160 команд с префиксом `.` (меняется на `!` `-` `,`), алиасы, синтаксис английский, описания и результаты — на вашем языке |
| Chat Control Framework | карточки с кнопками, только для владельца, версии против устаревших нажатий, идемпотентность, отзыв при отключении |
| Mute / Protect / NoGIF / NoMute | удаление входящих по правилам, защита от пересылки (`protect_content`), фильтр слов |
| AFK и автоответчик | `.afk`, ночной режим, режимы Manual/Auto/AI/AFK/Silent/Business/Hybrid, рабочие часы, правила, кулдауны |
| AI | OpenAI / Gemini / Anthropic / OpenAI-совместимые, fallback, бюджеты, память фактов с согласием, черновики, `.sum`, `.hint`, AI-двойник |
| Media / Voice Studio | FFmpeg + Pillow: кружки, голосовые, GIF (до 15 с), водяной знак, реверс, скорость, мемы, стикеры, STT/TTS |
| Игры, текстовые инструменты | дуэль, викторина, КНБ, крестики-нолики…; калькулятор без `eval`, `.fix`, Морзе, QR, хеши, пароли |
| Профиль | имя, био, фото (по правам), часы в профиле (не чаще 15 мин — лимиты Telegram) |
| Автоматизация | no-code «триггер → условия → действия», шаблоны (на языке владельца), dry-run, журнал |
| Напоминания | `.remind` (вам в личку), `.remindf` (в чат), список и отмена; переживают перезапуск |
| Подписки | Free / Plus / Pro / VIP, промокоды, триал, оплата Telegram Stars (выключена по умолчанию) |
| Делегирование | добровольная помощь администратора с отдельными настройками, отзывается в любой момент |
| Панели | пользовательская панель в боте (18 разделов) и Super Admin (23 раздела) |
| API | FastAPI на `127.0.0.1:8787`, 159 эндпоинтов, токены сессий, проверки прав на сервере ([API.md](API.md)) |

## 3. Чего нет и почему

* «В сети» нельзя подделать или скрыть через Bot API — `.online` честно отвечает `NOT_SUPPORTED_BY_OFFICIAL_API`.
* История до подключения и группы/каналы недоступны бизнес-боту.
* Ответ в чат возможен, только если собеседник писал за последние 24 часа — иначе результат приходит вам в личку.
* Передача Stars/подарков намеренно не реализована.
* Никаких фейковых статистик, онлайна или «успешных» оплат.

## 4. Быстрый старт

```bash
cd ~ && unzip /sdcard/Download/Chat_helper_v3_FULL_PROJECT.zip && cd ~/Chat_helper
bash scripts/install_termux.sh
nano backend/.env            # BOT_TOKEN=..., SUPER_ADMIN_ID=ваш_числовой_id
./scripts/start.sh && ./scripts/status.sh
```

Затем в Telegram: подключите бота ([TELEGRAM_BUSINESS.md](TELEGRAM_BUSINESS.md)), `/start` → проверьте подключение, `/app` → код для
приложения. Обновление с v1 — [INSTALL_TERMUX.md](INSTALL_TERMUX.md#3-обновление-с-v1-до-v3-данные-и-токен-сохраняются) и
[MIGRATION_V1_TO_V3.md](MIGRATION_V1_TO_V3.md). Остановить бота: `./scripts/stop.sh`.

## 5. Конфигурация (`backend/.env`)

* `BOT_TOKEN` — только здесь (не в коде, APK, логах, документации, архиве).
* `SUPER_ADMIN_ID=8053614984` — единственный администратор; проверка только по числовому ID.
* `API_HOST=127.0.0.1`, `API_PORT=8787`; удалённо — только `API_REMOTE_ENABLED=true` + TLS-сертификат. `API_DOCS_ENABLED=false`.
* Ключи AI — опционально. `PAYMENTS_ENABLED=false` — пока не настроите тарифы.

## 6. Структура

```
Chat_helper/
├── backend/            Python: main.py, chat_helper/ (business, commands, modules, ai, media, games, automation,
│                       localization/locales/{ru,uz}.json, services, api, handlers), tools/, requirements.txt, .env.example
├── flutter_app/        Chat helper Control v3 (Flutter): lib/, test/, design/tokens.json, android/
├── android/            нативное приложение v1 (Java) — для совместимости
├── tests/backend/      pytest (232 теста) + record_api_samples.py
├── scripts/            install/start/stop/restart/status/tests/backup/restore
├── assets/             шрифты, инфографика подключения RU/UZ
├── docs/               документация, screenshots/
└── .github/workflows/  backend tests, Flutter APK, native APK
```

## 7. Документация

| Файл | О чём |
|---|---|
| [INSTALL_TERMUX.md](INSTALL_TERMUX.md) | установка, обновление с v1, запуск/остановка, автозапуск |
| [TELEGRAM_BUSINESS.md](TELEGRAM_BUSINESS.md) | подключение в «Автоматизации чатов», события, ограничения Telegram |
| [CHAT_CONTROLS.md](CHAT_CONTROLS.md) | карточки управления, Mute/Protect/NoGIF/NoMute, `.re`, `.a` |
| [PERMISSIONS.md](PERMISSIONS.md) | права бота, инспектор, делегирование |
| [COMMANDS.md](COMMANDS.md) | все команды (генерируется из реестра) |
| [LOCALIZATION.md](LOCALIZATION.md) | каталоги RU/UZ, как добавить язык |
| [ADMIN_SECURITY.md](ADMIN_SECURITY.md) | Super Admin, невидимая админка, секреты, API |
| [MIGRATION_V1_TO_V3.md](MIGRATION_V1_TO_V3.md) | что изменилось и как перейти |
| [BUILD_FLUTTER.md](BUILD_FLUTTER.md) | приложение v3: установка, сборка, тесты |
| [FIGMA_DESIGN.md](FIGMA_DESIGN.md) | дизайн-система, токены, экраны, скриншоты |
| [API.md](API.md) | все эндпоинты (генерируется) |
| [FEATURE_MATRIX.md](FEATURE_MATRIX.md) | статус каждой функции |
| [TEST_REPORT.md](TEST_REPORT.md) | реальные результаты тестов |
| [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [OWNER_SETUP.md](OWNER_SETUP.md) | архитектура, модель угроз, проблемы, настройка владельца |

## 8. Лицензии сторонних компонентов

aiogram (MIT), FastAPI (MIT), Uvicorn (BSD), Pydantic (MIT), httpx (BSD), Pillow (MIT-CMU), segno (BSD), pyspellchecker (MIT),
aiosqlite (MIT), FFmpeg (LGPL/GPL, из пакетов Termux), шрифты Oswald и Inter (SIL OFL 1.1). Приложение: Flutter (BSD),
Riverpod (MIT), go_router (BSD), Dio (MIT), flutter_secure_storage (BSD), url_launcher (BSD).
