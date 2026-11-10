# S7-09 — ошибка 500 раздела финансов админки: исправлено в ветке

Ветка `claude/admin-finance-text-dates`, коммит 7d4c10e, база — Production API ba96d8c. Production не изменялся.

## Причина

`POST /api/admin/finance` → 500: `operator does not exist: text >= timestamp without time zone` (`admin_finance`/`_sync`).

- Основной бот создаёт `purchases` первым, со столбцом `created_at TEXT` (`sylvex-ai-bot`, `app/database/db.py`:249).
- `CREATE TABLE IF NOT EXISTS purchases (… created_at TIMESTAMP …)` в API (`main.py`:1549) в Production поэтому ничего не сделал, и столбец текстовый. Это подтверждает сама ошибка PostgreSQL; в SX-010 то же записано для схемы бота.
- Тест финансов проходил только потому, что тестовая таблица создавалась схемой API (`TIMESTAMP`).

Что лежит в столбце:
- от бота — `YYYY-MM-DD HH:MM:SS`;
- от API (shop orders, Stripe, billing safety) — `CURRENT_TIMESTAMP` в виде текста `…+00`;
- у 72 старых записей без даты (SX-010) — `NULL` или `''`.

## Исправление

- Четыре запроса раздела читают дату через `_purchase_time_sql()`: значение, начинающееся с `YYYY-MM-DD`, превращается в timestamp, иначе получается `NULL`.
- Покупки без даты не попадают ни в один период; даты не придумываются, как в SX-010.
- Схема, покупки, платежи, Stripe, кредиты и MFA не менялись. Других сырых сравнений `purchases.created_at` в API нет.

## Тесты

| Набор | Результат |
|---|---|
| `tests/test_admin_finance_text_dates.py`, схема бота `TEXT` | до исправления 3 падения с `text >= timestamp`; после — **4 passed** |
| Регрессия: финансы на схеме `TIMESTAMP` (stage_e), stage_d, MFA, console auth, users, extended, balance, messages, service token, console UI | **125 passed** |

Что проверяют адресные тесты:
- оба формата записи (бот и API);
- старая покупка с датой — вне 30 дней, но в «за всё время»;
- `NULL`, `''` и мусорная дата исключены;
- явный и пустой период;
- новый и повторный покупатель;
- данные `purchases` не меняются;
- нужно право `payments.view`.

**Остаточный риск:** строка, похожая на дату, но некорректная (например `2026-13-45`), снова вызовет ошибку. Писатели такие строки не создают.

## Развёртывание

Требует отдельного разрешения: fast-forward `release/sx010-api-20261108` ba96d8c → 7d4c10e, затем проверка `/api/admin/finance` в консоли.
