// Run with: node --test tests/test_video_character_object_visual_gate.mjs
//
// Regression tests for Phase 1 Batch 2 of the Pro Studio master remediation
// plan (see /root/.claude/plans/splendid-moseying-starlight.md, roadmap
// step 2): video mode's Character/Object visual-reference gate. Confirms:
// - getVideoModelCapabilities() reads the fetched /model-capabilities data
//   and fails OPEN (assume supported) when nothing has been fetched yet -
//   this is net-new gating, not a migration of prior always-enabled
//   behavior, so absent data must never newly restrict.
// - chooseVideoAddCharacter/chooseVideoAddObject block the click with a
//   toast for an unsupported model instead of opening the picker.
// - renderVideoReferenceButtons() disables the two icon buttons for an
//   unsupported model, mirroring renderImageReferenceSections()'s pattern.
// - videoOptionsPayload() strips characterReferences/objectReferences (the
//   actual reference-image arrays) for an unsupported model while still
//   sending characterId/characterName/objectId/objectName - the text/name
//   reference must always reach the prompt regardless of this gate.
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

const UNSUPPORTED_ENTRY = {
  character: {visual_reference: {visual_mode: 'unsupported'}},
  object: {visual_reference: {visual_mode: 'unsupported'}},
};
const SUPPORTED_ENTRY = {
  character: {visual_reference: {visual_mode: 'real_multi_image'}},
  object: {visual_reference: {visual_mode: 'degraded_single_image'}},
};

test('getVideoModelCapabilities: fails open (both true) when nothing fetched yet', () => {
  const {context} = buildContext();
  const result = vm.runInContext(`getVideoModelCapabilities('sora_2')`, context);
  assert.deepEqual(toPlain(result), {character: true, object: true});
});

test('getVideoModelCapabilities: reads unsupported from fetched data', () => {
  const {context} = buildContext();
  withCapabilities(context, 'sora_2', UNSUPPORTED_ENTRY);
  const result = vm.runInContext(`getVideoModelCapabilities('sora_2')`, context);
  assert.deepEqual(toPlain(result), {character: false, object: false});
});

test('getVideoModelCapabilities: real_multi_image/degraded_single_image both count as supported', () => {
  const {context} = buildContext();
  withCapabilities(context, 'kling_2_6', SUPPORTED_ENTRY);
  const result = vm.runInContext(`getVideoModelCapabilities('kling_2_6')`, context);
  assert.deepEqual(toPlain(result), {character: true, object: true});
});

test('chooseVideoAddCharacter: blocked with a toast for an unsupported model', () => {
  const {context, calls} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', UNSUPPORTED_ENTRY);
  vm.runInContext(`chooseVideoAddCharacter(null)`, context);
  assert.equal(calls.opened, null);
  assert.equal(calls.toasts.length, 1);
  assert.match(calls.toasts[0], /персонажа/);
});

test('chooseVideoAddObject: blocked with a toast for an unsupported model', () => {
  const {context, calls} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', UNSUPPORTED_ENTRY);
  vm.runInContext(`chooseVideoAddObject(null)`, context);
  assert.equal(calls.opened, null);
  assert.equal(calls.toasts.length, 1);
  assert.match(calls.toasts[0], /объекта/);
});

test('chooseVideoAddCharacter: opens the picker for a supported model', () => {
  const {context, calls} = buildContext({modelId: 'kling_2_6'});
  withCapabilities(context, 'kling_2_6', SUPPORTED_ENTRY);
  vm.runInContext(`chooseVideoAddCharacter(null)`, context);
  assert.equal(calls.opened, 'character');
  assert.equal(calls.toasts.length, 0);
});

test('renderVideoReferenceButtons: disables both icon buttons for an unsupported model', () => {
  const {context, buttons} = buildContext({modelId: 'sora_2'});
  withCapabilities(context, 'sora_2', UNSUPPORTED_ENTRY);
  vm.runInContext(`renderVideoReferenceButtons()`, context);
  assert.equal(buttons.videoCharacterButton.disabled, true);
  assert.equal(buttons.videoCharacterButton.attrs['aria-disabled'], 'true');
  assert.ok(buttons.videoCharacterButton.classList.has('image-setting-disabled'));
  assert.equal(buttons.videoObjectButton.disabled, true);
});

test('renderVideoReferenceButtons: leaves both icon buttons enabled for a supported model', () => {
  const {context, buttons} = buildContext({modelId: 'kling_2_6'});
  withCapabilities(context, 'kling_2_6', SUPPORTED_ENTRY);
  vm.runInContext(`renderVideoReferenceButtons()`, context);
  assert.equal(buttons.videoCharacterButton.disabled, false);
  assert.equal(buttons.videoCharacterButton.attrs['aria-disabled'], 'false');
  assert.ok(!buttons.videoCharacterButton.classList.has('image-setting-disabled'));
  assert.equal(buttons.videoObjectButton.disabled, false);
});

test('videoOptionsPayload: strips characterReferences/objectReferences for an unsupported model, but keeps name/id', () => {
  const videoState = {
    modelId: 'sora_2',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png', 'https://x/b.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/c.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'sora_2', UNSUPPORTED_ENTRY);
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, []);
  assert.deepEqual(plain.objectReferences, []);
  // Text/name reference must still flow regardless of the image-only gate.
  assert.equal(plain.characterId, 'char-1');
  assert.equal(plain.characterName, 'Alice');
  assert.equal(plain.objectId, 'obj-1');
  assert.equal(plain.objectName, 'Hat');
});

test('videoOptionsPayload: keeps characterReferences/objectReferences for a supported model', () => {
  const videoState = {
    modelId: 'kling_2_6',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png', 'https://x/b.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/c.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'kling_2_6', SUPPORTED_ENTRY);
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, ['https://x/a.png', 'https://x/b.png']);
  assert.deepEqual(plain.objectReferences, ['https://x/c.png']);
  assert.equal(plain.characterId, 'char-1');
  assert.equal(plain.objectId, 'obj-1');
});

test('videoOptionsPayload: strips are independent per field (character unsupported, object supported)', () => {
  const videoState = {
    modelId: 'mixed_model',
    characterVisual: {id: 'char-1', name: 'Alice', references: ['https://x/a.png']},
    objectVisual: {id: 'obj-1', name: 'Hat', references: ['https://x/c.png']},
    referenceVisual: null,
    advanced: {},
  };
  const {context} = buildContext(videoState);
  withCapabilities(context, 'mixed_model', {
    character: {visual_reference: {visual_mode: 'unsupported'}},
    object: {visual_reference: {visual_mode: 'real_multi_image'}},
  });
  const payload = vm.runInContext(`videoOptionsPayload()`, context);
  const plain = toPlain(payload);
  assert.deepEqual(plain.characterReferences, []);
  assert.deepEqual(plain.objectReferences, ['https://x/c.png']);
  assert.equal(plain.characterName, 'Alice');
});
