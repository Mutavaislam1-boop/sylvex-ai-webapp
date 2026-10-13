// Mini App Store UX: Month/Year updates the card in place (no re-render, no
// scroll jump), full re-renders keep the visible card where it was, pricing
// and token cards centre themselves, the bottom navigation auto-hides, and
// "Select" on a token package opens the checkout directly.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const cards = read('../webapp/js/store-cards.js');
const cabinet = read('../webapp/js/cabinet.js');
const css = read('../webapp/css/cabinet.css');

assert.match(cards, /container\.__sxsUpdatePlanCard\(card, plan, periodBtn\.dataset\.sxsPeriod\)/, 'period switch patches the card');
assert.match(cards, /function updatePlanCard\(card, plan, period\)/);
assert.match(cards, /keepScroll\(container, function \(\) \{\s*container\.innerHTML = '<div class="sxs-grid">'/, 'plans keep scroll on re-render');
assert.match(cards, /keepScroll\(container, function \(\) \{\s*container\.innerHTML =\s*'<div class="sxs-grid" role="group">'/, 'credits keep scroll on re-render');
assert.match(cards, /el\.focus\(\{ preventScroll: true \}\)/, 'focus never scrolls');
assert.match(cards, /options\.selectOpensCheckout && typeof options\.onContinue === 'function'/);
assert.match(cabinet, /selectOpensCheckout: true/, 'Mini App: Select opens checkout');
assert.match(cabinet, /function initStoreCardCentering\(\)/);
assert.match(cabinet, /function initNavAutoHide\(\)/);
assert.match(cabinet, /initStoreCardCentering\(\);\s*initNavAutoHide\(\);/);
assert.match(css, /\.app>\.nav\.nav-autohide\{transform:translateX\(-50%\) translateY\(/);
console.log('store scroll ux: ok');
