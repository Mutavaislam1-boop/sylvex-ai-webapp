// Run with: node --test tests/test_photo_tool_desktop_sizing.mjs
//
// Regression test for "Pro Studio Mini App - Navigation + Modal UI
// Cleanup", item 4: Tattoo and Replace Object render their Before/After
// compare block full-width inside the single-column `.tattoo-layout` /
// `.replace-object-layout` (not the normal two-column photo-tool-layout),
// which let it balloon to ~900px wide by up to 60vh tall on desktop. A
// desktop/tablet-only (>680px) cap keeps it compact without touching the
// mobile rules, which stay exactly as they were.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

test('base (mobile-inclusive) Before/After rules are unchanged: no width cap outside the desktop override', () => {
  assert.match(css, /\.tattoo-result-compare\{width:100%;max-height:52vh;margin:0 auto;background:var\(--bg-1\);aspect-ratio:4\/3\}/);
  assert.match(css, /\.replace-object-result-compare\{max-height:60vh;margin:0 auto;background:var\(--bg-1\)\}/);
});

test('a min-width:681px override caps Tattoo/Replace Object Before/After to a compact desktop size', () => {
  const block = /@media\(min-width:681px\)\{[^]*?\.tattoo-result-compare\{([^}]*)\}[^]*?\.replace-object-result-compare\{([^}]*)\}[^]*?\}/.exec(css);
  assert.ok(block, 'expected a min-width:681px override for both compare blocks');
  assert.match(block[1], /max-width:\d+px/);
  assert.match(block[1], /max-height:min\(/);
  assert.match(block[2], /max-width:\d+px/);
  assert.match(block[2], /max-height:min\(/);
});

test('the desktop override does not touch any existing mobile (max-width) breakpoint', () => {
  const desktopBlockStart = css.indexOf('@media(min-width:681px){\n  .tattoo-result-compare');
  assert.ok(desktopBlockStart >= 0);
  const desktopBlockEnd = css.indexOf('}\n', css.indexOf('.replace-object-result-compare{max-width', desktopBlockStart)) + 1;
  const desktopBlock = css.slice(desktopBlockStart, desktopBlockEnd + 1);
  assert.doesNotMatch(desktopBlock, /max-width:680px/);
});
