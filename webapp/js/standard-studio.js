/* SYLVEX Pro Studio — mobile "Standard" interface.
   One file for the Mini App and the website - keep it byte-identical in
   sylvex-ai-webapp/webapp/js/standard-studio.js and
   sylvex-website/studio/js/standard-studio.js.

   On phones (≤767px) Pro Studio opens in Standard by default; "Pro" is the
   existing mobile interface, unchanged. Standard has its own header, mode
   row, chips, bottom bar, "Параметры" panel and "+" sheet, and it is only a
   face: every value it shows is read from Pro Studio, every button runs the
   existing Pro Studio function (directly, through SYLVEX.studioBridge, or by
   pressing the existing control). The prompt field itself is Pro Studio's
   own #chatInput, so drafts, dictation, dialogues and sending are untouched.
   Grid Mode and Edit are not available on phones in either interface. */
(function () {
  'use strict';

  var S = (window.SYLVEX = window.SYLVEX || {});
  var PHONE = window.matchMedia('(max-width: 767px)');
  var STORE_KEY = 'sylvex-studio-ui';
  var MODES = ['image', 'video', 'music', 'voice', 'text'];
  var MODE_LABELS = { image: 'Фото', video: 'Видео', music: 'Музыка', voice: 'Озвучка', text: 'Текст' };
  var TABS = [['history', 'История'], ['character', 'Персонажи'], ['object', 'Объекты'], ['style', 'Стили']];
  // The Mini App's Pro Studio speaks Russian, the website's English.
  var EN = document.documentElement.classList.contains('website-studio') ? {
    'Фото': 'Image', 'Видео': 'Video', 'Музыка': 'Music', 'Озвучка': 'Voice', 'Текст': 'Text',
    'История': 'History', 'Персонажи': 'Characters', 'Объекты': 'Objects', 'Стили': 'Styles',
    'Параметры': 'Parameters', 'Соотношение сторон': 'Aspect ratio', 'Разрешение': 'Resolution', 'Количество': 'Count',
    'Продолжительность': 'Duration', 'Звук видео': 'Video sound', 'Стиль': 'Style', 'Длительность': 'Duration',
    'Минуты': 'Minutes', 'Секунды': 'Seconds', 'Сохранить': 'Save', 'максимум': 'max', 'для': 'for', 'модели': 'the model',
    'Начальное изображение': 'Start image', 'Конечный образ': 'End frame', 'Вокал': 'Vocals',
    'Референс': 'Reference', 'Объект': 'Object', 'Персонаж': 'Character', 'Начало': 'Start', 'Конец': 'End', 'Файл': 'File',
    'Меню': 'Menu', 'Домой': 'Home', 'Тема': 'Theme', 'Добавить': 'Add', 'Закрыть': 'Close', 'Назад': 'Back', 'Убрать': 'Remove',
    'Модель': 'Model', 'Голосовой ввод': 'Voice input', 'Отправить': 'Send', 'Список голосов': 'Voice list',
    'Настройки музыки': 'Music settings', 'Меньше': 'Less', 'Больше': 'More', 'Режим': 'Mode', 'Интерфейс': 'Interface',
  } : null;
  function t(text) {
    if (!EN) return text;
    if (EN[text]) return EN[text];
    var m = /^(Референс) (\d+)$/.exec(text);
    return m ? EN[m[1]] + ' ' + m[2] : text;
  }

  var I = {
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    home: '<path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-8Z"/>',
    theme: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17Z" fill="currentColor"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    sliders: '<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2"/><circle cx="9" cy="16" r="2"/>',
    list: '<path d="M4 7h13M4 11h13M4 15h8"/><circle cx="17" cy="17" r="2"/><path d="M19 17V10"/>',
    mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/>',
    up: '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>',
    chev: '<path d="m6 9 6 6 6-6"/>',
    back: '<path d="m15 6-6 6 6 6"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    ratio: '<rect x="3" y="7" width="18" height="10" rx="2"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    gem: '<path d="M6 4h12l3 5-9 11L3 9z"/><path d="M3 9h18"/>',
    speaker: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M16 9.5c1.2 1.4 1.2 3.6 0 5M18.5 7.5c2.3 2.6 2.3 6.4 0 9"/>',
    style: '<path d="M4 7h10M4 12h8M4 17h10"/><path d="m18 5-2 6h4l-2 8"/>',
    vocal: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    frameStart: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8 12 3 3 5-6"/>',
    frameEnd: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m20 15-4.5-4.5L6 20"/>',
    file: '<path d="M7 3.5h7l4.5 4.5v12.5H7z"/><path d="M14 3.5V8h4.5"/>',
    play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
    image: '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9.5" cy="9.5" r="1.6"/><path d="m20 15-4.5-4.5L6 20"/>',
    video: '<rect x="3" y="6.5" width="12.5" height="11" rx="2.5"/><path d="m15.5 10.5 5-3v9l-5-3"/>',
    music: '<circle cx="7" cy="17.5" r="2.5"/><circle cx="17" cy="15.5" r="2.5"/><path d="M9.5 17.5V6l10-2v11.5"/>',
    voice: '<path d="M12 5v14M8.5 8v8M15.5 8v8M5 11v2M19 11v2"/>',
    text: '<path d="M7 3.5h7l4.5 4.5v12.5H7z"/><path d="M14 3.5V8h4.5"/>',
  };
  // «Фото-инструменты» as icon tiles: the icon set of the Home quick tools.
  var TOOL_ICONS = {
    try_on: '<path d="M8 4 4 7l2 4 2-1v10h8V10l2 1 2-4-4-3a4 4 0 0 1-8 0Z"/>',
    remove_bg: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M4 15l4-4 5 5M14 14l2-2 4 4"/><path d="M9 4v16" stroke-dasharray="2 2.5"/>',
    replace_character: '<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0M16 7h5l-2-2M21 13h-5l2 2"/>',
    enhance: '<path d="M12 3l1.8 4.8L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.7z"/><path d="M18 15l.8 2.2 2.2.8-2.2.8L18 21l-.8-2.2-2.2-.8 2.2-.8z"/>',
    animate_photo: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3V9Z"/>',
    remove_object: '<path d="m7 21-4-4 10-10 6 6-8 8H7Z"/><path d="M14 21h7M9.5 10.5l6 6"/>',
    replace_object: '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/><path d="M15 3h3a3 3 0 0 1 3 3v2M9 21H6a3 3 0 0 1-3-3v-2"/>',
    tattoo: '<path d="m15 4 5 5-9 9H6v-5l9-9Z"/><path d="M4 21h7"/>',
    logo: '<circle cx="12" cy="12" r="8"/><path d="M9 12l2 2 4-4"/>',
    watermark_removal: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/><path d="M4 4l16 16"/>',
    hair_beard: '<path d="M6 10a6 6 0 0 1 12 0v2c0 4-2.7 7-6 7s-6-3-6-7v-2Z"/><path d="M8 9c2 1 6 1 8 0"/>',
    face_retouch: '<circle cx="12" cy="12" r="8"/><path d="M9 10h.01M15 10h.01M9 15c1.7 1.3 4.3 1.3 6 0"/>',
  };
  var TOOL_ICON_FALLBACK = '<path d="M12 3l1.8 4.8L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.7z"/>';
  S.photoToolIconHtml = function (key) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + (TOOL_ICONS[key] || TOOL_ICON_FALLBACK) + '</svg>';
  };

  function svg(name, cls) {
    return '<svg class="sxs-i' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true">' + (I[name] || '') + '</svg>';
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function bridge() { return S.studioBridge || null; }
  function stop(e) { if (e) { e.preventDefault(); e.stopPropagation(); } }

  function savedUi() {
    try { return localStorage.getItem(STORE_KEY) === 'pro' ? 'pro' : 'standard'; } catch (e) { return 'standard'; }
  }
  function saveUi(value) {
    try { localStorage.setItem(STORE_KEY, value); } catch (e) {}
  }

  var el = {};          // Standard's own nodes
  var pro = {};         // Pro Studio nodes Standard reads or presses
  var state = { params: false, list: null, sheet: false, tab: 'history', sig: {} };
  var mounted = false;

  function active() { return mounted && document.body.classList.contains('sxs-std'); }
  S.isStandardStudio = active;
  S.setStudioUi = function (value) { saveUi(value === 'pro' ? 'pro' : 'standard'); apply(); };

  // ---------------------------------------------------------------- mount
  function mount() {
    var studio = $('[data-view="tools"] .studio');
    var composer = $('#studioComposer');
    var b = bridge();
    if (!studio || !composer || !b) return false;
    pro.studio = studio;
    pro.composer = composer;
    pro.bar = $('.studio-bar', studio);
    pro.prompt = $('.studio-prompt-column', composer);
    pro.input = $('#chatInput');
    pro.send = $('#sendBtn');
    pro.mic = $('#micBtn');
    pro.model = $('.studio-control-row .studio-select-pill.wide', composer);
    pro.home = $('.studio-bar-right > button:last-child', studio);
    if (!pro.prompt || !pro.input || !pro.send) return false;

    // Header (Standard): menu, SYLVEX, Standard | Pro, home.
    el.hdr = document.createElement('header');
    el.hdr.className = 'sxs-hdr';
    el.hdr.innerHTML = '<button type="button" class="sxs-ib" data-sxs="menu" aria-label="' + t('Меню') + '">' + svg('menu') + '</button>'
      + '<div class="sxs-hdr-mid"><span class="sxs-brand">SYLVEX</span>' + segHtml() + '</div>'
      + '<button type="button" class="sxs-ib" data-sxs="home" aria-label="' + t('Домой') + '">' + svg('home') + '</button>';
    studio.insertBefore(el.hdr, studio.firstChild);

    // Pro on a phone: the same switch takes the place of «Обычный | Сетка».
    var cluster = $('.studio-brand-cluster', studio);
    if (cluster) {
      el.proSeg = document.createElement('div');
      el.proSeg.className = 'sxs-pro-seg';
      el.proSeg.innerHTML = segHtml();
      cluster.appendChild(el.proSeg);
    }

    // Above the composer: the parameters panel and the mode row.
    el.top = document.createElement('section');
    el.top.className = 'sxs-top';
    el.top.innerHTML = '<div class="sxs-params" role="dialog" aria-label="' + t('Параметры') + '"></div>'
      + '<div class="sxs-modes"><div class="sxs-seg-modes" role="tablist" aria-label="' + t('Режим') + '"></div><div class="sxs-chips"></div></div>';
    composer.parentNode.insertBefore(el.top, composer);
    el.params = $('.sxs-params', el.top);
    el.segModes = $('.sxs-seg-modes', el.top);
    el.chips = $('.sxs-chips', el.top);

    // Inside the composer: attachments above the prompt, Standard's bar below it.
    el.atts = document.createElement('div');
    el.atts.className = 'sxs-atts';
    pro.prompt.parentNode.insertBefore(el.atts, pro.prompt);
    el.bar = document.createElement('div');
    el.bar.className = 'sxs-bar';
    pro.prompt.appendChild(el.bar);

    // The "+" sheet for Photo and Video.
    el.sheet = document.createElement('div');
    el.sheet.className = 'sxs-sheet-wrap';
    el.sheet.hidden = true;
    el.sheet.innerHTML = '<div class="sxs-sheet" role="dialog" aria-label="' + t('Добавить') + '" onclick="event.stopPropagation()">'
      + '<div class="sxs-sheet-top"><div class="sxs-tabs" role="tablist"></div>'
      + '<button type="button" class="sxs-close" data-sxs="sheet-close" aria-label="' + t('Закрыть') + '">' + svg('close') + '</button></div>'
      + '<div class="sxs-sheet-content"></div>'
      + '<div class="sxs-sheet-upload"><div class="sxs-frames"></div><div class="sxs-upload-slot"></div></div>'
      + '</div>';
    document.body.appendChild(el.sheet);

    // Theme switch: in Standard it lives in the side menu, on the user card.
    var card = $('#hdUserCard');
    if (card) {
      el.theme = document.createElement('button');
      el.theme.type = 'button';
      el.theme.className = 'sxs-theme';
      el.theme.setAttribute('aria-label', t('Тема'));
      el.theme.dataset.sxs = 'theme';
      el.theme.innerHTML = svg('theme');
      card.appendChild(el.theme);
    }

    document.addEventListener('click', onClick, true);
    document.addEventListener('input', onInput, true);
    el.params.addEventListener('pointerdown', onSliderDown);
    document.addEventListener('pointermove', onSliderMove);
    document.addEventListener('pointerup', function () { slider = null; });
    if (PHONE.addEventListener) PHONE.addEventListener('change', apply); else PHONE.addListener(apply);
    watchHosts();
    mounted = true;
    apply();
    setInterval(sync, 350);
    return true;
  }

  function segHtml() {
    return '<div class="sxs-seg" role="group" aria-label="' + t('Интерфейс') + '">'
      + '<button type="button" data-sxs-ui="standard">Standard</button><button type="button" data-sxs-ui="pro">Pro</button></div>';
  }

  // ---------------------------------------------------------------- apply
  function apply() {
    var phone = PHONE.matches;
    var std = phone && savedUi() === 'standard';
    var body = document.body;
    body.classList.toggle('sxs-phone', phone);
    body.classList.toggle('sxs-std', std);
    body.classList.toggle('sxs-pro', phone && !std);
    $$('[data-sxs-ui]').forEach(function (btn) { btn.classList.toggle('on', btn.dataset.sxsUi === (std ? 'standard' : 'pro')); });
    // No Grid Mode on phones.
    var grid = $('#studioGridWorkspace');
    if (phone && grid && !grid.hidden && typeof S.setStudioLayout === 'function') S.setStudioLayout('classic');
    if (!std) { closeParams(); closeSheet(); }
    // Pages that size Pro Studio to the space left under their own header
    // re-measure on resize (the website hides its mode tabs in Standard).
    var wasStd = apply.std;
    apply.std = std;
    if (wasStd !== undefined && wasStd !== std) window.dispatchEvent(new Event('resize'));
    else if (wasStd === undefined) setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 0);
    state.sig = {};
    if (std) sync();
  }

  // ---------------------------------------------------------------- render
  function sync() {
    if (!active()) return;
    var b = bridge();
    var mode = b.mode();
    var chips = proChips(mode);
    renderIf('modes', mode + '|' + chips.map(function (c) { return c.label + (c.active ? '*' : ''); }).join(','), function () { renderModes(mode, chips); });
    var atts = b.attachments();
    renderIf('atts', JSON.stringify(atts), function () { renderAtts(atts); });
    var modelName = textOf($('#modelValComposer'));
    var modelIcon = ($('#modelIconComposer') || {}).innerHTML || '';
    var vocal = textOf($('#musicVocalVal'));
    renderIf('bar', [mode, modelName, modelIcon.length, vocal, b.videoSection(), state.params].join('|'), function () { renderBar(mode, modelName, modelIcon, vocal); });
    // Send and mic mirror the Pro Studio buttons they press.
    var send = $('.sxs-send', el.bar);
    if (send) {
      send.disabled = !!pro.send.disabled;
      send.classList.toggle('is-busy', pro.send.classList.contains('loading') || pro.send.classList.contains('is-loading'));
    }
    var mic = $('[data-sxs="mic"]', el.bar);
    if (mic && pro.mic) mic.classList.toggle('on', /\b(live|recording|active|is-recording)\b/.test(pro.mic.className));
    if (state.params) renderIf('params', paramsSig(mode), function () { renderParams(mode); });
    if (state.sheet) renderFrames();
  }
  function renderIf(key, sig, fn) {
    if (state.sig[key] === sig) return;
    state.sig[key] = sig;
    fn();
  }
  function textOf(node) { return node ? String(node.textContent || '').replace(/\s+/g, ' ').trim() : ''; }

  function proChips(mode) {
    return $$('.studio-mode-tabs .studio-mode-tab', pro.composer).filter(function (tab) {
      return tab.classList.contains(mode + '-only');
    }).map(function (tab) {
      var icon = $('svg', tab);
      return { node: tab, label: textOf($('span', tab)) || textOf(tab), icon: icon ? icon.outerHTML : '', active: tab.classList.contains('active') };
    });
  }

  function renderModes(mode, chips) {
    document.body.dataset.sxsCurrent = mode;
    el.segModes.innerHTML = MODES.map(function (m) {
      return '<button type="button" role="tab" data-sxs-mode="' + m + '" class="' + (m === mode ? 'on' : '') + '" aria-label="' + t(MODE_LABELS[m]) + '"'
        + (m === mode ? ' aria-selected="true"' : '') + '>' + svg(m) + '</button>';
    }).join('');
    el.chips.innerHTML = chips.map(function (c, i) {
      return '<button type="button" class="sxs-chip' + (c.active ? ' on' : '') + '" data-sxs-chip="' + i + '">' + c.icon + '<span>' + esc(c.label) + '</span></button>';
    }).join('');
    el.chipNodes = chips.map(function (c) { return c.node; });
  }

  function renderAtts(atts) {
    var refs = atts.filter(function (a) { return a.group === 'ref'; });
    var visuals = atts.filter(function (a) { return a.group === 'visual'; });
    function tile(a) {
      var media = a.type === 'video'
        ? '<span class="sxs-att-media is-video">' + svg('play') + '</span>'
        : (a.type === 'image' || a.group === 'visual' || /\.(png|jpe?g|webp|gif|heic)(\?|$)|^(blob:|data:image)/i.test(a.url || '')) && a.url
          ? '<img src="' + esc(a.url) + '" alt="" loading="lazy" decoding="async">'
          : '<span class="sxs-att-media is-file">' + svg('file') + '</span>';
      return '<div class="sxs-att">' + media
        + '<button type="button" class="sxs-att-x" data-sxs-remove="' + esc(a.id) + '" aria-label="' + t('Убрать') + '">×</button>'
        + '<span class="sxs-att-lbl">' + esc(t(a.label)) + '</span></div>';
    }
    el.atts.innerHTML = refs.map(tile).join('') + (refs.length && visuals.length ? '<span class="sxs-att-sep" aria-hidden="true"></span>' : '') + visuals.map(tile).join('');
    el.atts.hidden = !atts.length;
  }

  function renderBar(mode, modelName, modelIcon, vocal) {
    var settingsIcon = mode === 'voice' ? 'list' : 'sliders';
    var settings = '<button type="button" class="sxs-ib sxs-settings' + (state.params ? ' on' : '') + '" data-sxs="settings" aria-label="'
      + t(mode === 'voice' ? 'Список голосов' : 'Параметры') + '" aria-expanded="' + (state.params ? 'true' : 'false') + '">' + svg(settingsIcon) + '</button>';
    var model = '<button type="button" class="sxs-model" data-sxs="model" aria-label="' + t('Модель') + '">'
      + '<span class="sxs-model-icon">' + modelIcon + '</span><span class="sxs-model-name">' + esc(modelName) + '</span>' + svg('chev', 'sxs-chev') + '</button>';
    var vocalBtn = mode === 'music' && $('#musicVocalButton')
      ? '<button type="button" class="sxs-vocal" data-sxs="vocal">' + svg('vocal') + '<span>' + esc(vocal || t('Вокал')) + '</span></button>' : '';
    el.bar.innerHTML = '<button type="button" class="sxs-ib" data-sxs="plus" aria-label="' + t('Добавить') + '">' + svg('plus') + '</button>'
      + model + vocalBtn + (mode === 'text' ? settings : '')
      + '<span class="sxs-spacer"></span>'
      + (mode === 'text' ? '' : settings)
      + (pro.mic ? '<button type="button" class="sxs-ib" data-sxs="mic" aria-label="' + t('Голосовой ввод') + '">' + svg('mic') + '</button>' : '')
      + '<button type="button" class="sxs-send" data-sxs="send" aria-label="' + t('Отправить') + '">' + svg('up') + '</button>';
    el.bar.classList.toggle('is-music', mode === 'music');
    // A brand logo that cannot load leaves the name alone, as in Pro.
    $$('.sxs-model-icon img', el.bar).forEach(function (img) {
      var drop = function () { img.remove(); };
      if (img.complete && !img.naturalWidth) drop(); else img.addEventListener('error', drop);
    });
    state.sig.params = null;
  }

  // ---------------------------------------------------------------- params
  // Rows are the existing parameter buttons of each mode; a row shows that
  // button's current value and opens that button's own list.
  var ROWS = {
    image: [
      { label: 'Соотношение сторон', sel: '#imageSizeBtn', icon: 'ratio' },
      { label: 'Разрешение', sel: '#imageQualityBtn', icon: 'gem' },
      { label: 'Количество', count: true },
      { label: 'Seed', sel: '.studio-control-row .image-settings-pill.image-only', icon: 'sliders', iconOnly: true },
    ],
    video: [
      { label: 'Соотношение сторон', sel: '#imageSizeBtn', icon: 'ratio' },
      { label: 'Продолжительность', sel: '.studio-control-row [onclick*="\'duration\'"]', icon: 'clock' },
      { label: 'Разрешение', sel: '.studio-control-row [onclick*="\'resolution\'"]', icon: 'gem' },
      { label: 'Звук видео', sel: '.studio-control-row [onclick*="\'sound\'"]', icon: 'speaker' },
    ],
    music: [
      { label: 'Стиль', sel: '.studio-control-row [onclick*="\'genre\'"]', icon: 'style' },
      { label: 'Продолжительность', sel: '#musicDurationButton', icon: 'clock', duration: true },
    ],
  };
  function rowButton(row) { return row.sel ? $(row.sel, pro.composer) : null; }
  function rowsFor(mode) {
    return (ROWS[mode] || []).filter(function (row) {
      if (row.count) return true;
      var btn = rowButton(row);
      return btn && !btn.hidden;
    });
  }
  function paramsSig(mode) {
    var b = bridge();
    if (mode === 'text') return 'text|' + JSON.stringify(b.textVersions());
    if (state.list === 'duration') return 'dur|' + JSON.stringify(b.musicDuration()) + '|' + (state.durDraft == null ? '' : state.durDraft);
    if (state.list) return 'list|' + state.list;
    return mode + '|' + rowsFor(mode).map(function (row) {
      return row.count ? b.imageCount() : textOf(rowButton(row)) + (rowButton(row).disabled ? '!' : '');
    }).join('|');
  }

  function renderParams(mode) {
    var b = bridge();
    if (mode === 'text') {
      var v = b.textVersions();
      var n = v.items.length;
      var sel = Math.max(0, v.items.findIndex(function (item) { return item.id === v.activeId; }));
      if (n <= 1) sel = 0;
      var pos = function (i) { var f = n <= 1 ? 1 : i / (n - 1); return 'calc(14px + (100% - 28px) * ' + f + ')'; };
      var frac = n <= 1 ? 1 : sel / (n - 1);
      el.params.innerHTML = '<div class="sxs-ver"><div class="sxs-ver-title">' + esc(v.family) + '</div>'
        + '<div class="sxs-ver-slider' + (n <= 1 ? ' is-one' : '') + '" data-sxs-slider="1">'
        + '<div class="sxs-ver-label" style="left:' + pos(sel) + ';transform:translateX(' + (-frac * 100) + '%)">' + esc(n ? v.items[sel].label : '') + '</div>'
        + '<div class="sxs-ver-track">' + v.items.map(function (item, i) { return '<i style="left:' + pos(i) + '"></i>'; }).join('')
        + '<span class="sxs-ver-thumb" style="left:' + pos(sel) + '"></span></div></div></div>';
      return;
    }
    if (state.list === 'duration') return renderDuration();
    if (state.list) return; // an existing list is open inside the panel
    var rows = rowsFor(mode);
    el.params.innerHTML = '<h3 class="sxs-params-title">' + t('Параметры') + '</h3>' + rows.map(function (row, i) {
      if (row.count) {
        var count = b.imageCount();
        return '<div class="sxs-prow"><span>' + t(row.label) + '</span><span class="sxs-stepper">'
          + '<button type="button" data-sxs-step="-1" aria-label="' + t('Меньше') + '"' + (count <= 1 ? ' disabled' : '') + '>−</button><b>' + count + '</b>'
          + '<button type="button" data-sxs-step="1" aria-label="' + t('Больше') + '"' + (count >= 4 ? ' disabled' : '') + '>+</button></span></div>';
      }
      var btn = rowButton(row);
      var value = row.iconOnly ? '' : '<span>' + esc(textOf(btn)) + '</span>';
      return '<button type="button" class="sxs-prow" data-sxs-row="' + i + '"' + (btn.disabled ? ' aria-disabled="true"' : '') + '><span>' + t(row.label) + '</span>'
        + '<span class="sxs-pval">' + svg(row.icon) + value + '</span></button>';
    }).join('')
      + (mode === 'music' && $('.studio-control-row .image-settings-pill.music-only', pro.composer)
        ? '<div class="sxs-pfoot"><button type="button" class="sxs-ib" data-sxs="music-settings" aria-label="' + t('Настройки музыки') + '">' + svg('sliders') + '</button></div>' : '');
    el.rows = rows;
  }

  function renderDuration() {
    var d = bridge().musicDuration();
    var value = state.durDraft == null ? d.seconds : state.durDraft;
    var mm = Math.floor(value / 60);
    var ss = value % 60;
    var ticks = function (max, step, scale) {
      var html = '';
      for (var v = 0; v <= max; v += step) html += '<span style="left:' + (v / scale * 100) + '%">' + v + '</span>';
      return html;
    };
    el.params.innerHTML = '<div class="sxs-list-head"><button type="button" class="sxs-ib" data-sxs="list-back" aria-label="' + t('Назад') + '">' + svg('back') + '</button>'
      + '<span>' + t('Длительность') + '</span><b class="sxs-dur-val">' + (value ? mm + ':' + String(ss).padStart(2, '0') : 'Auto') + '</b></div>'
      + '<div class="sxs-dur"><div class="sxs-dur-lbl"><span>' + t('Минуты') + '</span><b>' + mm + '</b></div>'
      + '<input type="range" min="0" max="' + d.maxMinutes + '" step="1" value="' + mm + '" data-sxs-dur="m" aria-label="' + t('Минуты') + '">'
      + '<div class="sxs-ticks">' + ticks(d.maxMinutes, 1, d.maxMinutes) + '</div></div>'
      + '<div class="sxs-dur"><div class="sxs-dur-lbl"><span>' + t('Секунды') + '</span><b>' + String(ss).padStart(2, '0') + '</b></div>'
      + '<input type="range" min="0" max="59" step="1" value="' + ss + '" data-sxs-dur="s" aria-label="' + t('Секунды') + '"' + (mm >= d.maxMinutes ? ' disabled' : '') + '>'
      + '<div class="sxs-ticks">' + ticks(50, 10, 59) + '</div></div>'
      + '<p class="sxs-dur-hint">0:00 = Auto · ' + t('максимум') + ' ' + d.maxMinutes + ':00 ' + t('для') + ' ' + esc(d.model || t('модели')) + '</p>'
      + '<button type="button" class="sxs-save" data-sxs="dur-save">' + t('Сохранить') + '</button>';
  }

  function openParams() {
    state.params = true;
    state.list = null;
    document.body.classList.add('sxs-params-open');
    state.sig.params = null;
    state.sig.bar = null;
    sync();
  }
  function closeParams() {
    if (state.list && state.list !== 'duration') unhostPop(true);
    state.params = false;
    state.list = null;
    state.durDraft = null;
    document.body.classList.remove('sxs-params-open');
    if (el.params) el.params.innerHTML = '';
    state.sig.bar = null;
  }

  // An existing option list (#modelPop) shown inside the panel: same rows,
  // same handlers - only its place and look change while it is here.
  var popHome = null;
  function hostPop(title) {
    var pop = $('#modelPop');
    if (!pop || !pop.classList.contains('show')) return;
    if (!popHome) popHome = { parent: pop.parentNode, next: pop.nextSibling };
    state.list = 'pop';
    el.params.innerHTML = '<div class="sxs-list-head"><button type="button" class="sxs-ib" data-sxs="list-back" aria-label="' + t('Назад') + '">' + svg('back') + '</button><span class="sxs-list-title"></span></div><div class="sxs-list"></div>';
    $('.sxs-list-title', el.params).textContent = t(title);
    $('.sxs-list', el.params).appendChild(pop);
    el.params.classList.add('is-hosting');
    retitle();
  }
  function retitle() {
    var pop = $('#modelPop');
    var title = pop && $('.image-size-sheet-title', pop);
    var head = $('.sxs-list-head', el.params);
    if (head) head.hidden = !!(pop && $('.image-seed-head', pop));
    if (title && $('.sxs-list-title', el.params)) $('.sxs-list-title', el.params).textContent = textOf(title);
  }
  function unhostPop(closePop) {
    var pop = $('#modelPop');
    el.params.classList.remove('is-hosting');
    if (pop && popHome && pop.parentNode !== popHome.parent) {
      if (closePop) pop.classList.remove('show');
      popHome.parent.insertBefore(pop, popHome.next && popHome.next.parentNode === popHome.parent ? popHome.next : null);
    }
    state.list = null;
    state.sig.params = null;
  }

  // ---------------------------------------------------------------- sheet
  var sheetHome = {};
  var switching = false;
  function openSheet() {
    var b = bridge();
    var video = b.mode() === 'video';
    b.setUploadTarget(video ? 'video_references' : 'image_upload');
    state.sheet = true;
    state.tab = 'history';
    el.sheet.hidden = false;
    el.sheet.classList.toggle('is-video', video);
    document.body.classList.add('sxs-sheet-open');
    $('.sxs-tabs', el.sheet).innerHTML = TABS.filter(function (tab) { return !(video && tab[0] === 'style'); }).map(function (tab) {
      return '<button type="button" role="tab" data-sxs-tab="' + tab[0] + '">' + t(tab[1]) + '</button>';
    }).join('');
    state.sig.frames = null;
    showTab('history');
  }

  function showTab(tab) {
    var b = bridge();
    var video = b.mode() === 'video';
    switching = true;
    state.tab = tab;
    $$('[data-sxs-tab]', el.sheet).forEach(function (btn) { btn.classList.toggle('on', btn.dataset.sxsTab === tab); });
    returnVisualCard();
    var content = $('.sxs-sheet-content', el.sheet);
    // The upload half of the History panel is always at the bottom.
    if (typeof S.openUploadPanel === 'function') S.openUploadPanel();
    var panel = $('#uploadPanel');
    if (panel) {
      var part = function (key, sel) { return sheetHome[key] ? sheetHome[key].node : $(sel, panel); };
      adopt('generated', part('generated', '.upload-panel-generated'), tab === 'history' ? content : null);
      adopt('actions', part('actions', '.upload-panel-actions'), $('.sxs-upload-slot', el.sheet));
    }
    if (tab !== 'history') {
      if (video && tab === 'character' && S.chooseVideoAddCharacter) S.chooseVideoAddCharacter(null);
      else if (video && tab === 'object' && S.chooseVideoAddObject) S.chooseVideoAddObject(null);
      else S.openImageOptionMenu(null, tab === 'object' ? 'objects' : tab);
      var stylePanel = $('#imageStylePanel');
      var card = stylePanel && $('.image-style-panel-card', stylePanel);
      if (card && stylePanel.classList.contains('show')) adopt('visual', card, content);
    }
    switching = false;
  }

  // Moves an existing panel part into the sheet (to = null puts it back).
  function adopt(key, node, to) {
    if (!node) return;
    if (!sheetHome[key]) sheetHome[key] = { node: node, parent: node.parentNode, next: node.nextSibling };
    var home = sheetHome[key];
    if (to) { to.appendChild(node); return; }
    if (node.parentNode !== home.parent) home.parent.insertBefore(node, home.next && home.next.parentNode === home.parent ? home.next : null);
  }
  function returnVisualCard() {
    if (!sheetHome.visual) return;
    var stylePanel = $('#imageStylePanel');
    adopt('visual', sheetHome.visual.node, null);
    if (stylePanel && stylePanel.classList.contains('show') && typeof S.closeImageStylePanel === 'function') S.closeImageStylePanel();
  }

  function closeSheet() {
    if (!state.sheet) return;
    switching = true;
    state.sheet = false;
    returnVisualCard();
    adopt('generated', sheetHome.generated && sheetHome.generated.node, null);
    adopt('actions', sheetHome.actions && sheetHome.actions.node, null);
    var panel = $('#uploadPanel');
    if (panel && panel.classList.contains('show') && typeof S.closeUploadPanel === 'function') S.closeUploadPanel();
    el.sheet.hidden = true;
    document.body.classList.remove('sxs-sheet-open');
    switching = false;
    state.sig.atts = null;
  }

  function renderFrames() {
    var b = bridge();
    var video = b.mode() === 'video';
    var target = b.uploadTarget();
    var atts = b.attachments();
    var has = function (id) { return atts.some(function (a) { return a.id === id; }); };
    renderIf('frames', [video, target, has('start'), has('end')].join('|'), function () {
      var frames = $('.sxs-frames', el.sheet);
      frames.innerHTML = video
        ? '<button type="button" class="sxs-frame' + (target === 'video_start' ? ' on' : '') + (has('start') ? ' has' : '') + '" data-sxs-frame="video_start">' + svg('frameStart') + '<span>' + t('Начальное изображение') + '</span></button>'
          + '<button type="button" class="sxs-frame' + (target === 'video_end' ? ' on' : '') + (has('end') ? ' has' : '') + '" data-sxs-frame="video_end">' + svg('frameEnd') + '<span>' + t('Конечный образ') + '</span></button>'
        : '';
      frames.hidden = !video;
    });
  }

  // The panels Standard borrows close themselves after a choice (the same
  // moment they close in Pro); the sheet and the parameter list follow.
  function watchHosts() {
    var observe = function (node, fn) { if (node) new MutationObserver(fn).observe(node, { attributes: true, attributeFilter: ['class'] }); };
    var tries = 0;
    var timer = setInterval(function () {
      var upload = $('#uploadPanel');
      var style = $('#imageStylePanel');
      if (upload && !upload.__sxs) { upload.__sxs = 1; observe(upload, function () { if (state.sheet && !switching && !upload.classList.contains('show')) closeSheet(); }); }
      if (style && !style.__sxs) { style.__sxs = 1; observe(style, function () { if (state.sheet && !switching && state.tab !== 'history' && !style.classList.contains('show')) closeSheet(); }); }
      if (++tries > 2400 || (upload && style && upload.__sxs && style.__sxs)) clearInterval(timer);
    }, 500);
    var pop = $('#modelPop');
    if (pop) {
      new MutationObserver(function () {
        if (state.list !== 'pop') return;
        // The website places this list next to its button; inside the panel it has no position.
        if (pop.getAttribute('style')) pop.removeAttribute('style');
        if (!pop.classList.contains('show')) { unhostPop(false); state.sig.params = null; sync(); return; }
        var list = $('.sxs-list', el.params);
        if (list && pop.parentNode !== list) list.appendChild(pop);
        retitle();
      }).observe(pop, { attributes: true, attributeFilter: ['class', 'style'], childList: true });
      // Pro Studio re-attaches the list to <body> each time it opens a level.
      new MutationObserver(function () {
        var list = state.list === 'pop' && $('.sxs-list', el.params);
        if (list && pop.parentNode !== list && pop.classList.contains('show')) list.appendChild(pop);
      }).observe(document.body, { childList: true });
    }
  }

  // ---------------------------------------------------------------- events
  function press(node, e) {
    if (!node) return;
    stop(e);
    node.click();
  }

  function onClick(e) {
    var tg = e.target;
    if (!tg || !tg.closest) return;
    var ui = tg.closest('[data-sxs-ui]');
    if (ui) { stop(e); S.setStudioUi(ui.dataset.sxsUi); return; }
    if (!active()) return;
    if (tg.closest('.sxs-theme')) { stop(e); if (S.cycleStudioTheme) S.cycleStudioTheme(e); return; }

    var mode = tg.closest('[data-sxs-mode]');
    if (mode) { stop(e); closeParams(); S.genAction(mode.dataset.sxsMode); state.sig = {}; sync(); return; }
    var chip = tg.closest('[data-sxs-chip]');
    if (chip) { closeParams(); press(el.chipNodes && el.chipNodes[Number(chip.dataset.sxsChip)], e); state.sig.modes = null; setTimeout(sync, 60); return; }

    var remove = tg.closest('[data-sxs-remove]');
    if (remove) { stop(e); bridge().removeAttachment(remove.dataset.sxsRemove); state.sig.atts = null; sync(); return; }

    var tab = tg.closest('[data-sxs-tab]');
    if (tab) { stop(e); showTab(tab.dataset.sxsTab); return; }
    var frame = tg.closest('[data-sxs-frame]');
    if (frame) {
      stop(e);
      // Same as pressing the frame card in Pro: it becomes the upload target.
      bridge().setUploadTarget(frame.dataset.sxsFrame);
      if (state.tab !== 'history') showTab('history');
      else if (S.openUploadPanel) { switching = true; S.openUploadPanel(); switching = false; }
      state.sig.frames = null;
      renderFrames();
      return;
    }
    if (tg.closest('[data-sxs="sheet-close"]') || tg === el.sheet) { stop(e); closeSheet(); return; }

    var step = tg.closest('[data-sxs-step]');
    if (step) { stop(e); var b = bridge(); b.setImageCount(b.imageCount() + Number(step.dataset.sxsStep)); state.sig.params = null; sync(); return; }
    var row = tg.closest('[data-sxs-row]');
    if (row) {
      var def = el.rows && el.rows[Number(row.dataset.sxsRow)];
      var btn = def && rowButton(def);
      if (!btn) return;
      stop(e);
      if (def.duration && bridge().musicDuration().supported) { state.list = 'duration'; state.durDraft = null; state.sig.params = null; sync(); return; }
      btn.click();
      hostPop(def.label);
      return;
    }

    var action = tg.closest('[data-sxs]');
    if (!action) return;
    var name = action.dataset.sxs;
    var m = bridge().mode();
    if (name === 'menu') { stop(e); S.toggleHistory(e); }
    else if (name === 'home') press(pro.home, e);
    else if (name === 'model') { closeParams(); press(pro.model, e); }
    else if (name === 'vocal') press($('#musicVocalButton'), e);
    else if (name === 'mic') press(pro.mic, e);
    else if (name === 'send') { closeParams(); press(pro.send, e); }
    else if (name === 'settings') {
      stop(e);
      if (m === 'voice') { closeParams(); S.openVoiceList(e); return; }
      if (state.params) closeParams(); else openParams();
      sync();
    }
    else if (name === 'music-settings') press($('.studio-control-row .image-settings-pill.music-only', pro.composer), e);
    else if (name === 'list-back') {
      stop(e);
      if (state.list === 'pop') unhostPop(true); else { state.list = null; state.durDraft = null; }
      state.sig.params = null;
      sync();
    }
    else if (name === 'dur-save') {
      stop(e);
      bridge().setMusicDuration(state.durDraft == null ? bridge().musicDuration().seconds : state.durDraft);
      state.list = null;
      state.durDraft = null;
      state.sig.params = null;
      sync();
    }
    else if (name === 'plus') {
      stop(e);
      closeParams();
      if (m === 'image') openSheet();
      else if (m === 'video') {
        if (bridge().videoSection() === 'edit') press($('#videoEditUploadButton'), e);
        else openSheet();
      }
      else if (m === 'music') S.openNativeFilePicker('music_audio');
      else if (m === 'voice') S.openVoiceUpload(e);
      else S.openNativeFilePicker('text_media');
    }
  }

  function onInput(e) {
    var d = e.target && e.target.closest && e.target.closest('[data-sxs-dur]');
    if (!d || !active()) return;
    var info = bridge().musicDuration();
    var value = state.durDraft == null ? info.seconds : state.durDraft;
    var mm = Math.floor(value / 60);
    var ss = value % 60;
    if (d.dataset.sxsDur === 'm') mm = Number(d.value); else ss = Number(d.value);
    if (mm >= info.maxMinutes) { mm = info.maxMinutes; ss = 0; }
    state.durDraft = mm * 60 + ss;
    var which = d.dataset.sxsDur;
    renderDuration();
    var again = $('[data-sxs-dur="' + which + '"]', el.params);
    if (again) again.focus();
  }

  // Version slider: drag or tap, snaps to the nearest version.
  var slider = null;
  function pickVersion(ev) {
    var track = slider && $('.sxs-ver-track', slider);
    var v = bridge().textVersions();
    if (!track || v.items.length <= 1) return;
    var r = track.getBoundingClientRect();
    var share = Math.max(0, Math.min(1, (ev.clientX - r.left - 14) / (r.width - 28)));
    var item = v.items[Math.round(share * (v.items.length - 1))];
    if (item && item.id !== v.activeId) {
      bridge().pickTextVersion(item.id);
      state.sig.params = null;
      renderParams('text');
      slider = $('[data-sxs-slider]', el.params);
    }
  }
  function onSliderDown(e) {
    var s = e.target.closest && e.target.closest('[data-sxs-slider]');
    if (!s) return;
    slider = s;
    pickVersion(e);
  }
  function onSliderMove(e) { if (slider) pickVersion(e); }

  // ---------------------------------------------------------------- boot
  var boot = setInterval(function () {
    if (mounted) return clearInterval(boot);
    if (mount()) clearInterval(boot);
  }, 200);
})();
