// Real Telegram user data + backend balance/status sync.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});

  function initials(first, last, username) {
    const a = (first || '').trim();
    const b = (last || '').trim();
    if (a || b) return ((a[0] || '') + (b[0] || a[1] || '')).toUpperCase() || '·';
    const u = (username || '').trim();
    if (u) return u.slice(0, 2).toUpperCase();
    return '··';
  }

  function fmtNum(n) {
    const v = Number(n || 0);
    return v.toLocaleString();
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function setAvatar(id, photoUrl, ini) {
    const el = document.getElementById(id);
    if (!el) return;
    // Preserve the trailing online .dot span
    const dot = el.querySelector('.dot');
    el.innerHTML = '';
    if (photoUrl) {
      const img = document.createElement('img');
      img.src = photoUrl;
      img.alt = '';
      img.referrerPolicy = 'no-referrer';
      img.style.cssText = 'width:100%;height:100%;border-radius:inherit;object-fit:cover;display:block';
      img.onerror = () => { el.textContent = ini; if (dot) el.appendChild(dot); };
      el.appendChild(img);
    } else {
      el.textContent = ini;
    }
    if (dot) el.appendChild(dot);
  }

  function statusLabel(status) {
    const s = (status || 'free').toLowerCase();
    if (s === 'pro' || s === 'active') return 'PRO';
    if (s === 'premium') return 'PREMIUM';
    if (s === 'vip') return 'VIP';
    return 'FREE';
  }

  function normalizeState(state) {
    if (!state) return {};
    const subscription = state.subscription || state.subscription_plan || null;
    const until = state.subscription_until || state.subscription_expires_at || null;
    const status = state.status || (subscription ? 'pro' : 'free');
    return {
      balance: Number(state.balance || 0),
      status,
      subscription_status: state.subscription_status || (subscription || status === 'pro' || status === 'active' ? 'active' : 'free'),
      subscription_plan: subscription,
      subscription_expires_at: until,
    };
  }

  function mergeUserPatch(patch) {
    const prev = S.user || {};
    const next = Object.assign({}, prev);
    Object.keys(patch || {}).forEach((key) => {
      const val = patch[key];
      if ((key === 'photo_url' || key === 'username' || key === 'first_name' || key === 'last_name' || key === 'display_name')
          && (val === null || val === undefined || val === '')) {
        return;
      }
      next[key] = val;
    });
    S.user = next;
    return next;
  }

  function renderIdentity(u) {
    if (!u) return;
    const merged = mergeUserPatch(u);
    const fullName = (u.display_name && u.display_name.trim())
      || (merged.display_name && merged.display_name.trim())
      || [merged.first_name, merged.last_name].filter(Boolean).join(' ')
      || merged.username || 'Guest';
    const handle = merged.username ? '@' + merged.username : '@user';
    const idStr = merged.telegram_id ? String(merged.telegram_id) : '—';
    const ini = initials(merged.first_name, merged.last_name, merged.username);
    const avatarUrl = merged.custom_avatar_url || merged.photo_url;

    setText('homeUserName', fullName);
    setText('homeUserHandle', handle);
    setText('homeUserId', idStr);
    setAvatar('homeAvatar', avatarUrl, ini);

    setText('profileUserName', fullName);
    setText('profileUserHandle', handle);
    setText('profileUserId', idStr);
    setAvatar('profileAvatar', avatarUrl, ini);
  }

  function renderUserState(state) {
    const normalized = normalizeState(state);
    const u = mergeUserPatch(normalized);
    const badge = u.subscription_status === 'active' ? 'PRO' : statusLabel(u.status);
    const balNum = Number(u.balance || 0);
    const bal = fmtNum(balNum) + ' ⚡️';
    const usd = '≈ $' + (balNum / 100).toFixed(2);

    setText('homeBalance', bal);
    setText('homeBalanceUsd', usd);
    const hb = document.getElementById('homeUserBadge'); if (hb) { hb.textContent = badge; hb.removeAttribute('data-i18n'); }

    setText('profileBalance', bal);
    setText('profileBalanceUsd', usd);
    setText('profilePlan', u.subscription_status === 'active'
      ? (u.subscription_plan === 'year' ? 'Pro · 1 год' : 'Pro · 1 месяц')
      : 'Free');
    setText('profileReferrals', Number(u.referrals_count || 0).toLocaleString());
    setText('profileGens', Number(u.generations_count || 0).toLocaleString());
    setText('profileSpent', Number(u.tokens_spent || 0).toLocaleString() + ' ⚡️');
    if (u.created_at) {
      try {
        const d = new Date(u.created_at);
        setText('profileSince', d.toLocaleString(undefined, { month: 'short', year: 'numeric' }));
        const days = Math.max(0, Math.floor((Date.now() - d.getTime()) / 86400000));
        setText('profileUptime', days + ' дн.');
      } catch {}
    }
    const pb = document.getElementById('profileUserBadge'); if (pb) { pb.textContent = badge; pb.removeAttribute('data-i18n'); }

    setText('shopBalance', balNum.toLocaleString());
    setText('shopBalanceUsd', usd);

    if (S.renderSubscription) S.renderSubscription();
  }

  function renderUser(u) {
    if (!u) return;
    renderIdentity(u);
    renderUserState(u);
  }

  function telegramUserFromInit() {
    const tg = S.tg;
    const initDataUnsafe = tg && tg.initDataUnsafe ? tg.initDataUnsafe : null;
    const u = initDataUnsafe && initDataUnsafe.user;
    if (!u) return null;
    return {
      telegram_id: u.id,
      first_name: u.first_name,
      last_name: u.last_name,
      username: u.username,
      language_code: u.language_code,
      photo_url: u.photo_url,
      is_premium: !!u.is_premium,
      status: u.is_premium ? 'premium' : 'free',
    };
  }

  async function fetchUserState(telegramId) {
    if (!telegramId) return;
    try {
      const res = await fetch('/api/public/telegram/user-state?telegram_id=' + encodeURIComponent(telegramId), {
        cache: 'no-store',
      });
      if (!res.ok) throw new Error('user-state ' + res.status);
      const state = await res.json();
      renderUserState(state);
    } catch (err) {
      console.warn('[SYLVEX] user state failed', err);
    }
  }

  function syncTelegramUserInBackground(initData, initDataUnsafe, telegramId) {
    fetch('/api/public/telegram/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData, initDataUnsafe }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('sync ' + res.status);
        return res.json();
      })
      .then((json) => {
        if (json && json.user) renderUserState(json.user);
        if (telegramId) fetchUserState(telegramId);
      })
      .catch((err) => {
        console.warn('[SYLVEX] user sync failed', err);
      });
  }

  async function syncUser() {
    const tg = S.tg;
    const initData = tg && tg.initData ? tg.initData : '';
    const initDataUnsafe = tg && tg.initDataUnsafe ? tg.initDataUnsafe : null;
    const tgUser = telegramUserFromInit();

    // Optimistic render from client-side Telegram payload first.
    if (tgUser) {
      renderIdentity(tgUser);
      renderUserState({
        balance: (S.user && S.user.balance) || 0,
        status: tgUser.status,
        subscription_status: (S.user && S.user.subscription_status) || 'free',
        subscription_plan: S.user && S.user.subscription_plan,
        subscription_expires_at: S.user && S.user.subscription_expires_at,
      });
      // Apply Telegram language code if we support it.
      if (tgUser.language_code && S.setLang) {
        const code = tgUser.language_code.slice(0, 2).toLowerCase();
        if (['en', 'ru', 'ar', 'tr'].includes(code) && !localStorage.getItem('sylvex-lang')) {
          S.setLang(code);
        }
      }
    }

    const telegramId = (tgUser && tgUser.telegram_id) || (S.user && S.user.telegram_id);
    fetchUserState(telegramId);
    syncTelegramUserInBackground(initData, initDataUnsafe, telegramId);
  }

  S.syncUser = syncUser;
  S.renderUser = renderUser;
  S.renderUserState = renderUserState;
})();
