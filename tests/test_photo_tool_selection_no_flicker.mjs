// Run with: node --test tests/test_photo_tool_selection_no_flicker.mjs
//
// Regression tests for "Pro Studio Mini App - Photo Tools UI Polish":
//   - item 2: selecting a Logo/Hair&Beard/Tattoo reference must not call
//     renderPhotoToolModal() (no full-list rerender -> no flicker, no
//     carousel scroll reset) - only the clicked/previously-selected card's
//     class and the upload areas (#ptoolZones) are touched.
//   - item 3: clicking an already-selected reference deselects it.
//   - a picked reference shows up in the tool's upload area right away:
//     Logo's image area, Tattoo's tattoo area, a small icon in the corner
//     of Hair&Beard's portrait area; deselecting empties it again.
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

function extractConst(name) {
  const pattern = new RegExp(`^const ${name} = `, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `const not found: ${name}`);
  let i = match.index + match[0].length;
  let depth = 0;
  for (; i < cabinet.length; i++) {
    const ch = cabinet[i];
    if (ch === '[' || ch === '(' || ch === '{') depth++;
    else if (ch === ']' || ch === ')' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) { i++; break; }
  }
  return cabinet.slice(match.index, i);
}

function fakeElement(initial) {
  return Object.assign({
    innerHTML: '', textContent: '', value: '', disabled: false,
    classList: {
      set: new Set(),
      add(c) { this.set.add(c); },
      remove(c) { this.set.delete(c); },
      contains(c) { return this.set.has(c); },
      toggle(c, v) { const on = v === undefined ? !this.set.has(c) : !!v; if (on) this.set.add(c); else this.set.delete(c); },
    },
    setAttribute(name, v) { this['attr_' + name] = String(v); },
    getAttribute(name) { return this['attr_' + name]; },
  }, initial || {});
}

function fakeCard(id) {
  return fakeElement({ attr_data_ref_id: undefined, attr_data_preset_id: undefined, __id: id,
    getAttribute(name) { return name === 'data-ref-id' || name === 'data-preset-id' ? this.__id : this['attr_' + name]; } });
}

function makeContext() {
  const calls = { renderPhotoToolModal: 0 };
  const logoCards = { nivora: fakeCard('nivora'), kerno: fakeCard('kerno') };
  const hairCards = { bald: fakeCard('bald'), buzz_cut: fakeCard('buzz_cut') };
  const tattooCards = { tattoo_ref_01: fakeCard('tattoo_ref_01'), tattoo_ref_02: fakeCard('tattoo_ref_02') };
  const dom = {
    ptoolZones: fakeElement({}),
  };
  const querySelectorAllMap = {
    '.logo-reference-card': Object.values(logoCards),
    '.hair-beard-card': Object.values(hairCards),
    '.tattoo-reference-card': Object.values(tattooCards),
  };
  const sandbox = {
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    activePhotoTool: 'logo',
    logoState: { selectedReferenceId: null, prompt: '', generating: false, result: null },
    hairBeardState: { category: 'men', selectedPresetId: null, customPresets: [], referencePrompt: '' },
    tattooState: { selectedReferenceId: null, uploadedReference: '', customReferences: [], prompt: '', generatingReference: false },
    replaceObjectState: {},
    HAIR_BEARD_PRESET_LABELS: {},
    photoToolState: {
      logo: { files: [], generating: false },
      hair_beard: { files: [], generating: false },
      tattoo: { files: [], generating: false },
    },
    PHOTO_TOOL_CONFIG: { logo: { min: 0, max: 1 }, hair_beard: { min: 1, max: 1 }, tattoo: { min: 1, max: 1 } },
    document: {
      getElementById: (id) => dom[id] || null,
      querySelectorAll: (sel) => querySelectorAllMap[sel] || [],
      querySelector: () => null,
    },
    renderPhotoToolModal: () => { calls.renderPhotoToolModal += 1; },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractConst('LOGO_REFERENCES'), context);
  vm.runInContext(extractConst('HAIR_BEARD_PRESETS'), context);
  vm.runInContext(extractConst('TATTOO_REFERENCES'), context);
  for (const name of [
    'logoReferenceById', 'selectLogoReference',
    'hairBeardPresetById', 'selectHairBeardPreset', 'hairBeardZoneBadgeHtml',
    'tattooReferenceById', 'selectTattooReference',
    'photoToolStateFor', 'updatePresetCardSelection',
    'photoToolZones', 'photoToolZoneHtml', 'photoToolZonesInnerHtml', 'refreshPhotoToolZones', 'photoToolMarkBadgeHtml',
    'photoToolReadyState', 'photoToolIsReady', 'photoToolGenerateButtonLabel', 'updatePhotoToolGenerateButtonState',
  ]) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, dom, logoCards, hairCards, tattooCards, calls };
}

const zone = (html, key) => (html.split('<section').find((part) => part.includes('data-zone="' + key + '"')) || '');

test('selecting a Logo reference never calls renderPhotoToolModal (no full rerender)', () => {
  const { context, calls } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
});

test('selecting a Logo reference toggles only that card selected and puts it in the image area', () => {
  const { context, dom, logoCards, sandbox } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(sandbox.logoState.selectedReferenceId, 'nivora');
  assert.equal(logoCards.nivora.classList.contains('selected'), true);
  assert.equal(logoCards.kerno.classList.contains('selected'), false);
  const asset = vm.runInContext("logoReferenceById('nivora').asset", context);
  assert.match(zone(dom.ptoolZones.innerHTML, 'photo'), new RegExp('class="ptool-ref"><img src="' + asset.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '"'));
  assert.doesNotMatch(zone(dom.ptoolZones.innerHTML, 'photo'), /class="ptool-add"/);
});

test('selecting the same Logo reference again deselects it and empties the image area', () => {
  const { context, dom, logoCards, sandbox } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(sandbox.logoState.selectedReferenceId, null);
  assert.equal(logoCards.nivora.classList.contains('selected'), false);
  assert.doesNotMatch(dom.ptoolZones.innerHTML, /class="ptool-ref"/);
  assert.match(dom.ptoolZones.innerHTML, /class="ptool-add"/);
});

test('selecting a Hair&Beard preset never calls renderPhotoToolModal, sits in the portrait corner, is deselectable', () => {
  const { context, dom, hairCards, sandbox, calls } = makeContext();
  sandbox.activePhotoTool = 'hair_beard';
  vm.runInContext("selectHairBeardPreset(null, 'bald')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.hairBeardState.selectedPresetId, 'bald');
  assert.equal(hairCards.bald.classList.contains('selected'), true);
  assert.match(zone(dom.ptoolZones.innerHTML, 'photo'), /class="ptool-zone-badge"/);
  vm.runInContext("selectHairBeardPreset(null, 'bald')", context);
  assert.equal(sandbox.hairBeardState.selectedPresetId, null);
  assert.equal(hairCards.bald.classList.contains('selected'), false);
  assert.doesNotMatch(dom.ptoolZones.innerHTML, /ptool-zone-badge/);
});

test('selecting a Tattoo reference never calls renderPhotoToolModal, fills the tattoo area, is deselectable', () => {
  const { context, dom, tattooCards, sandbox, calls } = makeContext();
  sandbox.activePhotoTool = 'tattoo';
  sandbox.tattooState.uploadedReference = 'https://cdn.example.com/own.png';
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.tattooState.selectedReferenceId, 'tattoo_ref_01');
  assert.equal(sandbox.tattooState.uploadedReference, '', 'a picked tattoo replaces the uploaded design');
  assert.equal(tattooCards.tattoo_ref_01.classList.contains('selected'), true);
  const asset = vm.runInContext("tattooReferenceById('tattoo_ref_01').referenceAsset", context);
  assert.ok(zone(dom.ptoolZones.innerHTML, 'tattoo').includes('<img src="' + asset + '"'));
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  assert.equal(sandbox.tattooState.selectedReferenceId, null);
  assert.equal(tattooCards.tattoo_ref_01.classList.contains('selected'), false);
  assert.doesNotMatch(zone(dom.ptoolZones.innerHTML, 'tattoo'), /class="ptool-ref"/);
});

test('switching Tattoo selection from one reference to another clears the previous card and selects the new one', () => {
  const { context, tattooCards, sandbox } = makeContext();
  sandbox.activePhotoTool = 'tattoo';
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_02')", context);
  assert.equal(sandbox.tattooState.selectedReferenceId, 'tattoo_ref_02');
  assert.equal(tattooCards.tattoo_ref_01.classList.contains('selected'), false);
  assert.equal(tattooCards.tattoo_ref_02.classList.contains('selected'), true);
});

test('selecting a Tattoo reference updates the same Generate button in place', () => {
  const { context, sandbox } = makeContext();
  sandbox.activePhotoTool = 'tattoo';
  const button = fakeElement({ disabled: true });
  sandbox.document.querySelector = (sel) => (sel === '#photoToolModalBody .photo-tool-generate' ? button : null);
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  assert.equal(button.disabled, true, 'no photo yet');
  sandbox.photoToolState.tattoo.files = [{ url: 'https://cdn.example.com/arm.jpg' }];
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_02')", context);
  assert.equal(button.disabled, false, 'photo + picked tattoo is ready');
  assert.equal(button, sandbox.document.querySelector('#photoToolModalBody .photo-tool-generate'));
});
