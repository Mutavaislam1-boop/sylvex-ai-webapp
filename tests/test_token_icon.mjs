// Run with: node --test tests/test_token_icon.mjs
//
// SYLVEX token (credit) icon: the lightning emoji is replaced everywhere in
// the Mini App by one icon (Lucide "astroid", stroke #20d35d) defined once
// in css/token-icon.css and used through js/token-icon.js. Covers the icon
// itself, how text carries it ({token}, and the API's own mark in saved
// data), and that no frontend file uses the old emoji any more.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync, readFileSync, readdirSync, statSync} from 'node:fs';
import vm from 'node:vm';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const PATH = 'M12.983 21.186a1 1 0 0 1-1.966 0 10 10 0 0 0-8.203-8.203 1 1 0 0 1 0-1.966 10 10 0 0 0 8.203-8.203 1 1 0 0 1 1.966 0 10 10 0 0 0 8.203 8.203 1 1 0 0 1 0 1.966 10 10 0 0 0-8.203 8.203';

function loadToken() {
  const context = vm.createContext({});
  vm.runInContext(read('webapp/js/token-icon.js'), context);
  return context.SylvexToken;
}

test('the icon is the requested SVG: astroid path, stroke #20d35d, width 2.5, round caps', () => {
  const css = read('webapp/css/token-icon.css');
  const svg = decodeURIComponent(/url\("data:image\/svg\+xml,([^"]+)"\)/.exec(css)[1]);
  assert.ok(svg.includes(`d='${PATH}'`));
  assert.ok(svg.includes("stroke='#20d35d'") && svg.includes("stroke-width='2.5'"));
  assert.ok(svg.includes("stroke-linecap='round'") && svg.includes("stroke-linejoin='round'") && svg.includes("fill='none'"));
  assert.match(css, /\.sx-token\{[^}]*width:1em;[^}]*height:1em;/);
  const token = loadToken();
  assert.equal(token.PATH, PATH);
  assert.equal(token.COLOR, '#20d35d');
  assert.equal(token.STROKE, 2.5);
});

test('{token} and the API token mark render as the icon; everything else is escaped', () => {
  const token = loadToken();
  assert.equal(token.ICON, '<i class="sx-token" aria-hidden="true"></i>');
  assert.equal(token.text('12 ' + token.MARK), '12 ' + token.ICON);
  assert.equal(token.text('12 \u26A1'), '12 ' + token.ICON, 'API text');
  assert.equal(token.text('12 \u26A1\uFE0F'), '12 ' + token.ICON, 'saved history');
  assert.equal(token.text('<img src=x onerror=1> {token}'), '&lt;img src=x onerror=1&gt; ' + token.ICON);
});

test('every Mini App page that shows credits loads the icon', () => {
  for (const page of ['webapp/index.html', 'webapp/knowledge-workspace.html', 'webapp/payments.html', 'webapp/docs-pricing.html']) {
    const html = read(page);
    assert.ok(html.includes('token-icon.css'), page);
    assert.ok(html.includes('token-icon.js'), page);
  }
  for (const page of readdirSync(new URL('../webapp', import.meta.url)).filter((name) => /^docs-.*\.html$/.test(name))) {
    assert.ok(read('webapp/' + page).includes('css/token-icon.css'), page);
  }
  const index = read('webapp/index.html');
  assert.ok(index.indexOf('js/token-icon.js') < index.indexOf('js/language.js'), 'loaded before every script that uses it');
});

test('no Mini App file uses the old emoji any more', () => {
  const found = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = dir + '/' + name;
      if (statSync(full).isDirectory()) { if (name !== 'assets') walk(full); continue; }
      if (!/\.(js|mjs|html|css|json)$/.test(name)) continue;
      if (readFileSync(full, 'utf8').includes('\u26A1')) found.push(full);
    }
  };
  walk(new URL('../webapp', import.meta.url).pathname);
  assert.deepEqual(found, []);
});

test('the dead demo shop (old emoji packs) is gone', () => {
  assert.ok(!read('webapp/js/data.js').includes('shopData'));
  assert.ok(!read('webapp/js/ui.js').includes('shopCard'));
  assert.ok(!read('webapp/js/cabinet.js').includes('shopGrid'));
  assert.ok(!read('webapp/js/language.js').includes('invite_d'));
});

test('the Website copies, when checked out next to this repo, are identical', (t) => {
  const site = new URL('../../sylvex-website/', import.meta.url);
  if (!existsSync(site)) return t.skip('sylvex-website is not checked out alongside');
  assert.equal(readFileSync(new URL('js/token-icon.js', site), 'utf8'), read('webapp/js/token-icon.js'));
  assert.equal(readFileSync(new URL('css/token-icon.css', site), 'utf8'), read('webapp/css/token-icon.css'));
});
