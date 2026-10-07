// Run with: node --test tests/test_temp6_temp7_removed.mjs
//
// Regression tests for remediation item #23: removal of TEMP-6 (3
// audited unconditional debug statements) and TEMP-7 (the orphaned
// Brand Generator observer/index state left behind once item #20
// removed its only readers/writers).
//
// TEMP-6 removed:
//   - console.log("SYLVEX_CABINET_JS_STARTED");
//   - console.log("CABINET JS NEW VERSION 11.07.2026");
//   - the full console.debug('PROSTUDIO IMAGE METADATA DEBUG', {...}) block
//
// TEMP-7 removed:
//   - the brandGeneratorStartIndex/brandGeneratorObserver state declaration
//   - the two now-inert brandGeneratorObserver?.disconnect();
//     brandGeneratorObserver=null; teardown expressions in
//     launchBrandProStudio() and closeBrandGenerator() (brandGeneratorObserver
//     was only ever assigned null, so these never disconnected anything real)
//
// This file proves the 3 debug statements and the 2 orphaned symbols are
// gone, that the live Brand Generator/Brand Music functions and their
// non-observer cleanup (body classes/dataset, DOM removal, music pause,
// navigation) remain intact, and that an unrelated console statement
// (PAYPAL CHECKOUT URL) was left untouched.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

// ---------------------------------------------------------------------------
// TEMP-6: the 3 audited debug statements are gone
// ---------------------------------------------------------------------------

test('SYLVEX_CABINET_JS_STARTED debug log is gone', () => {
  assert.equal(source.includes('SYLVEX_CABINET_JS_STARTED'), false);
});

test('CABINET JS NEW VERSION debug log is gone', () => {
  assert.equal(source.includes('CABINET JS NEW VERSION 11.07.2026'), false);
});

test('PROSTUDIO IMAGE METADATA DEBUG console.debug block is gone', () => {
  assert.equal(source.includes('PROSTUDIO IMAGE METADATA DEBUG'), false);
  assert.equal(source.includes("console.debug('PROSTUDIO"), false);
});

// ---------------------------------------------------------------------------
// Unrelated console output must be untouched
// ---------------------------------------------------------------------------

test('the unrelated PAYPAL CHECKOUT URL console.log is untouched', () => {
  assert.equal(source.includes("console.log('PAYPAL CHECKOUT URL:', paypalUrl);"), true);
});

// ---------------------------------------------------------------------------
// TEMP-7: the orphaned Brand Generator state is gone
// ---------------------------------------------------------------------------

test('brandGeneratorStartIndex is gone', () => {
  assert.equal(/\bbrandGeneratorStartIndex\b/.test(source), false);
});

test('brandGeneratorObserver is gone', () => {
  assert.equal(/\bbrandGeneratorObserver\b/.test(source), false);
});

// ---------------------------------------------------------------------------
// Live Brand Generator / Brand Music functionality must remain
// ---------------------------------------------------------------------------

function extractFunction(name) {
  const pattern = new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(source);
  assert.ok(match, `declaration not found: ${name}`);
  const openIndex = source.indexOf('{', match.index);
  let depth = 0;
  let i = openIndex;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) break; }
  }
  assert.ok(i < source.length, `matching close not found: ${name}`);
  return source.slice(match.index, i + 1);
}

test('launchBrandProStudio still exists and still carries its non-observer cleanup', () => {
  const body = extractFunction('launchBrandProStudio');
  assert.match(body, /closeBrandPresentation\(\);/);
  assert.match(body, /document\.body\.classList\.remove\('brand-generator-active'\)/);
  assert.match(body, /delete document\.body\.dataset\.brandGenerator/);
  assert.match(body, /document\.querySelector\('\.brand-generator-head'\)\?\.remove\(\)/);
  assert.match(body, /document\.querySelector\('\.brand-music-showcase'\)\?\.remove\(\)/);
  assert.match(body, /switchView\('tools'\)/);
  // The now-inert observer teardown must be gone from inside this function.
  assert.equal(body.includes('brandGeneratorObserver'), false);
});

test('closeBrandGenerator still exists and still carries its full non-observer cleanup', () => {
  const body = extractFunction('closeBrandGenerator');
  assert.match(body, /brand-generator-old/);
  assert.match(body, /document\.querySelector\('#brandMusicPlayer audio'\)\?\.pause\(\)/);
  assert.match(body, /document\.body\.classList\.remove\('brand-generator-active'\)/);
  assert.match(body, /delete document\.body\.dataset\.brandGenerator/);
  assert.match(body, /document\.querySelector\('\.brand-generator-head'\)\?\.remove\(\)/);
  assert.match(body, /document\.querySelector\('\.brand-music-showcase'\)\?\.remove\(\)/);
  assert.match(body, /switchView\('home'\)/);
  assert.equal(body.includes('brandGeneratorObserver'), false);
});

test('live Brand Music player functions remain untouched', () => {
  for (const name of [
    'brandMusicShowcaseHtml', 'updateBrandMusicSlider', 'renderBrandMusicShowcase',
    'loadBrandMusicLibrary', 'selectBrandMusic', 'moveBrandMusic', 'toggleBrandMusic',
    'seekBrandMusic', 'toggleBrandMusicRepeat', 'shuffleBrandMusic', 'selectBrandMusicGenre',
  ]) {
    assert.doesNotThrow(() => extractFunction(name), `${name} must still exist`);
  }
});

test('openBrandGenerator (the presentation page opener) remains untouched', () => {
  assert.doesNotThrow(() => extractFunction('openBrandGenerator'));
});

test('cabinet.js still parses as valid JavaScript after the removals', () => {
  new Function(source);
});
