// Run with: node --test tests/test_character_reference_generation_payload.mjs
//
// Regression test for a reported bug: a user selected exactly ONE
// reference in the Character page (characterReferenceIds), but the
// generation actually used three. Root cause: imageVisualReferenceOptions()
// (consumed by imageOptionsPayload() -> buildGenerationRequest()) rebuilt
// characterReferences from the raw catalog item via visualGenerationReferences()
// - the pre-Character-System-V2 path - which ignored the user's manual
// selection entirely and sent up to 4 images from the item's own
// avatarUrl/referenceImages fields instead of imageState.characterReferences
// (the field applyCharacterReferenceSelection/toggleCharacterReferenceId
// actually keep in sync with the user's choice).
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

function makeContext(imageState, { characters = [], objects = [] } = {}) {
  const sandbox = { imageState };
  const context = vm.createContext(sandbox);
  // imageCharacters()/imageObjects() normally read PRESET_CHARACTERS/
  // PRESET_OBJECTS and localStorage via loadCustomVisualItems() - stubbed
  // directly here to the fixed catalog each test wants, since this test is
  // about imageVisualReferenceOptions()'s own selection logic, not catalog
  // loading (covered elsewhere).
  context.imageCharacters = () => characters;
  context.imageObjects = () => objects;
  vm.runInContext(extractFunction('selectedImageCharacter'), context);
  vm.runInContext(extractFunction('selectedImageObject'), context);
  vm.runInContext(extractFunction('isCustomVisualItem'), context);
  vm.runInContext(extractFunction('visualGenerationReferences'), context);
  vm.runInContext(extractFunction('imageVisualReferenceOptions'), context);
  return context;
}

test('imageVisualReferenceOptions: sends exactly the manually-selected reference, not the full catalog set', () => {
  // The Character's own catalog item carries 4 photos (1 face + 3 full-body)
  // - exactly the shape from the bug report - but the user selected only
  // the face photo in the Character page.
  const library = [
    { id: 'ref_face', url: 'https://cdn.sylvex.ai/face.png', role: 'Primary Face' },
    { id: 'ref_body1', url: 'https://cdn.sylvex.ai/body1.png', role: 'Additional' },
    { id: 'ref_body2', url: 'https://cdn.sylvex.ai/body2.png', role: 'Additional' },
    { id: 'ref_body3', url: 'https://cdn.sylvex.ai/body3.png', role: 'Additional' },
  ];
  const imageState = {
    characterId: 'custom_character_abc',
    characterReferences: ['https://cdn.sylvex.ai/face.png'],
    characterReferenceLibrary: library,
    characterReferenceIds: ['ref_face'],
    objectId: null,
    objectReferences: [],
  };
  const characters = [{
    id: 'custom_character_abc',
    name: 'Islam',
    type: 'custom',
    avatarUrl: 'https://cdn.sylvex.ai/body1.png',
    referenceImages: ['https://cdn.sylvex.ai/body2.png', 'https://cdn.sylvex.ai/body3.png', 'https://cdn.sylvex.ai/face.png'],
  }];
  const context = makeContext(imageState, { characters });

  const options = vm.runInContext('imageVisualReferenceOptions()', context);

  assert.deepEqual(options.characterReferences, ['https://cdn.sylvex.ai/face.png']);
  assert.equal(options.characterReferences.length, 1);
});

test('imageVisualReferenceOptions: no Character selected sends no character references', () => {
  const imageState = { characterId: null, characterReferences: [], objectId: null, objectReferences: [] };
  const context = makeContext(imageState);
  const options = vm.runInContext('imageVisualReferenceOptions()', context);
  assert.equal(options.characterReferences.length, 0);
});
