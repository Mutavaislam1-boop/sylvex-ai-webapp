// Run with: node --test tests/test_replace_object_mask_editor_resize_leak.mjs
//
// Regression tests for remediation item #16 (BUG-1):
//
// openReplaceObjectMaskEditor() replaced the module-level
// replaceObjectEditorRuntime object wholesale on every call:
//   replaceObjectEditorRuntime = {token, ..., resizeHandler: null};
// If a PREVIOUS open had already finished initializing (initReplaceObjectMaskCanvas's
// finish() attaches runtime.resizeHandler via window.addEventListener('resize', ...))
// and the editor was reopened again without an intervening
// closeReplaceObjectMaskEditor() call (the only other place that ever called
// removeEventListener), that old handler reference was simply discarded -
// never detached - leaking one window 'resize' listener per rapid reopen.
//
// Fix: openReplaceObjectMaskEditor() now removes any handler already on
// replaceObjectEditorRuntime.resizeHandler BEFORE replacing the runtime
// object. The pre-existing token-based guards (in the .then() callback and
// at the top of initReplaceObjectMaskCanvas) already stop a stale async
// image-load completion from touching a no-longer-current instance; this
// file also locks that invariant in with a real race.
//
// Exercises the REAL extracted functions via node:vm (same pattern as
// test_studio_theme.mjs / test_xss1_account_auth_escaping.mjs), with a
// synchronous requestAnimationFrame (removes one async hop that's
// orthogonal to this bug) and a controllable fake Image whose load only
// completes when the test calls resolveImageLoad()/failImageLoad().
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractBlock(src, startMarker, endFunctionName) {
  const start = src.indexOf(startMarker);
  assert.ok(start >= 0, `start marker not found: ${startMarker}`);
  const fnPattern = new RegExp(`function ${endFunctionName}\\(`);
  const fnMatch = fnPattern.exec(src.slice(start));
  assert.ok(fnMatch, `end function not found: ${endFunctionName}`);
  const fnStart = start + fnMatch.index;
  const openBrace = src.indexOf('{', fnStart);
  let depth = 0, i = openBrace;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < src.length, `matching close brace not found for ${endFunctionName}`);
  return src.slice(start, i + 1);
}

const BLOCK_SRC = extractBlock(source, 'let replaceObjectEditorRuntime=', 'closeReplaceObjectMaskEditor');

class FakeImage {
  set src(value) {
    this._src = value;
    FakeImage.pending.push(this);
  }
  get src() { return this._src; }
}
FakeImage.pending = [];

function resetPendingImages() {
  FakeImage.pending.length = 0;
}

function resolveImageLoad(width = 200, height = 150) {
  const img = FakeImage.pending.shift();
  assert.ok(img, 'no pending image load to resolve');
  img.naturalWidth = width;
  img.naturalHeight = height;
  img.complete = true;
  img.onload && img.onload();
}

function failImageLoad() {
  const img = FakeImage.pending.shift();
  assert.ok(img, 'no pending image load to fail');
  img.onerror && img.onerror();
}

async function tick() {
  // Lets the .then() microtask queued by loadReplaceObjectEditorImage's
  // promise resolution actually run before assertions continue.
  await Promise.resolve();
  await Promise.resolve();
}

function makeFakeElement(overrides = {}) {
  const el = {
    style: {},
    classList: {
      _set: new Set(),
      add(name) { this._set.add(name); },
      remove(name) { this._set.delete(name); },
      contains(name) { return this._set.has(name); },
    },
    hidden: false,
    disabled: false,
    attributes: {},
    setAttribute(name, value) { el.attributes[name] = value; },
    removeAttribute(name) { delete el.attributes[name]; },
    querySelector() { return null; },
    ...overrides,
  };
  return el;
}

function makeContext() {
  resetPendingImages(); // a previous test's uncaught exception must never leak a pending load into this one
  const resizeListeners = [];
  const canvasContext = {
    save() {}, restore() {}, setTransform() {}, beginPath() {}, arc() {}, fill() {},
    moveTo() {}, lineTo() {}, stroke() {}, clearRect() {}, drawImage() {},
  };
  const canvas = makeFakeElement({
    width: 0, height: 0,
    getContext: () => canvasContext,
  });
  const wrap = makeFakeElement({
    getBoundingClientRect: () => ({width: 400, height: 300}),
  });
  const loading = makeFakeElement();
  const saveButton = makeFakeElement();
  const undoButton = makeFakeElement();
  const clearButton = makeFakeElement();
  const brushSlider = makeFakeElement();
  const brushLabel = makeFakeElement();

  const modal = makeFakeElement({
    querySelector(selector) {
      if (selector === '.replace-object-editor-loading') return loading;
      if (selector === '.replace-object-mask-toolbar .save') return saveButton;
      return null;
    },
  });

  const byId = {
    replaceObjectPhotoCanvas: canvas,
    replaceObjectMaskEditorModal: modal,
    replaceObjectUndoButton: undoButton,
    replaceObjectClearButton: clearButton,
    replaceObjectBrushSize: brushSlider,
    replaceObjectBrushSizeValue: brushLabel,
  };

  const document = {
    getElementById: (id) => byId[id] || null,
    querySelector: (selector) => {
      if (selector === '#replaceObjectMaskEditorModal .replace-object-mask-canvas-wrap') return wrap;
      return null;
    },
  };

  const window = {
    addEventListener: (name, fn) => { if (name === 'resize') resizeListeners.push(fn); },
    removeEventListener: (name, fn) => {
      if (name !== 'resize') return;
      const index = resizeListeners.indexOf(fn);
      if (index >= 0) resizeListeners.splice(index, 1);
    },
    requestAnimationFrame: (fn) => fn(),
  };

  const context = vm.createContext({
    window,
    document,
    Image: FakeImage,
    toast: () => {},
    photoToolStateFor: () => null, // not exercised by any test here
  });
  vm.runInContext(BLOCK_SRC, context);
  // replaceObjectEditorRuntime is a top-level `let` - it never becomes a
  // property of the context's global object, so expose a live getter
  // (itself defined in the same context, closing over the real binding)
  // rather than reading context.replaceObjectEditorRuntime directly.
  vm.runInContext('globalThis.__runtime = () => replaceObjectEditorRuntime;', context);
  return {context, window, document, modal, canvas, wrap, resizeListeners, runtime: () => context.__runtime()};
}

function fakeState(url = 'https://cdn.sylvex.ai/replace-object-source.jpg') {
  return {files: [{url}], markedPhotoStrokes: []};
}

test('a single open + successful load attaches exactly one resize listener', async () => {
  const h = makeContext();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => fakeState();

  h.context.openReplaceObjectMaskEditor();
  resolveImageLoad();
  await tick();

  assert.equal(h.resizeListeners.length, 1);
});

test('rapid reopen before the previous editor was closed does not accumulate resize listeners', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  // Open #1 completes fully - its finish() attaches resizeHandler H1.
  h.context.openReplaceObjectMaskEditor();
  resolveImageLoad();
  await tick();
  assert.equal(h.resizeListeners.length, 1, 'first open should attach exactly one listener');
  const h1 = h.resizeListeners[0];

  // Open #2 happens WITHOUT calling closeReplaceObjectMaskEditor() first -
  // the bug: replaceObjectEditorRuntime used to be replaced wholesale here,
  // silently dropping H1 instead of detaching it.
  h.context.openReplaceObjectMaskEditor();
  resolveImageLoad();
  await tick();

  assert.equal(h.resizeListeners.length, 1, 'reopening must never leave more than one live resize listener');
  assert.notEqual(h.resizeListeners[0], h1, 'the active listener must be the NEW instance\'s handler, not the stale one');
});

test('repeated rapid reopen (5x) never grows the resize-listener count past one', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  for (let i = 0; i < 5; i++) {
    h.context.openReplaceObjectMaskEditor();
    resolveImageLoad();
    await tick();
    assert.equal(h.resizeListeners.length, 1, `listener count must stay at 1 after reopen #${i + 1}`);
  }
});

test('a stale async image-load completion (from an abandoned open) never installs a listener or touches the current instance', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  // Open #1 starts loading but does not finish before open #2 starts.
  h.context.openReplaceObjectMaskEditor();
  assert.equal(FakeImage.pending.length, 1);

  // Open #2 happens before #1's image ever loads.
  h.context.openReplaceObjectMaskEditor();
  assert.equal(FakeImage.pending.length, 2);
  const currentCanvas = h.runtime().canvas;

  // #1's stale load now completes late - it must be ignored entirely.
  resolveImageLoad(); // resolves open #1's image (queued first)
  await tick();
  assert.equal(h.resizeListeners.length, 0, 'a stale completion must not attach a resize listener');
  assert.equal(h.runtime().image, null, 'a stale completion must not touch the current instance\'s image');
  assert.equal(h.runtime().canvas, currentCanvas);

  // #2's own (current) load completes normally and must still work.
  resolveImageLoad();
  await tick();
  assert.equal(h.resizeListeners.length, 1, 'the current instance must still end up with exactly one listener');
  assert.equal(h.runtime().image.naturalWidth, 200);
});

test('a stale load failure (catch) for an abandoned open does not disturb the newer, current instance', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  h.context.openReplaceObjectMaskEditor(); // #1
  h.context.openReplaceObjectMaskEditor(); // #2, abandons #1
  failImageLoad(); // #1 fails late
  await tick();

  assert.equal(h.modal.attributes['aria-busy'], 'true', 'the CURRENT instance must still be marked busy - the stale failure must not clear it');

  resolveImageLoad(); // #2 completes normally
  await tick();
  assert.equal(h.resizeListeners.length, 1);
  assert.equal(h.modal.attributes['aria-busy'], undefined);
});

test('closing the editor normally still detaches its resize listener (no regression)', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  h.context.openReplaceObjectMaskEditor();
  resolveImageLoad();
  await tick();
  assert.equal(h.resizeListeners.length, 1);

  h.context.closeReplaceObjectMaskEditor();
  assert.equal(h.resizeListeners.length, 0);
});

test('the active editor still resizes correctly through its listener after a reopen', async () => {
  const h = makeContext();
  const state = fakeState();
  h.context.ensureReplaceObjectMaskEditor = () => h.modal;
  h.context.photoToolStateFor = () => state;

  h.context.openReplaceObjectMaskEditor();
  resolveImageLoad();
  await tick();

  h.context.openReplaceObjectMaskEditor(); // reopen without closing
  resolveImageLoad();
  await tick();

  h.wrap.style.width = '';
  h.wrap.style.height = '';
  h.resizeListeners[0](); // simulate a real window resize event firing
  assert.notEqual(h.wrap.style.width, '', 'the surviving listener must still resize the canvas wrap');
  assert.notEqual(h.canvas.style.width, '');
});
