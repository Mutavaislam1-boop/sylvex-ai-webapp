// Run with: node --test tests/test_sales_request.mjs
//
// Store → Contact sales opens the sales request in steps (js/sales-request.js,
// the same file as the website's): who is asking, what they need, where to
// answer. Send posts the fields to /api/public/contact; the admin sees them
// as a card in the Admin Console Inbox.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const module_ = read('webapp/js/sales-request.js');
const css = read('webapp/css/sales-request.css');
const js = read('webapp/js/cabinet.js');
const index = read('webapp/index.html');
const inbox = read('admin_console/src/pages/Inbox.tsx');

test('the Mini App loads the sales request', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/sales-request\.css\?v=tz1-20261028" \/>/);
  assert.match(index, /<script src="js\/sales-request\.js\?v=tz1-20261028"><\/script>/);
});

test('three steps on a rail, Russian in the Mini App, Send on the last one', () => {
  assert.match(module_, /steps: \[\['Заявитель', 'Организация или частное лицо'\], \['Запрос', 'Что нужно и в каком объёме'\], \['Контакты', 'Куда ответить'\]\]/);
  assert.match(module_, /var vertical = card\.clientWidth >= 520;/);
  assert.match(css, /\.sxr--vertical \.sxr-header\{width:220px;max-width:40%\}/);
  assert.match(module_, /next\.innerHTML = '<span>' \+ esc\(state\.sending \? t\.sending : last \? t\.send : t\.next\)/);
});

test('a step cannot be passed with its required fields empty', () => {
  assert.match(module_, /if \(!d\.kind\) return t\.needWho;/);
  assert.match(module_, /if \(d\.kind === 'organization' && !d\.company\.trim\(\)\) return t\.needCompany;/);
  assert.match(module_, /if \(!EMAIL\.test\(d\.email\.trim\(\)\)\) return t\.needEmail;/);
});

test('after Send the card closes by itself and a small "Отправлено" tick shows', () => {
  assert.match(module_, /close\(true\);\n\s+sent\(t\);/);
  assert.match(module_, /\n      sent: 'Отправлено',\n/);
  assert.match(module_, /box\.innerHTML = '<span class="sxr-sent-mark">' \+ ICON\.check \+ '<\/span><b>' \+ esc\(t\.sent\) \+ '<\/b>';/);
});

test('one size on every step: the title inside the main block, the rail and the buttons stay put', () => {
  assert.match(module_, /title: 'Связаться с отделом продаж',/);
  assert.match(module_, /<div class="sxr-body"><h2 class="sxr-heading">' \+ esc\(t\.title\) \+ '<\/h2><div class="sxr-viewport"/);
  assert.match(css, /\.sxr\{position:relative;display:flex;flex-direction:column;box-sizing:border-box;width:min\(100%,720px\);height:min\(580px,calc\(100dvh - 32px\)\);overflow:hidden;/);
  assert.match(css, /\.sxr-viewport\{position:relative;flex:1;min-height:0;margin:-6px -20px;overflow-x:hidden;overflow-y:auto;/);
  assert.match(css, /\.sxr-extra\{display:flex;flex-direction:column;gap:16px;padding:18px 16px;/);
  assert.doesNotMatch(module_, /viewport\.animate\(\[\{ height/);
});

test('Contact sales in the Mini App opens it and posts the fields', () => {
  assert.match(js, /if \(supportTopic === 'sales' && window\.SylvexSalesRequest\) \{ openSalesRequest\(\); return; \}/);
  assert.match(js, /body: JSON\.stringify\(\{ sales: request, surface: 'miniapp' \}\),/);
});

test('the Admin Console Inbox shows a sales request as a card', () => {
  assert.match(inbox, /\{m\.sales \? <SalesCard s=\{m\.sales\} \/> : <div style=\{\{ whiteSpace: "pre-wrap" \}\}>\{m\.text\}<\/div>\}/);
  assert.match(inbox, /<b>\{t\("Sales request"\)\}<\/b>/);
});

test('the Store balance block shows the active plan as its badge (js/plan-badge.js)', () => {
  const html = read('webapp/cabinet.html');
  const badge = read('webapp/js/plan-badge.js');
  assert.match(html, /<div class="sb-plan" id="shopPlan" hidden><\/div>/);
  assert.match(js, /const planBadge = active && window\.SylvexPlanBadge \? window\.SylvexPlanBadge\.html\(plan\) : '';/);
  assert.match(badge, /var PERIOD = \{ en: \{ month: 'Monthly', year: 'Yearly' \}, ru: \{ month: 'месяц', year: 'год' \} \};/);
  assert.match(index, /<script src="js\/plan-badge\.js\?v=tz1-20261028"><\/script>/);
});
