/* SYLVEX token (credit) icon for HTML built in JS. The icon itself is drawn
   by css/token-icon.css as .sx-token.

   Keep this file byte-identical in sylvex-ai-webapp/webapp/js/token-icon.js
   and sylvex-website/js/token-icon.js.

   SylvexToken.ICON   - the icon markup, for HTML strings.
   SylvexToken.MARK   - '{token}', the icon's place in plain-text strings
                        (translations, data attributes) until they are
                        rendered as HTML.
   SylvexToken.text() - escapes text and shows {token}, and the token mark
                        of text from the API or saved history
                        (generation_cost "12 \u26A1", the pricing catalog),
                        as the icon.
   SylvexToken.PATH / COLOR / STROKE - the same icon (24x24 path) for canvas
                        drawing (the store's 3D Lanyard card). */
(function (root) {
  'use strict';

  var ICON = '<i class="sx-token" aria-hidden="true"></i>';
  var MARK = '{token}';
  var PATH = 'M12.983 21.186a1 1 0 0 1-1.966 0 10 10 0 0 0-8.203-8.203 1 1 0 0 1 0-1.966 10 10 0 0 0 8.203-8.203 1 1 0 0 1 1.966 0 10 10 0 0 0 8.203 8.203 1 1 0 0 1 0 1.966 10 10 0 0 0-8.203 8.203';
  // {token}, and the API's text token mark (kept there: the Telegram bot
  // shows API text as is).
  var MARKS = /\{token\}|\u26A1\uFE0F?/g;

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function text(value) {
    return escapeHtml(value).replace(MARKS, ICON);
  }

  root.SylvexToken = { ICON: ICON, MARK: MARK, PATH: PATH, COLOR: '#20d35d', STROKE: 2.5, text: text };
})(typeof window !== 'undefined' ? window : globalThis);
