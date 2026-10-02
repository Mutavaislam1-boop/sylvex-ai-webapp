// Run with: node --test tests/test_workspace_isolation_contract.mjs
//
// Master A-Z Remediation Phase 24 (Contract test matrix): a direct
// regression test for the "workspace isolation" leg of the contract
// (Phase 11) that the rest of this effort's test suite exercises only
// indirectly via stubs - each top-level mode (Image/Video/Music/Voice/
// Text) must have its own independent chat space (messages + active
// conversation id), with no cross-mode result leakage, via
// rememberCurrentChatSpace()/restoreChatSpace().
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

function makeContext() {
  const store = {};
  const sandbox = {
    studioMode: 'image',
    activeGenerationLocked: () => false,
    activeGeneration: { mode: '', restoringMode: false },
    currentConvId: null,
    chatMessages: [],
    CHAT_SPACE_TYPES: ['image', 'video', 'music', 'voice', 'text'],
    chatSpaces: {
      image: { activeChatId: null, conversationId: null, messages: [] },
      video: { activeChatId: null, conversationId: null, messages: [] },
      music: { activeChatId: null, conversationId: null, messages: [] },
      voice: { activeChatId: null, conversationId: null, messages: [] },
      text: { activeChatId: null, conversationId: null, messages: [] },
    },
    chatCollections: { image: [], video: [], music: [], voice: [], text: [] },
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (key in store ? store[key] : null),
      setItem: (key, value) => { store[key] = String(value); },
    },
    isImageMode: () => sandbox.studioMode === 'image',
    isVideoMode: () => sandbox.studioMode === 'video',
    isMusicMode: () => sandbox.studioMode === 'music',
    isVoiceMode: () => sandbox.studioMode === 'voice',
    renderChat: () => {},
    renderConvList: () => {},
    updateSendButton: () => {},
    ensureActiveGenerationPlaceholder: () => {},
    openConv: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('chatTypeForMode'), context);
  vm.runInContext(extractFunction('currentChatType'), context);
  vm.runInContext(extractFunction('chatStorageKey'), context);
  vm.runInContext(extractFunction('lastModeStorageKey'), context);
  vm.runInContext(extractFunction('rememberCurrentChatSpace'), context);
  vm.runInContext(extractFunction('loadStoredChatSpace'), context);
  vm.runInContext(extractFunction('latestConversationForType'), context);
  vm.runInContext(extractFunction('restoreChatSpace'), context);
  return { context, sandbox };
}

test('switching modes persists each mode\'s own messages and restores the other mode\'s untouched - no cross-mode leakage', () => {
  const { context, sandbox } = makeContext();

  // Start in Image mode with two image-generation chat messages.
  sandbox.chatMessages = [{ role: 'assistant', type: 'image', url: 'https://cdn.sylvex.ai/a.png' }];
  sandbox.currentConvId = 'conv-image-1';
  vm.runInContext('rememberCurrentChatSpace()', context);

  // Switch to Video mode (as updateComposerMode does before calling
  // restoreChatSpace) - a fresh, empty video chat.
  sandbox.studioMode = 'video';
  vm.runInContext('restoreChatSpace("video")', context);
  assert.deepEqual(sandbox.chatMessages, []);
  assert.equal(sandbox.currentConvId, null);

  // Generate a video result while in Video mode.
  sandbox.chatMessages = [{ role: 'assistant', type: 'video', url: 'https://cdn.sylvex.ai/b.mp4' }];
  sandbox.currentConvId = 'conv-video-1';
  vm.runInContext('rememberCurrentChatSpace()', context);

  // Switch back to Image mode - the earlier image message/conversation
  // must come back exactly as it was, never the video one.
  sandbox.studioMode = 'image';
  vm.runInContext('restoreChatSpace("image")', context);
  assert.equal(sandbox.chatMessages.length, 1);
  assert.equal(sandbox.chatMessages[0].type, 'image');
  assert.equal(sandbox.chatMessages[0].url, 'https://cdn.sylvex.ai/a.png');
  assert.equal(sandbox.currentConvId, 'conv-image-1');

  // And Video mode's own result must still be there, untouched by the
  // round trip through Image mode.
  sandbox.studioMode = 'video';
  vm.runInContext('restoreChatSpace("video")', context);
  assert.equal(sandbox.chatMessages.length, 1);
  assert.equal(sandbox.chatMessages[0].type, 'video');
  assert.equal(sandbox.chatMessages[0].url, 'https://cdn.sylvex.ai/b.mp4');
  assert.equal(sandbox.currentConvId, 'conv-video-1');
});

test('each mode persists to its own localStorage key, never overwriting another mode\'s', () => {
  const { context, sandbox } = makeContext();

  sandbox.chatMessages = [{ role: 'assistant', type: 'music', url: 'https://cdn.sylvex.ai/song.mp3' }];
  sandbox.currentConvId = 'conv-music-1';
  sandbox.studioMode = 'music';
  vm.runInContext('rememberCurrentChatSpace()', context);

  sandbox.chatMessages = [{ role: 'assistant', type: 'voice', url: 'https://cdn.sylvex.ai/line.mp3' }];
  sandbox.currentConvId = 'conv-voice-1';
  sandbox.studioMode = 'voice';
  vm.runInContext('rememberCurrentChatSpace()', context);

  const musicKey = vm.runInContext('chatStorageKey("music")', context);
  const voiceKey = vm.runInContext('chatStorageKey("voice")', context);
  assert.notEqual(musicKey, voiceKey);
  const storedMusic = JSON.parse(sandbox.localStorage.getItem(musicKey));
  const storedVoice = JSON.parse(sandbox.localStorage.getItem(voiceKey));
  assert.equal(storedMusic.messages[0].url, 'https://cdn.sylvex.ai/song.mp3');
  assert.equal(storedVoice.messages[0].url, 'https://cdn.sylvex.ai/line.mp3');
});
