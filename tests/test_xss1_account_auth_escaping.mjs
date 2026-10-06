// Run with: node --test tests/test_xss1_account_auth_escaping.mjs
//
// Regression tests for the security audit's XSS-1 finding:
//
// webapp/js/account-auth.js interpolated server-controlled strings
// (session.email, session.telegram_username, res.json.error - the
// backend's error text) and, most notably, the exact string the user
// just typed into the "Connect existing SYLVEX account" email field
// (stepCode's `email` param) directly into HTML template literals that
// are then assigned to .innerHTML via setBody()/openOverlay() - with no
// escaping anywhere in the file, unlike cabinet.js which uses
// S.escapeHtml consistently. A malicious string in any of those 6 spots
// (lines 373, 376, 390, 409, 467, 507 at the time of the audit) would be
// parsed as live HTML/script by the browser instead of rendered as text.
//
// Fix: each of those 6 interpolations now routes through S.escapeHtml
// (the same helper cabinet.js already uses, defined in webapp/js/ui.js)
// before being embedded in the template literal.
//
// Exercises the real functions directly via node:vm extraction (same
// pattern as test_character_detail_page.mjs / test_generation_media_fallback.mjs),
// using the REAL escapeHtml implementation extracted from ui.js (not a
// reimplementation) so these tests prove the actual production escaping
// behavior, not a copy that could silently drift from it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const accountAuth = readFileSync(new URL('../webapp/js/account-auth.js', import.meta.url), 'utf8');
const ui = readFileSync(new URL('../webapp/js/ui.js', import.meta.url), 'utf8');

function extractFunction(source, name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(source);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = source.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < source.length, `matching close not found: ${name}`);
  return source.slice(match.index, i + 1);
}

const REAL_ESCAPE_HTML_SRC = extractFunction(ui, 'escapeHtml');

const SCRIPT_PAYLOAD = '<script>alert(1)</script>';
const IMG_ONERROR_PAYLOAD = '<img src=x onerror=alert(document.cookie)>';

function makeContext() {
  const calls = []; // every html string passed to setBody()
  const handlers = {}; // selector -> last-assigned onclick handler, via q()
  const context = vm.createContext({
    calls,
    handlers,
    S: {},
    toast: () => {},
    mountTelegramWidget: () => {},
    refreshLinkedStatusBadge: async () => {},
    setBody: (overlay, html) => { calls.push(html); },
    telegramInitData: () => '',
    q: (overlay, sel) => {
      handlers[sel] = handlers[sel] || {};
      return handlers[sel];
    },
  });
  // Install the real escapeHtml (from ui.js) onto the fake S, exactly as
  // production wires window.SYLVEX.escapeHtml via Object.assign.
  vm.runInContext(REAL_ESCAPE_HTML_SRC, context);
  vm.runInContext('S.escapeHtml = escapeHtml;', context);
  return context;
}

function lastHtml(context) {
  return context.calls[context.calls.length - 1];
}

function assertNeverExecutable(html) {
  // Escaping turns '<' into '&lt;' - the word "onerror=" surviving as
  // literal, inert text is correct and expected; what must never survive
  // is an actual unescaped '<script' or '<img ... onerror' tag opener.
  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<img[^>]*onerror/i);
}

// ---------------------------------------------------------------------------
// Lines 373/376: renderWebLinkedPanel's base() - session.email / telegram_username
// (server-controlled - returned by GET /api/web/session/me).
// ---------------------------------------------------------------------------

test('XSS-1: base() escapes a malicious session.email instead of rendering it as HTML', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'base'), context);
  context.session = {
    email: IMG_ONERROR_PAYLOAD,
    email_verified: true,
    oauth: {},
    telegram_connected: true,
    telegram_username: 'plainuser',
  };
  context.overlay = {};
  vm.runInContext('base()', context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;img src=x onerror=alert\(document\.cookie\)&gt;/);
});

test('XSS-1: base() escapes an unverified malicious session.email, keeping the "(unverified)" suffix readable', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'base'), context);
  context.session = {
    email: SCRIPT_PAYLOAD,
    email_verified: false,
    oauth: {},
    telegram_connected: true,
    telegram_username: 'plainuser',
  };
  context.overlay = {};
  vm.runInContext('base()', context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt; \(unverified\)/);
});

test('XSS-1: base() escapes a malicious session.telegram_username instead of rendering it as HTML', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'base'), context);
  context.session = {
    email: null,
    oauth: {},
    telegram_connected: true,
    telegram_username: SCRIPT_PAYLOAD,
  };
  context.overlay = {};
  vm.runInContext('base()', context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});

test('XSS-1: base() still renders ordinary email/telegram_username unescaped-looking text correctly (no over-escaping)', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'base'), context);
  context.session = {
    email: 'alice@example.com',
    email_verified: true,
    oauth: {},
    telegram_connected: true,
    telegram_username: 'alice_tg',
  };
  context.overlay = {};
  vm.runInContext('base()', context);
  const html = lastHtml(context);
  assert.match(html, /alice@example\.com/);
  assert.match(html, /@alice_tg/);
});

// ---------------------------------------------------------------------------
// Lines 390/409: renderWebLinkedPanel's previewFromWidget()/confirmFromWidget() -
// res.json.error (server-controlled error text).
// ---------------------------------------------------------------------------

test('XSS-1: previewFromWidget() escapes a malicious server error message', async () => {
  const context = makeContext();
  context.apiFetch = async () => ({ ok: false, json: { conflict: false, error: SCRIPT_PAYLOAD } });
  vm.runInContext(extractFunction(accountAuth, 'previewFromWidget'), context);
  context.overlay = {};
  await vm.runInContext('previewFromWidget({})', context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});

test('XSS-1: confirmFromWidget() escapes a malicious server error message', async () => {
  const context = makeContext();
  context.apiFetch = async () => ({ ok: false, json: { error: IMG_ONERROR_PAYLOAD } });
  vm.runInContext(extractFunction(accountAuth, 'confirmFromWidget'), context);
  context.overlay = {};
  await vm.runInContext('confirmFromWidget({}, false)', context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;img src=x onerror=alert\(document\.cookie\)&gt;/);
});

test('XSS-1: previewFromWidget() still falls back to the plain default message when the server sends none', async () => {
  const context = makeContext();
  context.apiFetch = async () => ({ ok: false, json: { conflict: false, error: '' } });
  vm.runInContext(extractFunction(accountAuth, 'previewFromWidget'), context);
  context.overlay = {};
  await vm.runInContext('previewFromWidget({})', context);
  const html = lastHtml(context);
  assert.match(html, /Something went wrong/);
});

// ---------------------------------------------------------------------------
// Line 467: renderTelegramLinkedPanel's stepCode() - the reflected-XSS
// shape the audit called out by name: the exact string the user just
// typed into the "Connect existing SYLVEX account" email field, echoed
// straight back after a successful request-code call.
// ---------------------------------------------------------------------------

test('XSS-1: stepCode() escapes the user-typed email it reflects back ("textbook reflected-DOM-XSS shape")', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'stepCode'), context);
  context.overlay = {};
  vm.runInContext(`stepCode(${JSON.stringify(IMG_ONERROR_PAYLOAD + '@evil.test')})`, context);
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;img src=x onerror=alert\(document\.cookie\)&gt;@evil\.test/);
});

test('XSS-1: stepCode() still shows a normal email address unescaped-looking', () => {
  const context = makeContext();
  vm.runInContext(extractFunction(accountAuth, 'stepCode'), context);
  context.overlay = {};
  vm.runInContext(`stepCode(${JSON.stringify('bob@example.com')})`, context);
  const html = lastHtml(context);
  assert.match(html, /We sent a 6-digit code to bob@example\.com\. It expires in 10 minutes\./);
});

// ---------------------------------------------------------------------------
// Line 507: renderTelegramLinkedPanel's stepConfirm() - res.json.error again,
// reached through its #tlaConfirm click handler.
// ---------------------------------------------------------------------------

test('XSS-1: stepConfirm()\'s confirm-click handler escapes a malicious server error message', async () => {
  const context = makeContext();
  context.apiFetch = async () => ({ ok: false, json: { error: SCRIPT_PAYLOAD } });
  vm.runInContext(extractFunction(accountAuth, 'renderMergeSummary'), context);
  vm.runInContext(extractFunction(accountAuth, 'stepConfirm'), context);
  context.overlay = {};
  vm.runInContext('stepConfirm("bob@example.com", "123456", {})', context);
  assert.ok(context.handlers['#tlaConfirm'] && context.handlers['#tlaConfirm'].onclick, 'confirm handler was not wired');
  await context.handlers['#tlaConfirm'].onclick();
  const html = lastHtml(context);
  assertNeverExecutable(html);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});
