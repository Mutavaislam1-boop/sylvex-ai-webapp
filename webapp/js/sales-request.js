/*
 * Sales request (Store → Contact sales): a short form in steps - who is
 * asking (an organisation or a private person), what they need, and where
 * to answer. Built on the Stepper look: a framed card, the steps on a rail
 * with a gliding tile, the content sliding between steps. The card keeps
 * one size on every step: the extra fields scroll inside it, the rail and
 * the Back / Continue buttons never move. Send hands the request to the
 * page (opts.submit); when it is through, the card closes by itself and a
 * small "Sent" tick shows.
 * The same file runs in the Mini App (Russian) and on the website
 * (English).
 *
 *   SylvexSalesRequest.open({ lang, theme, email, name, submit(request) })
 */
(function (global) {
  'use strict';
  if (global.SylvexSalesRequest) return;
  var doc = global.document;

  var SPRING = 'linear(0, 0.0603, 0.2033, 0.3821, 0.5633, 0.7258, 0.8584, 0.9574, 1.0242, 1.0634, 1.0809, 1.0828, 1.0747, 1.0613, 1.046, 1.0313, 1.0186, 1.0085, 1.0012, 0.9965, 0.994, 0.9931, 0.9933, 0.9941, 0.9953, 0.9966, 0.9978, 0.9988, 1)';
  var SETTLE = 'cubic-bezier(0.22, 1, 0.36, 1)';
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  var reduce = function () { return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches); };
  var spring = function () { return global.CSS && CSS.supports && CSS.supports('transition-timing-function', 'linear(0, 1)') ? SPRING : 'cubic-bezier(0.34, 1.4, 0.64, 1)'; };

  var TEXT = {
    ru: {
      title: 'Связаться с отделом продаж', close: 'Закрыть', back: 'Назад', next: 'Далее', send: 'Отправить', sending: 'Отправляем…',
      steps: [['Заявитель', 'Организация или частное лицо'], ['Запрос', 'Что нужно и в каком объёме'], ['Контакты', 'Куда ответить']],
      who: 'Кто обращается', org: 'Организация', orgNote: 'Компания, студия, команда', person: 'Частное лицо', personNote: 'Для себя или своего проекта',
      company: 'Название организации', companyPh: 'ООО «Пример» или название студии', team: 'Размер команды', site: 'Сайт', optional: 'необязательно',
      need: 'Что вас интересует', needs: [['images', 'Изображения'], ['video', 'Видео'], ['voice', 'Голос и музыка'], ['text', 'Тексты'], ['api', 'API и интеграция'], ['team', 'Доступ для команды']],
      volume: 'Ожидаемый бюджет в месяц', volumes: [['lt100', 'До $100'], ['100-500', '$100–500'], ['500-2000', '$500–2000'], ['2000+', 'Больше $2000'], ['unknown', 'Пока не знаю']],
      comment: 'Комментарий', commentPh: 'Расскажите о задаче, сроках и пожеланиях',
      name: 'Как к вам обращаться', namePh: 'Имя', email: 'E-mail для обратной связи', phone: 'Телефон или Telegram', phonePh: '+7 … или @username',
      reply: 'Ответ придёт на e-mail и в уведомления SYLVEX.',
      needWho: 'Выберите, кто обращается', needCompany: 'Укажите название организации', needAny: 'Выберите хотя бы одно направление',
      needName: 'Укажите имя', needEmail: 'Укажите корректный e-mail', failed: 'Не удалось отправить заявку. Попробуйте ещё раз.', tooMany: 'Вы уже отправили несколько сообщений. Дождитесь ответа.',
      sent: 'Отправлено',
    },
    en: {
      title: 'Contact sales', close: 'Close', back: 'Back', next: 'Continue', send: 'Send', sending: 'Sending…',
      steps: [['Applicant', 'Organization or private person'], ['Request', 'What you need and how much'], ['Contacts', 'Where to reply']],
      who: 'Who is asking', org: 'Organization', orgNote: 'Company, studio or team', person: 'Private person', personNote: 'For yourself or your project',
      company: 'Organization name', companyPh: 'Company or studio name', team: 'Team size', site: 'Website', optional: 'optional',
      need: 'What are you interested in', needs: [['images', 'Images'], ['video', 'Video'], ['voice', 'Voice & music'], ['text', 'Text'], ['api', 'API & integration'], ['team', 'Team access']],
      volume: 'Expected monthly budget', volumes: [['lt100', 'Under $100'], ['100-500', '$100–500'], ['500-2000', '$500–2,000'], ['2000+', 'Over $2,000'], ['unknown', 'Not sure yet']],
      comment: 'Comment', commentPh: 'Tell us about the task, timing and wishes',
      name: 'Your name', namePh: 'Name', email: 'E-mail for the reply', phone: 'Phone or Telegram', phonePh: '+1 … or @username',
      reply: 'The reply comes to your e-mail and to SYLVEX notifications.',
      needWho: 'Choose who is asking', needCompany: 'Enter the organization name', needAny: 'Choose at least one area',
      needName: 'Enter your name', needEmail: 'Enter a valid e-mail', failed: 'Could not send the request. Please try again.', tooMany: 'You have sent several messages already. Please wait for the reply.',
      sent: 'Sent',
    },
  };
  var TEAM = ['1–10', '11–50', '51–200', '200+'];

  var ICON = {
    back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>',
    next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    org: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16"/><path d="M15 9h3a2 2 0 0 1 2 2v10M3 21h18M8 7h3M8 11h3M8 15h3"/></svg>',
    person: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  };

  var state = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ---------------------------------------------------------------- steps
  function chips(name, list, picked, multi) {
    return '<div class="sxr-chips" data-sxr-chips="' + name + '"' + (multi ? ' data-multi' : '') + '>' + list.map(function (item) {
      var on = multi ? picked.indexOf(item[0]) >= 0 : picked === item[0];
      return '<button type="button" class="sxr-chip' + (on ? ' is-on' : '') + '" data-value="' + esc(item[0]) + '" aria-pressed="' + on + '">' + esc(item[1]) + '</button>';
    }).join('') + '</div>';
  }

  function field(label, name, value, opts) {
    var o = opts || {};
    var input = o.area
      ? '<textarea name="' + name + '" rows="3" maxlength="' + (o.max || 1500) + '" placeholder="' + esc(o.ph || '') + '">' + esc(value) + '</textarea>'
      : '<input name="' + name + '" type="' + (o.type || 'text') + '" maxlength="' + (o.max || 120) + '" value="' + esc(value) + '" placeholder="' + esc(o.ph || '') + '"' + (o.auto ? ' autocomplete="' + o.auto + '"' : '') + '>';
    return '<label class="sxr-field"><span>' + esc(label) + (o.optional ? ' <small>' + esc(state.t.optional) + '</small>' : '') + '</span>' + input + '</label>';
  }

  // Each step opens with its heading and the rail's line under it, centred.
  function lead(title, index) {
    return '<h3>' + esc(title) + '</h3><p class="sxr-lead">' + esc(state.t.steps[index][1]) + '</p>';
  }

  function stepHtml(n) {
    var t = state.t, d = state.data;
    if (n === 1) {
      var tile = function (kind, icon, title, note) {
        var on = d.kind === kind;
        return '<button type="button" class="sxr-kind' + (on ? ' is-on' : '') + '" data-sxr-kind="' + kind + '" aria-pressed="' + on + '"><i>' + icon + '</i><b>' + esc(title) + '</b><small>' + esc(note) + '</small></button>';
      };
      return lead(t.who, 0) + '<div class="sxr-kinds">' + tile('organization', ICON.org, t.org, t.orgNote) + tile('private', ICON.person, t.person, t.personNote) + '</div>'
        + (d.kind === 'organization'
          ? '<div class="sxr-extra">' + field(t.company, 'company', d.company, { ph: t.companyPh, auto: 'organization' })
            + '<div class="sxr-field"><span>' + esc(t.team) + '</span>' + chips('team', TEAM.map(function (v) { return [v, v]; }), d.team, false) + '</div>'
            + field(t.site, 'website', d.website, { ph: 'https://', optional: true, auto: 'url' }) + '</div>'
          : '');
    }
    if (n === 2) {
      return lead(t.need, 1) + chips('needs', t.needs, d.needs, true)
        + '<div class="sxr-field"><span>' + esc(t.volume) + '</span>' + chips('budget', t.volumes, d.budget, false) + '</div>'
        + field(t.comment, 'comment', d.comment, { area: true, ph: t.commentPh, optional: true });
    }
    return lead(t.steps[2][0], 2)
      + field(t.name, 'name', d.name, { ph: t.namePh, auto: 'name' })
      + field(t.email, 'email', d.email, { type: 'email', ph: 'name@example.com', auto: 'email', max: 254 })
      + field(t.phone, 'phone', d.phone, { ph: t.phonePh, optional: true, auto: 'tel' })
      + '<p class="sxr-note">' + esc(t.reply) + '</p>';
  }

  // What keeps a step from being done, or ''.
  function problem(n) {
    var t = state.t, d = state.data;
    if (n === 1) {
      if (!d.kind) return t.needWho;
      if (d.kind === 'organization' && !d.company.trim()) return t.needCompany;
    }
    if (n === 2 && !d.needs.length) return t.needAny;
    if (n === 3) {
      if (!d.name.trim()) return t.needName;
      if (!EMAIL.test(d.email.trim())) return t.needEmail;
    }
    return '';
  }

  // ------------------------------------------------------------- rendering
  function headerHtml() {
    var t = state.t;
    return '<div class="sxr-track" data-sxr-track><span class="sxr-glider" aria-hidden="true"></span>' + t.steps.map(function (s, i) {
      var n = i + 1;
      var status = n < state.step ? 'complete' : n === state.step ? 'active' : 'upcoming';
      return '<button type="button" class="sxr-segment" data-sxr-go="' + n + '" data-status="' + status + '"' + (n === state.step ? ' aria-current="step"' : '') + '>'
        + '<span class="sxr-badge" data-status="' + status + '">' + (status === 'complete' ? '<span class="sxr-check">' + ICON.check + '</span>' : n) + '</span>'
        + '<span class="sxr-text"><span class="sxr-title">' + esc(s[0]) + '</span><span class="sxr-desc">' + esc(s[1]) + '</span></span></button>';
    }).join('') + '</div>';
  }

  function renderHeader(animateChecks) {
    var host = state.root.querySelector('.sxr-header');
    var before = Array.prototype.map.call(host.querySelectorAll('.sxr-badge'), function (b) { return b.dataset.status; });
    host.innerHTML = headerHtml();
    host.querySelectorAll('.sxr-badge').forEach(function (b, i) {
      var path = b.querySelector('path');
      if (!path || !animateChecks || before[i] === 'complete' || reduce()) return;
      path.style.strokeDasharray = '24';
      path.animate([{ strokeDashoffset: 24 }, { strokeDashoffset: 0 }], { duration: 360, easing: SETTLE });
    });
    placeGlider(false);
  }

  function placeGlider(animate) {
    var track = state.root.querySelector('[data-sxr-track]');
    var glider = track && track.querySelector('.sxr-glider');
    var seg = track && track.querySelector('[data-sxr-go="' + state.step + '"]');
    if (!glider || !seg) return;
    var s = spring();
    var from = state.gliderAt;
    glider.style.transition = 'opacity 200ms ease';
    glider.style.width = seg.offsetWidth + 'px';
    glider.style.height = seg.offsetHeight + 'px';
    glider.style.opacity = '1';
    var to = 'translate3d(' + seg.offsetLeft + 'px,' + seg.offsetTop + 'px,0)';
    if (animate && from && !reduce()) {
      glider.style.transform = from;
      void glider.offsetWidth;
      glider.style.transition = 'transform 560ms ' + s + ', width 560ms ' + s + ', height 560ms ' + s + ', opacity 200ms ease';
    }
    glider.style.transform = to;
    state.gliderAt = to;
  }

  function renderFooter() {
    var t = state.t;
    var back = state.root.querySelector('[data-sxr-back]');
    var next = state.root.querySelector('[data-sxr-next]');
    var last = state.step === t.steps.length;
    back.toggleAttribute('data-hidden', state.step <= 1);
    next.innerHTML = '<span>' + esc(state.sending ? t.sending : last ? t.send : t.next) + '</span>' + (last ? ICON.check : ICON.next);
    next.disabled = state.sending;
  }

  function showStep(n, direction) {
    var viewport = state.root.querySelector('.sxr-viewport');
    var old = viewport.querySelector('.sxr-pane:not(.is-leaving)');
    state.step = n;
    var pane = doc.createElement('div');
    pane.className = 'sxr-pane';
    pane.innerHTML = stepHtml(n);
    viewport.appendChild(pane);
    setError('');
    renderHeader(direction > 0);
    renderFooter();
    placeGlider(true);
    if (old) {
      old.classList.add('is-leaving');
      if (reduce() || !old.animate) old.remove();
      else {
        var axis = state.vertical ? 'Y' : 'X';
        old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, easing: 'cubic-bezier(0.2, 0, 0.4, 1)', fill: 'forwards' });
        old.animate([{ transform: 'none' }, { transform: 'translate' + axis + '(' + (-direction * 36) + 'px)' }], { duration: 200, easing: 'cubic-bezier(0.4, 0, 1, 1)', fill: 'forwards' })
          .finished.then(function () { old.remove(); }, function () { old.remove(); });
        pane.animate([{ transform: 'translate' + axis + '(' + direction * 36 + 'px)' }, { transform: 'none' }], { duration: 560, easing: spring() });
        pane.animate([{ opacity: 0 }, { opacity: 0, offset: 0.25 }, { opacity: 1 }], { duration: 420, easing: 'ease-out' });
      }
    }
    viewport.scrollTop = 0;
    var first = pane.querySelector('input, textarea');
    if (first && !first.value && n > 1) setTimeout(function () { first.focus({ preventScroll: true }); }, 60);
  }

  function setError(text) {
    var box = state.root.querySelector('.sxr-error');
    box.textContent = text || '';
    box.hidden = !text;
  }

  // Changes inside a step that alter its layout (the organisation fields)
  // re-render it in place; the card keeps its size and the new fields fade
  // in inside it.
  function rerender() {
    var viewport = state.root.querySelector('.sxr-viewport');
    var pane = viewport.querySelector('.sxr-pane:not(.is-leaving)');
    pane.innerHTML = stepHtml(state.step);
    var extra = pane.querySelector('.sxr-extra');
    if (extra && !reduce() && extra.animate) extra.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: SETTLE });
  }

  function go(target) {
    var n = Math.max(1, Math.min(state.t.steps.length, target));
    if (n === state.step || state.sending) return;
    // Forward only past finished steps.
    for (var i = state.step; i < n; i += 1) {
      var why = problem(i);
      if (why) { if (i !== state.step) showStep(i, i > state.step ? 1 : -1); setError(why); return; }
    }
    showStep(n, n > state.step ? 1 : -1);
  }

  function request() {
    var d = state.data;
    return {
      kind: d.kind, company: d.kind === 'organization' ? d.company.trim() : '', team_size: d.kind === 'organization' ? d.team : '',
      website: d.kind === 'organization' ? d.website.trim() : '', needs: d.needs.slice(), budget: d.budget, comment: d.comment.trim(),
      name: d.name.trim(), email: d.email.trim(), phone: d.phone.trim(),
    };
  }

  function send() {
    for (var i = 1; i <= state.t.steps.length; i += 1) {
      var why = problem(i);
      if (why) { if (i !== state.step) showStep(i, -1); setError(why); return; }
    }
    state.sending = true;
    renderFooter();
    var submit = state.opts.submit || function () { return Promise.resolve(); };
    var t = state.t;
    Promise.resolve().then(function () { return submit(request()); }).then(function () {
      close(true);
      sent(t);
    }, function (error) {
      state.sending = false;
      renderFooter();
      setError(error && error.code === 'too_many_messages' ? t.tooMany : (error && error.userMessage) || t.failed);
    });
  }

  // The small tick after a request went through; it goes away by itself.
  function sent(t) {
    var box = doc.createElement('div');
    box.className = 'sxr-sent ' + (state && state.theme || lastTheme);
    box.setAttribute('role', 'status');
    box.innerHTML = '<span class="sxr-sent-mark">' + ICON.check + '</span><b>' + esc(t.sent) + '</b>';
    doc.body.appendChild(box);
    var path = box.querySelector('.sxr-sent-mark path');
    if (!reduce()) {
      box.animate([{ opacity: 0, transform: 'translate(-50%, -50%) scale(.9)' }, { opacity: 1, transform: 'translate(-50%, -50%) scale(1)' }], { duration: 380, easing: spring() });
      path.style.strokeDasharray = '24';
      path.animate([{ strokeDashoffset: 24 }, { strokeDashoffset: 24, offset: 0.35 }, { strokeDashoffset: 0 }], { duration: 560, easing: SETTLE });
    }
    setTimeout(function () {
      if (reduce() || !box.animate) { box.remove(); return; }
      box.animate([{ opacity: 1 }, { opacity: 0, transform: 'translate(-50%, -50%) scale(.96)' }], { duration: 220, fill: 'forwards' }).finished.then(function () { box.remove(); });
    }, 1800);
  }

  var lastTheme = 'dark';

  function bind() {
    var root = state.root;
    root.addEventListener('click', function (event) {
      var target = event.target;
      if (target === root || target.closest('[data-sxr-close]')) { close(false); return; }
      var seg = target.closest('[data-sxr-go]');
      if (seg) { go(Number(seg.dataset.sxrGo)); return; }
      if (target.closest('[data-sxr-back]')) { go(state.step - 1); return; }
      if (target.closest('[data-sxr-next]')) {
        if (state.step === state.t.steps.length) send();
        else go(state.step + 1);
        return;
      }
      var kind = target.closest('[data-sxr-kind]');
      if (kind) { state.data.kind = kind.dataset.sxrKind; setError(''); rerender(); return; }
      var chip = target.closest('.sxr-chip');
      if (chip) {
        var group = chip.parentNode;
        var name = group.dataset.sxrChips;
        if (group.hasAttribute('data-multi')) {
          var list = state.data[name];
          var at = list.indexOf(chip.dataset.value);
          if (at >= 0) list.splice(at, 1); else list.push(chip.dataset.value);
          chip.classList.toggle('is-on', at < 0);
          chip.setAttribute('aria-pressed', String(at < 0));
        } else {
          state.data[name] = state.data[name] === chip.dataset.value ? '' : chip.dataset.value;
          group.querySelectorAll('.sxr-chip').forEach(function (c) { var on = c.dataset.value === state.data[name]; c.classList.toggle('is-on', on); c.setAttribute('aria-pressed', String(on)); });
        }
        setError('');
      }
    });
    root.addEventListener('input', function (event) {
      var el = event.target;
      if (el.name && Object.prototype.hasOwnProperty.call(state.data, el.name)) state.data[el.name] = el.value;
    });
    root.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { event.preventDefault(); close(false); }
      if (event.key === 'Enter' && event.target.tagName === 'INPUT') { event.preventDefault(); root.querySelector('[data-sxr-next]').click(); }
    });
    state.resize = function () { layout(); placeGlider(false); };
    global.addEventListener('resize', state.resize);
  }

  // The rail on the left; under 520px the steps fold into a row.
  function layout() {
    var card = state.root.querySelector('.sxr');
    var vertical = card.clientWidth >= 520;
    state.vertical = vertical;
    card.classList.toggle('sxr--vertical', vertical);
    card.classList.toggle('sxr--horizontal', !vertical);
  }

  function open(opts) {
    if (state) close(false);
    var o = opts || {};
    var lang = TEXT[o.lang] ? o.lang : 'en';
    lastTheme = o.theme === 'light' ? 'light' : 'dark';
    state = {
      opts: o, t: TEXT[lang], step: 1, theme: lastTheme, sending: false, gliderAt: '',
      data: { kind: '', company: '', team: '', website: '', needs: [], budget: '', comment: '', name: String(o.name || ''), email: String(o.email || ''), phone: '' },
    };
    var t = state.t;
    var root = doc.createElement('div');
    root.className = 'sxr-overlay ' + state.theme;
    root.innerHTML = '<section class="sxr sxr--framed" role="dialog" aria-modal="true" aria-label="' + esc(t.title) + '">'
      + '<button type="button" class="sxr-x" data-sxr-close aria-label="' + esc(t.close) + '">' + ICON.close + '</button>'
      + '<div class="sxr-main"><div class="sxr-header"></div><div class="sxr-body"><h2 class="sxr-heading">' + esc(t.title) + '</h2><div class="sxr-viewport" aria-live="polite"></div>'
      + '<p class="sxr-error" role="alert" hidden></p>'
      + '<div class="sxr-footer"><button type="button" class="sxr-button sxr-button--back" data-sxr-back>' + ICON.back + '<span>' + esc(t.back) + '</span></button>'
      + '<button type="button" class="sxr-button sxr-button--next" data-sxr-next></button></div></div></div>'
      + '<span class="sxr-rim" aria-hidden="true"></span></section>';
    doc.body.appendChild(root);
    state.root = root;
    layout();
    bind();
    var pane = doc.createElement('div');
    pane.className = 'sxr-pane';
    pane.innerHTML = stepHtml(1);
    root.querySelector('.sxr-viewport').appendChild(pane);
    renderHeader(false);
    renderFooter();
    if (!reduce()) {
      root.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220 });
      root.querySelector('.sxr').animate([{ opacity: 0, transform: 'translateY(18px) scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 520, easing: spring() });
    }
    root.querySelector('.sxr-kind').focus({ preventScroll: true });
  }

  function close(done) {
    if (!state) return;
    var closing = state;
    state = null;
    global.removeEventListener('resize', closing.resize);
    var root = closing.root;
    if (reduce() || !root.animate) root.remove();
    else root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: done ? 160 : 200, fill: 'forwards' }).finished.then(function () { root.remove(); });
    if (!done && typeof closing.opts.onClose === 'function') closing.opts.onClose();
  }

  global.SylvexSalesRequest = { open: open, close: function () { close(false); }, isOpen: function () { return !!state; } };
})(window);
