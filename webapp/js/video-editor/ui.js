// SYLVEX Video Editor UI. It only talks to the SYLVEX editor core
// (editor.js) and reads the SYLVEX project; it never touches an engine SDK.
import { MAX_AUDIO_LANES, MIN_CLIP, DEFAULT_TRANSITION_DURATION, clipDuration } from './project.js';

const LANE = { ruler: 26, text: 36, video: 60, audio: 42 };
const ERRORS = {
  login_required: 'Войдите в SYLVEX, чтобы открыть видеоредактор.',
  config_failed: 'Не удалось получить настройки видеоредактора. Попробуйте ещё раз.',
  engine_load_failed: 'Не удалось загрузить видеодвижок. Проверьте соединение и попробуйте ещё раз.',
  engine_init_failed: 'Видеодвижок не запустился в этом браузере. Попробуйте Chrome или Edge на компьютере.',
  license_invalid: 'Лицензия видеодвижка не принята. Сообщите администратору SYLVEX.',
  browser_unsupported: 'Этот браузер не поддерживает редактирование видео. Откройте SYLVEX в Chrome или Edge на компьютере.',
  export_unsupported: 'Экспорт видео не поддерживается этим браузером. Откройте SYLVEX в Chrome или Edge на компьютере.',
  export_failed: 'Не удалось экспортировать видео. Попробуйте ещё раз или уменьшите длительность.',
  export_cancelled: 'Экспорт отменён.',
  nothing_to_export: 'Добавьте хотя бы один видеоклип.',
  not_video_file: 'Это не видеофайл.',
  not_audio_file: 'Это не аудиофайл.',
  media_unsupported: 'Этот файл не открывается в редакторе. Попробуйте MP4 (H.264), MOV, MP3, M4A или WAV.',
  media_duration_unknown: 'Не удалось определить длительность файла.',
  media_metadata_timeout: 'Файл слишком долго открывается. Попробуйте другой.',
  split_out_of_range: 'Поставьте курсор внутрь выбранного клипа, не у самого края.',
  transition_needs_next_clip: 'Переход ставится между двумя соседними клипами.',
};

const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const errorText = (error) => {
  const code = String((error && (error.code || error.message)) || '');
  return ERRORS[code] || ERRORS[code.split(':')[0]] || 'Что-то пошло не так. Попробуйте ещё раз.';
};
const formatTime = (seconds, precise) => {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return String(minutes).padStart(2, '0') + ':' + (precise ? rest.toFixed(1).padStart(4, '0') : String(Math.floor(rest)).padStart(2, '0'));
};
const ICON = {
  play: '<svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" stroke="none"/></svg>',
  split: '<svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  undo: '<svg viewBox="0 0 24 24"><path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/></svg>',
  redo: '<svg viewBox="0 0 24 24"><path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  speaker: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg>',
  mute: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="m17 9 4 6M21 9l-4 6"/></svg>',
  join: '<svg viewBox="0 0 24 24"><path d="M4 12h5l3-4v8l3-4h5"/></svg>',
};

export function mountVideoEditorUI(host, editor, { onClose } = {}) {
  const state = { selection: null, pps: 60, autoFit: true, time: 0, playing: false, exporting: null, caps: { transitions: [], fonts: [], canExport: false } };
  host.innerHTML = shell();
  const $ = (selector) => host.querySelector(selector);
  const stage = $('#veStage');
  const timeline = $('#veTimeline');
  const scroller = $('#veScroll');
  const inspector = $('#veInspector');
  let textTimer = 0;

  function shell() {
    return '<div class="ve" id="ve">'
      + '<header class="ve-head">'
      + '<button type="button" class="ve-icon" data-ve="close" aria-label="Закрыть редактор">' + ICON.close + '</button>'
      + '<div class="ve-title"><b>Видеоредактор</b><small id="veEngine"></small></div>'
      + '<span class="ve-spacer"></span>'
      + '<button type="button" class="ve-icon" data-ve="undo" aria-label="Отменить" disabled>' + ICON.undo + '</button>'
      + '<button type="button" class="ve-icon" data-ve="redo" aria-label="Повторить" disabled>' + ICON.redo + '</button>'
      + '<label class="ve-btn"><input type="file" accept="video/*" multiple hidden data-ve-file="video"><span>＋ Видео</span></label>'
      + '<label class="ve-btn"><input type="file" accept="audio/*" multiple hidden data-ve-file="audio"><span>＋ Аудио</span></label>'
      + '<button type="button" class="ve-btn" data-ve="add-text">＋ Текст</button>'
      + '<button type="button" class="ve-btn ve-primary" data-ve="export" disabled>Экспорт</button>'
      + '</header>'
      + '<div class="ve-body">'
      + '<section class="ve-preview"><div class="ve-stage" id="veStage"><div class="ve-stage-msg" id="veStageMsg">Загружаем видеодвижок…</div></div></section>'
      + '<aside class="ve-inspector" id="veInspector"></aside>'
      + '</div>'
      + '<div class="ve-transport">'
      + '<button type="button" class="ve-play" data-ve="play" aria-label="Воспроизвести">' + ICON.play + '</button>'
      + '<span class="ve-time"><b id="veTime">00:00.0</b> / <span id="veDuration">00:00.0</span></span>'
      + '<span class="ve-spacer"></span>'
      + '<button type="button" class="ve-tool" data-ve="split" disabled>' + ICON.split + '<span>Разрезать</span></button>'
      + '<button type="button" class="ve-tool" data-ve="delete" disabled>' + ICON.trash + '<span>Удалить</span></button>'
      + '<label class="ve-zoom" aria-label="Масштаб шкалы"><span>−</span><input type="range" id="veZoom" min="8" max="400" value="60"><span>+</span></label>'
      + '</div>'
      + '<div class="ve-timeline" id="veTimeline"><div class="ve-labels" id="veLabels"></div><div class="ve-scroll" id="veScroll"><div class="ve-canvas" id="veCanvas"></div></div></div>'
      + '<div class="ve-toast" id="veToast" hidden></div>'
      + '<div class="ve-modal" id="veModal" hidden></div>'
      + '</div>';
  }

  function toast(text) {
    const box = $('#veToast');
    box.textContent = text;
    box.hidden = !text;
    clearTimeout(toast.timer);
    if (text) toast.timer = setTimeout(() => { box.hidden = true; }, 4200);
  }

  function run(action) {
    try {
      const result = action();
      if (result && typeof result.then === 'function') return result.catch((error) => { toast(errorText(error)); return null; });
      return result;
    } catch (error) {
      toast(errorText(error));
      return null;
    }
  }

  // ---------------------------------------------------------------- render

  function project() { return editor.project; }
  function layout() { return editor.layout(); }

  function laneCount() {
    const used = project().audioClips.reduce((max, clip) => Math.max(max, clip.lane + 1), 0);
    return Math.min(MAX_AUDIO_LANES, Math.max(1, used + (used < MAX_AUDIO_LANES ? 1 : 0)));
  }

  function fitZoom() {
    const width = scroller.clientWidth - 40;
    const duration = Math.max(5, layout().duration);
    state.pps = Math.max(8, Math.min(400, width / duration));
    $('#veZoom').value = String(Math.round(state.pps));
  }

  function renderTimeline() {
    const p = project();
    const l = layout();
    if (state.autoFit) fitZoom();
    const pps = state.pps;
    const total = Math.max(l.duration, ...l.audio.map((item) => item.end), ...l.texts.map((item) => item.end), 5) + 4;
    const width = Math.ceil(total * pps);
    const lanes = laneCount();
    const step = pps >= 120 ? 1 : pps >= 40 ? 2 : pps >= 16 ? 5 : 10;
    let ruler = '';
    for (let t = 0; t <= total; t += step) ruler += '<span style="left:' + (t * pps) + 'px">' + formatTime(t) + '</span>';
    const sel = state.selection || {};
    const clipHtml = l.video.map((item, index) => {
      const clip = p.videoClips[index];
      const media = p.media[clip.mediaId] || {};
      return '<div class="ve-clip' + (sel.type === 'clip' && sel.id === clip.id ? ' is-selected' : '') + (clip.muted ? ' is-muted' : '') + '" data-clip="' + esc(clip.id) + '" style="left:' + (item.start * pps) + 'px;width:' + Math.max(6, item.duration * pps) + 'px">'
        + '<i class="ve-handle ve-handle-l" data-trim="start"></i><span><b>' + esc(media.name || 'Видео') + '</b><small>' + item.duration.toFixed(1) + ' с</small></span><i class="ve-handle ve-handle-r" data-trim="end"></i></div>';
    }).join('');
    const joins = l.video.slice(0, -1).map((item, index) => {
      const clip = p.videoClips[index];
      const has = !!(clip.transitionOut && clip.transitionOut.type);
      const at = item.end - item.transition / 2;
      return '<button type="button" class="ve-join' + (has ? ' has-transition' : '') + (sel.type === 'transition' && sel.id === clip.id ? ' is-selected' : '') + '" data-join="' + esc(clip.id) + '" style="left:' + (at * pps) + 'px" aria-label="Переход между клипами ' + (index + 1) + ' и ' + (index + 2) + '">' + ICON.join + '</button>';
    }).join('');
    const audioRows = [];
    for (let lane = 0; lane < lanes; lane += 1) {
      const items = p.audioClips.filter((clip) => clip.lane === lane).map((clip) => {
        const media = p.media[clip.mediaId] || {};
        return '<div class="ve-aclip' + (sel.type === 'audio' && sel.id === clip.id ? ' is-selected' : '') + (clip.muted ? ' is-muted' : '') + (clip.start >= l.duration && l.duration ? ' is-outside' : '') + '" data-audio="' + esc(clip.id) + '" style="left:' + (clip.start * pps) + 'px;width:' + Math.max(6, clipDuration(clip) * pps) + 'px">'
          + '<i class="ve-handle ve-handle-l" data-trim="start"></i><span><b>' + esc(media.name || 'Аудио') + '</b></span><i class="ve-handle ve-handle-r" data-trim="end"></i></div>';
      }).join('');
      audioRows.push('<div class="ve-lane ve-lane-audio" data-lane="audio" data-lane-index="' + lane + '" style="height:' + LANE.audio + 'px">' + items + '</div>');
    }
    const textItems = p.texts.map((text) => '<div class="ve-titem' + (sel.type === 'text' && sel.id === text.id ? ' is-selected' : '') + '" data-text="' + esc(text.id) + '" style="left:' + (text.start * pps) + 'px;width:' + Math.max(6, text.duration * pps) + 'px"><i class="ve-handle ve-handle-l" data-trim="start"></i><span>' + esc(text.text || 'Текст') + '</span><i class="ve-handle ve-handle-r" data-trim="end"></i></div>').join('');
    $('#veCanvas').style.width = width + 'px';
    $('#veCanvas').innerHTML = '<div class="ve-ruler" data-lane="ruler" style="height:' + LANE.ruler + 'px">' + ruler + '</div>'
      + '<div class="ve-lane ve-lane-text" data-lane="text" style="height:' + LANE.text + 'px">' + textItems + '</div>'
      + '<div class="ve-lane ve-lane-video" data-lane="video" style="height:' + LANE.video + 'px">' + clipHtml + joins + (p.videoClips.length ? '' : '<label class="ve-empty-lane"><input type="file" accept="video/*" multiple hidden data-ve-file="video">Загрузите видео, чтобы начать</label>') + '</div>'
      + audioRows.join('')
      + '<div class="ve-end" style="left:' + (l.duration * pps) + 'px"></div>'
      + '<div class="ve-playhead" id="vePlayhead" style="left:' + (state.time * pps) + 'px"></div>';
    const videoMuted = p.videoClips.length && p.videoClips.every((clip) => clip.muted);
    $('#veLabels').innerHTML = '<div style="height:' + LANE.ruler + 'px"></div>'
      + '<div class="ve-label" style="height:' + LANE.text + 'px">Текст</div>'
      + '<div class="ve-label" style="height:' + LANE.video + 'px"><span>Видео</span><button type="button" class="ve-mini" data-ve="video-audio" aria-label="' + (videoMuted ? 'Включить звук видео' : 'Выключить звук видео') + '" title="Звук видео">' + (videoMuted ? ICON.mute : ICON.speaker) + '</button></div>'
      + Array.from({ length: lanes }, (_, lane) => '<div class="ve-label" style="height:' + LANE.audio + 'px">Аудио ' + (lane + 1) + '</div>').join('');
    $('#veDuration').textContent = formatTime(l.duration, true);
  }

  function renderPlayhead() {
    const head = $('#vePlayhead');
    if (head) head.style.left = (state.time * state.pps) + 'px';
    $('#veTime').textContent = formatTime(state.time, true);
  }

  function renderToolbar() {
    const p = project();
    $('[data-ve="undo"]').disabled = !editor.canUndo();
    $('[data-ve="redo"]').disabled = !editor.canRedo();
    $('[data-ve="export"]').disabled = !p.videoClips.length || !!state.exporting;
    const sel = state.selection;
    $('[data-ve="split"]').disabled = !p.videoClips.length && !p.audioClips.length;
    $('[data-ve="delete"]').disabled = !sel;
    const play = $('[data-ve="play"]');
    play.innerHTML = state.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', state.playing ? 'Пауза' : 'Воспроизвести');
  }

  function field(label, control) {
    return '<label class="ve-field"><span>' + label + '</span>' + control + '</label>';
  }

  function num(name, value, attrs) {
    return '<input type="number" data-field="' + name + '" value="' + Number(value).toFixed(1) + '" step="0.1" ' + (attrs || '') + '>';
  }

  function slider(name, value, min, max, step, suffix) {
    return '<div class="ve-slider"><input type="range" data-field="' + name + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + value + '"><output>' + suffix(value) + '</output></div>';
  }

  function renderInspector(force) {
    if (!force && inspector.contains(document.activeElement) && document.activeElement !== inspector) return;
    const p = project();
    const l = layout();
    const sel = state.selection;
    let html = '';
    if (sel && sel.type === 'clip') {
      const index = p.videoClips.findIndex((clip) => clip.id === sel.id);
      const clip = p.videoClips[index];
      const media = p.media[clip.mediaId];
      html = '<h3>Видеоклип ' + (index + 1) + '</h3><p class="ve-muted">' + esc(media.name) + ' · исходник ' + media.duration.toFixed(1) + ' с' + (media.width ? ' · ' + media.width + '×' + media.height : '') + '</p>'
        + '<div class="ve-row">' + field('Начало (с)', num('sourceStart', clip.sourceStart, 'min="0" max="' + media.duration + '"')) + field('Конец (с)', num('sourceEnd', clip.sourceEnd, 'min="0" max="' + media.duration + '"')) + '</div>'
        + '<h4>Звук видео</h4><div class="ve-row ve-row-center"><button type="button" class="ve-toggle' + (clip.muted ? ' is-on' : '') + '" data-field="muted">' + (clip.muted ? ICON.mute + ' Без звука' : ICON.speaker + ' Звук включён') + '</button></div>'
        + field('Громкость', slider('volume', Math.round(clip.volume * 100), 0, 100, 1, (v) => v + '%'))
        + '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="split">' + ICON.split + ' Разрезать по курсору</button><button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить</button></div>';
    } else if (sel && sel.type === 'transition') {
      const index = p.videoClips.findIndex((clip) => clip.id === sel.id);
      const clip = p.videoClips[index];
      const current = clip && clip.transitionOut;
      const limit = Math.max(0.1, Math.min(clipDuration(clip), clipDuration(p.videoClips[index + 1])) / 2);
      const duration = current ? l.video[index].transition : Math.min(DEFAULT_TRANSITION_DURATION, limit);
      html = '<h3>Переход ' + (index + 1) + ' → ' + (index + 2) + '</h3>'
        + '<div class="ve-chips">' + '<button type="button" class="ve-chip' + (!current ? ' is-active' : '') + '" data-transition="">Без перехода</button>'
        + state.caps.transitions.map((item) => '<button type="button" class="ve-chip' + (current && current.type === item.id ? ' is-active' : '') + '" data-transition="' + esc(item.id) + '">' + esc(item.label) + '</button>').join('') + '</div>'
        + (state.caps.transitions.length ? '' : '<p class="ve-muted">Переходы недоступны в текущем видеодвижке.</p>')
        + (current ? field('Длительность', slider('transitionDuration', duration.toFixed(1), 0.1, limit.toFixed(1), 0.1, (v) => Number(v).toFixed(1) + ' с')) : '')
        + '<div class="ve-actions">' + (current ? '<button type="button" class="ve-btn" data-ve="preview-transition">▶ Просмотреть</button><button type="button" class="ve-btn ve-danger" data-transition="">Убрать переход</button>' : '') + '</div>';
    } else if (sel && sel.type === 'audio') {
      const clip = p.audioClips.find((item) => item.id === sel.id);
      const media = p.media[clip.mediaId];
      html = '<h3>Аудио</h3><p class="ve-muted">' + esc(media.name) + ' · исходник ' + media.duration.toFixed(1) + ' с</p>'
        + '<div class="ve-row">' + field('На шкале с (с)', num('start', clip.start, 'min="0"')) + field('Дорожка', '<select data-field="lane">' + Array.from({ length: MAX_AUDIO_LANES }, (_, i) => '<option value="' + i + '"' + (i === clip.lane ? ' selected' : '') + '>Аудио ' + (i + 1) + '</option>').join('') + '</select>') + '</div>'
        + '<div class="ve-row">' + field('Начало (с)', num('sourceStart', clip.sourceStart, 'min="0"')) + field('Конец (с)', num('sourceEnd', clip.sourceEnd, 'min="0" max="' + media.duration + '"')) + '</div>'
        + '<div class="ve-row ve-row-center"><button type="button" class="ve-toggle' + (clip.muted ? ' is-on' : '') + '" data-field="muted">' + (clip.muted ? ICON.mute + ' Без звука' : ICON.speaker + ' Звук включён') + '</button></div>'
        + field('Громкость', slider('volume', Math.round(clip.volume * 100), 0, 100, 1, (v) => v + '%'))
        + '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="split">' + ICON.split + ' Разрезать по курсору</button><button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить</button></div>';
    } else if (sel && sel.type === 'text') {
      const text = p.texts.find((item) => item.id === sel.id);
      html = '<h3>Текст</h3>'
        + field('Текст', '<textarea data-field="text" rows="3" maxlength="500">' + esc(text.text) + '</textarea>')
        + field('Шрифт', '<select data-field="fontFamily"><option value="">Стандартный</option>' + state.caps.fonts.map((font) => '<option value="' + esc(font.id) + '"' + (font.id === text.fontFamily ? ' selected' : '') + '>' + esc(font.label) + '</option>').join('') + '</select>')
        + '<div class="ve-row ve-row-center">'
        + '<button type="button" class="ve-toggle' + (text.bold ? ' is-on' : '') + '" data-field="bold"><b>Ж</b></button>'
        + '<button type="button" class="ve-toggle' + (text.italic ? ' is-on' : '') + '" data-field="italic"><i>К</i></button>'
        + ['left', 'center', 'right'].map((align) => '<button type="button" class="ve-toggle' + (text.align === align ? ' is-on' : '') + '" data-align="' + align + '">' + ({ left: '⇤', center: '↔', right: '⇥' })[align] + '</button>').join('')
        + '<input type="color" data-field="color" value="' + esc(text.color) + '" aria-label="Цвет текста">'
        + '</div>'
        + field('Размер', slider('fontSize', Math.round(text.fontSize * 100), 2, 30, 1, (v) => v + '%'))
        + field('По горизонтали', slider('x', Math.round(text.x * 100), 0, 100, 1, (v) => v + '%'))
        + field('По вертикали', slider('y', Math.round(text.y * 100), 0, 100, 1, (v) => v + '%'))
        + '<div class="ve-row ve-row-center"><button type="button" class="ve-toggle' + (text.background ? ' is-on' : '') + '" data-field="hasBackground">Подложка</button>' + (text.background ? '<input type="color" data-field="background" value="' + esc(text.background) + '" aria-label="Цвет подложки">' : '') + '</div>'
        + '<div class="ve-row">' + field('Появляется (с)', num('start', text.start, 'min="0"')) + field('Длительность (с)', num('duration', text.duration, 'min="0.1"')) + '</div>'
        + '<div class="ve-actions"><button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить текст</button></div>';
    } else {
      const settings = p.exportSettings;
      html = '<h3>Проект</h3>'
        + '<p class="ve-muted">' + p.videoClips.length + ' видео · ' + p.audioClips.length + ' аудио · ' + p.texts.length + ' текст · ' + formatTime(l.duration, true) + '</p>'
        + '<h4>Экспорт</h4>'
        + '<div class="ve-row">' + field('Размер кадра', '<output class="ve-out">' + (settings.width ? settings.width + '×' + settings.height : 'по первому видео') + '</output>') + field('Кадров/с', '<select data-field="fps">' + [24, 25, 30, 50, 60].map((fps) => '<option value="' + fps + '"' + (fps === settings.fps ? ' selected' : '') + '>' + fps + '</option>').join('') + '</select>') + '</div>'
        + '<p class="ve-muted">MP4 (H.264 + AAC). Размер кадра берётся из первого видео без уменьшения.</p>'
        + (state.caps.canExport ? '' : '<p class="ve-warn">' + esc(errorText({ code: state.caps.exportReason || 'export_unsupported' })) + '</p>')
        + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-ve="export"' + (p.videoClips.length ? '' : ' disabled') + '>Экспортировать видео</button></div>'
        + '<p class="ve-hint">Перетаскивайте клипы, чтобы менять порядок, тяните за края, чтобы обрезать. Нажмите на ' + ICON.join + ' между клипами, чтобы добавить переход.</p>';
    }
    inspector.innerHTML = html;
  }

  function render() {
    renderTimeline();
    renderToolbar();
    renderInspector();
    renderPlayhead();
  }

  function select(selection) {
    state.selection = selection;
    renderTimeline();
    renderToolbar();
    renderInspector(true);
    host.classList.toggle('ve-has-selection', !!selection);
  }

  // ------------------------------------------------------------- actions

  async function addFiles(files, kind) {
    const list = Array.from(files || []);
    for (const file of list) {
      const added = await run(() => (kind === 'audio' ? editor.addAudio(file, { start: state.time }) : editor.addVideo(file)));
      if (added) select({ type: kind === 'audio' ? 'audio' : 'clip', id: added });
    }
  }

  function splitAtPlayhead() {
    const p = project();
    const sel = state.selection;
    if (sel && sel.type === 'audio') { const id = run(() => editor.splitAudio(sel.id, state.time)); if (id) select({ type: 'audio', id }); return; }
    let clipId = sel && sel.type === 'clip' ? sel.id : '';
    if (!clipId) {
      const placed = layout().video.find((item) => state.time > item.start && state.time < item.end);
      clipId = placed ? placed.id : '';
    }
    if (!clipId) { toast(ERRORS.split_out_of_range); return; }
    const id = run(() => editor.splitClip(clipId, state.time));
    if (id) select({ type: 'clip', id });
    void p;
  }

  function deleteSelection() {
    const sel = state.selection;
    if (!sel) return;
    if (sel.type === 'clip') run(() => editor.removeClip(sel.id));
    else if (sel.type === 'audio') run(() => editor.removeAudio(sel.id));
    else if (sel.type === 'text') run(() => editor.removeText(sel.id));
    else if (sel.type === 'transition') run(() => editor.setTransition(sel.id, null));
    select(null);
  }

  function togglePlay() {
    if (state.playing) editor.pause();
    else run(() => editor.play());
  }

  async function startExport() {
    if (state.exporting) return;
    if (!state.caps.canExport) { toast(errorText({ code: state.caps.exportReason || 'export_unsupported' })); return; }
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.exporting = controller || {};
    renderToolbar();
    const modal = $('#veModal');
    modal.hidden = false;
    modal.innerHTML = '<div class="ve-dialog"><h3>Экспорт видео</h3><div class="ve-progress"><i id="veProgress" style="width:0%"></i></div><p id="veProgressText">Подготовка…</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="cancel-export">Отменить</button></div></div>';
    try {
      const result = await editor.exportVideo({
        signal: controller ? controller.signal : undefined,
        onProgress: (ratio) => {
          const bar = $('#veProgress');
          const label = $('#veProgressText');
          if (bar) bar.style.width = Math.round(ratio * 100) + '%';
          if (label) label.textContent = 'Кодирование: ' + Math.round(ratio * 100) + '%';
        },
      });
      const url = URL.createObjectURL(result.blob);
      modal.innerHTML = '<div class="ve-dialog"><h3>Видео готово</h3><video class="ve-result" src="' + url + '" controls playsinline></video>'
        + '<p class="ve-muted">' + esc(result.fileName) + ' · ' + (result.blob.size / 1048576).toFixed(1) + ' МБ</p>'
        + '<div class="ve-actions"><a class="ve-btn ve-primary" href="' + url + '" download="' + esc(result.fileName) + '" data-ve="download">Скачать MP4</a><button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div></div>';
      modal.dataset.url = url;
    } catch (error) {
      modal.innerHTML = '<div class="ve-dialog"><h3>Экспорт не завершён</h3><p class="ve-warn">' + esc(errorText(error)) + '</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div></div>';
      console.error('[video-editor] export', error);
    } finally {
      state.exporting = null;
      renderToolbar();
    }
  }

  function closeModal() {
    const modal = $('#veModal');
    if (modal.dataset.url) { URL.revokeObjectURL(modal.dataset.url); delete modal.dataset.url; }
    modal.hidden = true;
    modal.innerHTML = '';
  }

  // ---------------------------------------------------------- inspector

  function inspectorChange(target, live) {
    const sel = state.selection;
    if (!sel) {
      if (target.dataset.field === 'fps' && !live) run(() => editor.setExportSettings({ fps: Number(target.value) }));
      return;
    }
    const name = target.dataset.field;
    const value = target.type === 'range' || target.type === 'number' ? Number(target.value) : target.value;
    const output = target.parentElement && target.parentElement.querySelector('output');
    if (output && target.type === 'range') output.textContent = name === 'transitionDuration' ? value.toFixed(1) + ' с' : value + '%';
    if (live && target.type === 'range') return;
    if (sel.type === 'clip') {
      const clip = project().videoClips.find((item) => item.id === sel.id);
      if (name === 'sourceStart' || name === 'sourceEnd') run(() => editor.trimClip(sel.id, { sourceStart: name === 'sourceStart' ? value : clip.sourceStart, sourceEnd: name === 'sourceEnd' ? value : clip.sourceEnd }));
      if (name === 'volume') run(() => editor.setClipVolume(sel.id, value / 100));
    } else if (sel.type === 'audio') {
      const clip = project().audioClips.find((item) => item.id === sel.id);
      if (name === 'sourceStart' || name === 'sourceEnd') run(() => editor.trimAudio(sel.id, { sourceStart: name === 'sourceStart' ? value : clip.sourceStart, sourceEnd: name === 'sourceEnd' ? value : clip.sourceEnd }));
      if (name === 'start') run(() => editor.moveAudio(sel.id, { start: value }));
      if (name === 'lane') run(() => editor.moveAudio(sel.id, { lane: Number(value) }));
      if (name === 'volume') run(() => editor.setAudioVolume(sel.id, value / 100));
    } else if (sel.type === 'transition') {
      const clip = project().videoClips.find((item) => item.id === sel.id);
      if (name === 'transitionDuration' && clip && clip.transitionOut) run(() => editor.setTransition(sel.id, { type: clip.transitionOut.type, duration: value }));
    } else if (sel.type === 'text') {
      const patch = {};
      if (name === 'text') patch.text = value;
      else if (name === 'fontFamily') patch.fontFamily = value;
      else if (name === 'color' || name === 'background') patch[name] = value;
      else if (name === 'fontSize' || name === 'x' || name === 'y') patch[name] = value / 100;
      else if (name === 'start' || name === 'duration') patch[name] = value;
      if (Object.keys(patch).length) run(() => editor.updateText(sel.id, patch));
    }
  }

  inspector.addEventListener('input', (event) => {
    const target = event.target;
    if (!target.dataset.field) return;
    if (target.dataset.field === 'text') {
      clearTimeout(textTimer);
      textTimer = setTimeout(() => inspectorChange(target, false), 350);
      return;
    }
    if (target.type === 'range') inspectorChange(target, true);
  });
  inspector.addEventListener('change', (event) => {
    const target = event.target;
    if (target.dataset.field && target.dataset.field !== 'text') inspectorChange(target, false);
  });

  // ---------------------------------------------------- timeline gestures

  function timeAt(clientX) {
    const rect = $('#veCanvas').getBoundingClientRect();
    return Math.max(0, (clientX - rect.left) / state.pps);
  }

  function seek(time) {
    state.time = Math.max(0, Math.min(layout().duration, time));
    editor.seek(state.time);
    renderPlayhead();
  }

  function drag(event, handlers) {
    const startX = event.clientX;
    const startY = event.clientY;
    const target = event.currentTarget || event.target;
    let moved = false;
    try { target.setPointerCapture(event.pointerId); } catch (_) {}
    const move = (ev) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (!moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      moved = true;
      handlers.move(dx, dy, ev);
    };
    const up = (ev) => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      target.removeEventListener('pointercancel', up);
      handlers.end(moved, ev.clientX - startX, ev.clientY - startY, ev);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
    target.addEventListener('pointercancel', up);
  }

  $('#veCanvas').addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    const pps = state.pps;
    const handle = event.target.closest('[data-trim]');
    const clipNode = event.target.closest('[data-clip]');
    const audioNode = event.target.closest('[data-audio]');
    const textNode = event.target.closest('[data-text]');
    const joinNode = event.target.closest('[data-join]');
    if (joinNode) return;
    const p = project();
    if (clipNode) {
      const clip = p.videoClips.find((item) => item.id === clipNode.dataset.clip);
      const media = p.media[clip.mediaId];
      const startLeft = clipNode.offsetLeft;
      const startWidth = clipNode.offsetWidth;
      if (state.selection?.id !== clip.id) select({ type: 'clip', id: clip.id });
      const node = $('[data-clip="' + CSS.escape(clip.id) + '"]');
      if (handle) {
        const edge = handle.dataset.trim;
        drag(event, {
          move(dx) {
            if (edge === 'start') {
              const delta = Math.max(-clip.sourceStart, Math.min(clipDuration(clip) - MIN_CLIP, dx / pps));
              node.style.width = (startWidth - delta * pps) + 'px';
            } else {
              const delta = Math.max(-(clipDuration(clip) - MIN_CLIP), Math.min(media.duration - clip.sourceEnd, dx / pps));
              node.style.width = (startWidth + delta * pps) + 'px';
            }
          },
          end(moved, dx) {
            if (!moved) return;
            const delta = dx / pps;
            run(() => editor.trimClip(clip.id, edge === 'start' ? { sourceStart: clip.sourceStart + delta } : { sourceEnd: clip.sourceEnd + delta }));
          },
        });
      } else {
        drag(event, {
          move(dx) { node.style.left = (startLeft + dx) + 'px'; node.classList.add('is-dragging'); },
          end(moved, dx, dy, ev) {
            if (!moved) { seek(timeAt(ev.clientX)); return; }
            const center = (startLeft + dx + startWidth / 2) / pps;
            const others = layout().video.filter((item) => item.id !== clip.id);
            const index = others.filter((item) => (item.start + item.end) / 2 < center).length;
            run(() => editor.moveClip(clip.id, index));
            render();
          },
        });
      }
      return;
    }
    if (audioNode) {
      const clip = p.audioClips.find((item) => item.id === audioNode.dataset.audio);
      const media = p.media[clip.mediaId];
      if (state.selection?.id !== clip.id) select({ type: 'audio', id: clip.id });
      const node = $('[data-audio="' + CSS.escape(clip.id) + '"]');
      const startLeft = node.offsetLeft;
      const startWidth = node.offsetWidth;
      if (handle) {
        const edge = handle.dataset.trim;
        drag(event, {
          move(dx) {
            if (edge === 'start') {
              const delta = Math.max(-Math.min(clip.sourceStart, clip.start), Math.min(clipDuration(clip) - MIN_CLIP, dx / pps));
              node.style.left = (startLeft + delta * pps) + 'px';
              node.style.width = (startWidth - delta * pps) + 'px';
            } else {
              const delta = Math.max(-(clipDuration(clip) - MIN_CLIP), Math.min(media.duration - clip.sourceEnd, dx / pps));
              node.style.width = (startWidth + delta * pps) + 'px';
            }
          },
          end(moved, dx) {
            if (!moved) return;
            const delta = dx / pps;
            run(() => editor.trimAudio(clip.id, edge === 'start' ? { sourceStart: clip.sourceStart + Math.max(-clip.start, delta) } : { sourceEnd: clip.sourceEnd + delta }));
          },
        });
      } else {
        drag(event, {
          move(dx, dy) { node.style.left = Math.max(0, startLeft + dx) + 'px'; node.style.transform = 'translateY(' + dy + 'px)'; node.classList.add('is-dragging'); },
          end(moved, dx, dy, ev) {
            if (!moved) { seek(timeAt(ev.clientX)); return; }
            const lane = Math.max(0, Math.min(MAX_AUDIO_LANES - 1, clip.lane + Math.round(dy / LANE.audio)));
            run(() => editor.moveAudio(clip.id, { start: Math.max(0, clip.start + dx / pps), lane }));
            render();
          },
        });
      }
      return;
    }
    if (textNode) {
      const text = p.texts.find((item) => item.id === textNode.dataset.text);
      if (state.selection?.id !== text.id) select({ type: 'text', id: text.id });
      const node = $('[data-text="' + CSS.escape(text.id) + '"]');
      const startLeft = node.offsetLeft;
      const startWidth = node.offsetWidth;
      const edge = handle ? handle.dataset.trim : '';
      drag(event, {
        move(dx) {
          if (edge === 'start') { const delta = Math.max(-text.start * pps, Math.min(startWidth - MIN_CLIP * pps, dx)); node.style.left = (startLeft + delta) + 'px'; node.style.width = (startWidth - delta) + 'px'; }
          else if (edge === 'end') node.style.width = Math.max(MIN_CLIP * pps, startWidth + dx) + 'px';
          else node.style.left = Math.max(0, startLeft + dx) + 'px';
        },
        end(moved, dx, dy, ev) {
          if (!moved) { if (!edge) seek(timeAt(ev.clientX)); return; }
          const delta = dx / pps;
          if (edge === 'start') { const d = Math.max(-text.start, Math.min(text.duration - MIN_CLIP, delta)); run(() => editor.updateText(text.id, { start: text.start + d, duration: text.duration - d })); }
          else if (edge === 'end') run(() => editor.updateText(text.id, { duration: Math.max(MIN_CLIP, text.duration + delta) }));
          else run(() => editor.updateText(text.id, { start: Math.max(0, text.start + delta) }));
          render();
        },
      });
      return;
    }
    // Scrubbing on the ruler or empty lanes.
    if (event.target.closest('.ve-empty-lane')) return;
    // The ruler only moves the playhead; an empty lane also clears the selection.
    if (state.selection && !event.target.closest('.ve-ruler')) select(null);
    seek(timeAt(event.clientX));
    drag(event, { move: (dx, dy, ev) => seek(timeAt(ev.clientX)), end: () => {} });
  });

  // ------------------------------------------------------------- clicks

  host.addEventListener('click', (event) => {
    const target = event.target;
    const action = target.closest('[data-ve]');
    const join = target.closest('[data-join]');
    const transition = target.closest('[data-transition]');
    if (join) { select({ type: 'transition', id: join.dataset.join }); return; }
    if (transition && state.selection && state.selection.type === 'transition') {
      const clipId = state.selection.id;
      const type = transition.dataset.transition;
      const clip = project().videoClips.find((item) => item.id === clipId);
      const duration = clip && clip.transitionOut ? clip.transitionOut.duration : DEFAULT_TRANSITION_DURATION;
      run(() => editor.setTransition(clipId, type ? { type, duration } : null));
      renderInspector(true);
      return;
    }
    const toggle = target.closest('.ve-toggle');
    if (toggle && state.selection) {
      const sel = state.selection;
      const name = toggle.dataset.field;
      if (sel.type === 'clip' && name === 'muted') run(() => editor.muteClip(sel.id, !project().videoClips.find((c) => c.id === sel.id).muted));
      if (sel.type === 'audio' && name === 'muted') run(() => editor.muteAudio(sel.id, !project().audioClips.find((c) => c.id === sel.id).muted));
      if (sel.type === 'text') {
        const text = project().texts.find((item) => item.id === sel.id);
        if (name === 'bold' || name === 'italic') run(() => editor.updateText(sel.id, { [name]: !text[name] }));
        if (name === 'hasBackground') run(() => editor.updateText(sel.id, { background: text.background ? '' : '#000000' }));
        if (toggle.dataset.align) run(() => editor.updateText(sel.id, { align: toggle.dataset.align }));
      }
      renderInspector(true);
      return;
    }
    if (!action) return;
    const name = action.dataset.ve;
    if (name === 'close') { if (onClose) onClose(); return; }
    if (name === 'undo') { editor.undo(); return; }
    if (name === 'redo') { editor.redo(); return; }
    if (name === 'play') { togglePlay(); return; }
    if (name === 'split') { splitAtPlayhead(); return; }
    if (name === 'delete') { deleteSelection(); return; }
    if (name === 'add-text') {
      const l = layout();
      const start = state.time < l.duration ? state.time : 0;
      const id = run(() => editor.addText({ start, duration: Math.max(MIN_CLIP, Math.min(3, (l.duration || 3) - start)) }));
      if (id) select({ type: 'text', id });
      return;
    }
    if (name === 'video-audio') { const p = project(); run(() => editor.muteVideoAudio(!p.videoClips.every((clip) => clip.muted))); return; }
    if (name === 'export') { startExport(); return; }
    if (name === 'cancel-export') { if (state.exporting && state.exporting.abort) state.exporting.abort(); return; }
    if (name === 'close-modal') { closeModal(); return; }
    if (name === 'preview-transition') {
      const index = project().videoClips.findIndex((clip) => clip.id === state.selection.id);
      const placed = layout().video[index];
      seek(Math.max(0, placed.end - placed.transition - 1));
      run(() => editor.play());
    }
  });

  host.addEventListener('change', (event) => {
    const input = event.target.closest('[data-ve-file]');
    if (!input || !input.files || !input.files.length) return;
    const files = Array.from(input.files);
    input.value = '';
    addFiles(files, input.dataset.veFile);
  });

  $('#veZoom').addEventListener('input', (event) => {
    state.autoFit = false;
    state.pps = Number(event.target.value);
    renderTimeline();
  });

  host.addEventListener('keydown', (event) => {
    if (event.target.closest('input, textarea, select')) return;
    if (event.key === ' ') { event.preventDefault(); togglePlay(); }
    else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteSelection(); }
    else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); if (event.shiftKey) editor.redo(); else editor.undo(); }
    else if (event.key.toLowerCase() === 's' && !event.ctrlKey && !event.metaKey) { event.preventDefault(); splitAtPlayhead(); }
  });
  host.tabIndex = -1;

  // ------------------------------------------------------------ editor events

  editor.on('change', () => {
    const sel = state.selection;
    const p = project();
    if (sel && !((sel.type === 'clip' || sel.type === 'transition') ? p.videoClips.some((c) => c.id === sel.id) : sel.type === 'audio' ? p.audioClips.some((c) => c.id === sel.id) : p.texts.some((t) => t.id === sel.id))) state.selection = null;
    state.time = Math.min(state.time, layout().duration);
    render();
  });
  editor.on('time', (time) => { state.time = time; renderPlayhead(); });
  editor.on('playstate', (playing) => { state.playing = playing; renderToolbar(); });
  editor.on('error', ({ error }) => { console.error('[video-editor]', error); toast(errorText(error)); });
  const resizeObserver = new ResizeObserver(() => {
    if (!host.contains(scroller)) { resizeObserver.disconnect(); return; }
    if (state.autoFit) renderTimeline();
  });
  resizeObserver.observe(scroller);

  render();

  return {
    stage,
    setEngineReady(caps, info) {
      state.caps = caps || state.caps;
      const msg = $('#veStageMsg');
      if (msg) msg.remove();
      $('#veEngine').textContent = info || '';
      render();
      renderInspector(true);
    },
    setEngineError(error) {
      const msg = $('#veStageMsg');
      if (msg) { msg.textContent = errorText(error); msg.classList.add('is-error'); }
      $('#veEngine').textContent = '';
    },
    addFiles,
    focus: () => host.focus(),
  };
}
