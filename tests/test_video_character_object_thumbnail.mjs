// Run with: node --test tests/test_video_character_object_thumbnail.mjs
//
// Regression test for the Uploads block fix (commit e310575) and its
// follow-up correction: selecting a Character/Object for video previously
// had no thumbnail anywhere (videoState.characterVisual/objectVisual were
// set but nothing ever rendered a preview for them). renderVideoReferencesPreview()
// now also paints a thumbnail onto videoCharacterButton/videoObjectButton
// via the existing renderUploadPreviewOnButton() helper.
//
// This file proves:
//   - a live selection (applyVisualReferenceToVideo's shape, previewUrl set)
//     shows a thumbnail;
//   - a Regenerate-restored selection (restoreVideoStateFromGenerationMetadata's
//     shape - {id,name,kind,references}, NO previewUrl) still shows a
//     thumbnail, falling back to its first reference image - this is the
//     gap found during manual verification of e310575 and fixed in the
//     same pass;
//   - clearing the selection removes the thumbnail;
//   - replacing one selection with another updates the thumbnail to the
//     new one, never leaving the stale image.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

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

function makeFakeElement(tag) {
  const classes = new Set();
  const el = {
    tagName: tag,
    children: [],
    parentNode: null,
    dataset: {},
    style: {},
    get className() { return [...classes].join(' '); },
    set className(v) { classes.clear(); String(v || '').split(/\s+/).filter(Boolean).forEach((n) => classes.add(n)); },
    _html: '',
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; },
    classList: {
      add: (...names) => names.forEach((n) => classes.add(n)),
      remove: (...names) => names.forEach((n) => classes.delete(n)),
      toggle: (name, force) => {
        if (force === undefined) { classes.has(name) ? classes.delete(name) : classes.add(name); }
        else if (force) classes.add(name); else classes.delete(name);
      },
      contains: (name) => classes.has(name),
    },
    insertBefore(node, ref) {
      const idx = ref ? this.children.indexOf(ref) : -1;
      if (idx === -1) this.children.unshift(node); else this.children.splice(idx, 0, node);
      node.parentNode = this;
      return node;
    },
    appendChild(node) { this.children.push(node); node.parentNode = this; return node; },
    remove() {
      if (!this.parentNode) return;
      const i = this.parentNode.children.indexOf(this);
      if (i !== -1) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    },
    querySelector(sel) {
      const m = /^:scope > \.(.+)$/.exec(sel);
      if (!m) return null;
      return this.children.find((c) => c.classList.contains(m[1])) || null;
    },
    get firstChild() { return this.children[0] || null; },
    setAttribute() {},
  };
  return el;
}

function makeContext(videoState) {
  const elements = {};
  const document = {
    getElementById: (id) => {
      if (!elements[id]) elements[id] = makeFakeElement('button');
      return elements[id];
    },
    createElement: (tag) => makeFakeElement(tag),
  };
  const context = vm.createContext({
    document,
    videoState,
    S: { escapeHtml: (v) => String(v == null ? '' : v) },
    currentVideoReferenceUrl: () => '',
    currentVideoReferenceImages: () => [],
  });
  vm.runInContext(extractFunction('renderUploadPreviewOnButton'), context);
  vm.runInContext(extractFunction('renderVideoReferencesPreview'), context);
  return { context, elements };
}

function thumbUrl(button) {
  const bg = button.querySelector(':scope > .image-upload-control-bg');
  if (!bg) return null;
  const match = /src="([^"]*)"/.exec(bg.innerHTML);
  return match ? match[1] : null;
}

test('a live Character selection (previewUrl set) shows a thumbnail', () => {
  const videoState = { characterVisual: { id: 'c1', previewUrl: 'https://cdn/char-preview.png' }, objectVisual: null };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoCharacterButton.classList.contains('has-upload-preview'), true);
  assert.equal(thumbUrl(elements.videoCharacterButton), 'https://cdn/char-preview.png');
});

test('a Regenerate-restored Character selection (no previewUrl, only references) still shows a thumbnail', () => {
  const videoState = {
    characterVisual: { id: 'c1', name: 'Alex', kind: 'character', references: ['https://cdn/char-ref-0.png', 'https://cdn/char-ref-1.png'] },
    objectVisual: null,
  };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoCharacterButton.classList.contains('has-upload-preview'), true);
  assert.equal(thumbUrl(elements.videoCharacterButton), 'https://cdn/char-ref-0.png');
});

test('a Regenerate-restored Object selection (no previewUrl, only references) still shows a thumbnail', () => {
  const videoState = {
    characterVisual: null,
    objectVisual: { id: 'o1', name: 'Mug', kind: 'object', references: ['https://cdn/obj-ref-0.png'] },
  };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoObjectButton.classList.contains('has-upload-preview'), true);
  assert.equal(thumbUrl(elements.videoObjectButton), 'https://cdn/obj-ref-0.png');
});

test('no Character/Object selected shows no thumbnail on either button', () => {
  const videoState = { characterVisual: null, objectVisual: null };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoCharacterButton.classList.contains('has-upload-preview'), false);
  assert.equal(elements.videoObjectButton.classList.contains('has-upload-preview'), false);
});

test('clearing a selection (characterVisual set to null) removes the thumbnail', () => {
  const videoState = { characterVisual: { id: 'c1', previewUrl: 'https://cdn/char-preview.png' }, objectVisual: null };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoCharacterButton.classList.contains('has-upload-preview'), true);
  videoState.characterVisual = null;
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(elements.videoCharacterButton.classList.contains('has-upload-preview'), false);
  assert.equal(thumbUrl(elements.videoCharacterButton), null);
});

test('replacing a Character selection with a different one updates the thumbnail, not left stale', () => {
  const videoState = { characterVisual: { id: 'c1', previewUrl: 'https://cdn/first.png' }, objectVisual: null };
  const { context, elements } = makeContext(videoState);
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(thumbUrl(elements.videoCharacterButton), 'https://cdn/first.png');
  videoState.characterVisual = { id: 'c2', previewUrl: 'https://cdn/second.png' };
  vm.runInContext('renderVideoReferencesPreview()', context);
  assert.equal(thumbUrl(elements.videoCharacterButton), 'https://cdn/second.png');
  assert.equal(elements.videoCharacterButton.children.filter((c) => c.classList.contains('image-upload-control-bg')).length, 1);
});
