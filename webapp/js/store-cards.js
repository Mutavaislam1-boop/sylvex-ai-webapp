/* SYLVEX Store cards: subscription plans, credit packages and the custom
   amount, shared by the Website Store (sylvex-website/store.html) and the
   Telegram Mini App shop view (sylvex-ai-webapp/webapp/cabinet.html).

   Keep this file byte-identical in sylvex-website/js/store-cards.js and
   sylvex-ai-webapp/webapp/js/store-cards.js. Each host passes its own
   strings (t), locale and purchase callbacks; nothing here talks to the
   network or changes how a purchase is paid.

   Purchase rules for this phase:
   - Credit cards whose price matches an existing backend product
     (SHOP_ITEMS pack_500..pack_5000) continue to the host's existing
     checkout. $100, $200 and custom amounts render but cannot be bought.
   - The new subscription plans are not purchasable yet: their button is
     disabled unless the host reports the plan as available. */
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

  // Credits per example, from the SYLVEX price engine
  // (calculate_generation_price) for the model Pro Studio uses for that
  // kind of result. A count is how many of that one example the balance
  // covers; the five rows are alternatives, not separate allowances.
  // Text is billed on the tokens actually used, so it has no fixed count.
  var EXAMPLES = [
    { key: 'photo', cost: 6, model: 'seedream_5_0_lite' },
    { key: 'video', cost: 90, model: 'seedance_2_fast' },
    { key: 'music', cost: 6, model: 'google_lyria_3_clip' },
    { key: 'voice', cost: 40, model: 'elevenlabs_eleven_v3' },
    { key: 'text', cost: null, model: 'gpt-5.5' },
  ];

  var EN = {
    store_period_month: 'Monthly',
    store_period_year: 'Annual',
    store_per_month: '/ mo',
    store_billed_monthly: 'Billed monthly',
    store_billed_annually: '{total} billed yearly · save {pct}%',
    store_credits_monthly: 'Every paid month',
    store_credits_annual: 'Full annual allocation upfront',
    store_examples_title: 'What you can create',
    store_example_photo: 'Images',
    store_example_video: 'Video · 5 sec',
    store_example_music: 'Music · 30 sec',
    store_example_voice: 'Voice · 1,000 chars',
    store_example_text: 'Text',
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
    store_examples_note: 'Examples are alternative uses of the same balance, not separate allowances. Based on the default Pro Studio models: images Seedream 5.0 Lite, video Seedance 2.0 Fast 720p, music Lyria 3 (30 sec), voice ElevenLabs v3. Text is billed by the tokens used.',
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
    return {
      number: function (n) { return number.format(n); },
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

  function examplesBlock(tr, fmt, credits) {
    return '<div class="sxs-examples">' +
      '<div class="sxs-examples-title">' + escapeHtml(tr('store_examples_title')) + '</div>' +
      EXAMPLES.map(function (example) {
        var count = exampleCount(credits, example.cost);
        var value = example.cost == null ? tr('store_by_tokens') : (count == null ? '—' : fmt.number(count));
        return '<div class="sxs-example" data-example="' + example.key + '">' +
          '<span class="sxs-example-label">' + icon(example.key) + '<span>' + escapeHtml(tr('store_example_' + example.key)) + '</span></span>' +
          '<span class="sxs-example-value" data-sxs-example-value>' + escapeHtml(value) + '</span>' +
        '</div>';
      }).join('') +
    '</div>';
  }

  function examplesNote(tr) {
    return '<p class="sxs-footnote">' + escapeHtml(tr('store_examples_note')) + '</p>';
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

    function planCard(plan) {
      var period = state.periods[plan.id] || 'month';
      var price = planPricing(plan, period);
      var available = !!isAvailable(plan.id, period);
      var note = period === 'year'
        ? tr('store_billed_annually', { total: fmt.usd(price.totalUsd, 0), pct: price.discountPct })
        : tr('store_billed_monthly');
      return '<article class="sxs-card sxs-plan' + (plan.popular ? ' is-popular' : '') + '" data-plan="' + plan.id + '">' +
        '<div class="sxs-plan-head"><h3 class="sxs-plan-name">' + escapeHtml(plan.name) + '</h3>' +
          (plan.popular ? '<span class="sxs-badge">' + escapeHtml(tr('store_popular')) + '</span>' : '') + '</div>' +
        '<div class="sxs-seg" role="group" aria-label="' + escapeHtml(tr('store_billing_period')) + '">' +
          ['month', 'year'].map(function (p) {
            return '<button type="button" data-sxs-period="' + p + '" aria-pressed="' + (p === period) + '">' + escapeHtml(tr('store_period_' + p)) + '</button>';
          }).join('') +
        '</div>' +
        '<div class="sxs-price"><span class="sxs-price-amount">' + escapeHtml(fmt.usd(price.displayUsd, price.decimals)) + '</span><span class="sxs-price-unit">' + escapeHtml(tr('store_per_month')) + '</span></div>' +
        '<div class="sxs-price-note">' + escapeHtml(note) + '</div>' +
        creditPanel(fmt, price.credits, tr(period === 'year' ? 'store_credits_annual' : 'store_credits_monthly'), true) +
        examplesBlock(tr, fmt, price.credits) +
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
    container.innerHTML = '<div class="sxs-grid">' + PLANS.map(planCard).join('') + businessCard() + '</div>' + examplesNote(tr);

    if (!container.__sxsPlansBound) {
      container.__sxsPlansBound = true;
      container.addEventListener('click', function (event) {
        var periodBtn = event.target.closest('[data-sxs-period]');
        var card = event.target.closest('[data-plan]');
        if (periodBtn && card) {
          state.periods[card.dataset.plan] = periodBtn.dataset.sxsPeriod;
          renderPlans(container, container.__sxsPlanOptions);
          var again = container.querySelector('[data-plan="' + card.dataset.plan + '"] [data-sxs-period="' + periodBtn.dataset.sxsPeriod + '"]');
          if (again) again.focus();
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
    var range = { min: fmt.usd(CUSTOM_MIN_USD, 0), max: fmt.usd(CUSTOM_MAX_USD, 0) };

    function packCard(usd) {
      var selected = !state.customOpen && state.usd === usd;
      var credits = creditsForUsd(usd);
      return '<article class="sxs-card sxs-pack' + (selected ? ' is-selected' : '') + '" data-pack-usd="' + usd + '"' +
          ' data-checkout-card data-checkout-title="' + escapeHtml(fmt.number(credits) + ' ⚡') + '" data-checkout-price="' + escapeHtml(fmt.usd(usd, 0)) + '">' +
        '<div class="sxs-pack-head"><span class="sxs-pack-price">' + escapeHtml(fmt.usd(usd, 0)) + '</span>' +
          (selected ? icon('check', 'sxs-pick sxs-pick--on') : '<span class="sxs-pick" aria-hidden="true"></span>') + '</div>' +
        creditPanel(fmt, credits, tr('store_credits_label'), false) +
        examplesBlock(tr, fmt, credits) +
        '<button type="button" class="sxs-pack-cta" data-sxs-pick="' + usd + '" aria-pressed="' + selected + '">' + escapeHtml(tr(selected ? 'store_selected' : 'store_select')) + '</button>' +
      '</article>';
    }

    function customCard() {
      var parsed = parseCustomAmount(state.customRaw);
      var credits = parsed.ok ? parsed.credits : 0;
      var error = !state.customRaw ? '' : (parsed.ok ? '' : tr(parsed.error === 'cents' ? 'store_custom_cents' : 'store_custom_error', range));
      return '<section class="sxs-card sxs-custom' + (state.customOpen ? ' is-open' : '') + '">' +
        '<button type="button" class="sxs-custom-head" data-sxs-custom-toggle aria-expanded="' + state.customOpen + '" aria-controls="sxsCustomBody">' +
          icon('sliders', 'sxs-custom-icon') +
          '<span class="sxs-custom-text"><span class="sxs-custom-title">' + escapeHtml(tr('store_custom_title')) + '</span>' +
          '<span class="sxs-custom-range">' + escapeHtml(tr('store_custom_range', range)) + '</span></span>' +
          icon('chevron', 'sxs-chevron') +
        '</button>' +
        '<div class="sxs-custom-body" id="sxsCustomBody"' + (state.customOpen ? '' : ' hidden') + '>' +
          '<label class="sxs-amount"><span class="sxs-amount-label">' + escapeHtml(tr('store_custom_input')) + '</span>' +
            '<span class="sxs-amount-field' + (error ? ' is-invalid' : '') + '"><span aria-hidden="true">$</span>' +
            '<input type="text" inputmode="decimal" autocomplete="off" data-sxs-custom-input value="' + escapeHtml(state.customRaw) + '" placeholder="10"' +
              ' aria-invalid="' + !!error + '" aria-describedby="sxsCustomError"></span></label>' +
          '<div class="sxs-field-error" id="sxsCustomError" role="alert">' + escapeHtml(error) + '</div>' +
          creditPanel(fmt, credits, tr('store_credits_label'), false) +
          examplesBlock(tr, fmt, credits) +
        '</div>' +
      '</section>';
    }

    function summary() {
      var usd, credits, packId = null, note = '';
      if (state.customOpen) {
        var parsed = parseCustomAmount(state.customRaw);
        usd = parsed.ok ? parsed.usd : 0;
        credits = parsed.ok ? parsed.credits : 0;
        note = tr('store_custom_soon');
      } else {
        usd = state.usd;
        credits = creditsForUsd(usd);
        packId = (opts.packIdForUsd || packIdForUsd)(usd);
        if (!packId) note = tr('store_pack_soon');
      }
      return '<div class="sxs-summary" data-checkout-card data-checkout-title="' + escapeHtml(fmt.number(credits) + ' ⚡') + '" data-checkout-price="' + escapeHtml(fmt.usd(usd, 2)) + '">' +
        '<div class="sxs-summary-row"><span>' + escapeHtml(tr('store_summary_package')) + '</span><b data-sxs-summary-usd>' + escapeHtml(fmt.usd(usd, 2)) + '</b></div>' +
        '<div class="sxs-summary-row"><span>' + escapeHtml(tr('store_summary_credits')) + '</span><b>' + icon('bolt', 'sxs-bolt') + '<span data-sxs-summary-credits>' + escapeHtml(fmt.number(credits)) + '</span><span class="sxs-emoji" aria-hidden="true">⚡</span></b></div>' +
        '<button type="button" class="sxs-continue" data-sxs-continue' + (packId ? ' data-pack-id="' + packId + '"' : ' disabled aria-disabled="true"') + '>' +
          escapeHtml(tr('store_continue')) + icon('arrow', 'sxs-arrow') + '</button>' +
        (note ? '<p class="sxs-summary-note">' + escapeHtml(note) + '</p>' : '') +
      '</div>';
    }

    function paint() {
      container.classList.add('sxs-root', 'sxs-credits');
      container.innerHTML =
        '<div class="sxs-grid" role="group">' + CREDIT_PACK_USD.map(packCard).join('') + '</div>' +
        customCard() + summary() + examplesNote(tr);
    }

    // Typing in the custom amount updates credits, examples and summary in
    // place so the input keeps focus and caret.
    function updateCustom() {
      var parsed = parseCustomAmount(state.customRaw);
      var credits = parsed.ok ? parsed.credits : 0;
      var body = container.querySelector('.sxs-custom-body');
      var field = container.querySelector('.sxs-amount-field');
      var input = container.querySelector('[data-sxs-custom-input]');
      var error = !state.customRaw ? '' : (parsed.ok ? '' : tr(parsed.error === 'cents' ? 'store_custom_cents' : 'store_custom_error', range));
      container.querySelector('#sxsCustomError').textContent = error;
      field.classList.toggle('is-invalid', !!error);
      input.setAttribute('aria-invalid', String(!!error));
      body.querySelector('[data-sxs-credits]').textContent = fmt.number(credits);
      body.querySelectorAll('.sxs-example').forEach(function (row, i) {
        var example = EXAMPLES[i];
        var count = exampleCount(credits, example.cost);
        row.querySelector('[data-sxs-example-value]').textContent = example.cost == null ? tr('store_by_tokens') : fmt.number(count);
      });
      var usd = parsed.ok ? parsed.usd : 0;
      var summaryEl = container.querySelector('.sxs-summary');
      summaryEl.querySelector('[data-sxs-summary-usd]').textContent = fmt.usd(usd, 2);
      summaryEl.querySelector('[data-sxs-summary-credits]').textContent = fmt.number(credits);
      summaryEl.dataset.checkoutTitle = fmt.number(credits) + ' ⚡';
      summaryEl.dataset.checkoutPrice = fmt.usd(usd, 2);
    }

    paint();
    container.__sxsCreditOptions = opts;
    container.__sxsCreditPaint = paint;
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
        if (!cont.disabled && cont.dataset.packId && typeof container.__sxsCreditOptions.onContinue === 'function') {
          container.__sxsCreditOptions.onContinue(cont.dataset.packId, cont);
        }
        return;
      }
      var card = event.target.closest('[data-pack-usd]');
      if (card) {
        state.usd = Number(card.dataset.packUsd);
        state.customOpen = false;
        container.__sxsCreditPaint();
        var pick = container.querySelector('[data-sxs-pick="' + state.usd + '"]');
        if (pick) pick.focus();
      }
    });
    container.addEventListener('input', function (event) {
      if (!event.target.matches('[data-sxs-custom-input]')) return;
      state.customRaw = event.target.value;
      updateCustom();
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
