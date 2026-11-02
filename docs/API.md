# Chat helper Control API (v1)

> Сгенерировано из OpenAPI (`backend/tools/gen_docs.py`). Swagger UI (`/api/docs`) выключен по умолчанию, потому что показывает все маршруты; для разработки включается `API_DOCS_ENABLED=true`.

**Базовый адрес:** `http://127.0.0.1:8787/api/v1` (по умолчанию слушает только localhost).

**Аутентификация:** одноразовый код из Telegram (`/app`) → `POST /auth/pair` → `access_token` (1 ч) + `refresh_token` (30 дн., ротация). Все запросы, кроме `/health`, `/auth/pair`, `/auth/refresh`: `Authorization: Bearer <access_token>`.

**Ошибки:** `{"error": {"code": "...", "message": "..."}}` · 401 токен · 403 действие не разрешено (например, не делегировано) · 404 не найдено/чужое · 409 конфликт · 422 валидация · 429 лимит (`Retry-After`).

**Роли:** `user` — только свои данные; `super_admin` (ID из `SUPER_ADMIN_ID`) — всё. Роль вычисляется на сервере; передача чужого Telegram ID в запросе ничего не даёт.

**Админ-маршруты невидимы.** Для всех, кроме Super Admin, любой админ-маршрут отвечает тем же `404 not_found`, что и несуществующий адрес; без токена и админ-, и несуществующие маршруты отвечают одинаковым `401`. Каждая такая попытка пишется в журнал аудита (`security.admin_api_denied`).

## afk

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/afk` | Afk Status |
| `POST` | `/afk/disable` | Afk Disable |
| `POST` | `/afk/enable` | Afk Enable |
| `GET` | `/afk/history` | Afk History |
| `GET` | `/afk/preview` | Afk Preview |

## ai

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/ai/compare` | Compare |
| `GET` | `/ai/drafts` | Drafts |
| `POST` | `/ai/drafts/{did}/{action}` | Draft Action |
| `GET` | `/ai/memory` | Memory |
| `POST` | `/ai/memory` | Add Memory |
| `DELETE` | `/ai/memory` | Clear Memory |
| `DELETE` | `/ai/memory/{mid}` | Delete Memory |
| `POST` | `/ai/playground` | Playground |
| `GET` | `/ai/profiles` | Profiles |
| `POST` | `/ai/profiles` | Create Profile |
| `PATCH` | `/ai/profiles/{pid}` | Update Profile |
| `DELETE` | `/ai/profiles/{pid}` | Delete Profile |
| `POST` | `/ai/profiles/{pid}/activate` | Activate Profile |
| `GET` | `/ai/providers` | Providers |
| `POST` | `/ai/providers/check` | Providers Check |
| `PATCH` | `/ai/system` | Ai System |
| `GET` | `/ai/usage` | Usage |

## ai-twin

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/ai/twin` | Twin Get |
| `PUT` | `/ai/twin` | Twin Put |
| `POST` | `/ai/twin/examples` | Twin Example |
| `DELETE` | `/ai/twin/examples` | Twin Examples Clear |
| `POST` | `/ai/twin/preview` | Twin Preview |

## analytics

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/analytics/export` | Analytics Export |
| `GET` | `/analytics/overview` | Analytics |

## animations

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/animations` | Animations |
| `POST` | `/animations/preview` | Animation Preview |
| `PUT` | `/animations/settings` | Animation Settings |

## auth

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/auth/logout` | Logout |
| `GET` | `/auth/me` | Me |
| `POST` | `/auth/pair` | Pair |
| `POST` | `/auth/refresh` | Refresh |
| `GET` | `/auth/sessions` | Sessions |
| `DELETE` | `/auth/sessions/{session_id}` | Revoke Session |
| `GET` | `/health` | Health |

## automation

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/automation/executions` | Auto Exec |
| `GET` | `/automation/rules` | Auto Rules |
| `POST` | `/automation/rules` | Auto Create |
| `PATCH` | `/automation/rules/{rid}` | Auto Update |
| `DELETE` | `/automation/rules/{rid}` | Auto Delete |
| `GET` | `/automation/schema` | Automation Schema |
| `GET` | `/automation/templates` | Auto Templates |
| `POST` | `/automation/templates/{tid}/install` | Auto Install |
| `POST` | `/automation/test` | Auto Test |

## autoreply

| Метод | Путь | Описание |
|---|---|---|
| `PUT` | `/autoreply/mode` | Set Mode |
| `GET` | `/autoreply/rules` | Ar Rules |
| `POST` | `/autoreply/rules` | Ar Create |
| `PATCH` | `/autoreply/rules/{rid}` | Ar Update |
| `DELETE` | `/autoreply/rules/{rid}` | Ar Delete |
| `GET` | `/autoreply/templates` | Tpl List |
| `POST` | `/autoreply/templates` | Tpl Save |
| `DELETE` | `/autoreply/templates/{name}` | Tpl Delete |

## broadcast

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/broadcasts` | Broadcasts |
| `POST` | `/broadcasts` | Create Broadcast |
| `POST` | `/broadcasts/estimate` | Estimate |
| `GET` | `/broadcasts/{bid}` | Broadcast Detail |
| `POST` | `/broadcasts/{bid}/{action}` | Broadcast Action |

## chat-controls

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/admin/chat-controls` | Admin Controls |
| `GET` | `/chats/{chat_id}/controls` | Chat Controls |
| `PATCH` | `/chats/{chat_id}/controls` | Set Chat Control |

## chats

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/chats` | Chats |
| `GET` | `/chats/{chat_id}` | Chat |
| `PATCH` | `/chats/{chat_id}` | Patch Chat |
| `DELETE` | `/chats/{chat_id}/data` | Delete Chat Data |
| `DELETE` | `/chats/{chat_id}/history` | Clear Chat History |
| `GET` | `/inbox` | Inbox |

## commands

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/commands` | Commands |
| `GET` | `/commands/custom` | Custom List |
| `POST` | `/commands/custom` | Custom Save |
| `DELETE` | `/commands/custom/{name}` | Custom Delete |
| `PUT` | `/commands/prefix` | Set Prefix |
| `POST` | `/commands/test` | Test Cmd |
| `PATCH` | `/commands/{cid}` | Toggle Cmd |
| `PATCH` | `/commands/{cid}/global` | Global Cmd |

## connections

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/connections` | Connections |
| `GET` | `/connections/{conn_id}/inspector` | Inspector |
| `POST` | `/connections/{conn_id}/refresh` | Refresh Conn |
| `POST` | `/connections/{conn_id}/{action}` | Pause Conn |

## dashboard

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/dashboard` | Dashboard |

## delegation

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/admin/delegated/{uid}` | Admin Delegated |
| `POST` | `/admin/delegated/{uid}/profile-request` | Admin Profile Request |
| `PATCH` | `/admin/delegated/{uid}/settings` | Admin Delegated Settings |
| `GET` | `/delegation` | Delegation |
| `PUT` | `/delegation/{scope}` | Delegation Set |

## flags

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/flags` | Flags |
| `PUT` | `/flags/{key}` | Set Flag |

## games

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/games` | Games |
| `GET` | `/games/history` | Game History |
| `DELETE` | `/games/history` | Clear Games |
| `GET` | `/games/leaderboard` | Leaderboard |
| `GET` | `/games/sessions` | Game Sessions |
| `POST` | `/games/sessions/{sid}/end` | Game End |
| `PATCH` | `/games/settings` | Games Settings |

## live

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/events` | Events |

## media

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/media/cleanup` | Media Cleanup |
| `GET` | `/media/demo/{effect}` | Media Demo |
| `GET` | `/media/jobs` | Media Jobs |
| `POST` | `/media/jobs/{job_id}/cancel` | Media Cancel |
| `GET` | `/media/settings` | Media Settings |
| `PATCH` | `/media/settings` | Media System |
| `GET` | `/media/stats` | Media Stats |

## mute

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/mute` | Mute Overview |
| `PUT` | `/mute/settings` | Mute Settings |

## notifications

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/notifications` | Notifications |
| `POST` | `/notifications/read` | Notifications Read |

## onboarding

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/onboarding` | Onboarding |

## payments

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/payments` | Payments |
| `POST` | `/payments/{pid}/refund` | Refund |

## permissions

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/permissions` | Permissions |

## privacy

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/export` | Export Me |

## protect

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/protect` | Protect Overview |

## reminders

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/reminders` | Reminders |
| `POST` | `/reminders` | Reminder Create |
| `DELETE` | `/reminders/{rid}` | Reminder Cancel |

## security

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/security/audit` | Audit |
| `POST` | `/security/emergency-stop` | Emergency |
| `GET` | `/security/logins` | Logins |
| `GET` | `/security/ratelimits` | Ratelimits |
| `POST` | `/security/revoke-all` | Revoke All |
| `GET` | `/security/sessions` | All Sessions |
| `DELETE` | `/security/sessions/{sid}` | Kill Session |
| `GET` | `/security/suspicious` | Suspicious |

## settings

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/settings` | Get Settings |
| `PATCH` | `/settings` | Patch Settings |

## subscriptions

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/subscriptions/me` | My Sub |
| `GET` | `/subscriptions/plans` | Plans |
| `PUT` | `/subscriptions/plans/{plan_id}` | Upsert Plan |
| `GET` | `/subscriptions/promo` | Promos |
| `POST` | `/subscriptions/promo` | Create Promo |
| `DELETE` | `/subscriptions/promo/{code}` | Disable Promo |
| `POST` | `/subscriptions/redeem` | Redeem |
| `GET` | `/subscriptions/stats` | Sub Stats |
| `POST` | `/subscriptions/trial` | Trial |

## system

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/changelog` | Changelog |
| `POST` | `/support` | Support |
| `POST` | `/system/backup` | Backup |
| `GET` | `/system/backups` | Backups |
| `GET` | `/system/checks` | System Checks |
| `POST` | `/system/cleanup` | Cleanup |
| `GET` | `/system/db-integrity` | Db Integrity |
| `GET` | `/system/logs` | Logs |
| `GET` | `/system/logs/export` | Logs Export |
| `POST` | `/system/maintenance` | Maintenance |
| `GET` | `/system/modules` | Modules |
| `PUT` | `/system/modules` | Set Modules |
| `POST` | `/system/restart/{component}` | Restart |
| `GET` | `/system/status` | System Status |

## users

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/users` | Users |
| `GET` | `/users/{uid}` | User Detail |
| `GET` | `/users/{uid}/audit` | User Audit |
| `POST` | `/users/{uid}/restore` | Restore |
| `POST` | `/users/{uid}/restrict` | Restrict |
| `PUT` | `/users/{uid}/role` | Set Role |
| `POST` | `/users/{uid}/subscription` | Grant |
| `DELETE` | `/users/{uid}/subscription` | Revoke Sub |

Всего эндпоинтов: **159**.