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
//
// Final correction (this file's third pass, per review): two bugs
// remained even after sharing gridVideoModelSupported() between the two
// consumers.
// 1. gridVideoModelSupported(modelId) treated an id with neither a
//    fetched entry nor a local VIDEO_MODEL_CONFIG entry as supported -
//    `VIDEO_MODEL_CONFIG[modelId] || {}` produced an empty object with no
//    avatar/video_effects flags to trip, so any unknown/stale id passed.
//    It now returns false outright when the id is unknown to both
//    sources.
// 2. gridDefaultModel('video') ended in an unconditional
//    `|| 'seedance_2_fast'` - the registry-driven guarantee
//    gridVideoModelSupported() exists to provide broke at exactly the
//    point the fallback itself was not re-checked: if a fetched
//    capability update ever marked seedance_2_fast itself
//    Grid-incompatible, the picker (gridModelsForType) would hide it
//    while this resolver kept handing it out anyway. The fallback logic
//    is now its own shared function, gridDefaultVideoModel(currentModelId),
//    which builds its entire chain (keep current -> prefer
//    seedance_2_fast -> first picker entry) from gridModelsForType
//    ('video')'s own filtered set, so it can never return a model the
//    picker itself excludes. The "agree under a fetched-registry
//    override" cross-check test below was itself wrong before this pass -
//    it excluded seedance_2_fast from the picker and then asserted
//    gridDefaultModel() still returned it, which was asserting the bug,
//    not catching it.
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
  vm.runInContext(extractFunction('gridDefaultVideoModel'), context);
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
  // seedance_2_fast, which is untouched by this particular override (a
  // different model than the one under test, so this can't pass by
  // coincidence).
  const context = loadGridModelContext({version: 'v1', models: {runway_gen4_5: {avatar: false, modes: ['video_effects']}}}, 'runway_gen4_5');
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

// =====================================================================
// gridVideoModelSupported must not treat an unknown id as supported -
// the guard added alongside gridDefaultVideoModel's registry-aware
// fallback (an empty {} local lookup has no avatar/video_effects flags
// to trip, so without this check any nonsense id would pass).
// =====================================================================

test('gridVideoModelSupported: an unknown model id (no fetched entry, no local VIDEO_MODEL_CONFIG entry) is not supported', () => {
  const context = loadGridModelContext();
  assert.equal(vm.runInContext(`gridVideoModelSupported('totally_made_up_model_id')`, context), false);
});

test('gridVideoModelSupported: an unknown model id stays unsupported even with unrelated fetched data loaded', () => {
  const context = loadGridModelContext({version: 'v1', models: {seedance_2_fast: {avatar: false, modes: ['text_to_video']}}});
  assert.equal(vm.runInContext(`gridVideoModelSupported('totally_made_up_model_id')`, context), false);
});

// =====================================================================
// The Grid default resolver must be capability-aware even for its own
// traditional fallback (seedance_2_fast) - the bug this correction
// exists to fix: the old gridDefaultModel('video') ended in an
// unconditional `|| 'seedance_2_fast'`, so if the fetched registry ever
// marked seedance_2_fast itself Grid-incompatible, the picker would hide
// it while the default resolver kept handing it out anyway.
// =====================================================================

test('gridDefaultVideoModel: when the fetched registry excludes seedance_2_fast itself, the default is some other visible/supported model', () => {
  const context = loadGridModelContext({version: 'v1', models: {seedance_2_fast: {avatar: false, modes: ['video_effects']}}}, 'seedance_2_fast');
  const pickerIds = new Set(vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id));
  assert.ok(!pickerIds.has('seedance_2_fast'), 'sanity check: the picker must actually exclude seedance_2_fast under this override');

  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.notEqual(result, 'seedance_2_fast');
  assert.ok(pickerIds.has(result), `the selected fallback (${result}) must itself be present in gridModelsForType('video')`);
});

test('gridDefaultVideoModel: an unknown/stale current model id does not survive as the Grid default', () => {
  const context = loadGridModelContext(null, 'a_model_id_that_no_longer_exists');
  const pickerIds = new Set(vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id));
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.notEqual(result, 'a_model_id_that_no_longer_exists');
  assert.ok(pickerIds.has(result), `the selected fallback (${result}) must itself be present in gridModelsForType('video')`);
});

// =====================================================================
// gridModelsForType() and gridDefaultModel() must always agree - the
// required cross-check for sharing one decision function. Under BOTH the
// local fallback and a fetched override: if the picker lists a model, the
// default resolver must keep it as the current selection unchanged; if
// the picker excludes it, the default resolver must never return that
// same id, and whatever it returns instead must itself be a picker entry
// (or '' if the picker is empty).
// =====================================================================

function assertPickerAndDefaultAgree(context) {
  const pickerIds = new Set(vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id));
  const allIds = vm.runInContext('VIDEO_MODELS', context).map((item) => item.id).filter((id) => id !== 'sylvex_test');
  for (const id of allIds) {
    vm.runInContext(`videoState.modelId = ${JSON.stringify(id)};`, context);
    const defaulted = vm.runInContext(`gridDefaultModel('video')`, context);
    if (pickerIds.has(id)) {
      assert.equal(defaulted, id, `picker includes ${id} but the default resolver replaced it with ${defaulted}`);
    } else {
      assert.notEqual(defaulted, id, `picker excludes ${id} but the default resolver still returned it`);
      assert.ok(pickerIds.size === 0 ? defaulted === '' : pickerIds.has(defaulted), `fallback ${defaulted} for excluded ${id} must itself be in the picker`);
    }
  }
}

test('gridModelsForType and gridDefaultModel agree under the local fallback for every video model', () => {
  assertPickerAndDefaultAgree(loadGridModelContext());
});

test('gridModelsForType and gridDefaultModel agree under a fetched-registry override for every video model', () => {
  const fetchedOverride = {version: 'v1', models: {
    seedance_2_fast: {avatar: false, modes: ['video_effects']}, // now excluded, was allowed locally
    kling_effects: {avatar: false, modes: ['text_to_video']},   // now allowed, was excluded locally
  }};
  assertPickerAndDefaultAgree(loadGridModelContext(fetchedOverride));
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
