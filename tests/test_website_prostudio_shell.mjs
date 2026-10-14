import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const css = fs.readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const js = fs.readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

test('website Pro Studio removes the Mini App shell and floating assistant only in web embed mode', () => {
  assert.match(css, /html\.web-embed \.view\[data-view="tools"\] \.studio-bar,/);
  assert.match(css, /html\.web-embed #histDrawer,/);
  assert.match(css, /html\.web-embed #histBackdrop,/);
  assert.match(css, /html\.web-embed #aiAssistantFab,/);
  assert.match(css, /html\.web-embed #aiAssistantModal,/);
  assert.match(js, /if \(isWebEmbed\(\)\) \{\s*fab\.remove\(\);/);
});

test('website classic Pro Studio uses a clean background while Grid Mode stays independent', () => {
  assert.match(css, /html\.web-embed \.view\[data-view="tools"\]\.active \.studio:not\(\.grid-mode\)::before,/);
  assert.match(css, /html\.web-embed \.view\[data-view="tools"\]\.active \.studio:not\(\.grid-mode\) \.chat-area\{\s*background-color:var\(--st-bg\)!important;\s*background-image:none!important;/);
});

test('website option panels are positioned from the clicked control', () => {
  assert.match(js, /function positionWebsiteStudioPopover\(el, anchorRect\)/);
  assert.match(js, /const centeredLeft = anchorRect\.left \+ \(anchorRect\.width \/ 2\) - \(panelWidth \/ 2\)/);
  assert.match(js, /const above = anchorRect\.top - panelHeight - gap/);
  assert.match(js, /requestAnimationFrame\(\(\) => positionWebsiteStudioPopover\(document\.getElementById\('modelPop'\), websiteAnchorRect\)\)/);
});

test('website Pro Studio forces English UI text without changing the Mini App language setting', () => {
  assert.match(js, /const language = \(\) => \{\s*if \(isWebEmbed\(\)\) return 'en';/);
  assert.match(js, /return isWebEmbed\(\) \? 'en' : \(localStorage\.getItem\('sylvex-lang'\)/);
  assert.match(js, /const WEBSITE_STUDIO_ENGLISH = Object\.freeze/);
  assert.match(js, /'Соотношение сторон':'Aspect ratio'/);
  assert.match(js, /initWebsiteProStudioUi\(\);/);
});

test('model picker text follows Pro Studio theme tokens in white theme', () => {
  assert.match(css, /\.image-model-name\{\s*color:var\(--st-text, #f3f3f3\)/);
  assert.match(css, /\.image-model-desc\{\s*color:var\(--st-dim, #8d8d92\)/);
  assert.match(css, /\.image-model-check\{[\s\S]*?color:var\(--st-text, #f3f3f3\)/);
});
