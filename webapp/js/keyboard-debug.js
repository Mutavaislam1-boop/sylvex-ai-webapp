/* SYLVEX Keyboard Debug - a diagnostic panel for the Browser Mini App and the
   Telegram Mini App. It measures what the page really does while the system
   keyboard opens and closes: viewport sizes, the composer's position, gaps,
   overlaps and extra bottom layers, and keeps a short log that can be copied
   as a JSON report.

   It is off for everyone by default. A request to turn it on (?kbdebug=1,
   Telegram startapp=kbdebug, or 7 quick taps on the App Version window)
   is checked by the server (/api/public/keyboard-debug/access): only
   development builds and active SYLVEX admins get the panel. Without that,
   this file adds nothing to the page but a tap counter on the App Version row.

   It only observes: no layout change (the panel is a fixed overlay), no
   change to how the composer is positioned. The report never contains the
   typed text, tokens, personal data or Telegram initData. */
(function () {
  'use strict';

  var FLAG_KEY = 'sylvex-kbdebug';
  var MAX_EVENTS = 200;
  var COMPOSERS = ['.sxs-composer', '#studioComposer', '#homeIdeaForm'];
  var S = (window.SYLVEX = window.SYLVEX || {});
  var tg = function () { return (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) ? window.Telegram.WebApp : null; };

  function flagGet() { try { return localStorage.getItem(FLAG_KEY) === '1'; } catch (e) { return false; } }
  function flagSet(on) { try { if (on) localStorage.setItem(FLAG_KEY, '1'); else localStorage.removeItem(FLAG_KEY); } catch (e) {} }

  // ------------------------------------------------------------ turning on
  function requested() {
    var query = new URLSearchParams(location.search);
    if (query.get('kbdebug') === '0') { flagSet(false); return false; }
    if (query.get('kbdebug') === '1') return true;
    var app = tg();
    if (app && app.initDataUnsafe && app.initDataUnsafe.start_param === 'kbdebug') return true;
    return flagGet();
  }

  var checking = false;
  function requestAccess(fromGesture) {
    if (state || checking) return;
    checking = true;
    var app = tg();
    fetch('/api/public/keyboard-debug/access', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(app ? { initData: app.initData } : {}),
    }).then(function (r) { return r.json(); }).then(function (data) {
      checking = false;
      if (data && data.allowed) { flagSet(true); start(); }
      else { flagSet(false); if (fromGesture) quietToast('Keyboard Debug недоступен'); }
    }).catch(function () { checking = false; });
  }
  function quietToast(text) {
    if (typeof window.toast === 'function') { try { window.toast(text); } catch (e) {} }
  }

  // 7 quick taps on the App Version window (settings -> App Version, then tap
  // the logo/version text): the way in from Telegram. The row itself counts
  // too, as the first tap that opens the window.
  var taps = [];
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target : null;
    var hit = el && (el.closest('[onclick*="openAppVersion"]') || (el.closest('#appVersionModal section') && !el.closest('button')));
    if (!hit) return;
    var now = Date.now();
    taps = taps.filter(function (t) { return now - t < 3000; });
    taps.push(now);
    if (taps.length >= 7) { taps = []; requestAccess(true); }
  }, true);

  S.keyboardDebug = {
    request: function () { requestAccess(true); },
    stop: function () { stop(true); },
    report: function () { return state ? buildReport() : null; },
  };

  // ------------------------------------------------------------ measuring
  var state = null;

  function describe(el) {
    if (!el || el.nodeType !== 1) return '';
    var name = el.tagName.toLowerCase();
    if (el.id) name += '#' + el.id;
    var cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    if (cls.length) name += '.' + cls.join('.');
    return name;
  }
  function rectOf(el) {
    var r = el.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), height: Math.round(r.height), width: Math.round(r.width) };
  }
  function visible(el) {
    if (!el || !el.isConnected) return false;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function isEditable(el) {
    return !!(el && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !/^(button|checkbox|radio|range|file|submit|color)$/i.test(el.type)) || el.isContentEditable));
  }
  function findComposer() {
    var active = document.activeElement;
    if (isEditable(active)) {
      for (var i = 0; i < COMPOSERS.length; i++) {
        var hit = active.closest(COMPOSERS[i]);
        if (hit && visible(hit)) return hit;
      }
    }
    for (var j = 0; j < COMPOSERS.length; j++) {
      var el = document.querySelector(COMPOSERS[j]);
      if (visible(el)) return el;
    }
    return isEditable(active) ? active : null;
  }

  // env(safe-area-inset-*) read from an invisible fixed probe (no layout effect).
  function safeArea() {
    var probe = state && state.probe;
    if (!probe) return null;
    var cs = getComputedStyle(probe);
    return { top: parseFloat(cs.paddingTop) || 0, right: parseFloat(cs.paddingRight) || 0, bottom: parseFloat(cs.paddingBottom) || 0, left: parseFloat(cs.paddingLeft) || 0 };
  }
  function telegramInfo() {
    var app = tg();
    if (!app) return null;
    var pick = function (o) { return o ? { top: o.top || 0, bottom: o.bottom || 0, left: o.left || 0, right: o.right || 0 } : null; };
    return {
      platform: app.platform || '', version: app.version || '',
      viewportHeight: Math.round(app.viewportHeight || 0), viewportStableHeight: Math.round(app.viewportStableHeight || 0),
      isExpanded: !!app.isExpanded, isFullscreen: !!app.isFullscreen,
      safeAreaInset: pick(app.safeAreaInset), contentSafeAreaInset: pick(app.contentSafeAreaInset),
    };
  }

  function measure() {
    var vv = window.visualViewport;
    var innerH = window.innerHeight;
    var vvTop = vv ? vv.offsetTop : 0;
    var vvH = vv ? vv.height : innerH;
    var visibleBottom = vvTop + vvH;            // in layout-viewport coordinates, like getBoundingClientRect
    var active = document.activeElement;
    var editable = isEditable(active) && !(state && state.panel && state.panel.contains(active));
    var sa = safeArea();
    var t = telegramInfo();
    // Layout overlap only: it reads 0 when iOS pans the visual viewport
    // (offsetTop grows by what height lost), so it never decides alone.
    var overlap = Math.max(0, Math.round(innerH - vvH - vvTop));
    // Heights before the keyboard opened: taken only while no field is
    // focused, never replaced by a shrunk value - just after a blur (the
    // keyboard still closing) they may only grow - and reset on rotation.
    var base = state.base;
    var width = vv ? vv.width : window.innerWidth;
    if (base.width !== width) { base.width = width; base.visible = 0; base.inner = 0; }
    if (!editable) {
      var settled = Date.now() - base.blurAt > 700;
      if (!base.visible || vvH > base.visible || settled) base.visible = vvH;
      if (!base.inner || innerH > base.inner || settled) base.inner = innerH;
    } else {
      if (!base.visible) base.visible = vvH;
      if (!base.inner) base.inner = innerH;
    }
    var keyboardHeight = Math.max(0, Math.round(base.visible - vvH));
    var shrink = Math.max(0, Math.round(base.inner - innerH));
    var tgShrink = t && t.viewportStableHeight && t.viewportHeight ? Math.max(0, t.viewportStableHeight - t.viewportHeight) : 0;
    var keyboardOpen = editable && (keyboardHeight > 80 || tgShrink > 80);
    var composer = findComposer();
    var m = {
      innerHeight: innerH,
      clientHeight: document.documentElement.clientHeight,
      visualViewport: vv ? { height: Math.round(vvH), width: Math.round(vv.width), offsetTop: Math.round(vvTop), pageTop: Math.round(vv.pageTop), scale: Number(vv.scale.toFixed(3)) } : null,
      scrollY: Math.round(window.scrollY),
      visibleBottom: Math.round(visibleBottom),
      baseVisibleHeight: Math.round(base.visible),
      keyboardHeight: keyboardHeight,
      keyboardOverlap: overlap,
      innerHeightShrink: shrink,
      telegramViewportShrink: tgShrink,
      keyboard: keyboardOpen ? 'open (presumed)' : 'closed (presumed)',
      focused: editable ? describe(active) : '',
      safeArea: sa,
      telegram: t,
      // What Standard's own keyboard rule decided (standard-studio.js).
      standard: typeof S.standardKeyboard === 'function' ? S.standardKeyboard() : null,
      composer: null,
      issues: [],
    };
    if (composer) {
      var r = rectOf(composer);
      // When the keyboard is closed the safe-area bottom is the real floor.
      var floor = visibleBottom - (keyboardOpen ? 0 : (sa ? sa.bottom : 0)) - (keyboardOpen || !t || !t.contentSafeAreaInset ? 0 : t.contentSafeAreaInset.bottom);
      m.composer = { element: describe(composer), rect: r, gapToVisibleBottom: Math.round(visibleBottom - r.bottom), gapToSafeFloor: Math.round(floor - r.bottom), heightShareOfVisible: Number((r.height / Math.max(1, vvH)).toFixed(2)) };
      findIssues(m, composer, r, visibleBottom, vvTop, vvH, keyboardOpen);
      m.layers = layerProbe(composer, true);
      if (m.layers.covered.length) m.issues.push({ code: 'composer_covered', elements: m.layers.covered, note: 'блок ввода перекрыт сверху: ' + m.layers.covered.join(', ') });
      if (m.layers.paintedOver && m.layers.paintedOver.length) m.issues.push({ code: 'painted_layer_over_composer', elements: m.layers.paintedOver.map(function (x) { return x.element; }), note: 'окрашенный слой поверх блока ввода (невидим для elementsFromPoint)' });
      if (m.layers.studio && m.layers.studio.position === 'fixed' && m.layers.studio.fixedRelativeTo !== 'viewport') m.issues.push({ code: 'fixed_not_screen', element: m.layers.studio.fixedRelativeTo.element, note: 'position: fixed студии отсчитывается не от экрана, а от ' + m.layers.studio.fixedRelativeTo.element });
    }
    return m;
  }

  function findIssues(m, composer, r, visibleBottom, vvTop, vvH, keyboardOpen) {
    var issues = m.issues;
    if (r.bottom > visibleBottom + 1) issues.push({ code: 'composer_below_visible_area', px: Math.round(r.bottom - visibleBottom), note: 'низ блока ввода за видимой областью' + (keyboardOpen ? ' (под клавиатурой)' : '') });
    if (r.top < vvTop - 1) issues.push({ code: 'composer_above_visible_area', px: Math.round(vvTop - r.top), note: 'верх блока ввода выше видимой области' });
    if (r.height > vvH * 0.6) issues.push({ code: 'composer_too_tall', share: Number((r.height / vvH).toFixed(2)), note: 'блок ввода занимает больше 60% видимой высоты' });
    var gap = Math.round(visibleBottom - r.bottom);
    if (keyboardOpen && gap > 24) issues.push({ code: 'gap_above_keyboard', px: gap, note: 'зазор между блоком ввода и клавиатурой (предполагаемо)' });
    // With the keyboard open: what sits between the composer and the keyboard
    // (the composer's own containers are its background, not an extra layer).
    if (keyboardOpen && gap > 2) {
      var y = Math.round(r.bottom + gap / 2);
      var seen = {};
      [0.1, 0.5, 0.9].forEach(function (fx) {
        var x = Math.round(window.innerWidth * fx);
        (document.elementsFromPoint(x, y) || []).slice(0, 4).forEach(function (el) {
          if (el === document.documentElement || el === document.body || el.contains(composer) || (state.panel && state.panel.contains(el))) return;
          var key = describe(el);
          if (seen[key]) return;
          seen[key] = 1;
          var cs = getComputedStyle(el);
          var painted = (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent') || cs.backgroundImage !== 'none' || cs.boxShadow !== 'none';
          if (painted || cs.position === 'fixed' || cs.position === 'sticky') {
            issues.push({ code: 'layer_below_composer', element: key, position: cs.position, background: cs.backgroundColor, rect: rectOf(el), note: 'видимый слой между блоком ввода и низом экрана' });
          }
        });
      });
    }
    // Fixed/sticky elements overlapping the composer or sticking out under the keyboard.
    var all = document.body.getElementsByTagName('*');
    var limit = Math.min(all.length, 4000);
    var found = 0;
    for (var i = 0; i < limit && found < 8; i++) {
      var el = all[i];
      if (el === composer || composer.contains(el) || el.contains(composer) || (state.panel && state.panel.contains(el)) || el === state.probe) continue;
      var cs = getComputedStyle(el);
      if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
      if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0 || cs.pointerEvents === 'none' && cs.backgroundColor === 'rgba(0, 0, 0, 0)') continue;
      var b = el.getBoundingClientRect();
      if (b.width < 2 || b.height < 2) continue;
      var overlaps = b.bottom > r.top && b.top < r.bottom && b.right > r.left && b.left < r.right;
      var full = b.width >= window.innerWidth - 2 && b.height >= window.innerHeight - 2;
      if (overlaps && !full) { issues.push({ code: 'overlaps_composer', element: describe(el), position: cs.position, zIndex: cs.zIndex, rect: rectOf(el), note: 'фиксированный элемент пересекает блок ввода' }); found++; }
      else if (keyboardOpen && b.bottom > visibleBottom + 1 && b.top < visibleBottom && b.height < vvH * 0.5) { issues.push({ code: 'bottom_panel_under_keyboard', element: describe(el), rect: rectOf(el), note: 'нижняя панель частично под клавиатурой' }); found++; }
    }
  }

  // ------------------------------------------------------------ layers
  // What is really painted over the composer: the top elements at several
  // points of it (document.elementsFromPoint), with the CSS that decides
  // painting and their parents; painted elements hit-testing cannot see
  // (pointer-events: none), full-screen ones included; what fills the bottom
  // of the screen; and whether position: fixed of the pinned studio is really
  // relative to the screen.
  var LAYER_PROPS = ['position', 'zIndex', 'opacity', 'visibility', 'pointerEvents', 'backgroundColor', 'backgroundImage', 'backdropFilter', 'transform', 'filter', 'mixBlendMode', 'overflow'];
  var LAYER_DEFAULTS = { position: 'static', zIndex: 'auto', opacity: '1', visibility: 'visible', pointerEvents: 'auto', backgroundColor: 'rgba(0, 0, 0, 0)', backgroundImage: 'none', backdropFilter: 'none', transform: 'none', filter: 'none', mixBlendMode: 'normal', overflow: 'visible' };
  function cssOf(el) {
    var cs = getComputedStyle(el), out = {};
    LAYER_PROPS.forEach(function (k) {
      var v = cs[k];
      if (v != null && v !== '' && v !== LAYER_DEFAULTS[k]) out[k] = k === 'backgroundImage' ? String(v).slice(0, 40) : v;
    });
    return out;
  }
  function parentsOf(el, n) {
    var out = [];
    for (var p = el.parentElement; p && p !== document.documentElement && out.length < n; p = p.parentElement) out.push(describe(p));
    return out;
  }
  function inPanel(el) { return !!(state && state.panel && state.panel.contains(el)); }
  // The box position: fixed is relative to: the screen, unless an ancestor
  // has a transform, filter, contain... - then that ancestor.
  function fixedBoxOf(node) {
    for (var n = node.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      var cs = getComputedStyle(n);
      if (cs.transform !== 'none' || cs.perspective !== 'none' || cs.filter !== 'none' || (cs.backdropFilter && cs.backdropFilter !== 'none')
        || /paint|layout|strict|content/.test(cs.contain || '') || /transform|perspective|filter/.test(cs.willChange || '')
        || (cs.containerType && cs.containerType !== 'normal')) {
        return { element: describe(n), transform: cs.transform, filter: cs.filter, willChange: cs.willChange, contain: cs.contain };
      }
    }
    return 'viewport';
  }
  function scrolledAncestors(node) {
    var out = [];
    for (var n = node.parentElement; n; n = n.parentElement) {
      if (n.scrollTop || n.scrollLeft) out.push({ element: describe(n), scrollTop: Math.round(n.scrollTop), scrollLeft: Math.round(n.scrollLeft), overflow: getComputedStyle(n).overflowY });
    }
    return out;
  }
  function probePoints(r) {
    return [[0.12, 0.2], [0.5, 0.2], [0.88, 0.2], [0.12, 0.85], [0.5, 0.55], [0.88, 0.85]].map(function (f) {
      return [Math.round(r.left + r.width * f[0]), Math.round(r.top + r.height * f[1])];
    });
  }
  function hitAt(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return null;
    return { element: describe(el), background: getComputedStyle(el).backgroundColor };
  }
  function layerProbe(composer, full) {
    var r = composer.getBoundingClientRect();
    var vv = window.visualViewport;
    var visibleBottom = vv ? vv.offsetTop + vv.height : window.innerHeight;
    var studio = composer.closest('.studio');
    var points = probePoints(r).map(function (p) {
      var stack = (document.elementsFromPoint(p[0], p[1]) || []).filter(function (el) { return !inPanel(el); });
      var top = stack[0];
      var entry = { x: p[0], y: p[1], covered: !!(top && !composer.contains(top)), top: top ? describe(top) : null };
      if (full) entry.stack = stack.slice(0, 5).map(function (el) { return { element: describe(el), inComposer: composer.contains(el), css: cssOf(el), parents: parentsOf(el, 3) }; });
      return entry;
    });
    var out = {
      composer: [Math.round(r.top), Math.round(r.bottom)],
      covered: points.filter(function (p) { return p.covered; }).map(function (p) { return p.top; }),
      points: points,
      bottomOfScreen: hitAt(Math.round(window.innerWidth / 2), Math.max(0, window.innerHeight - 3)),
      bottomOfVisible: hitAt(Math.round(window.innerWidth / 2), Math.max(0, Math.round(visibleBottom) - 3)),
    };
    if (studio) {
      var s = studio.getBoundingClientRect();
      out.studio = { rect: [Math.round(s.top), Math.round(s.bottom)], position: getComputedStyle(studio).position, fixedRelativeTo: fixedBoxOf(studio), scrolledAncestors: scrolledAncestors(studio) };
    }
    if (full) {
      // Painted layers over the composer that hit-testing does not report.
      var silent = [];
      var all = document.body.getElementsByTagName('*');
      for (var i = 0, n = Math.min(all.length, 5000); i < n && silent.length < 10; i++) {
        var el = all[i];
        if (el === composer || composer.contains(el) || el.contains(composer) || inPanel(el) || el === state.probe) continue;
        var cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0 || cs.position === 'static') continue;
        var painted = (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent') || cs.backgroundImage !== 'none' || (cs.backdropFilter && cs.backdropFilter !== 'none') || cs.boxShadow !== 'none';
        if (!painted) continue;
        var b = el.getBoundingClientRect();
        if (b.width < 2 || b.height < 2 || !(b.bottom > r.top && b.top < r.bottom && b.right > r.left && b.left < r.right)) continue;
        silent.push({ element: describe(el), css: cssOf(el), rect: [Math.round(b.top), Math.round(b.bottom), Math.round(b.left), Math.round(b.right)], parents: parentsOf(el, 3) });
      }
      out.paintedOver = silent;
    }
    return out;
  }

  // ------------------------------------------------------------ frames
  // Automatic snapshots, every animation frame, from a focus change (or a
  // viewport change) until the screen settles: coordinates and what is on
  // top, so a layer that shows only while the keyboard moves is caught. Kept
  // after the keyboard closes and across reloads (localStorage, no text).
  var BURSTS_KEY = 'sylvex-kbdebug-frames';
  var MAX_BURSTS = 12;
  var MAX_FRAMES = 150;
  function frameSnapshot(burst) {
    var vv = window.visualViewport;
    var composer = findComposer();
    var app = tg();
    var f = {
      t: Math.round(performance.now() - burst.t0),
      innerHeight: window.innerHeight,
      vv: vv ? [Math.round(vv.height), Math.round(vv.offsetTop), Math.round(vv.pageTop)] : null,
      scrollY: Math.round(window.scrollY),
      focused: isEditable(document.activeElement) && !inPanel(document.activeElement),
    };
    if (app) f.tg = [Math.round(app.viewportHeight || 0), Math.round(app.viewportStableHeight || 0)];
    var root = document.documentElement.style;
    f.pin = [root.getPropertyValue('--sxs-vv-top'), root.getPropertyValue('--sxs-vv-h')];
    if (composer) {
      var p = layerProbe(composer, false);
      f.composer = p.composer;
      f.covered = p.covered;
      f.bottomOfScreen = p.bottomOfScreen;
      f.bottomOfVisible = p.bottomOfVisible;
      if (p.studio) { f.studio = p.studio.rect; f.fixedRelativeTo = typeof p.studio.fixedRelativeTo === 'string' ? p.studio.fixedRelativeTo : p.studio.fixedRelativeTo.element; f.scrolled = p.studio.scrolledAncestors; }
    }
    return f;
  }
  function startBurst(reason) {
    if (!state) return;
    var now = performance.now();
    if (state.burst) { state.burst.until = Math.min(state.burst.t0 + 4000, Math.max(state.burst.until, now + 700)); return; }
    state.burst = { reason: reason, at: new Date().toISOString(), t0: now, until: now + 1500, frames: [] };
    var composer = findComposer();
    if (composer) state.burst.layersAtStart = layerProbe(composer, true);
    var step = function () {
      if (!state || !state.burst) return;
      var b = state.burst;
      if (b.frames.length < MAX_FRAMES) b.frames.push(frameSnapshot(b));
      if (performance.now() < b.until) { state.burstFrame = requestAnimationFrame(step); return; }
      finishBurst();
    };
    state.burstFrame = requestAnimationFrame(step);
  }
  function finishBurst() {
    var b = state.burst;
    state.burst = null;
    if (!b) return;
    var composer = findComposer();
    if (composer) b.layersAtEnd = layerProbe(composer, true);
    b.coveredFrames = b.frames.filter(function (f) { return f.covered && f.covered.length; }).length;
    delete b.t0;
    delete b.until;
    state.bursts.push(b);
    while (state.bursts.length > MAX_BURSTS) state.bursts.shift();
    saveBursts();
    log('frames_recorded', { reason: b.reason, frames: b.frames.length, coveredFrames: b.coveredFrames });
  }
  function saveBursts() {
    try { localStorage.setItem(BURSTS_KEY, JSON.stringify({ savedAt: new Date().toISOString(), bursts: state.bursts })); } catch (e) {}
  }
  function loadBursts() {
    try { var saved = JSON.parse(localStorage.getItem(BURSTS_KEY) || 'null'); return saved && saved.bursts ? saved : null; } catch (e) { return null; }
  }

  // A log entry keeps the layer verdict, not the full element stacks (those
  // are in the current snapshot and at the start/end of each frame series).
  function compactForLog(m) {
    var out = {};
    Object.keys(m).forEach(function (k) { out[k] = m[k]; });
    if (m.layers) {
      var s = m.layers.studio;
      out.layers = {
        covered: m.layers.covered,
        paintedOver: (m.layers.paintedOver || []).map(function (x) { return x.element; }),
        bottomOfScreen: m.layers.bottomOfScreen,
        bottomOfVisible: m.layers.bottomOfVisible,
        studio: s ? { rect: s.rect, fixedRelativeTo: typeof s.fixedRelativeTo === 'string' ? s.fixedRelativeTo : s.fixedRelativeTo.element, scrolledAncestors: s.scrolledAncestors } : null,
      };
    }
    return out;
  }

  // ------------------------------------------------------------ log
  function log(type, extra) {
    var m = measure();
    var entry = { t: Math.round(performance.now() - state.t0), at: new Date().toISOString(), type: type };
    if (extra) entry.detail = extra;
    entry.m = compactForLog(m);
    // The phases the report is read by.
    var wasOpen = state.keyboardOpen;
    var isOpen = m.keyboard.indexOf('open') === 0;
    if (type === 'focusin' && !wasOpen) entry.phase = 'before_keyboard';
    if (isOpen && !wasOpen) entry.phase = 'keyboard_opened';
    if (!isOpen && wasOpen) entry.phase = 'keyboard_closed';
    state.keyboardOpen = isOpen;
    var last = state.events[state.events.length - 1];
    if (!entry.phase && last && last.type === type && JSON.stringify(last.m) === JSON.stringify(entry.m)) return render(m);
    state.events.push(entry);
    if (state.events.length > MAX_EVENTS) state.events.shift();
    render(m);
  }
  var pending = {};
  function soon(type, extra) {
    if (pending[type]) return;
    pending[type] = requestAnimationFrame(function () { pending[type] = 0; if (state) log(type, extra); });
  }

  // ------------------------------------------------------------ panel
  var CSS = ''
    + '#sxKbDebug{position:fixed;top:calc(env(safe-area-inset-top,0px) + 4px);left:4px;right:4px;z-index:2147483647;max-height:44vh;overflow:auto;'
    + 'font:10.5px/1.35 ui-monospace,Menlo,Consolas,monospace;color:#d9ffd9;background:rgba(8,10,8,.88);border:1px solid rgba(120,255,120,.35);border-radius:10px;'
    + 'padding:6px 8px;box-shadow:0 6px 20px rgba(0,0,0,.4);-webkit-user-select:text;user-select:text;contain:layout paint}'
    + '#sxKbDebug.is-min{right:auto;max-height:none;overflow:visible;padding:4px 8px}'
    + '#sxKbDebug.is-min .kbd-body{display:none}'
    + '#sxKbDebug .kbd-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}'
    + '#sxKbDebug .kbd-head b{color:#7dff7d}'
    + '#sxKbDebug button{font:inherit;color:#0b130b;background:#7dff7d;border:0;border-radius:6px;padding:3px 7px;cursor:pointer}'
    + '#sxKbDebug button.alt{background:#2b3a2b;color:#d9ffd9}'
    + '#sxKbDebug .kbd-grid{display:grid;grid-template-columns:auto 1fr;gap:1px 8px;margin-top:5px}'
    + '#sxKbDebug .kbd-grid span{color:#8fb38f}'
    + '#sxKbDebug .kbd-issue{color:#ffcf6b;margin-top:3px}'
    + '#sxKbDebug .kbd-ok{color:#7dff7d;margin-top:3px}'
    + '#sxKbDebug textarea{width:100%;height:90px;margin-top:5px;font:inherit;color:#d9ffd9;background:#050705;border:1px solid #2b3a2b;border-radius:6px}'
    + '#sxKbDebugProbe{position:fixed;left:0;top:0;width:0;height:0;visibility:hidden;pointer-events:none;'
    + 'padding:env(safe-area-inset-top,0px) env(safe-area-inset-right,0px) env(safe-area-inset-bottom,0px) env(safe-area-inset-left,0px)}';

  function row(label, value) { return '<span>' + label + '</span><div>' + value + '</div>'; }
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function render(m) {
    if (!state) return;
    if (state.panel.classList.contains('is-min')) {
      state.head.textContent = 'KB ' + (m.keyboard.indexOf('open') === 0 ? 'open*' : 'closed*') + ' · ' + (m.composer ? 'gap ' + m.composer.gapToVisibleBottom : '—') + (m.issues.length ? ' · ⚠' + m.issues.length : '');
      return;
    }
    var vv = m.visualViewport || {};
    var c = m.composer;
    var t = m.telegram;
    state.head.textContent = 'Keyboard Debug · ' + m.keyboard;
    state.grid.innerHTML = ''
      + row('innerHeight', m.innerHeight + ' · clientHeight ' + m.clientHeight)
      + row('visualViewport', vv.height != null ? vv.height + ' (top ' + vv.offsetTop + ', pageTop ' + vv.pageTop + ', ×' + vv.scale + ')' : '—')
      + row('scrollY', m.scrollY + ' · видимый низ ' + m.visibleBottom)
      + row('клавиатура*', m.keyboardHeight + 'px (исходно ' + m.baseVisibleHeight + ') · перекрытие ' + m.keyboardOverlap + ' · сжатие ' + m.innerHeightShrink + (t ? ' · tg ' + m.telegramViewportShrink : ''))
      + (m.standard ? row('Standard', (m.standard.open ? 'клавиатура открыта' : 'клавиатура закрыта') + ' · top ' + m.standard.pinTop + ' · h ' + m.standard.pinHeight) : '')
      + row('фокус', esc(m.focused) || '—')
      + row('блок ввода', c ? esc(c.element) + ' top ' + c.rect.top + ' bottom ' + c.rect.bottom + ' h ' + c.rect.height : 'не найден')
      + row('зазор до низа', c ? c.gapToVisibleBottom + 'px · до safe-area ' + c.gapToSafeFloor + 'px' : '—')
      + row('safe-area', m.safeArea ? 't' + m.safeArea.top + ' b' + m.safeArea.bottom : '—')
      + (t ? row('Telegram', 'vh ' + t.viewportHeight + ' / stable ' + t.viewportStableHeight + (t.isExpanded ? ' · expanded' : '') + (t.safeAreaInset ? ' · safe b' + t.safeAreaInset.bottom : '') + (t.contentSafeAreaInset ? ' · content b' + t.contentSafeAreaInset.bottom : '')) : '')
      + (m.layers ? row('слои', m.layers.covered.length ? '⚠ сверху: ' + esc(m.layers.covered.join(', ')) : 'сверху блок ввода')
        + row('fixed от', m.layers.studio ? esc(typeof m.layers.studio.fixedRelativeTo === 'string' ? 'экрана' : m.layers.studio.fixedRelativeTo.element) : '—')
        + row('низ экрана', m.layers.bottomOfScreen ? esc(m.layers.bottomOfScreen.element) + ' ' + esc(m.layers.bottomOfScreen.background) : '—') : '')
      + row('кадры', (state.burst ? 'запись… ' : '') + state.bursts.length + ' серий · ' + state.bursts.reduce(function (n, b) { return n + b.frames.length; }, 0) + ' снимков')
      + row('событий', state.events.length + ' / ' + MAX_EVENTS);
    state.issues.innerHTML = m.issues.length
      ? m.issues.map(function (i) { return '<div class="kbd-issue">⚠ ' + esc(i.note) + (i.px != null ? ' — ' + i.px + 'px' : '') + (i.element ? ' — ' + esc(i.element) : '') + '</div>'; }).join('')
      : '<div class="kbd-ok">подозрительных элементов не найдено</div>';
  }

  function buildReport() {
    var nav = navigator;
    var t = telegramInfo();
    return {
      tool: 'SYLVEX Keyboard Debug',
      generatedAt: new Date().toISOString(),
      app: t ? 'telegram_mini_app' : 'browser_mini_app',
      page: location.origin + location.pathname,        // no query/hash: Telegram puts its launch data there
      platform: {
        userAgent: nav.userAgent,
        platform: nav.platform || '',
        language: nav.language || '',
        devicePixelRatio: window.devicePixelRatio,
        screen: { width: screen.width, height: screen.height, availHeight: screen.availHeight },
        orientation: (screen.orientation && screen.orientation.type) || '',
        standalone: !!(window.matchMedia && window.matchMedia('(display-mode: standalone)').matches),
        telegram: t ? { platform: t.platform, version: t.version, colorScheme: tg().colorScheme || '' } : null,
        studioUi: document.body.classList.contains('sxs-std') ? 'standard' : (document.body.classList.contains('sxs-pro') ? 'pro' : ''),
      },
      current: measure(),
      events: state.events.slice(),
      // Frame-by-frame snapshots around each keyboard open/close (kept
      // across reloads until "Очистить").
      frames: state.bursts.slice(),
    };
  }

  function copyReport() {
    var text = JSON.stringify(buildReport(), null, 2);
    var done = function () { state.copyBtn.textContent = 'Скопировано'; setTimeout(function () { if (state) state.copyBtn.textContent = 'Скопировать отчёт'; }, 1500); };
    var fallback = function () {
      var area = state.panel.querySelector('textarea') || document.createElement('textarea');
      area.readOnly = true;
      area.value = text;
      if (!area.parentNode) state.body.appendChild(area);
      area.focus();
      area.select();
      try { if (document.execCommand('copy')) return done(); } catch (e) {}
      state.copyBtn.textContent = 'Выделите текст ниже';
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  }

  // ------------------------------------------------------------ start / stop
  function start() {
    if (state) return;
    var saved = loadBursts();
    state = { t0: performance.now(), events: [], keyboardOpen: false, base: { visible: 0, inner: 0, width: 0, blurAt: 0 }, offs: [], bursts: saved ? saved.bursts : [], burst: null };
    var style = document.createElement('style');
    style.id = 'sxKbDebugStyle';
    style.textContent = CSS;
    document.head.appendChild(style);
    state.style = style;
    state.probe = document.createElement('div');
    state.probe.id = 'sxKbDebugProbe';
    document.body.appendChild(state.probe);
    var panel = document.createElement('section');
    panel.id = 'sxKbDebug';
    panel.setAttribute('aria-label', 'Keyboard Debug');
    panel.innerHTML = '<div class="kbd-head"><b class="kbd-title"></b>'
      + '<button type="button" data-kbd="copy">Скопировать отчёт</button>'
      + '<button type="button" class="alt" data-kbd="clear">Очистить</button>'
      + '<button type="button" class="alt" data-kbd="min">Свернуть</button>'
      + '<button type="button" class="alt" data-kbd="off">Выключить</button></div>'
      + '<div class="kbd-body"><div class="kbd-grid"></div><div class="kbd-issues"></div></div>';
    document.body.appendChild(panel);
    state.panel = panel;
    state.head = panel.querySelector('.kbd-title');
    state.grid = panel.querySelector('.kbd-grid');
    state.issues = panel.querySelector('.kbd-issues');
    state.body = panel.querySelector('.kbd-body');
    state.copyBtn = panel.querySelector('[data-kbd="copy"]');
    // Buttons must not steal focus from the field being tested.
    panel.addEventListener('pointerdown', function (e) { if (e.target.closest('button')) e.preventDefault(); });
    panel.addEventListener('click', function (e) {
      var b = e.target.closest('[data-kbd]');
      if (!b) return;
      var a = b.dataset.kbd;
      if (a === 'copy') copyReport();
      else if (a === 'clear') { state.events = []; state.bursts = []; try { localStorage.removeItem(BURSTS_KEY); } catch (err) {} log('cleared'); }
      else if (a === 'min') { panel.classList.toggle('is-min'); b.textContent = panel.classList.contains('is-min') ? 'Развернуть' : 'Свернуть'; render(measure()); }
      else if (a === 'off') stop(true);
    });

    var on = function (target, type, fn, opts) { target.addEventListener(type, fn, opts); state.offs.push(function () { target.removeEventListener(type, fn, opts); }); };
    on(document, 'focusin', function (e) {
      if (panel.contains(e.target)) return;
      log('focusin', describe(e.target));
      if (isEditable(e.target)) startBurst('focusin');
      setTimeout(function () { if (state) soon('after_focus'); }, 350);
    }, true);
    on(document, 'focusout', function (e) {
      if (panel.contains(e.target)) return;
      state.base.blurAt = Date.now();
      log('focusout', describe(e.target));
      if (isEditable(e.target)) startBurst('focusout');
      setTimeout(function () { if (state) soon('after_blur'); }, 350);
    }, true);
    // Typing: only that it happened (never what was typed), at most once a second.
    var lastTyping = 0;
    on(document, 'input', function (e) {
      if (panel.contains(e.target) || !isEditable(e.target)) return;
      var now = Date.now();
      if (now - lastTyping < 1000) return;
      lastTyping = now;
      log('typing', describe(e.target));
    }, true);
    on(window, 'resize', function () { soon('window_resize'); });
    on(window, 'orientationchange', function () { log('orientationchange'); setTimeout(function () { if (state) log('orientation_settled'); }, 500); });
    on(window, 'scroll', function () { soon('window_scroll'); }, { passive: true });
    if (window.visualViewport) {
      // A resize after a series ended (a WebView growing back late) starts a
      // new one; during a series it only extends it.
      on(window.visualViewport, 'resize', function () { soon('visualViewport_resize'); startBurst('visualViewport_resize'); });
      on(window.visualViewport, 'scroll', function () { soon('visualViewport_scroll'); });
    }
    var app = tg();
    if (app && app.onEvent) {
      ['viewportChanged', 'safeAreaChanged', 'contentSafeAreaChanged', 'fullscreenChanged'].forEach(function (name) {
        var fn = function (ev) {
          log('telegram_' + name, ev && typeof ev.isStateStable === 'boolean' ? { isStateStable: ev.isStateStable } : null);
          if (name === 'viewportChanged') startBurst('telegram_viewportChanged');
        };
        app.onEvent(name, fn);
        state.offs.push(function () { try { app.offEvent(name, fn); } catch (e) {} });
      });
    }
    // The composer can be replaced (mode switch, Standard/Pro): watch whichever is current.
    if (window.ResizeObserver) {
      state.ro = new ResizeObserver(function () { soon('composer_resize'); });
      var watchComposer = function () {
        var el = findComposer();
        if (el === state.watched) return;
        if (state.watched) state.ro.unobserve(state.watched);
        state.watched = el;
        if (el) state.ro.observe(el);
      };
      watchComposer();
      state.watchTimer = setInterval(watchComposer, 1000);
    }
    log('start');
  }

  function stop(clearFlag) {
    if (!state) return;
    state.offs.forEach(function (off) { off(); });
    if (state.ro) state.ro.disconnect();
    clearInterval(state.watchTimer);
    if (state.burstFrame) cancelAnimationFrame(state.burstFrame);
    Object.keys(pending).forEach(function (k) { cancelAnimationFrame(pending[k]); pending[k] = 0; });
    [state.panel, state.probe, state.style].forEach(function (n) { if (n && n.parentNode) n.parentNode.removeChild(n); });
    state = null;
    if (clearFlag) flagSet(false);
  }

  if (requested()) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { requestAccess(false); });
    else requestAccess(false);
  }
})();
