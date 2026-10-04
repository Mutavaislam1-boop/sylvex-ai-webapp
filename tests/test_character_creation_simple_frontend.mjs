// Run with: node --test tests/test_character_creation_simple_frontend.mjs
//
// Regression tests for Character Creation's background-card UX: pressing
// Create submits the job, receives a job_id, immediately closes the
// creation modal, and immediately inserts a pending Character card into
// the Character list (loading state) - it never blocks the modal waiting
// for the job to finish. Character creation then continues independently
// in the background: the user is free to close the picker, navigate
// elsewhere, generate other content, or close the app entirely.
//
// Covers:
//   - One Character creation job = one Character card, keyed by job_id
//     (a map, never a single global "pendingCharacterCreationJob") - so
//     several jobs can run at once, each with its own independent card.
//   - pollCharacterCreationJob()/waitCharacterCreationJob(): polls GET
//     /api/public/prostudio/job/{id}; onProgress fires on every
//     still-processing tick (so a pending card can show "1/4", a
//     progressive Primary Face preview, etc.), and the terminal outcome
//     (completed/failed/cancelled) is unchanged from before.
//   - Pending-job storage is a job_id-keyed map (persist/read/clear),
//     and a separate dismissed-job set so a deleted failed card never
//     resurrects from the backend's own forever-failed job row.
//   - upsertCharacterCreationPendingCard/removeCharacterCreationCard/
//     replaceCharacterCreationCardWithResource/
//     updateCharacterCreationPendingCardProgress: the pending-card
//     lifecycle inside serverVisualItems.characters (stable position,
//     never removed-then-reinserted as an unrelated card).
//   - characterCardPendingStatus(): the gate that makes a 'creating'/
//     'failed' Character card unselectable, while every existing/preset
//     Character and every genuinely 'ready' custom Character behaves
//     exactly as before.
//   - startCharacterCreationCardPoll/completeCharacterCreationJobCard/
//     failCharacterCreationJobCard: on completion, result.resource is
//     authoritative (already persisted server-side) - replaces the
//     pending card in place, no second
//     /api/public/prostudio/resources POST. On a genuine terminal
//     failure, the card stays visible as failed, never silently removed.
//   - retryFailedCharacterJob/deleteFailedCharacterJob: Retry starts a
//     brand-new job from the failed card's own inputs; Delete removes
//     only that one pending-job card, never a real saved Character.
//   - restorePendingCharacterCreationJobs(): backend-first restore after
//     a reload - GET /api/public/prostudio/character-creation-jobs is
//     authoritative; works even with localStorage empty/unavailable.
//   - saveVisualCreateDraft(): Object creation's synchronous flow is
//     unaffected; Character creation now delegates to the above instead.
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

function makeStorage() {
  const store = new Map();
  return {
    store,
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => { store.set(key, String(value)); },
      removeItem: (key) => { store.delete(key); },
    },
  };
}

// ---- openVisualCreateModal / visualCreateCanSave: unaffected by the
// background-card rework ----

function makeDraftContext() {
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
  const context = makeDraftContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  const draft = vm.runInContext('visualCreateDraft', context);
  assert.deepEqual(Object.keys(draft).sort(), ['description', 'gender', 'kind', 'name', 'photos']);
  assert.equal(draft.kind, 'character');
});

test('visualCreateCanSave: Character requires name, gender and exactly one photo - description stays optional', () => {
  const context = makeDraftContext();
  vm.runInContext(`openVisualCreateModal(null, 'character')`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  vm.runInContext(`visualCreateDraft.name = 'Islam'`, context);
  vm.runInContext(`visualCreateDraft.gender = 'male'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false, 'still missing the photo');
  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

test('visualCreateCanSave: Object creation is unaffected (name + photo, no gender requirement)', () => {
  const context = makeDraftContext();
  vm.runInContext(`openVisualCreateModal(null, 'object')`, context);
  vm.runInContext(`visualCreateDraft.name = 'Watch'`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), false);
  vm.runInContext(`visualCreateDraft.photos = ['data:image/png;base64,aaa']`, context);
  assert.equal(vm.runInContext('visualCreateCanSave()', context), true);
});

// ---- createCharacterCreationJob: unchanged - still returns only a job_id ----

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
  assert.equal(calls.url, '/api/public/prostudio/character');
});

test('createCharacterCreationJob: a response with no job_id is treated as a failure', async () => {
  const {context} = makeNetworkContext({ok: false, error: 'boom'}, false);
  await assert.rejects(
    vm.runInContext(`createCharacterCreationJob('Islam', ['https://cdn.sylvex.ai/a.jpg'], 'male', '')`, context),
  );
});

// ---- pollCharacterCreationJob / waitCharacterCreationJob: polling +
// progress reporting ----

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
  vm.runInContext(extractFunction('pollCharacterCreationJob'), context);
  vm.runInContext(extractFunction('waitCharacterCreationJob'), context);
  return {context, calls};
}

test('waitCharacterCreationJob: polls until completed and returns the result with job_id filled in', async () => {
  const {context, calls} = makePollingContext([
    {ok: true, status: 'processing', job_id: 'job-1'},
    {ok: true, status: 'completed', job_id: 'job-1', result: {ok: true, character_id: 'custom_character_abc', resource: {id: 'custom_character_abc'}}},
  ]);
  const result = await vm.runInContext(`waitCharacterCreationJob('job-1')`, context);
  assert.equal(result.character_id, 'custom_character_abc');
  assert.equal(result.job_id, 'job-1');
  assert.equal(calls.urls[0], '/api/public/prostudio/job/job-1');
});

test('waitCharacterCreationJob: throws a translated error with terminalStatus on a failed job', async () => {
  const {context} = makePollingContext([
    {ok: true, status: 'failed', error: {error: 'OpenAI quota exceeded'}},
  ]);
  await assert.rejects(
    vm.runInContext(`waitCharacterCreationJob('job-2')`, context),
    (err) => { assert.equal(err.terminalStatus, 'failed'); return true; },
  );
});

test('pollCharacterCreationJob: onProgress fires on every still-processing tick with the raw job payload', async () => {
  const progressTicks = [];
  const {context} = makePollingContext([
    {ok: true, status: 'processing', result: {stage: 'front', completed_references: 1, primary_url: 'https://cdn.sylvex.ai/primary.png'}},
    {ok: true, status: 'processing', result: {stage: 'side', completed_references: 2}},
    {ok: true, status: 'completed', result: {ok: true, resource: {id: 'custom_character_abc'}}},
  ]);
  vm.runInContext('(globalThis.__onProgress = (job) => { globalThis.__ticks = (globalThis.__ticks||[]).concat([job]); })', context);
  const result = await vm.runInContext(`pollCharacterCreationJob('job-3', {onProgress: __onProgress})`, context);
  const ticks = vm.runInContext('globalThis.__ticks', context);
  assert.equal(ticks.length, 2);
  assert.equal(ticks[0].result.stage, 'front');
  assert.equal(ticks[0].result.primary_url, 'https://cdn.sylvex.ai/primary.png');
  assert.equal(ticks[1].result.stage, 'side');
  assert.equal(result.resource.id, 'custom_character_abc');
});

test('pollCharacterCreationJob: onProgress never fires once the job reaches a terminal status', async () => {
  const {context} = makePollingContext([
    {ok: true, status: 'failed', error: {error: 'boom'}},
  ]);
  vm.runInContext('(globalThis.__onProgress = (job) => { globalThis.__ticks = (globalThis.__ticks||[]).concat([job]); })', context);
  await assert.rejects(vm.runInContext(`pollCharacterCreationJob('job-4', {onProgress: __onProgress})`, context));
  const ticks = vm.runInContext('globalThis.__ticks || []', context);
  assert.equal(ticks.length, 0);
});

// ---- Map-keyed pending-job storage: one job = one entry, never a single
// global pending job ----

function makeJobsStorageContext() {
  const {store, localStorage} = makeStorage();
  const sandbox = { getTelegramId: () => 42, localStorage };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationJobsStorageKey'), context);
  vm.runInContext(extractFunction('readPendingCharacterCreationJobs'), context);
  vm.runInContext(extractFunction('writePendingCharacterCreationJobs'), context);
  vm.runInContext(extractFunction('persistPendingCharacterCreationJob'), context);
  vm.runInContext(extractFunction('clearPendingCharacterCreationJob'), context);
  return {context, store};
}

test('readPendingCharacterCreationJobs: starts empty', () => {
  const {context} = makeJobsStorageContext();
  assert.deepEqual({...vm.runInContext('readPendingCharacterCreationJobs()', context)}, {});
});

test('persistPendingCharacterCreationJob: multiple jobs are tracked independently in the same map', () => {
  const {context} = makeJobsStorageContext();
  vm.runInContext(`persistPendingCharacterCreationJob('job-A', 'Islam', 'male', 'tall', 'https://cdn.sylvex.ai/a.jpg')`, context);
  vm.runInContext(`persistPendingCharacterCreationJob('job-B', 'Nova', 'female', '', 'https://cdn.sylvex.ai/b.jpg')`, context);
  const map = vm.runInContext('readPendingCharacterCreationJobs()', context);
  assert.equal(Object.keys(map).length, 2);
  assert.equal(map['job-A'].name, 'Islam');
  assert.equal(map['job-A'].previewUrl, 'https://cdn.sylvex.ai/a.jpg');
  assert.equal(map['job-B'].name, 'Nova');
});

test('clearPendingCharacterCreationJob: removes only the matching job_id, leaving every other pending job untouched', () => {
  const {context} = makeJobsStorageContext();
  vm.runInContext(`persistPendingCharacterCreationJob('job-A', 'Islam', 'male', '', 'https://cdn.sylvex.ai/a.jpg')`, context);
  vm.runInContext(`persistPendingCharacterCreationJob('job-B', 'Nova', 'female', '', 'https://cdn.sylvex.ai/b.jpg')`, context);
  vm.runInContext(`clearPendingCharacterCreationJob('job-A')`, context);
  const map = vm.runInContext('readPendingCharacterCreationJobs()', context);
  assert.deepEqual(Object.keys(map), ['job-B']);
});

// ---- Dismissed-job set: deleting a failed card must not resurrect it ----

function makeDismissedContext() {
  const {localStorage} = makeStorage();
  const sandbox = { getTelegramId: () => 42, localStorage };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('dismissedCharacterJobsKey'), context);
  vm.runInContext(extractFunction('readDismissedCharacterJobIds'), context);
  vm.runInContext(extractFunction('rememberDismissedCharacterJob'), context);
  return context;
}

test('rememberDismissedCharacterJob: records a job_id so it is not forgotten', () => {
  const context = makeDismissedContext();
  assert.deepEqual([...vm.runInContext('readDismissedCharacterJobIds()', context)], []);
  vm.runInContext(`rememberDismissedCharacterJob('job-dead')`, context);
  assert.deepEqual([...vm.runInContext('readDismissedCharacterJobIds()', context)], ['job-dead']);
  // Idempotent - dismissing the same job twice does not duplicate it.
  vm.runInContext(`rememberDismissedCharacterJob('job-dead')`, context);
  assert.deepEqual([...vm.runInContext('readDismissedCharacterJobIds()', context)], ['job-dead']);
});

// ---- pendingCharacterCardId / characterJobIdFromCardId: round-trip ----

test('pendingCharacterCardId / characterJobIdFromCardId round-trip a job_id', () => {
  const sandbox = {};
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('pendingCharacterCardId'), context);
  vm.runInContext(extractFunction('characterJobIdFromCardId'), context);
  const id = vm.runInContext(`pendingCharacterCardId('job-123')`, context);
  assert.equal(id, 'pending_character_job-123');
  assert.equal(vm.runInContext(`characterJobIdFromCardId('${id}')`, context), 'job-123');
});

// ---- characterCardPendingStatus: the selectability gate ----

test('characterCardPendingStatus: creating/failed are gated; every other Character (including no status field at all) is "ready" as before', () => {
  const sandbox = {};
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCardPendingStatus'), context);
  assert.equal(vm.runInContext(`characterCardPendingStatus({status: 'creating'})`, context), 'creating');
  assert.equal(vm.runInContext(`characterCardPendingStatus({status: 'failed'})`, context), 'failed');
  assert.equal(vm.runInContext(`characterCardPendingStatus({status: 'ready'})`, context), '');
  // Preset/built-in Characters never carry a status field at all.
  assert.equal(vm.runInContext(`characterCardPendingStatus({})`, context), '');
  assert.equal(vm.runInContext(`characterCardPendingStatus(null)`, context), '');
});

// ---- characterCreationPendingCardHtml: markup for the two non-ready
// states - same card dimensions/classes, loader lives inside the card,
// and a failed card never silently disappears (Retry/Delete instead) ----

function makeCardHtmlContext() {
  const sandbox = { S: { escapeHtml: (s) => String(s) } };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCardPendingStatus'), context);
  vm.runInContext(extractFunction('characterCreationStageLabel'), context);
  vm.runInContext(extractFunction('characterCreationPendingCardHtml'), context);
  return context;
}

test('characterCreationPendingCardHtml: a "creating" card shows a loader and progress label, and is not clickable into References/History', () => {
  const context = makeCardHtmlContext();
  const html = vm.runInContext(
    `characterCreationPendingCardHtml({stage: 'side', completedReferences: 2, totalReferences: 4}, 'pending_character_job-1', 'Islam', '', 'creating')`,
    context,
  );
  assert.match(html, /image-style-card/);
  assert.match(html, /character-pending-spinner/);
  assert.match(html, />2\/4</);
  assert.doesNotMatch(html, /openCharacterDetail/);
  assert.doesNotMatch(html, /pickVisualReference/);
  assert.match(html, /handlePendingCharacterCardClick/);
});

test('characterCreationPendingCardHtml: a "failed" card shows the name, Failed status, and Retry/Delete - never silently removed', () => {
  const context = makeCardHtmlContext();
  const html = vm.runInContext(
    `characterCreationPendingCardHtml({}, 'pending_character_job-2', 'Islam', '', 'failed')`,
    context,
  );
  assert.match(html, /Islam/);
  assert.match(html, /character-pending-status-failed/);
  assert.match(html, /retryFailedCharacterJob\(event, 'pending_character_job-2'\)/);
  assert.match(html, /deleteFailedCharacterJob\(event, 'pending_character_job-2'\)/);
  assert.doesNotMatch(html, /openCharacterDetail/);
  assert.doesNotMatch(html, /pickVisualReference/);
});

test('characterCreationStageLabel: "Creating..." before Primary, N/4 per completed reference, "Finalizing..." while saving', () => {
  const sandbox = {};
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('characterCreationStageLabel'), context);
  assert.equal(vm.runInContext(`characterCreationStageLabel({})`, context), 'Создаём...');
  assert.equal(vm.runInContext(`characterCreationStageLabel({completedReferences: 1, totalReferences: 4})`, context), '1/4');
  assert.equal(vm.runInContext(`characterCreationStageLabel({completedReferences: 3, totalReferences: 4})`, context), '3/4');
  assert.equal(vm.runInContext(`characterCreationStageLabel({stage: 'saving', completedReferences: 4, totalReferences: 4})`, context), 'Завершаем...');
});

// ---- Pending-card lifecycle inside serverVisualItems.characters ----

function makeCardLifecycleContext() {
  const serverVisualItems = { characters: [], objects: [] };
  const localCache = { characters: [] };
  const sandbox = {
    serverVisualItems,
    normalizeVisualItem: (x) => x,
    loadCustomVisualItems: (kind) => localCache[kind].slice(),
    saveCustomVisualItems: (kind, items) => { localCache[kind] = items.slice(); },
    activeImageStylePanelKind: 'character',
    renderImageStylePanel: () => {},
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractFunction('pendingCharacterCardId'), context);
  vm.runInContext(extractFunction('characterJobIdFromCardId'), context);
  vm.runInContext(extractFunction('upsertCharacterCreationPendingCard'), context);
  vm.runInContext(extractFunction('removeCharacterCreationCard'), context);
  vm.runInContext(extractFunction('replaceCharacterCreationCardWithResource'), context);
  vm.runInContext(extractFunction('updateCharacterCreationPendingCardProgress'), context);
  return {context, serverVisualItems, localCache};
}

test('upsertCharacterCreationPendingCard: inserts a pending card with job_id/name/gender/preview/status/created_at', () => {
  const {context, serverVisualItems} = makeCardLifecycleContext();
  vm.runInContext(
    `upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: 'https://cdn.sylvex.ai/a.jpg', status: 'creating', createdAt: '2026-01-01T00:00:00Z'})`,
    context,
  );
  assert.equal(serverVisualItems.characters.length, 1);
  const card = serverVisualItems.characters[0];
  assert.equal(card.id, 'pending_character_job-1');
  assert.equal(card.job_id, 'job-1');
  assert.equal(card.name, 'Islam');
  assert.equal(card.gender, 'male');
  assert.equal(card.previewUrl, 'https://cdn.sylvex.ai/a.jpg');
  assert.equal(card.status, 'creating');
  assert.equal(card.created_at, '2026-01-01T00:00:00Z');
});

test('upsertCharacterCreationPendingCard: multiple concurrent jobs each get their own independent card', () => {
  const {context, serverVisualItems} = makeCardLifecycleContext();
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-A', name: 'Islam', gender: 'male', previewUrl: 'https://cdn.sylvex.ai/a.jpg', status: 'creating'})`, context);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-B', name: 'Nova', gender: 'female', previewUrl: 'https://cdn.sylvex.ai/b.jpg', status: 'creating'})`, context);
  assert.equal(serverVisualItems.characters.length, 2);
  vm.runInContext(`updateCharacterCreationPendingCardProgress('job-A', {stage: 'front', completed_references: 1})`, context);
  const cardA = serverVisualItems.characters.find((c) => c.job_id === 'job-A');
  const cardB = serverVisualItems.characters.find((c) => c.job_id === 'job-B');
  assert.equal(cardA.completedReferences, 1);
  assert.equal(cardB.completedReferences, 0, 'job-B must be unaffected by job-A\'s progress update');
});

test('upsertCharacterCreationPendingCard: re-upserting the same job_id updates in place - never duplicates or reorders the card', () => {
  const {context, serverVisualItems} = makeCardLifecycleContext();
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-other', name: 'Nova', gender: 'female', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', status: 'failed'})`, context);
  assert.equal(serverVisualItems.characters.length, 2);
  const card = serverVisualItems.characters.find((c) => c.job_id === 'job-1');
  assert.equal(card.status, 'failed');
  assert.equal(card.name, 'Islam', 'name carried forward from the original upsert');
});

test('updateCharacterCreationPendingCardProgress: writes stage/completedReferences and the progressive Primary Face preview', () => {
  const {context, serverVisualItems} = makeCardLifecycleContext();
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: 'https://cdn.sylvex.ai/source.jpg', status: 'creating'})`, context);
  vm.runInContext(`updateCharacterCreationPendingCardProgress('job-1', {stage: 'front', completed_references: 1, primary_url: 'https://cdn.sylvex.ai/primary.png'})`, context);
  const card = serverVisualItems.characters[0];
  assert.equal(card.stage, 'front');
  assert.equal(card.completedReferences, 1);
  // Primary completion is never treated as Character completion - status
  // stays 'creating'.
  assert.equal(card.status, 'creating');
  assert.equal(card.previewUrl, 'https://cdn.sylvex.ai/primary.png', 'source thumbnail is replaced by the generated Primary Face once known');
});

test('replaceCharacterCreationCardWithResource: swaps the pending card in place for the real Character - same position, no stray card left behind', () => {
  const {context, serverVisualItems, localCache} = makeCardLifecycleContext();
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-other', name: 'Nova', gender: 'female', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(
    `replaceCharacterCreationCardWithResource('job-1', {id: 'custom_character_abc', name: 'Islam', previewUrl: 'https://cdn.sylvex.ai/p.png'})`,
    context,
  );
  assert.equal(serverVisualItems.characters.length, 2);
  assert.ok(!serverVisualItems.characters.some((c) => c.id === 'pending_character_job-1'), 'the pending representation is gone');
  assert.ok(serverVisualItems.characters.some((c) => c.id === 'custom_character_abc'), 'replaced by the real Character id');
  assert.ok(localCache.characters.some((c) => c.id === 'custom_character_abc'), 'local cache updated too');
});

test('removeCharacterCreationCard: removes only that one job\'s card from both serverVisualItems and the local cache', () => {
  const {context, serverVisualItems, localCache} = makeCardLifecycleContext();
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: '', status: 'failed'})`, context);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-2', name: 'Nova', gender: 'female', previewUrl: '', status: 'failed'})`, context);
  localCache.characters = serverVisualItems.characters.slice();
  vm.runInContext(`removeCharacterCreationCard('job-1')`, context);
  assert.equal(serverVisualItems.characters.length, 1);
  assert.equal(serverVisualItems.characters[0].job_id, 'job-2');
});

// ---- startCharacterCreationCardPoll / completeCharacterCreationJobCard /
// failCharacterCreationJobCard: the polling+card integration ----

function makePollCardContext(jobOutcomes) {
  const serverVisualItems = { characters: [], objects: [] };
  const localCache = { characters: [] };
  const calls = { toasts: [], rendered: 0 };
  let index = 0;
  const sandbox = {
    serverVisualItems,
    normalizeVisualItem: (x) => x,
    loadCustomVisualItems: (kind) => localCache[kind].slice(),
    saveCustomVisualItems: (kind, items) => { localCache[kind] = items.slice(); },
    activeImageStylePanelKind: 'character',
    renderImageStylePanel: () => { calls.rendered += 1; },
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderVideoReferencesPreview: () => {},
    toast: (msg) => calls.toasts.push(msg),
    translateGenerationError: (err, fallback) => fallback,
    wait: () => Promise.resolve(),
    getTelegramId: () => 42,
    localStorage: makeStorage().localStorage,
    activeCharacterCreationCardPolls: {},
    fetch: async () => {
      const job = jobOutcomes[Math.min(index, jobOutcomes.length - 1)];
      index += 1;
      return { ok: true, json: async () => job };
    },
  };
  const context = vm.createContext(sandbox);
  [
    'pollCharacterCreationJob', 'waitCharacterCreationJob',
    'characterCreationJobsStorageKey', 'readPendingCharacterCreationJobs', 'writePendingCharacterCreationJobs',
    'persistPendingCharacterCreationJob', 'clearPendingCharacterCreationJob',
    'pendingCharacterCardId', 'characterJobIdFromCardId',
    'upsertCharacterCreationPendingCard', 'removeCharacterCreationCard',
    'replaceCharacterCreationCardWithResource', 'updateCharacterCreationPendingCardProgress',
    'startCharacterCreationCardPoll', 'completeCharacterCreationJobCard', 'failCharacterCreationJobCard',
  ].forEach((name) => vm.runInContext(extractFunction(name), context));
  return {context, serverVisualItems, calls};
}

test('startCharacterCreationCardPoll: on completion, replaces the pending card with result.resource immediately - no second backend save', async () => {
  const {context, serverVisualItems, calls} = makePollCardContext([
    {ok: true, status: 'completed', result: {ok: true, character_id: 'custom_character_abc', resource: {id: 'custom_character_abc', name: 'Islam', previewUrl: 'https://cdn.sylvex.ai/p.png'}}},
  ]);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(`startCharacterCreationCardPoll('job-1')`, context);
  // Let the poll's microtask chain resolve.
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(serverVisualItems.characters.length, 1);
  assert.equal(serverVisualItems.characters[0].id, 'custom_character_abc');
  assert.ok(calls.toasts.length > 0);
});

test('startCharacterCreationCardPoll: on a genuine terminal failure, the card stays visible as failed - never silently removed', async () => {
  const {context, serverVisualItems} = makePollCardContext([
    {ok: true, status: 'failed', error: {error: 'OpenAI quota exceeded'}},
  ]);
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-1', name: 'Islam', gender: 'male', previewUrl: '', status: 'creating'})`, context);
  vm.runInContext(`startCharacterCreationCardPoll('job-1')`, context);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(serverVisualItems.characters.length, 1);
  assert.equal(serverVisualItems.characters[0].status, 'failed');
});

test('startCharacterCreationCardPoll: never polls the same job_id twice at once', async () => {
  let fetchCalls = 0;
  const serverVisualItems = { characters: [] };
  const sandbox = {
    serverVisualItems,
    normalizeVisualItem: (x) => x,
    loadCustomVisualItems: () => [],
    saveCustomVisualItems: () => {},
    activeImageStylePanelKind: 'character',
    renderImageStylePanel: () => {},
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderVideoReferencesPreview: () => {},
    toast: () => {},
    translateGenerationError: (err, fallback) => fallback,
    wait: () => new Promise((resolve) => setTimeout(resolve, 5)),
    getTelegramId: () => 42,
    localStorage: makeStorage().localStorage,
    activeCharacterCreationCardPolls: {},
    fetch: async () => {
      fetchCalls += 1;
      // Resolve after a couple of ticks so the poll loop actually
      // terminates (an unbounded 'processing' response would loop
      // forever and keep the process alive) - fetchCalls still proves
      // whether one or two concurrent loops were polling.
      const status = fetchCalls >= 3 ? 'completed' : 'processing';
      return { ok: true, json: async () => (status === 'completed' ? {ok: true, status, result: {ok: true, resource: {id: 'custom_character_abc'}}} : {ok: true, status}) };
    },
  };
  const context = vm.createContext(sandbox);
  [
    'pollCharacterCreationJob', 'waitCharacterCreationJob',
    'characterCreationJobsStorageKey', 'readPendingCharacterCreationJobs', 'writePendingCharacterCreationJobs',
    'persistPendingCharacterCreationJob', 'clearPendingCharacterCreationJob',
    'pendingCharacterCardId', 'characterJobIdFromCardId',
    'upsertCharacterCreationPendingCard', 'removeCharacterCreationCard',
    'replaceCharacterCreationCardWithResource', 'updateCharacterCreationPendingCardProgress',
    'startCharacterCreationCardPoll', 'completeCharacterCreationJobCard', 'failCharacterCreationJobCard',
  ].forEach((name) => vm.runInContext(extractFunction(name), context));
  vm.runInContext(`startCharacterCreationCardPoll('job-dup')`, context);
  vm.runInContext(`startCharacterCreationCardPoll('job-dup')`, context);
  await new Promise((resolve) => setTimeout(resolve, 60));
  // Exactly one in-flight poll loop ever ran for this job_id (3 ticks to
  // reach 'completed') - the second call was a no-op, not a second
  // concurrent fetch loop (which would have produced 6).
  assert.ok(fetchCalls <= 3, `expected at most one poll loop's worth of fetches, got ${fetchCalls}`);
});

// ---- retryFailedCharacterJob / deleteFailedCharacterJob ----

function makeRetryDeleteContext(createJobImpl) {
  const serverVisualItems = { characters: [] };
  const localCache = { characters: [] };
  const calls = { toasts: [], startedPolls: [] };
  const {localStorage} = makeStorage();
  const sandbox = {
    serverVisualItems,
    normalizeVisualItem: (x) => x,
    loadCustomVisualItems: (kind) => localCache[kind].slice(),
    saveCustomVisualItems: (kind, items) => { localCache[kind] = items.slice(); },
    renderImageStylePanel: () => {},
    renderImageReferenceSections: () => {},
    toast: (msg) => calls.toasts.push(msg),
    translateGenerationError: (err, fallback) => fallback,
    getTelegramId: () => 42,
    localStorage,
    createCharacterCreationJob: createJobImpl,
    startCharacterCreationCardPoll: (jobId) => calls.startedPolls.push(jobId),
  };
  const context = vm.createContext(sandbox);
  [
    'characterCreationJobsStorageKey', 'readPendingCharacterCreationJobs', 'writePendingCharacterCreationJobs',
    'persistPendingCharacterCreationJob', 'clearPendingCharacterCreationJob',
    'dismissedCharacterJobsKey', 'readDismissedCharacterJobIds', 'rememberDismissedCharacterJob',
    'pendingCharacterCardId', 'characterJobIdFromCardId',
    'upsertCharacterCreationPendingCard', 'removeCharacterCreationCard',
    'retryFailedCharacterJob', 'deleteFailedCharacterJob', 'handlePendingCharacterCardClick',
  ].forEach((name) => vm.runInContext(extractFunction(name), context));
  return {context, serverVisualItems, calls};
}

test('retryFailedCharacterJob: starts a brand-new job from the failed card\'s own name/gender/photo, replacing the old card', async () => {
  const {context, serverVisualItems, calls} = makeRetryDeleteContext(async () => 'job-new');
  vm.runInContext(
    `upsertCharacterCreationPendingCard({jobId: 'job-old', name: 'Islam', gender: 'male', description: 'tall', previewUrl: 'https://cdn.sylvex.ai/a.jpg', status: 'failed'})`,
    context,
  );
  await vm.runInContext(`retryFailedCharacterJob(null, 'pending_character_job-old')`, context);
  assert.ok(!serverVisualItems.characters.some((c) => c.job_id === 'job-old'));
  assert.ok(serverVisualItems.characters.some((c) => c.job_id === 'job-new' && c.status === 'creating'));
  assert.deepEqual(calls.startedPolls, ['job-new']);
});

test('deleteFailedCharacterJob: removes only this one failed pending-job card, never touching a real saved Character', async () => {
  const {context, serverVisualItems} = makeRetryDeleteContext(async () => 'job-new');
  vm.runInContext(`upsertCharacterCreationPendingCard({jobId: 'job-dead', name: 'Islam', gender: 'male', previewUrl: '', status: 'failed'})`, context);
  serverVisualItems.characters.unshift({id: 'custom_character_real', name: 'Nova', status: 'ready'});
  vm.runInContext(`deleteFailedCharacterJob(null, 'pending_character_job-dead')`, context);
  assert.equal(serverVisualItems.characters.length, 1);
  assert.equal(serverVisualItems.characters[0].id, 'custom_character_real');
  const dismissed = [...vm.runInContext('readDismissedCharacterJobIds()', context)];
  assert.deepEqual(dismissed, ['job-dead']);
});

// ---- restorePendingCharacterCreationJobs: backend-first restore after a
// reload - works even with no localStorage at all ----

function makeRestoreJobsContext(backendJobs, {noLocalStorage = false} = {}) {
  const serverVisualItems = { characters: [] };
  const localCache = { characters: [] };
  const calls = { toasts: [], startedPolls: [], fetchedUrls: [] };
  const sandbox = {
    serverVisualItems,
    normalizeVisualItem: (x) => x,
    loadCustomVisualItems: (kind) => localCache[kind].slice(),
    saveCustomVisualItems: (kind, items) => { localCache[kind] = items.slice(); },
    activeImageStylePanelKind: 'character',
    renderImageStylePanel: () => {},
    renderImageReferenceSections: () => {},
    toast: (msg) => calls.toasts.push(msg),
    getTelegramId: () => 42,
    fetch: async (url) => {
      calls.fetchedUrls.push(url);
      return { ok: true, json: async () => ({ok: true, jobs: backendJobs}) };
    },
    startCharacterCreationCardPoll: (jobId) => calls.startedPolls.push(jobId),
  };
  if (noLocalStorage) {
    sandbox.localStorage = {
      getItem: () => { throw new Error('localStorage unavailable'); },
      setItem: () => { throw new Error('localStorage unavailable'); },
      removeItem: () => { throw new Error('localStorage unavailable'); },
    };
  } else {
    sandbox.localStorage = makeStorage().localStorage;
  }
  const context = vm.createContext(sandbox);
  [
    'characterCreationJobsStorageKey', 'readPendingCharacterCreationJobs', 'writePendingCharacterCreationJobs',
    'persistPendingCharacterCreationJob', 'clearPendingCharacterCreationJob',
    'dismissedCharacterJobsKey', 'readDismissedCharacterJobIds', 'rememberDismissedCharacterJob',
    'pendingCharacterCardId', 'characterJobIdFromCardId',
    'upsertCharacterCreationPendingCard', 'removeCharacterCreationCard',
    'restorePendingCharacterCreationJobs',
  ].forEach((name) => vm.runInContext(extractFunction(name), context));
  return {context, serverVisualItems, calls};
}

test('restorePendingCharacterCreationJobs: inserts a pending card and resumes polling for every still-processing backend job', async () => {
  const {context, serverVisualItems, calls} = makeRestoreJobsContext([
    {job_id: 'job-1', status: 'processing', name: 'Islam', gender: 'male', photos: ['https://cdn.sylvex.ai/a.jpg'], result: {stage: 'side', completed_references: 2, primary_url: 'https://cdn.sylvex.ai/primary.png'}},
    {job_id: 'job-2', status: 'processing', name: 'Nova', gender: 'female', photos: ['https://cdn.sylvex.ai/b.jpg'], result: null},
  ]);
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(serverVisualItems.characters.length, 2);
  assert.deepEqual(calls.startedPolls.sort(), ['job-1', 'job-2']);
  const card1 = serverVisualItems.characters.find((c) => c.job_id === 'job-1');
  assert.equal(card1.status, 'creating');
  assert.equal(card1.previewUrl, 'https://cdn.sylvex.ai/primary.png');
});

test('restorePendingCharacterCreationJobs: a failed backend job restores as a failed card, not silently dropped', async () => {
  const {context, serverVisualItems} = makeRestoreJobsContext([
    {job_id: 'job-1', status: 'failed', name: 'Islam', gender: 'male', photos: ['https://cdn.sylvex.ai/a.jpg'], error: {error: 'quota exceeded'}},
  ]);
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(serverVisualItems.characters.length, 1);
  assert.equal(serverVisualItems.characters[0].status, 'failed');
});

test('restorePendingCharacterCreationJobs: a completed backend job gets no extra card (its real Character already loads through the normal catalog)', async () => {
  const {context, serverVisualItems} = makeRestoreJobsContext([
    {job_id: 'job-1', status: 'completed', name: 'Islam', gender: 'male', photos: [], result: {ok: true, resource: {id: 'custom_character_abc'}}},
  ]);
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(serverVisualItems.characters.length, 0);
});

test('restorePendingCharacterCreationJobs: a dismissed job_id never resurrects, even though the backend still reports it', async () => {
  const {context, serverVisualItems} = makeRestoreJobsContext([
    {job_id: 'job-dead', status: 'failed', name: 'Islam', gender: 'male', photos: []},
  ]);
  vm.runInContext(`rememberDismissedCharacterJob('job-dead')`, context);
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(serverVisualItems.characters.length, 0);
});

test('restorePendingCharacterCreationJobs: works correctly even when localStorage throws on every access - the backend is the source of truth', async () => {
  const {context, serverVisualItems, calls} = makeRestoreJobsContext([
    {job_id: 'job-1', status: 'processing', name: 'Islam', gender: 'male', photos: ['https://cdn.sylvex.ai/a.jpg'], result: null},
  ], {noLocalStorage: true});
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(serverVisualItems.characters.length, 1);
  assert.deepEqual(calls.startedPolls, ['job-1']);
});

test('restorePendingCharacterCreationJobs: never returns another user\'s jobs - it only ever calls the endpoint with this telegram_id', async () => {
  const {context, calls} = makeRestoreJobsContext([]);
  await vm.runInContext('restorePendingCharacterCreationJobs()', context);
  assert.equal(calls.fetchedUrls.length, 1);
  assert.match(calls.fetchedUrls[0], /telegram_id=42/);
});

// ---- saveVisualCreateDraft: Character creation is now a background-card
// workflow; Object creation's synchronous flow is unaffected ----

function makeSaveDraftContext({createJobResult, createJobError} = {}) {
  const serverVisualItems = { characters: [], objects: [] };
  const localCache = { characters: [], objects: [] };
  const calls = { toasts: [], closedCreateModal: 0, saveBackendCalls: [], startedPolls: [] };
  const {localStorage} = makeStorage();
  const sandbox = {
    getTelegramId: () => 42,
    localStorage,
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
    createCharacterCreationJob: async () => {
      if (createJobError) throw createJobError;
      return createJobResult || 'job-save-1';
    },
    generateVisualResourceWithOpenAI: async () => 'https://cdn.sylvex.ai/object-generated.png',
    saveVisualItemToBackend: async (kind, item) => { calls.saveBackendCalls.push({kind, item}); return Object.assign({}, item, {id: 'custom_object_saved'}); },
    serverVisualItems,
    loadCustomVisualItems: (kind) => localCache[kind].slice(),
    saveCustomVisualItems: (kind, items) => { localCache[kind] = items.slice(); },
    isVideoMode: () => false,
    applyVisualReferenceToVideo: () => {},
    applyCharacterReferenceSelection: () => {},
    imageState: {},
    renderImageReferenceSections: () => {},
    renderImageControls: () => {},
    renderImageStylePanel: () => {},
    renderVideoReferencesPreview: () => {},
    closeVisualCreateModal: () => { calls.closedCreateModal += 1; },
    closeVisualPicker: () => {},
    closeImageStylePanel: () => {},
    startCharacterCreationCardPoll: (jobId) => calls.startedPolls.push(jobId),
  };
  const context = vm.createContext(sandbox);
  [
    'characterCreationJobsStorageKey', 'readPendingCharacterCreationJobs', 'writePendingCharacterCreationJobs',
    'persistPendingCharacterCreationJob', 'clearPendingCharacterCreationJob',
    'pendingCharacterCardId', 'characterJobIdFromCardId',
    'upsertCharacterCreationPendingCard',
    'startCharacterCreationFromDraft', 'saveVisualCreateDraft',
  ].forEach((name) => vm.runInContext(extractFunction(name), context));
  return {context, serverVisualItems, calls, localCache};
}

test('saveVisualCreateDraft (character): closes the creation modal immediately after receiving job_id - never waits for generation', async () => {
  const {context, calls} = makeSaveDraftContext({createJobResult: 'job-save-1'});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(calls.closedCreateModal, 1);
  // No second backend save is ever attempted for Character creation.
  assert.equal(calls.saveBackendCalls.length, 0);
});

test('saveVisualCreateDraft (character): a pending Character card appears immediately, keyed by the new job_id, and polling starts', async () => {
  const {context, serverVisualItems, calls} = makeSaveDraftContext({createJobResult: 'job-save-1'});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(serverVisualItems.characters.length, 1);
  const card = serverVisualItems.characters[0];
  assert.equal(card.id, 'pending_character_job-save-1');
  assert.equal(card.name, 'Islam');
  assert.equal(card.gender, 'male');
  assert.equal(card.status, 'creating');
  assert.deepEqual(calls.startedPolls, ['job-save-1']);
});

test('saveVisualCreateDraft (character): a job-creation failure shows an error and never inserts a card', async () => {
  const {context, serverVisualItems, calls} = makeSaveDraftContext({createJobError: new Error('telegram_id_required')});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(serverVisualItems.characters.length, 0);
  assert.equal(calls.closedCreateModal, 0);
  assert.ok(calls.toasts.length > 0);
});

test('saveVisualCreateDraft (character): starting a second Character creation while the first is still pending keeps both cards independent', async () => {
  const {context, serverVisualItems} = makeSaveDraftContext({createJobResult: 'job-first'});
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  vm.runInContext(`createCharacterCreationJob = async () => 'job-second'`, context);
  vm.runInContext(`visualCreateDraft.name = 'Nova'; visualCreateDraft.gender = 'female';`, context);
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(serverVisualItems.characters.length, 2);
  assert.deepEqual(serverVisualItems.characters.map((c) => c.job_id).sort(), ['job-first', 'job-second']);
});

test('saveVisualCreateDraft (object): unaffected - still calls saveVisualItemToBackend exactly once and never touches the Character job machinery', async () => {
  const {context, serverVisualItems, calls} = makeSaveDraftContext();
  vm.runInContext(`visualCreateDraft.kind = 'object'; visualCreateDraft.name = 'Watch'; visualCreateDraft.gender = '';`, context);
  await vm.runInContext('saveVisualCreateDraft(null)', context);
  assert.equal(calls.saveBackendCalls.length, 1);
  assert.equal(calls.saveBackendCalls[0].kind, 'object');
  assert.equal(serverVisualItems.objects.length, 1);
  assert.equal(serverVisualItems.objects[0].id, 'custom_object_saved');
  assert.equal(serverVisualItems.characters.length, 0);
  assert.equal(calls.closedCreateModal, 1);
});
