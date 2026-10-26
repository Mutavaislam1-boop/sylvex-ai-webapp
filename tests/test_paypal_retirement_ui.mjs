import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('legacy payment page never calls a provider or opens a hosted payment link', () => {
  const grid = {textContent: ''};
  const source = readFileSync(new URL('../webapp/js/payments.js', import.meta.url), 'utf8');
  vm.runInNewContext(source, {document: {readyState: 'complete', getElementById: () => grid},
    fetch: () => assert.fail('retired page must not request checkout'),
    window: {location: new Proxy({}, {set: () => assert.fail('must not redirect to PayPal')})}});
  assert.match(grid.textContent, /PayPal больше не используется/);
  assert.doesNotMatch(source, /paypal\.com|payments\/paypal/);
});

test('Mini App contains no PayPal SDK button or binding request', () => {
  const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /paypal\.Buttons|payments\/paypal|PAYPAL_PRO_.*PLAN_ID/);
  assert.match(source, /payments\/stripe\/checkout/);
  assert.match(source, /payments\/stripe\/portal/);
  assert.match(source, /const STORE_METHODS = \{ stars: 'telegram_stars' \}/);
});
