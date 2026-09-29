// Run with: node --test tests/test_phase6_grid_mode_fixes.mjs
//
// Regression tests for the Pro Studio A-Z audit's Phase 6 Grid Mode fixes:
// - the image node's reference-image input port was named 'image_reference'
//   (mismatching gridGenerationPayload's inputs.image read, and connectable
//   by nothing since no output type is ever literally 'image_reference')
//   and is now 'image', matching an image node's own output type.
// - the workflow-completion formula only checked FAILED/WAITING nodes, so a
//   chain where every failed node ended up CANCELLED (via the auto-cancel
//   path when a parent fails) incorrectly reported "Цепочка завершена".
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extract(name, kind = 'function') {
  const pattern = kind === 'function'
    ? new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm')
    : new RegExp(`^([ \\t]*)const ${name} = \\{`, 'm');
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
  return cabinet.slice(match.index, i + 1) + (kind === 'const' ? ';' : '');
}

test('GRID_TYPES: image node declares an "image" input port, not "image_reference"', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('GRID_TYPES', 'const'), context);
  const imageInputs = vm.runInContext('GRID_TYPES.image.inputs', context);
  assert.ok(imageInputs.includes('image'), 'image port missing');
  assert.ok(!imageInputs.includes('image_reference'), 'stale image_reference port still present');
});

test('gridConnectionCompatible now allows an image node output into another image node\'s reference port', () => {
  const context = vm.createContext({});
  vm.runInContext(extract('GRID_TYPES', 'const'), context);
  vm.runInContext(extract('gridConnectionCompatible'), context);
  const fromNode = {id: 'a', type: 'image'};
  const toNode = {id: 'b', type: 'image'};
  const compatible = vm.runInContext(
    'gridConnectionCompatible(fromNode, "image", toNode, "image")',
    Object.assign(context, {fromNode, toNode})
  );
  assert.equal(compatible, true);
});

test('gridGenerationPayload reads a connected image reference via the same key resolveGridNodeInputs writes', () => {
  const context = vm.createContext({console});
  vm.runInContext(extract('GRID_TYPES', 'const'), context);
  context.studioGridState = {
    nodes: [
      {id: 'src', type: 'image', status: 'COMPLETED', output: {type: 'image', items: [{url: 'https://x.test/ref.png'}]}},
      {id: 'dst', type: 'image', status: 'READY', settings: {}, attachments: [], prompt: 'a portrait'},
    ],
    edges: [{from: 'src', fromPort: 'image', to: 'dst', toPort: 'image'}],
  };
  context.loadStudioGridState = () => context.studioGridState;
  vm.runInContext(extract('getGridNodeOutputValue'), context);
  vm.runInContext(extract('resolveGridNodeInputs'), context);
  context.providerHintForModel = () => 'sylvex-router';
  context.gridDefaultModel = () => 'seedream_5_0_lite';
  context.getTelegramId = () => 123;
  context.gridTestModeEnabled = () => false;
  context.uiLang = () => 'en';
  vm.runInContext(extract('gridGenerationPayload'), context);

  const inputs = vm.runInContext("resolveGridNodeInputs('dst')", context);
  assert.equal(inputs.image.value.url, 'https://x.test/ref.png');

  const node = context.studioGridState.nodes[1];
  const payload = vm.runInContext('gridGenerationPayload(node, inputs)', Object.assign(context, {node, inputs}));
  // Cross-realm arrays from vm.runInContext aren't `instanceof Array` in
  // this realm, so re-materialize before a strict deep-equal comparison.
  assert.deepEqual(Array.from(payload.image_options.referenceImageUrls), ['https://x.test/ref.png']);
});

test('workflow completion formula treats a CANCELLED node as unfinished (not silent success)', () => {
  // The formula itself (kept minimal and inline in runStudioGridWorkflow
  // rather than its own named function) is exercised directly here rather
  // than through the full async runStudioGridWorkflow, which has too many
  // unrelated dependencies (chat UI, cost estimation, network) to usefully
  // stub for this one arithmetic check.
  const formula = (nodes, stopRequested) => {
    const unfinished = nodes.some((node) => node.type !== 'task' && ['FAILED', 'WAITING', 'CANCELLED'].includes(node.status));
    return stopRequested ? 'CANCELLED' : (unfinished ? 'FAILED' : 'COMPLETED');
  };
  const nodes = [
    {type: 'image', status: 'COMPLETED'},
    {type: 'video', status: 'CANCELLED'}, // auto-cancelled because its parent failed
  ];
  assert.equal(formula(nodes, false), 'FAILED');

  // Confirm the fix is actually present in the shipped source, not just in
  // this test's own reimplementation of the intended formula.
  const source = extract('runStudioGridWorkflow');
  assert.match(source, /\['FAILED','WAITING','CANCELLED'\]\.includes\(node\.status\)/);
});
