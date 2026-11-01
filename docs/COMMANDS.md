# Chat helper — команды / buyruqlar

> Файл сгенерирован автоматически из Command Registry (`backend/tools/gen_docs.py`). Всего команд: **160**. Префикс по умолчанию `.` (меняется в настройках: `.` `!` `-` `,`).

Команды выполняет **только владелец** бизнес-аккаунта: в любом подключённом чате или в личном чате с ботом. Пробел после префикса допустим (`. afk`), регистр не важен, у команд есть русские/узбекские алиасы.

## 💤 AFK / AFK

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.afk`<br><sub>.афк, .away</sub> | Включить режим «нет на месте» с причиной и таймером; status / time / off | «Joyida yo'q» rejimini sabab va taymer bilan yoqish; status / time / off | `.afk [время] [причина] | .afk status | .afk time | .afk off` | `.afk Занят делами` | ✅ реализовано | free; — |
| `.sleep`<br><sub>.сон, .спать, .uyqu</sub> | Ночной режим: AFK с ночным шаблоном до указанного времени | Tungi rejim: belgilangan vaqtgacha tungi AFK | `.sleep [ЧЧ:ММ]` | `.sleep` | ✅ реализовано | free; — |
| `.unafk`<br><sub>.анафк, .back, .вернулся</sub> | Выключить AFK и получить сводку пропущенного | AFK'ni o'chirish va o'tkazib yuborilganlar xulosasi | `.unafk` | `.unafk` | ✅ реализовано | free; — |

## 🧠 AI-ассистент / AI yordamchi

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.ai`<br><sub>.gpt, .ask, .гпт, .спроси</sub> | Задать вопрос AI (можно ответом на сообщение — оно станет контекстом) | AI'ga savol berish (xabarga javob sifatida — u kontekst bo'ladi) | `.gpt вопрос` | `.gpt Придумай название для кофейни` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.analyze`<br><sub>.анализ, .tahlil</sub> | Анализ сообщения: намерение, тон, срочность (видите только вы) | Xabar tahlili: maqsad, ohang, shoshilinchlik (faqat siz ko'rasiz) | `.analyze (ответом на сообщение)` | `.analyze` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.code`<br><sub>.код, .kod</sub> | Помощь с программированием | Dasturlash bo'yicha yordam | `.code задача` | `.code функция на Python для проверки палиндрома` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.context`<br><sub>.контекст</sub> | Сколько контекста AI хранится для этого чата | Bu chat uchun AI qancha kontekst saqlaydi | `.context` | `.context` | ✅ реализовано | free; — |
| `.explain`<br><sub>.объясни, .tushuntir</sub> | Объяснить простыми словами | Oddiy so'zlar bilan tushuntirish | `.explain [текст]` | `.explain квантовая запутанность` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.forget`<br><sub>.забудь, .unut</sub> | Удалить факт(ы) из памяти AI: ID, текст или all | AI xotirasidan fakt(lar)ni o'chirish: ID, matn yoki all | `.forget ID|текст|all` | `.forget 3` | ✅ реализовано | free; — |
| `.grammar`<br><sub>.грамматика, .imlo</sub> | Проверка грамматики с объяснением исправлений | Grammatikani tekshirish va tuzatishlarni tushuntirish | `.grammar текст` | `.grammar I has a apple` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.hint`<br><sub>.подсказка, .варианты, .maslahat</sub> | 3 варианта ответа на сообщение — придут вам в личку с кнопками «Отправить» | Xabarga 3 ta javob varianti — shaxsiy chatga «Yuborish» tugmalari bilan keladi | `.hint (ответом на сообщение)` | `.hint` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.prompt`<br><sub>.промпт</sub> | Показать или задать свой системный prompt для AI (reset — сброс) | AI uchun shaxsiy system prompt'ni ko'rish yoki o'rnatish (reset — tiklash) | `.prompt [текст|reset]` | `.prompt Отвечай как вежливый менеджер студии` | ✅ реализовано | free; — |
| `.remember`<br><sub>.запомни, .eslab</sub> | Сохранить факт о себе для AI (долгосрочная память, с вашего согласия) | AI uchun o'zingiz haqingizda faktni saqlash (uzoq xotira, roziligingiz bilan) | `.remember факт` | `.remember Я работаю дизайнером, офис открыт с 10 до 19` | ✅ реализовано | free; — |
| `.resetai`<br><sub>.сбросии, .aireset</sub> | Очистить AI-контекст этого чата | Bu chatning AI kontekstini tozalash | `.resetai` | `.resetai` | ✅ реализовано | free; — |
| `.rewrite`<br><sub>.перефразируй, .rw, .qaytayoz</sub> | Переписать текст в нужном стиле: formal, friendly, short, funny, polite | Matnni uslubda qayta yozish: formal, friendly, short, funny, polite | `.rewrite [стиль] текст` | `.rewrite formal привет, скинь отчёт` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.smart`<br><sub>.умно, .aqlli</sub> | AI пишет ответ вашим голосом и вставляет его вместо команды | AI sizning nomingizdan javob yozadi va buyruq o'rniga qo'yadi | `.smart (ответом на сообщение) [подсказка]` | `.smart` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.sum`<br><sub>.пересказ, .qaytaaytish</sub> | AI-пересказ последних 10–100 сообщений этого чата: темы, договорённости, вопросы, задачи — вам в личку | Ushbu chatning so'nggi 10–100 xabari AI-xulosasi: mavzular, kelishuvlar, savollar, vazifalar — shaxsiy chatga | `.sum [10–100]` | `.sum` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.summary`<br><sub>.кратко, .резюме, .xulosa</sub> | Краткое содержание текста, сообщения-ответа или недавней переписки чата | Matn, javob xabari yoki so'nggi suhbatning qisqacha mazmuni | `.summary [текст]` | `.summary (ответом на длинное сообщение)` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.translate`<br><sub>.tr, .перевод, .переведи, .tarjima</sub> | Перевести текст или сообщение-ответ на язык (en, ru, uz, tr, de…) | Matn yoki javob xabarini tarjima qilish (en, ru, uz, tr, de…) | `.translate [язык] [текст]` | `.translate en Привет, как дела?` | 🔑 нужен AI-ключ | free; — · deps: ai |
| `.twin`<br><sub>.двойник, .egizak</sub> | AI-двойник: настройки в личке; auto | manual | draft | off — режим; learn — добавить пример вашего стиля; forget — удалить примеры | AI-egizak: sozlamalar shaxsiy chatda; auto | manual | draft | off — rejim; learn — uslubingiz namunasini qo'shish; forget — o'chirish | `.twin [auto|manual|draft|off] | .twin learn [текст или ответом на ВАШЕ сообщение] | .twin forget` | `.twin` | ✅ реализовано | free; — |
| `.vision`<br><sub>.зрение, .фото, .rasm</sub> | Описать фото или ответить на вопрос о нём | Rasmni tasvirlash yoki u haqida savolga javob | `.vision [вопрос] (ответом на фото)` | `.vision` | 🔑 нужен AI-ключ | free; — · deps: ai |

## 🎙 Voice Studio / Voice Studio

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.denoise`<br><sub>.шумодав, .clean</sub> | Очистка аудио от шума (FFT-шумоподавление) | Audioni shovqindan tozalash | `.denoise` | `.denoise` | ✅ реализовано | free; — · deps: ffmpeg |
| `.extract`<br><sub>.извлечь, .голосизвидео</sub> | Извлечь голос из видео в голосовое сообщение | Videodan ovozni ovozli xabar sifatida ajratish | `.extract (ответом на видео)` | `.extract` | ✅ реализовано | free; — · deps: ffmpeg |
| `.stt`<br><sub>.текст, .расшифруй, .v2t, .matn</sub> | Голосовое/кружок/видео → текст (Speech-to-Text) | Ovozli/dumaloq/video → matn (Speech-to-Text) | `.stt (ответом на голосовое)` | `.stt` | 🔑 нужен AI-ключ | free; — · deps: ai_stt |
| `.tts`<br><sub>.say, .скажи, .озвучь, .ayt</sub> | Текст → голосовое (OpenAI TTS или офлайн espeak-ng, если установлен) | Matn → ovozli xabar (OpenAI TTS yoki o'rnatilgan bo'lsa oflayn espeak-ng) | `.tts текст` | `.tts Привет! Перезвоню через 5 минут` | ✅ реализовано | free; — |
| `.voice`<br><sub>.голосовое, .войс, .ovozli</sub> | Сделать голосовое из аудио/видео | Audio/videodan ovozli xabar | `.voice` | `.voice` | ✅ реализовано | free; — · deps: ffmpeg |
| `.vreply`<br><sub>.ответголос</sub> | AI-ответ на голосовое сообщение (черновик вам в личку) | Ovozli xabarga AI javobi (qoralama shaxsiy chatga) | `.vreply (ответом на голосовое)` | `.vreply` | 🔑 нужен AI-ключ | free; — · deps: ai_stt, ai |
| `.vtranslate`<br><sub>.перевестиголос, .vtr</sub> | Перевод голосового сообщения | Ovozli xabarni tarjima qilish | `.vtranslate [язык] (ответом на голосовое)` | `.vtranslate en` | 🔑 нужен AI-ключ | free; — · deps: ai_stt, ai |

## 🎬 Media Studio / Media Studio

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.blur`<br><sub>.размыть, .xira</sub> | Размытие (радиус 1–60, по умолчанию 8) | Xiralashtirish (radius 1–60) | `.blur [радиус]` | `.blur` | ✅ реализовано | free; — |
| `.brightness`<br><sub>.яркость, .yorqinlik</sub> | Яркость: коэффициент 0–5 (1 = без изменений) | Yorqinlik: koeffitsient 0–5 | `.brightness [коэф.]` | `.brightness 1.3` | ✅ реализовано | free; — |
| `.bw`<br><sub>.чб, .oq_qora</sub> | Чёрно-белое фото | Oq-qora rasm | `.bw` | `.bw` | ✅ реализовано | free; — |
| `.cancel`<br><sub>.отмена, .bekor</sub> | Отменить медиа-задачу (последнюю или по ID) | Media vazifani bekor qilish | `.cancel [ID]` | `.cancel` | ✅ реализовано | free; — |
| `.caption`<br><sub>.подпись, .izoh</sub> | Изменить подпись вашего медиа-сообщения (ответом на него) | Media xabaringiz izohini o'zgartirish (unga javob sifatida) | `.caption текст | .caption -` | `.caption Новый текст` | ✅ реализовано | free; can_reply |
| `.circle`<br><sub>.кружок, .note, .dumaloq</sub> | Сделать видеокружок из видео (до 60 с) | Videodan dumaloq video (60 s gacha) | `.circle` | `.circle` | ✅ реализовано | free; — · deps: ffmpeg |
| `.compress`<br><sub>.сжать, .siqish</sub> | Сжать фото/видео/аудио (уровень 1–3) | Rasm/video/audioni siqish (1–3 daraja) | `.compress [1-3]` | `.compress` | ✅ реализовано | free; — · deps: ffmpeg |
| `.contrast`<br><sub>.контраст, .kontrast</sub> | Контраст: коэффициент 0–5 (1 = без изменений) | Kontrast: koeffitsient 0–5 | `.contrast [коэф.]` | `.contrast 1.4` | ✅ реализовано | free; — |
| `.convert`<br><sub>.конверт, .конвертировать</sub> | Конвертировать формат: png/jpg/webp/bmp/gif/ico/pdf, mp3/ogg/wav/m4a/flac, mp4/webm/gif | Formatni o'zgartirish: png/jpg/webp/…, mp3/ogg/wav/…, mp4/webm/gif | `.convert формат` | `.convert png` | ✅ реализовано | free; — · deps: ffmpeg |
| `.crop`<br><sub>.кроп, .qirqish</sub> | Обрезать: пропорция 1:1, 16:9 или x,y,w,h | Qirqish: nisbat 1:1, 16:9 yoki x,y,w,h | `.crop 1:1 | .crop x,y,w,h` | `.crop 1:1` | ✅ реализовано | free; — |
| `.finfo`<br><sub>.fileinfo, .медиаинфо, .meta</sub> | Метаданные файла (формат, размер, длительность, кодеки) | Fayl metama'lumotlari | `.finfo (ответом на медиа)` | `.finfo` | ✅ реализовано | free; — |
| `.gif`<br><sub>.гиф</sub> | Фото или видео (до 15 с) → GIF-анимация без звука | Rasm yoki video (15 s gacha) → ovozsiz GIF animatsiya | `.gif (ответом на фото или видео)` | `.gif` | ✅ реализовано | free; — |
| `.ld`<br><sub>.volume, .громкость, .loud, .ovoz</sub> | Усилить громкость: 0–100 (по умолчанию 25). Шкала: +0.3 дБ за шаг → 25 = +7.5 дБ (×2.4), 100 = +30 дБ | Ovoz balandligini oshirish: 0–100 (standart 25). Shkala: har qadam +0.3 dB → 25 = +7.5 dB, 100 = +30 dB | `.ld [0-100]` | `.ld` | ✅ реализовано | free; — · deps: ffmpeg |
| `.meme`<br><sub>.мем</sub> | Мем с текстом сверху/снизу | Yuqori/pastki matnli mem | `.meme текст | .meme up текст | .meme down текст | .meme up верх | down низ` | `.meme Когда код заработал` | ✅ реализовано | free; — |
| `.merge`<br><sub>.склеить, .birlashtir</sub> | Склеить файлы: ответьте .merge на каждый файл, затем .merge done (clear — очистить) | Fayllarni birlashtirish: har bir faylga .merge, so'ng .merge done (clear — tozalash) | `.merge | .merge done | .merge clear` | `.merge` | ✅ реализовано | free; — · deps: ffmpeg |
| `.mirror`<br><sub>.зеркало, .ko'zgu</sub> | Отражение: h — горизонтально, v — вертикально | Aks: h — gorizontal, v — vertikal | `.mirror [h|v]` | `.mirror` | ✅ реализовано | free; — |
| `.mp3`<br><sub>.мп3, .audio</sub> | Извлечь звук в MP3 | Ovozni MP3 ga ajratish | `.mp3` | `.mp3` | ✅ реализовано | free; — · deps: ffmpeg |
| `.noise`<br><sub>.шум, .shovqin</sub> | Эффект шума/зерна для фото (1–100) | Rasm uchun shovqin effekti (1–100) | `.noise [сила]` | `.noise` | ✅ реализовано | free; — |
| `.normalize`<br><sub>.норм, .нормализация</sub> | Нормализация громкости (EBU R128) | Ovozni normallashtirish (EBU R128) | `.normalize` | `.normalize` | ✅ реализовано | free; — · deps: ffmpeg |
| `.pixel`<br><sub>.пиксель, .pixelate</sub> | Пикселизация (блок 2–100) | Pikselizatsiya (blok 2–100) | `.pixel [размер]` | `.pixel` | ✅ реализовано | free; — |
| `.ptext`<br><sub>.ocr, .текстсфото, .matnrasm</sub> | Распознать текст на фото (русский, узбекский, английский): офлайн tesseract или AI-зрение | Rasmdagi matnni aniqlash (rus, o'zbek, ingliz): oflayn tesseract yoki AI ko'rish | `.ptext (ответом на фото)` | `.ptext` | ✅ реализовано | free; — |
| `.ramka`<br><sub>.рамка, .frame, .ramka_</sub> | Дизайнерская рамка: gold, luxury, diamond, neon, cyber, glass, minimal | Dizayner ramka: gold, luxury, diamond, neon, cyber, glass, minimal | `.ramka [стиль]` | `.ramka gold` | ✅ реализовано | free; — |
| `.resize`<br><sub>.размер, .o'lcham</sub> | Изменить размер: 800, 800x600, x600, 50% | O'lchamni o'zgartirish: 800, 800x600, 50% | `.resize размер` | `.resize 1080` | ✅ реализовано | free; — |
| `.reverse`<br><sub>.реверс, .задомнаперёд, .teskari</sub> | Развернуть голосовое, аудио, видео или кружок задом наперёд (тип сохраняется) | Ovozli, audio, video yoki dumaloq videoni teskari aylantirish (turi saqlanadi) | `.reverse (ответом на медиа)` | `.reverse` | ✅ реализовано | free; — · deps: ffmpeg |
| `.rotate`<br><sub>.повернуть, .aylantir</sub> | Повернуть по часовой (по умолчанию 90°) | Soat yo'nalishida burish (90°) | `.rotate [градусы]` | `.rotate` | ✅ реализовано | free; — |
| `.sepia`<br><sub>.сепия</sub> | Эффект сепии | Sepiya effekti | `.sepia` | `.sepia` | ✅ реализовано | free; — |
| `.sharpen`<br><sub>.резкость, .aniqlik</sub> | Повысить резкость (0.1–5) | Aniqlikni oshirish (0.1–5) | `.sharpen [сила]` | `.sharpen` | ✅ реализовано | free; — |
| `.speed`<br><sub>.скорость, .tezlik</sub> | Изменить скорость медиа: 0.25x–5x (без числа — кнопки выбора) | Media tezligini o'zgartirish: 0.25x–5x (raqamsiz — tugmalar) | `.speed [0.25|0.5|0.75|1.25|1.5|2|3|4|5]` | `.speed 2` | ✅ реализовано | free; — · deps: ffmpeg |
| `.sticker`<br><sub>.стикер, .stiker</sub> | Сделать стикер из картинки (512 px WEBP) | Rasmdan stiker (512 px WEBP) | `.sticker` | `.sticker` | ✅ реализовано | free; — |
| `.trim`<br><sub>.обрезать, .kesish</sub> | Обрезать аудио/видео по времени | Audio/videoni vaqt bo'yicha kesish | `.trim начало [конец]` | `.trim 0:05 0:20` | ✅ реализовано | free; — · deps: ffmpeg |
| `.watermark`<br><sub>.вотермарк, .водянойзнак, .wm, .wtm</sub> | Водяной знак на фото, видео или кружок (позиция: br, bl, tr, tl, c) | Rasm, video yoki dumaloq videoga suv belgisi (joylashuv: br, bl, tr, tl, c) | `.wtm [позиция] текст` | `.wtm © Мой бренд` | ✅ реализовано | free; — |

## 🎮 Игры / O'yinlar

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.challenge`<br><sub>.вызов, .chaqiruv</sub> | Случайный вызов: бот выбирает игру за вас | Tasodifiy chaqiruv: bot o'yinni tanlaydi | `.challenge` | `.challenge` | ✅ реализовано | free; can_reply |
| `.coin`<br><sub>.монетка, .монета, .tanga</sub> | Подбросить монетку | Tanga tashlash | `.coin` | `.coin` | ✅ реализовано | free; — |
| `.dice`<br><sub>.кубик, .кости, .zar</sub> | Бросить кубик Telegram (🎲 🎯 🏀 ⚽ 🎳) | Telegram zarini tashlash (🎲 🎯 🏀 ⚽ 🎳) | `.dice [🎲|🎯|🏀|⚽|🎳]` | `.dice` | ✅ реализовано | free; can_reply |
| `.duel`<br><sub>.дуэль, .duel_</sub> | Дуэль на реакцию: приглашение, фальстарт, время реакции, рейтинг | Reaksiya dueli: taklif, fal'start, reaksiya vaqti, reyting | `.duel` | `.duel` | ✅ реализовано | free; can_reply |
| `.guess`<br><sub>.угадай, .top</sub> | Угадай число (подсказки больше/меньше) | Sonni top (kattaroq/kichikroq maslahatlari) | `.guess` | `.guess 100` | ✅ реализовано | free; can_reply |
| `.mathgame`<br><sub>.математика, .matematika</sub> | Кто быстрее решит пример | Kim misolni tezroq yechadi | `.mathgame` | `.mathgame` | ✅ реализовано | free; can_reply |
| `.quiz`<br><sub>.викторина, .viktorina</sub> | Викторина: кто первым ответит правильно | Viktorina: kim birinchi to'g'ri javob beradi | `.quiz` | `.quiz` | ✅ реализовано | free; can_reply |
| `.rd`<br><sub>.рандом, .random_choice, .tasodif</sub> | Случайное число или выбор: .rd, .rd 50, .rd 10 20, .rd чай | кофе | Tasodifiy son yoki tanlov: .rd, .rd 50, .rd 10 20, .rd choy | qahva | `.rd [макс | мин макс | вариант | вариант]` | `.rd` | ✅ реализовано | free; — |
| `.reaction`<br><sub>.реакция, .reaksiya</sub> | Тест реакции для обоих игроков | Ikkala o'yinchi uchun reaksiya testi | `.reaction` | `.reaction` | ✅ реализовано | free; can_reply |
| `.revo`<br><sub>.рулетка, .ruletka</sub> | Виртуальная русская рулетка: 6 камер, пошагово, без ставок | Virtual rus ruletkasi: 6 kamera, navbat bilan, garovsiz | `.revo` | `.revo` | ✅ реализовано | free; can_reply |
| `.rps`<br><sub>.кнб, .камень, .tqq</sub> | Камень-ножницы-бумага с тайным выбором | Tosh-qaychi-qog'oz yashirin tanlov bilan | `.rps` | `.rps` | ✅ реализовано | free; can_reply |
| `.slot`<br><sub>.слот, .казино</sub> | Слот-машина Telegram 🎰 (без ставок) | Telegram slot-mashinasi 🎰 (garovsiz) | `.slot` | `.slot` | ✅ реализовано | free; can_reply |
| `.ttt`<br><sub>.крестики, .xo, .tictactoe</sub> | Крестики-нолики (с собеседником или с ботом) | X-O (suhbatdosh yoki bot bilan) | `.ttt` | `.ttt` | ✅ реализовано | free; can_reply |
| `.wordgame`<br><sub>.слова, .so'zlar</sub> | Игра в слова: на последнюю букву | So'z o'yini: oxirgi harfga | `.wordgame` | `.wordgame` | ✅ реализовано | free; can_reply |

## ⌨️ Текстовые инструменты / Matn vositalari

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.ball`<br><sub>.шар, .8ball, .shar</sub> | Магический шар: случайный ответ на вопрос (для развлечения) | Sehrli shar: savolga tasodifiy javob (ko'ngilochar) | `.ball [вопрос]` | `.ball Пойти сегодня в кино?` | ✅ реализовано | free; — |
| `.base64`<br><sub>.b64</sub> | Кодировать в Base64 | Base64 ga kodlash | `.base64 текст` | `.base64 hello` | ✅ реализовано | free; — |
| `.binary`<br><sub>.бин, .bin</sub> | Текст ↔ двоичный код (автоопределение) | Matn ↔ ikkilik kod (avto) | `.binary текст | 01101000…` | `.binary hi` | ✅ реализовано | free; — |
| `.bubble`<br><sub>.пузыри, .kopik</sub> | Текст в кружочках ⓑⓤⓑⓑⓛⓔ | Doiradagi matn ⓑⓤⓑⓑⓛⓔ | `.bubble текст` | `.bubble hello` | ✅ реализовано | free; — |
| `.calc`<br><sub>.калк, .счёт, .посчитай, .hisob</sub> | Калькулятор (безопасный парсер): + − × ÷ ^ % ! sqrt sin log pi… | Kalkulyator (xavfsiz tahlilchi): + − × ÷ ^ % ! sqrt sin log pi… | `.calc выражение` | `.calc 2+2*2` | ✅ реализовано | free; — |
| `.count`<br><sub>.счётчик, .sanash</sub> | Статистика текста: символы, слова, строки, время чтения | Matn statistikasi | `.count текст | (ответом)` | `.count` | ✅ реализовано | free; — |
| `.date`<br><sub>.дата, .sana</sub> | Сегодняшняя дата и день недели | Bugungi sana va hafta kuni | `.date [часовой пояс]` | `.date` | ✅ реализовано | free; — |
| `.emoji`<br><sub>.эмодзи, .emodzi</sub> | Добавить эмодзи к словам (или случайный эмодзи) | So'zlarga emoji qo'shish (yoki tasodifiy) | `.emoji [текст]` | `.emoji люблю кофе и музыку` | ✅ реализовано | free; — |
| `.fix`<br><sub>.исправь, .fixit, .tuzat</sub> | Исправить опечатки, раскладку (ghbdtn → привет), Caps Lock, растянутые буквы. Неоднозначное — только с подтверждения | Xatolar, klaviatura (ghbdtn → привет), Caps Lock'ni tuzatish. Noaniq bo'lsa — faqat tasdiq bilan | `.fix текст | .fix (ответом) | .fix ai текст` | `.fix ghbdtn rfr ltkf` | ✅ реализовано | free; — |
| `.format`<br><sub>.формат, .fmt</sub> | Форматирование: b, i, u, s, code, spoiler, quote | Formatlash: b, i, u, s, code, spoiler, quote | `.format стиль текст` | `.format b Важно!` | ✅ реализовано | free; — |
| `.geo`<br><sub>.гео, .карта, .xarita</sub> | Координаты и карты: точка → геометка и ссылки; две точки → расстояние; ответом на геопозицию → ссылки | Koordinatalar va xaritalar: nuqta → geobelgi va havolalar; ikki nuqta → masofa; geojoylashuvga javob → havolalar | `.geo широта, долгота [; широта2, долгота2]` | `.geo 41.3111, 69.2797` | ✅ реализовано | free; — |
| `.hash`<br><sub>.хэш, .хеш</sub> | Хэш текста: sha256 (по умолчанию), md5, sha1, sha512, blake2b | Matn xeshi | `.hash [алгоритм] текст` | `.hash hello` | ✅ реализовано | free; — |
| `.hex`<br><sub>.хекс</sub> | Текст ↔ HEX (автоопределение) | Matn ↔ HEX (avto) | `.hex текст | 68656c6c6f` | `.hex hello` | ✅ реализовано | free; — |
| `.json`<br><sub>.джсон</sub> | Проверить и красиво оформить JSON (min — сжать) | JSON'ni tekshirish va formatlash (min — siqish) | `.json [min] текст` | `.json {"a":1,"b":[1,2]}` | ✅ реализовано | free; — |
| `.leet`<br><sub>.лит, .1337</sub> | Текст в стиле l33t | Matnni l33t uslubida | `.leet текст` | `.leet hacker` | ✅ реализовано | free; — |
| `.lower`<br><sub>.низ, .kichik</sub> | нижний регистр | kichik harflar | `.lower текст` | `.lower ПРИВЕТ` | ✅ реализовано | free; — |
| `.morse`<br><sub>.морзе, .morze</sub> | Азбука Морзе: текст → код или код → текст (латиница, кириллица, цифры) | Morze alifbosi: matn → kod yoki kod → matn (lotin, kirill, raqamlar) | `.morse текст | .morse ... --- ... | .morse ru код` | `.morse SOS` | ✅ реализовано | free; — |
| `.normalize_text`<br><sub>.clean_text</sub> | Нормализовать Unicode (убрать «невидимые» символы) | Unicode'ni normallashtirish | `.normalize_text текст` | `.normalize_text ｔｅｘｔ` | ✅ реализовано | free; — |
| `.password`<br><sub>.пароль, .parol, .pass</sub> | Надёжный пароль (8–64, по умолчанию 16) — придёт вам в личку | Kuchli parol (8–64, standart 16) — shaxsiy chatga keladi | `.password [длина] [nosym]` | `.password` | ✅ реализовано | free; — |
| `.qr`<br><sub>.кьюар, .qrcode</sub> | QR-код из текста или ссылки; ответом на фото — распознать QR | Matn yoki havoladan QR-kod; rasmga javob — QR'ni o'qish | `.qr текст | .qr (ответом на фото с QR)` | `.qr https://t.me/libPM` | ✅ реализовано | free; — |
| `.r`<br><sub>.rtl, .справаналево, .o'ngdan</sub> | Текст справа налево (Unicode-безопасно: эмодзи и акценты не ломаются); rlo — направление через RLO-символ | O'ngdan chapga matn (Unicode xavfsiz: emoji va urg'ular buzilmaydi); rlo — RLO belgisi orqali yo'nalish | `.r текст | .r rlo текст` | `.r Привет 👋🏽` | ✅ реализовано | free; — |
| `.random`<br><sub>.случайно, .rand</sub> | Случайное: число, цвет, буква, да/нет | Tasodifiy: son, rang, harf, ha/yo'q | `.random [num min max|color|letter|yesno]` | `.random` | ✅ реализовано | free; — |
| `.repeat`<br><sub>.повтори, .takror</sub> | Повторить текст N раз (до 20) | Matnni N marta takrorlash (20 gacha) | `.repeat N текст` | `.repeat 3 ура!` | ✅ реализовано | free; — |
| `.reverse_text`<br><sub>.перевернуть, .rtext, .teskari_matn</sub> | Перевернуть текст задом наперёд | Matnni teskari qilish | `.reverse_text текст` | `.reverse_text привет` | ✅ реализовано | free; — |
| `.short`<br><sub>.сократить, .qisqa</sub> | Сократить ссылку (через is.gd / tinyurl — внешний сервис) | Havolani qisqartirish (is.gd / tinyurl orqali) | `.short ссылка` | `.short https://example.com/very/long/link` | ✅ реализовано | free; — · deps: network |
| `.time`<br><sub>.время, .vaqt</sub> | Текущее время (можно указать город/пояс) | Joriy vaqt (shahar/mintaqa ko'rsatish mumkin) | `.time [пояс]` | `.time` | ✅ реализовано | free; — |
| `.timestamp`<br><sub>.unix, .ts</sub> | Unix-время: сейчас, из числа в дату или из даты в число | Unix vaqt: hozir, son↔sana | `.timestamp [число | ГГГГ-ММ-ДД ЧЧ:ММ]` | `.timestamp` | ✅ реализовано | free; — |
| `.title`<br><sub>.заглавные, .sarlavha</sub> | Каждое Слово С Большой Буквы | Har So'z Katta Harf Bilan | `.title текст` | `.title привет мир` | ✅ реализовано | free; — |
| `.unbase64`<br><sub>.ub64, .debase64</sub> | Декодировать Base64 | Base64 ni dekodlash | `.unbase64 строка` | `.unbase64 aGVsbG8=` | ✅ реализовано | free; — |
| `.upper`<br><sub>.верх, .katta</sub> | ВЕРХНИЙ РЕГИСТР | KATTA HARFLAR | `.upper текст` | `.upper привет` | ✅ реализовано | free; — |
| `.urldecode`<br><sub>.urldec</sub> | URL-декодирование | URL dekodlash | `.urldecode строка` | `.urldecode %D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82` | ✅ реализовано | free; — |
| `.urlencode`<br><sub>.urlenc</sub> | URL-кодирование | URL kodlash | `.urlencode текст` | `.urlencode привет мир` | ✅ реализовано | free; — |
| `.uuid`<br><sub>.гуид, .guid</sub> | Случайный UUID v4 | Tasodifiy UUID v4 | `.uuid` | `.uuid` | ✅ реализовано | free; — |
| `.zalgo`<br><sub>.залго</sub> | Z̷a̶l̸g̵o̴-текст (сила 1–10) | Z̷a̶l̸g̵o̴ matn (kuch 1–10) | `.zalgo [сила] текст` | `.zalgo 5 привет` | ✅ реализовано | free; — |

## 👤 Профиль / Profil

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.avatar`<br><sub>.аватар, .ava</sub> | Сделать фото аватаром (ответом на фото, с подтверждением) | Rasmni avatar qilish (rasmga javob, tasdiq bilan) | `.avatar (ответом на фото)` | `.avatar` | ⚠️ ограничено Telegram | free; can_edit_profile_photo |
| `.bio`<br><sub>.био</sub> | Изменить био (до 140 символов, «-» очистить) | Bio'ni o'zgartirish (140 belgigacha) | `.bio текст | .bio -` | `.bio Дизайнер · отвечаю с 10 до 19` | ⚠️ ограничено Telegram | free; can_edit_bio |
| `.clock`<br><sub>.часы, .soat</sub> | Часы в био или фамилии: on/off, bio/last_name, интервал (мин. 15 мин из-за лимитов Telegram) | Bio yoki familiyada soat: on/off, bio/last_name, interval (Telegram cheklovlari tufayli kamida 15 daq) | `.clock on|off|bio|last_name|interval N|format ТЕКСТ` | `.clock on` | ⚠️ ограничено Telegram | free; — |
| `.name`<br><sub>.имя, .ism</sub> | Изменить имя бизнес-аккаунта (с предпросмотром) | Biznes akkaunt ismini o'zgartirish | `.name Имя [| Фамилия]` | `.name Камрон | Ахмедов` | ⚠️ ограничено Telegram | free; can_edit_name |
| `.online`<br><sub>.онлайн, .offline, .оффлайн</sub> | «В сети» — честно: официальный Bot API не управляет онлайн-статусом (NOT_SUPPORTED_BY_OFFICIAL_API); карточка с альтернативами (AFK, Chat Activity) | «Onlayn» — halol: rasmiy Bot API onlayn holatni boshqarmaydi (NOT_SUPPORTED_BY_OFFICIAL_API); muqobillar kartasi (AFK, Chat Activity) | `.online | .offline` | `.online` | ⛔ не поддерживается Bot API | free; — |
| `.profile`<br><sub>.профиль, .profil</sub> | Ваш профиль (или публичные данные автора сообщения-ответа) | Profilingiz (yoki javob xabari muallifining ochiq ma'lumotlari) | `.profile` | `.profile` | ✅ реализовано | free; — |
| `.profile_backup`<br><sub>.бэкаппрофиля, .pbackup</sub> | Сохранить резервную копию имени и био | Ism va bio zaxirasi | `.profile_backup` | `.profile_backup` | ✅ реализовано | free; — |
| `.profile_restore`<br><sub>.восстановитьпрофиль, .prestore</sub> | Восстановить профиль из резервной копии | Profilni zaxiradan tiklash | `.profile_restore` | `.profile_restore` | ✅ реализовано | free; can_edit_name |

## 💬 Автоответчик / Avtojavob

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.allow`<br><sub>.разрешить, .whitelist, .ruxsat</sub> | Разрешить автоответы в этом чате (белый список) | Bu chatda avtojavobga ruxsat (oq ro'yxat) | `.allow [chat_id]` | `.allow` | ✅ реализовано | free; — |
| `.auto`<br><sub>.режим, .mode, .rejim</sub> | Показать или сменить режим автоответчика (manual/auto/ai/afk/silent/business/hybrid) | Avtojavob rejimini ko'rish yoki o'zgartirish | `.auto [режим]` | `.auto` | ✅ реализовано | free; — |
| `.ignore`<br><sub>.игнор, .blacklist</sub> | Не отвечать автоматически в этом чате (чёрный список) | Bu chatda avtomatik javob bermaslik (qora ro'yxat) | `.ignore [chat_id]` | `.ignore` | ✅ реализовано | free; — |
| `.pause`<br><sub>.пауза, .to'xtat</sub> | Приостановить всю автоматизацию (автоответы, AI, AFK-ответы) | Barcha avtomatlashtirishni to'xtatish | `.pause [время]` | `.pause` | ✅ реализовано | free; — |
| `.reply`<br><sub>.ответ, .rule, .javob</sub> | Правила автоответа по ключевым словам: add / list / del / on / off | Kalit so'zlar bo'yicha avtojavob qoidalari: add / list / del / on / off | `.reply add слова | ответ  ·  .reply list  ·  .reply del ID` | `.reply add цена, прайс | Прайс-лист: example.com/price` | ✅ реализовано | free; — |
| `.resume`<br><sub>.продолжить, .davom</sub> | Возобновить автоматизацию | Avtomatlashtirishni davom ettirish | `.resume` | `.resume` | ✅ реализовано | free; — |
| `.tpl`<br><sub>.шаблон, .template, .shablon</sub> | Шаблоны ответов: save имя | текст, имя (вставить), list, del | Javob shablonlari: save nom | matn, nom (qo'yish), list, del | `.tpl save имя | текст · .tpl имя · .tpl list · .tpl del имя` | `.tpl save прайс | Наш прайс: …` | ✅ реализовано | free; — |
| `.welcome`<br><sub>.приветствие, .salomlash</sub> | Приветствие для новых собеседников: текст / on / off | Yangi suhbatdoshlar uchun salomlashish | `.welcome [текст | on | off]` | `.welcome Привет, {name}! Я скоро отвечу.` | ✅ реализовано | free; — |
| `.work`<br><sub>.работа, .ish, .hours</sub> | Рабочие часы и бизнес-режим: on / off / 9-18 / текст вне часов | Ish vaqti va biznes rejim: on / off / 9-18 / ish vaqtidan tashqari matn | `.work [on|off|ЧЧ:ММ-ЧЧ:ММ|text ...]` | `.work 09:00-18:00` | ✅ реализовано | free; — |

## 🎛 Управление чатом / Chatni boshqarish

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.chat`<br><sub>.панель, .cp, .chatpanel</sub> | Панель управления этим чатом — в личке с ботом | Ushbu chatni boshqarish paneli — bot bilan shaxsiy chatda | `.chat` | `.chat` | ✅ реализовано | free; — |
| `.g`<br><sub>.защищённо, .secret</sub> | Защищённое сообщение (protect_content): текст или ответом на фото/видео — без пересылки и сохранения | Himoyalangan xabar (protect_content): matn yoki rasm/videoga javob — uzatish va saqlashsiz | `.g текст | .g (ответом на фото/видео)` | `.g Код от двери 4521` | ⚠️ ограничено Telegram | free; can_reply |
| `.mute`<br><sub>.мьют, .заглушить, .jim</sub> | Mute: удалять новые входящие сообщения собеседника в этом чате (с подтверждением); время и типы по желанию | Mute: ushbu chatdagi suhbatdoshning yangi kiruvchi xabarlarini o'chirish (tasdiq bilan); vaqt va turlar ixtiyoriy | `.mute [10m|1h|1d] [all|text|media|voice|circle|gif|sticker] | .mute status | .mute off` | `.mute` | ⚠️ ограничено Telegram | free; can_reply, can_delete_all_messages |
| `.nogif`<br><sub>.безгиф, .gifsiz</sub> | Удалять входящие GIF и стикеры в этом чате (типы настраиваются кнопкой) | Ushbu chatdagi kiruvchi GIF va stikerlarni o'chirish (turlarni tugma orqali sozlash) | `.nogif [off] [gif] [sticker] [circle]` | `.nogif` | ⚠️ ограничено Telegram | free; can_reply, can_delete_all_messages |
| `.nomute`<br><sub>.фильтрслов, .sozfiltr</sub> | Фильтр слов: удалять входящие сообщения с выбранными словами (add / del / list / on / off) | So'z filtri: tanlangan so'zli kiruvchi xabarlarni o'chirish (add / del / list / on / off) | `.nomute add слово [слово…] | .nomute del слово | .nomute list | .nomute on | .nomute off` | `.nomute add реклама казино` | ⚠️ ограничено Telegram | free; can_reply, can_delete_all_messages |
| `.protect`<br><sub>.защита, .himoya</sub> | Protect: сообщения Chat helper в этом чате нельзя переслать или сохранить (protect_content) | Protect: Chat helper'ning bu chatdagi xabarlarini uzatib yoki saqlab bo'lmaydi (protect_content) | `.protect [off]` | `.protect` | ⚠️ ограничено Telegram | free; can_reply |
| `.quiet`<br><sub>.тихо, .jimlik</sub> | Не отвечать автоматически в этом чате на время (автоответы, AFK, AI); сообщения не удаляются | Ushbu chatda vaqtincha avtomatik javob bermaslik (avtojavob, AFK, AI); xabarlar o'chirilmaydi | `.quiet [время|off]` | `.quiet 2h` | ✅ реализовано | free; — |
| `.re`<br><sub>.повтор, .qaytar, .loop</sub> | Повтор сообщения: отправляет текст и каждые 5 с удаляет предыдущую копию и отправляет снова (до 2 минут); stop — остановить | Xabarni takrorlash: matnni yuboradi va har 5 s oldingi nusxani o'chirib qayta yuboradi (2 daqiqagacha); stop — to'xtatish | `.re текст | .re stop` | `.re Ты где? 👀` | ✅ реализовано | free; can_reply, can_delete_sent_messages |
| `.unmute`<br><sub>.анмьют, .размьют, .unjim</sub> | Выключить Mute в этом чате | Ushbu chatda Mute'ni o'chirish | `.unmute` | `.unmute` | ✅ реализовано | free; — |
| `.unprotect`<br><sub>.снятьзащиту</sub> | Выключить Protect в этом чате | Ushbu chatda Protect'ni o'chirish | `.unprotect` | `.unprotect` | ✅ реализовано | free; — |

## ⚙️ Система / Tizim

| Команда | Описание (RU) | Tavsif (UZ) | Синтаксис | Пример | Статус | Тариф / права |
|---|---|---|---|---|---|---|
| `.a`<br><sub>.анимация, .anim, .animatsiya</sub> | Анимация текста: 16 типов (typewriter, fast, reverse, wave, glitch, matrix, dots, progress, countdown, pulse, heart, slide, rainbow, counter, reveal, custom) и скорости slow/normal/turbo; stop — отменить; без текста — студия анимаций | Matn animatsiyasi: 16 tur va slow/normal/turbo tezliklari; stop — bekor qilish; matnsiz — animatsiya studiyasi | `.a [тип] [скорость] текст | .a custom кадр1 | кадр2 | итог | .a stop` | `.a Привет!` | ✅ реализовано | free; can_reply |
| `.about`<br><sub>.оботе, .haqida</sub> | О Chat helper | Chat helper haqida | `.about` | `.about` | ✅ реализовано | free; — |
| `.backup`<br><sub>.бэкап, .zaxira</sub> | Резервная копия базы (супер-админ, с подтверждением); для остальных — экспорт данных | Bazaning zaxira nusxasi (super-admin, tasdiq bilan) | `.backup` | `.backup` | ✅ реализовано | free; — |
| `.clear`<br><sub>.очистить, .tozala</sub> | Очистить сохранённый AI-контекст и превью этого чата (all — всех чатов) | Ushbu chatning AI konteksti va ko'rinishlarini tozalash (all — barchasi) | `.clear [all]` | `.clear` | ✅ реализовано | free; — |
| `.commands`<br><sub>.команды, .buyruqlar, .cmds</sub> | Компактный список всех команд | Barcha buyruqlarning qisqa ro'yxati | `.commands` | `.commands` | ✅ реализовано | free; — |
| `.export`<br><sub>.экспорт, .eksport</sub> | Экспорт ваших данных (JSON в личку) | Ma'lumotlaringizni eksport (JSON shaxsiy chatga) | `.export` | `.export` | ✅ реализовано | free; — |
| `.fav`<br><sub>.избранное, .sevimli</sub> | Избранные команды для меню «⚡ Быстрые команды»: .fav команда1 команда2 … (без аргументов — показать) | «⚡ Tezkor buyruqlar» menyusi uchun sevimli buyruqlar: .fav buyruq1 buyruq2 … (argumentsiz — ko'rsatish) | `.fav [команды…] | .fav reset` | `.fav afk mute ai sum` | ✅ реализовано | free; — |
| `.help`<br><sub>.помощь, .h, .yordam, .start_help</sub> | Список команд по категориям или справка по команде | Buyruqlar ro'yxati yoki buyruq bo'yicha yordam | `.help [команда]` | `.help` | ✅ реализовано | free; — |
| `.inbox`<br><sub>.входящие, .kiruvchi</sub> | Smart Inbox: кто ждёт ответа (ai — с AI-приоритетами) | Smart Inbox: kim javob kutmoqda (ai — AI ustuvorliklari bilan) | `.inbox [ai]` | `.inbox` | ✅ реализовано | free; — |
| `.info`<br><sub>.инфо, .whois, .kim</sub> | Сведения о пользователе (ответом на сообщение или о собеседнике): имя, username, ID, bio и фото, если доступны боту | Foydalanuvchi haqida ma'lumot (xabarga javob yoki suhbatdosh): ism, username, ID, bio va rasm, agar botga ochiq bo'lsa | `.info (ответом на сообщение)` | `.info` | ✅ реализовано | free; — |
| `.lang`<br><sub>.язык, .til</sub> | Язык интерфейса: ru или uz | Interfeys tili: ru yoki uz | `.lang ru|uz` | `.lang uz` | ✅ реализовано | free; — |
| `.limits`<br><sub>.лимиты, .limitlar</sub> | Лимиты тарифа и использование сегодня | Tarif limitlari va bugungi foydalanish | `.limits` | `.limits` | ✅ реализовано | free; — |
| `.logs`<br><sub>.логи</sub> | Последние предупреждения и ошибки (только администратор) | So'nggi xatolar (faqat admin) | `.logs [N]` | `.logs` | ✅ реализовано | free; — |
| `.mad`<br><sub>.action, .печатает, .актив</sub> | Короткая контролируемая серия статусов «печатает… / записывает… / отправляет фото…» (до 60 с); stop — отмена. Это не «онлайн» | Qisqa nazoratli holatlar seriyasi «yozmoqda… / yozib olmoqda… / rasm yubormoqda…» (60 s gacha); stop — bekor. Bu «onlayn» emas | `.mad [секунды 5–60] [typing|voice|video|photo|doc|sticker…] | .mad stop` | `.mad` | ✅ реализовано | free; can_reply |
| `.menu`<br><sub>.меню, .menyu</sub> | Открыть меню Chat helper (в личке с ботом) | Chat helper menyusini ochish | `.menu` | `.menu` | ✅ реализовано | free; — |
| `.ping`<br><sub>.пинг</sub> | Задержка до Telegram API и время отклика бота | Telegram API kechikishi | `.ping` | `.ping` | ✅ реализовано | free; — |
| `.privacy`<br><sub>.приватность, .maxfiylik</sub> | Что хранится и как удалить данные | Nima saqlanadi va qanday o'chirish | `.privacy` | `.privacy` | ✅ реализовано | free; — |
| `.remind`<br><sub>.напомни, .eslat</sub> | Личное напоминание в личку с ботом; list — список, del ID — отменить | Shaxsiy eslatma bot bilan chatga; list — ro'yxat, del ID — bekor qilish | `.remind время текст | .remind list | .remind del ID` | `.remind 30m позвонить маме` | ✅ реализовано | free; — |
| `.remindf`<br><sub>.напомнивчат, .eslatchat</sub> | Напоминание в этот чат в указанное время (от вашего имени; нужно право «Ответы» и окно 24 ч Telegram) | Belgilangan vaqtda shu chatga eslatma (sizning nomingizdan; «Javob berish» huquqi va Telegram 24 soat oynasi kerak) | `.remindf время текст` | `.remindf 1h Не забудь документы!` | ⚠️ ограничено Telegram | free; can_reply |
| `.settings`<br><sub>.настройки, .sozlamalar</sub> | Текущие настройки | Joriy sozlamalar | `.settings` | `.settings` | ✅ реализовано | free; — |
| `.stats`<br><sub>.статистика, .statistika</sub> | Ваша статистика за сегодня и 7 дней | Bugungi va 7 kunlik statistika | `.stats` | `.stats` | ✅ реализовано | free; — |
| `.status`<br><sub>.статус, .holat</sub> | Статус подключения, режима и модулей | Ulanish, rejim va modullar holati | `.status` | `.status` | ✅ реализовано | free; — |
| `.support`<br><sub>.поддержка, .yordam_so'rov</sub> | Написать администратору Chat helper | Chat helper administratoriga yozish | `.support текст` | `.support Не работает .speed` | ✅ реализовано | free; — |
| `.theme`<br><sub>.тема, .mavzu</sub> | Стиль сообщений бота: classic, minimal, fancy, emoji | Bot xabarlari uslubi | `.theme classic|minimal|fancy|emoji` | `.theme fancy` | ✅ реализовано | free; — |
| `.timer`<br><sub>.таймер, .taymer</sub> | Сообщение, которое удалится через время (или ответом — удалить ваше сообщение). Не защищённые «исчезающие» сообщения | Vaqt o'tib o'chadigan xabar (yoki javob — xabaringizni o'chirish). Himoyalangan «yo'qoladigan» xabar emas | `.timer время [текст]` | `.timer 30s Секретный код 1234` | ⚠️ ограничено Telegram | free; can_reply |
| `.uptime`<br><sub>.аптайм</sub> | Время работы backend | Backend ishlash vaqti | `.uptime` | `.uptime` | ✅ реализовано | free; — |

## Примечания

- `.online` — не поддерживается: Bot API не меняет статус «в сети». Подделок не делаем.
- `.clock` — меняет профиль не чаще 1 раза в 15 минут (лимиты Telegram), с откатом при FloodWait.
- `.timer` — удаляет только то, что разрешает Bot API; это не защищённые «исчезающие» сообщения.
- Медиа: вход до 20 МБ (лимит скачивания Bot API), результат до 50 МБ (лимит отправки).
- Ответ в бизнес-чате возможен, только если собеседник писал за последние 24 часа; иначе результат приходит вам в личку.
