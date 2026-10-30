// Run with: node --test tests/test_home_animated_content.mjs
//
// The home screen comes in like AnimatedContent: each marked block rises
// 100px into place and fades in (0.8 s, power3.out) when its top passes 85%
// of the screen, once; a stagger group's children come in turn, 80 ms apart.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const js = read('webapp/js/animated-content.js');
const index = read('webapp/index.html');
const html = read('webapp/cabinet.html');
const home = html.slice(html.indexOf('<section class="view active" data-view="home">'), html.indexOf('<section class="view" data-view="tools">'));

test('the AnimatedContent settings: 100px, 0.8 s, power3.out, 80 ms apart, at 85% of the screen', () => {
  assert.match(js, /var DISTANCE = 100, DURATION = 800, STAGGER = 80, THRESHOLD = 0\.15;/);
  assert.match(js, /var EASE = 'cubic-bezier\(0\.165, 0\.84, 0\.44, 1\)'; \/\/ power3\.out/);
  assert.match(js, /\{ translate: '0 ' \+ DISTANCE \+ 'px', opacity: 0 \},\n\s+\{ translate: '0 0', opacity: 1 \}/);
  assert.match(js, /\{ rootMargin: '0px 0px -' \+ THRESHOLD \* 100 \+ '% 0px' \}/);
  assert.match(js, /observer\.unobserve\(entry\.target\);/);
});

test('nothing hides with reduced motion or without the browser features', () => {
  assert.match(js, /if \(global\.matchMedia && global\.matchMedia\('\(prefers-reduced-motion: reduce\)'\)\.matches\) return;/);
  assert.match(js, /if \(!global\.IntersectionObserver \|\| !global\.Element \|\| !Element\.prototype\.animate\) return;/);
});

test('the Mini App loads it in <head>, before the home is drawn', () => {
  const head = index.slice(0, index.indexOf('</head>'));
  assert.match(head, /<script src="js\/animated-content\.js\?v=animated-content-20261027"><\/script>/);
  assert.match(index, /fetch\('cabinet\.html\?v=admin-c-20261029'\)/);
});

test('the home blocks are marked; card rows and the FAQ come in turn', () => {
  for (const block of ['<div class="user-card" data-animated-content>', '<section class="home-idea-ai" id="homeIdeaAi" data-animated-content>',
    '<div class="hero-carousel" data-animated-content>']) assert.ok(home.includes(block), block);
  assert.equal(home.split('<div class="section-title" data-animated-content>').length - 1, 3);
  for (const group of ['class="home-socials" aria-label="Follow us" data-animated-content="stagger"', 'id="homeHist" data-animated-content="stagger"',
    'id="homeTools" data-animated-content="stagger"', 'aria-labelledby="homeFaqTitle" data-animated-content="stagger"']) assert.ok(home.includes(group), group);
});
