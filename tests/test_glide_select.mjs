// Run with: node --test tests/test_glide_select.mjs
//
// GlideSelect everywhere a button opens a list: the app menus pop in from
// their button and a pill glides between the rows; native <select>s open
// the same menu instead of the system one. Music gets its own Vocal pill;
// Text loses Text tools / Format / Text styles; Voice loses General
// settings / Text templates / Voice settings, and Upload goes straight to
// the file picker, the action following the file.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const glide = read('webapp/js/glide-select.js');
const css = read('webapp/css/glide-select.css');
const js = read('webapp/js/cabinet.js');
const html = read('webapp/cabinet.html');
const index = read('webapp/index.html');
const workspace = read('webapp/knowledge-workspace.html');

test('the Mini App and its workspaces load GlideSelect', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/glide-select\.css\?v=glide-20261027" \/>/);
  assert.match(index, /<script src="js\/glide-select\.js\?v=glide-20261027"><\/script>/);
  assert.match(workspace, /<link rel="stylesheet" href="css\/glide-select\.css\?v=glide-20261027">/);
  assert.match(workspace, /<script src="js\/glide-select\.js\?v=glide-20261027"><\/script>/);
});

test('every app menu is registered: Pro Studio, Grid, Edit, Music and Dialogues workspaces', () => {
  for (const root of ['#modelPop', '.studio-grid-download-menu', '.history-item-menu > div', '.edit-sketch-tool-strip', '.voice-caret-menu',
    '.photo-picker-menu', '.qt-model-sheet', '.qv-model-menu', '.qv-speed-menu', '.qv-emo-menu']) {
    assert.ok(glide.includes("{ root: '" + root + "'"), root);
  }
  assert.match(glide, /list: '\.image-model-sheet-list, \.image-size-sheet-list', row: '\.image-model-row, \.image-size-row'/);
});

test('the motion follows GlideSelect: 180 ms pop from the button, 220 ms glide, 120 ms close', () => {
  assert.match(glide, /menu\.animate\(\[\{ opacity: 0, scale: '0\.95' \}, \{ opacity: 1, scale: '1' \}\], \{ duration: 180, easing: 'cubic-bezier\(0\.23, 1, 0\.32, 1\)' \}\)/);
  assert.match(css, /\.glide-pill\{[^}]*transition:transform 220ms var\(--gl-ease\),width 220ms var\(--gl-ease\),height 220ms var\(--gl-ease\),opacity 150ms ease\}/);
  assert.match(css, /\.glide-select__menu\[data-state="closed"\]\{transition-duration:120ms;pointer-events:none\}/);
  assert.match(css, /@media \(prefers-reduced-motion:reduce\)\{/);
});

test('a menu is dark or light by the text of the button it opened from', () => {
  assert.match(glide, /return lum > 0\.5 \? 'dark' : 'light';/);
  assert.match(css, /\[data-glide-tone="light"\]:is\(\[data-glide-menu\],\.glide-select__menu\)\{--gl-surface:#fff;/);
  assert.match(css, /\[data-glide-menu\],\.glide-select__menu\{--gl-surface:#27272a;--gl-highlight:#3f3f46;/);
});

test('a native select keeps its value and events: the pick fires input and change', () => {
  assert.match(glide, /select\.selectedIndex = option\.index;\n\s+select\.dispatchEvent\(new Event\('input', \{ bubbles: true \}\)\);\n\s+select\.dispatchEvent\(new Event\('change', \{ bubbles: true \}\)\);/);
  assert.match(glide, /doc\.addEventListener\('mousedown', function \(event\) \{\n\s+var select = event\.target\.closest && event\.target\.closest\('select\[data-glide-select\]'\);/);
  assert.match(glide, /\}, \{ capture: true, passive: false \}\);/);
  assert.match(glide, /return select\.multiple \|\| select\.size > 1 \|\| !!select\.closest\('\[data-glide="off"\]'\);/);
});

test('the check marks the chosen row only', () => {
  assert.match(css, /\[data-glide-list\] \[data-glide-row\]:not\(\.image-seed-row\) \.image-size-check:is\(#gl,\*\):is\(#gl,\*\)\{visibility:hidden;/);
  assert.match(css, /\.glide-select__check\[data-on\]\{visibility:visible\}/);
});

test('Music: Vocal is a pill in the bottom row with its own list, not in Settings', () => {
  assert.match(html, /<button class="studio-select-pill music-only" id="musicVocalButton" type="button" onclick="SYLVEX\.openImageOptionMenu\(event,'vocal'\)">\n\s+<svg[^\n]+<\/svg>\n\s+<span id="musicVocalVal">Вокал<\/span>/);
  assert.ok(html.indexOf('id="musicVocalButton"') > html.indexOf('id="musicGenreVal"'));
  assert.match(js, /openMusicSheet\('Вокал', items, 'vocal', musicState\.settings\.vocal \|\| 'auto'\);/);
  assert.match(js, /const MUSIC_MODAL_SETTINGS = Object\.keys\(MUSIC_SETTINGS\)\.filter\(\(key\) => key !== 'vocal'\);/);
  assert.match(js, /\+ MUSIC_MODAL_SETTINGS\.map\(\(settingKey\) => \{/);
});

test('Text: only the model and its version; no Text tools, Format or Text styles', () => {
  assert.doesNotMatch(html, /text_tool|text_format|text_style|Стили текста/);
  assert.doesNotMatch(js, /TEXT_STYLE_OPTIONS|TEXT_FORMAT_OPTIONS|textOptionLabel|'text_tool'|'text_style'|'text_format'/);
  assert.match(html, /onclick="SYLVEX\.openImageOptionMenu\(event,'text_version'\)"/);
});

test('Voice: no General settings, Text templates or Voice settings; Create text with AI stays', () => {
  assert.doesNotMatch(html, /Общие настройки|Шаблоны текста|Настройки голоса/);
  assert.match(html, /onclick="SYLVEX\.openVoiceAddon\(event,'ai',true\)"/);
  assert.doesNotMatch(js, /applyVoiceTemplate|setVoiceEditorSetting|'Настройки озвучки'|>Настройки озвучки</);
});

test('Voice upload: one press opens the file picker; the file decides the action', () => {
  assert.match(js, /if \(!voiceFilePurposes\(\)\.length\) \{\n\s+toast\('Эта модель не принимает файлы'\);\n\s+return;\n\s+\}\n\s+openNativeFilePicker\('voice_upload'\);/);
  assert.match(js, /\{ kind:'file', purpose:'document_voiceover'/);
  assert.match(js, /\{ kind:'video', purpose:'dub_video', accept:'video\/\*' \}/);
  assert.match(js, /\{ kind:'audio', purpose:'speech_to_speech', accept:'audio\/\*' \}/);
  assert.match(js, /applyVoiceUploadPurpose\(match\.purpose\);/);
  assert.doesNotMatch(js, /renderVoiceUploadPanel|confirmVoiceUpload|openVoiceMediaPicker|toggleVoiceUploadDropdown|selectVoiceUploadOption/);
  assert.match(html, /<button class="vgen-upload-clear" id="voiceUploadClear" type="button" aria-label="Убрать файл" hidden onclick="event\.stopPropagation\(\);SYLVEX\.clearVoiceUploads\(event\)">×<\/button>/);
});
