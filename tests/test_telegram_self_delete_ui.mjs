// S7-04: "Удалить аккаунт" in the Telegram Mini App profile (static checks).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const index = readFileSync(new URL('../webapp/index.html', import.meta.url), 'utf8');

function extract(name) {
  const start = source.search(new RegExp('^[ \\t]*(?:async )?function ' + name + '\\(', 'm'));
  assert.ok(start >= 0, name);
  const open = start + source.slice(start).search(/\)\s*\{/);
  let depth = 0;
  for (let i = source.indexOf('{', open); i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error('unterminated ' + name);
}

test('the profile shows "Удалить аккаунт" in Telegram too', () => {
  assert.match(html, /onclick="SYLVEX\.openDeleteAccount\(\)">Удалить аккаунт<\/button>/);
  assert.match(css, /html\.telegram-app \.ep-danger\{display:block/);
  assert.match(source, /classList\.toggle\('telegram-app', hasTelegramContext\(\) && !isWebEmbed\(\)\)/);
  assert.match(extract('openDeleteAccount'), /if \(hasTelegramContext\(\) && !isWebEmbed\(\)\) \{ openTelegramDeleteAccount\(\); return; \}/);
});

test('Telegram flow: preview, Stars renewal first, hold to confirm, session ends', () => {
  const flow = extract('openTelegramDeleteAccount');
  assert.match(flow, /'\/api\/account\/telegram-delete\/start'/);
  assert.match(flow, /blocker === 'stars_renewal_active'\) \{ renewalStep/);
  assert.match(flow, /subscriptionRequest\('cancel'\)/);
  assert.match(flow, /Баланс ' \+ Number\(info\.balance/);
  assert.match(flow, /SylvexHoldButton\.create/);
  assert.match(flow, /'\/api\/account\/telegram-delete\/confirm',\s*\{ confirm_token: info\.confirm_token, erasure_scope: 'telegram_account_content_v1' \}/);
  assert.ok(flow.indexOf('S.tg.close()') > flow.indexOf('function doneStep'));
  assert.doesNotMatch(flow, /\/api\/web\/account\/delete|\/api\/admin\//);
});

test('the browser flow is unchanged and assets are re-versioned', () => {
  assert.match(extract('openDeleteAccount'), /post\('\/api\/web\/account\/delete\/start'\)/);
  assert.match(index, /js\/cabinet\.js\?v=telegram-delete-20261111/);
  assert.match(index, /css\/cabinet\.css\?v=telegram-delete-20261111/);
  assert.match(index, /cabinet\.html\?v=telegram-delete-20261111/);
});
