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
//   - Styles and Objects send only the photo uploaded by the user. Their
//     catalog image is presentation-only, while their built-in prompt is
//     folded into the generation instruction.
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
  const context = vm.createContext(Object.assign(sandbox, { guestNeedsAccount: () => false }));
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

test('objects kind: uses only the user photo and the built-in object prompt', async () => {
  const item = { id: 'obj1', kind: 'objects', title: 'Leather Bag', url: 'https://cdn.sylvex.ai/obj1.png', prompt: 'Black leather handbag with brass hardware.' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/user-photo.jpg']);
  assert.equal(imageState.objectId, 'obj1');
  assert.equal(imageState.objectName, 'Leather Bag');
  assert.deepEqual([...imageState.objectReferences], []);
  assert.equal(imageState.objectPrompt, 'Black leather handbag with brass hardware.');
});

test('styles kind, catalog-folder item: uses only the user photo and folds in its template prompt', async () => {
  const item = { id: 'quick_styles_07', kind: 'styles', title: 'Lime Editorial', url: 'https://cdn.sylvex.ai/style07.png', prompt: 'Vivid lime-toned editorial fashion look.' };
  const { imageState } = await run(item);
  assert.equal(imageState.modelId, 'gpt_image_2');
  assert.deepEqual([...imageState.referenceImageUrls], ['https://cdn.sylvex.ai/user-photo.jpg']);
  assert.ok(!('https://cdn.sylvex.ai/style07.png' in imageState.referenceSourceByUrl));
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

test('catalog transport strips hidden style and object images while retaining both display thumbnails', () => {
  const sandbox = {};
  const context = vm.createContext(Object.assign(sandbox, { guestNeedsAccount: () => false }));
  vm.runInContext(extractFunction('applyCatalogImageGenerationOptions'), context);
  const base = {
    referenceImageUrls: ['https://cdn.sylvex.ai/catalog.png', 'https://cdn.sylvex.ai/user.jpg'],
    referenceImages: ['https://cdn.sylvex.ai/catalog.png', 'https://cdn.sylvex.ai/user.jpg'],
    uploadedImageUrls: ['https://cdn.sylvex.ai/user.jpg'],referenceImageUrl:'https://cdn.sylvex.ai/catalog.png',
    characterId:'old-character',characterReferences:['https://cdn.sylvex.ai/character.jpg'],
    objectId:'obj',objectName:'Bag',objectPrompt:'Bag prompt',objectReferences:['https://cdn.sylvex.ai/catalog.png'],
    style:'cinematic',style_id:'cinematic',style_prompt:'Old style',
  };
  const catalog = {kind:'objects',catalogUrl:'https://cdn.sylvex.ai/catalog.png',userUrl:'https://cdn.sylvex.ai/user.jpg',itemId:'obj',displayPrompt:'Object: Bag'};
  sandbox.options=structuredClone(base);sandbox.catalog=catalog;
  vm.runInContext('applyCatalogImageGenerationOptions(options,catalog)',context);
  assert.deepEqual([...sandbox.options.referenceImageUrls],['https://cdn.sylvex.ai/user.jpg']);
  assert.deepEqual([...sandbox.options.referenceImages],['https://cdn.sylvex.ai/user.jpg']);
  assert.deepEqual([...sandbox.options.characterReferences],[]);assert.deepEqual([...sandbox.options.objectReferences],[]);
  assert.equal(sandbox.options.objectId,null);assert.equal(sandbox.options.objectPrompt,'');assert.equal(sandbox.options.style,'auto');
  assert.equal(sandbox.options.catalog_reference_url,catalog.catalogUrl);
  assert.deepEqual([...sandbox.options.reference_roles],['catalog_display','user']);

  vm.runInContext(extractFunction('requestImageReferences')+'\n'+extractFunction('requestDisplayReferences')+'\nfunction imageStyleSheetItem(){return null}',context);
  sandbox.meta={type:'image',catalog_reference_url:catalog.catalogUrl,image_options:sandbox.options};
  assert.deepEqual([...vm.runInContext('requestImageReferences(meta)',context)],['https://cdn.sylvex.ai/user.jpg']);
  assert.deepEqual([...vm.runInContext('requestDisplayReferences(meta)',context).map((ref) => ref.src)],[catalog.catalogUrl,'https://cdn.sylvex.ai/user.jpg']);

  sandbox.options=structuredClone(base);sandbox.catalog={...catalog,kind:'references'};
  vm.runInContext('applyCatalogImageGenerationOptions(options,catalog)',context);
  assert.deepEqual([...sandbox.options.referenceImageUrls],[catalog.catalogUrl,'https://cdn.sylvex.ai/user.jpg'],'ordinary reference catalog behavior stays unchanged');
  assert.deepEqual([...sandbox.options.objectReferences],[catalog.catalogUrl]);
});
