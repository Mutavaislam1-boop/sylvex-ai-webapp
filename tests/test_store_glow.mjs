// Run with: node --test tests/test_store_glow.mjs
//
// Store: every subscription and purchase card (plans, Business, credit
// packages, custom amount) inside the React Bits BorderGlow (store_glow/ ->
// webapp/js/vendor/store-glow, applied by js/store-glow.js, shared
// byte-identical with sylvex-website/js/store-glow.js).
// Covers: the component is the published one, unmodified; the task's
// settings with the purple edge colour replaced by green; how the cards are
// wrapped; and where the Mini App turns it on.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');

test('BorderGlow.jsx / BorderGlow.css: the published files, unmodified', () => {
  // `npx shadcn@latest add @react-bits/BorderGlow-JS-CSS`
  assert.equal(sha256('store_glow/src/BorderGlow.jsx'), 'c3b1eec9099cf4c8ddd8ab9d910922b79c12ea1f243b60fa0666a2efa60caf73');
  assert.equal(sha256('store_glow/src/BorderGlow.css'), 'c6b645f1ff163046b55246a6a4f98b47d75868f4879ef445f0a83b5636acc6b4');
  const bundle = read('webapp/js/vendor/store-glow/store-glow.js');
  assert.ok(bundle.includes('SylvexStoreGlow') && bundle.includes('border-glow-card'));
  assert.ok(read('webapp/js/vendor/store-glow/store-glow.css').includes('.border-glow-card'));
  assert.ok(read('.gitignore').includes('store_glow/node_modules/'));
});

test('the task settings: purple edge colour and gold glow are SYLVEX green, no automatic sweep', () => {
  const main = read('store_glow/src/main.jsx');
  const start = main.indexOf('const GLOW_PROPS = {');
  const block = main.slice(start, main.indexOf('};', start) + 1);
  const settings = vm.runInNewContext('(' + block.replace('const GLOW_PROPS = ', '') + ')');
  assert.deepEqual(JSON.parse(JSON.stringify(settings)), {
    edgeSensitivity: 0, glowColor: '140 80 55', backgroundColor: '#120F17', borderRadius: 23, glowRadius: 80,
    glowIntensity: 1, coneSpread: 35, animated: false, colors: ['#10b945', '#f472b6', '#38bdf8'],
  });
  assert.ok(!block.includes('#c084fc') && !block.includes('40 80 80'), 'no purple or gold left');
  const bundle = read('webapp/js/vendor/store-glow/store-glow.js');
  assert.ok(bundle.includes('"#10b945"') && bundle.includes('glowColor:"140 80 55"') && bundle.includes('animated:!1'));
});

function loadHelper(src) {
  const window = {};
  const document = {currentScript: {src}};
  vm.runInNewContext(read('webapp/js/store-glow.js'), {window, document, globalThis: window});
  return window.SylvexStoreGlowCards;
}

test('surface: the task #120F17 on dark themes, the card colour on light ones; bundle next to the script', () => {
  const glow = loadHelper('https://app.example/webapp/js/store-glow.js?v=1');
  assert.equal(glow.BASE, 'https://app.example/webapp/');
  assert.equal(loadHelper('https://sylvexai.com/js/store-glow.js?v=1').BASE, 'https://sylvexai.com/');
  assert.equal(glow.toHex('rgb(255, 255, 255)'), '#ffffff');
  assert.equal(glow.toHex('rgba(18, 15, 23, 1)'), '#120f17');
  assert.equal(glow.isLight('#ffffff'), true);
  assert.equal(glow.isLight('#1c1c1e'), false);
  const source = read('webapp/js/store-glow.js');
  assert.ok(source.includes("var DARK_SURFACE = '#120F17';"));
  assert.ok(source.includes('return isLight(hex) ? hex : DARK_SURFACE;'));
});

test('every Store card is wrapped once, kept as the same element, and re-wrapped after a re-render', () => {
  const source = read('webapp/js/store-glow.js');
  assert.ok(source.includes("container.querySelectorAll('.sxs-card')"));
  assert.ok(source.includes('if (!wrapped || wrapped.has(card)) return;'));
  assert.ok(source.includes('api.mount(host, card, { backgroundColor: surface })'), 'the card element itself moves inside');
  assert.ok(source.includes('observe(container, { childList: true, subtree: true })'));
  assert.ok(source.includes('entry.instance.unmount();'), 'removed cards release their glow');
  assert.match(read('store_glow/src/host.css'), /\.sxs-glow \.border-glow-inner \.sxs-card \{[^}]*background: transparent !important;/);
});

test('Mini App: shop and browser store cards both get the glow', () => {
  const index = read('webapp/index.html');
  assert.ok(index.includes('<script src="js/store-glow.js?v=store-glow-soft-20261019"></script>'));
  assert.ok(!index.includes('vendor/store-glow'), 'bundle loaded on demand only');
  const cabinet = read('webapp/js/cabinet.js');
  assert.equal((cabinet.match(/glowStoreCards\(plans, credits\);/g) || []).length, 2);
  assert.ok(cabinet.includes('if (glow) containers.forEach((container) => container && glow.watch(container));'));
});

test('the Website copy, when checked out next to this repo, is identical', (t) => {
  const sibling = new URL('../../sylvex-website/js/store-glow.js', import.meta.url);
  if (!existsSync(sibling)) return t.skip('sylvex-website is not checked out alongside');
  assert.equal(readFileSync(sibling, 'utf8'), read('webapp/js/store-glow.js'));
});
