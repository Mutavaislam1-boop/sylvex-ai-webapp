// Run with: node --test tests/test_video_sound_capability_repoint.mjs
//
// Regression tests for Phase 1 Batch 4 of the Pro Studio master remediation
// plan (see /root/.claude/plans/splendid-moseying-starlight.md, roadmap
// step 4): currentVideoConfig() now also prefers the fetched capability
// registry's sound_toggle over the local, independently-hand-maintained
// VIDEO_MODEL_CONFIG mirror - the same pattern Batch 3 established for
// start_image/end_image. Every consumer of currentVideoConfig().sound
// (normalizeVideoStateForModel, renderVideoControls, pickVideoOption, the
// openImageOptionMenu 'sound' gate) reads through this single function, so
// repointing it here alone fixes all of them.
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

function toPlain(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value));
}

function buildContext(modelId) {
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: {modelId: modelId || 'seedance_2_fast'},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  return context;
}

function withVideoCapabilities(context, modelId, entry) {
  vm.runInContext(
    `fetchedModelCapabilities = {version: 'v1', models: {${JSON.stringify(modelId)}: ${JSON.stringify(entry)}}};`,
    context
  );
}

test('currentVideoConfig: with no fetched data, returns the local VIDEO_MODEL_CONFIG sound value unchanged', () => {
  // veo_3_1 declares sound:true locally.
  const context = buildContext('veo_3_1');
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.sound, true);
});

test('currentVideoConfig: fetched sound_toggle overrides local, local drift is corrected', () => {
  // Simulate the exact JS-vs-Python VIDEO_MODEL_CONFIG mirror-drift this
  // repoint exists to fix: local JS says sound true, fetched (Python-
  // sourced) registry says false - fetched must win.
  const context = buildContext('veo_3_1');
  withVideoCapabilities(context, 'veo_3_1', {sound_toggle: false});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.sound, false);
});

test('currentVideoConfig: fetched sound_toggle can also turn sound on for a locally-false model', () => {
  // sora_2 declares sound:false locally.
  const context = buildContext('sora_2');
  withVideoCapabilities(context, 'sora_2', {sound_toggle: true});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.sound, true);
});

test('currentVideoConfig: fetched entry for a different model does not affect the current one (fail open per-model)', () => {
  const context = buildContext('sora_2');
  withVideoCapabilities(context, 'veo_3_1', {sound_toggle: true});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  // sora_2 has no fetched entry of its own - falls back to local, which
  // declares sound:false for sora_2.
  assert.equal(result.sound, false);
});

test('currentVideoConfig: sound repoint composes with the existing start_image/end_image (Batch 3) repoint', () => {
  const context = buildContext('kling_o3_omni');
  withVideoCapabilities(context, 'kling_o3_omni', {start_frame: true, end_frame: false, sound_toggle: false});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.start_image, true);
  assert.equal(result.end_image, false);
  assert.equal(result.sound, false);
});

test('currentVideoConfig: preserves other local fields untouched by the sound repoint', () => {
  const context = buildContext('seedance_2_fast');
  withVideoCapabilities(context, 'seedance_2_fast', {sound_toggle: true});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.provider, 'bytedance');
  assert.deepEqual(result.durations, [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
});

test('currentVideoConfig: native_audio is not exposed/overridden by this batch (only sound_toggle is read)', () => {
  // kling_2_6 declares native_audio:true locally - the repoint must not
  // touch or derive a "native_audio" field on the returned config, since
  // that axis is deliberately left alone (Kling-cost-tier-only, used via
  // videoOptionsPayload's own config.native_audio && videoState.sound
  // computation, unaffected by currentVideoConfig()).
  const context = buildContext('kling_2_6');
  withVideoCapabilities(context, 'kling_2_6', {sound_toggle: true});
  const result = toPlain(vm.runInContext('currentVideoConfig()', context));
  assert.equal(result.native_audio, true); // still the local value, untouched
});
