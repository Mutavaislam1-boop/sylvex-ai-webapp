# S1-06 — живая проверка sylvex.ai (11.11.2026, 01:07Z)

Запросы из сессии после того, как `sylvex.ai` был разрешён в сети окружения сессии (это настройка сессии, не Production). Код и Production не менялись.

| Проверка | Результат |
|---|---|
| `GET https://sylvex.ai/account/profile.html` | `HTTP/2 200`, `cache-control: no-cache`, `content-type: text/html`, `x-content-type-options: nosniff` |
| `GET https://sylvex.ai/account/settings.html` | `HTTP/2 200`, `cache-control: no-cache`, `content-type: text/html`, `x-content-type-options: nosniff` |
| Ссылка на скрипт в обеих страницах | `/js/site.js?v=s106-xss-20261109` |
| `GET https://sylvex.ai/js/site.js?v=s106-xss-20261109` | `HTTP/2 200`, `text/javascript`; содержит `escapeHtmlLocal(session.avatar_url)` и `escapeHtmlLocal(initials(session))` |
| Побайтное сравнение с sylvex-website 3009404 (= `main`) | `account/profile.html`, `account/settings.html`, `js/site.js` — **идентичны** |

Связь с уже пройденными проверками:
- Production отдаёт ровно те файлы (3009404), на которых прошли `tests/account-xss-escaping.test.mjs` (4 теста) и браузерная проверка с опасными данными: 0 выполненных и 0 внедрённых элементов против 19 и 16 до исправления (`fixes/S1-06/RESULT.md`).
- HTML не кэшируется (`no-cache`), а скрипт подключается с новой версией, поэтому браузеры получают исправленный JS.
- Повторный XSS-аудит не проводился.
