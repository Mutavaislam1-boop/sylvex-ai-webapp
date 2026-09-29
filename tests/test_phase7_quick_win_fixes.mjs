// Run with: node --test tests/test_phase7_quick_win_fixes.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 7 quick-win fixes:
// - canGenerateImageFromControls() required 2 of {style, character, object}
//   to enable Generate, so selecting only a Character (or only an Object)
//   left the button disabled even though the backend's own readiness check
//   (public_prostudio_generate's reference_images OR-chain) accepts either
//   alone.
// - validateGridNodeInputs() checked a text node's raw node.prompt instead
//   of the chain-aware inputs.effective_prompt every other node type uses,
//   so a text node chained after another text/task node with no local
//   override could never be run manually even though the real payload
//   builder would have used the parent's text correctly.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extract(name) {
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

test('canGenerateImageFromControls: a Character alone is enough', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('canGenerateImageFromControls'), context);
  const enabled = vm.runInContext(
    'canGenerateImageFromControls({hasPrompt:false, hasUserImageReference:false, hasStyle:false, hasCharacter:true, hasObject:false})',
    context
  );
  assert.equal(enabled, true);
});

test('canGenerateImageFromControls: an Object alone is enough', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('canGenerateImageFromControls'), context);
  const enabled = vm.runInContext(
    'canGenerateImageFromControls({hasPrompt:false, hasUserImageReference:false, hasStyle:false, hasCharacter:false, hasObject:true})',
    context
  );
  assert.equal(enabled, true);
});

test('canGenerateImageFromControls: still disabled with nothing selected', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('canGenerateImageFromControls'), context);
  const enabled = vm.runInContext(
    'canGenerateImageFromControls({hasPrompt:false, hasUserImageReference:false, hasStyle:false, hasCharacter:false, hasObject:false})',
    context
  );
  assert.equal(enabled, false);
});

test('canGenerateImageFromControls: Style alone still requires the pre-existing 2-of-3 rule', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('canGenerateImageFromControls'), context);
  const enabled = vm.runInContext(
    'canGenerateImageFromControls({hasPrompt:false, hasUserImageReference:false, hasStyle:true, hasCharacter:false, hasObject:false})',
    context
  );
  assert.equal(enabled, false);
});

test('validateGridNodeInputs: a text node with no local prompt but a connected parent text is valid', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('validateGridNodeInputs'), context);
  const node = {type: 'text', prompt: '', attachments: []};
  const inputs = {effective_prompt: {value: 'inherited from parent text node'}};
  const result = vm.runInContext('validateGridNodeInputs(node, inputs)', Object.assign(context, {node, inputs}));
  assert.equal(result.ok, true);
});

test('validateGridNodeInputs: a text node with neither local prompt nor connected text is invalid', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('validateGridNodeInputs'), context);
  const node = {type: 'text', prompt: '', attachments: []};
  const inputs = {};
  const result = vm.runInContext('validateGridNodeInputs(node, inputs)', Object.assign(context, {node, inputs}));
  assert.equal(result.ok, false);
  assert.ok(result.missing.includes('Инструкция для текста'));
});
