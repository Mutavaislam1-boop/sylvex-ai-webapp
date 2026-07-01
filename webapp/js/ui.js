// Generic UI helpers: toast, view switching, theme, switches, popovers.
(function () {
  let toastT;
  function toast(msg) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastT);
    toastT = setTimeout(() => el.classList.remove('show'), 1800);
    if (window.SYLVEX && window.SYLVEX.haptic) window.SYLVEX.haptic.impact('light');
  }

  function setTheme(mode) {
    document.documentElement.dataset.theme = mode;
    localStorage.setItem('sylvex-theme', mode);
    const ts = document.getElementById('themeSwitch');
    if (ts) ts.classList.toggle('on', mode === 'dark');
    const tg = window.SYLVEX && window.SYLVEX.tg;
    if (tg) { try { tg.setHeaderColor && tg.setHeaderColor(mode === 'dark' ? '#030308' : '#eef0f7'); } catch (e) {} }
  }

  function toggleTheme() {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }

  function toggleSwitch(el) { el.classList.toggle('on'); }

  function switchView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    const sc = document.querySelector('.scroll');
    if (sc) {
      sc.classList.toggle('studio-mode', name === 'tools');
      if (name !== 'tools') sc.scrollTo({ top: 0, behavior: 'smooth' });
    }
    if (name === 'tools' && window.SYLVEX) {
      window.SYLVEX.renderChat && window.SYLVEX.renderChat();
      const ci = document.getElementById('chatInput');
      if (ci && window.SYLVEX.autoGrow) window.SYLVEX.autoGrow(ci);
    }
    if (window.SYLVEX && window.SYLVEX.haptic) window.SYLVEX.haptic.select();
    if (window.SYLVEX && window.SYLVEX.updatePrice) window.SYLVEX.updatePrice();
  }

  // Card / list HTML renderers (presentation only).
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function getCurrentUser() {
    const S = window.SYLVEX || {};
    return S.currentUser || S.user || window.currentUser || null;
  }

  function getSubscriptionPlan(user) {
    return user && (user.subscription_plan || user.plan || user.subscriptionType || user.subscription_type || null);
  }

  function getSubscriptionExpiresAt(user) {
    return user && (user.subscription_expires_at || user.expires_at || user.subscriptionExpiresAt || null);
  }

  function isActiveSubscriptionCard(s) {
    const user = getCurrentUser();
    if (!user || user.status !== 'active') return false;
    const itemKind = s.kind || (s.id && String(s.id).startsWith('sub_') ? 'subscription' : 'credits');
    if (itemKind !== 'subscription') return false;

    const activePlan = getSubscriptionPlan(user);
    const cardPlan = s.plan_key || s.plan || (s.id === 'sub_month' ? 'month' : s.id === 'sub_year' ? 'year' : null);

    return Boolean(activePlan && cardPlan && activePlan === cardPlan);
  }

  function formatSubscriptionCountdown(expiresAt) {
    if (!expiresAt) return '';

    const end = new Date(expiresAt).getTime();
    if (!Number.isFinite(end)) return '';

    const diff = end - Date.now();
    if (diff <= 0) return 'истекла';

    const totalSeconds = Math.floor(diff / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);

    if (days > 0) return days + ' дн. ' + hours + ' ч.';
    if (hours > 0) return hours + ' ч. ' + minutes + ' мин.';
    return minutes + ' мин.';
  }

  function toolCard(tt) {
    return '<div class="tool" onclick="toast(t(\u0027tool_' + tt.k + '\u0027))">'
      + '<div class="ico">' + tt.icon + '</div>'
      + '<h4>' + t('tool_' + tt.k) + '</h4>'
      + '<p>' + t('tool_' + tt.k + '_d') + '</p></div>';
  }

  function histCard(h) {
    return '<div class="hist-item"><div class="thumb">' + h.icon + '</div>'
      + '<div class="hist-body"><div class="hist-title">' + t(h.tk) + '</div>'
      + '<div class="hist-sub">' + t(h.sk) + '</div></div>'
      + '<button class="chip open" onclick="event.stopPropagation();toast(t(\u0027open\u0027)+\u0027 \u2192\u0027)">' + t('open') + '</button></div>';
  }

  function shopCard(s) {
    const packId = s.id || ('pack_' + s.tokens);
    const itemKind = s.kind || (String(packId).startsWith('sub_') ? 'subscription' : 'credits');
    const user = getCurrentUser();
    const isSub = itemKind === 'subscription';
    const isActive = isActiveSubscriptionCard(s);
    const expiresAt = getSubscriptionExpiresAt(user);
    const countdown = isActive ? formatSubscriptionCountdown(expiresAt) : '';
    const title = s.title || (isSub ? (s.plan_key === 'year' || packId === 'sub_year' ? 'PRO · 1 год' : 'PRO · 1 месяц') : ((s.tokens || 0).toLocaleString() + ' ⚡️'));
    const subtitle = isSub ? 'Подписка' : t('tokens');
    const priceText = s.price || '';
    const activeClass = isActive ? ' active-subscription' : '';

    return '<div class="pack ' + (s.pop && !isActive ? 'pop ' : '') + activeClass + '" data-pack-id="' + escapeHtml(packId) + '">'
      + (s.pop && !isActive ? '<div class="pop-tag">' + t('popular') + '</div>' : '')
      + '<div class="pico">' + (s.icon || '⚡️') + '</div>'
      + '<div class="pa">' + escapeHtml(title) + '</div>'
      + '<div class="pn">' + escapeHtml(subtitle) + '</div>'
      + (isActive
        ? '<div class="pp subscription-countdown" data-subscription-countdown="' + escapeHtml(expiresAt || '') + '">' + escapeHtml(countdown || 'активна') + '</div>'
        : '<div class="pp">' + escapeHtml(priceText) + '</div>')
      + (isActive
        ? '<button class="subscribed-btn" disabled>✓</button>'
        : '<button onclick="SYLVEX.openBuy(\'' + packId + '\')">' + t('buy') + '</button>')
      + '</div>';
  }

  // Expose globally.
  window.toast = toast;
  window.setTheme = setTheme;
  window.toggleTheme = toggleTheme;
  window.toggleSwitch = toggleSwitch;
  window.switchView = switchView;

  window.SYLVEX = window.SYLVEX || {};
  Object.assign(window.SYLVEX, {
    toast, setTheme, toggleTheme, switchView, escapeHtml,
    toolCard, histCard, shopCard,
    formatSubscriptionCountdown
  });
})();