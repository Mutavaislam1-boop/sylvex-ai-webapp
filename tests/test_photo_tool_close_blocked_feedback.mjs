// Run with: node --test tests/test_photo_tool_close_blocked_feedback.mjs
//
// Regression tests for remediation item #17 (BUG-2):
//
// closePhotoToolModal() already correctly refused to close the Photo Tool
// modal while a generation was actively in progress
// (photoToolState[activePhotoTool].generating, or hairBeardState/
// tattooState.generatingReference), but did so silently - the close
// button/overlay click simply did nothing, with no feedback telling the
// user why.
//
// Fix: the same blocked-by-active-generation branch now shows a toast
// before returning, reusing both the existing toast() mechanism and the
// exact wording Grid Mode already uses for the same kind of
// "action blocked by an active generation" situation
// ('Сначала дождитесь завершения текущей генерации' - see
// studioGridHasActiveRun() call sites in cabinet.js).
//
// Exercises the REAL extracted function via node:vm (same pattern as
// test_xss1_account_auth_escaping.mjs), not a reimplementation.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractFunction(src, name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(src);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = src.indexOf('{', match.index);
  let depth = 0, i = openIndex;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < src.length, `matching close not found: ${name}`);
  return src.slice(match.index, i + 1);
}

const CLOSE_FN_SRC = extractFunction(source, 'closePhotoToolModal');

const BLOCKED_MESSAGE = 'Сначала дождитесь завершения текущей генерации';

function makeModal() {
  const classes = new Set(['show']);
  return {
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    querySelector: () => null,
    _classes: classes,
  };
}

function makeContext({activePhotoTool = '', photoToolState = {}, hairBeardState = {}, tattooState = {}} = {}) {
  const toastCalls = [];
  const modal = makeModal();
  const context = vm.createContext({
    activePhotoTool,
    photoToolState,
    hairBeardState: {generatingReference: false, ...hairBeardState},
    tattooState: {generatingReference: false, ...tattooState},
    logoState: {},
    replaceObjectState: {},
    photoToolCameFromList: false,
    photoToolListScrollTop: 0,
    photoToolReturnMode: null,
    studioMode: 'image',
    toast: (msg) => toastCalls.push(msg),
    document: {getElementById: (id) => (id === 'photoToolModal' ? modal : null)},
    window: {setTimeout: () => {}},
    activeGenerationLocked: () => false,
    updateComposerMode: () => {},
    renderPhotoToolModal: () => {},
    closeReplaceObjectMaskEditor: () => {},
  });
  vm.runInContext(CLOSE_FN_SRC, context);
  return {context, modal, toastCalls};
}

function fakeEvent() {
  return {preventDefault: () => {}, stopPropagation: () => {}};
}

test('normal close (no active generation) closes the modal without any extra feedback', () => {
  const h = makeContext({
    activePhotoTool: 'logo',
    photoToolState: {logo: {generating: false, files: []}},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false, 'modal must close');
  assert.deepEqual(h.toastCalls, [], 'no toast on a normal close');
});

test('closing with no activePhotoTool at all still works unchanged', () => {
  const h = makeContext({activePhotoTool: ''});
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false);
  assert.deepEqual(h.toastCalls, []);
});

test('close is blocked and shows feedback while a generic photo-tool generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'watermark_removal',
    photoToolState: {watermark_removal: {generating: true}},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), true, 'modal must stay open while generating');
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE]);
});

test('close is blocked and shows feedback while hair_beard reference generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'hair_beard',
    photoToolState: {hair_beard: {generating: false}},
    hairBeardState: {generatingReference: true},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), true);
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE]);
});

test('close is blocked and shows feedback while tattoo reference generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'tattoo',
    photoToolState: {tattoo: {generating: false}},
    tattooState: {generatingReference: true},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), true);
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE]);
});

test('each blocked close attempt shows feedback again (not just the first click)', () => {
  const h = makeContext({
    activePhotoTool: 'replace_object',
    photoToolState: {replace_object: {generating: true}},
  });
  h.context.closePhotoToolModal(fakeEvent());
  h.context.closePhotoToolModal(fakeEvent());
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), true);
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE, BLOCKED_MESSAGE, BLOCKED_MESSAGE]);
});

test('once generation finishes, closing the same tool works normally with no stale feedback', () => {
  const state = {generating: true};
  const h = makeContext({activePhotoTool: 'logo', photoToolState: {logo: state}});
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), true);
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE]);

  state.generating = false; // generation completes
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false, 'must now close normally');
  assert.deepEqual(h.toastCalls, [BLOCKED_MESSAGE], 'no additional toast once it actually closes');
});
