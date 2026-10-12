// Run with: node --test tests/test_store_cards.mjs
//
// Store cards (js/store-cards.js), shared by the Telegram Mini App
// (sylvex-ai-webapp/webapp) and the Website (sylvex-website). This file is
// kept identical in both repositories and loads whichever copy exists.
//
// Covers the plan/credit math shown on the cards, custom-amount
// validation, which credit cards may continue to the existing checkout
// (only the packs SHOP_ITEMS already sells, unless the host says
// otherwise), and that without host purchase options the new plans,
// $100/$200 and custom amounts are rendered as not purchasable.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const candidates = ['../webapp/js/store-cards.js', '../js/store-cards.js'].map((p) => new URL(p, import.meta.url));
const source = readFileSync(candidates.find((url) => existsSync(url)), 'utf8');
const context = vm.createContext({Intl, WeakMap});
vm.runInContext(source, context);
const S = context.SylvexStoreCards;

function fakeContainer() {
  return {innerHTML: '', classList: {add() {}}, addEventListener() {}};
}

test('plans match the approved pricing table', () => {
  const table = {
    starter: [5, 48, 100, 1200], pro: [10, 96, 300, 3600], max: [25, 240, 1000, 12000],
    ultra: [50, 480, 2500, 30000], creator: [100, 960, 5500, 66000],
  };
  assert.deepEqual(Array.from(S.PLANS, (p) => p.id), Object.keys(table));
  for (const plan of S.PLANS) {
    const [monthly, annual, monthCredits, yearCredits] = table[plan.id];
    const month = S.planPricing(plan, 'month');
    const year = S.planPricing(plan, 'year');
    assert.equal(month.displayUsd, monthly);
    assert.equal(month.credits, monthCredits);
    assert.equal(year.totalUsd, annual);
    assert.equal(year.displayUsd, annual / 12);
    assert.equal(year.discountPct, 20);
    assert.equal(year.credits, yearCredits);
  }
  assert.deepEqual(Array.from(S.PLANS.filter((p) => p.popular), (p) => p.id), ['max']);
});

test('credit packages: $1 = 100 credits, only existing packs continue to checkout', () => {
  assert.deepEqual(Array.from(S.CREDIT_PACK_USD), [5, 10, 20, 30, 40, 50, 100, 200]);
  assert.equal(S.creditsForUsd(5), 500);
  assert.equal(S.creditsForUsd(12.34), 1234);
  assert.deepEqual(Array.from(S.CREDIT_PACK_USD, (usd) => S.packIdForUsd(usd)),
    ['pack_500', 'pack_1000', 'pack_2000', 'pack_3000', 'pack_4000', 'pack_5000', null, null]);
});

test('custom amount validation', () => {
  assert.equal(S.parseCustomAmount('').error, 'empty');
  assert.equal(S.parseCustomAmount('0.99').error, 'range');
  assert.equal(S.parseCustomAmount('1000.01').error, 'range');
  assert.equal(S.parseCustomAmount('abc').error, 'range');
  assert.equal(S.parseCustomAmount('-5').error, 'range');
  assert.equal(S.parseCustomAmount('12.345').error, 'cents');
  assert.deepEqual({...S.parseCustomAmount('1')}, {ok: true, usd: 1, credits: 100});
  assert.deepEqual({...S.parseCustomAmount('1000')}, {ok: true, usd: 1000, credits: 100000});
  assert.deepEqual({...S.parseCustomAmount(' 12,5 ')}, {ok: true, usd: 12.5, credits: 1250});
});

test('examples are counts of one example each, with live server costs overriding defaults', () => {
  assert.deepEqual(Array.from(S.EXAMPLES, (e) => e.key), ['photo', 'video', 'music', 'voice', 'text']);
  assert.deepEqual(Array.from(S.EXAMPLES, (e) => S.exampleCount(1000, e.cost)), [333, 111, 166, 1000, 1000]);
  assert.equal(S.exampleCount(0, 6), 0);
  const container = fakeContainer();
  S.renderCredits(container, {locale: 'en', defaultUsd: 10, examples: {
    photo: {credits: 4, model: 'm', label: 'Cheap Image'},
    text: {credits: 2, model: 't', label: 'Tiny LLM', input_credits: 0.01, output_credits: 0.04},
  }});
  const html = container.innerHTML;
  assert.match(html, /data-example="photo">[\s\S]*?data-sxs-example-value>250</);
  assert.match(html, /data-example="text">[\s\S]*?data-sxs-example-value>500</);
  assert.match(html, /Cheap Image, 4 ⚡ per image/);
  assert.match(html, /Tiny LLM, 0\.01 ⚡ for 1,000 input \+ 0\.04 ⚡ for 1,000 output tokens, minimum 2 ⚡ per request/);
  assert.match(html, /Text · 1K in \+ 1K out/);
  assert.doesNotMatch(html, /By tokens/);
});

test('copy promises automatic renewal only when the host says plans renew', () => {
  const container = fakeContainer();
  S.renderPlans(container, {locale: 'en'});
  assert.match(container.innerHTML, /One month · no auto-renewal/);
  assert.equal(S.EN.store_billed_annually, '{total} for 12 months · save {pct}%');
  assert.doesNotMatch(container.innerHTML, /[Bb]illed monthly|auto-renews|cancel anytime/);

  const auto = fakeContainer();
  S.renderPlans(auto, {locale: 'en', renewal: 'auto'});
  assert.match(auto.innerHTML, /Billed monthly · cancel anytime/);
  assert.doesNotMatch(auto.innerHTML, /no auto-renewal/);
});

test('the host decides purchasability: all packs and custom amounts when enabled', () => {
  const container = fakeContainer();
  S.renderCredits(container, {locale: 'en', defaultUsd: 200, packIdForUsd: (usd) => 'pack_' + usd * 100, customPurchase: true});
  assert.match(container.innerHTML, /data-sxs-continue data-pack-id="pack_20000"/);
  assert.doesNotMatch(container.innerHTML, /sxs-summary-note/);
});

// A container that records listeners and hands out stub elements, enough to
// drive the bound click/input handlers without a DOM.
function interactiveContainer() {
  const listeners = {};
  const button = {disabled: true, attrs: {}, dataset: {}, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; }};
  const stub = () => ({textContent: '', dataset: {}, classList: {toggle() {}}, setAttribute() {}, removeAttribute() {}, focus() {},
    querySelector: (sel) => (sel === '[data-sxs-continue]' ? button : stub()), querySelectorAll: () => []});
  return {
    innerHTML: '', classList: {add() {}}, button,
    addEventListener(type, fn) { listeners[type] = fn; },
    querySelector: (sel) => (sel === '.sxs-summary' ? {dataset: {}, querySelector: (s) => (s === '[data-sxs-continue]' ? button : stub())} : stub()),
    fire(type, target) { listeners[type]({target}); },
  };
}

test('custom amounts follow the latest render options after the host re-renders', () => {
  const container = interactiveContainer();
  // First render happens before the host catalog loads: custom not purchasable.
  S.renderCredits(container, {locale: 'en'});
  const bought = [];
  S.renderCredits(container, {locale: 'en', customPurchase: true, onContinueCustom: (usd) => bought.push(usd)});
  container.fire('click', {closest: (sel) => (sel === '[data-sxs-custom-toggle]' ? {} : null)});
  container.fire('input', {matches: () => true, value: '25'});
  assert.equal(container.button.disabled, false);
  assert.equal(container.button.attrs['data-custom-amount'], '25.00');
  container.fire('input', {matches: () => true, value: '1000.01'});
  assert.equal(container.button.disabled, true);
  assert.equal(container.button.attrs['data-custom-amount'], undefined);
  const cont = {disabled: false, dataset: {customAmount: '25.00'}};
  container.fire('click', {closest: (sel) => (sel === '[data-sxs-continue]' ? cont : null)});
  assert.deepEqual(bought, ['25.00']);
});

test('plan cards render all five plans plus Business, none purchasable yet', () => {
  const container = fakeContainer();
  let contacted = 0;
  S.renderPlans(container, {locale: 'en', onContactSales: () => { contacted += 1; }});
  const html = container.innerHTML;
  assert.equal((html.match(/class="sxs-card sxs-plan/g) || []).length, 6);
  assert.equal((html.match(/data-sxs-select-plan disabled/g) || []).length, 5);
  assert.match(html, /Coming soon/);
  assert.doesNotMatch(html, />Select plan</);
  assert.match(html, /For businesses and organizations/);
  assert.match(html, /data-sxs-contact-sales>Contact Sales/);
  assert.match(html, /class="sxs-card sxs-plan is-popular" data-plan="max"/);
  // Every card lists all five example rows.
  assert.equal((html.match(/class="sxs-example"/g) || []).length, 25);
});

test('plans become selectable only when the host reports them available', () => {
  const container = fakeContainer();
  S.renderPlans(container, {locale: 'en', isPlanAvailable: (id) => id === 'pro'});
  assert.equal((container.innerHTML.match(/data-sxs-select-plan>Select plan/g) || []).length, 1);
});

test('credit cards: selected legacy pack continues, $100/$200 do not', () => {
  const legacy = fakeContainer();
  S.renderCredits(legacy, {locale: 'en'});
  assert.equal((legacy.innerHTML.match(/class="sxs-card sxs-pack/g) || []).length, 8);
  assert.match(legacy.innerHTML, /class="sxs-card sxs-pack is-selected" data-pack-usd="10"/);
  assert.match(legacy.innerHTML, /data-sxs-continue data-pack-id="pack_1000"/);
  assert.doesNotMatch(legacy.innerHTML, /sxs-summary-note/);

  const large = fakeContainer();
  S.renderCredits(large, {locale: 'en', defaultUsd: 200});
  assert.match(large.innerHTML, /data-sxs-continue disabled aria-disabled="true"/);
  assert.doesNotMatch(large.innerHTML, /data-pack-id=/);
  assert.match(large.innerHTML, /isn’t available for purchase yet/);
  assert.match(large.innerHTML, /data-checkout-title="20,000 ⚡" data-checkout-price="\$200.00"/);
});

test('locale grouping with a point before cents, host strings with English fallback', () => {
  const container = fakeContainer();
  const ru = {store_custom_title: 'Своя сумма', store_custom_range: 'От {min} до {max}'};
  S.renderCredits(container, {locale: 'ru', t: (key) => ru[key] || key});
  const html = container.innerHTML.replace(/ /g, ' ');
  assert.match(html, /От \$1 до \$1 000/);
  assert.match(html, /Своя сумма/);
  assert.match(html, /\$10\.00/);
  assert.match(html, /What you can create/); // untranslated key falls back to English
});

test('host text is escaped', () => {
  const container = fakeContainer();
  S.renderPlans(container, {locale: 'en', t: (key) => (key === 'store_popular' ? '<img src=x onerror=alert(1)>' : key)});
  assert.doesNotMatch(container.innerHTML, /<img/);
  assert.match(container.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

// Telegram Mini App: Stars mode (starsPrice), as the host prices it.
const starsPrice = (cents) => Math.max(1, Math.ceil(cents * 499 / 500));

test('stars mode shows only Telegram Stars prices on plans', () => {
  const container = fakeContainer();
  S.renderPlans(container, {locale: 'en', starsPrice});
  const html = container.innerHTML;
  for (const [stars] of [['499'], ['998'], ['2,495'], ['4,990'], ['9,980']]) {
    assert.match(html, new RegExp(stars + ' ⭐</span><span class="sxs-price-unit">/ mo'));
  }
  assert.doesNotMatch(html, /\$\d/);
  assert.match(html, /One month · no auto-renewal/);
});

test('stars mode annual plans show the one-time yearly payment', () => {
  const container = fakeContainer();
  const plans = new Map();
  container.addEventListener = (type, fn) => plans.set(type, fn);
  container.querySelector = () => null;
  S.renderPlans(container, {locale: 'en', starsPrice});
  for (const [id, stars] of [['starter', '4,791'], ['pro', '9,581'], ['max', '23,952'], ['ultra', '47,904'], ['creator', '95,808']]) {
    const card = {dataset: {plan: id}};
    plans.get('click')({target: {closest: (sel) => (sel === '[data-sxs-period]' ? {dataset: {sxsPeriod: 'year'}} : sel === '[data-plan]' ? card : null)}});
    assert.match(container.innerHTML, new RegExp(stars + ' ⭐</span><span class="sxs-price-unit">/ year'));
  }
  assert.match(container.innerHTML, /One payment for 12 months · save 20% · no auto-renewal/);
  assert.doesNotMatch(container.innerHTML, /\$\d/);
});

test('stars mode credits: host packs, Stars prices and custom amounts in credits', () => {
  const container = interactiveContainer();
  const bought = [];
  S.renderCredits(container, {locale: 'en', starsPrice, packUsd: [1, 5, 10, 20, 30, 40, 50, 100, 200],
    packIdForUsd: (usd) => (usd === 200 ? null : 'pack_' + usd * 100), customPurchase: true,
    customCredits: {min: 100, max: 10020}, onContinueCustom: (amount) => bought.push(amount)});
  const html = container.innerHTML;
  assert.equal((html.match(/class="sxs-card sxs-pack/g) || []).length, 9);
  for (const stars of ['100', '499', '998', '1,996', '2,994', '3,992', '4,990', '9,980', '19,960']) {
    assert.match(html, new RegExp('<span class="sxs-pack-price">' + stars + ' ⭐</span>'));
  }
  assert.doesNotMatch(html, /\$\d/);
  assert.match(html, /From 100 to 10,020 ⚡/);
  container.fire('click', {closest: (sel) => (sel === '[data-sxs-custom-toggle]' ? {} : null)});
  for (const [raw, ok] of [['1234', true], ['10020', true], ['10021', false], ['99', false], ['12.5', false], ['', false]]) {
    container.fire('input', {matches: () => true, value: raw});
    assert.equal(container.button.disabled, !ok, raw);
    assert.equal(container.button.attrs['data-custom-amount'], ok ? raw : undefined, raw);
  }
  container.fire('input', {matches: () => true, value: '1234'});
  container.fire('click', {closest: (sel) => (sel === '[data-sxs-continue]' ? {disabled: false, dataset: {customAmount: '1234'}} : null)});
  assert.deepEqual(bought, ['1234']);
});
