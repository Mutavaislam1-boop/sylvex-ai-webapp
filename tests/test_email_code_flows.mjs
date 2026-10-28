// Run with: node --test tests/test_email_code_flows.mjs
//
// Every sign-up waits for the code emailed to the address (the old instant
// /api/web/auth/register route is gone), typed into code slots
// (js/code-slots.js); deleting the account sends a code to the account's
// email and, once it is accepted, a hold button (js/hold-button.js)
// deletes it with the confirm token. Both files are the same as the
// website's.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const main = read('main.py');
const security = read('services/security.py');
const identity = read('services/account_identity.py');
const auth = read('webapp/js/account-auth.js');
const cabinet = read('webapp/js/cabinet.js');
const slots = read('webapp/js/code-slots.js');
const hold = read('webapp/js/hold-button.js');
const index = read('webapp/index.html');

test('no route creates an account without the emailed code', () => {
  assert.doesNotMatch(main, /@app\.post\("\/api\/web\/auth\/register"\)/);
  assert.doesNotMatch(security, /'\/api\/web\/auth\/register',/);
  assert.doesNotMatch(auth, /'\/api\/web\/auth\/register'/);
});

test('deletion: start, verify, then delete with the confirm token', () => {
  for (const path of ['/api/web/account/delete/start', '/api/web/account/delete/verify', '/api/web/account/delete']) {
    assert.match(main, new RegExp('@app\\.post\\("' + path.replace(/\//g, '\\/') + '"\\)'), path);
  }
  assert.match(main, /account_identity_service\.delete_account,\n\s+DATABASE_URL, account_id, payload\.get\("confirm_token"\),/);
  assert.match(identity, /raise AccountError\("deletion_not_confirmed", 403\)/);
  assert.match(security, /'\/api\/web\/account\/delete\/start', '\/api\/web\/account\/delete\/verify',/);
});

test('the Mini App loads the shared modules with fresh pins', () => {
  for (const file of ['code-slots', 'hold-button']) {
    assert.match(index, new RegExp('<link rel="stylesheet" href="css/' + file + '\\.css\\?v=email-code-20261028" />'), file);
    assert.match(index, new RegExp('<script src="js/' + file + '\\.js\\?v=email-code-20261028"></script>'), file);
  }
  assert.ok(index.indexOf('js/code-slots.js') < index.indexOf('js/account-auth.js'));
});

test('code slots: wrong code drains red, right code washes with a tick', () => {
  assert.match(slots, /if \(next === 'error'\) \{/);
  assert.match(slots, /open\.tween\(1, WASH_IN, 0\);/);
  assert.match(slots, /autocomplete="one-time-code"/);
});

test('the Mini App delete sheet: Russian, code then hold, no password or DELETE', () => {
  assert.match(cabinet, /'<h3 style="margin:6px 0 10px;font-size:17px">Удалить аккаунт SYLVEX\?<\/h3>'/);
  assert.match(cabinet, /label: 'Удерживайте, чтобы удалить', doneLabel: 'Аккаунт удалён'/);
  assert.match(cabinet, /backgroundColor: '#27272a', fillColor: '#f60303', textColor: '#f5f5f5', fillTextColor: '#ffffff',/);
  assert.match(cabinet, /invalid_code: \(d\) => d\.attempts_left \? `Неверный код\. Осталось попыток: \$\{d\.attempts_left\}\.` : 'Неверный код\.',/);
  assert.match(hold, /if \(phase !== 'holding' \|\| performance\.now\(\) - start < holdTime - 50\) return;/);
});
