# Настройка владельца / Egasini sozlash

Владелец (Super Admin): Telegram ID **8053614984** (username `@libPM` — справочно; права определяются **только по ID**, проверка на сервере).

---

## RU

### 1. Создать бота и включить Business Mode
1. Откройте **@BotFather** → `/newbot` (или используйте существующего бота) → сохраните токен. **Никому его не пересылайте** и не вставляйте в чаты.
2. @BotFather → `/mybots` → ваш бот → **Bot Settings → Business Mode → Turn on**.
3. (Необязательно) `/setdescription`, `/setuserpic` — имя бота: **Chat helper**.

### 2. Заполнить `.env`
```bash
cd ~/Chat_helper
cp -n backend/.env.example backend/.env   # install_termux.sh делает это сам
chmod 600 backend/.env
nano backend/.env
```
Обязательно: `BOT_TOKEN=<токен из BotFather>`. Уже стоит: `SUPER_ADMIN_ID=8053614984`, `API_HOST=127.0.0.1`, `API_PORT=8787`.
Необязательно: ключи AI (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` или `COMPAT_*`), `TIMEZONE`, `DEFAULT_LANG=ru|uz`.

Проверка конфигурации без запуска бота: `cd backend && python main.py --check` (выводит сводку **без секретов**).

### 3. Первый запуск
```bash
./scripts/start.sh      # запускает бот + API в tmux и включает termux-wake-lock
./scripts/status.sh     # должно быть: process running, API {"status":"ok",...}
```
Откройте бота в Telegram → **/start**. Появится меню на русском (язык меняется в «Настройки»). До подключения аккаунта бот покажет мастер подключения (функции откроются после него). Для ID 8053614984 в меню будет кнопка **«👑 Super Admin»** — другие пользователи её не видят.

### 4. Подключить бота к своему аккаунту (Telegram Business)
**Telegram Premium не нужен** — бизнес-бота может подключить любой аккаунт.
1. Telegram → **Настройки → Изм. (Edit) профиля → «Автоматизация чатов»** (в старых версиях: Настройки → Telegram для бизнеса → Чат-боты).
2. Введите username вашего бота → выберите, в каких чатах он работает (все личные / выбранные / исключения).
3. Права (рекомендация):
   * ✅ **Читать сообщения** и ✅ **Отвечать на сообщения** — основа всех функций.
   * ✅ **Удалять отправленные сообщения** — для уборки командных сообщений.
   * ⚪ Имя / био / фото / username — только если нужны `.name`, `.bio`, `.avatar`, `.clock`.
   * ⛔ **Передача Stars, подарков, конвертация подарков** — не выдавайте: Chat helper их не использует, инспектор прав предупредит, если они включены.
4. Бот пришлёт в личку «🔗 Аккаунт подключён к Chat helper!» со списком доступного и недоступного. Проверить в любой момент: `.status` или меню → «🔗 Подключить аккаунт».

### 5. Проверка команд
В **любом подключённом личном чате** (или в личке с ботом) напишите:
* `.ping` — бот ответит временем реакции (командное сообщение будет заменено ответом).
* `.help` — список категорий; `.help afk` — помощь по команде.
* `.afk Занят до 18:00` → попросите собеседника написать вам → он получит AFK-ответ; `.unafk` — сводка.
* `.calc 2+2*2`, `.fix ghbdtn` — проверка текстовых инструментов.
* Ответом на видео: `.circle` — кружок (нужен ffmpeg).

> Если собеседник **не писал вам 24 часа**, Telegram запрещает боту писать в этот чат — результат придёт в личку с ботом. Это не ошибка.

### 6. Привязка приложения Chat helper Control
1. Установите `Chat_helper_Control.apk` (см. [INSTALL_ANDROID.md](INSTALL_ANDROID.md#2-установка-apk)).
2. В боте отправьте **/app** (или меню → «Приложение») — придёт одноразовый код вида `ABCD-EFGH`, живёт 5 минут.
3. В приложении: **Сервер** `http://127.0.0.1:8787` (по умолчанию), **Код из Telegram** → **Войти**.
4. Приложение хранит только токены (зашифрованы Android Keystore). Токен бота в приложение **не передаётся никогда**.

Альтернатива без Telegram (например, бот ещё не настроен): в Termux `cd backend && python tools/issue_pair_code.py` — код для SUPER_ADMIN_ID. Кто может запустить эту команду, уже имеет доступ к файлам backend, поэтому безопасность не снижается.

### 7. Контрольный список
- [ ] `./scripts/status.sh` — процесс работает, API отвечает.
- [ ] `/start` показывает кнопку «👑 Super Admin» (только у вас).
- [ ] Меню → «🔗 Подключить аккаунт»: статус **connected**, права «читать» и «отвечать» включены, опасных прав нет.
- [ ] `.ping` в подключённом чате работает.
- [ ] Приложение: вход по коду, дашборд показывает «Chat helper is running».
- [ ] `termux-wake-lock` активен, Termux исключён из оптимизации батареи.
- [ ] `./scripts/backup.sh` создаёт бэкап.

---

## UZ

### 1. Bot yaratish va Business Mode'ni yoqish
1. **@BotFather** → `/newbot` → tokenni saqlang. **Uni hech kimga yubormang.**
2. @BotFather → `/mybots` → botingiz → **Bot Settings → Business Mode → Turn on**.

### 2. `.env` faylini to'ldirish
```bash
cd ~/Chat_helper && nano backend/.env
```
Majburiy: `BOT_TOKEN=<BotFather tokeni>`. Tayyor: `SUPER_ADMIN_ID=8053614984`, `API_HOST=127.0.0.1`. Ixtiyoriy: AI kalitlari, `TIMEZONE`, `DEFAULT_LANG=uz`.

### 3. Birinchi ishga tushirish
```bash
./scripts/start.sh && ./scripts/status.sh
```
Telegram'da botga **/start** yuboring. Tilni «Sozlamalar» bo'limida o'zbekchaga almashtiring. ID 8053614984 uchun menyuda **«👑 Super Admin»** tugmasi bo'ladi (boshqalarga ko'rinmaydi).

### 4. Botni akkauntga ulash (Telegram Business)
**Telegram Premium shart emas** — biznes botni istalgan akkaunt ulashi mumkin.
1. **Sozlamalar → profilni Tahrirlash → «Chatlarni avtomatlashtirish»** (eski versiyalarda: Telegram Business → Chat-botlar) → botning username'ini kiriting.
2. Huquqlar: ✅ xabarlarni o'qish, ✅ javob berish, ✅ yuborilgan xabarlarni o'chirish. ⚪ ism/bio/rasm — kerak bo'lsa. ⛔ **Stars va sovg'alarni o'tkazish** — bermang.
3. Bot shaxsiy chatga «🔗 Akkaunt Chat helper'ga ulandi!» xabarini yuboradi. Tekshirish: `.status`.

### 5. Buyruqlarni tekshirish
Ulangan chatda: `.ping`, `.help`, `.afk Band`, `.unafk`, `.calc 2+2*2`. Suhbatdosh 24 soatdan beri yozmagan bo'lsa, natija bot bilan shaxsiy chatga keladi.

### 6. Chat helper Control ilovasini ulash
1. `Chat_helper_Control.apk` ni o'rnating.
2. Botga **/app** yuboring — bir martalik kod (`ABCD-EFGH`, 5 daqiqa).
3. Ilovada: Server `http://127.0.0.1:8787`, Kod → **Kirish**.

Telegram'siz: `cd backend && python tools/issue_pair_code.py`.

### 7. Tekshiruv ro'yxati
- [ ] `./scripts/status.sh` — jarayon ishlayapti, API javob beradi.
- [ ] `/start` da «🛡 Boshqaruv» bo'limi bor.
- [ ] Ulanish holati **connected**, xavfli huquqlar yo'q.
- [ ] `.ping` ishlaydi; ilovaga kod bilan kirildi.
- [ ] `termux-wake-lock` yoqilgan, Termux batareya optimizatsiyasidan chiqarilgan.
