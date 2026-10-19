// Client boundary for the shared SYLVEX Core.
// Telegram initData is attached only inside the real Telegram client. The
// standalone Browser Mini App uses only the signed web-session cookie and
// removes legacy identity fields constructed by shared UI code.
(function () {
  'use strict';
  if (window.__sylvexAuthenticatedFetch) return;
  window.__sylvexAuthenticatedFetch = true;
  const originalFetch = window.fetch.bind(window);
  function stripBrowserIdentity(url, options) {
    ['telegram_id', 'initData', 'init_data'].forEach((key) => url.searchParams.delete(key));
    const body = options.body;
    if (body instanceof FormData) {
      body.delete('telegram_id'); body.delete('initData'); body.delete('init_data'); body.delete('initDataUnsafe');
    } else if (body instanceof URLSearchParams) {
      body.delete('telegram_id'); body.delete('initData'); body.delete('init_data');
    } else if (typeof body === 'string') {
      try {
        const json = JSON.parse(body);
        if (json && typeof json === 'object' && !Array.isArray(json)) {
          delete json.telegram_id; delete json.initData; delete json.init_data; delete json.initDataUnsafe;
          options.body = JSON.stringify(json);
        }
      } catch (_) {}
    }
    return url;
  }
  window.__sylvexApiAuthOptions = function (input, init) {
    const options = Object.assign({}, init || {});
    const source = input instanceof Request ? input.url : String(input);
    let url;
    try { url = new URL(source, window.location.href); } catch (_) { return options; }
    if (url.origin === window.location.origin && (url.pathname.startsWith('/api/') || url.pathname === '/save-settings')) {
      const tg = window.Telegram && window.Telegram.WebApp;
      const signed = tg && tg.initData;
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      if (signed) headers.set('X-Telegram-Init-Data', signed);
      else {
        headers.delete('X-Telegram-Init-Data');
        stripBrowserIdentity(url, options);
        options.__sylvexBrowserUrl = url.toString();
      }
      options.headers = headers;
      if (!options.credentials) options.credentials = 'same-origin';
    }
    return options;
  };
  window.fetch = function (input, init) {
    const options = window.__sylvexApiAuthOptions(input, init);
    const target = options.__sylvexBrowserUrl || input;
    delete options.__sylvexBrowserUrl;
    return originalFetch(target, options);
  };
})();
