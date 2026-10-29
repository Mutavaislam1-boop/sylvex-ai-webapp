// Notices from SYLVEX in the Mini App (Telegram and browser): a blocked
// account sees the reason (and can still contact support), and credits / a
// subscription / a team role given by SYLVEX show once as a centered card
// (js/account-notice.js, the same file as the website's).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../webapp/' + path, import.meta.url), 'utf8');
const cabinet = read('js/cabinet.js');
const index = read('index.html');
const module_ = read('js/account-notice.js');

test('the module and its stylesheet are loaded by the Mini App', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/account-notice\.css\?v=admin-a-20261029" \/>/);
  assert.match(index, /<script src="js\/account-notice\.js\?v=admin-a-20261029"><\/script>/);
});

test('the Mini App checks the block first, then the award cards, outside the website embed', () => {
  assert.match(cabinet, /return !!window\.SylvexAccountNotice && !isWebEmbed\(\)/);
  assert.match(cabinet, /fetch\('\/api\/public\/account\/status'\)[\s\S]{0,120}if \(status\.blocked\) \{ showAccountBlocked\(status\); return; \}/);
  assert.match(cabinet, /fetch\('\/api\/public\/notifications\/awards'\)/);
  assert.match(cabinet, /body: JSON\.stringify\(\{ ids \}\)/);
  assert.match(cabinet, /initFeedbackPrompt\(\);\n\s+initAccountNotices\(\);/);
});

test('contacting support from the block notice opens the support window above it', () => {
  assert.match(cabinet, /notice\.setBlockedBehind\(true\);\n\s+openSupport\('support'\);/);
});

function fakeDom() {
  const made = [];
  const el = () => {
    const node = {
      className: '', innerHTML: '', classList: { add() {}, toggle() {} }, listeners: {},
      addEventListener(type, fn) { this.listeners[type] = fn; }, remove() { this.removed = true; },
      querySelector(sel) { const child = el(); child.sel = sel; (node.children ||= []).push(child); return child; },
      focus() {},
    };
    return node;
  };
  const document = { body: { appendChild(n) { made.push(n); } }, createElement: () => el(), addEventListener() {}, removeEventListener() {} };
  return { made, window: { document, setTimeout: (fn) => fn() } };
}

test('award cards: English text, public reason, one card at a time, seen ids reported once', () => {
  const { made, window } = fakeDom();
  vm.runInNewContext(module_, { window, setTimeout: window.setTimeout, Object, String, Number, Date, isNaN });
  const seen = [];
  const shown = window.SylvexAccountNotice.showAwards({
    lang: 'en', theme: 'light',
    items: [
      { notification_id: 7, award: { type: 'credits', amount: 50, reason_code: 'error_compensation' } },
      { notification_id: 8, award: { type: 'role', role: 'moderator', label: 'Модератор' } },
    ],
    onSeen: (ids) => seen.push(ids),
  });
  assert.equal(shown, true);
  const root = made[0];
  assert.match(root.className, /sxn-layer light sxn-awards/);
  assert.match(root.innerHTML, /You received 50 credits/);
  assert.match(root.innerHTML, /Compensation for an error/);
  assert.match(root.innerHTML, />Next</);
  root.children.at(-1).listeners.click();
  assert.match(root.innerHTML, /You are on the SYLVEX team/);
  assert.match(root.innerHTML, /Your role: Moderator/);
  root.children.at(-1).listeners.click();
  assert.equal(JSON.stringify(seen), "[[7,8]]");
});

test('block notice: Russian text with the reason, escaped', () => {
  const { made, window } = fakeDom();
  vm.runInNewContext(module_, { window, setTimeout: window.setTimeout, Object, String, Number, Date, isNaN });
  window.SylvexAccountNotice.showBlocked({ lang: 'ru', reason: 'Спам <b>', since: '2026-10-29T10:00:00', onContact() {} });
  assert.match(made[0].innerHTML, /Доступ к аккаунту ограничен/);
  assert.match(made[0].innerHTML, /Спам &lt;b&gt;/);
  assert.match(made[0].innerHTML, /Написать в поддержку/);
  assert.equal(window.SylvexAccountNotice.isBlockedShown(), true);
});
