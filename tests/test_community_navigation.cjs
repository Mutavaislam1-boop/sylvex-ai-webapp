// Real ui.js and cabinet navigation functions, synthetic DOM, no network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const ui = fs.readFileSync(path.join(root, 'webapp/js/ui.js'), 'utf8');
const cabinet = fs.readFileSync(path.join(root, 'webapp/js/cabinet.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'webapp/cabinet.html'), 'utf8');
const index = fs.readFileSync(path.join(root, 'webapp/index.html'), 'utf8');
const user = fs.readFileSync(path.join(root, 'webapp/js/user.js'), 'utf8');

function context(mode) {
  const views = ['home', 'tools', 'media', 'history', 'profile', 'settings', 'shop', 'pay'];
  const nodes = views.map(name => ({dataset:{view:name}, active:false,
    classList:{toggle(_key, on){this.owner.active=on}, owner:null}}));
  nodes.forEach(node => {node.classList.owner=node});
  const switched = [];
  const S = {haptic:{select(){}}, updatePrice(){}, onViewSwitched(name){switched.push(name)},
    guardGuestView(){return false}, goToHostPage(){return false}};
  if (mode === 'telegram') S.tg = {setHeaderColor(){}};
  const document = {querySelectorAll(selector){return selector === '.view' ? nodes : []},
    querySelector(){return null}, getElementById(){return null},
    body:{classList:{contains(){return false}}}, documentElement:{dataset:{theme:'dark'}}};
  const window = {SYLVEX:S, location:{search:'',hash:''}};
  const ctx = vm.createContext({window, document, URLSearchParams, setTimeout, clearTimeout});
  vm.runInContext(ui, ctx);
  return {ctx, nodes, switched, window};
}

for (const mode of ['browser', 'telegram']) {
  test(`${mode}: an old Community view goes home without dispatching an action`, () => {
    const env = context(mode);
    env.window.switchView('community');
    assert.deepEqual(env.nodes.filter(n=>n.active).map(n=>n.dataset.view), ['home']);
    assert.deepEqual(env.switched, ['home']);
  });
  for (const view of ['home','tools','media','history','profile','settings','shop','pay']) {
    test(`${mode}: ${view} navigation is preserved`, () => {
      const env = context(mode);
      env.window.switchView(view);
      assert.deepEqual(env.nodes.filter(n=>n.active).map(n=>n.dataset.view), [view]);
    });
  }
  test(`${mode}: saved Community query/hash cannot restore the removed screen`, () => {
    const env = context(mode);
    const start = cabinet.indexOf('  function initialViewFromUrl() {');
    const end = cabinet.indexOf('  function applyInitialViewFromUrl()', start);
    assert.ok(start > 0 && end > start);
    vm.runInContext(cabinet.slice(start, end), env.ctx);
    for (const params of ['?view=community','?screen=community','?section=community','?view=COMMUNITY']) {
      env.window.location.search = params;
      assert.equal(vm.runInContext('initialViewFromUrl()', env.ctx), 'home');
    }
    env.window.location.search=''; env.window.location.hash='#community';
    assert.equal(vm.runInContext('initialViewFromUrl()', env.ctx), 'home');
    env.window.location.search='?view=history';
    assert.equal(vm.runInContext('initialViewFromUrl()', env.ctx), 'history');
  });
}

test('Community markup, actions, profile counters and client calls are removed', () => {
  assert.doesNotMatch(html, /data-view="community"|switchView\('community'\)|SYLVEX\.\w*Community|id="profile(?:Posts|PostLikes)"/);
  assert.doesNotMatch(cabinet, /\/api\/public\/community|(?:async )?function \w*Community|action:'community'|community: \[|loadCommunityFeed/);
  assert.doesNotMatch(user, /community_(?:posts|likes)_count|profilePosts|profilePostLikes/);
  assert.doesNotMatch(cabinet, /['"]community['"]/);
});

test('Updated markup and scripts have new cache URLs', () => {
  for (const asset of ['cabinet.html','js/ui.js','js/user.js','js/cabinet.js']) {
    assert.ok(index.includes(asset+'?v=community-removed-20261113'), asset);
  }
});

test('Billing statistics keep their shared modal and actions', () => {
  assert.match(cabinet, /function spendingModal\(/);
  assert.match(cabinet, /async function openSpendingStats\(/);
  assert.match(cabinet, /community-modal spending-stats-modal/);
  assert.match(html, /onclick="SYLVEX\.openSpendingStats\(\)"/);
});
