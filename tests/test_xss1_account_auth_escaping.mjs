import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const accountAuth = readFileSync(new URL('../webapp/js/account-auth.js', import.meta.url), 'utf8');

test('browser identity panel escapes server-provided email', () => {
  assert.match(accountAuth, /S\.escapeHtml\(session\.email_verified \? session\.email : session\.email \+ ' \(unverified\)'\)/);
});

test('browser identity UI has no self-service Telegram linking or merging', () => {
  assert.doesNotMatch(accountAuth, /telegram-widget|auth\/telegram|account\/telegram|account\/link|Connect Telegram|Confirm merge/i);
  assert.match(accountAuth, /Your SYLVEX web account is independent from Telegram/);
});
