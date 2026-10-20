// ThoughtLine: one generation progress line for Pro Studio, Grid and Edit.
// It lists only the stages the backend confirmed (job.progress.stages) and
// replaces the old timed percentages and rotating captions.
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

function core() {
  const start = cabinet.indexOf('// ХОД ГЕНЕРАЦИИ: ThoughtLine');
  const end = cabinet.indexOf('function syncEditWorkspaceChain(root) {', start);
  const shown = [];
  const sandbox = {
    window: {}, EDIT_PIXEL_BASE: '', editWorkspaceState: {sessionId: 's1'}, shown,
    document: {querySelectorAll: () => [], createElement: () => ({className: '', textContent: ''}), head: {appendChild() {}}},
    Promise, Date, Number, Object, String, Map, Math,
  };
  vm.createContext(sandbox);
  vm.runInContext(cabinet.slice(start, end) + '\nshowGenerationThought = (key, thought) => shown.push([key, generationThoughtProps(thought)]);\nthis.generationThoughtJobs = generationThoughtJobs;', sandbox);
  return sandbox;
}

test('ThoughtLine.jsx / .css are the provided files, unmodified, built into the committed bundle', () => {
  assert.equal(sha256('thought_line/src/ThoughtLine.jsx'), 'd06f30a62cb65fb4fc0bc4868665e6b1f0b4458c092616116fdaf69c7b94532a');
  assert.equal(sha256('thought_line/src/ThoughtLine.css'), 'fcf125579ead2806c69ecd109c88f14007eaf5fb54ffe46c867482d03add2ef7');
  assert.ok(existsSync(new URL('../webapp/js/vendor/thought-line/thought-line.js', import.meta.url)));
  assert.ok(existsSync(new URL('../webapp/js/vendor/thought-line/thought-line.css', import.meta.url)));
  const main = read('thought_line/src/main.jsx');
  for (const prop of ["glyph: 'sparkle'", 'fontSize: 16', 'breathPeriod: 1.6', 'breathDepth: 0.45', 'settleDuration: 350', 'settleBlur: 2', 'collapsible: true', 'collapseOnSettle: true', 'showTimer: true'])
    assert.ok(main.includes(prop), prop);
  assert.ok(main.includes("color: 'var(--sx-thought-color, #a1a1aa)'"), 'a concrete colour, so the shimmering label stays visible');
});

test('only confirmed stages are ticked; the next stage waits with a pulse', () => {
  const s = core();
  const thought = s.createGenerationThought('image');
  const steps = () => plain(s.generationThoughtProps(thought).steps);
  assert.deepEqual(steps(), ['Задание получено SYLVEX']);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 100}, server_time: 100});
  assert.deepEqual(steps(), ['Задание получено SYLVEX', 'Запрос отправлен ИИ']);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 100, sent: 101, accepted: 102}, server_time: 102});
  assert.deepEqual(steps(), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Запрос принят на генерацию', 'ИИ обрабатывает изображение']);
  assert.equal(s.generationThoughtProps(thought).working, true);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 100, sent: 101, accepted: 102, processing: 103, ready: 109}, server_time: 109});
  const done = s.generationThoughtProps(thought);
  assert.deepEqual(plain(done.steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Запрос принят на генерацию', 'ИИ обрабатывает изображение', 'Готово к скачиванию']);
  assert.equal(done.working, false);
  assert.equal(done.doneLabel, 'Готово к скачиванию');
  assert.equal((done.finishedAt - done.startedAt) / 1000, 9, 'the timer is the job time from received to ready');
});

test('a provider without intermediate statuses never shows them as done', () => {
  const s = core();
  const thought = s.createGenerationThought('video');
  s.applyGenerationThoughtProgress(thought, {stages: {received: 10, sent: 11}, server_time: 11});
  assert.deepEqual(plain(s.generationThoughtProps(thought).steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Запрос принят на генерацию']);
  s.applyGenerationThoughtProgress(thought, {stages: {received: 10, sent: 11, ready: 30}, server_time: 30});
  assert.deepEqual(plain(s.generationThoughtProps(thought).steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Готово к скачиванию']);
});

test('a failed job ends the line as an error instead of ready', () => {
  const s = core();
  const thought = s.createGenerationThought('music');
  s.applyGenerationThoughtProgress(thought, {stages: {received: 10, sent: 11, failed: 14}, server_time: 14});
  const props = s.generationThoughtProps(thought);
  assert.equal(props.failed, true);
  assert.equal(props.working, false);
  assert.equal(props.doneLabel, 'Ошибка генерации');
  assert.deepEqual(plain(props.steps), ['Задание получено SYLVEX', 'Запрос отправлен ИИ', 'Генерация не выполнена']);
  // A result that arrives later can never turn the error into success.
  s.finishGenerationThought(thought, false);
  assert.equal(s.generationThoughtProps(thought).failed, true);
});

test('another chosen interface language shows the English stage names', () => {
  const s = core();
  s.localStorage = {getItem: () => 'en'};
  const thought = s.createGenerationThought('image');
  s.applyGenerationThoughtProgress(thought, {stages: {received: 1, sent: 2}, server_time: 2});
  const props = s.generationThoughtProps(thought);
  assert.deepEqual(plain([props.label, ...props.steps]), ['Generating image…', 'Task received by SYLVEX', 'Request sent to the AI', 'Request accepted for generation']);
  s.localStorage = {getItem: () => 'ru'};
  assert.equal(s.generationThoughtProps(thought).label, 'Генерация изображения…');
});

test('stage names follow the generation type', () => {
  const s = core();
  const names = (kind) => {
    const thought = s.createGenerationThought(kind);
    s.applyGenerationThoughtProgress(thought, {stages: {received: 1, sent: 2, accepted: 3, processing: 4}, server_time: 4});
    const props = s.generationThoughtProps(thought);
    return plain([props.label, props.steps[3], props.steps[4]]);
  };
  assert.deepEqual(names('image'), ['Генерация изображения…', 'ИИ обрабатывает изображение', 'Готово к скачиванию']);
  assert.deepEqual(names('video'), ['Генерация видео…', 'ИИ создаёт видео', 'Готово к скачиванию']);
  assert.deepEqual(names('music'), ['Генерация музыки…', 'ИИ создаёт музыку', 'Готово к скачиванию']);
  assert.deepEqual(names('voice'), ['Генерация озвучки…', 'ИИ озвучивает текст', 'Готово к скачиванию']);
  assert.deepEqual(names('text'), ['Генерация текста…', 'ИИ формирует ответ', 'Ответ готов']);
  assert.equal(s.generationThoughtKind('montage'), 'video');
  assert.equal(s.generationThoughtKind('audio'), 'music');
});

test('server times are moved onto the device clock with the response server_time', () => {
  const s = core();
  const thought = s.createGenerationThought('image');
  const before = Date.now();
  s.applyGenerationThoughtProgress(thought, {stages: {received: 1000}, server_time: 1005});
  const received = thought.stages.received;
  assert.ok(received >= before - 5000 - 50 && received <= Date.now() - 5000 + 50, 'received 5s before the response, on this clock');
});

test('every line bound to a job follows its polls and the binding ends with the job', () => {
  const s = core();
  const chat = s.createGenerationThought('image'), edit = s.createGenerationThought('image');
  s.bindGenerationThought('job1', 'thought_a', chat);
  s.bindGenerationThought('job1', 'edit_s1_n1', edit);
  s.noteGenerationJob('job1', {status: 'provider_processing', progress: {stages: {received: 1, sent: 2, accepted: 3}, server_time: 3}});
  assert.deepEqual(plain(s.shown.map(([key]) => key)), ['thought_a', 'edit_s1_n1']);
  assert.equal(chat.stages.accepted !== undefined && edit.stages.accepted !== undefined, true);
  s.noteGenerationJob('job1', {status: 'failed', progress: {stages: {received: 1, sent: 2, accepted: 3, failed: 5}, server_time: 5}});
  assert.equal(chat.outcome, 'failed');
  assert.equal(s.generationThoughtJobs.has('job1'), false);
});

test('the pollers, chat, Grid and Edit feed and show the same line', () => {
  assert.ok(cabinet.includes('    if (placeholder && placeholder.thoughtKey) bindGenerationThought(jobId, placeholder.thoughtKey, placeholder.thought);\n    noteGenerationJob(jobId, job);'));
  assert.ok(cabinet.includes("transientErrors=0;noteGenerationJob(jobId,job);if(onStatus)onStatus(job.status||'running');"));
  assert.ok(cabinet.includes("+ generationThoughtSlot(m.thoughtKey, 'generation-thought')"));
  assert.ok(cabinet.includes("el.innerHTML = chatMessages.map((m, i) => withChatThought(m, messageHtml(m, i))).join('');"));
  assert.ok(cabinet.includes("if(thought&&status==='RUNNING')return thought;"));
  assert.ok(cabinet.includes("node.thought=createGenerationThought(node.type);"));
  assert.ok(cabinet.includes("generationThoughtSlot(editThoughtKey(node),'edit-chain-thought')"));
  assert.ok(cabinet.includes('thought: finishGenerationThought(applyGenerationThoughtProgress(thoughtFields.thought, result.progress)),'));
});

test('the timed percentages, rotating captions and their styles are gone', () => {
  for (const name of ['GENERATION_PROGRESS_STEPS', 'GENERATION_STAGE_MESSAGES', 'createGenerationProgress', 'nextGenerationProgress', 'renderGenerationLoadingCard',
    'renderTextLoadingDots', 'patchActiveGenerationDom', 'progressTimer', 'updateGenerationLoadingProgress'])
    assert.ok(!cabinet.includes(name), name);
  for (const name of ['generation-loading-card', 'generation-loading-percent', 'generation-loading-progress', 'text-loading-dots', 'generationBorderSweep'])
    assert.ok(!css.includes(name), name);
  assert.ok(css.includes('.generation-thought{display:flex;align-items:center;min-height:32px;max-width:100%;padding:4px 2px;--sx-thought-color:var(--st-text,#f3f3f3)}'));
});
