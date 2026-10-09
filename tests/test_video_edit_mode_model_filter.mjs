// Run with: node --test tests/test_video_edit_mode_model_filter.mjs
//
// Regression tests for Phase 1 Batch 6 of the Pro Studio master
// remediation plan (see /root/.claude/plans/splendid-moseying-starlight.md,
// roadmap step 6): "Video Edit mode model-picker filtering". Before this
// batch, currentComposerModelList() returned the full unfiltered VIDEO_MODELS
// list regardless of videoState.section, so every video model appeared in
// the picker even while composing a Video Edit request.
//
// A second fix landed alongside the filter: normalizeVideoStateForModel()'s
// force-switch-to-kling_o3_omni used to key off video_effects (a
// Kling-effects-catalog flag, true only for kling_effects) for BOTH Edit
// and Motion Control sections - since no other model ever sets
// video_effects, picking ANY model other than kling_o3_omni while in
// Edit/Motion sections snapped it straight back. Without narrowing this to
// check the picked model's own Video Edit support for the Edit section
// specifically, the picker filter would have been a no-op. Motion
// Control's own force-switch is deliberately left unchanged (still keyed
// off video_effects) since Motion Control's own picker filtering is a
// separate, later roadmap step (7).
//
// Correction (second pass, per review): two capability-consistency issues
// in the first version of this batch:
// 1. normalizeVideoStateForModel() read previousConfig.video_edit directly
//    instead of calling videoModelSupportsEdit() - the exact function the
//    picker filter itself calls - so the two could independently drift
//    from the fetched capability registry. Fixed: both now call
//    videoModelSupportsEdit(videoState.modelId).
// 2. videoModelSupportsEdit() classified support from the legacy
//    video_edit boolean alone, which is insufficient: kling_motion_3_0
//    declares video_edit:true but its real modes are only
//    ['motion_control'] - no actual video_edit mode exists for it. Fixed:
//    the check is now modes.includes('video_edit') against the fetched
//    registry's modes array, falling back to the local VIDEO_MODEL_CONFIG
//    modes array only when no fetched data has loaded yet.
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

// Video models whose real modes array includes 'video_edit' and are
// actually reachable via VIDEO_MODELS today (excludes orphaned ids like
// runway_seedance2* / runway_gemini_omni_flash / kling_lip_sync, which
// have video_edit in their modes but are absent from VIDEO_MODELS
// entirely). kling_motion_3_0 is deliberately NOT in this set - it
// declares video_edit:true as a boolean but its modes are only
// ['motion_control'], so the modes-based check correctly excludes it.
const VIDEO_EDIT_CAPABLE_MODELS = new Set([
  'luma_ray_v3_2', 'grok_video_edit', 'wan_2_7_edit', 'runway_aleph2',
  'runway_aleph', 'gemini_omni_flash', 'kling_o3_omni', 'kling_o3_edit',
  'kling_o1',
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

test('currentComposerModelList: generate section returns the full unfiltered VIDEO_MODELS list', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "generate";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  const allVideoModelIds = vm.runInContext('VIDEO_MODELS.map((m) => m.id)', context);
  assert.deepEqual(ids.sort(), allVideoModelIds.sort());
});

test('currentComposerModelList: edit section returns only genuinely video_edit-mode-capable models', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "edit";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.deepEqual(new Set(ids), VIDEO_EDIT_CAPABLE_MODELS);
});

test('currentComposerModelList: edit section excludes a model with video_edit:false', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "edit";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(!ids.includes('sora_2'), 'sora_2 (video_edit:false) must not appear in the Edit mode picker');
  assert.ok(!ids.includes('seedance_2_fast'), 'seedance_2_fast (video_edit:false) must not appear in the Edit mode picker');
});

test('currentComposerModelList: edit section excludes kling_motion_3_0 despite its video_edit:true boolean', () => {
  // The core correction: kling_motion_3_0's modes are only
  // ['motion_control'] - no real video_edit mode exists for it, so the
  // modes-based check must exclude it even though the legacy boolean says
  // video_edit:true.
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "edit";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(!ids.includes('kling_motion_3_0'), 'kling_motion_3_0 must not appear in the Edit mode picker');
});

test('currentComposerModelList: motion section is now filtered too (Batch 7 landed) - spot-check only, see test_motion_control_mode_model_filter.mjs for full coverage', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "motion";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(ids.includes('kling_motion_2_6'));
  assert.ok(!ids.includes('sora_2'), 'Motion Control mode filtering shipped in Batch 7 - this list is no longer the full unfiltered VIDEO_MODELS set');
});

test('videoModelSupportsEdit: kling_motion_3_0 is false despite its legacy video_edit:true boolean', () => {
  const context = buildModelListContext();
  assert.equal(vm.runInContext(`videoModelSupportsEdit('kling_motion_3_0')`, context), false);
});

test('videoModelSupportsEdit: fetched registry modes array overrides the local modes array', () => {
  const context = buildModelListContext();
  // sora_2's local modes don't include video_edit - simulate the fetched
  // registry saying it does, and confirm the fetched value wins (same
  // fail-open-by-override pattern as Batch 3/4's currentVideoConfig()
  // repoint). Conversely, override kling_o3_omni (locally video_edit-
  // capable) to a fetched modes array that drops video_edit, and confirm
  // the fetched value wins there too - proving this is a real override,
  // not just an OR of local-and-fetched.
  vm.runInContext(`fetchedModelCapabilities = {version: 'v1', models: {
    sora_2: {modes: ['text_to_video', 'video_edit']},
    kling_o3_omni: {modes: ['text_to_video']},
  }};`, context);
  assert.equal(vm.runInContext(`videoModelSupportsEdit('sora_2')`, context), true);
  assert.equal(vm.runInContext(`videoModelSupportsEdit('kling_o3_omni')`, context), false);
});

test('videoModelSupportsEdit: falls back to local VIDEO_MODEL_CONFIG.modes when no fetched data', () => {
  const context = buildModelListContext();
  assert.equal(vm.runInContext(`videoModelSupportsEdit('grok_video_edit')`, context), true);
  assert.equal(vm.runInContext(`videoModelSupportsEdit('sora_2')`, context), false);
});

function buildNormalizeContext(modelId, section, fetchedOverride) {
  const sandbox = {
    fetchedModelCapabilities: fetchedOverride || null,
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

test('normalizeVideoStateForModel: edit section keeps a genuinely video_edit-capable model (the core fix)', () => {
  assert.equal(buildNormalizeContext('grok_video_edit', 'edit'), 'grok_video_edit');
  assert.equal(buildNormalizeContext('kling_o1', 'edit'), 'kling_o1');
  assert.equal(buildNormalizeContext('wan_2_7_edit', 'edit'), 'wan_2_7_edit');
});

test('normalizeVideoStateForModel: edit section still force-switches a video_edit-unsupported model', () => {
  assert.equal(buildNormalizeContext('sora_2', 'edit'), 'kling_o3_omni');
  assert.equal(buildNormalizeContext('seedance_2_fast', 'edit'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: edit section force-switches kling_motion_3_0 despite its legacy video_edit:true boolean', () => {
  assert.equal(buildNormalizeContext('kling_motion_3_0', 'edit'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: motion section now also uses the capability check (Batch 7 landed) - spot-check only, see test_motion_control_mode_model_filter.mjs for full coverage', () => {
  // kling_motion_2_6 genuinely supports motion_control - Batch 7 fixed
  // Motion Control's own force-switch, so it now survives selection
  // instead of being forced to kling_o3_omni (the old, pre-Batch-7 bug
  // this repo used to have).
  assert.equal(buildNormalizeContext('kling_motion_2_6', 'motion'), 'kling_motion_2_6');
  assert.equal(buildNormalizeContext('kling_o3_omni', 'motion'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: generate section is entirely unrestricted', () => {
  assert.equal(buildNormalizeContext('sora_2', 'generate'), 'sora_2');
});

// --- Fix regression test: picker and force-switch must derive from the
// --- same capability decision and can never disagree ----------------------

test('fetched capability override: picker filter and force-switch agree for every video model (the required cross-check)', () => {
  // Build one combined context that exercises both currentComposerModelList()
  // and normalizeVideoStateForModel() against the same fetchedModelCapabilities
  // object - the exact scenario the fix's shared videoModelSupportsEdit()
  // helper exists to guarantee. seedance_2_fast is locally video_edit:false;
  // override the fetched registry to say it now supports video_edit, and
  // confirm BOTH the picker includes it AND the force-switch lets it
  // survive being picked, proving they agree because they call the same
  // function rather than independently-drifting checks.
  const sandbox = {
    fetchedModelCapabilities: {version: 'v1', models: {seedance_2_fast: {modes: ['text_to_video', 'video_edit']}}},
    videoState: {modelId: 'seedance_2_fast', section: 'edit', duration: 5, ratio: '16:9', resolution: '720p'},
    S: {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext('function isImageMode(){return false;} function isVideoMode(){return true;} function isMusicMode(){return false;} function isVoiceMode(){return false;} var studioMode="video";', context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('currentComposerModelList'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('normalizeVideoStateForModel'), context);

  const pickerIds = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  assert.ok(pickerIds.includes('seedance_2_fast'), 'picker must include seedance_2_fast once the fetched registry says it supports video_edit');

  vm.runInContext('normalizeVideoStateForModel();', context);
  const modelIdAfterNormalize = vm.runInContext('videoState.modelId', context);
  assert.equal(modelIdAfterNormalize, 'seedance_2_fast', 'force-switch must not revert a model the fetched registry says supports video_edit');
});
