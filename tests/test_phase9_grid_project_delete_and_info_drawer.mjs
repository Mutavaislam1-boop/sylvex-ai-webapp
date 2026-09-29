// Run with: node --test tests/test_phase9_grid_project_delete_and_info_drawer.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 9 fixes:
// - Grid Mode's project history (list/create/open) had no way to ever
//   remove a saved project - deleteStudioGridProject is new (M-062).
// - openGenerationInfoDrawer called restoreImageStateFromGenerationMetadata
//   (regenMsg's Regenerate-only helper, which even overwrites the live
//   chat input textarea) merely from opening a view-only drawer, silently
//   mutating the live composer's model/style/character/object/seed just
//   from tapping to view an old generation's details (M-034). Verified by
//   confirming the stray call site no longer exists in the source.
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

function extractConstObject(name) {
  const re = new RegExp(`const ${name} *= *\\{`);
  const m = re.exec(cabinet);
  assert.ok(m, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', m.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(m.index, i + 1) + ';';
}

function makeLocalStorage() {
  const store = new Map();
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => { store.set(key, String(value)); },
    removeItem: (key) => { store.delete(key); },
    _store: store,
  };
}

function buildContext(initialActiveState) {
  const localStorage = makeLocalStorage();
  const sandbox = {
    localStorage,
    window: {confirm: () => true},
    document: {getElementById: () => null},
    toast: () => {},
    gridEscape: (v) => v,
    STUDIO_GRID_PROJECTS_KEY: 'sylvex-prostudio-grid-projects-v1',
    STUDIO_GRID_PROJECT_PREFIX: 'sylvex-prostudio-grid-project-v1:',
    studioGridState: initialActiveState,
    studioGridSelectedIds: new Set(['x']),
    clearStudioGridConnectionMode: () => {},
    renderStudioGrid: () => {},
    resetStudioGridView: () => {},
    saveStudioGridState: () => { localStorage.setItem('sylvex-prostudio-grid-v2', JSON.stringify(sandbox.studioGridState)); },
    loadStudioGridState: () => sandbox.studioGridState,
    studioGridHasActiveRun: () => false,
    // gridDefaultModel/gridDefaultSettings dependencies - unused for a plain
    // 'task' node (emptyStudioGridState's only node type) but referenced by
    // normalizeStudioGridState's generic node-normalization pass.
    imageState: {}, videoState: {}, musicState: {}, voiceState: {}, textState: {},
    IMAGE_MODEL_LIST: [], MUSIC_MODEL_LIST: [], VOICE_MODEL_LIST: [],
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractConstObject('VIDEO_MODEL_CONFIG'), context);
  vm.runInContext(extractConstObject('GRID_TYPES'), context);
  vm.runInContext(extractFunction('gridDefaultModel'), context);
  vm.runInContext(extractFunction('gridDefaultSettings'), context);
  vm.runInContext(extractFunction('normalizeStudioGridState'), context);
  vm.runInContext(extractFunction('emptyStudioGridState'), context);
  vm.runInContext(extractFunction('loadStudioGridProjects'), context);
  vm.runInContext(extractFunction('saveStudioGridProjects'), context);
  vm.runInContext(extractFunction('touchStudioGridProject'), context);
  vm.runInContext(extractFunction('renderStudioGridProjects'), context);
  vm.runInContext(extractFunction('deleteStudioGridProject'), context);
  return context;
}

test('deleteStudioGridProject: removes a non-active project from the list and its stored state', () => {
  const active = {projectId: 'grid_project_active', title: 'Active'};
  const context = buildContext(active);
  vm.runInContext(`
    localStorage.setItem(STUDIO_GRID_PROJECTS_KEY, JSON.stringify([
      {id: 'grid_project_active', title: 'Active', updated_at: new Date().toISOString()},
      {id: 'grid_project_old', title: 'Old', updated_at: new Date().toISOString()},
    ]));
    localStorage.setItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_old', JSON.stringify({projectId: 'grid_project_old', nodes: []}));
  `, context);
  vm.runInContext(`deleteStudioGridProject('grid_project_old')`, context);
  const remaining = vm.runInContext('loadStudioGridProjects()', context);
  assert.deepEqual(Array.from(remaining).map((item) => item.id), ['grid_project_active']);
  const removedState = vm.runInContext(`localStorage.getItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_old')`, context);
  assert.equal(removedState, null);
  // The active project must be untouched - deleting a different project
  // must never reset the live canvas.
  assert.equal(vm.runInContext('studioGridState.projectId', context), 'grid_project_active');
});

test('deleteStudioGridProject: deleting the currently-open project resets the live canvas to a fresh one', () => {
  const active = {projectId: 'grid_project_active', title: 'Active'};
  const context = buildContext(active);
  vm.runInContext(`
    localStorage.setItem(STUDIO_GRID_PROJECTS_KEY, JSON.stringify([
      {id: 'grid_project_active', title: 'Active', updated_at: new Date().toISOString()},
    ]));
    localStorage.setItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_active', JSON.stringify({projectId: 'grid_project_active', nodes: []}));
  `, context);
  vm.runInContext(`deleteStudioGridProject('grid_project_active')`, context);
  const newProjectId = vm.runInContext('studioGridState.projectId', context);
  assert.notEqual(newProjectId, 'grid_project_active');
  const removedState = vm.runInContext(`localStorage.getItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_active')`, context);
  assert.equal(removedState, null);
});

test('deleteStudioGridProject: a live workflow run blocks deletion entirely', () => {
  const active = {projectId: 'grid_project_active', title: 'Active'};
  const context = buildContext(active);
  vm.runInContext(`studioGridHasActiveRun = () => true`, context);
  vm.runInContext(`
    localStorage.setItem(STUDIO_GRID_PROJECTS_KEY, JSON.stringify([
      {id: 'grid_project_other', title: 'Other', updated_at: new Date().toISOString()},
    ]));
    localStorage.setItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_other', JSON.stringify({projectId: 'grid_project_other', nodes: []}));
  `, context);
  vm.runInContext(`deleteStudioGridProject('grid_project_other')`, context);
  const remaining = vm.runInContext('loadStudioGridProjects()', context);
  assert.equal(remaining.length, 1);
  const stillThere = vm.runInContext(`localStorage.getItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_other')`, context);
  assert.notEqual(stillThere, null);
});

test('deleteStudioGridProject: declining the confirmation dialog leaves everything untouched', () => {
  const active = {projectId: 'grid_project_active', title: 'Active'};
  const context = buildContext(active);
  vm.runInContext(`window.confirm = () => false`, context);
  vm.runInContext(`
    localStorage.setItem(STUDIO_GRID_PROJECTS_KEY, JSON.stringify([
      {id: 'grid_project_old', title: 'Old', updated_at: new Date().toISOString()},
    ]));
    localStorage.setItem(STUDIO_GRID_PROJECT_PREFIX + 'grid_project_old', JSON.stringify({projectId: 'grid_project_old', nodes: []}));
  `, context);
  vm.runInContext(`deleteStudioGridProject('grid_project_old')`, context);
  const remaining = vm.runInContext('loadStudioGridProjects()', context);
  assert.equal(remaining.length, 1);
});

test('openGenerationInfoDrawer no longer calls the Regenerate-only state-restore helper', () => {
  const pattern = /function openGenerationInfoDrawer\(/;
  const match = pattern.exec(cabinet);
  assert.ok(match, 'openGenerationInfoDrawer not found');
  const openIndex = cabinet.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  const body = cabinet.slice(match.index, i + 1);
  // Substring alone would also match this file's own explanatory comment
  // (which names the removed helper) - check for an actual call instead.
  assert.ok(
    !body.includes('restoreImageStateFromGenerationMetadata(meta)'),
    'openGenerationInfoDrawer must not mutate live composer state just from being opened'
  );
});
