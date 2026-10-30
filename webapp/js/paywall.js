/* SYLVEX paywall: the window that explains why a generation did not start
   when the account has no subscription or not enough credits.

   One file for the website and both Mini Apps - keep it byte-identical in
   sylvex-website/js/paywall.js and sylvex-ai-webapp/webapp/js/paywall.js.

   It watches the app's own POST requests to the SYLVEX API. Only a refusal
   the server marks for it opens the window:
     403 + subscription_required            -> "start" (no credits either)
                                               or "subscription" (credits, no plan)
     402 + paywall / insufficient_balance   -> "balance" (not enough for this one)
   Any other refusal is left to the app's own error message. Access rules,
   prices and checkout stay where they are: the plans are the Store's own
   (js/store-cards.js) and buying goes through the host's Store.

     SylvexPaywall.configure({ lang, price(plan), onPlan(planId), onCredits(), storeCardsSrc })
     SylvexPaywall.show(kind, { required, balance })
     SylvexPaywall.classify(status, body)  -> { kind, required, balance } | null
*/
(function (root) {
  'use strict';
  if (root.SylvexPaywall) return;

  var TEXT = {
    en: {
      eyebrow: 'SYLVEX', close: 'Close',
      start_title: 'Start creating with SYLVEX',
      start_text: 'Choose a plan that suits you and get credits to generate images, video and other AI content.',
      subscription_title: 'This needs a subscription',
      subscription_text: 'Generations in Pro Studio, Grid, Edit and the tools run with an active subscription. Your credits stay on your balance - choose a plan to continue.',
      balance_title: 'Not enough credits',
      balance_text: 'This generation needs {required} ⚡ and your balance is {balance} ⚡. Top up your credits and run it right away.',
      balance_text_plain: 'Your balance does not cover this generation. Top up your credits and run it right away.',
      per_month: '/ month', credits: '{n} ⚡ every month', examples: '≈ {photo} images or {video} videos',
      tools: 'Pro Studio, Grid, Edit and every tool', choose: 'Subscribe', popular: 'Popular',
      credits_link: 'Only need credits? Buy a credit package', top_up: 'Top up credits', plans_link: 'See plans',
      need: 'Needed', have: 'On your balance', loading: 'Loading plans…',
    },
    ru: {
      eyebrow: 'SYLVEX', close: 'Закрыть',
      start_title: 'Начните создавать с SYLVEX',
      start_text: 'Выберите подходящий план и получите кредиты для генерации изображений, видео и другого ИИ-контента.',
      subscription_title: 'Нужна подписка',
      subscription_text: 'Генерации в Pro Studio, Grid, Edit и инструментах работают с активной подпиской. Кредиты остаются на балансе — выберите план, чтобы продолжить.',
      balance_title: 'Недостаточно кредитов',
      balance_text: 'Для этой генерации нужно {required} ⚡, а на балансе {balance} ⚡. Пополните кредиты — и запустите генерацию сразу.',
      balance_text_plain: 'Баланса не хватает для этой генерации. Пополните кредиты — и запустите генерацию сразу.',
      per_month: '/ мес', credits: '{n} ⚡ каждый месяц', examples: '≈ {photo} фото или {video} видео',
      tools: 'Pro Studio, Grid, Edit и все инструменты', choose: 'Оформить', popular: 'Популярный',
      credits_link: 'Нужны только кредиты? Купить пакет', top_up: 'Пополнить кредиты', plans_link: 'Посмотреть тарифы',
      need: 'Нужно', have: 'На балансе', loading: 'Загружаем тарифы…',
    },
  };
  // The three plans the window offers (the Store keeps the full list).
  var OFFERED = ['starter', 'pro', 'max'];

  var host = { lang: 'en', price: null, onPlan: null, onCredits: null, storeCardsSrc: '' };
  var node = null;
  var current = null;
  var lastShown = 0;
  var cardsLoading = null;

  function lang() {
    var value = typeof host.lang === 'function' ? host.lang() : host.lang;
    return TEXT[value] ? value : 'en';
  }
  function say(key, vars) {
    var text = TEXT[lang()][key] || TEXT.en[key] || key;
    Object.keys(vars || {}).forEach(function (k) { text = text.split('{' + k + '}').join(String(vars[k])); });
    return text;
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function num(value) {
    var n = Number(value);
    return isFinite(n) ? n : 0;
  }
  function fmt(n) {
    try { return Number(n).toLocaleString(lang() === 'ru' ? 'ru-RU' : 'en-US'); } catch (_) { return String(n); }
  }

  // ---------------------------------------------------------- the refusal
  function classify(status, body) {
    body = body && typeof body === 'object' ? body : {};
    var code = String(body.error || '');
    var subscription = body.subscription_required === true || code === 'subscription_required' || code === 'prostudio_subscription_required';
    if (status === 403 && subscription) {
      var balance = num(body.balance);
      return { kind: balance > 0 ? 'subscription' : 'start', balance: balance, required: 0 };
    }
    if (status === 402 && (body.paywall === true || body.insufficient_balance === true)) {
      return { kind: 'balance', required: num(body.required_credits), balance: num(body.balance) };
    }
    return null;
  }

  function requestInfo(input, init) {
    var method = (init && init.method) || (input && typeof input === 'object' && input.method) || 'GET';
    var url = typeof input === 'string' ? input : (input && input.url) || String(input || '');
    return { method: String(method).toUpperCase(), url: String(url) };
  }

  function watch() {
    if (typeof root.fetch !== 'function' || root.fetch.__sxPaywall) return;
    var original = root.fetch;
    var wrapped = function (input, init) {
      var pending = original.apply(this, arguments);
      var info;
      try { info = requestInfo(input, init); } catch (_) { return pending; }
      if (info.method !== 'POST' || !/\/api\//.test(info.url)) return pending;
      return pending.then(function (response) {
        if (response && (response.status === 402 || response.status === 403) && typeof response.clone === 'function') {
          try {
            response.clone().json().then(function (body) {
              var hit = classify(response.status, body);
              if (hit) api.show(hit.kind, hit);
            }, function () {});
          } catch (_) { /* a body that is not JSON is not ours */ }
        }
        return response;
      });
    };
    wrapped.__sxPaywall = true;
    root.fetch = wrapped;
  }

  // ---------------------------------------------------------- the plans
  function storeCards() {
    if (root.SylvexStoreCards) return Promise.resolve(root.SylvexStoreCards);
    if (!host.storeCardsSrc || typeof document === 'undefined') return Promise.resolve(null);
    if (!cardsLoading) {
      cardsLoading = new Promise(function (resolve) {
        var script = document.createElement('script');
        script.src = host.storeCardsSrc;
        script.async = true;
        script.onload = function () { resolve(root.SylvexStoreCards || null); };
        script.onerror = function () { cardsLoading = null; resolve(null); };
        document.head.appendChild(script);
      });
    }
    return cardsLoading;
  }

  function priceOf(plan) {
    var custom = typeof host.price === 'function' ? host.price(plan) : null;
    return custom || ('$' + fmt(plan.monthlyUsd));
  }

  function exampleCost(cards, key) {
    var row = (cards.EXAMPLES || []).filter(function (e) { return e.key === key; })[0];
    return row ? num(row.cost) : 0;
  }

  function planCard(cards, plan) {
    var credits = num(plan.monthlyCredits);
    var photo = exampleCost(cards, 'photo');
    var video = exampleCost(cards, 'video');
    var count = function (cost) { return cost ? (cards.exampleCount ? cards.exampleCount(credits, cost) : Math.floor(credits / cost)) : 0; };
    var perks = [say('credits', { n: fmt(credits) })];
    if (photo && video) perks.push(say('examples', { photo: fmt(count(photo)), video: fmt(count(video)) }));
    perks.push(say('tools'));
    return '<article class="sxpw-plan' + (plan.popular ? ' is-popular' : '') + '" data-sxpw-card="' + esc(plan.id) + '">'
      + (plan.popular ? '<span class="sxpw-badge">' + esc(say('popular')) + '</span>' : '')
      + '<h3>' + esc(plan.name) + '</h3>'
      + '<div class="sxpw-price"><b>' + esc(priceOf(plan)) + '</b><span>' + esc(say('per_month')) + '</span></div>'
      + '<ul>' + perks.map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('') + '</ul>'
      + '<button type="button" class="sxpw-cta" data-sxpw-plan="' + esc(plan.id) + '">' + esc(say('choose')) + '</button>'
      + '</article>';
  }

  function fillPlans() {
    var holder = node && node.querySelector('[data-sxpw-plans-host]');
    if (!holder) return;
    storeCards().then(function (cards) {
      if (!node || !holder.isConnected) return;
      var plans = cards ? (cards.PLANS || []).filter(function (p) { return OFFERED.indexOf(p.id) !== -1; }) : [];
      holder.innerHTML = plans.length ? plans.map(function (p) { return planCard(cards, p); }).join('') : '';
      holder.classList.toggle('is-empty', !plans.length);
    });
  }

  // ---------------------------------------------------------- the window
  function body(kind, info) {
    if (kind === 'balance') {
      var known = info.required > 0;
      return '<p class="sxpw-text">' + esc(known ? say('balance_text', { required: fmt(info.required), balance: fmt(info.balance) }) : say('balance_text_plain')) + '</p>'
        + (known ? '<div class="sxpw-balance"><div><span>' + esc(say('need')) + '</span><b>' + esc(fmt(info.required)) + ' ⚡</b></div>'
          + '<div><span>' + esc(say('have')) + '</span><b>' + esc(fmt(info.balance)) + ' ⚡</b></div></div>' : '')
        + '<div class="sxpw-actions"><button type="button" class="sxpw-primary" data-sxpw-credits>' + esc(say('top_up')) + '</button>'
        + '<button type="button" class="sxpw-link" data-sxpw-to-plans>' + esc(say('plans_link')) + '</button></div>';
    }
    return '<p class="sxpw-text">' + esc(say(kind + '_text')) + '</p>'
      + '<div class="sxpw-plans" data-sxpw-plans-host><div class="sxpw-loading">' + esc(say('loading')) + '</div></div>'
      + '<button type="button" class="sxpw-link sxpw-credits-link" data-sxpw-credits>' + esc(say('credits_link')) + '</button>';
  }

  function render() {
    if (!node || !current) return;
    var kind = current.kind;
    node.querySelector('.sxpw-panel').innerHTML =
      '<button type="button" class="sxpw-x" data-sxpw-close aria-label="' + esc(say('close')) + '">×</button>'
      + '<span class="sxpw-eyebrow">' + esc(say('eyebrow')) + '</span>'
      + '<h2 id="sxpwTitle">' + esc(say(kind + '_title')) + '</h2>'
      + body(kind, current);
    node.querySelector('.sxpw-panel').dataset.kind = kind;
    if (kind !== 'balance') fillPlans();
  }

  function ensureNode() {
    if (node) return node;
    node = document.createElement('div');
    node.className = 'sxpw';
    node.setAttribute('role', 'dialog');
    node.setAttribute('aria-modal', 'true');
    node.setAttribute('aria-labelledby', 'sxpwTitle');
    node.hidden = true;
    node.innerHTML = '<div class="sxpw-backdrop" data-sxpw-close></div><section class="sxpw-panel" tabindex="-1"></section>';
    node.addEventListener('click', onClick);
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && node && !node.hidden) close(); });
    document.body.appendChild(node);
    return node;
  }

  function onClick(event) {
    var target = event.target;
    if (target.closest('[data-sxpw-close]')) { close(); return; }
    var plan = target.closest('[data-sxpw-plan]');
    if (plan) {
      var id = plan.getAttribute('data-sxpw-plan');
      close();
      if (typeof host.onPlan === 'function') host.onPlan(id);
      return;
    }
    if (target.closest('[data-sxpw-credits]')) {
      close();
      if (typeof host.onCredits === 'function') host.onCredits();
      return;
    }
    if (target.closest('[data-sxpw-to-plans]')) {
      current = { kind: 'start', balance: current ? current.balance : 0, required: 0 };
      render();
    }
  }

  function show(kind, info) {
    // A page inside another page (the website's hidden Pro Studio frame)
    // opens the window in the page the person is looking at.
    try {
      if (root.top && root.top !== root && root.top.SylvexPaywall && root.top.SylvexPaywall !== api) {
        return root.top.SylvexPaywall.show(kind, info);
      }
    } catch (_) { /* another origin: show it here */ }
    if (typeof document === 'undefined' || !document.body) return;
    kind = kind === 'balance' || kind === 'subscription' ? kind : 'start';
    info = info || {};
    // The same refusal from a retried request does not reopen it.
    var now = Date.now();
    if (node && !node.hidden && current && current.kind === kind && now - lastShown < 1500) return;
    lastShown = now;
    current = { kind: kind, required: num(info.required), balance: num(info.balance) };
    ensureNode();
    render();
    node.hidden = false;
    document.documentElement.classList.add('sxpw-open');
    var panel = node.querySelector('.sxpw-panel');
    try { panel.focus({ preventScroll: true }); } catch (_) { panel.focus(); }
  }

  function close() {
    if (!node) return;
    node.hidden = true;
    current = null;
    document.documentElement.classList.remove('sxpw-open');
  }

  function configure(options) {
    Object.keys(options || {}).forEach(function (key) { host[key] = options[key]; });
    if (node && current) render();
  }

  var api = {
    configure: configure, show: show, close: close, classify: classify,
    isOpen: function () { return !!(node && !node.hidden); },
  };
  root.SylvexPaywall = api;
  watch();
})(typeof window !== 'undefined' ? window : this);
