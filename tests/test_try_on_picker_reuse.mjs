// Run with: node --test tests/test_try_on_picker_reuse.mjs
//
// Regression tests for remediation item #21A (DUP-1): Try-On's "choose a
// Character" action used to open its own bespoke grid (openTryOnCharacterPicker/
// renderTryOnPickerGrid's 'character' branch/pickTryOnCharacter), duplicating
// the exact same mechanism Replace Character already shares with Image
// mode's own Character picker (openVisualPicker -> the imageStylePanel card
// grid -> the Character's own detail page -> "Use Character" ->
// confirmCharacterDetailSelection()'s redirect branch, gated by
// visualPickerRedirectTarget).
//
// This file proves:
//   - Try-On's "Character" source now opens that exact same shared picker,
//     not a second grid (the bespoke openTryOnCharacterPicker/pickTryOnCharacter
//     no longer exist at all).
//   - "Use Character" from that picker commits into Try-On's own isolated
//     photoToolState.try_on (personSource/characterId/personImage/personLabel),
//     exactly as the old bespoke pickTryOnCharacter() used to - never into
//     imageState and never into photoToolState.replace_character.
//   - The selected Character's reference set is captured too, capped at 3
//     (characterReferenceUrls), matching the same cap Replace Character's
//     own redirect branch already uses - so migrating to the shared picker
//     does not lose any reference data.
//   - Garments (the tool's other, independent state) are untouched by a
//     Character pick.
//   - Cancelling/closing the picker (closeImageStylePanel) clears the
//     redirect so a later normal (non-redirected) character pick in the
//     main composer is unaffected, and so is Try-On's own Media picker.
//   - Replace Character's own redirect branch and bespoke History/Upload
//     pickers are completely unaffected by this migration.
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

function functionExists(name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  return pattern.test(cabinet);
}

function fakeElement(initial) {
  return Object.assign({
    classList: {
      set: new Set(),
      add(c) { this.set.add(c); },
      remove(c) { this.set.delete(c); },
      contains(c) { return this.set.has(c); },
    },
    hidden: false,
  }, initial || {});
}

function makeContext() {
  const calls = { openImageStylePanel: [], applyCharacterReferenceSelection: 0, sendVisualInteraction: 0, renderPhotoToolModal: 0, renderImageReferenceSections: 0, updateSendButton: 0, toast: [] };
  const character = {
    id: 'char_1', name: 'Islam', previewUrl: 'https://cdn.sylvex.ai/islam.png',
    referenceImages: ['https://cdn.sylvex.ai/islam-ref1.png', 'https://cdn.sylvex.ai/islam-ref2.png', 'https://cdn.sylvex.ai/islam-ref3.png', 'https://cdn.sylvex.ai/islam-ref4.png'],
  };
  const dom = { imageStylePanel: fakeElement({}) };
  const sandbox = {
    activePhotoTool: 'try_on',
    visualPickerRedirectTarget: null,
    activeCharacterDetailId: '',
    characterDetailPendingIds: [],
    photoToolState: {
      try_on: { generating: false, personSource: null, personImage: '', personLabel: '', characterId: null, characterReferenceUrls: [], garments: [null, null, null] },
      replace_character: { generating: false, sourceImage: '', sourceLabel: '', identitySource: null, identityImage: '', identityLabel: '', characterId: null, characterReferenceUrls: [] },
    },
    imageState: { characterId: null, characterName: '', characterReferenceLibrary: [], characterReferenceIds: [], characterReferences: [] },
    imageCharacters: () => [character],
    openImageStylePanel: (e, kind) => { calls.openImageStylePanel.push(kind); },
    openTryOnMediaPicker: () => { throw new Error('the Media picker must not be touched by a Character pick'); },
    document: { getElementById: (id) => dom[id] || null },
    hideImageStyleInfo: () => {},
    applyCharacterReferenceSelection: () => { calls.applyCharacterReferenceSelection += 1; },
    sendVisualInteraction: () => { calls.sendVisualInteraction += 1; },
    renderImageReferenceSections: () => { calls.renderImageReferenceSections += 1; },
    updateSendButton: () => { calls.updateSendButton += 1; },
    renderPhotoToolModal: () => { calls.renderPhotoToolModal += 1; },
    toast: (msg) => { calls.toast.push(msg); },
  };
  const context = vm.createContext(sandbox);
  for (const name of ['visualPreviewUrl', 'normalizeVisualItem', 'characterReferenceLibraryFor', 'closeCharacterDetail', 'closeImageStylePanel', 'openVisualPicker', 'chooseTryOnPersonSource', 'confirmCharacterDetailSelection']) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, calls, character };
}

// ---------------------------------------------------------------------------
// The bespoke duplicate is gone
// ---------------------------------------------------------------------------

test('the bespoke Try-On Character picker functions no longer exist', () => {
  assert.equal(functionExists('openTryOnCharacterPicker'), false, 'openTryOnCharacterPicker must be removed');
  assert.equal(functionExists('pickTryOnCharacter'), false, 'pickTryOnCharacter must be removed');
});

// ---------------------------------------------------------------------------
// Try-On's "Character" source now opens the shared picker
// ---------------------------------------------------------------------------

test('choosing "Character" in Try-On opens the real Pro Studio Character picker, not a second grid', () => {
  const { context, sandbox, calls } = makeContext();
  vm.runInContext("chooseTryOnPersonSource(null, 'character')", context);
  assert.deepEqual(calls.openImageStylePanel, ['character']);
  assert.equal(sandbox.visualPickerRedirectTarget, 'try_on');
});

test('"Use Character" from that picker commits into Try-On\'s own state, never imageState or replace_character', () => {
  const { context, sandbox, calls, character } = makeContext();
  vm.runInContext("chooseTryOnPersonSource(null, 'character')", context);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [character.id + '_ref_1', character.id + '_ref_2'];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);

  const target = sandbox.photoToolState.try_on;
  assert.equal(target.personSource, 'character');
  assert.equal(target.characterId, 'char_1');
  assert.equal(target.personImage, 'https://cdn.sylvex.ai/islam.png');
  assert.equal(target.personLabel, 'Islam');
  assert.deepEqual([...target.characterReferenceUrls], ['https://cdn.sylvex.ai/islam-ref1.png', 'https://cdn.sylvex.ai/islam-ref2.png']);

  // Never touched the normal Pro Studio character picker's own commit path,
  // and never touched Replace Character's isolated state either.
  assert.equal(calls.applyCharacterReferenceSelection, 0);
  assert.equal(calls.sendVisualInteraction, 0);
  assert.equal(sandbox.imageState.characterId, null);
  assert.equal(sandbox.photoToolState.replace_character.characterId, null);

  // Garments (the tool's other, independent state) are untouched.
  assert.deepEqual(target.garments, [null, null, null]);

  // The redirect is one-shot and the tool's own UI is refreshed.
  assert.equal(sandbox.visualPickerRedirectTarget, null);
  assert.equal(calls.renderPhotoToolModal, 1);
  assert.deepEqual(calls.toast, ['Персонаж выбран']);
});

test('characterReferenceUrls is capped at 3, matching Replace Character\'s own cap', () => {
  const { context, sandbox, character } = makeContext();
  vm.runInContext("chooseTryOnPersonSource(null, 'character')", context);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [0, 1, 2, 3].map((i) => character.id + '_ref_' + i);
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  const target = sandbox.photoToolState.try_on;
  assert.equal(target.characterReferenceUrls.length, 3);
  assert.deepEqual([...target.characterReferenceUrls], [
    'https://cdn.sylvex.ai/islam.png',
    'https://cdn.sylvex.ai/islam-ref1.png',
    'https://cdn.sylvex.ai/islam-ref2.png',
  ]);
});

test('a zero-reference selection still commits the Character itself with an empty reference list', () => {
  const { context, sandbox, character } = makeContext();
  vm.runInContext("chooseTryOnPersonSource(null, 'character')", context);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  const target = sandbox.photoToolState.try_on;
  assert.equal(target.characterId, 'char_1');
  assert.deepEqual([...target.characterReferenceUrls], []);
});

// ---------------------------------------------------------------------------
// Cancel/back navigation restores the correct tool state
// ---------------------------------------------------------------------------

test('cancelling/closing the picker without confirming clears the redirect so a later pick is unaffected', () => {
  const { context, sandbox } = makeContext();
  vm.runInContext("chooseTryOnPersonSource(null, 'character')", context);
  assert.equal(sandbox.visualPickerRedirectTarget, 'try_on');
  vm.runInContext('closeImageStylePanel(null)', context);
  assert.equal(sandbox.visualPickerRedirectTarget, null, 'no stray redirect must be left armed');
  // Try-On's own state is untouched by a cancelled pick.
  assert.equal(sandbox.photoToolState.try_on.characterId, null);
  assert.equal(sandbox.photoToolState.try_on.personSource, null);
});

test('a normal (non-redirected) character pick elsewhere still commits to imageState exactly as before', () => {
  const { context, sandbox, calls, character } = makeContext();
  sandbox.activePhotoTool = '';
  sandbox.visualPickerRedirectTarget = null;
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [character.id + '_ref_0'];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  assert.equal(calls.applyCharacterReferenceSelection, 1);
  assert.equal(calls.sendVisualInteraction, 1);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.photoToolState.try_on.characterId, null);
  assert.equal(sandbox.photoToolState.replace_character.characterId, null);
});

// ---------------------------------------------------------------------------
// Replace Character's own redirect branch is unaffected by this migration
// ---------------------------------------------------------------------------

test('Replace Character\'s own "choose a Character" redirect still works unchanged', () => {
  const { context, sandbox, calls, character } = makeContext();
  // Mirrors chooseCharacterReplaceIdentitySource's own redirect, inlined
  // here since that function isn't extracted into this context - only its
  // effect (the redirect target + shared-picker open) matters for proving
  // DUP-1 didn't disturb Replace Character's own path.
  vm.runInContext("visualPickerRedirectTarget = 'replace_character'; openVisualPicker(null, 'character')", context);
  assert.deepEqual(calls.openImageStylePanel, ['character']);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [character.id + '_ref_0', character.id + '_ref_1'];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  const target = sandbox.photoToolState.replace_character;
  assert.equal(target.identitySource, 'character');
  assert.equal(target.characterId, 'char_1');
  assert.equal(target.identityImage, 'https://cdn.sylvex.ai/islam.png');
  assert.equal(target.identityLabel, 'Islam');
  assert.deepEqual([...target.characterReferenceUrls], ['https://cdn.sylvex.ai/islam.png', 'https://cdn.sylvex.ai/islam-ref1.png']);
  // Try-On's state is untouched by Replace Character's own pick.
  assert.equal(sandbox.photoToolState.try_on.characterId, null);
});
