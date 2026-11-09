# B15 — Production

09.11.2026. **Статус: развёрнуто, все 6 деплоев SUCCESS.**

## Перед выкаткой
- **Активных генераций не было:** на всех 5 workers `active_tasks: 0`, за предыдущий час не взято ни одного задания.
- **Ветки `release/*` не менялись** после подготовки: `ccde13e` / `8b08994`.
- **Все 10 сервисов Online**, pendingWork пуст.

## Выкатка
Fast-forward без force:
- `release/sx010-api-20261108`: `ccde13e` → `5dbcde1`;
- `release/workers-unified-20261108`: `8b08994` → `dde6dea`.

| Сервис | Деплой | SUCCESS |
|---|---|---|
| API `sylvex-ai-webapp` | `be0686d8` | 21:39:55Z |
| sylvex-worker | `c5c8fb40` | 21:41:24Z |
| worker-2 | `fe64902c` | 21:43:08Z |
| worker-3 | `70345486` | 21:44:20Z |
| worker-4 | `142d6925` | 21:47:44Z |
| worker-5 | `9caab3df` | 21:43:44Z |

## После выкатки
- **API:** `Application startup complete`, `ACCOUNT_ERASURE_RUNTIME` в порядке (индекс 49/49). HTTP только 200, ни одного 5xx; исключений и deadlock нет.
- **Workers:** пул, R2-хранилище и напоминания стартовали на всех пяти.
- **Фоновый опрос:** запускается вместе с пулом. Ошибок его SQL (`LATE_RESULT_CLAIM_FAILED`, `BACKGROUND_WAIT_CLAIM_FAILED`, `LATE_RESULT_LOOP_FAILED`) нет. При простое в лог он не пишет, поэтому его работа подтверждена косвенно.
- **Ошибки в логах** только давние: `SUBSCRIPTION_REMINDER_FAILED` для тестового веб-аккаунта (chat not found) и одно предупреждение Postgres.

## Тесты (локально, до выкатки)
- `tests/test_b15_completion_atomicity.py`: 31/31 на API и workers.
- Регрессия против исходного кода — 0 новых падений:
  - основной набор: 1422 / 1298 PASS;
  - LB-003 и биллинг: 160;
  - LB-006: 78/78;
  - LR-002: 29/29;
  - удаление B09: 111;
  - R2 SQL: 11/11.

## Не подтверждено
- **Поведение Kling после 480 с** (фоновое ожидание, затем завершение или возврат) не подтверждено реальной генерацией. Платные тесты не запускались.
- **Как подтвердить:** на первой естественной генерации видео дольше 480 с найти в логах:
  - `JOB_PROVIDER_BACKGROUND_WAIT`;
  - затем `BACKGROUND_PROVIDER_JOB_COMPLETED` или уведомление о неудаче.

## Откат
Redeploy:
- API — `6848544d`;
- worker — `c31ff082`, worker-2 — `e04e12d8`, worker-3 — `0f79af8a`, worker-4 — `6e11536d`, worker-5 — `f522eccc`.
