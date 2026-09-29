// Run with: node --test tests/test_phase10_regenerate_fallback_defaults.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 10 fix (M-022):
// restoreImageStateFromGenerationMetadata/restoreVideoStateFromGenerationMetadata/
// restoreMusicStateFromGenerationMetadata/restoreVoiceStateFromGenerationMetadata
// exist specifically so regenMsg ("Повторить генерацию") reproduces the
// ORIGINAL generation's settings instead of whatever the composer currently
// happens to be set to. But when a field was missing from older metadata,
// each one's final fallback used to be the live *State value itself
// (imageState.modelId, videoState.ratio, etc.) - defeating that exact
// purpose by silently mixing in whatever unrelated generation the composer
// was last set to. Fixed to fall back to a fixed default matching each
// state object's own module-level initial value.
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

function baseSandbox() {
  return {
    document: {getElementById: () => null},
    autoGrow: () => {},
    updateSendButton: () => {},
    renderImageControls: () => {},
    renderComposerImageDraft: () => {},
    renderUploadedPhotoGrid: () => {},
    updateImageUploadButtonPreview: () => {},
    renderVideoControls: () => {},
    renderMusicControls: () => {},
    renderVoiceControls: () => {},
    setCurrentVideoReferenceImages: () => {},
  };
}

test('restoreImageStateFromGenerationMetadata: missing model/size/count/style/character/objects fall back to fixed defaults, not the live (unrelated) composer state', () => {
  const sandbox = Object.assign(baseSandbox(), {
    imageState: {modelId: 'nano_banana_pro', size: '1:1', count: 4, style: 'anime', character: 'happy', objects: 'a red bicycle'},
  });
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('restoreImageStateFromGenerationMetadata'), context);
  vm.runInContext(`restoreImageStateFromGenerationMetadata({type:'image', settings:{}})`, context);
  assert.equal(vm.runInContext('imageState.modelId', context), 'seedream_5_0_lite');
  assert.equal(vm.runInContext('imageState.size', context), '');
  assert.equal(vm.runInContext('imageState.count', context), 1);
  // These three were the part of M-022 a prior fix mistakenly left in place:
  // `meta.X || settings.X || imageState.X || default` still lets the live
  // (unrelated) value win over the default because it's checked first.
  assert.equal(vm.runInContext('imageState.style', context), 'auto');
  assert.equal(vm.runInContext('imageState.character', context), 'auto');
  assert.equal(vm.runInContext('imageState.objects', context), '');
});

test('restoreImageStateFromGenerationMetadata: an explicit value in metadata is still used over the default', () => {
  const sandbox = Object.assign(baseSandbox(), {
    imageState: {modelId: 'nano_banana_pro', size: '1:1', count: 4, style: 'anime', character: 'happy', objects: 'a red bicycle'},
  });
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('restoreImageStateFromGenerationMetadata'), context);
  vm.runInContext(`restoreImageStateFromGenerationMetadata({type:'image', model:'flux_2', size:'16:9', count:2, style:'cinematic', character:'serious', objects:'a blue kite', settings:{}})`, context);
  assert.equal(vm.runInContext('imageState.modelId', context), 'flux_2');
  assert.equal(vm.runInContext('imageState.size', context), '16:9');
  assert.equal(vm.runInContext('imageState.count', context), 2);
  assert.equal(vm.runInContext('imageState.style', context), 'cinematic');
  assert.equal(vm.runInContext('imageState.character', context), 'serious');
  assert.equal(vm.runInContext('imageState.objects', context), 'a blue kite');
});

test('restoreVideoStateFromGenerationMetadata: missing fields fall back to fixed defaults, not the live composer state', () => {
  const sandbox = Object.assign(baseSandbox(), {
    videoState: {modelId: 'kling_3_0', ratio: '9:16', resolution: '1080p', duration: 12},
  });
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('restoreVideoStateFromGenerationMetadata'), context);
  vm.runInContext(`restoreVideoStateFromGenerationMetadata({type:'video', settings:{}})`, context);
  assert.equal(vm.runInContext('videoState.modelId', context), 'seedance_2_fast');
  assert.equal(vm.runInContext('videoState.ratio', context), '16:9');
  assert.equal(vm.runInContext('videoState.resolution', context), '720p');
  assert.equal(vm.runInContext('videoState.duration', context), 5);
});

test('restoreMusicStateFromGenerationMetadata: missing model falls back to a fixed default, not the live composer state', () => {
  const sandbox = Object.assign(baseSandbox(), {
    musicState: {modelId: 'minimax_music_2_5', settings: {}},
  });
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('restoreMusicStateFromGenerationMetadata'), context);
  vm.runInContext(`restoreMusicStateFromGenerationMetadata({type:'music', settings:{}})`, context);
  assert.equal(vm.runInContext('musicState.modelId', context), 'suno_chirp_5');
});

test('restoreVoiceStateFromGenerationMetadata: missing model falls back to a fixed default, not the live composer state', () => {
  const sandbox = Object.assign(baseSandbox(), {
    voiceState: {modelId: 'runway_voice'},
  });
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('restoreVoiceStateFromGenerationMetadata'), context);
  vm.runInContext(`restoreVoiceStateFromGenerationMetadata({type:'voice', settings:{}})`, context);
  assert.equal(vm.runInContext('voiceState.modelId', context), 'elevenlabs_eleven_v3');
});
