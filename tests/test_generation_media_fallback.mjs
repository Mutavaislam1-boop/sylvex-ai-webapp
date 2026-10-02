// Run with: node --test tests/test_generation_media_fallback.mjs
//
// Regression test for Master A-Z Remediation Phase 15 (History/result
// storage/media persistence): "genuinely unavailable old assets get a
// clean 'Media unavailable' state, not a broken empty card." The chat
// timeline's generation-result mini-card (buildGenerationResultCard,
// previewImgHtml helper) already degraded gracefully on a 404'd image -
// swapping to a fallback URL first, then to a plain
// <span class="generation-result-fallback"> placeholder - but
// renderGeneratedImage's own multi-image grid card used a bare <img> with
// no onerror handling at all, so an expired/lost provider URL there
// rendered the browser's broken-image icon forever. previewImgHtml was
// extended with an optional extraClass param so renderGeneratedImage can
// reuse the exact same graceful-degradation markup instead of duplicating
// (or omitting) it.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

function extractFunction(name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = cabinet.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < cabinet.length, `matching close not found: ${name}`);
  return cabinet.slice(match.index, i + 1);
}

function makeContext() {
  const context = vm.createContext({
    S: { escapeHtml: (v) => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') },
  });
  vm.runInContext(extractFunction('previewImgHtml'), context);
  return context;
}

test('previewImgHtml: with a URL, renders an <img> with an onerror graceful-degradation handler', () => {
  const context = makeContext();
  const html = vm.runInContext('previewImgHtml("https://cdn.sylvex.ai/a.png", "generated", "https://cdn.sylvex.ai/full.png")', context);
  assert.match(html, /<img /);
  assert.match(html, /src="https:\/\/cdn\.sylvex\.ai\/a\.png"/);
  assert.match(html, /data-fallback-src="https:\/\/cdn\.sylvex\.ai\/full\.png"/);
  assert.match(html, /onerror=/);
  assert.match(html, /generation-result-fallback/);
});

test('previewImgHtml: no URL at all renders the clean fallback placeholder directly, never a broken <img>', () => {
  const context = makeContext();
  const html = vm.runInContext('previewImgHtml("", "generated", "")', context);
  assert.equal(html, '<span class="generation-result-fallback">IMG</span>');
  assert.doesNotMatch(html, /<img/);
});

test('previewImgHtml: extraClass is applied to both the <img> and the eventual fallback span', () => {
  const context = makeContext();
  const html = vm.runInContext('previewImgHtml("https://cdn.sylvex.ai/a.png", "generated", "", "gen-img")', context);
  assert.match(html, /<img class="gen-img"/);
  assert.match(html, /className:'generation-result-fallback gen-img'/);
});

test('previewImgHtml: renderGeneratedImage\'s own call site produces a gen-img-classed element consistent with its grid CSS', () => {
  const context = makeContext();
  // Mirrors the exact call renderGeneratedImage makes.
  const html = vm.runInContext('previewImgHtml("https://cdn.sylvex.ai/thumb.png", "generated", "https://cdn.sylvex.ai/full.png", "gen-img")', context);
  assert.match(html, /class="gen-img"/);
  assert.match(html, /src="https:\/\/cdn\.sylvex\.ai\/thumb\.png"/);
});

test('previewImgHtml: special characters in the URL are escaped exactly once (no double-escaping)', () => {
  const context = makeContext();
  const html = vm.runInContext('previewImgHtml("https://cdn.sylvex.ai/a.png?x=1&y=2", "generated", "", "gen-img")', context);
  assert.match(html, /src="https:\/\/cdn\.sylvex\.ai\/a\.png\?x=1&amp;y=2"/);
  assert.doesNotMatch(html, /&amp;amp;/);
});
