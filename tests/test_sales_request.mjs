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
  assert.match(index, /<link rel="stylesheet" href="css\/sales-request\.css\?v=sales-request-20261028" \/>/);
  assert.match(index, /<script src="js\/sales-request\.js\?v=sales-request-20261028"><\/script>/);
});

test('three steps on a rail, Russian in the Mini App, Send on the last one', () => {
  assert.match(module_, /steps: \[\['Заявитель', 'Организация или частное лицо'\], \['Запрос', 'Что нужно и в каком объёме'\], \['Контакты', 'Куда ответить'\]\]/);
  assert.match(module_, /var vertical = card\.clientWidth >= 520;/);
  assert.match(css, /\.sxr--vertical \.sxr-header\{width:212px;max-width:42%\}/);
  assert.match(module_, /next\.innerHTML = '<span>' \+ esc\(state\.sending \? t\.sending : last \? t\.send : t\.next\)/);
});

test('a step cannot be passed with its required fields empty', () => {
  assert.match(module_, /if \(!d\.kind\) return t\.needWho;/);
  assert.match(module_, /if \(d\.kind === 'organization' && !d\.company\.trim\(\)\) return t\.needCompany;/);
  assert.match(module_, /if \(!EMAIL\.test\(d\.email\.trim\(\)\)\) return t\.needEmail;/);
});

test('after Send the card closes and a small "Request sent" window shows', () => {
  assert.match(module_, /close\(true\);\n\s+sent\(t\);/);
  assert.match(module_, /sent: 'Запрос отправлен', sentNote: 'Отдел продаж свяжется с вами в ближайшее время\.'/);
});

test('Contact sales in the Mini App opens it and posts the fields', () => {
  assert.match(js, /if \(supportTopic === 'sales' && window\.SylvexSalesRequest\) \{ openSalesRequest\(\); return; \}/);
  assert.match(js, /body: JSON\.stringify\(\{ sales: request, surface: 'miniapp' \}\),/);
});

test('the Admin Console Inbox shows a sales request as a card', () => {
  assert.match(inbox, /\{m\.sales \? <SalesCard s=\{m\.sales\} \/> : <div style=\{\{ whiteSpace: "pre-wrap" \}\}>\{m\.text\}<\/div>\}/);
  assert.match(inbox, /<b>\{t\("Sales request"\)\}<\/b>/);
});
