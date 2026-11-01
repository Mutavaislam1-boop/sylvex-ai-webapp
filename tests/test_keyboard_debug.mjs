// Keyboard Debug (js/keyboard-debug.js): a diagnostic overlay that is off for
// everyone by default, checked by the server, and never reports typed text,
// tokens or Telegram initData.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const js = read('../webapp/js/keyboard-debug.js');
const index = read('../webapp/index.html');

function run({ search = '', stored = null, telegram = null } = {}) {
  const calls = { fetch: [], appended: 0, listeners: [] };
  const store = new Map(stored ? [['sylvex-kbdebug', stored]] : []);
  const document = {
    readyState: 'complete',
    addEventListener: (type) => calls.listeners.push(type),
    head: { appendChild: () => { calls.appended++; } },
    body: { appendChild: () => { calls.appended++; } },
  };
  const window = {
    document,
    Telegram: telegram ? { WebApp: telegram } : undefined,
  };
  const context = {
    window, document,
    location: { search, origin: 'https://example.test', pathname: '/webapp/index.html' },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    URLSearchParams,
    fetch: (url, opts) => { calls.fetch.push({ url, opts }); return new Promise(() => {}); },
  };
  vm.runInNewContext(js, context);
  return { calls, store, api: window.SYLVEX.keyboardDebug };
}

test('loaded by the Mini App after the Standard interface', () => {
  assert.match(index, /<script src="js\/standard-studio\.js\?v=[^"]+"><\/script>\s*<script src="js\/keyboard-debug\.js\?v=[^"]+"><\/script>/);
});

test('off by default: no request, nothing added to the page', () => {
  const { calls, api } = run();
  assert.equal(calls.fetch.length, 0);
  assert.equal(calls.appended, 0);
  assert.deepEqual(calls.listeners, ['click']);      // only the tap counter
  assert.equal(api.report(), null);
});

test('?kbdebug=1 asks the server; the flag alone is not access', () => {
  const { calls } = run({ search: '?kbdebug=1' });
  assert.equal(calls.fetch.length, 1);
  assert.equal(calls.fetch[0].url, '/api/public/keyboard-debug/access');
  assert.equal(calls.fetch[0].opts.method, 'POST');
  assert.equal(calls.fetch[0].opts.body, '{}');      // no Telegram, nothing to send
  assert.equal(calls.appended, 0);                    // panel only after "allowed"
  assert.match(js, /if \(data && data\.allowed\) \{ flagSet\(true\); start\(\); \}/);
  assert.match(js, /else \{ flagSet\(false\);/);
});

test('?kbdebug=0 clears a stored flag without any request', () => {
  const { calls, store } = run({ search: '?kbdebug=0', stored: '1' });
  assert.equal(calls.fetch.length, 0);
  assert.equal(store.has('sylvex-kbdebug'), false);
});

test('Telegram: initData goes only to the access check, startapp=kbdebug works', () => {
  const { calls } = run({ telegram: { initData: 'signed-init-data', initDataUnsafe: { start_param: 'kbdebug' } } });
  assert.equal(calls.fetch.length, 1);
  assert.deepEqual(JSON.parse(calls.fetch[0].opts.body), { initData: 'signed-init-data' });
});

test('the report never carries typed text, initData or user data', () => {
  // Everything that ends up in the report: the measurements, Telegram's
  // viewport fields and the report envelope.
  const report = js.slice(js.indexOf('function telegramInfo'), js.indexOf('function findIssues'))
    + js.slice(js.indexOf('function buildReport'), js.indexOf('function copyReport'));
  assert.doesNotMatch(report, /initData|initDataUnsafe|\.user\b|\.value|location\.search|location\.hash|location\.href|cookie/);
  assert.match(report, /page: location\.origin \+ location\.pathname/);
  // Typing is logged as an event only, never its content.
  const typing = js.slice(js.indexOf("on(document, 'input'"), js.indexOf("on(window, 'resize'"));
  assert.doesNotMatch(typing, /\.value|textContent|innerText/);
  // The only .value write is the read-only fallback that shows the report itself.
  assert.deepEqual(js.match(/\.value\b/g), ['.value']);
});

test('observes only: a fixed overlay, no change to composer positioning', () => {
  assert.match(js, /#sxKbDebug\{position:fixed;/);
  assert.doesNotMatch(js, /\.style\.(top|bottom|height|transform|paddingBottom|marginBottom)\s*=/);
  assert.doesNotMatch(js, /setProperty\(|classList\.(add|toggle|remove)\('(kb-open|composer-input-window)/);
  assert.doesNotMatch(js, /--kb|--sxs-kb|--vv-/);
  assert.doesNotMatch(js, /import |require\(|<script/);
});

test('measures what the task lists and keeps at most 200 events', () => {
  for (const name of ['innerHeight', 'clientHeight', 'offsetTop', 'pageTop', 'scrollY', 'getBoundingClientRect', 'viewportHeight', 'viewportStableHeight', 'isExpanded', 'safeAreaInset', 'contentSafeAreaInset']) {
    assert.ok(js.includes(name), name);
  }
  for (const ev of ["'focusin'", "'focusout'", "'resize'", "'orientationchange'", "'scroll'", "'viewportChanged'", "'safeAreaChanged'", "'contentSafeAreaChanged'", 'ResizeObserver']) {
    assert.ok(js.includes(ev), ev);
  }
  assert.match(js, /var MAX_EVENTS = 200;/);
  assert.match(js, /if \(state\.events\.length > MAX_EVENTS\) state\.events\.shift\(\);/);
  assert.match(js, /'open \(presumed\)' : 'closed \(presumed\)'/);
});

test('keyboard state compares with the height taken before the keyboard opened', () => {
  // Taken only while no field is focused; just after a blur (keyboard still
  // closing) it may only grow; reset on rotation - never the shrunk height.
  assert.match(js, /if \(!editable\) \{\s*var settled = Date\.now\(\) - base\.blurAt > 700;\s*if \(!base\.visible \|\| vvH > base\.visible \|\| settled\) base\.visible = vvH;/);
  assert.match(js, /if \(base\.width !== width\) \{ base\.width = width; base\.visible = 0; base\.inner = 0; \}/);
  assert.match(js, /var keyboardHeight = Math\.max\(0, Math\.round\(base\.visible - vvH\)\);/);
  // The layout overlap (0 when iOS pans the visual viewport) never decides alone.
  assert.match(js, /var keyboardOpen = editable && \(keyboardHeight > 80 \|\| tgShrink > 80\);/);
  assert.match(js, /state\.base\.blurAt = Date\.now\(\);/);
  // What Standard's own rule decided is part of the report.
  assert.match(js, /standard: typeof S\.standardKeyboard === 'function' \? S\.standardKeyboard\(\) : null/);
});
