// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/user.js
// Файл содержит frontend-логику Mini App.
// Комментарии описывают экраны, кнопки, запросы и обработчики без изменения поведения.
// =====================================================
// Real Telegram user data + backend balance/status sync.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});
  let syncPromise = null;
  let lastSyncAt = 0;
  const USER_SYNC_COOLDOWN_MS = 10000;
  function identityCacheKey(telegramId) { return 'sylvex-profile-identity-' + String(telegramId || 'guest'); }
  function readCachedIdentity(telegramId) {
    try { return JSON.parse(localStorage.getItem(identityCacheKey(telegramId)) || 'null'); } catch { return null; }
  }
  function cacheProfileIdentity(user) {
    if (!user || !user.telegram_id) return;
    const previous = readCachedIdentity(user.telegram_id) || {};
    const value = {
      telegram_id: user.telegram_id,
      username: typeof user.username === 'string' ? user.username : previous.username,
      first_name: typeof user.first_name === 'string' ? user.first_name : previous.first_name,
      last_name: typeof user.last_name === 'string' ? user.last_name : previous.last_name,
      photo_url: typeof user.photo_url === 'string' ? user.photo_url : previous.photo_url,
      display_name: typeof user.display_name === 'string' ? user.display_name : previous.display_name,
      custom_avatar_url: typeof user.custom_avatar_url === 'string' ? user.custom_avatar_url : previous.custom_avatar_url,
      balance: user.balance !== undefined ? Number(user.balance || 0) : Number(previous.balance || 0),
      status: user.status || previous.status || null,
      subscription_status: user.subscription_status || previous.subscription_status || null,
      subscription_plan: user.subscription_plan || user.subscription || previous.subscription_plan || null,
      subscription_expires_at: user.subscription_expires_at || previous.subscription_expires_at || null,
      referrals_count: user.referrals_count !== undefined ? Number(user.referrals_count || 0) : Number(previous.referrals_count || 0),
      generations_count: user.generations_count !== undefined ? Number(user.generations_count || 0) : Number(previous.generations_count || 0),
      tokens_spent: user.tokens_spent !== undefined ? Number(user.tokens_spent || 0) : Number(previous.tokens_spent || 0),
      created_at: user.created_at || previous.created_at || null,
    };
    try { localStorage.setItem(identityCacheKey(user.telegram_id), JSON.stringify(value)); } catch {}
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: initials
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function initials(first, last, username) {
    const a = (first || '').trim();
    const b = (last || '').trim();
    if (a || b) return ((a[0] || '') + (b[0] || a[1] || '')).toUpperCase() || '·';
    const u = (username || '').trim();
    if (u) return u.slice(0, 2).toUpperCase();
    return '··';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: fmtNum
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function fmtNum(n) {
    const v = Number(n || 0);
    return v.toLocaleString();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: setText
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: setAvatar
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
      img.loading = 'eager';
      img.decoding = 'sync';
      img.fetchPriority = 'high';
      img.referrerPolicy = 'no-referrer';
      img.style.cssText = 'width:100%;height:100%;border-radius:inherit;object-fit:cover;display:block';
      img.onerror = () => { el.textContent = ini; if (dot) el.appendChild(dot); };
      el.appendChild(img);
    } else {
      el.textContent = ini;
    }
    if (dot) el.appendChild(dot);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: statusLabel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function statusLabel(status) {
    const s = (status || 'free').toLowerCase();
    if (s === 'pro' || s === 'active') return 'PRO';
    if (s === 'premium') return 'PREMIUM';
    if (s === 'vip') return 'VIP';
    return 'FREE';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: normalizeState
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
      last_subscription_expires_at: state.last_subscription_expires_at || until,
      subscription_expired: !!state.subscription_expired,
      telegram_id: state.telegram_id,
      username: state.username,
      first_name: state.first_name,
      last_name: state.last_name,
      photo_url: state.photo_url,
      display_name: state.display_name,
      custom_avatar_url: state.custom_avatar_url,
      theme_preference: state.theme_preference || {},
      created_at: state.created_at,
      generations_count: state.generations_count || state.total_generations || 0,
      tokens_spent: state.tokens_spent || 0,
      referrals_count: state.referrals_count || 0,
    };
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: mergeUserPatch
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function mergeUserPatch(patch) {
    const prev = S.user || {};
    const next = Object.assign({}, prev);
    Object.keys(patch || {}).forEach((key) => {
      const val = patch[key];
      if ((key === 'photo_url' || key === 'username' || key === 'first_name' || key === 'last_name' || key === 'display_name' || key === 'custom_avatar_url')
          && (val === null || val === undefined || val === '')) {
        return;
      }
      next[key] = val;
    });
    S.user = next;
    return next;
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderIdentity
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
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
    if (S.applyStoredTheme) S.applyStoredTheme();
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderUserState
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
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
    if (normalized.subscription_expired && S.showExpiredSubscriptionModal) {
      S.showExpiredSubscriptionModal(normalized);
    }
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderUser
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderUser(u) {
    if (!u) return;
    renderIdentity(u);
    renderUserState(u);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: telegramUserFromInit
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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

  // =====================================================
  // JAVASCRIPT-БЛОК: fetchUserState
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function fetchUserState(telegramId) {
    if (!telegramId) return;
    try {
      const res = await fetch('/api/public/telegram/user-state?telegram_id=' + encodeURIComponent(telegramId), {
        cache: 'no-store',
      });
      if (!res.ok) throw new Error('user-state ' + res.status);
      const state = await res.json();
      const tgUser = telegramUserFromInit();
      const resolved = Object.assign({}, state, {
        photo_url: state.custom_avatar_url ? state.photo_url : (state.photo_url || (tgUser && tgUser.photo_url)),
      });
      cacheProfileIdentity(resolved);
      renderUser(resolved);
    } catch (err) {
      console.warn('[SYLVEX] user state failed', err);
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: syncTelegramUserInBackground
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function syncTelegramUserInBackground(initData, initDataUnsafe) {
    const res = await fetch('/api/public/telegram/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData, initDataUnsafe }),
    });
    if (!res.ok) throw new Error('sync ' + res.status);
    return res.json();
  }
  async function loadProfileFast(tgUser) {
    if (!tgUser || !tgUser.telegram_id) return null;
    try {
      const res = await fetch('/api/public/telegram/profile?telegram_id=' + encodeURIComponent(tgUser.telegram_id), { cache: 'no-store' });
      if (!res.ok) return null;
      const json = await res.json();
      const profile = json && json.profile ? json.profile : null;
      if (!profile) return null;
      const user = Object.assign({}, tgUser, profile);
      cacheProfileIdentity(user);
      renderIdentity(user);
      return user;
    } catch { return null; }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: syncUser
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function syncUser(options) {
    const force = !!(options && options.force);
    const now = Date.now();
    if (syncPromise) return syncPromise;
    if (!force && now - lastSyncAt < USER_SYNC_COOLDOWN_MS) return S.user || {};

    syncPromise = (async () => {
    const tg = S.tg;
    const initData = tg && tg.initData ? tg.initData : '';
    const initDataUnsafe = tg && tg.initDataUnsafe ? tg.initDataUnsafe : null;
    const tgUser = telegramUserFromInit();

    // Optimistic render from client-side Telegram payload first.
    if (tgUser) {
      const cachedIdentity = readCachedIdentity(tgUser.telegram_id);
      if (cachedIdentity) {
        renderUser(Object.assign({}, tgUser, cachedIdentity));
      } else {
        // Do not flash the Telegram photo before the saved Mini App profile arrives.
        const placeholderIdentity = Object.assign({}, tgUser);
        delete placeholderIdentity.photo_url;
        renderIdentity(placeholderIdentity);
      }
      loadProfileFast(tgUser);
      // Apply Telegram language code if we support it.
      if (tgUser.language_code && S.setLang) {
        const code = tgUser.language_code.slice(0, 2).toLowerCase();
        if (['en', 'ru', 'ar', 'tr'].includes(code) && !localStorage.getItem('sylvex-lang')) {
          S.setLang(code);
        }
      }
    }

    const telegramId = (tgUser && tgUser.telegram_id) || (S.user && S.user.telegram_id);
    try {
      const json = await syncTelegramUserInBackground(initData, initDataUnsafe);
      if (json && json.user) {
        const authoritativeUser = Object.assign({}, json.user, {
          photo_url: json.user.custom_avatar_url ? json.user.photo_url : (json.user.photo_url || (tgUser && tgUser.photo_url)),
        });
        cacheProfileIdentity(authoritativeUser);
        renderUser(authoritativeUser);
        return authoritativeUser;
      }
    } catch (err) {
      console.warn('[SYLVEX] user sync failed', err);
      if (telegramId) {
        await fetchUserState(telegramId);
        return S.user || {};
      }
    }
    return S.user || {};
    })();

    try {
      return await syncPromise;
    } finally {
      lastSyncAt = Date.now();
      syncPromise = null;
    }
  }

  S.syncUser = syncUser;
  S.renderUser = renderUser;
  S.renderUserState = renderUserState;
  S.cacheProfileIdentity = cacheProfileIdentity;
})();
