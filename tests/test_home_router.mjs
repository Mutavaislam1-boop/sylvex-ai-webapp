// Home input router (local classification) and Text-chat internal links.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const slice = (from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, 'missing ' + from);
  return source.slice(start, end);
};
const code = slice('  const HOME_ROUTE_TOOL_PATTERNS', '  async function serverHomeRoute')
  + slice('  function renderSylvexChatLinks', '  function openSylvexChatLink');
const context = vm.createContext({
  IMAGE_MODEL_LIST: [{ id: 'seedream_5_0_pro', label: 'Seedream 5.0 Pro' }],
  VIDEO_MODELS: [{ id: 'kling_3_0', label: 'Kling 3.0' }],
  MUSIC_MODEL_LIST: [{ id: 'suno_chirp_5_5', label: 'Suno Chirp v5.5' }],
  VOICE_MODEL_LIST: [{ id: 'elevenlabs_eleven_v3', label: 'ElevenLabs Eleven v3' }],
  TEXT_MODEL_LIST: [{ id: 'gpt-5.6', label: 'GPT-5.6' }],
  BRAND_GENERATORS: { kling: { label: 'Kling AI', mode: 'video', model: 'kling_3_0' }, suno: { label: 'Suno', mode: 'music', model: 'suno_chirp_5_5' } },
  PHOTO_TOOL_CONFIG: { remove_bg: {}, try_on: {}, enhance: {}, tattoo: {}, animate_photo: {}, replace_character: {} },
});
vm.runInContext(code + '\nthis.localHomeRoute = localHomeRoute; this.renderSylvexChatLinks = renderSylvexChatLinks;', context);
const route = (text, attachment = false) => {
  const r = context.localHomeRoute(text, attachment);
  return { mode: r.mode, model: r.model, tool: r.tool, confident: r.confident };
};

test('clear media requests route locally to the right studio', () => {
  assert.equal(route('Нарисуй кота в космосе').mode, 'image');
  assert.equal(route('Сгенерируй картинку заката').mode, 'image');
  assert.equal(route('Создай видео, где лиса бежит по снегу').mode, 'video');
  assert.equal(route('Сочини песню про море').mode, 'music');
  assert.equal(route('Озвучь этот текст: привет всем').mode, 'voice');
  assert.equal(route('make a short video of a city at night').mode, 'video');
  assert.equal(route('generate a lo-fi beat').mode, 'music');
  assert.ok(route('Нарисуй кота').confident);
});

test('a named model or tool opens exactly that model/tool', () => {
  assert.deepEqual(route('Сделай ролик в Kling AI про дождь'), { mode: 'video', model: 'kling_3_0', tool: '', confident: true });
  assert.deepEqual(route('Спроси у GPT-5.6, что такое квант'), { mode: 'text', model: 'gpt-5.6', tool: '', confident: true });
  assert.deepEqual(route('Удали фон с этого фото', true), { mode: 'tool', model: '', tool: 'remove_bg', confident: true });
  assert.equal(route('remove the background please').tool, 'remove_bg');
});

test('questions and discussion go to the full Text chat without a server call', () => {
  for (const text of ['Как работает видеокодек?', 'Объясни теорию относительности', 'Помоги составить план на неделю', 'What is a diffusion model?', 'Привет!']) {
    const r = route(text);
    assert.equal(r.mode, 'text', text);
    assert.equal(r.confident, true, text);
  }
});

test('ambiguous requests ask the server router (text is only the fallback)', () => {
  assert.equal(route('Сделай что-нибудь красивое').confident, false);
  assert.equal(route('видео про котов').confident, false);
});

test('only sylvex://open links in AI text become internal buttons', () => {
  const html = context.renderSylvexChatLinks('Можно сделать видео. [Открыть Video Studio](sylvex://open/video) [x](https://evil.example) [y](sylvex://open/admin)');
  assert.match(html, /<button type="button" class="sylvex-chat-link" data-sylvex-open="video">Открыть Video Studio →<\/button>/);
  assert.match(html, /\[x\]\(https:\/\/evil\.example\)/);
  assert.match(html, /\[y\]\(sylvex:\/\/open\/admin\)/);
});
