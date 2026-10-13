// Run with: node tests/test_browser_guest_frontend.mjs
//
// Browser Mini App (opened outside Telegram): sign-in is optional. The
// sign-in window can be closed, a guest sees Log in / Sign up in the home
// user card, and the global header hides the usage counters. Telegram never
// gets the browser-only classes, so its header and card stay as they were.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const html = read('../webapp/cabinet.html');
const css = read('../webapp/css/cabinet.css');
const auth = read('../webapp/js/account-auth.js');
const cabinet = read('../webapp/js/cabinet.js');
const lang = read('../webapp/js/language.js');

test('the sign-in window can be closed to continue as a guest', () => {
  const gate = auth.slice(auth.indexOf('function openWebAuthGate()'), auth.indexOf('S.ensureWebAuthGate = ensureWebAuthGate'));
  assert.doesNotMatch(gate, /persistent:\s*true/);
  assert.match(gate, /onClose:/);
  assert.match(gate, /Continue as guest/);
});

test('the guest block lives in the home user card and opens sign-in', () => {
  const home = html.slice(html.indexOf('data-view="home"'), html.indexOf('home-socials'));
  assert.match(home, /id="homeGuest"/);
  assert.match(home, /SYLVEX\.openWebAuthGate/);
  assert.equal((html.match(/id="homeGuest"/g) || []).length, 1);
});

test('usage counters are hidden only in the browser app header', () => {
  assert.match(css, /html\.browser-app \.tb-stats\{display:none\}/);
  assert.doesNotMatch(css, /(^|\n)\.tb-stats\{display:none/);
  assert.match(html, /id="tbGenToday"/);
  assert.match(html, /id="profileGens"/);
  assert.match(cabinet, /classList\.toggle\('browser-app', isBrowserApp\(\)\)/);
  assert.match(cabinet, /classList\.toggle\('browser-guest', !!on && isBrowserApp\(\)\)/);
});

test('guest texts exist in English and Russian', () => {
  for (const key of ['guest_title', 'guest_sub', 'guest_login']) {
    assert.equal((lang.match(new RegExp('\\b' + key + ':', 'g')) || []).length, 2, key);
  }
});
