/* SYLVEX Store: the selected subscription as a 3D card on a lanyard.

   Shown before card payment in the browser Mini App (pay screen) and on
   the Website Store (checkout dialog). Keep this file byte-identical in
   sylvex-ai-webapp/webapp/js/store-lanyard.js and
   sylvex-website/js/store-lanyard.js, like js/store-cards.js. The card is
   the React Bits Lanyard component, built unchanged from
   sylvex-ai-webapp/store_lanyard/src into js/vendor/store-lanyard/ and
   loaded only when a plan is selected. This file draws what the card shows:

   - frontImage / backImage: painted here from the same plan data the Store
     cards and the pay screen use (SylvexStoreCards.PLANS + planPricing,
     the Store's example rows and its renewal terms). Nothing
     is typed in by hand per plan, and the server still re-derives the real
     price when checkout starts;
   - strapImage: the SYLVEX logo (assets/logo.bleck.png) on the black band.

   Nothing here pays, prices or grants anything: the button under the card
   is the host's existing card-payment button. If the bundle or WebGL is
   unavailable, show() rejects and the host keeps its previous screen. */
(function (root) {
  'use strict';

  // Paths are relative to the folder holding js/store-lanyard.js, so the
  // same file works in the Mini App (/webapp/) and on the Website (/).
  var VERSION = 'store-lanyard-20261018';
  var BASE = scriptBase();
  var BUNDLE_JS = BASE + 'js/vendor/store-lanyard/store-lanyard.js?v=' + VERSION;
  var BUNDLE_CSS = BASE + 'js/vendor/store-lanyard/store-lanyard.css?v=' + VERSION;
  var LOGO_URL = BASE + 'assets/logo.bleck.png';

  function scriptBase() {
    var script = typeof document !== 'undefined' ? document.currentScript : null;
    var match = script && script.src ? /^(.*\/)js\/store-lanyard\.js(?:[?#].*)?$/.exec(script.src) : null;
    return match ? match[1] : '';
  }
  var FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", system-ui, sans-serif';

  // Card faces match the component's portrait card (1.6 x 2.25) at the
  // resolution it paints its faces with (1024 px wide).
  var FACE_W = 1024;
  var FACE_H = 1440;
  var PAD = 96;
  var INK = '#0b0b0c';
  var MUTED = '#6b6d73';
  var LINE = '#e3e4e8';

  // The store's settings for the component (see the Store task); every
  // other behaviour is the component's own.
  var LANYARD_PROPS = {
    imageFit: 'cover',
    cardColor: '#ffffff',
    orientation: 'portrait',
    finish: 'glossy',
    cornerRadius: 0.3,
    size: 0.6,
    anchor: 'center',
    strapLength: 0.5,
    strapColor: '#111111',
    strapWidth: 0.65,
    metal: 'silver',
    gravity: 1,
    damping: 0.5,
    elasticity: 0.5,
    breeze: 0.5,
    interactive: true,
    intro: true,
  };

  // Card texts, plus the Store strings an older js/store-cards.js copy may
  // not have yet (its EN table is the fallback for the rest).
  var EN = {
    store_per_year: '/ year',
    store_card_subscription: 'Subscription',
    store_card_details: 'Plan details',
    store_card_period: 'Billing period',
    store_card_price: 'Price',
    store_card_saving: 'You save',
    store_card_credits: 'Credits',
    store_card_rate: 'Rate',
    store_card_flip: 'Tap the card to see all terms on the back',
    store_card_flip_back: 'Tap the card again to flip it back',
    store_card_renews_month: 'Renews automatically every month until you turn renewal off. ⚡ credits are added after each payment.',
    store_card_renews_year: 'Renews automatically every year until you turn renewal off. ⚡ credits are added after each payment.',
    store_card_one_month: 'One payment for one month, no auto-renewal. ⚡ credits are added right after payment.',
    store_card_one_year: 'One payment for 12 months, no auto-renewal. ⚡ credits are added right after payment.',
  };

  function makeT(t) {
    var cards = root.SylvexStoreCards || {};
    var fallback = Object.assign({}, cards.EN || {}, EN);
    return function (key, vars) {
      var value = typeof t === 'function' ? t(key) : '';
      if (!value || value === key) value = fallback[key] || key;
      Object.keys(vars || {}).forEach(function (name) {
        value = value.split('{' + name + '}').join(vars[name]);
      });
      return value;
    };
  }

  function makeFormat(locale) {
    var number = new Intl.NumberFormat(locale || 'en', { maximumFractionDigits: 0 });
    var decimal = new Intl.NumberFormat(locale || 'en', { maximumFractionDigits: 4 });
    return {
      number: function (n) { return number.format(n); },
      decimal: function (n) { return n == null ? '—' : decimal.format(n); },
      usd: function (n, decimals) {
        var parts = Number(n).toFixed(decimals || 0).split('.');
        return '$' + number.format(Number(parts[0])) + (parts[1] ? '.' + parts[1] : '');
      },
    };
  }

  // Store examples, with the server catalog's live rows when the host has
  // them (same rule as js/store-cards.js resolveExamples).
  function resolveExamples(server) {
    var cards = root.SylvexStoreCards || {};
    return (cards.EXAMPLES || []).map(function (example) {
      var live = server && server[example.key];
      if (!live || !(Number(live.credits) > 0)) return example;
      return Object.assign({}, example, {
        cost: Number(live.credits),
        model: live.model || example.model,
        label: live.label || example.label,
        seconds: live.seconds || example.seconds,
        resolution: live.resolution || example.resolution,
        inputCredits: live.input_credits != null ? Number(live.input_credits) : example.inputCredits,
        outputCredits: live.output_credits != null ? Number(live.output_credits) : example.outputCredits,
      });
    });
  }

  // Everything the card says about one plan and billing period, derived
  // from the Store's plan list. Returns null for an unknown plan.
  function planDetails(planId, period, options) {
    var cards = root.SylvexStoreCards;
    var opts = options || {};
    if (!cards || !cards.PLANS || typeof cards.planPricing !== 'function') return null;
    var plan = cards.PLANS.filter(function (p) { return p.id === planId; })[0];
    if (!plan || (period !== 'month' && period !== 'year')) return null;
    var tr = makeT(opts.t);
    var fmt = makeFormat(opts.locale);
    var price = cards.planPricing(plan, period);
    var autoRenew = opts.renewal === 'auto';
    var billing = period === 'year'
      ? tr(autoRenew ? 'store_billed_annually_auto' : 'store_billed_annually', { total: fmt.usd(price.totalUsd, 0), pct: price.discountPct })
      : tr(autoRenew ? 'store_billed_monthly_auto' : 'store_billed_monthly');
    var examples = resolveExamples(opts.examples).map(function (example) {
      var count = example.cost == null ? null : cards.exampleCount(price.credits, example.cost);
      return {
        key: example.key,
        label: tr('store_example_' + example.key, { seconds: example.seconds || 30 }),
        value: example.cost == null ? tr('store_by_tokens') : (count == null ? '—' : fmt.number(count)),
        note: tr('store_note_' + example.key, {
          model: example.label || example.model,
          credits: fmt.decimal(example.cost),
          seconds: example.seconds || '',
          resolution: example.resolution || '',
          input: fmt.decimal(example.inputCredits),
          output: fmt.decimal(example.outputCredits),
        }).replace(/\s+,/g, ','),
      };
    });
    var notes = {};
    examples.forEach(function (row) { notes[row.key] = row.note; });
    return {
      planId: plan.id,
      period: period,
      name: plan.name,
      title: 'SYLVEX ' + plan.name,
      popular: !!plan.popular,
      popularLabel: tr('store_popular'),
      eyebrow: tr('store_card_subscription'),
      periodLabel: tr('store_period_' + period),
      amount: fmt.usd(price.displayUsd, price.decimals),
      unit: tr('store_per_month'),
      total: period === 'year' ? fmt.usd(price.totalUsd, 0) + ' ' + tr('store_per_year') : fmt.usd(price.totalUsd, 0) + ' ' + tr('store_per_month'),
      discountPct: price.discountPct,
      billing: billing,
      credits: fmt.number(price.credits),
      creditNote: tr(period === 'year' ? 'store_credits_annual' : 'store_credits_monthly'),
      rate: '1 ⚡ = $0.01',
      examplesTitle: tr('store_examples_title'),
      examples: examples,
      examplesNote: tr('store_examples_note', notes),
      terms: tr(autoRenew ? 'store_card_renews_' + period : (period === 'year' ? 'store_card_one_year' : 'store_card_one_month')),
      labels: {
        details: tr('store_card_details'),
        period: tr('store_card_period'),
        price: tr('store_card_price'),
        saving: tr('store_card_saving'),
        credits: tr('store_card_credits'),
        rate: tr('store_card_rate'),
        flip: tr('store_card_flip'),
        flipBack: tr('store_card_flip_back'),
      },
    };
  }

  /* ---------------- painting ---------------- */

  function font(size, weight) {
    return (weight || 400) + ' ' + size + 'px ' + FONT;
  }

  function newCanvas(width, height) {
    var canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function setSpacing(ctx, px) {
    if ('letterSpacing' in ctx) ctx.letterSpacing = px + 'px';
  }

  // Splits `text` into lines no wider than `width` with the current font.
  function wrap(ctx, text, width) {
    var lines = [];
    String(text || '').split('\n').forEach(function (paragraph) {
      var line = '';
      paragraph.split(/\s+/).filter(Boolean).forEach(function (word) {
        var next = line ? line + ' ' + word : word;
        if (line && ctx.measureText(next).width > width) {
          lines.push(line);
          line = word;
        } else {
          line = next;
        }
      });
      if (line) lines.push(line);
    });
    return lines;
  }

  function drawLines(ctx, lines, x, y, lineHeight) {
    lines.forEach(function (line, i) { ctx.fillText(line, x, y + i * lineHeight); });
    return y + lines.length * lineHeight;
  }

  function drawLogo(ctx, logo, x, y, size) {
    // logo.bleck.png: the mark sits in its central 2/3 on transparency.
    if (logo) ctx.drawImage(logo, x - size * 0.2, y - size * 0.2, size * 1.4, size * 1.4);
  }

  function rule(ctx, y) {
    ctx.fillStyle = LINE;
    ctx.fillRect(PAD, y, FACE_W - PAD * 2, 2);
  }

  function row(ctx, label, value, y, size, strong) {
    ctx.textAlign = 'left';
    ctx.fillStyle = MUTED;
    ctx.font = font(size, 500);
    ctx.fillText(label, PAD, y);
    ctx.textAlign = 'right';
    ctx.fillStyle = INK;
    ctx.font = font(size, strong ? 700 : 600);
    ctx.fillText(value, FACE_W - PAD, y);
    ctx.textAlign = 'left';
  }

  // The top of the card holds the lanyard slot: content starts below it.
  function header(ctx, logo, right) {
    var y = 196;
    drawLogo(ctx, logo, PAD, y - 62, 84);
    ctx.fillStyle = INK;
    ctx.font = font(40, 800);
    ctx.textBaseline = 'alphabetic';
    setSpacing(ctx, 10);
    ctx.fillText('SYLVEX', PAD + 108, y);
    ctx.font = font(24, 700);
    setSpacing(ctx, 5);
    ctx.fillStyle = MUTED;
    ctx.textAlign = 'right';
    ctx.fillText(String(right || '').toUpperCase(), FACE_W - PAD, y - 4);
    ctx.textAlign = 'left';
    setSpacing(ctx, 0);
    return y;
  }

  function paintFront(details, logo) {
    var canvas = newCanvas(FACE_W, FACE_H);
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, FACE_W, FACE_H);
    header(ctx, logo, details.eyebrow + ' · ' + details.periodLabel);

    ctx.fillStyle = INK;
    ctx.font = font(176, 800);
    setSpacing(ctx, -4);
    ctx.fillText(details.name, PAD - 6, 440);
    setSpacing(ctx, 0);
    if (details.popular) {
      var nameWidth = ctx.measureText(details.name).width;
      ctx.font = font(26, 700);
      var label = details.popularLabel;
      var pillW = ctx.measureText(label).width + 44;
      var pillX = Math.min(PAD + nameWidth + 28, FACE_W - PAD - pillW);
      ctx.fillStyle = INK;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(pillX, 330, pillW, 52, 26); else ctx.rect(pillX, 330, pillW, 52);
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, pillX + 22, 366);
    }

    ctx.fillStyle = INK;
    ctx.font = font(128, 800);
    setSpacing(ctx, -3);
    ctx.fillText(details.amount, PAD - 4, 640);
    var amountWidth = ctx.measureText(details.amount).width;
    setSpacing(ctx, 0);
    ctx.fillStyle = MUTED;
    ctx.font = font(46, 600);
    ctx.fillText(details.unit, PAD + amountWidth + 18, 640);

    ctx.font = font(32, 500);
    var y = drawLines(ctx, wrap(ctx, details.billing, FACE_W - PAD * 2), PAD, 712, 44);

    y = Math.max(y + 22, 800);
    rule(ctx, y);
    y += 112;
    ctx.fillStyle = INK;
    ctx.font = font(96, 800);
    setSpacing(ctx, -2);
    ctx.fillText(details.credits + ' ⚡', PAD - 4, y);
    setSpacing(ctx, 0);
    ctx.fillStyle = MUTED;
    ctx.font = font(32, 500);
    ctx.fillText(details.creditNote, PAD, y + 56);

    y += 140;
    ctx.font = font(24, 700);
    setSpacing(ctx, 4);
    ctx.fillText(details.examplesTitle.toUpperCase(), PAD, y);
    setSpacing(ctx, 0);
    details.examples.slice(0, 3).forEach(function (example, i) {
      var rowY = y + 66 + i * 64;
      row(ctx, example.label, example.value, rowY, 34, true);
      if (i < 2) rule(ctx, rowY + 24);
    });

    ctx.fillStyle = MUTED;
    ctx.font = font(26, 500);
    ctx.textAlign = 'center';
    ctx.fillText(details.labels.flip, FACE_W / 2, FACE_H - 84);
    ctx.textAlign = 'left';
    return canvas;
  }

  function paintBack(details, logo) {
    var canvas = newCanvas(FACE_W, FACE_H);
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, FACE_W, FACE_H);
    header(ctx, logo, details.labels.details);

    ctx.fillStyle = INK;
    ctx.font = font(64, 800);
    setSpacing(ctx, -1);
    ctx.fillText(details.title, PAD, 300);
    setSpacing(ctx, 0);

    var y = 372;
    var rows = [
      [details.labels.period, details.periodLabel],
      [details.labels.price, details.total],
    ];
    if (details.period === 'year') rows.push([details.labels.saving, details.discountPct + '%']);
    rows.push([details.labels.credits, details.credits + ' ⚡']);
    rows.push([details.labels.rate, details.rate]);
    rows.forEach(function (pair, i) {
      row(ctx, pair[0], pair[1], y, 30, i === 1);
      rule(ctx, y + 22);
      y += 58;
    });

    ctx.fillStyle = MUTED;
    ctx.font = font(26, 500);
    y = drawLines(ctx, wrap(ctx, details.billing + '. ' + details.creditNote + '.', FACE_W - PAD * 2), PAD, y + 8, 36);
    if (details.terms) {
      ctx.fillStyle = INK;
      y = drawLines(ctx, wrap(ctx, details.terms, FACE_W - PAD * 2), PAD, y + 6, 36);
    }

    y += 54;
    ctx.fillStyle = MUTED;
    ctx.font = font(24, 700);
    setSpacing(ctx, 4);
    ctx.fillText(details.examplesTitle.toUpperCase(), PAD, y);
    setSpacing(ctx, 0);
    y += 52;
    details.examples.forEach(function (example) {
      row(ctx, example.label, example.value, y, 30, true);
      rule(ctx, y + 20);
      y += 52;
    });

    // The note on how the examples are counted fills what is left above
    // the footer; long translations get a smaller size instead of
    // running off the card.
    var bottom = FACE_H - 132;
    var size = 22;
    var lines;
    for (; size >= 15; size -= 1) {
      ctx.font = font(size, 500);
      lines = wrap(ctx, details.examplesNote, FACE_W - PAD * 2);
      if (y + 14 + lines.length * size * 1.36 <= bottom) break;
    }
    ctx.fillStyle = MUTED;
    drawLines(ctx, lines, PAD, y + 14 + size, Math.round(size * 1.36));

    ctx.font = font(26, 500);
    ctx.textAlign = 'center';
    ctx.fillText(details.labels.flipBack, FACE_W / 2, FACE_H - 84);
    ctx.textAlign = 'left';
    return canvas;
  }

  // The band texture: the component lays the image along the strap, so it
  // is a long horizontal tile with the white SYLVEX mark and wordmark.
  function paintStrap(logo) {
    var w = 1280;
    var h = 192;
    var canvas = newCanvas(w, h);
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#111111';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    for (var x = 0; x < w; x += 4) ctx.fillRect(x, 0, 1, h);
    ctx.fillStyle = 'rgba(255,255,255,0.2)';
    for (var s = 0; s < w; s += 14) {
      ctx.fillRect(s, h * 0.075, 8, 2);
      ctx.fillRect(s, h * 0.925 - 2, 8, 2);
    }
    var mark = null;
    if (logo) {
      mark = newCanvas(logo.width, logo.height);
      var m = mark.getContext('2d');
      m.drawImage(logo, 0, 0);
      m.globalCompositeOperation = 'source-in';
      m.fillStyle = '#ffffff';
      m.fillRect(0, 0, mark.width, mark.height);
    }
    ctx.textBaseline = 'middle';
    ctx.font = font(64, 800);
    setSpacing(ctx, 16);
    ctx.fillStyle = '#ffffff';
    [0, w / 2].forEach(function (left) {
      var text = 'SYLVEX';
      var textWidth = ctx.measureText(text).width;
      var markSize = 104;
      var start = left + (w / 2 - (markSize + 28 + textWidth)) / 2;
      if (mark) ctx.drawImage(mark, start - markSize * 0.2, h / 2 - markSize * 0.7, markSize * 1.4, markSize * 1.4);
      ctx.fillText(text, start + markSize + 28, h / 2 + 4);
    });
    setSpacing(ctx, 0);
    return canvas;
  }

  /* ---------------- loading ---------------- */

  var bundle = null;
  var logoPromise = null;

  function webgl2Available() {
    try {
      var canvas = document.createElement('canvas');
      return !!(root.WebGL2RenderingContext && canvas.getContext('webgl2'));
    } catch (e) {
      return false;
    }
  }

  function loadBundle() {
    if (root.SylvexLanyard) return Promise.resolve(root.SylvexLanyard);
    if (bundle) return bundle;
    bundle = new Promise(function (resolve, reject) {
      if (!document.querySelector('link[data-store-lanyard]')) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = BUNDLE_CSS;
        link.setAttribute('data-store-lanyard', '');
        document.head.appendChild(link);
      }
      var script = document.createElement('script');
      script.src = BUNDLE_JS;
      script.async = true;
      script.onload = function () {
        if (root.SylvexLanyard) resolve(root.SylvexLanyard);
        else reject(new Error('lanyard_bundle_empty'));
      };
      script.onerror = function () { reject(new Error('lanyard_bundle_failed')); };
      document.head.appendChild(script);
    }).catch(function (error) {
      bundle = null;
      throw error;
    });
    return bundle;
  }

  function loadLogo() {
    if (logoPromise) return logoPromise;
    logoPromise = new Promise(function (resolve) {
      var image = new Image();
      image.decoding = 'async';
      image.onload = function () { resolve(image); };
      image.onerror = function () { logoPromise = null; resolve(null); };
      image.src = LOGO_URL;
    });
    return logoPromise;
  }

  function fontsReady() {
    try {
      return document.fonts && document.fonts.ready ? document.fonts.ready.catch(function () {}) : Promise.resolve();
    } catch (e) {
      return Promise.resolve();
    }
  }

  /* ---------------- mount ---------------- */

  var current = null; // { host, instance, key }
  var token = 0;

  // Mounts the card for `planId`/`period` into `host` (an empty element
  // sized by the page). Each call starts the component fresh, so its
  // intro plays every time the pay screen opens. Rejects - leaving `host`
  // empty - when the card cannot be shown.
  function show(host, planId, period, options) {
    var mine = ++token;
    hide();
    var details = planDetails(planId, period, options);
    if (!host || !details) return Promise.reject(new Error('unknown_plan'));
    if (!webgl2Available()) return Promise.reject(new Error('webgl_unavailable'));
    return Promise.all([loadBundle(), loadLogo(), fontsReady()]).then(function (loaded) {
      if (mine !== token) return null;
      var api = loaded[0];
      var logo = loaded[1];
      var props = Object.assign({}, LANYARD_PROPS, {
        frontImage: paintFront(details, logo).toDataURL('image/png'),
        backImage: paintBack(details, logo).toDataURL('image/png'),
        strapImage: paintStrap(logo).toDataURL('image/png'),
      });
      host.setAttribute('role', 'img');
      host.setAttribute('aria-label', details.title + ' · ' + details.amount + ' ' + details.unit + ' · ' + details.credits + ' ⚡');
      current = { host: host, instance: api.mount(host, props), key: planId + '_' + period };
      return details;
    });
  }

  function hide() {
    if (!current) return;
    var done = current;
    current = null;
    try { done.instance.unmount(); } catch (e) { /* already gone */ }
    done.host.removeAttribute('aria-label');
  }

  function cancel() {
    token += 1;
    hide();
  }

  root.SylvexStoreLanyard = {
    BASE: BASE,
    LANYARD_PROPS: LANYARD_PROPS,
    EN: EN,
    planDetails: planDetails,
    paintFront: paintFront,
    paintBack: paintBack,
    paintStrap: paintStrap,
    show: show,
    hide: cancel,
    isShowing: function (key) { return !!current && (!key || current.key === key); },
  };
})(typeof window !== 'undefined' ? window : globalThis);
