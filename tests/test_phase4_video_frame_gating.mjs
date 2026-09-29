// Run with: node --test tests/test_phase4_video_frame_gating.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 4 fix: video
// start/end frame state must be cleared when switching to a model that
// doesn't support it, and the composer's Start/End Frame cards must be
// hidden for such models. Uses the same node:vm extraction pattern as
// tests/test_miniapp_sylvex_test.mjs to run the real cabinet.js functions
// without booting the whole app.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

// Extract a top-level `function name(...) { ... }` or `const NAME = { ... };`
// / `const NAME = [ ... ];` block by brace-matching from its declaration.
function extract(name, kind = 'function') {
  const pattern = kind === 'function'
    ? new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm')
    : new RegExp(`^const ${name} = [\\[{]`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = kind === 'function' ? cabinet.indexOf('{', match.index) : match.index + match[0].length - 1;
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{' || cabinet[i] === '[') depth++;
    else if (cabinet[i] === '}' || cabinet[i] === ']') {
      depth--;
      if (depth === 0) break;
    }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(match.index, i + 1) + (kind === 'function' ? '' : ';');
}

// VIDEO_MODEL_CONFIG's base entries are declared as one object literal, but
// the kling_* entries are merged in afterwards via a separate
// `Object.assign(VIDEO_MODEL_CONFIG, {...})` call that also depends on a
// handful of KLING_VIDEO_* array constants declared in between - extract
// that whole span by line range (found once, matches the file as committed)
// rather than trying to brace-match across a declaration + a later mutation.
function videoModelConfigWithKlingSource() {
  const lines = cabinet.split('\n');
  const startLine = lines.findIndex((l) => /^const VIDEO_MODEL_CONFIG = \{/.test(l));
  assert.ok(startLine >= 0, 'VIDEO_MODEL_CONFIG declaration not found');
  let end = startLine;
  let sawAssign = false;
  for (let i = startLine; i < lines.length; i++) {
    if (/^Object\.assign\(VIDEO_MODEL_CONFIG,/.test(lines[i])) sawAssign = true;
    if (sawAssign && /^\}\);/.test(lines[i])) { end = i; break; }
  }
  assert.ok(end > startLine, 'Object.assign(VIDEO_MODEL_CONFIG, ...) close not found');
  return lines.slice(startLine, end + 1).join('\n');
}

function makeContext() {
  const context = vm.createContext({console});
  vm.runInContext(videoModelConfigWithKlingSource(), context);
  vm.runInContext('var videoState = {};', context);
  vm.runInContext(extract('currentVideoConfig'), context);
  vm.runInContext(extract('normalizeVideoStateForModel'), context);
  return context;
}

test('normalizeVideoStateForModel clears startImage when the new model does not support it', () => {
  const context = makeContext();
  // heygen_v3_video_agent declares start_image:false.
  vm.runInContext(`
    videoState.modelId = 'heygen_v3_video_agent';
    videoState.startImage = 'https://x.test/stale-start.png';
    videoState.section = 'generate';
    videoState.generationMode = 'text_to_video';
    videoState.duration = 5;
    videoState.ratio = '16:9';
    videoState.resolution = '720p';
    normalizeVideoStateForModel();
  `, context);
  assert.equal(vm.runInContext('videoState.startImage', context), '');
});

test('normalizeVideoStateForModel clears endImage when the new model does not support it', () => {
  const context = makeContext();
  // seedance_2_fast declares end_image:false.
  vm.runInContext(`
    videoState.modelId = 'seedance_2_fast';
    videoState.endImage = 'https://x.test/stale-end.png';
    videoState.section = 'generate';
    videoState.generationMode = 'text_to_video';
    videoState.duration = 5;
    videoState.ratio = '16:9';
    videoState.resolution = '720p';
    normalizeVideoStateForModel();
  `, context);
  assert.equal(vm.runInContext('videoState.endImage', context), '');
});

test('normalizeVideoStateForModel keeps startImage/endImage for a model that supports both', () => {
  const context = makeContext();
  // kling_3_0 declares both start_image:true and end_image:true.
  vm.runInContext(`
    videoState.modelId = 'kling_3_0';
    videoState.startImage = 'https://x.test/start.png';
    videoState.endImage = 'https://x.test/end.png';
    videoState.section = 'generate';
    videoState.generationMode = 'text_to_video';
    videoState.duration = 5;
    videoState.ratio = '16:9';
    videoState.resolution = '720p';
    normalizeVideoStateForModel();
  `, context);
  assert.equal(vm.runInContext('videoState.startImage', context), 'https://x.test/start.png');
  assert.equal(vm.runInContext('videoState.endImage', context), 'https://x.test/end.png');
});

test('normalizeVideoStateForModel keeps startImage but clears endImage when only start is supported', () => {
  const context = makeContext();
  // seedance_2_fast: start_image:true, end_image:false.
  vm.runInContext(`
    videoState.modelId = 'seedance_2_fast';
    videoState.startImage = 'https://x.test/start.png';
    videoState.endImage = 'https://x.test/end.png';
    videoState.section = 'generate';
    videoState.generationMode = 'text_to_video';
    videoState.duration = 5;
    videoState.ratio = '16:9';
    videoState.resolution = '720p';
    normalizeVideoStateForModel();
  `, context);
  assert.equal(vm.runInContext('videoState.startImage', context), 'https://x.test/start.png');
  assert.equal(vm.runInContext('videoState.endImage', context), '');
});

test('renderVideoStartPreview and renderVideoEndPreview hide the card when unsupported', () => {
  const context = vm.createContext({console});
  vm.runInContext(videoModelConfigWithKlingSource(), context);
  vm.runInContext('var videoState = {};', context);
  vm.runInContext(extract('currentVideoConfig'), context);
  const startCard = {hidden: false, querySelector: () => null};
  const endCard = {hidden: false, querySelector: () => null};
  context.document = {getElementById: (id) => (id === 'videoStartFrameCard' ? startCard : id === 'videoEndFrameCard' ? endCard : null)};
  context.setFramePreview = () => {};
  vm.runInContext(extract('renderVideoStartPreview'), context);
  vm.runInContext(extract('renderVideoEndPreview'), context);

  // heygen_v3_video_agent: neither start nor end image supported.
  vm.runInContext(`videoState.modelId = 'heygen_v3_video_agent'; renderVideoStartPreview(); renderVideoEndPreview();`, context);
  assert.equal(startCard.hidden, true);
  assert.equal(endCard.hidden, true);

  // kling_3_0: both supported.
  vm.runInContext(`videoState.modelId = 'kling_3_0'; renderVideoStartPreview(); renderVideoEndPreview();`, context);
  assert.equal(startCard.hidden, false);
  assert.equal(endCard.hidden, false);
});
