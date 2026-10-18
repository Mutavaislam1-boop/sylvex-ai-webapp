// Run with: node --test tests/test_studio_ref_stack.mjs
//
// Pro Studio: a generation's reference images shown as the React Bits Stack
// (studio_stack/ -> webapp/js/vendor/ref-stack, mounted by cabinet.js).
// Covers: the component is the published one with only the demo images
// removed; the task's settings; one card per reference, in the request's
// order; where the stack replaces the previous display; and that it is
// display only, isolated and switchable off.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const sha256 = (path) => createHash('sha256').update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex');
const cabinet = read('webapp/js/cabinet.js');

test('Stack.jsx / Stack.css: the published files, only the demo images removed', () => {
  // `npx shadcn@latest add @react-bits/Stack-JS-CSS`, with DEFAULT_IMAGES
  // emptied as in the task's source (no Unsplash demo photos).
  assert.equal(sha256('studio_stack/src/Stack.jsx'), '12bf68964660e2e70a0e3938f1bf3ca20a05b86237d1b047c4e9f1cd8dcb9558');
  assert.equal(sha256('studio_stack/src/Stack.css'), 'a399d752bfe72accf6cc10a264ef984e98d3109f358bd2a680aa6819e4698338');
  const jsx = read('studio_stack/src/Stack.jsx');
  assert.ok(jsx.includes('const DEFAULT_IMAGES = [\n ];') && !jsx.includes('unsplash'));
  assert.ok(jsx.includes("from 'motion/react'"));
  assert.equal(JSON.parse(read('studio_stack/package.json')).dependencies.motion, '12.23.12');
  const bundle = read('webapp/js/vendor/ref-stack/ref-stack.js');
  assert.ok(bundle.includes('SylvexRefStack') && bundle.includes('stack-card-face'));
  assert.ok(existsSync(new URL('../webapp/js/vendor/ref-stack/ref-stack.css', import.meta.url)));
  assert.ok(read('.gitignore').includes('studio_stack/node_modules/'));
});

test('the stack runs with the settings from the task; cards and visible come from the references', () => {
  const main = read('studio_stack/src/main.jsx');
  const start = main.indexOf('const STACK_PROPS = {');
  const block = main.slice(start, main.indexOf('};', start) + 1);
  const settings = vm.runInNewContext('(' + block.replace('const STACK_PROPS = ', '') + ')');
  assert.deepEqual({...settings}, {
    layout: 'fan', sendToBackOnClick: true, spread: 0.8, depth: 0.5, radius: 33, frame: 0, frameColor: '#ffffff',
    shadow: true, tilt: 30, threshold: 90, speed: 1, autoplay: false, autoplayDelay: 3000, pauseOnHover: false,
  });
  assert.ok(main.includes('cards: list.map((src, index) =>'));
  assert.ok(main.includes('visible: list.length'));
});

function extract(name) {
  const start = cabinet.indexOf(`  function ${name}(`);
  assert.ok(start > 0, name);
  let depth = 0;
  for (let i = cabinet.indexOf('{', start); i < cabinet.length; i++) {
    if (cabinet[i] === '{') depth++;
    else if (cabinet[i] === '}' && --depth === 0) return cabinet.slice(start, i + 1);
  }
  throw new Error('unbalanced ' + name);
}

test('one card per reference the request used, in its order, no duplicates or extras', () => {
  const context = vm.createContext({S: {escapeHtml: (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}});
  vm.runInContext('const REF_STACK_ENABLED = true;' + ['requestImageReferences', 'requestImageDisplayReferences', 'renderReferencePile', 'renderReferenceStack'].map(extract).join('\n')
    + ';globalThis.api = {requestImageDisplayReferences, renderReferenceStack};', context);
  const {requestImageDisplayReferences, renderReferenceStack} = context.api;
  const urls = (n) => Array.from({length: n}, (_, i) => `https://cdn.example/r${i + 1}.jpg`);
  for (const n of [1, 2, 5, 10]) {
    const all = urls(n);
    const meta = {type: 'image', image_options: {referenceImageUrls: all.slice(0, Math.ceil(n / 2)), characterReferences: all.slice(Math.ceil(n / 2), n - (n > 2 ? 1 : 0)), objectReferences: n > 2 ? all.slice(n - 1) : []}};
    const refs = requestImageDisplayReferences(meta);
    assert.deepEqual(Array.from(refs), all, `${n} references, request order`);
    const html = renderReferenceStack(refs, 'r7');
    const slot = /data-ref-urls="([^"]*)"/.exec(html);
    assert.deepEqual(JSON.parse(slot[1].replace(/&quot;/g, '"')), all);
    assert.ok(html.includes('data-ref-stack="r7"'));
    assert.equal((html.match(/class="msg-ref-img"/g) || []).length, n, 'fallback pile inside');
  }
  assert.equal(renderReferenceStack([], 'r1'), '', 'no references, no stack');
});

test('the stack replaces the reference group in the workspace, and shows from the moment Generate is pressed', () => {
  assert.ok(cabinet.includes("renderReferenceRequest(refs, userPrompt, 'r' + i)"));
  assert.ok(cabinet.includes("renderReferenceRequest(resultRefs, requestPromptIsInternal(next.metadata) ? '' : String(m.text || ''), 'r' + (i + 1))"));
  assert.ok(cabinet.includes("renderReferenceRequest(pendingRefs, '', 'r' + i)"), 'while generating, keyed like its result');
  assert.ok(cabinet.includes("? renderReferenceStack(m.referenceImages, 'u' + i)"));
  const send = cabinet.slice(cabinet.indexOf('      loadingIndex = appendPendingGenerationPlaceholder();\n      // The workspace shows'), cabinet.indexOf('    } else if (!uploadOnlyVoice) {'));
  assert.ok(send.includes("requestImageDisplayReferences({ type: 'image', image_options: imageOptionsSnapshot })"));
  assert.ok(send.includes('chatMessages[loadingIndex].requestReferences = pendingRefs;'));
  assert.ok(cabinet.includes('    mountReferenceStacks(el);\n    el.scrollTop = el.scrollHeight;'));
});

test('display only and isolated: request untouched, events contained, switchable off, works from the Website', () => {
  const mount = extract('mountReferenceStacks');
  assert.ok(!/chatMessages|imageState|fetch\(/.test(mount), 'never reads or writes the request');
  assert.ok(mount.includes("['pointerdown', 'mousedown', 'touchstart', 'click', 'dblclick', 'contextmenu'].forEach"));
  assert.ok(mount.includes('slot.replaceChildren(entry.holder);'), 'the same live stack is reused across re-renders');
  assert.ok(cabinet.includes('  const REF_STACK_ENABLED = true;'));
  const stack = extract('renderReferenceStack');
  assert.ok(stack.includes('if (!REF_STACK_ENABLED || !key) return renderReferencePile(refs);'));
  assert.ok(cabinet.includes("const match = script && script.src ? /^(.*\\/)js\\/cabinet\\.js(?:[?#].*)?$/.exec(script.src) : null;"));
  assert.ok(!read('webapp/index.html').includes('vendor/ref-stack'), 'loaded on demand only');
  assert.match(read('webapp/css/cabinet.css'), /\.msg-ref-stack\{\n {2}position:relative !important;/);
});
