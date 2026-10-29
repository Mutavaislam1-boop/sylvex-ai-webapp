// Run with: node --test tests/test_home_reference_composer.mjs
//
// Home composer (PromptBar): one layer - the prompt from the edge, then +,
// the Video / Photo switch, the mic and send; the quick tools as small
// icons below. Tapping into the prompt opens Motion repeat / Photo from
// reference over the composer (js/reference-panel.js, the same file as the
// website's); a picked reference plus the user's photo runs that
// reference's own generation. Quick tools open over the current screen.
// Pro Studio on wide screens: the photo and video catalogs open in the
// workspace; the photo catalog is one list without tabs.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const panel = read('webapp/js/reference-panel.js');
const panelCss = read('webapp/css/reference-panel.css');
const js = read('webapp/js/cabinet.js');
const css = read('webapp/css/cabinet.css');
const html = read('webapp/cabinet.html');
const index = read('webapp/index.html');

test('the Mini App loads the reference panel with fresh pins', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/reference-panel\.css\?v=ref-panel-20261027" \/>/);
  assert.match(index, /<script src="js\/reference-panel\.js\?v=ref-panel-20261027"><\/script>/);
  assert.match(index, /<link rel="stylesheet" href="css\/cabinet\.css\?v=tz3-20261029" \/>/);
  assert.match(index, /<script src="js\/cabinet\.js\?v=tz3-20261029"><\/script>/);
});

test('the composer: prompt first, then +, Video / Photo (video by default), mic, send; tools below', () => {
  assert.match(html, /<form class="home-idea-field" id="homeIdeaForm">\n\s+<div class="home-idea-refs" id="homeIdeaRefs" hidden><\/div>\n\s+<textarea id="homeIdeaInput"/);
  assert.match(html, /<button type="button" class="on" data-home-idea-mode="video" aria-pressed="true" aria-label="Видео">/);
  assert.match(html, /<button type="button" data-home-idea-mode="photo" aria-pressed="false" aria-label="Фото">/);
  assert.match(html, /<button type="button" id="homeIdeaVoice" class="voice" aria-label="Голосовой ввод">/);
  assert.match(html, /<nav class="home-idea-tools" id="homeIdeaTools" aria-label="Быстрые инструменты"><\/nav>/);
  assert.doesNotMatch(html, /home-idea-attachment/);
  assert.match(css, /\.home-idea-field\{display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:16px;background:var\(--home-idea-bg\);cursor:text\}/);
  assert.match(css, /\.home-idea-tools button span\{display:grid;place-items:center;width:38px;height:38px;border-radius:11px;/);
});

test('only tapping into the prompt opens the panel: Motion repeat or Photo from reference, 3 columns, 2 rows', () => {
  assert.match(js, /const HOME_IDEA_PANEL_TITLES = \{ video: 'Повтор движения', photo: 'Фото по референсу' \};/);
  assert.match(js, /input\?\.addEventListener\('focus', openHomeIdeaPanel\);/);
  assert.match(js, /anchor: field, layout: 'grid', cols: 3, rows: 2, closeLabel: 'Закрыть'/);
  assert.match(js, /'<button type="button" class="home-idea-upload" data-home-idea-upload><span>＋<\/span>Загрузите любое изображение<\/button>'/);
});

test('a reference + the photo runs that reference\'s own generation; otherwise the router as before', () => {
  assert.match(js, /\? \{ kind: 'video_template', itemId: ref\.id, upload, aspect: ref\.aspect \}\n\s+: \{ kind: 'image', itemId: ref\.id, upload \};/);
  assert.match(js, /if \(!await runMediaGeneration\(request\)\) return;/);
  assert.match(js, /if \(homeIdeaRef\) generateHomeIdeaRef\(\); else sendHomeIdea\(\);/);
  assert.match(js, /async function runMediaGeneration\(request\) \{/);
  assert.match(js, /const url = await uploadProStudioMediaFile\(file, 'image'\);/);
});

test('the mic types speech into the prompt', () => {
  assert.match(js, /const response = await fetch\('\/api\/public\/prostudio\/transcribe', \{ method: 'POST', body \}\);/);
});

test('quick tools open over the current screen and show their result there', () => {
  assert.doesNotMatch(js, /if \(!document\.querySelector\('\.view\[data-view="tools"\]\.active'\)\) switchView\('tools'\);\n\s+\/\/ Only remember the mode/);
  assert.match(js, /photoToolInPlace = !document\.querySelector\('\.view\[data-view="tools"\]\.active'\);/);
  assert.match(js, /if \(inPlaceResult && inPlaceResult\.length\) openImageViewer\(null, inPlaceResult\[0\], inPlaceResult\);/);
  assert.match(js, /if \(route\.mode === 'tool' && route\.tool\) \{\n\s+openPhotoToolModal\(null, route\.tool\);/);
});

test('the panel rises from the composer, keeps it usable, stays open on a pick and closes by ×, shade or Esc', () => {
  assert.match(panel, /var height = Math\.max\(0, box\.top - EDGE - top\);/);
  assert.match(panel, /state\.shade\.style\.clipPath = holePath\(box,/);
  assert.match(panel, /select\(id\);\n\s+if \(typeof state\.opts\.onPick === 'function'\) state\.opts\.onPick\(item\);/);
  assert.match(panel, /if \(event\.key === 'Escape' && state\) \{ event\.preventDefault\(\); close\(\); \}/);
  assert.match(panel, /shade\.addEventListener\('click', function \(\) \{ close\(\); \}\);/);
  assert.match(panel, /clipPath: 'inset\(100% 0 0 0 round 22px\)', translate: '0 14px' \}/);
  assert.match(panelCss, /\.ref-panel\{position:fixed;z-index:2147480001;/);
});

test('Pro Studio: one photo catalog without tabs or Tools', () => {
  assert.doesNotMatch(js, /photoCatalogTabs|selectPhotoCatalogSection|openPhotoCatalogTool|'Инструменты'\]/);
  assert.match(js, /const PHOTO_CATALOG_SECTIONS = \['references', 'styles', 'popular_references', 'objects'\];/);
  assert.doesNotMatch(css, /\.photo-catalog-tabs|\.photo-catalog-tool-card/);
});

test('Pro Studio wide: catalogs in the workspace, 6 and 7 columns, a still transparent ×', () => {
  assert.match(js, /if \(!window\.matchMedia\('\(min-width: 1000px\)'\)\.matches\) return null;/);
  assert.match(js, /watchCatalogWorkspace\(modal, modal\.querySelector\('\.photo-catalog-dialog'\), modal\.querySelector\('\.photo-tool-head button'\)\);/);
  assert.match(js, /watchCatalogWorkspace\(overlay, overlay\.querySelector\('\.video-templates-panel'\), closeBtn\);/);
  assert.match(css, /\.catalog-in-workspace #photoCatalogGrid\{column-count:6\}/);
  assert.match(css, /\.catalog-in-workspace:not\(\.kling-effects-overlay\) \.video-templates-grid\{column-count:7\}/);
  assert.match(css, /\.catalog-in-workspace>\.catalog-workspace-close\{position:fixed!important;[^}]*background:transparent!important;box-shadow:none!important;/);
  assert.match(css, /\.catalog-in-workspace:is\(\.photo-catalog-modal,\.video-templates-overlay\)\{background:transparent!important;[^}]*pointer-events:none\}/);
});
