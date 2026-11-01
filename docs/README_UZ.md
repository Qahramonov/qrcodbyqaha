# Chat helper — qo'llanma (UZ)

**Chat helper** — **Telegram Business** rejimi uchun bot (rasmiy Bot API, «Chat-botlar» / Business Mode) va uni boshqarish uchun **Chat helper Control** Android ilovasi. Hammasi **bitta Android telefonda, Termux ichida** ishlaydi: kompyuter, VPS, root va Docker kerak emas. Yangilanishlar long polling orqali olinadi — webhook va oq IP kerak emas.

> Ruscha versiya: [README_RU.md](README_RU.md) · Buyruqlar: [COMMANDS.md](COMMANDS.md) · API: [API.md](API.md) · Funksiyalar holati: [FEATURE_MATRIX.md](FEATURE_MATRIX.md)

---

## 1. Imkoniyatlar

| Modul | Qisqacha |
|---|---|
| **Business dvigateli** | `business_connection`, `business_message`, tahrirlar va o'chirishlarni qabul qiladi; ulanish huquqlarini hisobga oladi, sikl va dublikatlardan himoya, sizning nomingizdan javob, buyruq xabarini natijaga aylantirish (tahrirlash), zaxira kanal — bot bilan shaxsiy chat. |
| **Egasining buyruqlari** | `.` prefiksli 141 ta buyruq (`!` `-` `,` ga o'zgartirish mumkin), RU/UZ taxalluslar, `. afk` (bo'sh joy bilan) ham ishlaydi, registr muhim emas. Istalgan ulangan chatda va bot bilan shaxsiy chatda ishlaydi. To'liq ro'yxat — [COMMANDS.md](COMMANDS.md). |
| **AFK** | `.afk [vaqt] [sabab]`, tungi rejim `.sleep`, `.unafk` da o'tkazib yuborilganlar xulosasi, anti-spam (har bir chatga interval ichida 1 marta), istisnolar. |
| **Avtojavob** | **Manual / Auto / AI / AFK / Silent / Business / Hybrid** rejimlari, kalit so'z qoidalari, ish vaqti va undan tashqari matn, yangi suhbatdoshlarga salom, siz o'zingiz yozganingizda avtojavob pauzasi, kalit so'z bo'yicha insonga uzatish, oq/qora ro'yxat, kunlik limitlar. |
| **AI yordamchi** | OpenAI, Gemini, Anthropic va istalgan OpenAI-mos API (OpenRouter, Groq, DeepSeek, Ollama…). Fallback zanjiri, navbat, $ dagi byudjet, roziligingiz bilan fakt xotirasi, profillar, «Yuborish» tugmali qoralamalar, «AI javobi» belgisi. Kalitsiz — AI buyruqlari kalit sozlanmaganini ochiq aytadi. |
| **Media Studio** | FFmpeg + Pillow: videodan dumaloq video, ovozli xabar, konvertatsiya, siqish, kesish, tezlik, teskari, ovoz balandligi (`.ld`), shovqinni tozalash, GIF, filtrlar, ramkalar (gold/luxury/diamond/neon/cyber/glass/minimal), memlar, stikerlar, QR. Navbat, taymautlar, `.cancel`. |
| **Voice Studio** | STT (Whisper), TTS (OpenAI yoki oflayn espeak-ng), ovozli xabar tarjimasi, ovozli xabarga AI javobi. |
| **O'yinlar** | Dice/slot/coin/ruletka, duel, «Revo», krestik-nolik, tosh-qaychi-qog'oz, viktorina, son topish, matematika, so'zlar, reaksiya; taklif, revansh, Elo reytingi. |
| **Matn vositalari** | Xavfsiz kalkulyator (`eval`siz), `.fix` — RU↔EN klaviatura, Caps Lock, cho'zilgan harflar, imlo xatolari, hisoblash, xeshlar, base64/hex/url, JSON, parollar, UUID, vaqt, QR. |
| **Profil** | Biznes akkauntning ismi, bio, rasmi, username'i (faqat huquq berilgan bo'lsa), bio/familiyada soat. |
| **Avtomatlashtirish** | Kodsiz qoidalar «trigger → shartlar → amallar», shablonlar, dry-run, bajarilish jurnali, o'z buyruqlaringiz konstruktori. |
| **Rejalashtiruvchi** | Kechiktirilgan xabarlar/vazifalar, qayta ishga tushirishdan keyin ham saqlanadi. |
| **Analitika** | DAU/WAU/MAU, retention, churn, grafiklar; CSV/JSON/PDF eksport. Faqat bazadagi haqiqiy ma'lumotlar. |
| **Ko'p foydalanuvchi** | Rollar user / moderator / super_admin (super_admin — faqat `SUPER_ADMIN_ID` dagi ID), tarif limitlari, ban, audit. |
| **Obunalar** | Free / Plus / Pro / VIP, sinov muddati, promokodlar, **Telegram Stars** (XTR) orqali to'lov, idempotent to'lov ishlovi, qaytarish. Standart holatda to'lovlar o'chirilgan. |
| **Telegram panel** | `/start` → RU/UZ menyu: rejimlar, AFK, avtojavoblar, AI, media, o'yinlar, profil, tarif, sozlamalar, ilovani ulash. |
| **Admin panel** | Foydalanuvchilar, tariflar, xabarnomalar (faqat bot shaxsiy chatiga, 20/s), loglar, funksiya bayroqlari, texnik xizmat, favqulodda to'xtatish, zaxira nusxalar. |
| **Lokal API** | FastAPI `127.0.0.1:8787`, 135 endpoint, tokenlar, serverda rol tekshiruvi. Tavsif — [API.md](API.md). |
| **Chat helper Control (APK)** | Nativ Android ilova: «shisha» uslubidagi qorong'i dizayn, Telegram'dan bir martalik kod bilan kirish, dashboard, chatlar, ulanishlar va huquqlar, avtomatlashtirish, AI, media, o'yinlar, admin bo'limlari, Theme Studio, RU/UZ/EN. |

## 2. Nima yo'q va nima uchun (ochiq aytamiz)

* **Bot butun yozishmalar tarixini o'qimaydi** — Telegram faqat ulangandan keyingi yangi xabarlarni yuboradi.
* **Suhbatdosh 24 soatdan beri yozmagan chatga bot javob bera olmaydi** — Telegram cheklovi (`BUSINESS_PEER_USAGE_MISSING`); bunda natija sizga bot bilan shaxsiy chatda keladi.
* **Guruhlar va kanallar** — Business Mode faqat shaxsiy chatlarda ishlaydi.
* **«Onlayn» holatini** soxtalashtirib yoki yashirib bo'lmaydi — Bot API ruxsat bermaydi.
* **Stars / sovg'alarni o'tkazish** ataylab qilinmagan. Bunday huquqlar berilgan bo'lsa, huquq inspektori ogohlantiradi.
* Soxta statistika, soxta muvaffaqiyatli to'lov va soxta «onlayn» yo'q.

## 3. Tez boshlash (Android 14, Termux)

Batafsil — [INSTALL_ANDROID.md](INSTALL_ANDROID.md). Qisqacha:

```bash
# 1. Termux'ni F-Droid yoki GitHub'dan o'rnating (Google Play'dan emas)
pkg update -y && pkg install -y git
# 2. Chat_helper_FULL_PROJECT.zip arxivini ~/Chat_helper ga oching (yoki git clone)
cd ~/Chat_helper
bash scripts/install_termux.sh        # paketlar, Python kutubxonalari, .env, baza, testlar
nano backend/.env                     # BOT_TOKEN=... (@BotFather'dan)
./scripts/start.sh                    # bot + API fon rejimida (tmux)
./scripts/status.sh                   # tekshirish
```

Keyin — [OWNER_SETUP.md](OWNER_SETUP.md): botda Business Mode'ni yoqish, Telegram'da botni ulash (Sozlamalar → Telegram Business → Chat-botlar), `/start`, `/app` orqali kod olish, ilovaga kirish.

## 4. Boshqarish skriptlari

| Skript | Vazifasi |
|---|---|
| `scripts/install_termux.sh` | Noldan o'rnatish (qayta ishga tushirish xavfsiz) |
| `scripts/start.sh` | tmux (yoki nohup) da ishga tushirish, `termux-wake-lock` |
| `scripts/stop.sh` | To'g'ri to'xtatish |
| `scripts/restart.sh` | Qayta ishga tushirish |
| `scripts/status.sh` | Jarayon, `/api/v1/health`, xotira, disk, oxirgi loglar |
| `scripts/run_tests.sh` | Barcha backend testlari (pytest) |
| `scripts/backup.sh [--shared]` | Bazaning onlayn zaxira nusxasi |
| `scripts/restore.sh [fayl]` | Nusxalar ro'yxati / tiklash (to'xtatish → joriy baza nusxasi → tiklash → ishga tushirish) |
| `scripts/run_android_tests.sh` | APK yig'ish + Robolectric testlari (kompyuter/CI uchun) |

## 5. Sozlamalar

Barcha sozlamalar `backend/.env` faylida (shablon: `backend/.env.example`):

* `BOT_TOKEN` — faqat shu yerda. Token APK, loglar, hujjatlar va testlarga tushmaydi.
* `SUPER_ADMIN_ID=8053614984` — bosh administrator. Identifikatsiya faqat Telegram ID bo'yicha; `@libPM` username — ma'lumot uchun.
* `API_HOST=127.0.0.1`, `API_PORT=8787` — API faqat telefonning o'zida tinglaydi. Masofaviy kirish faqat aniq yoqilganda (`API_REMOTE_ENABLED=true` + HTTPS), qarang [SECURITY.md](SECURITY.md).
* `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `COMPAT_*` — ixtiyoriy.
* `PAYMENTS_ENABLED=false` — tariflarni sozlamaguningizcha Stars to'lovi o'chiq.

## 6. Hujjatlar

| Fayl | Mazmuni |
|---|---|
| [OWNER_SETUP.md](OWNER_SETUP.md) | Egasini sozlash (RU + UZ) |
| [INSTALL_ANDROID.md](INSTALL_ANDROID.md) | Termux, avtoishga tushirish, batareya; APK o'rnatish va yig'ish |
| [COMMANDS.md](COMMANDS.md) | Barcha buyruqlar (RU + UZ tavsif) |
| [API.md](API.md) | Barcha endpointlar |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arxitektura |
| [SECURITY.md](SECURITY.md) | Xavfsizlik hisoboti |
| [FEATURE_MATRIX.md](FEATURE_MATRIX.md) | Har bir funksiya holati |
| [TEST_REPORT.md](TEST_REPORT.md) | Haqiqiy test natijalari |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Muammolar va yechimlar |

Hujjatlarning bir qismi (arxitektura, xavfsizlik, testlar) rus tilida; asosiy foydalanuvchi qismi — buyruqlar, panel va ilova — to'liq o'zbek tilida mavjud.
