# Chat helper v3 — qo'llanma (UZ)

**Chat helper** — **Telegram Business** («Chatlarni avtomatlashtirish», rasmiy Bot API) uchun bot va uni boshqarish uchun
**Chat helper Control** ilovasi. Bot va API **bitta Android telefonda, Termux ichida** ishlaydi (Android 14, ARM64, Python 3.13):
kompyuter, VPS, root va Docker kerak emas; yangilanishlar — long polling.

> Ruscha versiya: [README_RU.md](README_RU.md) · Buyruqlar: [COMMANDS.md](COMMANDS.md) · API: [API.md](API.md) ·
> Funksiyalar holati: [FEATURE_MATRIX.md](FEATURE_MATRIX.md) · Test natijalari: [TEST_REPORT.md](TEST_REPORT.md)

## 1. v3 da asosiy yangiliklar

* **Ulanmaguncha — funksiyalar yopiq.** Bot «Chatlarni avtomatlashtirish»ga ulanmaguncha faqat `/start`, `/help`, `/connect`,
  ulanishni tekshirish, yo'riqnoma, til va qo'llab-quvvatlash ishlaydi. RU/UZ infografikali yangi ulash ustasi.
  **Telegram Premium shart emas.**
* **Chatdagi boshqaruv kartalari** — `.mute`, `.protect`, `.nogif`, `.nomute`, `.afk`, `.re`… tugmali xabar bilan javob beradi;
  tugmalarni faqat egasi bosa oladi ([CHAT_CONTROLS.md](CHAT_CONTROLS.md), ruscha).
* **Haqiqiy Mute:** yangi kiruvchi xabarlarni `deleteBusinessMessages` orqali o'chirish («Kiruvchilarni o'chirish» huquqi),
  tasdiq, 10 daq / 1 soat / 1 kun taymerlari, turlar, oq ro'yxat, hisobot.
* **Animatsiyalar** (`.a`, 16 tur, 4 tezlik), **`.re`** (har 5 soniyada takrorlash, 2 daqiqagacha), **`.r`** (o'ngdan chapga matn),
  `.sum`, `.ball`, `.morse`, `.ptext` (rasmdagi matn: ru/uz/en), `.remind`/`.remindf`, `.qr`, `.info`, `.gif`, `.wtm`, `.geo`, `.g`…
* **AI**: `.ai` (`.gpt` taxallusi), **AI egizak** — sizning uslubingizda javob beradi, faqat o'zingiz qo'shgan misollardan
  o'rganadi, javoblar «🤖 AI» deb belgilanadi; Auto / Manual / Draft / Disabled rejimlari.
* **Yagona administrator** — Super Admin (`SUPER_ADMIN_ID`). Boshqalar uchun admin bo'limi **umuman yo'q**: tugma ham, buyruq ham
  ko'rinmaydi, API esa mavjud bo'lmagan manzil kabi javob beradi.
* **To'liq RU/UZ tarjima** — bot va ilova o'zbek tilida ruscha qo'shimchalarsiz ishlaydi.
* **Yangi Chat helper Control v3 ilovasi** (Flutter): 40 ta ekran, «liquid glass» dizayn.

## 2. Imkoniyatlar

| Modul | Qisqacha |
|---|---|
| Business dvigateli | `business_connection`, `business_message`, tahrirlar, o'chirishlar, `BusinessBotRights` huquqlari, sikl va dublikatlardan himoya |
| Buyruqlar | `.` prefiksli 160 ta buyruq (`!` `-` `,` ga o'zgartirish mumkin); sintaksis inglizcha, tavsif va natijalar — sizning tilingizda |
| Boshqaruv kartalari | faqat egasi uchun tugmalar, eskirgan bosishlardan himoya, bir martalik bajarilish |
| Mute / Protect / NoGIF / NoMute | qoidalar bo'yicha kiruvchilarni o'chirish, uzatishdan himoya, so'z filtri |
| AFK va avtojavob | `.afk`, tungi rejim, Manual/Auto/AI/AFK/Silent/Business/Hybrid rejimlari, ish vaqti, qoidalar |
| AI | OpenAI / Gemini / Anthropic / OpenAI-mos, byudjetlar, roziligingiz bilan xotira, qoralamalar, `.sum`, `.hint`, AI egizak |
| Media / Voice Studio | dumaloq video, ovozli, GIF (15 soniyagacha), suv belgisi, teskari, tezlik, memlar, stikerlar, STT/TTS |
| O'yinlar va matn vositalari | duel, viktorina, tosh-qaychi-qog'oz…; `eval`siz kalkulyator, `.fix`, Morze, QR, parollar |
| Avtomatlashtirish | kodsiz «trigger → shartlar → amallar», shablonlar (egasining tilida), tekshiruv, jurnal |
| Eslatmalar | `.remind` (sizga shaxsiy chatda), `.remindf` (chatga); qayta ishga tushirishdan keyin ham saqlanadi |
| Obunalar | Free / Plus / Pro / VIP, promokodlar, sinov, Telegram Stars (standart holatda o'chiq) |
| Delegatsiya | administrator yordamiga ixtiyoriy ruxsat, istalgan vaqtda bekor qilinadi |
| API | FastAPI `127.0.0.1:8787`, 159 ta endpoint, serverda huquq tekshiruvi |

## 3. Nima yo'q va nima uchun

* «Tarmoqda» holatini Bot API orqali soxtalashtirib ham, yashirib ham bo'lmaydi — `.online` buni ochiq aytadi.
* Ulanishdan oldingi tarix, guruhlar va kanallar biznes botga mavjud emas.
* Suhbatdosh oxirgi 24 soatda yozgan bo'lsagina chatga javob berish mumkin — aks holda natija sizga shaxsiy chatda keladi.
* Stars/sovg'alarni o'tkazish ataylab qilinmagan. Soxta statistika, «onlayn» va «muvaffaqiyatli» to'lovlar yo'q.

## 4. Tez boshlash

```bash
cd ~ && unzip /sdcard/Download/Chat_helper_v3_FULL_PROJECT.zip && cd ~/Chat_helper
bash scripts/install_termux.sh
nano backend/.env            # BOT_TOKEN=..., SUPER_ADMIN_ID=raqamli_id
./scripts/start.sh && ./scripts/status.sh
```

Keyin Telegram'da: botni ulang (Sozlamalar → profilni Tahrirlash → «Chatlarni avtomatlashtirish»), `/start` → ulanishni tekshiring,
`/app` → ilova uchun kod. v1 dan yangilash: `./scripts/backup.sh && ./scripts/stop.sh`, arxivni ustidan oching, `./scripts/start.sh` —
baza o'zi yangilanadi (oldin zaxira nusxa olinadi). Botni to'xtatish: `./scripts/stop.sh`.

## 5. Ilova (Chat helper Control v3)

1. `Chat_helper_Control_v3.apk` ni GitHub Actions'dan yuklab oling (Actions → «Flutter APK (v3)» → Artifacts).
2. Eski v1 ilova o'rnatilgan bo'lsa va Android «ilova o'rnatilmadi» desa — uni o'chiring (unda faqat sessiya bor).
3. Ilovada «Ilovani ulash» → botga `/app` yuboring → kodni kiriting. Server: `http://127.0.0.1:8787`.

## 6. Hujjatlar (ruscha)

[INSTALL_TERMUX.md](INSTALL_TERMUX.md) · [TELEGRAM_BUSINESS.md](TELEGRAM_BUSINESS.md) · [CHAT_CONTROLS.md](CHAT_CONTROLS.md) ·
[PERMISSIONS.md](PERMISSIONS.md) · [LOCALIZATION.md](LOCALIZATION.md) · [ADMIN_SECURITY.md](ADMIN_SECURITY.md) ·
[MIGRATION_V1_TO_V3.md](MIGRATION_V1_TO_V3.md) · [BUILD_FLUTTER.md](BUILD_FLUTTER.md) · [FIGMA_DESIGN.md](FIGMA_DESIGN.md) ·
[FEATURE_MATRIX.md](FEATURE_MATRIX.md) · [TEST_REPORT.md](TEST_REPORT.md)
