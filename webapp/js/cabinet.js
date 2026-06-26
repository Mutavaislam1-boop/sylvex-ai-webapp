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
  // Pending attachment for next send.
  let pendingAttachment = null; // { kind, mime, name, dataBase64 }
  let pendingAttachAccept = '';
  // Voice recording state.
  let mediaRecorder = null;
  let mediaChunks = [];
  let mediaStream = null;
  // Current "model label" selected from popover, mapped to OpenAI model id.
  let currentModelLabel = 'SYLVEX Pro';

  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      return u && u.id ? Number(u.id) : 0;
    } catch { return 0; }
  }

  function pickOpenAIModel() {
    // Map mode to a sensible default OpenAI model id.
    if (studioMode === 'image') return 'gpt-image-1';
    if (currentModelLabel && /lite/i.test(currentModelLabel)) return 'gpt-4o-mini';
    return 'gpt-4o-mini';
  }

  /* ===== Rendering ===== */
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = '';
  }

  function renderModelPop() {
    const el = document.getElementById('modelPop'); if (!el) return;
    const cur = S.CTRL.model[S.CTRL_IDX.model] || 'SYLVEX Pro';
    const groups = [
      { items: [
        { k:'pro',   label:'SYLVEX Pro' },
        { k:'lite',  label:'SYLVEX Lite' },
      ]},
      { label:'AI Models', items: [
        { k:'video', label:'Video AI Models' },
        { k:'image', label:'Image AI Models' },
        { k:'music', label:'Music AI Models' },
        { k:'voice', label:'Voice AI Models' },
        { k:'text',  label:'Text AI Models' },
      ]},
    ];
    let html = '';
    groups.forEach((g, gi) => {
      if (gi > 0) html += '<div class="mp-div"></div>';
      if (g.label) html += '<div class="mp-label">' + g.label + '</div>';
      g.items.forEach(it => {
        html += '<button class="' + (cur === it.label ? 'sel' : '') + '" onclick="SYLVEX.pickModelKey(event,\'' + it.k + '\',\'' + it.label + '\')">' + it.label + '</button>';
      });
    });
    el.innerHTML = html;
  }

  function renderChat() {
    const el = document.getElementById('chatArea'); if (!el) return;
    el.innerHTML = chatMessages.map((m, i) => {
      if (m.typing) {
        return '<div class="msg ai" data-i="' + i + '"><div class="ai-avatar">S</div>'
          + '<div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div></div>';
      }
      const actions = '<div class="msg-actions">'
        + '<button onclick="SYLVEX.copyMsg(' + i + ')" title="Copy">Copy</button>'
        + (m.role === 'ai' ? '<button onclick="SYLVEX.regenMsg(' + i + ')" title="Regenerate">Regenerate</button>' : '')
        + '<button onclick="SYLVEX.deleteMsg(' + i + ')" title="Delete">Delete</button></div>';
      let inner = '';
      if (m.text) inner += S.escapeHtml(m.text).replace(/\n/g, '<br>');
      if (m.imageUrl) inner += '<img class="gen-img" src="' + m.imageUrl + '" alt="generated" />';
      if (m.attachmentName) inner = '<div style="opacity:.7;font-size:12px;margin-bottom:4px">📎 ' + S.escapeHtml(m.attachmentName) + '</div>' + inner;
      return '<div class="msg ' + m.role + '" data-i="' + i + '">'
        + (m.role === 'ai' ? '<div class="ai-avatar">S</div>' : '')
        + '<div class="bubble">' + inner + '</div>' + actions + '</div>';
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
    if (mv) mv.textContent = 'SYLVEX';
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
    toast(t('generating') + ' · ' + computePrice() + ' ⚡️');
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
  function pickModelKey(e, key, label) {
    e.stopPropagation();
    // Persist label in CTRL.model[0] slot so downstream price/aiReply still works.
    S.CTRL.model[0] = label;
    S.CTRL_IDX.model = 0;
    currentModelLabel = label;
    const mv = document.getElementById('modelVal');
    if (mv) mv.textContent = 'SYLVEX';
    // Map model categories to studio mode where applicable.
    if (['video','image','music','voice','text'].indexOf(key) >= 0) {
      studioMode = key; activeCat = key;
    }
    if (key === 'pro' || key === 'lite') {
      // Pro/Lite default to text chat.
      studioMode = 'text'; activeCat = 'text';
    }
    renderModelPop();
    const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
    const bb = document.getElementById('modelBtn'); if (bb) bb.setAttribute('aria-expanded','false');
    toast(label);
    S.haptic.select();
  }
  function togglePlusPop(e) {
    if (e) e.stopPropagation();
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.add('show');
    const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }
  function closePlusSheet(e) {
    if (e && e.target && e.target.id !== 'plusSheet') return;
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
  }
  function attach(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    const inp = document.getElementById('attachInput');
    if (!inp) return;
    if (kind === 'image') { inp.accept = 'image/*'; pendingAttachAccept = 'image'; }
    else if (kind === 'video') { inp.accept = 'video/*'; pendingAttachAccept = 'video'; }
    else { inp.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx'; pendingAttachAccept = 'file'; }
    inp.value = '';
    inp.click();
  }
  function onAttachFile(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    // Limit ~10MB.
    if (f.size > 10 * 1024 * 1024) { toast('File too large (max 10 MB)'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const b64 = result.split(',')[1] || '';
      pendingAttachment = {
        kind: pendingAttachAccept || 'file',
        mime: f.type || 'application/octet-stream',
        name: f.name,
        dataBase64: b64,
      };
    };
    reader.readAsDataURL(f);
  }
  function clearAttachment() {
    pendingAttachment = null;
  }
  function genAction(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    studioMode = kind === 'voice' ? 'voice' : kind;
    activeCat = studioMode;
    const labels = { image:'Generate Image', video:'Generate Video', music:'Generate Music', voice:'Voiceover' };
    toast(labels[kind] || kind);
    const ta = document.getElementById('chatInput');
    if (ta) ta.focus();
  }
  function toggleHistory(e) {
    if (e) e.stopPropagation();
    const d = document.getElementById('histDrawer');
    const b = document.getElementById('histBackdrop');
    if (!d || !b) return;
    const on = !d.classList.contains('show');
    d.classList.toggle('show', on);
    b.classList.toggle('show', on);
  }
  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }
  async function callGenerate(promptText, attachment) {
    const history = chatMessages
      .filter((m) => !m.typing && m.text && (m.role === 'user' || m.role === 'ai'))
      .slice(-10)
      .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }));
    const payload = {
      telegram_id: getTelegramId(),
      prompt: promptText,
      mode: studioMode,
      model: pickOpenAIModel(),
      history,
      attachment: attachment || null,
    };
    const res = await fetch('/api/public/prostudio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok || !j.ok) throw new Error(j.error || ('HTTP ' + res.status));
    return j;
  }

  async function sendChat() {
    const ta = document.getElementById('chatInput');
    const v = (ta.value || '').trim();
    const attachment = pendingAttachment;
    if (!v && !attachment) return;
    chatMessages.push({
      role: 'user',
      text: v,
      attachmentName: attachment ? attachment.name : null,
    });
    ta.value = ''; autoGrow(ta);
    clearAttachment();
    chatMessages.push({ typing: true, role: 'ai' });
    renderChat();
    S.haptic.impact('light');
    try {
      const j = await callGenerate(v, attachment);
      chatMessages.pop();
      if (j.type === 'image') {
        chatMessages.push({ role: 'ai', text: '', imageUrl: j.image_url });
      } else {
        chatMessages.push({ role: 'ai', text: j.text || '' });
      }
    } catch (err) {
      chatMessages.pop();
      chatMessages.push({ role: 'ai', text: '⚠️ ' + (err && err.message ? err.message : 'Generation failed') });
    }
    renderChat();
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
    callGenerate(prev.text, null)
      .then((j) => {
        chatMessages[i] = j.type === 'image'
          ? { role: 'ai', text: '', imageUrl: j.image_url }
          : { role: 'ai', text: j.text || '' };
        renderChat();
      })
      .catch((err) => {
        chatMessages[i] = { role: 'ai', text: '⚠️ ' + (err && err.message ? err.message : 'Regeneration failed') };
        renderChat();
      });
  }

  /* ===== Voice (mic) recording → Whisper ===== */
  async function toggleMic(e) {
    if (e) e.stopPropagation();
    const btn = document.getElementById('micBtn');
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast('Microphone not supported'); return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      toast('Microphone access denied'); return;
    }
    const mime = ['audio/webm', 'audio/mp4'].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
    try {
      mediaRecorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime }) : new MediaRecorder(mediaStream);
    } catch {
      mediaRecorder = new MediaRecorder(mediaStream);
    }
    mediaChunks = [];
    mediaRecorder.ondataavailable = (ev) => { if (ev.data && ev.data.size > 0) mediaChunks.push(ev.data); };
    mediaRecorder.onstop = async () => {
      if (btn) btn.classList.remove('rec');
      try { mediaStream.getTracks().forEach((t) => t.stop()); } catch {}
      const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      if (blob.size < 800) { toast('Recording too short'); return; }
      const ta = document.getElementById('chatInput');
      if (ta) { ta.placeholder = 'Transcribing…'; }
      try {
        const fd = new FormData();
        const ext = (blob.type.includes('mp4') ? 'mp4' : 'webm');
        fd.append('file', blob, 'voice.' + ext);
        const r = await fetch('/api/public/prostudio/transcribe', { method: 'POST', body: fd });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(j.error || 'transcribe failed');
        if (ta) { ta.value = (ta.value ? ta.value + ' ' : '') + (j.text || ''); autoGrow(ta); ta.focus(); }
      } catch (err) {
        toast('Voice: ' + (err && err.message ? err.message : 'failed'));
      } finally {
        if (ta) ta.placeholder = 'Message SYLVEX…';
      }
    };
    mediaRecorder.start();
    if (btn) btn.classList.add('rec');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }
  function deleteMsg(i) {
    chatMessages.splice(i, 1); renderChat();
    S.haptic.impact('light');
  }
  function newChat() {
    chatMessages = [{ role: 'ai', text: "New conversation started. How can I help?" }];
    renderChat();
    S.haptic.impact('light');
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
      const bp = document.getElementById('brandPop'); if (bp) bp.classList.remove('show');
      const bb = document.getElementById('brandBtn'); if (bb) bb.setAttribute('aria-expanded','false');
    });

    // Brand dropdown
    const brandBtn = document.getElementById('brandBtn');
    const brandPop = document.getElementById('brandPop');
    if (brandBtn && brandPop) {
      brandBtn.addEventListener('click', e => {
        e.stopPropagation();
        const show = !brandPop.classList.contains('show');
        brandPop.classList.toggle('show', show);
        brandBtn.setAttribute('aria-expanded', show ? 'true' : 'false');
      });
      brandPop.querySelectorAll('button[data-brand]').forEach(b => {
        b.addEventListener('click', e => {
          e.stopPropagation();
          const k = b.dataset.brand;
          brandPop.classList.remove('show');
          brandBtn.setAttribute('aria-expanded','false');
          if (k === 'settings') { switchView('settings'); return; }
          if (k === 'studio' || k === 'pro' || k === 'lite') {
            switchView('tools');
            const mv = document.getElementById('modelVal');
            const label = k === 'pro' ? 'SYLVEX Pro' : k === 'lite' ? 'SYLVEX Lite' : 'SYLVEX Studio';
            if (mv) mv.textContent = label;
            toast(label);
          }
        });
      });
    }

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

    // Keyboard offset: keep the Pro Studio input pinned above the on-screen
    // keyboard without shrinking the app or moving the header. The bottom
    // nav stays in its natural position and gets covered by the keyboard.
    const vv = window.visualViewport;
    if (vv) {
      const updateKb = () => {
        const kb = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
        document.documentElement.style.setProperty('--kb', kb + 'px');
        document.body.classList.toggle('kb-open', kb > 80);
      };
      vv.addEventListener('resize', updateKb);
      vv.addEventListener('scroll', updateKb);
      updateKb();
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
    if (S.syncUser) S.syncUser();
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, pickModelKey, toggleModelPop, togglePlusPop, closePlusSheet,
    attach, onAttachFile, clearAttachment, genAction, toggleHistory, autoGrow, toggleMic,
    sendChat, copyMsg, regenMsg, deleteMsg, newChat,
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
  window.openSupport    = openSupport;
  window.closeSupport   = closeSupport;
  window.sendSupport    = sendSupport;
  window.generateNow    = generateNow;
})();