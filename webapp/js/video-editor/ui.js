// SYLVEX Video Editor UI. It talks to the SYLVEX editor core (editor.js)
// and the SYLVEX action layer (actions.js) and reads the SYLVEX project; it
// never touches an engine SDK or names AI providers or models.
import { MAX_AUDIO_LANES, MIN_CLIP, DEFAULT_TRANSITION_DURATION, MAX_IMAGE_DURATION, clipDuration, createProject } from './project.js';
import { availableTransitions, transitionById, transitionPreview } from './transitions.js';
import { createFrameCache, createWaveformCache, frameTiles, frameKey } from './media.js';

const LANE = { ruler: 26, text: 34, video: 64, speech: 30, audio: 46 };
const ZOOM = { min: 4, max: 400 };
const ROLE_LABEL = { audio: 'Аудио', original: 'Звук видео', music: 'Музыка', voice: 'Голос', sfx: 'Эффекты' };
const ERRORS = {
  login_required: 'Войдите в SYLVEX, чтобы открыть видеоредактор.',
  config_failed: 'Не удалось получить настройки видеоредактора. Попробуйте ещё раз.',
  engine_load_failed: 'Не удалось загрузить видеодвижок. Проверьте соединение и попробуйте ещё раз.',
  engine_init_failed: 'Видеодвижок не запустился в этом браузере. Попробуйте Chrome или Edge на компьютере.',
  license_invalid: 'Лицензия видеодвижка не принята. Сообщите администратору SYLVEX.',
  browser_unsupported: 'Этот браузер не поддерживает редактирование видео. Откройте SYLVEX в Chrome или Edge на компьютере.',
  export_unsupported: 'Экспорт видео не поддерживается этим браузером.',
  export_failed: 'Не удалось экспортировать видео. Попробуйте ещё раз или уменьшите длительность.',
  export_cancelled: 'Экспорт отменён.',
  nothing_to_export: 'Добавьте хотя бы один видеоклип или изображение.',
  not_video_file: 'Это не видеофайл.',
  not_audio_file: 'Это не аудиофайл.',
  not_image_file: 'Это не изображение.',
  unsupported_file: 'Поддерживаются видео, изображения и аудио.',
  media_unsupported: 'Этот файл не открывается в редакторе. Попробуйте MP4 (H.264), MOV, JPG, PNG, MP3, M4A или WAV.',
  media_duration_unknown: 'Не удалось определить длительность файла.',
  media_metadata_timeout: 'Файл слишком долго открывается. Попробуйте другой.',
  media_has_no_audio: 'В этом видео нет звука.',
  split_out_of_range: 'Поставьте курсор внутрь выбранного клипа, не у самого края.',
  transition_needs_next_clip: 'Переход ставится между двумя соседними клипами.',
  range_too_short: 'Отметьте начало и конец фрагмента.',
  range_outside_clip: 'Фрагмент не пересекается с выбранным аудио.',
  no_original_version: 'У этого клипа нет другой версии.',
  no_speech: 'В расшифровке нет речи для субтитров.',
  upload_failed: 'Файл не загрузился в SYLVEX. Нажмите на клип, чтобы повторить.',
  upload_too_large: 'Файл больше лимита загрузки (видео до 200 МБ, фото и аудио до 50 МБ). Он останется только в этой сессии.',
  media_not_uploaded: 'Файл ещё не загружен в SYLVEX.',
  select_image: 'Выберите изображение на шкале.',
  select_video: 'Выберите видеоклип на шкале.',
  active_generation: 'Дождитесь окончания текущей генерации.',
  insufficient_balance: 'Недостаточно токенов. Пополните баланс.',
  subscription_required: 'AI-инструменты доступны после активации подписки.',
  generation_failed: 'Не удалось выполнить действие. Попробуйте ещё раз.',
  network_error: 'Нет соединения. Проверьте интернет.',
  project_save_failed: 'Проект не сохранился. Повторим автоматически.',
  project_not_found: 'Проект не найден или ссылка устарела.',
  transcribe_failed: 'Не удалось расшифровать речь. Попробуйте ещё раз.',
  enhance_prepare_failed: 'Не удалось подготовить видео к улучшению.',
};

const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const errorText = (error) => {
  if (error && error.serverMessage) return error.serverMessage;
  const code = String((error && (error.code || error.message)) || '');
  return ERRORS[code] || ERRORS[code.split(':')[0]] || 'Что-то пошло не так. Попробуйте ещё раз.';
};
const formatTime = (seconds, precise) => {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return String(minutes).padStart(2, '0') + ':' + (precise ? rest.toFixed(1).padStart(4, '0') : String(Math.floor(rest)).padStart(2, '0'));
};
const credits = (value) => (value ? Math.ceil(value) + ' ⚡' : '');
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
  copy: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  text: '<svg viewBox="0 0 24 24"><path d="M5 6V4h14v2M12 4v16M9 20h6"/></svg>',
  spark: '<svg viewBox="0 0 24 24"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  zoomIn: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5M8.5 11h5M11 8.5v5"/></svg>',
  zoomOut: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5M8.5 11h5"/></svg>',
  fit: '<svg viewBox="0 0 24 24"><path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/></svg>',
  markIn: '<svg viewBox="0 0 24 24"><path d="M9 4H6v16h3M13 12h7M16 9l-3 3 3 3"/></svg>',
  markOut: '<svg viewBox="0 0 24 24"><path d="M15 4h3v16h-3M11 12H4M8 9l3 3-3 3"/></svg>',
  cut: '<svg viewBox="0 0 24 24"><path d="M5 5h14M5 19h14M9 9l6 6M15 9l-6 6"/></svg>',
  speech: '<svg viewBox="0 0 24 24"><path d="M4 5h16v10H9l-5 4z"/><path d="M8 9h8M8 12h5"/></svg>',
  detach: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M17 8l4 4-4 4"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-4"/></svg>',
  link: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
};

// AI actions of the editor: names of what they do, no provider names.
const AI_ACTIONS = [
  { id: 'generateVideo', label: 'Generate Video', hint: 'Видео по описанию или из выбранного кадра' },
  { id: 'animatePhoto', label: 'Animate Photo', hint: 'Оживить выбранное изображение' },
  { id: 'generateMusic', label: 'Generate Music', hint: 'Музыка по описанию на аудиодорожку' },
  { id: 'voiceOver', label: 'Voice-over', hint: 'Озвучка текста голосом из библиотеки' },
  { id: 'enhanceVideo', label: 'Enhance Video', hint: 'Улучшить качество выбранного клипа' },
  { id: 'generateSubtitles', label: 'Generate Subtitles', hint: 'Субтитры из речи в ролике' },
  { id: 'transcribe', label: 'Transcribe Speech', hint: 'Текст речи с таймкодами для монтажа' },
];

export function mountVideoEditorUI(host, editor, { onClose, actions, services, environment } = {}) {
  const env = environment || { telegram: false, nativeDownload: false, openLink: (url) => window.open(url, '_blank', 'noopener'), downloadFile: async () => false };
  const state = {
    selection: null, pps: 60, autoFit: true, time: 0, playing: false, exporting: null, range: null, panel: '',
    caps: { transitionKinds: [], fonts: [], canExport: false, images: true }, ready: false,
    work: { job: null, transcribing: false, save: 'idle', uploads: {} },
  };
  host.innerHTML = shell();
  const $ = (selector) => host.querySelector(selector);
  const stage = $('#veStage');
  const scroller = $('#veScroll');
  const inspector = $('#veInspector');
  let textTimer = 0;
  let uiSaveTimer = 0;
  let jobTimer = 0;

  const frames = createFrameCache({
    onFrame: (mediaId, time, url) => {
      if (!url) return;
      host.querySelectorAll('[data-frame="' + CSS.escape(frameKey(mediaId, time)) + '"]').forEach((node) => { node.style.backgroundImage = 'url("' + url + '")'; });
    },
  });
  const waves = createWaveformCache({ onReady: () => paintWaves() });

  function shell() {
    return '<div class="ve" id="ve">'
      + '<header class="ve-head">'
      + '<button type="button" class="ve-icon" data-ve="close" aria-label="Закрыть редактор">' + ICON.close + '</button>'
      + '<div class="ve-title"><input id="veName" maxlength="120" aria-label="Название проекта" value=""><small id="veStatus"></small></div>'
      + '<span class="ve-spacer"></span>'
      + '<button type="button" class="ve-icon" data-ve="undo" aria-label="Отменить" disabled>' + ICON.undo + '</button>'
      + '<button type="button" class="ve-icon" data-ve="redo" aria-label="Повторить" disabled>' + ICON.redo + '</button>'
      + '<button type="button" class="ve-icon" data-ve="projects" aria-label="Проекты" title="Проекты">' + ICON.folder + '</button>'
      + '<label class="ve-btn" title="Видео, изображения и аудио"><input type="file" accept="video/*,image/*,audio/*" multiple hidden data-ve-file="media">' + ICON.plus + '<span>Медиа</span></label>'
      + '<button type="button" class="ve-btn" data-ve="add-text">' + ICON.text + '<span>Текст</span></button>'
      + '<button type="button" class="ve-btn ve-ai" data-ve="ai-menu" aria-haspopup="true">' + ICON.spark + '<span>AI</span></button>'
      + '<button type="button" class="ve-btn ve-primary" data-ve="export" disabled>Экспорт</button>'
      + '</header>'
      + '<div class="ve-body">'
      + '<section class="ve-preview"><div class="ve-stage" id="veStage"><div class="ve-stage-msg" id="veStageMsg">Загружаем видеодвижок…</div></div></section>'
      + '<aside class="ve-inspector" id="veInspector"></aside>'
      + '</div>'
      + '<div class="ve-work" id="veWork" hidden></div>'
      + '<div class="ve-transport">'
      + '<button type="button" class="ve-play" data-ve="play" aria-label="Воспроизвести">' + ICON.play + '</button>'
      + '<span class="ve-time"><b id="veTime">00:00.0</b> / <span id="veDuration">00:00.0</span></span>'
      + '<span class="ve-spacer"></span>'
      + '<div class="ve-group">'
      + '<button type="button" class="ve-tool" data-ve="mark-in" title="Начало фрагмента (I)">' + ICON.markIn + '<span>Начало</span></button>'
      + '<button type="button" class="ve-tool" data-ve="mark-out" title="Конец фрагмента (O)">' + ICON.markOut + '<span>Конец</span></button>'
      + '<button type="button" class="ve-tool" data-ve="remove-range" disabled title="Удалить отмеченный фрагмент">' + ICON.cut + '<span>Удалить фрагмент</span></button>'
      + '</div><div class="ve-group">'
      + '<button type="button" class="ve-tool" data-ve="split" disabled title="Разрезать по курсору (S)">' + ICON.split + '<span>Разрезать</span></button>'
      + '<button type="button" class="ve-tool" data-ve="duplicate" disabled title="Дублировать (Ctrl+D)">' + ICON.copy + '<span>Дублировать</span></button>'
      + '<button type="button" class="ve-tool" data-ve="delete" disabled title="Удалить (Delete)">' + ICON.trash + '<span>Удалить</span></button>'
      + '</div><div class="ve-group ve-zoom" aria-label="Масштаб шкалы">'
      + '<button type="button" class="ve-mini" data-ve="zoom-out" aria-label="Уменьшить масштаб">' + ICON.zoomOut + '</button>'
      + '<input type="range" id="veZoom" min="0" max="1000" value="500" aria-label="Масштаб">'
      + '<button type="button" class="ve-mini" data-ve="zoom-in" aria-label="Увеличить масштаб">' + ICON.zoomIn + '</button>'
      + '<button type="button" class="ve-mini" data-ve="zoom-fit" aria-label="Вместить весь ролик" title="Вместить весь ролик">' + ICON.fit + '</button>'
      + '</div></div>'
      + '<div class="ve-timeline" id="veTimeline"><div class="ve-labels" id="veLabels"></div><div class="ve-scroll" id="veScroll"><div class="ve-canvas" id="veCanvas"></div></div></div>'
      + '<div class="ve-menu" id="veMenu" hidden></div>'
      + '<div class="ve-toast" id="veToast" hidden></div>'
      + '<div class="ve-modal" id="veModal" hidden></div>'
      + '</div>';
  }

  function toast(text) {
    const box = $('#veToast');
    box.textContent = text;
    box.hidden = !text;
    clearTimeout(toast.timer);
    if (text) toast.timer = setTimeout(() => { box.hidden = true; }, 4800);
  }

  function run(action) {
    try {
      const result = action();
      if (result && typeof result.then === 'function') return result.catch((error) => { console.error('[video-editor]', error); toast(errorText(error)); return null; });
      return result;
    } catch (error) {
      toast(errorText(error));
      return null;
    }
  }

  // ---------------------------------------------------------------- zoom

  const zoomToSlider = (pps) => Math.round(1000 * Math.log(pps / ZOOM.min) / Math.log(ZOOM.max / ZOOM.min));
  const sliderToZoom = (value) => ZOOM.min * Math.pow(ZOOM.max / ZOOM.min, Number(value) / 1000);

  function fitZoom() {
    const width = scroller.clientWidth - 40;
    const duration = Math.max(5, layout().duration);
    state.pps = Math.max(ZOOM.min, Math.min(ZOOM.max, width / duration));
  }

  // Zoom changes the scale of the timeline only; `anchor` (seconds) stays
  // under the same screen position.
  function setZoom(pps, anchorTime, anchorX) {
    const value = Math.max(ZOOM.min, Math.min(ZOOM.max, pps));
    const time = anchorTime == null ? state.time : anchorTime;
    const offset = anchorX == null ? (time * state.pps - scroller.scrollLeft) : anchorX;
    state.autoFit = false;
    state.pps = value;
    renderTimeline();
    scroller.scrollLeft = Math.max(0, time * value - offset);
    rememberZoom();
  }

  function rememberZoom() {
    clearTimeout(uiSaveTimer);
    uiSaveTimer = setTimeout(() => editor.setUiState({ pps: state.pps, autoFit: state.autoFit }), 600);
  }

  // ---------------------------------------------------------------- render

  function project() { return editor.project; }
  function layout() { return editor.layout(); }

  function laneCount() {
    const used = project().audioClips.reduce((max, clip) => Math.max(max, clip.lane + 1), 0);
    return Math.min(MAX_AUDIO_LANES, Math.max(1, used + (used < MAX_AUDIO_LANES ? 1 : 0)));
  }

  function hasTranscript() {
    return Object.keys(project().transcripts || {}).length > 0;
  }

  function uploadBadge(mediaId) {
    const upload = state.work.uploads[mediaId];
    if (!upload) return '';
    if (upload.failed) return '<em class="ve-badge ve-badge-error" data-retry="' + esc(mediaId) + '" title="' + esc(errorText({ code: upload.failed })) + '">Не загружено' + (upload.failed === 'upload_too_large' ? '' : ' · повторить') + '</em>';
    return '<em class="ve-up"><i style="width:' + Math.round(upload.progress * 100) + '%"></i></em>';
  }

  function thumbsHtml(clip, media, width) {
    if (!media) return '';
    if (media.kind === 'image') {
      const url = media.previewUrl || media.url;
      return '<span class="ve-thumbs ve-thumbs-image" style="background-image:url(&quot;' + esc(url) + '&quot;)"></span>';
    }
    const aspect = media.width && media.height ? media.width / media.height : 16 / 9;
    const tile = Math.max(28, Math.round((LANE.video - 10) * aspect));
    const times = frameTiles(clip, width, tile);
    return '<span class="ve-thumbs">' + times.map((time) => {
      const url = frames.get(media, time);
      return '<i data-frame="' + esc(frameKey(media.id, time)) + '" style="width:' + tile + 'px' + (url ? ';background-image:url(&quot;' + url + '&quot;)' : '') + '"></i>';
    }).join('') + '</span>';
  }

  function waveHtml(media, clip, cls) {
    if (!media || !(media.kind === 'audio' || (media.kind === 'video' && media.hasAudio))) return '';
    return '<canvas class="ve-wave' + (cls ? ' ' + cls : '') + '" data-wave="' + esc(media.id) + '" data-from="' + clip.sourceStart + '" data-to="' + clip.sourceEnd + '"></canvas>';
  }

  function renderTimeline() {
    const p = project();
    const l = layout();
    if (state.autoFit) fitZoom();
    const pps = state.pps;
    $('#veZoom').value = String(zoomToSlider(pps));
    const total = Math.max(l.duration, ...l.audio.map((item) => item.end), ...l.texts.map((item) => item.end), 5) + 4;
    const width = Math.ceil(total * pps);
    const lanes = laneCount();
    const speechLane = hasTranscript();
    const step = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].find((value) => value * pps >= 64) || 600;
    let ruler = '';
    for (let t = 0; t <= total; t += step) ruler += '<span style="left:' + (t * pps) + 'px">' + formatTime(t, step < 1) + '</span>';
    const sel = state.selection || {};
    const clipHtml = l.video.map((item, index) => {
      const clip = p.videoClips[index];
      const media = p.media[clip.mediaId] || {};
      const w = Math.max(6, item.duration * pps);
      const badge = media.origin && media.origin !== 'upload' ? '<em class="ve-badge">' + esc(media.label || 'AI') + '</em>' : '';
      return '<div class="ve-clip' + (media.kind === 'image' ? ' is-image' : '') + (sel.type === 'clip' && sel.id === clip.id ? ' is-selected' : '') + (clip.muted ? ' is-muted' : '') + '" data-clip="' + esc(clip.id) + '" style="left:' + (item.start * pps) + 'px;width:' + w + 'px">'
        + thumbsHtml(clip, media, w)
        + (clip.muted ? '' : waveHtml(media, clip, 've-wave-mini'))
        + '<i class="ve-handle ve-handle-l" data-trim="start"></i><span class="ve-clip-info"><b>' + esc(media.name || 'Видео') + '</b><small>' + item.duration.toFixed(1) + ' с</small>' + badge + '</span>' + uploadBadge(media.id) + '<i class="ve-handle ve-handle-r" data-trim="end"></i></div>';
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
        return '<div class="ve-aclip ve-role-' + esc(clip.role || 'audio') + (sel.type === 'audio' && sel.id === clip.id ? ' is-selected' : '') + (clip.muted ? ' is-muted' : '') + (clip.start >= l.duration && l.duration ? ' is-outside' : '') + '" data-audio="' + esc(clip.id) + '" style="left:' + (clip.start * pps) + 'px;width:' + Math.max(6, clipDuration(clip) * pps) + 'px">'
          + waveHtml(media, clip)
          + '<i class="ve-handle ve-handle-l" data-trim="start"></i><span class="ve-clip-info" title="' + esc(ROLE_LABEL[clip.role] || 'Аудио') + '"><b>' + esc(media.name || 'Аудио') + '</b></span>' + uploadBadge(media.id) + '<i class="ve-handle ve-handle-r" data-trim="end"></i></div>';
      }).join('');
      audioRows.push('<div class="ve-lane ve-lane-audio" data-lane="audio" data-lane-index="' + lane + '" style="height:' + LANE.audio + 'px">' + items + '</div>');
    }
    const textItems = p.texts.map((text) => '<div class="ve-titem' + (text.role === 'subtitle' ? ' is-subtitle' : '') + (sel.type === 'text' && sel.id === text.id ? ' is-selected' : '') + '" data-text="' + esc(text.id) + '" style="left:' + (text.start * pps) + 'px;width:' + Math.max(6, text.duration * pps) + 'px"><i class="ve-handle ve-handle-l" data-trim="start"></i><span>' + esc(text.text || 'Текст') + '</span><i class="ve-handle ve-handle-r" data-trim="end"></i></div>').join('');
    const speechItems = speechLane ? editor.transcript().map((item) => '<button type="button" class="ve-speech is-' + item.kind + '" data-speech-start="' + item.start + '" data-speech-end="' + item.end + '" style="left:' + (item.start * pps) + 'px;width:' + Math.max(3, (item.end - item.start) * pps) + 'px" title="' + esc(item.kind === 'silence' ? 'Нет речи · ' + (item.end - item.start).toFixed(1) + ' с' : item.text) + '">' + esc(item.kind === 'silence' ? 'нет речи' : item.text) + '</button>').join('') : '';
    const range = state.range && state.range.end > state.range.start ? '<div class="ve-range" style="left:' + (state.range.start * pps) + 'px;width:' + ((state.range.end - state.range.start) * pps) + 'px"></div>'
      : (state.range ? '<div class="ve-range-mark" style="left:' + (state.range.start * pps) + 'px"></div>' : '');
    const emptyVideo = p.videoClips.length ? '' : '<label class="ve-empty-lane"><input type="file" accept="video/*,image/*" multiple hidden data-ve-file="media">Загрузите видео или изображения</label>';
    $('#veCanvas').style.width = width + 'px';
    $('#veCanvas').innerHTML = '<div class="ve-ruler" data-lane="ruler" style="height:' + LANE.ruler + 'px">' + ruler + '</div>'
      + '<div class="ve-lane ve-lane-text" data-lane="text" style="height:' + LANE.text + 'px">' + textItems + '</div>'
      + '<div class="ve-lane ve-lane-video" data-lane="video" style="height:' + LANE.video + 'px">' + clipHtml + joins + emptyVideo + '</div>'
      + (speechLane ? '<div class="ve-lane ve-lane-speech" data-lane="speech" style="height:' + LANE.speech + 'px">' + speechItems + '</div>' : '')
      + audioRows.join('')
      + range
      + '<div class="ve-end" style="left:' + (l.duration * pps) + 'px"></div>'
      + '<div class="ve-playhead" id="vePlayhead" style="left:' + (state.time * pps) + 'px"></div>';
    const videoMuted = p.videoClips.length && p.videoClips.every((clip) => clip.muted);
    $('#veLabels').innerHTML = '<div style="height:' + LANE.ruler + 'px"></div>'
      + '<div class="ve-label" style="height:' + LANE.text + 'px">Текст</div>'
      + '<div class="ve-label" style="height:' + LANE.video + 'px"><span>Видео</span><button type="button" class="ve-mini" data-ve="video-audio" aria-label="' + (videoMuted ? 'Включить звук видео' : 'Выключить звук видео') + '" title="Звук видео">' + (videoMuted ? ICON.mute : ICON.speaker) + '</button></div>'
      + (speechLane ? '<div class="ve-label" style="height:' + LANE.speech + 'px"><span>Речь</span><button type="button" class="ve-mini" data-ve="transcript" aria-label="Расшифровка речи" title="Расшифровка речи">' + ICON.speech + '</button></div>' : '')
      + Array.from({ length: lanes }, (_, lane) => '<div class="ve-label" style="height:' + LANE.audio + 'px">Аудио ' + (lane + 1) + '</div>').join('');
    $('#veDuration').textContent = formatTime(l.duration, true);
    paintWaves();
  }

  function paintWaves() {
    const p = project();
    host.querySelectorAll('canvas[data-wave]').forEach((canvas) => {
      const media = p.media[canvas.dataset.wave];
      if (!media) return;
      waves.request(media);
      waves.draw(canvas, media.id, Number(canvas.dataset.from), Number(canvas.dataset.to), canvas.classList.contains('ve-wave-mini') ? 'rgba(255,255,255,.5)' : 'rgba(255,255,255,.55)');
    });
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
    $('[data-ve="export"]').disabled = !p.videoClips.length || !!state.exporting || !state.ready;
    const sel = state.selection;
    $('[data-ve="split"]').disabled = !p.videoClips.length && !p.audioClips.length;
    $('[data-ve="delete"]').disabled = !sel;
    $('[data-ve="duplicate"]').disabled = !sel || sel.type === 'transition';
    $('[data-ve="remove-range"]').disabled = !(state.range && state.range.end - state.range.start >= MIN_CLIP);
    const play = $('[data-ve="play"]');
    play.innerHTML = state.playing ? ICON.pause : ICON.play;
    play.setAttribute('aria-label', state.playing ? 'Пауза' : 'Воспроизвести');
    const name = $('#veName');
    if (document.activeElement !== name) name.value = p.name || '';
  }

  function renderStatus() {
    const work = state.work;
    const status = { saving: 'Сохраняем…', saved: 'Сохранено', waiting: 'Ждём загрузку файлов…', error: 'Не сохранено', partial: 'Сохранено без незагруженных файлов' }[work.save] || '';
    $('#veStatus').textContent = status;
    $('#veStatus').classList.toggle('is-error', work.save === 'error');
    const box = $('#veWork');
    const items = [];
    if (work.job) items.push('<span class="ve-spin"></span><b>' + esc(work.job.label) + '</b><small id="veJobTime">' + formatTime((Date.now() - work.job.startedAt) / 1000) + '</small><small>' + (work.job.status === 'queued' ? 'в очереди' : 'создаём…') + '</small>');
    if (work.transcribing) items.push('<span class="ve-spin"></span><b>Расшифровываем речь…</b>');
    const uploading = Object.values(work.uploads).filter((item) => !item.failed);
    if (uploading.length) items.push('<span class="ve-spin"></span><b>Загружаем в SYLVEX: ' + uploading.length + '</b><small>' + Math.round(uploading.reduce((sum, item) => sum + item.progress, 0) / uploading.length * 100) + '%</small>');
    box.hidden = !items.length;
    box.innerHTML = items.map((item) => '<div class="ve-work-item">' + item + '</div>').join('');
    clearInterval(jobTimer);
    if (work.job) jobTimer = setInterval(() => { const node = $('#veJobTime'); if (node && state.work.job) node.textContent = formatTime((Date.now() - state.work.job.startedAt) / 1000); }, 1000);
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

  function aiButton(action, label, extra) {
    return '<button type="button" class="ve-btn ve-ai-btn" data-ai="' + action + '"' + (extra || '') + '>' + ICON.spark + ' ' + label + '</button>';
  }

  function framePair(clipA, clipB) {
    const p = project();
    const side = (clip, atEnd) => {
      if (!clip) return {};
      const media = p.media[clip.mediaId];
      if (!media) return {};
      if (media.kind === 'image') return { url: media.previewUrl || media.url };
      const time = Math.round(Math.max(clip.sourceStart, atEnd ? clip.sourceEnd - 0.5 : clip.sourceStart + 0.5) * 2) / 2;
      return { url: frames.get(media, time), key: frameKey(media.id, time) };
    };
    return [side(clipA, true), side(clipB, false)];
  }

  function inspectorClip(sel) {
    const p = project();
    const index = p.videoClips.findIndex((clip) => clip.id === sel.id);
    const clip = p.videoClips[index];
    const media = p.media[clip.mediaId];
    const isImage = media.kind === 'image';
    const version = media.derivedFrom ? '<div class="ve-version"><span>' + ICON.spark + ' Улучшенная версия</span><button type="button" class="ve-btn" data-ve="revert-version">' + ICON.back + ' Вернуть оригинал</button></div>' : '';
    let html = '<h3>' + (isImage ? 'Изображение' : 'Видеоклип') + ' ' + (index + 1) + '</h3><p class="ve-muted">' + esc(media.name) + (isImage ? '' : ' · исходник ' + media.duration.toFixed(1) + ' с') + (media.width ? ' · ' + media.width + '×' + media.height : '') + '</p>' + version;
    if (isImage) {
      html += field('Длительность (с)', num('duration', clipDuration(clip), 'min="0.1" max="' + MAX_IMAGE_DURATION + '"'))
        + '<div class="ve-ai-row">' + aiButton('animatePhoto', 'Animate Photo') + aiButton('generateVideo', 'Generate Video') + '</div>';
    } else {
      html += '<div class="ve-row">' + field('Начало (с)', num('sourceStart', clip.sourceStart, 'min="0" max="' + media.duration + '"')) + field('Конец (с)', num('sourceEnd', clip.sourceEnd, 'min="0" max="' + media.duration + '"')) + '</div>'
        + '<h4>Звук видео</h4>'
        + (media.hasAudio ? '<div class="ve-row ve-row-center"><button type="button" class="ve-toggle' + (clip.muted ? ' is-on' : '') + '" data-field="muted">' + (clip.muted ? ICON.mute + ' Без звука' : ICON.speaker + ' Звук включён') + '</button><button type="button" class="ve-toggle" data-ve="detach-audio">' + ICON.detach + ' Отделить звук</button></div>'
          + field('Громкость', slider('volume', Math.round(clip.volume * 100), 0, 100, 1, (v) => v + '%')) : '<p class="ve-muted">В этом видео нет звука.</p>')
        + '<div class="ve-ai-row">' + aiButton('enhanceVideo', 'Enhance Video') + aiButton('generateVideo', 'Generate Video') + '</div>';
    }
    return html + '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="split">' + ICON.split + ' Разрезать</button><button type="button" class="ve-btn" data-ve="duplicate">' + ICON.copy + ' Дублировать</button><button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить</button></div>';
  }

  function inspectorTransition(sel) {
    const p = project();
    const l = layout();
    const index = p.videoClips.findIndex((clip) => clip.id === sel.id);
    const clip = p.videoClips[index];
    const next = p.videoClips[index + 1];
    const current = clip && clip.transitionOut;
    const currentItem = current ? transitionById(current.type) : null;
    const limit = Math.max(0.1, Math.min(clipDuration(clip), clipDuration(next)) / 2);
    const duration = current ? l.video[index].transition : Math.min(DEFAULT_TRANSITION_DURATION, limit);
    const library = availableTransitions(state.caps.transitionKinds);
    const [a, b] = framePair(clip, next);
    const groups = [];
    library.forEach((item) => { let group = groups.find((g) => g.name === item.group); if (!group) { group = { name: item.group, items: [] }; groups.push(group); } group.items.push(item); });
    let html = '<h3>Переход ' + (index + 1) + ' → ' + (index + 2) + '</h3><p class="ve-muted">' + (currentItem ? esc(currentItem.label) + ' · ' + duration.toFixed(1) + ' с' : 'Без перехода — клипы идут встык') + '</p>';
    if (current) {
      html += field('Длительность', slider('transitionDuration', duration.toFixed(1), 0.1, limit.toFixed(1), 0.1, (v) => Number(v).toFixed(1) + ' с'));
      if (currentItem && currentItem.colorable) html += '<div class="ve-row ve-row-center"><span class="ve-muted">Цвет</span><input type="color" data-field="transitionColor" value="' + esc(current.color || currentItem.color) + '" aria-label="Цвет перехода"></div>';
      html += '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="preview-transition">' + ICON.play + ' Просмотреть</button><button type="button" class="ve-btn ve-danger" data-transition="">Убрать переход</button></div>';
    }
    if (!library.length) return html + '<p class="ve-muted">Переходы недоступны в текущем видеодвижке.</p>';
    html += groups.map((group) => '<h4>' + esc(group.name) + '</h4><div class="ve-tgrid">' + group.items.map((item) => '<button type="button" class="ve-tcard' + (currentItem && currentItem.id === item.id ? ' is-active' : '') + '" data-transition="' + esc(item.id) + '" title="' + esc(item.label) + '">' + transitionPreview(item, a, b) + '<span>' + esc(item.label) + '</span></button>').join('') + '</div>').join('');
    return html;
  }

  function inspectorAudio(sel) {
    const p = project();
    const clip = p.audioClips.find((item) => item.id === sel.id);
    const media = p.media[clip.mediaId];
    const rangeHit = state.range && state.range.end > state.range.start && state.range.start < clip.start + clipDuration(clip) && state.range.end > clip.start;
    return '<h3>' + esc(ROLE_LABEL[clip.role] || 'Аудио') + '</h3><p class="ve-muted">' + esc(media.name) + ' · исходник ' + media.duration.toFixed(1) + ' с</p>'
      + '<div class="ve-row">' + field('Тип дорожки', '<select data-field="role">' + Object.entries(ROLE_LABEL).map(([id, label]) => '<option value="' + id + '"' + (clip.role === id ? ' selected' : '') + '>' + label + '</option>').join('') + '</select>')
      + field('Дорожка', '<select data-field="lane">' + Array.from({ length: MAX_AUDIO_LANES }, (_, i) => '<option value="' + i + '"' + (i === clip.lane ? ' selected' : '') + '>Аудио ' + (i + 1) + '</option>').join('') + '</select>') + '</div>'
      + field('На шкале с (с)', num('start', clip.start, 'min="0"'))
      + '<div class="ve-row">' + field('Начало (с)', num('sourceStart', clip.sourceStart, 'min="0"')) + field('Конец (с)', num('sourceEnd', clip.sourceEnd, 'min="0" max="' + media.duration + '"')) + '</div>'
      + '<div class="ve-row ve-row-center"><button type="button" class="ve-toggle' + (clip.muted ? ' is-on' : '') + '" data-field="muted">' + (clip.muted ? ICON.mute + ' Без звука' : ICON.speaker + ' Звук включён') + '</button></div>'
      + field('Громкость', slider('volume', Math.round(clip.volume * 100), 0, 100, 1, (v) => v + '%'))
      + '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="split">' + ICON.split + ' Разрезать</button><button type="button" class="ve-btn" data-ve="duplicate">' + ICON.copy + ' Дублировать</button>'
      + (rangeHit ? '<button type="button" class="ve-btn" data-ve="remove-audio-range">' + ICON.cut + ' Вырезать фрагмент</button>' : '')
      + '<button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить</button></div>';
  }

  function inspectorText(sel) {
    const text = project().texts.find((item) => item.id === sel.id);
    return '<h3>' + (text.role === 'subtitle' ? 'Субтитр' : 'Текст') + '</h3>'
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
      + '<div class="ve-actions"><button type="button" class="ve-btn" data-ve="duplicate">' + ICON.copy + ' Дублировать</button><button type="button" class="ve-btn ve-danger" data-ve="delete">' + ICON.trash + ' Удалить</button></div>';
  }

  function inspectorTranscript() {
    const items = editor.transcript();
    const sources = Object.keys(project().transcripts || {}).length;
    let html = '<div class="ve-panel-head"><h3>Расшифровка речи</h3><button type="button" class="ve-mini" data-ve="panel-close" aria-label="Закрыть">' + ICON.close + '</button></div>'
      + '<p class="ve-muted">Только для монтажа: в видео не попадает. Нажмите на фразу, чтобы перейти к ней.</p>';
    if (!sources) return html + '<div class="ve-actions">' + aiButton('transcribe', 'Transcribe Speech') + '</div>';
    html += '<div class="ve-actions">' + aiButton('generateSubtitles', 'Generate Subtitles') + (transcribeMissing() ? aiButton('transcribe', 'Расшифровать новые клипы') : '') + '</div>';
    html += '<ol class="ve-transcript">' + items.map((item) => '<li class="is-' + item.kind + (state.time >= item.start && state.time < item.end ? ' is-current' : '') + '"><button type="button" data-speech-start="' + item.start + '" data-speech-end="' + item.end + '"><time>' + formatTime(item.start, true) + '</time><span>' + (item.kind === 'silence' ? 'нет речи · ' + (item.end - item.start).toFixed(1) + ' с' : esc(item.text)) + '</span></button>'
      + (item.kind === 'silence' ? '<button type="button" class="ve-mini" data-remove-pause="' + item.start + ':' + item.end + '" title="Удалить паузу" aria-label="Удалить паузу">' + ICON.cut + '</button>' : '') + '</li>').join('') + '</ol>';
    if (!items.length) html += '<p class="ve-muted">Речь не найдена.</p>';
    return html;
  }

  function inspectorProject() {
    const p = project();
    const l = layout();
    const settings = p.exportSettings;
    const media = Object.values(p.media);
    const ORIGIN = { upload: 'Загружено', generate_video: 'Generate Video', animate_photo: 'Animate Photo', generate_music: 'Generate Music', voice_over: 'Voice-over', enhance_video: 'Enhance Video' };
    return '<h3>Проект</h3>'
      + '<p class="ve-muted">' + p.videoClips.length + ' клип(ов) · ' + p.audioClips.length + ' аудио · ' + p.texts.length + ' текст · ' + formatTime(l.duration, true) + '</p>'
      + '<div class="ve-actions">' + aiButton('transcribe', hasTranscript() ? 'Расшифровка речи' : 'Transcribe Speech') + '</div>'
      + '<h4>Медиа проекта</h4>'
      + (media.length ? '<ul class="ve-assets">' + media.map((item) => '<li><span class="ve-asset-kind ve-kind-' + item.kind + '"></span><span class="ve-asset-name"><b>' + esc(item.name) + '</b><small>' + esc(ORIGIN[item.origin] || 'Медиа') + (item.duration ? ' · ' + item.duration.toFixed(1) + ' с' : '') + (state.work.uploads[item.id] ? (state.work.uploads[item.id].failed ? ' · не загружено' : ' · загрузка') : '') + '</small></span><button type="button" class="ve-mini" data-place="' + esc(item.id) + '" title="Добавить на шкалу" aria-label="Добавить на шкалу">' + ICON.plus + '</button></li>').join('') + '</ul>' : '<p class="ve-muted">Добавьте видео, изображения или аудио кнопкой «Медиа».</p>')
      + '<h4>Экспорт</h4>'
      + '<div class="ve-row">' + field('Размер кадра', '<output class="ve-out">' + (settings.width ? settings.width + '×' + settings.height : 'по первому кадру') + '</output>') + field('Кадров/с', '<select data-field="fps">' + [24, 25, 30, 50, 60].map((fps) => '<option value="' + fps + '"' + (fps === settings.fps ? ' selected' : '') + '>' + fps + '</option>').join('') + '</select>') + '</div>'
      + '<p class="ve-muted">MP4 (H.264 + AAC) в исходном разрешении.</p>'
      + (state.caps.canExport ? '' : '<p class="ve-warn">' + esc(exportUnavailableText()) + '</p>')
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-ve="export"' + (p.videoClips.length ? '' : ' disabled') + '>Экспортировать видео</button></div>'
      + '<p class="ve-hint">Перетаскивайте клипы, чтобы менять порядок, тяните за края, чтобы обрезать. ' + ICON.join + ' между клипами — переход. Ctrl + колесо мыши — масштаб.</p>';
  }

  function renderInspector(force) {
    if (!force && inspector.contains(document.activeElement) && document.activeElement !== inspector) return;
    const sel = state.selection;
    let html;
    if (state.panel === 'transcript') html = inspectorTranscript();
    else if (sel && sel.type === 'clip') html = inspectorClip(sel);
    else if (sel && sel.type === 'transition') html = inspectorTransition(sel);
    else if (sel && sel.type === 'audio') html = inspectorAudio(sel);
    else if (sel && sel.type === 'text') html = inspectorText(sel);
    else html = inspectorProject();
    inspector.innerHTML = html;
    const busy = !!state.work.job;
    inspector.querySelectorAll('[data-ai]').forEach((button) => { if (busy && !['transcribe', 'generateSubtitles'].includes(button.dataset.ai)) button.disabled = true; });
  }

  function render() {
    renderTimeline();
    renderToolbar();
    renderInspector();
    renderPlayhead();
  }

  function select(selection) {
    state.selection = selection;
    if (selection) state.panel = '';
    renderTimeline();
    renderToolbar();
    renderInspector(true);
    host.classList.toggle('ve-has-selection', !!selection || !!state.panel);
  }

  function showPanel(panel) {
    state.panel = panel;
    state.selection = null;
    host.classList.toggle('ve-has-selection', !!panel);
    renderTimeline();
    renderToolbar();
    renderInspector(true);
  }

  // ------------------------------------------------------------- actions

  async function addFiles(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    const sel = state.selection;
    const at = sel && sel.type === 'clip' ? project().videoClips.findIndex((clip) => clip.id === sel.id) + 1 : undefined;
    const added = await run(() => actions.importFiles(list, { at, start: state.time }));
    if (added && added.length) {
      const last = added[added.length - 1];
      select({ type: last.kind === 'audio' ? 'audio' : 'clip', id: last.id });
    }
  }

  function splitAtPlayhead() {
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
  }

  function duplicateSelection() {
    const sel = state.selection;
    if (!sel) return;
    if (sel.type === 'clip') { const id = run(() => editor.duplicateClip(sel.id)); if (id) select({ type: 'clip', id }); }
    if (sel.type === 'audio') { const id = run(() => editor.duplicateAudio(sel.id)); if (id) select({ type: 'audio', id }); }
    if (sel.type === 'text') { const id = run(() => editor.duplicateText(sel.id)); if (id) select({ type: 'text', id }); }
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

  function markRange(edge) {
    const time = state.time;
    const range = state.range ? Object.assign({}, state.range) : { start: time, end: time };
    if (edge === 'in') { range.start = time; if (range.end < time) range.end = time; }
    else { range.end = time; if (range.start > time) range.start = time; }
    state.range = range;
    renderTimeline();
    renderToolbar();
  }

  function removeRange() {
    const range = state.range;
    if (!range) return;
    if (run(() => editor.removeRange(range.start, range.end)) !== null) {
      state.range = null;
      seek(range.start);
    }
    render();
  }

  function togglePlay() {
    if (state.playing) editor.pause();
    else run(() => editor.play());
  }

  // ---------------------------------------------------------------- export

  function exportUnavailableText() {
    if (env.telegram) return 'В приложении Telegram экспорт видео недоступен. Проект сохранён — откройте его в браузере, чтобы экспортировать.';
    return errorText({ code: state.caps.exportReason || 'export_unsupported' }) + ' Откройте SYLVEX в Chrome или Edge на компьютере.';
  }

  async function openInBrowser() {
    const link = await run(() => actions.browserLink());
    if (!link) return;
    if (!env.openLink(link)) {
      showModal('<h3>Ссылка на проект</h3><p class="ve-muted">Откройте её в браузере:</p><input class="ve-link" readonly value="' + esc(link) + '"><div class="ve-actions"><button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div>');
    }
  }

  async function startExport() {
    if (state.exporting) return;
    if (!state.caps.canExport) {
      showModal('<h3>Экспорт</h3><p class="ve-warn">' + esc(exportUnavailableText()) + '</p><div class="ve-actions">'
        + (env.telegram ? '<button type="button" class="ve-btn ve-primary" data-ve="open-browser">' + ICON.link + ' Открыть в браузере</button>' : '')
        + '<button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div>');
      return;
    }
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    state.exporting = controller || {};
    renderToolbar();
    showModal('<h3>Экспорт видео</h3><div class="ve-progress"><i id="veProgress" style="width:0%"></i></div><p id="veProgressText">Подготовка…</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="cancel-export">Отменить</button></div>');
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
      const save = env.telegram
        ? '<button type="button" class="ve-btn ve-primary" data-ve="save-export">Сохранить видео</button>'
        : '<a class="ve-btn ve-primary" href="' + url + '" download="' + esc(result.fileName) + '" data-ve="download">Скачать MP4</a>';
      showModal('<h3>Видео готово</h3><video class="ve-result" src="' + url + '" controls playsinline></video>'
        + '<p class="ve-muted">' + esc(result.fileName) + ' · ' + (result.blob.size / 1048576).toFixed(1) + ' МБ</p>'
        + '<div class="ve-actions">' + save + '<button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div>', { url });
      state.exported = result;
    } catch (error) {
      showModal('<h3>Экспорт не завершён</h3><p class="ve-warn">' + esc(errorText(error)) + '</p><div class="ve-actions">'
        + (env.telegram ? '<button type="button" class="ve-btn" data-ve="open-browser">' + ICON.link + ' Открыть в браузере</button>' : '')
        + '<button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div>');
      console.error('[video-editor] export', error);
    } finally {
      state.exporting = null;
      renderToolbar();
    }
  }

  // Telegram cannot save a blob from the page: the file goes to SYLVEX
  // storage first and Telegram saves it from that link.
  async function saveExportInTelegram(button) {
    const result = state.exported;
    if (!result) return;
    button.disabled = true;
    button.textContent = 'Готовим файл…';
    try {
      const link = await actions.uploadExport(result.blob, result.fileName);
      const saved = env.nativeDownload ? await env.downloadFile(link, result.fileName) : false;
      if (!saved) env.openLink(link);
      button.textContent = 'Сохранено';
    } catch (error) {
      toast(errorText(error));
      button.disabled = false;
      button.textContent = 'Сохранить видео';
    }
  }

  // ----------------------------------------------------------------- modal

  function showModal(inner, { url, wide } = {}) {
    const modal = $('#veModal');
    if (modal.dataset.url) { URL.revokeObjectURL(modal.dataset.url); delete modal.dataset.url; }
    modal.hidden = false;
    modal.innerHTML = '<div class="ve-dialog' + (wide ? ' is-wide' : '') + '" role="dialog" aria-modal="true">' + inner + '</div>';
    if (url) modal.dataset.url = url;
    return modal.firstElementChild;
  }

  function closeModal() {
    const modal = $('#veModal');
    if (modal.dataset.url) { URL.revokeObjectURL(modal.dataset.url); delete modal.dataset.url; }
    const audio = modal.querySelector('audio');
    if (audio) audio.pause();
    modal.hidden = true;
    modal.innerHTML = '';
    state.exported = null;
  }

  // -------------------------------------------------------------- AI menu

  function toggleMenu(open) {
    const menu = $('#veMenu');
    const show = open == null ? menu.hidden : open;
    menu.hidden = !show;
    if (!show) return;
    const busy = !!state.work.job;
    menu.innerHTML = '<div class="ve-menu-list" role="menu">' + AI_ACTIONS.map((item) => '<button type="button" role="menuitem" data-ai="' + item.id + '"' + (busy && !['transcribe', 'generateSubtitles'].includes(item.id) ? ' disabled' : '') + '><b>' + ICON.spark + ' ' + esc(item.label) + '</b><small>' + esc(item.hint) + '</small></button>').join('')
      + (busy ? '<p class="ve-muted">Идёт генерация: ' + esc(state.work.job.label) + '</p>' : '') + '</div>';
  }

  const selectedClip = () => {
    const sel = state.selection;
    if (!sel || sel.type !== 'clip') return null;
    const clip = project().videoClips.find((item) => item.id === sel.id);
    return clip ? { clip, media: project().media[clip.mediaId] } : null;
  };

  function priceLine(id) {
    return '<p class="ve-price" id="' + id + '"><span class="ve-spin"></span> Считаем стоимость…</p>';
  }

  function setPrice(id, value, note) {
    const node = host.querySelector('#' + id);
    if (!node) return;
    node.innerHTML = value ? 'Стоимость: <b>' + credits(value) + '</b>' + (note ? ' · ' + esc(note) : '') : (note ? esc(note) : 'Стоимость покажем после запуска.');
  }

  async function openAi(action) {
    toggleMenu(false);
    const config = await run(() => services.actions());
    if (!config) return;
    if (action === 'generateVideo') return dialogGenerateVideo(config.generateVideo);
    if (action === 'animatePhoto') return dialogAnimate(config.animatePhoto);
    if (action === 'generateMusic') return dialogMusic();
    if (action === 'voiceOver') return dialogVoice();
    if (action === 'enhanceVideo') return dialogEnhance(config.enhanceVideo);
    if (action === 'generateSubtitles') return dialogSubtitles(config.transcribe);
    if (action === 'transcribe') return dialogTranscribe(config.transcribe);
    return null;
  }

  // Runs an AI action in the background; its result arrives as a project
  // asset and gets selected.
  function launch(promise, done) {
    closeModal();
    renderInspector(true);
    promise.then((id) => {
      if (id && done) done(id);
    }).catch((error) => { console.error('[video-editor] action', error); toast(errorText(error)); });
  }

  function dialogGenerateVideo(config) {
    const picked = selectedClip();
    const source = picked && (picked.media.kind === 'image' || picked.media.kind === 'video') ? picked : null;
    const durations = config.durations || [5];
    const box = showModal('<h3>' + ICON.spark + ' Generate Video</h3>'
      + field('Что должно происходить в видео', '<textarea id="veAiPrompt" rows="4" maxlength="2000" placeholder="Например: камера медленно облетает героя на закате"></textarea>')
      + (source ? '<div class="ve-chips" role="radiogroup" aria-label="Исходник"><button type="button" class="ve-chip is-active" data-src="clip">' + (source.media.kind === 'image' ? 'Из выбранного изображения' : 'С выбранным видео') + '</button><button type="button" class="ve-chip" data-src="none">Только по описанию</button></div>' : '<p class="ve-muted">Выберите изображение или клип на шкале, чтобы использовать его как основу.</p>')
      + '<div class="ve-chips" role="radiogroup" aria-label="Длительность">' + durations.map((value, i) => '<button type="button" class="ve-chip' + (value === (config.duration || durations[0]) || (!durations.includes(config.duration) && i === 0) ? ' is-active' : '') + '" data-duration="' + value + '">' + value + ' с</button>').join('') + '</div>'
      + priceLine('vePrice')
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="generateVideo" disabled>Создать видео</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    const input = () => {
      const useSource = source && box.querySelector('[data-src].is-active') && box.querySelector('[data-src].is-active').dataset.src === 'clip';
      const duration = Number(box.querySelector('[data-duration].is-active').dataset.duration);
      return { prompt: box.querySelector('#veAiPrompt').value, duration, sourceClipId: useSource ? source.clip.id : '' };
    };
    const reprice = async () => {
      const value = input();
      const media = value.sourceClipId ? source.media : null;
      const price = await services.estimateVideo({ prompt: value.prompt || 'video', duration: value.duration, width: project().settings.width, height: project().settings.height, imageUrl: media && media.kind === 'image' ? 'x' : '', videoUrl: media && media.kind === 'video' ? 'x' : '', videoDuration: media ? media.duration : 0 });
      setPrice('vePrice', price);
    };
    box.addEventListener('click', (event) => {
      const chip = event.target.closest('.ve-chip');
      if (chip) { chip.parentElement.querySelectorAll('.ve-chip').forEach((node) => node.classList.toggle('is-active', node === chip)); reprice(); }
      if (event.target.closest('[data-run]')) launch(actions.generateVideo(input()), (id) => { select({ type: 'clip', id }); toast('Видео добавлено на шкалу'); });
    });
    box.querySelector('#veAiPrompt').addEventListener('input', (event) => { box.querySelector('[data-run]').disabled = !event.target.value.trim(); });
    reprice();
    box.querySelector('#veAiPrompt').focus();
  }

  function dialogAnimate(config) {
    const picked = selectedClip();
    if (!picked || picked.media.kind !== 'image') {
      showModal('<h3>' + ICON.spark + ' Animate Photo</h3><p class="ve-muted">' + ERRORS.select_image + ' Загрузите фото кнопкой «Медиа», нажмите на него на шкале и снова выберите Animate Photo.</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="close-modal">Понятно</button></div>');
      return;
    }
    const box = showModal('<h3>' + ICON.spark + ' Animate Photo</h3>'
      + '<div class="ve-src" style="background-image:url(&quot;' + esc(picked.media.previewUrl || picked.media.url) + '&quot;)"></div>'
      + field('Как оживить (необязательно)', '<textarea id="veAiPrompt" rows="3" maxlength="' + (config.promptMaxLength || 250) + '" placeholder="Например: волосы развеваются на ветру"></textarea>')
      + '<p class="ve-price">Стоимость: <b>' + credits(config.credits) + '</b> · видео ' + (config.duration || 5) + ' с</p>'
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="animate">Оживить фото</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    box.querySelector('[data-run]').addEventListener('click', () => launch(actions.animatePhoto({ clipId: picked.clip.id, prompt: box.querySelector('#veAiPrompt').value }), (id) => { select({ type: 'clip', id }); toast('Ожившее фото добавлено на шкалу'); }));
  }

  function dialogMusic() {
    const box = showModal('<h3>' + ICON.spark + ' Generate Music</h3>'
      + field('Какая музыка нужна', '<textarea id="veAiPrompt" rows="3" maxlength="1000" placeholder="Например: спокойный эмбиент для путешествия"></textarea>')
      + '<div class="ve-row ve-row-center"><button type="button" class="ve-toggle" data-vocal>С вокалом</button><span class="ve-muted">Без вокала — фоновая музыка</span></div>'
      + priceLine('vePrice')
      + '<p class="ve-muted">Трек встанет на свободную аудиодорожку с позиции курсора.</p>'
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="music" disabled>Создать музыку</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    const vocal = () => box.querySelector('[data-vocal]').classList.contains('is-on');
    const reprice = async () => setPrice('vePrice', await services.estimateMusic({ prompt: box.querySelector('#veAiPrompt').value || 'music', vocal: vocal() }));
    box.querySelector('[data-vocal]').addEventListener('click', (event) => { event.currentTarget.classList.toggle('is-on'); reprice(); });
    box.querySelector('#veAiPrompt').addEventListener('input', (event) => { box.querySelector('[data-run]').disabled = !event.target.value.trim(); });
    box.querySelector('[data-run]').addEventListener('click', () => launch(actions.generateMusic({ prompt: box.querySelector('#veAiPrompt').value, vocal: vocal(), start: state.time }), (id) => { select({ type: 'audio', id }); toast('Музыка добавлена на аудиодорожку'); }));
    reprice();
  }

  async function dialogVoice() {
    const box = showModal('<h3>' + ICON.spark + ' Voice-over</h3>'
      + field('Текст озвучки', '<textarea id="veAiPrompt" rows="4" maxlength="5000" placeholder="Текст, который прочитает голос"></textarea>')
      + '<div class="ve-voice-head"><input id="veVoiceSearch" placeholder="Поиск голоса" aria-label="Поиск голоса"><div class="ve-chips" role="radiogroup"><button type="button" class="ve-chip is-active" data-gender="">Все</button><button type="button" class="ve-chip" data-gender="female">Женские</button><button type="button" class="ve-chip" data-gender="male">Мужские</button></div></div>'
      + '<ul class="ve-voices" id="veVoices"><li class="ve-muted"><span class="ve-spin"></span> Загружаем голоса…</li></ul>'
      + priceLine('vePrice')
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="voice" disabled>Озвучить</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div><audio id="veVoicePreview" hidden></audio>', { wide: true });
    let voices = [];
    let chosen = null;
    let gender = '';
    let priceTimer = 0;
    const text = () => box.querySelector('#veAiPrompt').value.trim();
    const update = () => { box.querySelector('[data-run]').disabled = !(text() && chosen); };
    const list = () => {
      const query = box.querySelector('#veVoiceSearch').value.trim().toLowerCase();
      const shown = voices.filter((voice) => (!gender || voice.gender === gender) && (!query || (voice.name + ' ' + voice.accent + ' ' + voice.description).toLowerCase().includes(query))).slice(0, 120);
      box.querySelector('#veVoices').innerHTML = shown.map((voice) => '<li class="' + (chosen && chosen.id === voice.id ? 'is-active' : '') + '"><button type="button" class="ve-voice" data-voice="' + esc(voice.id) + '"><b>' + esc(voice.name) + '</b><small>' + esc([voice.gender === 'female' ? 'женский' : voice.gender === 'male' ? 'мужской' : '', voice.accent, voice.description].filter(Boolean).join(' · ')) + '</small></button>'
        + (voice.previewUrl ? '<button type="button" class="ve-mini" data-preview="' + esc(voice.id) + '" aria-label="Прослушать">' + ICON.play + '</button>' : '') + '</li>').join('') || '<li class="ve-muted">Голоса не найдены.</li>';
    };
    const reprice = () => {
      clearTimeout(priceTimer);
      priceTimer = setTimeout(async () => setPrice('vePrice', text() && chosen ? await services.estimateVoice({ text: text(), voiceId: chosen.id, voiceName: chosen.name }) : 0, text() && chosen ? '' : 'Введите текст и выберите голос'), 400);
    };
    box.addEventListener('click', (event) => {
      const voice = event.target.closest('[data-voice]');
      const preview = event.target.closest('[data-preview]');
      const chip = event.target.closest('[data-gender]');
      if (voice) { chosen = voices.find((item) => item.id === voice.dataset.voice) || null; list(); update(); reprice(); }
      if (preview) { const item = voices.find((v) => v.id === preview.dataset.preview); const audio = box.querySelector('#veVoicePreview'); if (item) { audio.src = item.previewUrl; audio.play().catch(() => {}); } }
      if (chip) { gender = chip.dataset.gender; chip.parentElement.querySelectorAll('.ve-chip').forEach((node) => node.classList.toggle('is-active', node === chip)); list(); }
      if (event.target.closest('[data-run]')) launch(actions.voiceOver({ text: text(), voiceId: chosen.id, voiceName: chosen.name, start: state.time }), (id) => { select({ type: 'audio', id }); toast('Озвучка добавлена на аудиодорожку'); });
    });
    box.querySelector('#veVoiceSearch').addEventListener('input', list);
    box.querySelector('#veAiPrompt').addEventListener('input', () => { update(); reprice(); });
    setPrice('vePrice', 0, 'Введите текст и выберите голос');
    try {
      voices = await services.listVoices();
      list();
    } catch (error) {
      box.querySelector('#veVoices').innerHTML = '<li class="ve-warn">Не удалось загрузить голоса.</li>';
    }
  }

  async function dialogEnhance(config) {
    const picked = selectedClip();
    if (!picked || picked.media.kind !== 'video') {
      showModal('<h3>' + ICON.spark + ' Enhance Video</h3><p class="ve-muted">' + ERRORS.select_video + '</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="close-modal">Понятно</button></div>');
      return;
    }
    const length = clipDuration(picked.clip);
    const box = showModal('<h3>' + ICON.spark + ' Enhance Video</h3>'
      + '<p class="ve-muted">Клип ' + esc(picked.media.name) + ' · ' + length.toFixed(1) + ' с. Улучшается только эта часть файла.</p>'
      + '<div id="veLevels"><p class="ve-price"><span class="ve-spin"></span> Измеряем видео и считаем стоимость…</p></div>'
      + '<h4>Результат</h4><div class="ve-choice" role="radiogroup">'
      + '<label><input type="radio" name="veEnhanceMode" value="replace" checked><span><b>Заменить в клипе</b><small>Оригинал останется в проекте, его можно вернуть одной кнопкой</small></span></label>'
      + '<label><input type="radio" name="veEnhanceMode" value="add"><span><b>Добавить рядом</b><small>Улучшенная версия встанет следующим клипом</small></span></label></div>'
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="enhance" disabled>Улучшить видео</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    if (length > (config.maxSeconds || 20) + 0.05) {
      box.querySelector('#veLevels').innerHTML = '<p class="ve-warn">Улучшить можно фрагмент до ' + (config.maxSeconds || 20) + ' секунд. Разрежьте клип и выберите нужную часть.</p>';
      return;
    }
    try {
      const url = await actions.durableUrl(picked.media.id);
      const info = await services.estimateEnhance({ url, start: picked.clip.sourceStart, end: picked.clip.sourceEnd });
      if (!box.isConnected) return;
      box.querySelector('#veLevels').innerHTML = '<div class="ve-choice" role="radiogroup">' + info.levels.map((level, index) => '<label><input type="radio" name="veEnhanceLevel" value="' + esc(level.id) + '"' + (index === 0 ? ' checked' : '') + '><span><b>' + esc(level.label) + ' · ' + credits(level.credits) + '</b><small>' + esc(level.hint) + '</small></span></label>').join('') + '</div>';
      box.querySelector('[data-run]').disabled = false;
    } catch (error) {
      if (box.isConnected) box.querySelector('#veLevels').innerHTML = '<p class="ve-warn">' + esc(errorText(error)) + '</p>';
      return;
    }
    box.querySelector('[data-run]').addEventListener('click', () => {
      const level = box.querySelector('[name="veEnhanceLevel"]:checked').value;
      const mode = box.querySelector('[name="veEnhanceMode"]:checked').value;
      launch(actions.enhanceVideo({ clipId: picked.clip.id, level, mode }), (id) => { select({ type: 'clip', id }); toast('Улучшенное видео в проекте'); });
    });
  }

  function transcribeMissing() {
    return actions.transcribeSeconds() > 0;
  }

  function transcribePrice(config) {
    const seconds = actions.transcribeSeconds();
    if (!seconds) return 0;
    return Math.max(1, Math.ceil(seconds / 60 * (config.creditsPerMinute || 0.9)));
  }

  function dialogTranscribe(config) {
    if (!transcribeMissing()) {
      if (hasTranscript()) { showPanel('transcript'); return; }
      showModal('<h3>' + ICON.spark + ' Transcribe Speech</h3><p class="ve-muted">На шкале нет клипов со звуком.</p><div class="ve-actions"><button type="button" class="ve-btn" data-ve="close-modal">Понятно</button></div>');
      return;
    }
    const box = showModal('<h3>' + ICON.spark + ' Transcribe Speech</h3>'
      + '<p class="ve-muted">SYLVEX распознает речь в клипах и покажет её на шкале с таймкодами. Паузы будут отмечены как «нет речи». Расшифровка нужна только для монтажа и не попадает в видео.</p>'
      + '<p class="ve-price">Стоимость: ≈ <b>' + credits(transcribePrice(config)) + '</b> · ' + Math.ceil(actions.transcribeSeconds() / 60) + ' мин звука</p>'
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="transcribe">Расшифровать</button><button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    box.querySelector('[data-run]').addEventListener('click', () => launch(actions.transcribe(), () => { showPanel('transcript'); }));
  }

  function dialogSubtitles(config) {
    const existing = project().texts.some((text) => text.role === 'subtitle');
    const price = transcribePrice(config);
    const box = showModal('<h3>' + ICON.spark + ' Generate Subtitles</h3>'
      + '<p class="ve-muted">Субтитры создаются из речи в ролике и становятся обычными текстами на шкале — их можно править.</p>'
      + (price ? '<p class="ve-price">Сначала расшифруем речь: ≈ <b>' + credits(price) + '</b></p>' : '<p class="ve-price">Расшифровка уже есть — субтитры бесплатно.</p>')
      + '<h4>Расположение</h4><div class="ve-chips" data-group="pos"><button type="button" class="ve-chip is-active" data-value="0.86">Внизу</button><button type="button" class="ve-chip" data-value="0.5">По центру</button><button type="button" class="ve-chip" data-value="0.12">Вверху</button></div>'
      + '<h4>Размер</h4><div class="ve-chips" data-group="size"><button type="button" class="ve-chip is-active" data-value="0.05">Обычный</button><button type="button" class="ve-chip" data-value="0.07">Крупный</button></div>'
      + '<div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-run="subtitles">' + (existing ? 'Обновить субтитры' : 'Создать субтитры') + '</button>'
      + (existing ? '<button type="button" class="ve-btn ve-danger" data-clear-subtitles>Удалить субтитры</button>' : '') + '<button type="button" class="ve-btn" data-ve="close-modal">Отмена</button></div>');
    box.addEventListener('click', (event) => {
      const chip = event.target.closest('.ve-chip');
      if (chip) chip.parentElement.querySelectorAll('.ve-chip').forEach((node) => node.classList.toggle('is-active', node === chip));
      if (event.target.closest('[data-clear-subtitles]')) { run(() => editor.clearSubtitles()); closeModal(); }
      if (event.target.closest('[data-run]')) {
        const y = Number(box.querySelector('[data-group="pos"] .is-active').dataset.value);
        const fontSize = Number(box.querySelector('[data-group="size"] .is-active').dataset.value);
        launch(actions.generateSubtitles({ style: { y, fontSize } }).then(() => 'ok'), () => toast('Субтитры добавлены на шкалу текста'));
      }
    });
  }

  // -------------------------------------------------------------- projects

  async function showProjects() {
    const box = showModal('<h3>Проекты</h3><ul class="ve-projects" id="veProjects"><li class="ve-muted"><span class="ve-spin"></span> Загружаем…</li></ul><div class="ve-actions"><button type="button" class="ve-btn ve-primary" data-ve="new-project">' + ICON.plus + ' Новый проект</button><button type="button" class="ve-btn" data-ve="close-modal">Закрыть</button></div>', { wide: true });
    try {
      const items = await services.listProjects();
      if (!box.isConnected) return;
      box.querySelector('#veProjects').innerHTML = items.length ? items.map((item) => '<li' + (item.id === project().id ? ' class="is-current"' : '') + '><button type="button" class="ve-project" data-open-project="' + esc(item.id) + '"><span class="ve-project-thumb"' + (item.preview_url ? ' style="background-image:url(&quot;' + esc(item.preview_url) + '&quot;)"' : '') + '></span><span><b>' + esc(item.title || 'Без названия') + '</b><small>' + esc(item.updated_at ? new Date(item.updated_at).toLocaleString('ru-RU') : '') + '</small></span></button><button type="button" class="ve-mini ve-danger" data-delete-project="' + esc(item.id) + '" aria-label="Удалить проект">' + ICON.trash + '</button></li>').join('') : '<li class="ve-muted">Сохранённых проектов пока нет.</li>';
    } catch (error) {
      if (box.isConnected) box.querySelector('#veProjects').innerHTML = '<li class="ve-warn">' + esc(errorText(error)) + '</li>';
    }
  }

  async function openProject(id, token) {
    await actions.save().catch(() => {});
    const loaded = await run(() => actions.open(id, token));
    if (!loaded) return;
    closeModal();
    applyProjectView();
    select(null);
    seek(0);
  }

  function applyProjectView() {
    const ui = project().ui || {};
    state.autoFit = ui.autoFit !== false || !ui.pps;
    if (!state.autoFit) state.pps = ui.pps;
    state.range = null;
    state.panel = '';
  }

  // ------------------------------------------------------------ inspector

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
      if (name === 'duration') run(() => editor.trimClip(sel.id, { duration: value }));
      if (name === 'volume') run(() => editor.setClipVolume(sel.id, value / 100));
    } else if (sel.type === 'audio') {
      const clip = project().audioClips.find((item) => item.id === sel.id);
      if (name === 'sourceStart' || name === 'sourceEnd') run(() => editor.trimAudio(sel.id, { sourceStart: name === 'sourceStart' ? value : clip.sourceStart, sourceEnd: name === 'sourceEnd' ? value : clip.sourceEnd }));
      if (name === 'start') run(() => editor.moveAudio(sel.id, { start: value }));
      if (name === 'lane') run(() => editor.moveAudio(sel.id, { lane: Number(value) }));
      if (name === 'role') run(() => editor.setAudioRole(sel.id, value));
      if (name === 'volume') run(() => editor.setAudioVolume(sel.id, value / 100));
    } else if (sel.type === 'transition') {
      const clip = project().videoClips.find((item) => item.id === sel.id);
      if (clip && clip.transitionOut && name === 'transitionDuration') run(() => editor.setTransition(sel.id, Object.assign({}, clip.transitionOut, { duration: value })));
      if (clip && clip.transitionOut && name === 'transitionColor') run(() => editor.setTransition(sel.id, Object.assign({}, clip.transitionOut, { color: value })));
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
    if (event.target.closest('[data-join], [data-retry], [data-speech-start]')) return;
    const p = project();
    if (clipNode) {
      const clip = p.videoClips.find((item) => item.id === clipNode.dataset.clip);
      const media = p.media[clip.mediaId];
      const maxEnd = media.kind === 'image' ? MAX_IMAGE_DURATION : media.duration;
      const startLeft = clipNode.offsetLeft;
      const startWidth = clipNode.offsetWidth;
      if (state.selection?.id !== clip.id) select({ type: 'clip', id: clip.id });
      const node = $('[data-clip="' + CSS.escape(clip.id) + '"]');
      if (handle) {
        const edge = handle.dataset.trim;
        drag(event, {
          move(dx) {
            if (edge === 'start') {
              const delta = Math.max(media.kind === 'image' ? -Infinity : -clip.sourceStart, Math.min(clipDuration(clip) - MIN_CLIP, dx / pps));
              node.style.width = (startWidth - delta * pps) + 'px';
            } else {
              const delta = Math.max(-(clipDuration(clip) - MIN_CLIP), Math.min(maxEnd - clip.sourceEnd, dx / pps));
              node.style.width = (startWidth + delta * pps) + 'px';
            }
          },
          end(moved, dx) {
            if (!moved) return;
            const delta = dx / pps;
            if (media.kind === 'image') run(() => editor.trimClip(clip.id, { duration: clipDuration(clip) + (edge === 'start' ? -delta : delta) }));
            else run(() => editor.trimClip(clip.id, edge === 'start' ? { sourceStart: clip.sourceStart + delta } : { sourceEnd: clip.sourceEnd + delta }));
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

  // Ctrl/⌘ + wheel (or a trackpad pinch) zooms around the pointer.
  scroller.addEventListener('wheel', (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    const rect = scroller.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const time = (scroller.scrollLeft + x) / state.pps;
    setZoom(state.pps * Math.exp(-event.deltaY * 0.0025), time, x);
  }, { passive: false });

  // ------------------------------------------------------------- clicks

  host.addEventListener('click', (event) => {
    const target = event.target;
    const action = target.closest('[data-ve]');
    const menu = $('#veMenu');
    if (!menu.hidden && !target.closest('#veMenu') && !target.closest('[data-ve="ai-menu"]')) toggleMenu(false);
    const ai = target.closest('[data-ai]');
    if (ai && !ai.disabled) { openAi(ai.dataset.ai); return; }
    const join = target.closest('[data-join]');
    if (join) { select({ type: 'transition', id: join.dataset.join }); return; }
    const retry = target.closest('[data-retry]');
    if (retry) { actions.retryUpload(retry.dataset.retry); return; }
    const speech = target.closest('[data-speech-start]');
    if (speech) {
      const start = Number(speech.dataset.speechStart);
      const end = Number(speech.dataset.speechEnd);
      state.range = { start, end };
      seek(start);
      renderTimeline();
      renderToolbar();
      if (state.panel === 'transcript') renderInspector(true);
      return;
    }
    const pause = target.closest('[data-remove-pause]');
    if (pause) {
      const [start, end] = pause.dataset.removePause.split(':').map(Number);
      run(() => editor.removeRange(start, end));
      return;
    }
    const place = target.closest('[data-place]');
    if (place) {
      const media = project().media[place.dataset.place];
      run(() => editor.placeMedia(place.dataset.place, media && media.kind === 'audio' ? { start: state.time } : {})).then((id) => { if (id) select({ type: media.kind === 'audio' ? 'audio' : 'clip', id }); });
      return;
    }
    const openProjectButton = target.closest('[data-open-project]');
    if (openProjectButton) { openProject(openProjectButton.dataset.openProject); return; }
    const deleteProjectButton = target.closest('[data-delete-project]');
    if (deleteProjectButton) {
      const id = deleteProjectButton.dataset.deleteProject;
      if (window.confirm('Удалить проект? Файлы в истории SYLVEX останутся.')) run(() => services.deleteProject(id)).then(() => showProjects());
      return;
    }
    const transition = target.closest('[data-transition]');
    if (transition && state.selection && state.selection.type === 'transition') {
      const clipId = state.selection.id;
      const type = transition.dataset.transition;
      const clip = project().videoClips.find((item) => item.id === clipId);
      const duration = clip && clip.transitionOut ? clip.transitionOut.duration : DEFAULT_TRANSITION_DURATION;
      run(() => editor.setTransition(clipId, type ? { type, duration } : null));
      renderInspector(true);
      return;
    }
    const toggle = target.closest('.ve-toggle[data-field], .ve-toggle[data-align]');
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
    if (name === 'close') { actions.save().catch(() => {}); if (onClose) onClose(); return; }
    if (name === 'undo') { editor.undo(); return; }
    if (name === 'redo') { editor.redo(); return; }
    if (name === 'play') { togglePlay(); return; }
    if (name === 'split') { splitAtPlayhead(); return; }
    if (name === 'duplicate') { duplicateSelection(); return; }
    if (name === 'delete') { deleteSelection(); return; }
    if (name === 'mark-in') { markRange('in'); return; }
    if (name === 'mark-out') { markRange('out'); return; }
    if (name === 'remove-range') { removeRange(); return; }
    if (name === 'remove-audio-range') {
      const range = state.range;
      if (range && run(() => editor.removeAudioRange(state.selection.id, range.start, range.end)) !== null) { state.range = null; select(null); }
      return;
    }
    if (name === 'detach-audio') { const id = run(() => editor.detachAudio(state.selection.id)); if (id) select({ type: 'audio', id }); return; }
    if (name === 'revert-version') { run(() => editor.revertClipMedia(state.selection.id)); renderInspector(true); return; }
    if (name === 'zoom-in') { setZoom(state.pps * 1.5); return; }
    if (name === 'zoom-out') { setZoom(state.pps / 1.5); return; }
    if (name === 'zoom-fit') { state.autoFit = true; renderTimeline(); scroller.scrollLeft = 0; rememberZoom(); return; }
    if (name === 'ai-menu') { toggleMenu(); return; }
    if (name === 'transcript') { showPanel(state.panel === 'transcript' ? '' : 'transcript'); return; }
    if (name === 'panel-close') { showPanel(''); return; }
    if (name === 'projects') { showProjects(); return; }
    if (name === 'new-project') {
      actions.save().catch(() => {});
      run(() => editor.load(createProject())).then(() => { closeModal(); applyProjectView(); select(null); seek(0); });
      return;
    }
    if (name === 'add-text') {
      const l = layout();
      const start = state.time < l.duration ? state.time : 0;
      const id = run(() => editor.addText({ start, duration: Math.max(MIN_CLIP, Math.min(3, (l.duration || 3) - start)) }));
      if (id) select({ type: 'text', id });
      return;
    }
    if (name === 'video-audio') { const p = project(); run(() => editor.muteVideoAudio(!p.videoClips.every((clip) => clip.muted))); return; }
    if (name === 'export') { startExport(); return; }
    if (name === 'open-browser') { openInBrowser(); return; }
    if (name === 'save-export') { saveExportInTelegram(action); return; }
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
    addFiles(files);
  });

  // Files dropped onto the editor.
  host.addEventListener('dragover', (event) => { if (event.dataTransfer && Array.from(event.dataTransfer.types || []).includes('Files')) event.preventDefault(); });
  host.addEventListener('drop', (event) => {
    if (!event.dataTransfer || !event.dataTransfer.files.length) return;
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  });

  $('#veName').addEventListener('change', (event) => run(() => editor.rename(event.target.value)));
  $('#veName').addEventListener('keydown', (event) => { if (event.key === 'Enter') event.target.blur(); });

  $('#veZoom').addEventListener('input', (event) => {
    const center = (scroller.scrollLeft + scroller.clientWidth / 2) / state.pps;
    setZoom(sliderToZoom(event.target.value), center, scroller.clientWidth / 2);
  });

  host.addEventListener('keydown', (event) => {
    if (event.target.closest('input, textarea, select')) return;
    const key = event.key.toLowerCase();
    if (event.key === ' ') { event.preventDefault(); togglePlay(); }
    else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteSelection(); }
    else if ((event.ctrlKey || event.metaKey) && key === 'z') { event.preventDefault(); if (event.shiftKey) editor.redo(); else editor.undo(); }
    else if ((event.ctrlKey || event.metaKey) && key === 'd') { event.preventDefault(); duplicateSelection(); }
    else if (event.ctrlKey || event.metaKey) { /* browser shortcuts */ }
    else if (key === 's') { event.preventDefault(); splitAtPlayhead(); }
    else if (key === 'i') { markRange('in'); }
    else if (key === 'o') { markRange('out'); }
    else if (key === '+' || key === '=') { setZoom(state.pps * 1.5); }
    else if (key === '-') { setZoom(state.pps / 1.5); }
    else if (event.key === 'Escape') { if (!$('#veModal').hidden) closeModal(); else if (state.range) { state.range = null; render(); } else select(null); }
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
      state.caps = Object.assign({ transitionKinds: [], fonts: [] }, caps || {});
      state.ready = true;
      const msg = $('#veStageMsg');
      if (msg) msg.remove();
      if (info) toast(info);
      render();
      renderInspector(true);
    },
    setEngineError(error) {
      const msg = $('#veStageMsg');
      if (msg) { msg.textContent = errorText(error); msg.classList.add('is-error'); }
    },
    setWorkState(work) {
      const before = state.work;
      state.work = Object.assign({ uploads: {} }, work || {});
      renderStatus();
      const uploadsChanged = JSON.stringify(before.uploads) !== JSON.stringify(state.work.uploads);
      if (uploadsChanged || !!before.job !== !!state.work.job || before.transcribing !== state.work.transcribing) { renderTimeline(); renderInspector(); }
    },
    projectLoaded() { applyProjectView(); render(); },
    showProjects,
    openProject,
    addFiles,
    toast,
    focus: () => host.focus(),
    destroy() { frames.destroy(); waves.destroy(); clearInterval(jobTimer); },
  };
}
