// Run with: node --test tests/test_photo_tool_desktop_sizing.mjs
//
// Tool windows are laid out like the Media viewer: one fixed-size window,
// the banner edge to edge on the left (a strip on top on a phone), a clean
// right side, and nothing scrolls - everything fits on one screen.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const js = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const block = css.slice(css.indexOf('CSS-БЛОК: photo tool windows'));
const phone = block.slice(block.indexOf('@media(max-width:680px){'));

test('every tool window has one fixed size with no padding around the banner', () => {
  assert.match(block, /#photoToolDialog:has\(\.ptool-layout\)\{width:min\(940px,calc\(100vw - 32px\)\);height:min\(620px,calc\(100vh - 40px\)\);height:min\(620px,calc\(100dvh - 40px\)\);max-width:none;max-height:none;padding:0;display:flex;overflow:hidden;/);
  assert.match(block, /\.ptool-layout\{[^}]*grid-template-columns:minmax\(0,44%\) minmax\(0,1fr\)\}/);
});

test('the right side never scrolls: it is a column whose upload areas shrink to fit', () => {
  assert.match(block, /\.ptool-work\{[^}]*display:flex;flex-direction:column;[^}]*overflow:hidden;/);
  assert.match(block, /\.ptool-zones\{flex:1 1 auto;min-height:0;/);
  assert.match(block, /\.ptool-zone\{position:relative;flex:1 1 0;min-height:0;/);
  assert.doesNotMatch(block, /overflow-y:auto/);
});

test('on a phone the banner is a strip on top and the window fills the screen', () => {
  assert.match(phone, /#photoToolDialog:has\(\.ptool-layout\)\{width:100%;height:calc\(100vh - 16px\);height:calc\(100dvh - 16px\);/);
  assert.match(phone, /\.ptool-layout\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:clamp\(76px,17dvh,150px\) minmax\(0,1fr\)\}/);
});

test('the window has the kicker and title on the right and a round close over the corner', () => {
  assert.match(js, /'<header class="ptool-head"><small>Быстрый инструмент<\/small><h3>' \+ S\.escapeHtml\(config\.title\) \+ '<\/h3><\/header>'/);
  assert.match(js, /'<button type="button" class="ptool-close" aria-label="Закрыть" onclick="SYLVEX\.closePhotoToolModal\(event\)">×<\/button>'/);
  assert.doesNotMatch(js, /<small>Фото-инструмент<\/small>/);
});

test('hair colour is a small pill beside the category switch that opens a panel over the window', () => {
  assert.match(js, /'<div class="ptool-hair">' \+ hairBeardCatalogHtml\(\) \+ hairBeardColorsHtml\(\) \+ '<\/div>'/);
  assert.match(block, /\.ptool-dropdown-panel\{position:absolute;right:0;bottom:calc\(100% \+ 8px\);/);
  assert.match(block, /\.hair-beard-color-row\{display:grid;grid-template-columns:56px minmax\(0,1fr\);/);
  assert.match(js, /const HAIR_BEARD_CATEGORY_LABELS = \{ men:'Мужчины', beard_mustache:'Борода и усы', women:'Девушки' \};/);
});
