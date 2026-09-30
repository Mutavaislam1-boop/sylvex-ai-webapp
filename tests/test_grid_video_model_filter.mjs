// Run with: node --test tests/test_grid_video_model_filter.mjs
//
// Regression tests for Phase 1 Batch 8 of the Pro Studio master
// remediation plan (see /root/.claude/plans/splendid-moseying-starlight.md,
// roadmap step 8): "Grid's gridModelsForType('video') generalized to the
// same filter."
//
// gridModelsForType('video') already excluded avatar:true models (Grid has
// no Character-reference port to source an avatar_id from - see
// tests/test_phase8_dead_ui_and_grid_avatar_fixes.mjs). This batch extends
// the exact same reasoning - "Grid has no UI control for this model's one
// required input, so it can never work correctly here" - to models whose
// modes include 'video_effects' (kling_effects): its effect_scene field is
// only ever supplied by the Kling Effects catalog
// (startVideoTemplateGeneration), and gridNodeSettingsHtml's video branch
// has no effect_scene control at all, so selecting it in Grid would always
// fail server-side with "effect_scene is missing" (_build_video_payload).
// gridDefaultModel('video') gets the same guard, so a freshly-created node
// can never inherit an excluded model from the main composer's current
// selection either.
//
// Correction (this file's second pass, per review): the two consumers used
// to each independently read VIDEO_MODEL_CONFIG[id].avatar/.video_effects,
// which could drift from the central capability registry the same way
// videoModelSupportsEdit()'s legacy video_edit:true boolean once did (see
// test_video_edit_mode_model_filter.mjs). Both consumers now call one
// shared helper, gridVideoModelSupported(modelId), which prefers
// fetchedModelCapabilities.models[modelId] (a direct mirror of Python's
// VIDEO_MODEL_CONFIG[model_id], see services/model_capabilities.py
// register_video_models()) over the local VIDEO_MODEL_CONFIG mirror - the
// same fail-open pattern as videoModelSupportsEdit()/
// videoModelSupportsMotionControl() - using local data only as the
// additive fallback when no fetched data has loaded yet. The local
// fallback now also derives its video_effects exclusion from
// modes.includes('video_effects') rather than a separately-maintained
// boolean.
//
// Motion Control models (kling_motion_3_0, kling_motion_2_6, kling_o3_omni)
// are deliberately NOT excluded: motion_control needs both a subject image
// and a motion/reference video, and Grid's video node now has ports,
// payload propagation (gridGenerationPayload) and validation
// (validateGridNodeInputs) for both - nothing about either required input
// is catalog-only or missing a Grid control, so these models are
// structurally usable here.
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

// gridModelsForType/gridDefaultModel/gridVideoModelSupported's local
// fallback needs the Kling entries (kling_effects, kling_motion_3_0,
// etc.) - those are added via a separate
// Object.assign(VIDEO_MODEL_CONFIG, {...}) call, not the base object
// literal, so plain extractConstObject('VIDEO_MODEL_CONFIG') alone (as
// used by the older avatar-only test file) would silently omit them. Same
// combined extraction as the Batch 6/7 test files.
function extractVideoModelConfigWithKling() {
  const startMatch = /const VIDEO_MODEL_CONFIG *= *\{/.exec(cabinet);
  assert.ok(startMatch, 'VIDEO_MODEL_CONFIG declaration not found');
  const assignMatch = /Object\.assign\(VIDEO_MODEL_CONFIG, *\{/.exec(cabinet);
  assert.ok(assignMatch, 'Object.assign(VIDEO_MODEL_CONFIG, ...) not found');
  const openIndex = cabinet.indexOf('{', assignMatch.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  let j = i + 1;
  while (cabinet[j] !== ')') j++;
  assert.ok(j < cabinet.length, 'matching close not found for Object.assign(VIDEO_MODEL_CONFIG, ...)');
  return cabinet.slice(startMatch.index, j + 1) + ';';
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

// fetchedOverride mirrors the shape /api/public/prostudio/model-capabilities
// serves: {version, models: {<id>: {avatar, modes, ...}}}.
function loadGridModelContext(fetchedOverride, videoModelId) {
  const context = vm.createContext({
    filterSylvexTestEntries: (list) => list,
    fetchedModelCapabilities: fetchedOverride || null,
    videoState: {modelId: videoModelId || ''},
    imageState: {}, musicState: {}, voiceState: {}, textState: {},
    IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: [], TEXT_MODEL_LIST: [],
  });
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  return context;
}

test('VIDEO_MODEL_CONFIG: kling_effects is the only video model whose local modes include video_effects (sanity check for the local-fallback exclusion)', () => {
  const context = loadGridModelContext();
  const config = vm.runInContext('VIDEO_MODEL_CONFIG', context);
  const flagged = Object.keys(config).filter((id) => Array.isArray(config[id].modes) && config[id].modes.includes('video_effects'));
  assert.deepEqual(flagged, ['kling_effects']);
});

// =====================================================================
// gridModelsForType('video') - local-fallback behavior (no fetched data)
// =====================================================================

test('gridModelsForType(video): video_effects (kling_effects) is excluded via the local fallback', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(!ids.includes('kling_effects'));
});

test('gridModelsForType(video): avatar:true HeyGen models are still excluded via the local fallback', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(!ids.includes('heygen_avatar_iv'));
  assert.ok(!ids.includes('heygen_avatar_v'));
  assert.ok(!ids.includes('heygen_avatar_iii'));
  assert.ok(!ids.includes('heygen_cinematic_avatar'));
});

test('gridModelsForType(video): motion_control-capable models remain selectable (not conflated with the Motion Catalog\'s own fixed-model restriction)', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(ids.includes('kling_motion_3_0'));
  assert.ok(ids.includes('kling_motion_2_6'));
  assert.ok(ids.includes('kling_o3_omni'));
});

test('gridModelsForType(video): ordinary non-excluded models (including non-avatar HeyGen) still present', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(ids.includes('seedance_2_fast'));
  assert.ok(ids.includes('heygen_v3_video_agent'));
  assert.ok(ids.includes('heygen_image_video'));
});

// =====================================================================
// gridDefaultModel('video') - local-fallback behavior (no fetched data)
// =====================================================================

test('gridDefaultModel(video): falls back past a video_effects model the main composer currently has selected', () => {
  const context = loadGridModelContext(null, 'kling_effects');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

test('gridDefaultModel(video): still falls back past an avatar model too', () => {
  const context = loadGridModelContext(null, 'heygen_avatar_iv');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

test('gridDefaultModel(video): a motion_control-capable current selection passes through unchanged (not caught by the video_effects/avatar guard)', () => {
  const context = loadGridModelContext(null, 'kling_motion_3_0');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'kling_motion_3_0');
});

test('gridDefaultModel(video): a non-excluded current selection passes through unchanged', () => {
  const context = loadGridModelContext(null, 'runway_gen4_5');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'runway_gen4_5');
});

// =====================================================================
// fetchedModelCapabilities overrides the local fallback, in both
// directions - proving the decision is registry-driven, not a second
// independent read of VIDEO_MODEL_CONFIG.
// =====================================================================

test('gridVideoModelSupported: fetched registry can exclude a model the local config would have allowed', () => {
  // seedance_2_fast has no avatar/video_effects locally - simulate the
  // fetched registry (Python-sourced) saying this model is now
  // effects-only, and confirm the fetched value wins.
  const context = loadGridModelContext({version: 'v1', models: {seedance_2_fast: {avatar: false, modes: ['video_effects']}}});
  assert.equal(vm.runInContext(`gridVideoModelSupported('seedance_2_fast')`, context), false);
});

test('gridVideoModelSupported: fetched registry can include a model the local config would have excluded', () => {
  // kling_effects is video_effects locally - simulate the fetched
  // registry saying it has since gained a real non-effects mode with no
  // avatar/video_effects flag, and confirm the fetched value wins over
  // the local exclusion.
  const context = loadGridModelContext({version: 'v1', models: {kling_effects: {avatar: false, modes: ['text_to_video']}}});
  assert.equal(vm.runInContext(`gridVideoModelSupported('kling_effects')`, context), true);
});

test('gridVideoModelSupported: fetched registry can exclude via avatar even when the local config says otherwise', () => {
  const context = loadGridModelContext({version: 'v1', models: {seedance_2_fast: {avatar: true, modes: ['text_to_video']}}});
  assert.equal(vm.runInContext(`gridVideoModelSupported('seedance_2_fast')`, context), false);
});

test('gridVideoModelSupported: a fetched entry for a different model does not affect the one being checked (fail open per-model)', () => {
  const context = loadGridModelContext({version: 'v1', models: {heygen_avatar_iv: {avatar: false, modes: ['text_to_video']}}});
  // seedance_2_fast has no fetched entry of its own - falls back to local,
  // which declares no avatar/video_effects for it, so it stays included.
  assert.equal(vm.runInContext(`gridVideoModelSupported('seedance_2_fast')`, context), true);
});

test('gridModelsForType(video): reflects a fetched-registry exclusion end to end', () => {
  const context = loadGridModelContext({version: 'v1', models: {seedance_2_fast: {avatar: false, modes: ['video_effects']}}});
  const ids = vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id);
  assert.ok(!ids.includes('seedance_2_fast'));
});

test('gridDefaultModel(video): reflects a fetched-registry exclusion end to end', () => {
  // runway_gen4_5 has no avatar/video_effects locally or by default - the
  // fetched registry saying otherwise must still force the fallback to
  // the hardcoded ultimate default (seedance_2_fast, a different model
  // than the one under test, so this can't pass by coincidence).
  const context = loadGridModelContext({version: 'v1', models: {runway_gen4_5: {avatar: false, modes: ['video_effects']}}}, 'runway_gen4_5');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

// =====================================================================
// gridModelsForType() and gridDefaultModel() must always agree - the
// required cross-check for sharing one decision function.
// =====================================================================

test('gridModelsForType and gridDefaultModel agree under the local fallback for every video model', () => {
  const context = loadGridModelContext();
  const pickerIds = new Set(vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id));
  const allIds = vm.runInContext('VIDEO_MODELS', context).map((item) => item.id).filter((id) => id !== 'sylvex_test');
  for (const id of allIds) {
    vm.runInContext(`videoState.modelId = ${JSON.stringify(id)};`, context);
    const defaulted = vm.runInContext(`gridDefaultModel('video')`, context);
    const pickerIncludesIt = pickerIds.has(id);
    assert.equal(defaulted === id, pickerIncludesIt, `disagreement for ${id}: picker includes=${pickerIncludesIt}, default kept it=${defaulted === id}`);
  }
});

test('gridModelsForType and gridDefaultModel agree under a fetched-registry override', () => {
  const fetchedOverride = {version: 'v1', models: {
    seedance_2_fast: {avatar: false, modes: ['video_effects']}, // now excluded, was allowed locally
    kling_effects: {avatar: false, modes: ['text_to_video']},   // now allowed, was excluded locally
  }};
  const context = loadGridModelContext(fetchedOverride);
  const pickerIds = new Set(vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id));
  assert.ok(!pickerIds.has('seedance_2_fast'));
  assert.ok(pickerIds.has('kling_effects'));

  vm.runInContext(`videoState.modelId = 'seedance_2_fast';`, context);
  assert.equal(vm.runInContext(`gridDefaultModel('video')`, context), 'seedance_2_fast');

  vm.runInContext(`videoState.modelId = 'kling_effects';`, context);
  assert.equal(vm.runInContext(`gridDefaultModel('video')`, context), 'kling_effects');
});

test('gridModelsForType: non-video types are unaffected (image/music/voice/text still return their unfiltered lists)', () => {
  const context = vm.createContext({
    filterSylvexTestEntries: (list) => list,
    fetchedModelCapabilities: null,
    IMAGE_MODEL_LIST: [{id: 'img_1'}],
    MUSIC_MODEL_LIST: [{id: 'music_1'}],
    VOICE_MODEL_LIST: [{id: 'voice_1'}],
    TEXT_MODEL_LIST: [{id: 'text_1'}],
  });
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  assert.deepEqual(vm.runInContext(`gridModelsForType('image')`, context), [{id: 'img_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('music')`, context), [{id: 'music_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('voice')`, context), [{id: 'voice_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('text')`, context), [{id: 'text_1'}]);
});
