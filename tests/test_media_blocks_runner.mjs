// Media blocks on the user side (js/media-blocks.js, the same file as the
// website's): a catalog item that carries `media_block` opens the block
// window instead of the app's own flow, and the block runs through
// /api/public/media-blocks/{id}/generate and the ordinary job polling.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../webapp/' + path, import.meta.url), 'utf8');
const cabinet = read('js/cabinet.js');
const index = read('index.html');
const runner = read('js/media-blocks.js');

function load() {
  const context = { document: { documentElement: { lang: 'ru' } }, fetch: () => Promise.reject(new Error('offline')) };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(runner, context);
  return context.SylvexMediaBlocks;
}

test('the module and its stylesheet are loaded before the Mini App code', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/media-blocks\.css\?v=media-c-20261029" \/>/);
  assert.match(index, /<script src="js\/media-blocks\.js\?v=media-fix-20261030"><\/script>\n<script src="js\/cabinet\.js/);
});

test('catalog items with a block open the block window', () => {
  assert.match(cabinet, /if \(template && template\.media_block\) \{ openMediaBlock\(template\.media_block\); return; \}/);
  assert.match(cabinet, /if \(item\.mediaBlock\) \{ openMediaBlock\(item\.mediaBlock\); return; \}/);
  assert.match(cabinet, /mediaBlock:item\.media_block \|\| null/);
  // Admin-built tools follow the built-in photo tools.
  assert.match(cabinet, /window\.SylvexMediaBlocks\.list\('ai_tools'\)/);
  // The home composer panel keeps to the plain catalog items.
  assert.match(cabinet, /!template\.is_kling_effect && !template\.media_block/);
  assert.match(cabinet, /item\.source === 'prostudio_style' \|\| item\.mediaBlock/);
});

test('a block runs through its own endpoint and the ordinary job polling', () => {
  assert.match(runner, /'\/api\/public\/media-blocks\/' \+ encodeURIComponent\(current\.block\.id\) \+ '\/generate'/);
  assert.match(runner, /JSON\.stringify\(\{ uploads: uploads \}\)/);
  assert.match(runner, /'\/api\/public\/prostudio\/job\/' \+ encodeURIComponent\(jobId\)/);
  assert.match(runner, /'\/api\/public\/prostudio\/upload-media\?kind=' \+ kind/);
  // The client never sends a prompt or a model: the server builds them.
  assert.doesNotMatch(runner.slice(runner.indexOf('function generate()')), /prompt:|model:/);
});

test('helpers: the block of an item and the result of a job', () => {
  const api = load();
  assert.equal(api.of({ id: 'x' }), null);
  assert.equal(api.of({ media_block: { id: 4, name: 'Neon' } }).name, 'Neon');
  assert.equal(api._resultUrl({ video_url: 'v.mp4', images: ['a.png'] }), 'v.mp4');
  assert.equal(api._resultUrl({ images: [{ url: 'a.png' }] }), 'a.png');
  assert.equal(api._resultUrl({ image_url: 'b.png' }), 'b.png');
  assert.equal(api._resultUrl(null), '');
});

test('without the network the block list is empty, not an error', async () => {
  assert.deepEqual(Array.from(await load().list('ai_tools')), []);
});

// The Mini App's own Media page (js/media.js + js/media-page.js, loaded by
// cabinet.js) once had no block support: an admin's photo block opened as a
// plain catalog photo, which always runs on GPT Image 2. It now carries the
// block and opens it in the block window with the block's own model.
test("the Mini App's Media page opens a block instead of the GPT Image catalog flow", () => {
  const media = read('js/media.js');
  const page = read('js/media-page.js');
  const site = (path) => { try { return readFileSync(new URL('../../sylvex-website/' + path, import.meta.url), 'utf8'); } catch { return null; } };
  for (const kind of ['video_styles', 'image_styles', 'photo_references']) {
    assert.match(media, new RegExp("push\\(item\\('" + kind + "'[^\\n]*block: [a-z]+\\.media_block"));
  }
  assert.match(media, /if \(entry && entry\.block\) return 'media_block';/);
  assert.match(page, /if \(entry\.block\) \{ openBlock\(entry\.block\); return; \}/);
  assert.match(page, /bridge && typeof bridge\.openBlock === 'function'\) \{ bridge\.openBlock\(block\); return; \}/);
  assert.match(cabinet, /openBlock:block=>openMediaBlock\(block\),/);
  assert.match(cabinet, /load\('js\/media\.js\?v=media-fix-20261030'\)\.then\(\(\)=>load\('js\/media-page\.js\?v=media-fix-20261030'\)\)/);
  // One file for both apps.
  if (site('js/media.js')) {
    assert.equal(media, site('js/media.js'));
    assert.equal(page, site('js/media-page.js'));
  }
});

test('an item of the shared data layer keeps its block', () => {
  const context = { window: {} };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read('js/media.js'), context);
  const M = context.SYLVEX_MEDIA;
  assert.equal(M.generationKind({ category: 'photo_references', sourceId: 'media_block_7', block: { id: 7, model: 'seedream_4_5' } }), 'media_block');
  assert.equal(M.generationKind({ category: 'photo_references', sourceId: 'quick_1' }), 'image');
});
