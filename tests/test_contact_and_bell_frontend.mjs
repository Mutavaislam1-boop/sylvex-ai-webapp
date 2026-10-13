// Mini App: Contact administrator / Contact sales open the internal popup
// (posting to the Admin Console Inbox) instead of a personal Telegram, and
// the notification bell reads the shared SYLVEX Team history.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const lang = readFileSync(new URL('../webapp/js/language.js', import.meta.url), 'utf8');

assert.doesNotMatch(cabinet, /t\.me\/sylvex_admin/, 'no redirect to a personal Telegram account');
assert.match(cabinet, /function contactAdmin\(topic\) \{\s*openSupport\(/);
assert.match(cabinet, /onContactSales: \(\) => openSupport\('sales'\)/);
assert.match(cabinet, /fetch\('\/api\/public\/contact'/);
assert.doesNotMatch(cabinet, /sendToBot\(\{ type: 'support'/, 'support no longer relies on tg.sendData');
assert.match(cabinet, /\/api\/public\/notifications\?surface=miniapp/);
assert.match(cabinet, /\/api\/public\/notifications\/read/);
assert.match(html, /id="notifBtn"/);
assert.match(cabinet, /const onHome = !!\(home && home\.classList\.contains\('active'\)\)/, 'bell only on the home screen');
assert.match(html, /id="notifPop"/);
for (const key of ['notif_title', 'notif_empty', 'contact_title', 'support_failed']) {
  assert.match(lang, new RegExp(key + ':'), `translation ${key}`);
}
console.log('contact + bell frontend: ok');
