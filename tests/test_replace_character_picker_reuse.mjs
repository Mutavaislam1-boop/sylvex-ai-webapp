// Run with: node --test tests/test_replace_character_picker_reuse.mjs
//
// Regression test for "Pro Studio Mini App - Photo Tools UI Polish",
// item 8: Replace Character's "choose a Character" action must open the
// exact same Pro Studio Character picker (openVisualPicker -> the
// imageStylePanel card grid -> the Character's own detail page -> "Use
// Character") that Image mode uses - not a second, bespoke grid - while
// still never writing the pick into imageState (Replace Character's own
// isolated photoToolState.replace_character instead).
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
    activePhotoTool: 'replace_character',
    visualPickerRedirectTarget: null,
    activeCharacterDetailId: '',
    characterDetailPendingIds: [],
    photoToolState: { replace_character: { generating: false, sourceImage: '', sourceLabel: '', identitySource: null, identityImage: '', identityLabel: '', characterId: null, characterReferenceUrls: [] } },
    imageState: { characterId: null, characterName: '', characterReferenceLibrary: [], characterReferenceIds: [], characterReferences: [] },
    imageCharacters: () => [character],
    openImageStylePanel: (e, kind) => { calls.openImageStylePanel.push(kind); },
    openCharacterReplacePicker: () => { throw new Error('the bespoke picker must not be used for the character source'); },
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
  for (const name of ['visualPreviewUrl', 'normalizeVisualItem', 'characterReferenceLibraryFor', 'closeCharacterDetail', 'closeImageStylePanel', 'openVisualPicker', 'chooseCharacterReplaceIdentitySource', 'confirmCharacterDetailSelection']) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, calls, character };
}

test('choosing "Character" in Replace Character opens the real Pro Studio Character picker, not a second grid', () => {
  const { context, sandbox, calls } = makeContext();
  vm.runInContext("chooseCharacterReplaceIdentitySource(null, 'character')", context);
  assert.deepEqual(calls.openImageStylePanel, ['character']);
  assert.equal(sandbox.visualPickerRedirectTarget, 'replace_character');
});

test('"Use Character" from that picker commits into Replace Character\'s own state, never imageState', () => {
  const { context, sandbox, calls, character } = makeContext();
  vm.runInContext("chooseCharacterReplaceIdentitySource(null, 'character')", context);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [character.id + '_ref_1', character.id + '_ref_2'];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  const target = sandbox.photoToolState.replace_character;
  assert.equal(target.identitySource, 'character');
  assert.equal(target.characterId, 'char_1');
  assert.equal(target.identityImage, 'https://cdn.sylvex.ai/islam.png');
  assert.equal(target.identityLabel, 'Islam');
  assert.deepEqual([...target.characterReferenceUrls], ['https://cdn.sylvex.ai/islam-ref1.png', 'https://cdn.sylvex.ai/islam-ref2.png']);
  // Never touched the normal Pro Studio character picker's own commit path.
  assert.equal(calls.applyCharacterReferenceSelection, 0);
  assert.equal(calls.sendVisualInteraction, 0);
  assert.equal(sandbox.imageState.characterId, null);
  // The redirect is one-shot and the tool's own UI is refreshed.
  assert.equal(sandbox.visualPickerRedirectTarget, null);
  assert.equal(calls.renderPhotoToolModal, 1);
});

test('characterReferenceUrls is capped at 3, matching the previous bespoke picker\'s own cap', () => {
  const { context, sandbox, character } = makeContext();
  vm.runInContext("chooseCharacterReplaceIdentitySource(null, 'character')", context);
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [0, 1, 2, 3].map((i) => character.id + '_ref_' + i);
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  assert.equal(sandbox.photoToolState.replace_character.characterReferenceUrls.length, 3);
});

test('a normal (non-redirected) character pick still commits to imageState exactly as before', () => {
  const { context, sandbox, calls, character } = makeContext();
  sandbox.activePhotoTool = '';
  sandbox.visualPickerRedirectTarget = null;
  sandbox.activeCharacterDetailId = character.id;
  sandbox.characterDetailPendingIds = [character.id + '_ref_0'];
  vm.runInContext('confirmCharacterDetailSelection(null)', context);
  assert.equal(calls.applyCharacterReferenceSelection, 1);
  assert.equal(calls.sendVisualInteraction, 1);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.photoToolState.replace_character.characterId, null);
});

test('cancelling/closing the picker without confirming clears the redirect so a later normal pick is unaffected', () => {
  const { context, sandbox } = makeContext();
  vm.runInContext("chooseCharacterReplaceIdentitySource(null, 'character')", context);
  assert.equal(sandbox.visualPickerRedirectTarget, 'replace_character');
  vm.runInContext('closeImageStylePanel(null)', context);
  assert.equal(sandbox.visualPickerRedirectTarget, null);
});
