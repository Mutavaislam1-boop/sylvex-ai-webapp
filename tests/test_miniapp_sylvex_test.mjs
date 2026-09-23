// Run with: node --test tests/test_miniapp_sylvex_test.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const userSource = readFileSync(new URL('../webapp/js/user.js', import.meta.url), 'utf8');
const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
function harness({allowed = false, syncFails = false, stateFails = false} = {}) {
  const calls = [];
  const S = {tg: {initData: 'signed-test-fixture', initDataUnsafe: {user: {id: 123}}}};
  let renders = 0;
  S.renderModelPop = () => { renders++; };
  const context = vm.createContext({
    window: {SYLVEX: S, setTimeout, clearTimeout},
    document: {getElementById: () => null},
    localStorage: {getItem: () => null, setItem() {}},
    console: {warn() {}}, AbortController,
    fetch: async url => {
      calls.push(url);
      if (url.includes('/profile?')) return {ok: true, json: async () => ({profile: {}})};
      if (url.endsWith('/sync')) return {ok: !syncFails, json: async () => ({user: {telegram_id: 123, balance: 50}})};
      if (url.includes('/user-state?')) return {ok: !stateFails, json: async () => ({telegram_id: 123, balance: 50, sylvex_test_available: allowed})};
      if (url === '/api/web/session/me') return {ok: true, json: async () => ({authenticated: true, account_id: 456, balance: 50})};
      throw new Error('Unexpected request: ' + url);
    },
  });
  vm.runInContext(userSource, context);
  return {S, calls, context, renders: () => renders};
}

for (const allowed of [true, false]) {
  test(`successful Telegram sync loads server permission=${allowed}`, async () => {
    const h = harness({allowed});
    const user = await h.S.syncUser();
    assert.equal(user.sylvex_test_available, allowed);
    assert.equal(h.calls.filter(url => url.includes('/user-state?')).length, 1);
    assert.equal(h.renders(), 1);
  });
}
test('failed sync still loads permissions through existing fallback', async () => {
  const h = harness({allowed: true, syncFails: true});
  assert.equal((await h.S.syncUser()).sylvex_test_available, true);
});
test('failed permission lookup keeps SYLVEX Test hidden', async () => {
  const h = harness({allowed: true, stateFails: true});
  h.S.user = {telegram_id: 123, sylvex_test_available: true};
  assert.equal((await h.S.syncUser()).sylvex_test_available, false);
});
test('Website session does not use the Telegram permission sync', async () => {
  const h = harness();
  await h.S.syncWebSession();
  assert.deepEqual(h.calls, ['/api/web/session/me']);
});

// Evaluate the actual model catalogs and picker functions without initializing
// unrelated pages, media players, network calls, or the grid editor.
function declaration(name, kind = 'function') {
  const pattern = kind === 'function'
    ? new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`, 'm')
    : new RegExp(`^([ \\t]*)const ${name} = \\[`, 'm');
  const match = pattern.exec(cabinet);
  assert.ok(match, name);
  const end = cabinet.indexOf('\n' + match[1] + (kind === 'function' ? '}' : '];'), match.index);
  assert.ok(end > match.index, name);
  return cabinet.slice(match.index, end + match[1].length + (kind === 'function' ? 2 : 3));
}
function pickerContext(S) {
  const pop = {innerHTML: '', style: {}, classList: {remove() {}}};
  const context = vm.createContext({S, document: {getElementById: id => id === 'modelPop' ? pop : null},
    imageModelIconHtml: () => '',
  });
  S.escapeHtml = value => String(value);
  const catalogs = ['GROK_IMAGE_SIZES', 'GOOGLE_IMAGE_SIZES', 'IMAGE_MODEL_LIST', 'VIDEO_MODELS', 'MUSIC_MODEL_LIST', 'VOICE_MODEL_LIST', 'TEXT_MODEL_LIST', 'TEXT_MODEL_FAMILIES'];
  vm.runInContext(catalogs.map(name => declaration(name, 'const')).join('\n'), context);
  vm.runInContext(`var studioMode, activeCat; var imageState={},videoState={},musicState={},voiceState={},textState={};`, context);
  const functions = ['isImageMode', 'isVideoMode', 'isMusicMode', 'isVoiceMode', 'sylvexTestModeAvailable', 'filterSylvexTestEntries', 'currentComposerModelList', 'imageModelButton', 'renderModelPop', 'pickImageOption', 'pickStudioModel', 'textModelFamilyId', 'textVersionsForFamily'];
  vm.runInContext(functions.map(name => declaration(name)).join('\n'), context);
  for (const name of ['syncImageModelOptionDefaults','syncImageFeatureAvailability','renderImageReferenceSections','saveCurrentVideoModelSettings','restoreVideoModelSettings','ensureMusicSettings','renderMusicControls','normalizeTextToolForModel','renderTextControls','renderVoiceControls','pickVideoOption','renderImageControls']) context[name] = () => {};
  context.isElevenLabsVoiceModel = context.isRunwayVoiceModel = () => false;
  return {context, pop};
}
for (const mode of ['image', 'video', 'text', 'voice', 'music']) {
  test(`${mode}: admin gets one final selectable test model; normal user gets none`, async () => {
    const h = harness({allowed: true});
    await h.S.syncUser();
    const {context, pop} = pickerContext(h.S);
    vm.runInContext(`studioMode=activeCat='${mode}'; renderModelPop()`, context);
    const ids = vm.runInContext('currentComposerModelList().map(m => m.id)', context);
    assert.equal(ids.at(-1), 'sylvex_test');
    assert.equal(ids.filter(id => id === 'sylvex_test').length, 1);
    assert.match(pop.innerHTML, /image-model-row/);
    assert.match(pop.innerHTML, /<span class="image-model-name">SYLVEX Test<\/span>(?:(?!image-model-name)[\s\S])*$/);
    vm.runInContext("pickImageOption(null, 'model', 'sylvex_test')", context);
    assert.equal(vm.runInContext('pickStudioModel()', context), 'sylvex_test');
    // Run the real Generate payload builder, stopping at a mocked HTTP boundary.
    let sent;
    Object.assign(context, {
      AbortController, setTimeout, clearTimeout, console: {log() {}},
      isTextGenerationMode: value => value === 'text',
      activeGenerationLocked: () => true,
      activeGenerationPlaceholderIndex: () => 0,
      chatMessages: [], currentConvId: '',
      getTelegramId: () => 123, uiLang: () => 'en',
      currentVideoReferenceImages: () => [],
      currentVideoProvider: () => 'sylvex-router', pickProviderHint: () => 'sylvex-router',
      imageOptionsPayload: () => ({}), videoOptionsPayload: () => ({}),
      musicOptionsPayload: () => ({}), voiceOptionsPayload: () => ({}), textOptionsPayload: () => ({}),
      fetch: async (url, options) => {
        sent = {url, payload: JSON.parse(options.body)};
        return {ok: true, status: 200, json: async () => ({ok: true})};
      },
    });
    vm.runInContext(declaration('callGenerateCore'), context);
    await vm.runInContext("callGenerateCore('Mini App pipeline check', null)", context);
    assert.equal(sent.url, '/api/public/prostudio/generate');
    assert.equal(sent.payload.model, 'sylvex_test');
    assert.equal(sent.payload.mode, mode);
    assert.equal(sent.payload.sylvex_test, false, 'normal modes use the model, not a global toggle');
    h.S.user.sylvex_test_available = false;
    vm.runInContext('renderModelPop()', context);
    assert.ok(!pop.innerHTML.includes('SYLVEX Test'));
  });
}
