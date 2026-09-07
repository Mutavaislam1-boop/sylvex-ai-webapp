// Attach Telegram credentials only to this application's API, never external URLs.
(function () {
  'use strict';
  if (window.__sylvexAuthenticatedFetch) return;
  window.__sylvexAuthenticatedFetch = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const options = Object.assign({}, init || {});
    const source = input instanceof Request ? input.url : String(input);
    let url;
    try { url = new URL(source, window.location.href); } catch (_) { return originalFetch(input, init); }
    if (url.origin === window.location.origin && (url.pathname.startsWith('/api/') || url.pathname === '/save-settings')) {
      const tg = window.Telegram && window.Telegram.WebApp;
      const signed = tg && tg.initData;
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      if (signed) headers.set('X-Telegram-Init-Data', signed);
      options.headers = headers;
      if (!options.credentials) options.credentials = 'same-origin';
    }
    return originalFetch(input, options);
  };
})();
