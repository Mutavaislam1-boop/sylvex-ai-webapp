// Run with: node --test tests/test_character_creation_v2_frontend.mjs
//
// Regression tests for the frontend half of Character Creation V2 (Manual
// + Create with AI). Exercises the new cabinet.js helpers directly via
// node:vm extraction (same pattern as test_character_reference_library_frontend.mjs):
//   - setVisualCreateMode / setVisualCreateProcessingMode: mode switching,
//     ignored while saving.
//   - visualCreateCanSave: per-mode validation (AI mode accepts photo OR
//     description; Manual mode and Objects still require a photo).
//   - buildManualCharacterResource: role-mapping from whichever of the 4
//     fixed slots were filled, skipping empty ones without renumbering,
//     and the Primary-first/fallback-to-first-filled-slot rule.
//   - saveVisualCreateDraft: Manual mode never calls the AI character
//     endpoint (createHeygenCharacterResource) and assembles its resource
//     locally; Create with AI mode calls it with the uploaded photo and
//     chosen processing mode. Neither path touches
//     applyCharacterReferenceSelection's own selection semantics - it is
//     stubbed here and only its call (single-arg, per the already-fixed
//     generation/reference-selection contract) is asserted.
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

function extractConst(name) {
  const pattern = new RegExp(`^const ${name} = .*;$`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `const not found: ${name}`);
  return match[0];
}

function baseSandbox() {
  const calls = {
    toasts: [],
    applyCharacterReferenceSelectionArgs: null,
    applyVisualReferenceToVideoArgs: null,
    createHeygenCharacterResourceArgs: null,
    saveVisualItemToBackendArgs: null,
    savedCustomItems: null,
    closed: 0,
  };
  const sandbox = {
    console,
    toast: (msg) => { calls.toasts.push(msg); },
    wait: () => Promise.resolve(),
    visualCreateKindLabel: (kind) => (kind === 'character' ? 'Персонаж' : 'Объект'),
    visualCreateListLabel: (kind) => (kind === 'character' ? 'список персонажей' : 'список объектов'),
    translateGenerationError: (err, fallback) => fallback,
    normalizeGenerationImageReference: async (raw) => (raw ? { url: 'https://cdn.sylvex.ai/uploaded/' + Buffer.from(String(raw)).toString('hex').slice(0, 8) + '.png' } : null),
    visualPreviewUrl: (resource) => (resource && resource.avatarUrl) || '',
    generateVisualResourceWithOpenAI: async () => 'https://cdn.sylvex.ai/object-preview.png',
    createHeygenCharacterResource: async (name, photos, gender, description, processingMode) => {
      calls.createHeygenCharacterResourceArgs = { name, photos, gender, description, processingMode };
      return {
        id: 'custom_character_ai123',
        avatarUrl: 'https://cdn.sylvex.ai/ai/primary.png',
        referenceImages: [
          'https://cdn.sylvex.ai/ai/primary.png',
          'https://cdn.sylvex.ai/ai/front.png',
          'https://cdn.sylvex.ai/ai/side.png',
          'https://cdn.sylvex.ai/ai/back.png',
        ],
      };
    },
    saveVisualItemToBackend: async (kind, item) => {
      calls.saveVisualItemToBackendArgs = { kind, item };
      return item;
    },
    normalizeVisualItem: (x) => x,
    serverVisualItems: { characters: [], objects: [] },
    loadCustomVisualItems: () => [],
    saveCustomVisualItems: (storageKind, items) => { calls.savedCustomItems = { storageKind, items }; },
    isVideoMode: () => false,
    applyVisualReferenceToVideo: (item, kind) => { calls.applyVisualReferenceToVideoArgs = { item, kind }; },
    applyCharacterReferenceSelection: (...args) => { calls.applyCharacterReferenceSelectionArgs = args; },
    imageState: {},
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderImageStylePanel: () => {},
    renderVideoReferencesPreview: () => {},
    renderVisualCreateModal: () => {},
    closeVisualCreateModal: () => { calls.closed += 1; },
    closeVisualPicker: () => {},
    closeImageStylePanel: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractConst('MANUAL_CHARACTER_REFERENCE_ROLES'), context);
  vm.runInContext(extractFunction('buildManualCharacterResource'), context);
  vm.runInContext(extractFunction('visualCreateCanSave'), context);
  vm.runInContext(extractFunction('setVisualCreateMode'), context);
  vm.runInContext(extractFunction('setVisualCreateProcessingMode'), context);
  vm.runInContext(extractFunction('saveVisualCreateDraft'), context);
  return { context, calls };
}

// ---- setVisualCreateMode / setVisualCreateProcessingMode ----

test('setVisualCreateMode: switches between manual and ai, defaults anything else to ai', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'ai', saving: false };
  vm.runInContext(`setVisualCreateMode(null, 'manual')`, context);
  assert.equal(context.visualCreateDraft.mode, 'manual');
  vm.runInContext(`setVisualCreateMode(null, 'nonsense')`, context);
  assert.equal(context.visualCreateDraft.mode, 'ai');
});

test('setVisualCreateMode: ignored while a creation is in flight', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'ai', saving: true };
  vm.runInContext(`setVisualCreateMode(null, 'manual')`, context);
  assert.equal(context.visualCreateDraft.mode, 'ai');
});

test('setVisualCreateProcessingMode: switches between preserve and ai_polish, defaults anything else to ai_polish', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'ai', processingMode: 'ai_polish', saving: false };
  vm.runInContext(`setVisualCreateProcessingMode(null, 'preserve')`, context);
  assert.equal(context.visualCreateDraft.processingMode, 'preserve');
  vm.runInContext(`setVisualCreateProcessingMode(null, 'maximum')`, context);
  assert.equal(context.visualCreateDraft.processingMode, 'ai_polish');
});

// ---- visualCreateCanSave ----

test('visualCreateCanSave: Create-with-AI mode accepts a description with no photo', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'ai', name: 'Nova', gender: 'female', description: 'cyberpunk hacker', photos: [] };
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

test('visualCreateCanSave: Create-with-AI mode rejects no photo AND no description', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'ai', name: 'Nova', gender: 'female', description: '', photos: [] };
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
});

test('visualCreateCanSave: Manual mode requires at least one filled slot even with a description', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'character', mode: 'manual', name: 'Islam', gender: 'male', description: 'tall', photos: [] };
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  context.visualCreateDraft.photos = ['data:image/png;base64,aaa'];
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

test('visualCreateCanSave: Object creation still requires name + photo (unaffected by Character Creation V2)', () => {
  const { context } = baseSandbox();
  context.visualCreateDraft = { kind: 'object', name: 'Watch', photos: [] };
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  context.visualCreateDraft.photos = ['data:image/png;base64,aaa'];
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

// ---- buildManualCharacterResource ----

test('buildManualCharacterResource: only Primary filled - Character contains only Primary, matching the "Primary only is valid" rule', () => {
  const { context } = baseSandbox();
  const resource = vm.runInContext(`buildManualCharacterResource('Islam', 'male', ['https://cdn.sylvex.ai/primary.png', '', '', ''])`, context);
  assert.equal(resource.referenceLibrary.length, 1);
  assert.equal(resource.referenceLibrary[0].role, 'Primary Face');
  assert.equal(resource.primaryReferenceUrl, 'https://cdn.sylvex.ai/primary.png');
  assert.equal(resource.avatarUrl, 'https://cdn.sylvex.ai/primary.png');
  // Arrays built inside the vm context aren't reference-equal to host
  // arrays even with identical contents, so compare via a spread copy.
  assert.deepEqual([...resource.referenceImages], ['https://cdn.sylvex.ai/primary.png']);
});

test('buildManualCharacterResource: skips empty slots without renumbering roles (Primary + Back only)', () => {
  const { context } = baseSandbox();
  const resource = vm.runInContext(`buildManualCharacterResource('Islam', 'male', ['https://cdn.sylvex.ai/primary.png', '', '', 'https://cdn.sylvex.ai/back.png'])`, context);
  assert.equal(resource.referenceLibrary.length, 2);
  assert.equal(resource.referenceLibrary[0].role, 'Primary Face');
  assert.equal(resource.referenceLibrary[1].role, 'Full Body Back');
  assert.equal(resource.primaryReferenceUrl, 'https://cdn.sylvex.ai/primary.png');
});

test('buildManualCharacterResource: no Primary - falls back to the first filled slot as the identity reference', () => {
  const { context } = baseSandbox();
  const resource = vm.runInContext(`buildManualCharacterResource('Islam', 'male', ['', 'https://cdn.sylvex.ai/front.png', 'https://cdn.sylvex.ai/side.png', ''])`, context);
  assert.equal(resource.referenceLibrary.length, 2);
  assert.equal(resource.primaryReferenceUrl, 'https://cdn.sylvex.ai/front.png');
  assert.equal(resource.referenceLibrary[0].role, 'Full Body Front');
});

test('buildManualCharacterResource: all four slots filled produces all four roles in order', () => {
  const { context } = baseSandbox();
  const resource = vm.runInContext(`buildManualCharacterResource('Islam', 'male', ['https://cdn.sylvex.ai/p.png', 'https://cdn.sylvex.ai/f.png', 'https://cdn.sylvex.ai/s.png', 'https://cdn.sylvex.ai/b.png'])`, context);
  assert.deepEqual([...resource.referenceLibrary].map((entry) => entry.role), ['Primary Face', 'Full Body Front', 'Full Body Side', 'Full Body Back']);
});

// ---- saveVisualCreateDraft: Manual vs Create-with-AI branching ----

test('saveVisualCreateDraft: Manual mode never calls the AI/HeyGen character endpoint', async () => {
  const { context, calls } = baseSandbox();
  context.visualCreateDraft = {
    kind: 'character', mode: 'manual', name: 'Islam', gender: 'male', description: '',
    photos: ['data:image/png;base64,primaryRaw', '', '', 'data:image/png;base64,backRaw'],
    saving: false,
  };
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(calls.createHeygenCharacterResourceArgs, null);
  assert.ok(calls.saveVisualItemToBackendArgs, 'expected the manually-built resource to still be persisted via the generic save endpoint');
  const savedItem = calls.saveVisualItemToBackendArgs.item;
  assert.equal(savedItem.ai_provider, 'manual');
  assert.equal(savedItem.referenceImages.length, 2);
  // Characters still go through the single-arg applyCharacterReferenceSelection
  // call, matching the already-fixed creation-time auto-select-defaults
  // behavior - this test guards that contract is not touched.
  assert.deepEqual(calls.applyCharacterReferenceSelectionArgs.length, 1);
});

test('saveVisualCreateDraft: Create with AI mode uploads the single photo and threads processingMode through', async () => {
  const { context, calls } = baseSandbox();
  context.visualCreateDraft = {
    kind: 'character', mode: 'ai', name: 'Nova', gender: 'female', description: 'cyberpunk hacker',
    photos: ['data:image/png;base64,sourceRaw'],
    processingMode: 'preserve',
    saving: false,
  };
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.ok(calls.createHeygenCharacterResourceArgs, 'expected the AI character endpoint to be called');
  assert.equal(calls.createHeygenCharacterResourceArgs.name, 'Nova');
  assert.equal(calls.createHeygenCharacterResourceArgs.processingMode, 'preserve');
  assert.equal(calls.createHeygenCharacterResourceArgs.photos.length, 1);
  assert.ok(calls.createHeygenCharacterResourceArgs.photos[0].startsWith('https://cdn.sylvex.ai/uploaded/'), 'raw data: photo must be uploaded to a real URL before being sent');
});

test('saveVisualCreateDraft: Create with AI mode with no photo at all (text-only Scenario B) still calls the endpoint with an empty photo list', async () => {
  const { context, calls } = baseSandbox();
  context.visualCreateDraft = {
    kind: 'character', mode: 'ai', name: 'Nova', gender: 'female', description: 'cyberpunk hacker, neon jacket',
    photos: [],
    processingMode: 'ai_polish',
    saving: false,
  };
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.ok(calls.createHeygenCharacterResourceArgs);
  assert.deepEqual([...calls.createHeygenCharacterResourceArgs.photos], []);
});

test('saveVisualCreateDraft: Object creation path is unaffected (still goes through generateVisualResourceWithOpenAI, never the character endpoint)', async () => {
  const { context, calls } = baseSandbox();
  context.visualCreateDraft = {
    kind: 'object', name: 'Watch', description: '',
    photos: ['data:image/png;base64,objRaw'],
    saving: false,
  };
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(calls.createHeygenCharacterResourceArgs, null);
  assert.ok(calls.saveVisualItemToBackendArgs);
  assert.equal(calls.saveVisualItemToBackendArgs.item.ai_provider, 'openai');
});
