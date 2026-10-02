// Run with: node --test tests/test_motion_control_object_hidden.mjs
//
// Regression test for Master A-Z Remediation Phase 9 (Motion Control):
// "Object hidden unless a concrete provider capability needs it." Motion
// Control's product contract is subject image/Character + motion-reference
// video - there is no Object concept in it. Before this fix, a Character/
// Object picked earlier in Generate mode survived untouched into Motion
// Control (normalizeVideoStateForModel only ever cleared stale start/end
// frame state, never characterVisual/objectVisual), so a stale Object
// selection could silently ride along into a motion-control dispatch and
// fill the same single-image subject slot Kling's motion-control branch
// uses for Character (per services/model_capabilities.py's
// DEGRADED_SINGLE_IMAGE classification for kling_motion_3_0/kling_motion_2_6).
//
// The Object *button* itself is hidden via a CSS rule
// (.studio-video-composer[data-video-section="motion"] #imageObjectButton)
// which this test does not exercise (no CSS engine here) - this test
// covers the state-clearing half: updateComposerMode('motion') must null
// out videoState.objectVisual/referenceVisual so a stale selection can
// never reach videoOptionsPayload() even if the hidden button is bypassed
// some other way (e.g. a lingering catalog modal).
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

function fakeElement() {
  return {
    hidden: false,
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    setAttribute() {},
    querySelector: () => null,
    blur() {},
  };
}

function makeContext(videoState) {
  const context = vm.createContext({
    chatTypeForMode: () => 'video',
    currentChatType: () => 'video',
    stopTextListen: () => {},
    activeGenerationLocked: () => false,
    activeGeneration: {},
    toast: () => {},
    activeGenerationButtonLabel: () => '',
    restoringChatSpace: true,
    rememberCurrentChatSpace: () => {},
    studioMode: 'video',
    activeCat: 'video',
    localStorage: { setItem() {} },
    lastModeStorageKey: () => 'k',
    videoState,
    videoUploadTarget: '',
    normalizeVideoStateForModel: () => {},
    document: {
      activeElement: null,
      getElementById: () => fakeElement(),
      querySelectorAll: () => [],
    },
    isMusicMode: () => false,
    isVoiceMode: () => false,
    voiceWorkspaceMode: 'push_to_talk',
    VoiceDialogueComposer: { closeMenus: () => {} },
    currentModeAttachment: () => null,
    applyVoiceWorkspaceMode: () => {},
    PromptPlaceholderManager: { setMode: () => {} },
    imageState: { modelId: 'x' },
    IMAGE_MODEL_LIST: [],
    renderImageControls: () => {},
    renderUploadedPhotoGrid: () => {},
    updateImageUploadButtonPreview: () => {},
    renderModelPop: () => {},
    renderTextControls: () => {},
    renderMusicControls: () => {},
    renderVoiceControls: () => {},
    renderVideoControls: () => {},
    renderVoiceSpeakerComposer: () => {},
    resetVoiceToolGuideTimer: () => {},
    restoreChatSpace: () => {},
    applyCurrentDraft: () => {},
    updateSendButton: () => {},
  });
  vm.runInContext(extractFunction('updateComposerMode'), context);
  return context;
}

test('updateComposerMode("motion"): clears a stale Object selected earlier in Generate mode', () => {
  const videoState = {
    section: 'generate',
    objectVisual: { id: 'obj1', kind: 'object', references: ['https://cdn.sylvex.ai/obj.png'] },
    referenceVisual: { id: 'obj1', kind: 'object' },
    characterVisual: { id: 'char1', kind: 'character', references: ['https://cdn.sylvex.ai/char.png'] },
  };
  const context = makeContext(videoState);
  vm.runInContext('updateComposerMode("motion")', context);

  assert.equal(videoState.section, 'motion');
  assert.equal(videoState.objectVisual, null);
  assert.equal(videoState.referenceVisual, null);
  // Character must survive - Motion Control's contract is subject image/
  // Character + motion-reference video, Character is never cleared here.
  assert.equal(videoState.characterVisual.id, 'char1');
});

test('updateComposerMode("motion"): a Character-kind referenceVisual is left untouched', () => {
  const videoState = {
    section: 'generate',
    objectVisual: null,
    referenceVisual: { id: 'char1', kind: 'character' },
    characterVisual: { id: 'char1', kind: 'character' },
  };
  const context = makeContext(videoState);
  vm.runInContext('updateComposerMode("motion")', context);

  assert.deepEqual(videoState.referenceVisual, { id: 'char1', kind: 'character' });
});

test('updateComposerMode("video"): entering plain Generate section never touches objectVisual', () => {
  const videoState = {
    section: 'motion',
    objectVisual: { id: 'obj1', kind: 'object' },
    referenceVisual: { id: 'obj1', kind: 'object' },
    characterVisual: null,
  };
  const context = makeContext(videoState);
  vm.runInContext('updateComposerMode("video")', context);

  assert.equal(videoState.section, 'generate');
  assert.deepEqual(videoState.objectVisual, { id: 'obj1', kind: 'object' });
});
