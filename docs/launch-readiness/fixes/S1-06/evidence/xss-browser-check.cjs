// S1-06: load account/profile.html and account/settings.html in Chromium with
// a session whose every user-controlled field carries HTML/JS payloads, and
// check that nothing executes and the text is shown literally.
// Usage: node xss-browser-check.cjs http://127.0.0.1:PORT
const { chromium } = require('playwright');

const base = process.argv[2];
const P = (n) => `"'><img src=x onerror="window.__xss.push(${n})"><svg onload="window.__xss.push(${n}+100)"></svg><script>window.__xss.push(${n}+200)</script>`;
const session = {
  authenticated: true,
  display_name: 'Ann ' + P(1),
  username: 'u' + P(2),
  avatar_url: 'x" onerror="window.__xss.push(3)',
  email: 'a' + P(4) + '@example.com',
  has_email: true,
  email_verified: true,
  has_password: true,
  oauth: { google: 'g' + P(5), apple: 'a' + P(6) },
  subscription_plan: 'Pro' + P(7),
  member_since: '2026' + P(8),
  sylvex_user_id: '42' + P(9),
  balance: 100,
  generations_count: 3,
  generations_this_month: 1,
};

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const page_path of ['/account/profile.html', '/account/settings.html']) {
    const page = await browser.newPage();
    await page.addInitScript(() => { window.__xss = []; window.alert = () => window.__xss.push('alert'); });
    await page.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/web/session/me') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) });
      }
      if (url.pathname.startsWith('/api/')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
      }
      if (url.origin !== new URL(base).origin) return route.abort();
      return route.continue();
    });
    await page.goto(base + page_path, { waitUntil: 'load' });
    await page.waitForSelector('#sxDashContent .sx-dash-panel', { timeout: 15000 });
    await page.waitForTimeout(800);
    const r = await page.evaluate((s) => {
      const root = document.getElementById('sxDashContent');
      const injected = root.querySelectorAll('img[src="x"], svg[onload], script, [onerror]');
      const text = root.textContent;
      const shown = ['display_name', 'username', 'email', 'subscription_plan', 'member_since']
        .filter((k) => s[k] && text.includes(String(s[k]).slice(0, 12)));
      const input = document.getElementById('setName');
      return {
        executed: window.__xss.slice(),
        injected_elements: injected.length,
        name_text_literal: text.includes(s.display_name),
        name_input_value_literal: input ? input.value === s.display_name : null,
        fields_shown_as_text: shown,
      };
    }, session);
    results.push({ page: page_path, ...r });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
  const bad = results.some((r) => r.executed.length || r.injected_elements);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
