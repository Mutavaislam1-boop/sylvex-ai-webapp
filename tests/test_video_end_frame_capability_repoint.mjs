// Run with: node --test tests/test_video_end_frame_capability_repoint.mjs
//
// Regression tests for Phase 1 Batch 3 of the Pro Studio master remediation
// plan (see /root/.claude/plans/splendid-moseying-starlight.md, roadmap
// step 3): currentVideoConfig() now prefers the fetched capability
// registry's start_frame/end_frame over the local, independently-
// hand-maintained VIDEO_MODEL_CONFIG mirror, so the End Frame button
// (renderVideoStartPreview/renderVideoEndPreview) and
// normalizeVideoStateForModel()'s stale-state clearing - both of which
// read through currentVideoConfig() - inherit a single Python-sourced
// source of truth instead of the JS-side copy that can drift from it.
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

// VIDEO_MODEL_CONFIG's Kling entries (plus the KLING_VIDEO_* duration/ratio/
// resolution const arrays those entries reference) are added via a separate
// Object.assign(VIDEO_MODEL_CONFIG, {...}) call further down the file (same
// pattern as the Python-side VIDEO_MODEL_CONFIG.update({...}) for Kling).
// Capture everything from the start of VIDEO_MODEL_CONFIG through the end
// of that Object.assign call as one block so the const arrays it depends on
// come along with it, or every kling_* lookup would be undefined/throw.
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

test('currentVideoConfig: with no fetched data, returns the local VIDEO_MODEL_CONFIG entry unchanged', () => {
  // kling_o3_omni has start_image:true, end_image:true locally.
  const context = buildContext('kling_o3_omni');
  const result = vm.runInContext(`currentVideoConfig()`, context);
  const plain = toPlain(result);
  assert.equal(plain.start_image, true);
  assert.equal(plain.end_image, true);
  assert.equal(plain.provider, 'kling');
});

test('currentVideoConfig: fetched data overrides start_image/end_image, local drift is corrected', () => {
  // Simulate the exact JS-vs-Python VIDEO_MODEL_CONFIG mirror-drift this
  // repoint exists to fix: local JS says end_image true, fetched (Python-
  // sourced) registry says false - fetched must win.
  const context = buildContext('kling_o3_omni');
  withVideoCapabilities(context, 'kling_o3_omni', {start_frame: true, end_frame: false});
  const result = vm.runInContext(`currentVideoConfig()`, context);
  const plain = toPlain(result);
  assert.equal(plain.start_image, true);
  assert.equal(plain.end_image, false);
});

test('currentVideoConfig: fetched entry for a different model does not affect the current one (fail open per-model)', () => {
  const context = buildContext('sora_2');
  withVideoCapabilities(context, 'kling_o3_omni', {start_frame: true, end_frame: true});
  const result = vm.runInContext(`currentVideoConfig()`, context);
  const plain = toPlain(result);
  // sora_2 has no fetched entry of its own - falls back to local, which
  // declares end_image:false for sora_2.
  assert.equal(plain.end_image, false);
});

test('currentVideoConfig: preserves other local fields (modes/durations/provider) untouched by the fetch', () => {
  const context = buildContext('seedance_2_fast');
  withVideoCapabilities(context, 'seedance_2_fast', {start_frame: true, end_frame: false});
  const result = vm.runInContext(`currentVideoConfig()`, context);
  const plain = toPlain(result);
  assert.equal(plain.provider, 'bytedance');
  assert.deepEqual(plain.durations, [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
});
