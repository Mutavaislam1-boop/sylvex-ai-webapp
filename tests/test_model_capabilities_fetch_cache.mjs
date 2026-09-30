// Run with: node --test tests/test_model_capabilities_fetch_cache.mjs
//
// Regression tests for Phase 1 Batch 1 of the Pro Studio master remediation
// plan (see /root/.claude/plans/splendid-moseying-starlight.md): the
// frontend fetch/cache/fallback behavior for the new
// /api/public/prostudio/model-capabilities endpoint. Per the approved plan's
// correction 2, localStorage must be a last-known-good accelerator, never
// the sole source of truth - every bootstrap revalidates, a failed fetch
// falls back to the cached snapshot, and with no cache at all
// getModelCapabilities() falls back to the still-present MODEL_FEATURES
// table (additive-only migration keeps it around for exactly this).
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

// Objects returned from vm.runInContext() are instances of that context's
// own Object/Array constructors (a separate realm), so assert.deepEqual
// (deepStrictEqual under node:assert/strict) reports "same structure but
// not reference-equal" against a plain literal in this file's realm even
// when every property matches. A JSON round-trip normalizes to this
// realm's plain objects before comparing.
function toPlain(value) {
  return value === undefined ? value : JSON.parse(JSON.stringify(value));
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

function buildContext({fetchImpl} = {}) {
  const localStorage = makeLocalStorage();
  const calls = {renders: 0, warns: []};
  const sandbox = {
    localStorage,
    fetch: fetchImpl || (async () => { throw new Error('no fetch configured'); }),
    console: {warn: (...args) => { calls.warns.push(args); }},
    renderImageControls: () => { calls.renders++; },
    renderModelPop: () => { calls.renders++; },
    fetchedModelCapabilities: null,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext('const MODEL_CAPABILITIES_CACHE_KEY = "sylvex-model-capabilities-v1";', context);
  vm.runInContext(extractConstObject('MODEL_FEATURES'), context);
  vm.runInContext(extractFunction('getModelCapabilities'), context);
  vm.runInContext(extractFunction('readCachedModelCapabilities'), context);
  vm.runInContext(extractFunction('writeCachedModelCapabilities'), context);
  vm.runInContext(extractFunction('loadModelCapabilities'), context);
  return {context, sandbox, localStorage, calls};
}

test('getModelCapabilities: falls back to MODEL_FEATURES when nothing fetched yet', () => {
  const {context} = buildContext();
  const result = vm.runInContext(`getModelCapabilities('nano_banana_pro')`, context);
  assert.deepEqual(toPlain(result), {character: true, object: true, seed: false, maxReferences: null});
});

test('getModelCapabilities: unknown model still defaults to all-false via fallback', () => {
  const {context} = buildContext();
  const result = vm.runInContext(`getModelCapabilities('totally_unknown_xyz')`, context);
  assert.deepEqual(toPlain(result), {character: false, object: false, seed: false, maxReferences: null});
});

test('getModelCapabilities: prefers fetched data over MODEL_FEATURES once loaded', () => {
  const {context} = buildContext();
  vm.runInContext(`fetchedModelCapabilities = {version: 'v1', models: {
    nano_banana_pro: {
      character: {visual_reference: {visual_mode: 'unsupported', max_count: 0}},
      object: {visual_reference: {visual_mode: 'unsupported', max_count: 0}},
      seed: true,
    },
  }};`, context);
  // MODEL_FEATURES says character:true/object:true/seed:false for this id -
  // the fetched entry above says the opposite, so the result must reflect
  // the fetched data, proving it takes priority once available.
  const result = vm.runInContext(`getModelCapabilities('nano_banana_pro')`, context);
  assert.deepEqual(toPlain(result), {character: false, object: false, seed: true, maxReferences: null});
});

test('getModelCapabilities: surfaces maxReferences from fetched visual_reference.max_count', () => {
  const {context} = buildContext();
  vm.runInContext(`fetchedModelCapabilities = {version: 'v1', models: {
    seedream_5_0_pro: {
      character: {visual_reference: {visual_mode: 'real_multi_image', max_count: 10}},
      object: {visual_reference: {visual_mode: 'real_multi_image', max_count: 10}},
      seed: true,
    },
  }};`, context);
  const result = vm.runInContext(`getModelCapabilities('seedream_5_0_pro')`, context);
  assert.deepEqual(toPlain(result), {character: true, object: true, seed: true, maxReferences: 10});
});

test('readCachedModelCapabilities: returns null when nothing cached', () => {
  const {context} = buildContext();
  const result = vm.runInContext(`readCachedModelCapabilities()`, context);
  assert.equal(result, null);
});

test('readCachedModelCapabilities: returns null (not a throw) on corrupt JSON', () => {
  const {context, localStorage} = buildContext();
  localStorage.setItem('sylvex-model-capabilities-v1', '{not valid json');
  const result = vm.runInContext(`readCachedModelCapabilities()`, context);
  assert.equal(result, null);
});

test('writeCachedModelCapabilities + readCachedModelCapabilities round-trip', () => {
  const {context, localStorage} = buildContext();
  vm.runInContext(`writeCachedModelCapabilities({version: 'abc123', models: {x: 1}})`, context);
  const stored = JSON.parse(localStorage.getItem('sylvex-model-capabilities-v1'));
  assert.deepEqual(toPlain(stored), {version: 'abc123', models: {x: 1}});
  const result = vm.runInContext(`readCachedModelCapabilities()`, context);
  assert.deepEqual(toPlain(result), {version: 'abc123', models: {x: 1}});
});

test('loadModelCapabilities: 200 response updates in-memory + localStorage and re-renders', async () => {
  let capturedHeaders = null;
  const {context, localStorage, calls} = buildContext({
    fetchImpl: async (url, opts) => {
      capturedHeaders = opts && opts.headers;
      return {
        status: 200,
        ok: true,
        json: async () => ({ok: true, version: 'v2', models: {grok: {character: {visual_reference: {visual_mode: 'unsupported'}}, object: {visual_reference: {visual_mode: 'unsupported'}}, seed: false}}}),
      };
    },
  });
  await vm.runInContext(`loadModelCapabilities()`, context);
  assert.deepEqual(toPlain(capturedHeaders), {});
  const fetched = vm.runInContext('fetchedModelCapabilities', context);
  assert.equal(fetched.version, 'v2');
  assert.ok(fetched.models.grok);
  assert.deepEqual(JSON.parse(localStorage.getItem('sylvex-model-capabilities-v1')), toPlain(fetched));
  assert.ok(calls.renders >= 1, 'should re-render after a fresh fetch');
});

test('loadModelCapabilities: sends If-None-Match from a pre-existing cache', async () => {
  const {context, localStorage} = buildContext({
    fetchImpl: async (url, opts) => {
      assert.deepEqual(toPlain(opts.headers), {'If-None-Match': '"cached-v1"'});
      return {status: 304, ok: true, json: async () => { throw new Error('must not be called on 304'); }};
    },
  });
  localStorage.setItem('sylvex-model-capabilities-v1', JSON.stringify({version: 'cached-v1', models: {a: 1}}));
  await vm.runInContext(`loadModelCapabilities()`, context);
  const fetched = vm.runInContext('fetchedModelCapabilities', context);
  // 304 confirms the cache is current - it must be left exactly as read from
  // localStorage, not cleared or replaced.
  assert.deepEqual(toPlain(fetched), {version: 'cached-v1', models: {a: 1}});
});

test('loadModelCapabilities: network failure falls back to the pre-existing cached snapshot', async () => {
  const {context, localStorage, calls} = buildContext({
    fetchImpl: async () => { throw new TypeError('Failed to fetch'); },
  });
  localStorage.setItem('sylvex-model-capabilities-v1', JSON.stringify({version: 'last-known-good', models: {b: 2}}));
  await vm.runInContext(`loadModelCapabilities()`, context);
  const fetched = vm.runInContext('fetchedModelCapabilities', context);
  assert.deepEqual(toPlain(fetched), {version: 'last-known-good', models: {b: 2}});
  assert.ok(calls.warns.length >= 1, 'should log a warning, not throw');
});

test('loadModelCapabilities: network failure with no cache at all leaves fetchedModelCapabilities null (MODEL_FEATURES fallback stays active)', async () => {
  const {context} = buildContext({
    fetchImpl: async () => { throw new TypeError('Failed to fetch'); },
  });
  await vm.runInContext(`loadModelCapabilities()`, context);
  const fetched = vm.runInContext('fetchedModelCapabilities', context);
  assert.equal(fetched, null);
  // Confirms the promised fallback: getModelCapabilities still works via
  // MODEL_FEATURES when nothing was ever successfully fetched or cached.
  const result = vm.runInContext(`getModelCapabilities('nano_banana_pro')`, context);
  assert.deepEqual(toPlain(result), {character: true, object: true, seed: false, maxReferences: null});
});

test('loadModelCapabilities: non-ok, non-304 HTTP error keeps the cached snapshot', async () => {
  const {context, localStorage} = buildContext({
    fetchImpl: async () => ({status: 500, ok: false, json: async () => { throw new Error('must not be called'); }}),
  });
  localStorage.setItem('sylvex-model-capabilities-v1', JSON.stringify({version: 'still-good', models: {c: 3}}));
  await vm.runInContext(`loadModelCapabilities()`, context);
  const fetched = vm.runInContext('fetchedModelCapabilities', context);
  assert.deepEqual(toPlain(fetched), {version: 'still-good', models: {c: 3}});
});
