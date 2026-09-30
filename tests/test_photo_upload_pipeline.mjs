// Run with: node --test tests/test_photo_upload_pipeline.mjs
//
// Regression tests for the Pro Studio photo upload/reference audit:
//
// Root cause found: the Image-mode "select a local photo" path
// (processAttachFile's pendingKind === 'image' branch) never called the
// real /api/public/prostudio/upload-media endpoint at selection time - it
// only FileReader'd the file into a local data: URL and stored THAT as the
// generation reference. The real upload was deferred to Generate time
// (buildGenerationRequest -> normalizeGenerationImageReference ->
// uploadProStudioMediaFile), so a photo could look "attached" in the
// composer for an arbitrary time before its first real validation against
// the server (wrong format, too large, etc.) ever happened. Every other
// upload path in this file (video edit input, video references, voice,
// text attachments, Grid's onStudioGridMediaFiles) already uploads eagerly
// via uploadProStudioMediaFile and only records a reference on success -
// this brings the primary Image-mode path in line with that existing,
// already-correct pattern instead of inventing a new one.
//
// These tests cover the repaired path only:
// - a fresh local photo now uploads immediately and the confirmed SERVER
//   URL (never a data:/blob: URL) becomes the reference, converging with
//   how History/Share/Grid references already look;
// - a HEIC/HEIF file is rejected client-side with a specific message
//   before ever calling the upload endpoint (the endpoint's allowed_exts
//   never included .heic/.heif, but the file picker's accept attribute
//   still listed them - see openNativeFilePicker);
// - a failed upload never adds anything to referenceImageUrls/
//   uploadedImageUrls (no silent "generate without the photo" fallback);
// - imageState.uploading (bookkeeping for the in-flight upload) never
//   leaks into the wire payload built by imageOptionsPayload;
// - Generate is disabled (updateSendButton) while any photo upload is
//   still in flight, mirroring the existing textState.attachment.uploading
//   gate for Text mode.
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

function baseImageState(extra) {
  return Object.assign({
    modelId: 'seedream_5_0_lite',
    referenceImageUrl: '',
    referenceImageUrls: [],
    uploadedImageUrls: [],
    referenceSourceByUrl: {},
    uploading: [],
    attachment: null,
    style: 'auto',
    characterId: null,
    objectId: null,
  }, extra || {});
}

function makeUploadContext(imageState, opts) {
  const logs = [];
  const toasts = [];
  const options = opts || {};
  const context = vm.createContext({
    console: { info: (...args) => logs.push(args) },
    toast: (msg) => toasts.push(msg),
    imageState,
    imageReadRevisionByTarget: {},
    getUploadTarget: () => 'image_upload',
    UPLOAD_TARGETS: { IMAGE_UPLOAD: 'image_upload', VIDEO_START: 'video_start', VIDEO_END: 'video_end', VIDEO_REFERENCES: 'video_references' },
    uploadLimitForTarget: () => 4,
    renderImageUploadPreview: () => {},
    renderUploadedPhotoGrid: () => {},
    renderUploadPreviewForTarget: () => {},
    updateSendButton: () => {},
    isVideoFileLike: () => false,
    isAudioFileLike: () => false,
    isImageFileLike: (f) => /^image\//i.test(String(f && f.type || '')),
    isKlingOmniEditUploadContext: () => false,
    isVoiceMode: () => false,
    isMusicMode: () => false,
    isVideoMode: () => false,
    studioMode: 'image',
    window: { URL: { createObjectURL: () => 'blob:preview', revokeObjectURL: () => {} } },
    URL: { createObjectURL: () => 'blob:preview', revokeObjectURL: () => {} },
    uploadProStudioMediaFile: options.uploadProStudioMediaFile || (async () => 'https://cdn.sylvex.ai/uploads/photo.jpg'),
  });
  vm.runInContext(extractFunction('processAttachFile'), context);
  vm.runInContext(extractFunction('applyUploadToTarget'), context);
  return { context, logs, toasts };
}

test('fresh local photo: uploads eagerly and the server URL becomes the reference (converges with History/Grid representation)', async () => {
  const imageState = baseImageState();
  const { context, logs, toasts } = makeUploadContext(imageState, {
    uploadProStudioMediaFile: async (file, kind) => {
      assert.equal(kind, 'image');
      return 'https://cdn.sylvex.ai/uploads/real-photo.jpg';
    },
  });
  const file = { name: 'photo.jpg', type: 'image/jpeg', size: 500_000 };
  await vm.runInContext('processAttachFile(f, "image", undefined, 0)', Object.assign(context, { f: file }));

  assert.deepEqual(imageState.referenceImageUrls, ['https://cdn.sylvex.ai/uploads/real-photo.jpg']);
  assert.equal(imageState.referenceImageUrl, 'https://cdn.sylvex.ai/uploads/real-photo.jpg');
  assert.deepEqual(imageState.uploadedImageUrls, ['https://cdn.sylvex.ai/uploads/real-photo.jpg']);
  // Never a local data:/blob: URL - only a confirmed server reference.
  assert.ok(!/^data:|^blob:/i.test(imageState.referenceImageUrl));
  assert.deepEqual(imageState.uploading, []);
  assert.ok(logs.some((entry) => entry[0] === 'PHOTO_UPLOAD_STARTED'));
  assert.ok(logs.some((entry) => entry[0] === 'PHOTO_UPLOAD_COMPLETED'));
  assert.ok(logs.some((entry) => entry[0] === 'PHOTO_REFERENCE_SELECTED' && entry[1].reference_count === 1));
  assert.ok(toasts.includes('Фото добавлено'));
});

test('fresh local photo: imageState.uploading is populated (and Generate-blocking) for the duration of the network call', async () => {
  const imageState = baseImageState();
  let resolveUpload;
  const uploadPromise = new Promise((resolve) => { resolveUpload = resolve; });
  const { context } = makeUploadContext(imageState, {
    uploadProStudioMediaFile: async () => uploadPromise,
  });
  const file = { name: 'photo.jpg', type: 'image/jpeg', size: 500_000 };
  const call = vm.runInContext('processAttachFile(f, "image", undefined, 0)', Object.assign(context, { f: file }));

  // Upload not resolved yet - the reference must not exist, but the
  // uploading bookkeeping must show the in-flight file.
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(imageState.uploading.length, 1);
  assert.equal(imageState.referenceImageUrls.length, 0);

  resolveUpload('https://cdn.sylvex.ai/uploads/real-photo.jpg');
  await call;
  assert.deepEqual(imageState.uploading, []);
  assert.deepEqual(imageState.referenceImageUrls, ['https://cdn.sylvex.ai/uploads/real-photo.jpg']);
});

test('HEIC/HEIF photo: rejected client-side before ever calling upload-media', async () => {
  const imageState = baseImageState();
  let uploadCalled = false;
  const { context, toasts } = makeUploadContext(imageState, {
    uploadProStudioMediaFile: async () => { uploadCalled = true; return 'https://cdn.sylvex.ai/uploads/should-not-happen.jpg'; },
  });
  const file = { name: 'IMG_0001.HEIC', type: 'image/heic', size: 4_000_000 };
  await vm.runInContext('processAttachFile(f, "image", undefined, 0)', Object.assign(context, { f: file }));

  assert.equal(uploadCalled, false);
  assert.deepEqual(imageState.referenceImageUrls, []);
  assert.deepEqual(imageState.uploading, []);
  assert.ok(toasts.some((msg) => /HEIC/i.test(msg)));
});

test('failed upload (e.g. the backend 400s): reference is never added - no silent "generate without the photo" fallback', async () => {
  const imageState = baseImageState();
  const { context, logs, toasts } = makeUploadContext(imageState, {
    uploadProStudioMediaFile: async () => { throw new Error('invalid_image'); },
  });
  const file = { name: 'photo.jpg', type: 'image/jpeg', size: 500_000 };
  await vm.runInContext('processAttachFile(f, "image", undefined, 0)', Object.assign(context, { f: file }));

  assert.deepEqual(imageState.referenceImageUrls, []);
  assert.deepEqual(imageState.uploadedImageUrls, []);
  assert.equal(imageState.referenceImageUrl, '');
  assert.deepEqual(imageState.uploading, []);
  assert.ok(logs.some((entry) => entry[0] === 'PHOTO_UPLOAD_FAILED'));
  assert.ok(toasts.some((msg) => /HEIC|повреждён/i.test(msg)));
});

test('History-style reselection (selectUploadedPhoto) converges to the identical referenceImageUrls representation as a fresh upload', async () => {
  const imageState = baseImageState({ uploadedImageUrls: ['https://cdn.sylvex.ai/uploads/older.jpg'] });
  const context = vm.createContext({
    console: { info: () => {} },
    toast: () => {},
    imageState,
    getUploadTarget: () => 'image_upload',
    UPLOAD_TARGETS: { IMAGE_UPLOAD: 'image_upload' },
    uploadLimitForTarget: () => 4,
    renderImageUploadPreview: () => {},
    renderUploadedPhotoGrid: () => {},
    renderUploadPreviewForTarget: () => {},
    updateSendButton: () => {},
  });
  vm.runInContext(extractFunction('applyUploadToTarget'), context);
  vm.runInContext(extractFunction('selectUploadedPhoto'), context);
  vm.runInContext('selectUploadedPhoto(null, "https://cdn.sylvex.ai/uploads/older.jpg")', context);

  assert.deepEqual(imageState.referenceImageUrls, ['https://cdn.sylvex.ai/uploads/older.jpg']);
  assert.equal(imageState.referenceImageUrl, 'https://cdn.sylvex.ai/uploads/older.jpg');
});

test('imageOptionsPayload: internal uploading bookkeeping never leaks into the generation request payload', () => {
  const imageState = baseImageState({ uploading: [{ name: 'in-flight.jpg', size: 1, mime: 'image/jpeg', previewUrl: 'blob:x' }] });
  const context = vm.createContext({
    imageState,
    getModelCapabilities: () => ({ seed: false }),
    normalizeImageSeed: (v) => v,
    imageVisualReferenceOptions: () => ({}),
  });
  vm.runInContext(extractFunction('imageOptionsPayload'), context);
  const payload = vm.runInContext('imageOptionsPayload([])', context);
  assert.equal(payload.uploading, undefined);
  assert.equal(payload.referenceSourceByUrl, undefined);
});

function makeSendButtonElement() {
  return {
    value: '',
    hidden: false,
    disabled: false,
    title: '',
    classList: {
      _set: new Set(['studio-generate']),
      add(name) { this._set.add(name); },
      remove(name) { this._set.delete(name); },
      contains(name) { return this._set.has(name); },
      toggle(name, force) { if (force) this._set.add(name); else this._set.delete(name); },
    },
    setAttribute() {},
    querySelector: () => ({ textContent: '' }),
  };
}

function makeSendButtonContext(imageState, sendButton) {
  const elements = { chatInput: { value: '' }, micBtn: { hidden: false }, sendBtn: sendButton };
  return vm.createContext({
    document: { getElementById: (id) => elements[id] || null },
    studioMode: 'image',
    textRequestInFlight: false,
    activeGenerationLocked: () => false,
    activeGeneration: { status: '' },
    activeGenerationButtonLabel: () => '',
    isVideoMode: () => false,
    currentVideoReferenceImages: () => [],
    isImageMode: () => true,
    currentModeAttachment: () => null,
    isMusicMode: () => false,
    isVoiceMode: () => false,
    currentAudioState: () => ({ uploads: [] }),
    textState: { attachment: null },
    canGenerateImageFromControls: () => true,
    imageState,
    currentVideoEditInputUrl: () => '',
    currentVideoReferenceUrl: () => '',
  });
}

test('updateSendButton: Generate stays enabled once nothing is uploading', () => {
  const imageState = baseImageState({ referenceImageUrls: ['https://cdn.sylvex.ai/uploads/a.jpg'] });
  const sendButton = makeSendButtonElement();
  const context = makeSendButtonContext(imageState, sendButton);
  vm.runInContext(extractFunction('updateSendButton'), context);
  vm.runInContext('updateSendButton()', context);
  assert.equal(sendButton.disabled, false);
});

test('updateSendButton: Generate is disabled while a photo upload is still in flight (CRITICAL BEHAVIOR - never generate pretending the photo is attached)', () => {
  const imageState = baseImageState({
    referenceImageUrls: [],
    uploading: [{ name: 'in-flight.jpg', size: 1, mime: 'image/jpeg', previewUrl: 'blob:x' }],
  });
  const sendButton = makeSendButtonElement();
  const context = makeSendButtonContext(imageState, sendButton);
  vm.runInContext(extractFunction('updateSendButton'), context);
  vm.runInContext('updateSendButton()', context);
  assert.equal(sendButton.disabled, true);
});
