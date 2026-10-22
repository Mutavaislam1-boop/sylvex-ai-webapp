// ThoughtLine: the generation progress line of Pro Studio (not Grid or Edit).
// It ticks the stages the backend confirmed (job.progress.stages) one after
// another, ends a finished job with all five stages ticked, and holds the
// result until the line has settled. It replaces the old timed percentages.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');
const cabinet = read('webapp/js/cabinet.js');
const css = read('webapp/css/cabinet.css');
// Values made inside the vm context have that context's prototypes.
const plain = (value) => JSON.parse(JSON.stringify(value));

// The shared module, on a fake clock: run(ms) advances it and fires timers.
function core() {
  const start = cabinet.indexOf('// ХОД ГЕНЕРАЦИИ: ThoughtLine');
  const end = cabinet.indexOf('function syncEditWorkspaceChain(root) {', start);
  let now = 0;
  const timers = [];
  const sandbox = {
    window: {SylvexThoughtLine: {mount: () => ({update() {}, unmount() {}})}},
    EDIT_PIXEL_BASE: '',
    document: {querySelectorAll: () => [], createElement: () => ({className: '', textContent: ''}), head: {appendChild() {}}},
    setTimeout: (fn, ms) => { timers.push({fn, at: now + (ms || 0)}); return timers.length; },
    Date: {now: () => now},
    Promise, Number, Object, String, Map, Set, Math, Infinity,
  };
  sandbox.run = (ms) => {
    const until = now + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const next = timers[0];
      if (!next || next.at > until) break;
      timers.shift();
      now = next.at;
      next.fn();
    }
    now = until;
  };
  vm.createContext(sandbox);
  vm.runInContext(cabinet.slice(start, end) + '\nthis.generationThoughtJobs = generationThoughtJobs;\nthis.generationThoughtSettleListeners = generationThoughtSettleListeners;', sandbox);
  return sandbox;
}
const steps = (s, thought) => plain(s.generationThoughtProps(thought).steps);
// Show every confirmed stage at once (what the paced ticks end up at).
const caughtUp = (s, thought) => Object.assign(thought, {shown: s.generationThoughtTarget(thought)});

test('ThoughtLine.jsx / .css are the provided files, unmodified, built into the committed bundle', () => {
  assert.equal(sha256('thought_line/src/ThoughtLine.jsx'), 'd06f30a62cb65fb4fc0bc4868665e6b1f0b4458c092616116fdaf69c7b94532a');
  assert.equal(sha256('thought_line/src/ThoughtLine.css'), 'fcf125579ead2806c69ecd109c88f14007eaf5fb54ffe46c867482d03add2ef7');
  assert.ok(existsSync(new URL('../webapp/js/vendor/thought-line/thought-line.js', import.meta.url)));
  assert.ok(existsSync(new URL('../webapp/js/vendor/thought-line/thought-line.css', import.meta.url)));
  const main = read('thought_line/src/main.jsx');
  for (const prop of ["glyph: 'sparkle'", 'fontSize: 16', 'breathPeriod: 1.6', 'breathDepth: 0.45', 'settleDuration: 350', 'settleBlur: 2', 'collapsible: true', 'collapseOnSettle: true', 'showTimer: true'])
    assert.ok(main.includes(prop), prop);
  assert.ok(main.includes("color: 'var(--sx-thought-color, #a1a1aa)'"), 'a concrete colour, so the shimmering label stays visible');
  assert.ok(main.includes('const end = finishedAt || now;'), 'the timer stops at the real end while the last ticks play');
  const host = read('thought_line/src/host.css');
  assert.ok(host.includes('.sx-thought .thought-line__step[data-done] .thought-line__mark {\n  color: var(--sx-thought-success, #22c55e);'), 'green ticks');
  assert.ok(host.includes('  border-top-color: transparent;\n  border-radius: 50%;\n  background: none;\n  opacity: 0.8;\n  animation: sx-thought-spin 0.8s linear infinite;'), 'a spinning ring until the tick');
});

test('confirmed stages are ticked; the next stage waits with a pulse', () => {
  const s = core();
  const thought = s.createGenerationThought('image');
  assert.deepEqual(steps(s, thought), ['Задание получено SYLVEX']);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 100, sent: 101, accepted: 102}, server_time: 102});
  caughtUp(s, thought);
  assert.deepEqual(steps(s, thought), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Запрос принят на генерацию', 'ИИ обрабатывает изображение']);
  assert.equal(s.generationThoughtProps(thought).working, true);
});

test('ticks come one by one, 1s apart; the finished line stays open 1s, then the result shows', () => {
  const s = core();
  const settled = [];
  s.generationThoughtSettleListeners.add((key) => settled.push(key));
  const thought = s.createGenerationThought('image');
  s.bindGenerationThought('job1', 'thought_a', thought);
  // A provider that answered before any intermediate status was polled.
  s.noteGenerationJob('job1', {status: 'completed', progress: {stages: {received: 1, sent: 1.2, ready: 4}, server_time: 4}});
  s.run(0);
  const seen = [];
  for (let t = 0; t <= 6000; t += 500) {
    const props = s.generationThoughtProps(thought);
    seen.push([t, thought.shown, props.working, props.collapseOnSettle, s.generationThoughtDone(thought), settled.length]);
    s.run(500);
  }
  assert.deepEqual(plain(seen.filter(([t]) => t % 1000 === 0)), [
    [0, 1, true, false, false, 0], [1000, 2, true, false, false, 0], [2000, 3, true, false, false, 0], [3000, 4, true, false, false, 0],
    // «Готово к скачиванию» ticked at 4s: the line settles open…
    [4000, 5, false, false, false, 0],
    // …and folds 1s later, when the result is released.
    [5000, 5, false, true, true, 1], [6000, 5, false, true, true, 1],
  ]);
  const done = s.generationThoughtProps(thought);
  assert.deepEqual(plain(done.steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Запрос принят на генерацию', 'ИИ обрабатывает изображение', 'Готово к скачиванию']);
  assert.equal(done.doneLabel, 'Готово к скачиванию');
  assert.ok(s.generationThoughtSettled(thought));
  assert.deepEqual(plain(settled), ['thought_a'], 'the held result is released once, after the settle');
});

test('the timer runs from Generate to the real end and does not include the catch-up ticks or the hold', () => {
  const s = core();
  s.run(1000);
  const thought = s.createGenerationThought('video');
  s.run(500);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 15.8, ready: 16}, server_time: 16});
  const props = s.generationThoughtProps(thought);
  assert.equal(props.startedAt, 1000, 'the press of Generate, before the server received it');
  assert.equal(props.finishedAt, 1500);
});

test('a failed job ticks the stages it reached, then shows the error 2s before the line folds', () => {
  const s = core();
  const thought = s.createGenerationThought('music');
  s.bindGenerationThought('job2', 'thought_b', thought);
  s.noteGenerationJob('job2', {status: 'failed', progress: {stages: {received: 10, sent: 11, failed: 14}, server_time: 14}});
  s.run(500);
  assert.equal(s.generationThoughtProps(thought).working, true, 'still ticking the reached stages');
  s.run(1000);
  const props = s.generationThoughtProps(thought);
  assert.equal(props.failed, true);
  assert.equal(props.working, false);
  assert.equal(props.collapseOnSettle, false, 'the error stays open');
  assert.equal(props.doneLabel, 'Ошибка генерации');
  assert.deepEqual(plain(props.steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Генерация не выполнена']);
  // Settled with the error at 1s: open until 3s.
  s.run(1400);
  assert.equal(s.generationThoughtProps(thought).collapseOnSettle, false, 'still open just before 2s');
  s.run(200);
  assert.equal(s.generationThoughtProps(thought).collapseOnSettle, true, 'folded after 2s');
  s.finishGenerationThought(thought, false);
  assert.equal(s.generationThoughtProps(thought).failed, true, 'a later result never turns the error into success');
});

test('a line saved before the paced ticks is complete when restored', () => {
  const s = core();
  const saved = {kind: 'image', stages: {received: 1, sent: 2, ready: 5}, outcome: 'ready', startedAt: 1, finishedAt: 5};
  assert.ok(s.generationThoughtSettled(saved));
  assert.ok(s.generationThoughtDone(saved));
  assert.equal(s.generationThoughtProps(saved).working, false);
});

test('stage names follow the generation type and the interface language', () => {
  const s = core();
  const names = (kind) => {
    const thought = caughtUp(s, s.applyGenerationThoughtProgress(s.createGenerationThought(kind), {stages: {received: 1, sent: 2, accepted: 3, processing: 4}, server_time: 4}));
    const props = s.generationThoughtProps(thought);
    return plain([props.label, props.steps[3], props.steps[4]]);
  };
  assert.deepEqual(names('image'), ['Генерация изображения…', 'ИИ обрабатывает изображение', 'Готово к скачиванию']);
  assert.deepEqual(names('video'), ['Генерация видео…', 'ИИ создаёт видео', 'Готово к скачиванию']);
  assert.deepEqual(names('music'), ['Генерация музыки…', 'ИИ создаёт музыку', 'Готово к скачиванию']);
  assert.deepEqual(names('voice'), ['Генерация озвучки…', 'ИИ озвучивает текст', 'Готово к скачиванию']);
  assert.deepEqual(names('text'), ['Думает…', 'Завершает ответ', 'Ответ готов']);
  const text = caughtUp(s, s.applyGenerationThoughtProgress(s.createGenerationThought('text'), {stages: {received: 1, sent: 2, accepted: 3, processing: 4}, server_time: 4}));
  assert.deepEqual(plain(s.generationThoughtProps(text).steps), ['Анализирует запрос', 'Обдумывает ответ', 'Формирует текст', 'Завершает ответ', 'Ответ готов']);
  s.localStorage = {getItem: () => 'en'};
  assert.deepEqual(names('image'), ['Generating image…', 'AI is processing the image', 'Ready to download']);
});

test('server times are moved onto the device clock with the response server_time', () => {
  const s = core();
  s.run(100000);
  const thought = s.createGenerationThought('image');
  s.applyGenerationThoughtProgress(thought, {stages: {received: 1000}, server_time: 1005});
  assert.equal(thought.stages.received, 95000, 'received 5s before the response, on this clock');
});

test('Pro Studio only: Grid and Edit carry no line', () => {
  for (const name of ['gridThoughtKey', 'editThoughtKey', 'studio-grid-thought', 'edit-chain-thought', 'gridNodeOutputPreview', 'node.thought', 'chainResult.thought'])
    assert.ok(!cabinet.includes(name), name);
  assert.ok(cabinet.includes("transientErrors=0;if(onStatus)onStatus(job.status||'running');"), 'the Grid poller is back to its own job');
  assert.ok(!css.includes('studio-grid-thought') && !css.includes('edit-chain-thought'));
});

test('Pro Studio starts the line at once, holds the result until it settles and keeps it in view', () => {
  assert.ok(cabinet.includes("if(typeof window.requestIdleCallback==='function')window.requestIdleCallback(warm,{timeout:3000});else setTimeout(warm,1200);"), 'bundle loaded before the first Generate');
  assert.ok(cabinet.includes("    if (m.isError || !generationThoughtDone(m.thought)) return '<div class=\"msg ai generation-loading-msg\"><div class=\"ai-avatar\">S</div>' + slot + '</div>';"), 'held result; a failure is the line alone');
  assert.ok(cabinet.includes('if(area&&grew>0&&area.scrollHeight-area.scrollTop-area.clientHeight-grew<96)area.scrollTop=area.scrollHeight;'));
  assert.ok(cabinet.includes('    if (placeholder && placeholder.thoughtKey) bindGenerationThought(jobId, placeholder.thoughtKey, placeholder.thought);\n    noteGenerationJob(jobId, job);'));
  assert.ok(cabinet.includes("el.innerHTML = chatMessages.map((m, i) => withChatThought(m, messageHtml(m, i))).join('');"));
});

test('only the latest failure stays in the workspace', () => {
  const start = cabinet.indexOf('  function dismissStaleFailedGenerations() {');
  const body = cabinet.slice(start, cabinet.indexOf('\n  }\n', start) + 4);
  const sandbox = {chatMessages: [{role: 'ai', isError: true}, {role: 'user', text: 'x'}, {role: 'ai', text: 'ok'}, {role: 'ai', isError: true}]};
  vm.createContext(sandbox);
  vm.runInContext(body + '\ndismissStaleFailedGenerations();', sandbox);
  assert.deepEqual(plain(sandbox.chatMessages.map((m) => !!m.dismissed)), [true, false, false, false]);
  assert.ok(cabinet.includes("    if (m && m.dismissed) return '';"));
  assert.ok(cabinet.includes('    adoptReplacedGenerationThoughts();\n    dismissStaleFailedGenerations();'));
});

test('the timed percentages, rotating captions and their styles are gone', () => {
  for (const name of ['GENERATION_PROGRESS_STEPS', 'GENERATION_STAGE_MESSAGES', 'createGenerationProgress', 'nextGenerationProgress', 'renderGenerationLoadingCard',
    'renderTextLoadingDots', 'patchActiveGenerationDom', 'progressTimer', 'updateGenerationLoadingProgress'])
    assert.ok(!cabinet.includes(name), name);
  for (const name of ['generation-loading-card', 'generation-loading-percent', 'generation-loading-progress', 'text-loading-dots', 'generationBorderSweep'])
    assert.ok(!css.includes(name), name);
});

test('notices: green bottom glow for a success, red for an error; nothing else changes', () => {
  const ui = read('webapp/js/ui.js');
  const success = eval(ui.match(/const NOTICE_SUCCESS = (\/.*\/i);/)[1]), failure = eval(ui.match(/const NOTICE_FAILURE = (\/.*\/i);/)[1]);
  const tone = (text) => (success.test(text) && !failure.test(text) ? 'success' : 'error');
  for (const text of ['Генерация завершена', 'Фото добавлено', 'Трек готов в проигрывателе', 'Видео загружено', 'Голос создан и выбран'])
    assert.equal(tone(text), 'success', text);
  for (const text of ['Ошибка генерации', 'Не удалось подготовить фото на этом устройстве.', 'Недостаточно токенов', 'Сначала дождитесь завершения текущей генерации',
    'Поделиться можно только завершённой генерацией', 'Генерация не завершена', 'This new project is already empty', 'Provider unavailable'])
    assert.equal(tone(text), 'error', text);
  assert.ok(ui.includes("const NOTICE_GLOW = { success: '#51f524', error: '#ef4444' };"));
  assert.ok(ui.includes('loadSwipeToast().then((api) => api.show(text, { fuseColor })).catch(() => fallbackToast(text));'));
  // The SwipeToast settings themselves are untouched; only the fuse colour varies.
  assert.ok(read('swipe_toast/src/main.jsx').includes("  fuseColor: '#51f524',"));
});
