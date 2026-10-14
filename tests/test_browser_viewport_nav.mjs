// Run with: node tests/test_browser_viewport_nav.mjs
//
// Mini App opened in a mobile browser (never inside Telegram): sizes follow
// the visible browser viewport (--bvh) instead of vh, and Back/Forward walks
// the app's own steps. Both are switched on only for html.browser-app /
// isBrowserApp(), so Telegram layout and navigation stay as they are.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const cabinet = read('../webapp/js/cabinet.js');
const ui = read('../webapp/js/ui.js');
const css = read('../webapp/css/cabinet.css');

const between = (text, start, end) => text.slice(text.indexOf(start), text.indexOf(end, text.indexOf(start)));

test('viewport and history only start in the browser app', () => {
  assert.match(between(cabinet, 'function initBrowserViewport()', 'const VH_VALUE_RE'), /if \(!isBrowserApp\(\) \|\| initBrowserViewport\.done\) return;/);
  assert.match(between(cabinet, 'function start() {\n      if (enabled', 'function push('), /!isBrowserApp\(\)/);
  assert.match(cabinet, /setTimeout\(\(\) => BrowserNav\.start\(\), 400\)/);
  assert.match(ui, /window\.SYLVEX\.onViewSwitched\(name\)/);
});

test('vh rules get browser-only twins with the visible-viewport unit', () => {
  // Reproduce the conversion used at runtime on a sample value and selector.
  const VH_VALUE_RE = /(\d*\.?\d+)vh\b/g;
  const convert = (v) => v.replace(VH_VALUE_RE, (_, n) => 'calc(var(--bvh, 1vh) * ' + n + ')');
  assert.equal(convert('min(760px, calc(100vh - 40px))'), 'min(760px, calc(calc(var(--bvh, 1vh) * 100) - 40px))');
  assert.equal(convert('100dvh'), '100dvh');
  assert.match(cabinet, /':where\(html\.browser-app\) ' \+ sel/);
  assert.match(cabinet, /owner\.insertRule\(browserScopedSelector\(rule\.selectorText\)/);
});

test('Pro Studio and Photo Tools fit the visible browser area', () => {
  assert.match(css, /html\.browser-app \.view\[data-view="tools"\]\.active \.studio\{\s*height:calc\(var\(--bvh,1vh\) \* 100 - env\(safe-area-inset-top,0px\) - env\(safe-area-inset-bottom,0px\)\)/);
  assert.match(css, /html\.browser-app \.photo-tool-dialog\{max-height:calc\(var\(--bvh,1vh\) \* 100/);
});

test('Photo Tools list and tool are separate history steps', () => {
  assert.match(cabinet, /browserNav\.push\(navKey, \{\s*open: \(\) => openPhotoToolModal\(null, kind\)/);
  assert.equal((cabinet.match(/window\.SYLVEX\.browserNav\.closed\(navKey\)/g) || []).length, 2);
});

test('browser app has no custom keyboard lift or keyboard-close button', () => {
  const fn = between(cabinet, 'function usesVirtualKeyboardLayout() {', 'function dismissGenerationInputUi');
  assert.match(fn, /if \(S\.isBrowserApp && S\.isBrowserApp\(\)\) return false;/);
  assert.match(fn, /return Boolean\(S\.device && S\.device\.usesVirtualKeyboard\);/);
  assert.match(css, /html\.browser-app \.mobile-keyboard-close\{display:none!important\}/);
});
