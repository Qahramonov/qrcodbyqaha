# Chat helper v3.0 — журнал разработки

Исходное ТЗ: `Chat_helper_v3_MASTER_PROMPT.txt` (41 раздел). Работа идёт фазами; после каждой — тесты и коммит.

## Phase 1 — аудит (готово)

| Область | Что было в v1/v2 | Что требует v3 |
|---|---|---|
| Admin Panel | видна super_admin **и moderator** (бот: `screen_home`, API: `deps.admin`, APK: capability `users`) | только ID 8053614984 на всех уровнях |
| Доступ до подключения | все команды и меню доступны без Business-подключения | только /start, /help, /connect, проверка, инструкция, язык, поддержка (+ /app для привязки APK к мастеру подключения) |
| `.mute` | выключал автоответы в чате (`chats.muted_until`) | удалять новые входящие через `deleteBusinessMessages` (право `can_delete_all_messages`), подтверждение, таймер, типы, отчёт; старое поведение → `.quiet` |
| `.online` | честное объяснение NOT_SUPPORTED | сохранить честность; добавить «Chat Activity» только во время реальной обработки |
| `.a` | typewriter, 8 кадров, 0.9 с | Animation Engine: 16 типов, 4 скорости, отмена, без FloodWait |
| `.r` | chat action «печатает» | RTL-эффект; chat actions → `.mad` |
| `.info` (media) | сведения о файле | сведения о пользователе; файл → `.finfo` |
| Локализация | пары `tr(lang, ru, uz)` прямо в коде | JSON-каталоги ru/uz(/en) с ключами + тесты |
| Inline-кнопки в бизнес-чатах | не использовались | Chat Control Framework (control messages, owner-only callbacks, идемпотентность) |

### Проверенные факты Bot API (aiogram 3.31 = Bot API 10.3; core.telegram.org из среды недоступен)
* `editMessageText`: «business messages that were not sent by the bot and do not contain an inline keyboard can only be edited within 48 hours» → inline-клавиатуры в бизнес-сообщениях поддерживаются.
* `deleteBusinessMessages`: `can_delete_sent_messages` — сообщения бота, `can_delete_all_messages` — любые.
* `BusinessBotRights`: + `can_delete_outgoing_messages` (deprecated с 9.1).
* Ephemeral messages (`ephemeral_message_parameters`) — методы без `business_connection_id` → в бизнес-чатах не используем; приватный вариант = личка с ботом.
* Manage Bot bar → `/start bizChat<user_chat_id>` (Bot Features, grammY guide). Premium для подключения бизнес-бота не нужен.

## План фаз
- [x] 1. Аудит
- [ ] 2–3. RBAC (только super admin), gating до подключения, онбординг + инфографика RU/UZ, `tg://settings/edit`
- [ ] 4–6. Chat Context Manager (`bizChat`), Chat Control Framework, Mute Engine, Protect/.g, .nogif, .nomute
- [ ] 7–9. Animation Engine, .re, .r (RTL), .mad, .online, новые команды, AI Twin, `.ai`
- [ ] 11–12. Локализация (JSON + codemod), новые панели (user/admin), делегирование, миграция M003, API
- [ ] 13–14. Flutter-приложение + дизайн-система (Figma-ready)
- [ ] 15–16. Тесты, документация (15 файлов), ZIP v3, отчёт
