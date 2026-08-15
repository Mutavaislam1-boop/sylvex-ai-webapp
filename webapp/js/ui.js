// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/ui.js
// Файл содержит frontend-логику Mini App.
// Комментарии описывают экраны, кнопки, запросы и обработчики без изменения поведения.
// =====================================================
// Generic UI helpers: toast, view switching, theme, switches, popovers.
(function () {
  let toastT;
  const UI_ICON_PATHS = {
    '🎨':'<path d="M4 19 15 8l3 3L7 22H4v-3Z"/><path d="m13 10 2-5 4-2 2 2-2 4-5 2"/>',
    '✍️':'<path d="M4 20h4L19 9a3 3 0 0 0-4-4L4 16v4Z"/><path d="m13 7 4 4"/>',
    '🎙️':'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/>',
    '🎬':'<rect x="3" y="6" width="18" height="14" rx="2"/><path d="m3 10 18-4M8 6l3 4M15 6l3 4"/>',
    '🎵':'<path d="M9 18V6l10-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
    '✨':'<path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z"/>',
    '🧠':'<path d="M9 4a3 3 0 0 0-4 3 3 3 0 0 0-1 5 3 3 0 0 0 2 5 3 3 0 0 0 5 2V5A3 3 0 0 0 9 4ZM15 4a3 3 0 0 1 4 3 3 3 0 0 1 1 5 3 3 0 0 1-2 5 3 3 0 0 1-5 2V5a3 3 0 0 1 2-1Z"/>',
    '🔍':'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
    '📝':'<path d="M6 3h9l4 4v14H6Z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
    '↻':'<path d="M20 7v5h-5"/><path d="M19 12a7 7 0 1 0-2 5"/>',
    '👤':'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    '⭐':'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z"/>',
    '🎁':'<path d="M4 10h16v11H4ZM3 7h18v3H3ZM12 7v14"/><path d="M12 7H8.5a2.5 2.5 0 1 1 0-5C11 2 12 7 12 7Zm0 0h3.5a2.5 2.5 0 1 0 0-5C13 2 12 7 12 7Z"/>',
    '🌐':'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    '🔔':'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/>',
    '📩':'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>',
    '📖':'<path d="M4 4h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H4ZM20 4h-6a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h6Z"/>',
    '💬':'<path d="M4 5h16v12H9l-5 4V5Z"/>',
    '🔒':'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    '📜':'<path d="M7 3h11v17H7a3 3 0 0 1 0-6h11M7 3a3 3 0 0 0 0 6h11"/>',
    'ℹ️':'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    '🚪':'<path d="M10 4H4v16h6M14 8l4 4-4 4M8 12h10"/>',
    '✓':'<path d="m5 12 4 4L19 6"/>','›':'<path d="m9 5 7 7-7 7"/>','→':'<path d="M5 12h14M13 6l6 6-6 6"/>','×':'<path d="M6 6l12 12M18 6 6 18"/>','+':'<path d="M12 5v14M5 12h14"/>',
    'P':'<path d="M7 20 10 4h6a4 4 0 0 1 0 8h-5M9 16h5"/>','₿':'<path d="M8 4h7a4 4 0 0 1 0 8H8h8a4 4 0 0 1 0 8H8ZM11 2v20M15 2v2M15 20v2"/>',
    '◫':'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 8h8v8H8Z"/>','◌':'<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/>','◎':'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>','◇':'<path d="m12 3 9 9-9 9-9-9 9-9Z"/>','▷':'<path d="m8 5 11 7-11 7V5Z"/>','✦':'<path d="m12 3 2 7 7 2-7 2-2 7-2-7-7-2 7-2 2-7Z"/>','L':'<path d="M7 4v16h11"/>','−':'<path d="M5 12h14"/>','⇄':'<path d="M4 8h14m-3-3 3 3-3 3M20 16H6m3-3-3 3 3 3"/>'
  };
  function svgUiIcon(value) {
    const paths = UI_ICON_PATHS[String(value || '').trim()];
    return paths ? '<svg class="ui-svg-icon" viewBox="0 0 24 24" aria-hidden="true">' + paths + '</svg>' : '';
  }
  function replaceLegacyUiIcons(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('.ico,.mi,.pm-ico,.pm-arr,.chev,.home-quick-icon,.thumb,.pico,.modal-close').forEach((node) => {
      if (node.closest('.view[data-view="tools"]') || node.querySelector('svg,img')) return;
      const svg = svgUiIcon(node.textContent);
      if (svg) node.innerHTML = svg;
    });
  }
  function syncTelegramHeader(forceStudio) {
    const tg = window.SYLVEX && window.SYLVEX.tg;
    if (!tg || !tg.setHeaderColor) return;
    const studioActive = typeof forceStudio === 'boolean'
      ? forceStudio
      : !!document.querySelector('.view[data-view="tools"].active');
    const mode = document.documentElement.dataset.theme || 'dark';
    try { tg.setHeaderColor(studioActive || mode === 'dark' ? '#030308' : '#eef0f7'); } catch (e) {}
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: toast
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function toast(msg) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastT);
    toastT = setTimeout(() => el.classList.remove('show'), 1800);
    if (window.SYLVEX && window.SYLVEX.haptic) window.SYLVEX.haptic.impact('light');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: setTheme
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function setTheme(mode) {
    document.documentElement.dataset.theme = mode;
    localStorage.setItem('sylvex-theme', mode);
    const ts = document.getElementById('themeSwitch');
    if (ts) ts.classList.toggle('on', mode === 'dark');
    syncTelegramHeader();
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleTheme
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleTheme() {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleSwitch
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleSwitch(el) { el.classList.toggle('on'); }

  // =====================================================
  // JAVASCRIPT-БЛОК: switchView
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function switchView(name) {
    if ((name === 'shop' || name === 'pay') && window.SYLVEX && window.SYLVEX.closeExpiredSubscriptionModal) {
      window.SYLVEX.closeExpiredSubscriptionModal();
    }
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
    if (name !== 'tools' && window.SYLVEX && window.SYLVEX.VoiceDialogueComposer) {
      window.SYLVEX.VoiceDialogueComposer.closeMenus();
    }
    syncTelegramHeader(name === 'tools');
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
    if (name === 'history' && window.SYLVEX && window.SYLVEX.loadProfileGallery) window.SYLVEX.loadProfileGallery();
    if (name === 'community' && window.SYLVEX && window.SYLVEX.loadCommunityFeed) window.SYLVEX.loadCommunityFeed();
    if (window.SYLVEX && window.SYLVEX.haptic) window.SYLVEX.haptic.select();
    if (window.SYLVEX && window.SYLVEX.updatePrice) window.SYLVEX.updatePrice();
  }

  // Card / list HTML renderers (presentation only).
  // =====================================================
  // JAVASCRIPT-БЛОК: escapeHtml
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: toolCard
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function toolCard(tt) {
    const docsSections = { image:'images', text:'text', voice:'voice', video:'video', music:'music', general:'general' };
    const docsLabels = { image:'Изображения', text:'Текст', voice:'Голос', video:'Видео AI', music:'Музыка', general:'Общее' };
    const docsDescriptions = { image:'Руководство по изображениям', text:'Руководство по тексту', voice:'Руководство по озвучке', video:'Руководство по видео', music:'Руководство по музыке', general:'О платформе SYLVEX' };
    const docsImages = { image:'images.png', video:'video.png', music:'music.png', voice:'voice.png', text:'text.png', general:'general.png' };
    const section = docsSections[tt.k] || 'general';
    return '<div class="tool" onclick="SYLVEX.openKnowledgeWorkspace(\u0027' + section + '\u0027)">'
      + '<img class="knowledge-card-image" src="assets/knowledge-center/' + docsImages[tt.k] + '" alt="" loading="lazy">'
      + '<div class="knowledge-card-copy"><h4>' + docsLabels[tt.k] + '</h4>'
      + '<p>' + docsDescriptions[tt.k] + '</p></div></div>';
  }

  function openQuickTool(mode) {
    switchView('tools');
    if (mode !== 'general' && window.SYLVEX && window.SYLVEX.updateComposerMode) {
      window.SYLVEX.updateComposerMode(mode);
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: histCard
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function histCard(h) {
    return '<div class="hist-item"><div class="thumb">' + h.icon + '</div>'
      + '<div class="hist-body"><div class="hist-title">' + t(h.tk) + '</div>'
      + '<div class="hist-sub">' + t(h.sk) + '</div></div>'
      + '<button class="chip open" onclick="event.stopPropagation();toast(t(\u0027open\u0027)+\u0027 \u2192\u0027)">' + t('open') + '</button></div>';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: shopCard
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function shopCard(s) {
    return '<div class="pack ' + (s.pop ? 'pop' : '') + '">'
      + (s.pop ? '<div class="pop-tag">' + t('popular') + '</div>' : '')
      + '<div class="pico">' + s.icon + '</div>'
      + '<div class="pa">' + s.tokens.toLocaleString() + ' ⚡️</div>'
      + '<div class="pn">' + t('tokens') + '</div>'
      + '<div class="pp">' + s.price + '</div>'
      + '<button onclick="toast(\'' + t('buy') + ' ' + s.tokens + ' ⚡️\')">' + t('buy') + '</button></div>';
  }

  // Expose globally.
  window.toast = toast;
  window.setTheme = setTheme;
  window.toggleTheme = toggleTheme;
  window.toggleSwitch = toggleSwitch;
  window.switchView = switchView;

  window.SYLVEX = window.SYLVEX || {};
  Object.assign(window.SYLVEX, { toast, setTheme, toggleTheme, switchView, syncTelegramHeader, svgUiIcon, replaceLegacyUiIcons, escapeHtml, toolCard, openQuickTool, histCard, shopCard });
})();
