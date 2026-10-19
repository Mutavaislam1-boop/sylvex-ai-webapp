// Run with: node --test tests/test_grid_profile_card.mjs
//
// Grid Mode nodes in the React Bits ProfileCard style: the frame / tile /
// footer structure, the card's tilt (tiltStrength 3, intro, mouse only) on
// the frame only, and the old node visuals removed rather than overridden.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const cabinet = read('webapp/js/cabinet.js');
const css = read('webapp/css/cabinet.css');

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

test('every node renders as frame > tile + footer, ports outside the frame', () => {
  const render = extract('renderStudioGrid');
  assert.ok(render.includes('<button class="studio-grid-port out side-bottom" type="button" data-grid-output="${outputPort}" data-grid-side="bottom" aria-label="Подключить выход снизу"></button>\n        <div class="studio-grid-node-card"><div class="studio-grid-node-tile"><header class="studio-grid-node-header">'));
  assert.ok(render.includes('<div class="studio-grid-node-result">${preview}</div></div></div>\n        <footer class="studio-grid-node-footer"><div class="studio-grid-node-meta"><span class="studio-grid-node-status">'));
  assert.ok(render.includes('</footer><span class="studio-grid-node-rim" aria-hidden="true"></span></div>\n      </article>'));
  // Same handlers' hooks as before.
  for (const hook of ['data-grid-expand-text', 'data-grid-delete', 'data-grid-prompt', 'data-grid-build', 'data-grid-run', 'data-grid-more'])
    assert.ok(render.includes(hook), hook);
  assert.ok(render.includes('paintStudioGridCards(state);'));
});

test('the card tilt: 3deg, the card spring, intro, mouse only, frame only', () => {
  assert.ok(cabinet.includes('const GRID_CARD_TILT=3;'));
  const tick = extract('gridCardTick');
  assert.ok(tick.includes('stiffness=slow?24:120,damping=slow?9:16'));
  const move = extract('onStudioGridCardMove');
  assert.ok(move.includes("if(event.pointerType!=='mouse'||gridCardReduced())return;"));
  assert.ok(move.includes('event.buttons?null:'), 'rests while dragging or panning');
  assert.ok(extract('paintStudioGridCards').includes('{x:{p:.62,v:0,target:0},y:{p:-.55,v:0,target:0},slowUntil:performance.now()+1400}'));
  assert.ok(extract('gridCardWrite').includes(".studio-grid-node-card');"));
  assert.ok(cabinet.includes("canvas.addEventListener('pointermove',onStudioGridCardMove);canvas.addEventListener('pointerleave',onStudioGridCardLeave);"));
  assert.match(css, /\.studio-grid-node-card\{[^}]*transform:var\(--pc-transform,none\)\}/);
});

test('the card tokens (dark, and light on the white theme); old node visuals are gone', () => {
  assert.ok(css.includes('.studio-grid-node{--pc-radius:15px;--pc-frame:rgba(38,35,46,.66);'));
  assert.ok(css.includes('.studio[data-ps-theme="white"] .studio-grid-node{--pc-frame:rgba(240,240,243,.8);'));
  for (const gone of [
    '.view[data-view="tools"].active .studio-grid-node{border',
    '.view[data-view="tools"].active .studio-grid-node-footer button{',
    '.view[data-view="tools"].active .studio-grid-node textarea{',
    '.view[data-view="tools"].active .studio-grid-node[data-status="RUNNING"]{border-color',
    'background:#1b1c20;box-shadow:0 18px 44px rgba(0,0,0,.35)',
    'font:500 10px/1.45 inherit',
  ]) assert.ok(!css.includes(gone), gone);
});
