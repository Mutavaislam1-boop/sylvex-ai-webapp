// Run with: node --test tests/test_feedback_prompt.mjs
//
// "Как вам SYLVEX?": stars (PeekRating), an optional comment, Send, Remind
// me later, Don't show again and ×. The server decides when it shows,
// counted in successful generations (services/reviews.py); answers land in
// the Admin Console «Отзывы». js/feedback-prompt.js is the same file as the
// website's.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const module_ = read('webapp/js/feedback-prompt.js');
const css = read('webapp/css/feedback-prompt.css');
const js = read('webapp/js/cabinet.js');
const index = read('webapp/index.html');
const main = read('main.py');
const rules = read('services/reviews.py');
const layout = read('admin_console/src/Layout.tsx');
const page = read('admin_console/src/pages/Reviews.tsx');

test('the Mini App loads the prompt with fresh pins', () => {
  assert.match(index, /<link rel="stylesheet" href="css\/feedback-prompt\.css\?v=reviews-20261028" \/>/);
  assert.match(index, /<script src="js\/feedback-prompt\.js\?v=reviews-20261028"><\/script>/);
  assert.match(index, /<script src="js\/cabinet\.js\?v=generation-centered-download-20261029"><\/script>/);
});

test('five stars with grades, the comment, Send only after a rating, later, never and ×', () => {
  assert.match(module_, /labels: \['Плохо', 'Так себе', 'Хорошо', 'Отлично', 'Превосходно'\]/);
  assert.match(module_, /send: 'Отправить отзыв', later: 'Напомнить позже', never: 'Больше не показывать', close: 'Закрыть'/);
  assert.match(module_, /state\.root\.querySelector\('\[data-sxf-send\]'\)\.classList\.toggle\('is-ready', state\.value > 0\);/);
  assert.match(module_, /if \(action === 'send' && !state\.value\) \{ setError\(t\.pick\); return; \}/);
  assert.match(module_, /setTimeout\(function \(\) \{ close\(current\); \}, 2600\);/);
  assert.match(css, /\.sxf-dock\{/);
});

test('the Mini App asks the server on the home screen and reports every answer', () => {
  assert.match(js, /const res = await fetch\('\/api\/public\/feedback\/state'\);/);
  assert.match(js, /if \(!home \|\| !home\.classList\.contains\('active'\) \|\| Date\.now\(\) - feedbackCheckedAt < 20000\) return;/);
  assert.match(js, /lang: 'ru',\n\s+theme: document\.documentElement\.getAttribute\('data-theme'\) === 'light' \? 'light' : 'dark',\n\s+onAnswer: sendFeedback,/);
  assert.match(js, /sendFeedback\('shown'\)\.catch\(\(\) => \{\}\);/);
  assert.match(js, /body: JSON\.stringify\(\{ action, \.\.\.\(payload \|\| \{\}\), surface: 'miniapp' \}\),/);
  assert.match(js, /initNotifications\(\);\n\s+initFeedbackPrompt\(\);/);
});

test('the rules: 5 generations, 2 after a purchase, × +10, later +25', () => {
  assert.match(rules, /FIRST_AT = 5\nAFTER_PURCHASE = 2\nAFTER_CLOSE = 10\nAFTER_LATER = 25/);
  assert.match(main, /@app\.get\("\/api\/public\/feedback\/state"\)/);
  assert.match(main, /@app\.post\("\/api\/public\/feedback"\)/);
  assert.match(main, /@app\.post\("\/api\/admin\/reviews\/list"\)\nasync def admin_reviews_list\(request: Request\):\n\s+payload = await request\.json\(\)\n\n\s+def work\(cursor\):\n\s+actor = _admin_actor\(payload, request, "users\.view"\)/);
});

test('the Admin Console has «Отзывы»: summary, stars, the list with a filter', () => {
  assert.match(layout, /\{ key: "reviews", label: "Reviews", icon: "★", permission: "users\.view" \},/);
  assert.match(page, /post<\{ items: Review\[\]; total: number; summary: Summary \}>\("\/api\/admin\/reviews\/list", \{ rating, limit: PAGE, offset \}\)/);
  assert.match(page, /<Kpi label=\{t\("Closed with ×"\)\} value=\{fmtNum\(s\.closes\)\} \/>/);
});
