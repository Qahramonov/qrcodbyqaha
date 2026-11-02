# Chat helper Control v3 (Flutter)

Мобильный пульт для бота **Chat helper** (Telegram Business). Android-пакет `com.chathelper.control`, версия 3.0.0 (versionCode 30).

* **Стек:** Flutter 3.47 / Dart 3.13 · Riverpod 3 · GoRouter 18 · Dio 5 · flutter_secure_storage · Material 3 (тёмная тема, «liquid glass»), шрифт Inter (OFL).
* **40 экранов**, все работают с настоящим REST API бэкенда (`/api/v1`), без заглушек. 24 пользовательских: Splash, Offline, Welcome, Pairing, Connection Wizard, Home, Chats, Chat Controls, Permissions, AI, AI Twin, AI Playground, AFK, Mute, Protect, Animations, Media Studio, Games, Commands, Reminders, Automation Builder, Profile, Statistics, Subscription, Language, Settings. 16 экранов Super Admin: Dashboard, Users, User card, Connections, Permissions, AI, Media, Games, Commands, Payments, Analytics, Broadcast, Security, System, Logs, Diagnostics.
* **Языки:** русский и узбекский (латиница) — `lib/core/strings.dart`; тексты сервера приходят уже на языке аккаунта.

## Безопасность

* Подключение только одноразовым кодом из бота (`/app`). Токены хранятся в Android Keystore (`flutter_secure_storage`), `allowBackup=false`.
* Обычный `http://` разрешён **только** для бота на этом же телефоне (`127.0.0.1`, `localhost`, эмулятор `10.0.2.2`). Удалённый сервер — только `https://` (проверка в приложении и `network_security_config.xml`).
* **Админ-раздел существует только для Super Admin.** Роль приходит с сервера (`/auth/me`), её нельзя подделать на клиенте; роутер не открывает `/admin/*` никому другому, а сервер на все админ-маршруты отвечает чужим `404`, как на несуществующий адрес.
* Пока Telegram-аккаунт не подключён в «Автоматизации чатов», открыты только мастер подключения, язык, настройки, профиль и подписка (как в боте).
* В APK нет токена бота и никаких секретов.

## Разработка

```bash
flutter pub get
flutter analyze          # 0 issues
flutter test             # unit + widget tests (34)
flutter run              # телефон/эмулятор; бот должен быть запущен (Termux: ./scripts/start.sh)
```

Тесты используют **записанные ответы настоящего бэкенда**: `test/fixtures/api_samples.json` создаётся скриптом
`python3 tests/backend/record_api_samples.py` (поднимает реальный backend с фейковым Telegram и опрашивает все GET-эндпоинты
как обычный пользователь и как Super Admin, на ru и uz). Токены в файл не попадают.

Скриншоты реальных экранов (те же виджеты и данные, шрифт Inter):

```bash
flutter test --update-goldens --tags screenshots --run-skipped test/screenshots_test.dart   # → test/screenshots/*.png
```

Оптимизированные копии лежат в `docs/screenshots/`.

## Сборка APK

* **GitHub Actions:** workflow `.github/workflows/flutter.yml` (analyze → test → `flutter build apk --release`), APK публикуется
  в релиз `control-v3` — прямая ссылка: https://github.com/Qahramonov/qrcodbyqaha/releases/download/control-v3/Chat_helper_Control_v3.apk (а также артефакт `Chat_helper_Control_v3` запуска). Подпись: секреты `CH_KEYSTORE_B64`, `CH_KS_PASS`, `CH_KEY_ALIAS`; без них APK подписан debug-ключом.
* **Локально:** `flutter build apk --release` → `build/app/outputs/flutter-apk/app-release.apk` (нужен Android SDK).

Если на телефоне стоит старое нативное приложение v1 с другой подписью, Android не даст установить поверх —
удалите старое (данных в нём нет, только сессия) и подключите v3 заново кодом `/app`.

Дизайн-система и макеты для Figma: `docs/FIGMA_DESIGN.md`, токены — `design/tokens.json` (тест сверяет их с `lib/core/theme.dart`).
