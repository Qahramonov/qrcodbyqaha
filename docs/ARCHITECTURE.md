# Архитектура Chat helper

## 1. Общая схема

```
 ┌───────────────────────── Android-телефон ──────────────────────────────┐
 │                                                                         │
 │  Termux                                                                 │
 │  ┌───────────────────────── python main.py (один процесс, asyncio) ──┐  │
 │  │                                                                   │  │
 │  │  aiogram Dispatcher ── long polling ───────────────► api.telegram.org
 │  │    ├─ handlers/business.py  (business_* апдейты)                  │  │
 │  │    └─ handlers/panel.py     (/start, меню, FSM, платежи)          │  │
 │  │                                                                   │  │
 │  │  AppContext (app.py) — сервисы:                                   │  │
 │  │    business: connections · rights · sender · guard                │  │
 │  │    commands: registry · parser · executor · context               │  │
 │  │    modules:  pipeline · afk · autoreply · ai_cmds · media_cmds …  │  │
 │  │    ai · media · games · automation · subscriptions · services     │  │
 │  │                                                                   │  │
 │  │  Scheduler (периодические и отложенные задачи) · EventBus         │  │
 │  │  SQLite (aiosqlite, WAL) — backend/data/chat_helper.db            │  │
 │  │                                                                   │  │
 │  │  FastAPI + uvicorn (тот же event loop) ── 127.0.0.1:8787 ◄──┐     │  │
 │  └─────────────────────────────────────────────────────────────┼─────┘  │
 │                                                                │ HTTP   │
 │  Chat helper Control (APK, Java) ──────────────────────────────┘        │
 └─────────────────────────────────────────────────────────────────────────┘
```

Один процесс Python держит бота, планировщик и API в одном event loop: на телефоне это экономит память и исключает гонки между процессами за SQLite. FFmpeg запускается дочерними процессами через очередь с ограничением параллелизма.

## 2. Backend: слои

| Слой | Пакет | Ответственность |
|---|---|---|
| Вход | `main.py` | Флаги CLI, PID-файл, запуск polling + uvicorn, корректная остановка (SIGTERM/SIGINT) |
| Сборка | `app.py` | `build_app()` создаёт сервисы, подключает роутеры, middleware активности/обслуживания, регистрирует задачи планировщика |
| Конфигурация | `config.py` | `.env` → `Settings` (Pydantic); принудительный 127.0.0.1; `public_summary()` без секретов |
| Ядро | `core/` | логирование с маскировкой секретов, EventBus, время/часовые пояса, `Runtime` (аварийная остановка, обслуживание, пауза модулей) |
| БД | `database/` | `Database` (сериализованная запись, `BEGIN IMMEDIATE`, FK, WAL), миграции, онлайн-бэкап/восстановление, `integrity_check` |
| Business | `business/` | учёт подключений и прав, `BusinessSender` (классификация ошибок Telegram, flood control, fallback в личку), дедупликация и защита от петель |
| Команды | `commands/` | реестр (`CommandSpec`: алиасы, категории, тариф, права, статус), парсер, исполнитель (авторизация, лимиты, песочница), контекст ответа (правка на месте / fallback / уборка) |
| Модули | `modules/` | pipeline входящих/исходящих, AFK, автоответчик, AI-команды, медиа-команды, текстовые инструменты, профиль, системные команды |
| AI | `ai/` | провайдеры (OpenAI, Gemini, Anthropic, совместимые, тестовый), fallback, очередь-семафор, бюджеты, память, авто-ответы и черновики |
| Медиа | `media/` | обёртка FFmpeg (аргументы списком, таймауты, отмена), AV-операции, Pillow-операции, очередь задач, TTS/STT |
| Игры | `games/` | движок сессий (блокировки, таймауты, callback-кнопки, Elo), набор игр |
| Автоматизация | `automation/` | декларативные правила (триггеры/условия/действия), dry-run, шаблоны, конструктор команд |
| Подписки | `subscriptions/` | тарифы, лимиты, триалы, промокоды, платежи Stars |
| Сервисы | `services/` | пользователи/роли, настройки (схема с валидацией), чаты, аудит, метрики, уведомления, inbox, планировщик, рассылки, бэкапы, аналитика, health |
| Auth | `auth/` | коды привязки, сессии, токены, журнал входов |
| API | `api/` | FastAPI-приложение, зависимости ролей, роутеры (auth, user, ai, ops, admin) |
| Telegram UI | `handlers/`, `keyboards/`, `localization/` | панель `/start` на RU/UZ, клавиатуры, фразы |

## 3. Поток бизнес-сообщения

```
business_message
  └─ handlers/business.py → ConnectionService.get(conn_id)
       └─ Pipeline.on_message
            ├─ дубль? (LRU + processed_updates)               → стоп
            ├─ sender_business_bot != None (эхо ботов)        → стоп (защита от петель)
            ├─ подключение выключено                          → стоп
            ├─ отправитель == владелец → on_owner_message
            │     ├─ Executor.try_handle → команда: авторизация, лимиты, права подключения,
            │     │      выполнение, ответ правкой командного сообщения (или в личку при ошибке/24 ч)
            │     ├─ пауза автоответов в этом чате (owner_pause_minutes), отмена ожидающего AI-ответа
            │     ├─ ход в игре
            │     └─ авто-выключение AFK
            └─ иначе → on_incoming
                  ├─ учёт чата/метрик, inbox (приоритет, «важное» → уведомление)
                  ├─ ход в игре, правила автоматизации, авто-расшифровка голосовых
                  └─ auto_reply → gate(): emergency_stop · пауза модуля · статус подключения · право can_reply
                        · бан · белый/чёрный список · mute · пауза владельца · боты · LoopGuard · кулдауны · дневные лимиты
                        └─ режим: AFK → AFK-текст; Business → рабочие часы/приветствие; Auto → правила;
                           AI → AutoAI (debounce, черновик или ответ с пометкой); Hybrid → правила, затем AI
```

Отправка всегда идёт через `BusinessSender`: flood control (≈1 сообщение/с на чат, ≈25/с всего), `retry_after`, классификация ошибок (`window_24h`, `missing_rights`, `connection_invalid`, `too_old`, `not_found`, `forbidden`, `network`), при невозможности ответить в чате — уведомление владельцу в личку.

## 4. Команды
* Каждая команда описана `CommandSpec` (имя, RU/UZ-алиасы, категория, синтаксис, примеры, тариф, нужные права подключения, зависимости `ffmpeg`/`ai`, флаг `sandbox_safe`, статус).
* `docs/COMMANDS.md` генерируется из реестра (`python backend/tools/gen_docs.py`), поэтому документация не расходится с кодом.
* Песочница (`Executor.sandbox`) выполняет безопасные команды без отправки в Telegram — используется экраном «Тест команды» в приложении.

## 5. Хранилище
SQLite в режиме WAL, внешние ключи включены, все записи сериализуются через одну очередь, транзакции `BEGIN IMMEDIATE`. Основные таблицы (миграции M001–M002):

`users`, `admin_roles`, `admin_sessions`, `pairing_codes`, `login_events` · `business_connections`, `business_rights`, `processed_updates` · `user_settings`, `module_settings`, `chat_settings`, `chat_permissions`, `feature_flags` · `command_registry`, `command_history`, `custom_commands` · `ai_profiles`, `ai_history`, `ai_memory`, `ai_usage`, `ai_costs`, `ai_drafts` · `afk_sessions`, `autoresponse_rules`, `reply_templates` · `automation_rules`, `automation_executions` · `media_jobs` · `game_sessions`, `game_players`, `game_results`, `game_ratings` · `scheduled_tasks` · `subscription_plans`, `subscriptions`, `payments`, `promo_codes`, `promo_redemptions`, `referrals` · `notification_events`, `audit_logs`, `system_logs`, `daily_metrics`, `user_activity`, `rate_limits` · `broadcasts`, `broadcast_errors` · `profile_history`.

Файлы: `backend/data/` — БД, `secret.key`, `logs/`, `backups/`, `tmp/` (медиа, очищается задачей `tmp_cleanup`).

## 6. Фоновые задачи (Scheduler)
Персистентные задачи (`scheduled_tasks`: напоминания, отложенные действия, рассылки) восстанавливаются после перезапуска и никогда не выполняются дважды. Периодические: истечение AFK (30 с), таймауты игр (30 с), временные и «нет ответа» триггеры автоматизации (30/60 с), часы в профиле (60 с), запланированные рассылки (60 с), окончание подписок (10 мин), очистка по срокам хранения (1 ч), очистка tmp (30 мин), автобэкап (проверка каждые 30 мин, интервал из `BACKUP_INTERVAL_HOURS`), а также контроль AI-бюджета, места на диске и вечерняя AI-сводка.

## 7. API
FastAPI, префикс `/api/v1`, 135 эндпоинтов (полный список — [API.md](API.md), живой Swagger — `/api/docs`). Middleware: лимит по IP, `X-HTTP-Method-Override` (для клиентов без PATCH), заголовки безопасности, единый формат ошибок `{"error":{"code","message"}}`. Зависимости `principal` → `admin` → `super_admin` проверяют роль на сервере при каждом запросе.

## 8. Android-приложение (Chat helper Control)

```
com.chathelper.control
├── MainActivity        splash → pairing → shell (5 вкладок со своими стеками экранов), верхняя панель, тосты, выход
├── core/
│   ├── Api             пул потоков, JSON, автообновление access-токена, PATCH через override
│   ├── SessionStore    токены в SharedPreferences, зашифрованные AES-GCM ключом из Android Keystore
│   ├── L               локализация RU/UZ/EN, Fmt — форматирование чисел/дат/размеров, ApiError
├── ui/
│   ├── Theme           токены цветов (Dark/Light/AMOLED/System), 8 акцентов, интенсивность анимаций
│   ├── UI, Icons       набор компонентов и векторные иконки на Canvas
│   └── widget/         Glass, AuroraBackground, Toggle, Chart, Skeleton, BottomNav, Logo
└── screens/            Home (дашборд, чаты, подключения, инспектор, уведомления, live-монитор),
                        Admin (пользователи, аудит, подписки, рассылки, аналитика, файлы, безопасность,
                               System Control + Backup Center, логи, флаги), Automation (правила, шаблоны,
                        журнал, команды, свои команды, медиа, игры), AI (провайдеры, профили, playground,
                        память, черновики), Settings (Theme Studio, диагностика, поддержка, changelog)
```

Без AndroidX и сторонних библиотек: только фреймворк Android (minSdk 24, targetSdk 34), интерфейс строится программно. Это даёт APK ≈190 КБ и позволяет собрать его прямо в Termux (`android/build_apk.sh`).

## 9. Тестирование
* `tests/backend/` — pytest: поддельная сессия Bot API (`fakes.py`) записывает каждый вызов метода Telegram, так что тесты проверяют реальные запросы бота; FFmpeg и Pillow — настоящие; API — через `httpx.ASGITransport`.
* `android/robolectric/` — Maven-стенд: Robolectric 4.17 запускает приложение на настоящем фреймворке Android 14 в JVM; `scripts/run_android_tests.sh` поднимает живой backend и прогоняет сценарий входа/навигации против него.
