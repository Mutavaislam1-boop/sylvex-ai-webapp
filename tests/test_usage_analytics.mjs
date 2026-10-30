// Usage analytics in the Mini Apps (js/analytics.js, the same file as the
// website's): ids and counts only, batched, never a prompt or a file.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../webapp/' + path, import.meta.url), 'utf8');

function load() {
  const sent = [];
  const store = {};
  const context = {
    fetch: (url, init) => { sent.push({ url, body: JSON.parse(init.body) }); return Promise.resolve({}); },
    localStorage: { getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = v; } },
    setTimeout: () => 1, clearTimeout: () => {}, Date,
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read('js/analytics.js'), context);
  return { api: context.SylvexAnalytics, sent };
}

test('events carry ids only and are sent in one batch', () => {
  const { api, sent } = load();
  api.configure({ surface: 'telegram_miniapp' });
  api.track('section_open', { section: 'media' });
  api.track('section_open', { section: 'media' }); // the same section twice counts once
  api.track('item_select', { item: 'Photo 09', kind: 'style', prompt: 'my private prompt' });
  api.track('keylogger', { item: 'x' });
  api.flush();
  assert.equal(sent.length, 1);
  const { url, body } = sent[0];
  assert.equal(url, '/api/public/analytics/events');
  assert.equal(body.surface, 'telegram_miniapp');
  assert.match(body.visitor, /^v[a-z0-9]+$/);
  assert.deepEqual(body.events.map((e) => [e.event, e.section, e.item, e.kind]),
    [['section_open', 'media', '', ''], ['item_select', 'media', 'photo_09', 'style']]);
  assert.ok(!JSON.stringify(body).includes('private prompt'));
});

test('time spent in a section is sent when another opens', () => {
  const { api, sent } = load();
  api.track('section_open', { section: 'home' });
  api.track('section_open', { section: 'shop' });
  api.flush();
  const events = sent[0].body.events.map((e) => e.event);
  assert.deepEqual(events, ['section_open', 'section_leave', 'section_open']);
});

test('the Mini App loads it and reports sections, tools, references, models and downloads', () => {
  const index = read('index.html');
  const cabinet = read('js/cabinet.js');
  assert.match(index, /<script src="js\/analytics\.js\?v=admin-d-20261030"><\/script>\n<script src="js\/ui\.js/);
  assert.match(read('js/ui.js'), /SylvexAnalytics\.track\('section_open'/);
  for (const event of ['model_select', 'item_select', 'download']) {
    assert.ok(cabinet.includes(`globalThis.SylvexAnalytics?.track('${event}'`), event);
  }
  assert.ok(cabinet.includes("globalThis.SylvexAnalytics?.track(kind ? 'tool_open' : 'section_open'"));
  assert.match(cabinet, /section: 'grid'/);
  assert.match(cabinet, /section: 'edit'/);
});

test('a model turned off by an admin is shown but cannot be chosen', () => {
  const cabinet = read('js/cabinet.js');
  assert.match(cabinet, /fetch\('\/api\/public\/models\/status'/);
  assert.match(cabinet, /if \(isModelTurnedOff\(value\)\) \{ toast\('Эта модель временно недоступна'\); return; \}/);
  assert.match(cabinet, /\(off \? ' is-unavailable' : ''\)/);
});
