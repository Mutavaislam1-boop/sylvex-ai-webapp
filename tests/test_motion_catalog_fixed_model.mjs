// Run with: node --test tests/test_motion_catalog_fixed_model.mjs
//
// Regression tests for the Phase 1 Batch 7 CORRECTION (see
// /root/.claude/plans/splendid-moseying-starlight.md): the Motion Catalog
// is not a general multi-model Motion Control picker - it's the reference-
// video-driven video templates catalog (openVideoTemplatesCatalog('templates')
// -> a template card click -> startVideoTemplateGeneration()), a dedicated
// fixed-model workflow. Tracing found two concrete bugs matching the
// reported product behavior:
//
// 1. Backend: prostudio_builtin_video_template_slots() (main.py) served
//    preferred_model: "kling_o3_omni" for every non-effect built-in
//    template, even though the env-sourced sibling function
//    (prostudio_video_templates_from_env()) already hardcodes
//    kling_motion_3_0 for the same catalog - a drift, not a deliberate
//    choice.
// 2. Frontend: templatePreferredModel() (cabinet.js) was bugged so that it
//    ALWAYS resolved to 'kling_o3_omni' regardless of what preferred_model/
//    models the template payload actually carried - the literal
//    "always falls back to kling_o3_omni" bug the correction describes.
//
// A third, latent regression was also found and fixed here: the just-
// landed Batch 7 force-switch in normalizeVideoStateForModel() keys off
// videoState.section ('edit'/'motion'), which startVideoTemplateGeneration()
// also sets (to 'edit' for the Motion Catalog, to 'motion' for the
// separate Kling Effects catalog) as an implementation detail of its
// catalog-driven, fixed-model dispatch - NOT because the user is using the
// composer's manual Edit/Motion picker. Without a guard, the force-switch
// would silently snap kling_motion_3_0 (modes: ['motion_control'] only)
// back to kling_o3_omni the moment videoOptionsPayload() calls
// normalizeVideoStateForModel() again right before dispatch, and would do
// the same to the Kling Effects catalog's fixed 'kling_effects' model.
// normalizeVideoStateForModel() now skips this force-switch entirely
// whenever videoState.videoTemplate is set, which is only ever true during
// a catalog-driven dispatch - never during ordinary manual Edit/Motion
// composer usage - so this also proves Video Generate/Video Edit are
// unaffected (see the "non-catalog" tests below, which show the pre-
// existing force-switch behavior is untouched).
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
// (Kling entries) extraction as the other video model-filter test files.
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

function extractLetObject(name) {
  const re = new RegExp(`let ${name} *= *\\{`);
  const m = re.exec(cabinet);
  assert.ok(m, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', m.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(m.index, i + 1) + ';';
}

// =====================================================================
// Part 1: pure unit tests - templatePreferredModel() and the
// normalizeVideoStateForModel() catalog-dispatch guard in isolation.
// =====================================================================

function buildNormalizeContext(modelId, section, videoTemplate) {
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: {modelId, section, videoTemplate: videoTemplate || null, duration: 5, ratio: '16:9', resolution: '720p'},
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

test('templatePreferredModel: always resolves to kling_motion_3_0, ignoring a stale/wrong preferred_model', () => {
  const sandbox = {};
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('templatePreferredModel'), context);
  const result = vm.runInContext(
    "templatePreferredModel({preferred_model: 'kling_o3_omni', models: ['kling_o3_omni', 'kling_motion_2_6']})",
    context
  );
  assert.equal(result, 'kling_motion_3_0');
});

test('templatePreferredModel: ignores a missing/empty template entirely (no picker, no fallback)', () => {
  const sandbox = {};
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('templatePreferredModel'), context);
  assert.equal(vm.runInContext('templatePreferredModel(null)', context), 'kling_motion_3_0');
  assert.equal(vm.runInContext('templatePreferredModel({})', context), 'kling_motion_3_0');
});

test('normalizeVideoStateForModel: catalog dispatch (videoTemplate set) keeps kling_motion_3_0 in the edit section instead of snapping to kling_o3_omni', () => {
  const videoTemplate = {catalog_type: 'video_template', reference_video: '/assets/reference.mp4'};
  assert.equal(buildNormalizeContext('kling_motion_3_0', 'edit', videoTemplate), 'kling_motion_3_0');
});

test('normalizeVideoStateForModel: catalog dispatch keeps the Kling Effects catalog\'s fixed kling_effects model in the motion section (regression fix)', () => {
  // Before this correction, Batch 7's brand-new motion-section force-switch
  // would have snapped this to kling_o3_omni too, since kling_effects has
  // no 'motion_control' mode - a real, previously-unnoticed regression in
  // the already-working Kling Effects catalog (task #94), caught here.
  const videoTemplate = {catalog_type: 'kling_effect', is_kling_effect: true};
  assert.equal(buildNormalizeContext('kling_effects', 'motion', videoTemplate), 'kling_effects');
});

test('normalizeVideoStateForModel: non-catalog edit/motion force-switch is completely unaffected (Video Edit/Motion Control picker still works)', () => {
  // No videoTemplate - this is the ordinary composer Edit/Motion tab path,
  // untouched by this correction.
  assert.equal(buildNormalizeContext('kling_motion_3_0', 'edit', null), 'kling_o3_omni');
  assert.equal(buildNormalizeContext('sora_2', 'edit', null), 'kling_o3_omni');
  assert.equal(buildNormalizeContext('grok_video_edit', 'edit', null), 'grok_video_edit');
  assert.equal(buildNormalizeContext('kling_motion_2_6', 'motion', null), 'kling_motion_2_6');
});

// =====================================================================
// Part 2: end-to-end - the real startVideoTemplateGeneration() dispatch,
// with only DOM/network/chat-UI stubbed out. videoOptionsPayload(),
// normalizeVideoStateForModel(), templatePreferredModel() and
// videoTemplateReferenceVideo() all run for real, so the captured options
// passed to callGenerate() are exactly what would be sent to the backend.
// =====================================================================

function buildDispatchContext() {
  const sandbox = {
    fetchedModelCapabilities: null,
    studioMode: 'text',
    activeCat: 'text',
    chatMessages: [],
    activeGeneration: {jobId: null, status: ''},
    activeVideoTemplate: null,
    videoTemplateUploadUrl: '',
    videoTemplateRatio: '16:9',
    capturedOptions: null,
    capturedPrompt: null,
    closeVideoTemplateModal() {},
    closeVideoTemplatesCatalog() {},
    createGenerationProgress() { return {}; },
    renderChat() {},
    rememberCurrentChatSpace() {},
    toast() {},
    videoTemplateText(key) { return String(key || ''); },
    generationResultMetadata() { return {}; },
    loadConversations() {},
    clearActiveProStudioJob() {},
    isActiveGenerationStatus() { return false; },
    document: {body: {classList: {add() {}, remove() {}}}},
  };
  // callGenerate is defined after the object literal (rather than as a
  // shorthand method inside it) and writes through the `sandbox` closure
  // explicitly: this file is an ES module, so it runs in strict mode, and
  // a bare `capturedOptions = videoOptions` assignment inside a shorthand
  // method here would throw a ReferenceError instead of creating an
  // implicit global - it would never actually reach the sandbox object
  // vm.createContext() contextifies.
  sandbox.callGenerate = function callGenerate(promptText, _image, _refs, videoOptions) {
    sandbox.capturedPrompt = promptText;
    sandbox.capturedOptions = videoOptions;
    return Promise.resolve({result: {id: 'job_test_1', status: 'completed'}});
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractLetObject('videoState'), context);
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('currentVideoEditInputUrl'), context);
  vm.runInContext(extractFunction('currentVideoReferenceUrl'), context);
  vm.runInContext(extractFunction('videoReferenceBucketKey'), context);
  vm.runInContext(extractFunction('videoReferenceBuckets'), context);
  vm.runInContext(extractFunction('currentVideoReferenceImages'), context);
  vm.runInContext(extractFunction('getVideoModelCapabilities'), context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  vm.runInContext(extractFunction('normalizeVideoStateForModel'), context);
  vm.runInContext(extractFunction('videoOptionsPayload'), context);
  vm.runInContext(extractFunction('videoTemplateReferenceVideo'), context);
  vm.runInContext(extractFunction('templatePreferredModel'), context);
  vm.runInContext(extractFunction('startVideoTemplateGeneration'), context);
  return context;
}

test('Motion Catalog dispatch: always resolves model to kling_motion_3_0, never kling_o3_omni, even with a stale picker-selected modelId and a wrong template preferred_model', async () => {
  const context = buildDispatchContext();
  // Simulate the composer having last been left on kling_o3_omni (e.g. from
  // an earlier manual Edit-mode picker selection) - the Motion Catalog must
  // not be controlled by this leftover state at all.
  vm.runInContext("videoState.modelId = 'kling_o3_omni';", context);
  context.videoTemplateUploadUrl = 'https://cdn.example.com/subject-character.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_01',
    title: 'Test Motion Template',
    description: 'A test motion catalog template',
    prompt: 'A subject performs the template motion',
    reference_video: '/webapp/assets/video-templates/01/preview.mp4',
    duration: 5,
    resolution: '720p',
    cost_credits: 100,
    catalog_type: 'video_template',
    is_kling_effect: false,
    input_count: 1,
    // Deliberately stale/wrong values a drifted backend or cached payload
    // might still send - templatePreferredModel() must ignore both.
    models: ['kling_o3_omni'],
    preferred_model: 'kling_o3_omni',
  };

  await vm.runInContext('startVideoTemplateGeneration()', context);

  assert.ok(context.capturedOptions, 'callGenerate must have been invoked with options');
  assert.equal(context.capturedOptions.model, 'kling_motion_3_0');
});

test('Motion Catalog dispatch: preserves the selected catalog reference video as the motion source', async () => {
  const context = buildDispatchContext();
  context.videoTemplateUploadUrl = 'https://cdn.example.com/subject.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_02',
    title: 'Another Motion Template',
    prompt: 'Motion catalog prompt',
    reference_video: '/webapp/assets/video-templates/02/preview.mp4',
    duration: 5,
    resolution: '720p',
    catalog_type: 'video_template',
    is_kling_effect: false,
  };

  await vm.runInContext('startVideoTemplateGeneration()', context);

  assert.equal(context.capturedOptions.input_video, '/webapp/assets/video-templates/02/preview.mp4');
  assert.equal(context.capturedOptions.video_url, '/webapp/assets/video-templates/02/preview.mp4');
  assert.equal(context.capturedOptions.video_template.reference_video, '/webapp/assets/video-templates/02/preview.mp4');
});

test('Motion Catalog dispatch: preserves the user-selected subject/character image as start_image', async () => {
  const context = buildDispatchContext();
  context.videoTemplateUploadUrl = 'https://cdn.example.com/my-uploaded-character.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_03',
    title: 'Subject Preservation Template',
    prompt: 'Motion catalog prompt',
    reference_video: '/webapp/assets/video-templates/03/preview.mp4',
    duration: 5,
    resolution: '720p',
    catalog_type: 'video_template',
    is_kling_effect: false,
  };

  await vm.runInContext('startVideoTemplateGeneration()', context);

  assert.equal(context.capturedOptions.start_image, 'https://cdn.example.com/my-uploaded-character.jpg');
});

test('Motion Catalog dispatch: the normal video model picker does not control the dispatched model (picker excludes kling_motion_3_0 from Edit mode, catalog uses it anyway)', async () => {
  // Cross-check against the established fact (see
  // test_video_edit_mode_model_filter.mjs) that kling_motion_3_0 is
  // excluded from the Edit-mode picker's own model list, because its real
  // modes are only ['motion_control']. The Motion Catalog still dispatches
  // it correctly precisely because it never consults that picker/filter at
  // all for its own fixed model choice.
  const context = buildDispatchContext();
  const editModeSupportsIt = vm.runInContext(
    "(function(){ videoState.modelId='kling_motion_3_0'; videoState.section='edit'; videoState.videoTemplate=null; return videoModelSupportsEdit('kling_motion_3_0'); })()",
    context
  );
  assert.equal(editModeSupportsIt, false, 'sanity check: the picker genuinely would reject kling_motion_3_0 for Edit mode');

  context.videoTemplateUploadUrl = 'https://cdn.example.com/subject.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_04',
    title: 'Picker Independence Template',
    prompt: 'Motion catalog prompt',
    reference_video: '/webapp/assets/video-templates/04/preview.mp4',
    duration: 5,
    resolution: '720p',
    catalog_type: 'video_template',
    is_kling_effect: false,
  };
  await vm.runInContext('startVideoTemplateGeneration()', context);
  assert.equal(context.capturedOptions.model, 'kling_motion_3_0');
});

test('Video Generate and Video Edit are unaffected: videoState is fully restored to its pre-dispatch value after a Motion Catalog generation', async () => {
  const context = buildDispatchContext();
  const before = vm.runInContext('JSON.stringify(videoState)', context);
  context.videoTemplateUploadUrl = 'https://cdn.example.com/subject.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_05',
    title: 'Restore Template',
    prompt: 'Motion catalog prompt',
    reference_video: '/webapp/assets/video-templates/05/preview.mp4',
    duration: 5,
    resolution: '720p',
    catalog_type: 'video_template',
    is_kling_effect: false,
  };
  await vm.runInContext('startVideoTemplateGeneration()', context);
  const after = vm.runInContext('JSON.stringify(videoState)', context);
  assert.equal(after, before, 'videoState must be restored exactly - a Motion Catalog generation must not leak into ordinary Generate/Edit composer state');
});

test('Kling Effects catalog dispatch: still resolves to the fixed kling_effects model (regression check for the sibling catalog flow)', async () => {
  const context = buildDispatchContext();
  context.videoTemplateUploadUrl = 'https://cdn.example.com/pet-photo.jpg';
  context.activeVideoTemplate = {
    id: 'builtin_video_template_64',
    title: 'Wiggle Faces',
    prompt: 'Wiggle faces effect',
    effect_scene: 'wiggle_faces',
    model_name: 'kling-v1-6',
    mode: 'std',
    input_count: 1,
    duration: 5,
    resolution: '720p',
    catalog_type: 'kling_effect',
    is_kling_effect: true,
    reference_video: '',
  };
  await vm.runInContext('startVideoTemplateGeneration()', context);
  assert.equal(context.capturedOptions.model, 'kling_effects');
  assert.equal(context.capturedOptions.is_kling_effect, true);
});
