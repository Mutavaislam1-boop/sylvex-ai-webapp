// Run with: node --test tests/test_catalog_blocks_and_phone_viewer.mjs
//
// The references built in the admin Media constructor come from the one
// catalog (video templates, quick image catalog) everywhere, the Home
// catalog panel included, with the same cards; a pick opens the block's own
// window with its own fields, model and prompt. On phones the reference
// viewer is one column: a small picture on top, the details under it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

test('the Home catalog panel lists the admin blocks of the one catalog and opens their own window', () => {
  assert.doesNotMatch(cabinet, /!template\.media_block\) items\.push|item\.mediaBlock \|\| seen\.has/);
  assert.match(cabinet, /if \(!template\.is_kling_effect\) items\.push\(\{[^\n]*block:template\.media_block \|\| null \}\);/);
  assert.match(cabinet, /items\.push\(\{ id: item\.id, image: item\.url, title: item\.title, block: item\.mediaBlock \|\| null \}\);/);
  assert.match(cabinet, /if \(item && item\.block\) \{ window\.SylvexRefPanel\?\.close\(\); openMediaBlock\(item\.block\); return; \}/);
});

test('phones: the reference viewers are one column with a small picture on top; wide screens keep two columns', () => {
  const block = css.slice(css.indexOf('/* Phones: the reference viewer is one column'));
  assert.match(block, /@media\(max-width:560px\)\{\n  \.video-template-modal\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:auto minmax\(0,1fr\);/);
  assert.match(block, /\.video-template-preview\{min-height:0;height:min\(30vh,220px\)\}/);
  assert.match(block, /\.sxmb-sheet \.sxmb-media\{aspect-ratio:auto;height:min\(30vh,220px\);max-height:none\}/);
  assert.match(css, /\.video-template-modal\{\n  position:relative;\n  display:grid;\n  grid-template-columns:minmax\(260px,1fr\) minmax\(300px,1fr\);/);
});
