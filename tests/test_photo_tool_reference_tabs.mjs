// Run with: node --test tests/test_photo_tool_reference_tabs.mjs
//
// The upload areas of the photo tools pick references in the one existing
// reference window - Grid Mode's "+ Референс" (История / Персонажи /
// Объекты, the upload of a file under them) - showing only the tabs the area
// takes. Try-On and Replace Character have no intermediate
// "Персонаж / Загрузить" step any more. The Mini App and the website share
// this code.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

function extract(source, name) {
  const match = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm').exec(source);
  assert.ok(match, `declaration not found: ${name}`);
  let depth = 0, i = source.indexOf('{', match.index);
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) break;
  }
  return source.slice(match.index, i + 1);
}

function tabsMap() {
  const match = /const PHOTO_TOOL_REFERENCE_TABS = (\{[\s\S]*?\n\});/.exec(cabinet);
  assert.ok(match, 'PHOTO_TOOL_REFERENCE_TABS not found');
  return vm.runInNewContext('(' + match[1] + ')');
}

test('each upload area shows the tabs of the task table; Logo, Remove Object, Watermark, Face Retouch and the main photos keep their upload', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(tabsMap())), {
    try_on: { person: ['history', 'character'], garments: ['history'] },
    replace_character: { identity: ['history', 'character'] },
    animate_photo: { photo: ['history', 'character', 'object'] },
    tattoo: { photo: ['history', 'character'], tattoo: ['history'] },
    replace_object: { object: ['history', 'object'] },
    hair_beard: { photo: ['history', 'character'] },
  });
});

test('the intermediate Character / Upload step and the redirected Character picker are gone', () => {
  assert.doesNotMatch(cabinet, /choosePhotoToolZoneSource|visualPickerRedirectTarget|ptool-chooser|is-choosing|photo-tool-picking|chooser:true/);
  assert.doesNotMatch(css, /ptool-chooser|photo-tool-picking/);
});

function sandbox() {
  const calls = { picker: [], upload: [], rendered: 0, selected: [] };
  const character = { id: 'char_1', name: 'Islam', previewUrl: 'https://cdn/islam.png', referenceImages: ['https://cdn/r1.png', 'https://cdn/r2.png', 'https://cdn/r3.png', 'https://cdn/r4.png'] };
  let answer = null;
  const ctx = vm.createContext({
    activePhotoTool: 'try_on',
    photoToolState: {
      try_on: { generating: false, personSource: null, personImage: '', personLabel: '', characterId: null, characterReferenceUrls: [], garments: [null, null, null] },
      replace_character: { generating: false, sourceImage: '', identitySource: null, identityImage: '', identityLabel: '', characterId: null, characterReferenceUrls: [] },
      replace_object: { generating: false, files: [null, null] },
    },
    replaceObjectState: { selectedObjectId: null },
    S: { openCatalogReferencePicker: (kind, tabs) => { calls.picker.push([kind, tabs]); return Promise.resolve(answer); } },
    photoToolStateFor: (tool) => ctx.photoToolState[tool],
    photoToolZoneByKey: (key) => ({ key, max: 3, items: [] }),
    openPhotoToolUploadPanel: (key) => calls.upload.push(key),
    renderPhotoToolModal: () => { calls.rendered += 1; },
    updatePresetCardSelection: (...args) => calls.selected.push(args),
    imageCharacters: () => [character],
    normalizeVisualItem: (item) => item,
    visualPreviewUrl: (item) => item.previewUrl,
    isCustomVisualItem: () => false,
  });
  for (const name of ['addPhotoToolZoneItem', 'pickPhotoToolZoneReference', 'setPhotoToolZoneCharacter', 'setPhotoToolZoneItems', 'visualGenerationReferences']) vm.runInContext(extract(cabinet, name), ctx);
  vm.runInContext(/const PHOTO_TOOL_REFERENCE_TABS = \{[\s\S]*?\n\};/.exec(cabinet)[0].replace('const ', 'var '), ctx);
  return { ctx, calls, answer: (value) => { answer = value; } };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test('＋ opens the reference window with the area\'s tabs; other areas open the standard upload panel', async () => {
  const { ctx, calls } = sandbox();
  vm.runInContext("addPhotoToolZoneItem(null, 'garments')", ctx);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.picker)), [['history', ['history']]]);
  ctx.activePhotoTool = 'replace_character';
  vm.runInContext("addPhotoToolZoneItem(null, 'source')", ctx);
  assert.deepEqual(calls.upload, ['source']);
  await tick();
});

test('a Character picked for the Try-On person goes into Try-On\'s own state with up to 3 references', async () => {
  const { ctx, calls, answer } = sandbox();
  answer({ url: 'https://cdn/islam.png', kind: 'image', character_id: 'char_1' });
  vm.runInContext("addPhotoToolZoneItem(null, 'person')", ctx);
  await tick();
  const state = ctx.photoToolState.try_on;
  assert.equal(state.personSource, 'character');
  assert.equal(state.characterId, 'char_1');
  assert.equal(state.personImage, 'https://cdn/islam.png');
  assert.equal(state.personLabel, 'Islam');
  assert.equal(state.characterReferenceUrls.length, 3);
  assert.deepEqual(JSON.parse(JSON.stringify(state.garments)), [null, null, null]);
  assert.equal(calls.rendered, 1);
});

test('a Character picked for the new face of Replace Character goes into its own state', async () => {
  const { ctx, answer } = sandbox();
  ctx.activePhotoTool = 'replace_character';
  answer({ url: 'https://cdn/islam.png', kind: 'image', character_id: 'char_1' });
  vm.runInContext("addPhotoToolZoneItem(null, 'identity')", ctx);
  await tick();
  const state = ctx.photoToolState.replace_character;
  assert.equal(state.identitySource, 'character');
  assert.equal(state.characterId, 'char_1');
  assert.equal(state.identityImage, 'https://cdn/islam.png');
  assert.equal(state.characterReferenceUrls.length, 3);
});

test('a history photo is an upload; an Object picked for Replace Object is marked in its row', async () => {
  const { ctx, calls, answer } = sandbox();
  answer({ url: 'https://cdn/h1.png', kind: 'image' });
  vm.runInContext("addPhotoToolZoneItem(null, 'person')", ctx);
  await tick();
  assert.equal(ctx.photoToolState.try_on.personSource, 'upload');
  assert.equal(ctx.photoToolState.try_on.personImage, 'https://cdn/h1.png');
  ctx.activePhotoTool = 'replace_object';
  answer({ url: 'https://cdn/bag.png', kind: 'image', object_id: 'object_bag' });
  vm.runInContext("addPhotoToolZoneItem(null, 'object')", ctx);
  await tick();
  assert.equal(ctx.photoToolState.replace_object.files[1].url, 'https://cdn/bag.png');
  assert.equal(ctx.replaceObjectState.selectedObjectId, 'object_bag');
  assert.deepEqual(calls.selected.at(-1), ['.replace-object-object-card', 'data-object-id', 'object_bag']);
});

test('the reference window shows only the tabs asked for, above the tool window, and uploads photos', () => {
  const open = extract(cabinet, 'openCatalogReferencePicker');
  assert.match(open, /studioGridReferenceTabs = Array\.isArray\(tabs\) && tabs\.length \? tabs\.filter/);
  assert.match(open, /panel\.classList\.toggle\('for-photo-tool', !!document\.getElementById\('photoToolModal'\)\?\.classList\.contains\('show'\)\);/);
  assert.match(extract(cabinet, 'renderStudioGridReferencePanel'), /\.filter\(\(\[key\]\)=>!studioGridReferenceTabs\|\|studioGridReferenceTabs\.includes\(key\)\)/);
  assert.match(extract(cabinet, 'finishCatalogReferencePicker'), /studioGridReferenceTabs = null;/);
  assert.match(css, /#studioGridReferencePanel\.for-photo-tool\{z-index:1000006 !important\}/);
  assert.match(css, /body:has\(#photoToolModal\.show\) #visualCreateModal\{z-index:1000007 !important\}/);
});
