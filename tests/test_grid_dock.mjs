// Run with: node --test tests/test_grid_dock.mjs
//
// Grid Mode: the side panel as the React Bits Dock (grid_dock/ ->
// webapp/js/vendor/grid-dock, mounted by cabinet.js). Covers: the component
// is the published one, unmodified; the task's settings at the panel's
// existing size; that the Dock items are the panel's own buttons (same
// icons, each clicks its original button) and follow its changes; and that
// the bundle loads on demand only, when Grid Mode opens.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');
const cabinet = read('webapp/js/cabinet.js');

test('Dock.jsx / Dock.css: the published files, unmodified', () => {
  // https://raw.githubusercontent.com/DavidHDev/react-bits/main/public/r/Dock-JS-CSS.json
  assert.equal(sha256('grid_dock/src/Dock.jsx'), 'f1eba9b158a023e78ff76242a0b17468ed733475918b1cb473158af19f59ebf9');
  assert.equal(sha256('grid_dock/src/Dock.css'), '68914a58df742acacbe82341d930f6ae6d2e0720176e9428f5edcad4353f53e6');
  const bundle = read('webapp/js/vendor/grid-dock/grid-dock.js');
  assert.ok(bundle.includes('SylvexGridDock') && bundle.includes('dock-item'));
  assert.ok(existsSync(new URL('../webapp/js/vendor/grid-dock/grid-dock.css', import.meta.url)));
  assert.ok(read('.gitignore').includes('grid_dock/node_modules/'));
});

test('the task settings, scaled to the side panel block', () => {
  const main = read('grid_dock/src/main.jsx');
  const start = main.indexOf('const DOCK_PROPS = {');
  const block = main.slice(start, main.indexOf('};', start) + 1);
  const settings = vm.runInNewContext('(' + block.replace('const DOCK_PROPS = ', '') + ')');
  assert.deepEqual(JSON.parse(JSON.stringify(settings)), {
    baseItemSize: 42, magnification: 71, panelHeight: 54, distance: 140, gap: 4, roundness: 0.7,
    accentColor: '#0a84ff', badgeColor: '#ff453a', position: 'left', bounce: true, autoHide: false,
    tiles: false, showLabels: true, showIndicators: false, showBadges: true, theme: 'dark',
  });
  // Same ratios as the task's baseItemSize 60 / magnification 102 / distance 200.
  assert.equal(Math.round(settings.baseItemSize * 102 / 60), settings.magnification);
  assert.equal(Math.round(settings.baseItemSize * 200 / 60), settings.distance);
});

function extract(name) {
  const start = cabinet.indexOf(`function ${name}(`);
  assert.ok(start > 0, name);
  let depth = 0;
  for (let i = cabinet.indexOf('{', start); i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}' && --depth === 0) return cabinet.slice(start, i + 1);
  }
  throw new Error('unbalanced ' + name);
}

test('Dock items are the panel buttons: same icons and labels, each clicks its button', () => {
  const html = read('webapp/cabinet.html');
  const panel = html.slice(html.indexOf('<aside class="studio-grid-node-tools"'), html.indexOf('</aside>', html.indexOf('<aside class="studio-grid-node-tools"')));
  const clicks = [];
  const el = (tag, extra = {}) => ({tagName: tag, ...extra});
  const button = (icon, label, className = '') => el('BUTTON', {
    className, title: '', click: () => clicks.push(label),
    querySelector: (s) => (s === 'i' ? {textContent: icon} : {textContent: label}),
  });
  const gridDockItems = vm.runInNewContext('(' + extract('gridDockItems') + ')');
  const rows = [];
  for (const m of panel.matchAll(/<button([^>]*)><i>([^<]*)<\/i><span>([^<]*)<\/span><\/button>|<hr/g)) {
    rows.push(m[0] === '<hr' ? el('HR') : button(m[2], m[3], (/class="([^"]*)"/.exec(m[1]) || [])[1] || ''));
  }
  assert.equal(rows.length, 11);
  const items = gridDockItems({children: rows});
  assert.deepEqual([...items].map((item) => item.separator ? '|' : item.icon + ' ' + item.label),
    ['＋ Новый', '⌘ Расставить', '▷ Запустить', '|', '✦ Задача', 'T Текст', '▧ Фото', '▶ Видео', '♫ Музыка', '◉ Голос', '⌘ Монтаж']);
  assert.equal(items[0].className, 'studio-grid-tool-primary');
  items[5].onClick();
  items[2].onClick();
  assert.deepEqual(clicks, ['Текст', 'Запустить']);
});

test('mounted next to the hidden panel, follows it and the theme; bundle on demand only', () => {
  const mount = extract('mountStudioGridDock');
  assert.ok(mount.includes("panel.after(mount);"));
  assert.ok(mount.includes("panel.dataset.docked='';"));
  assert.ok(mount.includes("new MutationObserver(()=>panel._gridDock.update(gridDockItems(panel))).observe(panel,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class']});"));
  assert.ok(mount.includes("studioSurfaceTheme(panel.parentNode,'--st-bg-2')"));
  assert.ok(!/fetch\(|addStudioGridNode|runStudioGridWorkflow/.test(mount), 'display only');
  assert.ok(read('grid_dock/src/host.css').includes('.studio-grid-node-tools[data-docked] {\n  display: none !important;'));
  assert.ok(cabinet.includes("autoLayoutStudioGrid();\n      else renderStudioGrid();\n      mountStudioGridDock();"), 'when Grid Mode opens');
  assert.ok(cabinet.includes("?._gridDock) mountStudioGridDock();"));
  assert.ok(cabinet.includes("EDIT_PIXEL_BASE+'js/vendor/grid-dock/grid-dock.js?v='+GRID_DOCK_VERSION"));
  assert.ok(!read('webapp/index.html').includes('vendor/grid-dock'));
});
