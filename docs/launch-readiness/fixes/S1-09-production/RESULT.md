# S1-09 / B13 — заголовки безопасности (закрыто)

- **Сайт `806ac3ed`** (деплой 08.11 21:11Z, SUCCESS) отдаёт четыре заголовка:
  - HSTS, только для sylvex.ai;
  - CSP: `frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; object-src 'none'; base-uri 'self'`;
  - `nosniff`;
  - `Referrer-Policy: strict-origin-when-cross-origin`.
- **API `36b56ef1`** (21:19Z, SUCCESS): `nosniff` и Referrer-Policy для страниц и статики Mini App. Ответы `/api/*` не менялись.
- **Тесты.** Новые тесты падают на старом коде и проходят на новом. Новых падений нет: в API те же 3 старых, на сайте те же 4.
- **Владелец подтвердил:** HTTP/2 200 и все четыре заголовка; сайт, Pro Studio, вход и Telegram Mini App работают (08.11 21:52Z и 22:04Z).
- **Ограничение.** Claude живые заголовки не проверял: сеть сессии блокирует sylvex.ai.
