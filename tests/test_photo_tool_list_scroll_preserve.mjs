// Run with: node --test tests/test_photo_tool_list_scroll_preserve.mjs
//
// Regression test for "Pro Studio Mini App - Photo Tools UI Polish",
// item 6: scrolling far down the Tools List, opening a tool, then
// closing/back must restore the list at the exact same scroll position,
// never reset to the top.
//
// openPhotoToolModal() captures the Tools List's scroll position (read
// off the modal's .photo-tool-dialog, the actual overflow:auto scroll
// container - #photoToolModalBody itself never scrolls) right before a
// tool opened from the list replaces its content; closePhotoToolModal()'s
// one-level-back branch (photoToolCameFromList) restores it after
// re-rendering the list.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractFunction(name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(match.index, i + 1);
}

function fakeElement(initial) {
  return Object.assign({
    innerHTML: '', scrollTop: 0,
    classList: {
      set: new Set(),
      add(c) { this.set.add(c); },
      remove(c) { this.set.delete(c); },
      contains(c) { return this.set.has(c); },
      toggle(c, v) { const on = v === undefined ? !this.set.has(c) : !!v; if (on) this.set.add(c); else this.set.delete(c); },
    },
  }, initial || {});
}

function makeContext() {
  const dialog = fakeElement({ scrollTop: 0 });
  const modal = fakeElement({ id: 'photoToolModal', querySelector: (sel) => (sel === '.photo-tool-dialog' ? dialog : null) });
  const dom = { photoToolModal: modal, photoToolModalBody: fakeElement({}) };
  const calls = { renderPhotoToolModal: 0, renderPhotoToolCatalog: 0 };
  const sandbox = {
    activePhotoTool: '',
    photoToolReturnMode: null,
    photoToolCameFromList: false,
    photoToolListScrollTop: 0,
    studioMode: 'image',
    PHOTO_TOOL_CONFIG: { remove_bg: {} },
    photoToolState: { remove_bg: { files: [], generating: false } },
    hairBeardState: { generatingReference: false },
    tattooState: { generatingReference: false },
    switchView: () => {},
    updateComposerMode: () => {},
    loadPhotoToolDemos: () => Promise.resolve(),
    closeReplaceObjectMaskEditor: () => {},
    replaceObjectState: {},
    logoState: {},
    window: { setTimeout, clearTimeout },
    activeGenerationLocked: () => false,
    document: {
      getElementById: (id) => dom[id] || null,
      querySelector: (sel) => (sel === '.view[data-view="tools"].active' ? {} : null),
      body: { appendChild: () => {} },
    },
    // renderPhotoToolModal/renderPhotoToolCatalog are stubbed as spies -
    // this test is only about the scroll capture/restore mechanics around
    // them, not about rendering correctness (covered elsewhere).
    renderPhotoToolModal: () => {
      calls.renderPhotoToolModal += 1;
      if (!sandbox2.activePhotoTool) { calls.renderPhotoToolCatalog += 1; }
    },
  };
  const sandbox2 = sandbox;
  const context = vm.createContext(sandbox);
  for (const name of ['ensurePhotoToolModal', 'openPhotoToolModal', 'closePhotoToolModal']) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, dialog, modal, calls };
}

test('opening a tool from the Tools List captures the list scroll position', () => {
  const { context, sandbox, dialog, modal } = makeContext();
  // The list is already showing, scrolled down.
  modal.classList.add('show');
  dialog.scrollTop = 420;
  vm.runInContext("openPhotoToolModal(null, 'remove_bg')", context);
  assert.equal(sandbox.photoToolCameFromList, true);
  assert.equal(sandbox.photoToolListScrollTop, 420);
});

test('closing back to the Tools List restores the exact captured scroll position, not the top', () => {
  const { context, sandbox, dialog, modal } = makeContext();
  modal.classList.add('show');
  dialog.scrollTop = 420;
  vm.runInContext("openPhotoToolModal(null, 'remove_bg')", context);
  // Simulate the tool's own content being shorter and clamping scrollTop,
  // the way a real browser would when #photoToolModalBody's content
  // shrinks - this is exactly the scenario the fix must survive.
  dialog.scrollTop = 0;
  vm.runInContext('closePhotoToolModal(null)', context);
  assert.equal(sandbox.activePhotoTool, '');
  assert.equal(dialog.scrollTop, 420);
});

test('a tool opened directly (deep link, list never shown) does not capture/restore any scroll position', () => {
  const { context, sandbox, dialog, modal } = makeContext();
  // Modal not shown yet - this is a direct open, not from the list.
  vm.runInContext("openPhotoToolModal(null, 'remove_bg')", context);
  assert.equal(sandbox.photoToolCameFromList, false);
  assert.equal(sandbox.photoToolListScrollTop, 0);
  dialog.scrollTop = 777; // whatever the tool's own view happens to be scrolled to
  vm.runInContext('closePhotoToolModal(null)', context);
  // Full close (not back-to-list) - scrollTop is left alone, never forced to 0.
  assert.equal(dialog.scrollTop, 777);
  assert.equal(modal.classList.contains('show'), false);
});
