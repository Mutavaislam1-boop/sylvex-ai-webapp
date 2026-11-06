(function (root) {
  'use strict';

  var icon = '<svg class="sx-credit-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.7 15 9l6.3 3-6.3 3-3 6.3L9 15l-6.3-3L9 9l3-6.3Z"/></svg>';

  function amount(value) {
    var safe = String(value == null ? 0 : value).replace(/[<>&"]/g, function (character) {
      return {'<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;'}[character];
    });
    return '<span class="sx-credit-amount notranslate" translate="no">' + icon + '<span>' + safe + '</span></span>';
  }

  root.SYLVEX_CREDIT = {icon: icon, amount: amount};

  var style = document.createElement('style');
  style.textContent = '.sx-credit-amount{display:inline-flex;align-items:center;gap:.32em;white-space:nowrap}.sx-credit-icon{width:1em;height:1em;display:inline-block;fill:#22c55e;filter:drop-shadow(0 1px 2px rgba(34,197,94,.25));flex:0 0 auto}';
  document.head.appendChild(style);
})(window);
