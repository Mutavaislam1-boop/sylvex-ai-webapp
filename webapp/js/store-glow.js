/* SYLVEX Store: every subscription and purchase card (js/store-cards.js
   .sxs-card - plans, Business, credit packages, custom amount) wrapped in
   the React Bits BorderGlow (store_glow/src, published files unchanged,
   built into js/vendor/store-glow/ and loaded on demand).

   Keep this file byte-identical in sylvex-ai-webapp/webapp/js/store-glow.js
   and sylvex-website/js/store-glow.js, like js/store-cards.js.

   The card element itself is moved inside the glow - its listeners, state
   and the Store's in-place updates keep working; nothing about prices or
   checkout is touched. Hosts call SylvexStoreGlowCards.watch(container)
   after rendering their cards; re-renders are picked up automatically.
   Surface: the task's #120F17 on dark themes, the card's own colour on
   light ones (dark text must stay readable). */
(function (root) {
  'use strict';

  var VERSION = 'store-glow-soft-20261019';
  var BASE = scriptBase();
  var BUNDLE_JS = BASE + 'js/vendor/store-glow/store-glow.js?v=' + VERSION;
  var BUNDLE_CSS = BASE + 'js/vendor/store-glow/store-glow.css?v=' + VERSION;
  var DARK_SURFACE = '#120F17';

  function scriptBase() {
    var script = typeof document !== 'undefined' ? document.currentScript : null;
    var match = script && script.src ? /^(.*\/)js\/store-glow\.js(?:[?#].*)?$/.exec(script.src) : null;
    return match ? match[1] : '';
  }

  var bundle = null;
  function loadBundle() {
    if (root.SylvexStoreGlow) return Promise.resolve(root.SylvexStoreGlow);
    if (bundle) return bundle;
    bundle = new Promise(function (resolve, reject) {
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = BUNDLE_CSS;
      document.head.appendChild(link);
      var script = document.createElement('script');
      script.src = BUNDLE_JS;
      script.async = true;
      script.onload = function () {
        if (root.SylvexStoreGlow) resolve(root.SylvexStoreGlow);
        else reject(new Error('store_glow_empty'));
      };
      script.onerror = function () { reject(new Error('store_glow_failed')); };
      document.head.appendChild(script);
    }).catch(function (error) {
      bundle = null;
      throw error;
    });
    return bundle;
  }

  // rgb()/rgba() -> #rrggbb (BorderGlow's light-surface check reads hex).
  function toHex(color) {
    var parts = String(color || '').match(/[\d.]+/g);
    if (!parts || parts.length < 3) return '';
    return '#' + parts.slice(0, 3).map(function (n) {
      var v = Math.max(0, Math.min(255, Math.round(Number(n))));
      return (v < 16 ? '0' : '') + v.toString(16);
    }).join('');
  }

  function isLight(hex) {
    var v = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex || '');
    if (!v) return false;
    return parseInt(v[1], 16) * 0.2126 + parseInt(v[2], 16) * 0.7152 + parseInt(v[3], 16) * 0.0722 > 180;
  }

  // The Store's own card colour for this theme (store-cards.css --sxs-card),
  // read through a probe so theme variables are resolved.
  function surfaceFor(container) {
    var probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none;width:0;height:0;background:var(--sxs-card)';
    container.appendChild(probe);
    var hex = toHex(getComputedStyle(probe).backgroundColor);
    probe.remove();
    return isLight(hex) ? hex : DARK_SURFACE;
  }

  var entries = []; // { host, instance, container }
  var wrapped = typeof WeakSet === 'function' ? new WeakSet() : null;

  function wrap(container) {
    var api = root.SylvexStoreGlow;
    var cards = container.querySelectorAll('.sxs-card');
    if (!api) {
      if (cards.length) loadBundle().then(function () { wrap(container); }).catch(function () {});
      return;
    }
    var surface = null;
    cards.forEach(function (card) {
      if (!wrapped || wrapped.has(card)) return;
      wrapped.add(card);
      if (surface === null) surface = surfaceFor(container);
      var host = document.createElement('div');
      host.className = 'sxs-glow' + (card.classList.contains('sxs-custom') ? ' sxs-glow--custom' : '');
      card.parentNode.insertBefore(host, card);
      entries.push({ host: host, container: container, instance: api.mount(host, card, { backgroundColor: surface }) });
    });
    entries = entries.filter(function (entry) {
      if (entry.host.isConnected) return true;
      entry.instance.unmount();
      return false;
    });
  }

  function retheme() {
    var surfaces = new Map();
    entries.forEach(function (entry) {
      if (!entry.host.isConnected) return;
      if (!surfaces.has(entry.container)) surfaces.set(entry.container, surfaceFor(entry.container));
      entry.instance.update({ backgroundColor: surfaces.get(entry.container) });
    });
  }

  var themeWatch = false;
  function watchTheme() {
    if (themeWatch) return;
    themeWatch = true;
    new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    var system = root.matchMedia && root.matchMedia('(prefers-color-scheme: dark)');
    if (system && system.addEventListener) system.addEventListener('change', retheme);
  }

  function watch(container) {
    if (!container || !wrapped) return;
    watchTheme();
    if (!container.__sxsGlowWatch) {
      var pending = false;
      container.__sxsGlowWatch = new MutationObserver(function () {
        if (pending) return;
        pending = true;
        Promise.resolve().then(function () { pending = false; wrap(container); });
      });
      container.__sxsGlowWatch.observe(container, { childList: true, subtree: true });
    }
    wrap(container);
  }

  root.SylvexStoreGlowCards = { watch: watch, surfaceFor: surfaceFor, toHex: toHex, isLight: isLight, BASE: BASE };
})(typeof window !== 'undefined' ? window : globalThis);
