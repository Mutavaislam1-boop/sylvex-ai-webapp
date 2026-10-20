// Run with: node --test tests/test_composer_level.mjs
//
// Pro Studio composer at one level in every mode (the video section is the
// reference) and the mode switch as the React Bits RubberSegment
// (mode_segment/ -> webapp/js/vendor/mode-segment, mounted by cabinet.js).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');
const css = read('webapp/css/cabinet.css');
const cabinet = read('webapp/js/cabinet.js');

test('every mode keeps the video section height in each layout', () => {
  assert.ok(css.includes('.studio-video-composer{--sx-media-h:228px;--sx-prompt-h:228px}'));
  assert.ok(css.includes('.studio-video-composer.is-compact{--sx-media-h:150px;--sx-prompt-h:145px}'));
  assert.ok(css.includes('@media(max-width:560px){.studio-video-composer.is-compact{--sx-media-h:164px}}'));
  assert.ok(css.includes('.studio-video-panel>:is(.studio-media-column,.studio-voice-full){height:var(--sx-media-h);min-height:0;box-sizing:border-box}'));
  assert.ok(css.includes('.studio-video-panel>.studio-prompt-column{height:var(--sx-prompt-h);min-height:0;box-sizing:border-box}'));
  assert.ok(css.includes(':not([data-composer-mode="voice"][data-voice-workspace="dialogue"])'), 'dialogue keeps its own layout');
  for (const fill of ['.studio-media-column>.image-visual-grid{flex:1 1 auto;', '.studio-voice-full>.vgen-actions{flex:1 1 auto;', '.studio-text-tools>.studio-image-tool{flex:1 1 auto;', '.studio-video-tools>:is(.studio-frame-row,.studio-video-edit-upload){flex:1 1 auto;'])
    assert.ok(css.includes(fill), fill);
  // Edit video no longer forces a 128px card in the compact layout.
  assert.match(css, /\.studio-video-composer\.is-compact\[data-video-section="motion"\] \.studio-video-edit-upload\{\n  min-height:0;/);
  assert.ok(!css.includes('[data-video-section="motion"] .studio-video-edit-upload{\n  min-height:128px;'));
});

test('RubberSegment.jsx / .css: the published files, unmodified; the task settings', () => {
  // https://raw.githubusercontent.com/DavidHDev/react-bits/main/public/r/RubberSegment-JS-CSS.json
  assert.equal(sha256('mode_segment/src/RubberSegment.jsx'), '35489f6c3c59dae1cd98d82c11e69f3ecee3cfb831bec70278365d07caac0bcf');
  assert.equal(sha256('mode_segment/src/RubberSegment.css'), '8e27a0daf7c64dc09939020db11d0461b03368763bceaaa60b88accad1b06cb4');
  assert.ok(read('webapp/js/vendor/mode-segment/mode-segment.js').includes('SylvexModeSegment'));
  assert.ok(existsSync(new URL('../webapp/js/vendor/mode-segment/mode-segment.css', import.meta.url)));
  assert.ok(read('.gitignore').includes('mode_segment/node_modules/'));
  const main = read('mode_segment/src/main.jsx');
  const start = main.indexOf('const SEGMENT_PROPS = {');
  const settings = vm.runInNewContext('(' + main.slice(start, main.indexOf('};', start) + 1).replace('const SEGMENT_PROPS = ', '') + ')');
  assert.deepEqual(JSON.parse(JSON.stringify(settings)), {
    trackColor: '#27272a', thumbColor: '#ffffff', textColor: '#ffffff', activeTextColor: '#18181b', size: 'lg', radius: 18,
    inset: 3, equalSlots: true, stretch: 100, squash: 3, speed: 1.4, glide: 45, draggable: true, disabled: false,
  });
});

test('the segment clicks the existing tabs and follows updateComposerMode()', () => {
  assert.ok(cabinet.includes("host._modeSegment=api.mount(mount,items,{value:active,...modeSegmentColors(host),onChange:next=>tabs[Number(next)]?.click()});"));
  assert.ok(cabinet.includes("    if (minis[miniIndex]) minis[miniIndex].classList.add('active');\n    mountModeSegment();"));
  assert.ok(cabinet.includes("EDIT_PIXEL_BASE+'js/vendor/mode-segment/mode-segment.js?v='+MODE_SEGMENT_VERSION"));
  assert.ok(read('mode_segment/src/host.css').includes('.studio-mini-tabs[data-segment] > .studio-mini-tab {\n  display: none !important;'));
});

test('light theme segment colours; old tabs and Dock panel never flash before the components', () => {
  assert.ok(cabinet.includes("const MODE_SEGMENT_LIGHT={trackColor:'#e4e4e7',thumbColor:'#18181b',textColor:'#18181b',activeTextColor:'#ffffff'};"));
  assert.ok(cabinet.includes("if (document.querySelector('#studioComposer .studio-mini-tabs')?._modeSegment) mountModeSegment();"));
  assert.ok(css.includes('.studio-mini-tabs:not([data-segment-failed])>.studio-mini-tab{visibility:hidden}'));
  assert.ok(css.includes('.studio-grid-node-tools:not([data-dock-failed]){visibility:hidden}'));
  assert.ok(cabinet.includes("host.dataset.segmentFailed='';") && cabinet.includes("panel.dataset.dockFailed='';"));
});

test('leaving Grid mounts the segment, so Pro Studio never opens without mode buttons', () => {
  assert.ok(cabinet.includes("}else{toggleStudioGridDrawer(false);unmountStudioGridSidebarHistory();mountModeSegment()}"));
});
