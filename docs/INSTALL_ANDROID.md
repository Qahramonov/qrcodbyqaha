# Установка на Android (Termux) и APK / Android'ga o'rnatish

> **v3:** установка и обновление бота — [INSTALL_TERMUX.md](INSTALL_TERMUX.md); новое приложение Chat helper Control v3 (Flutter) — [BUILD_FLUTTER.md](BUILD_FLUTTER.md). Этот файл описывает нативное приложение v1 (`dist/Chat_helper_Control.apk`), которое остаётся совместимым с сервером v3.

Целевая платформа: **Android 14, ARM64, Termux, Python 3.13**. Root, ПК, VPS и Docker не нужны.

---

## 1. Backend в Termux

### 1.1 Termux
* Ставьте Termux **из F-Droid** (`com.termux`) или из релизов GitHub `termux/termux-app`. Версия из Google Play устарела и не получает пакеты.
* Желательно поставить **Termux:API** (уведомления, wake-lock) и **Termux:Boot** (автозапуск) — из того же источника, что и Termux.
* Первый запуск: `termux-setup-storage` (нужно только для `backup.sh --shared`).

### 1.2 Получение проекта
Вариант A — архив: скопируйте `Chat_helper_FULL_PROJECT.zip` в «Загрузки», затем
```bash
pkg install -y unzip
cd ~ && unzip /sdcard/Download/Chat_helper_FULL_PROJECT.zip   # появится ~/Chat_helper
```
Вариант B — git: `pkg install -y git && git clone <url репозитория> ~/Chat_helper`.

### 1.3 Установка
```bash
cd ~/Chat_helper
bash scripts/install_termux.sh
```
Скрипт: ставит пакеты (python, ffmpeg, tmux, rust/clang для сборки `pydantic-core`, libjpeg/freetype для Pillow), Python-зависимости, создаёт `backend/.env` (права 600), инициализирует БД, прогоняет тесты и самопроверку. **Первая установка 10–20 минут** — компилируется `pydantic-core`. Повторный запуск безопасен.

Если `pip` падает на `pydantic-core`: `pkg install -y rust binutils && export ANDROID_API_LEVEL=$(getprop ro.build.version.sdk) && pip install -r backend/requirements.txt`.

### 1.4 Настройка и запуск
```bash
nano backend/.env           # BOT_TOKEN=..., при желании ключи AI
./scripts/start.sh          # tmux-сессия "chat_helper", termux-wake-lock
./scripts/status.sh
```
Логи: `backend/data/logs/chat_helper.log` (токены и ключи маскируются). Подключиться к консоли: `tmux attach -t chat_helper` (выйти не останавливая: `Ctrl+B`, затем `D`).

### 1.5 Чтобы Android не «убивал» процесс
1. **Настройки → Приложения → Termux → Батарея → Без ограничений** (на MIUI/HyperOS также «Автозапуск: вкл», на Samsung — убрать из «Спящих приложений»).
2. `termux-wake-lock` (start.sh вызывает сам) — в шторке появится уведомление Termux «wake lock held».
3. Не смахивайте Termux из недавних на прошивках с агрессивной экономией.
4. Android 12+ может останавливать «фантомные процессы». Если бот пропадает через какое-то время — см. [TROUBLESHOOTING.md](TROUBLESHOOTING.md#процесс-исчезает-phantom-process-killer).

### 1.6 Автозапуск после перезагрузки (Termux:Boot)
```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/chat_helper.sh <<'SH'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
cd ~/Chat_helper && ./scripts/start.sh
SH
chmod +x ~/.termux/boot/chat_helper.sh
```
Один раз откройте приложение Termux:Boot, чтобы Android разрешил ему запуск.

### 1.7 Обновление
```bash
./scripts/backup.sh && ./scripts/stop.sh
# распакуйте новую версию поверх (backend/.env и backend/data/ не трогаются) или git pull
pip install -r backend/requirements.txt
./scripts/start.sh            # миграции БД применяются автоматически
```

---

## 2. Установка APK

Готовый файл: **`dist/Chat_helper_Control.apk`** (≈190 КБ, package `com.chathelper.control`, versionName 1.0.0, minSdk 24 / targetSdk 34, подпись APK Signature Scheme v2 + v3, единственное разрешение — `INTERNET`).

1. Скопируйте APK на телефон, откройте его из «Файлов».
2. Разрешите «Установку из этого источника» для файлового менеджера.
3. Google Play Protect может показать «Приложение не проверено» — это ожидаемо для APK вне Play; выберите «Всё равно установить». Код приложения открыт: `android/app/src/main/java`.
4. Откройте **Chat helper Control** → сервер `http://127.0.0.1:8787` → код из `/app` → «Войти». Подробно — [OWNER_SETUP.md](OWNER_SETUP.md#6-привязка-приложения-chat-helper-control).

> Приложение подключается к backend на этом же телефоне. Обычный HTTP разрешён **только** для `127.0.0.1`, `localhost` и `10.0.2.2` (эмулятор); для любых других адресов приложение требует HTTPS.

**О подписи.** Готовый APK подписан локальным самоподписанным ключом, который не хранится в репозитории. Если вы соберёте APK сами, подпись будет другой — Android не даст «обновить» поверх: удалите старое приложение и установите новое (данных на телефоне почти нет — просто войдите заново по коду).

---

## 3. Сборка APK самостоятельно

### Вариант A — прямо на телефоне (Termux), без Android Studio и Gradle
```bash
pkg install -y aapt aapt2 apksigner d8 openjdk-17 python zip
cd ~/Chat_helper/android
./build_apk.sh                       # → ~/Chat_helper/dist/Chat_helper_Control.apk
```
Шаги скрипта: `aapt2 compile/link` → `javac` (или `ecj`) → `d8` (или `dalvik-dx`) → упаковка → `zipalign` (Python-реализация) → подпись v2/v3 (`apksigner`, иначе `uber-apk-signer`) → проверка подписи и выравнивания. При первом запуске создаётся ключ `android/chat_helper_control.keystore` (не коммитится). Свой пароль: `KS_PASS=... ./build_apk.sh`. **Сохраните keystore** — им нужно подписывать обновления.

Если нет `android.jar`, скрипт скачает публичный stub API 34 (`raw.githubusercontent.com/Sable/android-platforms`), либо укажите `ANDROID_JAR=/путь/android.jar`.

### Вариант B — GitHub Actions
Workflow `.github/workflows/android.yml` собирает `assembleRelease` через Gradle при push в `android/**` (или вручную: Actions → Android APK → Run workflow) и выкладывает APK как artifact — его можно скачать прямо на телефон. Для подписи своим ключом добавьте secrets репозитория `CH_KEYSTORE_B64` (`base64 -w0 my.keystore`), `CH_KS_PASS`, `CH_KEY_ALIAS`; без них APK подписывается debug-ключом Gradle.

> Gradle-сборка и этот workflow **не запускались** в среде разработки (Google Maven там недоступен); APK в `dist/` собран вариантом A. Статус в [FEATURE_MATRIX.md](FEATURE_MATRIX.md): NOT_VERIFIED.

### Вариант C — Android Studio / Gradle на ПК
```bash
cd android && ./gradlew assembleRelease     # нужен Android SDK 34, JDK 17
```
Проект без AndroidX и сторонних библиотек: AGP 8.7.3, Gradle 8.11.1, compileSdk 34, minSdk 24.

### Про AIDE и похожие IDE
Проект — чистая Java без lambda и AndroidX, поэтому теоретически импортируется в AIDE/CodeAssist как обычный Android-проект (`android/app`), но это **не проверялось**. Рекомендуемый путь на телефоне — вариант A.

### Тесты приложения (ПК/CI)
`scripts/run_android_tests.sh` — собирает классы, запускает backend в режиме `--api-only` на временной БД, выдаёт два одноразовых кода и прогоняет Robolectric-тесты (реальный фреймворк Android 14 в JVM) против живого API. Требуются JDK 17+ и Maven. Результаты — [TEST_REPORT.md](TEST_REPORT.md).

---

## UZ — qisqacha

1. **Termux**ni F-Droid'dan o'rnating (Google Play'dagi versiya eskirgan). Termux:API va Termux:Boot ham tavsiya etiladi.
2. Arxivni oching: `cd ~ && unzip /sdcard/Download/Chat_helper_FULL_PROJECT.zip`.
3. `cd ~/Chat_helper && bash scripts/install_termux.sh` — birinchi o'rnatish 10–20 daqiqa.
4. `nano backend/.env` → `BOT_TOKEN=...`, so'ng `./scripts/start.sh`, `./scripts/status.sh`.
5. Batareya: Sozlamalar → Ilovalar → Termux → Batareya → **Cheklovsiz**. `termux-wake-lock` yoqilgan bo'lsin.
6. Avtoishga tushirish: yuqoridagi 1.6 bo'limdagi `~/.termux/boot/chat_helper.sh` skripti.
7. **APK**: `dist/Chat_helper_Control.apk` ni o'rnating (noma'lum manbadan o'rnatishga ruxsat bering), server `http://127.0.0.1:8787`, kod — botdagi `/app` buyrug'idan.
8. APK'ni telefonda yig'ish: `pkg install -y aapt aapt2 apksigner d8 openjdk-17 python zip && cd android && ./build_apk.sh`. Keystore faylini saqlab qo'ying — yangilanishlar shu kalit bilan imzolanadi.
