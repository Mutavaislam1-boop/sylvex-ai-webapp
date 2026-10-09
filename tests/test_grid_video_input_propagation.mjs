// Run with: node --test tests/test_grid_video_input_propagation.mjs
//
// Regression tests for a standalone fix (not part of Phase 1 Batch 8's
// gridModelsForType filtering work - see
// /root/.claude/plans/splendid-moseying-starlight.md): a Grid video node's
// 'video' input port (GRID_TYPES.video.inputs includes 'video', for
// chaining an upstream video node's output into video_edit/motion_control
// mode) could be connected via the UI, and resolveGridNodeInputs()
// correctly resolved the connected edge into inputs.video - but two
// consumers of that resolved value ignored it entirely:
//
// 1. gridGenerationPayload()'s video branch built video_url only from
//    attachedVideos[0] (a locally attached file), never from
//    inputs.video?.value - so a connected upstream video was silently
//    dropped at dispatch time even though it was present in `inputs`.
// 2. validateGridNodeInputs() only checked hasVideo from local
//    attachments, and only gated on it for mode==='video_edit' -
//    motion_control wasn't checked for a video source at all, so a node
//    with neither an attachment nor a connection would pass validation
//    and dispatch with an empty video source.
//
// Both are fixed here: gridGenerationPayload now resolves
// input_video/video_url from inputs.video?.value.url (or .preview_url)
// first, falling back to attachedVideos[0] only when no connection
// exists - the same precedence the image port already had. validateGridNodeInputs
// now treats inputs.video?.value as a valid source and checks it for both
// video_edit and motion_control. image_to_video/text_to_video are
// unaffected - the image port's own resolution is untouched, and
// text_to_video has never required a video source.
//
// This patch deliberately does NOT touch connectStudioGridNodes() - no
// auto-change of generation_mode when a video edge is connected.
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

function buildPayloadContext() {
  const context = vm.createContext({
    providerHintForModel: () => 'kling',
    getTelegramId: () => 0,
    uiLang: () => 'ru',
    loadStudioGridState: () => ({projectId: 'grid_project_test'}),
  });
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('gridGenerationPayload'), context);
  return context;
}

function runPayload(context, node, inputs) {
  vm.runInContext('__node = ' + JSON.stringify(node) + ';', context);
  vm.runInContext('__inputs = ' + JSON.stringify(inputs) + ';', context);
  return vm.runInContext('gridGenerationPayload(__node, __inputs)', context);
}

const baseVideoNode = (overrides) => Object.assign({
  id: 'grid_video_1',
  type: 'video',
  model: 'kling_motion_3_0',
  prompt: 'test prompt',
  settings: {generation_mode: 'motion_control'},
  attachments: [],
}, overrides);

test('gridGenerationPayload: connected video reaches both video_url and input_video', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected.mp4');
});

test('gridGenerationPayload: connected video falls back to preview_url when url is absent', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {preview_url: 'https://cdn.example.com/connected-preview.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected-preview.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected-preview.mp4');
});

test('gridGenerationPayload: local attachment still works as a fallback when nothing is connected', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]});
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/attached.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/attached.mp4');
});

test('gridGenerationPayload: connected video takes precedence over a local attachment when both exist', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]});
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4', type: 'video'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, 'https://cdn.example.com/connected.mp4');
  assert.equal(payload.video_options.input_video, 'https://cdn.example.com/connected.mp4');
});

test('gridGenerationPayload: no connection and no attachment leaves video_url/input_video empty', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode();
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.input_video, '');
});

test('gridGenerationPayload: image_to_video is unaffected by the video-input change (image resolution untouched)', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({model: 'seedance_2_fast', settings: {generation_mode: 'image_to_video'}});
  const inputs = {
    effective_prompt: {value: 'test prompt'},
    image: {value: {url: 'https://cdn.example.com/character.jpg'}},
  };
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.start_image, 'https://cdn.example.com/character.jpg');
  assert.equal(payload.video_options.image_url, 'https://cdn.example.com/character.jpg');
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.generation_mode, 'image_to_video');
});

test('gridGenerationPayload: text_to_video is unaffected (no video source required or sent)', () => {
  const context = buildPayloadContext();
  const node = baseVideoNode({model: 'seedance_2_fast', settings: {generation_mode: 'text_to_video'}});
  const inputs = {effective_prompt: {value: 'test prompt'}};
  const payload = runPayload(context, node, inputs);
  assert.equal(payload.video_options.video_url, '');
  assert.equal(payload.video_options.input_video, '');
  assert.equal(payload.video_options.generation_mode, 'text_to_video');
});

// =====================================================================
// validateGridNodeInputs
// =====================================================================

function buildValidateContext() {
  const context = vm.createContext({});
  vm.runInContext(extractFunction('validateGridNodeInputs'), context);
  return context;
}

function runValidate(context, node, inputs) {
  vm.runInContext('__node = ' + JSON.stringify(node) + ';', context);
  vm.runInContext('__inputs = ' + JSON.stringify(inputs) + ';', context);
  return vm.runInContext('validateGridNodeInputs(__node, __inputs)', context);
}

test('validateGridNodeInputs: video_edit with a connected video (no attachment) passes validation', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'edit this'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: video_edit with neither connected nor attached video fails', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: []};
  const inputs = {effective_prompt: {value: 'edit this'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
});

// motion_control needs BOTH a video (motion/reference source) and an
// image (subject) - the Kling provider path's own requires_image gate
// (services/video_router.py's requires_image) includes motion_control
// alongside image_to_video, so a motion_control request with a video but
// no image would pass a video-only check here and still fail server-side.
test('validateGridNodeInputs: motion_control with a connected video AND a connected image passes validation', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
    image: {value: {url: 'https://cdn.example.com/subject.jpg'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: motion_control with a connected video but no image fails with the image message', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    video: {value: {url: 'https://cdn.example.com/connected.mp4'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное изображение'));
  assert.ok(!result.missing.includes('Исходное видео'));
});

test('validateGridNodeInputs: motion_control with a connected image but no video fails with the video message', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {
    effective_prompt: {value: 'apply this motion'},
    image: {value: {url: 'https://cdn.example.com/subject.jpg'}},
  };
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
  assert.ok(!result.missing.includes('Исходное изображение'));
});

test('validateGridNodeInputs: motion_control with neither video nor image fails with both messages', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'motion_control'}, attachments: []};
  const inputs = {effective_prompt: {value: 'apply this motion'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Исходное видео'));
  assert.ok(result.missing.includes('Исходное изображение'));
});

test('validateGridNodeInputs: motion_control with both required inputs supplied through local attachments passes', () => {
  const context = buildValidateContext();
  const node = {
    type: 'video',
    settings: {generation_mode: 'motion_control'},
    attachments: [
      {kind: 'video', url: 'https://cdn.example.com/attached.mp4'},
      {kind: 'image', url: 'https://cdn.example.com/attached.jpg'},
    ],
  };
  const inputs = {effective_prompt: {value: 'apply this motion'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});

test('validateGridNodeInputs: video_edit with a local attachment only (no connection) still passes (fallback preserved)', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'video_edit'}, attachments: [{kind: 'video', url: 'https://cdn.example.com/attached.mp4'}]};
  const inputs = {effective_prompt: {value: 'edit this'}};
  const result = runValidate(context, node, inputs);
  assert.equal(result.ok, true);
});

test('validateGridNodeInputs: image_to_video is unaffected by the video-source check', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'image_to_video'}, attachments: []};
  const withImage = runValidate(context, node, {effective_prompt: {value: 'p'}, image: {value: {url: 'https://cdn.example.com/a.jpg'}}});
  assert.equal(withImage.ok, true);
  const withoutImage = runValidate(context, node, {effective_prompt: {value: 'p'}});
  assert.equal(withoutImage.ok, false);
  assert.ok(withoutImage.missing.includes('Исходное изображение'));
  assert.ok(!withoutImage.missing.includes('Исходное видео'));
});

test('validateGridNodeInputs: text_to_video never requires a video or image source', () => {
  const context = buildValidateContext();
  const node = {type: 'video', settings: {generation_mode: 'text_to_video'}, attachments: []};
  const result = runValidate(context, node, {effective_prompt: {value: 'a video about cats'}});
  assert.equal(result.ok, true);
  assert.equal(result.missing.length, 0);
});
