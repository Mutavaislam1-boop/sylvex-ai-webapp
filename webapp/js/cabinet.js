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

  // Information pages for the quick tools on the Home screen.
  // These pages are opened when the user taps a quick tool card.
  const QUICK_TOOL_INFO = [
    {
      key: 'image',
      title: 'Изображения',
      label: 'OpenAI Image',
      body: `
OpenAI Image — это инструменты для генерации, редактирования, анализа и понимания изображений. Они позволяют создавать новые изображения по текстовому описанию, изменять готовые фото, делать вариации, распознавать текст и анализировать визуальный контент.

Инструменты:
• Images API
• Image Generation
• Image Edits
• Image Variations
• Responses API with image input
• Image Generation Tool through Responses API
• Vision

Модели:
• GPT-Image-2
• GPT-Image-1.5
• GPT-Image-1
• GPT-Image-1 Mini
• GPT vision-capable models

Функционал генерации:
• text-to-image
• генерация изображений по промпту
• создание иллюстраций
• создание баннеров
• создание обложек
• создание визуальных концептов
• создание персонажей
• создание рекламных изображений
• создание изображений для соцсетей
• генерация изображений внутри agent workflow

Функционал редактирования:
• image edit
• редактирование изображения
• замена фона
• удаление объектов
• добавление объектов
• изменение стиля
• inpainting
• редактирование по маске
• reference images
• image-to-image
• создание вариантов изображения
• работа с несколькими изображениями

Анализ изображений:
• анализ фото
• описание изображения
• OCR
• распознавание текста на фото
• распознавание текста на скриншоте
• извлечение данных из чеков
• извлечение данных из таблиц на изображении
• визуальная классификация
• сравнение нескольких изображений
• structured output из изображения
• JSON extraction из изображения
      `.trim()
    },
    {
      key: 'text',
      title: 'Текст',
      label: 'OpenAI Text',
      body: `
OpenAI Text — это набор инструментов для работы с текстом, промптами, структурированными ответами, переводами, сценариями, статьями, описаниями и логикой запросов.

Инструменты:
• Responses API
• Conversations API
• Chat Completions
• Structured Outputs
• Function Calling
• Streaming
• Background Mode
• Batch API
• Prompt Caching
• Flex Processing

Модели:
• GPT-5.5
• GPT-5.4
• GPT-5.4 Mini
• GPT-5.4 Nano
• reasoning-модели
• multimodal-модели

Функционал:
• генерация текста
• обычный AI-чат
• написание статей
• написание описаний
• рекламные тексты
• сценарии
• посты для соцсетей
• исправление текста
• улучшение текста
• сокращение текста
• расширение текста
• перевод текста
• генерация промптов
• промпты для изображений
• промпты для видео
• промпты для музыки
• генерация идей
• структурированные ответы
• JSON-ответы
• извлечение данных
• code generation
• reasoning-задачи
• обработка сложных запросов
• потоковая генерация текста
• фоновые текстовые задачи
      `.trim()
    },
    {
      key: 'voice',
      title: 'Голос',
      label: 'OpenAI Voice / Text-to-Speech',
      body: `
OpenAI Voice — это инструменты для превращения текста в голос. Они позволяют создавать озвучку, дикторскую речь, рекламную подачу, эмоциональную речь и голосовые аудиофайлы.

Инструменты:
• Audio Speech
• Text-to-Speech
• Voice Instructions
• Voice Consents
• Custom Voice
• Realtime Voice Agent

Модели:
• GPT-4o Mini TTS
• TTS-1
• TTS-1 HD
• speech-compatible models

Функционал:
• text-to-speech
• текст в голос
• генерация речи
• выбор голоса
• управление стилем
• управление тоном
• управление скоростью
• управление эмоцией
• управление интонацией
• whispering
• accent
• emotional range
• дикторская озвучка
• рекламная озвучка
• спокойная озвучка
• энергичная озвучка
• custom voice
• voice consent
• voice creation
• voice id
• live voice agent

Voice Style:
• спокойный
• уверенный
• энергичный
• рекламный
• деловой
• мягкий
• эмоциональный
• дикторский
• кинематографичный
      `.trim()
    },
    {
      key: 'video',
      title: 'Видео',
      label: 'OpenAI Video / Sora',
      body: `
OpenAI Video — это инструменты для генерации и редактирования видео через Sora. Они позволяют создавать видео по текстовому описанию, редактировать готовые ролики, продолжать видео, делать remix и работать с персонажами.

Инструменты:
• Sora Video Create
• Sora Video Edit
• Sora Video Extend
• Sora Video Remix
• Sora Character
• Async Video Jobs
• Video Polling
• Video Download

Модели:
• Sora 2
• Sora 2 Pro

Функционал:
• text-to-video
• генерация видео по промпту
• создание коротких роликов
• создание вертикальных видео
• создание горизонтальных видео
• создание видео для соцсетей
• создание рекламных роликов
• создание cinematic-сцен
• создание анимационных сцен
• prompt + media video workflow
• редактирование видео
• продолжение видео
• remix видео
• character video workflow
• создание видео с постоянным персонажем
• получение статуса генерации
• скачивание готового видео

Video Create используется для создания видео по текстовому описанию. Пользователь описывает сцену, стиль, персонажа, движение камеры, атмосферу и действие в кадре.

Video Edit используется для изменения готового видео. Можно изменить сцену, стиль, фон, атмосферу, детали или отдельные элементы ролика.

Video Extend используется для продолжения уже созданного видео. Подходит для увеличения длительности сцены или продолжения движения.

Video Remix используется для создания новой версии видео на основе существующего ролика. Можно сохранить идею, но изменить стиль, атмосферу или визуальное исполнение.

Sora Character используется для работы с постоянными персонажами. Подходит для серийного контента, бренд-персонажей, маскотов и повторяющихся героев.

Параметры:
• model
• prompt
• size
• seconds
      `.trim()
    },
    {
      key: 'music',
      title: 'Музыка',
      label: 'OpenAI Music Assistant',
      body: `
OpenAI не является полноценным инструментом генерации музыки, но может использоваться как помощник для музыкальных задач: написания текстов песен, создания промптов для музыкальных AI, описания стиля, перевода и анализа лирики.

Инструменты:
• Responses API
• Text Generation
• Prompt Generation
• Audio Transcription
• Audio Translation

Функционал:
• написание текстов песен
• генерация музыкальных идей
• создание промптов для музыки
• описание стиля трека
• подбор жанра
• подбор настроения
• создание структуры песни
• написание куплетов
• написание припевов
• написание bridge
• улучшение текста песни
• перевод текста песни
• анализ лирики
• расшифровка аудио
• подготовка описания для музыкального AI

Что не является основной функцией OpenAI:
• полноценная генерация инструментальной музыки
• full song generation
• stems
• remix музыки
• BPM control
• tempo control
• image-to-music
• beat maker
      `.trim()
    },
    {
      key: 'documents',
      title: 'Документы',
      label: 'OpenAI Documents',
      body: `
OpenAI Documents — это инструменты для загрузки, анализа, поиска и обработки документов. Они позволяют работать с PDF, файлами, таблицами, инструкциями, договорами, отчётами и пользовательской базой знаний.

Инструменты:
• Files API
• Uploads API
• Vector Stores
• Vector Store Files
• Vector Store File Batches
• File Search
• Responses API with file input
• Embeddings

Функционал:
• загрузка файлов
• получение списка файлов
• получение metadata файла
• получение content файла
• multipart uploads
• file input
• поиск по файлам
• retrieval по документам
• создание vector store
• индексация файлов
• document Q&A
• анализ PDF
• анализ документов
• краткое содержание документа
• поиск информации внутри файла
• извлечение данных
• извлечение таблиц
• сравнение документов
• semantic document search
• user library
• knowledge base
• citations/results
• structured extraction
• JSON extraction из документа

Document Q&A используется для вопросов по содержанию файла. Пользователь загружает документ и может спрашивать, что в нём написано, где находится нужная информация или какие выводы можно сделать.

File Search используется для поиска информации внутри загруженных документов. Подходит для больших PDF, инструкций, договоров, отчётов и базы знаний.

Vector Store используется для создания базы знаний из документов. Файлы индексируются, после чего по ним можно выполнять смысловой поиск.
      `.trim()
    }
  ];
  function extraQuickToolCard(t) {
    return '' +
      '<button class="tool-card quick-tool-extra-card" type="button">' +
        '<div class="tool-ico">' + t.icon + '</div>' +
        '<div class="tool-title">' + t.title + '</div>' +
        '<div class="tool-desc">' + t.desc + '</div>' +
      '</button>';
  }

  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      if (u && u.id) return Number(u.id);
      if (S.user && S.user.telegram_id) return Number(S.user.telegram_id);
      return 0;
    } catch { return 0; }
  }

  async function ensureTelegramUser() {
    if (getTelegramId()) return S.user || null;

    try {
      if (S.userReady && typeof S.userReady.then === 'function') {
        await S.userReady;
      }
    } catch {}

    if (getTelegramId()) return S.user || null;

    if (S.syncUser) {
      try {
        S.userReady = S.syncUser();
        await S.userReady;
      } catch {}
    }

    return S.user || null;
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

  function ensureQuickToolInfoPage() {
    let page = document.getElementById('quickToolInfoPage');
    if (page) return page;

    page = document.createElement('div');
    page.id = 'quickToolInfoPage';
    page.className = 'quick-tool-info-page';
    page.innerHTML = '' +
      '<div class="quick-tool-info-head">' +
        '<button class="quick-tool-info-back" onclick="SYLVEX.closeQuickToolInfo()">‹</button>' +
        '<div>' +
          '<div class="quick-tool-info-kicker">OpenAI Tools</div>' +
          '<div class="quick-tool-info-title" id="quickToolInfoTitle">Инструмент</div>' +
        '</div>' +
      '</div>' +
      '<div class="quick-tool-info-card">' +
        '<div class="quick-tool-info-label" id="quickToolInfoLabel">OpenAI</div>' +
        '<div class="quick-tool-info-body" id="quickToolInfoBody"></div>' +
      '</div>';

    document.body.appendChild(page);
    return page;
  }

  function ensureQuickToolInfoStyles() {
    if (document.getElementById('quickToolInfoStyles')) return;
    const st = document.createElement('style');
    st.id = 'quickToolInfoStyles';
    st.textContent = `
      .quick-tool-info-page {
        position: fixed;
        inset: 0;
        z-index: 80;
        display: none;
        overflow-y: auto;
        padding: calc(env(safe-area-inset-top, 0px) + 18px) 16px calc(92px + env(safe-area-inset-bottom, 0px));
        background: radial-gradient(circle at top, rgba(255,255,255,.08), transparent 34%), var(--bg, #08090d);
        color: var(--text, #fff);
      }
      .quick-tool-info-page.show {
        display: block;
      }
      .quick-tool-info-head {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
      }
      .quick-tool-info-back {
        width: 42px;
        height: 42px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 16px;
        background: rgba(255,255,255,.06);
        color: #fff;
        font-size: 30px;
        line-height: 1;
      }
      .quick-tool-info-kicker {
        opacity: .55;
        font-size: 12px;
        letter-spacing: .08em;
        text-transform: uppercase;
        color: #fff;
      }
      .quick-tool-info-title {
        margin-top: 2px;
        font-size: 24px;
        font-weight: 800;
        color: #fff;
      }
      .quick-tool-info-card {
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 24px;
        padding: 18px;
        background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.035));
        box-shadow: 0 18px 60px rgba(0,0,0,.28);
        backdrop-filter: blur(18px);
      }
      .quick-tool-info-label {
        display: inline-flex;
        align-items: center;
        min-height: 28px;
        padding: 0 10px;
        margin-bottom: 14px;
        border-radius: 999px;
        background: rgba(255,255,255,.08);
        color: #fff;
        font-size: 12px;
        font-weight: 700;
      }
      .quick-tool-info-body {
        white-space: pre-line;
        color: rgba(255,255,255,.9);
        font-size: 14px;
        line-height: 1.62;
      }
      body.light .quick-tool-info-page {
        background: radial-gradient(circle at top, rgba(0,0,0,.05), transparent 34%), var(--bg, #f5f6fb);
      }
      body.light .quick-tool-info-card,
      body.light .quick-tool-info-back,
      body.light .quick-tool-info-label {
        border-color: rgba(0,0,0,.08);
        background: rgba(255,255,255,.72);
      }
      body.light .quick-tool-info-kicker,
      body.light .quick-tool-info-title,
      body.light .quick-tool-info-label,
      body.light .quick-tool-info-back,
      body.light .quick-tool-info-body {
        color: #fff;
      }
    `;
    document.head.appendChild(st);
  }

  function openQuickToolInfo(index) {
    const data = QUICK_TOOL_INFO[index];
    if (!data) return;

    ensureQuickToolInfoStyles();
    const page = ensureQuickToolInfoPage();

    const title = document.getElementById('quickToolInfoTitle');
    const label = document.getElementById('quickToolInfoLabel');
    const body = document.getElementById('quickToolInfoBody');

    if (title) title.textContent = data.title;
    if (label) label.textContent = data.label;
    if (body) body.textContent = data.body;

    page.classList.add('show');
    document.body.classList.add('quick-tool-info-open');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function closeQuickToolInfo() {
    const page = document.getElementById('quickToolInfoPage');
    if (page) page.classList.remove('show');
    document.body.classList.remove('quick-tool-info-open');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function renderDynamic() {
    const ht = document.getElementById('homeTools');
    const hh = document.getElementById('homeHist');
    const fh = document.getElementById('fullHist');
    const sg = document.getElementById('shopGrid');
    if (ht) {
      const extraTools = [
        { icon: '🎵', title: 'Музыка', desc: 'Тексты песен, промпты, идеи и анализ лирики' },
        { icon: '📄', title: 'Документы', desc: 'PDF, файлы, поиск, анализ и база знаний' },
      ];

      ht.innerHTML =
        S.toolsData.slice(0, 4).map(S.toolCard).join('') +
        extraTools.map(extraQuickToolCard).join('');
    }
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
  };
  let pendingPack = null;
  function openBuy(packId) {
    pendingPack = packId;
    const m = PACK_META[packId] || { title: packId, price: '—' };
    const tEl = document.getElementById('payPackTitle'); if (tEl) tEl.textContent = m.title;
    const pEl = document.getElementById('payPackPrice'); if (pEl) pEl.textContent = m.price;
    const u = S.user || {};
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
    switchView('pay');
    S.haptic && S.haptic.impact('light');
  }
  function parseSubscriptionDate(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function formatSubscriptionCountdown(expiresAt) {
    const end = parseSubscriptionDate(expiresAt);
    if (!end) return 'Осталось: —';

    const diff = end.getTime() - Date.now();
    if (diff <= 0) return 'Подписка закончилась';

    const totalMinutes = Math.floor(diff / 60000);
    const days = Math.floor(totalMinutes / 1440);
    const hours = Math.floor((totalMinutes % 1440) / 60);
    const minutes = totalMinutes % 60;

    if (days > 0) return 'Осталось: ' + days + 'д ' + hours + 'ч';
    if (hours > 0) return 'Осталось: ' + hours + 'ч ' + minutes + 'м';
    return 'Осталось: ' + minutes + 'м';
  }

  function getUserSubscriptionInfo() {
    const u = S.user || {};

    const plan = (
      u.subscription_plan ||
      u.sub_plan ||
      u.plan ||
      localStorage.getItem('sylvex-dev-sub-plan') ||
      ''
    ).toString().toLowerCase();

    const expiresAt = (
      u.subscription_expires_at ||
      u.subscription_until ||
      u.sub_expires_at ||
      u.pro_until ||
      localStorage.getItem('sylvex-dev-sub-expires-at') ||
      ''
    );

    const end = parseSubscriptionDate(expiresAt);
    const active = !!end && end.getTime() > Date.now();

    return { active, plan, expiresAt };
  }

  function renderSubscriptionCards() {
    const info = getUserSubscriptionInfo();
    document.querySelectorAll('[data-sub-plan]').forEach((card) => {
      const plan = (card.dataset.subPlan || '').toLowerCase();
      const isActive = info.active && (info.plan === plan || info.plan === 'sub_' + plan || !info.plan);
      card.classList.toggle('is-subscribed', !!isActive);

      // Find relevant elements inside the card if they exist
      const countdownEl = card.querySelector('[data-sub-countdown]');
      const activeBlock = card.querySelector('[data-sub-active]');
      const priceBlock = card.querySelector('[data-sub-price]');
      const buyBtn = card.querySelector('[data-sub-buy]');
      const subscribedBtn = card.querySelector('[data-sub-subscribed]');
      const discountBadge = card.querySelector('.discount-badge');

      if (isActive) {
        // Set the countdown text
        if (countdownEl) countdownEl.textContent = formatSubscriptionCountdown(info.expiresAt);
        // Show active block
        if (activeBlock) activeBlock.hidden = false;
        // Hide price block
        if (priceBlock) priceBlock.hidden = true;
        // Hide buy button
        if (buyBtn) buyBtn.hidden = true;
        // Show subscribed button
        if (subscribedBtn) {
          subscribedBtn.hidden = false;
          subscribedBtn.textContent = '✅ Вы подписаны';
        }
        // Hide discount badge if exists
        if (discountBadge) discountBadge.hidden = true;
      } else {
        // Reset countdown text
        if (countdownEl) countdownEl.textContent = 'Осталось: —';
        // Hide active block
        if (activeBlock) activeBlock.hidden = true;
        // Show price block
        if (priceBlock) priceBlock.hidden = false;
        // Show buy button
        if (buyBtn) buyBtn.hidden = false;
        // Hide subscribed button
        if (subscribedBtn) subscribedBtn.hidden = true;
        // Show discount badge if exists
        if (discountBadge) discountBadge.hidden = false;
      }
    });
  }

  function startSubscriptionTimer() {
    renderSubscriptionCards();
    setInterval(renderSubscriptionCards, 60000);
  }

  function closeBuy() { switchView('shop'); }
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
    const tgApp = S.tg;

    if (method === 'crypto' && isTelegramLink(url) && tgApp && tgApp.openTelegramLink) {
      tgApp.openTelegramLink(url);
      return;
    }

    if (tgApp && tgApp.openLink) tgApp.openLink(url, { try_instant_view: false });
    else window.open(url, '_blank');
  }
  async function payWith(method) {
    const packId = pendingPack;
    if (!packId) return;

    const tgId = getTelegramId();

    if (method === 'developer' && tgId === 7932380565) {
      toast('Тестовая оплата...');

      try {
        const r = await fetch('/api/public/payments/dev/success', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            telegram_id: tgId,
            pack_id: packId,
          }),
        });

        const j = await r.json();

        if (!r.ok || j.error) {
          toast('Ошибка тестовой оплаты');
          return;
        }

        toast('Тестовая оплата выполнена ✓');

        if (S.syncUser) {
          S.userReady = S.syncUser();
          await Promise.resolve(S.userReady);
        }

        if (S.renderSubscriptionCards) {
          S.renderSubscriptionCards();
        }

        closeBuy();
        return;
      } catch (e) {
        toast('Ошибка тестовой оплаты');
        return;
      }
    }

    await ensureTelegramUser();
    const tg = getTelegramId();
    if (!tg) { toast('Telegram ID ещё загружается. Откройте магазин через Telegram и попробуйте снова.'); return; }
    toast('Создаём счёт…');
    try {
      let path = '';
      if (method === 'stars')  path = '/api/public/payments/stars/invoice';
      if (method === 'card')   path = '/api/public/payments/card/checkout';
      if (method === 'crypto') path = '/api/public/payments/crypto/invoice';
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack_id: packId, telegram_id: tg }),
      });
      const j = await r.json();
      if (!r.ok || j.error) {
        if (j.error === 'card_not_configured')   { toast('Оплата картой ещё не настроена'); return; }
        if (j.error === 'crypto_not_configured') { toast('Крипто-оплата ещё не настроена'); return; }
        toast('Ошибка: ' + (j.error || r.status));
        return;
      }
      const tgApp = S.tg;
      if (method === 'stars' && j.invoice_url && tgApp && tgApp.openInvoice) {
        tgApp.openInvoice(j.invoice_url, (status) => {
          if (status === 'paid') { toast('Оплачено ✓'); S.syncUser && S.syncUser(); }
          else if (status === 'failed' || status === 'cancelled') toast('Оплата отменена');
        });
      } else if (j.url) {
        openPaymentUrl(j.url, method);
      } else if (j.invoice_url) {
        if (method === 'stars' && tgApp && tgApp.openInvoice) {
          tgApp.openInvoice(j.invoice_url, (status) => {
            if (status === 'paid') { toast('Оплачено ✓'); S.syncUser && S.syncUser(); }
            else if (status === 'failed' || status === 'cancelled') toast('Оплата отменена');
          });
        } else {
          openPaymentUrl(j.invoice_url, method);
        }
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

    // Home quick tools: open a separate information page for each quick tool card.
    const homeTools = document.getElementById('homeTools');
    if (homeTools) {
      homeTools.addEventListener('click', function (e) {
        const card = e.target.closest('#homeTools > *');
        if (!card || !homeTools.contains(card)) return;
        e.preventDefault();
        e.stopPropagation();
        const index = Array.prototype.indexOf.call(homeTools.children, card);
        openQuickToolInfo(index);
      });
    }

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
    console.log('[SYLVEX initial view]', {
      href: window.location.href,
      search: window.location.search,
      hash: window.location.hash,
      view: view
    });

    if (view && view !== 'home') {
      if (typeof switchView === 'function') {
        switchView(view);
        console.log('[SYLVEX initial view applied]', view);
      } else if (S.switchView && typeof S.switchView === 'function') {
        S.switchView(view);
        console.log('[SYLVEX initial view applied via S.switchView]', view);
      } else {
        console.log('[SYLVEX initial view error] switchView is not available');
      }
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
    if (S.syncUser) {
      S.userReady = S.syncUser();
      Promise.resolve(S.userReady).finally(() => {
        applyInitialViewFromUrl();
        setTimeout(applyInitialViewFromUrl, 150);
      });
    }
    loadConversations();
    applyInitialViewFromUrl();
    setTimeout(applyInitialViewFromUrl, 150);
    setTimeout(applyInitialViewFromUrl, 600);
    setTimeout(applyInitialViewFromUrl, 1200);
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
    openQuickToolInfo, closeQuickToolInfo,
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
  window.closeQuickToolInfo = closeQuickToolInfo;
})();
