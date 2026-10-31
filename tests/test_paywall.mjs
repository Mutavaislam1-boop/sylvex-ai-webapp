// The paywall window (js/paywall.js, the same file as the website's): a
// generation refused for lack of a subscription or credits opens it; every
// other refusal is left to the app's own error message.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../webapp/' + path, import.meta.url), 'utf8');
const source = read('js/paywall.js');

function load(responder) {
  const shown = [];
  const context = {
    Date, Promise, JSON, Number, String, isFinite,
    fetch: (input, init) => Promise.resolve(responder(input, init)),
  };
  context.window = context;
  context.top = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  context.SylvexPaywall.show = (kind, info) => shown.push([kind, info.required, info.balance]);
  return { context, shown };
}
const response = (status, body) => ({ status, clone: () => ({ json: () => Promise.resolve(body) }) });
const settle = () => new Promise((resolve) => setTimeout(resolve, 5));

test('which refusal opens which window', () => {
  const { context } = load(() => response(200, {}));
  const c = (status, body) => { const hit = context.SylvexPaywall.classify(status, body); return hit && [hit.kind, hit.required, hit.balance]; };
  // No subscription and nothing on the balance: the plans.
  assert.deepEqual(c(403, { subscription_required: true, error: 'prostudio_subscription_required', balance: 0 }), ['start', 0, 0]);
  // No subscription but credits left: the plans, as a subscription question.
  assert.deepEqual(c(403, { subscription_required: true, balance: 120 }), ['subscription', 0, 120]);
  assert.deepEqual(c(403, { ok: false, error: 'subscription_required' }), ['start', 0, 0]);
  // A subscription, not enough credits for this generation: top up.
  assert.deepEqual(c(402, { paywall: true, insufficient_balance: true, required_credits: 30, balance: 5 }), ['balance', 30, 5]);
  // Anything else is not a reason to sell a plan.
  assert.equal(c(403, { error: 'origin_not_allowed' }), null);
  assert.equal(c(403, { error: 'account_blocked' }), null);
  assert.equal(c(402, { error: 'pricing_not_configured' }), null);
  assert.equal(c(409, { error: 'model_disabled' }), null);
  assert.equal(c(403, null), null);
});

test("the app's own requests open it, wherever the generation was started", async () => {
  const replies = {
    '/api/public/prostudio/generate': response(403, { subscription_required: true, balance: 0 }),
    '/api/public/media-blocks/7/generate': response(402, { paywall: true, insufficient_balance: true, required_credits: 30, balance: 4 }),
    '/api/public/grid/generate': response(403, { error: 'origin_not_allowed' }),
  };
  const { context, shown } = load((input) => replies[new URL(String(input), 'https://api.sylvex.ai').pathname] || response(200, {}));
  await context.fetch('https://api.sylvex.ai/api/public/prostudio/generate', { method: 'POST', body: '{}' });
  await context.fetch('/api/public/media-blocks/7/generate', { method: 'POST' });
  await context.fetch('/api/public/grid/generate', { method: 'POST' });
  // A read is never a generation.
  await context.fetch('/api/public/prostudio/generate');
  await settle();
  assert.deepEqual(shown, [['start', 0, 0], ['balance', 30, 4]]);
});

test('the response still reaches the app unchanged', async () => {
  const reply = response(403, { subscription_required: true });
  const { context } = load(() => reply);
  assert.equal(await context.fetch('/api/public/prostudio/generate', { method: 'POST' }), reply);
});

test('the window offers the Store plans; a plan or a package goes straight to its checkout', () => {
  assert.match(source, /var OFFERED = \['starter', 'pro', 'max'\];/);
  assert.match(source, /root\.SylvexStoreCards/);
  assert.match(source, /'Начните создавать с SYLVEX'/);
  assert.match(source, /'Выберите подходящий план и получите кредиты для генерации изображений, видео и другого ИИ-контента\.'/);
  // "Top up" shows the packages right in the window.
  assert.match(source, /current = \{ kind: 'packs', balance: current \? current\.balance : 0, required: 0 \};/);
  assert.match(source, /if \(plan\) \{ buy\(host\.onPlan, plan\.getAttribute\('data-sxpw-plan'\), plan\); return; \}/);
  assert.match(source, /if \(pack\) \{ buy\(host\.onPack, pack\.getAttribute\('data-sxpw-pack'\), pack\); return; \}/);
  const index = read('index.html');
  assert.match(index, /<link rel="stylesheet" href="css\/paywall\.css\?v=handoff-20261031" \/>/);
  assert.match(index, /<script src="js\/paywall\.js\?v=handoff-20261031"><\/script>/);
  const cabinet = read('js/cabinet.js');
  assert.match(cabinet, /initGenerationPaywall\(\);/);
  // Telegram sells in Stars, the browser by card - straight to the product's own checkout.
  assert.match(cabinet, /onPlan: \(planId\) => paywallProduct\('plan_' \+ planId \+ '_month'\),/);
  assert.match(cabinet, /onPack: \(packId\) => paywallProduct\(packId\),/);
  assert.match(cabinet, /if \(!browserStripeEnabled\) throw new Error\(BROWSER_STRIPE_ERRORS\.stripe_not_configured\);\n\s+openBrowserStoreProduct\(productId\);/);
  assert.match(cabinet, /if \(!storeProductAvailable\(productId\)\) throw new Error\(STORE_ERRORS\.unknown_product\);\n\s+openStoreProduct\(productId\);/);
  // A confirmed payment brings the person back.
  assert.match(cabinet, /window\.SylvexPaywall\?\.completeReturn\(\);/);
});

function withStorage() {
  const store = new Map();
  const shown = [];
  const context = {
    Date, Promise, JSON, Number, String, isFinite, location: { pathname: '/pro-studio.html', search: '?mode=image' },
    localStorage: { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    fetch: () => Promise.resolve(response(200, {})),
  };
  context.window = context;
  context.top = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  return { context, store, shown, P: context.SylvexPaywall };
}

test('a purchase remembers where it started and brings it back once - nothing is resubmitted', () => {
  const { P } = withStorage();
  const restored = [];
  P.addCapture(() => ({ view: 'home', home: { ref: { id: 'r1' }, photo: { url: 'https://x/me.png' }, prompt: 'neon' } }));
  P.onReturn((data) => restored.push(data));
  const entry = P.remember();
  assert.equal(entry.path, '/pro-studio.html?mode=image');
  assert.equal(P.peekReturn().data.home.prompt, 'neon');
  // A payment on the same page (Mini App): delivered once, then gone.
  assert.equal(P.completeReturn().data.view, 'home');
  assert.equal(P.completeReturn(), null);
  assert.deepEqual(restored.map((d) => d.home.photo.url), ['https://x/me.png']);
});

test('a payment confirmed on another page (the Store) lands back on its own page only', () => {
  const { context, P } = withStorage();
  const restored = [];
  P.onReturn((data) => restored.push(data));
  P.addCapture(() => ({ mode: 'video' }));
  P.remember();
  // Not paid yet: nothing lands.
  assert.equal(P.landReturn(), null);
  assert.equal(P.markPaid().paid, true);
  context.location.search = '?mode=grid';
  assert.equal(P.landReturn(), null, 'another page does not take it');
  context.location.search = '?mode=image';
  assert.equal(P.landReturn().data.mode, 'video');
  assert.equal(P.peekReturn(), null);
  assert.equal(restored.length, 1);
});

test('an old return point expires', () => {
  const { store, P } = withStorage();
  store.set('sylvex-purchase-return-v1', JSON.stringify({ at: Date.now() - 4 * 60 * 60 * 1000, path: '/', data: {} }));
  assert.equal(P.peekReturn(), null);
});

test('one file for the website and the Mini Apps', () => {
  let site;
  try { site = (p) => readFileSync(new URL('../../sylvex-website/' + p, import.meta.url), 'utf8'); site('js/paywall.js'); } catch { return; }
  assert.equal(source, site('js/paywall.js'));
  assert.equal(read('css/paywall.css'), site('css/paywall.css'));
});
