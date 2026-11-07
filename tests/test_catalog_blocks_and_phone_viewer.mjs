// Run with: node --test tests/test_catalog_blocks_and_phone_viewer.mjs
//
// The references built in the admin Media constructor come from the one
// catalog (video templates, quick image catalog) everywhere, the Home
// catalog panel included, with the same cards. On Home such a reference is
// picked into the composer as every other one and runs its own generation
// (its model, prompt and fields) with the user's photo; elsewhere it opens a
// window that is the window of every catalog reference. On phones every
// reference viewer is one column: a small picture on top, details under it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const blocksJs = readFileSync(new URL('../webapp/js/media-blocks.js', import.meta.url), 'utf8');
const blocksCss = readFileSync(new URL('../webapp/css/media-blocks.css', import.meta.url), 'utf8');
const mediaCss = readFileSync(new URL('../webapp/css/media.css', import.meta.url), 'utf8');

test('Home: an admin reference of the one catalog is picked into the composer and runs its own generation', () => {
  assert.doesNotMatch(cabinet, /!template\.media_block\) items\.push|item\.mediaBlock \|\| seen\.has|SylvexRefPanel\?\.close\(\); openMediaBlock\(item\.block\)/);
  assert.match(cabinet, /if \(!template\.is_kling_effect\) items\.push\(\{[^\n]*block:template\.media_block \|\| null \}\);/);
  assert.match(cabinet, /items\.push\(\{ id: item\.id, image: item\.url, title: item\.title, block: item\.mediaBlock \|\| null \}\);/);
  assert.match(cabinet, /if \(ref\.block\) return generateHomeIdeaBlock\(ref, photo, form\);/);
  assert.match(cabinet, /const jobId = await blocks\.run\(block, \{ \[field\.key\]: photo\.url \}, \{ lang: uiLang\(\) \}\);/);
  assert.match(cabinet, /await openMediaHandoff\(\{ jobId, kind: kind === 'video' \? 'video_reference' : 'image_reference', title: ref\.title \|\| block\.name \|\| '', refs: \[ref\.image, photo\.url\] \}\);/);
  // More than the one photo: its window opens with the photo already in.
  assert.match(cabinet, /openMediaBlock\(block, field \? \{ files: \{ \[field\.key\]: \{ url: photo\.url, preview: photo\.preview \|\| photo\.url \} \} \} : \{\}\);/);
});

test('the block runner: one photo field, whether one photo is enough, and the refusals', async () => {
  const sandbox = { window: {}, document: { documentElement: { lang: 'ru' } } };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(blocksJs, sandbox);
  const blocks = sandbox.window.SylvexMediaBlocks || sandbox.SylvexMediaBlocks;
  const one = { id: 5, fields: [{ key: 'face', accept: 'image', required: true }, { key: 'extra', accept: 'image', required: false }] };
  const two = { id: 6, fields: [{ key: 'clip', accept: 'video', required: true }, { key: 'face', accept: 'image', required: true }] };
  assert.equal(blocks.mainField(one).key, 'face');
  assert.equal(blocks.onePhotoIsEnough(one), true);
  assert.equal(blocks.mainField(two).key, 'face');
  assert.equal(blocks.onePhotoIsEnough(two), false);
  const reply = (status, body) => () => Promise.resolve({ status, ok: status < 300, json: () => Promise.resolve(body) });
  sandbox.fetch = reply(200, { job_id: 'job_1' });
  assert.equal(await blocks.run(one, { face: '/u.png' }, { lang: 'ru' }), 'job_1');
  sandbox.fetch = reply(402, { insufficient_balance: true });
  await assert.rejects(blocks.run(one, { face: '/u.png' }, { lang: 'ru' }), (error) => error.action === 'shop');
  sandbox.fetch = reply(401, { error: 'authentication_required' });
  await assert.rejects(blocks.run(one, { face: '/u.png' }, {}), (error) => error.action === 'login');
});

test('the block window is the window of every catalog reference', () => {
  assert.match(blocksJs, /'<button type="button" class="sxmb-upload" data-sxmb-field="' \+ esc\(field\.key\) \+ '"><span class="sxmb-upload-icon" aria-hidden="true">▧<\/span>'/);
  assert.match(blocksJs, /uploadImage: 'Загрузить изображение', uploadVideo: 'Загрузить видео', hintImage: 'PNG, JPG или вставьте из буфера обмена'/);
  assert.match(blocksJs, /media\.style\.setProperty\('--catalog-backdrop'/);
  assert.doesNotMatch(blocksJs, /class="sxmb-(thumb|label|action|plus|field)[ "]/);
  // The values of the Media viewer (css/media.css).
  assert.match(blocksCss, /\.sxmb-sheet \{ position: relative; display: grid; grid-template-columns: minmax\(260px, 1fr\) minmax\(300px, 1fr\);/);
  assert.match(blocksCss, /\.sxmb-upload \{ position: relative; flex: 0 0 auto; min-height: 190px;[^}]*border: 2px dashed rgba\(255, 255, 255, \.16\); border-radius: 26px;/);
  assert.match(mediaCss, /\.sx-media-upload\{position:relative;flex:0 0 auto;min-height:190px;[^}]*border:2px dashed rgba\(255,255,255,\.16\);border-radius:26px;/);
  assert.match(blocksCss, /\.sxmb-go \{ flex: 0 0 auto; margin-top: auto; min-height: 58px; border: 0; border-radius: 22px; background: #1f5da6;/);
  assert.match(mediaCss, /\.sx-media-generate\{flex:0 0 auto;margin-top:auto;min-height:58px;border:0;border-radius:22px;background:#1f5da6;/);
});

test('phones: the reference viewers are one column with a small picture on top; wide screens keep two columns', () => {
  const block = css.slice(css.indexOf('/* Phones: the reference viewer is one column'));
  assert.match(block, /@media\(max-width:560px\)\{\n  \.video-template-modal\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:auto minmax\(0,1fr\);/);
  assert.match(block, /\.video-template-preview\{min-height:0;height:min\(30vh,220px\)\}/);
  assert.match(blocksCss, /@media \(max-width: 560px\) \{[\s\S]*\.sxmb-sheet \{[^}]*grid-template-columns: minmax\(0, 1fr\); grid-template-rows: auto minmax\(0, 1fr\); \}\n  \.sxmb-media \{ min-height: 0; height: min\(30vh, 220px\);/);
  assert.match(mediaCss, /\.sx-media-viewer\[open\]\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:auto minmax\(0,1fr\)\}\n  \.sx-media-viewer-media\{min-height:0;height:min\(30vh,220px\);/);
  assert.match(css, /\.video-template-modal\{\n  position:relative;\n  display:grid;\n  grid-template-columns:minmax\(260px,1fr\) minmax\(300px,1fr\);/);
});
