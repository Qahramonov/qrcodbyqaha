# Матрица функций / Funksiyalar matritsasi

**Статусы**

| Статус | Значение |
|---|---|
| `TESTED` | Реализовано и покрыто автотестом, который реально запускался (см. [TEST_REPORT.md](TEST_REPORT.md)). Telegram в тестах — поддельная сессия Bot API, проверяющая точные вызовы методов. |
| `IMPLEMENTED` | Реализовано, проверено ревью/ручным прогоном, отдельного автотеста нет. |
| `REQUIRES_API_KEY` | Работает только с ключом AI-провайдера в `.env`; без ключа — честное сообщение «ключ не настроен». |
| `REQUIRES_PERMISSION` | Нужна соответствующая галочка в правах бизнес-бота в Telegram. |
| `LIMITED_BY_TELEGRAM` | Работает в рамках ограничений Telegram (см. примечание). |
| `NOT_SUPPORTED` | Невозможно через официальный Bot API или намеренно не реализовано. |
| `NOT_VERIFIED_ON_DEVICE` | Не проверено на реальном телефоне / реальном Telegram: в среде разработки нет доступа к `api.telegram.org` и к устройству. |

> **Общее для всего, что общается с Telegram:** логика проверена тестами на поддельной Bot API-сессии, но поведение настоящих серверов Telegram — `NOT_VERIFIED_ON_DEVICE`. Первым делом после установки выполните чек-лист из [OWNER_SETUP.md](OWNER_SETUP.md#7-контрольный-список).

## 0. Новое в v3

| Функция | Статус | Где проверено / примечание |
|---|---|---|
| Блокировка до подключения (меню, команды, callback, FSM, API) + сообщение 🔒 с кнопками | `TESTED` | `test_v3_access.py` |
| Мастер подключения, `tg://settings/edit` с запасным вариантом, инфографика RU/UZ | `TESTED` · `NOT_VERIFIED_ON_DEVICE` | открытие `tg://` в реальном клиенте не проверялось |
| Chat Context Manager `/start bizChat<id>` с проверкой владельца | `TESTED` | `test_v3_controls.py` |
| Chat Control Framework: карточки, только владелец, версии, идемпотентность, отзыв, таймеры | `TESTED` · `NOT_VERIFIED_ON_DEVICE` | inline-кнопки в живом бизнес-чате не проверялись |
| `.mute` (deleteBusinessMessages, подтверждение, таймеры, типы, белый список, отчёт), `.unmute`, `.quiet` | `TESTED` · `REQUIRES_PERMISSION` · `NOT_VERIFIED_ON_DEVICE` | `test_v3_controls.py`, `test_v3_extra.py`; реальное удаление у собеседника не проверялось |
| `.protect`/`.unprotect`, `.g`, `.nogif`, `.nomute` | `TESTED` · `REQUIRES_PERMISSION` | |
| `.online` — честный `NOT_SUPPORTED_BY_OFFICIAL_API` + Chat Activity | `TESTED` · `NOT_SUPPORTED` (подделка онлайна) | |
| `.a` Animation Engine: 16 типов, 4 скорости, студия, отмена, без FloodWait | `TESTED` | |
| `.re` (5 с × до 2 мин, стоп, лимит Free 3/день), `.r` RTL, `.mad` | `TESTED` | |
| AI-двойник: режимы Auto/Manual/Draft/Disabled, обучение только на своих примерах, подпись AI | `TESTED` (тестовый AI-провайдер) · `REQUIRES_API_KEY` | `test_v3_features.py` |
| `.sum`, `.hint`, `.ai` (алиас `.gpt`) | `IMPLEMENTED` · `REQUIRES_API_KEY` | алиас `.gpt` → `.ai` проверен; без ключа — честный ответ «AI не настроен» |
| `.ball`, `.morse`, `.geo`, `.info`, `.finfo`, `.gif` (≤15 с), `.wtm` (фото и видео/кружок), `.qr` создать/распознать | `TESTED` | `test_v3_features.py`, `test_v3_extra.py`; `.qr`: zxing-cpp/zbarimg/AI |
| `.ptext` OCR ru/uz/en | `TESTED` (с заглушкой tesseract) · `NOT_VERIFIED_ON_DEVICE` | реальный tesseract в среде разработки не установлен; без него — AI или понятное сообщение |
| `.remind`, `.remindf`, список/отмена, переживают перезапуск | `TESTED` | |
| Делегирование (добровольное, отзывное, профиль — только с подтверждения) | `TESTED` | |
| Super Admin — единственный админ; админ-раздел невидим (бот, приложение, 43 API-маршрута → 404) | `TESTED` | `test_v3_admin_hidden.py`, `router_test.dart` |
| Локализация RU/UZ из JSON (≈1700 ключей), все экраны и команды на узбекском без кириллицы | `TESTED` | `test_v3_localization.py` |
| Миграция M003 с бэкапом перед ней (данные сохраняются, новая установка — без бэкапа) | `TESTED` | `test_v3_extra.py` |
| Приложение Flutter v3: 40 экранов на реальном API, RU/UZ | `TESTED` (widget-тесты на записанных ответах backend) · `NOT_VERIFIED_ON_DEVICE` | |
| Сборка Flutter APK в GitHub Actions | `TESTED` | run 41418763510: analyze + test + build — success |
| Дизайн-система (токены, компоненты, скриншоты), Figma-ready | `IMPLEMENTED` | файла `.fig` нет — интеграции Figma нет |

## 1. Telegram Business

| Функция | Статус | Примечание |
|---|---|---|
| Приём `business_connection` (новое/выкл/смена прав), уведомление владельцу | `TESTED` | |
| Восстановление подключений после перезапуска | `TESTED` | `getBusinessConnection` при старте |
| Несколько подключений, изоляция данных | `TESTED` | |
| `business_message`, `edited_business_message`, `deleted_business_messages` | `TESTED` | |
| Команды владельца в бизнес-чате, замена командного сообщения результатом | `TESTED` · `REQUIRES_PERMISSION` | правка своих сообщений — до 48 ч (Telegram) |
| Собеседник не может выполнить команды владельца | `TESTED` | |
| Защита от петель (`sender_business_bot`), дедупликация, лимит автоответов | `TESTED` | |
| Окно 24 ч → результат в личку с ботом | `TESTED` · `LIMITED_BY_TELEGRAM` | `BUSINESS_PEER_USAGE_MISSING` |
| Инспектор прав, понятные причины отказа | `TESTED` | |
| Предупреждение об опасных правах (Stars, подарки) | `TESTED` | |
| Пауза при ответе владельца, пауза/аварийная остановка | `TESTED` | |
| Пометка «прочитано» (`readBusinessMessage`) | `IMPLEMENTED` · `REQUIRES_PERMISSION` | |
| Чтение истории до подключения | `NOT_SUPPORTED` | Telegram не отдаёт историю ботам |
| Группы и каналы | `NOT_SUPPORTED` | Business Mode — только личные чаты |
| Подделка/скрытие онлайн-статуса (`.online`) | `NOT_SUPPORTED` | команда объясняет причину |
| Передача Stars / подарков | `NOT_SUPPORTED` | намеренно (безопасность) |
| Реальные серверы Telegram | `NOT_VERIFIED_ON_DEVICE` | |

## 2. Команды и режимы

| Функция | Статус | Примечание |
|---|---|---|
| Парсер (`.`/`!`/`-`/`,`, пробел после префикса, регистр, RU/UZ-алиасы) | `TESTED` | 160 команд, [COMMANDS.md](COMMANDS.md) |
| Ошибки синтаксиса → подсказка приватно; неизвестная команда — тихо в чате, помощь в личке | `TESTED` | |
| Лимиты частоты, отключение команд, тарифные ограничения, бан | `TESTED` | |
| Песочница для теста команд из приложения | `TESTED` | |
| AFK: причина, таймер, ночной режим, кулдаун, авто-выкл., сводка | `TESTED` | |
| Режимы Manual / Auto / AI / AFK / Silent / Business / Hybrid | `TESTED` | AI и Hybrid — `REQUIRES_API_KEY` для AI-части |
| Правила автоответа, белый/чёрный список, рабочие часы, приветствие | `TESTED` | |
| Шаблоны `.tpl` | `IMPLEMENTED` | `.mute`, `.a`, `.r` в v3 — см. раздел 0 |
| Планировщик задач: выполнение и восстановление после перезапуска | `TESTED` | |
| Напоминания и таймеры `.remind`, `.timer` | `IMPLEMENTED` | работают через планировщик |

## 3. AI

| Функция | Статус | Примечание |
|---|---|---|
| Провайдеры OpenAI / Gemini / Anthropic / OpenAI-совместимый | `IMPLEMENTED` · `REQUIRES_API_KEY` · `NOT_VERIFIED_ON_DEVICE` | реальные API не вызывались (нет ключей); формат запросов сверен с документацией |
| Fallback, таймауты, очередь, учёт стоимости, дневные бюджеты/квоты | `TESTED` | на тестовом провайдере |
| `.gpt`, `.smart`, `.hint`, `.rewrite`, `.translate`, `.summary`, `.explain`, `.code`, `.grammar`, `.analyze` | `TESTED` (`.gpt`) / `IMPLEMENTED` · `REQUIRES_API_KEY` | |
| Авто-ответ AI с пометкой, склейка сообщений (debounce), черновики с подтверждением | `TESTED` | |
| Отмена AI-ответа, если владелец ответил сам | `TESTED` | |
| Защита от prompt injection (обёртка недоверенного текста) | `TESTED` | |
| Память фактов (с согласием), изоляция по пользователю и чату, TTL | `TESTED` | |
| Профили/персоны, playground в приложении | `TESTED` | |
| `.vision` (фото) | `IMPLEMENTED` · `REQUIRES_API_KEY` | |

## 4. Media Studio и Voice Studio

| Функция | Статус | Примечание |
|---|---|---|
| Реверс голосового/кружка/видео, скорость, громкость `.ld` (шкала 0–100, +0.3 дБ/шаг) | `TESTED` | реальный FFmpeg |
| Кружок, GIF, MP3, обрезка | `TESTED` | |
| Нормализация, шумодав, голосовое из видео, сжатие, конвертация (wav/webm/gif), склейка, извлечение звука | `TESTED` | smoke-тест на реальном FFmpeg |
| Фото: рамки (7 стилей), мем, blur, pixel, resize, crop, rotate, стикер, ч/б, сепия, резкость, шум, яркость, контраст, зеркало, водяной знак | `TESTED` | Pillow |
| Очередь, отмена `.cancel`, таймаут, лимит размера (20 МБ), защита от path traversal | `TESTED` | |
| Скачивание файлов > 20 МБ | `LIMITED_BY_TELEGRAM` | лимит Bot API на `getFile` |
| `.caption` (правка подписи своего сообщения) | `IMPLEMENTED` · `REQUIRES_PERMISSION` | |
| STT `.stt`, `.vtranslate`, `.vreply` | `IMPLEMENTED` · `REQUIRES_API_KEY` | Whisper |
| TTS `.tts` | `IMPLEMENTED` · `REQUIRES_API_KEY` | без ключа — офлайн espeak-ng, если установлен (`pkg install espeak`) |
| FFmpeg на телефоне (ARM64, Termux) | `NOT_VERIFIED_ON_DEVICE` | тесты шли на Linux x86-64 |

## 5. Игры

| Функция | Статус |
|---|---|
| Дуэль (фальстарт, время реакции, отказ, таймаут), дуэль с ботом в личке | `TESTED` |
| Крестики-нолики (ходы, победа, AI), КНБ (скрытый выбор), Revo, «Угадай число» | `TESTED` |
| Dice через бизнес-подключение, комбинации слотов | `TESTED` |
| Викторина, математика, слова, реакция, coin, рулетка, challenge, реванш, Elo | `IMPLEMENTED` |

## 6. Текст, профиль, автоматизация

| Функция | Статус | Примечание |
|---|---|---|
| Калькулятор (без `eval`, проценты `100-15%`), `.fix` (раскладка, Caps, опечатки) | `TESTED` | |
| base64/hex/binary/регистр/leet/hash/url/json/count/repeat/bubble/format/rd/timestamp/random | `TESTED` | |
| Смена имени/био бизнес-аккаунта с подтверждением | `TESTED` (через панель) · `REQUIRES_PERMISSION` | |
| Фото, username, бэкап/восстановление профиля | `IMPLEMENTED` · `REQUIRES_PERMISSION` | |
| Часы в био/фамилии `.clock` | `IMPLEMENTED` · `REQUIRES_PERMISSION` · `LIMITED_BY_TELEGRAM` | интервал ≥ 15 мин из-за лимитов |
| No-code правила, шаблоны, dry-run, журнал | `TESTED` | |
| Конструктор своих команд | `IMPLEMENTED` | |

## 7. Платформа

| Функция | Статус | Примечание |
|---|---|---|
| Панель `/start` (RU/UZ), все экраны, FSM-мастера, переключатели | `TESTED` | |
| Привязка приложения по коду `/app` | `TESTED` | |
| Один Super Admin, невидимый админ-раздел, защита от подстановки ID | `TESTED` | роль moderator из v1 упразднена |
| Подписки, триалы, промокоды, лимиты | `TESTED` | |
| Оплата Telegram Stars (идемпотентность, проверка суммы/валюты), выключено по умолчанию | `TESTED` · `NOT_VERIFIED_ON_DEVICE` | реальная оплата не проводилась |
| Рассылки (только админ, только личка бота) | `TESTED` | |
| Аналитика DAU/WAU/MAU, retention, экспорт CSV/JSON/PDF | `TESTED` | |
| Бэкап/восстановление БД, экспорт и удаление данных пользователя | `TESTED` | |
| Миграции, транзакции, параллельная запись | `TESTED` | |
| Режим обслуживания, аварийная остановка | `TESTED` | |
| Локальный REST API (159 эндпоинтов): auth, RBAC, лимиты, ошибки | `TESTED` | |
| Скрипты start/stop/status/backup | `TESTED` (вручную, Linux) · `NOT_VERIFIED_ON_DEVICE` | tmux/nohup, Termux-специфика не проверена |
| `install_termux.sh` | `IMPLEMENTED` · `NOT_VERIFIED_ON_DEVICE` | |

## 8. Chat helper Control v1 (нативное Android-приложение, для совместимости)

| Функция | Статус | Примечание |
|---|---|---|
| Сборка APK (aapt2 → javac → dx → zipalign → подпись v2/v3) | `TESTED` | подпись и выравнивание проверены |
| Экран привязки, форматирование кода, отказ от HTTP для не-локальных адресов, ошибка «backend недоступен» | `TESTED` | Robolectric, Android 14 framework |
| Полный сценарий против живого backend: вход → дашборд → все вкладки → вложенные экраны → поворот → выход → повторный вход | `TESTED` | Robolectric + реальный API; перепроверено против backend v3 (10/10) |
| Смена темы (Dark/Light/AMOLED) и языка (RU/UZ/EN) | `TESTED` | |
| Остальные экраны (чаты, подключения, правила, AI, медиа, игры, админ, Backup Center, Theme Studio…) | `IMPLEMENTED` | компилируются, открываются из тестового сценария выборочно |
| Хранение токенов в Android Keystore | `IMPLEMENTED` · `NOT_VERIFIED_ON_DEVICE` | Robolectric не эмулирует аппаратный Keystore полностью |
| Установка и работа на реальном Android 14 | `NOT_VERIFIED_ON_DEVICE` | |
| Сборка через Gradle / GitHub Actions | `IMPLEMENTED` · `NOT_VERIFIED_ON_DEVICE` | Google Maven недоступен в среде разработки |
