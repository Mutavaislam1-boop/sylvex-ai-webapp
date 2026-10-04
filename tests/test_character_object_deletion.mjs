// Run with: node --test tests/test_character_object_deletion.mjs
//
// Regression tests for Character/Object deletion ("Fix 1"): deleting a
// user-created Character or Object must
//   - confirm the backend DELETE succeeds before touching any local state
//     (a network/backend failure must leave the item exactly as it was,
//     never removed from the UI while still present server-side - which
//     is what used to make it silently reappear after a reload);
//   - remove it from serverVisualItems and the localStorage-backed custom
//     list immediately on success;
//   - clear it from the currently selected Character/Object state if it
//     was active;
//   - never be reachable for a built-in/preset item (isCustomVisualItem
//     gates every delete entry point).
//
// Exercises the real cabinet.js functions directly via node:vm extraction
// (same pattern as test_character_detail_page.mjs).
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
    classList: { list: new Set(), add(c) { this.list.add(c); }, remove(c) { this.list.delete(c); }, contains(c) { return this.list.has(c); } },
  };
}

function fakeEvent() {
  return { preventDefault: () => {}, stopPropagation: () => {} };
}

function makeContext(opts) {
  const options = opts || {};
  const toasts = [];
  const store = new Map();
  for (const [key, value] of Object.entries(options.localStorageSeed || {})) store.set(key, value);
  const dom = { visualCharacterDetail: fakeElement(), imageStylePanel: fakeElement() };
  const fetchCalls = [];
  const sandbox = {
    imageState: Object.assign({ characterId: null, characterName: '', characterReferences: [], characterReferenceLibrary: [], characterReferenceIds: [], objectId: null, objectName: '', objectReferences: [], objects: '' }, options.imageState || {}),
    videoState: { characterVisual: null, characterImage: '', objectVisual: null, referenceVisual: null },
    activeCharacterDetailId: options.activeCharacterDetailId || '',
    characterDetailPendingIds: [],
    studioMode: 'image',
    activeCat: 'image',
    serverVisualItems: options.serverVisualItems || {},
    toast: (msg) => toasts.push(msg),
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { store.delete(key); },
    },
    confirmResourceDelete: options.confirmResourceDelete || (async () => true),
    fetch: options.fetch || (async (url) => {
      fetchCalls.push(url);
      return { ok: true, json: async () => ({ ok: true, deleted: true }) };
    }),
    document: { getElementById: (id) => dom[id] || null },
    renderImageStylePanel: () => {},
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderVideoReferencesPreview: () => {},
    window: {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('isCustomVisualItem'), context);
  vm.runInContext(extractFunction('customVisualKey'), context);
  vm.runInContext(extractFunction('visualPreviewUrl'), context);
  vm.runInContext(extractFunction('normalizeVisualItem'), context);
  vm.runInContext(extractFunction('loadCustomVisualItems'), context);
  vm.runInContext(extractFunction('saveCustomVisualItems'), context);
  vm.runInContext(extractFunction('clearSelectedCharacter'), context);
  vm.runInContext(extractFunction('clearSelectedObject'), context);
  vm.runInContext(extractFunction('isVideoMode'), context);
  vm.runInContext(extractFunction('currentVideoReferenceImages'), context);
  vm.runInContext(extractFunction('setCurrentVideoReferenceImages'), context);
  vm.runInContext(extractFunction('closeCharacterDetail'), context);
  vm.runInContext(extractFunction('deleteVisualItemFromBackend'), context);
  const imageCharacters = options.imageCharacters || (() => vm.runInContext(`loadCustomVisualItems('characters')`, context));
  const imageObjects = options.imageObjects || (() => vm.runInContext(`loadCustomVisualItems('objects')`, context));
  context.imageCharacters = imageCharacters;
  context.imageObjects = imageObjects;
  vm.runInContext(extractFunction('deleteVisualReference'), context);
  return { context, toasts, dom, store, fetchCalls };
}

// ===== deleteVisualItemFromBackend() itself: success requires BOTH
// ok:true AND deleted:true from the backend. =====

test('deleteVisualItemFromBackend: returns true only when the backend returns ok:true AND deleted:true', async () => {
  const { context } = makeContext({
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, deleted: true }) }),
  });
  const result = await vm.runInContext(`deleteVisualItemFromBackend('character', 'custom_character_abc')`, context);
  assert.equal(result, true);
});

test('deleteVisualItemFromBackend: returns false when the backend returns ok:true but deleted:false', async () => {
  const { context } = makeContext({
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, deleted: false }) }),
  });
  const result = await vm.runInContext(`deleteVisualItemFromBackend('character', 'custom_character_abc')`, context);
  assert.equal(result, false);
});

test('deleteVisualItemFromBackend: returns false when the HTTP response itself is not ok, even if the body claims success', async () => {
  const { context } = makeContext({
    fetch: async () => ({ ok: false, json: async () => ({ ok: true, deleted: true }) }),
  });
  const result = await vm.runInContext(`deleteVisualItemFromBackend('character', 'custom_character_abc')`, context);
  assert.equal(result, false);
});

test('deleteVisualReference: ok:true but deleted:false must not remove the Character locally', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, toasts } = makeContext({
    serverVisualItems,
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, deleted: false }) }),
  });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.characters, [character], 'deleted:false must be treated the same as a failed delete');
  assert.ok(!toasts.some((msg) => /удал[её]н/.test(msg)));
  assert.ok(toasts.some((msg) => /не удалось/i.test(msg)));
});

test('deleteVisualReference: a custom Character is removed from serverVisualItems and localStorage once the backend confirms the delete', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, toasts } = makeContext({ serverVisualItems });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.characters, []);
  const remaining = vm.runInContext(`loadCustomVisualItems('characters')`, context);
  assert.equal(remaining.length, 0);
  assert.ok(toasts.some((msg) => /удал/i.test(msg)));
});

test('deleteVisualReference: persists after "reload" - loadCustomVisualItems never returns the deleted Character again', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context } = makeContext({ serverVisualItems });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  // Simulate a fresh page load: serverVisualItems.characters is gone (as
  // the backend would now report) and only localStorage persists across
  // the reload - the deleted Character must not resurface from either.
  serverVisualItems.characters = [];
  const afterReload = vm.runInContext(`loadCustomVisualItems('characters')`, context);
  assert.equal(afterReload.find((item) => item.id === 'custom_character_abc'), undefined);
});

test('deleteVisualReference: clears the currently selected Character when the deleted Character was active', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context } = makeContext({
    serverVisualItems,
    imageState: { characterId: 'custom_character_abc', characterName: 'Islam', characterReferenceIds: ['r1'], characterReferences: ['https://cdn.sylvex.ai/a.png'] },
  });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.equal(vm.runInContext('imageState.characterId', context), null);
  assert.equal(vm.runInContext('imageState.characterReferenceIds.length', context), 0);
});

test('deleteVisualReference: closes the Character detail page if the deleted Character was the one open', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, dom } = makeContext({ serverVisualItems, activeCharacterDetailId: 'custom_character_abc' });
  dom.visualCharacterDetail.hidden = false;

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.equal(vm.runInContext('activeCharacterDetailId', context), '');
  assert.equal(dom.visualCharacterDetail.hidden, true);
});

test('deleteVisualReference: a backend failure leaves the Character exactly as it was - no local removal, no false success toast', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, toasts } = makeContext({
    serverVisualItems,
    fetch: async () => ({ ok: false, json: async () => ({}) }),
  });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.characters, [character], 'the Character must still be present after a failed backend delete');
  assert.ok(!toasts.some((msg) => /удал[её]н/.test(msg)), 'must never claim success when the backend delete failed');
  assert.ok(toasts.some((msg) => /не удалось/i.test(msg)), 'must surface a failure toast');
});

test('deleteVisualReference: a network exception during the backend call is treated the same as a failure', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, toasts } = makeContext({
    serverVisualItems,
    fetch: async () => { throw new Error('network down'); },
  });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.characters, [character]);
  assert.ok(toasts.some((msg) => /не удалось/i.test(msg)));
});

test('deleteVisualReference: declining the confirm dialog never calls the backend and changes nothing', async () => {
  const character = { id: 'custom_character_abc', name: 'Islam', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/a.png', referenceImages: [] };
  const serverVisualItems = { characters: [character] };
  const { context, toasts, fetchCalls } = makeContext({ serverVisualItems, confirmResourceDelete: async () => false });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'custom_character_abc')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.characters, [character]);
  assert.equal(fetchCalls.length, 0);
  assert.equal(toasts.length, 0);
});

test('deleteVisualReference: a built-in/preset Character (not isCustomVisualItem) is never deletable', async () => {
  const builtIn = { id: 'character_sylvex', name: 'SYLVEX', previewUrl: 'https://cdn.sylvex.ai/sylvex.png', referenceImages: [] };
  const { context, toasts, fetchCalls } = makeContext({ imageCharacters: () => [builtIn] });

  await vm.runInContext(`deleteVisualReference(e, 'character', 'character_sylvex')`, Object.assign(context, { e: fakeEvent() }));

  assert.equal(fetchCalls.length, 0, 'the backend must never be called for a built-in Character');
  assert.equal(toasts.length, 0);
});

test('deleteVisualReference: Object deletion follows the same confirm-before-remove contract', async () => {
  const object = { id: 'custom_object_xyz', name: 'Watch', type: 'custom', previewUrl: 'https://cdn.sylvex.ai/watch.png', referenceImages: [] };
  const serverVisualItems = { objects: [object] };
  const { context } = makeContext({ serverVisualItems, imageState: { objectId: 'custom_object_xyz', objectName: 'Watch', objectReferences: ['https://cdn.sylvex.ai/watch.png'] } });

  await vm.runInContext(`deleteVisualReference(e, 'object', 'custom_object_xyz')`, Object.assign(context, { e: fakeEvent() }));

  assert.deepEqual(serverVisualItems.objects, []);
  assert.equal(vm.runInContext('imageState.objectId', context), null);
});
