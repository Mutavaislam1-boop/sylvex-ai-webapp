const { chromium } = require('playwright');
const base = process.argv[2];
const session = { authenticated: true, display_name: `Tom & Jerry's "Studio" <3`, username: 'tom_j',
  email: "o'neil+tag@example.com", has_email: true, email_verified: true, has_password: true,
  oauth: { google: 'tom@gmail.com' }, subscription_plan: 'Pro', member_since: '2026-10-01',
  sylvex_user_id: 42, balance: 100, generations_count: 3, generations_this_month: 1 };
(async () => {
  const browser = await chromium.launch(); const out = [];
  for (const path of ['/account/profile.html', '/account/settings.html']) {
    const page = await browser.newPage();
    await page.route('**/*', (r) => { const u = new URL(r.request().url());
      if (u.pathname === '/api/web/session/me') return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) });
      if (u.pathname.startsWith('/api/')) return r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
      if (u.origin !== new URL(base).origin) return r.abort(); return r.continue(); });
    await page.goto(base + path); await page.waitForSelector('#sxDashContent .sx-dash-panel'); await page.waitForTimeout(500);
    out.push(await page.evaluate((s) => { const root = document.getElementById('sxDashContent'); const t = root.textContent;
      const h2 = root.querySelector('.sx-profile-head h2'); const input = document.getElementById('setName');
      return { path: location.pathname, entity_text_visible: /&amp;|&quot;|&#39;|&lt;/.test(t),
        heading_exact: h2 ? h2.textContent === s.display_name : null, input_exact: input ? input.value === s.display_name : null,
        email_shown: t.includes(s.email) || t.includes('o') , google_shown: t.includes(s.oauth.google),
        sidebar_name_exact: (document.getElementById('sxSidebarAccountName') || {}).textContent === s.display_name };
    }, session)); await page.close(); }
  await browser.close(); console.log(JSON.stringify(out, null, 1));
  process.exit(out.some((o) => o.entity_text_visible || o.heading_exact === false || o.input_exact === false) ? 1 : 0);
})();
