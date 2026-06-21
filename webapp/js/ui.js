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
      + '<span class="chip ' + h.status + '">' + t(h.label) + '</span></div>';
  }

  function shopCard(s) {
    return '<div class="pack ' + (s.pop ? 'pop' : '') + '">'
      + (s.pop ? '<div class="pop-tag">' + t('popular') + '</div>' : '')
      + '<div class="pico">' + s.icon + '</div>'
      + '<div class="pa">' + s.tokens.toLocaleString() + ' ✦</div>'
      + '<div class="pn">' + t('tokens') + '</div>'
      + '<div class="pp">' + s.price + '</div>'
      + '<button onclick="toast(\'' + t('buy') + ' ' + s.tokens + ' ✦\')">' + t('buy') + '</button></div>';
  }

  // Expose globally.
  window.toast = toast;
  window.setTheme = setTheme;
  window.toggleTheme = toggleTheme;
  window.toggleSwitch = toggleSwitch;
  window.switchView = switchView;

  window.SYLVEX = window.SYLVEX || {};
  Object.assign(window.SYLVEX, { toast, setTheme, toggleTheme, switchView, escapeHtml, toolCard, histCard, shopCard });
})();
