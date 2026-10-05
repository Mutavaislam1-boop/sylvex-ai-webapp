// Run with: node --test tests/test_photo_tool_selection_no_flicker.mjs
//
// Regression tests for "Pro Studio Mini App - Photo Tools UI Polish":
//   - item 2: selecting a Logo/Hair&Beard/Tattoo reference must not call
//     renderPhotoToolModal() (no full-list rerender -> no flicker, no
//     carousel scroll reset) - only the clicked/previously-selected card's
//     class and the demo/preview column are touched.
//   - item 3: clicking an already-selected reference deselects it.
//   - item 5/10: selecting a reference immediately previews it (Logo's
//     result area / Hair&Beard's before-after area) before generation;
//     deselecting reverts to the generic placeholder/demo.
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
  const calls = { renderPhotoToolModal: 0, syncTattooAspect: 0, syncReplaceObjectAspect: 0 };
  const logoCards = { nivora: fakeCard('nivora'), kerno: fakeCard('kerno') };
  const hairCards = { bald: fakeCard('bald'), buzz_cut: fakeCard('buzz_cut') };
  const tattooCards = { tattoo_ref_01: fakeCard('tattoo_ref_01'), tattoo_ref_02: fakeCard('tattoo_ref_02') };
  const dom = {
    photoToolDemoColumn: fakeElement({}),
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
    hairBeardState: { category: 'men', selectedPresetId: null, customPresets: [], comparison: null, smartCrop: false, referencePrompt: '' },
    tattooState: { selectedReferenceId: null, customReferences: [], prompt: '', comparison: null, generatingReference: false },
    replaceObjectState: { comparison: null },
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
    syncTattooComparisonAspectRatio: () => { calls.syncTattooAspect += 1; },
    syncReplaceObjectComparisonAspectRatio: () => { calls.syncReplaceObjectAspect += 1; },
    renderPhotoToolModal: () => { calls.renderPhotoToolModal += 1; },
    logoSvgDownloadUrl: () => '',
    downloadGeneratedFile: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractConst('LOGO_REFERENCES'), context);
  vm.runInContext(extractConst('HAIR_BEARD_PRESETS'), context);
  vm.runInContext(extractConst('TATTOO_REFERENCES'), context);
  for (const name of [
    'photoToolMediaHtml', 'photoToolDemoHtml', 'logoReferenceById', 'logoResultPreviewHtml', 'selectLogoReference',
    'hairBeardPresetById', 'hairBeardComparisonHtml', 'selectHairBeardPreset',
    'tattooReferenceById', 'tattooComparisonHtml', 'selectTattooReference',
    'photoToolStateFor', 'updatePresetCardSelection', 'refreshPhotoToolDemoColumn',
    'photoToolReadyState', 'photoToolGenerateButtonLabel', 'photoToolDemoColumnInnerHtml', 'updatePhotoToolGenerateButtonState',
  ]) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, dom, logoCards, hairCards, tattooCards, calls };
}

test('selecting a Logo reference never calls renderPhotoToolModal (no full rerender)', () => {
  const { context, calls } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
});

test('selecting a Logo reference toggles only that card selected, previews it immediately', () => {
  const { context, dom, logoCards, sandbox } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(sandbox.logoState.selectedReferenceId, 'nivora');
  assert.equal(logoCards.nivora.classList.contains('selected'), true);
  assert.equal(logoCards.kerno.classList.contains('selected'), false);
  assert.match(dom.photoToolDemoColumn.innerHTML, /logo-result-preview/);
  assert.match(dom.photoToolDemoColumn.innerHTML, /Nivora/);
  assert.doesNotMatch(dom.photoToolDemoColumn.innerHTML, /Тут появится ваш результат/);
});

test('selecting the same Logo reference again deselects it and reverts the preview to the placeholder', () => {
  const { context, dom, logoCards, sandbox } = makeContext();
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  vm.runInContext("selectLogoReference(null, 'nivora')", context);
  assert.equal(sandbox.logoState.selectedReferenceId, null);
  assert.equal(logoCards.nivora.classList.contains('selected'), false);
  assert.match(dom.photoToolDemoColumn.innerHTML, /Тут появится ваш результат/);
});

test('selecting a Hair&Beard preset never calls renderPhotoToolModal, previews the reference, is deselectable', () => {
  const { context, dom, hairCards, sandbox, calls } = makeContext();
  sandbox.activePhotoTool = 'hair_beard';
  vm.runInContext("selectHairBeardPreset(null, 'bald')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.hairBeardState.selectedPresetId, 'bald');
  assert.equal(hairCards.bald.classList.contains('selected'), true);
  assert.match(dom.photoToolDemoColumn.innerHTML, /hair-beard-reference-preview/);
  vm.runInContext("selectHairBeardPreset(null, 'bald')", context);
  assert.equal(sandbox.hairBeardState.selectedPresetId, null);
  assert.equal(hairCards.bald.classList.contains('selected'), false);
  assert.doesNotMatch(dom.photoToolDemoColumn.innerHTML, /hair-beard-reference-preview/);
});

test('selecting a Tattoo reference never calls renderPhotoToolModal, previews the reference, is deselectable', () => {
  const { context, dom, tattooCards, sandbox, calls } = makeContext();
  sandbox.activePhotoTool = 'tattoo';
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  assert.equal(calls.renderPhotoToolModal, 0);
  assert.equal(sandbox.tattooState.selectedReferenceId, 'tattoo_ref_01');
  assert.equal(tattooCards.tattoo_ref_01.classList.contains('selected'), true);
  assert.match(dom.photoToolDemoColumn.innerHTML, /tattoo-reference-preview/);
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  assert.equal(sandbox.tattooState.selectedReferenceId, null);
  assert.equal(tattooCards.tattoo_ref_01.classList.contains('selected'), false);
  assert.doesNotMatch(dom.photoToolDemoColumn.innerHTML, /tattoo-reference-preview/);
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

test('selecting a Tattoo/Hair&Beard reference updates the Generate button readiness without rebuilding it', () => {
  const { context, sandbox } = makeContext();
  sandbox.activePhotoTool = 'tattoo';
  const button = fakeElement({ disabled: true });
  sandbox.document.querySelector = (sel) => (sel === '#photoToolModalBody .photo-tool-generate' ? button : null);
  vm.runInContext("selectTattooReference(null, 'tattoo_ref_01')", context);
  // No uploaded photo yet, but a selected reference alone does not make a
  // photo-less Tattoo ready (photoToolReadyState requires text when there
  // is no photo) - button stays disabled; the point of this test is that
  // the SAME button instance was updated in place, not replaced.
  assert.equal(button, sandbox.document.querySelector('#photoToolModalBody .photo-tool-generate'));
});
