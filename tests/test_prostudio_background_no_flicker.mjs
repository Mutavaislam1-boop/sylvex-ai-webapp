// Run with: node --test tests/test_prostudio_background_no_flicker.mjs
//
// Regression tests for "Pro Studio Mini App - Photo Tools UI Polish",
// item 7: the dotted/grid-like background in the NORMAL (classic) Pro
// Studio workspace must stay visually static when generation starts -
// no pulse/flicker/drift animation. Grid Mode and the separate Edit
// workspace must be completely unaffected.
//
// Three independent generation-triggered animations were found layered
// on top of each other over time (safeStudioDotsMove on .chat-area,
// safeStudioDotsMove on .studio, and studioGridPulse's brightness pulse
// on .studio - the last one wins the cascade and is the one actually
// visible). Each is now split into a `.studio.grid-mode` rule (left
// byte-for-byte as it was) and a `.studio:not(.grid-mode)` rule (no
// animation).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

function blockFor(selectorFragment) {
  const index = css.indexOf(selectorFragment);
  assert.ok(index >= 0, `selector not found: ${selectorFragment}`);
  const open = css.indexOf('{', index);
  const close = css.indexOf('}', open);
  return css.slice(index, close + 1);
}

test('classic workspace .studio::before/::after no longer animate on generation', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .studio:not(.grid-mode)::before');
  assert.match(block, /animation:none !important/);
  const afterBlock = blockFor('body.ai-generating .view[data-view="tools"].active .studio:not(.grid-mode)::after');
  assert.match(afterBlock, /animation:none !important/);
});

test('grid-mode ::before/::after keep their original aiParticles animation untouched', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .studio.grid-mode::before');
  assert.match(block, /animation:aiParticlesMove 10s linear infinite, aiParticlesGlow 2\.2s ease-in-out infinite !important/);
});

test('classic workspace .chat-area dots no longer drift on generation', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .chat-area,');
  assert.match(block, /animation:none !important/);
  assert.doesNotMatch(block, /safeStudioDotsMove/);
});

test('classic workspace .studio background-image no longer animates via safeStudioDotsMove', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .studio:not(.grid-mode),');
  assert.match(block, /animation:none !important/);
  assert.doesNotMatch(block, /safeStudioDotsMove/);
});

test('grid-mode keeps the original safeStudioDotsMove animation on .studio untouched', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .studio.grid-mode,');
  assert.match(block, /animation:safeStudioDotsMove 8s linear infinite !important/);
});

test('classic workspace decorative dot matrix no longer pulses (studioGridPulse removed, filter reset)', () => {
  const block = css.slice(
    css.indexOf('body.ai-generating .view[data-view="tools"].active .studio:not(.grid-mode),', css.indexOf('studioGridPulse')),
  );
  const close = block.indexOf('}');
  const rule = block.slice(0, close + 1);
  assert.match(rule, /animation:none !important/);
  assert.match(rule, /filter:none !important/);
  assert.doesNotMatch(rule, /studioGridPulse/);
});

test('grid-mode keeps the original studioGridPulse brightness pulse untouched', () => {
  const block = blockFor('body.ai-generating .view[data-view="tools"].active .studio.grid-mode,\n.view[data-view="tools"].active .studio.grid-mode:has(.typing){\n  background-image:\n    radial-gradient(circle, var(--st-grid-line)');
  assert.match(block, /animation:studioGridPulse 2\.6s ease-in-out infinite !important/);
});
