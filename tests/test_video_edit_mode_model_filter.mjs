// Run with: node --test tests/test_video_edit_mode_model_filter.mjs
//
// Regression tests for Phase 1 Batch 6 of the Pro Studio master
// remediation plan (see /root/.claude/plans/splendid-moseying-starlight.md,
// roadmap step 6): "Video Edit mode model-picker filtering". Before this
// batch, currentComposerModelList() returned the full unfiltered VIDEO_MODELS
// list regardless of videoState.section, so every video model appeared in
// the picker even while composing a Video Edit request, even though only
// a handful of models declare video_edit:true in VIDEO_MODEL_CONFIG.
//
// A second, more important fix landed alongside the filter:
// normalizeVideoStateForModel()'s force-switch-to-kling_o3_omni used to key
// off video_effects (a Kling-effects-catalog flag, true only for
// kling_effects) for BOTH Edit and Motion Control sections - since no other
// model ever sets video_effects, picking ANY model other than kling_o3_omni
// while in Edit/Motion sections snapped it straight back. Without narrowing
// this to check the picked model's own video_edit support for the Edit
// section specifically, the new picker filter would have been a no-op: a
// user could pick e.g. grok_video_edit from the filtered list, and it would
// immediately revert to kling_o3_omni. Motion Control's own force-switch is
// deliberately left unchanged (still keyed off video_effects) since Motion
// Control's own picker filtering is a separate, later roadmap step (7).
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

// Video models that declare video_edit:true in VIDEO_MODEL_CONFIG and are
// actually reachable via VIDEO_MODELS today (excludes orphaned ids like
// runway_seedance2* / runway_gemini_omni_flash / kling_lip_sync, which are
// video_edit:true in the config but absent from VIDEO_MODELS entirely).
const VIDEO_EDIT_CAPABLE_MODELS = new Set([
  'luma_ray_v3_2', 'grok_video_edit', 'wan_2_7_edit', 'runway_aleph2',
  'runway_aleph', 'gemini_omni_flash', 'kling_motion_3_0', 'kling_o3_omni',
  'kling_o3_edit', 'kling_o1',
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
  vm.runInContext('function sylvexTestModeAvailable(){return !!(S && S.user && S.user.sylvex_test_available);} function filterSylvexTestEntries(list){if(sylvexTestModeAvailable())return list;return (list||[]).filter((item)=>!(item&&item.sylvexTest));}', context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('currentComposerModelList'), context);
  return context;
}

test('currentComposerModelList: generate section returns the full unfiltered VIDEO_MODELS list', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "generate";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  const allVideoModelIds = vm.runInContext('VIDEO_MODELS.map((m) => m.id)', context).filter((id) => id !== 'sylvex_test');
  assert.deepEqual(ids.sort(), allVideoModelIds.sort());
});

test('currentComposerModelList: edit section returns only video_edit-capable models', () => {
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

test('currentComposerModelList: motion section is unaffected (step 7 is a separate batch)', () => {
  const context = buildModelListContext();
  vm.runInContext('videoState.section = "motion";', context);
  const ids = vm.runInContext('currentComposerModelList().map((m) => m.id)', context);
  const allVideoModelIds = vm.runInContext('VIDEO_MODELS.map((m) => m.id)', context).filter((id) => id !== 'sylvex_test');
  assert.deepEqual(ids.sort(), allVideoModelIds.sort());
});

test('videoModelSupportsEdit: fetched registry video_input overrides the local video_edit value', () => {
  const context = buildModelListContext();
  // sora_2 declares video_edit:false locally - simulate the registry
  // saying true, and confirm the fetched value wins (fail-open-by-override
  // pattern established by Batch 3/4's currentVideoConfig() repoint).
  vm.runInContext(`fetchedModelCapabilities = {version: 'v1', models: {sora_2: {video_input: true}}};`, context);
  const result = vm.runInContext(`videoModelSupportsEdit('sora_2')`, context);
  assert.equal(result, true);
});

test('videoModelSupportsEdit: falls back to local VIDEO_MODEL_CONFIG.video_edit when no fetched data', () => {
  const context = buildModelListContext();
  assert.equal(vm.runInContext(`videoModelSupportsEdit('grok_video_edit')`, context), true);
  assert.equal(vm.runInContext(`videoModelSupportsEdit('sora_2')`, context), false);
});

function buildNormalizeContext(modelId, section) {
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: {modelId, section, duration: 5, ratio: '16:9', resolution: '720p'},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
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

test('normalizeVideoStateForModel: motion section behavior is unchanged (still forces non-kling_o3_omni models)', () => {
  // kling_motion_2_6 genuinely supports motion_control, but Motion
  // Control's own force-switch fix is roadmap step 7, not this batch - it
  // must still be forced to kling_o3_omni today, exactly as before.
  assert.equal(buildNormalizeContext('kling_motion_2_6', 'motion'), 'kling_o3_omni');
  assert.equal(buildNormalizeContext('kling_o3_omni', 'motion'), 'kling_o3_omni');
});

test('normalizeVideoStateForModel: generate section is entirely unrestricted', () => {
  assert.equal(buildNormalizeContext('sora_2', 'generate'), 'sora_2');
});
