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
    if (s === 'premium') return 'PREMIUM';
    if (s === 'vip') return 'VIP';
    return 'FREE';
  }

  function renderUser(u) {
    if (!u) return;
    S.user = u;
    const fullName = [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || 'Guest';
    const handle = u.username ? '@' + u.username : '@user';
    const idStr = u.telegram_id ? String(u.telegram_id) : '—';
    const ini = initials(u.first_name, u.last_name, u.username);
    const badge = statusLabel(u.status);
    const bal = fmtNum(u.balance) + ' ⚡️';

    setText('homeUserName', fullName);
    setText('homeUserHandle', handle);
    setText('homeUserId', idStr);
    setText('homeBalance', bal);
    const hb = document.getElementById('homeUserBadge'); if (hb) { hb.textContent = badge; hb.removeAttribute('data-i18n'); }
    setAvatar('homeAvatar', u.photo_url, ini);

    setText('profileUserName', fullName);
    setText('profileUserHandle', handle);
    setText('profileUserId', idStr);
    setText('profileBalance', bal);
    setText('profilePlan', badge.charAt(0) + badge.slice(1).toLowerCase());
    if (u.created_at) {
      try {
        const d = new Date(u.created_at);
        setText('profileSince', d.toLocaleString(undefined, { month: 'short', year: 'numeric' }));
      } catch {}
    }
    const pb = document.getElementById('profileUserBadge'); if (pb) { pb.textContent = badge; pb.removeAttribute('data-i18n'); }
    setAvatar('profileAvatar', u.photo_url, ini);

    setText('shopBalance', bal);
  }

  async function syncUser() {
    const tg = S.tg;
    const initData = tg && tg.initData ? tg.initData : '';
    const initDataUnsafe = tg && tg.initDataUnsafe ? tg.initDataUnsafe : null;

    // Optimistic render from client-side Telegram payload first.
    if (initDataUnsafe && initDataUnsafe.user) {
      const u = initDataUnsafe.user;
      renderUser({
        telegram_id: u.id,
        first_name: u.first_name,
        last_name: u.last_name,
        username: u.username,
        language_code: u.language_code,
        photo_url: u.photo_url,
        is_premium: !!u.is_premium,
        status: u.is_premium ? 'premium' : 'free',
        balance: 0,
      });
      // Apply Telegram language code if we support it.
      if (u.language_code && S.setLang) {
        const code = u.language_code.slice(0, 2).toLowerCase();
        if (['en', 'ru', 'ar', 'tr'].includes(code) && !localStorage.getItem('sylvex-lang')) {
          S.setLang(code);
        }
      }
    }

    // Always confirm with backend so balance/status are real.
    try {
      const res = await fetch('/api/public/telegram/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ initData, initDataUnsafe }),
      });
      if (!res.ok) throw new Error('sync ' + res.status);
      const json = await res.json();
      if (json && json.user) renderUser(json.user);
    } catch (err) {
      console.warn('[SYLVEX] user sync failed', err);
    }
  }

  S.syncUser = syncUser;
  S.renderUser = renderUser;
})();