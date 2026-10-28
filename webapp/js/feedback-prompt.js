/*
 * Feedback prompt: "How do you like SYLVEX?" - stars (PeekRating: the stars
 * up to the pointer rise, the one under it grows, a tip names the grade, a
 * picked star pops), an optional comment, Send, Remind me later, Don't show
 * again and ×. The page decides when to show it and what each answer does
 * (opts.onAnswer(action, payload) -> Promise). The same file runs in the
 * Mini App (Russian) and on the website (English).
 *
 *   SylvexFeedbackPrompt.open({ lang, theme, onAnswer })
 *   actions: 'send' { rating, text } · 'later' · 'never' · 'close'
 */
(function (global) {
  'use strict';
  if (global.SylvexFeedbackPrompt) return;
  var doc = global.document;
  var EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)';
  var COUNT = 5;
  var reduce = function () { return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches); };

  var TEXT = {
    ru: {
      title: 'Как вам SYLVEX?', sub: 'Оцените проект — это помогает нам становиться лучше.',
      labels: ['Плохо', 'Так себе', 'Хорошо', 'Отлично', 'Превосходно'], rating: 'Оценка проекта',
      placeholder: 'Что понравилось или что улучшить? (необязательно)',
      send: 'Отправить отзыв', later: 'Напомнить позже', never: 'Больше не показывать', close: 'Закрыть',
      pick: 'Поставьте оценку звёздами', thanks: 'Спасибо за отзыв!', thanksNote: 'Мы читаем каждый отзыв.', failed: 'Не удалось отправить. Попробуйте ещё раз.',
      of: 'из',
    },
    en: {
      title: 'How do you like SYLVEX?', sub: 'Rate the project — it helps us get better.',
      labels: ['Poor', 'Fair', 'Good', 'Great', 'Superb'], rating: 'Project rating',
      placeholder: 'What did you like, or what should we improve? (optional)',
      send: 'Send feedback', later: 'Remind me later', never: "Don't show again", close: 'Close',
      pick: 'Choose a rating with the stars', thanks: 'Thank you for your feedback!', thanksNote: 'We read every review.', failed: 'Could not send. Please try again.',
      of: 'of',
    },
  };
  var STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.75 5.6 6.15.9-4.45 4.33 1.05 6.12L12 16.87l-5.5 2.88 1.05-6.12L3.1 9.3l6.15-.9z"/></svg>';
  var CLOSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  var CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';

  var state = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ---------------------------------------------------------- PeekRating
  // hover: the star under the pointer (0-based) while previewing, or null.
  function paint() {
    var r = state.rating;
    var previewing = r.hover !== null && !r.settled;
    var shown = previewing ? r.hover + 1 : state.value;
    var still = reduce();
    r.lifts.forEach(function (lift, i) {
      var lifted = previewing && !still && i <= r.hover;
      lift.style.transform = lifted ? 'translateY(' + (-r.lift) + 'px) scale(' + (i === r.hover ? r.magnify : 1) + ')' : 'translateY(0px) scale(1)';
      r.glyphs[i].dataset.lit = String(i < shown);
    });
    var tip = r.tip;
    if (previewing) {
      var slot = r.row.clientWidth / COUNT;
      var hidden = tip.dataset.show !== 'true';
      if (hidden) tip.style.transition = 'none';
      tip.textContent = state.t.labels[r.hover];
      tip.style.transform = 'translate(calc(' + slot * (r.hover + 0.5) + 'px - 50%), 0)';
      if (hidden) { void tip.offsetWidth; tip.style.transition = ''; }
      tip.dataset.show = 'true';
    } else {
      tip.dataset.show = 'false';
    }
    var label = state.root.querySelector('.sxf-grade');
    label.textContent = state.value ? state.t.labels[state.value - 1] : '';
    state.root.querySelector('[data-sxf-send]').classList.toggle('is-ready', state.value > 0);
  }

  function setHover(index) {
    var r = state.rating;
    if (index === r.hover) return;
    r.hover = index;
    if (index !== null) r.settled = false;
    paint();
  }

  function indexAt(x, y) {
    var r = state.rating;
    var rect = r.rect;
    if (!rect || !rect.width) return null;
    if (r.pressing && (y < rect.top - r.size || y > rect.bottom + r.size)) return null;
    return Math.min(COUNT - 1, Math.max(0, Math.floor(((x - rect.left) / rect.width) * COUNT)));
  }

  function commit(next, pop) {
    var r = state.rating;
    state.value = next;
    r.settled = true;
    r.stars.forEach(function (star, i) { star.setAttribute('aria-checked', String(i + 1 === next)); star.tabIndex = i + 1 === next ? 0 : -1; });
    setError('');
    paint();
    var glyph = r.glyphs[next - 1];
    if (pop && glyph && glyph.animate && !reduce()) {
      glyph.getAnimations().forEach(function (a) { a.cancel(); });
      glyph.animate([{ transform: 'scale(1)', easing: EASE_OUT }, { transform: 'scale(1.3)', offset: 0.35, easing: EASE_OUT }, { transform: 'scale(1)' }], { duration: 300 });
    }
  }

  function bindRating() {
    var r = state.rating;
    var row = r.row;
    var measure = function () { r.rect = row.getBoundingClientRect(); };
    row.addEventListener('pointerenter', function (e) { if (e.pointerType === 'mouse') { state.root.removeAttribute('data-instant'); measure(); } });
    row.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || r.pointerId !== null) return;
      state.root.removeAttribute('data-instant');
      try { row.setPointerCapture(e.pointerId); } catch (_) {}
      r.pointerId = e.pointerId;
      r.pressing = true;
      measure();
      setHover(indexAt(e.clientX, e.clientY));
    });
    row.addEventListener('pointermove', function (e) {
      if (e.pointerType !== 'mouse' && !r.pressing) return;
      if (r.pressing && e.pointerId !== r.pointerId) return;
      if (!r.pressing && !r.rect) measure();
      setHover(indexAt(e.clientX, e.clientY));
    });
    var end = function (e) {
      if (!r.pressing || e.pointerId !== r.pointerId) return;
      r.pressing = false;
      r.pointerId = null;
      if (e.type === 'pointerup' && r.hover !== null) commit(r.hover + 1, true);
      if (e.pointerType !== 'mouse') setHover(null);
    };
    row.addEventListener('pointerup', end);
    row.addEventListener('pointercancel', end);
    row.addEventListener('lostpointercapture', end);
    row.addEventListener('pointerleave', function () { if (!r.pressing) setHover(null); });
    row.addEventListener('keydown', function (e) {
      var next;
      if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = Math.min(COUNT, state.value + 1);
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = Math.max(1, state.value - 1);
      else if (e.key === 'Home') next = 1;
      else if (e.key === 'End') next = COUNT;
      else if (e.key === ' ' || e.key === 'Enter') { var i = r.stars.indexOf(e.target); if (i < 0) return; next = i + 1; }
      else return;
      e.preventDefault();
      state.root.setAttribute('data-instant', 'true');
      r.hover = null;
      commit(next, false);
      r.stars[next - 1].focus();
    });
  }

  // ------------------------------------------------------------- the card
  function setError(text) {
    var box = state.root.querySelector('.sxf-error');
    box.textContent = text || '';
    box.hidden = !text;
  }

  function answer(action) {
    if (!state || state.busy) return;
    var t = state.t;
    if (action === 'send' && !state.value) { setError(t.pick); return; }
    var payload = action === 'send' ? { rating: state.value, text: String(state.root.querySelector('textarea').value || '').trim() } : {};
    var handler = state.opts.onAnswer || function () { return Promise.resolve(); };
    var current = state;
    current.busy = true;
    current.root.classList.toggle('is-busy', action === 'send');
    Promise.resolve().then(function () { return handler(action, payload); }).then(function () {
      if (action === 'send') thanks(current); else close(current);
    }, function () {
      current.busy = false;
      current.root.classList.remove('is-busy');
      if (action === 'send') setError(t.failed); else close(current);
    });
  }

  function thanks(current) {
    var card = current.root.querySelector('.sxf');
    var from = card.offsetHeight;
    card.innerHTML = '<div class="sxf-thanks"><span class="sxf-thanks-mark">' + CHECK + '</span><b>' + esc(current.t.thanks) + '</b><small>' + esc(current.t.thanksNote) + '</small></div>';
    if (!reduce()) {
      card.animate([{ height: from + 'px' }, { height: card.offsetHeight + 'px' }], { duration: 420, easing: EASE_OUT });
      var path = card.querySelector('path');
      path.style.strokeDasharray = '24';
      path.animate([{ strokeDashoffset: 24 }, { strokeDashoffset: 24, offset: 0.35 }, { strokeDashoffset: 0 }], { duration: 640, easing: EASE_OUT });
    }
    setTimeout(function () { close(current); }, 2600);
  }

  function open(opts) {
    if (state) return;
    var o = opts || {};
    var t = TEXT[o.lang] ? TEXT[o.lang] : TEXT.en;
    var root = doc.createElement('div');
    root.className = 'sxf-dock ' + (o.theme === 'light' ? 'light' : 'dark');
    var stars = '';
    for (var i = 0; i < COUNT; i += 1) {
      stars += '<button type="button" class="sxf-star" role="radio" aria-checked="false" tabindex="' + (i === 0 ? 0 : -1) + '" aria-label="' + (i + 1) + ' ' + esc(t.of) + ' ' + COUNT + ', ' + esc(t.labels[i]) + '">'
        + '<span class="sxf-lift"><span class="sxf-glyph" data-lit="false">' + STAR + '</span></span></button>';
    }
    root.innerHTML = '<section class="sxf" role="dialog" aria-label="' + esc(t.title) + '">'
      + '<button type="button" class="sxf-x" data-sxf-close aria-label="' + esc(t.close) + '">' + CLOSE + '</button>'
      + '<h3>' + esc(t.title) + '</h3><p class="sxf-sub">' + esc(t.sub) + '</p>'
      + '<div class="sxf-rating" role="radiogroup" aria-label="' + esc(t.rating) + '"><div class="sxf-row"><span class="sxf-tip" aria-hidden="true"></span>' + stars + '</div><span class="sxf-grade"></span></div>'
      + '<textarea rows="3" maxlength="1500" placeholder="' + esc(t.placeholder) + '"></textarea>'
      + '<p class="sxf-error" role="alert" hidden></p>'
      + '<div class="sxf-actions"><button type="button" class="sxf-later" data-sxf-later>' + esc(t.later) + '</button>'
      + '<button type="button" class="sxf-send" data-sxf-send>' + esc(t.send) + '</button></div>'
      + '<button type="button" class="sxf-never" data-sxf-never>' + esc(t.never) + '</button>'
      + '</section>';
    doc.body.appendChild(root);
    var row = root.querySelector('.sxf-row');
    state = {
      opts: o, t: t, root: root, value: 0, busy: false,
      rating: {
        row: row, tip: root.querySelector('.sxf-tip'), stars: Array.prototype.slice.call(root.querySelectorAll('.sxf-star')),
        lifts: Array.prototype.slice.call(root.querySelectorAll('.sxf-lift')), glyphs: Array.prototype.slice.call(root.querySelectorAll('.sxf-glyph')),
        hover: null, pressing: false, pointerId: null, settled: false, rect: null, size: 36, lift: 7, magnify: 1.15,
      },
    };
    bindRating();
    root.addEventListener('click', function (e) {
      if (e.target.closest('[data-sxf-close]')) answer('close');
      else if (e.target.closest('[data-sxf-later]')) answer('later');
      else if (e.target.closest('[data-sxf-never]')) answer('never');
      else if (e.target.closest('[data-sxf-send]')) answer('send');
    });
    state.reset = function () { if (!state) return; state.rating.pressing = false; state.rating.pointerId = null; setHover(null); };
    global.addEventListener('blur', state.reset);
    paint();
    if (!reduce()) root.querySelector('.sxf').animate([{ opacity: 0, transform: 'translateY(24px) scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 480, easing: 'cubic-bezier(0.34, 1.4, 0.64, 1)' });
  }

  function close(current) {
    var closing = current || state;
    if (!closing) return;
    if (closing === state) state = null;
    global.removeEventListener('blur', closing.reset);
    var card = closing.root.querySelector('.sxf');
    if (reduce() || !card.animate) { closing.root.remove(); return; }
    card.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(16px) scale(.98)' }], { duration: 200, easing: 'cubic-bezier(0.4, 0, 1, 1)', fill: 'forwards' })
      .finished.then(function () { closing.root.remove(); });
  }

  global.SylvexFeedbackPrompt = { open: open, close: function () { close(); }, isOpen: function () { return !!state; } };
})(window);
