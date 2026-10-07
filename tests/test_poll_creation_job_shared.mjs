// Run with: node --test tests/test_poll_creation_job_shared.mjs
//
// Regression tests for remediation item #21B (DUP-2): the polling/retry/
// completed/failed loop pollCharacterCreationJob() and
// pollObjectCreationJob() each ran, byte for byte identical except their
// own fallback error text, was extracted into one shared
// pollCreationJob(jobId, options, fallbackErrorText) helper in
// webapp/js/cabinet.js. Both wrappers now just call it with their own
// text - this file proves the shared helper itself, and both thin
// wrappers through it, still produce the exact same outcomes as before
// the extraction: transient retry (network error and non-ok response),
// completed (with job_id filled in), failed/cancelled (terminalStatus +
// each caller's own fallback text), and onProgress firing on every
// still-processing tick and never on a terminal one.
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

function makeContext(responder) {
  const calls = {urls: [], waits: []};
  const sandbox = {
    wait: (ms) => { calls.waits.push(ms); return Promise.resolve(); },
    translateGenerationError: (err, fallback) => `translated(${fallback}): ${JSON.stringify(err)}`,
    fetch: async (url) => {
      calls.urls.push(url);
      return responder(calls.urls.length);
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('pollCreationJob'), context);
  vm.runInContext(extractFunction('pollCharacterCreationJob'), context);
  vm.runInContext(extractFunction('pollObjectCreationJob'), context);
  return {context, calls};
}

// ---------------------------------------------------------------------------
// Both wrappers call the correct endpoint and hand off to the shared loop
// ---------------------------------------------------------------------------

test('pollCharacterCreationJob delegates to the shared loop and hits the real job endpoint', async () => {
  const {context, calls} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', result: {character_id: 'custom_character_abc'}})}));
  const result = await vm.runInContext(`pollCharacterCreationJob('job-1', {})`, context);
  assert.equal(result.character_id, 'custom_character_abc');
  assert.equal(result.job_id, 'job-1');
  assert.equal(calls.urls[0], '/api/public/prostudio/job/job-1');
});

test('pollObjectCreationJob delegates to the shared loop and hits the real job endpoint', async () => {
  const {context, calls} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', result: {object_id: 'custom_object_abc'}})}));
  const result = await vm.runInContext(`pollObjectCreationJob('job-2', {})`, context);
  assert.equal(result.object_id, 'custom_object_abc');
  assert.equal(result.job_id, 'job-2');
  assert.equal(calls.urls[0], '/api/public/prostudio/job/job-2');
});

// ---------------------------------------------------------------------------
// Completed
// ---------------------------------------------------------------------------

test('pollCreationJob: completed result gets job_id filled in from the job payload when missing', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', job_id: 'job-3', result: {ok: true, resource: {id: 'x'}}})}));
  const result = await vm.runInContext(`pollCreationJob('job-3', {}, 'fallback text')`, context);
  assert.equal(result.job_id, 'job-3');
  assert.equal(result.resource.id, 'x');
});

test('pollCreationJob: an existing result.job_id is never overwritten', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', job_id: 'job-outer', result: {job_id: 'job-inner'}})}));
  const result = await vm.runInContext(`pollCreationJob('job-outer', {}, 'fallback text')`, context);
  assert.equal(result.job_id, 'job-inner');
});

// ---------------------------------------------------------------------------
// Failed / cancelled - each caller's own fallback text is used
// ---------------------------------------------------------------------------

test('pollCharacterCreationJob: a failed job throws with terminalStatus and the Character fallback text', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'failed', error: {error: 'boom'}})}));
  await assert.rejects(
    vm.runInContext(`pollCharacterCreationJob('job-4', {})`, context),
    (err) => {
      assert.equal(err.terminalStatus, 'failed');
      assert.match(err.message, /Не удалось создать персонажа/);
      return true;
    },
  );
});

test('pollObjectCreationJob: a failed job throws with terminalStatus and the Object fallback text', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'failed', error: {error: 'boom'}})}));
  await assert.rejects(
    vm.runInContext(`pollObjectCreationJob('job-5', {})`, context),
    (err) => {
      assert.equal(err.terminalStatus, 'failed');
      assert.match(err.message, /Не удалось создать объект/);
      return true;
    },
  );
});

test('pollCreationJob: a cancelled job also throws with terminalStatus "cancelled"', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'cancelled'})}));
  await assert.rejects(
    vm.runInContext(`pollCreationJob('job-6', {}, 'custom fallback')`, context),
    (err) => { assert.equal(err.terminalStatus, 'cancelled'); assert.match(err.message, /custom fallback/); return true; },
  );
});

// ---------------------------------------------------------------------------
// Transient retry: network errors and non-ok/non-ok-body responses
// ---------------------------------------------------------------------------

test('pollCreationJob: a transient network error retries and then succeeds once the fetch recovers', async () => {
  let attempt = 0;
  const {context, calls} = makeContext(() => {
    attempt += 1;
    if (attempt <= 2) throw new Error('network down');
    return {ok: true, json: async () => ({ok: true, status: 'completed', result: {ok: true}})};
  });
  const result = await vm.runInContext(`pollCreationJob('job-7', {}, 'fallback')`, context);
  assert.equal(result.ok, true);
  assert.equal(attempt, 3, 'must have retried exactly twice before succeeding on the third attempt');
  assert.equal(calls.waits.length, 2, 'two backoff waits for the two transient failures');
});

test('pollCreationJob: a transient non-ok HTTP response retries and then succeeds', async () => {
  let attempt = 0;
  const {context} = makeContext(() => {
    attempt += 1;
    if (attempt <= 2) return {ok: false, json: async () => ({ok: false, error: 'temporary'})};
    return {ok: true, json: async () => ({ok: true, status: 'completed', result: {ok: true}})};
  });
  const result = await vm.runInContext(`pollCreationJob('job-8', {}, 'fallback')`, context);
  assert.equal(result.ok, true);
  assert.equal(attempt, 3);
});

test('pollCreationJob: a transient job.ok:false body (HTTP 200 but ok:false) also retries', async () => {
  let attempt = 0;
  const {context} = makeContext(() => {
    attempt += 1;
    if (attempt <= 2) return {ok: true, json: async () => ({ok: false, error: 'temporary'})};
    return {ok: true, json: async () => ({ok: true, status: 'completed', result: {ok: true}})};
  });
  const result = await vm.runInContext(`pollCreationJob('job-9', {}, 'fallback')`, context);
  assert.equal(result.ok, true);
  assert.equal(attempt, 3);
});

test('pollCreationJob: a run of network errors that never recovers eventually throws the raw error after 80 retries', async () => {
  const {context} = makeContext(() => { throw new Error('permanently down'); });
  await assert.rejects(
    vm.runInContext(`pollCreationJob('job-10', {}, 'fallback')`, context),
    (err) => { assert.equal(err.message, 'permanently down'); return true; },
  );
});

test('pollCreationJob: a run of non-ok responses that never recovers throws the translated fallback text after 80 retries', async () => {
  const {context} = makeContext(() => ({ok: false, json: async () => ({ok: false, error: 'still down'})}));
  await assert.rejects(
    vm.runInContext(`pollCreationJob('job-11', {}, 'my fallback')`, context),
    (err) => { assert.match(err.message, /my fallback/); return true; },
  );
});

// ---------------------------------------------------------------------------
// onProgress: fires on every still-processing tick, never on a terminal one
// ---------------------------------------------------------------------------

test('pollCreationJob: onProgress fires on every still-processing tick with the raw job payload', async () => {
  const ticks = [];
  const statuses = [
    {ok: true, status: 'processing', result: {stage: 'reference'}},
    {ok: true, status: 'processing', result: {stage: 'saving'}},
    {ok: true, status: 'completed', result: {ok: true}},
  ];
  let index = 0;
  const {context} = makeContext(() => ({ok: true, json: async () => statuses[Math.min(index++, statuses.length - 1)]}));
  vm.runInContext('globalThis.__onProgress = (job) => { globalThis.__ticks = (globalThis.__ticks || []).concat([job]); }', context);
  const result = await vm.runInContext(`pollCreationJob('job-12', {onProgress: __onProgress}, 'fallback')`, context);
  const recorded = vm.runInContext('globalThis.__ticks', context);
  assert.equal(recorded.length, 2);
  assert.equal(recorded[0].result.stage, 'reference');
  assert.equal(recorded[1].result.stage, 'saving');
  assert.equal(result.ok, true);
});

test('pollCreationJob: onProgress never fires once the job reaches a terminal status', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', result: {ok: true}})}));
  vm.runInContext('globalThis.__onProgress = () => { globalThis.__fired = (globalThis.__fired || 0) + 1; }', context);
  await vm.runInContext(`pollCreationJob('job-13', {onProgress: __onProgress}, 'fallback')`, context);
  const fired = vm.runInContext('globalThis.__fired', context);
  assert.equal(fired, undefined, 'onProgress must never fire for a job that completes on the very first tick');
});

test('pollCreationJob: works correctly with no options object at all (onProgress omitted)', async () => {
  const {context} = makeContext(() => ({ok: true, json: async () => ({ok: true, status: 'completed', result: {ok: true}})}));
  const result = await vm.runInContext(`pollCreationJob('job-14', undefined, 'fallback')`, context);
  assert.equal(result.ok, true);
});
