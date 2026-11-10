// Drives the built Admin Console with a mocked API and a fake Telegram.WebApp.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const dist = process.argv[2], out = process.argv[3];
const scenario = { enrolled: true };
(async () => {
  const browser = await chromium.launch();
  const results = {};
  async function run(name, opts) {
    const page = await browser.newPage({ viewport: { width: 390, height: 780 }, deviceScaleFactor: 1 });
    const calls = [];
    let state = { mfa: false, enrolled: opts.enrolled };
    await page.route('https://telegram.org/**', (r) => r.fulfill({ contentType: 'text/javascript',
      body: 'window.Telegram={WebApp:{initData:"query_id=x&user=%7B%22id%22%3A1%7D&hash=abc",ready(){},expand(){},close(){window.__closed=true},onEvent(){}}};' }));
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.host === 'telegram.org') return route.fulfill({ contentType: 'text/javascript',
        body: 'window.Telegram={WebApp:{initData:"query_id=x&user=%7B%22id%22%3A1%7D&hash=abc",ready(){},expand(){},close(){window.__closed=true},onEvent(){}}};' });
      if (url.host !== 'admin.test') return route.abort();
      if (url.pathname.startsWith('/api/')) {
        const body = route.request().postData() ? JSON.parse(route.request().postData()) : null;
        calls.push([url.pathname, body]);
        const json = (status, data) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
        const me = () => ({ ok: true, csrf_token: 'c', admin: { admin_id: 1, sylvex_user_id: '42', role: 'owner', status: 'active', permissions: [], grants: [], denies: [], totp_enabled: state.enrolled },
          identity: null, session: { channel: 'miniapp', reauth_fresh: true, mfa_verified: state.mfa },
          telegram_confirmation: { confirmed: state.mfa, critical: state.mfa, valid_until: state.mfa ? new Date(Date.now() + 1800e3).toISOString() : null, critical_until: null } });
        if (url.pathname === '/api/admin/v2/auth/telegram') {
          if (state.enrolled && !body.totp) return json(401, { detail: 'totp_required' });
          if (state.enrolled && body.totp !== '123456') return json(401, { detail: 'totp_invalid' });
          state.mfa = state.enrolled; state.session = true;
          return json(200, { ok: true, session_token: 't', csrf_token: 'c', totp_enrollment_required: !state.enrolled, session: { mfa_verified: state.mfa } });
        }
        if (url.pathname === '/api/admin/v2/auth/me') return state.session ? json(200, me()) : json(401, { detail: 'admin_session_required' });
        if (url.pathname === '/api/admin/v2/auth/totp/enroll') return json(200, { ok: true, secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/SYLVEX%20Admin:42?secret=JBSWY3DPEHPK3PXP' });
        if (url.pathname === '/api/admin/v2/auth/totp/confirm') { state.mfa = true; state.enrolled = true; return json(200, { ok: true }); }
        return json(200, { ok: true, items: [] });
      }
      const file = path.join(dist, url.pathname.replace(/^\/admin\/?/, '') || 'index.html');
      const real = fs.existsSync(file) && fs.statSync(file).isFile() ? file : path.join(dist, 'index.html');
      const type = real.endsWith('.js') ? 'text/javascript' : real.endsWith('.css') ? 'text/css' : 'text/html';
      return route.fulfill({ status: 200, contentType: type, body: fs.readFileSync(real) });
    });
    await page.goto('https://admin.test/admin/' + (opts.query || ''));
    page.on('console', (m) => { if (m.type() === 'error') console.error('console:', m.text()); });
    page.on('pageerror', (e) => console.error('pageerror:', e.message));
    let r;
    try { r = await opts.steps(page, calls); } catch (e) { r = { error: e.message.split('\n')[0], body: (await page.textContent('body')).slice(0, 300), calls: calls.map(c => c[0]) }; }
    results[name] = r;
    await page.screenshot({ path: path.join(out, name + '.png') });
    await page.close();
  }
  await run('enrolled_login', { enrolled: true, steps: async (page, calls) => {
    await page.waitForSelector('input[autocomplete="one-time-code"]', { timeout: 10000 });
    const form = await page.textContent('form');
    await page.fill('input[autocomplete="one-time-code"]', '000000');
    await page.click('button.btn.primary');
    await page.waitForSelector('.notice.bad');
    const wrong = await page.textContent('.notice.bad');
    await page.fill('input[autocomplete="one-time-code"]', '123456');
    await page.click('button.btn.primary');
    await page.waitForFunction(() => !document.querySelector('input[autocomplete="one-time-code"]'), null, { timeout: 10000 });
    const sent = calls.filter(c => c[0] === '/api/admin/v2/auth/telegram').map(c => c[1].totp || null);
    return { code_form: /2FA/.test(form), wrong_code_message: wrong, totp_sent: sent, console_open: !(await page.$('input[autocomplete="one-time-code"]')) };
  }});
  await run('not_enrolled', { enrolled: false, steps: async (page, calls) => {
    await page.waitForSelector('.notice.warn', { timeout: 10000 });
    const notice = await page.textContent('.notice.warn');
    await page.click('button:has-text("Set up authenticator")');
    await page.waitForSelector('img.qr', { timeout: 10000 });
    await page.fill('input[placeholder="123456"]', '654321');
    await page.click('button:has-text("Turn on")');
    await page.waitForFunction(() => !document.querySelector('img.qr'), null, { timeout: 10000 });
    return { enrollment_notice: notice, enroll_called: calls.some(c => c[0].endsWith('/totp/enroll')), confirm_body: (calls.find(c => c[0].endsWith('/totp/confirm')) || [])[1] };
  }});
  await run('bot_confirm', { enrolled: true, query: '?confirm=bot', steps: async (page) => {
    await page.waitForSelector('input[autocomplete="one-time-code"]');
    await page.fill('input[autocomplete="one-time-code"]', '123456');
    await page.click('button.btn.primary');
    await page.waitForSelector('.notice.good', { timeout: 10000 });
    const text = await page.textContent('.notice.good');
    await page.click('button.btn.primary');
    return { confirmed_text: text, closed: await page.evaluate(() => !!window.__closed) };
  }});
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})().catch((e) => { console.error(e); process.exit(2); });
