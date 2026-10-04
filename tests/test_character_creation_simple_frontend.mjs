// Run with: node --test tests/test_character_creation_simple_frontend.mjs
//
// Regression tests for the frontend half of the final simplified Character
// creation flow: Name + Gender + exactly one photo + one optional text
// field + Create Character button - nothing else. Guards against
// reintroducing any of the reverted Character Creation V2 complexity
// (Manual/Create-with-AI modes, Preserve/AI Polish, multiple upload
// slots) and confirms Object creation (3 photo slots, no gender) is
// untouched.
//
// Also covers the conversion of Character creation into an async SYLVEX
// job: createCharacterCreationJob() only ever returns a job_id (never a
// resource), waitCharacterCreationJob() polls the same job endpoint
// every other Pro Studio generation job uses, and the pending-job
// persistence helpers let an unfinished job survive a page reload.
//
// Exercises the cabinet.js helpers directly via node:vm extraction (same
// pattern as test_character_reference_library_frontend.mjs).
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

function makeContext() {
  const sandbox = {
    renderVisualCreateModal: () => {},
    toast: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('openVisualCreateModal'), context);
  vm.runInContext(extractFunction('visualCreateCanSave'), context);
  return context;
}

test('openVisualCreateModal: the draft has only kind/name/gender/description/photos - no mode or processingMode field', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  const draft = vm.runInContext('visualCreateDraft', context);
  assert.deepEqual(Object.keys(draft).sort(), ['description', 'gender', 'kind', 'name', 'photos']);
  assert.equal(draft.kind, 'character');
  assert.equal(draft.name, '');
  assert.equal(draft.gender, '');
  assert.equal(draft.description, '');
  assert.deepEqual([...draft.photos], []);
});

test('visualCreateCanSave: Character requires name, gender and exactly one photo - description stays optional', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);

  vm.runInContext(`visualCreateDraft.name = 'Islam'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false, 'still missing gender and photo');

  vm.runInContext(`visualCreateDraft.gender = 'male'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false, 'still missing the photo');

  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true, 'description was never required');
});

test('visualCreateCanSave: Character with no photo cannot be saved even with a description (photo is mandatory, unlike the reverted text-only mode)', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  vm.runInContext(`visualCreateDraft.name = 'Nova'`, context);
  vm.runInContext(`visualCreateDraft.gender = 'female'`, context);
  vm.runInContext(`visualCreateDraft.description = 'cyberpunk hacker, neon jacket'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
});

test('visualCreateCanSave: Object creation is unaffected (name + photo, no gender requirement)', () => {
  const context = makeContext();
  vm.runInContext(`openVisualCreateModal(null, 'object')`, context);
  vm.runInContext(`visualCreateDraft.name = 'Watch'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

// ---- createCharacterCreationJob: the request always caps photos at 1,
// never mentions HeyGen, and only ever returns a job_id (the endpoint is
// now async - it never returns the finished resource directly) ----

function makeNetworkContext(responseBody, ok = true) {
  const calls = {body: null, url: null};
  const sandbox = {
    getTelegramId: () => 42,
    translateGenerationError: (err, fallback) => fallback,
    fetch: async (url, options) => {
      calls.url = url;
      calls.body = JSON.parse(options.body);
      return { ok, json: async () => responseBody };
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('createCharacterCreationJob'), context);
  return {context, calls};
}

test('createCharacterCreationJob: sends at most one photo even if more were somehow collected, and returns only a job_id', async () => {
  const {context, calls} = makeNetworkContext({ok: true, job_id: 'job-abc', status: 'processing'});
  const jobId = await vm.runInContext(`createCharacterCreationJob('Islam', ['https://cdn.sylvex.ai/a.jpg', 'https://cdn.sylvex.ai/b.jpg'], 'male', 'tall')`, context);
  assert.equal(jobId, 'job-abc');
  assert.deepEqual(calls.body.photos, ['https://cdn.sylvex.ai/a.jpg']);
  assert.equal(calls.body.name, 'Islam');
  assert.equal(calls.body.gender, 'male');
  assert.equal(calls.body.description, 'tall');
  // No mode/processingMode field is ever sent - that was V2-only.
  assert.equal('mode' in calls.body, false);
  assert.equal('processing_mode' in calls.body, false);
  // SYLVEX-only Character pipeline: the request never mentions HeyGen in
  // any form - no heygen_* fields, no separate provider-registration call.
  assert.equal(calls.url, '/api/public/prostudio/character');
  assert.equal(Object.keys(calls.body).some((key) => key.toLowerCase().includes('heygen')), false);
});

test('createCharacterCreationJob: a response with no job_id is treated as a failure, never blaming HeyGen', async () => {
  const {context} = makeNetworkContext({ok: false, error: 'boom'}, false);
  await assert.rejects(
    vm.runInContext(`createCharacterCreationJob('Islam', ['https://cdn.sylvex.ai/a.jpg'], 'male', '')`, context),
    (err) => {
      assert.equal(/heygen/i.test(err.message), false);
      return true;
    },
  );
});

// ---- waitCharacterCreationJob: polls GET /api/public/prostudio/job/{id},
// the same endpoint every other Pro Studio generation job uses ----

function makePollingContext(statuses) {
  const calls = {urls: []};
  let index = 0;
  const sandbox = {
    wait: () => Promise.resolve(),
    translateGenerationError: (err, fallback) => fallback,
    fetch: async (url) => {
      calls.urls.push(url);
      const job = statuses[Math.min(index, statuses.length - 1)];
      index += 1;
      return { ok: true, json: async () => job };
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('waitCharacterCreationJob'), context);
  return {context, calls};
}

test('waitCharacterCreationJob: polls until completed and returns the result with job_id filled in', async () => {
  const {context, calls} = makePollingContext([
    {ok: true, status: 'processing', job_id: 'job-1'},
    {ok: true, status: 'processing', job_id: 'job-1'},
    {ok: true, status: 'completed', job_id: 'job-1', result: {ok: true, character_id: 'custom_character_abc', resource: {id: 'custom_character_abc'}}},
  ]);
  const result = await vm.runInContext(`waitCharacterCreationJob('job-1')`, context);
  assert.equal(result.character_id, 'custom_character_abc');
  assert.equal(result.job_id, 'job-1');
  assert.equal(calls.urls[0], '/api/public/prostudio/job/job-1');
});

test('waitCharacterCreationJob: throws a translated error on a failed job', async () => {
  const {context} = makePollingContext([
    {ok: true, status: 'failed', error: {error: 'OpenAI quota exceeded'}},
  ]);
  await assert.rejects(
    vm.runInContext(`waitCharacterCreationJob('job-2')`, context),
    (err) => {
      assert.equal(err.terminalStatus, 'failed');
      return true;
    },
  );
});

// ---- Pending-job persistence: survives a page reload ----

function makeStorageContext() {
  const store = new Map();
  const sandbox = {
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { store.delete(key); },
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationJobStorageKey'), context);
  vm.runInContext(extractFunction('persistPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('readPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('clearPendingCharacterCreationJob'), context);
  return {context, store};
}

test('persistPendingCharacterCreationJob / readPendingCharacterCreationJob: round-trip the job info', () => {
  const {context} = makeStorageContext();
  assert.equal(vm.runInContext('readPendingCharacterCreationJob()', context), null);
  vm.runInContext(`persistPendingCharacterCreationJob('job-9', 'Islam', 'male', 'tall')`, context);
  const pending = vm.runInContext('readPendingCharacterCreationJob()', context);
  assert.equal(pending.jobId, 'job-9');
  assert.equal(pending.name, 'Islam');
  assert.equal(pending.gender, 'male');
  assert.equal(pending.description, 'tall');
});

test('clearPendingCharacterCreationJob: only clears a matching jobId, never someone else\'s in-flight job', () => {
  const {context} = makeStorageContext();
  vm.runInContext(`persistPendingCharacterCreationJob('job-9', 'Islam', 'male', '')`, context);
  vm.runInContext(`clearPendingCharacterCreationJob('job-other')`, context);
  assert.ok(vm.runInContext('readPendingCharacterCreationJob()', context), 'a mismatched jobId must not clear the pending marker');
  vm.runInContext(`clearPendingCharacterCreationJob('job-9')`, context);
  assert.equal(vm.runInContext('readPendingCharacterCreationJob()', context), null);
});

// ---- restorePendingCharacterCreationJob: resumes an unfinished job on
// page load and inserts the Character even though the modal is closed ----

function makeRestoreContext(pending, jobOutcome) {
  const store = new Map();
  if (pending) store.set('sylvex-prostudio-character-job-42', JSON.stringify(pending));
  const calls = {toasts: [], saved: null, applied: null, cleared: false};
  const sandbox = {
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { store.delete(key); calls.cleared = true; },
    },
    toast: (msg) => calls.toasts.push(msg),
    translateGenerationError: (err, fallback) => fallback,
    normalizeVisualItem: (x) => x,
    visualPreviewUrl: (resource) => (resource && resource.previewUrl) || '',
    fetch: async () => ({ ok: true, json: async () => jobOutcome }),
    wait: () => Promise.resolve(),
    saveVisualItemToBackend: async (kind, item) => { calls.saved = {kind, item}; return item; },
    serverVisualItems: { characters: [], objects: [] },
    loadCustomVisualItems: () => [],
    saveCustomVisualItems: () => {},
    isVideoMode: () => false,
    applyVisualReferenceToVideo: () => {},
    applyCharacterReferenceSelection: (item) => { calls.applied = item; },
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderImageStylePanel: () => {},
    renderVideoReferencesPreview: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationJobStorageKey'), context);
  vm.runInContext(extractFunction('persistPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('readPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('clearPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('waitCharacterCreationJob'), context);
  vm.runInContext(extractFunction('restorePendingCharacterCreationJob'), context);
  return {context, calls};
}

test('restorePendingCharacterCreationJob: does nothing when no job was pending', async () => {
  const {context, calls} = makeRestoreContext(null, {});
  await vm.runInContext('restorePendingCharacterCreationJob()', context);
  assert.equal(calls.saved, null);
  assert.equal(calls.toasts.length, 0);
});

test('restorePendingCharacterCreationJob: on completion, inserts the Character and clears the pending marker', async () => {
  const pending = {jobId: 'job-9', name: 'Islam', gender: 'male', description: '', startedAt: Date.now()};
  const jobOutcome = {
    ok: true, status: 'completed', job_id: 'job-9',
    result: {ok: true, character_id: 'custom_character_abc', resource: {id: 'custom_character_abc', previewUrl: 'https://cdn.sylvex.ai/p.png'}},
  };
  const {context, calls} = makeRestoreContext(pending, jobOutcome);
  await vm.runInContext('restorePendingCharacterCreationJob()', context);
  assert.ok(calls.saved, 'the restored Character must still be saved via saveVisualItemToBackend');
  assert.equal(calls.saved.kind, 'character');
  assert.equal(calls.saved.item.id, 'custom_character_abc');
  assert.ok(calls.applied, 'applyCharacterReferenceSelection must run for the restored Character');
  assert.ok(calls.toasts.length > 0);
  assert.equal(calls.cleared, true, 'the pending marker must be cleared once the job resolves');
});

test('restorePendingCharacterCreationJob: on a genuine terminal failure, toasts the backend error and still clears the pending marker', async () => {
  const pending = {jobId: 'job-9', name: 'Islam', gender: 'male', description: '', startedAt: Date.now()};
  const jobOutcome = {ok: true, status: 'failed', job_id: 'job-9', error: {error: 'OpenAI billing limit reached'}};
  const {context, calls} = makeRestoreContext(pending, jobOutcome);
  await vm.runInContext('restorePendingCharacterCreationJob()', context);
  assert.equal(calls.saved, null);
  assert.ok(calls.toasts.length > 0);
  assert.equal(calls.cleared, true);
});

test('restorePendingCharacterCreationJob: a transient/non-terminal error (e.g. network exhaustion) must NOT clear the pending marker', async () => {
  // Fix: with the backend heartbeat fix, a 'failed' job status now
  // genuinely means the background Character task stopped and will
  // never later create a resource - so clearing the marker on that
  // outcome is safe. But waitCharacterCreationJob() can also throw a
  // plain network/polling error with no terminalStatus at all (the job
  // itself may still be running server-side) - that case must leave the
  // marker in place so the next reload/init can try restoring it again,
  // instead of silently losing track of a still-running job.
  const pending = {jobId: 'job-9', name: 'Islam', gender: 'male', description: '', startedAt: Date.now()};
  const store = new Map();
  store.set('sylvex-prostudio-character-job-42', JSON.stringify(pending));
  const calls = {toasts: [], removed: []};
  const sandbox = {
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { calls.removed.push(key); store.delete(key); },
    },
    toast: (msg) => calls.toasts.push(msg),
    translateGenerationError: (err, fallback) => fallback,
    normalizeVisualItem: (x) => x,
    visualPreviewUrl: () => '',
    waitCharacterCreationJob: async () => { throw new Error('network unreachable'); },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationJobStorageKey'), context);
  vm.runInContext(extractFunction('persistPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('readPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('clearPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('restorePendingCharacterCreationJob'), context);

  await vm.runInContext('restorePendingCharacterCreationJob()', context);

  assert.ok(calls.toasts.length > 0, 'the user is still told something went wrong');
  assert.equal(calls.removed.length, 0, 'the pending marker must survive a non-terminal error');
  assert.ok(store.has('sylvex-prostudio-character-job-42'));
});

// ---- saveVisualCreateDraft: same pending-marker rule applies to the
// Create Character modal's own save path, not just the reload-recovery
// path ----

function makeSaveDraftContext({result, error} = {}) {
  const store = new Map();
  const calls = { removed: [], toasts: [] };
  const sandbox = {
    getTelegramId: () => 42,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { calls.removed.push(key); store.delete(key); },
    },
    visualCreateDraft: {
      kind: 'character', name: 'Islam', gender: 'male', description: '',
      photos: ['https://cdn.sylvex.ai/a.jpg'], saving: false, done: false, statusText: '',
    },
    wait: () => Promise.resolve(),
    toast: (msg) => { calls.toasts.push(msg); return msg; },
    renderVisualCreateModal: () => {},
    visualCreateKindLabel: () => 'Персонаж',
    visualCreateListLabel: () => 'персонажей',
    translateGenerationError: (err, fallback) => fallback,
    normalizeVisualItem: (x) => x,
    visualPreviewUrl: (resource) => (resource && resource.previewUrl) || '',
    createCharacterCreationJob: async () => 'job-save-1',
    waitCharacterCreationJob: async () => {
      if (error) throw error;
      return result;
    },
    saveVisualItemToBackend: async (kind, item) => item,
    serverVisualItems: { characters: [], objects: [] },
    loadCustomVisualItems: () => [],
    saveCustomVisualItems: () => {},
    isVideoMode: () => false,
    applyVisualReferenceToVideo: () => {},
    applyCharacterReferenceSelection: () => {},
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderImageStylePanel: () => {},
    renderVideoReferencesPreview: () => {},
    closeVisualCreateModal: () => {},
    closeVisualPicker: () => {},
    closeImageStylePanel: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationJobStorageKey'), context);
  vm.runInContext(extractFunction('persistPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('readPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('clearPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('saveVisualCreateDraft'), context);
  return {context, calls, store};
}

test('saveVisualCreateDraft: on success, the pending marker is persisted then cleared', async () => {
  const {context, calls, store} = makeSaveDraftContext({
    result: {ok: true, character_id: 'custom_character_abc', resource: {id: 'custom_character_abc', previewUrl: 'https://cdn.sylvex.ai/p.png'}},
  });
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.ok(calls.removed.includes('sylvex-prostudio-character-job-42'));
  assert.equal(store.has('sylvex-prostudio-character-job-42'), false);
});

test('saveVisualCreateDraft: a genuine terminal job failure clears the pending marker', async () => {
  const terminalError = new Error('safety rejection');
  terminalError.terminalStatus = 'failed';
  const {context, calls, store} = makeSaveDraftContext({error: terminalError});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.ok(calls.removed.includes('sylvex-prostudio-character-job-42'));
  assert.equal(store.has('sylvex-prostudio-character-job-42'), false);
  assert.ok(calls.toasts.length > 0);
});

test('saveVisualCreateDraft: a transient/non-terminal error leaves the pending marker in place for reload recovery', async () => {
  const {context, calls, store} = makeSaveDraftContext({error: new Error('network unreachable')});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(calls.removed.length, 0, 'the pending marker must survive a non-terminal error');
  assert.ok(store.has('sylvex-prostudio-character-job-42'));
  assert.ok(calls.toasts.length > 0, 'the user is still told something went wrong');
});
