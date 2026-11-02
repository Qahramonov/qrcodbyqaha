# Chat helper Control v3 (Flutter): установка и сборка

Исходники — `flutter_app/` ([README](../flutter_app/README.md)). Пакет `com.chathelper.control`, версия 3.0.0 (versionCode 30),
minSdk — по умолчанию Flutter 3.47, единственное разрешение — `INTERNET`.

## 1. Установить на телефон

1. Скачайте `Chat_helper_Control_v3.apk`:
   * **прямая ссылка (без входа в GitHub):** https://github.com/Qahramonov/qrcodbyqaha/releases/download/control-v3/Chat_helper_Control_v3.apk
   * страница релиза: https://github.com/Qahramonov/qrcodbyqaha/releases/tag/control-v3 (там же SHA-256);
   * запасной вариант — GitHub → Actions → «Flutter APK (v3)» → запуск → Artifacts (zip, нужен вход в GitHub);
   * или соберите сами (раздел 3).
2. Если стоит старое приложение Chat helper Control (v1) и Android пишет «Приложение не установлено» — подписи разные:
   удалите старое (в нём только сессия входа) и установите v3.
3. Разрешите установку из файлового менеджера; Play Protect может предупредить о приложении не из Play — это ожидаемо, код открыт.
4. Откройте приложение → «Подключить приложение» → в Telegram отправьте боту `/app` → введите код (действует 5 минут).
   Сервер по умолчанию `http://127.0.0.1:8787` — бот в Termux на этом же телефоне.

Если приложение пишет «Сервер недоступен» — бот не запущен: `./scripts/start.sh` в Termux, затем «Повторить».

## 2. Что внутри

* Flutter 3.47.9 / Dart 3.13.7, Riverpod 3, GoRouter 18, Dio 5, flutter_secure_storage 11, url_launcher, Material 3, Inter.
* 40 экранов на реальном API (список — [FIGMA_DESIGN.md](FIGMA_DESIGN.md#5-экраны-40)), RU/UZ, состояния загрузки/пусто/ошибка.
* Безопасность: токены в Android Keystore, `allowBackup=false`, HTTP только к `127.0.0.1/localhost/10.0.2.2`
  (`network_security_config.xml` + проверка в коде), админ-маршруты только для `super_admin` (роль с сервера).

## 3. Сборка

### GitHub Actions (рекомендуется)

Workflow `.github/workflows/flutter.yml` запускается при push в `flutter_app/**` (или вручную: Actions → Flutter APK (v3) → Run workflow):
`flutter pub get` → `flutter analyze` → `flutter test` → `flutter build apk --release` → артефакт `Chat_helper_Control_v3`
(APK + `.sha256`, хранится 30 дней) → **GitHub Release `control-v3`** (pre-release; APK и `.sha256` как прямые ссылки,
пересоздаётся при каждой сборке).

Подпись своим ключом: секреты репозитория `CH_KEYSTORE_B64` (`base64 -w0 my.keystore`), `CH_KS_PASS`, `CH_KEY_ALIAS`.
Без них APK подписан debug-ключом (ставится на свой телефон, но обновлять поверх можно только APK с той же подписью).
**Keystore не коммитьте в репозиторий.**

### На ПК

```bash
cd flutter_app
flutter pub get
flutter analyze
flutter test
flutter build apk --release      # → build/app/outputs/flutter-apk/app-release.apk
```

Нужны Flutter 3.47.x, Android SDK (platform + build-tools), JDK 17. Gradle 9.3.1 и AGP 9.1 скачиваются автоматически.

### В Termux на телефоне

Официальной сборки Flutter для Termux нет, поэтому собирать APK на телефоне не рекомендуется — используйте GitHub Actions.

## 4. Тесты

* `flutter test` — 34 теста: роутер (админ-маршруты, блокировка до подключения), API-клиент (refresh токена, ошибки),
  локализация (ключи, плейсхолдеры, латиница), токены дизайна, **все 40 экранов на записанных ответах настоящего бэкенда**
  (ru и uz), сопряжение, Mute с подтверждением, AFK/напоминания/песочница команд/конструктор автоматизаций.
* Ответы бэкенда для тестов: `python3 tests/backend/record_api_samples.py` → `flutter_app/test/fixtures/api_samples.json`.
* Скриншоты: `flutter test --update-goldens --tags screenshots --run-skipped test/screenshots_test.dart`.

## 5. Проверено / не проверено

* ✅ `flutter analyze` — 0 замечаний; `flutter test` — 34/34 (локально и на GitHub Actions).
* ✅ Сборка release APK — в GitHub Actions (см. [TEST_REPORT.md](TEST_REPORT.md)).
* ⚠️ **NOT VERIFIED ON REAL DEVICE:** установка и работа APK на реальном телефоне (Android 14), открытие `tg://settings/edit`
  из приложения, Android Keystore на конкретной прошивке.
