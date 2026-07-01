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
  let activeQuickToolIndex = 0;

  // Information pages for the quick tools on the Home screen.
  // These pages are opened when the user taps a quick tool card.
  const QUICK_TOOL_INFO = [
    {
      key: 'image',
      title: 'Изображения',
      label: 'SYLVEX Image Tools',
      body: `
SYLVEX генерация изображений включает в себя несколько ИИ-инструментов для создания, редактирования, улучшения и анализа визуального контента.

В этом разделе пользователь может работать не с одной моделью, а с набором инструментов для разных задач:
• генерация изображений по тексту
• редактирование готовых фото
• улучшение качества
• изменение фона
• добавление и удаление объектов
• создание баннеров, обложек и визуальных концептов
• создание персонажей
• анализ изображений
• распознавание текста на фото
• работа с image-to-image сценариями

Откройте боковое меню, чтобы выбрать конкретный ИИ-инструмент или провайдера для изображений.
      `.trim()
    },
    {
      key: 'text',
      title: 'Текст',
      label: 'SYLVEX Text Tools',
      body: `
SYLVEX генерация текста включает в себя несколько ИИ-инструментов для написания, улучшения, перевода, анализа и структурирования текста.

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
      label: 'SYLVEX Voice Tools',
      body: `
SYLVEX генерация голоса включает в себя несколько ИИ-инструментов для озвучки, дикторской речи, рекламной подачи, эмоциональной речи и голосовых аудиофайлов.

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
      label: 'SYLVEX Video Tools',
      body: `
SYLVEX генерация видео включает в себя несколько ИИ-инструментов для создания, редактирования, оживления и продолжения видео.

В этом разделе пользователь может работать не с одной моделью, а с набором инструментов под разные задачи: text-to-video, image-to-video, video edit, remix, extend, character workflow, face tools и cinematic video.

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
      label: 'SYLVEX Music Tools',
      body: `
SYLVEX генерация музыки включает в себя несколько ИИ-инструментов для музыкальных идей, текстов песен, промптов, стилей, жанров и музыкального контента.

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
      label: 'SYLVEX Document Tools',
      body: `
SYLVEX документы включают в себя несколько ИИ-инструментов для загрузки, анализа, поиска и обработки файлов, PDF, таблиц, инструкций, договоров, отчётов и пользовательской базы знаний.

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

  const QUICK_TOOL_PROVIDER_INFO = {
    image: [
      {
        name: 'OpenAI Image',
        badge: 'Генерация · Редактирование · Vision',
        body: QUICK_TOOL_INFO[0].body
      },
      {
        name: 'Image AI Providers',
        badge: 'Дополнительные ИИ для изображений',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с изображениями.

Сюда можно добавить:
• генераторы изображений
• редакторы изображений
• инструменты улучшения фото
• image-to-image модели
• inpainting модели
• background remover
• upscale tools
• face/photo tools
• style transfer tools
• OCR и анализ изображений

Каждый провайдер может иметь отдельное описание, список функций, доступные модели, ограничения и будущий price.
        `.trim()
      }
    ],
    text: [
      {
        name: 'OpenAI Text',
        badge: 'Чат · Промпты · Тексты · JSON',
        body: QUICK_TOOL_INFO[1].body
      },
      {
        name: 'Text AI Providers',
        badge: 'Дополнительные ИИ для текста',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с текстом.

Сюда можно добавить:
• чат-модели
• reasoning-модели
• модели для копирайтинга
• модели для перевода
• модели для кода
• модели для сценариев
• модели для промптов
• модели для структурированных JSON-ответов

Каждый текстовый провайдер может иметь отдельное описание, доступные модели, сильные стороны, ограничения и будущий price.
        `.trim()
      }
    ],
    voice: [
      {
        name: 'OpenAI Voice',
        badge: 'Text-to-Speech · Voice tools',
        body: QUICK_TOOL_INFO[2].body
      },
      {
        name: 'Voice AI Providers',
        badge: 'Дополнительные ИИ для голоса',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с голосом и озвучкой.

Сюда можно добавить:
• text-to-speech провайдеры
• дикторские голоса
• рекламную озвучку
• эмоциональную озвучку
• voice style tools
• voice cloning tools
• voice changer tools
• realtime voice tools

Каждый голосовой провайдер может иметь отдельное описание, список голосов, языки, стили, ограничения и будущий price.
        `.trim()
      }
    ],
    video: [
      {
        name: 'OpenAI Sora',
        badge: 'Video generation · Edit · Remix',
        body: QUICK_TOOL_INFO[3].body
      },
      {
        name: 'Kling',
        badge: 'Video generation · Image-to-video',
        body: `
Kling — видео-инструмент для генерации роликов и работы с image-to-video сценариями.

Функционал:
• text-to-video
• image-to-video
• генерация коротких видео
• вертикальные видео
• горизонтальные видео
• cinematic-сцены
• анимационные сцены
• видео по промпту
• видео по изображению
• выбор длительности
• выбор формата
• выбор качества

Этот блок можно расширить точными моделями Kling, доступными режимами, длительностью, форматами, ограничениями и price.
        `.trim()
      },
      {
        name: 'Video AI Providers',
        badge: 'Дополнительные ИИ для видео',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с видео.

Сюда можно добавить:
• Sora
• Kling
• Runway
• Pika
• Luma
• video edit tools
• video extend tools
• video remix tools
• face swap tools
• image-to-video tools
• text-to-video tools

Каждый видео-провайдер может иметь отдельное описание, список моделей, режимы генерации, длительность, форматы, ограничения и будущий price.
        `.trim()
      }
    ],
    music: [
      {
        name: 'OpenAI Music Assistant',
        badge: 'Lyrics · Prompts · Ideas',
        body: QUICK_TOOL_INFO[4].body
      },
      {
        name: 'Music AI Providers',
        badge: 'Дополнительные ИИ для музыки',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с музыкой.

Сюда можно добавить:
• генерацию музыки
• генерацию песен
• instrumental generation
• lyrics-to-song
• text-to-music
• remix tools
• stems tools
• voice + music tools
• BPM/tempo tools
• жанры и стили

Каждый музыкальный провайдер может иметь отдельное описание, доступные режимы, жанры, длительность, ограничения и будущий price.
        `.trim()
      }
    ],
    documents: [
      {
        name: 'OpenAI Documents',
        badge: 'PDF · Files · Search · Knowledge base',
        body: QUICK_TOOL_INFO[5].body
      },
      {
        name: 'Document AI Providers',
        badge: 'Дополнительные ИИ для документов',
        body: `
Этот раздел предназначен для всех встроенных ИИ-инструментов, которые работают с файлами и документами.

Сюда можно добавить:
• PDF анализаторы
• OCR tools
• table extraction tools
• document Q&A
• knowledge base tools
• file search tools
• semantic search
• document comparison
• spreadsheet analysis
• contract/document analysis

Каждый документный провайдер может иметь отдельное описание, поддерживаемые форматы, ограничения, возможности поиска и будущий price.
        `.trim()
      }
    ]
  };

  function extraQuickToolCard(t) {
    if (typeof S.toolCard === 'function') {
      return S.toolCard(t);
    }

    return '' +
      '<div class="tool-card quick-tool-extra-card" role="button" tabindex="0">' +
        '<div class="tool-ico">' + t.icon + '</div>' +
        '<div class="tool-title">' + t.title + '</div>' +
        '<div class="tool-desc">' + t.desc + '</div>' +
      '</div>';
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
      '<div class="quick-tool-info-card quick-tool-info-main-card">' +
        '<div class="quick-tool-info-head">' +
          '<button class="quick-tool-menu-open" onclick="SYLVEX.openQuickToolProviderDrawer(event)" aria-label="Open menu">☰</button>' +
          '<div class="quick-tool-info-heading">' +
            '<div class="quick-tool-info-kicker">AI Tools</div>' +
            '<div class="quick-tool-info-title" id="quickToolInfoTitle">Инструмент</div>' +
          '</div>' +
          '<button class="quick-tool-home-btn" onclick="SYLVEX.closeQuickToolInfo()" aria-label="Home">⌂</button>' +
        '</div>' +
        '<div class="quick-tool-info-label" id="quickToolInfoLabel">SYLVEX Tools</div>' +
        '<div class="quick-tool-info-provider-badge" id="quickToolInfoProviderBadge"></div>' +
        '<div class="quick-tool-info-body" id="quickToolInfoBody"></div>' +
      '</div>' +
      '<div class="quick-tool-provider-backdrop" id="quickToolProviderBackdrop" onclick="SYLVEX.closeQuickToolProviderDrawer()"></div>' +
      '<div class="quick-tool-provider-drawer" id="quickToolProviderDrawer">' +
        '<div class="quick-tool-provider-head">' +
          '<div class="quick-tool-provider-kicker">Инструменты</div>' +
          '<button class="quick-tool-provider-close" onclick="SYLVEX.closeQuickToolProviderDrawer()">×</button>' +
        '</div>' +
        '<div class="quick-tool-provider-list" id="quickToolProviderList"></div>' +
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
      .quick-tool-info-heading {
        flex: 1;
        min-width: 0;
      }
      .quick-tool-menu-open,
      .quick-tool-home-btn {
        height: 42px;
        border: 0;
        background: transparent;
        color: #fff;
      }
      .quick-tool-menu-open {
        width: 42px;
        font-size: 25px;
        line-height: 1;
      }
      .quick-tool-home-btn {
        width: 42px;
        min-width: 42px;
        padding: 0;
        font-size: 23px;
        font-weight: 800;
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
      .quick-tool-info-main-card {
        min-height: calc(100vh - 130px);
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
      .quick-tool-info-provider-badge {
        margin-bottom: 14px;
        color: rgba(255,255,255,.62);
        font-size: 12px;
        line-height: 1.35;
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
      body.light .quick-tool-info-label {
        border-color: rgba(0,0,0,.08);
        background: rgba(255,255,255,.72);
      }
      body.light .quick-tool-info-kicker,
      body.light .quick-tool-info-title,
      body.light .quick-tool-info-label,
      body.light .quick-tool-menu-open,
      body.light .quick-tool-home-btn,
      body.light .quick-tool-info-body {
        color: #fff;
      }
      .quick-tool-provider-backdrop {
        position: fixed;
        inset: 0;
        z-index: 90;
        display: none;
        background: rgba(0,0,0,.42);
      }
      .quick-tool-provider-backdrop.show {
        display: block;
      }
      .quick-tool-provider-drawer {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        z-index: 91;
        width: 50vw;
        max-width: 260px;
        min-width: 190px;
        padding: calc(env(safe-area-inset-top, 0px) + 18px) 14px calc(env(safe-area-inset-bottom, 0px) + 18px);
        transform: translateX(-110%);
        transition: transform .22s ease;
        background: rgba(10,11,16,.82);
        border-right: 1px solid rgba(255,255,255,.12);
        box-shadow: 18px 0 60px rgba(0,0,0,.38);
        backdrop-filter: blur(20px);
      }
      .quick-tool-provider-drawer.show {
        transform: translateX(0);
      }
      .quick-tool-provider-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 16px;
      }
      .quick-tool-provider-kicker {
        color: rgba(255,255,255,.55);
        font-size: 12px;
        letter-spacing: .08em;
        text-transform: uppercase;
      }
      .quick-tool-provider-title {
        display: none;
      }
      .quick-tool-provider-close {
        width: 38px;
        height: 38px;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 14px;
        background: rgba(255,255,255,.07);
        color: #fff;
        font-size: 24px;
        line-height: 1;
      }
      .quick-tool-provider-list {
        display: grid;
        gap: 4px;
      }
      .quick-tool-provider-item {
        width: 100%;
        border: 0;
        border-radius: 0;
        padding: 9px 0;
        background: transparent;
        color: rgba(255,255,255,.72);
        text-align: left;
      }
      .quick-tool-provider-item.active {
        color: #fff;
        background: transparent;
      }
      .quick-tool-provider-item-name {
        font-size: 13px;
        font-weight: 750;
      }
      .quick-tool-provider-item-badge {
        margin-top: 3px;
        color: rgba(255,255,255,.42);
        font-size: 10px;
        line-height: 1.3;
      }
    `;
    document.head.appendChild(st);
  }

  function openQuickToolInfo(index) {
    const data = QUICK_TOOL_INFO[index];
    if (!data) return;
    activeQuickToolIndex = index;

    ensureQuickToolInfoStyles();
    const page = ensureQuickToolInfoPage();

    const title = document.getElementById('quickToolInfoTitle');
    if (title) title.textContent = data.title;

    renderQuickToolProviderList(-1);

    const label = document.getElementById('quickToolInfoLabel');
    const badge = document.getElementById('quickToolInfoProviderBadge');
    const body = document.getElementById('quickToolInfoBody');

    if (label) label.textContent = data.label || 'SYLVEX Tools';
    if (badge) badge.textContent = 'Общая информация';
    if (body) body.textContent = data.body || '';

    page.classList.add('show');
    document.body.classList.add('quick-tool-info-open');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function closeQuickToolInfo() {
    const page = document.getElementById('quickToolInfoPage');
    if (page) page.classList.remove('show');
    closeQuickToolProviderDrawer();
    document.body.classList.remove('quick-tool-info-open');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function getQuickToolProviders(index) {
    const info = QUICK_TOOL_INFO[index];
    if (!info) return [];
    return QUICK_TOOL_PROVIDER_INFO[info.key] || [{ name: info.label, badge: '', body: info.body }];
  }

  function renderQuickToolProviderList(activeProviderIndex) {
    const list = document.getElementById('quickToolProviderList');
    if (!list) return;

    const providers = getQuickToolProviders(activeQuickToolIndex);
    list.innerHTML = providers.map((p, i) => '' +
      '<button class="quick-tool-provider-item ' + (i === activeProviderIndex ? 'active' : '') + '" onclick="SYLVEX.selectQuickToolProvider(' + i + ')">' +
        '<div class="quick-tool-provider-item-name">' + S.escapeHtml(p.name || 'AI Provider') + '</div>' +
        (p.badge ? '<div class="quick-tool-provider-item-badge">' + S.escapeHtml(p.badge) + '</div>' : '') +
      '</button>'
    ).join('');
  }

  function selectQuickToolProvider(providerIndex) {
    const providers = getQuickToolProviders(activeQuickToolIndex);
    const provider = providers[providerIndex] || providers[0];
    if (!provider) return;

    const label = document.getElementById('quickToolInfoLabel');
    const badge = document.getElementById('quickToolInfoProviderBadge');
    const body = document.getElementById('quickToolInfoBody');

    if (label) label.textContent = provider.name || 'AI Provider';
    if (badge) badge.textContent = provider.badge || '';
    if (body) body.textContent = provider.body || '';

    renderQuickToolProviderList(providerIndex || 0);
    closeQuickToolProviderDrawer();
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function openQuickToolProviderDrawer(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const drawer = document.getElementById('quickToolProviderDrawer');
    const backdrop = document.getElementById('quickToolProviderBackdrop');
    if (drawer) drawer.classList.add('show');
    if (backdrop) backdrop.classList.add('show');
  }

  function closeQuickToolProviderDrawer() {
    const drawer = document.getElementById('quickToolProviderDrawer');
    const backdrop = document.getElementById('quickToolProviderBackdrop');
    if (drawer) drawer.classList.remove('show');
    if (backdrop) backdrop.classList.remove('show');
  }

  function renderDynamic() {
    const ht = document.getElementById('homeTools');
    const hh = document.getElementById('homeHist');
    const fh = document.getElementById('fullHist');
    const sg = document.getElementById('shopGrid');
    if (ht) {
      const extraTools = [
        {
          icon: '🎵',
          title: 'Музыка',
          desc: 'Тексты песен, промпты, идеи и анализ лирики',
          sub: 'Тексты песен, промпты, идеи и анализ лирики',
          text: 'Тексты песен, промпты, идеи и анализ лирики'
        },
        {
          icon: '📄',
          title: 'Документы',
          desc: 'PDF, файлы, поиск, анализ и база знаний',
          sub: 'PDF, файлы, поиск, анализ и база знаний',
          text: 'PDF, файлы, поиск, анализ и база знаний'
        },
      ];

      ht.innerHTML =
        S.toolsData.slice(0, 4).map(S.toolCard).join('') +
        extraTools.map(extraQuickToolCard).join('');
    }
    if (hh) hh.innerHTML = S.histData.slice(0, 2).map(S.histCard).join('');
    if (fh) fh.innerHTML = S.histData.map(S.histCard).join('');
    if (sg) {
      sg.innerHTML = S.shopData.map(S.shopCard).join('');
      renderSubscriptionCards();
    }
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
    sendUserEvent && sendUserEvent('button_click', 'open_shop', { view: 'shop' });
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
    sendUserEvent && sendUserEvent('button_click', 'open_buy', { pack_id: packId, price: m.price });
    switchView('pay');
    S.haptic && S.haptic.impact('light');
  }
  function setCurrentUser(user) {
    if (!user) return;
    S.user = user;
    S.currentUser = user;
    window.currentUser = user;
  }

  function parseSubscriptionDate(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function getUserSubscriptionInfo() {
    const u = S.currentUser || S.user || window.currentUser || {};

    const plan = (
      u.subscription_plan ||
      u.sub_plan ||
      u.plan ||
      u.subscription_type ||
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
    const active = (u.status === 'active' || u.subscription === 'active') && !!end && end.getTime() > Date.now();

    return { active, plan, expiresAt };
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

  function renderSubscriptionCards() {
    const info = getUserSubscriptionInfo();

    document.querySelectorAll('[data-subscription-countdown]').forEach((el) => {
      const expiresAt = el.getAttribute('data-subscription-countdown') || info.expiresAt;
      el.textContent = formatSubscriptionCountdown(expiresAt);
    });

    document.querySelectorAll('.pack.active-subscription').forEach((card) => {
      const packId = card.getAttribute('data-pack-id') || '';
      const expectedPlan = packId === 'sub_year' ? 'year' : packId === 'sub_month' ? 'month' : '';
      const isStillActive = info.active && expectedPlan && info.plan === expectedPlan;
      if (!isStillActive) renderDynamic();
    });
  }

  let subscriptionTimerId = null;
  function startSubscriptionTimer() {
    renderSubscriptionCards();
    if (subscriptionTimerId) clearInterval(subscriptionTimerId);
    subscriptionTimerId = setInterval(renderSubscriptionCards, 60000);
  }

  function refreshShopAfterUserChange(user) {
    if (user) setCurrentUser(user);
    renderDynamic();
    startSubscriptionTimer();
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

        if (j.user) {
          refreshShopAfterUserChange(j.user);
        } else if (S.syncUser) {
          S.userReady = S.syncUser();
          const syncedUser = await Promise.resolve(S.userReady);
          refreshShopAfterUserChange(syncedUser || S.user);
        } else {
          renderDynamic();
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
    sendUserEvent && sendUserEvent('payment_invoice_created', 'payment_invoice_requested', { pack_id: packId, method });
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
        tgApp.openInvoice(j.invoice_url, async (status) => {
          if (status === 'paid') {
            toast('Оплачено ✓');
            sendUserEvent && sendUserEvent('payment_success', 'stars_payment_success', { pack_id: packId, method, charge_id: j.charge_id });
            try {
              const confirmRes = await fetch('/api/public/payments/stars/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegram_id: tg, pack_id: packId, charge_id: j.charge_id }),
              });
              const confirmJson = await confirmRes.json();
              if (confirmRes.ok && confirmJson.user) {
                refreshShopAfterUserChange(confirmJson.user);
              } else if (S.syncUser) {
                S.userReady = S.syncUser();
                const syncedUser = await Promise.resolve(S.userReady);
                refreshShopAfterUserChange(syncedUser || S.user);
              }
            } catch (err) {
              console.warn('Stars confirm failed', err);
              if (S.syncUser) {
                S.userReady = S.syncUser();
                const syncedUser = await Promise.resolve(S.userReady);
                refreshShopAfterUserChange(syncedUser || S.user);
              }
            }
          } else if (status === 'failed' || status === 'cancelled') {
            sendUserEvent && sendUserEvent('payment_cancelled', 'payment_cancelled', { pack_id: packId, method, status });
            toast('Оплата отменена');
          }
        });
      } else if (j.url) {
        openPaymentUrl(j.url, method);
      } else if (j.invoice_url) {
        if (method === 'stars' && tgApp && tgApp.openInvoice) {
          tgApp.openInvoice(j.invoice_url, async (status) => {
            if (status === 'paid') {
              toast('Оплачено ✓');
              sendUserEvent && sendUserEvent('payment_success', 'stars_payment_success', { pack_id: packId, method, charge_id: j.charge_id });
              try {
                const confirmRes = await fetch('/api/public/payments/stars/confirm', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ telegram_id: tg, pack_id: packId, charge_id: j.charge_id }),
                });
                const confirmJson = await confirmRes.json();
                if (confirmRes.ok && confirmJson.user) {
                  refreshShopAfterUserChange(confirmJson.user);
                } else if (S.syncUser) {
                  S.userReady = S.syncUser();
                  const syncedUser = await Promise.resolve(S.userReady);
                  refreshShopAfterUserChange(syncedUser || S.user);
                }
              } catch (err) {
                console.warn('Stars confirm failed', err);
                if (S.syncUser) {
                  S.userReady = S.syncUser();
                  const syncedUser = await Promise.resolve(S.userReady);
                  refreshShopAfterUserChange(syncedUser || S.user);
                }
              }
            }
            else if (status === 'failed' || status === 'cancelled') {
              sendUserEvent && sendUserEvent('payment_cancelled', 'payment_cancelled', { pack_id: packId, method, status });
              toast('Оплата отменена');
            }
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
    startSubscriptionTimer();
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
    openQuickToolProviderDrawer, closeQuickToolProviderDrawer, selectQuickToolProvider,
    computePrice, updatePrice, generateNow,
    setCurrentUser, renderSubscriptionCards, startSubscriptionTimer, refreshShopAfterUserChange,
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
  window.openQuickToolProviderDrawer = openQuickToolProviderDrawer;
  window.closeQuickToolProviderDrawer = closeQuickToolProviderDrawer;
  window.selectQuickToolProvider = selectQuickToolProvider;
  window.renderSubscriptionCards = renderSubscriptionCards;
  window.startSubscriptionTimer = startSubscriptionTimer;
  window.refreshShopAfterUserChange = refreshShopAfterUserChange;
})();
