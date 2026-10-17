// Standalone browser Mini App sign-in screen (openBrowserAuthScreen in
// webapp/js/account-auth.js): the intro video plays once, holds for 5 s and
// plays again (never a plain loop), sign-up goes through the emailed-code
// endpoints, and only the standalone browser gets this screen.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/account-auth.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/browser-auth.css', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/index.html', import.meta.url), 'utf8');

function extract(name) {
  const start = source.indexOf(`  function ${name}(`);
  assert.ok(start > 0, name);
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error('unbalanced ' + name);
}

function introHarness({reduced = false} = {}) {
  const timers = [];
  const listeners = {};
  const video = {
    plays: 0, paused: true, currentTime: 3, loop: true, controls: true, muted: false,
    play() { this.plays++; this.paused = false; this.currentTime = 0; return Promise.resolve(); },
    pause() { this.paused = true; },
    addEventListener(type, fn) { listeners[type] = fn; },
    removeEventListener(type) { delete listeners[type]; },
  };
  const docListeners = {};
  const context = vm.createContext({
    INTRO_PAUSE_MS: 5000,
    window: {matchMedia: () => ({matches: reduced})},
    document: {hidden: false, addEventListener(t, fn) { docListeners[t] = fn; }, removeEventListener(t) { delete docListeners[t]; }},
    setTimeout(fn, ms) { timers.push({fn, ms}); return timers.length; },
    clearTimeout(id) { if (id && timers[id - 1]) timers[id - 1].cleared = true; },
  });
  vm.runInContext(extract('runIntroVideo') + '\n;globalThis.runIntroVideo = runIntroVideo;', context);
  const stop = context.runIntroVideo(video);
  return {video, timers, listeners, docListeners, stop, context};
}

test('the intro plays once, waits 5 seconds after it ends, then plays again', () => {
  const {video, timers, listeners} = introHarness();
  assert.equal(video.plays, 1);
  assert.equal(video.loop, false);
  assert.equal(video.controls, false);
  assert.equal(video.muted, true);
  video.paused = true;
  listeners.ended();
  assert.equal(timers.length, 1);
  assert.equal(timers[0].ms, 5000);
  assert.equal(video.plays, 1, 'no replay before the pause is over');
  timers[0].fn();
  assert.equal(video.plays, 2);
  assert.equal(video.currentTime, 0);
  listeners.ended();
  assert.equal(timers[1].ms, 5000);
});

test('closing the screen stops the cycle', () => {
  const {video, timers, listeners, stop, docListeners} = introHarness();
  listeners.ended();
  stop();
  assert.equal(timers[0].cleared, true);
  assert.equal(video.paused, true);
  assert.equal(listeners.ended, undefined);
  assert.equal(docListeners.visibilitychange, undefined);
});

test('a hidden tab pauses the cycle and resumes when visible again', () => {
  const {video, timers, listeners, docListeners, context} = introHarness();
  listeners.ended();
  context.document.hidden = true;
  docListeners.visibilitychange();
  assert.equal(timers[0].cleared, true);
  context.document.hidden = false;
  docListeners.visibilitychange();
  const resume = timers[timers.length - 1];
  assert.ok(!resume.cleared && resume.ms < 5000);
  resume.fn();
  assert.equal(video.plays, 2);
});

test('reduced motion keeps the still poster', () => {
  const {video, timers} = introHarness({reduced: true});
  assert.equal(video.plays, 0);
  assert.equal(timers.length, 0);
});

test('the video markup has no player UI and no loop', () => {
  const markup = source.slice(source.indexOf('<video class="sxAuth-video"'), source.indexOf('</video>'));
  assert.ok(markup.includes(' muted') && markup.includes(' playsinline') && markup.includes(' autoplay'));
  assert.ok(markup.includes('disablepictureinpicture') && markup.includes('poster="assets/auth/sylvex-intro-poster.jpg"'));
  assert.ok(!/\bcontrols\b/.test(markup) && !/\bloop\b/.test(markup));
  assert.ok(markup.includes('assets/auth/sylvex-intro.mp4') && markup.includes('assets/auth/sylvex-intro.webm'));
  assert.match(css, /\.sxAuth-video::-webkit-media-controls/);
});

test('sign-up goes through the emailed code, never straight to an account', () => {
  const screen = source.slice(source.indexOf('function openBrowserAuthScreen('), source.indexOf('S.closeBrowserAuthScreen'));
  for (const path of ['/api/web/auth/register/start', '/api/web/auth/register/verify', '/api/web/auth/register/resend', '/api/web/auth/login', '/api/web/auth/google']) {
    assert.ok(screen.includes(`'${path}'`), path);
  }
  assert.ok(!screen.includes("'/api/web/auth/register'"));
  assert.ok(screen.includes('autocomplete="one-time-code"'));
});

test('only the standalone browser gets the full-screen page; the footer links to the website', () => {
  assert.match(source, /if \(S\.isBrowserApp && S\.isBrowserApp\(\)\) \{ openBrowserAuthScreen\(\); return; \}/);
  for (const href of ['${WEBSITE_URL}/legal/privacy.html', '${WEBSITE_URL}/legal/terms.html', '${WEBSITE_URL}/']) {
    assert.ok(source.includes(`href="${href}" target="_blank" rel="noopener"`), href);
  }
  assert.ok(source.includes("const WEBSITE_URL = 'https://sylvex.ai';"));
  assert.ok(source.includes('© ${year} SYLVEX. All rights reserved.'));
  assert.ok(html.includes('css/browser-auth.css'));
});

test('Google uses the official rendered button, initialized once', () => {
  assert.match(source, /renderButton\(host, \{[^}]*text: 'continue_with'/);
  const init = extract('initGoogleOnce');
  assert.ok(init.includes('if (googleInitFor === clientId) return;'));
});
