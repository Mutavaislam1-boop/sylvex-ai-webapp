// Cabinet controller: wires DOM events, renders dynamic content, manages
// Pro Studio chat workspace, support modal, hero carousel, pricing logic.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});

  // Pro Studio state.
  let studioMode = 'image';
  let activeCat = null;
  let chatMessages = [
    { role: 'ai', text: "Hi! I'm SYLVEX. Pick a mode above and tell me what to create." }
  ];

  /* ===== Rendering ===== */
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = S.STUDIO_MODES.map(m => (
      '<div class="mode-ico' + (studioMode === m.k ? ' act' : '') + '" data-mode="' + m.k + '" onclick="SYLVEX.selMode(\'' + m.k + '\')">'
      + '<div class="mi">' + m.icon + '</div><div class="ml">' + t('cat_' + m.k) + '</div></div>'
    )).join('');
  }

  function renderModelPop() {
    const el = document.getElementById('modelPop'); if (!el) return;
    el.innerHTML = S.CTRL.model.map((m, i) => (
      '<button class="' + (i === S.CTRL_IDX.model ? 'sel' : '') + '" data-i="' + i + '" onclick="SYLVEX.pickModel(event,' + i + ')">' + m + '</button>'
    )).join('');
  }

  function renderChat() {
    const el = document.getElementById('chatArea'); if (!el) return;
    el.innerHTML = chatMessages.map((m, i) => {
      if (m.typing) {
        return '<div class="msg ai" data-i="' + i + '"><div class="ai-avatar">S</div>'
          + '<div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div></div>';
      }
      const actions = '<div class="msg-actions">'
        + '<button onclick="SYLVEX.copyMsg(' + i + ')" title="Copy">📋</button>'
        + (m.role === 'ai' ? '<button onclick="SYLVEX.regenMsg(' + i + ')" title="Regenerate">↻</button>' : '')
        + '<button onclick="SYLVEX.deleteMsg(' + i + ')" title="Delete">🗑</button></div>';
      return '<div class="msg ' + m.role + '" data-i="' + i + '">'
        + (m.role === 'ai' ? '<div class="ai-avatar">S</div>' : '')
        + '<div class="bubble">' + S.escapeHtml(m.text) + '</div>' + actions + '</div>';
    }).join('');
    el.scrollTop = el.scrollHeight;
  }

  function renderDynamic() {
    const ht = document.getElementById('homeTools');
    const hh = document.getElementById('homeHist');
    const fh = document.getElementById('fullHist');
    const sg = document.getElementById('shopGrid');
    if (ht) ht.innerHTML = S.toolsData.slice(0, 4).map(S.toolCard).join('');
    if (hh) hh.innerHTML = S.histData.slice(0, 3).map(S.histCard).join('');
    if (fh) fh.innerHTML = S.histData.map(S.histCard).join('');
    if (sg) sg.innerHTML = S.shopData.map(S.shopCard).join('');
    renderModeStrip();
    renderModelPop();
    const mv = document.getElementById('modelVal');
    if (mv) mv.textContent = S.CTRL.model[S.CTRL_IDX.model];
    updatePrice();
  }

  /* ===== Pricing ===== */
  function computePrice() {
    if (!activeCat) return 0;
    let p = S.CAT_PRICE[activeCat] || 0;
    Object.keys(S.CTRL_PRICE).forEach(k => { p += (S.CTRL_PRICE[k][S.CTRL_IDX[k]] || 0); });
    return p;
  }
  function updatePrice() {
    const bar = document.getElementById('priceBar');
    if (bar) bar.classList.remove('show');
  }
  function generateNow() {
    if (!activeCat) { toast(t('generating')); return; }
    toast(t('generating') + ' · ' + computePrice() + ' ✦');
    S.haptic.impact('medium');
  }

  /* ===== Studio interactions ===== */
  function selMode(k) {
    studioMode = k;
    activeCat = k;
    renderModeStrip();
    S.haptic.select();
  }
  function toggleModelPop(e) {
    e.stopPropagation();
    document.getElementById('modelPop').classList.toggle('show');
    const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
  }
  function pickModel(e, i) {
    e.stopPropagation();
    S.CTRL_IDX.model = i;
    document.getElementById('modelVal').textContent = S.CTRL.model[i];
    renderModelPop();
    document.getElementById('modelPop').classList.remove('show');
    S.haptic.select();
  }
  function togglePlusPop(e) {
    e.stopPropagation();
    document.getElementById('plusPop').classList.toggle('show');
    document.getElementById('modelPop').classList.remove('show');
  }
  function attach(kind) {
    document.getElementById('plusPop').classList.remove('show');
    toast(t('att_' + kind));
  }
  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }
  function aiReply(prompt) {
    const m = S.CTRL.model[S.CTRL_IDX.model];
    return '✨ ' + m + ' · ' + t('cat_' + studioMode) + '\n\n' + t('ai_stub') + ' "' + prompt + '"';
  }
  function sendChat() {
    const ta = document.getElementById('chatInput');
    const v = (ta.value || '').trim();
    if (!v) return;
    chatMessages.push({ role: 'user', text: v });
    ta.value = ''; autoGrow(ta);
    chatMessages.push({ typing: true, role: 'ai' });
    renderChat();
    S.haptic.impact('light');
    setTimeout(() => {
      chatMessages.pop();
      chatMessages.push({ role: 'ai', text: aiReply(v) });
      renderChat();
    }, 900);
  }
  function copyMsg(i) {
    const m = chatMessages[i]; if (!m) return;
    if (navigator.clipboard) navigator.clipboard.writeText(m.text || '');
    toast(t('copied'));
  }
  function regenMsg(i) {
    const prev = chatMessages[i - 1];
    if (!prev || prev.role !== 'user') return;
    chatMessages[i] = { typing: true, role: 'ai' }; renderChat();
    setTimeout(() => { chatMessages[i] = { role: 'ai', text: aiReply(prev.text) }; renderChat(); }, 800);
  }
  function deleteMsg(i) {
    chatMessages.splice(i, 1); renderChat();
    S.haptic.impact('light');
  }
  function toggleMic(btn) {
    btn.classList.toggle('rec');
    toast(btn.classList.contains('rec') ? t('rec_start') : t('rec_stop'));
  }

  /* ===== Support modal ===== */
  function openSupport() {
    const m = document.getElementById('supportModal');
    m.classList.add('show');
    setTimeout(() => { const ta = document.getElementById('supportMsg'); ta && ta.focus(); }, 250);
    S.haptic.impact('light');
  }
  function closeSupport() {
    document.getElementById('supportModal').classList.remove('show');
  }
  function sendSupport() {
    const ta = document.getElementById('supportMsg');
    const v = (ta.value || '').trim();
    if (!v) { toast(t('support_empty')); return; }
    S.sendToBot({ type: 'support', message: v });
    ta.value = '';
    closeSupport();
    toast(t('support_sent'));
    S.haptic.notify('success');
  }

  /* ===== Hero carousel ===== */
  let slideIdx = 0;
  let autoT;
  function initHero() {
    const track = document.getElementById('heroTrack');
    const dotsEl = document.getElementById('heroDots');
    if (!track || !dotsEl) return;

    function renderDots() {
      const n = track.children.length;
      let s = '';
      for (let i = 0; i < n; i++) s += '<div class="dot-i ' + (i === slideIdx ? 'act' : '') + '"></div>';
      dotsEl.innerHTML = s;
    }
    function goSlide(i) {
      const n = track.children.length;
      slideIdx = ((i % n) + n) % n;
      const slide = track.children[slideIdx];
      track.scrollTo({ left: slide.offsetLeft - track.offsetLeft, behavior: 'smooth' });
      renderDots();
    }
    autoT = setInterval(() => goSlide(slideIdx + 1), 4200);
    track.addEventListener('scroll', () => {
      const w = track.clientWidth;
      const i = Math.round(track.scrollLeft / w);
      if (i !== slideIdx) { slideIdx = i; renderDots(); }
    });
    ['touchstart', 'mousedown'].forEach(e => track.addEventListener(e, () => clearInterval(autoT)));
    ['touchend', 'mouseup', 'mouseleave'].forEach(e => track.addEventListener(e, () => {
      clearInterval(autoT);
      autoT = setInterval(() => goSlide(slideIdx + 1), 4200);
    }));
    renderDots();
  }

  /* ===== Wire up DOM ===== */
  function bindEvents() {
    // Language popover
    const langBtn = document.getElementById('langBtn');
    const langPop = document.getElementById('langPop');
    if (langBtn && langPop) {
      langBtn.addEventListener('click', e => { e.stopPropagation(); langPop.classList.toggle('show'); });
      langPop.querySelectorAll('button').forEach(b => {
        b.addEventListener('click', () => { S.setLang(b.dataset.lang); langPop.classList.remove('show'); });
      });
    }
    const langRow = document.getElementById('langRow');
    if (langRow && langPop) {
      langRow.addEventListener('click', e => { e.stopPropagation(); langPop.classList.toggle('show'); });
    }

    // Close popovers on outside click
    document.addEventListener('click', () => {
      if (langPop) langPop.classList.remove('show');
      const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
      const pp = document.getElementById('plusPop');  if (pp) pp.classList.remove('show');
    });

    // Bottom navigation
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Theme
    const themeBtn = document.getElementById('themeBtn');
    const themeSwitch = document.getElementById('themeSwitch');
    if (themeBtn) themeBtn.addEventListener('click', S.toggleTheme);
    if (themeSwitch) themeSwitch.addEventListener('click', S.toggleTheme);

    // Animated background switch
    const bgSwitch = document.getElementById('bgSwitch');
    if (bgSwitch) {
      bgSwitch.addEventListener('click', function () {
        this.classList.toggle('on');
        document.body.style.setProperty('animation-play-state', this.classList.contains('on') ? 'running' : 'paused');
      });
    }

    // Support modal background click → close
    const supportModal = document.getElementById('supportModal');
    if (supportModal) supportModal.addEventListener('click', closeSupport);

    // Enter to send chat
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
      chatInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
      });
    }
  }

  /* ===== Init (called after cabinet.html is injected) ===== */
  function init() {
    // Restore saved theme.
    const tg = S.tg;
    const savedTheme = localStorage.getItem('sylvex-theme') || (tg && tg.colorScheme === 'light' ? 'light' : 'dark');
    S.setTheme(savedTheme);

    bindEvents();
    applyLang();       // triggers renderDynamic
    initHero();
    renderChat();
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, toggleModelPop, togglePlusPop, attach, autoGrow,
    sendChat, copyMsg, regenMsg, deleteMsg, toggleMic,
    openSupport, closeSupport, sendSupport,
    computePrice, updatePrice, generateNow,
    get studioMode() { return studioMode; },
    get activeCat() { return activeCat; }
  });

  // Also expose the inline-onclick handlers as globals.
  window.toggleModelPop = toggleModelPop;
  window.togglePlusPop  = togglePlusPop;
  window.attach         = attach;
  window.autoGrow       = autoGrow;
  window.sendChat       = sendChat;
  window.toggleMic      = toggleMic;
  window.openSupport    = openSupport;
  window.closeSupport   = closeSupport;
  window.sendSupport    = sendSupport;
  window.generateNow    = generateNow;
})();
