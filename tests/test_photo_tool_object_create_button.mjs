// Run with: node --test tests/test_photo_tool_object_create_button.mjs
//
// Regression test for a gap found alongside M-029 in the Pro Studio A-Z
// audit: openVisualCreateModal already supports both 'character' and
// 'object' kinds identically (saveVisualCreateDraft is fully generic for
// both, and the main composer's Object picker already calls
// openVisualCreateModal(event, 'object') at cabinet.js:11184), but Photo
// Tools' own createPhotoToolReference() only checked for 'character' -
// clicking "Create" for Object inside a Photo Tool's reference library
// silently fell through to a placeholder toast instead of the real,
// working object-creation modal.
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

function buildContext() {
  const calls = {opened: null, toasted: null};
  const sandbox = {
    openVisualCreateModal: (e, kind) => { calls.opened = kind; },
    toast: (message) => { calls.toasted = message; },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('createPhotoToolReference'), context);
  return {context, calls};
}

test('createPhotoToolReference: character opens the real creation modal', () => {
  const {context, calls} = buildContext();
  vm.runInContext(`createPhotoToolReference(null, 'character')`, context);
  assert.equal(calls.opened, 'character');
  assert.equal(calls.toasted, null);
});

test('createPhotoToolReference: object opens the real creation modal (previously fell through to a placeholder toast)', () => {
  const {context, calls} = buildContext();
  vm.runInContext(`createPhotoToolReference(null, 'object')`, context);
  assert.equal(calls.opened, 'object');
  assert.equal(calls.toasted, null);
});

test('createPhotoToolReference: tools with no real creation flow (e.g. makeup) still show the placeholder toast, not an error', () => {
  const {context, calls} = buildContext();
  vm.runInContext(`createPhotoToolReference(null, 'makeup')`, context);
  assert.equal(calls.opened, null);
  assert.equal(calls.toasted, 'Слот для нового референса подготовлен');
});
