// Run with: node --test tests/test_photo_tool_desktop_sizing.mjs
//
// Tool windows follow the sketch: one fixed-size window, the banner edge to
// edge on the left (a strip on top on a phone); on the right the gradient
// "Быстрый инструмент", the title and a short line, dashed upload tiles, a
// pill text field, preset rows with page dots and a gradient Generate pill.
// Nothing scrolls - everything fits on one screen.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const js = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const block = css.slice(css.indexOf('CSS-БЛОК: photo tool windows'));
const phone = block.slice(block.indexOf('@media(max-width:680px){'));

test('every tool window has one fixed size with no padding around the banner', () => {
  assert.match(block, /#photoToolDialog:has\(\.ptool-layout\)\{--ptool-grad:linear-gradient\(90deg,#2f8fb8,#86d36a\);width:min\(980px,calc\(100vw - 32px\)\);height:min\(700px,calc\(100vh - 40px\)\);height:min\(700px,calc\(100dvh - 40px\)\);max-width:none;max-height:none;padding:0;display:flex;overflow:hidden;/);
  assert.match(block, /\.ptool-layout\{[^}]*grid-template-columns:minmax\(0,46%\) minmax\(0,1fr\)\}/);
});

test('the right side never scrolls: a column whose upload areas shrink to fit', () => {
  assert.match(block, /\.ptool-work\{[^}]*display:flex;flex-direction:column;/);
  assert.match(block, /\.ptool-zones\{flex:1 1 auto;min-height:0;/);
  assert.match(block, /\.ptool-zone\{position:relative;flex:1 1 0;min-height:0;/);
  assert.match(block, /\.ptool-zone:not\(\.has-items\) \.ptool-add\{height:min\(100%,160px\);/);
});

test('on a phone the banner is a strip on top and the window fills the screen', () => {
  assert.match(phone, /#photoToolDialog:has\(\.ptool-layout\)\{width:100%;height:calc\(100vh - 16px\);height:calc\(100dvh - 16px\);/);
  assert.match(phone, /\.ptool-layout\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:clamp\(70px,15dvh,140px\) minmax\(0,1fr\)\}/);
});

test('the head is the gradient kicker, the title and a short line; Generate is a gradient pill', () => {
  assert.match(js, /'<header class="ptool-head"><b class="ptool-kicker">Быстрый инструмент<\/b><h3>' \+ S\.escapeHtml\(config\.title\) \+ '<\/h3>'/);
  assert.match(js, /try_on:'Реалистичная примерка одежды'/);
  assert.match(block, /\.ptool-kicker\{display:inline-block;background:var\(--ptool-grad\);-webkit-background-clip:text;background-clip:text;color:transparent;/);
  assert.match(block, /\.ptool-work \.photo-tool-generate\{flex:0 0 auto;align-self:flex-end;width:auto;[^}]*border-radius:999px;background:var\(--ptool-grad\);/);
  assert.match(block, /\.ptool-work textarea\{[^}]*border-radius:999px;/);
});

test('preset rows get page dots', () => {
  assert.match(js, /function mountPhotoToolPresetPages\(\) \{/);
  assert.match(js, /  mountPhotoToolPresetPages\(\);\n\}/);
  assert.match(block, /\.ptool-pages button\.active\{background:var\(--ptool-grad\)\}/);
});

test('hair colour: the parts list beside a picker with shade square, hue, HEX, reset and a 7x4 palette', () => {
  assert.match(js, /'<div class="ptool-hair">' \+ hairBeardCatalogHtml\(\) \+ hairBeardColorsHtml\(\) \+ '<\/div>'/);
  assert.match(js, /'<div class="ptool-color-sv" style="--hue:'/);
  assert.match(js, /'<input class="ptool-color-hue" type="range" min="0" max="359"/);
  assert.match(js, /onchange="SYLVEX\.setHairBeardHex\(event\)"/);
  assert.match(js, /'EyeDropper' in window/);
  assert.match(block, /\.ptool-color-grid\{display:grid;grid-template-columns:repeat\(7,1fr\);/);
  assert.match(block, /\.ptool-dropdown-panel\{position:absolute;right:0;bottom:calc\(100% \+ 8px\);display:grid;grid-template-columns:auto 196px;/);
  assert.match(js, /const HAIR_BEARD_CATEGORY_LABELS = \{ men:'Мужчины', beard_mustache:'Борода и усы', women:'Девушки' \};/);
});

test('hsv conversions round-trip a colour', async () => {
  const src = ['hexToHsvColor', 'hsvToHexColor'].map((name) => {
    const start = js.indexOf('function ' + name + '(');
    return js.slice(start, js.indexOf('\n}\n', start) + 2);
  }).join('\n');
  const {hexToHsvColor, hsvToHexColor} = new Function(src + '; return {hexToHsvColor, hsvToHexColor};')();
  for (const hex of ['#3b2a20', '#a5452c', '#123abc', '#ffffff', '#000000']) {
    const {h, s, v} = hexToHsvColor(hex);
    assert.equal(hsvToHexColor(h, s, v), hex);
  }
});
