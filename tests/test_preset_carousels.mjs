// Run with: node --test tests/test_preset_carousels.mjs
//
// Regression tests for "Pro Studio Mini App - Navigation + Modal UI
// Cleanup", item 3: Tattoo/Logo/Hair&Beard preset lists render as a single
// horizontal carousel (one scrollable track + desktop prev/next arrows)
// instead of a large grid, without changing what each preset does.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

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

function extractConst(name) {
  const pattern = new RegExp(`^const ${name} = `, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, `const not found: ${name}`);
  let i = match.index + match[0].length;
  let depth = 0;
  for (; i < cabinet.length; i++) {
    const ch = cabinet[i];
    if (ch === '[' || ch === '(' || ch === '{') depth++;
    else if (ch === ']' || ch === ')' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) { i++; break; }
  }
  assert.ok(i <= cabinet.length, `terminating ; not found: ${name}`);
  return cabinet.slice(match.index, i);
}

function makeContext(extra) {
  const sandbox = Object.assign({
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
  }, extra);
  return vm.createContext(sandbox);
}

test('logoCatalogHtml wraps the preset grid in a carousel with prev/next arrows, selection untouched', () => {
  const context = makeContext({ logoState: { selectedReferenceId: 'nivora' } });
  vm.runInContext(extractConst('LOGO_REFERENCES'), context);
  vm.runInContext(extractFunction('logoCatalogHtml'), context);
  const html = vm.runInContext('logoCatalogHtml()', context);
  assert.match(html, /class="preset-carousel"/);
  assert.match(html, /class="logo-reference-grid preset-carousel-track"/);
  assert.match(html, /SYLVEX\.scrollPresetCarousel\(event,this,-1\)/);
  assert.match(html, /SYLVEX\.scrollPresetCarousel\(event,this,1\)/);
  assert.match(html, /SYLVEX\.selectLogoReference\(event,'nivora'\)/);
  assert.match(html, /logo-reference-card selected/);
});

test('tattooCatalogHtml and hairBeardCatalogHtml markup use the shared carousel wrapper', () => {
  const context = makeContext({
    tattooState: { selectedReferenceId: null, customReferences: [] },
    hairBeardState: { category: 'men', selectedPresetId: null, customPresets: [] },
    HAIR_BEARD_CATEGORY_LABELS: { men: 'Men', women: 'Women', beard_mustache: 'Beard' },
    HAIR_BEARD_PRESET_LABELS: {},
  });
  vm.runInContext(extractConst('TATTOO_REFERENCES'), context);
  vm.runInContext(extractConst('HAIR_BEARD_PRESETS'), context);
  vm.runInContext('function hairBeardColorsHtml(){ return ""; }', context);
  vm.runInContext(extractFunction('tattooCatalogHtml'), context);
  vm.runInContext(extractFunction('hairBeardCatalogHtml'), context);

  const tattooHtml = vm.runInContext('tattooCatalogHtml()', context);
  assert.match(tattooHtml, /class="preset-carousel"/);
  assert.match(tattooHtml, /class="tattoo-reference-grid preset-carousel-track"/);
  assert.match(tattooHtml, /SYLVEX\.scrollPresetCarousel\(event,this,-1\)/);
  assert.match(tattooHtml, /SYLVEX\.scrollPresetCarousel\(event,this,1\)/);
  assert.match(tattooHtml, /SYLVEX\.selectTattooReference\(event,'tattoo_ref_01'\)/);

  const hairBeardHtml = vm.runInContext('hairBeardCatalogHtml()', context);
  assert.match(hairBeardHtml, /class="preset-carousel"/);
  assert.match(hairBeardHtml, /class="hair-beard-grid preset-carousel-track"/);
  assert.match(hairBeardHtml, /SYLVEX\.scrollPresetCarousel\(event,this,-1\)/);
  assert.match(hairBeardHtml, /SYLVEX\.scrollPresetCarousel\(event,this,1\)/);
  assert.match(hairBeardHtml, /SYLVEX\.selectHairBeardPreset\(event,'bald'\)/);
});

test('scrollPresetCarousel scrolls the track inside its own carousel wrapper, smoothly, by direction', () => {
  const calls = [];
  const track = { clientWidth: 300, scrollBy: (opts) => calls.push(opts) };
  const wrap = { querySelector: (sel) => (sel === '.preset-carousel-track' ? track : null) };
  const btn = { closest: (sel) => (sel === '.preset-carousel' ? wrap : null) };
  const context = makeContext({ __btn: btn });
  vm.runInContext(extractFunction('scrollPresetCarousel'), context);
  vm.runInContext('scrollPresetCarousel(null, __btn, 1)', context);
  vm.runInContext('scrollPresetCarousel(null, __btn, -1)', context);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].left, 240);
  assert.equal(calls[0].behavior, 'smooth');
  assert.equal(calls[1].left, -240);
});

test('scrollPresetCarousel is a no-op when the button has no enclosing carousel (never throws)', () => {
  const context = makeContext({ __btn: { closest: () => null } });
  vm.runInContext(extractFunction('scrollPresetCarousel'), context);
  assert.doesNotThrow(() => vm.runInContext('scrollPresetCarousel(null, __btn, 1)', context));
});

test('CSS: preset carousel tracks scroll horizontally and hide the native scrollbar', () => {
  assert.match(css, /\.preset-carousel\{[^}]*display:flex/);
  assert.match(css, /\.preset-carousel-arrow\{[^}]*border-radius:50%/);
  assert.match(css, /@media\(max-width:900px\)\{\.preset-carousel-arrow\{display:none\}\}/);
  for (const trackClass of ['.logo-reference-grid', '.tattoo-reference-grid', '.hair-beard-grid']) {
    const rule = new RegExp(trackClass.replace('.', '\\.') + '\\{[^}]*overflow-x:auto');
    assert.match(css, rule, `${trackClass} should scroll horizontally`);
  }
});
