// Run with: node --test tests/test_store_lanyard.mjs
//
// Browser Mini App Store: the selected subscription plan shown as the React
// Bits Lanyard 3D card on the pay screen (webapp/js/store-lanyard.js), with
// the existing card payment under it. Covers: the component is the
// published one, unmodified; the card's data comes from the Store's plan
// list for every plan and period; the store settings for the component;
// and the integration stays isolated (browser plans only, previous pay
// screen kept, bundle loaded on demand).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');

const context = vm.createContext({Intl, WeakMap});
vm.runInContext(read('webapp/js/store-cards.js'), context);
vm.runInContext(read('webapp/js/store-lanyard.js'), context);
const cards = context.SylvexStoreCards;
const lanyard = context.SylvexStoreLanyard;

test('Lanyard.jsx and Lanyard.css are the published React Bits files, unmodified', () => {
  // `npx shadcn@latest add @react-bits/Lanyard-JS-CSS` (registry item
  // Lanyard-JS-CSS, three@^0.180.0).
  assert.equal(sha256('store_lanyard/src/Lanyard.jsx'), 'c5d3750b82111c400c8b1ae564fafee71f43012fbf86e2001aa4ff2d7912ed4c');
  assert.equal(sha256('store_lanyard/src/Lanyard.css'), '25678081ba329fe4f4c8730351e68b023e028a673eda5a4638199f79eec5b463');
  const pkg = JSON.parse(read('store_lanyard/package.json'));
  assert.equal(pkg.dependencies.three, '0.180.0');
});

test('the built bundle is committed and exposes the mount API', () => {
  const bundle = read('webapp/js/vendor/store-lanyard/store-lanyard.js');
  assert.ok(bundle.includes('SylvexLanyard'));
  assert.ok(bundle.includes('lanyard-canvas'), 'the component itself is inside');
  assert.match(read('webapp/js/vendor/store-lanyard/store-lanyard.css'), /\.lanyard\{position:relative;width:100%;height:100%;overflow:hidden\}/);
  assert.ok(read('.gitignore').includes('store_lanyard/node_modules/'));
});

test('the store uses the requested component settings', () => {
  assert.deepEqual({...lanyard.LANYARD_PROPS}, {
    imageFit: 'cover', cardColor: '#ffffff', orientation: 'portrait', finish: 'glossy', cornerRadius: 0.3,
    size: 0.6, anchor: 'center', strapLength: 0.5, strapColor: '#111111', strapWidth: 0.65, metal: 'silver',
    gravity: 1, damping: 0.5, elasticity: 0.5, breeze: 0.5, interactive: true, intro: true,
  });
  const source = read('webapp/js/store-lanyard.js');
  for (const prop of ['frontImage', 'backImage', 'strapImage']) assert.ok(source.includes(prop + ':'), prop);
  assert.ok(source.includes("LOGO_URL = BASE + 'assets/logo.bleck.png'"));
  assert.ok(existsSync(new URL('../webapp/assets/logo.bleck.png', import.meta.url)));
});

test('the Website copy, when checked out next to this repo, is identical', (t) => {
  const sibling = new URL('../../sylvex-website/js/store-lanyard.js', import.meta.url);
  if (!existsSync(sibling)) return t.skip('sylvex-website is not checked out alongside');
  assert.equal(readFileSync(sibling, 'utf8'), read('webapp/js/store-lanyard.js'));
});

test('bundle and logo resolve next to the script, in the Mini App and on the Website', () => {
  const source = read('webapp/js/store-lanyard.js');
  const base = (src) => {
    const ctx = vm.createContext({Intl, document: {currentScript: {src}}});
    vm.runInContext(source, ctx);
    return ctx.SylvexStoreLanyard.BASE;
  };
  assert.equal(base('https://api.sylvex.ai/webapp/js/store-lanyard.js?v=1'), 'https://api.sylvex.ai/webapp/');
  assert.equal(base('https://sylvex.ai/js/store-lanyard.js?v=1'), 'https://sylvex.ai/');
  assert.equal(lanyard.BASE, '', 'no script element: relative to the page');
});

test('every plan and period: the card shows the Store plan data, nothing typed in', () => {
  const fmt = new Intl.NumberFormat('en', {maximumFractionDigits: 0});
  for (const plan of cards.PLANS) {
    for (const period of ['month', 'year']) {
      const price = cards.planPricing(plan, period);
      const d = lanyard.planDetails(plan.id, period, {locale: 'en', renewal: 'auto'});
      assert.equal(d.name, plan.name);
      assert.equal(d.title, 'SYLVEX ' + plan.name);
      assert.equal(d.popular, !!plan.popular);
      assert.equal(d.amount, '$' + Number(price.displayUsd).toFixed(price.decimals));
      assert.equal(d.credits, fmt.format(price.credits));
      assert.equal(d.periodLabel, period === 'year' ? 'Annual' : 'Monthly');
      assert.equal(d.total, period === 'year' ? `$${price.totalUsd} / year` : `$${price.totalUsd} / mo`);
      assert.equal(d.examples.length, cards.EXAMPLES.length);
      d.examples.forEach((row, i) => {
        const example = cards.EXAMPLES[i];
        assert.equal(row.value, fmt.format(Math.floor(price.credits / example.cost)));
      });
      assert.match(d.terms, period === 'year' ? /every year/ : /every month/);
      if (period === 'year') assert.match(d.billing, new RegExp(`save ${price.discountPct}%`));
    }
  }
  assert.equal(lanyard.planDetails('business', 'month'), null, 'the sales block has no card');
  assert.equal(lanyard.planDetails('max', 'week'), null);
});

test('the card follows the app language and live example prices', () => {
  const ru = {store_period_month: 'Месяц', store_card_subscription: 'Подписка', store_per_month: '/ мес.'};
  const d = lanyard.planDetails('max', 'month', {locale: 'ru', t: (key) => ru[key] || key, renewal: 'auto',
    examples: {photo: {credits: 5, label: 'Live model'}}});
  assert.equal(d.periodLabel, 'Месяц');
  assert.equal(d.eyebrow, 'Подписка');
  assert.equal(d.unit, '/ мес.');
  assert.equal(d.examples[0].value, '200');
  assert.ok(d.examplesNote.includes('Live model'));
  const lang = read('webapp/js/language.js');
  for (const key of Object.keys(lanyard.EN).filter((k) => k.startsWith('store_card_'))) {
    assert.equal(lang.split(`${key}:`).length - 1, 2, key + ' has an English and a Russian text');
  }
});

test('pay screen: the card and the card-payment button, the previous screen kept', () => {
  const html = read('webapp/cabinet.html');
  const pay = html.slice(html.indexOf('<section class="view" data-view="pay">'), html.indexOf('<section class="view" data-view="profile">'));
  const stage = pay.indexOf('id="payLanyardStage"');
  const button = pay.indexOf('class="pay-lanyard-cta" data-browser-pay="card"');
  assert.ok(stage > 0 && button > stage, 'the button is right under the card');
  assert.ok(pay.includes('Перейти к оплате картой'));
  assert.ok(pay.includes(`onclick="SYLVEX.payWith('card')"`));
  for (const kept of ['class="pay-user"', 'class="pay-summary"', 'id="payStoreNote"', 'class="pay-methods"', 'data-browser-pay="card" type="button" onclick="SYLVEX.payWith(\'card\')" hidden']) {
    assert.ok(pay.includes(kept), kept);
  }
  const css = read('webapp/css/cabinet.css');
  assert.ok(css.includes('.view[data-view="pay"].is-lanyard .pay-summary'));
});

test('integration is isolated: browser subscription plans only, switchable off', () => {
  const js = read('webapp/js/cabinet.js');
  assert.ok(js.includes('const STORE_LANYARD_ENABLED = true;'));
  const sync = js.slice(js.indexOf('function syncStorePlanCard('), js.indexOf('function setBrowserPayMethods('));
  assert.match(sync, /viewName === 'pay' && STORE_LANYARD_ENABLED && isBrowserApp\(\) \? \/\^plan_\(\[a-z\]\+\)_\(month\|year\)\$\/\.exec\(productId\)/);
  assert.ok(sync.includes('.catch(() => setStorePlanCardShown(false))'), 'a card that cannot show falls back to the previous screen');
  assert.match(js, /S\.onViewSwitched = \(name\) => \{\n {4}syncStorePlanCard\(name\);\n {4}BrowserNav\.viewChanged\(name\);/);
  // Telegram purchases (Stars) never reach the card.
  const telegram = js.slice(js.indexOf('function openStoreProduct('), js.indexOf('async function payStoreProduct('));
  assert.ok(!telegram.includes('Lanyard') && !telegram.includes('PlanCard'));
  // The bundle is fetched on demand, never with the page.
  const index = read('webapp/index.html');
  assert.ok(index.includes('<script src="js/store-lanyard.js?v='));
  assert.ok(!index.includes('vendor/store-lanyard'));
  assert.ok(index.indexOf('js/store-cards.js') < index.indexOf('js/store-lanyard.js'));
});
