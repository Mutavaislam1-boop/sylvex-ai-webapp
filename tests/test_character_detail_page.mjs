// Run with: node --test tests/test_character_detail_page.mjs
//
// Regression tests for the Character Card Cleanup / Selection Flow fix:
//
//   Character list -> open Character page -> choose references ->
//   "Use Character" -> only then commit Character + selected references.
//
// Opening a Character page is now purely staging (characterDetailPendingIds),
// never a commit. Back/close/Cancel discard the staged state and leave
// whatever Character was already active untouched. Only
// confirmCharacterDetailSelection ("Use Character") writes to imageState,
// and it never falls back to "every reference" when nothing is checked.
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
    characterDetailPendingIds: [],
    characterDetailHistoryCache: {},
    getModelCapabilities: options.getModelCapabilities || (() => ({ maxReferences: null })),
    toast: (msg) => toasts.push(msg),
    sendVisualInteraction: () => {},
    renderImageReferenceSections: () => {},
    updateSendButton: () => {},
    hideImageStyleInfo: () => {},
    ensureImageStylePanel: () => panel,
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    document: { getElementById: (id) => dom[id] || null },
    getTelegramId: () => 42,
    window: {},
    imageCharacters: options.imageCharacters || (() => []),
    normalizeVisualItem: (item) => item,
    visualPreviewUrl: (item) => (item && (item.previewUrl || item.avatarUrl)) || '',
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterReferenceCap'), context);
  vm.runInContext(extractFunction('characterReferenceLibraryFor'), context);
  vm.runInContext(extractFunction('defaultCharacterReferenceIds'), context);
  vm.runInContext(extractFunction('syncCharacterReferencesFromIds'), context);
  vm.runInContext(extractFunction('applyCharacterReferenceSelection'), context);
  vm.runInContext(extractFunction('clearSelectedCharacter'), context);
  vm.runInContext(extractFunction('isCustomVisualItem'), context);
  vm.runInContext(extractFunction('toggleCharacterDetailReferenceId'), context);
  vm.runInContext(extractFunction('toggleCharacterDetailSelectAll'), context);
  vm.runInContext(extractFunction('characterDetailReferenceGridHtml'), context);
  vm.runInContext(extractFunction('setCharacterDetailView'), context);
  vm.runInContext('function renderCharacterDetail(){}', context);
  vm.runInContext('function characterDetailHistoryHtml(){ return ""; }', context);
  vm.runInContext(extractFunction('visualCharacterDetailHtml'), context);
  vm.runInContext(extractFunction('openCharacterDetail'), context);
  vm.runInContext(extractFunction('closeCharacterDetail'), context);
  vm.runInContext(extractFunction('cancelCharacterDetail'), context);
  vm.runInContext('function closeImageStylePanel(){ const p = document.getElementById("imageStylePanel"); if (p) p.classList.remove("show"); }', context);
  vm.runInContext(extractFunction('confirmCharacterDetailSelection'), context);
  return { context, toasts, dom, panel };
}

function fakeEvent() {
  return { preventDefault: () => {}, stopPropagation: () => {} };
}

const library4 = [
  { id: 'ref_face', url: 'https://cdn.sylvex.ai/face.png', role: 'Primary Face' },
  { id: 'ref_body1', url: 'https://cdn.sylvex.ai/body1.png', role: 'Additional' },
  { id: 'ref_body2', url: 'https://cdn.sylvex.ai/body2.png', role: 'Additional' },
  { id: 'ref_body3', url: 'https://cdn.sylvex.ai/body3.png', role: 'Additional' },
];

test('openCharacterDetail: opening a Character never commits it - imageState is untouched', () => {
  const imageState = baseImageState();
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context, dom, panel } = makeContext(imageState, { imageCharacters: () => [item] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, null, 'opening must not set characterId');
  assert.equal(imageState.characterReferenceIds.length, 0);
  assert.equal(vm.runInContext('activeCharacterDetailId', context), 'custom_character_abc');
  assert.equal(dom.visualCharacterDetail.hidden, false);
  assert.ok(panel.classList.contains('has-character-detail'));
});

test('openCharacterDetail: initial reference selection is empty - no preselection', () => {
  const imageState = baseImageState();
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [item] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 0);
  const html = vm.runInContext('characterDetailReferenceGridHtml(item)', Object.assign(context, { item }));
  assert.doesNotMatch(html, /image-style-card selected/);
});

test('toggleCharacterDetailReferenceId: individual selection toggles on and off, capped by the model', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context, toasts } = makeContext(imageState, {
    imageCharacters: () => [item],
    getModelCapabilities: () => ({ maxReferences: 1 }),
  });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_face")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 1);
  assert.equal(vm.runInContext('characterDetailPendingIds[0]', context), 'ref_face');

  // Model caps at 1 - a second selection is refused, not silently capped-and-swapped.
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_body1")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 1);
  assert.ok(toasts.some((msg) => /1 референс/.test(msg)));

  // Deselect.
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_face")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 0);

  // imageState is still untouched - nothing is committed until confirm.
  assert.equal(imageState.characterId, null);
});

test('toggleCharacterDetailSelectAll: selects every reference up to the model cap, then deselects all', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, {
    imageCharacters: () => [item],
    getModelCapabilities: () => ({ maxReferences: 3 }),
  });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  vm.runInContext('toggleCharacterDetailSelectAll(e)', Object.assign(context, { e: fakeEvent() }));
  // Library has 4, model caps at 3 - "select all" respects the cap.
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 3);

  vm.runInContext('toggleCharacterDetailSelectAll(e)', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 0);
});

test('Cancel discards the staged selection and leaves the previously active Character untouched', () => {
  const imageState = baseImageState({
    characterId: 'already_active',
    characterName: 'Previous',
    characterReferenceLibrary: [{ id: 'old_ref', url: 'https://cdn.sylvex.ai/old.png' }],
    characterReferenceIds: ['old_ref'],
    characterReferences: ['https://cdn.sylvex.ai/old.png'],
  });
  const otherItem = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [otherItem] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_face")', Object.assign(context, { e: fakeEvent() }));
  assert.equal(vm.runInContext('characterDetailPendingIds.length', context), 1);

  vm.runInContext('cancelCharacterDetail(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, 'already_active');
  assert.equal(imageState.characterReferenceIds.length, 1);
  assert.equal(imageState.characterReferenceIds[0], 'old_ref');
  assert.equal(vm.runInContext('activeCharacterDetailId', context), '');
});

test('Back (closeCharacterDetail) has the same discard semantics as Cancel', () => {
  const imageState = baseImageState({ characterId: 'already_active', characterReferenceIds: ['old_ref'] });
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [item] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_body2")', Object.assign(context, { e: fakeEvent() }));
  vm.runInContext('closeCharacterDetail(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, 'already_active');
  assert.equal(imageState.characterReferenceIds.length, 1);
  assert.equal(imageState.characterReferenceIds[0], 'old_ref');
});

test('"Use Character" commits exactly the selected references - a partial selection', () => {
  const imageState = baseImageState();
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context, dom, panel, toasts } = makeContext(imageState, { imageCharacters: () => [item] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_face")', Object.assign(context, { e: fakeEvent() }));
  dom.imageStylePanel.classList.add('show');

  vm.runInContext('confirmCharacterDetailSelection(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, 'custom_character_abc');
  assert.equal(imageState.characterReferenceIds.length, 1);
  assert.equal(imageState.characterReferenceIds[0], 'ref_face');
  assert.equal(imageState.characterReferences.length, 1);
  assert.equal(imageState.characterReferences[0], 'https://cdn.sylvex.ai/face.png');
  assert.equal(vm.runInContext('activeCharacterDetailId', context), '');
  assert.equal(dom.visualCharacterDetail.hidden, true);
  assert.ok(!dom.imageStylePanel.classList.contains('show'));
  assert.ok(toasts.some((msg) => /выбран/.test(msg)));
});

test('"Use Character" with nothing selected commits zero references - never falls back to all', () => {
  const imageState = baseImageState();
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [item] });

  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));
  // No toggles at all - nothing checked.
  vm.runInContext('confirmCharacterDetailSelection(e)', Object.assign(context, { e: fakeEvent() }));

  assert.equal(imageState.characterId, 'custom_character_abc');
  assert.equal(imageState.characterReferenceIds.length, 0);
  assert.equal(imageState.characterReferences.length, 0);
});

test('characterDetailReferenceGridHtml: only the pending-selected card is highlighted', () => {
  const imageState = baseImageState();
  const item = { id: 'custom_character_abc', name: 'Islam', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [item] });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));
  vm.runInContext('toggleCharacterDetailReferenceId(e, "ref_body1")', Object.assign(context, { e: fakeEvent() }));

  const html = vm.runInContext('characterDetailReferenceGridHtml(item)', Object.assign(context, { item }));
  assert.match(html, /image-style-card selected[^>]*onclick="SYLVEX\.toggleCharacterDetailReferenceId\(event,'ref_body1'\)"/);
  assert.doesNotMatch(html, /image-style-card selected[^>]*onclick="SYLVEX\.toggleCharacterDetailReferenceId\(event,'ref_face'\)"/);
});

test('built-in/preset Characters never show the Generation History tab; user-created Characters do', () => {
  const builtIn = { id: 'character_sylvex', name: 'SYLVEX', avatarUrl: 'https://cdn.sylvex.ai/sylvex.png', referenceImages: [] };
  const custom = { id: 'custom_character_abc', name: 'Islam', type: 'custom', referenceLibrary: library4 };
  assert.equal(vm.runInContext('isCustomVisualItem(builtIn)', Object.assign(makeContext(baseImageState()).context, { builtIn })), false);
  assert.equal(vm.runInContext('isCustomVisualItem(custom)', Object.assign(makeContext(baseImageState()).context, { custom })), true);
});

test('visualCharacterDetailHtml: a built-in/preset Character renders with no History tab and no "История" text at all', () => {
  const imageState = baseImageState();
  const builtIn = { id: 'character_sylvex', name: 'SYLVEX', avatarUrl: 'https://cdn.sylvex.ai/sylvex.png', referenceImages: [] };
  const { context } = makeContext(imageState, { imageCharacters: () => [builtIn] });
  vm.runInContext('openCharacterDetail(e, "character_sylvex")', Object.assign(context, { e: fakeEvent() }));

  const html = vm.runInContext('visualCharacterDetailHtml(item)', Object.assign(context, { item: builtIn }));
  assert.doesNotMatch(html, /character-detail-tabs/);
  assert.doesNotMatch(html, /История/);
});

test('visualCharacterDetailHtml: a user-created Character renders with the History tab available', () => {
  const imageState = baseImageState();
  const custom = { id: 'custom_character_abc', name: 'Islam', type: 'custom', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [custom] });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  const html = vm.runInContext('visualCharacterDetailHtml(item)', Object.assign(context, { item: custom }));
  assert.match(html, /character-detail-tabs/);
  assert.match(html, /История/);
});

test('visualCharacterDetailHtml: no like/favorite UI and no description text remain on the page', () => {
  const imageState = baseImageState();
  const custom = { id: 'custom_character_abc', name: 'Islam', type: 'custom', description: 'A tall hero with blue eyes.', referenceLibrary: library4 };
  const { context } = makeContext(imageState, { imageCharacters: () => [custom] });
  vm.runInContext('openCharacterDetail(e, "custom_character_abc")', Object.assign(context, { e: fakeEvent() }));

  const html = vm.runInContext('visualCharacterDetailHtml(item)', Object.assign(context, { item: custom }));
  assert.doesNotMatch(html, /sendVisualInteraction\('character','[^']*','like'/);
  assert.doesNotMatch(html, /sendVisualInteraction\('character','[^']*','favorite'/);
  assert.doesNotMatch(html, /visual-character-like-count/);
  assert.doesNotMatch(html, /A tall hero with blue eyes\./);
  assert.match(html, /Отмена/);
  assert.doesNotMatch(html, /Убрать/);
});

test('reference and history grid thumbnails use object-fit: contain, never cover - full-body references must render whole, not cropped', () => {
  const cssMatch = cabinet.match(/\.character-detail-reference-grid \.image-style-thumb img,\s*\n\s*\.character-detail-history-grid \.image-style-thumb img\s*\{[^}]*object-fit:\s*contain/);
  assert.ok(cssMatch, 'expected a contain-mode rule scoped to the Character page reference/history grids');
});

test('cap-respecting default/select-all stays correct for a Character with more references than the model allows (regression context for the grid)', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const { context } = makeContext(imageState, { getModelCapabilities: () => ({ maxReferences: 2 }) });
  const ids = vm.runInContext('defaultCharacterReferenceIds(library, characterReferenceCap(imageState.modelId))', Object.assign(context, { library: library4 }));
  assert.equal(ids.length, 2);
});
