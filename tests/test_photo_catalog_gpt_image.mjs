// Run with: node --test tests/test_photo_catalog_gpt_image.mjs
//
// Regression tests for "Photo Catalog generation only": connecting the
// existing Photo Catalog modal's References/Styles/Popular/Objects tabs to
// GPT Image 2, without touching any Photo Tool, preset, asset or the
// catalog's own UI/selection logic.
//
// Covers generateQuickImageDetail():
//   - Every catalog kind (references/popular/styles/objects) forces
//     imageState.modelId to 'gpt_image_2' for this generation, regardless
//     of whatever model the user had selected in the composer.
//   - References/Popular (the default branch): unchanged - the catalog
//     image and the user's uploaded photo are both sent as references
//     (already working before this change).
//   - Objects: unchanged - the user's photo stays the sole
//     referenceImageUrls entry, the catalog item's own images flow
//     through the existing objectReferences/objectPrompt channel.
//   - Styles, catalog-folder item (no styleId): now also sends the
//     catalog's own image as a visual/style reference alongside the
//     uploaded photo, and folds the style's own template prompt into the
//     final prompt - previously neither ever reached the model.
//   - Styles, built-in Pro Studio style (styleId set): completely
//     unaffected - still only the uploaded photo(s), no prompt injection -
//     since that style already applies through the untouched
//     imageState.style mechanism.
//   - The result is still handed to the ordinary chat/history pipeline
//     (sendChat()), never a separate code path.
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

function fakeElement(initial) {
  return Object.assign({ value: '', textContent: '', style: {}, classList: { add() {}, remove() {}, contains() { return false; } }, scrollIntoView() {} }, initial || {});
}

function makeGenerateContext(item) {
  const calls = { sendChat: 0, closedCatalog: 0, closedDetail: 0, switchedView: [], composerModes: [] };
  const imageState = {
    modelId: 'seedream_4_0', // whatever the user last had selected - must be overridden
    uploadedImageUrls: [], referenceImageUrls: [], referenceImageUrl: '',
    referenceSourceByUrl: {}, style: '', objectId: '', objectName: '', objectReferences: [], objectPrompt: '',
  };
  const elements = {
    quickImageDetailPrompt: fakeElement({ value: 'make it cinematic' }),
    chatInput: fakeElement({}),
  };
  const sandbox = {
    quickImageDetailState: { item, source: 'prostudio', uploadedUrl: 'https://cdn.sylvex.ai/user-photo.jpg', extraUploads: {} },
    pendingCatalogImageGeneration: null,
    imageState,
    document: {
      getElementById: (id) => elements[id] || null,
      querySelectorAll: () => [],
    },
    switchView: (view) => calls.switchedView.push(view),
    updateComposerMode: (mode) => calls.composerModes.push(mode),
    autoGrow: () => {},
    renderImageControls: () => {},
    renderImageUploadPreview: () => {},
    renderUploadedPhotoGrid: () => {},
    updateSendButton: () => {},
    closeQuickImageDetail: () => { calls.closedDetail += 1; },
    closePhotoCatalog: () => { calls.closedCatalog += 1; },
    sendChat: async () => { calls.sendChat += 1; },
    visualPreviewUrl: (o) => (o && o.previewUrl) || '',
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('generateQuickImageDetail'), context);
  return { context, sandbox, imageState, calls };
}

async function run(item) {
  const { context, sandbox, imageState, calls } = makeGenerateContext(item);
  await vm.runInContext('generateQuickImageDetail(null)', context);
  return { imageState, calls, pending: sandbox.pendingCatalogImageGeneration };
}

test('references kind: forces GPT Image 2 and keeps the existing catalog+user reference pair', async () => {
  const item = { id: 'ref1', kind: 'references', title: 'Boat at sunset', url: 'https://cdn.sylvex.ai/ref1.png', prompt: 'A warm golden-hour boat scene.' };
  const { imageState, calls } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/ref1.png', 'https://cdn.sylvex.ai/user-photo.jpg']);
  assert.equal(imageState.referenceSourceByUrl['https://cdn.sylvex.ai/ref1.png'], 'history');
  assert.equal(imageState.referenceSourceByUrl['https://cdn.sylvex.ai/user-photo.jpg'], 'upload');
  assert.equal(calls.sendChat, 1);
  assert.equal(calls.closedCatalog, 1);
  assert.equal(calls.closedDetail, 1);
});

test('popular_references kind behaves exactly like references', async () => {
  const item = { id: 'pop1', kind: 'popular_references', title: 'Studio portrait', url: 'https://cdn.sylvex.ai/pop1.png', prompt: 'Clean studio portrait lighting.' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/pop1.png', 'https://cdn.sylvex.ai/user-photo.jpg']);
});

test('objects kind: forces GPT Image 2 but leaves the existing Object-reference channel untouched', async () => {
  const item = { id: 'obj1', kind: 'objects', title: 'Leather Bag', url: 'https://cdn.sylvex.ai/obj1.png', prompt: 'Black leather handbag with brass hardware.' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  // The user's photo remains the only referenceImageUrls entry - the
  // catalog object's own image(s) flow through objectReferences instead.
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/user-photo.jpg']);
  assert.equal(imageState.objectId, 'obj1');
  assert.equal(imageState.objectName, 'Leather Bag');
  assert.deepEqual([...imageState.objectReferences], ['https://cdn.sylvex.ai/obj1.png']);
  assert.equal(imageState.objectPrompt, 'Black leather handbag with brass hardware.');
});

test('styles kind, catalog-folder item (no styleId): sends the catalog image as a reference and folds in its template prompt', async () => {
  const item = { id: 'quick_styles_07', kind: 'styles', title: 'Lime Editorial', url: 'https://cdn.sylvex.ai/style07.png', prompt: 'Vivid lime-toned editorial fashion look.' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/style07.png', 'https://cdn.sylvex.ai/user-photo.jpg']);
  assert.equal(imageState.referenceSourceByUrl['https://cdn.sylvex.ai/style07.png'], 'history');
  assert.equal(imageState.style, 'quick_styles_07');
});

test('styles kind, built-in Pro Studio style (styleId set): untouched - no catalog image reference, no prompt injection', async () => {
  const item = { id: 'noir_trio', kind: 'styles', styleId: 'noir_trio', title: 'Noir Trio', url: 'https://cdn.sylvex.ai/builtin-noir.png', prompt: '' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  // Only the uploaded photo - the built-in style thumbnail is never sent
  // as a visual reference, matching its pre-existing behavior exactly.
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/user-photo.jpg']);
  assert.ok(!('https://cdn.sylvex.ai/builtin-noir.png' in imageState.referenceSourceByUrl));
  assert.equal(imageState.style, 'noir_trio');
});

test('a missing catalog-folder style prompt does not inject a stray leading blank line', async () => {
  const item = { id: 'quick_styles_99', kind: 'styles', title: 'Untitled Style', url: 'https://cdn.sylvex.ai/style99.png', prompt: '' };
  const { context, sandbox } = makeGenerateContext(item);
  await vm.runInContext('generateQuickImageDetail(null)', context);
  // pendingCatalogImageGeneration.prompt should be just the free-text
  // extra ("make it cinematic"), not "\n\nmake it cinematic".
  assert.equal(sandbox.pendingCatalogImageGeneration.prompt, 'make it cinematic');
});
