const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('webapp/js/cabinet.js', 'utf8');
const helperMatch = source.match(/function canGenerateImageFromControls\(state\) \{[\s\S]*?\n  \}/);
assert.ok(helperMatch, 'image Generate eligibility helper must exist');
const helperContext = {};
vm.createContext(helperContext);
vm.runInContext(helperMatch[0] + '\nthis.canGenerateImageFromControls = canGenerateImageFromControls;', helperContext);
const canGenerate = helperContext.canGenerateImageFromControls;

const cases = [
  ['prompt', { hasPrompt: true }, true],
  ['image', { hasUserImageReference: true }, true],
  ['style', { hasStyle: true }, false],
  ['character', { hasCharacter: true }, false],
  ['object', { hasObject: true }, false],
  ['style + character', { hasStyle: true, hasCharacter: true }, true],
  ['style + object', { hasStyle: true, hasObject: true }, true],
  ['character + object', { hasCharacter: true, hasObject: true }, true],
  ['style + character + object', { hasStyle: true, hasCharacter: true, hasObject: true }, true],
  ['style + prompt', { hasStyle: true, hasPrompt: true }, true],
  ['character + prompt', { hasCharacter: true, hasPrompt: true }, true],
  ['object + prompt', { hasObject: true, hasPrompt: true }, true],
  ['style + image', { hasStyle: true, hasUserImageReference: true }, true],
  ['character + image', { hasCharacter: true, hasUserImageReference: true }, true],
  ['object + image', { hasObject: true, hasUserImageReference: true }, true],
];
for (const [name, state, expected] of cases) {
  assert.equal(canGenerate(state), expected, name);
}

const waitStart = source.indexOf('async function waitGeneration(jobId, options)');
const waitEnd = source.indexOf('\n  // =====================================================\n  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openShopForGeneration', waitStart);
assert.ok(waitStart >= 0 && waitEnd > waitStart, 'waitGeneration must exist');
const waitSource = source.slice(waitStart, waitEnd);
const terminalResults = ['failed', 'timeout'];

(async () => {
  for (const status of terminalResults) {
    let pollCount = 0;
    let locked = true;
    const context = {
      Date,
      setTimeout,
      clearTimeout,
      DOMException,
      isActiveGenerationStatus: (value) => ['queued', 'processing', 'running'].includes(String(value).toLowerCase()),
      transitionActiveGeneration: () => true,
      patchActiveGenerationDom: () => {},
      translateGenerationError: (_value, fallback) => fallback,
      fetch: async () => {
        pollCount += 1;
        return { ok: true, json: async () => ({ ok: true, status, error: { message: status } }) };
      },
    };
    vm.createContext(context);
    vm.runInContext(waitSource, context);
    try {
      await context.waitGeneration('job-test');
      assert.fail(status + ' should terminate polling');
    } catch (error) {
      assert.equal(error.terminalStatus, status);
      if (error.terminalStatus) locked = false; // sendChat's terminal-error unlock path
    }
    assert.equal(pollCount, 1, status + ' must stop after the terminal response');
    assert.equal(locked, false, status + ' must clear the generation-loading lock');
  }
  assert.match(source, /if \(err && err\.terminalStatus\) unlockAfterRender = true;/);
  assert.match(source, /if \(unlockAfterRender\) clearActiveProStudioJob\(activeGeneration\.jobId\);/);
  console.log(`Pro Studio local checks passed: ${cases.length} Generate states, ${terminalResults.length} terminal statuses`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
