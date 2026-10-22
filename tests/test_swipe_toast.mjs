// Run with: node --test tests/test_swipe_toast.mjs
//
// App notices as the React Bits SwipeToast (swipe_toast/ ->
// webapp/js/vendor/swipe-toast, used by js/ui.js toast()): the published
// component unmodified, the task's settings, the bottom right stack above
// every block, and the #toast fallback in the same corner.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');

test('SwipeToast.jsx / SwipeToast.css: the published files, unmodified', () => {
  // https://raw.githubusercontent.com/DavidHDev/react-bits/main/public/r/SwipeToast-JS-CSS.json
  assert.equal(sha256('swipe_toast/src/SwipeToast.jsx'), '0d111d637b5ba6ec388d68ee3fca6ae9f60ecd632363381c7b20ec56a5300154');
  assert.equal(sha256('swipe_toast/src/SwipeToast.css'), 'dcb13f804fa6c3012b48bfa3c2c3c2ca35369209c4fe0687283191b516db22be');
  assert.ok(read('webapp/js/vendor/swipe-toast/swipe-toast.js').includes('SylvexSwipeToast'));
  assert.ok(existsSync(new URL('../webapp/js/vendor/swipe-toast/swipe-toast.css', import.meta.url)));
  assert.ok(read('.gitignore').includes('swipe_toast/node_modules/'));
});

test('the task settings', () => {
  const main = read('swipe_toast/src/main.jsx');
  const start = main.indexOf('const TOAST_PROPS = {');
  const block = main.slice(start, main.indexOf('};', start) + 1);
  const settings = vm.runInNewContext('(' + block.replace('const TOAST_PROPS = ', '') + ')');
  assert.deepEqual(JSON.parse(JSON.stringify(settings)), {
    actionLabel: '', background: '#27272a', color: '#f5f5f5', fuseColor: '#51f524', width: 356, radius: 12,
    slideMs: 400, settleBounce: 0.2, swipeDistance: 40, duration: 4000, fuse: 'bottom', pauseOnHover: true, closeButton: true,
  });
});

test('notices stack in the bottom right corner above every block', () => {
  const host = read('swipe_toast/src/host.css');
  assert.match(host, /\.sylvex-toasts \{\n  position: fixed;\n  right: 32px;\n  bottom: calc\(32px \+ env\(safe-area-inset-bottom, 0px\)\);\n  z-index: 999999999;/);
  const css = read('webapp/css/cabinet.css');
  assert.ok(css.includes('.toast{position:fixed;right:32px;bottom:calc(32px + env(safe-area-inset-bottom,0px));z-index:999999999;'));
  assert.ok(!css.includes('.toast{position:fixed;left:50%;top:18px;'), 'no notice from the top any more');
});

test('toast() shows the SwipeToast, the #toast element only as the fallback', () => {
  const ui = read('webapp/js/ui.js');
  assert.ok(ui.includes("loadSwipeToast().then((api) => api.show(text, { fuseColor })).catch(() => fallbackToast(text));"));
  assert.ok(ui.includes("if (document.documentElement.classList.contains('sxAuth-open')) return;"));
  assert.ok(ui.includes("SWIPE_TOAST_BASE + 'js/vendor/swipe-toast/swipe-toast.js?v=' + SWIPE_TOAST_VERSION"));
});
