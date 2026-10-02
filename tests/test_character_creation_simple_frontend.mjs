// Run with: node --test tests/test_character_creation_simple_frontend.mjs
//
// Regression tests for the frontend half of the final simplified Character
// creation flow: Name + Gender + exactly one photo + one optional text
// field + Create Character button - nothing else. Guards against
// reintroducing any of the reverted Character Creation V2 complexity
// (Manual/Create-with-AI modes, Preserve/AI Polish, multiple upload
// slots) and confirms Object creation (3 photo slots, no gender) is
// untouched.
//
// Exercises the cabinet.js helpers directly via node:vm extraction (same
// pattern as test_character_reference_library_frontend.mjs).
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

function makeContext() {
  const sandbox = {
    renderVisualCreateModal: () => {},
    toast: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('openVisualCreateModal'), context);
  vm.runInContext(extractFunction('visualCreateCanSave'), context);
  return context;
}

test('openVisualCreateModal: the draft has only kind/name/gender/description/photos - no mode or processingMode field', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  const draft = vm.runInContext('visualCreateDraft', context);
  assert.deepEqual(Object.keys(draft).sort(), ['description', 'gender', 'kind', 'name', 'photos']);
  assert.equal(draft.kind, 'character');
  assert.equal(draft.name, '');
  assert.equal(draft.gender, '');
  assert.equal(draft.description, '');
  assert.deepEqual([...draft.photos], []);
});

test('visualCreateCanSave: Character requires name, gender and exactly one photo - description stays optional', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);

  vm.runInContext(`visualCreateDraft.name = 'Islam'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false, 'still missing gender and photo');

  vm.runInContext(`visualCreateDraft.gender = 'male'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false, 'still missing the photo');

  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true, 'description was never required');
});

test('visualCreateCanSave: Character with no photo cannot be saved even with a description (photo is mandatory, unlike the reverted text-only mode)', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  vm.runInContext(`visualCreateDraft.name = 'Nova'`, context);
  vm.runInContext(`visualCreateDraft.gender = 'female'`, context);
  vm.runInContext(`visualCreateDraft.description = 'cyberpunk hacker, neon jacket'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
});

test('visualCreateCanSave: Object creation is unaffected (name + photo, no gender requirement)', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'object')`, context);
  vm.runInContext(`visualCreateDraft.name = 'Watch'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

// ---- createHeygenCharacterResource: the request always caps photos at 1 ----

function makeNetworkContext() {
  const calls = {body: null};
  const sandbox = {
    getTelegramId: () => 42,
    translateGenerationError: (err, fallback) => fallback,
    normalizeVisualItem: (x) => x,
    fetch: async (url, options) => {
      calls.body = JSON.parse(options.body);
      return {
        ok: true,
        json: async () => ({ok: true, resource: {id: 'custom_character_abc'}}),
      };
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('createHeygenCharacterResource'), context);
  return {context, calls};
}

test('createHeygenCharacterResource: sends at most one photo even if more were somehow collected', async () => {
  const {context, calls} = makeNetworkContext();
  await vm.runInContext(`createHeygenCharacterResource('Islam', ['https://cdn.sylvex.ai/a.jpg', 'https://cdn.sylvex.ai/b.jpg'], 'male', 'tall')`, context);
  assert.deepEqual(calls.body.photos, ['https://cdn.sylvex.ai/a.jpg']);
  assert.equal(calls.body.name, 'Islam');
  assert.equal(calls.body.gender, 'male');
  assert.equal(calls.body.description, 'tall');
  // No mode/processingMode field is ever sent - that was V2-only.
  assert.equal('mode' in calls.body, false);
  assert.equal('processing_mode' in calls.body, false);
});
