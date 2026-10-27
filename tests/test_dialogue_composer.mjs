// Run with: node --test tests/test_dialogue_composer.mjs
//
// Dialogues: the composer is the PromptBar - the prompt from the edge, the
// + for a new block and the fold button in the corner, the model, «Текст с
// ИИ» (the sparks rise while it is on), the mic and send. The player shows
// only after a dialogue is voiced. On wide screens the composer folds into
// a cube that sticks to the workspace edges (hover: Раскрыть /
// Сгенерировать) and the board zooms (−/+).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const js = read('webapp/js/quick-voice.js');
const css = read('webapp/css/knowledge-workspace.css');
const page = read('webapp/knowledge-workspace.html');

test('the workspace loads the new dialogue composer', () => {
  assert.match(page, /css\/knowledge-workspace\.css\?v=dialogue-pb-20261027/);
  assert.match(page, /js\/quick-voice\.js\?v=dialogue-pb-20261027/);
});

test('PromptBar composer: + and fold in the corner, model, Текст с ИИ, mic, send; no old buttons', () => {
  assert.match(js, /'<div class="qv-pb-corner"><button type="button" class="qv-pb-ic qv-pb-add" data-qv-add aria-label="Добавить блок"/);
  assert.match(js, /data-qv-collapse aria-label="Свернуть"/);
  assert.match(js, /class="qv-pb-pick qv-ai-btn" data-qv-ai aria-pressed="false">' \+ ICONS\.spark \+ '<span>Текст с ИИ<\/span>/);
  assert.match(js, /class="qv-pb-send" data-qv-generate aria-label="Сгенерировать" disabled>/);
  assert.doesNotMatch(js, /qv-composer|<span>Добавить блок<\/span>/);
  assert.doesNotMatch(css, /\.qv-composer|\.qv-add\{|\.qv-generate\{/);
});

test('Текст с ИИ starts the sparks; typing speeds them up', () => {
  assert.match(js, /if \(state\.aiMode\) startSparks\(\); else stopSparks\(\);/);
  assert.match(js, /sparks\.energy = Math\.min\(1\.6, sparks\.energy \+ 0\.22\);/);
  assert.match(css, /\.qv-pb\[data-ai\] \.qv-pb-field\{box-shadow:/);
});

test('the player shows only after a dialogue is voiced', () => {
  assert.match(js, /'<div class="qv-player" id="qvPlayer" data-empty="1" hidden>'/);
  assert.match(js, /if \(playerNode\) \{ playerNode\.dataset\.empty = '0'; playerNode\.hidden = false; \}/);
});

test('wide screens: the cube sticks to the nearest edge; hover offers Раскрыть and Сгенерировать', () => {
  assert.match(js, /const gaps = \[\[cx - b\.minX, 'left'\], \[b\.maxX - cx, 'right'\], \[cy - b\.minY, 'top'\], \[b\.maxY - cy, 'bottom'\]\]/);
  assert.match(js, /<button type="button" data-qv-expand-composer>' \+ ICONS\.expand \+ '<span>Раскрыть<\/span><\/button>'/);
  assert.match(js, /<button type="button" class="is-main" data-qv-generate>' \+ ICONS\.send \+ '<span>Сгенерировать<\/span>/);
  assert.match(css, /\.qv-cube:not\(\.is-dragging\):hover \.qv-cube-actions/);
  assert.match(css, /@media\(max-width:900px\)\{\.qv-zoom,\.qv-cube,\.qv-pb-fold\{display:none!important\}/);
});

test('wide screens: −/+ zoom the board from 70% to 150%', () => {
  assert.match(js, /const ZOOM = \{ min: 70, max: 150, step: 10 \};/);
  assert.match(js, /if \(board\) board\.style\.zoom = wide\(\) \? String\(state\.zoom \/ 100\) : '';/);
});
