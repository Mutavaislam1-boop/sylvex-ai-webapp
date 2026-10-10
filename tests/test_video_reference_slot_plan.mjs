// Run with: node --test tests/test_video_reference_slot_plan.mjs
//
// Video reference inputs must reach the provider or be explicitly reported.
// videoOptionsPayload() applies the registry's reference_inputs slots
// (services/model_capabilities.py) and lists anything it could not send in
// reference_inputs_dropped; the send path toasts videoDroppedReferenceNotice().
// Reference-video upload limits come from the same registry entry, so Kling
// Motion Control gets its own 3-30 s limit instead of the Omni 3-15.5 s one.
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
  return cabinet.slice(match.index, i + 1);
}

const plain = (value) => JSON.parse(JSON.stringify(value));

function buildContext(videoState, entry, extra = {}) {
  const sandbox = Object.assign({
    fetchedModelCapabilities: entry ? {version: 'v1', models: {[videoState.modelId]: entry}} : null,
    videoState,
    normalizeVideoStateForModel: () => {},
    currentVideoConfig: () => ({}),
    currentVideoReferenceImages: () => [],
    currentVideoEditInputUrl: () => '',
    currentVideoReferenceUrl: () => '',
  }, extra);
  const context = vm.createContext(sandbox);
  for (const name of ['getVideoModelCapabilities', 'videoOptionsPayload', 'videoDroppedReferenceNotice', 'referenceVideoMetadataError']) {
    vm.runInContext(extractFunction(name), context);
  }
  return context;
}

const DEGRADED = {
  character: {text_conditioning: true, visual_reference: {visual_mode: 'degraded_single_image', max_count: 1}},
  object: {text_conditioning: true, visual_reference: {visual_mode: 'degraded_single_image', max_count: 1}},
};
const NONE = {
  character: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
  object: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
};

test('Kling with a start frame: character image is not sent and is reported, name still flows', () => {
  const state = {modelId: 'kling_3_0', startImage: 'https://x/start.png', advanced: {},
    characterVisual: {id: 'c1', name: 'Ann', references: ['https://x/c.png']}, objectVisual: null, referenceVisual: null};
  const entry = Object.assign({reference_inputs: {image_slots: 1, start_frame_uses_image_slot: true, accepts_video: false}}, DEGRADED);
  const payload = plain(vm.runInContext('videoOptionsPayload()', buildContext(state, entry)));
  assert.equal(payload.start_image, 'https://x/start.png');
  assert.deepEqual(payload.characterReferences, []);
  assert.equal(payload.characterName, 'Ann');
  assert.deepEqual(payload.reference_inputs_dropped, ['character_images']);
});

test('Kling without a start frame: the single character image is sent', () => {
  const state = {modelId: 'kling_3_0', startImage: '', advanced: {},
    characterVisual: {id: 'c1', name: 'Ann', references: ['https://x/c.png']}, objectVisual: null, referenceVisual: null};
  const entry = Object.assign({reference_inputs: {image_slots: 1, start_frame_uses_image_slot: true, accepts_video: false}}, DEGRADED);
  const payload = plain(vm.runInContext('videoOptionsPayload()', buildContext(state, entry)));
  assert.deepEqual(payload.characterReferences, ['https://x/c.png']);
  assert.deepEqual(payload.reference_inputs_dropped, []);
});

test('model without reference slots or video input: uploaded refs and stale video are not sent and are reported', () => {
  const state = {modelId: 'runway_gen4_5', startImage: 'https://x/start.png', advanced: {}, characterVisual: null, objectVisual: null, referenceVisual: null};
  const entry = Object.assign({reference_inputs: {image_slots: 0, start_frame_uses_image_slot: false, accepts_video: false}}, NONE);
  const context = buildContext(state, entry, {
    currentVideoReferenceImages: () => ['https://x/u.png'],
    currentVideoEditInputUrl: () => 'https://x/stale.mp4',
  });
  const payload = plain(vm.runInContext('videoOptionsPayload()', context));
  assert.deepEqual(payload.reference_images, []);
  assert.equal(payload.input_video, '');
  assert.equal(payload.video_url, '');
  assert.deepEqual(payload.reference_inputs_dropped, ['reference_images', 'video']);
  const notice = vm.runInContext(`videoDroppedReferenceNotice(${JSON.stringify(payload.reference_inputs_dropped)})`, context);
  assert.match(notice, /референс-фото/);
  assert.match(notice, /референс-видео/);
});

test('no capability data loaded: payload unchanged and nothing reported', () => {
  const state = {modelId: 'kling_3_0', startImage: 'https://x/start.png', advanced: {},
    characterVisual: {id: 'c1', name: 'Ann', references: ['https://x/c.png']}, objectVisual: null, referenceVisual: null};
  const payload = plain(vm.runInContext('videoOptionsPayload()', buildContext(state, null)));
  assert.deepEqual(payload.characterReferences, ['https://x/c.png']);
  assert.deepEqual(payload.reference_inputs_dropped, []);
  assert.equal(vm.runInContext('videoDroppedReferenceNotice([])', buildContext(state, null)), '');
});

test('reference video limits: motion accepts a 25 s 480x854 clip that the Omni rule rejected', () => {
  const context = buildContext({modelId: 'kling_motion_3_0'}, null);
  const motion = {video_min_seconds: 3, video_max_seconds: 30, video_min_px: 340, video_max_px: 3850};
  const omni = {video_min_seconds: 3, video_max_seconds: 15.5, video_min_px: 700, video_max_px: 4553, video_min_ratio: 0.4, video_max_ratio: 2, video_max_area: 8294400};
  const meta = JSON.stringify({duration: 25, width: 480, height: 854});
  assert.equal(vm.runInContext(`referenceVideoMetadataError(${meta}, ${JSON.stringify(motion)}, 'Kling Motion')`, context), '');
  assert.match(vm.runInContext(`referenceVideoMetadataError(${meta}, ${JSON.stringify(omni)}, 'Kling Omni')`, context), /3–15.5 секунд/);
  const tooLong = JSON.stringify({duration: 31, width: 1080, height: 1920});
  assert.match(vm.runInContext(`referenceVideoMetadataError(${tooLong}, ${JSON.stringify(motion)}, 'Kling Motion')`, context), /3–30 секунд/);
});
