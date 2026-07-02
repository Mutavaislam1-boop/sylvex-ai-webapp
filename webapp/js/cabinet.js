// Cabinet controller: wires DOM events, renders dynamic content, manages
// Pro Studio chat workspace, support modal, hero carousel, pricing logic.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});

  // Pro Studio state.
  let studioMode = 'pro';
  let activeCat = null;
  let chatMessages = [];
  let currentConvId = null;
  let conversationsCache = [];
  // Pending attachment for next send.
  let pendingAttachment = null; // { kind, mime, name, dataBase64 }
  let pendingAttachAccept = '';
  // Voice recording state.
  let mediaRecorder = null;
  let mediaChunks = [];
  let mediaStream = null;
  let currentModelLabel = 'SYLVEX Pro';

  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      return u && u.id ? Number(u.id) : Number(S.user && S.user.telegram_id ? S.user.telegram_id : 0);
    } catch { return 0; }
  }

  function pickOpenAIModel() {
    if (studioMode === 'image') return 'gpt-image-1';
    return /lite/i.test(currentModelLabel || '') ? 'gpt-4o-mini' : 'gpt-4o';
  }

  function uiLang() {
    return (localStorage.getItem('sylvex-lang') || 'en').slice(0, 2);
  }

  function localizedGreeting() {
    const l = uiLang();
    if (l === 'ru') return 'Здравствуйте! Чем могу помочь?';
    if (l === 'ar') return 'مرحباً! كيف يمكنني مساعدتك؟';
    if (l === 'tr') return 'Merhaba! Size nasıl yardımcı olabilirim?';
    return 'Hi! How can I help you today?';
  }

  /* ===== Rendering ===== */
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = '';
  }

  function renderModelPop() {
    const el = document.getElementById('modelPop'); if (!el) return;
    const items = [
      { k:'pro',  label:'SYLVEX Pro'  },
      { k:'lite', label:'SYLVEX Lite' },
    ];
    el.innerHTML = items.map(it =>
      '<button class="' + (currentModelLabel === it.label ? 'sel' : '') +
      '" onclick="SYLVEX.pickModelKey(event,\'' + it.k + '\',\'' + it.label + '\')">' + it.label + '</button>'
    ).join('');
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
    if (mv) mv.textContent = currentModelLabel;
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
    currentModelLabel = label;
    studioMode = key === 'pro' ? 'pro' : 'lite';
    activeCat = studioMode;
    const mv = document.getElementById('modelVal');
    if (mv) mv.textContent = label;
    renderModelPop();
    const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
    const bb = document.getElementById('modelBtn'); if (bb) bb.setAttribute('aria-expanded','false');
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
      try { updateSendButton(); } catch {}
    };
    reader.readAsDataURL(f);
  }
  function clearAttachment() {
    pendingAttachment = null;
    try { updateSendButton(); } catch {}
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
      conversation_id: currentConvId,
      language: uiLang(),
    };
    const res = await fetch('/api/public/prostudio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await res.json().catch(() => ({}));
    if (res.status === 402 && j && j.paywall) {
      const err = new Error('paywall');
      err.paywall = true;
      throw err;
    }
    if (!res.ok || !j.ok) throw new Error(j.error || ('HTTP ' + res.status));
    if (j.conversation_id) currentConvId = j.conversation_id;
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
    ta.value = ''; autoGrow(ta); updateSendButton();
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
      loadConversations(); // refresh sidebar order
    } catch (err) {
      chatMessages.pop();
      if (err && err.paywall) {
        renderChat();
        openPaywall();
        return;
      }
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
    currentConvId = null;
    chatMessages = [{ role: 'ai', text: localizedGreeting() }];
    renderChat();
    S.haptic.impact('light');
  }

  /* ===== Real history sidebar ===== */
  async function loadConversations() {
    const tg = getTelegramId();
    if (!tg) return;
    try {
      const r = await fetch('/api/public/prostudio/conversations?telegram_id=' + tg);
      const j = await r.json();
      conversationsCache = (j && j.conversations) || [];
      renderConvList();
    } catch {}
  }
  function renderConvList() {
    const el = document.getElementById('hdConvList'); if (!el) return;
    if (!conversationsCache.length) {
      el.innerHTML = '<div class="hd-label" style="opacity:.5">No chats yet</div>';
      return;
    }
    el.innerHTML = conversationsCache.map(c =>
      '<div class="hd-item-row">' +
        '<button class="hd-item ' + (c.id === currentConvId ? 'act' : '') + '" onclick="SYLVEX.openConv(\'' + c.id + '\')">' +
          S.escapeHtml(c.title || 'Chat') +
        '</button>' +
        '<button class="hd-del" onclick="SYLVEX.deleteConv(event,\'' + c.id + '\')" aria-label="Delete">×</button>' +
      '</div>'
    ).join('');
  }
  async function openConv(id) {
    const tg = getTelegramId(); if (!tg) return;
    try {
      const r = await fetch('/api/public/prostudio/conversations?telegram_id=' + tg + '&conversation_id=' + id);
      const j = await r.json();
      if (!j.ok) return;
      currentConvId = id;
      chatMessages = (j.messages || []).map(m => ({
        role: m.role === 'assistant' ? 'ai' : 'user',
        text: m.role === 'assistant' ? (m.response_text || '') : (m.prompt || ''),
        imageUrl: m.image_url || undefined,
      }));
      if (!chatMessages.length) chatMessages = [{ role: 'ai', text: localizedGreeting() }];
      renderChat();
      renderConvList();
      toggleHistory();
    } catch {}
  }
  async function deleteConv(e, id) {
    e.stopPropagation();
    const tg = getTelegramId(); if (!tg) return;
    await fetch('/api/public/prostudio/conversations?telegram_id=' + tg + '&conversation_id=' + id, { method: 'DELETE' });
    if (id === currentConvId) newChat();
    loadConversations();
  }

  /* ===== Paywall ===== */
  function openPaywall() {
    const el = document.getElementById('paywall');
    if (el) el.classList.add('show');
  }
  function closePaywall(e) {
    if (e && e.target && e.target.id !== 'paywall') return;
    const el = document.getElementById('paywall');
    if (el) el.classList.remove('show');
  }
  function openShopFromPaywall() {
    closePaywall();
    switchView('shop');
  }

  /* ===== Shop: buy flow ===== */
  const PACK_META = {
    sub_month: { title: 'SYLVEX Pro · 1 месяц',  price: '$5 · 230 ⭐' },
    sub_year:  { title: 'SYLVEX Pro · 1 год',    price: '$59 · 2751 ⭐' },
    pack_100:  { title: '100 ⚡️ токенов',        price: '$1 · 46 ⭐' },
    pack_500:  { title: '500 ⚡️ токенов',        price: '$5 · 230 ⭐' },
    pack_1000: { title: '1000 ⚡️ токенов',       price: '$10 · 460 ⭐' },
    pack_2000: { title: '2000 ⚡️ токенов',       price: '$20 · 920 ⭐' },
    pack_3000: { title: '3000 ⚡️ токенов',       price: '$30 · 1380 ⭐' },
    pack_4000: { title: '4000 ⚡️ токенов',       price: '$40 · 1840 ⭐' },
    pack_5000: { title: '5000 ⚡️ токенов',       price: '$50 · 2300 ⭐' },
  };
  const PAYPAL_PAYMENT_LINKS = {
    pack_500: 'https://www.paypal.com/ncp/payment/QXN7U6RQU7Y8L',
    pack_1000: 'https://www.paypal.com/ncp/payment/YRWTDN4D585SL',
    pack_2000: 'https://www.paypal.com/ncp/payment/YGGSLURF7ZC8N',
    pack_3000: 'https://www.paypal.com/ncp/payment/5MV8DDWFZK5KC',
    pack_4000: 'https://www.paypal.com/ncp/payment/Z5R9QMJKY2A2Y',
    pack_5000: 'https://www.paypal.com/ncp/payment/LTF8NMXED9ZCW',
  };
  const PAYPAL_PRO_MONTHLY_PLAN_ID = 'P-2JN99488MP781262CNJDGCZI';
  const PAYPAL_PRO_YEARLY_PLAN_ID = 'P-0YT1496917791881BNJDGRMY';
  const paypalSubscriptionRendered = {};
  const paypalSubscriptionRenderAttempts = {};
  let pendingPack = null;
  function getPayPalSubscriptionConfig(packId) {
    if (packId === 'sub_month') {
      return {
        containerId: 'paypalSubscribePayMonth',
        planId: PAYPAL_PRO_MONTHLY_PLAN_ID,
        planType: 'monthly',
      };
    }
    if (packId === 'sub_year') {
      return {
        containerId: 'paypalSubscribePayYear',
        planId: PAYPAL_PRO_YEARLY_PLAN_ID,
        planType: 'yearly',
      };
    }
    return null;
  }
  function resetPayPalSubscriptionPanel() {
    const panel = document.getElementById('paypalSubscriptionPanel');
    if (panel) panel.hidden = true;
    ['paypalSubscribePayMonth', 'paypalSubscribePayYear'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    });
  }
  function showPayPalSubscriptionPanel(packId) {
    const config = getPayPalSubscriptionConfig(packId);
    const panel = document.getElementById('paypalSubscriptionPanel');
    if (!config || !panel) return false;
    resetPayPalSubscriptionPanel();
    const container = document.getElementById(config.containerId);
    if (!container) return false;
    panel.hidden = false;
    container.hidden = false;
    renderPayPalSubscriptionButton(config);
    return true;
  }
  function openBuy(packId) {
    // If already subscribed and clicking same-tier subscription card, open info modal instead.
    const u = S.user || {};
    if ((packId === 'sub_month' || packId === 'sub_year')
        && u.subscription_status === 'active') {
      openSubActive(packId);
      return;
    }
    pendingPack = packId;
    const m = PACK_META[packId] || { title: packId, price: '—' };
    const tEl = document.getElementById('payPackTitle'); if (tEl) tEl.textContent = m.title;
    const pEl = document.getElementById('payPackPrice'); if (pEl) pEl.textContent = m.price;
    const fullName = [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || 'Guest';
    const handle   = u.username ? '@' + u.username : '@user';
    const nm = document.getElementById('payUserName');   if (nm) nm.textContent = fullName;
    const hd = document.getElementById('payUserHandle'); if (hd) hd.textContent = handle;
    const av = document.getElementById('payAvatar');
    if (av) {
      av.innerHTML = '';
      if (u.photo_url) {
        const img = document.createElement('img'); img.src = u.photo_url; img.alt = '';
        av.appendChild(img);
      } else {
        const ini = ((u.first_name || u.username || '·').slice(0,1) + (u.last_name || '').slice(0,1)).toUpperCase();
        av.textContent = ini || '··';
      }
    }
    const bal = Number(u.balance || 0);
    const bEl = document.getElementById('payBalance');    if (bEl) bEl.textContent = bal.toLocaleString();
    const bU  = document.getElementById('payBalanceUsd'); if (bU)  bU.textContent  = '≈ $' + (bal/100).toFixed(2);
    resetPayPalSubscriptionPanel();
    switchView('pay');
    S.haptic && S.haptic.impact('light');
  }
  function closeBuy() { switchView('shop'); }

  /* ===== Subscription state rendering ===== */
  let _cdTimer = null;
  function fmtCountdown(ms) {
    if (ms <= 0) return '0 д 0 ч 0 м 0 с';

    const totalSeconds = Math.floor(ms / 1000);
    const totalDays = Math.floor(totalSeconds / 86400);
    const months = Math.floor(totalDays / 30);
    const days = totalDays % 30;
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (months > 0) {
      return months + ' мес ' + days + ' д ' + hours + ' ч ' + minutes + ' м ' + seconds + ' с';
    }

    return totalDays + ' д ' + hours + ' ч ' + minutes + ' м ' + seconds + ' с';
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString('ru-RU', { day:'2-digit', month:'long', year:'numeric' }); }
    catch { return '—'; }
  }

  function renderPayPalSubscriptionButton(config) {
    const container = document.getElementById(config.containerId);
    if (!container || paypalSubscriptionRendered[config.containerId]) return;

    if (!window.paypal || !window.paypal.Buttons) {
      paypalSubscriptionRenderAttempts[config.containerId] = (paypalSubscriptionRenderAttempts[config.containerId] || 0) + 1;
      if (paypalSubscriptionRenderAttempts[config.containerId] < 30) {
        setTimeout(() => renderPayPalSubscriptionButton(config), 300);
      }
      return;
    }

    container.innerHTML = '';
    window.paypal.Buttons({
      style: {
        shape: 'rect',
        color: 'gold',
        layout: 'vertical',
        label: 'subscribe',
        height: 45,
      },
      createSubscription(data, actions) {
        const tg = getTelegramId();
        if (!tg) {
          toast('Telegram ID не найден');
          return Promise.reject(new Error('telegram_id_required'));
        }
        return actions.subscription.create({
          plan_id: config.planId,
        });
      },
      async onApprove(data) {
        const subscriptionID = data && data.subscriptionID;
        const tg = getTelegramId();
        if (!subscriptionID || !tg) {
          toast('Не удалось сохранить подписку PayPal');
          return;
        }

        try {
          const response = await fetch('/api/public/payments/paypal/subscription-created', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              telegram_id: tg,
              user_id: tg,
              subscription_id: subscriptionID,
              subscriptionID,
              plan_id: config.planId,
              plan_type: config.planType,
            }),
          });
          const result = await response.json();
          if (!response.ok || result.error) {
            toast('Ошибка: ' + (result.error || response.status));
            return;
          }
          toast('Подписка оформляется. После подтверждения PayPal статус обновится.');
          resetPayPalSubscriptionPanel();
          if (S.syncUser) setTimeout(() => S.syncUser(), 2500);
        } catch (e) {
          toast('Сетевая ошибка');
        }
      },
      onError(err) {
        console.warn('PAYPAL SUBSCRIPTION ERROR:', err);
        toast('PayPal подписка не открылась');
      },
      onCancel() {
        toast('Подписка PayPal отменена');
      },
    }).render('#' + config.containerId).then(() => {
      paypalSubscriptionRendered[config.containerId] = true;
    }).catch((err) => {
      console.warn('PAYPAL SUBSCRIPTION RENDER FAILED:', err);
    });
  }

  function renderSubscription() {
    const u = S.user || {};
    const active = u.subscription_status === 'active';
    const plan = u.subscription_plan; // 'month' | 'year' | null
    const expIso = u.subscription_expires_at;
    ['subMonthCard','subYearCard'].forEach((cid) => {
      const card = document.getElementById(cid); if (!card) return;
      const key = cid === 'subMonthCard' ? 'month' : 'year';
      const badge = card.querySelector('[data-sub-el="badge"]');
      const prices = card.querySelector('[data-sub-el="prices"]');
      const cd = card.querySelector('[data-sub-el="countdown"]');
      const cta = card.querySelector('[data-sub-el="cta"]');
      const isThis = active && plan === key;
      const priceEls = card.querySelectorAll('[data-sub-el="prices"], .sub-price, .sub-old, .sub-old-price, .sub-stars, .sub-discount, .sub-save, .sub-percent');
      if (isThis) {
        if (badge) badge.hidden = true;
        if (prices) prices.hidden = true;
        priceEls.forEach((el) => { el.hidden = true; el.style.display = 'none'; });
        if (cd) { cd.hidden = false; const v = cd.querySelector('[data-sub-cd]'); if (v && expIso) v.textContent = fmtCountdown(new Date(expIso).getTime() - Date.now()); }
        if (cta) { cta.hidden = false; cta.textContent = 'Вы подписаны ✓'; cta.classList.add('sub-cta-active'); }
      } else {
        if (badge) badge.hidden = false;
        if (prices) prices.hidden = false;
        priceEls.forEach((el) => { el.hidden = false; el.style.display = ''; });
        if (cd) cd.hidden = true;
        if (key === 'month' || key === 'year') {
          if (cta) {
            cta.hidden = false;
            cta.textContent = 'Выбрать оплату';
            cta.classList.remove('sub-cta-active');
          }
        }
      }
    });
    // Manage-subscription row subtitle
    const ms = document.getElementById('manageSubSub');
    if (ms) ms.textContent = active
      ? (plan === 'year' ? '1 год · до ' : '1 месяц · до ') + fmtDate(expIso)
      : 'Нет активной подписки';
    // Live countdown every second while subscription is active.
    if (_cdTimer) clearInterval(_cdTimer);
    if (active && expIso) {
      const tickCountdown = () => {
        const ms = new Date(expIso).getTime() - Date.now();
        document.querySelectorAll('[data-sub-cd]').forEach((el) => { el.textContent = fmtCountdown(ms); });
        const sa = document.getElementById('saCountdown'); if (sa) sa.textContent = fmtCountdown(ms);
        if (ms <= 0 && S.syncUser) S.syncUser();
      };
      tickCountdown();
      _cdTimer = setInterval(tickCountdown, 1000);
    }
  }

  function openSubActive(packId) {
    const u = S.user || {};
    const plan = u.subscription_plan || (packId === 'sub_year' ? 'year' : 'month');
    const exp = u.subscription_expires_at;
    document.getElementById('saPlan').textContent = plan === 'year' ? 'SYLVEX Pro · 1 год' : 'SYLVEX Pro · 1 месяц';
    document.getElementById('saExpires').textContent = fmtDate(exp);
    document.getElementById('saCountdown').textContent = exp ? fmtCountdown(new Date(exp).getTime() - Date.now()) : '—';
    document.getElementById('subActiveModal').classList.add('show');
    pendingPack = 'sub_' + plan;
  }
  function renewFromModal() {
    closeModal(null, 'subActiveModal');
    // Force purchase flow (bypass "already subscribed" branch).
    const pack = pendingPack || 'sub_month';
    const savedUser = S.user; S.user = Object.assign({}, savedUser, { subscription_status: 'free' });
    openBuy(pack);
    S.user = savedUser;
  }
  function openManageSub() {
    const u = S.user || {};
    if (u.subscription_status === 'active') openSubActive('sub_' + (u.subscription_plan || 'month'));
    else switchView('shop');
  }

  /* ===== Modal helpers ===== */
  function closeModal(e, id) {
    if (e && e.target && e.target.id !== id) return;
    const el = document.getElementById(id); if (el) el.classList.remove('show');
  }
  function openProInfo() {
    const u = S.user || {};
    const body = document.getElementById('proInfoBody');
    if (!body) return;
    if (u.subscription_status === 'active') {
      const plan = u.subscription_plan === 'year' ? '1 год' : '1 месяц';
      const exp = u.subscription_expires_at;
      body.innerHTML = '<h3 style="margin:6px 0 4px;font-size:17px">✅ Вы подписаны</h3>'
        + '<div class="sub-info-grid" style="margin-top:12px">'
        + '<div><div class="k">Тариф</div><div class="v">SYLVEX Pro · ' + plan + '</div></div>'
        + '<div><div class="k">Осталось</div><div class="v">' + (exp ? fmtCountdown(new Date(exp).getTime() - Date.now()) : '—') + '</div></div>'
        + '<div><div class="k">Окончание</div><div class="v">' + fmtDate(exp) + '</div></div>'
        + '</div>';
    } else {
      body.innerHTML = '<h3 style="margin:6px 0 8px;font-size:17px">Нет активной подписки</h3>'
        + '<p style="opacity:.75;font-size:13px;margin:0 0 14px">Оформите подписку, чтобы получить полный доступ.</p>'
        + '<button class="topup" style="width:100%" onclick="SYLVEX.closeModal(null,\'proInfoModal\');switchView(\'shop\')">Открыть магазин</button>';
    }
    document.getElementById('proInfoModal').classList.add('show');
  }

  /* ===== Edit profile ===== */
  const AVATAR_PRESETS = [
    'assets/avatars/a1.png','assets/avatars/a2.png','assets/avatars/a3.png',
    'assets/avatars/a4.png','assets/avatars/a5.png',
  ];
  let epSelectedAvatar = null;
  function openEditProfile() {
    const u = S.user || {};
    document.getElementById('epName').value = u.display_name || [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || '';
    epSelectedAvatar = u.custom_avatar_url || null;
    const grid = document.getElementById('avatarGrid');
    if (grid) {
      const items = [{ url: null, label: 'TG' }].concat(AVATAR_PRESETS.map((p) => ({ url: p })));
      grid.innerHTML = items.map((it, i) => {
        const sel = (epSelectedAvatar || '') === (it.url || '') ? 'sel' : '';
        const inner = it.url ? '<img src="' + it.url + '" alt="" />' : '<span>TG</span>';
        return '<button class="av-opt ' + sel + '" data-url="' + (it.url || '') + '" onclick="SYLVEX.pickAvatar(this)">' + inner + '</button>';
      }).join('');
    }
    document.getElementById('editProfileModal').classList.add('show');
  }
  function pickAvatar(btn) {
    epSelectedAvatar = btn.dataset.url || null;
    document.querySelectorAll('#avatarGrid .av-opt').forEach((el) => el.classList.remove('sel'));
    btn.classList.add('sel');
  }
  async function saveEditProfile() {
    const name = (document.getElementById('epName').value || '').trim().slice(0, 60);
    const body = {
      initData: S.tg && S.tg.initData ? S.tg.initData : '',
      initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
      telegram_id: getTelegramId(),
      display_name: name,
      custom_avatar_url: epSelectedAvatar,
    };
    try {
      const r = await fetch('/api/public/telegram/profile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || j.error) { toast('Ошибка: ' + (j.error || r.status)); return; }
      toast('Сохранено ✓');
      closeModal(null, 'editProfileModal');
      S.syncUser && S.syncUser();
    } catch { toast('Сетевая ошибка'); }
  }

  /* ===== Theme picker ===== */
  const THEMES = [
    { id: 'dark',  label: 'Тёмная',    css: { '--bg-0':'#212121','--bg-1':'#171717','--bg-2':'#2f2f2f','--surface':'#2f2f2f','--surface-2':'#3a3a3a','--text':'#ececec' }, mode:'dark' },
    { id: 'black', label: 'Чёрная',    css: { '--bg-0':'#000000','--bg-1':'#0a0a0a','--bg-2':'#141414','--surface':'#161616','--surface-2':'#222222','--text':'#f5f5f5' }, mode:'dark' },
    { id: 'blue',  label: 'Синяя ночь', css: { '--bg-0':'#0b1220','--bg-1':'#0a0f1c','--bg-2':'#111a2e','--surface':'#12203a','--surface-2':'#1a2c4d','--text':'#eaf1ff' }, mode:'dark' },
    { id: 'plum',  label: 'Слива',     css: { '--bg-0':'#1a0f22','--bg-1':'#120a19','--bg-2':'#241432','--surface':'#2b1a3a','--surface-2':'#3a2450','--text':'#f2eaff' }, mode:'dark' },
    { id: 'light', label: 'Светлая',   css: { '--bg-0':'#ffffff','--bg-1':'#f7f7f8','--bg-2':'#ffffff','--surface':'#f4f4f4','--surface-2':'#ececec','--text':'#0d0d0d' }, mode:'light' },
  ];
  function applyTheme(themeId) {
    const t = THEMES.find((x) => x.id === themeId) || THEMES[0];
    document.documentElement.setAttribute('data-theme', t.mode);
    const r = document.documentElement.style;
    Object.keys(t.css).forEach((k) => r.setProperty(k, t.css[k]));
    localStorage.setItem('sylvex-theme-id', themeId);
    // Persist to backend.
    const body = {
      initData: S.tg && S.tg.initData ? S.tg.initData : '',
      initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
      telegram_id: getTelegramId(),
      theme_preference: { id: themeId },
    };
    fetch('/api/public/telegram/profile', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).catch(() => {});
    renderThemeGrid();
  }
  function renderThemeGrid() {
    const g = document.getElementById('themeGrid'); if (!g) return;
    const cur = localStorage.getItem('sylvex-theme-id')
      || (S.user && S.user.theme_preference && S.user.theme_preference.id)
      || 'dark';
    g.innerHTML = THEMES.map((t) => {
      const sel = cur === t.id ? 'sel' : '';
      const sw = 'background:' + t.css['--bg-0'];
      const swInner = 'background:' + t.css['--surface-2'];
      return '<button class="th-opt ' + sel + '" onclick="SYLVEX.applyTheme(\'' + t.id + '\')">'
        + '<div class="th-sw" style="' + sw + '"><div class="th-sw-inner" style="' + swInner + '"></div></div>'
        + '<div class="th-lbl">' + t.label + '</div></button>';
    }).join('');
  }
  function openThemePicker() {
    renderThemeGrid();
    document.getElementById('themeModal').classList.add('show');
  }
  function applyStoredTheme() {
    const id = localStorage.getItem('sylvex-theme-id')
      || (S.user && S.user.theme_preference && S.user.theme_preference.id);
    if (id) applyTheme(id);
  }

  /* ===== Referrals ===== */
  let _refData = null;
  async function openReferrals() {
    document.getElementById('refsModal').classList.add('show');
    document.getElementById('refLinkVal').textContent = 'Загрузка…';
    const tg = getTelegramId(); if (!tg) return;
    try {
      const r = await fetch('/api/public/telegram/referrals?telegram_id=' + tg);
      const j = await r.json();
      _refData = j;
      document.getElementById('refLinkVal').textContent = j.link || j.code || '—';
      document.getElementById('refCount').textContent = j.referrals_count || 0;
      document.getElementById('refEarned').textContent = (j.tokens_earned || 0).toLocaleString();
      document.getElementById('refStatus').textContent = j.activated_at ? 'Активна' : 'Не активна';
      const btn = document.getElementById('refActivateBtn');
      if (btn) { btn.textContent = j.activated_at ? '✅ Активирована' : '🚀 Активировать'; btn.disabled = !!j.activated_at; }
    } catch { document.getElementById('refLinkVal').textContent = '—'; }
  }
  function copyRefLink() {
    const v = (_refData && (_refData.link || _refData.code)) || document.getElementById('refLinkVal').textContent;
    if (!v || v === '—') return;
    if (navigator.clipboard) navigator.clipboard.writeText(v).catch(() => {});
    toast('Ссылка скопирована');
    S.haptic && S.haptic.notify && S.haptic.notify('success');
  }
  async function activateRefLink() {
    const body = {
      initData: S.tg && S.tg.initData ? S.tg.initData : '',
      initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
      telegram_id: getTelegramId(),
      activate: true,
    };
    try {
      const r = await fetch('/api/public/telegram/referrals', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || j.error) { toast('Ошибка: ' + (j.error || r.status)); return; }
      toast('Ссылка активирована ✓');
      openReferrals();
    } catch { toast('Сетевая ошибка'); }
  }

  /* ===== Sign out ===== */
  function signOut() {
    try { localStorage.removeItem('sylvex-theme-id'); } catch {}
    if (S.tg && S.tg.close) S.tg.close();
  }
  function contactAdmin() {
    const url = 'https://t.me/sylvex_admin';
    const tgApp = S.tg;
    if (tgApp && tgApp.openTelegramLink) tgApp.openTelegramLink(url);
    else if (tgApp && tgApp.openLink)    tgApp.openLink(url);
    else window.open(url, '_blank');
  }
  function isTelegramLink(url) {
    return /^https:\/\/t\.me\//i.test(url || '') || /^tg:\/\//i.test(url || '');
  }
  function openPaymentUrl(url, method) {
    if (!url) {
      toast('Ссылка оплаты не найдена');
      return;
    }
    const tgApp = S.tg;
    if (method === 'crypto' && isTelegramLink(url) && tgApp && tgApp.openTelegramLink) {
      tgApp.openTelegramLink(url);
      return;
    }
    if (method === 'paypal') {
      window.location.href = url;
      return;
    }
    if (tgApp && tgApp.openLink) tgApp.openLink(url, { try_instant_view: false });
    else window.open(url, '_blank');
  }
  async function payWith(method) {
    const packId = pendingPack;
    if (!packId) return;
    const tg = getTelegramId();
    if (!tg) { toast('Telegram ID не найден'); return; }

    if (method === 'paypal' && PAYPAL_PAYMENT_LINKS[packId]) {
      window.location.href = PAYPAL_PAYMENT_LINKS[packId];
      return;
    }

    if (method === 'paypal' && getPayPalSubscriptionConfig(packId)) {
      if (showPayPalSubscriptionPanel(packId)) {
        toast('Выберите PayPal ниже');
      } else {
        toast('PayPal подписка недоступна');
      }
      return;
    }

    toast('Создаём счёт…');
    try {
      let path = '';
      if (method === 'stars')  path = '/api/public/payments/stars/invoice';
      if (method === 'paypal') path = '/api/public/payments/paypal/create-order';
      if (method === 'crypto') path = '/api/public/payments/crypto/invoice';
      if (!path) { toast('Способ оплаты недоступен'); return; }
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pack_id: packId,
          telegram_id: tg,
          user_id: tg,
          type: packId.indexOf('sub_') === 0 ? 'subscription' : 'tokens',
        }),
      });
      const j = await r.json();
      if (!r.ok || j.error) {
        if (j.error === 'paypal_not_configured') { toast('PayPal ещё не настроен'); return; }
        if (j.error === 'crypto_not_configured') { toast('Крипто-оплата ещё не настроена'); return; }
        toast('Ошибка: ' + (j.error || r.status));
        return;
      }
      const tgApp = S.tg;
      if (method === 'stars' && j.invoice_url && tgApp && tgApp.openInvoice) {
        tgApp.openInvoice(j.invoice_url, async (status) => {
          if (status === 'paid') {
            toast('Оплачено ✓');
            try {
              const confirmRes = await fetch('/api/public/payments/stars/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegram_id: tg, pack_id: packId, charge_id: j.charge_id }),
              });
              const confirmJson = await confirmRes.json();
              if (confirmRes.ok && confirmJson.user) {
                S.renderUser && S.renderUser(confirmJson.user);
              } else if (S.syncUser) {
                S.syncUser();
              }
            } catch {
              if (S.syncUser) S.syncUser();
            }
          } else if (status === 'failed' || status === 'cancelled') {
            toast('Оплата отменена');
          }
        });
      } else if (method === 'paypal') {
        const paypalUrl = j.url || j.approval_url || j.checkout_url;
        if (!paypalUrl) { toast('Ссылка PayPal не найдена'); return; }
        toast('Открываем PayPal…');
        console.log('PAYPAL CHECKOUT URL:', paypalUrl);
        openPaymentUrl(paypalUrl, method);
      } else if (j.url) {
        openPaymentUrl(j.url, method);
      } else if (j.invoice_url) {
        openPaymentUrl(j.invoice_url, method);
      }
    } catch (err) {
      toast('Сетевая ошибка');
    }
  }

  /* ===== Input mic/send toggle ===== */
  function updateSendButton() {
    const ta = document.getElementById('chatInput');
    const mic = document.getElementById('micBtn');
    const send = document.getElementById('sendBtn');
    if (!ta || !mic || !send) return;
    const has = (ta.value || '').trim().length > 0 || !!pendingAttachment;
    mic.hidden = has;
    send.hidden = !has;
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
      chatInput.addEventListener('input', updateSendButton);
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

  function initialViewFromUrl() {
    const allowed = new Set(['home', 'history', 'shop', 'pay', 'profile', 'settings', 'tools']);
    const params = new URLSearchParams(window.location.search || '');
    const hash = (window.location.hash || '').replace(/^#/, '');
    const raw = params.get('view') || params.get('screen') || params.get('section') || hash;
    const view = (raw || '').trim().toLowerCase();
    return allowed.has(view) ? view : 'home';
  }

  function applyInitialViewFromUrl() {
    const view = initialViewFromUrl();
    if (view && view !== 'home') switchView(view);
  }

  function handlePaymentReturnFromUrl() {
    const params = new URLSearchParams(window.location.search || '');
    if ((params.get('provider') || '').toLowerCase() !== 'paypal') return;

    const status = (params.get('payment') || '').toLowerCase();
    if (status === 'success') {
      toast('Оплата принята. Обновляем баланс…');
      if (S.syncUser) setTimeout(() => S.syncUser(), 1200);
    } else if (status === 'cancel') {
      toast('Оплата PayPal отменена');
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
    if (!chatMessages.length) chatMessages = [{ role: 'ai', text: localizedGreeting() }];
    renderChat();
    updateSendButton();
    handlePaymentReturnFromUrl();
    if (S.syncUser) {
      Promise.resolve(S.syncUser()).finally(() => {
        applyInitialViewFromUrl();
        applyStoredTheme();
      });
    }
    loadConversations();
    applyStoredTheme();
    applyInitialViewFromUrl();
    setTimeout(applyInitialViewFromUrl, 150);
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, pickModelKey, toggleModelPop, togglePlusPop, closePlusSheet,
    attach, onAttachFile, clearAttachment, genAction, toggleHistory, autoGrow, toggleMic,
    sendChat, copyMsg, regenMsg, deleteMsg, newChat,
    openConv, deleteConv, openPaywall, closePaywall, openShopFromPaywall, updateSendButton,
    openBuy, closeBuy, payWith, contactAdmin,
    openSupport, closeSupport, sendSupport,
    computePrice, updatePrice, generateNow,
    renderSubscription, openSubActive, renewFromModal, openManageSub, closeModal, openProInfo,
    openEditProfile, pickAvatar, saveEditProfile,
    openThemePicker, applyTheme,
    openReferrals, copyRefLink, activateRefLink,
    signOut,
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
