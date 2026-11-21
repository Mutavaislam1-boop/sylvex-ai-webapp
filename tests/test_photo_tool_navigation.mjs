// Closing a running tool preserves its state while allowing navigation.
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
    photoToolInPlace: false,
    photoToolInPlaceResult: null,
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

test('close preserves pending state while a generic photo-tool generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'watermark_removal',
    photoToolState: {watermark_removal: {generating: true}},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false, 'modal closes while the server task continues');
  assert.deepEqual(h.toastCalls, []);
});

test('close preserves pending state while hair_beard reference generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'hair_beard',
    photoToolState: {hair_beard: {generating: false}},
    hairBeardState: {generatingReference: true},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false);
  assert.deepEqual(h.toastCalls, []);
});

test('close preserves pending state while tattoo reference generation is active', () => {
  const h = makeContext({
    activePhotoTool: 'tattoo',
    photoToolState: {tattoo: {generating: false}},
    tattooState: {generatingReference: true},
  });
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false);
  assert.deepEqual(h.toastCalls, []);
});

test('repeated close attempts do not cancel a pending task', () => {
  const h = makeContext({
    activePhotoTool: 'replace_object',
    photoToolState: {replace_object: {generating: true}},
  });
  h.context.closePhotoToolModal(fakeEvent());
  h.context.closePhotoToolModal(fakeEvent());
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false);
  assert.deepEqual(h.toastCalls, []);
});

test('closing before and after completion remains available', () => {
  const state = {generating: true};
  const h = makeContext({activePhotoTool: 'logo', photoToolState: {logo: state}});
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false);
  assert.deepEqual(h.toastCalls, []);

  state.generating = false; // generation completes
  h.context.closePhotoToolModal(fakeEvent());
  assert.equal(h.modal.classList.contains('show'), false, 'must now close normally');
  assert.deepEqual(h.toastCalls, [], 'no additional toast once it actually closes');
});
