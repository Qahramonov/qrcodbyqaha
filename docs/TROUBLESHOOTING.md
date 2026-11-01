# Решение проблем / Muammolarni hal qilish

Сначала всегда: `./scripts/status.sh` и последние строки лога `backend/data/logs/chat_helper.log` (секреты в логе замаскированы — его можно показывать). Проверка конфигурации: `cd backend && python main.py --check`.

## Установка

**`pip` падает на `pydantic-core` / `maturin` / `rust`**
```bash
pkg install -y rust binutils clang
export ANDROID_API_LEVEL=$(getprop ro.build.version.sdk) CARGO_BUILD_JOBS=2
pip install -r backend/requirements.txt
```
Сборка занимает 10–20 минут, телефон должен быть на зарядке и не уходить в сон (`termux-wake-lock`).

**Pillow не собирается (`jpeg`/`zlib` not found)** — `pkg install -y libjpeg-turbo libpng freetype zlib`.

**`Python 3.11+ required`** — `pkg upgrade -y python`.

**Termux из Google Play: «repository is under maintenance», пакеты не ставятся** — удалите и поставьте Termux из F-Droid/GitHub.

## Запуск

**`BOT_TOKEN is empty in backend/.env`** — впишите токен: `nano backend/.env`.

**В логе `Telegram rejected BOT_TOKEN (Unauthorized)`, процесс завершился с кодом 3** — токен неверный или отозван (`/revoke` в BotFather). Скопируйте актуальный токен заново.

**`Telegram is unreachable … retrying`** — нет интернета или Telegram заблокирован в сети. Бот сам повторяет попытки (до раза в минуту) и начнёт работу, когда сеть появится; приложение в это время показывает «Bot is not polling Telegram». Если Telegram заблокирован провайдером — используйте системный VPN на телефоне.

**`Conflict: terminated by other getUpdates request`** — этот же токен опрашивает другая копия бота (второй телефон, ПК, старый tmux). Оставьте один экземпляр: `./scripts/stop.sh`, проверьте `tmux ls`. Webhook, оставшийся от другого хостинга, Chat helper снимает автоматически при старте.

**`already running (pid …)`, но бот не отвечает** — `./scripts/restart.sh`. Если PID «мёртвый», `stop.sh` удалит устаревший PID-файл.

**`address already in use` для порта 8787** — порт занят другим процессом: смените `API_PORT` в `.env` и адрес сервера в приложении.

## Процесс исчезает (phantom process killer)

Android 12+ убивает «лишние» фоновые процессы приложений, включая дочерние процессы Termux.
1. Батарея: Termux → «Без ограничений»; на Xiaomi/Huawei/Samsung — разрешить автозапуск и убрать из «спящих».
2. `termux-wake-lock` (делает `start.sh`).
3. Android 14: «Параметры разработчика» → **«Отключить ограничения дочерних процессов»** (Disable child process restrictions), если пункт есть в прошивке.
4. Иначе, через ADB с компьютера (один раз):
   `adb shell "/system/bin/device_config set_sync_disabled_for_tests persistent; /system/bin/device_config put activity_manager max_phantom_processes 2147483647"`
5. Автозапуск после перезагрузки — Termux:Boot ([INSTALL_ANDROID.md](INSTALL_ANDROID.md#16-автозапуск-после-перезагрузки-termuxboot)).

## Telegram Business

**Бот не реагирует в чатах**
1. BotFather → Bot Settings → **Business Mode включён** (в логе при старте иначе будет предупреждение).
2. Telegram → Настройки → Telegram для бизнеса → Чат-боты: бот подключён, чат не в исключениях. Нужен активный **Telegram Premium**.
3. Меню бота → «🔗 Подключить аккаунт»: статус `connected`, права «Читать» и «Отвечать» включены.
4. Режим автоответчика не `manual`/`silent` (`.auto`), подключение не на паузе, нет аварийной остановки.
5. Чат в чёрном списке (`.ignore`) или на mute (`.mute off`)?

**Команды не выполняются** — пишите их **от своего имени** в подключённом личном чате или в личке с ботом; проверьте префикс (`.settings`), не отключена ли команда, хватает ли тарифа (`.limits`). В группах Business Mode не работает.

**«Не удалось ответить в чате, результат прислан в личку»** — собеседник не писал вам 24 часа (ограничение Telegram для ботов). Это ожидаемо.

**Команда не заменяет моё сообщение результатом** — Telegram разрешает боту править ваши сообщения только 48 часов и только при выданных правах; иначе результат приходит отдельным сообщением или в личку.

**`.name`/`.bio`/`.avatar`/`.clock` — «нет прав»** — включите соответствующие права в настройках чат-бота.

## Приложение Chat helper Control

| Сообщение | Причина / решение |
|---|---|
| «Cannot reach the backend» / «Сервер недоступен» | backend не запущен (`./scripts/status.sh`), неверный порт, или Termux выгружен системой |
| «Remote servers require https» | для адресов кроме 127.0.0.1/localhost нужен HTTPS (см. SECURITY.md) |
| «Invalid or expired code» | код одноразовый и живёт 5 минут — получите новый `/app` |
| «Too many attempts» / «Pairing temporarily locked» | сработала защита от перебора; подождите (до 15 минут) |
| «Session expired. Pair the app again.» | refresh-токен истёк (30 дней) или сессия отозвана — войдите заново |
| «Account access is restricted» | аккаунт ограничен администратором |

**«Приложение не установлено»** — уже установлена версия с другой подписью: удалите старое приложение и поставьте новое.

## Медиа и AI

**Медиа-команды отключены / `ffmpeg missing`** — `pkg install -y ffmpeg`, затем `./scripts/restart.sh`.

**«Файл больше 20 МБ»** — лимит Bot API на скачивание файлов ботами; сожмите файл или отправьте короче.

**Обработка долгая / телефон греется** — оставьте `MEDIA_CONCURRENCY=1`, уменьшите `MEDIA_MAX_DURATION`; отмена — `.cancel`.

**AI: «ключ не настроен»** — добавьте ключ в `.env` и перезапустите. **401/403 от провайдера** — ключ неверный или без доступа к модели (проверьте `OPENAI_MODEL`/`GEMINI_MODEL`/`ANTHROPIC_MODEL`). **«Бюджет исчерпан»** — увеличьте `AI_GLOBAL_DAILY_BUDGET_USD` / `AI_USER_DAILY_BUDGET_USD`.

**`.tts` без ключа** — `pkg install -y espeak` для офлайн-озвучки.

## База данных

**Повреждение/ошибки SQLite** — `python main.py --check` (integrity check). Восстановление из копии:
```bash
./scripts/restore.sh                         # список копий
./scripts/restore.sh chat_helper_2026….db    # остановит бот, сохранит текущую базу, восстановит, запустит
```
**Нет места на диске** — удалите старые копии в `backend/data/backups`, уменьшите `BACKUP_KEEP`; временные медиа-файлы удаляются автоматически каждые 30 минут.

## Как сообщить о проблеме
Приложите: вывод `./scripts/status.sh`, `python main.py --check`, последние ~50 строк `chat_helper.log`. **Не публикуйте** `.env`, `secret.key`, базу данных, коды привязки.
