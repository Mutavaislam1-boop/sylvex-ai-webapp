# B10 — MFA (TOTP) для Telegram-администраторов: реализация в ветках

Дата: 10.11.2026. Production не изменялся: ничего не развёрнуто, переменные не менялись, release-ветки не тронуты.

## Коммиты (ветка `claude/b10-telegram-admin-mfa` в каждом репозитории)

| Репозиторий | База (Production) | Коммит | Что |
|---|---|---|---|
| sylvex-ai-webapp (API + консоль) | 5dbcde1 | ba96d8c | TOTP в Mini App, подтверждение для ботов и v1, сессия только для подключения, повторное подтверждение только по TOTP, сброс 2FA владельцем, экраны консоли, пересобранный dist |
| silvex-support-bot | f9cd89e | a75bf83 | Проверка состояния 2FA, кнопка «🔐 Подтвердить 2FA» (Web App), понятные тексты ошибок |
| sylvex-ai-bot | b7e1b90 | 55e57da | `/admin` и `/addbalance`: нужен владелец с 2FA и подтверждением за 30 / 5 минут |

## Как устроено

Используется существующий механизм TOTP веб-админки (`services/admin_auth.py`: RFC 6238, шифрование секрета, одноразовость кода, блокировка после 5 ошибок на 15 минут). Новой системы авторизации нет. Добавлены два столбца, создаются автоматически через `ALTER TABLE … ADD COLUMN IF NOT EXISTS`:
- `admin_sessions.mfa_at` — сессия прошла TOTP;
- `admin_accounts.telegram_confirmed_at` — время последнего подтверждения кодом внутри Telegram.

**Каналы:**

1. **Mini App (консоль, v2).**
   - Вход: `initData` + код TOTP в той же форме консоли.
   - Без кода — `401 totp_required`, сессия не создаётся.
   - Администратор без TOTP получает сессию только для подключения: доступны только `auth/me`, `totp/enroll`, `totp/confirm`, `reauth` (только для подключения), `logout`, `logout-all`. Первый подтверждённый код делает её полной.
2. **Браузер.** Без изменений: email + пароль + TOTP.
3. **Боты (service token + `telegram_id`) и старый Mini App v1 (`initData` в теле запроса).**
   - Любое действие с правом требует включённого TOTP и подтверждения в Mini App за последние 30 минут.
   - Критическое действие — за последние 5 минут.
   - Иначе `403 totp_enrollment_required`, `totp_confirmation_required` или `critical_confirmation_required`.
   - Подтверждение ставят: вход в Mini App с TOTP, повторное подтверждение TOTP в сессии Mini App, подключение TOTP.
   - Вход через браузер подтверждением для ботов не считается.
4. **Критические действия в консоли.** Только повторный TOTP (5 минут). Telegram (`initData`) повторно подтверждает только сессию для подключения, и только для настройки TOTP.
5. **Защита от обхода.**
   - Сессия, не прошедшая TOTP, не может заменить уже настроенный аутентификатор.
   - Неверные коды при подключении тоже считаются в блокировку.
   - «Выйти везде» снимает и подтверждение для ботов.
6. **Потерянный аутентификатор.** Новый маршрут `POST /api/admin/v2/admins/{id}/totp/reset`:
   - только владелец;
   - критическое действие (свежий TOTP);
   - обязательна причина;
   - нельзя применить к себе;
   - завершает сессии администратора;
   - записывается в аудит как `critical`.
7. **Коды не запрашиваются в чатах.**
   - Боты присылают кнопку Web App на `…/admin/?confirm=bot`.
   - Консоль сама спрашивает код и показывает «Подтверждено… Вернуться в бот».

**Основной бот.** `/admin` и `/addbalance` раньше проверяли только `ADMIN_ID`, причём `/addbalance` меняет баланс напрямую в базе. Теперь нужен ещё:
- активный владелец с TOTP;
- подтверждение за 30 минут для `/admin` и за 5 минут для `/addbalance`.

Любая ошибка базы означает отказ.

**Не затронуто:**
- обычные пользователи, генерации, платежи;
- CSRF, rate limiting, RBAC и SQL Codex;
- пересылка сообщений поддержки в боте поддержки: это переписка с пользователями, а не административное действие;
- `/api/public/keyboard-debug/access`: отвечает только да/нет на показ отладочной панели;
- консольный CLI `payment_review_admin` вне Telegram.

## Защищённые маршруты

Все маршруты `/api/admin/*` проверяются одним из двух защитников:
- `_admin_v2_actor` — сессия консоли;
- `_admin_actor` — сессия консоли, бот или v1 `initData`.

Тест `test_no_admin_route_accepts_a_session_without_totp` перебирает все маршруты `/api/admin/*` приложения (60 проверено), кроме входа и подключения. Тест `test_no_bot_route_acts_without_a_telegram_confirmation` перебирает все v1-маршруты для бота без подтверждения. Оба проходят.

| Маршрут | Право | Риск |
|---|---|---|
| `POST /api/admin/admins/list` | admins.view | low |
| `POST /api/admin/admins/set` | admins.permissions.edit | critical |
| `POST /api/admin/analytics` | analytics.view | low |
| `POST /api/admin/audience` | users.view | low |
| `POST /api/admin/audit` | audit.view | low |
| `POST /api/admin/dashboard` | dashboard.view | low |
| `POST /api/admin/error-reports` | errors.view | low |
| `POST /api/admin/errors` | errors.view | low |
| `POST /api/admin/finance` | payments.view | low |
| `POST /api/admin/generations` | generations.view | low |
| `POST /api/admin/generations/detail` | generations.view | low |
| `POST /api/admin/generations/stats` | generations.view | low |
| `POST /api/admin/inbox/assign` | messages.send / support.manage | medium–high |
| `POST /api/admin/inbox/assignees` | messages.send | medium |
| `POST /api/admin/inbox/attachments` | messages.send | medium |
| `POST /api/admin/inbox/list` | messages.send | medium |
| `POST /api/admin/inbox/reply` | messages.send | medium |
| `POST /api/admin/inbox/status` | messages.send | medium |
| `POST /api/admin/inbox/thread` | messages.send | medium |
| `POST /api/admin/me` | — (читается без подтверждения: роль и состояние 2FA) | — |
| `POST /api/admin/media/catalog` | content.references.manage | medium |
| `POST /api/admin/media/check` | content.references.manage | medium |
| `POST /api/admin/messages/broadcast` | broadcast.send | critical |
| `POST /api/admin/messages/history` | messages.send | medium |
| `POST /api/admin/messages/preview` | broadcast.create | medium |
| `POST /api/admin/messages/send` | messages.send (один получатель) / broadcast.send (рассылка) | medium / critical |
| `POST /api/admin/messages/upload-image` | messages.send | medium |
| `POST /api/admin/models/overview` | models.view | low |
| `POST /api/admin/models/toggle` | models.edit | critical |
| `POST /api/admin/prostudio/recover-job/{job_id}` | generations.recover | medium |
| `POST /api/admin/references/create` | content.references.manage | medium |
| `POST /api/admin/references/delete` | content.publish | high |
| `POST /api/admin/references/list` | content.references.manage | medium |
| `POST /api/admin/references/publish` | content.publish | high |
| `POST /api/admin/references/update` | content.references.manage | medium |
| `POST /api/admin/references/upload-media` | content.references.manage | medium |
| `POST /api/admin/reviews/list` | users.view | low |
| `POST /api/admin/reviews/reply` | messages.send | medium |
| `POST /api/admin/subscribers` | payments.view | low |
| `POST /api/admin/top-spenders` | payments.view | low |
| `POST /api/admin/users/balance` | users.balance.adjust | high |
| `POST /api/admin/users/block` | users.ban | high |
| `POST /api/admin/users/conversation` | messages.send | medium |
| `POST /api/admin/users/detail` | users.view | low |
| `POST /api/admin/users/message` | messages.send | medium |
| `POST /api/admin/users/message/send` | messages.send | medium |
| `POST /api/admin/users/online` | users.view | low |
| `POST /api/admin/users/search` | users.view | low |
| `POST /api/admin/users/subscription` | users.subscription.edit | high |
| `POST /api/admin/users/unblock` | users.ban | high |
| `GET /api/admin/v2/admins` | admins.view | low |
| `POST /api/admin/v2/admins` | admins.create | critical |
| `PATCH /api/admin/v2/admins/{admin_id}` | admins.permissions.edit | critical |
| `POST /api/admin/v2/admins/{admin_id}/totp/reset` | admins.permissions.edit | critical |
| `GET /api/admin/v2/audit` | audit.view | low |
| `GET /api/admin/v2/auth/logins` | - | - |
| `POST /api/admin/v2/auth/logout` | - | - |
| `POST /api/admin/v2/auth/logout-all` | - | - |
| `GET /api/admin/v2/auth/me` | - | - |
| `POST /api/admin/v2/auth/reauth` | - | - |
| `GET /api/admin/v2/auth/sessions` | - | - |
| `POST /api/admin/v2/auth/sessions/revoke` | - | - |
| `POST /api/admin/v2/auth/telegram` | - | - |
| `POST /api/admin/v2/auth/totp/confirm` | - | - |
| `POST /api/admin/v2/auth/totp/enroll` | - | - |
| `POST /api/admin/v2/auth/web` | - | - |
| `GET /api/admin/v2/permissions` | - | - |
| `POST /api/admin/v2/users/role` | admins.permissions.edit | critical |

Маршруты v2 без права в таблице проверяют только сессию:
- `auth/me`, `auth/totp/*`, `auth/reauth`, `auth/logout*` принимают сессию для подключения;
- `auth/sessions`, `auth/logins`, `auth/sessions/revoke`, `permissions` требуют сессию, прошедшую TOTP;
- `auth/telegram`, `auth/web` — входы.

## Результаты проверок

| Проверка | Результат |
|---|---|
| Новые адресные тесты API `tests/test_admin_telegram_mfa.py` (PGlite, реальный SQL) | **17 passed** (`evidence/api_mfa_tests.log`) |
| Регрессия API: 21 набор тестов админки и смежных | **240 passed, 10 failed**: все 10 — `test_canonical_identity.py`, падают так же на неизменённом 5dbcde1 (`invalid dsn: "pglite://test"` в psycopg2, ошибка тестового окружения) (`evidence/api_regression.log`) |
| Консоль: `npm run build` (проверка переводов + tsc + vite) | успешно |
| Консоль в Chromium (подменённый API, эмуляция Telegram) | код спрашивается; неверный отклонён; верный открывает консоль; подключение через QR; экран «Подтверждено» закрывает Mini App (`evidence/console_ui_check.cjs`) |
| Бот поддержки | **44 passed**, из них 5 новых (`evidence/support_bot_tests.log`) |
| Основной бот `tests/test_admin_mfa.py` (реальный PostgreSQL) | **5 passed**. `test_telegram_media::test_provider_receives_the_sylvex_url_not_a_telegram_url` падает так же на неизменённом b7e1b90 |

Что проверено тестами:
- **вход с TOTP:** `test_miniapp_login_needs_the_totp_code`;
- **отказ без TOTP:** тот же тест и оба обхода по всем маршрутам;
- **неверный, просроченный (±90 с), неправильного формата и повторный код:** `test_wrong_expired_and_malformed_codes_are_refused_and_lock_out` (включая блокировку), `test_miniapp_login_needs_the_totp_code` (повтор);
- **разграничение прав:** `test_bot_rbac_is_unchanged_and_checked_first` и существующие RBAC-тесты (`test_admin_console_auth.py`: 42 passed);
- **критические действия:** `test_critical_actions_need_a_fresh_totp_reauth_valid_five_minutes`, `test_critical_bot_actions_need_a_confirmation_from_the_last_five_minutes`;
- **безопасное подключение без блокировки всех:** `test_enrollment_only_session_reaches_nothing_but_setup`, `test_every_admin_can_enroll_after_rollout_so_nobody_is_locked_out`, `test_a_session_without_totp_cannot_replace_an_existing_authenticator`, `test_enrollment_needs_a_fresh_telegram_confirmation`;
- **источники и завершение подтверждения:** `test_where_the_telegram_confirmation_comes_from_and_ends`;
- **сброс владельцем:** `test_owner_resets_a_lost_authenticator`.

Изменения старых тестов: фикстуры теперь заводят администраторам тестовый TOTP и подтверждение (`admin_fixtures.enable_mfa`, `fresh_totp`). Так выглядят администраторы после внедрения. Тесты, проверяющие сценарий «без 2FA», явно снимают его (`_without_totp`). Утверждение старого теста «Telegram сам по себе подтверждает критическое действие» заменено на новое требование: только TOTP.

## Развёртывание (нужно отдельное разрешение владельца)

Порядок:
1. **API** (6b50067b) с ba96d8c. Столбцы появятся сами при первом запросе к админке.
2. **Бот поддержки** с a75bf83.
3. **Основной бот** с 55e57da. Он только читает новые столбцы. Если развернуть его раньше API, `/admin` и `/addbalance` будут отказывать, пока API не обновлён.
4. **Необязательно:** переменная `ADMIN_CONSOLE_URL` (https://…/admin/) у основного бота, чтобы появилась кнопка «🔐 Подтвердить 2FA». Без неё бот пишет текстовую инструкцию.

Сразу после развёртывания:
- Сессии Mini App попросят код.
- Боты попросят подтверждение.
- Администратор без TOTP (по данным Codex 07.11 — один из трёх) пройдёт подключение по инструкции `ADMIN_TOTP_GUIDE.md`.
- Перед развёртыванием владельцу стоит убедиться, что у него самого TOTP включён и аутентификатор доступен, либо сохранить резервную копию ключа (раздел 4 инструкции).

Реестр не менялся: S1-05 / S7-09 можно подтверждать только после развёртывания и живой проверки.
