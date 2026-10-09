// Run with: node --test tests/test_kling_lip_sync_visibility.mjs
//
// Regression tests for Phase 1 roadmap step 9 (final step, see
// /root/.claude/plans/splendid-moseying-starlight.md): "kling_lip_sync
// frontend visibility". kling_lip_sync was already fully implemented
// server-side (services/video_router.py - dispatch, polling, pricing) but
// absent from cabinet.js's VIDEO_MODELS/VIDEO_MODEL_CONFIG, so no user
// could ever select it.
//
// Tracing found the model needed two things to become genuinely usable,
// not just listed:
// 1. VIDEO_MODELS/VIDEO_MODEL_CONFIG entries mirroring
//    services/video_router.py's VIDEO_MODEL_CONFIG["kling_lip_sync"]
//    exactly (modes:['lip_sync'] only - not 'video_edit' - even though the
//    legacy boolean video_edit is also true, the same boolean-vs-modes
//    drift already proven for kling_motion_3_0 in Batch 6).
//    services/model_capabilities.py's registry needed NO changes at all:
//    register_video_models() is called with the full Python
//    VIDEO_MODEL_CONFIG dict (main.py:1015), which already includes
//    kling_lip_sync - the fetched capability registry already serves this
//    model's data today, it was purely a frontend picker/config gap.
// 2. A working way to attach the required source video. Since
//    kling_lip_sync's modes array is ['lip_sync'] only, it fails
//    videoModelSupportsEdit()'s modes.includes('video_edit') check and so
//    can never enter the composer's 'edit'/'motion' sections (Batch 6/7's
//    picker filters) - it only ever appears in the unfiltered 'generate'
//    section picker. The only control that can set an edit-input video
//    (#videoEditUploadButton -> openVideoEditInputUpload ->
//    openNativeFilePicker('video'), no section gating in that click path
//    at all) is hidden purely by a CSS class (.video-edit-only{display:
//    none}, shown only under [data-video-section="edit"]) - so a
//    lip_sync-only model would otherwise have no way to attach its video.
//    renderVideoEditPreview() (called every render via renderVideoControls
//    -> the same function that already runs renderVideoStartPreview/
//    renderVideoEndPreview) now also force-shows this button via an inline
//    style override (which beats the CSS class) whenever
//    currentVideoConfig().lip_sync is true, regardless of section.
//
// Motion Control/Video Edit picker exclusion and Grid inclusion follow
// automatically from the already-established shared capability-check
// functions (videoModelSupportsEdit/videoModelSupportsMotionControl/
// gridVideoModelSupported) once the modes array is correct - no
// special-casing needed there, which these tests also confirm.
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

function baseContext(extra) {
  const context = vm.createContext(Object.assign({fetchedModelCapabilities: null}, extra || {}));
  vm.runInContext(extractVideoModelConfigWithKling(), context);
  return context;
}

test('VIDEO_MODELS includes kling_lip_sync', () => {
  const context = baseContext();
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  const models = vm.runInContext('VIDEO_MODELS', context);
  const entry = models.find((item) => item.id === 'kling_lip_sync');
  assert.ok(entry, 'kling_lip_sync must be present in VIDEO_MODELS');
  assert.equal(entry.icon, 'kling');
});

test('VIDEO_MODEL_CONFIG.kling_lip_sync mirrors the backend config exactly', () => {
  const context = baseContext();
  // JSON round-trip: the value crosses from the vm's realm into ours, and
  // assert.deepEqual on a cross-realm array fails on prototype identity
  // even when the contents match - plain-object/array comparison after a
  // round-trip sidesteps that.
  const config = JSON.parse(vm.runInContext('JSON.stringify(VIDEO_MODEL_CONFIG.kling_lip_sync)', context));
  assert.ok(config, 'kling_lip_sync must have a VIDEO_MODEL_CONFIG entry');
  assert.equal(config.provider, 'kling');
  assert.deepEqual(config.modes, ['lip_sync']);
  assert.equal(config.sound, true);
  assert.equal(config.lip_sync, true);
  assert.equal(config.video_input, true);
  assert.equal(config.video_upload, true);
  assert.equal(config.video_edit, true);
  assert.deepEqual(config.resolutions, ['720p']);
});

test('videoModelSupportsEdit: kling_lip_sync is false despite its legacy video_edit:true boolean (modes-based check)', () => {
  const context = baseContext({videoState: {modelId: 'kling_lip_sync'}});
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  assert.equal(vm.runInContext(`videoModelSupportsEdit('kling_lip_sync')`, context), false);
});

test('videoModelSupportsMotionControl: kling_lip_sync is false (not a motion_control model)', () => {
  const context = baseContext({videoState: {modelId: 'kling_lip_sync'}});
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  assert.equal(vm.runInContext(`videoModelSupportsMotionControl('kling_lip_sync')`, context), false);
});

test('currentComposerModelList: Edit mode picker excludes kling_lip_sync', () => {
  const context = baseContext({videoState: {modelId: 'seedance_2_fast', section: 'edit'}, S: {}});
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext('function isImageMode(){return false;} function isVideoMode(){return true;} function isMusicMode(){return false;} function isVoiceMode(){return false;} var studioMode="video";', context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('currentComposerModelList'), context);
  const ids = vm.runInContext(`currentComposerModelList()`, context).map((item) => item.id);
  assert.ok(!ids.includes('kling_lip_sync'));
});

test('gridVideoModelSupported: kling_lip_sync is selectable in Grid (not avatar, not video_effects)', () => {
  const context = baseContext({videoState: {modelId: 'kling_lip_sync'}});
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  assert.equal(vm.runInContext(`gridVideoModelSupported('kling_lip_sync')`, context), true);
});

test('gridModelsForType(video): kling_lip_sync appears in the Grid picker', () => {
  const context = baseContext();
  vm.runInContext(extractConstArray('VIDEO_MODELS'), context);
  vm.runInContext(extractFunction('gridVideoModelSupported'), context);
  vm.runInContext(extractFunction('gridModelsForType'), context);
  const ids = vm.runInContext(`gridModelsForType('video')`, context).map((item) => item.id);
  assert.ok(ids.includes('kling_lip_sync'));
});

test('renderVideoEditPreview: forces the edit-upload button visible when lip_sync is active, regardless of section', () => {
  const button = {style: {}, classList: {add() {}, remove() {}, toggle() {}}, querySelector: () => null};
  const context = baseContext({
    videoState: {modelId: 'kling_lip_sync', section: 'generate', editUploading: null, editInputVideo: '', editVideoUrl: ''},
    document: {getElementById: (id) => (id === 'videoEditUploadButton' ? button : null)},
  });
  vm.runInContext(extractFunction('currentVideoEditInputUrl'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('renderVideoEditPreview'), context);
  vm.runInContext('renderVideoEditPreview();', context);
  assert.equal(button.style.display, 'flex');
});

test('renderVideoEditPreview: does not force the button visible for a non-lip_sync model (falls back to the normal CSS section gating)', () => {
  const button = {style: {}, classList: {add() {}, remove() {}, toggle() {}}, querySelector: () => null};
  const context = baseContext({
    videoState: {modelId: 'seedance_2_fast', section: 'generate', editUploading: null, editInputVideo: '', editVideoUrl: ''},
    document: {getElementById: (id) => (id === 'videoEditUploadButton' ? button : null)},
  });
  vm.runInContext(extractFunction('currentVideoEditInputUrl'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('renderVideoEditPreview'), context);
  vm.runInContext('renderVideoEditPreview();', context);
  assert.equal(button.style.display, '');
});

test('renderVideoEditPreview: still forces the button visible for kling_lip_sync while in the edit section too (no regression)', () => {
  const button = {style: {}, classList: {add() {}, remove() {}, toggle() {}}, querySelector: () => null};
  const context = baseContext({
    videoState: {modelId: 'kling_lip_sync', section: 'edit', editUploading: null, editInputVideo: '', editVideoUrl: ''},
    document: {getElementById: (id) => (id === 'videoEditUploadButton' ? button : null)},
  });
  vm.runInContext(extractFunction('currentVideoEditInputUrl'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('renderVideoEditPreview'), context);
  vm.runInContext('renderVideoEditPreview();', context);
  assert.equal(button.style.display, 'flex');
});

test('videoOptionsPayload: model field switches modes to lip_sync and reports lip_sync:true', () => {
  const context = baseContext({
    videoState: {
      modelId: 'kling_lip_sync', section: 'generate', generationMode: 'text_to_video', mode: 'text_to_video',
      duration: 5, ratio: '16:9', resolution: '720p', sound: false, startImage: '', endImage: '',
      editInputVideo: '/uploads/reference.mp4', editVideoUrl: '', referenceVideoUrl: '', videoTemplate: null,
      referenceVisual: null, characterVisual: null, objectVisual: null, characterImage: '', advanced: {},
      referenceImageBuckets: {generate: [], edit: [], motion: []}, motionPreset: '',
    },
    S: {},
  });
  vm.runInContext(extractFunction('currentVideoEditInputUrl'), context);
  vm.runInContext(extractFunction('currentVideoReferenceUrl'), context);
  vm.runInContext(extractFunction('videoReferenceBucketKey'), context);
  vm.runInContext(extractFunction('videoReferenceBuckets'), context);
  vm.runInContext(extractFunction('currentVideoReferenceImages'), context);
  vm.runInContext(extractFunction('getVideoModelCapabilities'), context);
  vm.runInContext(extractFunction('videoModelSupportsEdit'), context);
  vm.runInContext(extractFunction('videoModelSupportsMotionControl'), context);
  vm.runInContext(extractFunction('currentVideoConfig'), context);
  vm.runInContext(extractFunction('normalizeVideoStateForModel'), context);
  vm.runInContext(extractFunction('videoOptionsPayload'), context);
  const payload = vm.runInContext(`videoOptionsPayload([])`, context);
  assert.equal(payload.model, 'kling_lip_sync');
  assert.equal(payload.lip_sync, true);
  assert.equal(payload.generation_mode, 'lip_sync');
  assert.equal(payload.input_video, '/uploads/reference.mp4');
  assert.equal(payload.video_url, '/uploads/reference.mp4');
});
