// Run with: node --test tests/test_video_character_object_visual_gate.mjs
//
// Regression tests for Phase 1 Batch 2 of the Pro Studio master remediation
// plan (see /root/.claude/plans/splendid-moseying-starlight.md, roadmap
// step 2): video mode's Character/Object gate.
//
// Correction (post-review): text_conditioning and visual_reference are two
// independent axes and must be gated independently.
// - The Character/Object SELECTOR is gated on text_conditioning only (true
//   for every video model today, so it must never be disabled/blocked in
//   practice) - a model with no reference-image support must still let the
//   user pick a character/object by name, so its id/name reaches the
//   prompt.
// - Only the reference-IMAGE COUNT sent in the payload varies by
//   visual_reference mode: 0 for UNSUPPORTED, at most 1 for
//   DEGRADED_SINGLE_IMAGE, up to the registry's max_count for
//   REAL_MULTI_IMAGE.
// The original version of this file (and the code it tested) wrongly
// blocked the whole selector whenever visual_reference was UNSUPPORTED,
// which would have silently broken text_conditioning for every one of the
// ~32 video models that can't take a reference image but can perfectly
// well take a character/object by name (e.g. Sora). Fixed per explicit
// review; see the sora_2-specific test below.
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

function toPlain(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value));
}

function buildContext(videoState) {
  const calls = {toasts: [], opened: null};
  const buttons = {
    videoCharacterButton: {disabled: false, classList: new Set(), attrs: {}, closest: () => buttons.videoCharacterButton},
    videoObjectButton: {disabled: false, classList: new Set(), attrs: {}, closest: () => buttons.videoObjectButton},
  };
  for (const btn of Object.values(buttons)) {
    btn.classList.toggle = (cls, on) => { if (on) btn.classList.add(cls); else btn.classList.delete(cls); };
    btn.setAttribute = (name, value) => { btn.attrs[name] = value; };
  }
  const sandbox = {
    fetchedModelCapabilities: null,
    videoState: videoState || {modelId: 'sora_2', characterVisual: null, objectVisual: null, referenceVisual: null},
    toast: (msg) => { calls.toasts.push(msg); },
    closeVideoAddMenu: () => {},
    openVideoVisualPicker: (e, kind) => { calls.opened = kind; },
    document: {
      getElementById: (id) => buttons[id] || null,
    },
    // videoOptionsPayload dependencies unrelated to what these tests cover -
    // stubbed to fixed, harmless values so the function runs without error.
    normalizeVideoStateForModel: () => {},
    currentVideoConfig: () => ({}),
    currentVideoReferenceImages: () => [],
    currentVideoEditInputUrl: () => '',
    currentVideoReferenceUrl: () => '',
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('getVideoModelCapabilities'), context);
  vm.runInContext(extractFunction('videoFeatureUnavailableToast'), context);
  vm.runInContext(extractFunction('syncVideoFeatureAvailability'), context);
  vm.runInContext(extractFunction('renderVideoReferenceButtons'), context);
  vm.runInContext(extractFunction('chooseVideoAddCharacter'), context);
  vm.runInContext(extractFunction('chooseVideoAddObject'), context);
  vm.runInContext(extractFunction('videoOptionsPayload'), context);
  return {context, calls, buttons};
}

function withCapabilities(context, modelId, entry) {
  vm.runInContext(
    `fetchedModelCapabilities = {version: 'v1', models: {${JSON.stringify(modelId)}: ${JSON.stringify(entry)}}};`,
    context
  );
}

// sora_2's real registry entry per services/model_capabilities.py:
// text_conditioning is True for every video model; visual_reference is
// UNSUPPORTED with max_count 0 (_call_sora never reads reference_images).
const SORA_ENTRY = {
  character: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
  object: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
};
const DEGRADED_ENTRY = {
  character: {text_conditioning: true, visual_reference: {visual_mode: 'degraded_single_image', max_count: 1}},
  object: {text_conditioning: true, visual_reference: {visual_mode: 'degraded_single_image', max_count: 1}},
};
const MULTI_IMAGE_ENTRY = {
  character: {text_conditioning: true, visual_reference: {visual_mode: 'real_multi_image', max_count: 4}},
  object: {text_conditioning: true, visual_reference: {visual_mode: 'real_multi_image', max_count: 4}},
};

test('getVideoModelCapabilities: fails open (selectable, no limit) when nothing fetched yet', () => {
  const {context} = buildContext();
  const result = vm.runInContext(`getVideoModelCapabilities('sora_2')`, context);
  assert.deepEqual(toPlain(result), {
    character: {selectable: true, maxRefs: null},
    object: {selectable: true, maxRefs: null},
  });
});

test('getVideoModelCapabilities: sora_2 (visual_reference unsupported) stays selectable with maxRefs 0', () => {
  const {context} = buildContext();
  withCapabilities(context, 'sora_2', SORA_ENTRY);
  const result = vm.runInContext(`getVideoModelCapabilities('sora_2')`, context);
  assert.deepEqual(toPlain(result), {
    character: {selectable: true, maxRefs: 0},
    object: {selectable: true, maxRefs: 0},
  });
});

test('getVideoModelCapabilities: degraded_single_image reports maxRefs 1', () => {
  const {context} = buildContext();
  withCapabilities(context, 'kling_2_6', DEGRADED_ENTRY);
  const result = vm.runInContext(`getVideoModelCapabilities('kling_2_6')`, context);
  assert.deepEqual(toPlain(result), {
    character: {selectable: true, maxRefs: 1},
    object: {selectable: true, maxRefs: 1},
  });
});

test('getVideoModelCapabilities: real_multi_image reports the registry max_count', () => {
  const {context} = buildContext();
  withCapabilities(context, 'seedance_2_fast', MULTI_IMAGE_ENTRY);
  const result = vm.runInContext(`getVideoModelCapabilities('seedance_2_fast')`, context);
  assert.deepEqual(toPlain(result), {
    character: {selectable: true, maxRefs: 4},
    object: {selectable: true, maxRefs: 4},
  });
});

test('getVideoModelCapabilities: text_conditioning=false is the only thing that makes selectable false', () => {
  const {context} = buildContext();
  withCapabilities(context, 'hypothetical_model', {
    character: {text_conditioning: false, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
    object: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
  });
  const result = vm.runInContext(`getVideoModelCapabilities('hypothetical_model')`, context);
  assert.equal(result.character.selectable, false);
  assert.equal(result.object.selectable, true);
});

test('sora_2: chooseVideoAddCharacter opens the picker (selection must not be blocked by visual_reference=unsupported)', () => {
  const {context, calls} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', SORA_ENTRY);
  vm.runInContext(`chooseVideoAddCharacter(null)`, context);
  assert.equal(calls.opened, 'character');
  assert.equal(calls.toasts.length, 0);
});

test('sora_2: chooseVideoAddObject opens the picker (selection must not be blocked by visual_reference=unsupported)', () => {
  const {context, calls} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', SORA_ENTRY);
  vm.runInContext(`chooseVideoAddObject(null)`, context);
  assert.equal(calls.opened, 'object');
  assert.equal(calls.toasts.length, 0);
});

test('sora_2: renderVideoReferenceButtons leaves both icon buttons enabled', () => {
  const {context, buttons} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', SORA_ENTRY);
  vm.runInContext(`renderVideoReferenceButtons()`, context);
  assert.equal(buttons.videoCharacterButton.disabled, false);
  assert.equal(buttons.videoObjectButton.disabled, false);
  assert.ok(!buttons.videoCharacterButton.classList.has('image-setting-disabled'));
});

test('sora_2: videoOptionsPayload sends characterId/characterName/objectId/objectName but zero reference images', () => {
  const videoState = {
    modelId: 'sora_2',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png', 'https://x/b.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/c.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'sora_2', SORA_ENTRY);
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  // The hard requirement: text/name conditioning always flows.
  assert.equal(plain.characterId, 'char-1');
  assert.equal(plain.characterName, 'Alice');
  assert.equal(plain.objectId, 'obj-1');
  assert.equal(plain.objectName, 'Hat');
  // But no reference images - sora_2's provider never reads them.
  assert.deepEqual(plain.characterReferences, []);
  assert.deepEqual(plain.objectReferences, []);
});

test('degraded_single_image model: videoOptionsPayload sends at most one reference image per field', () => {
  const videoState = {
    modelId: 'kling_2_6',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png', 'https://x/b.png', 'https://x/c.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/d.png', 'https://x/e.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'kling_2_6', DEGRADED_ENTRY);
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, ['https://x/a.png']);
  assert.deepEqual(plain.objectReferences, ['https://x/d.png']);
  assert.equal(plain.characterName, 'Alice');
});

test('real_multi_image model: videoOptionsPayload respects the registry max_count (4)', () => {
  const videoState = {
    modelId: 'seedance_2_fast',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/1.png', 'https://x/2.png', 'https://x/3.png', 'https://x/4.png', 'https://x/5.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/6.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'seedance_2_fast', MULTI_IMAGE_ENTRY);
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, ['https://x/1.png', 'https://x/2.png', 'https://x/3.png', 'https://x/4.png']);
  assert.deepEqual(plain.objectReferences, ['https://x/6.png']);
});

test('videoOptionsPayload: with no fetched capability data, sends all attached references unchanged (fail open)', () => {
  const videoState = {
    modelId: 'sora_2',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png', 'https://x/b.png', 'https://x/c.png']},
    objectVisual: null,
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  // No withCapabilities() call - fetchedModelCapabilities stays null.
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, ['https://x/a.png', 'https://x/b.png', 'https://x/c.png']);
});

test('videoOptionsPayload: per-field independence - character unsupported, object real_multi_image', () => {
  const videoState = {
    modelId: 'mixed_model',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/c.png', 'https://x/d.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'mixed_model', {
    character: {text_conditioning: true, visual_reference: {visual_mode: 'unsupported', max_count: 0}},
    object: {text_conditioning: true, visual_reference: {visual_mode: 'real_multi_image', max_count: 4}},
  });
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, []);
  assert.deepEqual(plain.objectReferences, ['https://x/c.png', 'https://x/d.png']);
  assert.equal(plain.characterName, 'Alice');
});
