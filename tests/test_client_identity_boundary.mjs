import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const adapter = readFileSync(new URL('../webapp/js/api-auth.js', import.meta.url), 'utf8');
const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const user = readFileSync(new URL('../webapp/js/user.js', import.meta.url), 'utf8');

function harness(initData = '') {
  const calls = [];
  const window = {
    location: {href: 'https://api.sylvex.ai/webapp/index.html', origin: 'https://api.sylvex.ai'},
    SYLVEX: {tg: {initData}},
    Telegram: {WebApp: {initData}},
    fetch: async (input, options) => { calls.push({input: String(input), options}); return {ok: true}; },
  };
  vm.runInNewContext(adapter, {window, URL, Request, Headers, FormData, URLSearchParams});
  return {window, calls};
}

test('standalone Browser Mini App strips Telegram identity and uses its session cookie', async () => {
  const {window, calls} = harness('');
  await window.fetch('/api/public/prostudio/generate?telegram_id=999&initData=old', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Telegram-Init-Data': 'old'},
    body: JSON.stringify({telegram_id: 999, initData: 'old', prompt: 'hello'}),
  });
  const call = calls[0];
  assert.doesNotMatch(call.input, /telegram_id|initData/);
  assert.equal(call.options.credentials, 'same-origin');
  assert.equal(call.options.headers.has('X-Telegram-Init-Data'), false);
  assert.deepEqual(JSON.parse(call.options.body), {prompt: 'hello'});
});

test('real Telegram Mini App keeps signed Telegram authentication inside its boundary', async () => {
  const {window, calls} = harness('signed-init-data');
  await window.fetch('/api/public/prostudio/generate', {
    method: 'POST', body: JSON.stringify({telegram_id: 42, prompt: 'hello'}),
  });
  assert.equal(calls[0].options.headers.get('X-Telegram-Init-Data'), 'signed-init-data');
  assert.equal(JSON.parse(calls[0].options.body).telegram_id, 42);
});

test('browser workspace uses account_id while the web session exposes no storage key', () => {
  assert.match(cabinet, /S\.user && \(S\.user\.account_id \|\| S\.user\.sylvex_user_id\)/);
  assert.match(user, /account_id: json\.account_id \|\| json\.sylvex_user_id/);
  assert.doesNotMatch(user.slice(user.indexOf('async function syncWebSession')), /json\.storage_id/);
});
