// Run with: node --test tests/test_photo_catalog_nav_stack.mjs
//
// Regression tests for "Pro Studio Mini App - Navigation + Modal UI
// Cleanup": closing a child modal/detail/tool must return exactly one UI
// level back to the parent that opened it, never jumping 2-3 levels back
// to Pro Studio/Home. Also covers hiding the long title in the References
// detail modal only (not Styles/Objects/Popular References).
//
// Covers:
//   - selectPhotoCatalogItem(): no longer closes the Photo Catalog modal
//     when opening an item's detail view - the catalog stays mounted
//     underneath, so closing the detail view later reveals it again.
//   - selectPhotoCatalogItem(): hides quickImageDetailTitle only for
//     kind === 'references', keeps it for styles/objects/popular_references.
//   - openPhotoCatalogTool(): no longer closes the Photo Catalog modal when
//     opening a tool from the catalog's Tools tab.
//   - openPhotoToolModal()/closePhotoToolModal(): a tool opened while the
//     Tools List was already showing closes back to that list one level at
//     a time, instead of leaving the whole modal; a tool opened directly
//     (deep link) still closes the whole modal as before.
//   - openPhotoToolModal()/openPhotoCatalog(): switch the underlying view
//     into Pro Studio ('tools') when opened from Home, so closing the modal
//     reveals the Image section instead of jumping back to Home; do NOT
//     re-switch (and disturb Grid Mode/layout) when already inside Pro
//     Studio.
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
  const el = Object.assign({
    textContent: '', innerHTML: '', value: '', hidden: false, src: '', disabled: false,
    style: {},
    classList: {
      set: new Set(),
      add(c) { this.set.add(c); },
      remove(c) { this.set.delete(c); },
      contains(c) { return this.set.has(c); },
      toggle(c, v) { const on = v === undefined ? !this.set.has(c) : !!v; if (on) this.set.add(c); else this.set.delete(c); },
    },
    querySelector() { return fakeElement(); },
  }, initial || {});
  return el;
}

function makeContext({ toolsViewActive } = {}) {
  const dom = {
    photoCatalogModal: fakeElement({ id: 'photoCatalogModal' }),
    photoCatalogGrid: fakeElement({ id: 'photoCatalogGrid' }),
    quickImageDetailModal: fakeElement({ id: 'quickImageDetailModal' }),
    quickImageDetailTitle: fakeElement({ id: 'quickImageDetailTitle' }),
    quickImageDetailKind: fakeElement({ id: 'quickImageDetailKind' }),
    quickImageDetailImage: fakeElement({ id: 'quickImageDetailImage' }),
    quickImageDetailDescription: fakeElement({ id: 'quickImageDetailDescription' }),
    quickImageDetailPrompt: fakeElement({ id: 'quickImageDetailPrompt' }),
    quickImageDetailUpload: fakeElement({ id: 'quickImageDetailUpload' }),
    quickImageDetailGenerate: fakeElement({ id: 'quickImageDetailGenerate' }),
    photoToolModal: fakeElement({ id: 'photoToolModal' }),
  };
  const calls = { switchView: [], updateComposerMode: [], renderPhotoToolModal: 0, renderPhotoCatalog: 0, renderQuickImageDetailFields: 0 };
  const sandbox = {
    quickImageCatalogCache: {
      references: [{ id: 'ref1', kind: 'references', title: 'Sunset boat', url: 'https://cdn.sylvex.ai/ref1.png' }],
      popular_references: [{ id: 'pop1', kind: 'popular_references', title: 'Studio light', url: 'https://cdn.sylvex.ai/pop1.png' }],
      styles: [{ id: 'sty1', kind: 'styles', title: 'Lime Editorial', url: 'https://cdn.sylvex.ai/sty1.png' }],
      objects: [{ id: 'obj1', kind: 'objects', title: 'Leather Bag', url: 'https://cdn.sylvex.ai/obj1.png' }],
    },
    quickImageCatalogSection: 'references',
    quickImageDetailState: null,
    studioMode: 'video',
    activePhotoTool: '',
    photoToolReturnMode: null,
    photoToolCameFromList: false,
    PHOTO_TOOL_CONFIG: { tattoo: {}, logo: {}, hair_beard: {} },
    photoToolState: { tattoo: { files: [] }, logo: { files: [] }, hair_beard: { files: [] }, makeup: { files: [] }, face_retouch: { files: [] }, replace_object: { files: [] }, watermark_removal: { files: [] } },
    hairBeardState: { category: 'men', selectedPresetId: null, colors: {}, generatingReference: false },
    tattooState: { selectedReferenceId: null, customReferences: [], prompt: '', generatingReference: false },
    logoState: { selectedReferenceId: null, prompt: '', result: null, generating: false },
    replaceObjectState: { comparison: null },
    closeReplaceObjectMaskEditor: () => {},
    activeGenerationLocked: () => false,
    openEditWorkspace: () => { throw new Error('openEditWorkspace should not be called in these tests'); },
    switchView: (name) => calls.switchView.push(name),
    updateComposerMode: (mode) => calls.updateComposerMode.push(mode),
    loadPhotoCatalog: async () => sandbox.quickImageCatalogCache,
    loadPhotoToolDemos: () => Promise.resolve(),
    renderPhotoCatalog: () => { calls.renderPhotoCatalog += 1; },
    renderPhotoToolModal: () => { calls.renderPhotoToolModal += 1; },
    renderQuickImageDetailFields: () => { calls.renderQuickImageDetailFields += 1; },
    window: { setTimeout, clearTimeout },
    document: {
      getElementById: (id) => dom[id] || null,
      querySelector: (sel) => (sel === '.view[data-view="tools"].active' ? (toolsViewActive ? {} : null) : null),
      body: { appendChild: () => {} },
    },
  };
  const context = vm.createContext(sandbox);
  for (const name of ['ensurePhotoCatalogModal', 'ensureQuickImageDetailModal', 'ensurePhotoToolModal', 'openPhotoCatalog', 'closePhotoCatalog', 'selectPhotoCatalogItem', 'closeQuickImageDetail', 'openPhotoCatalogTool', 'openPhotoToolModal', 'closePhotoToolModal']) {
    vm.runInContext(extractFunction(name), context);
  }
  return { context, sandbox, dom, calls };
}

test('selectPhotoCatalogItem: catalog modal is left open underneath the detail view', () => {
  const { context, dom } = makeContext({ toolsViewActive: true });
  dom.photoCatalogModal.classList.add('show');
  vm.runInContext("selectPhotoCatalogItem(null, 'ref1')", context);
  assert.equal(dom.photoCatalogModal.classList.contains('show'), true);
  assert.equal(dom.quickImageDetailModal.classList.contains('show'), true);
});

test('selectPhotoCatalogItem: closing the detail view reveals the still-open catalog, not Home', () => {
  const { context, dom } = makeContext({ toolsViewActive: true });
  dom.photoCatalogModal.classList.add('show');
  vm.runInContext("selectPhotoCatalogItem(null, 'ref1')", context);
  vm.runInContext('closeQuickImageDetail(null)', context);
  assert.equal(dom.quickImageDetailModal.classList.contains('show'), false);
  assert.equal(dom.photoCatalogModal.classList.contains('show'), true);
});

test('selectPhotoCatalogItem: References detail hides the long title', () => {
  const { context, dom } = makeContext({ toolsViewActive: true });
  vm.runInContext("selectPhotoCatalogItem(null, 'ref1')", context);
  assert.equal(dom.quickImageDetailTitle.hidden, true);
});

test('selectPhotoCatalogItem: Popular References/Styles/Objects detail keeps the title', () => {
  for (const [section, id] of [['popular_references', 'pop1'], ['styles', 'sty1'], ['objects', 'obj1']]) {
    const { context, dom, sandbox } = makeContext({ toolsViewActive: true });
    sandbox.quickImageCatalogSection = section;
    vm.runInContext(`selectPhotoCatalogItem(null, '${id}')`, context);
    assert.equal(dom.quickImageDetailTitle.hidden, false, `expected title visible for ${section}`);
  }
});

test('openPhotoCatalogTool: opening a tool from the catalog Tools tab leaves the catalog open underneath', () => {
  const { context, dom } = makeContext({ toolsViewActive: true });
  dom.photoCatalogModal.classList.add('show');
  vm.runInContext("openPhotoCatalogTool(null, 'tattoo')", context);
  assert.equal(dom.photoCatalogModal.classList.contains('show'), true);
  assert.equal(dom.photoToolModal.classList.contains('show'), true);
});

test('openPhotoCatalogTool: closing the tool reveals the catalog again, not Pro Studio/Home', () => {
  const { context, dom } = makeContext({ toolsViewActive: true });
  dom.photoCatalogModal.classList.add('show');
  vm.runInContext("openPhotoCatalogTool(null, 'tattoo')", context);
  vm.runInContext('closePhotoToolModal(null)', context);
  assert.equal(dom.photoToolModal.classList.contains('show'), false);
  assert.equal(dom.photoCatalogModal.classList.contains('show'), true);
});

test('Tools List -> open a tool -> close returns to the Tools List, not out of the modal', () => {
  const { context, dom, sandbox } = makeContext({ toolsViewActive: true });
  // Opening the bare list (kind not in PHOTO_TOOL_CONFIG) shows the list.
  vm.runInContext("openPhotoToolModal(null, 'photo_catalog')", context);
  assert.equal(sandbox.activePhotoTool, '');
  assert.equal(dom.photoToolModal.classList.contains('show'), true);
  // Tapping a tool card while the list is already showing.
  vm.runInContext("openPhotoToolModal(null, 'tattoo')", context);
  assert.equal(sandbox.activePhotoTool, 'tattoo');
  assert.equal(sandbox.photoToolCameFromList, true);
  // First close: one level back to the list, modal stays open.
  vm.runInContext('closePhotoToolModal(null)', context);
  assert.equal(sandbox.activePhotoTool, '');
  assert.equal(dom.photoToolModal.classList.contains('show'), true);
  // Second close: now on the list itself, this fully closes the modal.
  vm.runInContext('closePhotoToolModal(null)', context);
  assert.equal(dom.photoToolModal.classList.contains('show'), false);
});

test('A tool opened directly (deep link, list never shown) closes the whole modal immediately', () => {
  const { context, dom, sandbox } = makeContext({ toolsViewActive: true });
  vm.runInContext("openPhotoToolModal(null, 'tattoo')", context);
  assert.equal(sandbox.photoToolCameFromList, false);
  vm.runInContext('closePhotoToolModal(null)', context);
  assert.equal(dom.photoToolModal.classList.contains('show'), false);
});

test('openPhotoToolModal/openPhotoCatalog switch into Pro Studio when opened from Home', () => {
  const { context, calls } = makeContext({ toolsViewActive: false });
  vm.runInContext("openPhotoToolModal(null, 'photo_catalog')", context);
  assert.deepEqual(calls.switchView, ['tools']);
});

test('openPhotoToolModal/openPhotoCatalog do not re-switch view when already inside Pro Studio', () => {
  const { context, calls } = makeContext({ toolsViewActive: true });
  vm.runInContext("openPhotoToolModal(null, 'photo_catalog')", context);
  assert.deepEqual(calls.switchView, []);
});

test('openPhotoCatalog switches into Pro Studio when opened from Home', async () => {
  const { context, calls } = makeContext({ toolsViewActive: false });
  await vm.runInContext('openPhotoCatalog(null)', context);
  assert.deepEqual(calls.switchView, ['tools']);
});

test('openPhotoCatalog does not re-switch view when already inside Pro Studio', async () => {
  const { context, calls } = makeContext({ toolsViewActive: true });
  await vm.runInContext('openPhotoCatalog(null)', context);
  assert.deepEqual(calls.switchView, []);
});
