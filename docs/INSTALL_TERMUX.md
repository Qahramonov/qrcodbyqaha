# Установка и запуск в Termux (Android 14, ARM64)

Бот и локальный API работают **на самом телефоне** в Termux: без ПК, VPS, root и Docker. Получение обновлений — long polling.

## 1. Подготовка

1. Termux — **из F-Droid** или релизов GitHub `termux/termux-app` (версия из Google Play устарела).
2. Желательно: **Termux:API** и **Termux:Boot** (из того же источника).
3. `termux-setup-storage` — нужно только для бэкапов в общую папку.

## 2. Новая установка

```bash
pkg update -y && pkg install -y unzip
cd ~ && unzip /sdcard/Download/Chat_helper_v3_FULL_PROJECT.zip      # появится ~/Chat_helper
cd ~/Chat_helper
bash scripts/install_termux.sh        # пакеты, Python-зависимости, backend/.env (chmod 600), БД, самопроверка
nano backend/.env                     # BOT_TOKEN=...  (из @BotFather; Business Mode → ON)
./scripts/start.sh                    # бот + API 127.0.0.1:8787 в фоне (tmux), termux-wake-lock
./scripts/status.sh                   # process: running, API: {"status":"ok",...,"bot_polling":true}
```

Первая установка 10–20 минут (компилируется `pydantic-core`). Если `pip` падает на нём:
`pkg install -y rust binutils && export ANDROID_API_LEVEL=$(getprop ro.build.version.sdk) && pip install -r backend/requirements.txt`.

Дальше — подключение бота в Telegram: [TELEGRAM_BUSINESS.md](TELEGRAM_BUSINESS.md).

## 3. Обновление с v1 до v3 (данные и токен сохраняются)

```bash
cd ~/Chat_helper
./scripts/backup.sh                   # онлайн-копия базы в backend/data/backups/
./scripts/stop.sh
cd ~ && unzip -o /sdcard/Download/Chat_helper_v3_FULL_PROJECT.zip   # поверх; backend/.env и backend/data/ в архиве нет — они не трогаются
cd ~/Chat_helper
pip install -r backend/requirements.txt
./scripts/start.sh                    # миграция M003 применяется сама; перед ней — копия pre_migration_v3 в backend/data/backups/
./scripts/status.sh
```

Что меняется для вас — [MIGRATION_V1_TO_V3.md](MIGRATION_V1_TO_V3.md).

## 4. Управление

| Скрипт | Что делает |
|---|---|
| `./scripts/start.sh` | запуск в tmux-сессии `chat_helper` (или nohup), `termux-wake-lock` |
| `./scripts/stop.sh` | корректная остановка (SIGTERM, ожидание) |
| `./scripts/restart.sh` | перезапуск (нужен после правки `.env`) |
| `./scripts/status.sh` | процесс, `/api/v1/health`, память, диск, последние строки лога |
| `./scripts/run_tests.sh` | backend-тесты (pytest) |
| `./scripts/backup.sh [--shared]` | бэкап БД (в `backend/data/backups` или в общую папку телефона) |
| `./scripts/restore.sh [файл]` | список копий / восстановление с остановкой и копией текущей базы |

Консоль бота: `tmux attach -t chat_helper` (выйти, не останавливая: `Ctrl+B`, затем `D`). Логи: `backend/data/logs/chat_helper.log`
(токены и ключи в логах маскируются).

## 5. Чтобы Android не останавливал бота

1. Настройки → Приложения → Termux → Батарея → **Без ограничений** (MIUI/HyperOS: ещё «Автозапуск»; Samsung: убрать из «Спящих»).
2. `termux-wake-lock` (start.sh вызывает сам) — в шторке уведомление «wake lock held».
3. Android 12+ может убивать «фантомные процессы» — см. [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
4. Автозапуск после перезагрузки (Termux:Boot):
   ```bash
   mkdir -p ~/.termux/boot && cat > ~/.termux/boot/chat_helper.sh <<'SH'
   #!/data/data/com.termux/files/usr/bin/sh
   termux-wake-lock
   cd ~/Chat_helper && ./scripts/start.sh
   SH
   chmod +x ~/.termux/boot/chat_helper.sh
   ```

## 6. Необязательные пакеты

| Пакет | Для чего |
|---|---|
| `pkg install ffmpeg` | Media Studio (видео, кружки, голосовые, GIF). Ставится `install_termux.sh` |
| `pkg install tesseract` (+ языковые данные rus/uzb/eng) | `.ptext` — распознавание текста на фото офлайн; без него — через AI-ключ, если он задан |
| `pkg install zbar` | `.qr` ответом на фото — распознавание QR офлайн (`zbarimg`); альтернатива — `pip install zxing-cpp` или AI |
| ключи `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | AI-ассистент, AI-двойник, `.sum`, `.hint`, STT |

## 7. Приложение Chat helper Control v3

Установка APK и подключение — [BUILD_FLUTTER.md](BUILD_FLUTTER.md). Коротко: установите `Chat_helper_Control_v3.apk`, в боте
отправьте `/app`, в приложении введите код; сервер по умолчанию `http://127.0.0.1:8787`.

---

## UZ — qisqacha

1. **Termux** — F-Droid'dan. `pkg update -y && pkg install -y unzip`.
2. `cd ~ && unzip /sdcard/Download/Chat_helper_v3_FULL_PROJECT.zip && cd ~/Chat_helper && bash scripts/install_termux.sh`.
3. `nano backend/.env` → `BOT_TOKEN=...`, so'ng `./scripts/start.sh` va `./scripts/status.sh`.
4. **v1 dan yangilash:** `./scripts/backup.sh && ./scripts/stop.sh`, arxivni ustidan oching (`unzip -o`), `pip install -r backend/requirements.txt`,
   `./scripts/start.sh` — baza avtomatik yangilanadi, oldin zaxira nusxa olinadi. `.env` va `backend/data/` saqlanadi.
5. Botni to'xtatish: `./scripts/stop.sh`. Holat: `./scripts/status.sh`.
6. Batareya: Sozlamalar → Ilovalar → Termux → Batareya → **Cheklovsiz**.
