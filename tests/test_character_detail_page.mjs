// Run with: node --test tests/test_character_detail_page.mjs
//
// Regression tests for the Character reference-selection UX fix: clicking
// a Character in the picker (Image mode) must open that Character's own
// page inside the same picker - never select-and-close immediately, and
// never route through a separate small "..." button/modal (that button
// and its modal were removed; see test_character_reference_library_frontend.mjs
// for the reference-selection helpers this page reuses unchanged).
//
// Exercises the real cabinet.js functions directly via node:vm extraction
// (same pattern as test_character_reference_library_frontend.mjs).
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

function fakeElement() {
  return {
    hidden: true,
    innerHTML: '',
    classList: {
      list: new Set(),
      add(c) { this.list.add(c); },
      remove(c) { this.list.delete(c); },
      contains(c) { return this.list.has(c); },
    },
  };
}

function baseImageState(extra) {
  return Object.assign({
    modelId: 'seedream_5_0_pro',
    characterId: null,
    characterName: '',
    characterReferences: [],
    characterReferenceLibrary: [],
    characterReferenceIds: [],
  }, extra || {});
}

function makeContext(imageState, opts) {
  const options = opts || {};
  const toasts = [];
  const dom = { visualCharacterDetail: fakeElement(), imageStylePanel: fakeElement() };
  const panel = fakeElement();
  const sandbox = {
    imageState,
    activeCharacterDetailId: '',
    characterDetailView: 'references',
    characterDetailHistoryCache: {},
    getModelCapabilities: options.getModelCapabilities || (() => ({ maxReferences: null })),
    toast: (msg) => toasts.push(msg),
    sendVisualInteraction: () => {},
    renderImageReferenceSections: () => {},
    updateSendButton: () => {},
    renderCharacterDetail: options.renderCharacterDetail || (() => {}),
    loadVisualStats: () => Promise.resolve(),
    hideImageStyleInfo: () => {},
    ensureImageStylePanel: () => panel,
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    document: { getElementById: (id) => dom[id] || null },
    getTelegramId: () => 42,
    window: {},
    imageCharacters: options.imageCharacters || (() => []),
    normalizeVisualItem: (item) => item,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterReferenceCap'), context);
  vm.runInContext(extractFunction('characterReferenceLibraryFor'), context);
  vm.runInContext(extractFunction('defaultCharacterReferenceIds'), context);
  vm.runInContext(extractFunction('syncCharacterReferencesFromIds'), context);
  vm.runInContext(extractFunction('applyCharacterReferenceSelection'), context);
  vm.runInContext(extractFunction('toggleCharacterReferenceId'), context);
  vm.runInContext(extractFunction('clearSelectedCharacter'), context);
  vm.runInContext(extractFunction('openCharacterDetail'), context);
  vm.runInContext(extractFunction('closeCharacterDetail'), context);
  vm.runInContext(extractFunction('closeImageStylePanel'), context);
  vm.runInContext(extractFunction('confirmCharacterDetailSelection'), context);
  vm.runInContext(extractFunction('removeCharacterDetailSelection'), context);
  vm.runInContext(extractFunction('setCharacterDetailView'), context);
  vm.runInContext(extractFunction('characterDetailReferenceGridHtml'), context);
  return { context, toasts, dom, panel };
}

function fakeEvent() {
  return { preventDefault: () => {}, stopPropagation: () => {} };
}

test('openCharacterDetail: selecting a new Character applies default references and opens the page (no small button, no separate modal)', () => {
  const imageState = baseImageState();
  const item = {
    id: 'custom_character_abc',
    name: 'Islam',
    referenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Additional' },
    ],
  };
  const { context, dom, panel } = makeContext(imageState, { imageCharacters: () => [item] });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, 'custom_character_abc');
  assert.deepEqual(imageState.characterReferenceIds, ['ref1', 'ref2']);
  assert.equal(vm.runInContext('activeCharacterDetailId', context), 'custom_character_abc');
  assert.equal(dom.visualCharacterDetail.hidden, false);
  assert.ok(panel.classList.contains('has-character-detail'));
});

test('openCharacterDetail: reopening the already-selected Character does not reset a manually-edited selection', () => {
  const imageState = baseImageState({
    characterId: 'custom_character_abc',
    characterReferenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Additional' },
    ],
    characterReferenceIds: ['ref2'],
  });
  const item = {
    id: 'custom_character_abc',
    name: 'Islam',
    referenceLibrary: imageState.characterReferenceLibrary,
  };
  const { context } = makeContext(imageState, { imageCharacters: () => [item] });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  // Still only ref2 - opening the page again must not silently re-apply the defaults.
  assert.deepEqual(imageState.characterReferenceIds, ['ref2']);
});

test('confirmCharacterDetailSelection: closes the Character page and the picker, selection already committed', () => {
  const imageState = baseImageState({ characterId: 'custom_character_abc' });
  const { context, dom, panel, toasts } = makeContext(imageState);
  vm.runInContext('activeCharacterDetailId = "custom_character_abc"', context);
  dom.visualCharacterDetail.hidden = false;
  panel.classList.add('has-character-detail');
  dom.imageStylePanel.classList.add('show');

  vm.runInContext('confirmCharacterDetailSelection(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(vm.runInContext('activeCharacterDetailId', context), '');
  assert.equal(dom.visualCharacterDetail.hidden, true);
  assert.ok(!dom.imageStylePanel.classList.contains('show'));
  assert.ok(toasts.some((msg) => /выбран/.test(msg)));
  // Character stays selected - confirm never undoes the selection.
  assert.equal(imageState.characterId, 'custom_character_abc');
});

test('removeCharacterDetailSelection: clears the Character and closes the page/picker', () => {
  const imageState = baseImageState({
    characterId: 'custom_character_abc',
    characterName: 'Islam',
    characterReferences: ['https://cdn.sylvex.ai/a.png'],
    characterReferenceLibrary: [{ id: 'ref1', url: 'https://cdn.sylvex.ai/a.png' }],
    characterReferenceIds: ['ref1'],
  });
  const { context, dom, toasts } = makeContext(imageState);
  vm.runInContext('activeCharacterDetailId = "custom_character_abc"', context);
  dom.imageStylePanel.classList.add('show');

  vm.runInContext('removeCharacterDetailSelection(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, null);
  assert.equal(imageState.characterReferenceIds.length, 0);
  assert.ok(!dom.imageStylePanel.classList.contains('show'));
  assert.ok(toasts.some((msg) => /удал/.test(msg)));
});

test('setCharacterDetailView: switches between the references and history tabs', () => {
  const { context } = makeContext(baseImageState(), { renderCharacterDetail: () => {} });
  vm.runInContext('setCharacterDetailView(e, "history")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailView', context), 'history');
  vm.runInContext('setCharacterDetailView(e, "references")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailView', context), 'references');
});

test('characterDetailReferenceGridHtml: highlights only the currently selected references and wires toggleCharacterReferenceId', () => {
  const imageState = baseImageState({
    characterReferenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Additional' },
    ],
    characterReferenceIds: ['ref1'],
  });
  const { context } = makeContext(imageState);
  const item = { id: 'custom_character_abc' };
  const html = vm.runInContext('characterDetailReferenceGridHtml(item)', Object.assign(context, { item }));

  // ref1 card is selected, ref2 is not.
  const ref1Card = html.slice(html.indexOf('ref1') - 400, html.indexOf('ref1'));
  assert.match(html, /image-style-card selected[^>]*onclick="SYLVEX\.toggleCharacterReferenceId\('ref1'\)"/);
  assert.doesNotMatch(html, /image-style-card selected[^>]*onclick="SYLVEX\.toggleCharacterReferenceId\('ref2'\)"/);
  assert.match(html, /onclick="SYLVEX\.toggleCharacterReferenceId\('ref2'\)"/);
});

test('characterDetailReferenceGridHtml: shows an empty state when the Character has no references', () => {
  const { context } = makeContext(baseImageState());
  const item = { id: 'custom_character_abc', referenceLibrary: [] };
  const html = vm.runInContext('characterDetailReferenceGridHtml(item)', Object.assign(context, { item }));
  assert.match(html, /character-detail-empty/);
});
