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

function introHarness({reduced = false, rejectPlay = false} = {}) {
  const context = vm.createContext({
    INTRO_LAST_FRAME: 'assets/auth/sylvex-intro-v2-poster.jpg',
    window: {matchMedia: () => ({matches: reduced})},
  });
  vm.runInContext(source.slice(source.indexOf('  let introPlayed = false;'), source.indexOf('  function runIntroVideo(')) + extract('runIntroVideo') + '\n;globalThis.runIntroVideo = runIntroVideo;', context);
  const makeVideo = () => ({
    plays: 0, paused: true, loop: true, controls: true, muted: false, poster: '', preload: 'auto',
    play() { this.plays++; this.paused = false; return rejectPlay ? Promise.reject(new Error('NotAllowed')) : Promise.resolve(); },
    pause() { this.paused = true; },
  });
  return {context, makeVideo};
}

test('the intro plays once, never loops, and stays on its last frame', () => {
  const {context, makeVideo} = introHarness();
  const video = makeVideo();
  const stop = context.runIntroVideo(video);
  assert.equal(video.plays, 1);
  assert.equal(video.loop, false);
  assert.equal(video.controls, false);
  assert.equal(video.muted, true);
  assert.ok(!source.slice(source.indexOf('function runIntroVideo('), source.indexOf('// Google Identity Services')).includes("'ended'"),
    'nothing restarts it when it ends: the ended video keeps showing its last frame');
  stop();
  assert.equal(video.paused, true);
});

test('reopening the screen in the same page load shows the last frame, not the animation again', () => {
  const {context, makeVideo} = introHarness();
  context.runIntroVideo(makeVideo());
  const again = makeVideo();
  context.runIntroVideo(again);
  assert.equal(again.plays, 0);
  assert.equal(again.poster, 'assets/auth/sylvex-intro-v2-poster.jpg');
});

test('reduced motion or a refused autoplay keep the last frame as a still', async () => {
  const reduced = introHarness({reduced: true});
  const still = reduced.makeVideo();
  reduced.context.runIntroVideo(still);
  assert.equal(still.plays, 0);
  assert.equal(still.poster, 'assets/auth/sylvex-intro-v2-poster.jpg');
  const refused = introHarness({rejectPlay: true});
  const video = refused.makeVideo();
  refused.context.runIntroVideo(video);
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(video.poster, 'assets/auth/sylvex-intro-v2-poster.jpg');
});

test('the video markup has no player UI and no loop', () => {
  const markup = source.slice(source.indexOf('<video class="sxAuth-video"'), source.indexOf('</video>'));
  assert.ok(markup.includes(' muted') && markup.includes(' playsinline') && markup.includes('disablepictureinpicture'));
  assert.ok(!/\bcontrols\b/.test(markup) && !/\bloop\b/.test(markup) && !/\bautoplay\b/.test(markup));
  assert.ok(markup.includes('assets/auth/sylvex-intro-v2.mp4') && markup.includes('assets/auth/sylvex-intro-v2.webm'));
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
