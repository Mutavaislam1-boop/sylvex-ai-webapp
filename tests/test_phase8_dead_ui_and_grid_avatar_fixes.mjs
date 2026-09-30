// Run with: node --test tests/test_phase8_dead_ui_and_grid_avatar_fixes.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 8 fixes:
// - Sora 2 / Sora 2 Pro declared sound:true in VIDEO_MODEL_CONFIG (the sole
//   frontend capability source the composer's Sound toggle is gated on -
//   VIDEO_MODELS only carries id/label/desc/icon for the picker list),
//   rendering a Sound toggle that _call_sora never reads (OpenAI's Sora 2
//   API has no documented audio control at all) - pure dead UI with zero
//   effect either way. Now sound:false so the toggle is hidden instead of
//   implying a control that doesn't exist.
// - Grid Mode's video model dropdown (gridModelsForType) listed every
//   VIDEO_MODELS entry including avatar:true HeyGen models, even though
//   gridGenerationPayload's video branch never sets avatar_id/heygen_* -
//   Grid has no Character-reference port to source one from. Now filtered
//   out until Grid gets a Character port; gridDefaultModel falls back past
//   an avatar model too so a freshly-created node can't inherit one from
//   the main composer's current selection.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractConstArray(name) {
  const re = new RegExp(`const ${name} *= *\\[`);
  const m = re.exec(cabinet);
  assert.ok(m, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('[', m.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '[') depth++;
    else if (cabinet[i] === ']') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(m.index, i + 1) + ';';
}

function extractConstObject(name) {
  const re = new RegExp(`const ${name} *= *\\{`);
  const m = re.exec(cabinet);
  assert.ok(m, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', m.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(m.index, i + 1) + ';';
}

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

function loadGridModelContext() {
  // gridModelsForType('video') now delegates its avatar/video_effects
  // decision to the shared gridVideoModelSupported() helper (Phase 1
  // Batch 8 correction - see test_grid_video_model_filter.mjs), which
  // reads fetchedModelCapabilities - both must be present in the sandbox
  // or the extracted function throws a ReferenceError.
  const context = vm.createContext({filterSylvexTestEntries: (list) => list, fetchedModelCapabilities: null});
  vm.runInContext(extractConstObject('VIDEO_MODEL_CONFIG'), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  return context;
}

test('VIDEO_MODEL_CONFIG: sora_2 and sora_2_pro no longer declare sound support', () => {
  const context = loadGridModelContext();
  const config = vm.runInContext('VIDEO_MODEL_CONFIG', context);
  assert.equal(config.sora_2.sound, false);
  assert.equal(config.sora_2_pro.sound, false);
});

test('VIDEO_MODELS: sora_2 and sora_2_pro entries still exist (picker list unaffected)', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext('VIDEO_MODELS', context);
  assert.ok(models.some((item) => item.id === 'sora_2'));
  assert.ok(models.some((item) => item.id === 'sora_2_pro'));
});

test('gridModelsForType(video): avatar:true HeyGen models are excluded', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(!ids.includes('heygen_avatar_iv'));
  assert.ok(!ids.includes('heygen_avatar_v'));
  assert.ok(!ids.includes('heygen_avatar_iii'));
  assert.ok(!ids.includes('heygen_cinematic_avatar'));
});

test('gridModelsForType(video): non-avatar models (including non-avatar HeyGen) still present', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(ids.includes('seedance_2_fast'));
  assert.ok(ids.includes('heygen_v3_video_agent'));
  assert.ok(ids.includes('heygen_image_video'));
});

test('gridDefaultModel(video): falls back past an avatar model the main composer currently has selected', () => {
  const context = vm.createContext({fetchedModelCapabilities: null, videoState: {modelId: 'heygen_avatar_iv'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractConstObject('VIDEO_MODEL_CONFIG'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

test('gridDefaultModel(video): a non-avatar current selection passes through unchanged', () => {
  const context = vm.createContext({fetchedModelCapabilities: null, videoState: {modelId: 'runway_gen4_5'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractConstObject('VIDEO_MODEL_CONFIG'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'runway_gen4_5');
});
