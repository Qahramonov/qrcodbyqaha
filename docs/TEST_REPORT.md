# Отчёт о тестировании — Chat helper v3

Дата прогона: 2026-11-02. Все цифры — результат реального запуска (локально в среде разработки и в GitHub Actions), а не ожидания.
Telegram в тестах — поддельная сессия Bot API (`tests/backend/fakes.py`), которая записывает и проверяет каждый вызов метода;
поведение настоящих серверов Telegram и реального телефона отмечено как **NOT VERIFIED ON REAL DEVICE**.

## 1. Среда

| Компонент | Версия |
|---|---|
| ОС / архитектура | Linux x86_64 (облачный контейнер) — **не Android-телефон**; CI — GitHub Actions `ubuntu-latest` |
| Python | 3.13.18 (синтаксис проверен на совместимость с 3.11: `ruff --target-version py311`) |
| aiogram / FastAPI / Pydantic / uvicorn | 3.31.0 (Bot API 10.3) / 0.162.0 / 2.13.5 / 0.54.0 |
| Pillow / aiosqlite / httpx / FFmpeg | 12.3.0 / 0.22.1 / 0.28.1 / 6.1.1 |
| Flutter / Dart | 3.47.9 / 3.13.7 (Riverpod 3.4.3, go_router 18.1.2, Dio 5.11.1) |
| JDK / Maven / Robolectric | OpenJDK 21 / 3.9.11 / 4.17 (Android 14) |
| Недоступно из среды | `api.telegram.org`, `core.telegram.org`, Google Maven (Gradle-сборка Android), AI-провайдеры, реальный телефон |

## 2. Backend — pytest: **238 из 238**

```
$ python3 -m pytest -q tests/backend
238 passed in 58.18s
$ ruff check --select F821,F811,F401,F841 --target-version py311 backend tests
All checks passed!
```

| Файл | Тестов | Что проверяет |
|---|---|---|
| `test_v3_access.py` | 19 | только Super Admin — администратор (moderator и username ничего не дают, подстановка ID в API — нет); блокировка до подключения: меню, команды, callback, FSM; мастер подключения (`copy_text`, `tg://settings/edit`), инфографика, проверка подключения; панели пользователя и Super Admin; v3 API |
| `test_v3_controls.py` | 18 | Chat Control Framework: карточки, нажатия только владельца, устаревшие версии, идемпотентность, отзыв при отключении, таймеры; Mute (подтверждение, `deleteBusinessMessages`, типы, белый список, отчёт, нет права → предупреждение), Protect, `.g`, NoGIF, NoMute, `.online`, `bizChat` |
| `test_v3_features.py` | 21 | Animation Engine (16 типов, эмодзи не рвутся, FloodWait, отмена), `.r`, `.ball`, `.morse`, `.re` (кнопка стоп, лимит Free), `.mad`, напоминания (личка/чат/запасной вариант), `.info`, `.geo`, `.qr` из фото, `.ptext` (заглушка tesseract и сообщение без движка), GIF из фото, водяной знак на видео/кружке, AI-двойник (режимы, обучение только на своих сообщениях) |
| `test_v3_localization.py` | 15 | каталоги ru/uz: одинаковые ключи, плейсхолдеры, нет кириллицы в uz, каждый ключ из кода существует, динамические ключи, нет русского в `handlers/`; **все экраны панели, все разделы Super Admin, основные команды и онбординг — на узбекском без кириллицы** |
| `test_v3_admin_hidden.py` | 11 | админ-раздел невидим: нет входов в меню, `.logs` = «неизвестная команда», подделанные callback/FSM — молча; **каждый из 43 админ-маршрутов API отвечает не-админу тем же 404, что несуществующий адрес**; без токена — одинаковый 401; Swagger выключен; Super Admin всё видит |
| `test_v3_extra.py` | 6 | бэкап перед миграцией M003 (данные сохраняются), без бэкапа на новой установке, `.finfo`, `.wtm` на фото, `.quiet`, уведомления Super Admin на его языке |
| `test_commands.py` | 41 | парсер, алиасы, префиксы, ошибки синтаксиса, лимиты, admin-only, тарифы, бан, песочница, текстовые инструменты, `.fix`, режимы автоответчика, AFK |
| `test_business.py` | 19 | подключения, восстановление после рестарта, изоляция аккаунтов, команды с правкой сообщения, LoopGuard, AFK-ответ и кулдаун, окно 24 ч → личка, правки/удаления, инспектор прав |
| `test_api.py` | 19 | health, сопряжение, ротация токенов, отзыв, не-админ → 404 на админ-API, изоляция данных, валидация, автоматизация, медиа, игры, подписки, публичный адрес только с TLS |
| `test_ai.py` / `test_media.py` / `test_games.py` | 14 / 14 / 10 | AI (fallback, бюджеты, память, черновики, prompt injection), реальный FFmpeg и Pillow, игры |
| `test_database.py` / `test_panel.py` / `test_security.py` | 10 / 12 / 9 | миграции, транзакции, бэкап/восстановление, платежи; экраны панели; маскировка секретов, блокировка сопряжения, лимиты |

**GitHub Actions «Backend tests»:** run 41413416091 (коммит 3003540) — success; run 41418763499 (коммит 45a95e4) — success.

## 3. Flutter — Chat helper Control v3

```
$ flutter analyze
No issues found!
$ flutter test
00:19 +34 ~1: All tests passed!          (~1 = рендер скриншотов, запускается по требованию)
```

| Файл | Тестов | Что проверяет |
|---|---|---|
| `router_test.dart` | 9 | `/admin/*` только для `super_admin` (обычный, неподключённый, с подделанными полями роли — домой); состояния сессии; блокировка до подключения; 40+ маршрутов зарегистрированы |
| `unit_test.dart` | 13 | адрес сервера (http только для 127.0.0.1/localhost/10.0.2.2), refresh токена при 401 и повтор запроса, конец сессии при отказе refresh, разбор ошибок; ключи ru/uz, плейсхолдеры, латиница, все ключи из кода, динамические ключи; токены дизайна = `design/tokens.json` |
| `screens_test.dart` | 12 | **все 24 пользовательских и 16 админ-экранов на записанных ответах настоящего бэкенда (ru и uz)**: без ошибок, без бесконечной загрузки; в uz нет русских строк приложения; у обычного пользователя нет плитки Super Admin, `/admin/*` возвращает домой, запросов к админ-API нет; мастер подключения для неподключённого аккаунта; сопряжение (http к удалённому хосту отклоняется до запроса), неверный код; Mute с подтверждением → `confirm=true`; AFK, напоминание, песочница команд, конструктор автоматизации — правильные тела запросов |

Ответы бэкенда для тестов записаны настоящим сервером: `tests/backend/record_api_samples.py` (246 ответов: обычный пользователь
и Super Admin, ru и uz).

**GitHub Actions «Flutter APK (v3)»** — run 41418763510 (коммит 45a95e4): `flutter pub get` ✅, `flutter analyze` ✅,
`flutter test` ✅, `flutter build apk --release` ✅, артефакт `Chat_helper_Control_v3` (APK + SHA-256, 26.75 МБ в zip,
хранится до 2026-12-02). Подпись — debug-ключ (секреты подписи в репозитории не заданы).

**Релиз `control-v3`** — run 41422499383 (коммит 9eba912): analyze ✅, test ✅, build ✅, публикация ✅. APK скачан с прямой ссылки релиза и проверен локально: SHA-256 совпадает с опубликованным (`a8cc1d9e1fff5ca5439caf800d3d51cc4b16378bf9206018fa89afcef8ec4abe`), `aapt2 dump badging` — `com.chathelper.control`, versionCode 30, versionName 3.0.0, compileSdk 36, разрешение `INTERNET` (+ служебное AndroidX `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`), ABI arm64-v8a / armeabi-v7a / x86_64; `uber-apk-signer --onlyVerify` — zipalign ✅, подпись v2 ✅ (debug-сертификат); секретов в APK нет. Размер 55 МиБ.

## 4. Нативное приложение v1 против сервера v3 — Robolectric: **10 из 10**

```
$ ./scripts/run_android_tests.sh          # реальный backend v3 (--api-only) + Android 14 framework в JVM
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0 -- in com.chathelper.control.AppFlowTest
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0 -- in com.chathelper.control.FmtTest
▸ Android tests PASSED
```
Сценарий: сопряжение по коду → дашборд → вкладки → менеджер команд → System Control → поворот → выход → повторный вход.
Вывод: нативное приложение v1 совместимо с сервером v3.

## 5. Безопасность — проверки

* Скан секретов (`git grep` по репозиторию и по рабочим файлам: токены Telegram, `sk-…`, `sk-ant-…`, `AIza…`, приватные ключи,
  ID бота) — **совпадений в отслеживаемых файлах нет**; находки только в `__pycache__` тестов маскировщика (фейковые токены,
  не в git). `backend/.env`, keystore и `local.properties` в git не попадают.
* Невидимость админ-раздела — перебором всех админ-маршрутов (раздел 2).
* Секреты в логах маскируются (в т.ч. внутри URL), API по умолчанию только на 127.0.0.1, удалённо — только с TLS.

## 6. Найдено и исправлено во время v3

* Ошибочное утверждение ранних ответов «для бизнес-бота нужен Telegram Premium» — **неверно**: Premium не нужен (исправлено в
  документации и мастере подключения).
* Переопределения стилей текста в теме Flutter теряли шрифт (тексты были бы Roboto вместо Inter) — найдено по скриншотам, исправлено.
* Английские тексты уведомлений Super Admin в коде — перенесены в каталоги RU/UZ.
* Две API-функции без зависимости `app` после локализации шаблонов автоматизации — исправлено до коммита (тесты).
* f-строки с вложенными кавычками (несовместимы с Python 3.11) — переписаны, проверено `ruff --target-version py311`.

## 7. NOT VERIFIED ON REAL DEVICE

| Что | Почему | Как проверить |
|---|---|---|
| Работа с настоящими серверами Telegram: business-апдейты, inline-кнопки карточек в бизнес-чате (у владельца и собеседника), `deleteBusinessMessages` (Mute), `protect_content`, окно 24 ч, правка сообщений | `api.telegram.org` недоступен из среды | подключить бота, `.mute 10m` в тестовом чате, нажать кнопки карточки |
| Открытие `tg://settings/edit` из бота и приложения | нет клиента Telegram | кнопка «Открыть настройки» в мастере |
| Ephemeral-сообщения | не используются (Bot API не принимает `business_connection_id`) | — |
| `.ptext` с настоящим tesseract | tesseract не установлен в среде (тест — с заглушкой) | `pkg install tesseract`, `.ptext` ответом на фото |
| Flutter APK на реальном Android 14: установка, Keystore, внешний вид | нет устройства | установить `Chat_helper_Control_v3.apk`, сопряжение `/app` |
| Termux (ARM64): `install_termux.sh`, FFmpeg, память и скорость | нет устройства | установка по [INSTALL_TERMUX.md](INSTALL_TERMUX.md) |
| Реальные AI-провайдеры и оплата Stars | нет ключей / нужен реальный платёж | добавить ключ, `.ai тест`; `PAYMENTS_ENABLED=true` |

## 8. Как повторить

```bash
python3 -m pytest -q tests/backend                                 # backend (238)
cd flutter_app && flutter analyze && flutter test                  # приложение v3 (34)
./scripts/run_android_tests.sh                                     # нативное v1 против backend (JDK 17+, Maven)
python3 tests/backend/record_api_samples.py                        # обновить ответы API для тестов Flutter
```
