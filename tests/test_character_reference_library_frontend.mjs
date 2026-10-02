// Run with: node --test tests/test_character_reference_library_frontend.mjs
//
// Regression tests for the frontend half of Master A-Z Remediation Phase 4
// (Character System V2): an expandable reference library capped by model
// capability, manual per-generation reference selection (never automatic),
// and the explicit "Add generated image to Character References" action.
//
// Exercises the new cabinet.js helper functions directly via node:vm
// extraction (same pattern as test_photo_upload_pipeline.mjs), with
// `getModelCapabilities` stubbed directly in the vm context rather than
// also extracted - these tests are about the new helpers' own logic, not
// about re-verifying getModelCapabilities itself (already covered
// elsewhere).
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
  const context = vm.createContext({
    imageState,
    activeCharacterDetailId: '',
    getModelCapabilities: options.getModelCapabilities || (() => ({ maxReferences: null })),
    toast: (msg) => toasts.push(msg),
    sendVisualInteraction: () => {},
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    document: { getElementById: () => null },
    getTelegramId: () => 42,
    fetch: options.fetch,
    window: {},
  });
  vm.runInContext(extractFunction('characterReferenceCap'), context);
  vm.runInContext(extractFunction('characterReferenceLibraryFor'), context);
  vm.runInContext(extractFunction('defaultCharacterReferenceIds'), context);
  vm.runInContext(extractFunction('syncCharacterReferencesFromIds'), context);
  vm.runInContext(extractFunction('applyCharacterReferenceSelection'), context);
  vm.runInContext('function renderCharacterDetail(){}', context);
  vm.runInContext('function renderImageReferenceSections(){}', context);
  vm.runInContext('function updateSendButton(){}', context);
  vm.runInContext(extractFunction('addGeneratedImageToCharacterReferences'), context);
  return { context, toasts };
}

test('characterReferenceCap: reads maxReferences from getModelCapabilities, null when the model has no declared cap', () => {
  const imageState = baseImageState();
  const { context } = makeContext(imageState, { getModelCapabilities: (id) => (id === 'seedream_5_0_pro' ? { maxReferences: 3 } : { maxReferences: null }) });
  assert.equal(vm.runInContext('characterReferenceCap("seedream_5_0_pro")', context), 3);
  assert.equal(vm.runInContext('characterReferenceCap("other_model")', context), null);
});

test('characterReferenceLibraryFor: uses the item\'s own referenceLibrary when present (expandable library, not fixed to 4 photos)', () => {
  const { context } = makeContext(baseImageState());
  const item = {
    id: 'custom_character_abc',
    referenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Full Body' },
      { id: 'ref3', url: 'https://cdn.sylvex.ai/c.png', role: 'Additional' },
      { id: 'ref4', url: 'https://cdn.sylvex.ai/d.png', role: 'Additional' },
      { id: 'ref5', url: 'https://cdn.sylvex.ai/e.png', role: 'Additional' },
    ],
  };
  const library = vm.runInContext('characterReferenceLibraryFor(item)', Object.assign(context, { item }));
  assert.equal(library.length, 5);
  assert.equal(library[0].url, 'https://cdn.sylvex.ai/a.png');
});

test('characterReferenceLibraryFor: synthesizes a library from avatarUrl/referenceImages when no explicit library exists', () => {
  const { context } = makeContext(baseImageState());
  const item = { id: 'character_1', avatarUrl: 'https://cdn.sylvex.ai/avatar.png', referenceImages: ['https://cdn.sylvex.ai/r1.png'] };
  const library = vm.runInContext('characterReferenceLibraryFor(item)', Object.assign(context, { item }));
  assert.equal(library.length, 2);
  assert.equal(library[0].role, 'Primary Face');
  assert.equal(library[1].role, 'Additional');
});

test('characterReferenceLibraryFor: returns [] for a falsy item', () => {
  const { context } = makeContext(baseImageState());
  assert.equal(vm.runInContext('characterReferenceLibraryFor(null)', context).length, 0);
});

test('defaultCharacterReferenceIds: caps the default selection at the model limit, not at the full library size', () => {
  const { context } = makeContext(baseImageState());
  const library = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }, { id: 'e' }];
  const ids = vm.runInContext('defaultCharacterReferenceIds(library, 2)', Object.assign(context, { library }));
  assert.deepEqual(ids, ['a', 'b']);
});

test('defaultCharacterReferenceIds: with no cap (null), defaults to the entire library', () => {
  const { context } = makeContext(baseImageState());
  const library = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const ids = vm.runInContext('defaultCharacterReferenceIds(library, null)', Object.assign(context, { library }));
  assert.deepEqual(ids, ['a', 'b', 'c']);
});

test('applyCharacterReferenceSelection: selecting a Character auto-fills the default reference set capped by the current model', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const { context } = makeContext(imageState, { getModelCapabilities: () => ({ maxReferences: 1 }) });
  const item = {
    id: 'custom_character_xyz',
    name: 'Islam',
    referenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Full Body' },
    ],
  };
  vm.runInContext('applyCharacterReferenceSelection(item)', Object.assign(context, { item }));
  assert.equal(imageState.characterId, 'custom_character_xyz');
  assert.equal(imageState.characterName, 'Islam');
  assert.equal(imageState.characterReferenceLibrary.length, 2);
  // Model caps at 1 - manual selection is capped, not automatically all of them.
  assert.deepEqual(imageState.characterReferenceIds, ['ref1']);
  assert.deepEqual(imageState.characterReferences, ['https://cdn.sylvex.ai/a.png']);
});

test('applyCharacterReferenceSelection: an explicit empty overrideIds commits zero references, never falls back to "all" (Character page "Use Character" with nothing checked)', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const { context } = makeContext(imageState, { getModelCapabilities: () => ({ maxReferences: 3 }) });
  const item = {
    id: 'custom_character_xyz',
    name: 'Islam',
    referenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Full Body' },
    ],
  };
  vm.runInContext('applyCharacterReferenceSelection(item, [])', Object.assign(context, { item }));
  assert.equal(imageState.characterId, 'custom_character_xyz');
  assert.equal(imageState.characterReferenceIds.length, 0);
  assert.equal(imageState.characterReferences.length, 0);
});

test('applyCharacterReferenceSelection: an explicit overrideIds subset commits exactly that subset, filtered against the library', () => {
  const imageState = baseImageState({ modelId: 'capped_model' });
  const { context } = makeContext(imageState, { getModelCapabilities: () => ({ maxReferences: 3 }) });
  const item = {
    id: 'custom_character_xyz',
    name: 'Islam',
    referenceLibrary: [
      { id: 'ref1', url: 'https://cdn.sylvex.ai/a.png', role: 'Primary Face' },
      { id: 'ref2', url: 'https://cdn.sylvex.ai/b.png', role: 'Full Body' },
      { id: 'ref3', url: 'https://cdn.sylvex.ai/c.png', role: 'Additional' },
    ],
  };
  vm.runInContext('applyCharacterReferenceSelection(item, ["ref3", "not_in_library"])', Object.assign(context, { item }));
  assert.equal(imageState.characterReferenceIds.length, 1);
  assert.equal(imageState.characterReferenceIds[0], 'ref3');
  assert.equal(imageState.characterReferences.length, 1);
  assert.equal(imageState.characterReferences[0], 'https://cdn.sylvex.ai/c.png');
});

test('addGeneratedImageToCharacterReferences: never automatic - requires explicit confirm, then POSTs to the add-reference endpoint', async () => {
  const imageState = baseImageState({ characterId: 'custom_character_abc' });
  let requestedUrl = '';
  let requestedBody = null;
  const { context, toasts } = makeContext(imageState, {
    fetch: async (url, init) => {
      requestedUrl = url;
      requestedBody = JSON.parse(init.body);
      return { ok: true, json: async () => ({ ok: true, resource: { id: 'custom_character_abc', referenceLibrary: [{ id: 'ref1', url: 'https://cdn.sylvex.ai/gen.png', role: 'Additional' }] } }) };
    },
  });
  context.window.confirm = () => true;
  context.confirm = () => true;
  const event = {
    preventDefault: () => {},
    stopPropagation: () => {},
    currentTarget: { dataset: { imageUrl: 'https://cdn.sylvex.ai/gen.png', characterId: 'custom_character_abc' } },
  };
  await vm.runInContext('addGeneratedImageToCharacterReferences(e)', Object.assign(context, { e: event }));

  assert.equal(requestedUrl, '/api/public/prostudio/character/custom_character_abc/references');
  assert.equal(requestedBody.url, 'https://cdn.sylvex.ai/gen.png');
  assert.equal(requestedBody.telegram_id, 42);
  assert.ok(toasts.includes('Фото добавлено в референсы персонажа'));
  assert.equal(imageState.characterReferenceLibrary.length, 1);
});

test('addGeneratedImageToCharacterReferences: declining the confirm never calls the endpoint', async () => {
  const imageState = baseImageState({ characterId: 'custom_character_abc' });
  let called = false;
  const { context } = makeContext(imageState, { fetch: async () => { called = true; return { ok: true, json: async () => ({ ok: true }) }; } });
  context.window.confirm = () => false;
  context.confirm = () => false;
  const event = {
    preventDefault: () => {},
    stopPropagation: () => {},
    currentTarget: { dataset: { imageUrl: 'https://cdn.sylvex.ai/gen.png', characterId: 'custom_character_abc' } },
  };
  await vm.runInContext('addGeneratedImageToCharacterReferences(e)', Object.assign(context, { e: event }));
  assert.equal(called, false);
});
