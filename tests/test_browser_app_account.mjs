// Standalone browser Mini App (webapp/js/cabinet.js): a guest browses but
// every account action opens sign-in first; local account data never
// outlives its account; and a profile save is one request with one answer.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const userSource = readFileSync(new URL('../webapp/js/user.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');
const index = readFileSync(new URL('../webapp/index.html', import.meta.url), 'utf8');

function extract(name, input = source) {
  const start = input.search(new RegExp('^[ \\t]*(?:async )?function ' + name + '\\(', 'm'));
  assert.ok(start >= 0, name);
  // The body starts at ") {", not at a default parameter like options={}.
  const open = start + input.slice(start).search(/\)\s*\{/);
  let depth = 0;
  for (let i = input.indexOf('{', open); i < input.length; i++) {
    if (input[i] === '{') depth++;
    else if (input[i] === '}' && --depth === 0) return input.slice(start, i + 1);
  }
  throw new Error('unbalanced ' + name);
}

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    get length() { return data.size; },
    key: (i) => Array.from(data.keys())[i] ?? null,
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    dump: () => Object.fromEntries(data),
  };
}

function stateHarness(initial, startKeys) {
  const localStorage = memoryStorage(initial);
  const sessionStorage = memoryStorage();
  const reloads = [];
  const context = vm.createContext({
    localStorage, sessionStorage, Date, S: {},
    isBrowserApp: () => true,
    window: { __sylvexStartKeys: startKeys || Object.keys(initial), location: { reload: () => reloads.push(1) } },
  });
  const block = source.slice(source.indexOf('  const BROWSER_DEVICE_KEYS = new Set(['), source.indexOf('  S.hasTelegramContext = hasTelegramContext;'));
  vm.runInContext(block + '\n;globalThis.settle = settleBrowserAccountState; globalThis.clear = clearBrowserAccountState;', context);
  return { context, localStorage, reloads };
}

const ACCOUNT_DATA = {
  'sylvex-prostudio-chat-900000000001-image': '[{"text":"secret"}]',
  'sylvex-prostudio-grid-v2': '{"nodes":[1]}',
  'sylvex-prostudio-active-generation-900000000001': '{"jobId":"x"}',
  'sylvex_voice_favorites': '["v1"]',
  'sylvex-lang': 'en',
  'sylvex-theme': 'dark',
  'sylvex-model-capabilities-v1': '{}',
};

test('signing out removes the account data and keeps device settings', () => {
  const { context, localStorage } = stateHarness(Object.assign({ 'sylvex-browser-state-owner': '900000000001' }, ACCOUNT_DATA));
  context.clear('guest');
  assert.deepEqual(localStorage.dump(), {
    'sylvex-lang': 'en', 'sylvex-theme': 'dark', 'sylvex-model-capabilities-v1': '{}', 'sylvex-browser-state-owner': 'guest',
  });
});

test('a guest load after an account clears its data and reloads once, never in a loop', () => {
  const { context, localStorage, reloads } = stateHarness(Object.assign({ 'sylvex-browser-state-owner': '900000000001' }, ACCOUNT_DATA));
  assert.equal(context.settle(null), true);
  assert.equal(reloads.length, 1);
  assert.equal(localStorage.getItem('sylvex-prostudio-grid-v2'), null);
  assert.equal(localStorage.getItem('sylvex-browser-state-owner'), 'guest');
  // The reloaded page: owner is now the guest - nothing more to do.
  assert.equal(context.settle(null), false);
  assert.equal(reloads.length, 1);
});

test('another account on this browser starts clean', () => {
  const { context, localStorage, reloads } = stateHarness(Object.assign({ 'sylvex-browser-state-owner': '900000000001' }, ACCOUNT_DATA));
  assert.equal(context.settle({ account_id: 102 }), true);
  assert.equal(reloads.length, 1);
  assert.equal(localStorage.getItem('sylvex-prostudio-chat-900000000001-image'), null);
  assert.equal(localStorage.getItem('sylvex-browser-state-owner'), '102');
});

test('the signed-in account keeps its own data, and a first guest visit does not reload', () => {
  const own = stateHarness(Object.assign({}, ACCOUNT_DATA));
  assert.equal(own.context.settle({ account_id: 101 }), false);
  assert.equal(own.localStorage.getItem('sylvex-prostudio-grid-v2'), '{"nodes":[1]}');
  assert.equal(own.localStorage.getItem('sylvex-browser-state-owner'), '101');
  // The app wrote its own defaults this load, but nothing was there before.
  const fresh = stateHarness({ 'sylvex-prostudio-last-mode-anon': 'image' }, []);
  assert.equal(fresh.context.settle(null), false);
  assert.equal(fresh.reloads.length, 0);
  assert.equal(fresh.localStorage.getItem('sylvex-browser-state-owner'), 'guest');
});

test('sign-out clears local account data before ending the session', () => {
  const signOut = extract('signOut');
  assert.ok(signOut.indexOf("clearBrowserAccountState('guest')") < signOut.indexOf("/api/web/auth/logout"));
});

test('account actions check for a guest before any job, card, upload or request', () => {
  const core = {
    create: ['sendChat', 'sendTextChat', 'sendHomeIdea', 'uploadProStudioMediaFile', 'runGridNode', 'runStudioGridWorkflow',
      'startVideoTemplateGeneration', 'generateEditWorkspace', 'generatePhotoTool', 'generateQuickImageDetail', 'createCharacterCreationJob',
      'createObjectCreationJob', 'runVoiceTextTool', 'generateNow'],
    buy: ['payStoreProduct', 'payBrowserProduct', 'openBrowserStoreProduct', 'payWith'],
    contact: ['sendSupport', 'openSupport'],
  };
  for (const [reason, names] of Object.entries(core)) {
    for (const name of names) {
      const body = extract(name);
      const head = body.slice(body.search(/\)\s*\{/), body.search(/\)\s*\{/) + 140);
      assert.match(head, new RegExp("\\{\\s*if \\(guestNeedsAccount\\('" + reason + "'\\)\\)"), name);
    }
  }
  const guards = extract('initBrowserGuestGuards');
  for (const name of ['openImageUpload', 'pickVisualReference', 'openVisualCreateModal', 'openBuy', 'openEditProfile', 'toggleCommunityLike', 'onStudioGridMediaFiles']) {
    assert.ok(source.slice(source.indexOf('const GUEST_GATED_ACTIONS'), source.indexOf('const GUEST_ALLOWED_POSTS')).includes("'" + name + "'"), name);
  }
  assert.match(guards, /HTMLInputElement\.prototype\.click = function/);
  assert.match(guards, /addEventListener\('drop', blockFiles, true\)/);
  assert.match(guards, /error: 'login_required'/);
  assert.match(source, /create: 'Log in or create an account to use SYLVEX generation features\.'/);
});

function profileHarness(response) {
  const calls = { fetch: 0, timers: 0, status: [], closed: 0, errors: [], queued: 0 };
  const els = {
    epName: { value: ' Nova ' },
    epSaveBtn: { disabled: false, textContent: 'Save' },
    epError: { textContent: '', hidden: true },
  };
  const context = vm.createContext({
    S: { user: { telegram_id: 900000000001 }, renderUser() {} },
    document: { getElementById: (id) => els[id] || null },
    epSelectedAvatar: 'assets/avatars/a2.png',
    epAppearanceDraft: { id: 'dark', coverIndex: 0 },
    getTelegramId: () => 900000000001,
    currentProfileAppearance: () => ({ id: 'dark', coverIndex: 0 }),
    storeProfileAppearance() {}, applyProfileAppearance() {},
    clearQueuedProfileSave() {}, queueProfileSave() { calls.queued++; },
    closeModal() { calls.closed++; },
    showProfileSaveStatus(text, state) { calls.status.push([text, state]); },
    setTimeout() { calls.timers++; },
    fetchWithTimeout: async (url, options) => { calls.fetch++; calls.url = url; calls.options = options; calls.body = JSON.parse(options.body); return response(); },
  });
  vm.runInContext('let browserProfileSaving = false;\n' + extract('setEditProfileError') + '\n' + extract('saveWebProfile') + '\n' + extract('saveBrowserProfile') + '\n;globalThis.save = saveBrowserProfile;', context);
  return { context, calls, els };
}

test('a browser profile save is one request with one success message', async () => {
  const { context, calls } = profileHarness(() => ({ ok: true, json: async () => ({ ok: true, profile: { display_name: 'Nova', custom_avatar_url: 'assets/avatars/a2.png' } }) }));
  await context.save();
  assert.equal(calls.fetch, 1);
  // The SYLVEX web session only: no Telegram endpoint, id or initData.
  assert.equal(calls.url, '/api/web/account/profile');
  assert.equal(calls.options.credentials, 'include');
  assert.deepEqual(Object.keys(calls.body).sort(), ['custom_avatar_url', 'display_name', 'theme_preference']);
  assert.deepEqual(calls.body.display_name, 'Nova');
  assert.equal(calls.closed, 1);
  assert.deepEqual(calls.status, [['Profile saved', 'saved']]);
  assert.equal(context.S.user.display_name, 'Nova');
  assert.equal(calls.timers + calls.queued, 0);
});

test('a failed browser profile save shows one message and never retries', async () => {
  const { context, calls, els } = profileHarness(() => ({ ok: false, status: 500, json: async () => ({ ok: false, error: 'profile_save_failed' }) }));
  await context.save();
  assert.equal(calls.fetch, 1);
  assert.equal(calls.closed, 0);
  assert.deepEqual(calls.status, []);
  assert.equal(els.epError.hidden, false);
  assert.match(els.epError.textContent, /Couldn’t save your profile/);
  assert.equal(calls.timers + calls.queued, 0, 'no background retry');
  assert.equal(els.epSaveBtn.disabled, false);
});

function browserBalanceHarness(sessionResponses) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: '', removeAttribute() {} });
    return elements.get(id);
  };
  const context = vm.createContext({
    S: {}, Number, Date, Intl,
    document: { getElementById: element, dispatchEvent() {} },
    CustomEvent: class CustomEvent { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
    userFetchWithTimeout: async () => ({ ok: true, json: async () => sessionResponses.shift() }),
    renderIdentity() {},
  });
  vm.runInContext([
    extract('fmtNum', userSource), extract('setText', userSource), extract('statusLabel', userSource), extract('normalizeState', userSource),
    extract('mergeUserPatch', userSource), extract('renderUserState', userSource), extract('syncWebSession', userSource),
    ';globalThis.sync = syncWebSession;',
  ].join('\n'), context);
  return { context, elements };
}

test('Browser Mini App renders the web account balance and a partial refresh cannot reset it to zero', async () => {
  const { context, elements } = browserBalanceHarness([
    { authenticated: true, account_id: 101, sylvex_user_id: 101, balance: 875 },
    { authenticated: true, account_id: 101, sylvex_user_id: 101 },
  ]);
  await context.sync();
  assert.equal(context.S.user.balance, 875);
  assert.equal(elements.get('homeBalance').textContent, '875 ⚡️');
  assert.equal(elements.get('shopBalance').textContent, '875');

  await context.sync();
  assert.equal(context.S.user.balance, 875);
  assert.equal(elements.get('profileBalance').textContent, '875 ⚡️');
});

test('the default avatar is sent as "" so the server does not keep the previous one', () => {
  assert.match(extract('saveBrowserProfile'), /custom_avatar_url: epSelectedAvatar \|\| ''/);
});

test('in the browser app no profile or theme save goes to a Telegram endpoint', () => {
  for (const name of ['saveWebProfile', 'saveBrowserProfile']) assert.ok(!/telegram|initData|getTelegramId/.test(extract(name)), name);
  assert.match(extract('persistProfileInBackground'), /^[^\n]*\n(?:\s*\/\/[^\n]*\n)*\s*if \(isBrowserApp\(\)\) \{ clearQueuedProfileSave\(\); return false; \}/);
  const theme = extract('applyTheme');
  assert.ok(theme.indexOf("persist && isBrowserApp()") < theme.indexOf("/api/public/telegram/profile"));
  assert.match(theme, /saveWebProfile\(\{ theme_preference: \{ id: themeId \} \}\)/);
});

test('browser-only profile changes: no invite or Telegram cards, Delete account behind its own confirmation', () => {
  assert.match(css, /html\.browser-app \.profile-linked-mini,\s*html\.browser-app \.profile-referrals-mini,\s*html\.browser-app \.profile-invite-row\{display:none\}/);
  assert.match(html, /class="row profile-invite-row"/);
  assert.match(css, /\.ep-danger\{display:none\}\s*html\.browser-app \.ep-danger\{display:block/);
  const del = extract('openDeleteAccount');
  assert.match(del, /post\('\/api\/web\/account\/delete\/start'\)/);
  assert.match(del, /post\('\/api\/web\/account\/delete\/verify', \{ code \}\)/);
  assert.match(del, /post\('\/api\/web\/account\/delete', confirmToken \? \{ confirm_token: confirmToken \} : \{\}\)/);
  assert.ok(del.indexOf("clearBrowserAccountState('guest')") > del.indexOf("'/api/web/account/delete',"));
  assert.doesNotMatch(del, /daPassword|daConfirm/);
});

test('no Telegram identity in the browser app; Telegram keeps its own', () => {
  assert.match(index, /<title>SYLVEX<\/title>/);
  assert.match(index, /classList\.add\('browser-app', 'browser-auth-pending'\)/);
  assert.match(extract('renderGeneratedTelegramButton'), /if \(usesWebSessionAuth\(\)\) return '';/);
  assert.match(source, /\(usesWebSessionAuth\(\) \? '' : generationInfoRow\('Telegram'/);
  assert.match(source, /const noneLabel = isBrowserApp\(\) \? .* : 'TG';/);
  assert.match(css, /html\.browser-auth-pending \.view\[data-view="home"\] \.user-card \.user-row/);
});
