// Run with: node --test tests/test_m060_text_mode_attach_restore.mjs
//
// Regression tests for M-060 (Pro Studio A-Z audit): the "+" attachment
// entry point (plusSheet/togglePlusPop) had no visible trigger anywhere in
// the current composer markup, and even if reconnected, attach()/
// addMediaLink() (the functions plusSheet's Photo/Video/Audio/File/Image
// URL/Video URL buttons call) had no Text-mode branch at all - a click
// while in Text mode fell through to the image-generation reference-upload
// default, not Text mode's existing "describe this / create a prompt from
// this" media-attach flow (textState.attachment, capability-gated
// tool/model auto-switch, already fully built and used by the old "Файл"
// button). This restores the "+" specifically in Text mode's composer and
// fixes attach()/addMediaLink() to route there correctly, reusing that
// pre-existing flow unchanged rather than replacing it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');

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

function fakeElement(overrides) {
  return Object.assign({
    classList: {add() {}, remove() {}},
    click() {},
    value: '',
    accept: '',
    multiple: false,
  }, overrides || {});
}

test('cabinet.html: Text mode composer has a visible "+" that opens plusSheet', () => {
  const textToolsBlock = html.slice(html.indexOf('studio-text-tools'), html.indexOf('studio-text-tools') + 800);
  assert.ok(textToolsBlock.includes('SYLVEX.togglePlusPop(event)'), 'Text mode composer button must open plusSheet');
});

test('cabinet.html: plusSheet has dedicated Video and Audio file-attach buttons', () => {
  const sheetBlock = html.slice(html.indexOf('id="plusSheet"'), html.indexOf('id="plusSheet"') + 2000);
  assert.ok(sheetBlock.includes(`SYLVEX.attach('video')`));
  assert.ok(sheetBlock.includes(`SYLVEX.attach('audio')`));
});

function buildAttachContext(studioMode) {
  const inp = fakeElement();
  const sandbox = {
    document: {getElementById: (id) => (id === 'attachInput' ? inp : fakeElement())},
    studioMode,
    pendingAttachAccept: '',
    isKlingOmniEditUploadContext: () => false,
    isVideoMode: () => false,
    videoUploadTargetAllowsVideo: () => true,
    isMusicMode: () => false,
    videoState: {section: 'generate'},
    openVideoEditInputUpload: () => {},
    openVideoStartUpload: () => {},
    openVideoEndUpload: () => {},
    openVideoReferencesUpload: () => {},
    openImageUpload: () => { sandbox.openImageUploadCalled = true; },
    getUploadTarget: () => 'image_upload',
    UPLOAD_TARGETS: {VIDEO_START: 'video_start', VIDEO_END: 'video_end', VIDEO_EDIT_INPUT: 'video_edit_input'},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('openNativeFilePicker'), context);
  vm.runInContext(extractFunction('attach'), context);
  return {context, inp};
}

test('attach(): in Text mode, Photo routes to the text_image picker (image-only accept, text_media pending kind)', () => {
  const {context, inp} = buildAttachContext('text');
  vm.runInContext(`attach('image')`, context);
  assert.equal(vm.runInContext('pendingAttachAccept', context), 'text_media');
  assert.equal(inp.accept, 'image/*,.heic,.heif');
  assert.equal(vm.runInContext('typeof openImageUploadCalled', context), 'undefined', 'must not fall through to the image-generation upload default');
});

test('attach(): in Text mode, Video routes to the text_video picker', () => {
  const {context, inp} = buildAttachContext('text');
  vm.runInContext(`attach('video')`, context);
  assert.equal(vm.runInContext('pendingAttachAccept', context), 'text_media');
  assert.ok(inp.accept.includes('video/mp4'));
});

test('attach(): in Text mode, Audio routes to the text_audio picker', () => {
  const {context, inp} = buildAttachContext('text');
  vm.runInContext(`attach('audio')`, context);
  assert.equal(vm.runInContext('pendingAttachAccept', context), 'text_media');
  assert.ok(inp.accept.includes('audio/mpeg'));
});

test('attach(): in Text mode, File routes to the text_document picker', () => {
  const {context, inp} = buildAttachContext('text');
  vm.runInContext(`attach('file')`, context);
  assert.equal(vm.runInContext('pendingAttachAccept', context), 'text_document');
  assert.ok(inp.accept.includes('application/pdf'));
});

test('attach(): non-text modes are unaffected (image kind still falls through to the generation upload default)', () => {
  const {context} = buildAttachContext('image');
  vm.runInContext(`attach('image')`, context);
  assert.equal(vm.runInContext('openImageUploadCalled', context), true);
});

function buildAddMediaLinkContext(promptedUrl) {
  const sandbox = {
    document: {getElementById: () => fakeElement()},
    window: {prompt: () => promptedUrl},
    studioMode: 'text',
    textState: {tool: 'text', attachment: null},
    pendingAttachment: null,
    isVideoMode: () => false,
    isMusicMode: () => false,
    isVoiceMode: () => false,
    isImageMode: () => false,
    currentAudioState: () => ({uploads: []}),
    applyUploadToTarget: () => {},
    applyVideoEditInputToState: () => {},
    applyVideoReferenceToState: () => {},
    getUploadTarget: () => '',
    UPLOAD_TARGETS: {VIDEO_EDIT_INPUT: 'video_edit_input', VIDEO_REFERENCES: 'video_references'},
    selectGeminiForTextMedia: () => { sandbox.textState.familyId = 'gemini'; },
    selectVisionModelForTextImage: () => { sandbox.textState.familyId = 'gpt'; },
    renderTextControls: () => {},
    renderComposerImageDraft: () => {},
    renderVoiceToolPanel: () => {},
    updateSendButton: () => {},
    toast: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('addMediaLink'), context);
  return context;
}

test('addMediaLink(): pasting an Image URL in Text mode sets textState.attachment and switches to a vision-capable model', () => {
  const context = buildAddMediaLinkContext('https://example.com/photo.png');
  vm.runInContext(`addMediaLink('image')`, context);
  const attachment = vm.runInContext('textState.attachment', context);
  assert.equal(attachment.kind, 'image');
  assert.equal(attachment.url, 'https://example.com/photo.png');
  assert.equal(vm.runInContext('textState.tool', context), 'image_prompt');
  assert.equal(vm.runInContext('textState.familyId', context), 'gpt');
  assert.equal(vm.runInContext('pendingAttachment', context).url, 'https://example.com/photo.png');
});

test('addMediaLink(): pasting a Video URL in Text mode sets textState.attachment and switches to Gemini', () => {
  const context = buildAddMediaLinkContext('https://example.com/clip.mp4');
  vm.runInContext(`addMediaLink('video')`, context);
  const attachment = vm.runInContext('textState.attachment', context);
  assert.equal(attachment.kind, 'video');
  assert.equal(vm.runInContext('textState.tool', context), 'video_prompt');
  assert.equal(vm.runInContext('textState.familyId', context), 'gemini');
});

test('addMediaLink(): an existing non-default tool selection is not overwritten', () => {
  const context = buildAddMediaLinkContext('https://example.com/photo.png');
  vm.runInContext(`textState.tool = 'summarize'`, context);
  vm.runInContext(`addMediaLink('image')`, context);
  assert.equal(vm.runInContext('textState.tool', context), 'summarize');
});

test('addMediaLink(): an empty prompt response attaches nothing', () => {
  const context = buildAddMediaLinkContext('   ');
  vm.runInContext(`addMediaLink('image')`, context);
  assert.equal(vm.runInContext('textState.attachment', context), null);
});
