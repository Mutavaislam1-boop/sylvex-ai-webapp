// Mobile Standard interface of Pro Studio (js/standard-studio.js): a new face
// on phones wired to the existing Pro Studio logic through SYLVEX.studioBridge.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const js = read('../webapp/js/standard-studio.js');
const css = read('../webapp/css/standard-studio.css');
const cabinet = read('../webapp/js/cabinet.js');
const index = read('../webapp/index.html');

test('Standard is loaded by the Mini App', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/standard-studio\.css\?v=[^"]+" \/>/);
  assert.match(index, /<script src="js\/standard-studio\.js\?v=[^"]+"><\/script>/);
});

test('phones only: Standard by default, Pro is the existing interface', () => {
  assert.match(js, /matchMedia\('\(max-width: 767px\)'\)/);
  assert.match(js, /localStorage\.getItem\(STORE_KEY\) === 'pro' \? 'pro' : 'standard'/);
  assert.match(js, /body\.classList\.toggle\('sxs-std', std\)/);
  // Every Standard rule is scoped to phones; tablets and wider are untouched.
  css.split('}').map((rule) => rule.split('{')[0].trim()).filter((sel) => sel && !sel.startsWith('/*') && !sel.startsWith('@'))
    .forEach((sel) => {
      sel.split(',').map((part) => part.replace(/\/\*[\s\S]*?\*\//g, '').trim()).filter(Boolean).forEach((part) => {
        assert.ok(/body\.sxs-(phone|std|params-open|sheet-open)|^\.sxs-|^\.photo-tool-icon/.test(part), 'unscoped rule: ' + part);
      });
    });
});

test('header: SYLVEX + Standard | Pro, no new-chat pencil; Pro keeps "SYLVEX Pro"', () => {
  assert.match(js, /<span class="sxs-brand">SYLVEX<\/span>/);
  assert.match(js, />Standard<\/button><button type="button" data-sxs-ui="pro">Pro<\/button>/);
  assert.doesNotMatch(js, /newChat/);
  assert.match(css, /body\.sxs-phone #studioLayoutSwitch,\s*body\.sxs-phone #studioGridWorkspace \{ display: none !important; \}/);
});

test('theme switch moves to the side menu user card in Standard', () => {
  assert.match(js, /\$\('#hdUserCard'\)/);
  assert.match(js, /S\.cycleStudioTheme\(e\)/);
  assert.match(css, /body\.sxs-std \.sxs-theme \{ display: grid;[^}]*top: 8px; right: 8px;/);
});

test('no business logic of its own: everything goes through Pro Studio', () => {
  assert.match(cabinet, /S\.studioBridge = \{/);
  for (const name of ['attachments()', 'removeAttachment(id)', 'textVersions()', 'pickTextVersion(id)', 'setImageCount(count)', 'musicDuration()', 'setMusicDuration(seconds)']) {
    assert.ok(cabinet.includes('    ' + name + ' {'), 'bridge lacks ' + name);
  }
  assert.doesNotMatch(js, /fetch\(|XMLHttpRequest|\/api\//);
  // The prompt is Pro Studio's own field; sending presses Pro Studio's button.
  assert.match(js, /pro\.input = \$\('#chatInput'\)/);
  assert.match(js, /else if \(name === 'send'\) \{ closeParams\(\); press\(pro\.send, e\); \}/);
});

test('"+" opens the sheet in Photo/Video and the file picker elsewhere', () => {
  assert.match(js, /if \(m === 'image'\) openSheet\(\);/);
  assert.match(js, /else if \(m === 'music'\) S\.openNativeFilePicker\('music_audio'\);/);
  assert.match(js, /else if \(m === 'voice'\) S\.openVoiceUpload\(e\);/);
  assert.match(js, /else S\.openNativeFilePicker\('text_media'\);/);
  assert.match(js, /\[\['history', 'История'\], \['character', 'Персонажи'\], \['object', 'Объекты'\], \['style', 'Стили'\]\]/);
});

test('parameters: existing rows per mode, voice opens the voice list', () => {
  for (const label of ['Соотношение сторон', 'Количество', 'Seed', 'Продолжительность', 'Разрешение', 'Звук видео', 'Стиль']) assert.ok(js.includes("label: '" + label + "'"), label);
  assert.match(js, /if \(m === 'voice'\) \{ closeParams\(\); S\.openVoiceList\(e\); return; \}/);
  // Music duration: minutes and seconds scales instead of the wheel.
  assert.match(js, /data-sxs-dur="m"/);
  assert.match(js, /data-sxs-dur="s"/);
  assert.match(cabinet, /musicDurationDraftSeconds = value;\s*saveMusicDuration\(null\);/);
  // Text: one slider position per version, the version name over the thumb.
  assert.match(js, /sxs-ver-label/);
  assert.doesNotMatch(js, /Faster|Smarter/);
});

test('photo tools open as icon tiles in Standard, without Edit on phones', () => {
  assert.match(cabinet, /S\.isStandardStudio && S\.isStandardStudio\(\) \? photoToolIconGridHtml\(\)/);
  assert.match(js, /S\.photoToolIconHtml = function \(key\)/);
  assert.match(cabinet, /const phone = typeof window !== 'undefined' && window\.matchMedia && window\.matchMedia\('\(max-width: 767px\)'\)\.matches;/);
});

test("the composer is Standard's own block, resting on the keyboard by its own rule", () => {
  // One block built from scratch: attachments, its own prompt field, bottom bar.
  assert.match(js, /<div class="sxs-composer">/);
  assert.match(js, /<textarea class="sxs-input"/);
  // Pro Studio's composer is hidden and only keeps the state: the text is mirrored into #chatInput.
  assert.match(js, /Object\.defineProperty\(pro\.input, 'value'/);
  assert.match(js, /pro\.input\.dispatchEvent\(new Event\('input', \{ bubbles: true \}\)\)/);
  assert.match(css, /body\.sxs-std #studioComposer > \.studio-mode-tabs,\s*body\.sxs-std #studioComposer > \.studio-video-panel \{ visibility: hidden !important;/);
  // No Pro input window, no keyboard-close button in Standard.
  assert.doesNotMatch(css, /composer-input-window/);
  assert.doesNotMatch(js + css, /mobile-keyboard-close/);
});

test('keyboard: one rule, Pro Studio pinned to the visual viewport', () => {
  // The visible box comes from visualViewport only (layout viewport
  // coordinates, like position: fixed): never mixed with scrollY or a rect.
  assert.match(js, /return vv \? \{ top: vv\.offsetTop, height: vv\.height, width: vv\.width \}/);
  assert.match(js, /var top = Math\.max\(kb\.frameTop, area\.top\);/);
  assert.match(js, /var height = Math\.max\(0, area\.top \+ area\.height - top\);/);
  assert.match(css, /body\.sxs-std #app-root \.view\[data-view="tools"\]\.active \.studio \{\s*position: fixed !important; top: var\(--sxs-vv-top, 0px\) !important;/);
  assert.match(css, /height: var\(--sxs-vv-h, 100%\) !important; min-height: 0 !important;/);
  // No second lift: the old padding rule and the layout-overlap formula
  // (0 when iOS pans the visual viewport) are gone.
  assert.doesNotMatch(js + css, /--sxs-kb\b/);
  assert.doesNotMatch(js, /window\.innerHeight - vv\.height - vv\.offsetTop/);
  assert.doesNotMatch(js, /\.style\.(paddingBottom|transform|bottom)\s*=/);
  // Pro Studio's keyboard rule (--kb, kb-open, input window) yields to Standard.
  assert.match(cabinet, /function standardOwnsKeyboard\(\) \{\s*return Boolean\(S\.isStandardStudio && S\.isStandardStudio\(\) && document\.querySelector\('\.view\[data-view="tools"\]\.active'\)\);/);
  assert.match(cabinet, /return Boolean\(S\.device && S\.device\.usesVirtualKeyboard\) && !standardOwnsKeyboard\(\);/);
  // Keyboard open = shrink against the height taken before it opened (only
  // the bottom margin depends on it); Telegram's viewport is a second source.
  assert.match(js, /if \(!kb\.base \|\| area\.height > kb\.base \|\| Date\.now\(\) - kb\.blurAt > 700\) kb\.base = area\.height;/);
  assert.match(js, /var open = editing && \(kb\.base - area\.height > 80 \|\| tgShrink > 80\);/);
  assert.match(js, /app\.onEvent\('viewportChanged', keyboardSoon\)/);
  assert.match(css, /body\.sxs-std \.sxs-composer \{ margin: 0 0 calc\(8px \+ env\(safe-area-inset-bottom\)\);/);
  assert.match(css, /body\.sxs-std\.sxs-kb-open \.sxs-composer \{ margin-bottom: 8px; \}/);
  // A page left shifted by iOS is put back only where the page never scrolls,
  // and only once no field is focused.
  assert.match(js, /getComputedStyle\(document\.body\)\.overflowY === 'hidden'/);
  assert.match(js, /if \(!editing\) \{[\s\S]*?resetPageScroll\(\);/);
  // A transformed ancestor (the site's view) becomes the fixed containing block.
  assert.match(js, /function fixedContainer\(node\)/);
});

