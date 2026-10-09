// Run with: node --test tests/test_motion_control_mode_model_filter.mjs
//
// Regression tests for Phase 1 Batch 7 of the Pro Studio master
// remediation plan (see /root/.claude/plans/splendid-moseying-starlight.md,
// roadmap step 7): "Motion Control mode model-picker filtering" - the
// Motion Control counterpart to Batch 6's Video Edit mode filtering.
//
// Before this batch, currentComposerModelList() showed the full unfiltered
// VIDEO_MODELS list for Motion Control mode, and
// normalizeVideoStateForModel()'s Motion Control force-switch still keyed
// off video_effects (a Kling-effects-catalog flag, true only for
// kling_effects) rather than actual motion_control support - exactly the
// bug Batch 6 fixed for Edit mode, left deliberately untouched for Motion
// Control at the time since this batch was its own separate, later
// roadmap step.
//
// videoModelSupportsMotionControl() mirrors videoModelSupportsEdit()'s
// final, accepted shape exactly (see test_video_edit_mode_model_filter.mjs
// for that history): modes.includes('motion_control') against the fetched
// capability registry's modes array, falling back to the local
// VIDEO_MODEL_CONFIG modes array only when no fetched data has loaded yet.
// kling_o3_omni remains the fixed fallback for an incompatible model in
// both Edit and Motion Control sections - an unconditional exemption from
// the capability check, not re-verified (the stricter alternative was
// proposed and explicitly rejected for Edit mode, so it is not introduced
// here either).
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

// Same combined VIDEO_MODEL_CONFIG + Object.assign(VIDEO_MODEL_CONFIG, {...})
// (Kling entries) extraction as tests/test_video_end_frame_capability_repoint.mjs.
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

// Video models whose real modes array includes 'motion_control' and are
// actually reachable via VIDEO_MODELS today. Unlike video_edit, no
// boolean-vs-modes mismatch exists for motion_control in the current data
// (verified: every model with motion_control:true also has
// 'motion_control' in its modes array, and vice versa).
const MOTION_CONTROL_CAPABLE_MODELS = new Set([
  'kling_motion_3_0', 'kling_o3_omni', 'kling_motion_2_6',
]);

function buildModelListContext() {
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: {modelId: 'seedance_2_fast', section: 'generate'},
    S: {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext('function isImageMode(){return false;} function isVideoMode(){return true;} function isMusicMode(){return false;} function isVoiceMode(){return false;} var studioMode="video";', context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  vm.runInContext(extractFunction('currentComposerModelList'), context);
  return context;
}

test('currentComposerModelList: motion section returns only genuinely motion-control-capable models', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "motion";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.deepEqual(new Set(ids), MOTION_CONTROL_CAPABLE_MODELS);
});

test('currentComposerModelList: motion section excludes models without motion_control support', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "motion";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(!ids.includes('sora_2'), 'sora_2 must not appear in the Motion Control picker');
  assert.ok(!ids.includes('grok_video_edit'), 'grok_video_edit (video_edit-only) must not appear in the Motion Control picker');
  assert.ok(!ids.includes('seedance_2_fast'), 'seedance_2_fast must not appear in the Motion Control picker');
});

test('currentComposerModelList: edit section is unaffected by the Motion Control filter', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "edit";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  // Edit mode's own set, unchanged by this batch - spot-check a couple of
  // representative ids rather than the full set (already covered by
  // test_video_edit_mode_model_filter.mjs).
  assert.ok(ids.includes('grok_video_edit'));
  assert.ok(!ids.includes('kling_motion_2_6'), 'kling_motion_2_6 (motion-only, video_edit:false) must not appear in the Edit picker');
});

test('currentComposerModelList: generate section returns the full unfiltered VIDEO_MODELS list', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "generate";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  const allVideoModelIds = vm.runInContext('VIDEO_MODELS.map((m) => m.id)', context);
  assert.deepEqual(ids.sort(), allVideoModelIds.sort());
});

test('videoModelSupportsMotionControl: fetched registry modes array overrides the local modes array', () => {
  const context = buildModelListContext();
  // sora_2's local modes don't include motion_control - simulate the
  // fetched registry saying it does, and confirm the fetched value wins
  // (same fail-open-by-override pattern as Batch 3/4's currentVideoConfig()
  // repoint). Conversely, override kling_motion_2_6 (locally
  // motion-control-capable) to a fetched modes array that drops
  // motion_control, and confirm the fetched value wins there too - proving
  // this is a real override, not just an OR of local-and-fetched.
  vm.runInContext(`fetchedModelCapabilities = {version: 'v1', models: {
    sora_2: {modes: ['text_to_video', 'motion_control']},
    kling_motion_2_6: {modes: ['text_to_video']},
  }};`, context);
  assert.equal(vm.runInContext(`videoModelSupportsMotionControl('sora_2')`, context), true);
  assert.equal(vm.runInContext(`videoModelSupportsMotionControl('kling_motion_2_6')`, context), false);
});

test('videoModelSupportsMotionControl: falls back to local VIDEO_MODEL_CONFIG.modes when no fetched data', () => {
  const context = buildModelListContext();
  assert.equal(vm.runInContext(`videoModelSupportsMotionControl('kling_motion_2_6')`, context), true);
  assert.equal(vm.runInContext(`videoModelSupportsMotionControl('sora_2')`, context), false);
});

function buildNormalizeContext(modelId, section) {
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: {modelId, section, duration: 5, ratio: '16:9', resolution: '720p'},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  vm.runInContext(extractFunction('normalizeVideoStateForModel'), context);
  vm.runInContext('normalizeVideoStateForModel();', context);
  return vm.runInContext('videoState.modelId', context);
}

test('normalizeVideoStateForModel: motion section keeps a genuinely motion-control-capable model (the core fix)', () => {
  assert.equal(buildNormalizeContext('kling_motion_2_6', 'motion'), 'kling_motion_2_6');
  assert.equal(buildNormalizeContext('kling_motion_3_0', 'motion'), 'kling_motion_3_0');
});

test('normalizeVideoStateForModel: motion section still force-switches a motion-control-unsupported model', () => {
  assert.equal(buildNormalizeContext('sora_2', 'motion'), 'kling_o3_omni');
  assert.equal(buildNormalizeContext('grok_video_edit', 'motion'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: motion section keeps kling_o3_omni selected (fixed fallback, not re-verified)', () => {
  assert.equal(buildNormalizeContext('kling_o3_omni', 'motion'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: edit section behavior is unaffected by this batch (regression check)', () => {
  assert.equal(buildNormalizeContext('grok_video_edit', 'edit'), 'grok_video_edit');
  assert.equal(buildNormalizeContext('sora_2', 'edit'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: generate section is entirely unrestricted', () => {
  assert.equal(buildNormalizeContext('sora_2', 'generate'), 'sora_2');
});

test('fetched capability override: Motion Control picker filter and force-switch agree (the required cross-check)', () => {
  // Build one combined context exercising both currentComposerModelList()
  // and normalizeVideoStateForModel() against the same
  // fetchedModelCapabilities object - proving they derive from the same
  // shared videoModelSupportsMotionControl() function and cannot disagree.
  // sora_2 is locally motion_control-unsupported; override the fetched
  // registry to say it now supports motion_control, and confirm BOTH the
  // picker includes it AND the force-switch lets it survive being picked.
  const sandbox = {
    fetchedModelCapabilities: {version: 'v1', models: {sora_2: {modes: ['text_to_video', 'motion_control']}}},
    videoState: {modelId: 'sora_2', section: 'motion', duration: 5, ratio: '16:9', resolution: '720p'},
    S: {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext('function isImageMode(){return false;} function isVideoMode(){return true;} function isMusicMode(){return false;} function isVoiceMode(){return false;} var studioMode="video";', context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  vm.runInContext(extractFunction('currentComposerModelList'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('normalizeVideoStateForModel'), context);

  const pickerIds = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(pickerIds.includes('sora_2'), 'picker must include sora_2 once the fetched registry says it supports motion_control');

  vm.runInContext('normalizeVideoStateForModel();', context);
  const modelIdAfterNormalize = vm.runInContext('videoState.modelId', context);
  assert.equal(modelIdAfterNormalize, 'sora_2', 'force-switch must not revert a model the fetched registry says supports motion_control');
});
