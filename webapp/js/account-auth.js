// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/account-auth.js
// Identity UI for the standalone Browser Mini App. It authenticates with a
// SYLVEX web session (email/Google/Apple) and never links to or merges with
// a Telegram identity. The real Telegram Mini App keeps its own initData
// authentication in its separate client boundary.
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
      .sylvexAuth-overlay{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);padding:16px;}
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
      .sylvexAuth-guest{color:var(--st-dim,#9a9aa2);margin-top:6px;}
      .sylvexAuth-code{display:flex;justify-content:center;margin:4px 0 14px;}
      .sylvexAuth-error{font-size:13px;color:#ff6b6b;margin:-4px 0 10px;min-height:1em;}
      .sylvexAuth-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--st-line,rgba(255,255,255,.08));font-size:14px;}
      .sylvexAuth-row:last-child{border-bottom:none;}
      .sylvexAuth-row .v{color:var(--st-dim,#9a9aa2);font-size:13px;text-align:right;}
      .sylvexAuth-summary{background:var(--st-bg,#0c0c0d);border:1px solid var(--st-border,rgba(255,255,255,.12));border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.7;margin-bottom:14px;}
      .sylvexAuth-summary b{color:var(--st-text,#f2f2f2);}
      .sylvexAuth-warn{background:rgba(255,180,60,.1);border:1px solid rgba(255,180,60,.35);color:#ffb43c;border-radius:10px;padding:10px 12px;font-size:13px;margin-bottom:12px;line-height:1.5;}
      .sylvexAuth-perm{font-size:12px;color:var(--st-mute,#6f6f78);text-align:center;margin-top:8px;line-height:1.5;}
      #sylvexTelegramWidgetHost{display:flex;justify-content:center;margin:6px 0 12px;}
      .sylvexAuth-gbtn{display:flex;justify-content:center;margin:-2px 0 10px;}
      .sylvexAuth-gbtn:empty{display:none;}
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

  // The emailed code is typed into code slots (js/code-slots.js): a wrong
  // code drains them red, the right one washes them and shows a tick, which
  // stays CODE_ACCEPTED_MS before the next screen.
  const CODE_ACCEPTED_MS = 800;
  function mountCodeEntry(host, { light, onCode }) {
    const slots = window.SylvexCodeSlots.mount(host, { length: 6, autoFocus: true, ariaLabel: 'Verification code', onComplete: onCode });
    if (light) slots.el.classList.add('light');
    return slots;
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

  // The page ships an empty <meta name="sylvex-google-client-id">; like the
  // website (js/oauth-buttons.js) it is filled from GET /api/web/auth/config,
  // the public GOOGLE_OAUTH_CLIENT_ID the backend verifies tokens against.
  let authConfigReady = null;
  function loadAuthConfig() {
    if (authConfigReady) return authConfigReady;
    authConfigReady = apiFetch('/api/web/auth/config').then((res) => {
      const config = res.json || {};
      if (config.google_enabled && config.google_client_id) {
        const meta = document.querySelector('meta[name="sylvex-google-client-id"]');
        if (meta && !meta.getAttribute('content')) meta.setAttribute('content', config.google_client_id);
      }
    }).catch(() => {});
    return authConfigReady;
  }
  S.loadAuthConfig = loadAuthConfig;

  // Same Google flow as the website (One Tap prompt). When the browser does
  // not show the prompt (blocked, dismissed recently, Safari), the official
  // Google button is rendered into `fallbackHost`; the promise resolves when
  // either one returns a credential.
  async function signInWithGoogle(fallbackHost) {
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
        if (!notification || !(notification.isNotDisplayed() || notification.isSkippedMoment())) return;
        if (fallbackHost && window.google.accounts.id.renderButton) {
          fallbackHost.innerHTML = '';
          window.google.accounts.id.renderButton(fallbackHost, { type: 'standard', theme: 'outline', size: 'large', text: 'continue_with', width: 300 });
        } else {
          resolve(null);
        }
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
  // A guest who closed the window is not asked again on every reload in this
  // browser tab; account actions still open it when they need an account.
  const GATE_DISMISSED_KEY = 'sylvex-auth-gate-dismissed';
  function gateDismissed() {
    try { return sessionStorage.getItem(GATE_DISMISSED_KEY) === '1'; } catch { return false; }
  }

  function ensureWebAuthGate() {
    // The standalone browser app asks on every page load without a session
    // (closing the screen lasts until the next load); the website embed
    // remembers the dismissal for the tab.
    const browserApp = !!(S.isBrowserApp && S.isBrowserApp());
    if (authGateOpen || (!browserApp && gateDismissed())) return;
    if (S.usesWebSessionAuth && !S.usesWebSessionAuth()) return;
    openWebAuthGate();
  }

  // Optional sign-in: the window can be closed (×, outside, "Continue as
  // guest") and the app stays usable as a guest.
  // options.reason: why an account is needed, shown on the browser screen
  // (e.g. a guest pressing Generate).
  function openWebAuthGate(options) {
    if (authGateOpen) return;
    if (S.isBrowserApp && S.isBrowserApp()) { openBrowserAuthScreen(null, options && options.reason); return; }
    authGateOpen = true;
    let mode = 'login';
    const overlay = openOverlay('', {
      onClose: () => {
        authGateOpen = false;
        try { sessionStorage.setItem(GATE_DISMISSED_KEY, '1'); } catch {}
      },
    });

    function render() {
      const isLogin = mode === 'login';
      const hasGoogle = !!metaContent('sylvex-google-client-id');
      const hasApple = !!(metaContent('sylvex-apple-client-id') && metaContent('sylvex-apple-redirect-uri'));
      setBody(overlay,
        `<div class="sylvexAuth-title">${isLogin ? 'Sign in to SYLVEX' : 'Create your SYLVEX account'}</div>
         <div class="sylvexAuth-sub">${isLogin ? 'Use your SYLVEX account from sylvex.ai.' : 'One SYLVEX account for sylvex.ai and the SYLVEX browser app.'}</div>
         <div class="sylvexAuth-error" id="saErr"></div>
         ${isLogin ? '' : '<input class="sylvexAuth-field" type="text" id="saName" placeholder="Display name" autocomplete="name">'}
         <input class="sylvexAuth-field" type="email" id="saEmail" placeholder="Email" autocomplete="email">
         <input class="sylvexAuth-field" type="password" id="saPass" placeholder="Password" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
         ${isLogin ? '' : '<input class="sylvexAuth-field" type="password" id="saConfirm" placeholder="Confirm password" autocomplete="new-password">'}
         <button class="sylvexAuth-btn" id="saSubmit">${isLogin ? 'Sign in' : 'Create Account'}</button>
         ${hasGoogle ? '<button class="sylvexAuth-btn secondary" id="saGoogle">Continue with Google</button><div class="sylvexAuth-gbtn" id="saGoogleHost"></div>' : ''}
         ${hasApple ? '<button class="sylvexAuth-btn secondary" id="saApple">Sign in with Apple</button>' : ''}
         <div class="sylvexAuth-link" id="saToggle">${isLogin ? 'New to SYLVEX? Create an account' : 'Already have an account? Sign in'}</div>
         ${isLogin ? '<div class="sylvexAuth-link" id="saForgot">Forgot password?</div>' : ''}
         <div class="sylvexAuth-link sylvexAuth-guest" id="saGuest">Continue as guest</div>`
      );
      q(overlay, '#saGuest').onclick = () => q(overlay, '.sylvexAuth-close').click();
      q(overlay, '#saToggle').onclick = () => { mode = isLogin ? 'register' : 'login'; render(); };
      if (isLogin) q(overlay, '#saForgot').onclick = () => openForgotPassword(overlay);
      q(overlay, '#saSubmit').onclick = () => submit(isLogin);
      if (hasGoogle) q(overlay, '#saGoogle').onclick = () => oauthFlow('google');
      if (hasApple) q(overlay, '#saApple').onclick = () => oauthFlow('apple');
    }

    function showErr(msg) { const e = q(overlay, '#saErr'); if (e) e.textContent = msg || ''; }

    async function oauthFlow(provider) {
      showErr('');
      const idToken = provider === 'google' ? await signInWithGoogle(q(overlay, '#saGoogleHost')) : await signInWithApple();
      if (!idToken) return;
      const res = await apiFetch(`/api/web/auth/${provider}`, { method: 'POST', body: JSON.stringify({ id_token: idToken }) });
      if (!res.ok) { showErr(friendlyAuthError(res.json.error, res.status)); return; }
      await onAuthenticated();
    }

    // Same checks and messages as the website (sylvex-website/js/auth-forms.js).
    async function submit(isLogin) {
      showErr('');
      const email = q(overlay, '#saEmail').value.trim();
      const password = q(overlay, '#saPass').value;
      if (!EMAIL_RE.test(email)) { showErr('Enter a valid email address.'); return; }
      if (isLogin && !password) { showErr('Enter your password.'); return; }
      if (!isLogin && password.length < 8) { showErr('Password must be at least 8 characters.'); return; }
      if (!isLogin && password !== q(overlay, '#saConfirm').value) { showErr('Passwords do not match.'); return; }
      const btn = q(overlay, '#saSubmit'); btn.disabled = true;
      const body = isLogin ? { email, password } : { email, password, display_name: q(overlay, '#saName').value.trim() };
      const res = await apiFetch(isLogin ? '/api/web/auth/login' : '/api/web/auth/register/start', {
        method: 'POST', body: JSON.stringify(body),
      });
      btn.disabled = false;
      if (!res.ok) { showErr(friendlyAuthError(res.json.error, res.status, res.json)); return; }
      if (isLogin) await onAuthenticated();
      else renderCode({ email: res.json.email || email, token: res.json.registration_token });
    }

    // Creating an account: the 6-digit code emailed by register/start.
    function renderCode(pending) {
      setBody(overlay,
        `<div class="sylvexAuth-title">Check your email</div>
         <div class="sylvexAuth-sub">We sent a 6-digit code to <b>${esc(pending.email)}</b>. Enter it to finish creating your account.</div>
         <div class="sylvexAuth-code" id="saCode"></div>
         <div class="sylvexAuth-error" id="saErr"></div>
         <div class="sylvexAuth-link" id="saResend">Resend code</div>
         <div class="sylvexAuth-link" id="saBack">Use a different email</div>`
      );
      const slots = mountCodeEntry(q(overlay, '#saCode'), {
        light: document.documentElement.getAttribute('data-theme') === 'light',
        onCode: async (code) => {
          showErr('');
          const res = await apiFetch('/api/web/auth/register/verify', {
            method: 'POST', body: JSON.stringify({ email: pending.email, registration_token: pending.token, code }),
          });
          if (res.ok) { slots.setStatus('success'); setTimeout(onAuthenticated, CODE_ACCEPTED_MS); return; }
          slots.setStatus('error');
          showErr(friendlyAuthError(res.json.error, res.status, res.json));
        },
      });
      q(overlay, '#saResend').onclick = async () => {
        const res = await apiFetch('/api/web/auth/register/resend', {
          method: 'POST', body: JSON.stringify({ email: pending.email, registration_token: pending.token }),
        });
        slots.clear();
        showErr(res.ok ? 'We sent a new code. Codes from earlier emails no longer work.' : friendlyAuthError(res.json.error, res.status, res.json));
      };
      q(overlay, '#saBack').onclick = () => { mode = 'register'; render(); };
    }

    async function onAuthenticated() {
      authGateOpen = false;
      closeOverlay(overlay);
      await completeWebSignIn();
    }

    // Render at once, then again when the Google client id has loaded.
    render();
    loadAuthConfig().then(() => { if (authGateOpen && metaContent('sylvex-google-client-id') && !q(overlay, '#saGoogle')) render(); });
  }
  S.ensureWebAuthGate = ensureWebAuthGate;
  S.openWebAuthGate = openWebAuthGate;

  async function completeWebSignIn() {
    // Start from the server's account data only - nothing from the guest
    // session (placeholder name, avatar, appearance) is kept or saved.
    if (S.isBrowserApp && S.isBrowserApp()) {
      S.user = {};
      try { localStorage.removeItem('sylvex-profile-save-pending'); } catch {}
    }
    if (S.syncWebSession) await S.syncWebSession();
    if (S.renderSubscription) S.renderSubscription();
    if (S.onWebSignedIn) S.onWebSignedIn();
    refreshLinkedStatusBadge();
  }

  // ---------------------------------------------------------------------
  // Standalone browser Mini App: full-screen sign-in page (white, SYLVEX
  // intro video, Continue with Google, email log in / create account with a
  // mandatory emailed code, legal footer). Same SYLVEX accounts and web
  // session as sylvex.ai; the website iframe embed keeps the window above
  // and the Telegram Mini App never reaches either.
  // ---------------------------------------------------------------------
  const WEBSITE_URL = 'https://sylvex.ai';
  // Last frame of the intro video, shown whenever it does not play.
  const INTRO_LAST_FRAME = 'assets/auth/sylvex-intro-v3-poster.jpg';
  const PENDING_REGISTRATION_KEY = 'sylvex-pending-registration';
  const GOOGLE_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="#4285F4" d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47c-.28 1.5-1.13 2.78-2.4 3.63v3.02h3.89c2.28-2.1 3.56-5.2 3.56-8.84z"/><path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.95-2.9l-3.89-3.02c-1.08.72-2.46 1.15-4.06 1.15-3.12 0-5.77-2.11-6.72-4.94H1.27v3.11C3.25 21.3 7.31 24 12 24z"/><path fill="#FBBC05" d="M5.28 14.29A7.2 7.2 0 0 1 4.9 12c0-.8.14-1.57.38-2.29V6.6H1.27A11.97 11.97 0 0 0 0 12c0 1.94.46 3.77 1.27 5.4z"/><path fill="#EA4335" d="M12 4.77c1.77 0 3.35.61 4.6 1.8l3.45-3.45C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.7 1.27 6.6l4.01 3.11C6.23 6.88 8.88 4.77 12 4.77z"/></svg>';
  const APPLE_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="currentColor"><path d="M16.365 1.43c0 1.14-.462 2.16-1.207 2.94-.822.85-2.09 1.5-3.18 1.41-.14-1.1.41-2.24 1.2-3.02.83-.85 2.24-1.47 3.19-1.33zM20.6 17.06c-.5 1.16-.74 1.68-1.38 2.7-.9 1.42-2.16 3.2-3.72 3.21-1.39.02-1.75-.9-3.64-.89-1.89.01-2.29.91-3.68.89-1.56-.02-2.76-1.61-3.66-3.02C1.5 16.66.85 12.02 2.5 8.83c1.02-1.98 2.85-3.23 4.83-3.26 1.42-.03 2.75.96 3.62.96.86 0 2.5-1.18 4.21-1.01.72.03 2.73.29 4.02 2.19-.1.06-2.4 1.4-2.38 4.19.03 3.33 2.91 4.44 2.94 4.46-.02.08-.46 1.58-1.14 2.7z"/></svg>';
  const EYE_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';

  function esc(value) {
    return S.escapeHtml ? S.escapeHtml(String(value == null ? '' : value)) : String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  function readPendingRegistration() {
    try {
      const data = JSON.parse(sessionStorage.getItem(PENDING_REGISTRATION_KEY) || 'null');
      return data && data.email && data.token ? data : null;
    } catch { return null; }
  }
  function writePendingRegistration(data) {
    try {
      if (data) sessionStorage.setItem(PENDING_REGISTRATION_KEY, JSON.stringify(data));
      else sessionStorage.removeItem(PENDING_REGISTRATION_KEY);
    } catch {}
  }

  // Plays the intro once per page load and stays on its last frame (the
  // SYLVEX wordmark at 2 s - the files are cut there) until the page is
  // reloaded - never a loop or a replay.
  // Reopening the screen, reduced motion or a refused autoplay show that
  // last frame as a still. Returns stop().
  let introPlayed = false;
  function runIntroVideo(video) {
    const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const still = () => { video.poster = INTRO_LAST_FRAME; };
    video.muted = true;
    video.defaultMuted = true;
    video.loop = false;
    video.controls = false;
    if (reduced || introPlayed) {
      still();
      video.preload = 'none';
      return () => {};
    }
    introPlayed = true;
    const p = video.play();
    if (p && p.catch) p.catch(still);
    return () => { try { video.pause(); } catch {} };
  }

  // Google Identity Services, initialized once; the official "Continue with
  // Google" button (renderButton) opens Google's own sign-in window on every
  // tap. The previous One Tap prompt() path did nothing at all whenever
  // Google suppressed the prompt (closed once before, third-party cookies
  // blocked, FedCM), which is why the browser button looked broken.
  let googleInitFor = '';
  let googleCredentialHandler = null;
  function initGoogleOnce(clientId) {
    if (googleInitFor === clientId) return;
    googleInitFor = clientId;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (resp) => { if (googleCredentialHandler && resp && resp.credential) googleCredentialHandler(resp.credential); },
      ux_mode: 'popup',
      auto_select: false,
      cancel_on_tap_outside: true,
    });
  }

  let browserAuthClose = null;
  function openBrowserAuthScreen(initialMode, reason) {
    if (authGateOpen) return;
    authGateOpen = true;
    const pending = readPendingRegistration();
    const state = {
      mode: initialMode || (pending ? 'code' : 'login'),
      reason: typeof reason === 'string' ? reason : '',
      email: pending ? pending.email : '',
      pending,
      googleState: 'loading',
      busy: false,
      tick: 0,
    };
    const year = new Date().getFullYear();
    const root = el(
      `<div class="sxAuth" role="dialog" aria-modal="true" aria-labelledby="sxaTitle">
        <button type="button" class="sxAuth-close" id="sxaClose" aria-label="Close">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
        <div class="sxAuth-scroll">
          <main class="sxAuth-main">
            <div class="sxAuth-hero" aria-hidden="true">
              <video class="sxAuth-video" muted playsinline webkit-playsinline preload="auto" disablepictureinpicture disableremoteplayback x-webkit-airplay="deny" tabindex="-1" width="960" height="644">
                <source src="assets/auth/sylvex-intro-v3.mp4" type='video/mp4; codecs="avc1.640020"'>
                <source src="assets/auth/sylvex-intro-v3.webm" type='video/webm; codecs="vp9"'>
              </video>
            </div>
            <div class="sxAuth-head" id="sxaHead"></div>
            <div class="sxAuth-social" id="sxaSocial">
              <div class="sxAuth-google" id="sxaGoogle">
                <button type="button" class="sxAuth-btn sxAuth-gbtn" id="sxaGoogleBtn">${GOOGLE_ICON}<span>Continue with Google</span></button>
                <div class="sxAuth-gis" id="sxaGis"></div>
              </div>
              <div id="sxaApple"></div>
              <div class="sxAuth-or"><span>or</span></div>
            </div>
            <div class="sxAuth-body" id="sxaBody"></div>
          </main>
          <footer class="sxAuth-footer">
            <nav aria-label="Legal">
              <a href="${WEBSITE_URL}/legal/privacy.html" target="_blank" rel="noopener">Privacy Policy</a>
              <a href="${WEBSITE_URL}/legal/terms.html" target="_blank" rel="noopener">Terms of Use</a>
              <a href="${WEBSITE_URL}/" target="_blank" rel="noopener">About Us</a>
            </nav>
            <p>© ${year} SYLVEX. All rights reserved.</p>
          </footer>
        </div>
      </div>`
    );
    const $ = (sel) => root.querySelector(sel);
    document.documentElement.classList.add('sxAuth-open');
    mountRoot().appendChild(root);
    const stopVideo = runIntroVideo($('.sxAuth-video'));
    let ticker = 0;
    let codeSlots = null;

    function close(dismissed) {
      if (!root.isConnected) return;
      authGateOpen = false;
      browserAuthClose = null;
      clearInterval(ticker);
      stopVideo();
      googleCredentialHandler = null;
      document.removeEventListener('keydown', onKey);
      document.documentElement.classList.remove('sxAuth-open');
      root.remove();
    }
    browserAuthClose = close;
    function onKey(e) { if (e.key === 'Escape') close(true); }
    document.addEventListener('keydown', onKey);
    $('#sxaClose').onclick = () => close(true);

    // Signed in: reload, so the account starts from its own data on the
    // server - nothing from the guest visit is kept or merged into it.
    async function finish() {
      writePendingRegistration(null);
      root.classList.add('is-done');
      window.location.reload();
    }

    function showErr(msg, tone) {
      const box = $('#sxaErr');
      if (!box) return;
      box.textContent = msg || '';
      box.classList.toggle('is-info', tone === 'info');
    }
    function setBusy(button, busy, label) {
      state.busy = busy;
      if (!button) return;
      button.disabled = busy;
      button.classList.toggle('is-busy', busy);
      if (label) button.querySelector('span').textContent = label;
    }

    // ----- Google -----
    googleCredentialHandler = async (idToken) => {
      if (!root.isConnected) return;
      showErr('');
      const res = await apiFetch('/api/web/auth/google', { method: 'POST', body: JSON.stringify({ id_token: idToken }) });
      if (!res.ok) { showErr(friendlyAuthError(res.json.error, res.status)); return; }
      await finish();
    };
    $('#sxaGoogleBtn').onclick = () => {
      if (state.googleState === 'loading') showErr('Google sign-in is loading. Please try again in a moment.', 'info');
      else showErr('Google sign-in isn’t available right now. Please use email or try again later.');
    };
    async function mountGoogle() {
      await loadAuthConfig();
      const clientId = metaContent('sylvex-google-client-id');
      const ok = clientId && await loadGoogleSdk();
      if (!root.isConnected) return;
      if (!ok || !window.google.accounts.id.renderButton) { state.googleState = 'unavailable'; return; }
      initGoogleOnce(clientId);
      const host = $('#sxaGis');
      const width = Math.max(220, Math.min(400, Math.round($('#sxaGoogle').getBoundingClientRect().width || 360)));
      window.google.accounts.id.renderButton(host, {
        type: 'standard', theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with',
        logo_alignment: 'center', width, locale: 'en',
      });
      state.googleState = 'ready';
      $('#sxaGoogle').classList.add('is-ready');
    }
    mountGoogle();

    if (metaContent('sylvex-apple-client-id') && metaContent('sylvex-apple-redirect-uri')) {
      $('#sxaApple').innerHTML = `<button type="button" class="sxAuth-btn sxAuth-gbtn" id="sxaAppleBtn">${APPLE_ICON}<span>Continue with Apple</span></button>`;
      $('#sxaAppleBtn').onclick = async () => {
        showErr('');
        const idToken = await signInWithApple();
        if (!idToken) return;
        const res = await apiFetch('/api/web/auth/apple', { method: 'POST', body: JSON.stringify({ id_token: idToken }) });
        if (!res.ok) { showErr(friendlyAuthError(res.json.error, res.status)); return; }
        await finish();
      };
    }

    // ----- views -----
    function render() {
      clearInterval(ticker);
      ticker = 0;
      const mode = state.mode;
      root.dataset.mode = mode;
      $('#sxaSocial').hidden = !(mode === 'login' || mode === 'register');
      if (mode === 'login' || mode === 'register') renderCredentials(mode === 'login');
      else if (mode === 'code') renderCode();
      else if (mode === 'forgot') renderForgot();
      const focus = root.querySelector('[data-autofocus]');
      if (focus && window.matchMedia && window.matchMedia('(pointer: fine)').matches) focus.focus();
    }

    function passwordField(id, placeholder, autocomplete) {
      return `<div class="sxAuth-pass">
          <input class="sxAuth-input" type="password" id="${id}" placeholder="${placeholder}" aria-label="${placeholder}" autocomplete="${autocomplete}" minlength="8" required>
          <button type="button" class="sxAuth-eye" data-eye="${id}" aria-label="Show password">${EYE_ICON}</button>
        </div>`;
    }

    function renderCredentials(isLogin) {
      const sub = state.reason ? esc(state.reason) : (isLogin ? 'One account for sylvex.ai and the SYLVEX app.' : 'We’ll email you a code to confirm your address.');
      $('#sxaHead').innerHTML = isLogin
        ? '<h1 class="sxAuth-title" id="sxaTitle">Log in to SYLVEX</h1><p class="sxAuth-sub">' + sub + '</p>'
        : '<h1 class="sxAuth-title" id="sxaTitle">Create your SYLVEX account</h1><p class="sxAuth-sub">' + sub + '</p>';
      $('#sxaBody').innerHTML =
        `<form class="sxAuth-form" id="sxaForm" novalidate>
          <input class="sxAuth-input" type="email" id="sxaEmail" placeholder="Email" aria-label="Email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" required value="${esc(state.email)}" data-autofocus>
          ${passwordField('sxaPass', 'Password', isLogin ? 'current-password' : 'new-password')}
          ${isLogin ? '' : passwordField('sxaConfirm', 'Confirm password', 'new-password')}
          ${isLogin ? '' : '<p class="sxAuth-hint">At least 8 characters.</p>'}
          <p class="sxAuth-error" id="sxaErr" role="alert" aria-live="polite"></p>
          <button type="submit" class="sxAuth-btn sxAuth-primary" id="sxaSubmit"><span>${isLogin ? 'Log in' : 'Continue'}</span></button>
        </form>
        ${isLogin ? '<button type="button" class="sxAuth-link" id="sxaForgot">Forgot password?</button>' : ''}
        <p class="sxAuth-switch">${isLogin ? 'New to SYLVEX?' : 'Already have an account?'} <button type="button" class="sxAuth-link is-strong" id="sxaSwitch">${isLogin ? 'Create account' : 'Log in'}</button></p>
`;
      $('#sxaEmail').addEventListener('input', (e) => { state.email = e.target.value.trim(); });
      root.querySelectorAll('[data-eye]').forEach((btn) => {
        btn.onclick = () => {
          const input = $('#' + btn.dataset.eye);
          const show = input.type === 'password';
          input.type = show ? 'text' : 'password';
          btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
          btn.classList.toggle('is-on', show);
        };
      });
      $('#sxaSwitch').onclick = () => { state.mode = isLogin ? 'register' : 'login'; render(); };
      if (isLogin) {
        $('#sxaForgot').onclick = () => { state.mode = 'forgot'; render(); };
      }
      $('#sxaForm').onsubmit = (e) => { e.preventDefault(); if (!state.busy) (isLogin ? submitLogin() : submitRegister()); };
    }

    async function submitLogin() {
      showErr('');
      const email = $('#sxaEmail').value.trim();
      const password = $('#sxaPass').value;
      if (!EMAIL_RE.test(email)) { showErr('Enter a valid email address.'); return; }
      if (!password) { showErr('Enter your password.'); return; }
      const btn = $('#sxaSubmit');
      setBusy(btn, true, 'Logging in…');
      const res = await apiFetch('/api/web/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
      if (!root.isConnected) return;
      setBusy(btn, false, 'Log in');
      if (!res.ok) { showErr(friendlyAuthError(res.json.error, res.status)); return; }
      await finish();
    }

    async function submitRegister() {
      showErr('');
      const email = $('#sxaEmail').value.trim();
      const password = $('#sxaPass').value;
      if (!EMAIL_RE.test(email)) { showErr('Enter a valid email address.'); return; }
      if (password.length < 8) { showErr('Password must be at least 8 characters.'); return; }
      if (password !== $('#sxaConfirm').value) { showErr('Passwords do not match.'); return; }
      const btn = $('#sxaSubmit');
      setBusy(btn, true, 'Sending code…');
      const res = await apiFetch('/api/web/auth/register/start', { method: 'POST', body: JSON.stringify({ email, password }) });
      if (!root.isConnected) return;
      setBusy(btn, false, 'Continue');
      if (!res.ok) {
        const previous = readPendingRegistration();
        // A code for this email went out moments ago from this tab: go on
        // to entering it instead of sending another.
        if (res.json.error === 'code_recently_sent' && previous && previous.email.toLowerCase() === email.toLowerCase()) {
          previous.resendAt = Date.now() + (Number(res.json.retry_after) || 60) * 1000;
          openCode(previous);
          return;
        }
        showErr(friendlyAuthError(res.json.error, res.status, res.json));
        return;
      }
      const now = Date.now();
      openCode({
        email: res.json.email || email,
        token: res.json.registration_token,
        expiresAt: now + (Number(res.json.expires_in) || 600) * 1000,
        resendAt: now + (Number(res.json.resend_in) || 60) * 1000,
      });
    }

    function openCode(pendingData) {
      state.pending = pendingData;
      state.email = pendingData.email;
      writePendingRegistration(pendingData);
      state.mode = 'code';
      render();
    }

    function clock(ms) {
      const total = Math.max(0, Math.ceil(ms / 1000));
      return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0');
    }

    function renderCode() {
      const p = state.pending;
      if (!p) { state.mode = 'register'; render(); return; }
      $('#sxaHead').innerHTML =
        `<h1 class="sxAuth-title" id="sxaTitle">Check your email</h1>
         <p class="sxAuth-sub">We sent a 6-digit code to <b>${esc(p.email)}</b>. Enter it to finish creating your account.</p>`;
      $('#sxaBody').innerHTML =
        `<div class="sxAuth-form">
          <div class="sxAuth-codehost" id="sxaCode"></div>
          <p class="sxAuth-meta" id="sxaExpiry"></p>
          <p class="sxAuth-error" id="sxaErr" role="alert" aria-live="polite"></p>
        </div>
        <p class="sxAuth-switch">Didn’t get it? <button type="button" class="sxAuth-link is-strong" id="sxaResend"></button></p>
        <button type="button" class="sxAuth-link" id="sxaBack">Use a different email</button>`;
      codeSlots = mountCodeEntry($('#sxaCode'), { light: true, onCode: (code) => { if (!state.busy) submitCode(code); } });
      $('#sxaResend').onclick = () => resendCode();
      $('#sxaBack').onclick = () => { writePendingRegistration(null); state.pending = null; state.mode = 'register'; render(); };
      tickCode();
      ticker = setInterval(tickCode, 1000);
    }

    function tickCode() {
      const p = state.pending;
      const expiry = $('#sxaExpiry');
      const resend = $('#sxaResend');
      if (!p || !expiry || !resend) return;
      const now = Date.now();
      const left = (p.expiresAt || 0) - now;
      expiry.textContent = left > 0 ? `Code expires in ${clock(left)}` : 'This code has expired. Request a new one below.';
      expiry.classList.toggle('is-expired', left <= 0);
      const wait = (p.resendAt || 0) - now;
      resend.disabled = wait > 0;
      resend.textContent = wait > 0 ? `Resend code in ${clock(wait)}` : 'Resend code';
    }

    async function submitCode(code) {
      showErr('');
      const p = state.pending;
      const slots = codeSlots;
      state.busy = true;
      const res = await apiFetch('/api/web/auth/register/verify', {
        method: 'POST', body: JSON.stringify({ email: p.email, registration_token: p.token, code }),
      });
      state.busy = false;
      if (!root.isConnected) return;
      if (res.ok) {
        slots.setStatus('success');
        setTimeout(() => { if (root.isConnected) finish(); }, CODE_ACCEPTED_MS);
        return;
      }
      const error = res.json.error;
      if (error === 'registration_expired' || error === 'email_already_registered') {
        writePendingRegistration(null);
        state.pending = null;
        state.mode = error === 'email_already_registered' ? 'login' : 'register';
        render();
        showErr(friendlyAuthError(error, res.status, res.json));
        return;
      }
      if (error === 'code_expired') { p.expiresAt = 0; tickCode(); }
      slots.setStatus('error');
      showErr(error === 'too_many_attempts'
        ? 'Too many incorrect codes. Tap “Resend code” to get a new one.'
        : friendlyAuthError(error, res.status, res.json));
    }

    async function resendCode() {
      const p = state.pending;
      if (!p || state.busy) return;
      showErr('');
      const btn = $('#sxaResend');
      btn.disabled = true;
      btn.textContent = 'Sending…';
      const res = await apiFetch('/api/web/auth/register/resend', {
        method: 'POST', body: JSON.stringify({ email: p.email, registration_token: p.token }),
      });
      if (!root.isConnected || state.pending !== p) return;
      const now = Date.now();
      if (res.ok) {
        p.expiresAt = now + (Number(res.json.expires_in) || 600) * 1000;
        p.resendAt = now + (Number(res.json.resend_in) || 60) * 1000;
        writePendingRegistration(p);
        codeSlots.clear();
        showErr('We sent a new code. Codes from earlier emails no longer work.', 'info');
      } else if (res.json.error === 'registration_expired') {
        writePendingRegistration(null);
        state.pending = null;
        state.mode = 'register';
        render();
        showErr(friendlyAuthError('registration_expired', res.status));
        return;
      } else {
        if (res.json.retry_after) p.resendAt = now + Number(res.json.retry_after) * 1000;
        writePendingRegistration(p);
        showErr(friendlyAuthError(res.json.error, res.status, res.json));
      }
      tickCode();
    }

    function renderForgot() {
      $('#sxaHead').innerHTML =
        '<h1 class="sxAuth-title" id="sxaTitle">Reset your password</h1><p class="sxAuth-sub">Enter your account email and we’ll send you a reset link.</p>';
      $('#sxaBody').innerHTML =
        `<form class="sxAuth-form" id="sxaForm" novalidate>
          <input class="sxAuth-input" type="email" id="sxaEmail" placeholder="Email" aria-label="Email" autocomplete="email" inputmode="email" autocapitalize="off" spellcheck="false" value="${esc(state.email)}" data-autofocus>
          <p class="sxAuth-error" id="sxaErr" role="alert" aria-live="polite"></p>
          <button type="submit" class="sxAuth-btn sxAuth-primary" id="sxaSubmit"><span>Send reset link</span></button>
        </form>
        <button type="button" class="sxAuth-link" id="sxaBack">Back to log in</button>`;
      $('#sxaBack').onclick = () => { state.mode = 'login'; render(); };
      $('#sxaForm').onsubmit = async (e) => {
        e.preventDefault();
        const email = $('#sxaEmail').value.trim();
        if (!EMAIL_RE.test(email)) { showErr('Enter a valid email address.'); return; }
        state.email = email;
        const btn = $('#sxaSubmit');
        setBusy(btn, true, 'Sending…');
        await apiFetch('/api/web/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
        if (!root.isConnected) return;
        setBusy(btn, false, 'Send reset link');
        $('#sxaHead').innerHTML = `<h1 class="sxAuth-title" id="sxaTitle">Check your email</h1><p class="sxAuth-sub">If ${esc(email)} has a SYLVEX account, a password reset link is on its way.</p>`;
        $('#sxaBody').innerHTML = '<button type="button" class="sxAuth-btn sxAuth-primary" id="sxaBack"><span>Back to log in</span></button>';
        $('#sxaBack').onclick = () => { state.mode = 'login'; render(); };
      };
    }

    render();
  }
  S.closeBrowserAuthScreen = () => { if (browserAuthClose) browserAuthClose(false); };

  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  // The website's messages for the same server errors.
  function friendlyAuthError(code, status, details) {
    const info = details || {};
    const minutes = Math.max(1, Math.ceil((Number(info.retry_after) || 60) / 60));
    const seconds = Math.max(1, Math.round(Number(info.retry_after) || 60));
    const left = Number(info.attempts_left) || 0;
    const text = ({
      invalid_code: left ? `That code isn’t right. ${left} ${left === 1 ? 'attempt' : 'attempts'} left.` : 'That code isn’t right.',
      code_expired: 'This code has expired. Tap “Resend code” to get a new one.',
      too_many_attempts: 'Too many attempts. Please wait a few minutes and try again.',
      code_recently_sent: `A code was just sent. You can request another in ${seconds} s.`,
      too_many_codes: `Too many codes requested. Please try again in ${minutes} min.`,
      registration_expired: 'This sign-up has expired. Please start again.',
      password_too_long: 'Password is too long.',
      invalid_credentials: 'Incorrect email or password.',
      email_already_registered: 'An account with this email already exists. Log in or reset your password instead.',
      invalid_email: 'Enter a valid email address.',
      password_too_short: 'Password must be at least 8 characters.',
      invalid_google_token: 'Sign-in failed. Please try again.',
      invalid_apple_token: 'Sign-in failed. Please try again.',
      google_oauth_not_configured: 'This sign-in method isn’t available yet.',
      apple_oauth_not_configured: 'This sign-in method isn’t available yet.',
      email_unsupported_for_id_format: 'This email address isn’t supported yet - please try a different one.',
      origin_not_allowed: 'Sign-in isn’t available on this address. Please open SYLVEX from sylvex.ai.',
    })[code];
    if (text) return text;
    if (status === 503) return 'Accounts aren’t available on this server right now. Please try again later.';
    return 'Something went wrong. Please try again.';
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
  // Identity panel. Website and standalone Browser Mini App accounts remain
  // independent from Telegram. Self-service account linking and merging are
  // intentionally absent; exceptional transfers are handled by Support.
  // ---------------------------------------------------------------------
  async function refreshLinkedStatusBadge() {
    const badge = document.getElementById('profileLinkedStatus');
    if (!badge) return;
    if (S.hasTelegramContext && S.hasTelegramContext()) {
      badge.textContent = 'Telegram account';
      return;
    }
    try {
      const res = await apiFetch('/api/web/session/me');
      badge.textContent = res.json && res.json.authenticated ? 'SYLVEX account' : 'Sign in';
    } catch {
      badge.textContent = '-';
    }
  }
  S.refreshLinkedAccountsBadge = refreshLinkedStatusBadge;

  function openLinkedAccounts() {
    if (S.hasTelegramContext && S.hasTelegramContext()) {
      const overlay = openOverlay('');
      setBody(overlay,
        '<div class="sylvexAuth-title">Account</div>' +
        '<div class="sylvexAuth-row"><span>Sign-in method</span><span class="v">Telegram</span></div>' +
        '<div class="sylvexAuth-perm">This Telegram account is independent from Website and Browser Mini App accounts.</div>'
      );
      return;
    }
    apiFetch('/api/web/session/me').then((res) => {
      if (!res.json || !res.json.authenticated) {
        openWebAuthGate();
        return;
      }
      const session = res.json;
      const overlay = openOverlay('');
      setBody(overlay,
        '<div class="sylvexAuth-title">Sign-in methods</div>' +
        '<div class="sylvexAuth-row"><span>Email</span><span class="v">' +
          (session.email ? S.escapeHtml(session.email_verified ? session.email : session.email + ' (unverified)') : 'Not set') +
        '</span></div>' +
        '<div class="sylvexAuth-row"><span>Google</span><span class="v">' +
          (session.oauth && session.oauth.google ? 'Connected' : 'Not connected') +
        '</span></div>' +
        '<div class="sylvexAuth-row"><span>Apple</span><span class="v">' +
          (session.oauth && session.oauth.apple ? 'Connected' : 'Not connected') +
        '</span></div>' +
        '<div class="sylvexAuth-perm">Your SYLVEX web account is independent from Telegram.</div>'
      );
    });
  }
  S.openLinkedAccounts = openLinkedAccounts;
})();
