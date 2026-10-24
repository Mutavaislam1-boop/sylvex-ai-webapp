// Run with: node --test tests/test_replace_object_objects_row.mjs
//
// Regression test for "Pro Studio Mini App - Photo Tools UI Polish",
// item 9: Replace Object gets a horizontal row of the user's existing Pro
// Studio Objects (imageObjects() - the same data/creation flow the main
// composer's Object picker already uses, never a second Object system)
// right under its Before/After preview, Create Object first then every
// existing Object, with the same toggle/no-flicker/no-scroll-jump
// selection behavior as every other Photo Tool reference list.
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
  return Object.assign({
    innerHTML: '',
    classList: {
      set: new Set(),
      add(c) { this.set.add(c); },
      remove(c) { this.set.delete(c); },
      contains(c) { return this.set.has(c); },
      toggle(c, v) { const on = v === undefined ? !this.set.has(c) : !!v; if (on) this.set.add(c); else this.set.delete(c); },
    },
    setAttribute(name, value) { this.attrs = this.attrs || {}; this.attrs[name] = String(value); },
    getAttribute(name) { return this.attrs ? (this.attrs[name] ?? null) : null; },
  }, initial || {});
}

function makeContext() {
  const objects = [
    { id: 'obj_lamp', name: 'Лампа', previewUrl: 'https://cdn.sylvex.ai/lamp.png' },
    { id: 'obj_chair', name: 'Стул', previewUrl: 'https://cdn.sylvex.ai/chair.png' },
  ];
  const zones = fakeElement({});
  const objectCards = [
    fakeElement({ attrs: { 'data-object-id': 'obj_lamp' } }),
    fakeElement({ attrs: { 'data-object-id': 'obj_chair' } }),
  ];
  const calls = { renderPhotoToolModal: 0, updatePhotoToolGenerateButtonState: 0 };
  const sandbox = {
    activePhotoTool: 'replace_object',
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    PHOTO_TOOL_CONFIG: { replace_object: { labels: ['Основное фото', 'Предмет для замены'], max: 2 } },
    photoToolState: { replace_object: { files: [], generating: false } },
    replaceObjectState: { selectedObjectId: null },
    imageObjects: () => objects,
    normalizeVisualItem: (item) => item,
    visualPreviewUrl: (item) => (item && item.previewUrl) || '',
    createPhotoToolReference: () => {},
    scrollPresetCarousel: () => {},
    document: {
      getElementById: (id) => (id === 'ptoolZones' ? zones : null),
      querySelector: () => null,
      querySelectorAll: (sel) => (sel === '.replace-object-object-card' ? objectCards : []),
    },
    renderPhotoToolModal: () => { calls.renderPhotoToolModal += 1; },
    updatePhotoToolGenerateButtonState: () => { calls.updatePhotoToolGenerateButtonState += 1; },
  };
  const context = vm.createContext(sandbox);
  for (const name of ['photoToolStateFor', 'replaceObjectObjectsRowHtml', 'updatePresetCardSelection', 'photoToolZones', 'photoToolZoneHtml', 'photoToolZonesInnerHtml', 'refreshPhotoToolZones', 'photoToolMarkBadgeHtml', 'selectReplaceObjectObject']) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, calls, objects, objectZone: () => zones.innerHTML.split('<section').find((part) => part.includes('data-zone="object"')) || '', objectCards };
}

test('replaceObjectObjectsRowHtml renders Create Object first, then every existing Object, inside the shared carousel wrapper', () => {
  const { context } = makeContext();
  const html = vm.runInContext('replaceObjectObjectsRowHtml()', context);
  assert.match(html, /class="preset-carousel"/);
  assert.match(html, /class="replace-object-objects-grid preset-carousel-track"/);
  const createIndex = html.indexOf('createPhotoToolReference');
  const lampIndex = html.indexOf("'obj_lamp'");
  const chairIndex = html.indexOf("'obj_chair'");
  assert.ok(createIndex >= 0 && createIndex < lampIndex, 'Create Object button must come first');
  assert.ok(lampIndex < chairIndex, 'existing Objects must follow in order');
  assert.match(html, /SYLVEX\.selectReplaceObjectObject\(event,'obj_lamp'\)/);
});

test('selecting an existing Object fills the replacement object area and never triggers a full modal rerender', () => {
  const { context, sandbox, calls, objectZone } = makeContext();
  vm.runInContext("selectReplaceObjectObject(null, 'obj_lamp')", context);
  assert.equal(sandbox.replaceObjectState.selectedObjectId, 'obj_lamp');
  assert.equal(sandbox.photoToolState.replace_object.files[1].url, 'https://cdn.sylvex.ai/lamp.png');
  assert.match(objectZone(), /lamp\.png/);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(calls.updatePhotoToolGenerateButtonState, 1);
});

test('selecting the same Object again deselects it and empties the object area', () => {
  const { context, sandbox, objectZone } = makeContext();
  vm.runInContext("selectReplaceObjectObject(null, 'obj_lamp')", context);
  vm.runInContext("selectReplaceObjectObject(null, 'obj_lamp')", context);
  assert.equal(sandbox.replaceObjectState.selectedObjectId, null);
  assert.equal(sandbox.photoToolState.replace_object.files[1], null);
  assert.doesNotMatch(objectZone(), /lamp\.png/);
});

test('switching the selection to a different Object puts the new one in the object area', () => {
  const { context, sandbox, objectZone } = makeContext();
  vm.runInContext("selectReplaceObjectObject(null, 'obj_lamp')", context);
  vm.runInContext("selectReplaceObjectObject(null, 'obj_chair')", context);
  assert.equal(sandbox.replaceObjectState.selectedObjectId, 'obj_chair');
  assert.equal(sandbox.photoToolState.replace_object.files[1].url, 'https://cdn.sylvex.ai/chair.png');
  assert.match(objectZone(), /chair\.png/);
});

test('selection is a no-op while the tool is generating (never changes mid-generation)', () => {
  const { context, sandbox } = makeContext();
  sandbox.photoToolState.replace_object.generating = true;
  vm.runInContext("selectReplaceObjectObject(null, 'obj_lamp')", context);
  assert.equal(sandbox.replaceObjectState.selectedObjectId, null);
  assert.equal(sandbox.photoToolState.replace_object.files[1], undefined);
});
