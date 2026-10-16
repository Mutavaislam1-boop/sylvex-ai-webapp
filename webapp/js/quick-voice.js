// Quick Access → Voice: dialogue builder.
// Each block is one turn of the dialogue with its own voice; the colour of a
// block belongs to its voice. The parent page (cabinet.js) owns the voice
// library, billing, generation and history; this module only talks to it
// through same-origin postMessage.
(function () {
  const PALETTE = ['#2f6fe0', '#e0782f', '#2e9b5f', '#8e44c9', '#c23d7a', '#1f9aa5', '#b8962a', '#c94444', '#4b55c9', '#6f8f2e'];
  const SPEEDS = ['0.75', '1', '1.25', '1.5', '2'];
  const MAX_CHARS = 2000;
  const MAX_VOICES = 10;

  const state = {
    root: null,
    voices: [],
    voicesLoaded: false,
    models: [{ id: 'elevenlabs_eleven_v3', label: 'ElevenLabs Eleven v3', icon: '', audioTags: [] }],
    modelId: 'elevenlabs_eleven_v3',
    blocks: [],
    selectedKey: '',
    filter: 'all',
    query: '',
    history: [],
    historyLoaded: false,
    user: null,
    job: '',
    scriptJob: '',
    fullKey: '',
    emotionKey: '',
    audioUrl: '',
    audioTitle: '',
    aiMode: false,
    speed: '1',
    seq: 0,
  };
  const ICONS = {
    swap: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.7"/><path d="M20 4v4.7h-4.7"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15.3"/><path d="M4 20v-4.7h4.7"/></svg>',
    remove: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>',
    emotion: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8.5 14.5c1.9 2 5.1 2 7 0"/><path d="M9 9.5h.01M15 9.5h.01"/></svg>',
    expand: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
    collapse: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7"/></svg>',
  };
  const DRAWER_QUERY = '(max-width:900px)';
  const colorOf = new Map();
  const preview = new Audio();

  const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const safeUrl = (value) => {
    const url = String(value || '').trim();
    if (!url) return '';
    if (url.startsWith('/') && !url.startsWith('//')) return url;
    try {
      const parsed = new URL(url, location.href);
      return parsed.protocol === 'https:' || parsed.origin === location.origin ? parsed.href : '';
    } catch (_) {
      return '';
    }
  };
  const $ = (selector) => state.root && state.root.querySelector(selector);
  const post = (data) => window.parent.postMessage(Object.assign({ source: 'sylvex-knowledge' }, data), location.origin);
  const newKey = () => 'b' + (++state.seq) + Math.random().toString(36).slice(2, 6);
  const voiceById = (id) => state.voices.find((voice) => voice.id === id) || null;
  const blockByKey = (key) => state.blocks.find((block) => block.key === key) || null;
  const model = () => state.models.find((item) => item.id === state.modelId) || state.models[0];
  const formatTime = (seconds) => {
    const value = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
    return String(Math.floor(value / 60)).padStart(2, '0') + ':' + String(value % 60).padStart(2, '0');
  };

  function colorFor(voiceId) {
    if (!voiceId) return '';
    if (!colorOf.has(voiceId)) colorOf.set(voiceId, PALETTE[colorOf.size % PALETTE.length]);
    return colorOf.get(voiceId);
  }

  function avatarMarkup(voice, name) {
    const src = voice && safeUrl(voice.avatar);
    if (src) return '<img src="' + esc(src) + '" alt="" loading="lazy">';
    return '<span>' + esc(String((voice && voice.name) || name || 'S').slice(0, 2).toUpperCase()) + '</span>';
  }

  function notice(text) {
    const box = $('#qvNotice');
    if (!box) return;
    box.textContent = text;
    box.hidden = !text;
    clearTimeout(notice.timer);
    if (text) notice.timer = setTimeout(() => { box.hidden = true; }, 4200);
  }

  // ---------------------------------------------------------------- markup

  function shell() {
    return '<div class="qv" id="qv">'
      + '<section class="qv-main">'
      + '<button type="button" class="qt-menu-btn" data-qv-history aria-label="История диалогов"><span></span><span></span><span></span></button>'
      + '<button type="button" class="qv-voices-btn" data-qv-lib-open>Голоса</button>'
      + '<div class="qv-notice" id="qvNotice" role="status" hidden></div>'
      + '<div class="qv-board" id="qvBoard"></div>'
      + '<div class="qv-bottom">'
      + '<section class="photo-generator quick-generator qv-composer">'
      + '<div class="photo-prompt-wrap qv-input"><textarea id="qvAiBrief" rows="2" maxlength="2000" disabled aria-label="Описание диалога для AI"></textarea></div>'
      + '<div class="qv-controls"><div class="qv-model" id="qvModel"></div>'
      + '<button type="button" class="qv-ai-btn" data-qv-ai aria-pressed="false" aria-label="Текст с AI"><b>✦</b><span>Текст с AI</span></button></div>'
      + '<button type="button" class="qv-add" data-qv-add><b>＋</b><span>Добавить блок</span></button>'
      + '<button type="button" class="qv-generate" data-qv-generate disabled><span>Сгенерировать</span></button>'
      + '</section>'
      + player()
      + '</div>'
      + '</section>'
      + '<aside class="qv-lib" id="qvLib" aria-label="Библиотека голосов">'
      + '<div class="qv-lib-head"><b>Голоса</b></div><button type="button" class="qv-lib-close" data-qv-lib-close aria-label="Закрыть голоса">×</button>'
      + '<label class="qv-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="qvSearch" type="search" placeholder="Поиск голосов" autocomplete="off"></label>'
      + '<div class="qv-filters" role="tablist"><button type="button" data-qv-filter="all" class="is-active">Все</button><button type="button" data-qv-filter="female">Женские</button><button type="button" data-qv-filter="male">Мужские</button></div>'
      + '<div class="qv-lib-hint" id="qvLibHint"></div>'
      + '<div class="qv-voice-list" id="qvVoiceList"></div>'
      + '</aside>'
      + '<div class="qv-lib-backdrop" data-qv-lib-close hidden></div>'
      + historyDrawer()
      + '<div class="qv-emo-menu" id="qvEmoMenu" hidden></div>'
      + '<div class="qv-full" id="qvFull" hidden></div>'
      + '</div>';
  }

  function player() {
    return '<div class="qv-player" id="qvPlayer" data-empty="1">'
      + '<button type="button" class="qv-play" data-qv-play aria-label="Воспроизвести">▶</button>'
      + '<time id="qvCurrent">00:00</time>'
      + '<input id="qvSeek" type="range" min="0" max="1000" value="0" step="1" aria-label="Позиция">'
      + '<time id="qvDuration">00:00</time>'
      + '<label class="qv-volume" aria-label="Громкость"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg><input id="qvVolume" type="range" min="0" max="1" step="0.05" value="1"></label>'
      + '<div class="qv-speed"><button type="button" class="qv-speed-btn" id="qvSpeed" data-qv-speed-open aria-haspopup="listbox" aria-label="Скорость воспроизведения">1x</button>'
      + '<div class="qv-speed-menu" id="qvSpeedMenu" role="listbox" hidden>' + SPEEDS.slice().reverse().map((speed) => '<button type="button" role="option" data-qv-speed="' + speed + '"' + (speed === '1' ? ' class="is-selected"' : '') + '>' + speed + 'x</button>').join('') + '</div></div>'
      + '<button type="button" class="qv-download" data-qv-download aria-label="Скачать"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14"/></svg></button>'
      + '<audio id="qvAudio" preload="metadata"></audio>'
      + '</div>';
  }

  function historyDrawer() {
    return '<div class="qt-backdrop" data-qv-history-close hidden></div>'
      + '<aside class="qt-drawer qv-drawer" id="qvDrawer" aria-hidden="true"><div class="qt-drawer-top"><b class="qm-drawer-title">Мои диалоги</b>'
      + '<button class="qt-collapse" type="button" data-qv-history-close aria-label="Скрыть историю">‹</button></div>'
      + '<button type="button" class="qv-new" data-qv-new>＋ Новый диалог</button>'
      + '<div class="qt-list" id="qvHistory"></div><button class="qt-user" type="button" data-qv-account id="qvUser"></button></aside>';
  }

  function renderModel() {
    const host = $('#qvModel');
    if (!host) return;
    const current = model();
    const logo = (item) => (safeUrl(item.icon) ? '<img class="qm-model-logo" src="' + esc(safeUrl(item.icon)) + '" alt="" data-fallback-hide>' : '');
    host.innerHTML = '<button type="button" class="qt-model-trigger qv-model-btn" data-qv-model-open aria-haspopup="listbox">' + logo(current) + '<b>' + esc(current.label) + '</b><i>⌄</i></button>'
      + '<div class="qv-model-menu" id="qvModelMenu" hidden>' + state.models.map((item) => '<button type="button" data-qv-model="' + esc(item.id) + '"' + (item.id === current.id ? ' class="is-selected"' : '') + '>' + logo(item) + '<span>' + esc(item.label) + '</span><i>✓</i></button>').join('') + '</div>';
  }

  function voiceMatches(voice, used) {
    if (voice.missing && !used) return false;
    const gender = String(voice.gender || '').toLowerCase();
    if (state.filter === 'female' && gender !== 'female') return false;
    if (state.filter === 'male' && gender !== 'male') return false;
    const query = state.query.trim().toLowerCase();
    if (!query) return true;
    return [voice.name, voice.accent, voice.gender].some((value) => String(value || '').toLowerCase().includes(query));
  }

  function usedVoiceIds() {
    return Array.from(new Set(state.blocks.map((block) => block.voiceId).filter(Boolean)));
  }

  function voiceRow(voice, used) {
    return '<div class="qv-voice' + (used ? ' is-used' : '') + '"' + (used ? ' style="--qv-c:' + colorFor(voice.id) + '"' : '') + (voice.missing ? '' : ' draggable="true"') + ' data-qv-voice="' + esc(voice.id) + '" role="button" tabindex="0">'
      + '<i>' + avatarMarkup(voice) + '</i><span><b>' + esc(voice.name) + '</b>' + (voice.accent ? '<small>' + esc(voice.accent) + '</small>' : '') + '</span>'
      + (voice.previewUrl ? '<button type="button" class="qv-voice-play" data-qv-preview="' + esc(voice.id) + '" aria-label="Прослушать ' + esc(voice.name) + '">▶</button>' : '')
      + '</div>';
  }

  function renderVoices() {
    const host = $('#qvVoiceList');
    if (!host) return;
    const usedIds = usedVoiceIds();
    const used = usedIds.map(voiceById).filter((voice) => voice && voiceMatches(voice, true));
    const rest = state.voices.filter((voice) => !usedIds.includes(voice.id) && voiceMatches(voice));
    if (!state.voicesLoaded) host.innerHTML = '<p class="qv-muted">Загрузка голосов…</p>';
    else if (!used.length && !rest.length) host.innerHTML = '<p class="qv-muted">Голоса не найдены</p>';
    else host.innerHTML = used.map((voice) => voiceRow(voice, true)).join('')
      + (used.length && rest.length ? '<hr class="qv-voice-sep">' : '')
      + rest.map((voice) => voiceRow(voice, false)).join('');
    renderLibHint();
  }

  function renderLibHint() {
    const hint = $('#qvLibHint');
    if (!hint) return;
    const block = blockByKey(state.selectedKey);
    hint.textContent = block ? 'Выберите голос для реплики ' + (state.blocks.indexOf(block) + 1) : 'Перетащите голос на блок или выберите блок и нажмите на голос';
    hint.classList.toggle('is-active', !!block);
  }

  function blockMarkup(block, index) {
    const voice = voiceById(block.voiceId);
    const filled = !!block.voiceId;
    const color = filled ? colorFor(block.voiceId) : '';
    const name = filled ? ((voice && voice.name) || block.voiceName || 'Голос') : '';
    const tags = (model().audioTags || []).length;
    return '<article class="qv-block' + (filled ? ' is-filled' : ' is-empty') + (block.key === state.selectedKey ? ' is-selected' : '') + (block.invalid ? ' is-invalid' : '') + (index % 2 ? ' is-right' : '') + '" data-qv-block="' + esc(block.key) + '"' + (color ? ' style="--qv-c:' + color + '"' : '') + '>'
      + '<button type="button" class="qv-remove" data-qv-delete="' + esc(block.key) + '" aria-label="Удалить блок">' + ICONS.remove + '</button>'
      + '<header>'
      + voiceArea(block, voice, name)
      + '<span class="qv-spacer"></span>'
      + (tags ? '<button type="button" class="qv-ic" data-qv-emotions="' + esc(block.key) + '" aria-label="Эмоции">' + ICONS.emotion + '</button>' : '')
      + '<button type="button" class="qv-ic" data-qv-expand="' + esc(block.key) + '" aria-label="Развернуть на весь экран">' + ICONS.expand + '</button>'
      + '</header>'
      + '<textarea data-qv-text="' + esc(block.key) + '" rows="3" placeholder="Текст реплики…" aria-label="Текст реплики ' + (index + 1) + '">' + esc(block.text) + '</textarea>'
      + '</article>';
  }

  function voiceArea(block, voice, name) {
    if (!block.voiceId) {
      return '<button type="button" class="qv-slot qv-pick" data-qv-pick="' + esc(block.key) + '"><i class="qv-plus">+</i><b>Выбрать голос</b></button>'
        + (block.hint ? '<span class="qv-hint">' + esc(block.hint) + '</span>' : '');
    }
    return '<span class="qv-slot"><i>' + avatarMarkup(voice, name) + '</i><b>' + esc(name) + '</b></span>'
      + (voice && voice.previewUrl ? '<button type="button" class="qv-round" data-qv-preview="' + esc(block.voiceId) + '" aria-label="Прослушать голос">▶</button>' : '')
      + '<button type="button" class="qv-ic qv-swap" data-qv-swap="' + esc(block.key) + '" aria-label="Сменить голос">' + ICONS.swap + '</button>';
  }

  function renderBoard() {
    const board = $('#qvBoard');
    if (!board) return;
    if (!state.blocks.length) {
      board.innerHTML = '<div class="qv-empty"><b>Пустой диалог</b><span>Нажмите «Добавить блок», чтобы написать первую реплику, или создайте текст с AI.</span></div>';
    } else {
      board.innerHTML = state.blocks.map(blockMarkup).join('');
      board.querySelectorAll('textarea[data-qv-text]').forEach(autoGrow);
    }
    if (state.blocks.length && state.aiMode) setAiMode(false);
    renderCounter();
    renderVoices();
  }

  // Generate is muted until it can actually run: a description in AI Text
  // mode, otherwise at least one block with a voice and text.
  function canGenerate() {
    if (state.job || state.scriptJob) return false;
    if (state.aiMode) return !!(($('#qvAiBrief') || {}).value || '').trim();
    return state.blocks.some((block) => block.voiceId && block.text.trim());
  }

  function renderCounter() {
    const chars = state.blocks.reduce((sum, block) => sum + block.text.trim().length, 0);
    const button = $('[data-qv-generate]');
    if (button) {
      button.disabled = !canGenerate();
      button.classList.toggle('is-busy', !!(state.job || state.scriptJob));
      button.querySelector('span').textContent = state.job ? 'Озвучиваем…' : state.scriptJob ? 'Пишем диалог…' : 'Сгенерировать';
      button.title = state.aiMode ? '' : chars + ' / ' + MAX_CHARS + ' символов';
    }
  }

  function setAiMode(on) {
    state.aiMode = !!on;
    const button = $('[data-qv-ai]');
    const field = $('#qvAiBrief');
    if (button) { button.classList.toggle('is-active', state.aiMode); button.setAttribute('aria-pressed', state.aiMode ? 'true' : 'false'); }
    if (field) {
      field.disabled = !state.aiMode;
      field.placeholder = state.aiMode ? 'Опишите диалог для AI' : '';
      if (state.aiMode) field.focus();
    }
    renderCounter();
  }

  function toggleAiMode() {
    if (state.scriptJob) return;
    if (!state.aiMode && state.blocks.length) {
      notice('Сначала очистите рабочую область: AI Text работает только с пустым диалогом');
      return;
    }
    setAiMode(!state.aiMode);
  }

  function renderHistory() {
    const host = $('#qvHistory');
    if (host) {
      if (!state.historyLoaded) host.innerHTML = '<p class="qv-muted">Загрузка…</p>';
      else if (!state.history.length) host.innerHTML = '<p class="qv-muted">Здесь появятся озвученные диалоги</p>';
      else host.innerHTML = state.history.map((item, index) => '<button type="button" class="qv-history-item" data-qv-open="' + index + '"><b>' + esc(item.title || 'Диалог') + '</b><small>' + item.blocks.length + ' ' + plural(item.blocks.length) + (item.createdAt ? ' · ' + esc(formatDate(item.createdAt)) : '') + '</small></button>').join('');
    }
    const card = $('#qvUser');
    const user = state.user;
    if (card && user) {
      const avatar = safeUrl(user.avatar);
      card.innerHTML = '<i>' + (avatar ? '<img src="' + esc(avatar) + '" alt="">' : esc(user.initials || 'S')) + '</i><span><b>' + esc(user.name) + '</b><small>' + esc(user.handle) + '</small></span>' + (user.balance !== null && user.balance !== undefined ? '<em>' + Number(user.balance).toLocaleString() + ' ⚡️</em>' : '');
    }
  }

  function plural(count) {
    const mod10 = count % 10, mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return 'реплика';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'реплики';
    return 'реплик';
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  }

  function autoGrow(field) {
    field.style.height = 'auto';
    field.style.height = Math.min(field.scrollHeight + 2, 320) + 'px';
  }

  // ---------------------------------------------------------------- blocks

  function addBlock(fields) {
    const block = Object.assign({ key: newKey(), voiceId: '', voiceName: '', text: '', hint: '', invalid: false }, fields || {});
    state.blocks.push(block);
    return block;
  }

  function createBlockWithVoice(voiceId) {
    const voice = voiceById(voiceId);
    if (!voice) return;
    const used = usedVoiceIds();
    if (!used.includes(voice.id) && used.length >= MAX_VOICES) {
      notice('В одном диалоге можно использовать до ' + MAX_VOICES + ' голосов');
      return;
    }
    colorFor(voice.id);
    const block = addBlock({ voiceId: voice.id, voiceName: voice.name });
    state.selectedKey = block.key;
    renderBoard();
    if (window.matchMedia(DRAWER_QUERY).matches) toggleLibrary(false);
    const node = state.root.querySelector('[data-qv-block="' + CSS.escape(block.key) + '"]');
    if (node) {
      node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      const field = node.querySelector('textarea');
      if (field && !window.matchMedia(DRAWER_QUERY).matches) field.focus({ preventScroll: true });
    }
  }

  function selectBlock(key, openLibrary) {
    state.selectedKey = key;
    state.root.querySelectorAll('.qv-block').forEach((node) => node.classList.toggle('is-selected', node.dataset.qvBlock === key));
    renderLibHint();
    if (openLibrary) toggleLibrary(true);
  }

  function assignVoice(key, voiceId) {
    const block = blockByKey(key);
    const voice = voiceById(voiceId);
    if (!block || !voice) return;
    const others = new Set(state.blocks.filter((item) => item !== block && item.voiceId).map((item) => item.voiceId));
    if (!others.has(voice.id) && others.size >= MAX_VOICES) {
      notice('В одном диалоге можно использовать до ' + MAX_VOICES + ' голосов');
      return;
    }
    block.voiceId = voice.id;
    block.voiceName = voice.name;
    block.invalid = false;
    colorFor(voice.id);
    // Continue with the next turn that still has no voice.
    const next = state.blocks.find((item) => !item.voiceId);
    state.selectedKey = next ? next.key : '';
    renderBoard();
    if (state.fullKey === key) renderFull();
    if (!next) toggleLibrary(false);
  }

  function unassignVoice(key) {
    const block = blockByKey(key);
    if (!block) return;
    block.voiceId = '';
    block.voiceName = '';
    state.selectedKey = key;
    renderBoard();
    if (state.fullKey === key) renderFull();
  }

  function deleteBlock(key) {
    state.blocks = state.blocks.filter((block) => block.key !== key);
    if (state.selectedKey === key) state.selectedKey = '';
    renderBoard();
  }

  function insertTag(field, tag) {
    if (!field) return;
    const start = Number.isFinite(field.selectionStart) ? field.selectionStart : field.value.length;
    const end = Number.isFinite(field.selectionEnd) ? field.selectionEnd : start;
    const before = field.value.slice(0, start);
    // The tag always ends with one space and the caret goes after it, so the
    // user keeps typing the words the emotion applies to.
    const after = field.value.slice(end).replace(/^[ \t]/, '');
    const token = (before && !/\s$/.test(before) ? ' ' : '') + '[' + tag + '] ';
    field.value = before + token + after;
    const caret = (before + token).length;
    field.focus();
    field.setSelectionRange(caret, caret);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function openEmotions(key, anchor) {
    const menu = $('#qvEmoMenu');
    const tags = model().audioTags || [];
    if (!menu || !tags.length) return;
    if (!menu.hidden && state.emotionKey === key) { closeEmotions(); return; }
    state.emotionKey = key;
    menu.innerHTML = '<small>Вставить в позицию курсора</small>' + tags.map(([tag, label]) => '<button type="button" data-qv-tag="' + esc(tag) + '"><b>[' + esc(tag) + ']</b><span>' + esc(label || tag) + '</span></button>').join('');
    menu.hidden = false;
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(260, window.innerWidth - 24);
    menu.style.width = width + 'px';
    menu.style.left = Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12)) + 'px';
    const below = rect.bottom + 6;
    const height = Math.min(menu.scrollHeight, 320);
    menu.style.top = (below + height > window.innerHeight - 12 ? Math.max(12, rect.top - height - 6) : below) + 'px';
  }

  function closeEmotions() {
    const menu = $('#qvEmoMenu');
    if (menu) menu.hidden = true;
    state.emotionKey = '';
  }

  function emotionTarget() {
    if (state.fullKey && state.emotionKey === state.fullKey) return $('#qvFullText');
    return state.root.querySelector('textarea[data-qv-text="' + CSS.escape(state.emotionKey) + '"]');
  }

  // ------------------------------------------------------------ fullscreen

  function renderFull() {
    const host = $('#qvFull');
    const block = blockByKey(state.fullKey);
    if (!host) return;
    if (!block) { host.hidden = true; host.innerHTML = ''; return; }
    const voice = voiceById(block.voiceId);
    const color = block.voiceId ? colorFor(block.voiceId) : '';
    const name = block.voiceId ? ((voice && voice.name) || block.voiceName || 'Голос') : '';
    const index = state.blocks.indexOf(block) + 1;
    const keep = $('#qvFullText');
    const selection = keep ? [keep.selectionStart, keep.selectionEnd] : null;
    host.innerHTML = '<div class="qv-full-card' + (block.voiceId ? ' is-filled' : ' is-empty') + '"' + (color ? ' style="--qv-c:' + color + '"' : '') + '>'
      + '<header>'
      + voiceArea(block, voice, name)
      + '<small class="qv-full-index">Реплика ' + index + '</small><span class="qv-spacer"></span>'
      + ((model().audioTags || []).length ? '<button type="button" class="qv-ic" data-qv-emotions="' + esc(block.key) + '" aria-label="Эмоции">' + ICONS.emotion + '</button>' : '')
      + '<button type="button" class="qv-ic" data-qv-full-close aria-label="Свернуть">' + ICONS.collapse + '</button>'
      + '</header>'
      + '<textarea id="qvFullText" data-qv-full-text="' + esc(block.key) + '" placeholder="Текст реплики…" aria-label="Текст реплики ' + index + '">' + esc(block.text) + '</textarea>'
      + '</div>';
    host.hidden = false;
    const field = $('#qvFullText');
    if (field && selection) field.setSelectionRange(selection[0], selection[1]);
  }

  function openFull(key) {
    state.fullKey = key;
    renderFull();
    const field = $('#qvFullText');
    if (field) { field.focus(); field.setSelectionRange(field.value.length, field.value.length); }
  }

  function closeFull() {
    state.fullKey = '';
    closeEmotions();
    renderFull();
    renderBoard();
  }

  // ------------------------------------------------------------- library

  function toggleLibrary(open) {
    const lib = $('#qvLib');
    const backdrop = state.root.querySelector('.qv-lib-backdrop');
    if (!lib) return;
    const drawer = window.matchMedia(DRAWER_QUERY).matches;
    const next = !!open && drawer;
    if (lib.classList.contains('open') === next && !(!next && state.libraryCovered)) return;
    lib.classList.toggle('open', next);
    if (backdrop) backdrop.hidden = !next;
    // On a phone the library covers the tool, so the tool's own close
    // button goes under it and the library's × is the only one visible.
    state.libraryCovered = next;
    post({ action: 'quick-voice-library', open: next });
  }

  function toggleHistory(open) {
    const drawer = $('#qvDrawer');
    const backdrop = state.root.querySelector('[data-qv-history-close].qt-backdrop');
    if (!drawer) return;
    drawer.classList.toggle('open', !!open);
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (backdrop) backdrop.hidden = !open;
    if (open && !state.historyLoaded) post({ action: 'voice-history-request' });
  }

  function playPreview(voiceId, button) {
    const voice = voiceById(voiceId);
    const src = voice && safeUrl(voice.previewUrl);
    if (!src) return;
    state.root.querySelectorAll('[data-qv-preview].is-playing').forEach((node) => { node.classList.remove('is-playing'); node.textContent = '▶'; });
    if (preview.dataset.voice === voiceId && !preview.paused) { preview.pause(); return; }
    preview.src = src;
    preview.dataset.voice = voiceId;
    const main = $('#qvAudio');
    if (main && !main.paused) main.pause();
    preview.play().then(() => { if (button) { button.classList.add('is-playing'); button.textContent = '❚❚'; } }).catch(() => {});
  }

  // ------------------------------------------------------------- generate

  function generate() {
    if (state.job) return;
    if (!state.blocks.length) { notice('Добавьте хотя бы один блок диалога'); return; }
    let firstInvalid = null;
    state.blocks.forEach((block) => {
      block.invalid = !block.voiceId || !block.text.trim();
      if (block.invalid && !firstInvalid) firstInvalid = block;
    });
    if (firstInvalid) {
      renderBoard();
      const node = state.root.querySelector('[data-qv-block="' + CSS.escape(firstInvalid.key) + '"]');
      if (node) node.scrollIntoView({ block: 'center', behavior: 'smooth' });
      notice(!firstInvalid.voiceId ? 'Назначьте голос каждой реплике' : 'Заполните текст каждой реплики');
      return;
    }
    const chars = state.blocks.reduce((sum, block) => sum + block.text.trim().length, 0);
    if (chars > MAX_CHARS) { notice('Диалог длиннее ' + MAX_CHARS + ' символов (' + chars + '). Сократите текст'); return; }
    if (new Set(state.blocks.map((block) => block.voiceId)).size > MAX_VOICES) { notice('В одном диалоге можно использовать до ' + MAX_VOICES + ' голосов'); return; }
    state.job = 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    renderCounter();
    setPlayerLoading(true);
    post({
      action: 'quick-voice-generate',
      clientId: state.job,
      model: model().id,
      blocks: state.blocks.map((block) => ({ voiceId: block.voiceId, voiceName: block.voiceName, text: block.text.trim() })),
    });
  }

  function setPlayerLoading(loading) {
    const playerNode = $('#qvPlayer');
    if (playerNode) playerNode.classList.toggle('is-loading', !!loading);
  }

  function loadAudio(url, title, autoplay) {
    const audio = $('#qvAudio');
    const src = safeUrl(url);
    if (!audio || !src) return;
    preview.pause();
    state.audioUrl = src;
    state.audioTitle = title || 'Диалог';
    audio.src = src;
    audio.playbackRate = Number(state.speed) || 1;
    const playerNode = $('#qvPlayer');
    if (playerNode) playerNode.dataset.empty = '0';
    setPlayerLoading(false);
    if (autoplay) audio.play().catch(() => {});
  }

  function dialogueTitle(blocks) {
    const first = (blocks.find((block) => block.text.trim()) || {}).text || 'Диалог';
    return first.replace(/\[[^\]]{1,40}\]\s*/g, '').trim().slice(0, 60) || 'Диалог';
  }

  // ------------------------------------------------------------ AI script

  function runScript() {
    const brief = ($('#qvAiBrief') || {}).value || '';
    if (!state.aiMode || !brief.trim() || state.scriptJob) return;
    if (state.blocks.length) { notice('Сначала очистите рабочую область: AI Text работает только с пустым диалогом'); return; }
    state.scriptJob = 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    setScriptBusy(true);
    post({ action: 'quick-voice-script', clientId: state.scriptJob, brief: brief.trim() });
  }

  function setScriptBusy(busy) {
    const button = $('[data-qv-ai]');
    if (button) { button.disabled = busy; button.classList.toggle('is-busy', busy); }
    renderCounter();
  }

  function finishScript(ok, blocks, message) {
    state.scriptJob = '';
    setScriptBusy(false);
    if (!ok) { notice(message || 'Не удалось создать диалог'); return; }
    blocks.forEach((item) => addBlock({ text: String(item.text || ''), hint: String(item.speaker || '').slice(0, 40) }));
    state.selectedKey = (state.blocks.find((block) => !block.voiceId) || {}).key || '';
    const field = $('#qvAiBrief');
    if (field) field.value = '';
    renderBoard();
    notice('Диалог готов. Назначьте голос каждой реплике');
  }

  // -------------------------------------------------------------- events

  function bind() {
    const root = state.root;
    root.addEventListener('click', (event) => {
      const target = event.target;
      const menu = $('#qvModelMenu');
      if (menu && !menu.hidden && !target.closest('.qv-model')) menu.hidden = true;
      const speedMenu = $('#qvSpeedMenu');
      if (speedMenu && !speedMenu.hidden && !target.closest('.qv-speed')) speedMenu.hidden = true;
      if (!target.closest('#qvEmoMenu') && !target.closest('[data-qv-emotions]')) closeEmotions();

      const previewButton = target.closest('[data-qv-preview]');
      if (previewButton) { event.stopPropagation(); playPreview(previewButton.dataset.qvPreview, previewButton); return; }
      const tag = target.closest('[data-qv-tag]');
      if (tag) { insertTag(emotionTarget(), tag.dataset.qvTag); closeEmotions(); return; }
      const emotions = target.closest('[data-qv-emotions]');
      if (emotions) { openEmotions(emotions.dataset.qvEmotions, emotions); return; }
      const voiceRow = target.closest('[data-qv-voice]');
      if (voiceRow) {
        // One click assigns the voice to the selected block, a double click
        // creates a new block with this voice; the single click waits a
        // moment so a double click never does both.
        const voiceId = voiceRow.dataset.qvVoice;
        clearTimeout(state.voiceClickTimer);
        if (event.detail >= 2) { createBlockWithVoice(voiceId); return; }
        state.voiceClickTimer = setTimeout(() => {
          const key = state.fullKey || state.selectedKey;
          if (!key || !blockByKey(key)) { notice('Выберите блок, перетащите голос на рабочую область или нажмите на голос дважды'); return; }
          assignVoice(key, voiceId);
        }, 260);
        return;
      }
      if (target.closest('[data-qv-add]')) {
        const block = addBlock();
        state.selectedKey = block.key;
        renderBoard();
        const node = root.querySelector('[data-qv-block="' + CSS.escape(block.key) + '"]');
        if (node) node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        return;
      }
      const pick = target.closest('[data-qv-pick]');
      if (pick) { selectBlock(pick.dataset.qvPick, true); return; }
      const swap = target.closest('[data-qv-swap]');
      if (swap) { unassignVoice(swap.dataset.qvSwap); selectBlock(swap.dataset.qvSwap, true); return; }
      const remove = target.closest('[data-qv-delete]');
      if (remove) { deleteBlock(remove.dataset.qvDelete); return; }
      const expand = target.closest('[data-qv-expand]');
      if (expand) { openFull(expand.dataset.qvExpand); return; }
      if (target.closest('[data-qv-full-close]')) { closeFull(); return; }
      const block = target.closest('[data-qv-block]');
      if (block && !target.closest('button')) { selectBlock(block.dataset.qvBlock, false); }

      if (target.closest('[data-qv-model-open]')) { if (menu) menu.hidden = !menu.hidden; return; }
      const modelChoice = target.closest('[data-qv-model]');
      if (modelChoice) { state.modelId = modelChoice.dataset.qvModel; renderModel(); renderBoard(); return; }
      if (target.closest('[data-qv-generate]')) { if (state.aiMode) runScript(); else generate(); return; }
      if (target.closest('[data-qv-ai]')) { toggleAiMode(); return; }
      if (target.closest('[data-qv-speed-open]')) { if (speedMenu) speedMenu.hidden = !speedMenu.hidden; return; }
      const speedChoice = target.closest('[data-qv-speed]');
      if (speedChoice) {
        state.speed = speedChoice.dataset.qvSpeed;
        const audio = $('#qvAudio');
        if (audio) audio.playbackRate = Number(state.speed) || 1;
        $('#qvSpeed').textContent = state.speed + 'x';
        root.querySelectorAll('[data-qv-speed]').forEach((node) => node.classList.toggle('is-selected', node === speedChoice));
        speedMenu.hidden = true;
        return;
      }
      const filter = target.closest('[data-qv-filter]');
      if (filter) {
        state.filter = filter.dataset.qvFilter;
        root.querySelectorAll('[data-qv-filter]').forEach((node) => node.classList.toggle('is-active', node === filter));
        renderVoices();
        return;
      }
      if (target.closest('[data-qv-lib-open]')) { toggleLibrary(true); return; }
      if (target.closest('[data-qv-lib-close]')) { toggleLibrary(false); return; }
      if (target.closest('[data-qv-history]')) { toggleHistory(true); return; }
      if (target.closest('[data-qv-history-close]')) { toggleHistory(false); return; }
      if (target.closest('[data-qv-account]')) { post({ action: 'quick-text-account' }); return; }
      if (target.closest('[data-qv-new]')) {
        state.blocks = [];
        state.selectedKey = '';
        renderBoard();
        toggleHistory(false);
        return;
      }
      const open = target.closest('[data-qv-open]');
      if (open) { restore(state.history[Number(open.dataset.qvOpen)]); toggleHistory(false); return; }
      if (target.closest('[data-qv-play]')) {
        const audio = $('#qvAudio');
        if (!audio || !audio.src) { notice('Сначала озвучьте диалог'); return; }
        if (audio.paused) { preview.pause(); audio.play().catch(() => {}); } else audio.pause();
        return;
      }
      if (target.closest('[data-qv-download]')) {
        if (!state.audioUrl) { notice('Сначала озвучьте диалог'); return; }
        post({ action: 'quick-voice-download', url: state.audioUrl, title: state.audioTitle || 'sylvex-dialogue' });
      }
    });

    root.addEventListener('input', (event) => {
      const field = event.target;
      if (field.dataset && field.dataset.qvText) {
        const block = blockByKey(field.dataset.qvText);
        if (block) { block.text = field.value; if (block.invalid && block.text.trim() && block.voiceId) { block.invalid = false; field.closest('.qv-block').classList.remove('is-invalid'); } }
        autoGrow(field);
        renderCounter();
      } else if (field.dataset && field.dataset.qvFullText) {
        const block = blockByKey(field.dataset.qvFullText);
        if (block) block.text = field.value;
      } else if (field.id === 'qvAiBrief') {
        renderCounter();
      } else if (field.id === 'qvSearch') {
        state.query = field.value;
        renderVoices();
      } else if (field.id === 'qvSeek') {
        const audio = $('#qvAudio');
        if (audio && audio.duration) audio.currentTime = Number(field.value) / 1000 * audio.duration;
      } else if (field.id === 'qvVolume') {
        const audio = $('#qvAudio');
        if (audio) audio.volume = Number(field.value);
      }
    });

    root.addEventListener('focusin', (event) => {
      const field = event.target;
      if (field.dataset && field.dataset.qvText) selectBlock(field.dataset.qvText, false);
    });

    root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (!($('#qvEmoMenu') || {}).hidden) { closeEmotions(); return; }
        if (state.fullKey) { closeFull(); return; }
        toggleLibrary(false);
        toggleHistory(false);
      }
      const voiceRow = event.target.closest && event.target.closest('[data-qv-voice]');
      if (voiceRow && (event.key === 'Enter' || event.key === ' ') && !event.target.closest('button')) {
        event.preventDefault();
        voiceRow.click();
      }
    });

    // Drag a voice from the library onto a block.
    root.addEventListener('dragstart', (event) => {
      const row = event.target.closest && event.target.closest('[data-qv-voice]');
      if (!row || !event.dataTransfer) return;
      event.dataTransfer.setData('text/plain', 'sylvex-voice:' + row.dataset.qvVoice);
      event.dataTransfer.effectAllowed = 'copy';
      root.classList.add('qv-dragging');
    });
    root.addEventListener('dragend', () => {
      root.classList.remove('qv-dragging');
      root.querySelectorAll('.is-drop').forEach((node) => node.classList.remove('is-drop'));
    });
    // A voice dropped on a block assigns it; dropped anywhere else on the
    // workspace it creates a new block with that voice.
    root.addEventListener('dragover', (event) => {
      const block = event.target.closest && event.target.closest('[data-qv-block], .qv-full-card, #qvBoard');
      if (!block) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
      root.querySelectorAll('.is-drop').forEach((node) => { if (node !== block) node.classList.remove('is-drop'); });
      block.classList.add('is-drop');
    });
    root.addEventListener('drop', (event) => {
      const block = event.target.closest && event.target.closest('[data-qv-block], .qv-full-card, #qvBoard');
      const payload = event.dataTransfer ? event.dataTransfer.getData('text/plain') : '';
      root.classList.remove('qv-dragging');
      root.querySelectorAll('.is-drop').forEach((node) => node.classList.remove('is-drop'));
      if (!block || !payload.startsWith('sylvex-voice:')) return;
      event.preventDefault();
      const voiceId = payload.slice('sylvex-voice:'.length);
      if (block.id === 'qvBoard') { createBlockWithVoice(voiceId); return; }
      assignVoice(block.dataset.qvBlock || state.fullKey, voiceId);
    });

    // Fall back to the initials when a voice or model picture fails to load.
    root.addEventListener('error', (event) => {
      const image = event.target;
      if (!(image instanceof HTMLImageElement)) return;
      if (image.hasAttribute('data-fallback-hide')) { image.remove(); return; }
      const slot = image.parentElement;
      if (slot) slot.innerHTML = '<span>' + esc(((slot.closest('[data-qv-voice]') || slot.closest('.qv-slot') || {}).textContent || 'S').trim().slice(0, 2).toUpperCase()) + '</span>';
    }, true);

    const audio = $('#qvAudio');
    const playButton = $('[data-qv-play]');
    const updateTime = () => {
      const current = $('#qvCurrent');
      const duration = $('#qvDuration');
      const seek = $('#qvSeek');
      if (current) current.textContent = formatTime(audio.currentTime);
      if (duration) duration.textContent = formatTime(audio.duration);
      if (seek) seek.style.setProperty('--qv-progress', (audio.duration ? audio.currentTime / audio.duration * 100 : 0) + '%');
      if (seek && audio.duration) seek.value = String(Math.round(audio.currentTime / audio.duration * 1000));
    };
    audio.addEventListener('timeupdate', updateTime);
    audio.addEventListener('loadedmetadata', updateTime);
    audio.addEventListener('play', () => { playButton.textContent = '❚❚'; playButton.setAttribute('aria-label', 'Пауза'); });
    audio.addEventListener('pause', () => { playButton.textContent = '▶'; playButton.setAttribute('aria-label', 'Воспроизвести'); });
    audio.addEventListener('ended', () => { playButton.textContent = '▶'; });
    preview.addEventListener('ended', () => state.root.querySelectorAll('[data-qv-preview].is-playing').forEach((node) => { node.classList.remove('is-playing'); node.textContent = '▶'; }));
    preview.addEventListener('pause', () => state.root.querySelectorAll('[data-qv-preview].is-playing').forEach((node) => { node.classList.remove('is-playing'); node.textContent = '▶'; }));
  }

  function restore(item) {
    if (!item) return;
    colorOf.clear();
    state.blocks = [];
    item.blocks.forEach((block) => {
      const added = addBlock({ voiceId: block.voiceId, voiceName: block.voiceName, text: block.text });
      if (added.voiceId) colorFor(added.voiceId);
      if (added.voiceId && !voiceById(added.voiceId)) {
        // A voice no longer in the library still shows by its saved name.
        state.voices.push({ id: added.voiceId, name: added.voiceName || 'Голос', avatar: '', previewUrl: '', gender: '', accent: '', missing: true });
      }
    });
    state.selectedKey = '';
    if (item.model && state.models.some((entry) => entry.id === item.model)) state.modelId = item.model;
    renderModel();
    renderBoard();
    renderVoices();
    loadAudio(item.audioUrl, item.title, false);
  }

  // ---------------------------------------------------------------- API

  function handle(message) {
    if (!state.root) return;
    if (message.action === 'voice-library') {
      const voices = (Array.isArray(message.voices) ? message.voices : [])
        .filter((voice) => voice && voice.id)
        .map((voice) => ({ id: String(voice.id), name: String(voice.name || 'Voice'), avatar: String(voice.avatar || ''), previewUrl: String(voice.previewUrl || ''), gender: String(voice.gender || '').toLowerCase(), accent: String(voice.accent || '') }));
      const missing = state.voices.filter((voice) => voice.missing && !voices.some((item) => item.id === voice.id));
      state.voices = voices.concat(missing);
      state.voicesLoaded = true;
      if (Array.isArray(message.models) && message.models.length) {
        state.models = message.models.map((item) => ({ id: String(item.id), label: String(item.label || item.id), icon: String(item.icon || ''), audioTags: Array.isArray(item.audioTags) ? item.audioTags.filter((tag) => Array.isArray(tag) && /^[a-z][a-z ]{0,30}$/.test(String(tag[0]))).map((tag) => [String(tag[0]), String(tag[1] || tag[0])]) : [] }));
        if (!state.models.some((item) => item.id === state.modelId)) state.modelId = state.models[0].id;
      }
      if (message.user) state.user = message.user;
      renderModel();
      renderVoices();
      renderBoard();
      renderHistory();
      return;
    }
    if (message.action === 'voice-history') {
      state.history = (Array.isArray(message.items) ? message.items : []).filter((item) => item && Array.isArray(item.blocks) && item.blocks.length);
      state.historyLoaded = true;
      if (message.user) state.user = message.user;
      renderHistory();
      return;
    }
    if (message.action === 'quick-voice-result' && message.clientId === state.job) {
      state.job = '';
      renderCounter();
      loadAudio(message.audioUrl, dialogueTitle(state.blocks), true);
      notice('Диалог озвучен');
      return;
    }
    if (message.action === 'quick-voice-error' && message.clientId === state.job) {
      state.job = '';
      renderCounter();
      setPlayerLoading(false);
      notice(String(message.message || 'Не удалось озвучить диалог'));
      return;
    }
    if (message.action === 'quick-voice-script-result' && message.clientId === state.scriptJob) {
      finishScript(true, Array.isArray(message.blocks) ? message.blocks : []);
      return;
    }
    if (message.action === 'quick-voice-script-error' && message.clientId === state.scriptJob) {
      finishScript(false, [], String(message.message || ''));
    }
  }

  function mount(root) {
    state.root = root;
    root.innerHTML = shell();
    renderModel();
    renderVoices();
    renderBoard();
    renderHistory();
    bind();
    post({ action: 'voice-library-request' });
  }

  window.SylvexQuickVoice = { mount, handle };
})();
