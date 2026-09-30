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
// required input, so it can never work correctly here" - to
// video_effects:true (kling_effects): its effect_scene field is only ever
// supplied by the Kling Effects catalog (startVideoTemplateGeneration),
// and gridNodeSettingsHtml's video branch has no effect_scene control at
// all, so selecting it in Grid would always fail server-side with
// "effect_scene is missing" (_build_video_payload). gridDefaultModel
// ('video') gets the same guard, so a freshly-created node can never
// inherit a video_effects model from the main composer's current
// selection either - matching the existing avatar guard.
//
// Motion Control models (kling_motion_3_0, kling_motion_2_6, kling_o3_omni)
// are deliberately NOT excluded: their motion_control mode only needs a
// prompt plus an optional image/video input, and Grid's video node already
// has 'image' and 'video' input ports declared in GRID_TYPES - unlike
// avatar_id/effect_scene, nothing about their required inputs is
// catalog-only or missing a Grid control.
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

// gridModelsForType/gridDefaultModel's video branch needs the Kling
// entries (kling_effects, kling_motion_3_0, etc.) - those are added via a
// separate Object.assign(VIDEO_MODEL_CONFIG, {...}) call, not the base
// object literal, so plain extractConstObject('VIDEO_MODEL_CONFIG') alone
// (as used by the older avatar-only test file) would silently omit them.
// Same combined extraction as the Batch 6/7 test files.
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

function loadGridModelContext() {
  const context = vm.createContext({filterSylvexTestEntries: (list) => list});
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  return context;
}

test('VIDEO_MODEL_CONFIG: kling_effects is the only video model with video_effects:true (sanity check for the exclusion flag)', () => {
  const context = loadGridModelContext();
  const config = vm.runInContext('VIDEO_MODEL_CONFIG', context);
  const flagged = Object.keys(config).filter((id) => config[id].video_effects);
  assert.deepEqual(flagged, ['kling_effects']);
});

test('gridModelsForType(video): video_effects:true (kling_effects) is excluded', () => {
  const context = loadGridModelContext();
  const models = vm.runInContext(`gridModelsForType('video')`, context);
  const ids = models.map((item) => item.id);
  assert.ok(!ids.includes('kling_effects'));
});

test('gridModelsForType(video): avatar:true HeyGen models are still excluded (pre-existing filter unaffected)', () => {
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

test('gridDefaultModel(video): falls back past a video_effects model the main composer currently has selected', () => {
  const context = vm.createContext({videoState: {modelId: 'kling_effects'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

test('gridDefaultModel(video): still falls back past an avatar model too (pre-existing behavior unaffected)', () => {
  const context = vm.createContext({videoState: {modelId: 'heygen_avatar_iv'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'seedance_2_fast');
});

test('gridDefaultModel(video): a motion_control-capable current selection passes through unchanged (not caught by the video_effects/avatar guard)', () => {
  const context = vm.createContext({videoState: {modelId: 'kling_motion_3_0'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'kling_motion_3_0');
});

test('gridDefaultModel(video): a non-excluded current selection passes through unchanged', () => {
  const context = vm.createContext({videoState: {modelId: 'runway_gen4_5'}, imageState: {}, musicState: {}, voiceState: {}, textState: {}, IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: []});
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  const result = vm.runInContext(`gridDefaultModel('video')`, context);
  assert.equal(result, 'runway_gen4_5');
});

test('gridModelsForType: non-video types are unaffected (image/music/voice/text still return their unfiltered lists)', () => {
  const context = vm.createContext({
    filterSylvexTestEntries: (list) => list,
    IMAGE_MODEL_LIST: [{id: 'img_1'}],
    MUSIC_MODEL_LIST: [{id: 'music_1'}],
    VOICE_MODEL_LIST: [{id: 'voice_1'}],
    TEXT_MODEL_LIST: [{id: 'text_1'}],
  });
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  assert.deepEqual(vm.runInContext(`gridModelsForType('image')`, context), [{id: 'img_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('music')`, context), [{id: 'music_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('voice')`, context), [{id: 'voice_1'}]);
  assert.deepEqual(vm.runInContext(`gridModelsForType('text')`, context), [{id: 'text_1'}]);
});
