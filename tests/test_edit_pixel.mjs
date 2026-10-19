// Run with: node --test tests/test_edit_pixel.mjs
//
// Edit workspace: the empty canvas' photo upload block as the React Bits
// PixelCard (edit_pixel/ -> webapp/js/vendor/edit-pixel, mounted by
// cabinet.js). Covers: the component is the published one, unmodified; the
// task's settings; that the upload button itself moves inside the card (its
// click and the workspace drop target unchanged); and that the card goes
// away with the block once a photo is on the canvas.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');
const cabinet = read('webapp/js/cabinet.js');

test('PixelCard.jsx / PixelCard.css: the published files, unmodified', () => {
  // `npx shadcn@latest add @react-bits/PixelCard-JS-CSS`
  assert.equal(sha256('edit_pixel/src/PixelCard.jsx'), 'e442796748a563c792eff90a8bf2b816ea99726877e7c31ba6a086ab7547ee00');
  assert.equal(sha256('edit_pixel/src/PixelCard.css'), 'aa76b07b6bf13f74443b28afb18242261e6ad07559f8a7e3110fb2fe794bf5a5');
  const bundle = read('webapp/js/vendor/edit-pixel/edit-pixel.js');
  assert.ok(bundle.includes('SylvexEditPixel') && bundle.includes('pixel-card-canvas'));
  assert.ok(existsSync(new URL('../webapp/js/vendor/edit-pixel/edit-pixel.css', import.meta.url)));
  assert.ok(read('.gitignore').includes('edit_pixel/node_modules/'));
});

test('the card runs with the settings from the task', () => {
  const main = read('edit_pixel/src/main.jsx');
  const start = main.indexOf('const PIXEL_PROPS = {');
  const block = main.slice(start, main.indexOf('};', start) + 1);
  const settings = vm.runInNewContext('(' + block.replace('const PIXEL_PROPS = ', '') + ')');
  assert.deepEqual(JSON.parse(JSON.stringify(settings)), {
    colors: ['#00fd50', '#00fd50', '#00fd50'], glowColor: '#10b945', shape: 'circle', origin: 'center', gap: 5,
    pixelSize: 2, speed: 35, revealDuration: 600, spotlight: 0.5, glow: 0.5, opacity: 0.7, fade: 0.7,
    trigger: 'hover', radius: 24, clickPulse: true, intro: true, theme: 'light',
  });
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

test('the upload button moves inside the card; the card goes with the block', () => {
  const sync = extract('syncEditWorkspaceChain');
  assert.ok(sync.includes('<div class="edit-workspace-upload-host"><button class="edit-workspace-upload" type="button" onclick="document.getElementById(\\\'editWorkspaceFile\\\').click()">'), 'same button, same click');
  assert.ok(sync.includes('Upload a photo or drop it here') && sync.includes('JPEG, PNG, WebP · up to 50 MB'));
  assert.ok(sync.includes('mountEditUploadPixel(world);\n    return;'));
  assert.ok(sync.includes('removeEditUploadPixel(world);'));
  const mount = extract('mountEditUploadPixel');
  assert.ok(mount.includes('host._editPixel=api.mount(mount,button,{theme:studioSurfaceTheme(host,\'--edit-surface\')});'));
  assert.ok(!/fetch\(|onEditWorkspaceFile|editWorkspaceState/.test(mount), 'display only');
  assert.ok(extract('removeEditUploadPixel').includes('host._editPixel?.unmount();host.remove();'));
  assert.ok(cabinet.includes("root.ondrop=e=>{e.preventDefault();root.classList.remove('is-dragging');if(!editWorkspaceLocked())onEditWorkspaceFile("), 'drop target unchanged');
});

test('light / dark follows Pro Studio; bundle next to cabinet.js, on demand only', () => {
  assert.ok(extract('studioSurfaceTheme').includes("?'light':'dark'"));
  assert.ok(cabinet.includes("const editWorld = document.querySelector('#editWorkspace .edit-workspace-world');\n    if (editWorld && typeof mountEditUploadPixel === 'function') mountEditUploadPixel(editWorld);"));
  assert.ok(cabinet.includes("EDIT_PIXEL_BASE+'js/vendor/edit-pixel/edit-pixel.js?v='+EDIT_PIXEL_VERSION"));
  assert.ok(!read('webapp/index.html').includes('vendor/edit-pixel'));
  assert.match(read('webapp/css/cabinet.css'), /\.edit-workspace-world>\.edit-workspace-upload-host\{position:absolute;left:0;top:0;width:min\(760px,82vw\);height:min\(620px,76vh\);transform:translate\(-50%,-50%\)\}/);
});
