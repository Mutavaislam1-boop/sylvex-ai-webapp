// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/account-auth.js
// Cross-platform identity UI: the standalone-browser login/register gate
// (spec requirement #24-#26) and the "Linked accounts" panel (Connect
// Telegram from a browser session, Connect Email from inside Telegram -
// requirements #6-#20). Talks only to the existing /api/web/* and
// /api/account/link/* endpoints in services/account_identity.py; never
// touches the Telegram Mini App's own initData auth path.
// =====================================================
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});

  function mountRoot() {
    // Always document.body, never .studio/#app-root: those stay display:none
    // during the app's own loading phase, which would silently collapse a
    // position:fixed overlay mounted inside them to 0x0. Falls back to
    // hard-coded colors below (matching the app's dark theme) since --st-*
    // variables are scoped to .studio and would not resolve on body anyway.
    return document.body;
  }

  function el(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  let stylesInjected = false;
  function ensureStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const style = document.createElement('style');
    style.textContent = `
      .sylvexAuth-overlay{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);padding:16px;}
      .sylvexAuth-card{position:relative;width:100%;max-width:380px;max-height:88vh;overflow:auto;background:var(--st-bg-2,#1c1c1e);color:var(--st-text,#f2f2f2);border:1px solid var(--st-border,rgba(255,255,255,.12));border-radius:16px;padding:22px 20px 20px;box-shadow:0 20px 60px rgba(0,0,0,.4);font-family:inherit;}
      .sylvexAuth-close{position:absolute;top:10px;right:10px;width:28px;height:28px;border-radius:50%;border:none;background:var(--st-bg-3,rgba(255,255,255,.08));color:var(--st-text,#f2f2f2);font-size:18px;line-height:1;cursor:pointer;}
      .sylvexAuth-title{font-size:17px;font-weight:700;margin:4px 0 14px;padding-right:20px;}
      .sylvexAuth-sub{font-size:13px;color:var(--st-dim,#9a9aa2);margin:-8px 0 14px;line-height:1.45;}
      .sylvexAuth-field{display:block;width:100%;box-sizing:border-box;padding:11px 12px;margin-bottom:10px;border-radius:10px;border:1px solid var(--st-border,rgba(255,255,255,.14));background:var(--st-bg,#0c0c0d);color:var(--st-text,#f2f2f2);font-size:14px;}
      .sylvexAuth-btn{display:block;width:100%;box-sizing:border-box;padding:11px 12px;margin-bottom:10px;border-radius:10px;border:none;background:var(--st-accent,#5b8dff);color:#fff;font-size:14px;font-weight:600;cursor:pointer;text-align:center;}
      .sylvexAuth-btn.secondary{background:var(--st-bg-3,rgba(255,255,255,.08));color:var(--st-text,#f2f2f2);}
      .sylvexAuth-btn.danger{background:transparent;color:#ff6b6b;border:1px solid rgba(255,107,107,.4);}
      .sylvexAuth-btn[disabled]{opacity:.5;cursor:not-allowed;}
      .sylvexAuth-link{display:block;text-align:center;font-size:13px;color:var(--st-accent,#5b8dff);cursor:pointer;margin-top:2px;padding:6px 0;}
      .sylvexAuth-error{font-size:13px;color:#ff6b6b;margin:-4px 0 10px;min-height:1em;}
      .sylvexAuth-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--st-line,rgba(255,255,255,.08));font-size:14px;}
      .sylvexAuth-row:last-child{border-bottom:none;}
      .sylvexAuth-row .v{color:var(--st-dim,#9a9aa2);font-size:13px;text-align:right;}
      .sylvexAuth-summary{background:var(--st-bg,#0c0c0d);border:1px solid var(--st-border,rgba(255,255,255,.12));border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.7;margin-bottom:14px;}
      .sylvexAuth-summary b{color:var(--st-text,#f2f2f2);}
      .sylvexAuth-warn{background:rgba(255,180,60,.1);border:1px solid rgba(255,180,60,.35);color:#ffb43c;border-radius:10px;padding:10px 12px;font-size:13px;margin-bottom:12px;line-height:1.5;}
      .sylvexAuth-perm{font-size:12px;color:var(--st-mute,#6f6f78);text-align:center;margin-top:8px;line-height:1.5;}
      #sylvexTelegramWidgetHost{display:flex;justify-content:center;margin:6px 0 12px;}
    `;
    document.head.appendChild(style);
  }

  function closeOverlay(overlay) {
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }

  function openOverlay(bodyHtml, options) {
    ensureStyles();
    const opts = options || {};
    const overlay = el(
      '<div class="sylvexAuth-overlay" role="dialog" aria-modal="true">' +
        '<div class="sylvexAuth-card"><button type="button" class="sylvexAuth-close" aria-label="Close">×</button>' +
        '<div class="sylvexAuth-body"></div></div></div>'
    );
    overlay.querySelector('.sylvexAuth-body').innerHTML = bodyHtml;
    const doClose = () => { closeOverlay(overlay); if (opts.onClose) opts.onClose(); };
    if (opts.persistent) {
      overlay.querySelector('.sylvexAuth-close').style.display = 'none';
    } else {
      overlay.querySelector('.sylvexAuth-close').onclick = doClose;
      overlay.addEventListener('click', (e) => { if (e.target === overlay) doClose(); });
    }
    mountRoot().appendChild(overlay);
    return overlay;
  }

  function setBody(overlay, html) { overlay.querySelector('.sylvexAuth-body').innerHTML = html; }
  function q(overlay, sel) { return overlay.querySelector(sel); }

  async function apiFetch(path, options) {
    const opts = Object.assign({ credentials: 'include', headers: { 'Content-Type': 'application/json' } }, options || {});
    let res, json = {};
    try {
      res = await fetch(path, opts);
      json = await res.json().catch(() => ({}));
    } catch {
      return { ok: false, status: 0, json: { error: 'network_error' } };
    }
    return { ok: res.ok, status: res.status, json };
  }

  function telegramInitData() { return (S.tg && S.tg.initData) || ''; }
  function metaContent(name) {
    const tag = document.querySelector(`meta[name="${name}"]`);
    return tag ? (tag.getAttribute('content') || '').trim() : '';
  }

  // ---------------------------------------------------------------------
  // Google / Apple sign-in (feature-detected: hidden if not configured -
  // see spec requirement #21/#22. Apple additionally needs a paid Apple
  // Developer Services ID configured server-side; see AccountError
  // apple_oauth_not_configured / WEB_API_CONTRACT.md).
  // ---------------------------------------------------------------------
  let googleReady = null;
  function loadGoogleSdk() {
    if (googleReady) return googleReady;
    googleReady = new Promise((resolve) => {
      if (window.google && window.google.accounts && window.google.accounts.id) return resolve(true);
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true; s.defer = true;
      s.onload = () => resolve(!!(window.google && window.google.accounts && window.google.accounts.id));
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
    return googleReady;
  }

  let appleReady = null;
  function loadAppleSdk() {
    if (appleReady) return appleReady;
    appleReady = new Promise((resolve) => {
      if (window.AppleID && window.AppleID.auth) return resolve(true);
      const s = document.createElement('script');
      s.src = 'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js';
      s.async = true;
      s.onload = () => resolve(!!(window.AppleID && window.AppleID.auth));
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
    return appleReady;
  }

  async function signInWithGoogle() {
    const clientId = metaContent('sylvex-google-client-id');
    if (!clientId) { toast('Google sign-in is not configured yet'); return null; }
    const ok = await loadGoogleSdk();
    if (!ok) { toast('Could not load Google sign-in'); return null; }
    return new Promise((resolve) => {
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (resp) => resolve(resp && resp.credential ? resp.credential : null),
      });
      window.google.accounts.id.prompt((notification) => {
        if (notification && (notification.isNotDisplayed() || notification.isSkippedMoment())) resolve(null);
      });
    });
  }

  async function signInWithApple() {
    const clientId = metaContent('sylvex-apple-client-id');
    const redirectUri = metaContent('sylvex-apple-redirect-uri');
    if (!clientId || !redirectUri) { toast('Sign in with Apple is not configured yet'); return null; }
    const ok = await loadAppleSdk();
    if (!ok) { toast('Could not load Sign in with Apple'); return null; }
    try {
      window.AppleID.auth.init({ clientId, scope: 'name email', redirectURI: redirectUri, usePopup: true });
      const result = await window.AppleID.auth.signIn();
      return (result && result.authorization && result.authorization.id_token) || null;
    } catch {
      return null;
    }
  }

  // ---------------------------------------------------------------------
  // Login / register gate (spec requirement #24/#25): shown whenever the
  // web session is unauthenticated and there is no real Telegram identity
  // to fall back on (standalone browser, or the website's own embed).
  // ---------------------------------------------------------------------
  let authGateOpen = false;

  function ensureWebAuthGate() {
    if (authGateOpen) return;
    if (S.usesWebSessionAuth && !S.usesWebSessionAuth()) return;
    openWebAuthGate();
  }

  function openWebAuthGate() {
    if (authGateOpen) return;
    authGateOpen = true;
    let mode = 'login';
    const overlay = openOverlay('', { persistent: true });

    function render() {
      const isLogin = mode === 'login';
      const hasGoogle = !!metaContent('sylvex-google-client-id');
      const hasApple = !!(metaContent('sylvex-apple-client-id') && metaContent('sylvex-apple-redirect-uri'));
      setBody(overlay,
        `<div class="sylvexAuth-title">${isLogin ? 'Sign in to SYLVEX' : 'Create your SYLVEX account'}</div>
         <div class="sylvexAuth-sub">${isLogin ? 'Use your SYLVEX website account, or Telegram if it has already been connected.' : 'This creates your SYLVEX account and SYLVEX ID automatically.'}</div>
         <div class="sylvexAuth-error" id="saErr"></div>
         <input class="sylvexAuth-field" type="email" id="saEmail" placeholder="Email" autocomplete="email">
         <input class="sylvexAuth-field" type="password" id="saPass" placeholder="Password" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
         <button class="sylvexAuth-btn" id="saSubmit">${isLogin ? 'Sign in' : 'Register'}</button>
         ${hasGoogle ? '<button class="sylvexAuth-btn secondary" id="saGoogle">Continue with Google</button>' : ''}
         ${hasApple ? '<button class="sylvexAuth-btn secondary" id="saApple">Sign in with Apple</button>' : ''}
         <div id="saTgHost"></div>
         <div class="sylvexAuth-link" id="saToggle">${isLogin ? 'New to SYLVEX? Create an account' : 'Already have an account? Sign in'}</div>
         ${isLogin ? '<div class="sylvexAuth-link" id="saForgot">Forgot password?</div>' : ''}`
      );
      q(overlay, '#saToggle').onclick = () => { mode = isLogin ? 'register' : 'login'; render(); };
      if (isLogin) q(overlay, '#saForgot').onclick = () => openForgotPassword(overlay);
      q(overlay, '#saSubmit').onclick = () => submit(isLogin);
      if (hasGoogle) q(overlay, '#saGoogle').onclick = () => oauthFlow('google');
      if (hasApple) q(overlay, '#saApple').onclick = () => oauthFlow('apple');
      mountTelegramWidget(q(overlay, '#saTgHost'), async (payload) => {
        const res = await apiFetch('/api/web/auth/telegram', { method: 'POST', body: JSON.stringify(payload) });
        if (!res.ok) { showErr(res.json.error === 'telegram_not_linked'
          ? 'This Telegram account is not connected to a SYLVEX account yet. Register with email, then connect Telegram from Linked Accounts.'
          : (res.json.error || 'Could not sign in with Telegram')); return; }
        await onAuthenticated();
      });
    }

    function showErr(msg) { const e = q(overlay, '#saErr'); if (e) e.textContent = msg || ''; }

    async function oauthFlow(provider) {
      showErr('');
      const idToken = provider === 'google' ? await signInWithGoogle() : await signInWithApple();
      if (!idToken) return;
      const res = await apiFetch(`/api/web/auth/${provider}`, { method: 'POST', body: JSON.stringify({ id_token: idToken }) });
      if (!res.ok) { showErr(res.json.error || 'Sign-in failed'); return; }
      await onAuthenticated();
    }

    async function submit(isLogin) {
      showErr('');
      const email = q(overlay, '#saEmail').value.trim();
      const password = q(overlay, '#saPass').value;
      if (!email || !password) { showErr('Enter your email and password'); return; }
      const btn = q(overlay, '#saSubmit'); btn.disabled = true;
      const res = await apiFetch(isLogin ? '/api/web/auth/login' : '/api/web/auth/register', {
        method: 'POST', body: JSON.stringify({ email, password }),
      });
      btn.disabled = false;
      if (!res.ok) { showErr(friendlyAuthError(res.json.error)); return; }
      await onAuthenticated();
    }

    async function onAuthenticated() {
      authGateOpen = false;
      closeOverlay(overlay);
      if (S.syncWebSession) await S.syncWebSession();
      if (S.renderSubscription) S.renderSubscription();
      refreshLinkedStatusBadge();
      toast('Signed in');
    }

    render();
  }
  S.ensureWebAuthGate = ensureWebAuthGate;
  S.openWebAuthGate = openWebAuthGate;

  function friendlyAuthError(code) {
    return ({
      invalid_email: 'Enter a valid email address',
      password_too_short: 'Password must be at least 8 characters',
      email_already_registered: 'An account with this email already exists',
      invalid_credentials: 'Incorrect email or password',
      accounts_not_configured: 'Accounts are not available right now',
    })[code] || 'Something went wrong, please try again';
  }

  function openForgotPassword(parentOverlay) {
    const overlay = openOverlay(
      `<div class="sylvexAuth-title">Reset your password</div>
       <div class="sylvexAuth-error" id="fpErr"></div>
       <input class="sylvexAuth-field" type="email" id="fpEmail" placeholder="Email" autocomplete="email">
       <button class="sylvexAuth-btn" id="fpSubmit">Send reset link</button>`,
      { onClose: () => {} }
    );
    q(overlay, '#fpSubmit').onclick = async () => {
      const email = q(overlay, '#fpEmail').value.trim();
      if (!email) return;
      await apiFetch('/api/web/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
      setBody(overlay, '<div class="sylvexAuth-title">Check your email</div><div class="sylvexAuth-sub">If that email has a SYLVEX account, a reset link is on its way.</div>');
    };
  }

  // ---------------------------------------------------------------------
  // Telegram Login Widget embed (website-initiated Connect Telegram
  // direction, spec requirement #7) - the real widget, not a hand-rolled
  // login form, per Telegram's own docs.
  // ---------------------------------------------------------------------
  let widgetCallbackSeq = 0;
  function mountTelegramWidget(host, onAuth) {
    if (!host) return;
    const botUsername = metaContent('sylvex-telegram-bot') || 'sylvexai_bot';
    const cbName = 'sylvexTgWidgetCb' + (++widgetCallbackSeq);
    window[cbName] = (user) => { onAuth(user); };
    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', 'medium');
    script.setAttribute('data-radius', '10');
    script.setAttribute('data-onauth', `${cbName}(user)`);
    script.setAttribute('data-request-access', 'write');
    host.innerHTML = '';
    host.appendChild(script);
  }

  // ---------------------------------------------------------------------
  // Linked Accounts panel: entry point from Profile ("Linked accounts").
  // Context-aware per spec requirement #26: a real Telegram Mini App shows
  // Connect Email (#8); a browser/web session shows Connect Telegram (#7).
  // ---------------------------------------------------------------------
  async function refreshLinkedStatusBadge() {
    const badge = document.getElementById('profileLinkedStatus');
    if (!badge) return;
    try {
      if (S.hasTelegramContext && S.hasTelegramContext()) {
        const res = await apiFetch('/api/account/link-status?initData=' + encodeURIComponent(telegramInitData()));
        badge.textContent = res.json.connected ? 'Connected' : 'Connect email';
      } else {
        const res = await apiFetch('/api/web/session/me');
        badge.textContent = res.json.authenticated ? (res.json.telegram_connected ? 'Connected' : 'Connect Telegram') : 'Sign in';
      }
    } catch { badge.textContent = '—'; }
  }
  S.refreshLinkedAccountsBadge = refreshLinkedStatusBadge;

  function openLinkedAccounts() {
    if (S.hasTelegramContext && S.hasTelegramContext()) {
      openLinkedAccountsFromTelegram();
    } else {
      openLinkedAccountsFromWeb();
    }
  }
  S.openLinkedAccounts = openLinkedAccounts;

  function renderMergeSummary(preview) {
    const res = preview.resolution || {};
    let subLine = 'No active subscription on either side.';
    if (res.surviving_plan) {
      subLine = `Subscription after merge: <b>${res.surviving_plan === 'sub_year' ? 'Pro · 1 year' : 'Pro · 1 month'}</b>` +
        (res.credits_from_conversion ? ` &mdash; the other side's unused subscription time converts to <b>${res.credits_from_conversion.toLocaleString()} ⚡</b>` : '');
    }
    let warn = '';
    if (preview.requires_subscription_confirmation) {
      warn = `<div class="sylvexAuth-warn">Both accounts have an active subscription. Only one can survive the merge - the other's remaining paid time becomes SYLVEX credits (⚡), never extra months. Review below and confirm to continue.</div>`;
    }
    return `
      ${warn}
      <div class="sylvexAuth-summary">
        Website balance: <b>${Number(preview.website_balance || 0).toLocaleString()} ⚡</b><br>
        Telegram balance: <b>${Number(preview.telegram_balance || 0).toLocaleString()} ⚡</b><br>
        Combined balance after merge: <b>${Number(preview.combined_balance || 0).toLocaleString()} ⚡</b><br>
        ${subLine}
      </div>
      <div class="sylvexAuth-sub">After confirmation these accounts will become one SYLVEX account. This action cannot be reversed through normal account settings.</div>
    `;
  }

  // --- Web-session direction: Connect Telegram ---
  function openLinkedAccountsFromWeb() {
    apiFetch('/api/web/session/me').then((res) => {
      if (!res.json.authenticated) { openWebAuthGate(); return; }
      renderWebLinkedPanel(res.json);
    });
  }

  function renderWebLinkedPanel(session) {
    const overlay = openOverlay('');
    function base() {
      setBody(overlay,
        `<div class="sylvexAuth-title">Linked accounts</div>
         <div class="sylvexAuth-row"><span>Email</span><span class="v">${session.email ? (session.email_verified ? session.email : session.email + ' (unverified)') : 'Not set'}</span></div>
         <div class="sylvexAuth-row"><span>Google</span><span class="v">${session.oauth && session.oauth.google ? 'Connected' : 'Not connected'}</span></div>
         <div class="sylvexAuth-row"><span>Apple</span><span class="v">${session.oauth && session.oauth.apple ? 'Connected' : 'Not connected'}</span></div>
         <div class="sylvexAuth-row"><span>Telegram</span><span class="v">${session.telegram_connected ? ('@' + (session.telegram_username || '')) + ' · Connected' : 'Not connected'}</span></div>
         ${session.telegram_connected ? '' : '<div id="wlaConnectHost"></div>'}
         <div class="sylvexAuth-perm">${session.telegram_connected ? 'Connecting Telegram is a one-time, permanent merge and cannot be undone from here.' : 'Connecting Telegram permanently merges its balance, subscription and history into this account.'}</div>`
      );
      if (!session.telegram_connected) {
        mountTelegramWidget(q(overlay, '#wlaConnectHost'), (payload) => previewFromWidget(payload));
      }
    }

    async function previewFromWidget(payload) {
      const res = await apiFetch('/api/web/account/telegram/preview', { method: 'POST', body: JSON.stringify(payload) });
      if (!res.ok) {
        setBody(overlay, res.json.conflict
          ? '<div class="sylvexAuth-title">Already connected</div><div class="sylvexAuth-warn">This Telegram account is already connected to another SYLVEX account.</div>'
          : `<div class="sylvexAuth-title">Could not connect</div><div class="sylvexAuth-warn">${res.json.error || 'Something went wrong'}</div>`);
        return;
      }
      if (res.json.status === 'already_linked') { toast('Already connected'); base(); return; }
      setBody(overlay,
        `<div class="sylvexAuth-title">Confirm merge</div>
         ${renderMergeSummary(res.json)}
         <button class="sylvexAuth-btn" id="wlaConfirm">Confirm merge</button>
         <button class="sylvexAuth-btn secondary" id="wlaCancel">Cancel</button>`
      );
      q(overlay, '#wlaCancel').onclick = () => base();
      q(overlay, '#wlaConfirm').onclick = () => confirmFromWidget(payload, res.json.requires_subscription_confirmation);
    }

    async function confirmFromWidget(payload, needsSubConfirm) {
      const res = await apiFetch('/api/web/account/telegram/confirm', {
        method: 'POST', body: JSON.stringify(Object.assign({}, payload, { confirmed_subscription_merge: !!needsSubConfirm })),
      });
      if (!res.ok) {
        setBody(overlay, `<div class="sylvexAuth-title">Could not connect</div><div class="sylvexAuth-warn">${res.json.error || 'Something went wrong'}</div>`);
        return;
      }
      if (S.syncWebSession) await S.syncWebSession();
      refreshLinkedStatusBadge();
      setBody(overlay, '<div class="sylvexAuth-title">Connected</div><div class="sylvexAuth-sub">Your Telegram and website accounts are now one SYLVEX account.</div>');
      toast('Accounts merged');
    }

    base();
  }

  // --- Telegram direction: Connect Email ("Connect existing SYLVEX account") ---
  function openLinkedAccountsFromTelegram() {
    apiFetch('/api/account/link-status?initData=' + encodeURIComponent(telegramInitData())).then((res) => {
      renderTelegramLinkedPanel(res.json || {});
    });
  }

  function renderTelegramLinkedPanel(status) {
    const overlay = openOverlay('');
    function base() {
      setBody(overlay,
        `<div class="sylvexAuth-title">Linked accounts</div>
         <div class="sylvexAuth-row"><span>Telegram</span><span class="v">Connected</span></div>
         <div class="sylvexAuth-row"><span>SYLVEX Web Account</span><span class="v">${status.connected ? (status.email || 'Connected') : 'Not connected'}</span></div>
         ${status.connected ? '<div class="sylvexAuth-perm">This is a permanent, one-time merge and cannot be undone from here.</div>' : ''}
         ${status.connected ? '' : '<button class="sylvexAuth-btn" id="tlaConnect">Connect existing SYLVEX account</button>'}`
      );
      if (!status.connected) q(overlay, '#tlaConnect').onclick = () => stepEmail();
    }

    function stepEmail() {
      setBody(overlay,
        `<div class="sylvexAuth-title">Connect Email</div>
         <div class="sylvexAuth-sub">Enter the email address of your existing SYLVEX website account. We'll send it a one-time code.</div>
         <div class="sylvexAuth-error" id="tlaErr"></div>
         <input class="sylvexAuth-field" type="email" id="tlaEmail" placeholder="Email" autocomplete="email">
         <button class="sylvexAuth-btn" id="tlaSend">Send code</button>
         <button class="sylvexAuth-link" id="tlaBack">Back</button>`
      );
      q(overlay, '#tlaBack').onclick = () => base();
      q(overlay, '#tlaSend').onclick = async () => {
        const email = q(overlay, '#tlaEmail').value.trim();
        if (!email) return;
        const btn = q(overlay, '#tlaSend'); btn.disabled = true;
        const res = await apiFetch('/api/account/link/request-code', {
          method: 'POST', body: JSON.stringify({ email, initData: telegramInitData() }),
        });
        btn.disabled = false;
        if (!res.ok) { q(overlay, '#tlaErr').textContent = res.json.error === 'code_recently_sent' ? 'Please wait a minute before requesting another code' : (res.json.error || 'Could not send code'); return; }
        stepCode(email);
      };
    }

    function stepCode(email) {
      setBody(overlay,
        `<div class="sylvexAuth-title">Enter the code</div>
         <div class="sylvexAuth-sub">We sent a 6-digit code to ${email}. It expires in 10 minutes.</div>
         <div class="sylvexAuth-error" id="tlaCodeErr"></div>
         <input class="sylvexAuth-field" inputmode="numeric" maxlength="6" id="tlaCode" placeholder="6-digit code">
         <button class="sylvexAuth-btn" id="tlaVerify">Continue</button>
         <button class="sylvexAuth-link" id="tlaBack2">Back</button>`
      );
      q(overlay, '#tlaBack2').onclick = () => stepEmail();
      q(overlay, '#tlaVerify').onclick = async () => {
        const code = q(overlay, '#tlaCode').value.trim();
        if (!code) return;
        const btn = q(overlay, '#tlaVerify'); btn.disabled = true;
        const res = await apiFetch('/api/account/link/preview', {
          method: 'POST', body: JSON.stringify({ email, code, initData: telegramInitData() }),
        });
        btn.disabled = false;
        if (!res.ok) {
          q(overlay, '#tlaCodeErr').textContent = res.json.conflict
            ? 'This SYLVEX account is already connected to another Telegram account.'
            : (res.json.error === 'invalid_or_expired_code' ? 'That code is invalid or has expired' : (res.json.error || 'Something went wrong'));
          return;
        }
        if (res.json.status === 'already_linked') { toast('Already connected'); base(); return; }
        stepConfirm(email, code, res.json);
      };
    }

    function stepConfirm(email, code, preview) {
      setBody(overlay,
        `<div class="sylvexAuth-title">Confirm merge</div>
         ${renderMergeSummary(preview)}
         <button class="sylvexAuth-btn" id="tlaConfirm">Confirm merge</button>
         <button class="sylvexAuth-btn secondary" id="tlaCancel">Cancel</button>`
      );
      q(overlay, '#tlaCancel').onclick = () => base();
      q(overlay, '#tlaConfirm').onclick = async () => {
        const res = await apiFetch('/api/account/link/confirm', {
          method: 'POST',
          body: JSON.stringify({ email, code, initData: telegramInitData(), confirmed_subscription_merge: !!preview.requires_subscription_confirmation }),
        });
        if (!res.ok) {
          setBody(overlay, `<div class="sylvexAuth-title">Could not connect</div><div class="sylvexAuth-warn">${res.json.error || 'Something went wrong'}</div>`);
          return;
        }
        if (S.syncUser) await S.syncUser({ force: true });
        refreshLinkedStatusBadge();
        setBody(overlay, '<div class="sylvexAuth-title">Connected</div><div class="sylvexAuth-sub">Your Telegram and website accounts are now one SYLVEX account.</div>');
        toast('Accounts merged');
      };
    }

    base();
  }
})();
