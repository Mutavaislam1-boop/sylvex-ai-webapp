// Run with: node --test tests/test_regenerate_restore_video_voice.mjs
//
// Regression test for Master A-Z Remediation Phase 16 (History/metadata/
// regenerate/open-in-studio): "Regenerate reproduces original settings
// not current Composer state... including Video/Voice gaps." The data
// was already captured (videoOptionsPayload()/voiceOptionsPayload()
// already snapshot start_image/end_image/characterId/.../runway_tool/
// elevenlabs_tool into generationResultMetadata's settings), but
// restoreVideoStateFromGenerationMetadata and
// restoreVoiceStateFromGenerationMetadata never read most of it back, so
// clicking "Повторить генерацию" silently dropped the original Start/End
// Frame, Character/Object selection (video) or tool/second-voice/duration
// (voice) even though the Mini App already had everything it needed to
// reproduce them.
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

function makeVideoContext(videoState) {
  const context = vm.createContext({
    videoState,
    setCurrentVideoReferenceImages: (refs) => { videoState.referenceImages = refs; },
    renderVideoControls: () => {},
    renderVideoReferencesPreview: () => {},
  });
  vm.runInContext(extractFunction('restoreVideoStateFromGenerationMetadata'), context);
  return context;
}

function makeVoiceContext(voiceState) {
  const context = vm.createContext({
    voiceState,
    renderVoiceControls: () => {},
  });
  vm.runInContext(extractFunction('restoreVoiceStateFromGenerationMetadata'), context);
  return context;
}

test('restoreVideoStateFromGenerationMetadata: restores start/end frame', () => {
  const videoState = {};
  const context = makeVideoContext(videoState);
  const meta = {
    type: 'video',
    model: 'kling_o3_omni',
    settings: { start_image: 'https://cdn.sylvex.ai/start.png', end_image: 'https://cdn.sylvex.ai/end.png' },
  };
  vm.runInContext('restoreVideoStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(videoState.startImage, 'https://cdn.sylvex.ai/start.png');
  assert.equal(videoState.endImage, 'https://cdn.sylvex.ai/end.png');
});

test('restoreVideoStateFromGenerationMetadata: restores the original Character selection', () => {
  const videoState = {};
  const context = makeVideoContext(videoState);
  const meta = {
    type: 'video',
    model: 'kling_o3_omni',
    settings: {
      characterId: 'custom_character_abc',
      characterName: 'Islam',
      characterReferences: ['https://cdn.sylvex.ai/char.png'],
    },
  };
  vm.runInContext('restoreVideoStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(videoState.characterVisual.id, 'custom_character_abc');
  assert.equal(videoState.characterVisual.name, 'Islam');
  assert.deepEqual(videoState.characterVisual.references, ['https://cdn.sylvex.ai/char.png']);
  assert.equal(videoState.objectVisual, null);
  assert.equal(videoState.referenceVisual.id, 'custom_character_abc');
});

test('restoreVideoStateFromGenerationMetadata: restores the original Object selection and clears a stale one', () => {
  const videoState = { characterVisual: { id: 'stale', kind: 'character' } };
  const context = makeVideoContext(videoState);
  const meta = {
    type: 'video',
    model: 'kling_o3_omni',
    settings: { objectId: 'custom_object_1', objectName: 'Car', objectReferences: ['https://cdn.sylvex.ai/obj.png'] },
  };
  vm.runInContext('restoreVideoStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(videoState.characterVisual, null);
  assert.equal(videoState.objectVisual.id, 'custom_object_1');
  assert.equal(videoState.referenceVisual.id, 'custom_object_1');
});

test('restoreVideoStateFromGenerationMetadata: no Character/Object in the original request restores to a clean null state', () => {
  const videoState = {};
  const context = makeVideoContext(videoState);
  const meta = { type: 'video', model: 'seedance_2_fast', settings: {} };
  vm.runInContext('restoreVideoStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(videoState.characterVisual, null);
  assert.equal(videoState.objectVisual, null);
  assert.equal(videoState.referenceVisual, null);
  assert.equal(videoState.startImage, '');
  assert.equal(videoState.endImage, '');
});

test('restoreVoiceStateFromGenerationMetadata: restores the original Runway/ElevenLabs tool, not the default text_to_speech', () => {
  const voiceState = { elevenlabsTool: 'text_to_speech' };
  const context = makeVoiceContext(voiceState);
  const meta = { type: 'voice', model: 'elevenlabs_eleven_v3', settings: { elevenlabs_tool: 'voice_isolation', runway_tool: 'sound_effect' } };
  vm.runInContext('restoreVoiceStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(voiceState.elevenlabsTool, 'voice_isolation');
  assert.equal(voiceState.runwayTool, 'sound_effect');
});

test('restoreVoiceStateFromGenerationMetadata: restores second dialogue voice, speaker count, and duration', () => {
  const voiceState = {};
  const context = makeVoiceContext(voiceState);
  const meta = {
    type: 'voice',
    model: 'elevenlabs_eleven_v3',
    settings: { elevenlabs_second_voice: 'voice-xyz', num_speakers: 2, duration: 12 },
  };
  vm.runInContext('restoreVoiceStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(voiceState.elevenlabsSecondVoice, 'voice-xyz');
  assert.equal(voiceState.numSpeakers, 2);
  assert.equal(voiceState.runwayDuration, 12);
});

test('restoreVoiceStateFromGenerationMetadata: a duration of 0 is still restored (not treated as missing)', () => {
  const voiceState = { runwayDuration: 99 };
  const context = makeVoiceContext(voiceState);
  const meta = { type: 'voice', model: 'runway_gwm1', settings: { duration: 0 } };
  vm.runInContext('restoreVoiceStateFromGenerationMetadata(meta)', Object.assign(context, { meta }));

  assert.equal(voiceState.runwayDuration, 0);
});
