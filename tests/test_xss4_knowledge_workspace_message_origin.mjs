// Run with: node --test tests/test_xss4_knowledge_workspace_message_origin.mjs
//
// Regression tests for the security audit's XSS-4 finding:
//
// webapp/js/knowledge-workspace.js's window.addEventListener('message', ...)
// listener (the bridge between Pro Studio's "Knowledge Workspace" iframe and
// its parent page) accepted any message whose event.data.source happened to
// equal the string 'sylvex-knowledge-parent' - with no check at all on
// event.origin or event.source. Since postMessage delivery is not restricted
// by same-origin policy, any page/frame that merely holds a reference to
// this window (not just the real parent) could spoof a reply and drive real
// state changes (injecting a fabricated music/voice library, or appending a
// fabricated "AI" chat message).
//
// Fix: the listener now rejects anything whose event.origin isn't this
// iframe's own location.origin (the one trusted origin - this iframe is
// always loaded via a relative src from the exact same origin, see
// openKnowledgeWorkspace() in cabinet.js, so every outbound postMessage in
// this same file already targets location.origin, never '*') or whose
// event.source isn't window.parent, before looking at the message content
// at all.
//
// Exercises the REAL extracted listener function via node:vm (same pattern
// as test_xss1_account_auth_escaping.mjs / test_studio_theme.mjs), not a
// reimplementation, so these tests prove the actual production behavior.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/knowledge-workspace.js', import.meta.url), 'utf8');

function extractMessageListenerSource(src) {
  const marker = "window.addEventListener('message',event=>{";
  const start = src.indexOf(marker);
  assert.ok(start >= 0, 'message listener registration not found');
  const braceIndex = start + marker.length - 1; // index of the opening '{'
  let depth = 0;
  let i = braceIndex;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < src.length, 'matching close brace not found');
  return 'event=>' + src.slice(braceIndex, i + 1);
}

const LISTENER_SRC = extractMessageListenerSource(source);

const TRUSTED_ORIGIN = 'https://sylvex.ai';

function makeContext() {
  const calls = {
    loadMusicSlides: [],
    renderFixedDemoAvatars: 0,
    renderVoiceSpeakers: 0,
    setVoicePreview: [],
    appendTextMessage: [],
    removedLoadingBubble: 0,
  };
  const parent = {}; // the trusted source - the real parent window
  const foreignWindow = {}; // any other window reference - never trusted
  const context = vm.createContext({
    location: {origin: TRUSTED_ORIGIN},
    window: {parent},
    document: {
      querySelector: (selector) => {
        if (selector === '.quick-text-message.loading') return {remove: () => { calls.removedLoadingBubble++; }};
        return null;
      },
    },
    loadMusicSlides: (tracks) => calls.loadMusicSlides.push(tracks),
    renderFixedDemoAvatars: () => { calls.renderFixedDemoAvatars++; },
    renderVoiceSpeakers: () => { calls.renderVoiceSpeakers++; },
    setVoicePreview: (voice, autoplay) => calls.setVoicePreview.push([voice, autoplay]),
    appendTextMessage: (role, text) => calls.appendTextMessage.push([role, text]),
  });
  // The real module's closed-over `let` state these actions read/reassign.
  context.voiceLibrary = [];
  context.demoVoiceLibrary = ['d0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6'];
  context.selectedSpeakers = [{id: 'v1', name: 'One'}, {id: '', name: 'Two'}];
  vm.runInContext('globalThis.__listener = ' + LISTENER_SRC + ';', context);
  return {context, calls, parent, foreignWindow};
}

test('trusted origin + real parent window: voice-library message is accepted and applied', () => {
  const {context, calls, parent} = makeContext();
  context.__listener({
    origin: TRUSTED_ORIGIN,
    source: parent,
    data: {source: 'sylvex-knowledge-parent', action: 'voice-library', voices: [{id: 'v1', name: 'One'}], demoVoices: ['a', 'b', 'c', 'd', 'e', 'f', 'g']},
  });
  assert.equal(calls.renderFixedDemoAvatars, 1);
  assert.equal(calls.renderVoiceSpeakers, 1);
  assert.equal(calls.setVoicePreview.length, 1);
  assert.deepEqual(context.demoVoiceLibrary, ['a', 'b', 'c', 'd', 'e', 'f', 'g']);
});

test('trusted origin + real parent window: music-library and text-chat-result still work unchanged', () => {
  const {context, calls, parent} = makeContext();
  context.__listener({origin: TRUSTED_ORIGIN, source: parent, data: {source: 'sylvex-knowledge-parent', action: 'music-library', tracks: [{id: 't1'}]}});
  assert.deepEqual(calls.loadMusicSlides, [[{id: 't1'}]]);

  context.__listener({origin: TRUSTED_ORIGIN, source: parent, data: {source: 'sylvex-knowledge-parent', action: 'text-chat-result', text: 'Hello'}});
  assert.equal(calls.removedLoadingBubble, 1);
  assert.deepEqual(calls.appendTextMessage, [['ai', 'Hello']]);
});

test('foreign origin is rejected without any side effects, even with a correctly shaped payload', () => {
  const {context, calls, parent} = makeContext();
  context.__listener({
    origin: 'https://evil.example',
    source: parent,
    data: {source: 'sylvex-knowledge-parent', action: 'music-library', tracks: [{id: 'malicious'}]},
  });
  assert.deepEqual(calls.loadMusicSlides, []);
  assert.equal(calls.renderVoiceSpeakers, 0);
  assert.equal(calls.appendTextMessage.length, 0);
});

test('correct origin but wrong window/source is rejected without any side effects', () => {
  const {context, calls, foreignWindow} = makeContext();
  context.__listener({
    origin: TRUSTED_ORIGIN,
    source: foreignWindow, // same origin, but not window.parent
    data: {source: 'sylvex-knowledge-parent', action: 'text-chat-result', text: 'spoofed'},
  });
  assert.equal(calls.removedLoadingBubble, 0);
  assert.deepEqual(calls.appendTextMessage, []);
});

test('missing origin/source (e.g. a non-postMessage-shaped event) is rejected, not just empty data', () => {
  const {context, calls} = makeContext();
  context.__listener({origin: '', source: null, data: {source: 'sylvex-knowledge-parent', action: 'text-chat-result', text: 'x'}});
  assert.deepEqual(calls.appendTextMessage, []);
});

test('trusted origin and source but an unrelated message.source string is still ignored (pre-existing content check preserved)', () => {
  const {context, calls, parent} = makeContext();
  context.__listener({origin: TRUSTED_ORIGIN, source: parent, data: {source: 'something-else', action: 'text-chat-result', text: 'x'}});
  assert.deepEqual(calls.appendTextMessage, []);
});
