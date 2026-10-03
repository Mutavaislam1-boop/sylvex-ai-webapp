import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const themeBlock = source.slice(source.indexOf('  const STUDIO_THEME_KEY'), source.indexOf("  // Grid Mode's canvas/workspace"));
const appearance = source.slice(source.indexOf('  function applyProfileAppearance('), source.indexOf('  function syncAppearanceEditor('));
const applyTheme = source.slice(source.indexOf('  function applyTheme('), source.indexOf('  function renderThemeGrid('));
const startup = source.slice(source.indexOf('  function restoreAppTheme('), source.indexOf('  function init()'));

function harness({siteTheme = 'light', embedded = true, host = true, stored = {}, search = ''} = {}) {
  const attributes = {'data-theme': siteTheme}, studioAttributes = {}, variables = {}, listeners = {};
  const storage = new Map(Object.entries(stored));
  const studio = {
    setAttribute: (key, value) => {studioAttributes[key] = value;},
    removeAttribute: key => {delete studioAttributes[key];},
  };
  const document = {
    documentElement: {getAttribute: key => attributes[key], style: {setProperty: (key, value) => {variables[key] = value;}}},
    querySelector: () => studio,
  };
  const window = {
    location: {search}, matchMedia: () => ({matches: false}),
    addEventListener: (name, fn) => {listeners[name] = fn;},
  };
  window.parent = window;
  if (host) window.SYLVEX_SITE = {currentTheme: () => attributes['data-theme']};
  const appThemes = [];
  const context = vm.createContext({window, document, URLSearchParams, isWebEmbed: () => embedded,
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    S: {setTheme: value => appThemes.push(value)},
    getComputedStyle: () => ({getPropertyValue: name => name === '--st-bg' ? (studioAttributes['data-ps-theme'] === 'white' ? '#ffffff' : '#000000') : 'theme-value'}),
  });
  vm.runInContext(themeBlock + appearance + applyTheme + startup, context);
  return {context, attributes, studioAttributes, variables, listeners, storage, appThemes, window};
}

test('website appearance wins over stale Mini App, Studio and URL themes on startup', () => {
  const h = harness({stored: {'sylvex-theme': 'dark', 'sylvex-prostudio-theme': 'black'}, search: '?theme=dark'});
  h.context.restoreAppTheme();
  assert.equal(h.studioAttributes['data-ps-theme'], 'white');
  assert.equal(h.attributes['data-theme'], 'light');
  assert.deepEqual(h.appThemes, []);
  assert.equal(h.storage.get('sylvex-prostudio-theme'), 'black');
});

test('live website toggles update Studio and document variables used by Edit/popups', () => {
  const h = harness();
  for (const [theme, studioTheme, bg] of [['dark', 'black', '#000000'], ['light', 'white', '#ffffff']]) {
    h.attributes['data-theme'] = theme;
    h.listeners['sylvex-theme']({detail: {theme}});
    assert.equal(h.studioAttributes['data-ps-theme'], studioTheme);
    assert.equal(h.variables['--st-bg'], bg);
    assert.ok(h.variables['--st-color-scheme']);
    assert.ok(h.variables['--st-success']);
  }
});

test('profile hydration cannot overwrite the host theme or persist Mini App appearance', () => {
  const h = harness();
  h.context.applyProfileAppearance({id: 'dark'});
  h.context.applyTheme('dark', false);
  assert.equal(h.attributes['data-theme'], 'light');
  assert.equal(h.studioAttributes['data-ps-theme'], 'white');
  assert.equal(h.storage.has('sylvex-theme-id'), false);
});

test('legacy iframe theme messages only work from the parent and accept light/dark', () => {
  const h = harness({host: false});
  const parent = {}; h.window.parent = parent;
  h.context.restoreStudioTheme();
  h.listeners.message({source: {}, data: {type: 'sylvex-theme', theme: 'dark'}});
  assert.equal(h.studioAttributes['data-ps-theme'], 'white');
  h.listeners.message({source: parent, data: {type: 'sylvex-theme', theme: 'dark'}});
  assert.equal(h.studioAttributes['data-ps-theme'], 'black');
  h.listeners.message({source: parent, data: {type: 'sylvex-theme', theme: 'invalid'}});
  assert.equal(h.studioAttributes['data-ps-theme'], 'black');
});

test('Mini App keeps its own saved preferences and ignores website events', () => {
  const h = harness({embedded: false, stored: {'sylvex-theme': 'dark', 'sylvex-prostudio-theme': 'white'}});
  h.context.restoreAppTheme(); h.context.restoreStudioTheme();
  h.attributes['data-theme'] = 'dark'; h.listeners['sylvex-theme']({});
  assert.deepEqual(h.appThemes, ['dark']);
  assert.equal(h.studioAttributes['data-ps-theme'], 'white');
});

test('hostless embed resolves an explicit root theme, with a system fallback', () => {
  const h = harness({host: false, siteTheme: 'dark'});
  h.context.restoreStudioTheme(); assert.equal(h.studioAttributes['data-ps-theme'], 'black');
  delete h.attributes['data-theme'];
  h.context.restoreStudioTheme(); assert.equal(h.studioAttributes['data-ps-theme'], 'white');
});
