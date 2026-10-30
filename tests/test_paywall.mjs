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

test('the window offers the Store plans and leads into the Store', () => {
  assert.match(source, /var OFFERED = \['starter', 'pro', 'max'\];/);
  assert.match(source, /root\.SylvexStoreCards/);
  assert.match(source, /'Начните создавать с SYLVEX'/);
  assert.match(source, /'Выберите подходящий план и получите кредиты для генерации изображений, видео и другого ИИ-контента\.'/);
  const index = read('index.html');
  assert.match(index, /<link rel="stylesheet" href="css\/paywall\.css\?v=paywall-20261030" \/>/);
  assert.match(index, /<script src="js\/paywall\.js\?v=paywall-20261030"><\/script>/);
  const cabinet = read('js/cabinet.js');
  assert.match(cabinet, /initGenerationPaywall\(\);/);
  // Telegram sells in Stars, the browser by card - the Store's own flows.
  assert.match(cabinet, /isBrowserApp\(\) \? '\$' \+ plan\.monthlyUsd : storeStarsFor\(plan\.monthlyUsd \* 100\)/);
  assert.match(cabinet, /else openStoreFor\(productId\);/);
  assert.match(cabinet, /onCredits: \(\) => \{ switchView\('shop'\); switchShopTab\('tokens'\); \}/);
});

test('one file for the website and the Mini Apps', () => {
  let site;
  try { site = (p) => readFileSync(new URL('../../sylvex-website/' + p, import.meta.url), 'utf8'); site('js/paywall.js'); } catch { return; }
  assert.equal(source, site('js/paywall.js'));
  assert.equal(read('css/paywall.css'), site('css/paywall.css'));
});
