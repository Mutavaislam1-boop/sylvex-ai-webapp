/*
 * Account notices from SYLVEX, shown in the middle of the screen:
 *
 *   SylvexAccountNotice.showAwards({ lang, theme, items, onSeen })
 *     "You received ..." cards for credits, a subscription or a team role,
 *     one after another. Each card is shown once: onSeen(ids) marks the
 *     notifications read on the server (every surface shares that state).
 *   SylvexAccountNotice.showBlocked({ lang, theme, reason, since, onContact, onSignOut })
 *     The account is blocked by SYLVEX: the reason, since when, and the way
 *     to contact support. It cannot be dismissed while the block lasts.
 *   SylvexAccountNotice.hideBlocked()
 *
 * The same file runs in the Mini App (Russian) and on the website (English).
 */
(function (global) {
  'use strict';
  if (global.SylvexAccountNotice) return;
  var doc = global.document;

  var TEXT = {
    ru: {
      credits: function (n) { return 'Вам начислено ' + n + ' ' + plural(n, 'кредит', 'кредита', 'кредитов'); },
      subscription: function (a) { return 'Вам подарена подписка' + (a.plan_label ? ' «' + a.plan_label + '»' : ''); },
      role: function (a) { return 'Вы в команде SYLVEX'; },
      roleSub: function (a) { return 'Ваша роль: ' + (a.label || a.role); },
      days: function (n) { return 'На ' + n + ' ' + plural(n, 'день', 'дня', 'дней'); },
      until: 'Действует до',
      from: 'От команды SYLVEX',
      ok: 'Отлично', next: 'Дальше',
      reasons: { error_compensation: 'Компенсация ошибки', bonus: 'Бонус', promo: 'Промоакция', gift: 'Подарок', refund: 'Возмещение' },
      blockedTitle: 'Доступ к аккаунту ограничен',
      blockedSub: 'Администрация SYLVEX ограничила доступ к генерациям, покупкам и боту для этого аккаунта.',
      reason: 'Причина', since: 'С', contact: 'Написать в поддержку', signOut: 'Выйти',
    },
    en: {
      credits: function (n) { return 'You received ' + n + ' ' + (n === 1 ? 'credit' : 'credits'); },
      subscription: function (a) { return 'You received a subscription' + (a.plan_label ? ': ' + a.plan_label : ''); },
      role: function (a) { return 'You are on the SYLVEX team'; },
      roleSub: function (a) { return 'Your role: ' + (a.label_en || a.label || a.role); },
      days: function (n) { return 'For ' + n + ' ' + (n === 1 ? 'day' : 'days'); },
      until: 'Valid until',
      from: 'From the SYLVEX team',
      ok: 'Great', next: 'Next',
      reasons: { error_compensation: 'Compensation for an error', bonus: 'Bonus', promo: 'Promotion', gift: 'Gift', refund: 'Refund' },
      blockedTitle: 'Access to this account is restricted',
      blockedSub: 'The SYLVEX team restricted generations, purchases and the bot for this account.',
      reason: 'Reason', since: 'Since', contact: 'Contact support', signOut: 'Sign out',
    },
  };
  // Mini App role labels arrive in Russian; the website shows English ones.
  var ROLE_EN = { administrator: 'Administrator', finance: 'Finance', support: 'Support', moderator: 'Moderator', analyst: 'Analyst', read_only: 'Read only' };

  var ICON = {
    credits: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2 4.5 13.2H11L10 22l8.5-11.2H12z"/></svg>',
    subscription: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.75 5.6 6.15.9-4.45 4.33 1.05 6.12L12 16.87l-5.5 2.88 1.05-6.12L3.1 9.3l6.15-.9z"/></svg>',
    role: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5 4 5.6v6c0 5 3.4 8.6 8 9.9 4.6-1.3 8-4.9 8-9.9v-6z"/><path d="m8.6 12 2.4 2.4 4.4-4.6"/></svg>',
    lock: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7"/></svg>',
  };

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtDate(iso, lang) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    try { return d.toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-US', { day: 'numeric', month: 'long', year: 'numeric' }); }
    catch (_) { return d.toDateString(); }
  }
  function textFor(lang) { return TEXT[lang === 'ru' ? 'ru' : 'en']; }
  function layer(theme, extra) {
    var el = doc.createElement('div');
    el.className = 'sxn-layer' + (theme === 'light' ? ' light' : '') + (extra ? ' ' + extra : '');
    doc.body.appendChild(el);
    return el;
  }

  // ------------------------------------------------------------ awards
  var awards = null;

  function awardCard(item, t, lang, last) {
    var a = item.award || {};
    var type = ICON[a.type] ? a.type : 'credits';
    var title, lines = [];
    if (type === 'credits') title = t.credits(Number(a.amount) || 0);
    else if (type === 'subscription') {
      title = t.subscription(a);
      if (a.days) lines.push(t.days(Number(a.days)));
      if (a.expires_at) lines.push(t.until + ' ' + fmtDate(a.expires_at, lang));
    } else {
      if (lang !== 'ru' && ROLE_EN[a.role]) a = Object.assign({}, a, { label_en: ROLE_EN[a.role] });
      title = t.role(a);
      lines.push(t.roleSub(a));
    }
    var reason = a.reason_code && t.reasons[a.reason_code];
    return '<div class="sxn-card sxn-award" role="dialog" aria-modal="true" aria-labelledby="sxnTitle">' +
      '<div class="sxn-burst" aria-hidden="true"></div>' +
      '<div class="sxn-mark sxn-' + type + '">' + ICON[type] + '</div>' +
      '<small class="sxn-from">' + esc(t.from) + '</small>' +
      '<h3 id="sxnTitle">' + esc(title) + '</h3>' +
      lines.map(function (l) { return '<p>' + esc(l) + '</p>'; }).join('') +
      (reason ? '<span class="sxn-reason">' + esc(reason) + '</span>' : '') +
      '<button type="button" class="sxn-primary" data-sxn-ok>' + esc(last ? t.ok : t.next) + '</button>' +
      '</div>';
  }

  function renderAward() {
    var item = awards.items[awards.index];
    var last = awards.index === awards.items.length - 1;
    awards.root.innerHTML = awardCard(item, awards.t, awards.lang, last);
    var ok = awards.root.querySelector('[data-sxn-ok]');
    ok.addEventListener('click', nextAward);
    setTimeout(function () { try { ok.focus({ preventScroll: true }); } catch (_) { ok.focus(); } }, 30);
  }

  function nextAward() {
    if (!awards) return;
    var seen = awards.items[awards.index];
    if (seen && seen.notification_id) awards.seen.push(seen.notification_id);
    if (awards.index < awards.items.length - 1) { awards.index += 1; renderAward(); return; }
    closeAwards();
  }

  function closeAwards() {
    if (!awards) return;
    var done = awards;
    awards = null;
    doc.removeEventListener('keydown', onAwardKey);
    done.root.classList.add('is-leaving');
    setTimeout(function () { done.root.remove(); }, 180);
    if (done.seen.length && typeof done.onSeen === 'function') {
      try { done.onSeen(done.seen.slice()); } catch (_) {}
    }
  }

  function onAwardKey(e) { if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); nextAward(); } }

  function showAwards(opts) {
    opts = opts || {};
    var items = (opts.items || []).filter(function (i) { return i && i.award; });
    if (!items.length || awards || blocked) return false;
    var lang = opts.lang === 'ru' ? 'ru' : 'en';
    awards = { items: items, index: 0, seen: [], lang: lang, t: textFor(lang), onSeen: opts.onSeen,
      root: layer(opts.theme, 'sxn-awards') };
    awards.root.addEventListener('click', function (e) { if (e.target === awards.root) nextAward(); });
    doc.addEventListener('keydown', onAwardKey);
    renderAward();
    return true;
  }

  // ------------------------------------------------------------ block
  var blocked = null;

  function showBlocked(opts) {
    opts = opts || {};
    var t = textFor(opts.lang);
    if (awards) closeAwards();
    if (!blocked) blocked = layer(opts.theme, 'sxn-blocked');
    var since = opts.since ? fmtDate(opts.since, opts.lang) : '';
    blocked.innerHTML = '<div class="sxn-card" role="alertdialog" aria-modal="true" aria-labelledby="sxnBlockTitle">' +
      '<div class="sxn-mark sxn-lock">' + ICON.lock + '</div>' +
      '<h3 id="sxnBlockTitle">' + esc(t.blockedTitle) + '</h3>' +
      '<p>' + esc(t.blockedSub) + '</p>' +
      (opts.reason ? '<div class="sxn-detail"><small>' + esc(t.reason) + '</small><b>' + esc(opts.reason) + '</b></div>' : '') +
      (since ? '<div class="sxn-detail"><small>' + esc(t.since) + '</small><b>' + esc(since) + '</b></div>' : '') +
      '<button type="button" class="sxn-primary" data-sxn-contact>' + esc(t.contact) + '</button>' +
      (typeof opts.onSignOut === 'function' ? '<button type="button" class="sxn-quiet" data-sxn-signout>' + esc(t.signOut) + '</button>' : '') +
      '</div>';
    blocked.querySelector('[data-sxn-contact]').addEventListener('click', function () {
      if (typeof opts.onContact === 'function') opts.onContact();
    });
    var out = blocked.querySelector('[data-sxn-signout]');
    if (out) out.addEventListener('click', function () { opts.onSignOut(); });
    return true;
  }

  function hideBlocked() {
    if (!blocked) return;
    blocked.remove();
    blocked = null;
  }

  // The contact window opens above the block notice.
  function setBlockedBehind(behind) { if (blocked) blocked.classList.toggle('is-behind', !!behind); }

  global.SylvexAccountNotice = {
    showAwards: showAwards,
    showBlocked: showBlocked,
    hideBlocked: hideBlocked,
    setBlockedBehind: setBlockedBehind,
    isBlockedShown: function () { return !!blocked; },
    isOpen: function () { return !!(awards || blocked); },
  };
})(window);
