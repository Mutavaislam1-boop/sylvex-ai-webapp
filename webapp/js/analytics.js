/*
 * SYLVEX usage analytics - which parts of SYLVEX people use, for the Admin
 * Console's "Analytics" section. The same file runs in the Mini Apps
 * (Telegram and browser) and on the website.
 *
 * Only what is needed for counts is sent: the event, the section, a tool /
 * style / template / reference id, a model id, how long a section was open,
 * the platform and a random visitor id kept in this browser. Never a prompt,
 * a file, a name or any other personal content. Generations and their
 * results are counted on the server from the jobs themselves.
 *
 *   SylvexAnalytics.track('section_open', { section: 'media' })
 *   SylvexAnalytics.track('model_select', { model: 'seedream_5_0' })
 *   SylvexAnalytics.track('tool_open', { item: 'remove_bg', kind: 'tool' })
 *   SylvexAnalytics.track('item_select', { item: 'photo_09', kind: 'style' })
 *   SylvexAnalytics.track('download', { section: 'pro_studio' })
 */
(function (global) {
  'use strict';
  if (global.SylvexAnalytics) return;

  var EVENTS = { section_open: 1, section_leave: 1, model_select: 1, tool_open: 1, item_select: 1, download: 1 };
  var ENDPOINT = '/api/public/analytics/events';
  var queue = [];
  var timer = 0;
  var current = { section: '', since: 0 };
  var config = { base: '', surface: '' };

  function visitorId() {
    var key = 'sylvex-analytics-visitor';
    try {
      var id = localStorage.getItem(key);
      if (!id) {
        id = 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
        localStorage.setItem(key, id);
      }
      return id;
    } catch (_) {
      return '';
    }
  }

  function surface() {
    if (config.surface) return config.surface;
    var tg = global.Telegram && global.Telegram.WebApp;
    return tg && tg.initData ? 'telegram_miniapp' : 'browser_miniapp';
  }

  function clean(value) {
    return String(value == null ? '' : value).toLowerCase().replace(/[^a-z0-9_.:-]/g, '_').slice(0, 64);
  }

  function flush(useBeacon) {
    if (timer) { clearTimeout(timer); timer = 0; }
    if (!queue.length) return;
    var body = JSON.stringify({ visitor: visitorId(), surface: surface(), events: queue.splice(0, 30) });
    var url = String(config.base || '').replace(/\/$/, '') + ENDPOINT;
    try {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body, keepalive: !!useBeacon, credentials: 'omit' })
        .catch(function () {});
    } catch (_) {}
    if (queue.length) flush(useBeacon);
  }

  function push(event, props) {
    var p = props || {};
    queue.push({
      event: event, section: clean(p.section || current.section), item: clean(p.item), kind: clean(p.kind),
      model: clean(p.model), duration_ms: Math.max(0, Math.round(Number(p.duration_ms) || 0)),
    });
    if (queue.length >= 20) flush(false);
    else if (!timer) timer = setTimeout(function () { flush(false); }, 4000);
  }

  function leave() {
    if (current.section && current.since) {
      push('section_leave', { section: current.section, duration_ms: Date.now() - current.since });
    }
    current.since = 0;
  }

  function track(event, props) {
    if (!EVENTS[event]) return;
    try {
      if (event === 'section_open') {
        var section = clean(props && props.section);
        if (!section || section === current.section) return;
        leave();
        current = { section: section, since: Date.now() };
      }
      push(event, props);
    } catch (_) {}
  }

  function configure(options) {
    config.base = (options && options.base) || config.base;
    config.surface = (options && options.surface) || config.surface;
  }

  // Time in a section ends when the page goes to the background or closes.
  if (global.document) {
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') { leave(); flush(true); }
      else if (current.section && !current.since) current.since = Date.now();
    });
    global.addEventListener('pagehide', function () { leave(); flush(true); });
  }

  global.SylvexAnalytics = { track: track, configure: configure, flush: flush, _queue: queue };
})(typeof window !== 'undefined' ? window : globalThis);
