// Run with: node --test tests/test_character_picker_card_routing.mjs
//
// Regression test for the Character reference-selection UX fix: in the
// Character picker grid (renderImageStylePanel), a Character card's click
// must route differently per mode -
//   - Image mode: opens the Character's own page (openCharacterDetail) -
//     never selects-and-closes immediately, and never goes through the
//     removed small "..." button/modal.
//   - Video mode: keeps selecting the Character directly (pickVisualReference),
//     since video's Character capability gating (Batch 2-5) is untouched.
// Object cards are out of scope for this change and must keep calling
// pickVisualReference in both modes.
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

function fakeElement() {
  return {
    innerHTML: '',
    classList: {
      list: new Set(),
      add(c) { this.list.add(c); },
      remove(c) { this.list.delete(c); },
      contains(c) { return this.list.has(c); },
    },
  };
}

function makeContext({ videoMode, characters, objects }) {
  const grid = fakeElement();
  const dom = {
    imageStylePanelGrid: grid,
    imageStylePanelTitle: { textContent: '' },
    imageStyleInfoWrap: { hidden: false },
  };
  const sandbox = {
    imageState: { style: 'auto', characterId: null, objectId: null },
    activeImageStylePanelKind: 'character',
    IMAGE_STYLE_SHEET_ITEMS: [],
    isVideoMode: () => !!videoMode,
    imageCharacters: () => characters || [],
    imageObjects: () => objects || [],
    normalizeVisualItem: (item) => item,
    visualPreviewUrl: (item) => (item && item.previewUrl) || '',
    isCustomVisualItem: () => false,
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    document: { getElementById: (id) => dom[id] || null },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCardPendingStatus'), context);
  vm.runInContext(extractFunction('characterCreationStageLabel'), context);
  vm.runInContext(extractFunction('characterCreationPendingCardHtml'), context);
  vm.runInContext(extractFunction('renderImageStylePanel'), context);
  return { context, grid };
}

test('Image mode: clicking a Character card opens its own page, not an immediate select', () => {
  const { context, grid } = makeContext({
    videoMode: false,
    characters: [{ id: 'char_1', name: 'Islam', previewUrl: 'https://cdn.sylvex.ai/a.png' }],
  });
  vm.runInContext('renderImageStylePanel()', context);
  assert.match(grid.innerHTML, /SYLVEX\.openCharacterDetail\(event, 'char_1'\)/);
  assert.doesNotMatch(grid.innerHTML, /SYLVEX\.pickVisualReference\(event, 'character', 'char_1'\)/);
});

test('Video mode: clicking a Character card still selects it directly (unchanged Batch 2-5 behavior)', () => {
  const { context, grid } = makeContext({
    videoMode: true,
    characters: [{ id: 'char_1', name: 'Islam', previewUrl: 'https://cdn.sylvex.ai/a.png' }],
  });
  vm.runInContext('renderImageStylePanel()', context);
  assert.match(grid.innerHTML, /SYLVEX\.pickVisualReference\(event, 'character', 'char_1'\)/);
  assert.doesNotMatch(grid.innerHTML, /SYLVEX\.openCharacterDetail/);
});

test('Object cards are unaffected: still select directly in both modes', () => {
  for (const videoMode of [false, true]) {
    const { context, grid } = makeContext({
      videoMode,
      objects: [{ id: 'obj_1', name: 'Car', previewUrl: 'https://cdn.sylvex.ai/car.png' }],
    });
    vm.runInContext('activeImageStylePanelKind = "object"', context);
    vm.runInContext('renderImageStylePanel()', context);
    assert.match(grid.innerHTML, /SYLVEX\.pickVisualReference\(event, 'object', 'obj_1'\)/);
  }
});
