/* SYLVEX Store cards: subscription plans, credit packages and the custom
   amount, shared by the Website Store (sylvex-website/store.html) and the
   Telegram Mini App shop view (sylvex-ai-webapp/webapp/cabinet.html).

   Keep this file byte-identical in sylvex-website/js/store-cards.js and
   sylvex-ai-webapp/webapp/js/store-cards.js. Each host passes its own
   strings (t), locale and purchase callbacks; nothing here talks to the
   network or changes how a purchase is paid.

   What can be bought is decided by the host, never by this file:
   - plans are selectable only when isPlanAvailable(plan, period) says so;
   - a credit card continues only when packIdForUsd(usd) returns a product;
   - a custom amount continues only when the host sets customPurchase.
   The Telegram Mini App enables all three from the server catalog
   (/api/public/shop/catalog); the Website keeps its existing packs only.
   Prices, credits and Stars are always re-derived on the server. */
(function (root) {
  'use strict';

  var CREDITS_PER_USD = 100;
  var CUSTOM_MIN_USD = 1;
  var CUSTOM_MAX_USD = 1000;
  var DEFAULT_PACK_USD = 10;

  var PLANS = [
    { id: 'starter', name: 'Starter', monthlyUsd: 5, annualUsd: 48, monthlyCredits: 100 },
    { id: 'pro', name: 'Pro', monthlyUsd: 10, annualUsd: 96, monthlyCredits: 300 },
    { id: 'max', name: 'Max', monthlyUsd: 25, annualUsd: 240, monthlyCredits: 1000, popular: true },
    { id: 'ultra', name: 'Ultra', monthlyUsd: 50, annualUsd: 480, monthlyCredits: 2500 },
    { id: 'creator', name: 'Creator', monthlyUsd: 100, annualUsd: 960, monthlyCredits: 5500 },
  ];

  var CREDIT_PACK_USD = [5, 10, 20, 30, 40, 50, 100, 200];

  // Credit packages the backend already sells (SHOP_ITEMS in
  // sylvex-ai-webapp/main.py). Only these continue to checkout.
  var LEGACY_PACK_IDS = { 5: 'pack_500', 10: 'pack_1000', 20: 'pack_2000', 30: 'pack_3000', 40: 'pack_4000', 50: 'pack_5000' };

  // Credits per example: the cheapest user-selectable generation in each
  // category at SYLVEX retail prices. These defaults mirror the server's
  // live selection (main.py store_generation_examples); a host passing the
  // catalog's `examples` overrides them. A count is how many of that one
  // example the balance covers; the rows are alternative uses of the same
  // balance, not separate allowances. Text is one request of 1,000 input +
  // 1,000 output tokens.
  var EXAMPLES = [
    { key: 'photo', cost: 3, model: 'imagen_4_fast', label: 'Imagen 4 Fast' },
    { key: 'video', cost: 9, model: 'seedance_1_5_pro', label: 'Seedance 1.5 Pro', seconds: 5, resolution: '480p' },
    { key: 'music', cost: 6, model: 'google_lyria_3_clip', label: 'Google Lyria 3 Clip', seconds: 30 },
    { key: 'voice', cost: 1, model: 'gemini_3_1_flash_tts_preview', label: 'Gemini 3.1 Flash TTS', characters: 1000 },
    { key: 'text', cost: 1, model: 'qwen_turbo', label: 'Qwen Turbo', inputTokens: 1000, outputTokens: 1000, inputCredits: 0.0075, outputCredits: 0.03 },
  ];

  // Server catalog examples ({photo: {credits, label, ...}, ...}) -> rows.
  function resolveExamples(server) {
    return EXAMPLES.map(function (example) {
      var live = server && server[example.key];
      if (!live || !(Number(live.credits) > 0)) return example;
      return {
        key: example.key,
        cost: Number(live.credits),
        model: live.model || example.model,
        label: live.label || example.label,
        seconds: live.seconds || example.seconds,
        resolution: live.resolution || example.resolution,
        characters: live.characters || example.characters,
        inputTokens: live.input_tokens || example.inputTokens,
        outputTokens: live.output_tokens || example.outputTokens,
        inputCredits: live.input_credits != null ? Number(live.input_credits) : example.inputCredits,
        outputCredits: live.output_credits != null ? Number(live.output_credits) : example.outputCredits,
      };
    });
  }

  var EN = {
    store_period_month: 'Monthly',
    store_period_year: 'Annual',
    store_per_month: '/ mo',
    store_billed_monthly: 'One month · no auto-renewal',
    store_billed_annually: '{total} for 12 months · save {pct}%',
    store_billed_monthly_auto: 'Billed monthly · cancel anytime',
    store_billed_annually_auto: '{total} billed yearly · save {pct}% · cancel anytime',
    store_credits_monthly: 'Every paid month',
    store_credits_annual: 'Full annual allocation upfront',
    store_per_year: '/ year',
    store_billed_annually_stars: 'One payment for 12 months · save {pct}% · no auto-renewal',
    store_renews_every_30_days: 'Automatically renews every 30 days. Cancel anytime.',
    store_custom_input_credits: 'Amount of ⚡',
    store_custom_range_credits: 'From {min} to {max} ⚡',
    store_custom_error_credits: 'Enter a whole number of ⚡ from {min} to {max}.',
    store_examples_title: 'What you can create',
    store_example_photo: 'Images',
    store_example_video: 'Video · 5 sec',
    store_example_music: 'Music · {seconds} sec',
    store_example_voice: 'Voice · 1,000 chars',
    store_example_text: 'Text · 1K in + 1K out',
    store_by_tokens: 'By tokens',
    store_select_plan: 'Select plan',
    store_plan_soon: 'Coming soon',
    store_popular: 'Popular',
    store_billing_period: 'Billing period',
    store_business_title: 'For businesses and organizations',
    store_business_text: 'For questions about using the SYLVEX platform in your organization, contact our sales team.',
    store_contact_sales: 'Contact Sales',
    store_credits_label: 'SYLVEX credits',
    store_select: 'Select',
    store_selected: 'Selected',
    store_custom_title: 'Custom amount',
    store_custom_range: 'From {min} to {max}',
    store_custom_input: 'Amount in USD',
    store_custom_error: 'Enter an amount from {min} to {max}.',
    store_custom_cents: 'Use at most two decimal places.',
    store_summary_package: 'Selected package',
    store_summary_credits: 'Credits to add',
    store_continue: 'Continue to payment',
    store_pack_soon: 'This package isn’t available for purchase yet.',
    store_custom_soon: 'Custom amounts will be available soon.',
    store_examples_note: 'Examples are alternative uses of the same balance, not separate allowances. Each uses the cheapest model in its category at current prices: images {photo}; video {video}; music {music}; voice {voice}; text {text}.',
    store_note_photo: '{model}, {credits} ⚡ per image',
    store_note_video: '{model} {resolution}, {credits} ⚡ per {seconds} sec',
    store_note_music: '{model}, {credits} ⚡ per {seconds} sec',
    store_note_voice: '{model}, {credits} ⚡ per 1,000 characters',
    store_note_text: '{model}, {input} ⚡ for 1,000 input + {output} ⚡ for 1,000 output tokens, minimum {credits} ⚡ per request',
  };

  var ICONS = {
    photo: '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="15.5" cy="8.5" r="1.6"/><path d="M3.5 16.5l5.2-5.2a1.5 1.5 0 0 1 2.1 0l7.7 7.7"/>',
    video: '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="M16 10.5l4.2-2.6a.5.5 0 0 1 .8.4v7.4a.5.5 0 0 1-.8.4L16 13.5"/>',
    music: '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    voice: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    text: '<path d="M4 12a8 8 0 1 1 3.4 6.5L4 20l1.1-3.6A7.9 7.9 0 0 1 4 12z"/>',
    bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6L13 3z"/>',
    sliders: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><path d="M15 5v4M9 10v4M17 15v4"/>',
    chevron: '<path d="M6 9l6 6 6-6"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="M8.3 12.3l2.5 2.5 5-5.2"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  };

  function icon(name, cls) {
    return '<svg class="' + (cls || 'sxs-icon') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + ICONS[name] + '</svg>';
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function creditsForUsd(usd) {
    return Math.round(Number(usd) * CREDITS_PER_USD);
  }

  function exampleCount(credits, cost) {
    if (!cost || !(credits >= 0)) return null;
    return Math.floor(credits / cost);
  }

  function planPricing(plan, period) {
    if (period === 'year') {
      return {
        period: 'year',
        displayUsd: plan.annualUsd / 12,
        decimals: 2,
        totalUsd: plan.annualUsd,
        discountPct: Math.round((1 - plan.annualUsd / (plan.monthlyUsd * 12)) * 100),
        credits: plan.monthlyCredits * 12,
      };
    }
    return { period: 'month', displayUsd: plan.monthlyUsd, decimals: 0, totalUsd: plan.monthlyUsd, discountPct: 0, credits: plan.monthlyCredits };
  }

  function packIdForUsd(usd) {
    return LEGACY_PACK_IDS[usd] || null;
  }

  // Validates the custom amount: dollars, at most two decimals, inside
  // [CUSTOM_MIN_USD, CUSTOM_MAX_USD].
  function parseCustomAmount(raw) {
    var text = String(raw == null ? '' : raw).trim().replace(',', '.');
    if (!text) return { ok: false, error: 'empty' };
    if (!/^\d+(\.\d+)?$/.test(text)) return { ok: false, error: 'range' };
    if (/\.\d{3,}$/.test(text)) return { ok: false, error: 'cents' };
    var usd = Number(text);
    if (!(usd >= CUSTOM_MIN_USD) || usd > CUSTOM_MAX_USD) return { ok: false, error: 'range', usd: usd };
    return { ok: true, usd: usd, credits: creditsForUsd(usd) };
  }

  function makeFormat(locale) {
    var number = new Intl.NumberFormat(locale || 'en', { maximumFractionDigits: 0 });
    var decimal = new Intl.NumberFormat(locale || 'en', { maximumFractionDigits: 4 });
    return {
      number: function (n) { return number.format(n); },
      decimal: function (n) { return n == null ? '—' : decimal.format(n); },
      // Dollar amounts keep the locale's digit grouping ("$1 000" in
      // Russian) but always use a point before cents ("$10.00").
      usd: function (n, decimals) {
        var parts = Number(n).toFixed(decimals || 0).split('.');
        return '$' + number.format(Number(parts[0])) + (parts[1] ? '.' + parts[1] : '');
      },
    };
  }

  function makeT(t) {
    return function (key, vars) {
      var value = (typeof t === 'function' && t(key)) || EN[key] || key;
      if (value === key && EN[key]) value = EN[key];
      Object.keys(vars || {}).forEach(function (name) {
        value = value.split('{' + name + '}').join(vars[name]);
      });
      return value;
    };
  }

  function creditPanel(fmt, credits, note, strong) {
    return '<div class="sxs-credit' + (strong ? ' sxs-credit--strong' : '') + '">' +
      '<div class="sxs-credit-amount">' + icon('bolt', 'sxs-bolt') + '<span data-sxs-credits>' + escapeHtml(fmt.number(credits)) + '</span><span class="sxs-emoji" aria-hidden="true">⚡</span></div>' +
      '<div class="sxs-credit-note">' + escapeHtml(note) + '</div>' +
    '</div>';
  }

  function exampleValue(tr, fmt, credits, example) {
    if (example.cost == null) return tr('store_by_tokens');
    var count = exampleCount(credits, example.cost);
    return count == null ? '—' : fmt.number(count);
  }

  function examplesBlock(tr, fmt, credits, examples) {
    return '<div class="sxs-examples">' +
      '<div class="sxs-examples-title">' + escapeHtml(tr('store_examples_title')) + '</div>' +
      examples.map(function (example) {
        var value = exampleValue(tr, fmt, credits, example);
        return '<div class="sxs-example" data-example="' + example.key + '">' +
          '<span class="sxs-example-label">' + icon(example.key) + '<span>' + escapeHtml(tr('store_example_' + example.key, { seconds: example.seconds || 30 })) + '</span></span>' +
          '<span class="sxs-example-value" data-sxs-example-value>' + escapeHtml(value) + '</span>' +
        '</div>';
      }).join('') +
    '</div>';
  }

  function examplesNote(tr, fmt, examples) {
    var parts = {};
    examples.forEach(function (example) {
      parts[example.key] = tr('store_note_' + example.key, {
        model: example.label || example.model,
        credits: fmt.decimal(example.cost),
        seconds: example.seconds || '',
        resolution: example.resolution || '',
        input: fmt.decimal(example.inputCredits),
        output: fmt.decimal(example.outputCredits),
      }).replace(/\s+,/g, ',');
    });
    return '<p class="sxs-footnote">' + escapeHtml(tr('store_examples_note', parts)) + '</p>';
  }

  /* ---------------- scroll stability ---------------- */

  // The element that actually scrolls around `el` (the Mini App scrolls a
  // <main class="scroll">, the Website the document).
  function scrollParent(el) {
    for (var node = el && el.parentElement; node; node = node.parentElement) {
      var style = root.getComputedStyle ? root.getComputedStyle(node) : null;
      if (style && /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) return node;
    }
    return (typeof document !== 'undefined' && document.scrollingElement) || null;
  }

  // Runs a full re-render without moving what the user is looking at: the
  // first card still on screen keeps its exact position afterwards.
  function keepScroll(container, render) {
    var scroller = typeof document !== 'undefined' ? scrollParent(container) : null;
    var anchor = null, key = null, top = 0;
    if (scroller && container.querySelectorAll) {
      var view = scroller === document.scrollingElement ? 0 : scroller.getBoundingClientRect().top;
      var cards = container.querySelectorAll('[data-plan],[data-pack-usd]');
      for (var i = 0; i < cards.length; i++) {
        var rect = cards[i].getBoundingClientRect();
        if (rect.bottom > view) { anchor = cards[i]; break; }
      }
      if (anchor) {
        key = anchor.hasAttribute('data-plan') ? '[data-plan="' + anchor.getAttribute('data-plan') + '"]'
          : '[data-pack-usd="' + anchor.getAttribute('data-pack-usd') + '"]';
        top = anchor.getBoundingClientRect().top;
      }
    }
    var saved = scroller ? scroller.scrollTop : 0;
    render();
    if (!scroller) return;
    var again = key ? container.querySelector(key) : null;
    if (again) scroller.scrollTop += again.getBoundingClientRect().top - top;
    else scroller.scrollTop = saved;
  }

  function focusQuietly(el) {
    if (!el || typeof el.focus !== 'function') return;
    try { el.focus({ preventScroll: true }); } catch (_) { /* old WebViews */ }
  }

  /* ---------------- subscriptions ---------------- */

  var planState = new WeakMap();

  function renderPlans(container, options) {
    var opts = options || {};
    var tr = makeT(opts.t);
    var fmt = makeFormat(opts.locale);
    var state = planState.get(container) || { periods: {} };
    planState.set(container, state);
    var isAvailable = opts.isPlanAvailable || function () { return false; };
    // Only a host whose payment provider renews plans automatically (the
    // Website's Stripe Checkout) says so; otherwise plans are one-off terms.
    var autoRenew = opts.renewal === 'auto';
    // Stars mode (Telegram Mini App): the host prices every product in
    // Telegram Stars via starsPrice(usdCents) and nothing shows USD.
    var starsPrice = typeof opts.starsPrice === 'function' ? opts.starsPrice : null;
    var examples = resolveExamples(opts.examples);

    function planView(plan, period) {
      var price = planPricing(plan, period);
      var note = period === 'year'
        ? (starsPrice ? tr('store_billed_annually_stars', { pct: price.discountPct })
          : tr(autoRenew ? 'store_billed_annually_auto' : 'store_billed_annually', { total: fmt.usd(price.totalUsd, 0), pct: price.discountPct }))
        : tr(starsPrice && autoRenew ? 'store_renews_every_30_days'
          : autoRenew ? 'store_billed_monthly_auto' : 'store_billed_monthly');
      return {
        price: price,
        available: !!isAvailable(plan.id, period),
        note: note,
        // Stars mode shows what one payment costs: a month, or the whole year.
        amount: starsPrice ? fmt.number(starsPrice(Math.round(price.totalUsd * 100))) + ' ⭐' : fmt.usd(price.displayUsd, price.decimals),
        unit: tr(starsPrice && period === 'year' ? 'store_per_year' : 'store_per_month'),
        creditNote: tr(period === 'year' ? 'store_credits_annual' : 'store_credits_monthly'),
      };
    }

    // Month / Year: only the values inside this one card change - no
    // re-render, so nothing on the page moves.
    function updatePlanCard(card, plan, period) {
      var v = planView(plan, period);
      card.querySelectorAll('[data-sxs-period]').forEach(function (btn) {
        btn.setAttribute('aria-pressed', String(btn.dataset.sxsPeriod === period));
      });
      card.querySelector('.sxs-price-amount').textContent = v.amount;
      card.querySelector('.sxs-price-unit').textContent = v.unit;
      card.querySelector('.sxs-price-note').textContent = v.note;
      card.querySelector('[data-sxs-credits]').textContent = fmt.number(v.price.credits);
      card.querySelector('.sxs-credit-note').textContent = v.creditNote;
      card.querySelectorAll('.sxs-example').forEach(function (row, i) {
        row.querySelector('[data-sxs-example-value]').textContent = exampleValue(tr, fmt, v.price.credits, examples[i]);
      });
      var cta = card.querySelector('[data-sxs-select-plan]');
      cta.disabled = !v.available;
      if (v.available) cta.removeAttribute('aria-disabled'); else cta.setAttribute('aria-disabled', 'true');
      cta.textContent = tr(v.available ? 'store_select_plan' : 'store_plan_soon');
    }

    function planCard(plan) {
      var period = state.periods[plan.id] || 'month';
      var v = planView(plan, period);
      var price = v.price, available = v.available, note = v.note, amount = v.amount, unit = v.unit;
      return '<article class="sxs-card sxs-plan' + (plan.popular ? ' is-popular' : '') + '" data-plan="' + plan.id + '">' +
        '<div class="sxs-plan-head"><h3 class="sxs-plan-name">' + escapeHtml(plan.name) + '</h3>' +
          (plan.popular ? '<span class="sxs-badge">' + escapeHtml(tr('store_popular')) + '</span>' : '') + '</div>' +
        '<div class="sxs-seg" role="group" aria-label="' + escapeHtml(tr('store_billing_period')) + '">' +
          ['month', 'year'].map(function (p) {
            return '<button type="button" data-sxs-period="' + p + '" aria-pressed="' + (p === period) + '">' + escapeHtml(tr('store_period_' + p)) + '</button>';
          }).join('') +
        '</div>' +
        '<div class="sxs-price"><span class="sxs-price-amount">' + escapeHtml(amount) + '</span><span class="sxs-price-unit">' + escapeHtml(unit) + '</span></div>' +
        '<div class="sxs-price-note">' + escapeHtml(note) + '</div>' +
        creditPanel(fmt, price.credits, v.creditNote, true) +
        examplesBlock(tr, fmt, price.credits, examples) +
        '<button type="button" class="sxs-plan-cta" data-sxs-select-plan' + (available ? '' : ' disabled aria-disabled="true"') + '>' +
          escapeHtml(tr(available ? 'store_select_plan' : 'store_plan_soon')) + '</button>' +
      '</article>';
    }

    function businessCard() {
      return '<article class="sxs-card sxs-plan sxs-business" data-plan="business">' +
        '<div class="sxs-plan-head"><h3 class="sxs-plan-name">SYLVEX Business</h3></div>' +
        '<div class="sxs-business-title">' + escapeHtml(tr('store_business_title')) + '</div>' +
        '<p class="sxs-business-text">' + escapeHtml(tr('store_business_text')) + '</p>' +
        '<button type="button" class="sxs-continue sxs-business-cta" data-sxs-contact-sales>' + escapeHtml(tr('store_contact_sales')) + icon('arrow', 'sxs-arrow') + '</button>' +
      '</article>';
    }

    container.classList.add('sxs-root', 'sxs-plans');
    keepScroll(container, function () {
      container.innerHTML = '<div class="sxs-grid">' + PLANS.map(planCard).join('') + businessCard() + '</div>' + examplesNote(tr, fmt, examples);
    });
    container.__sxsUpdatePlanCard = updatePlanCard;

    if (!container.__sxsPlansBound) {
      container.__sxsPlansBound = true;
      container.addEventListener('click', function (event) {
        var periodBtn = event.target.closest('[data-sxs-period]');
        var card = event.target.closest('[data-plan]');
        if (periodBtn && card) {
          var plan = PLANS.filter(function (p) { return p.id === card.dataset.plan; })[0];
          state.periods[card.dataset.plan] = periodBtn.dataset.sxsPeriod;
          if (plan && typeof card.querySelectorAll === 'function') container.__sxsUpdatePlanCard(card, plan, periodBtn.dataset.sxsPeriod);
          else renderPlans(container, container.__sxsPlanOptions); // no live DOM (headless hosts)
          focusQuietly(periodBtn);
          return;
        }
        var select = event.target.closest('[data-sxs-select-plan]');
        if (select && card && !select.disabled && typeof container.__sxsPlanOptions.onSelectPlan === 'function') {
          container.__sxsPlanOptions.onSelectPlan(card.dataset.plan, state.periods[card.dataset.plan] || 'month', select);
          return;
        }
        var sales = event.target.closest('[data-sxs-contact-sales]');
        if (sales && typeof container.__sxsPlanOptions.onContactSales === 'function') {
          container.__sxsPlanOptions.onContactSales(sales);
        }
      });
    }
    container.__sxsPlanOptions = opts;
  }

  /* ---------------- credits ---------------- */

  var creditState = new WeakMap();

  function renderCredits(container, options) {
    var opts = options || {};
    var tr = makeT(opts.t);
    var fmt = makeFormat(opts.locale);
    var state = creditState.get(container) || { usd: opts.defaultUsd || DEFAULT_PACK_USD, customOpen: false, customRaw: '' };
    creditState.set(container, state);
    var starsPrice = typeof opts.starsPrice === 'function' ? opts.starsPrice : null;
    // Stars mode takes custom amounts in whole credits (⚡), within the
    // host's customCredits {min, max}; otherwise in USD.
    var customCredits = starsPrice ? (opts.customCredits || { min: CUSTOM_MIN_USD * CREDITS_PER_USD, max: CUSTOM_MAX_USD * CREDITS_PER_USD }) : null;
    var range = customCredits
      ? { min: fmt.number(customCredits.min), max: fmt.number(customCredits.max) }
      : { min: fmt.usd(CUSTOM_MIN_USD, 0), max: fmt.usd(CUSTOM_MAX_USD, 0) };
    var packList = opts.packUsd || CREDIT_PACK_USD;
    var examples = resolveExamples(opts.examples);

    function priceLabel(usd, decimals) {
      return starsPrice ? fmt.number(starsPrice(Math.round(usd * 100))) + ' ⭐' : fmt.usd(usd, decimals);
    }

    function parseCustom(raw) {
      if (!customCredits) return parseCustomAmount(raw);
      var text = String(raw == null ? '' : raw).replace(/[\s\u00a0\u202f]/g, '');
      if (!text) return { ok: false, error: 'empty' };
      if (!/^\d+$/.test(text)) return { ok: false, error: 'range' };
      var credits = Number(text);
      if (credits < customCredits.min || credits > customCredits.max) return { ok: false, error: 'range' };
      return { ok: true, credits: credits, usd: credits / CREDITS_PER_USD };
    }

    function customError(parsed) {
      if (!state.customRaw || parsed.ok) return '';
      if (customCredits) return tr('store_custom_error_credits', range);
      return tr(parsed.error === 'cents' ? 'store_custom_cents' : 'store_custom_error', range);
    }

    function packCard(usd) {
      var selected = !state.customOpen && state.usd === usd;
      var credits = creditsForUsd(usd);
      return '<article class="sxs-card sxs-pack' + (selected ? ' is-selected' : '') + '" data-pack-usd="' + usd + '"' +
          ' data-checkout-card data-checkout-title="' + escapeHtml(fmt.number(credits) + ' ⚡') + '" data-checkout-price="' + escapeHtml(priceLabel(usd, 0)) + '">' +
        '<div class="sxs-pack-head"><span class="sxs-pack-price">' + escapeHtml(priceLabel(usd, 0)) + '</span>' +
          (selected ? icon('check', 'sxs-pick sxs-pick--on') : '<span class="sxs-pick" aria-hidden="true"></span>') + '</div>' +
        creditPanel(fmt, credits, tr('store_credits_label'), false) +
        examplesBlock(tr, fmt, credits, examples) +
        '<button type="button" class="sxs-pack-cta" data-sxs-pick="' + usd + '" aria-pressed="' + selected + '">' + escapeHtml(tr(selected ? 'store_selected' : 'store_select')) + '</button>' +
      '</article>';
    }

    function customCard() {
      var parsed = parseCustom(state.customRaw);
      var credits = parsed.ok ? parsed.credits : 0;
      var error = customError(parsed);
      return '<section class="sxs-card sxs-custom' + (state.customOpen ? ' is-open' : '') + '">' +
        '<button type="button" class="sxs-custom-head" data-sxs-custom-toggle aria-expanded="' + state.customOpen + '" aria-controls="sxsCustomBody">' +
          icon('sliders', 'sxs-custom-icon') +
          '<span class="sxs-custom-text"><span class="sxs-custom-title">' + escapeHtml(tr('store_custom_title')) + '</span>' +
          '<span class="sxs-custom-range">' + escapeHtml(tr(customCredits ? 'store_custom_range_credits' : 'store_custom_range', range)) + '</span></span>' +
          icon('chevron', 'sxs-chevron') +
        '</button>' +
        '<div class="sxs-custom-body" id="sxsCustomBody"' + (state.customOpen ? '' : ' hidden') + '>' +
          '<label class="sxs-amount"><span class="sxs-amount-label">' + escapeHtml(tr(customCredits ? 'store_custom_input_credits' : 'store_custom_input')) + '</span>' +
            '<span class="sxs-amount-field' + (error ? ' is-invalid' : '') + '"><span aria-hidden="true">' + (customCredits ? '⚡' : '$') + '</span>' +
            '<input type="text" inputmode="' + (customCredits ? 'numeric' : 'decimal') + '" autocomplete="off" data-sxs-custom-input value="' + escapeHtml(state.customRaw) + '" placeholder="' + (customCredits ? '1000' : '10') + '"' +
              ' aria-invalid="' + !!error + '" aria-describedby="sxsCustomError"></span></label>' +
          '<div class="sxs-field-error" id="sxsCustomError" role="alert">' + escapeHtml(error) + '</div>' +
          creditPanel(fmt, credits, tr('store_credits_label'), false) +
          examplesBlock(tr, fmt, credits, examples) +
        '</div>' +
      '</section>';
    }

    // What Continue would buy right now: a host product id for a package,
    // a canonical USD string (or, in Stars mode, a whole number of credits)
    // for a custom amount, or nothing.
    function continueTarget() {
      if (state.customOpen) {
        var parsed = parseCustom(state.customRaw);
        if (!opts.customPurchase) return { note: tr('store_custom_soon') };
        if (!parsed.ok) return {};
        return customCredits ? { customAmount: String(parsed.credits) } : { customAmount: parsed.usd.toFixed(2) };
      }
      var packId = (opts.packIdForUsd || packIdForUsd)(state.usd);
      return packId ? { packId: packId } : { note: tr('store_pack_soon') };
    }

    function continueAttrs(target) {
      if (target.packId) return ' data-pack-id="' + escapeHtml(target.packId) + '"';
      if (target.customAmount) return ' data-custom-amount="' + escapeHtml(target.customAmount) + '"';
      return ' disabled aria-disabled="true"';
    }

    function summary() {
      var usd, credits, target = continueTarget(), note = target.note || '';
      if (state.customOpen) {
        var parsed = parseCustom(state.customRaw);
        usd = parsed.ok ? parsed.usd : 0;
        credits = parsed.ok ? parsed.credits : 0;
      } else {
        usd = state.usd;
        credits = creditsForUsd(usd);
      }
      var price = credits ? priceLabel(usd, 2) : (starsPrice ? '—' : fmt.usd(0, 2));
      return '<div class="sxs-summary" data-checkout-card data-checkout-title="' + escapeHtml(fmt.number(credits) + ' ⚡') + '" data-checkout-price="' + escapeHtml(price) + '">' +
        '<div class="sxs-summary-row"><span>' + escapeHtml(tr('store_summary_package')) + '</span><b data-sxs-summary-usd>' + escapeHtml(price) + '</b></div>' +
        '<div class="sxs-summary-row"><span>' + escapeHtml(tr('store_summary_credits')) + '</span><b>' + icon('bolt', 'sxs-bolt') + '<span data-sxs-summary-credits>' + escapeHtml(fmt.number(credits)) + '</span><span class="sxs-emoji" aria-hidden="true">⚡</span></b></div>' +
        '<button type="button" class="sxs-continue" data-sxs-continue' + continueAttrs(target) + '>' +
          escapeHtml(tr('store_continue')) + icon('arrow', 'sxs-arrow') + '</button>' +
        (note ? '<p class="sxs-summary-note">' + escapeHtml(note) + '</p>' : '') +
      '</div>';
    }

    function paint() {
      container.classList.add('sxs-root', 'sxs-credits');
      keepScroll(container, function () {
        container.innerHTML =
          '<div class="sxs-grid" role="group">' + packList.map(packCard).join('') + '</div>' +
          customCard() + summary() + examplesNote(tr, fmt, examples);
      });
    }

    // Picking another package updates the cards and the summary in place.
    function selectPack(usd) {
      if (state.customOpen) {
        state.usd = usd;
        state.customOpen = false;
        paint();
        return;
      }
      state.usd = usd;
      container.querySelectorAll('[data-pack-usd]').forEach(function (card) {
        var on = Number(card.dataset.packUsd) === usd;
        card.classList.toggle('is-selected', on);
        var pick = card.querySelector('.sxs-pick');
        if (pick) pick.outerHTML = on ? icon('check', 'sxs-pick sxs-pick--on') : '<span class="sxs-pick" aria-hidden="true"></span>';
        var cta = card.querySelector('[data-sxs-pick]');
        if (cta) { cta.setAttribute('aria-pressed', String(on)); cta.textContent = tr(on ? 'store_selected' : 'store_select'); }
      });
      var old = container.querySelector('.sxs-summary');
      if (old) old.outerHTML = summary();
    }

    // Typing in the custom amount updates credits, examples and summary in
    // place so the input keeps focus and caret.
    function updateCustom() {
      var parsed = parseCustom(state.customRaw);
      var credits = parsed.ok ? parsed.credits : 0;
      var body = container.querySelector('.sxs-custom-body');
      var field = container.querySelector('.sxs-amount-field');
      var input = container.querySelector('[data-sxs-custom-input]');
      var error = customError(parsed);
      container.querySelector('#sxsCustomError').textContent = error;
      field.classList.toggle('is-invalid', !!error);
      input.setAttribute('aria-invalid', String(!!error));
      body.querySelector('[data-sxs-credits]').textContent = fmt.number(credits);
      body.querySelectorAll('.sxs-example').forEach(function (row, i) {
        row.querySelector('[data-sxs-example-value]').textContent = exampleValue(tr, fmt, credits, examples[i]);
      });
      var usd = parsed.ok ? parsed.usd : 0;
      var price = credits ? priceLabel(usd, 2) : (starsPrice ? '—' : fmt.usd(0, 2));
      var summaryEl = container.querySelector('.sxs-summary');
      summaryEl.querySelector('[data-sxs-summary-usd]').textContent = price;
      summaryEl.querySelector('[data-sxs-summary-credits]').textContent = fmt.number(credits);
      summaryEl.dataset.checkoutTitle = fmt.number(credits) + ' ⚡';
      summaryEl.dataset.checkoutPrice = price;
      var button = summaryEl.querySelector('[data-sxs-continue]');
      var target = continueTarget();
      button.disabled = !(target.packId || target.customAmount);
      if (button.disabled) button.setAttribute('aria-disabled', 'true'); else button.removeAttribute('aria-disabled');
      if (target.customAmount) button.setAttribute('data-custom-amount', target.customAmount); else button.removeAttribute('data-custom-amount');
    }

    paint();
    // Listeners are bound once; they reach the latest render's options and
    // closures through these, so a re-render (e.g. after the host's catalog
    // loads) takes effect.
    container.__sxsCreditOptions = opts;
    container.__sxsCreditPaint = paint;
    container.__sxsCreditUpdate = updateCustom;
    container.__sxsCreditSelect = selectPack;
    container.__sxsCreditPackId = function (usd) { return (opts.packIdForUsd || packIdForUsd)(usd); };
    if (container.__sxsCreditsBound) return;
    container.__sxsCreditsBound = true;

    container.addEventListener('click', function (event) {
      var toggle = event.target.closest('[data-sxs-custom-toggle]');
      if (toggle) {
        state.customOpen = !state.customOpen;
        container.__sxsCreditPaint();
        var head = container.querySelector('[data-sxs-custom-toggle]');
        var input = container.querySelector('[data-sxs-custom-input]');
        if (state.customOpen && input) input.focus(); else if (head) head.focus();
        return;
      }
      var cont = event.target.closest('[data-sxs-continue]');
      if (cont) {
        var hostOptions = container.__sxsCreditOptions;
        if (cont.disabled) return;
        if (cont.dataset.packId && typeof hostOptions.onContinue === 'function') {
          hostOptions.onContinue(cont.dataset.packId, cont);
        } else if (cont.dataset.customAmount && hostOptions.customPurchase && typeof hostOptions.onContinueCustom === 'function') {
          // A USD string, or in Stars mode a whole number of credits.
          hostOptions.onContinueCustom(cont.dataset.customAmount, cont);
        }
        return;
      }
      var card = event.target.closest('[data-pack-usd]');
      if (card) {
        var usd = Number(card.dataset.packUsd);
        container.__sxsCreditSelect(usd);
        var pick = container.querySelector('[data-sxs-pick="' + usd + '"]');
        focusQuietly(pick);
        // Hosts that ask for it (the Mini App): the card's Select button is
        // the purchase - open the checkout right away, no Continue step.
        var options = container.__sxsCreditOptions;
        if (event.target.closest('[data-sxs-pick]') && options.selectOpensCheckout && typeof options.onContinue === 'function') {
          var packId = container.__sxsCreditPackId(usd);
          if (packId) options.onContinue(packId, pick);
        }
      }
    });
    container.addEventListener('input', function (event) {
      if (!event.target.matches('[data-sxs-custom-input]')) return;
      state.customRaw = event.target.value;
      container.__sxsCreditUpdate();
    });
  }

  root.SylvexStoreCards = {
    PLANS: PLANS,
    CREDIT_PACK_USD: CREDIT_PACK_USD,
    LEGACY_PACK_IDS: LEGACY_PACK_IDS,
    EXAMPLES: EXAMPLES,
    CREDITS_PER_USD: CREDITS_PER_USD,
    CUSTOM_MIN_USD: CUSTOM_MIN_USD,
    CUSTOM_MAX_USD: CUSTOM_MAX_USD,
    EN: EN,
    creditsForUsd: creditsForUsd,
    exampleCount: exampleCount,
    planPricing: planPricing,
    packIdForUsd: packIdForUsd,
    parseCustomAmount: parseCustomAmount,
    renderPlans: renderPlans,
    renderCredits: renderCredits,
  };
})(typeof window !== 'undefined' ? window : globalThis);
