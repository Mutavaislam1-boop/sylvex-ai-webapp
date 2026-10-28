// Pro Studio: the prompt a user sends stays in the workspace as their own
// message (a light-blue block, at most half of the workspace), for every
// generation mode, and a failed generation has a small retry under it that
// sends the same prompt again with the model picked at that moment.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const js = read('webapp/js/cabinet.js');
const css = read('webapp/css/cabinet.css');
const sendChat = js.slice(js.indexOf('  async function sendChat() {'), js.indexOf('  function sanitizeTextForSpeech('));

test('every generation leaves its prompt in the workspace, images included', () => {
  assert.match(sendChat, /const retryRequest = \{\n      prompt: v,/);
  assert.match(sendChat, /if \(photoMode\) \{[\s\S]*?chatMessages\.push\(\{\n          role: 'user',\n          text: shownPrompt,\n          referenceImages: pendingRefs\.length \? pendingRefs\.filter\(\(ref\) => ref\.kind === 'image'\)\.map\(\(ref\) => ref\.src\) : null,\n          displayRefs: pendingRefs\.length \? pendingRefs : null,\n          retryRequest,/);
  assert.match(sendChat, /referenceVideos: referenceVideos\.length \? referenceVideos : null,\n        retryRequest,/);
  assert.doesNotMatch(sendChat, /requestReferences = pendingRefs/);
  assert.doesNotMatch(js, /userPrompt: visibleInputValue/);
});

test('a failed generation shows a retry that resends the prompt with the current model', () => {
  assert.match(js, /if \(m\.isError \|\| !generationThoughtDone\(m\.thought\)\) return '<div class="msg ai generation-loading-msg"><div class="ai-avatar">S<\/div>' \+ slot \+ \(m\.isError \? failedGenerationRetry\(i\) : ''\) \+ '<\/div>';/);
  assert.match(js, /withChatThought\(m, messageHtml\(m, i\), i\)/);
  assert.match(js, /onclick="SYLVEX\.regenMsg\(' \+ i \+ '\)" aria-label="Повторить генерацию"/);
  assert.match(js, /if \(chatMessages\[i\] && chatMessages\[i\]\.isError\) \{\n    retryFailedGeneration\(i\);/);
  const retry = js.slice(js.indexOf('  function retryFailedGeneration(i) {'), js.indexOf('  function regenMsg(i) {'));
  assert.match(retry, /if \(activeGenerationLocked\(\) \|\| generationSubmitting\)/);
  assert.match(retry, /restoreGenerationInputs\(prompt\.retryRequest \|\| \{ prompt: prompt\.text \|\| '', referenceImages: prompt\.referenceImages \|\| \[\] \}\);\n    chatMessages\.splice\(i - 1, 2\);\n    renderChat\(\);\n    sendChat\(\);/);
});

test('a request that could not start gives its inputs back through the same helper', () => {
  assert.match(sendChat, /else if \(!activeGeneration\.jobId\) \{\n        restoreGenerationInputs\(retryRequest\);\n        clearActiveProStudioJob\(\);/);
  assert.match(js, /if \(isVoiceMode\(\) && voiceWorkspaceMode === 'dialogue' && Array\.isArray\(request\.speakerVoices\)\)/);
});

test('the prompt block is light blue and at most half of the workspace', () => {
  assert.match(css, /\.view\[data-view="tools"\]\.active #chatArea \.msg\.user\{max-width:50%\}/);
  assert.match(css, /background:#dbeafe;color:#0b2447;border:1px solid #bfdbfe/);
  assert.match(css, /@media \(max-width:700px\)\{\.view\[data-view="tools"\]\.active #chatArea \.msg\.user\{max-width:80%\}\}/);
});

test('a long prompt starts folded to the composer box; the corner arrow opens it', () => {
  assert.match(js, /function renderFoldablePrompt\(html, index\) \{/);
  assert.match(js, /inner \+= m\.role === 'ai' \? renderSylvexChatLinks\(textHtml\) : renderFoldablePrompt\(textHtml, i\);/);
  assert.match(js, /const fold = Math\.max\(2, Math\.floor\(limit \/ lineHeight\)\) \* lineHeight;/);
  assert.match(js, /return input\.clientHeight - \(parseFloat\(style\.paddingTop\) \|\| 0\) - \(parseFloat\(style\.paddingBottom\) \|\| 0\);/);
  assert.match(js, /    mountReferenceStacks\(el\);\n    foldLongPrompts\(el\);\n    el\.scrollTop = el\.scrollHeight;/);
  assert.match(js, /regenMsg, retryTextGeneration, reportGenerationError, togglePromptFold,/);
  // Usable while a generation runs (the workspace click lock lets it through).
  assert.match(js, /if \(target\.closest\('\.msg-prompt-toggle'\)\) return;\n      if \(target\.closest\('\.view\[data-view="tools"\]'\)\) \{/);
  assert.match(css, /#chatArea \.msg-prompt-toggle\{display:none;position:absolute;right:-8px;bottom:-6px;[^}]*border:0!important;[^}]*background:none!important;/);
  assert.match(css, /#chatArea \.msg-prompt\.is-open \.msg-prompt-toggle svg\{transform:rotate\(180deg\)\}/);
});
