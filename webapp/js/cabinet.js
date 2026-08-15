console.log("SYLVEX_CABINET_JS_STARTED");

// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/cabinet.js
// Файл содержит frontend-логику Mini App.
// Комментарии описывают экраны, кнопки, запросы и обработчики без изменения поведения.
// =====================================================
// Cabinet controller: wires DOM events, renders dynamic content, manages
// Pro Studio chat workspace, support modal, hero carousel, pricing logic.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});
  console.log("CABINET JS NEW VERSION 11.07.2026");
  // Pro Studio state.
  let studioMode = 'pro';

  const PROMPT_PLACEHOLDER_ANIMATIONS = {
    ru: {
      image: { brand:'SYLVEX генерация фото', base:'Опиши свое фото', variants:['для рекламы','как профессиональный портрет','как киноафишу','как обложку журнала','как продуктовую фотографию','как рекламный баннер','как концепт-арт','в кинематографическом стиле','для социальных сетей'] },
      video: { brand:'SYLVEX генерация видео', base:'Опиши свое видео', variants:['как рекламный ролик','кинематографично','с плавным движением камеры','в замедленной съемке','для TikTok','для YouTube Shorts','как трейлер фильма','с динамичной камерой','как fashion video'] },
      music: { brand:'SYLVEX генерация музыки', base:'Опиши свою музыку', variants:['в стиле Pop','в стиле EDM','для фильма','для игры','эпичную','романтическую','атмосферную','с мужским вокалом','с женским вокалом'] },
      voice: { brand:'SYLVEX озвучка', base:'Введите текст для озвучки', variants:['для рекламного ролика','для трейлера фильма','спокойным голосом','эмоциональным голосом','голосом диктора','для персонажа','для презентации'] },
      text: { brand:'SYLVEX генерация текста', base:'Опиши свой запрос', variants:['напиши статью','напиши сценарий','напиши рекламный текст','напиши описание товара','напиши пост','напиши письмо','напиши историю','придумай идею','составь план'] },
    },
    en: {
      image: { brand:'SYLVEX image generation', base:'Describe your image', variants:['for an ad','as a professional portrait','as a movie poster','as a magazine cover','as product photography','as an advertising banner','as concept art','in a cinematic style','for social media'] },
      video: { brand:'SYLVEX video generation', base:'Describe your video', variants:['as a commercial','with a cinematic look','with smooth camera movement','in slow motion','for TikTok','for YouTube Shorts','as a movie trailer','with a dynamic camera','as a fashion video'] },
      music: { brand:'SYLVEX music generation', base:'Describe your music', variants:['in a Pop style','in an EDM style','for a film','for a game','epic','romantic','atmospheric','with male vocals','with female vocals'] },
      voice: { brand:'SYLVEX voiceover', base:'Enter text for voiceover', variants:['for a commercial','for a movie trailer','in a calm voice','in an emotional voice','with a narrator voice','for a character','for a presentation'] },
      text: { brand:'SYLVEX text generation', base:'Describe your request', variants:['write an article','write a script','write advertising copy','write a product description','write a post','write a letter','write a story','suggest an idea','create a plan'] },
    },
  };

  const PROMPT_PLACEHOLDER_TIMING = Object.freeze({
    typing: 45,
    deleting: 25,
    phrasePause: 1200,
    variationPause: 400,
    blurRestart: 1200,
  });

  const PromptPlaceholderManager = (() => {
    let element = null;
    let layer = null;
    let textNode = null;
    let timer = null;
    let runToken = 0;
    let mode = 'video';
    let variationIndex = 0;
    let temporaryText = '';

    const language = () => {
      const selected = String((S.getLang && S.getLang()) || localStorage.getItem('sylvex-lang') || 'en').slice(0, 2);
      return PROMPT_PLACEHOLDER_ANIMATIONS[selected] ? selected : 'en';
    };
    const copy = () => {
      const group = PROMPT_PLACEHOLDER_ANIMATIONS[language()] || PROMPT_PLACEHOLDER_ANIMATIONS.en;
      return group[mode] || group.video;
    };
    const clearTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };
    const cancel = () => {
      runToken += 1;
      clearTimer();
    };
    const show = (value, animated) => {
      if (!layer || !textNode) return;
      textNode.textContent = value || '';
      layer.classList.toggle('is-animated', !!animated);
      layer.hidden = !!(element && element.value);
      layer.dir = document.documentElement.dir || 'ltr';
    };
    const schedule = (callback, delay, token) => {
      clearTimer();
      timer = window.setTimeout(() => {
        timer = null;
        if (token === runToken) callback();
      }, delay);
    };
    const typeTo = (target, token, done) => {
      if (token !== runToken || !textNode) return;
      const current = textNode.textContent || '';
      if (current.length >= target.length) return done();
      show(target.slice(0, current.length + 1), true);
      schedule(() => typeTo(target, token, done), PROMPT_PLACEHOLDER_TIMING.typing, token);
    };
    const deleteTo = (length, token, done) => {
      if (token !== runToken || !textNode) return;
      const current = textNode.textContent || '';
      if (current.length <= length) return done();
      show(current.slice(0, -1), true);
      schedule(() => deleteTo(length, token, done), PROMPT_PLACEHOLDER_TIMING.deleting, token);
    };
    const runVariations = (token) => {
      if (token !== runToken) return;
      const settings = copy();
      const variants = settings.variants || [];
      if (!variants.length) {
        schedule(() => runVariations(token), PROMPT_PLACEHOLDER_TIMING.phrasePause, token);
        return;
      }
      const phrase = settings.base + ' ' + variants[variationIndex % variants.length];
      variationIndex = (variationIndex + 1) % variants.length;
      typeTo(phrase, token, () => {
        schedule(() => deleteTo(settings.base.length, token, () => {
          schedule(() => runVariations(token), PROMPT_PLACEHOLDER_TIMING.variationPause, token);
        }), PROMPT_PLACEHOLDER_TIMING.phrasePause, token);
      });
    };
    const start = () => {
      cancel();
      if (!element || element.value || document.activeElement === element || temporaryText) {
        if (element && !element.value) show(temporaryText || copy().base, false);
        return;
      }
      variationIndex = 0;
      const token = runToken;
      const settings = copy();
      show('', true);
      typeTo(settings.brand, token, () => {
        schedule(() => deleteTo(0, token, () => {
          schedule(() => typeTo(settings.base, token, () => {
            schedule(() => runVariations(token), PROMPT_PLACEHOLDER_TIMING.phrasePause, token);
          }), PROMPT_PLACEHOLDER_TIMING.variationPause, token);
        }), PROMPT_PLACEHOLDER_TIMING.phrasePause, token);
      });
    };
    const setMode = (nextMode) => {
      mode = ['image','video','music','voice','text'].includes(nextMode) ? nextMode : 'video';
      if (!element) return;
      const settings = copy();
      element.placeholder = settings.base;
      element.setAttribute('aria-label', settings.base);
      temporaryText = '';
      start();
    };
    const setup = (input, initialMode) => {
      if (!input || element === input) {
        if (input) setMode(initialMode || mode);
        return;
      }
      cancel();
      element = input;
      layer = document.createElement('div');
      layer.className = 'animated-prompt-placeholder';
      layer.setAttribute('aria-hidden', 'true');
      layer.innerHTML = '<span class="animated-prompt-placeholder-text"></span><i aria-hidden="true">|</i>';
      textNode = layer.querySelector('.animated-prompt-placeholder-text');
      element.insertAdjacentElement('afterend', layer);
      element.classList.add('has-animated-placeholder');
      element.addEventListener('focus', () => {
        cancel();
        if (!element.value) show(temporaryText || copy().base, false);
      });
      element.addEventListener('input', () => {
        cancel();
        if (element.value) {
          if (layer) layer.hidden = true;
        } else {
          show(temporaryText || copy().base, false);
        }
      });
      element.addEventListener('blur', () => {
        cancel();
        if (!element.value && !temporaryText) {
          const token = runToken;
          schedule(start, PROMPT_PLACEHOLDER_TIMING.blurRestart, token);
        }
      });
      window.addEventListener('pagehide', cancel);
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) cancel();
        else if (element && !element.value && document.activeElement !== element) start();
      });
      setMode(initialMode || mode);
    };
    const refreshLanguage = () => setMode(mode);
    const setTemporary = (value) => {
      cancel();
      temporaryText = String(value || '');
      if (element && !element.value) show(temporaryText || copy().base, false);
    };
    const clearTemporary = () => {
      temporaryText = '';
      if (!element || element.value) return;
      if (document.activeElement === element) show(copy().base, false);
      else start();
    };
    return { setup, setMode, refreshLanguage, setTemporary, clearTemporary, stop: cancel };
  })();
  let activeCat = null;
  let chatMessages = [];
  let currentConvId = null;
  let conversationsCache = [];
  const CHAT_SPACE_TYPES = ['image', 'video', 'music', 'voice', 'text'];
  const chatSpaces = {
    image: { activeChatId: null, conversationId: null, messages: [] },
    video: { activeChatId: null, conversationId: null, messages: [] },
    music: { activeChatId: null, conversationId: null, messages: [] },
    voice: { activeChatId: null, conversationId: null, messages: [] },
    text: { activeChatId: null, conversationId: null, messages: [] },
  };
  const chatCollections = {
    image: [],
    video: [],
    music: [],
    voice: [],
  };
  const expandedHistorySections = {};
  const activeGenerationWatchers = new Set();
  const activeGeneration = {
    locked: false,
    status: '',
    mode: '',
    jobId: '',
    model: '',
    startedAt: 0,
    requestId: '',
    loadingToken: '',
    placeholderMessage: null,
    progressTimer: null,
    restoringMode: false,
    historyPreview: false,
  };
  const openingConversations = new Set();
  let restoringChatSpace = false;
  // Pending attachment for next send.
  let pendingAttachment = null; // { kind, mime, name, dataBase64 }
  let pendingAttachAccept = '';
  // Voice recording state.
  let mediaRecorder = null;
  let mediaChunks = [];
  let mediaStream = null;
  let textMicAudioContext = null;
  let textMicAnalyser = null;
  let textMicAnimationFrame = 0;
  let textMicStartedAt = 0;
  let textMicLimitTimer = 0;
  let currentModelLabel = 'SYLVEX Pro';
let imageCapabilities = [];
let generatedImageLibrary = [];
let imageState = {
    modelId: 'seedream_5_0_lite',
    size: '',
    count: 1,
    style: 'auto',
    character: 'auto',
    objects: '',
    characterId: null,
    objectId: null,
    characterReferences: [],
    objectReferences: [],
    characterName: '',
    objectName: '',
    referenceImageUrl: '',
    referenceImageUrls: [],
    uploadedImageUrls: [],
    attachment: null,
    seed: null,
  };

const PHOTO_TOOL_CONFIG = {
  try_on: {
    title: 'Виртуальная примерка',
    shortTitle: 'Try‑On',
    description: 'Загрузите человека первым, затем от одной до трёх фотографий одежды.',
    min: 2,
    max: 4,
    labels: ['Человек', 'Одежда 1', 'Одежда 2', 'Одежда 3'],
    demo: '/webapp/assets/photo-tools/try-on/demo.mp4',
  },
  remove_bg: {
    title: 'Удаление фона',
    shortTitle: 'Удаление фона',
    description: 'Загрузите одно изображение. Объект останется без исходного фона.',
    min: 1,
    max: 1,
    labels: ['Исходное фото'],
    demo: '/webapp/assets/photo-tools/remove-background/demo.mp4',
  },
  replace_character: {
    title: 'Замена персонажа',
    shortTitle: 'Замена персонажа',
    description: 'Первое фото задаёт сцену, второе — персонажа для замены.',
    min: 2,
    max: 2,
    labels: ['Основное фото', 'Новый персонаж'],
    demo: '/webapp/assets/photo-tools/replace-character/demo.mp4',
  },
  enhance: {
    title: 'Улучшение фото',
    shortTitle: 'Улучшение фото',
    description: 'Загрузите одно фото для улучшения качества и детализации.',
    min: 1,
    max: 1,
    labels: ['Фото для улучшения'],
    demo: '/webapp/assets/photo-tools/enhance/demo.mp4',
  },
  tattoo: { title:'Тату', shortTitle:'Тату', description:'Загрузите фото человека и изображение татуировки.', min:2, max:2, labels:['Человек','Татуировка'] },
  logo: { title:'Лого', shortTitle:'Лого', description:'Загрузите основное изображение и логотип для размещения.', min:2, max:2, labels:['Основное фото','Логотип'] },
  remove_object: { title:'Удаление предмета', shortTitle:'Удалить предмет', description:'Загрузите фото и опишите предмет, который нужно удалить.', min:1, max:1, labels:['Исходное фото'] },
  replace_object: { title:'Замена предмета', shortTitle:'Заменить предмет', description:'Первое фото задаёт сцену, второе — новый предмет.', min:2, max:2, labels:['Основное фото','Новый предмет'] },
};
const photoToolState = Object.fromEntries(Object.keys(PHOTO_TOOL_CONFIG).map((key) => [key, { files: [], generating: false }]));
let activePhotoTool = '';

let videoState = {
  modelId: 'seedance_2_fast',
  provider: 'bytedance',
  section: 'generate',
  ratio: '16:9',
  duration: 5,
  resolution: '720p',
  sound: false,
  generationMode: 'text_to_video',
  quality: 'standard',
  startImage: '',
  endImage: '',
  characterImage: '',
  inputVideo: '',
  videoUrl: '',
  editInputVideo: '',
  editVideoUrl: '',
  referenceVideoUrl: '',
  imageUrl: '',
  motionPreset: '',
  videoTemplate: null,
  characterVisual: null,
  objectVisual: null,
  referenceVisual: null,
  referenceImageUrl: '',
  referenceImageUrls: [],
  referenceImageBuckets: {
    generate: [],
    edit: [],
    motion: [],
  },
  uploadedImageUrls: [],
  attachment: null,
  editUploading: null,
  referenceUploading: null,
  advanced: {},
};
let videoUploadTarget = 'reference';
const UPLOAD_TARGETS = {
  IMAGE_UPLOAD: 'image_upload',
  VIDEO_EDIT_INPUT: 'video_edit_input',
  VIDEO_START: 'video_start',
  VIDEO_END: 'video_end',
  VIDEO_REFERENCES: 'video_references',
};
let currentUploadTarget = UPLOAD_TARGETS.IMAGE_UPLOAD;
let activeUploadTarget = UPLOAD_TARGETS.IMAGE_UPLOAD;
let videoTemplatesCache = null;
let photoCatalogCache = null;
let klingEffectsCache = null;
let activeVideoTemplate = null;
let videoTemplateUploadUrl = '';
let videoTemplateRatio = '16:9';
const VIDEO_TEMPLATE_INTRO_KEY = 'sylvex_video_templates_intro_seen';

// =====================================================
// ЗАГРУЗКА В MINI APP: setUploadTarget
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function setUploadTarget(target) {
  activeUploadTarget = Object.values(UPLOAD_TARGETS).includes(target) ? target : UPLOAD_TARGETS.IMAGE_UPLOAD;
  currentUploadTarget = activeUploadTarget;

  if (activeUploadTarget === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) {
    videoUploadTarget = 'input_video';
  } else if (activeUploadTarget === UPLOAD_TARGETS.VIDEO_START) {
    videoUploadTarget = 'start';
  } else if (activeUploadTarget === UPLOAD_TARGETS.VIDEO_END) {
    videoUploadTarget = 'end';
  } else if (activeUploadTarget === UPLOAD_TARGETS.VIDEO_REFERENCES) {
    videoUploadTarget = 'reference';
  } else {
    videoUploadTarget = 'reference';
  }

  const panel = document.getElementById('uploadPanel');
  if (panel) panel.dataset.uploadTarget = activeUploadTarget;
}

// =====================================================
// ЗАГРУЗКА В MINI APP: getUploadTarget
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function getUploadTarget() {
  const panel = document.getElementById('uploadPanel');
  const target = (panel && panel.dataset && panel.dataset.uploadTarget) || activeUploadTarget || currentUploadTarget || UPLOAD_TARGETS.IMAGE_UPLOAD;
  return Object.values(UPLOAD_TARGETS).includes(target) ? target : UPLOAD_TARGETS.IMAGE_UPLOAD;
}

function currentVideoEditInputUrl() {
  return videoState.editInputVideo || videoState.editVideoUrl || '';
}

function currentVideoReferenceUrl() {
  return videoState.referenceVideoUrl || '';
}

function videoUploadTargetAllowsVideo(targetOverride) {
  const target = targetOverride || getUploadTarget();
  if (target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) return true;
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
    return videoState.section === 'edit' || videoState.section === 'motion';
  }
  return false;
}

function videoReferenceBucketKey() {
  return videoState.section === 'edit' ? 'edit' : (videoState.section === 'motion' ? 'motion' : 'generate');
}

function videoReferenceBuckets() {
  if (!videoState.referenceImageBuckets || typeof videoState.referenceImageBuckets !== 'object') {
    videoState.referenceImageBuckets = { generate: [], edit: [], motion: [] };
  }
  ['generate', 'edit', 'motion'].forEach((key) => {
    if (!Array.isArray(videoState.referenceImageBuckets[key])) videoState.referenceImageBuckets[key] = [];
  });
  return videoState.referenceImageBuckets;
}

function currentVideoReferenceImages() {
  const buckets = videoReferenceBuckets();
  return (buckets[videoReferenceBucketKey()] || []).slice();
}

function setCurrentVideoReferenceImages(urls) {
  const clean = (urls || []).filter(Boolean).slice(0, 4);
  const buckets = videoReferenceBuckets();
  buckets[videoReferenceBucketKey()] = clean;
  videoState.referenceImageUrls = clean.slice();
  videoState.uploadedImageUrls = clean.slice();
  videoState.referenceImageUrl = clean[0] || '';
  videoState.imageUrl = videoState.referenceImageUrl;
}
let videoModelSettings = {};
let activeImageStylePanelKind = 'style';

let musicState = {
  modelId: 'suno_chirp_5',
  uploads: [],
  attachment: null,
  genre: 'auto',
  duration: 'auto',
  style: '',
  voice: '',
  audioSettings: {},
  settings: {
    mood: 'auto',
    tempo: 'auto',
    theme: 'auto',
    vocal: 'auto',
  },
};
let musicSettingsDraft = null;
let musicDurationDraftSeconds = 0;

let voiceState = {
  modelId: 'elevenlabs_eleven_v3',
  uploads: [],
  attachment: null,
  uploading: null,
  uploadPreviewUrl: '',
  genre: '',
  duration: '',
  style: '',
  voice: 'Kore',
  runwayVoice: 'Maya',
  runwayTool: 'text_to_speech',
  runwayTargetLanguage: 'en',
  runwayDuration: 5,
  elevenlabsVoice: '21m00Tcm4TlvDq8ikWAM',
  elevenlabsSecondVoice: '21m00Tcm4TlvDq8ikWAM',
  elevenlabsTool: 'text_to_speech',
  elevenlabsTargetLanguage: 'en',
  uploadPurpose: 'voiceover',
  sourceLanguage: 'auto',
  targetLanguage: 'en',
  numSpeakers: 1,
  speakerVoices: ['Kore', '', '', '', '', '', ''],
  secondVoice: 'Puck',
  speakerMode: 'single',
  speaker1: 'Speaker1',
  speaker2: 'Speaker2',
  audioSettings: {
    style: 'auto',
    pace: 'auto',
    tone: 'auto',
    speed: 1,
    pitch: 50,
    expressiveness: 50,
    stability: 0.5,
    similarity_boost: 0.75,
  },
  editorTemplate: '',
  pronunciationRules: {},
  activeSpeakerIndex: null,
};
let voiceWorkspaceMode = 'voiceover';
const geminiVoicePreviewCache = {};
let geminiVoicePreviewAudio = null;
let runwayVoiceListLoaded = false;
let elevenlabsVoiceListLoaded = false;
let runwayVoiceListLoading = null;
let elevenlabsVoiceListLoading = null;
let voiceAvatarCatalogLoaded = false;
let voiceAvatarCatalogLoading = null;
let voiceAvatarCatalog = {};
let voiceAvatarPendingCount = 0;
let voiceAvatarPollTimer = null;
let voiceAvatarPollAttempts = 0;
let voiceCloneRecorder = null;
let voiceCloneStream = null;
let voiceCloneChunks = [];
let voiceCloneBlob = null;
let voiceClonePreviewUrl = '';
let voiceCloneSubmitting = false;
let voiceToolGuideIdleTimer = 0;
let voiceToolGuideStepTimer = 0;
let voiceToolGuideIndex = 0;
let voiceCloneDraft = {
  name: '',
  gender: 'neutral',
  emotion: 'neutral',
  speed: 50,
  pitch: 50,
  intonation: 50,
  expressiveness: 50,
  source: '',
  avatarUrl: '',
};
let voiceCloneCountdown = 0;
let voiceCloneCountdownTimer = null;
let voiceCloneRecordStartedAt = 0;
let voiceCloneRecordElapsed = 0;
let voiceCloneRecordTimer = null;
let voiceClonePreviewAudio = null;
let voiceClonePreviewPlaying = false;
let voiceClonePreviewTime = 0;
let voiceClonePreviewDuration = 0;
let activeVoicePanelSection = '';

let textState = {
  familyId: 'gpt',
  modelId: 'gpt-5.5',
  tool: 'text',
  style: 'neutral',
  format: 'markdown',
  language: 'auto',
  attachment: null,
};

let serverVisualItems = {
  characters: [],
  objects: [],
  voices: [],
};
let serverDrafts = {};
let draftSaveTimer = null;
let restoringDraft = false;

const LOBE_ICON_BASE = 'https://unpkg.com/@lobehub/icons-static-svg@latest/icons';

const AI_LOGOS = {
  openai: LOBE_ICON_BASE + '/openai.svg',
  gptImage: LOBE_ICON_BASE + '/openai.svg',
  flux: LOBE_ICON_BASE + '/flux.svg',
  bfl: LOBE_ICON_BASE + '/bfl.svg',
  qwen: LOBE_ICON_BASE + '/qwen.svg',
  microsoft: LOBE_ICON_BASE + '/microsoft.svg',
  krea: LOBE_ICON_BASE + '/krea.svg',
  ideogram: LOBE_ICON_BASE + '/ideogram.svg',
  recraft: LOBE_ICON_BASE + '/recraft.svg',
  luma: LOBE_ICON_BASE + '/luma.svg',
  dreamMachine: LOBE_ICON_BASE + '/luma.svg',
  minimax: LOBE_ICON_BASE + '/minimax.svg',
  hailuo: LOBE_ICON_BASE + '/minimax.svg',
  pixverse: LOBE_ICON_BASE + '/pixverse.svg',
  sora: LOBE_ICON_BASE + '/sora.svg',
  runway: LOBE_ICON_BASE + '/runway.svg',
  runwayVideo: LOBE_ICON_BASE + '/runway.svg',
  grok: LOBE_ICON_BASE + '/grok.svg',
  gemini: LOBE_ICON_BASE + '/gemini.svg',
  google: LOBE_ICON_BASE + '/google.svg',
  kling: LOBE_ICON_BASE + '/kling.svg',
  bytedance: LOBE_ICON_BASE + '/bytedance.svg',
  seedream: LOBE_ICON_BASE + '/bytedance.svg',
  seedance: LOBE_ICON_BASE + '/bytedance.svg',
  wan: LOBE_ICON_BASE + '/qwen.svg',
  veo: LOBE_ICON_BASE + '/gemini.svg',
  elevenlabs: LOBE_ICON_BASE + '/elevenlabs.svg',
  heygen: '/webapp/assets/logos/heygen-symbol-black-logo.svg',
  suno: LOBE_ICON_BASE + '/suno.svg',
  nanoBanana: 'custom-banana',
};

const GROK_IMAGE_SIZES = [
  { id:'1:1', label:'1:1', ratio:'1:1' },
  { id:'2:3', label:'2:3', ratio:'2:3' },
  { id:'3:2', label:'3:2', ratio:'3:2' },
  { id:'16:9', label:'16:9', ratio:'16:9' },
  { id:'9:16', label:'9:16', ratio:'9:16' },
  { id:'3:4', label:'3:4', ratio:'3:4' },
  { id:'4:3', label:'4:3', ratio:'4:3' },
  { id:'1:2', label:'1:2', ratio:'1:2' },
  { id:'2:1', label:'2:1', ratio:'2:1' },
  { id:'19.5:9', label:'19.5:9', ratio:'19.5:9' },
  { id:'9:19.5', label:'9:19.5', ratio:'9:19.5' },
  { id:'20:9', label:'20:9', ratio:'20:9' },
  { id:'9:20', label:'9:20', ratio:'9:20' }
];

const GOOGLE_IMAGE_SIZES = [
  { id:'1:1', label:'1:1', ratio:'1:1' },
  { id:'16:9', label:'16:9', ratio:'16:9' },
  { id:'9:16', label:'9:16', ratio:'9:16' },
  { id:'3:4', label:'3:4', ratio:'3:4' },
  { id:'4:3', label:'4:3', ratio:'4:3' },
  { id:'1:2', label:'1:2', ratio:'1:2' },
  { id:'2:1', label:'2:1', ratio:'2:1' },
  { id:'20:9', label:'20:9', ratio:'20:9' },
  { id:'9:20', label:'9:20', ratio:'9:20' },
  { id:'auto', label:'Auto', ratio:'auto' }
];

const IMAGE_MODEL_LIST = [
  {
    id:'seedream_5_0_lite',
    label:'Seedream 5.0 Lite',
    desc:'ByteDance Seedream 5.0 Lite image model',
    icon:'seedream',
    providerModel:'seedream-5-0-260128',
    seed:true,
    costUsd:0.0525,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'ideogram_3_0',
    label:'Ideogram 3.0',
    desc:'Ideogram 3.0 Turbo image model',
    icon:'ideogram',
    providerModel:'ideogram-v3',
    renderingSpeed:'TURBO',
    seed:true,
    costUsd:0.045,
    costCredits:5,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'1:1 HD', label:'1:1 HD', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'ideogram_4_0',
    label:'Ideogram 4.0',
    desc:'Ideogram 4.0 Turbo image model',
    icon:'ideogram',
    providerModel:'ideogram-v4',
    renderingSpeed:'TURBO',
    seed:false,
    costUsd:0.045,
    costCredits:5,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },

  {
    id:'recraft_v4_1',
    label:'Recraft V4.1',
    desc:'Recraft V4.1 raster generation',
    icon:'recraft',
    providerModel:'recraftv4_1',
    seed:true,
    costUsd:0.0525,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'4:3', label:'4:3', ratio:'4:3' }
    ],
    recraftTools:[
      { id:'image_to_image', label:'Изображение → Изображение', costCredits:6 }
    ]
  },
  {
    id:'recraft_v3',
    label:'Recraft V3',
    desc:'Recraft V3 raster generation',
    icon:'recraft',
    providerModel:'recraftv3',
    seed:true,
    costUsd:0.06,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'4:3', label:'4:3', ratio:'4:3' }
    ],
    recraftTools:[
      { id:'image_to_image', label:'Изображение → Изображение', costCredits:6 },
      { id:'outpaint', label:'Дорисовка изображения', costCredits:6 },
      { id:'replace_background', label:'Замена фона', costCredits:6 },
      { id:'generate_background', label:'Генерация фона', costCredits:6 },
      { id:'create_style', label:'Генерация стиля', costCredits:6 },
      { id:'vectorize', label:'Векторизация', costCredits:2 },
      { id:'remove_background', label:'Удаление фона', costCredits:2 },
      { id:'crisp_upscale', label:'Увеличение разрешения', costCredits:1 },
      { id:'creative_upscale', label:'Повышение качества', costCredits:38 },
      { id:'erase_region', label:'Стирание области', costCredits:1 }
    ]
  },
  {
    id:'recraft_v4_1_pro',
    label:'Recraft V4.1 Pro',
    desc:'Recraft V4.1 Pro raster generation',
    icon:'recraft',
    providerModel:'recraftv4_1_pro',
    seed:false,
    costUsd:0.21,
    costCredits:21,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'4:3', label:'4:3', ratio:'4:3' }
    ],
    recraftTools:[
      { id:'image_to_image', label:'Изображение → Изображение', costCredits:6 }
    ]
  },

  {
    id:'seedream_4_5',
    label:'Seedream 4.5',
    desc:'ByteDance Seedream image model',
    icon:'seedream',
    badge:'TRENDING',
    providerModel:'seedream-4-5-251128',
    seed:true,
    costUsd:0.06,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'seedream_5_0_pro',
    label:'Seedream 5.0 Pro',
    desc:'ByteDance Seedream Pro image model',
    icon:'seedream',
    providerModel:'dola-seedream-5-0-pro-260628',
    seed:true,
    costUsd:0.0675,
    costCredits:7,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'seedream_4_0',
    label:'Seedream 4.0',
    desc:'ByteDance Seedream image model',
    icon:'seedream',
    providerModel:'seedream-4-0-250828',
    seed:true,
    costUsd:0.0525,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'gpt_image_1',
    label:'GPT Image 1',
    desc:'OpenAI image generation',
    icon:'gptImage',
    seed:false,
    quality:'medium',
    costUsd:0.063,
    costCredits:7,
    sizes:[
      { id:'2:3', label:'2:3', ratio:'2:3' },
      { id:'3:2', label:'3:2', ratio:'3:2' },
      { id:'1:1', label:'1:1', ratio:'1:1' }
    ]
  },
  {
    id:'gpt_image_2',
    label:'GPT Image 2',
    desc:'OpenAI image generation',
    icon:'gptImage',
    badge:'FEATURED',
    seed:false,
    quality:'medium',
    costUsd:0.0795,
    costCredits:8,
    sizes:[
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },

  {
    id:'flux_pro_kontext',
    label:'FLUX Pro Text',
    desc:'Black Forest Labs FLUX.1 Kontext Pro text image model',
    icon:'flux',
    providerModel:'flux-kontext-pro',
    seed:false,
    costUsd:0.06,
    costCredits:6,
    sizes:[
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'flux_2',
    label:'FLUX.2',
    desc:'Black Forest Labs FLUX.2 image model',
    icon:'flux',
    providerModel:'flux-2-pro',
    seed:false,
    costUsd:0.045,
    costCredits:5,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'flux_2_turbo',
    label:'FLUX.2 Turbo',
    desc:'Black Forest Labs FLUX.2 fast image model',
    icon:'flux',
    providerModel:'flux-2-flex',
    seed:false,
    costUsd:0.105,
    costCredits:11,
    badges:['FAST','LOW COST'],
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },

  {
    id:'qwen_image',
    label:'Qwen Image',
    desc:'Qwen image model',
    icon:'qwen',
    seed:false,
    costUsd:0.0675,
    costCredits:7,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'qwen_image_2_pro',
    label:'Qwen Image 2 Pro',
    desc:'Qwen image generation',
    icon:'qwen',
    seed:true,
    costUsd:0.1125,
    costCredits:12,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },
  {
    id:'qwen_image_2',
    label:'Qwen Image 2',
    desc:'Qwen image generation',
    icon:'qwen',
    seed:true,
    costUsd:0.0525,
    costCredits:6,
    sizes:[
      { id:'auto', label:'Auto', ratio:'auto' },
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'4:3', label:'4:3', ratio:'4:3' },
      { id:'3:4', label:'3:4', ratio:'3:4' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ]
  },

  {
    id:'nano_banana_2',
    label:'Nano Banana 2',
    desc:'Google Gemini 3.1 Flash Image',
    icon:'nanoBanana',
    badge:'FAST',
    providerModel:'gemini-3.1-flash-image',
    seed:false,
    costCredits:11,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'nano_banana_2_lite',
    label:'Nano Banana 2 Lite',
    desc:'Google Gemini 3.1 Flash Lite Image',
    icon:'nanoBanana',
    badge:'FAST',
    providerModel:'gemini-3.1-flash-lite-image',
    seed:false,
    costCredits:6,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'nano_banana_pro',
    label:'Nano Banana Pro',
    desc:'Google Gemini 3 Pro Image',
    icon:'nanoBanana',
    badge:'DISCOUNT',
    providerModel:'gemini-3-pro-image',
    seed:false,
    costCredits:21,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'nano_banana',
    label:'Nano Banana',
    desc:'Google Gemini 2.5 Flash Image',
    icon:'nanoBanana',
    providerModel:'gemini-2.5-flash-image',
    seed:false,
    costCredits:6,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'imagen_4_fast',
    label:'Imagen 4 Fast',
    desc:'Google Imagen 4 Fast',
    icon:'google',
    providerModel:'imagen-4.0-fast-generate-001',
    seed:false,
    costCredits:3,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'imagen_4_standard',
    label:'Imagen 4 Standard',
    desc:'Google Imagen 4 Standard',
    icon:'google',
    providerModel:'imagen-4.0-generate-001',
    seed:false,
    costCredits:6,
    sizes:GOOGLE_IMAGE_SIZES
  },
  {
    id:'imagen_4_ultra',
    label:'Imagen 4 Ultra',
    desc:'Google Imagen 4 Ultra',
    icon:'google',
    providerModel:'imagen-4.0-ultra-generate-001',
    seed:false,
    costCredits:9,
    sizes:GOOGLE_IMAGE_SIZES
  },

  {
    id:'grok_pro',
    label:'Grok Pro',
    desc:'xAI Grok image quality model',
    icon:'grok',
    badge:'HOT',
    providerModel:'grok-imagine-image-quality',
    seed:false,
    costCredits:8,
    inputImageCostCredits:2,
    inputImageCostProvisional:true,
    sizes:GROK_IMAGE_SIZES
  },
  {
    id:'grok',
    label:'Grok',
    desc:'xAI Grok image model',
    icon:'grok',
    providerModel:'grok-imagine-image',
    seed:false,
    costCredits:3,
    inputImageCostCredits:1,
    inputImageCostProvisional:true,
    sizes:GROK_IMAGE_SIZES
  },

];

const MODEL_FEATURES = {
  nano_banana_pro: { character: true, object: true, seed: false },
  nano_banana_2: { character: false, object: false, seed: false },
  nano_banana_2_lite: { character: false, object: false, seed: false },
  nano_banana: { character: true, object: true, seed: false },
  imagen_4_fast: { character: false, object: false, seed: false },
  imagen_4_standard: { character: false, object: false, seed: false },
  imagen_4_ultra: { character: false, object: false, seed: false },
  gpt_image_2: { character: true, object: true, seed: false },
  seedream_5_0_lite: { character: true, object: true, seed: true },
  seedream_5_0: { character: true, object: true, seed: true },
  seedream_5: { character: true, object: true, seed: true },
  seedream_5_0_pro: { character: true, object: true, seed: true },
  seedream_5_pro: { character: true, object: true, seed: true },
  seedream_4_5: { character: true, object: true, seed: true },
  seedream_4_0: { character: true, object: true, seed: true },
  seedream_4: { character: true, object: true, seed: true },
  grok_pro: { character: false, object: false, seed: false },
  grok: { character: false, object: false, seed: false },
  flux_2: { character: true, object: true, seed: false },
  flux_2_turbo: { character: true, object: true, seed: false },
  flux_pro_kontext: { character: true, object: false, seed: false },
  ideogram_3_0: { character: false, object: false, seed: true },
  ideogram_3: { character: false, object: false, seed: true },
  ideogram_4_0: { character: false, object: false, seed: false },
  ideogram_4: { character: false, object: false, seed: false },
  recraft_v4_1: { character: false, object: false, seed: true },
  recraft_v3: { character: false, object: false, seed: true },
  recraft_v4_1_pro: { character: false, object: false, seed: false },
  gpt_image_1: { character: true, object: true, seed: false },
  qwen_image: { character: false, object: false, seed: false },
  qwen_image_2: { character: false, object: false, seed: true },
  qwen_image_2_pro: { character: false, object: false, seed: true },
  krea_2: { character: false, object: false },
  microsoft_mai_image_2_5: { character: false, object: false },
};

// =====================================================
// JAVASCRIPT-БЛОК: getModelCapabilities
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function getModelCapabilities(modelId) {
  const fallback = { character: false, object: false, seed: false };
  const raw = String(modelId || '').trim();
  const normalized = raw.replace(/_0$/, '').replace(/-/g, '_');
  const cfg = MODEL_FEATURES[raw] || MODEL_FEATURES[normalized] || fallback;
  return {
    character: !!cfg.character,
    object: !!cfg.object,
    seed: !!cfg.seed,
  };
}

// =====================================================
// JAVASCRIPT-БЛОК: isGrokImageModel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function isGrokImageModel(modelId) {
  const raw = String(modelId || '').trim().replace(/-/g, '_');
  return raw === 'grok' || raw === 'grok_pro';
}

// =====================================================
// JAVASCRIPT-БЛОК: hidesSeedSettings
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function hidesSeedSettings(modelId) {
  const raw = String(modelId || '').trim().replace(/-/g, '_');
  return isGrokImageModel(raw) || [
    'nano_banana_2',
    'nano_banana_2_lite',
    'nano_banana_pro',
    'nano_banana',
    'imagen_4_fast',
    'imagen_4_standard',
    'imagen_4_ultra'
  ].includes(raw);
}

// =====================================================
// КАТАЛОГ ПЕРСОНАЖЕЙ И ОБЪЕКТОВ
// Загружает пресеты с backend по тому же принципу, что и каталог видео.
// Локальные записи ниже используются как резерв, пока backend-каталог недоступен.
// =====================================================
function presetSvg(label, hue) {
  const text = String(label || '').slice(0, 2).toUpperCase();
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">'
    + '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="hsl(' + hue + ',70%,68%)"/><stop offset="1" stop-color="hsl(' + ((hue + 64) % 360) + ',72%,38%)"/></linearGradient></defs>'
    + '<rect width="160" height="160" rx="34" fill="url(#g)"/>'
    + '<circle cx="80" cy="62" r="32" fill="rgba(255,255,255,.55)"/>'
    + '<rect x="36" y="104" width="88" height="38" rx="19" fill="rgba(255,255,255,.42)"/>'
    + '<text x="80" y="91" font-family="Arial, sans-serif" font-size="34" font-weight="800" fill="#151515" text-anchor="middle">' + text + '</text>'
    + '</svg>';
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
}

const PRESET_CATALOG_ENDPOINT = '/api/public/prostudio/preset-catalog';

function normalizePresetCatalogItem(item, kind, index) {
  const source = item && typeof item === 'object' ? item : {};
  const name = String(source.name || source.label || '').trim();
  const baseHue = kind === 'character' ? 18 + index * 23 : 190 + index * 17;
  const avatarUrl = String(
    source.avatarUrl
    || source.avatar_url
    || source.previewUrl
    || source.preview_url
    || ''
  ).trim();
  const references = source.referenceImages || source.reference_images || [];
  const referenceImages = Array.isArray(references)
    ? references.filter(Boolean).map(String)
    : [];
  const videoReferences = Array.isArray(source.videoReferences || source.video_references)
    ? (source.videoReferences || source.video_references).filter(Boolean).map(String)
    : [];
  const previewUrl = avatarUrl || referenceImages[0] || '';

  return {
    id: String(source.id || ((kind === 'character' ? 'character_' : 'object_') + name.toLowerCase().replace(/[^a-z0-9]+/g, '_'))),
    name,
    gender: kind === 'character' ? String(source.gender || 'neutral') : undefined,
    description: String(source.description || ''),
    prompt: String(source.prompt || ''),
    negativePrompt: String(source.negativePrompt || source.negative_prompt || ''),
    avatarUrl,
    videoReferenceUrl: String(source.videoReferenceUrl || source.video_reference_url || videoReferences[0] || ''),
    videoReferences,
    heygenPhotoAvatarId: String(source.heygenPhotoAvatarId || source.heygen_photo_avatar_id || source.photoAvatarId || source.photo_avatar_id || ''),
    heygenVideoAvatarId: String(source.heygenVideoAvatarId || source.heygen_video_avatar_id || source.videoAvatarId || source.video_avatar_id || ''),
    heygenAvatarGroupId: String(source.heygenAvatarGroupId || source.heygen_avatar_group_id || source.avatarGroupId || source.avatar_group_id || ''),
    heygenDefaultVoiceId: String(source.heygenDefaultVoiceId || source.heygen_default_voice_id || source.defaultVoiceId || source.default_voice_id || ''),
    heygenLooks: Array.isArray(source.heygenLooks || source.heygen_looks) ? (source.heygenLooks || source.heygen_looks).slice() : [],
    previewUrl: previewUrl || presetSvg(name, baseHue),
    referenceImages: referenceImages.length
      ? referenceImages
      : [
          presetSvg(name + ' A', baseHue),
          presetSvg(name + ' B', baseHue + 18),
          presetSvg(name + ' C', baseHue + 36),
        ],
    tags: Array.isArray(source.tags) ? source.tags.filter(Boolean).map(String) : [],
    provider: String(source.provider || ''),
    version: String(source.version || '1.0'),
    type: String(source.type || 'preset'),
    status: String(source.status || 'ready'),
    official: !!source.official,
  };
}

const FALLBACK_PRESET_CHARACTERS = [
  ['character_sylvex', 'Sylvex', 'female', true],
  ['character_liz', 'Liz', 'female'],
  ['character_noah', 'Noah', 'male'],
  ['character_grace', 'Grace', 'female'],
  ['character_olivia', 'Olivia', 'female'],
  ['character_emily', 'Emily', 'female'],
  ['character_yasmin', 'Yasmin', 'female'],
  ['character_kingston', 'Kingston', 'male'],
  ['character_leo', 'Leo', 'male'],
  ['character_naomi', 'Naomi', 'female'],
  ['character_liam', 'Liam', 'male'],
  ['character_zara', 'Zara', 'female'],
  ['character_jax', 'Jax', 'male'],
  ['character_luca', 'Luca', 'male'],
  ['character_hiro', 'Hiro', 'male'],
  ['character_sofia', 'Sofia', 'female'],
].map((item, index) => normalizePresetCatalogItem({
  id: item[0],
  name: item[1],
  gender: item[2],
  official: !!item[3],
  avatarUrl: '',
  heygenPhotoAvatarId: item[0] === 'character_sylvex' ? 'afba3f7b836646c2a9fca9c4cca2c035' : '',
  heygenVideoAvatarId: item[0] === 'character_sylvex' ? 'f9cf885ac2594e4c8ab3762e251babec' : '',
  prompt: '',
  negativePrompt: '',
  referenceImages: [],
}, 'character', index));

const FALLBACK_PRESET_OBJECTS = [
  ['object_moka_pot', 'Moka Pot', 'Classic moka pot'],
  ['object_toaster', 'Toaster', 'Chrome toaster'],
  ['object_book', 'Book', 'Hardcover book'],
  ['object_lipstick', 'Lipstick', 'Red lipstick'],
  ['object_matcha_set', 'Matcha Set', 'Ceramic matcha set'],
  ['object_earpods', 'Earpods', 'Wireless earpods'],
  ['object_stilettos', 'Stilettos', 'Elegant stilettos'],
  ['object_water_bottle', 'Water Bottle', 'Minimal water bottle'],
  ['object_bag', 'Bag', 'Beige canvas tote bag'],
].map((item, index) => normalizePresetCatalogItem({
  id: item[0],
  name: item[1],
  description: item[2],
  avatarUrl: '',
  prompt: '',
  negativePrompt: '',
  referenceImages: [],
}, 'object', index));

let PRESET_CHARACTERS = FALLBACK_PRESET_CHARACTERS.slice();
let PRESET_OBJECTS = FALLBACK_PRESET_OBJECTS.slice();
let presetCatalogLoaded = false;
let presetCatalogLoading = null;

async function loadPresetCatalog(force) {
  if (presetCatalogLoaded && !force) {
    return { characters: PRESET_CHARACTERS, objects: PRESET_OBJECTS };
  }
  if (presetCatalogLoading && !force) return presetCatalogLoading;

  presetCatalogLoading = (async () => {
    try {
      const response = await fetch(PRESET_CATALOG_ENDPOINT, { method: 'GET', cache: 'default' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || data.error || ('HTTP ' + response.status));

      const rawCharacters = Array.isArray(data.characters)
        ? data.characters
        : (data.catalog && Array.isArray(data.catalog.characters) ? data.catalog.characters : []);
      const rawObjects = Array.isArray(data.objects)
        ? data.objects
        : (data.catalog && Array.isArray(data.catalog.objects) ? data.catalog.objects : []);

      if (rawCharacters.length) {
        PRESET_CHARACTERS = rawCharacters.map((item, index) => normalizePresetCatalogItem(item, 'character', index));
      }
      if (rawObjects.length) {
        PRESET_OBJECTS = rawObjects.map((item, index) => normalizePresetCatalogItem(item, 'object', index));
      }

      presetCatalogLoaded = true;
      window.dispatchEvent(new CustomEvent('sylvex:preset-catalog-loaded', {
        detail: {
          characters: PRESET_CHARACTERS.slice(),
          objects: PRESET_OBJECTS.slice(),
        },
      }));
    } catch (error) {
      console.warn('[SYLVEX] preset catalog failed, fallback presets are used', error);
    } finally {
      presetCatalogLoading = null;
    }

    return { characters: PRESET_CHARACTERS, objects: PRESET_OBJECTS };
  })();

  return presetCatalogLoading;
}

void loadPresetCatalog(false);

const MUSIC_MODEL_LIST = [
  { id:'suno_chirp_3_5', label:'Suno Chirp v3.5', providerModel:'chirp-v3-5', desc:'Suno music generation', icon:'suno', durations:[1,2] },
  { id:'suno_chirp_4_0', label:'Suno Chirp v4.0', providerModel:'chirp-v4-0', desc:'Suno music generation', icon:'suno', durations:[1,2,3,4] },
  { id:'suno_chirp_4_5', label:'Suno Chirp v4.5', providerModel:'chirp-v4-5', desc:'Suno music generation', icon:'suno', durations:[1,2,3,4] },
  { id:'suno_chirp_4_5_plus', label:'Suno Chirp v4.5 Plus', providerModel:'chirp-v4-5-plus', desc:'Suno music generation · расширенный стиль', icon:'suno', durations:[1,2,3,4] },
  { id:'suno_chirp_5', label:'Suno Chirp v5', providerModel:'chirp-v5', desc:'Suno music generation', icon:'suno', durations:[1,2,3,4] },
  { id:'suno_chirp_5_5', label:'Suno Chirp v5.5', providerModel:'chirp-v5-5', desc:'Suno music generation', icon:'suno', durations:[1,2,3,4] },
  { id:'minimax_music_2_5', label:'MiniMax Music 2.5', providerModel:'minimax-music-2.5', desc:'MiniMax text-to-music · отдельный API', icon:'minimax', durations:[1,2,3,4], capabilities:{ duration:false } },
  { id:'google_lyria_3_clip', label:'Google Lyria 3 Clip', providerModel:'lyria-3-clip-preview', desc:'Фиксированный музыкальный клип · 30 секунд · MP3', icon:'gemini', durations:[0.5], fixedDurationSeconds:30, capabilities:{ duration:false } },
  { id:'google_lyria_3_pro', label:'Google Lyria 3 Pro', providerModel:'lyria-3-pro-preview', desc:'Полноценные композиции · вокал и тексты · MP3', icon:'gemini', durations:[1,2] },
  { id:'google_lyria_realtime', label:'Google Lyria RealTime', providerModel:'models/lyria-realtime-exp', desc:'Экспериментальная потоковая инструментальная музыка · WAV', icon:'gemini', durations:[1,2,3,4], vocalModes:['auto','instrumental'] },
];

const VOICE_MODEL_LIST = [
  { id:'elevenlabs_eleven_v3', label:'ElevenLabs Eleven v3', providerModel:'eleven_v3', desc:'Эмоциональная озвучка и диалоги', icon:'elevenlabs' },
  { id:'gemini_3_1_flash_tts_preview', label:'Gemini 3.1 Flash TTS Preview', providerModel:'gemini-3.1-flash-tts-preview', desc:'Один или два диктора', icon:'gemini' },
  { id:'gemini_2_5_flash_preview_tts', label:'Gemini 2.5 Flash Preview TTS', providerModel:'gemini-2.5-flash-preview-tts', desc:'Быстрая озвучка Gemini', icon:'gemini' },
  { id:'gemini_2_5_pro_preview_tts', label:'Gemini 2.5 Pro Preview TTS', providerModel:'gemini-2.5-pro-preview-tts', desc:'Выразительная озвучка Gemini Pro', icon:'gemini' },
  { id:'elevenlabs_multilingual_v2', label:'ElevenLabs Multilingual v2', providerModel:'eleven_multilingual_v2', desc:'Стабильная многоязычная озвучка', icon:'elevenlabs' },
  { id:'elevenlabs_flash_v2_5', label:'ElevenLabs Flash v2.5', providerModel:'eleven_flash_v2_5', desc:'Быстрая озвучка с низкой задержкой', icon:'elevenlabs' },
  { id:'elevenlabs_flash_v2', label:'ElevenLabs Flash v2', providerModel:'eleven_flash_v2', desc:'Быстрая озвучка с низкой задержкой', icon:'elevenlabs' },
  { id:'elevenlabs_turbo_v2_5', label:'ElevenLabs Turbo v2.5', providerModel:'eleven_turbo_v2_5', desc:'Ускоренная генерация речи', icon:'elevenlabs' },
  { id:'elevenlabs_turbo_v2', label:'ElevenLabs Turbo v2', providerModel:'eleven_turbo_v2', desc:'Ускоренная генерация речи', icon:'elevenlabs' },
  { id:'elevenlabs_english_sts_v2', label:'ElevenLabs English STS v2', providerModel:'eleven_english_sts_v2', desc:'Изменение английского голоса', icon:'elevenlabs' },
  { id:'elevenlabs_multilingual_sts_v2', label:'ElevenLabs Multilingual STS v2', providerModel:'eleven_multilingual_sts_v2', desc:'Многоязычное изменение голоса', icon:'elevenlabs' },
  { id:'runway_eleven_multilingual_v2', label:'Runway Eleven Multilingual v2', providerModel:'eleven_multilingual_v2', desc:'Озвучка текста через Runway', icon:'runway' },
];

const TEXT_MODEL_LIST = [
  { id:'gpt-5.6', label:'GPT-5.6', versionLabel:'5.6', family:'gpt', providerModel:'gpt-5.6', desc:'Новейшая флагманская модель OpenAI', icon:'openai' },
  { id:'gpt-5.5', label:'GPT-5.5', versionLabel:'5.5', family:'gpt', providerModel:'gpt-5.5', desc:'Модель OpenAI для сложной профессиональной работы', icon:'openai' },
  { id:'gpt-5', label:'GPT-5', providerModel:'gpt-5', desc:'Флагманская модель для документов, анализа и промптов', icon:'openai' },
  { id:'gpt-5-mini', label:'GPT-5 mini', providerModel:'gpt-5-mini', desc:'Быстрый текст, документы и структурирование', icon:'openai' },
  { id:'gpt-4.1', label:'GPT-4.1', providerModel:'gpt-4.1', desc:'Сильная модель для длинных документов и задач', icon:'openai' },
  { id:'gpt-4.1-mini', label:'GPT-4.1 mini', providerModel:'gpt-4.1-mini', desc:'Быстрая генерация текста и промптов', icon:'openai' },
  { id:'gpt-4o', label:'GPT-4o', providerModel:'gpt-4o', desc:'Универсальная текстовая модель', icon:'openai' },
  { id:'gpt-4o-mini', label:'GPT-4o mini', providerModel:'gpt-4o-mini', desc:'Легкая модель для быстрых текстов', icon:'openai' },
  { id:'gemini_3_1_pro', label:'Gemini 3.1 Pro', providerModel:'gemini-3.1-pro', desc:'Google Gemini для документов, промптов и структурирования', icon:'gemini' },
  { id:'gemini_3_1_flash', label:'Gemini 3.1 Flash', providerModel:'gemini-3.1-flash', desc:'Быстрая Gemini-модель для текста и диалогов', icon:'gemini' },
  { id:'gemini_2_5_pro', label:'Gemini 2.5 Pro', providerModel:'gemini-2.5-pro', desc:'Gemini Pro для сложных текстовых задач', icon:'gemini' },
  { id:'gemini_2_5_flash', label:'Gemini 2.5 Flash', providerModel:'gemini-2.5-flash', desc:'Быстрая Gemini-модель для текстов и конспектов', icon:'gemini' },
  { id:'grok_4_1', label:'Grok 4.1', providerModel:'grok-4.1', desc:'xAI Grok для текстов, промптов и анализа', icon:'grok' },
  { id:'grok_4_fast', label:'Grok 4 Fast', providerModel:'grok-4-fast-reasoning', desc:'Быстрый Grok для генерации и структурирования', icon:'grok' },
  { id:'grok_3', label:'Grok 3', providerModel:'grok-3', desc:'Grok для универсальных текстовых задач', icon:'grok' },
  { id:'qwen_plus', label:'Qwen Plus', providerModel:'qwen-plus', desc:'Qwen для документов, промптов и диалогов', icon:'qwen' },
  { id:'qwen_turbo', label:'Qwen Turbo', providerModel:'qwen-turbo', desc:'Быстрый Qwen для текстов и конспектов', icon:'qwen' },
  { id:'qwen_max', label:'Qwen Max', providerModel:'qwen-max', desc:'Сильная Qwen-модель для длинных задач', icon:'qwen' },
  { id:'byteplus_seed_2_lite', label:'BytePlus Seed 2.0 Lite', providerModel:'seed-2-0-lite-260228', desc:'ModelArk Chat API для структурирования и генерации текста', icon:'bytedance' },
];

const TEXT_MODEL_FAMILIES = [
  { id:'gpt', label:'GPT', icon:'openai', defaultModel:'gpt-5.5' },
  { id:'gemini', label:'Gemini', icon:'gemini', defaultModel:'gemini_3_1_pro' },
  { id:'grok', label:'Grok', icon:'grok', defaultModel:'grok_4_1' },
  { id:'qwen', label:'Qwen', icon:'qwen', defaultModel:'qwen_plus' },
  { id:'byteplus', label:'BytePlus', icon:'bytedance', defaultModel:'byteplus_seed_2_lite' },
];

function textModelFamilyId(model) {
  const id = String((model && model.id) || model || '');
  if (id.startsWith('gpt-')) return 'gpt';
  if (id.startsWith('gemini_')) return 'gemini';
  if (id.startsWith('grok_')) return 'grok';
  if (id.startsWith('qwen_')) return 'qwen';
  return id.startsWith('byteplus_') ? 'byteplus' : 'gpt';
}

function textVersionsForFamily(familyId) {
  const family = String(familyId || 'gpt');
  const order = family === 'gpt' ? ['gpt-4o-mini','gpt-4o','gpt-4.1-mini','gpt-4.1','gpt-5-mini','gpt-5','gpt-5.5','gpt-5.6'] : [];
  return TEXT_MODEL_LIST.filter((item) => textModelFamilyId(item) === family).sort((a, b) => order.length ? order.indexOf(a.id) - order.indexOf(b.id) : 0).map((item) => Object.assign({}, item, {
    label: item.versionLabel || String(item.label || item.id).replace(/^(GPT|Gemini|Grok|Qwen|BytePlus)\s*/i, ''),
  }));
}

const TEXT_TOOL_OPTIONS = [
  { id:'text', label:'Текст' },
  { id:'document', label:'Документ' },
  { id:'prompt', label:'Промпт' },
  { id:'structured_dialogue', label:'Диалоги' },
  { id:'translate', label:'Перевод' },
  { id:'summarize', label:'Конспект' },
  { id:'rewrite', label:'Рерайт' },
  { id:'extract', label:'Извлечь текст' },
  { id:'image_prompt', label:'Промпт по фото' },
  { id:'video_prompt', label:'Промпт по видео' },
  { id:'audio_to_text', label:'Аудио → текст' },
  { id:'video_to_text', label:'Видео → текст' },
];

const TEXT_GEMINI_MEDIA_TOOLS = new Set(['video_prompt', 'audio_to_text', 'video_to_text']);

function textToolOptionsForCurrentModel() {
  const family = textState.familyId || textModelFamilyId(currentTextModel());
  return TEXT_TOOL_OPTIONS.filter((item) => !TEXT_GEMINI_MEDIA_TOOLS.has(item.id) || family === 'gemini');
}

function normalizeTextToolForModel() {
  if (!textToolOptionsForCurrentModel().some((item) => item.id === textState.tool)) textState.tool = 'text';
}

function selectGeminiForTextMedia() {
  textState.familyId = 'gemini';
  if (textModelFamilyId(textState.modelId) !== 'gemini') textState.modelId = 'gemini_3_1_pro';
}

const TEXT_STYLE_OPTIONS = [
  { id:'neutral', label:'Нейтрально' },
  { id:'business', label:'Бизнес' },
  { id:'creative', label:'Креатив' },
  { id:'technical', label:'Технично' },
  { id:'telegram', label:'Telegram' },
];

const TEXT_FORMAT_OPTIONS = [
  { id:'markdown', label:'Markdown' },
  { id:'plain', label:'Обычный текст' },
  { id:'pdf', label:'PDF' },
];

const GEMINI_TTS_VOICES = [
  ['Zephyr', 'Bright'], ['Puck', 'Upbeat'], ['Charon', 'Informative'],
  ['Kore', 'Firm'], ['Fenrir', 'Excitable'], ['Leda', 'Youthful'],
  ['Orus', 'Firm'], ['Aoede', 'Breezy'], ['Callirrhoe', 'Easy-going'],
  ['Autonoe', 'Bright'], ['Enceladus', 'Breathy'], ['Iapetus', 'Clear'],
  ['Umbriel', 'Easy-going'], ['Algieba', 'Smooth'], ['Despina', 'Smooth'],
  ['Erinome', 'Clear'], ['Algenib', 'Gravelly'], ['Rasalgethi', 'Informative'],
  ['Laomedeia', 'Upbeat'], ['Achernar', 'Soft'], ['Alnilam', 'Firm'],
  ['Schedar', 'Even'], ['Gacrux', 'Mature'], ['Pulcherrima', 'Forward'],
  ['Achird', 'Friendly'], ['Zubenelgenubi', 'Casual'], ['Vindemiatrix', 'Gentle'],
  ['Sadachbia', 'Lively'], ['Sadaltager', 'Knowledgeable'], ['Sulafat', 'Warm'],
].map(([id, style]) => ({ id, label:id, style }));

const RUNWAY_TTS_VOICES = [
  ['Maya', 'female', 'Мягкий универсальный голос для роликов и повествования'],
  ['Noah', 'male', 'Спокойный мужской голос для объяснений и историй'],
  ['Bernard', 'male', 'Зрелый уверенный голос для деловой озвучки'],
  ['Arjun', 'male', 'Выразительный голос для презентаций и рассказов'],
].map(([id, gender, description]) => ({ id, label:id, gender, description }));

let runwayVoiceList = RUNWAY_TTS_VOICES.slice();

const ELEVENLABS_TTS_VOICES = [
  ['21m00Tcm4TlvDq8ikWAM', 'Rachel'],
].map(([id, label]) => ({ id, label }));

let elevenlabsVoiceList = ELEVENLABS_TTS_VOICES.slice();

function userVoiceItems() {
  const list = serverVisualItems && Array.isArray(serverVisualItems.voices) ? serverVisualItems.voices : [];
  return list.map((item) => {
    const voiceId = String((item && (item.voice_id || item.voiceId || item.id)) || '').trim();
    const resourceId = String((item && item.id) || ('custom_voice_' + voiceId)).trim();
    const name = String((item && (item.name || item.label)) || voiceId).trim();
    const avatarUrl = String((item && (item.avatarUrl || item.avatar_url || item.previewUrl || item.preview_url)) || '').trim();
    if (!voiceId) return null;
    return {
      id: voiceId,
      resourceId,
      label: name,
      name,
      provider: 'elevenlabs',
      type: 'custom',
      custom: true,
      gender: item.gender || '',
      avatarUrl,
      previewUrl: item.previewUrl || item.preview_url || avatarUrl,
    };
  }).filter(Boolean);
}

function mergeUserVoicesWithProvider(list) {
  const user = userVoiceItems();
  const seen = new Set(user.map((item) => String(item.id)));
  return user.concat((list || []).filter((item) => {
    const id = String(item && item.id || '');
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  }));
}

function voiceAvatarLookupKeys(value, provider) {
  const raw = String(value || '').trim();
  const slug = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  const base = [raw.toLowerCase(), slug].filter(Boolean);
  const providerKey = String(provider || '').trim().toLowerCase();
  return providerKey ? base.concat(base.map((key) => providerKey + ':' + key)) : base;
}

function rememberVoiceAvatar(voiceId, provider, avatarUrl) {
  const url = String(avatarUrl || '').trim();
  if (!url) return;
  voiceAvatarLookupKeys(voiceId, provider).forEach((key) => {
    voiceAvatarCatalog[key] = url;
  });
}

function voiceAvatarUrlFor(item, provider) {
  if (!item || typeof item !== 'object') return '';
  const own = String(item.avatarUrl || item.avatar_url || item.imageUrl || item.image_url || '').trim();
  if (own) return own;
  const id = item.id || item.voice_id || item.voiceId || item.name || '';
  const itemProvider = provider || item.provider || '';
  const keys = voiceAvatarLookupKeys(id, itemProvider);
  for (const key of keys) {
    if (voiceAvatarCatalog[key]) return voiceAvatarCatalog[key];
  }
  return '';
}

function applyVoiceAvatarsToList(list, provider) {
  return (Array.isArray(list) ? list : []).map((item) => {
    if (!item || typeof item !== 'object') return item;
    const avatarUrl = voiceAvatarUrlFor(item, provider);
    return avatarUrl ? Object.assign({}, item, { avatarUrl, avatar_url: avatarUrl }) : item;
  });
}

const VOICE_STYLE_RU = {
  Bright:'яркий', Upbeat:'бодрый', Informative:'информативный', Firm:'уверенный',
  Excitable:'эмоциональный', Youthful:'молодой', Breezy:'лёгкий', 'Easy-going':'непринуждённый',
  Breathy:'мягкий с придыханием', Clear:'чёткий', Smooth:'плавный', Gravelly:'хрипловатый',
  Soft:'мягкий', Even:'ровный', Mature:'зрелый', Forward:'напористый', Friendly:'дружелюбный',
  Casual:'разговорный', Gentle:'нежный', Lively:'живой', Knowledgeable:'компетентный', Warm:'тёплый'
};

function voiceInitials(value) {
  const clean = String(value || 'Голос').replace(/[^a-zа-яё0-9]/gi, '').toUpperCase();
  return (clean.slice(0, 3) || 'VOX').padEnd(3, 'X');
}

function voiceAvatarStyle(value) {
  const text = String(value || 'voice');
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  const hue1 = Math.abs(hash) % 360;
  const hue2 = (hue1 + 75 + (Math.abs(hash >> 7) % 70)) % 360;
  const hue3 = (hue2 + 75 + (Math.abs(hash >> 13) % 70)) % 360;
  return '--voice-c1:hsl(' + hue1 + ' 82% 58%);--voice-c2:hsl(' + hue2 + ' 78% 54%);--voice-c3:hsl(' + hue3 + ' 84% 62%)';
}

function voiceDescription(item) {
  const genderId = voiceGenderForPanel(item);
  const gender = genderId === 'male' ? 'Мужской голос' : (genderId === 'female' ? 'Женский голос' : 'Нейтральный голос');
  const rawStyle = String((item && (item.style || item.description || item.useCase || item.use_case)) || '').trim();
  const style = rawStyle;
  const accent = String((item && item.accent) || '').trim();
  if (style) return gender + ' · ' + style;
  if (accent) return gender + ' · ' + accent + ' accent';
  return gender + ' · Universal voice';
}

async function loadVoiceAvatarCatalog(force) {
  if (voiceAvatarCatalogLoaded && !force) return voiceAvatarCatalog;
  if (voiceAvatarCatalogLoading && !force) return voiceAvatarCatalogLoading;
  voiceAvatarCatalogLoading = (async () => {
    try {
      const res = await fetch('/api/public/prostudio/voice-avatars', { method: 'GET', cache: 'no-store' });
      const data = await res.json().catch(() => ({}));
      const avatars = Array.isArray(data.avatars) ? data.avatars : [];
      avatars.forEach((item) => {
        rememberVoiceAvatar(item.voice_id || item.voiceId || item.id, item.provider || '', item.avatarUrl || item.avatar_url);
      });
      voiceAvatarPendingCount = Math.max(0, Number(data.pending_count || 0));
      voiceAvatarCatalogLoaded = true;
      if (voiceAvatarPendingCount > 0 && voiceAvatarPollAttempts < 75) scheduleVoiceAvatarCatalogPoll();
    } catch (err) {
      console.warn('[SYLVEX] voice avatars failed', err);
    } finally {
      voiceAvatarCatalogLoading = null;
    }
    return voiceAvatarCatalog;
  })();
  return voiceAvatarCatalogLoading;
}

function scheduleVoiceAvatarCatalogPoll() {
  if (voiceAvatarPollTimer) return;
  voiceAvatarPollTimer = window.setTimeout(async () => {
    voiceAvatarPollTimer = null;
    voiceAvatarPollAttempts += 1;
    await loadVoiceAvatarCatalog(true);
    if (isVoiceMode()) {
      renderVoiceControls();
      if (activeVoicePanelSection === 'voices') renderVoiceToolPanel();
    }
  }, 4000);
}

async function ensureGeneratedVoiceAvatars(items) {
  voiceAvatarPollAttempts = 0;
  const provider = isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini');
  const voices = (Array.isArray(items) ? items : []).slice(0, 100).map((item) => ({
    provider: item.provider || provider,
    voice_id: item.voice_id || item.voiceId || item.id || item.name,
  })).filter((item) => item.voice_id);
  if (!voices.length) return;
  try {
    const res = await fetch('/api/public/prostudio/voice-avatars/ensure', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ voices }),
    });
    const data = await res.json().catch(() => ({}));
    (Array.isArray(data.avatars) ? data.avatars : []).forEach((item) => {
      rememberVoiceAvatar(item.voice_id || item.voiceId || item.id, item.provider || '', item.avatarUrl || item.avatar_url);
    });
    voiceAvatarPendingCount = Math.max(0, Number(data.pending_count || 0));
    if (voiceAvatarPendingCount > 0) scheduleVoiceAvatarCatalogPoll();
    renderVoiceControls();
  } catch (err) {
    console.warn('[SYLVEX] voice avatar generation scheduling failed', err);
  }
}

void loadVoiceAvatarCatalog(false);

const ELEVENLABS_AUDIO_TOOLS = [
  { id:'text_to_speech', label:'Озвучить текст' },
  { id:'speech_to_speech', label:'Изменить голос записи' },
  { id:'dialogue', label:'Диалог нескольких дикторов' },
  { id:'dubbing', label:'Перевести и озвучить' },
  { id:'voice_design', label:'Создать голос по описанию' },
];

const RUNWAY_AUDIO_TOOLS = [
  { id:'text_to_speech', label:'Озвучить текст' },
  { id:'sound_effect', label:'Создать звуковой эффект' },
  { id:'speech_to_speech', label:'Изменить голос записи' },
  { id:'voice_dubbing', label:'Перевести и озвучить' },
  { id:'voice_isolation', label:'Очистить голос от шума' },
];

const RUNWAY_DUBBING_LANGUAGES = [
  { id:'en', label:'English' },
  { id:'ru', label:'Русский' },
  { id:'es', label:'Español' },
  { id:'fr', label:'Français' },
  { id:'de', label:'Deutsch' },
  { id:'it', label:'Italiano' },
  { id:'pt', label:'Português' },
  { id:'tr', label:'Türkçe' },
  { id:'ar', label:'العربية' },
  { id:'hi', label:'Hindi' },
  { id:'ja', label:'日本語' },
  { id:'ko', label:'한국어' },
  { id:'zh', label:'中文' },
];

const RUNWAY_SOUND_DURATIONS = [
  { id:'3', label:'3 сек' },
  { id:'5', label:'5 сек' },
  { id:'10', label:'10 сек' },
  { id:'15', label:'15 сек' },
  { id:'30', label:'30 сек' },
];

const VOICE_UPLOAD_PURPOSES = [
  { id:'voiceover', label:'Озвучка', hint:'Озвучить текст или сценарий', accept:'audio/*,video/*', gemini:true, elevenlabs:true, runway:true, elevenlabsTool:'text_to_speech', runwayTool:'text_to_speech', needsFile:false, speakers:true, languages:false },
  { id:'translate_voiceover', label:'Перевести и озвучить', hint:'Перевести текст и озвучить выбранным голосом', accept:'audio/*,video/*', gemini:false, elevenlabs:true, runway:true, elevenlabsTool:'dubbing', runwayTool:'voice_dubbing', needsFile:true, speakers:false, languages:true },
  { id:'dub_video', label:'Озвучить видео', hint:'Наложить новую озвучку на видео без lip-sync', accept:'video/*', gemini:false, elevenlabs:true, runway:false, elevenlabsTool:'text_to_speech', runwayTool:'text_to_speech', needsFile:true, speakers:false, languages:false },
  { id:'translate_audio', label:'Перевести аудио', hint:'Дубляж или перевод аудиофайла', accept:'audio/*', gemini:false, elevenlabs:true, runway:true, elevenlabsTool:'dubbing', runwayTool:'voice_dubbing', needsFile:true, speakers:false, languages:true },
  { id:'speech_to_speech', label:'Копировать голос', hint:'Преобразовать аудио в выбранный голос', accept:'audio/*', gemini:false, elevenlabs:true, runway:true, elevenlabsTool:'speech_to_speech', runwayTool:'speech_to_speech', needsFile:true, speakers:true, languages:false },
  { id:'isolate_voice', label:'Очистить голос', hint:'Отделить голос от шума или музыки', accept:'audio/*,video/*', gemini:false, elevenlabs:false, runway:true, elevenlabsTool:'speech_to_speech', runwayTool:'voice_isolation', needsFile:true, speakers:false, languages:false },
  { id:'sound_effect', label:'Звуковой эффект', hint:'Создать звуковой эффект по описанию', accept:'', gemini:false, elevenlabs:false, runway:true, elevenlabsTool:'text_to_speech', runwayTool:'sound_effect', needsFile:false, speakers:false, languages:false },
  { id:'document_voiceover', label:'Озвучить документ', hint:'Извлечь текст из TXT, PDF или DOCX и озвучить выбранным голосом', accept:'.txt,.pdf,.docx', gemini:true, elevenlabs:true, runway:true, elevenlabsTool:'text_to_speech', runwayTool:'text_to_speech', needsFile:true, speakers:true, languages:false },
  { id:'document_translate_voiceover', label:'Перевести документ и озвучить', hint:'Извлечь текст, перевести через OpenAI и озвучить выбранным голосом', accept:'.txt,.pdf,.docx', gemini:true, elevenlabs:true, runway:true, elevenlabsTool:'text_to_speech', runwayTool:'text_to_speech', needsFile:true, speakers:true, languages:true },
];

const VOICE_SPEAKER_COUNT_OPTIONS = [
  { id:'1', label:'1 диктор' },
  { id:'2', label:'2 диктора' },
  { id:'3', label:'3 диктора' },
  { id:'4', label:'4 диктора' },
  { id:'5', label:'5 дикторов' },
  { id:'6', label:'6 дикторов' },
  { id:'7', label:'7 дикторов' },
];

const VOICE_SPEAKER_MODES = [
  { id:'single', label:'Один голос' },
  { id:'multi', label:'Два голоса' },
];

// =====================================================
// АУДИОПЛЕЕР: isRunwayVoiceModel
// Проверяет, относится ли выбранная модель озвучки к Runway, чтобы открыть правильные голоса и payload.
// =====================================================
function isRunwayVoiceModel(modelId) {
  const model = VOICE_MODEL_LIST.find((item) => item.id === modelId);
  return String(modelId || '').indexOf('runway_') === 0 || String((model && model.id) || '').indexOf('runway_') === 0;
}

// =====================================================
// АУДИОПЛЕЕР: isElevenLabsVoiceModel
// Проверяет, относится ли выбранная модель озвучки к ElevenLabs.
// =====================================================
function isElevenLabsVoiceModel(modelId) {
  const model = VOICE_MODEL_LIST.find((item) => item.id === modelId);
  return String(modelId || '').indexOf('elevenlabs_') === 0 || String((model && model.id) || '').indexOf('elevenlabs_') === 0;
}

// =====================================================
// АУДИОПЛЕЕР: runwayToolLabel
// Возвращает человекочитаемое название выбранного инструмента Runway для кнопок Mini App.
// =====================================================
function runwayToolLabel(toolId) {
  const item = RUNWAY_AUDIO_TOOLS.find((tool) => tool.id === toolId);
  return (item && item.label) || 'Озвучить текст';
}

// =====================================================
// АУДИОПЛЕЕР: elevenlabsToolLabel
// Возвращает название выбранного инструмента ElevenLabs для кнопок Mini App.
// =====================================================
function elevenlabsToolLabel(toolId) {
  const item = ELEVENLABS_AUDIO_TOOLS.find((tool) => tool.id === toolId);
  return (item && item.label) || 'Озвучить текст';
}

// =====================================================
// БЛОК ОЗВУЧКИ: voiceProviderKey
// Возвращает активного провайдера озвучки, чтобы показывать только доступные цели загрузки.
// =====================================================
function voiceProviderKey(modelId) {
  if (isElevenLabsVoiceModel(modelId || voiceState.modelId)) return 'elevenlabs';
  if (isRunwayVoiceModel(modelId || voiceState.modelId)) return 'runway';
  return 'gemini';
}

// =====================================================
// БЛОК ОЗВУЧКИ: voiceUploadPurposeMeta
// Достаёт описание цели загрузки: дубляж, перевод, speech-to-speech, очистка голоса и т.д.
// =====================================================
function voiceUploadPurposeMeta(purposeId) {
  return VOICE_UPLOAD_PURPOSES.find((item) => item.id === purposeId) || VOICE_UPLOAD_PURPOSES[0];
}

// =====================================================
// БЛОК ОЗВУЧКИ: isVoicePurposeSupported
// Проверяет, поддерживает ли выбранная модель цель загрузки.
// Неподдерживаемые цели остаются в списке, но становятся некликабельными.
// =====================================================
function isVoicePurposeSupported(purpose, modelId) {
  const meta = typeof purpose === 'string' ? voiceUploadPurposeMeta(purpose) : purpose;
  const provider = voiceProviderKey(modelId);
  return !!(meta && meta[provider]);
}

// =====================================================
// БЛОК ОЗВУЧКИ: applyVoiceUploadPurpose
// Сохраняет выбранную цель загрузки и синхронизирует её с реальными tool-параметрами provider API.
// =====================================================
function applyVoiceUploadPurpose(purposeId) {
  const meta = voiceUploadPurposeMeta(purposeId);
  if (!isVoicePurposeSupported(meta)) return false;
  voiceState.uploadPurpose = meta.id;
  if (isElevenLabsVoiceModel(voiceState.modelId)) voiceState.elevenlabsTool = meta.elevenlabsTool || voiceState.elevenlabsTool || 'text_to_speech';
  if (isRunwayVoiceModel(voiceState.modelId)) voiceState.runwayTool = meta.runwayTool || voiceState.runwayTool || 'text_to_speech';
  if (meta.languages) {
    if (!voiceState.targetLanguage) voiceState.targetLanguage = voiceState.elevenlabsTargetLanguage || voiceState.runwayTargetLanguage || 'en';
    voiceState.elevenlabsTargetLanguage = voiceState.targetLanguage;
    voiceState.runwayTargetLanguage = voiceState.targetLanguage;
  }
  if (!meta.speakers) {
    voiceState.numSpeakers = 1;
    voiceState.speakerMode = 'single';
  }
  return true;
}

// =====================================================
// БЛОК ОЗВУЧКИ: voiceSpeakerVoiceValue
// Возвращает голос конкретного диктора для панели загрузки и payload.
// =====================================================
function voiceSpeakerVoiceValue(index) {
  const voices = Array.isArray(voiceState.speakerVoices) ? voiceState.speakerVoices : [];
  if (voiceWorkspaceMode === 'dialogue') return String(voices[index] || '');
  if (index === 0) {
    if (isElevenLabsVoiceModel(voiceState.modelId)) return voiceState.elevenlabsVoice || voices[0] || '21m00Tcm4TlvDq8ikWAM';
    if (isRunwayVoiceModel(voiceState.modelId)) return voiceState.runwayVoice || voices[0] || 'Maya';
    return voiceState.voice || voices[0] || 'Kore';
  }
  if (index === 1) {
    return voices[1] || '';
  }
  return voices[index] || '';
}

// =====================================================
// АУДИОПЛЕЕР: normalizeRunwayVoiceItems
// Приводит список голосов Runway API к формату шторки Mini App.
// =====================================================
function normalizeRunwayVoiceItems(items) {
  const list = Array.isArray(items) ? items : [];
  const mapped = list.map((item) => {
    const id = String(item.voice_id || item.voiceId || item.id || item.name || '').trim();
    const name = String(item.name || item.label || id).trim();
    const avatarUrl = item.avatarUrl || item.avatar_url || '';
    if (!id) return null;
    rememberVoiceAvatar(id, 'runway', avatarUrl);
    return {
      id,
      label: name || id,
      previewUrl: item.preview_url || item.previewUrl || '',
      avatarUrl,
      gender: item.gender || item.sex || '',
      description: item.description || item.use_case || item.useCase || '',
      accent: item.accent || '',
    };
  }).filter(Boolean);
  return mapped.length ? mapped : RUNWAY_TTS_VOICES.slice();
}

// =====================================================
// АУДИОПЛЕЕР: loadRunwayVoices
// Загружает реальные голоса Runway для выбора и прослушивания в Mini App.
// =====================================================
async function loadRunwayVoices(force) {
  if (runwayVoiceListLoaded && !force) return runwayVoiceList;
  if (runwayVoiceListLoading && !force) return runwayVoiceListLoading;
  runwayVoiceListLoading = (async () => { try {
    const res = await fetch('/api/public/prostudio/runway-voices', { method: 'GET' });
    const data = await res.json().catch(() => ({}));
    if (res.ok && (data.ok || data.success)) {
      runwayVoiceList = normalizeRunwayVoiceItems(data.voices || []);
      runwayVoiceListLoaded = true;
    }
  } catch (err) {
    console.warn('[SYLVEX] runway voices failed', err);
  } finally { runwayVoiceListLoading = null; }
  return runwayVoiceList; })();
  return runwayVoiceListLoading;
}

// =====================================================
// АУДИОПЛЕЕР: normalizeElevenLabsVoiceItems
// Приводит список голосов ElevenLabs API к формату общей шторки выбора голоса.
// =====================================================
function normalizeElevenLabsVoiceItems(items) {
  const list = Array.isArray(items) ? items : [];
  const mapped = list.map((item) => {
    const id = String(item.voice_id || item.voiceId || item.id || '').trim();
    const name = String(item.name || item.label || id).trim();
    const meta = [item.language, item.type || item.category].filter(Boolean).join(' · ');
    const avatarUrl = item.avatarUrl || item.avatar_url || '';
    if (!id) return null;
    rememberVoiceAvatar(id, 'elevenlabs', avatarUrl);
    return {
      id,
      label: name + (meta ? ' · ' + meta : ''),
      previewUrl: item.preview_url || item.previewUrl || '',
      avatarUrl,
      gender: item.gender || item.labels && item.labels.gender || item.voice_gender || '',
      description: item.description || item.use_case || item.useCase || item.labels && (item.labels.description || item.labels.use_case) || '',
      accent: item.accent || item.labels && item.labels.accent || '',
    };
  }).filter(Boolean);
  return mapped.length ? mapped : ELEVENLABS_TTS_VOICES.slice();
}

// =====================================================
// АУДИОПЛЕЕР: loadElevenLabsVoices
// Загружает голоса ElevenLabs для выбора и прослушивания в Mini App.
// =====================================================
async function loadElevenLabsVoices(force) {
  if (elevenlabsVoiceListLoaded && !force) return elevenlabsVoiceList;
  if (elevenlabsVoiceListLoading && !force) return elevenlabsVoiceListLoading;
  elevenlabsVoiceListLoading = (async () => { try {
    const res = await fetch('/api/public/prostudio/elevenlabs-voices', { method: 'GET' });
    const data = await res.json().catch(() => ({}));
    if (res.ok && (data.ok || data.success)) {
      elevenlabsVoiceList = normalizeElevenLabsVoiceItems(data.voices || []);
      elevenlabsVoiceListLoaded = true;
    }
  } catch (err) {
    console.warn('[SYLVEX] elevenlabs voices failed', err);
  } finally { elevenlabsVoiceListLoading = null; }
  return elevenlabsVoiceList; })();
  return elevenlabsVoiceListLoading;
}

const MUSIC_GENRES = [
  ['auto', 'Auto'],
  ['pop', 'Pop'],
  ['rock', 'Rock'],
  ['hip_hop', 'Hip-Hop'],
  ['rap', 'Rap'],
  ['trap', 'Trap'],
  ['rnb', 'R&B'],
  ['jazz', 'Jazz'],
  ['funk', 'Funk'],
  ['soul', 'Soul'],
  ['folk', 'Folk'],
  ['electronic', 'Electronic'],
  ['edm', 'EDM'],
  ['house', 'House'],
  ['techno', 'Techno'],
  ['ambient', 'Ambient'],
  ['lofi', 'Lo-fi'],
  ['cinematic', 'Cinematic'],
  ['classical', 'Classical'],
  ['metal', 'Metal'],
  ['reggae', 'Reggae'],
  ['latin', 'Latin'],
  ['arabic', 'Arabic'],
  ['turkish', 'Turkish'],
  ['russian_pop', 'Russian Pop'],
  ['phonk', 'Phonk'],
  ['drill', 'Drill'],
  ['afrobeat', 'Afrobeat'],
  ['country', 'Country'],
  ['blues', 'Blues'],
  ['punk', 'Punk'],
  ['disco', 'Disco'],
].map(([id, label]) => ({ id, label }));

const MUSIC_SETTINGS = {
  mood: {
    title: 'Настроение',
    items: [
      ['auto', 'Авто'],
      ['happy', 'Счастливое'],
      ['inspiring', 'Вдохновляющее'],
      ['sad', 'Грустное'],
      ['dramatic', 'Драматичное'],
      ['dark', 'Тёмное'],
      ['dreamy', 'Мечтательное'],
      ['aggressive', 'Агрессивное'],
      ['funny', 'Забавное'],
      ['cold', 'Холодное'],
      ['epic', 'Эпическое'],
      ['energetic', 'Энергичное'],
    ],
  },
  tempo: {
    title: 'Темп',
    items: [
      ['auto', 'Авто'],
      ['slow', 'Медленный'],
      ['slow_medium', 'Медленно-средний'],
      ['medium', 'Средний'],
      ['medium_fast', 'Средне-быстрый'],
      ['fast', 'Быстрый'],
    ],
  },
  theme: {
    title: 'Тема',
    items: [
      ['auto', 'Авто'],
      ['love', 'Любовь'],
      ['party', 'Вечеринка'],
      ['comedy', 'Комедия'],
      ['cinema', 'Кино'],
      ['motivation', 'Мотивация'],
      ['sport', 'Спорт'],
      ['ads', 'Реклама'],
      ['game', 'Игра'],
      ['travel', 'Путешествие'],
      ['night', 'Ночь'],
      ['future', 'Будущее'],
      ['drama', 'Драма'],
    ],
  },
  vocal: {
    title: 'Вокал',
    items: [
      ['auto', 'Авто'],
      ['instrumental', 'Инструментал'],
      ['with_vocals', 'С вокалом'],
      ['female', 'Женский вокал'],
      ['male', 'Мужской вокал'],
    ],
  },
};

Object.keys(MUSIC_SETTINGS).forEach((key) => {
  MUSIC_SETTINGS[key].items = MUSIC_SETTINGS[key].items.map(([id, label]) => ({ id, label }));
});

const VIDEO_MODELS = [
  { id:'heygen_v3_video_agent', label:'HeyGen V3 Video Agent', desc:'HeyGen video model', icon:'heygen' },
  { id:'heygen_avatar_iv', label:'HeyGen Avatar IV', desc:'HeyGen avatar engine', icon:'heygen' },
  { id:'heygen_avatar_v', label:'HeyGen Avatar V', desc:'HeyGen high fidelity avatar engine', icon:'heygen' },
  { id:'heygen_avatar_iii', label:'HeyGen Avatar III', desc:'HeyGen avatar engine', icon:'heygen' },
  { id:'heygen_image_video', label:'HeyGen Image Video', desc:'HeyGen image to avatar video', icon:'heygen' },
  { id:'heygen_cinematic_avatar', label:'HeyGen Cinematic Avatar', desc:'HeyGen cinematic avatar generation', icon:'heygen' },

  { id:'luma_ray_v3_2', label:'Luma Ray v3.2', desc:'Luma AI video model', icon:'luma' },
  { id:'luma_dream_machine', label:'Luma Dream Machine', desc:'Luma Dream Machine', icon:'dreamMachine' },

  { id:'minimax_hailuo_2_3', label:'MiniMax Hailuo 2.3', desc:'MiniMax Hailuo video', icon:'hailuo' },

  { id:'pixverse_v6', label:'PixVerse v6', desc:'PixVerse video model', icon:'pixverse' },

  { id:'sora_2', label:'Sora 2', desc:'OpenAI Sora video', icon:'sora' },
  { id:'sora_2_pro', label:'Sora 2 Pro', desc:'OpenAI Sora video', icon:'sora' },

  { id:'wan_2_6', label:'Wan 2.6', desc:'Alibaba Wan video model', icon:'wan' },
  { id:'wan_2_7', label:'Wan 2.7', desc:'Alibaba Wan video model', icon:'wan' },
  { id:'wan_2_7_edit', label:'Wan 2.7 Edit', desc:'Wan video editing model', icon:'wan' },

  { id:'veo_3_1', label:'Veo 3.1', desc:'Google Veo video model', icon:'veo', badge:'RECOMMENDED', badgeClass:'pink' },
  { id:'veo_3_1_fast', label:'Veo 3.1 Fast', desc:'Google Veo fast video', icon:'veo', badge:'FAST', badgeClass:'yellow' },

  { id:'grok_video', label:'Grok Video', desc:'xAI Grok video model', icon:'grok', badge:'BUDGET', badgeClass:'green' },
  { id:'grok_video_edit', label:'Grok Video Edit', desc:'xAI Grok video editing', icon:'grok' },

  { id:'runway_gen4_5', label:'Runway Gen-4.5', desc:'Runway text/image to video model', icon:'runway' },
  { id:'runway_gen4_turbo', label:'Runway Gen-4 Turbo', desc:'Runway image to video model', icon:'runway' },
  { id:'runway_aleph2', label:'Runway Aleph 2.0', desc:'Runway video to video editing model', icon:'runway' },
  { id:'runway_aleph', label:'Runway Gen-4 Aleph', desc:'Runway deprecated video edit model', icon:'runway' },
  { id:'runway_gen3a_turbo', label:'Runway Gen-3 Alpha Turbo', desc:'Runway deprecated image to video model', icon:'runway' },
  { id:'runway_happyhorse_1_0', label:'Runway HappyHorse 1.0', desc:'HappyHorse via Runway API', icon:'runway' },

  { id:'kling_3_0_turbo', label:'Kling 3.0 Turbo', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_3_0', label:'Kling 3.0', desc:'Kling video model', icon:'kling', badge:'DISCOUNT', badgeClass:'green' },
  { id:'kling_o3_omni', label:'Kling 3.0 Omni', desc:'Kling Omni video model', icon:'kling', badge:'HOT', badgeClass:'red' },
  { id:'kling_o3_edit', label:'Kling 3.0 Omni Edit', desc:'Kling Omni video editing model', icon:'kling' },
  { id:'kling_motion_2_6', label:'Kling Motion 2.6', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_motion_3_0', label:'Kling Motion 3.0', desc:'Kling Omni motion alias', icon:'kling' },
  { id:'kling_effects', label:'Kling Video Effects', desc:'Kling official video effects', icon:'kling' },
  { id:'kling_o1', label:'Kling O1', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_2_6', label:'Kling 2.6', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_2_5_turbo', label:'Kling 2.5 Turbo', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_2_1', label:'Kling 2.1', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_2_1_master', label:'Kling 2.1 Master', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_2_0_master', label:'Kling 2.0 Master', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_1_6', label:'Kling 1.6', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_1_5', label:'Kling 1.5', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_1_0', label:'Kling 1.0', desc:'Kling AI video model', icon:'kling' },

  { id:'seedance_1_5_pro', label:'Seedance 1.5 Pro', desc:'ByteDance Seedance video', icon:'seedance' },
  { id:'seedance_2_fast', label:'Seedance 2.0 Fast', desc:'ByteDance Seedance fast video', icon:'seedance', badge:'FAST', badgeClass:'yellow' },
  { id:'seedance_2_0', label:'Seedance 2.0', desc:'ByteDance Seedance video', icon:'seedance', badge:'TRENDING', badgeClass:'pink' },

  { id:'gemini_omni_flash', label:'Gemini Omni Flash', desc:'Google Gemini video model', icon:'gemini' }
];

const VIDEO_MODEL_CONFIG = {
  heygen_v3_video_agent: { provider:'heygen', modes:['text_to_video'], durations:[5], ratios:['16:9','9:16'], resolutions:['720p','1080p'], sound:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  heygen_avatar_iv: { provider:'heygen', modes:['text_to_video'], durations:[5], ratios:['auto','16:9','9:16','4:5','5:4','1:1'], resolutions:['720p','1080p'], sound:true, avatar:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  heygen_avatar_v: { provider:'heygen', modes:['text_to_video'], durations:[5], ratios:['auto','16:9','9:16','4:5','5:4','1:1'], resolutions:['720p','1080p'], sound:true, avatar:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  heygen_avatar_iii: { provider:'heygen', modes:['text_to_video'], durations:[5], ratios:['auto','16:9','9:16','4:5','5:4','1:1'], resolutions:['720p','1080p','4k'], sound:true, avatar:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  heygen_image_video: { provider:'heygen', modes:['image_to_video'], durations:[5], ratios:['auto','16:9','9:16','4:5','5:4','1:1'], resolutions:['720p','1080p'], sound:true, avatar:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  heygen_cinematic_avatar: { provider:'heygen', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:true, avatar:true, start_image:true, end_image:false, video_upload:true, video_edit:false },
  luma_ray_v3_2: { provider:'luma', modes:['text_to_video','image_to_video','video_edit','video_reframe'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:true, video_upload:true, video_edit:true },
  luma_dream_machine: { provider:'luma', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  minimax_hailuo_2_3: { provider:'minimax', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  pixverse_v6: { provider:'pixverse', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  sora_2_pro: { provider:'sora', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  wan_2_7: { provider:'wan', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1','4:3','3:4'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:true, video_upload:true, video_edit:false },
  veo_3_1: { provider:'veo', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  grok_video_edit: { provider:'grok', modes:['video_edit'], durations:[5], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:false, end_image:false, video_upload:true, video_edit:true },
  wan_2_7_edit: { provider:'wan', modes:['video_edit'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:false, end_image:false, video_upload:true, video_edit:true },
  runway_gen4_5: { provider:'runway', modes:['text_to_video','image_to_video'], durations:[2,3,4,5,6,7,8,9,10], ratios:['16:9','9:16','1:1','4:3','3:4','21:9'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_gen4_turbo: { provider:'runway', modes:['image_to_video'], durations:[2,3,4,5,6,7,8,9,10], ratios:['16:9','21:9','4:3','9:16','3:4','1:1'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_aleph2: { provider:'runway', modes:['video_edit'], durations:[2,3,4,5,6,7,8,9,10,11,12,13,14,15,20,25,30], ratios:['match_input','16:9','9:16','1:1','4:3','3:4','21:9'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:true, video_edit:true },
  runway_aleph: { provider:'runway', modes:['video_edit'], durations:[5,10], ratios:['16:9','21:9','4:3','9:16','3:4','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:true, video_edit:true },
  runway_gen3a_turbo: { provider:'runway', modes:['image_to_video'], durations:[5,10], ratios:['16:9','9:16'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_seedance2: { provider:'runway', modes:['text_to_video','image_to_video','video_edit'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['480p','720p','1080p','4K'], sound:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
  runway_seedance2_fast: { provider:'runway', modes:['text_to_video','image_to_video','video_edit'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['480p','720p','1080p'], sound:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
  runway_seedance2_mini: { provider:'runway', modes:['text_to_video','image_to_video','video_edit'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['480p','720p'], sound:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
  runway_happyhorse_1_0: { provider:'runway', modes:['text_to_video','image_to_video'], durations:[3,4,5,6,7,8,9,10,11,12,13,14,15], ratios:['16:9','9:16','1:1','4:3','3:4'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_veo3: { provider:'runway', modes:['image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_veo3_1: { provider:'runway', modes:['image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:true, video_upload:false, video_edit:false },
  runway_veo3_1_fast: { provider:'runway', modes:['image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:true, video_upload:false, video_edit:false },
  runway_gemini_omni_flash: { provider:'runway', modes:['text_to_video','image_to_video','video_edit'], durations:[3,4,5,6,7,8,9,10], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:true, video_edit:true },
  seedance_1_5_pro: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p','1080p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  wan_2_6: { provider:'wan', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  seedance_2_fast: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  seedance_2_0: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p','1080p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  gemini_omni_flash: { provider:'gemini', modes:['text_to_video','image_to_video','video_edit'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:true, video_edit:true },
  sora_2: { provider:'sora', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  grok_video: { provider:'grok', modes:['text_to_video'], durations:[5], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  veo_3_1_fast: { provider:'veo', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_gen: { provider:'runway', modes:['image_to_video'], durations:[2,3,4,5,6,7,8,9,10], ratios:['16:9','21:9','4:3','9:16','3:4','1:1'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false }
};

const KLING_VIDEO_BASE_RATIOS = ['16:9','9:16','1:1'];
const KLING_VIDEO_DURATIONS = [5,10,15];
const KLING_VIDEO_LONG_DURATIONS = [3,4,5,6,7,8,9,10,11,12,13,14,15];
const KLING_VIDEO_O1_DURATIONS = [3,4,5,6,7,8,9,10];
const KLING_VIDEO_SHORT_DURATIONS = [5,10];
const KLING_VIDEO_STANDARD_RESOLUTIONS = ['720p','1080p'];
const KLING_VIDEO_FULL_RESOLUTIONS = ['720p','1080p','4K'];

Object.assign(VIDEO_MODEL_CONFIG, {
  kling_3_0_turbo: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:true, native_audio:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  kling_3_0: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_FULL_RESOLUTIONS, sound:true, native_audio:true, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_motion_3_0: { provider:'kling', modes:['motion_control'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, motion_control:true, omni:true, start_image:true, end_image:false, video_upload:true, video_edit:true },
  kling_effects: { provider:'kling', modes:['video_effects'], durations:[5,10], ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false, video_effects:true },
  kling_o3_omni: { provider:'kling', modes:['text_to_video','image_to_video','video_edit','motion_control'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_FULL_RESOLUTIONS, sound:true, native_audio:true, omni:true, motion_control:true, video_input:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
  kling_o3_edit: { provider:'kling', modes:['video_edit'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_FULL_RESOLUTIONS, sound:true, native_audio:true, video_input:true, start_image:false, end_image:false, video_upload:true, video_edit:true },
  kling_o1: { provider:'kling', modes:['text_to_video','image_to_video','video_edit'], durations:KLING_VIDEO_O1_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, video_input:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
  kling_2_6: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:true, native_audio:true, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_motion_2_6: { provider:'kling', modes:['motion_control'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, motion_control:true, start_image:true, end_image:false, video_upload:true, video_edit:false },
  kling_2_5_turbo: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_2_1: { provider:'kling', modes:['image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_2_1_master: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:['1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  kling_2_0_master: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:['1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  kling_1_6: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, multi_image:false, multi_element_editing:false, video_extension:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_1_5: { provider:'kling', modes:['image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, video_extension:false, start_image:true, end_image:true, video_upload:false, video_edit:false },
  kling_1_0: { provider:'kling', modes:['text_to_video','image_to_video'], durations:KLING_VIDEO_SHORT_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, video_extension:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
});

const VIDEO_MOTION_PRESETS = [
  'Walk', 'Run', 'Turn around', 'Wave hand', 'Jump',
  'Dance 1', 'Dance 2', 'Cinematic pose', 'Camera orbit', 'Slow motion'
];

// =====================================================
// JAVASCRIPT-БЛОК: currentVideoModel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function currentVideoModel() {
  return VIDEO_MODELS.find((item) => item.id === videoState.modelId) || VIDEO_MODELS[0];
}

// =====================================================
// JAVASCRIPT-БЛОК: isImageMode
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function isImageMode() {
  return studioMode === 'image' || activeCat === 'image';
}

// =====================================================
// JAVASCRIPT-БЛОК: isVideoMode
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function isVideoMode() {
  return studioMode === 'video' || activeCat === 'video';
}

// =====================================================
// АУДИОПЛЕЕР: isMusicMode
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function isMusicMode() {
  return studioMode === 'music' || activeCat === 'music';
}

// =====================================================
// JAVASCRIPT-БЛОК: isVoiceMode
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function isVoiceMode() {
  return studioMode === 'voice' || activeCat === 'voice';
}

// =====================================================
// АУДИОПЛЕЕР: currentAudioState
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function currentAudioState() {
  if (isVoiceMode()) return voiceState;
  return musicState;
}

// =====================================================
// JAVASCRIPT-БЛОК: currentVideoConfig
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function currentVideoConfig() {
  return VIDEO_MODEL_CONFIG[videoState.modelId] || VIDEO_MODEL_CONFIG.seedance_2_fast;
}

// =====================================================
// JAVASCRIPT-БЛОК: currentVideoProvider
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function currentVideoProvider() {
  const config = currentVideoConfig();
  return (config && config.provider) || 'sylvex-router';
}

// =====================================================
// JAVASCRIPT-БЛОК: videoModelSettingsSnapshot
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function videoModelSettingsSnapshot() {
  return {
    ratio: videoState.ratio,
    duration: videoState.duration,
    resolution: videoState.resolution,
    sound: !!videoState.sound,
    generationMode: videoState.generationMode || videoState.mode || 'text_to_video',
    mode: videoState.generationMode || videoState.mode || 'text_to_video',
    quality: videoState.quality || 'standard',
    motionPreset: videoState.motionPreset || '',
  };
}

// =====================================================
// JAVASCRIPT-БЛОК: saveCurrentVideoModelSettings
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function saveCurrentVideoModelSettings() {
  if (!videoState.modelId) return;
  videoModelSettings[videoState.modelId] = videoModelSettingsSnapshot();
}

// =====================================================
// JAVASCRIPT-БЛОК: restoreVideoModelSettings
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function restoreVideoModelSettings(modelId) {
  const saved = videoModelSettings[modelId || videoState.modelId];
  if (saved) {
    Object.assign(videoState, saved);
  }
  normalizeVideoStateForModel();
}

// =====================================================
// JAVASCRIPT-БЛОК: normalizeVideoStateForModel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function normalizeVideoStateForModel() {
  const previousConfig = currentVideoConfig() || {};
  if ((videoState.section === 'edit' || videoState.section === 'motion') && !previousConfig.video_effects && videoState.modelId !== 'kling_o3_omni') {
    videoState.modelId = 'kling_o3_omni';
  }
  const config = currentVideoConfig();
  if (!config) return;
  const modes = config.modes || ['text_to_video'];
  const durations = config.durations || [5];
  const ratios = config.ratios || ['16:9'];
  const resolutions = config.resolutions || ['720p'];

  videoState.provider = config.provider || videoState.provider || 'sylvex-router';
  if (videoState.section === 'edit') {
    videoState.generationMode = 'video_edit';
  } else if (videoState.section === 'motion') {
    videoState.generationMode = 'motion_control';
  } else if (!modes.includes(videoState.generationMode)) {
    videoState.generationMode = modes[0] || 'text_to_video';
  }
  videoState.mode = videoState.generationMode;
  if (!durations.includes(Number(videoState.duration))) videoState.duration = durations[0] || 5;
  if (!ratios.includes(videoState.ratio)) videoState.ratio = ratios[0] || '16:9';
  if (!resolutions.includes(videoState.resolution)) videoState.resolution = resolutions[0] || '720p';
  if (!config.sound) videoState.sound = false;
}

// =====================================================
// JAVASCRIPT-БЛОК: labelItems
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function labelItems(values, suffix) {
  return (values || []).map((value) => {
    const id = String(value);
    return { id, label: suffix ? id + ' ' + suffix : id };
  });
}

// =====================================================
// JAVASCRIPT-БЛОК: videoOptionsPayload
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function videoOptionsPayload(referenceImagesOverride) {
  normalizeVideoStateForModel();
  const config = currentVideoConfig() || {};
  const videoTemplate = videoState.videoTemplate || null;
  const isKlingEffect = !!(videoTemplate && (videoTemplate.catalog_type === 'kling_effect' || videoState.generationMode === 'video_effects' || videoState.mode === 'video_effects'));
  const referenceVisual = videoState.referenceVisual || {};
  const characterVisual = videoState.characterVisual || (referenceVisual.kind === 'character' ? referenceVisual : {});
  const objectVisual = videoState.objectVisual || (referenceVisual.kind === 'object' ? referenceVisual : {});
  const referenceImages = Array.isArray(referenceImagesOverride)
    ? referenceImagesOverride.slice()
    : currentVideoReferenceImages();
  const isHeygenModel = String(videoState.modelId || '').toLowerCase().includes('heygen');
  const heygenAvatarId = characterVisual.heygenVideoAvatarId || characterVisual.heygenPhotoAvatarId || '';
  const heygenFiles = [];
  if (isHeygenModel && characterVisual.videoReferenceUrl) heygenFiles.push(characterVisual.videoReferenceUrl);

  return {
    section: videoState.section || 'generate',
    generation_mode: videoState.generationMode || videoState.mode || 'text_to_video',
    mode: videoState.generationMode || videoState.mode || 'text_to_video',
    ratio: videoState.ratio || '16:9',
    resolution: videoState.resolution || '720p',
    duration: Number(videoState.duration || 5),
    sound: !!videoState.sound,
    start_image: videoState.startImage || '',
    end_image: videoState.endImage || '',
    reference_images: referenceImages,
    referenceImageUrls: referenceImages,
    input_video: currentVideoEditInputUrl() || currentVideoReferenceUrl() || '',
    video_url: currentVideoEditInputUrl() || currentVideoReferenceUrl() || '',
    reference_video: currentVideoReferenceUrl() || '',
    image_url: '',
    motion_preset: videoState.motionPreset || '',
    video_template: videoTemplate,
    character_orientation: (videoTemplate && videoTemplate.character_orientation) || 'image',
    effect_scene: isKlingEffect ? (videoTemplate.effect_scene || '') : '',
    video_effects: isKlingEffect,
    is_kling_effect: isKlingEffect,
    character_image: videoState.characterImage || '',
    characterId: characterVisual.id || '',
    characterName: characterVisual.name || '',
    characterPrompt: '',
    characterReferences: Array.isArray(characterVisual.references) ? characterVisual.references.slice() : [],
    avatar_id: isHeygenModel ? heygenAvatarId : '',
    heygen_avatar_id: isHeygenModel ? heygenAvatarId : '',
    heygen_photo_avatar_id: characterVisual.heygenPhotoAvatarId || '',
    heygen_video_avatar_id: characterVisual.heygenVideoAvatarId || '',
    heygen_voice_id: characterVisual.heygenDefaultVoiceId || '',
    voice_id: isHeygenModel ? (characterVisual.heygenDefaultVoiceId || '') : '',
    heygen_files: heygenFiles,
    objectId: objectVisual.id || '',
    objectName: objectVisual.name || '',
    objectPrompt: objectVisual.prompt || '',
    objectReferences: Array.isArray(objectVisual.references) ? objectVisual.references.slice() : [],
    model: videoState.modelId || '',
    native_audio: !!(config.native_audio && videoState.sound),
    motion_control: !!config.motion_control && !isKlingEffect,
    video_input: !!(config.video_input || config.video_upload || currentVideoEditInputUrl() || currentVideoReferenceUrl()),
    avatar: !!config.avatar,
    lip_sync: !!config.lip_sync,
    multi_image: !!config.multi_image,
    multi_element_editing: !!config.multi_element_editing,
    video_extension: !!config.video_extension,
    advanced: Object.assign({}, videoState.advanced || {}, {
      native_audio: !!(config.native_audio && videoState.sound),
      motion_control: !!config.motion_control && !isKlingEffect,
      video_effects: isKlingEffect,
      video_input: !!(config.video_input || config.video_upload || currentVideoEditInputUrl() || currentVideoReferenceUrl()),
      avatar: !!config.avatar,
      lip_sync: !!config.lip_sync,
      multi_image: !!config.multi_image,
      multi_element_editing: !!config.multi_element_editing,
      video_extension: !!config.video_extension,
    }),
  };
}

// =====================================================
// JAVASCRIPT-БЛОК: videoOptionLabel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function videoOptionLabel(kind, value) {
  const str = String(value || '');

  if (kind === 'ratio') {
    return str || '16:9';
  }

  if (kind === 'duration') {
    return String(value || 5) + ' сек';
  }

  if (kind === 'mode') {
    if (str === 'image_to_video') return 'Image to Video';
    if (str === 'video_to_video') return 'Video to Video';
    if (str === 'video_edit') return 'Video Edit';
    if (str === 'motion_control') return 'Motion Control';
    if (str === 'multi_image_to_video') return 'Multi Image';
    if (str === 'multi_element_editing') return 'Multi Element';
    if (str === 'video_extension') return 'Video Extension';
    if (str === 'avatar') return 'Avatar';
    if (str === 'lip_sync') return 'Lip Sync';
    return 'Text to Video';
  }

  if (kind === 'quality') {
    if (str === 'pro') return 'Pro';
    if (str === 'high') return 'High';
    return 'Standard';
  }

  if (kind === 'sound') {
    return value ? 'Звук вкл' : 'Звук выкл';
  }

  return str;
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoControls
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVideoControls() {
  normalizeVideoStateForModel();
  injectImageStyleSheetCss();
  const model = currentVideoModel();
  const composer = document.getElementById('studioComposer');
  if (composer) composer.dataset.videoSection = videoState.section || 'generate';

  if (isVideoMode() && model) updateComposerModelDisplay(model);

  const sizeVal = document.getElementById('imageSizeVal');
  if (sizeVal) sizeVal.textContent = videoOptionLabel('ratio', videoState.ratio);

  const sizeIcon = document.getElementById('imageSizeIcon');
  if (sizeIcon) {
    const isAutoRatio = ['auto', 'adaptive'].includes(String(videoState.ratio || '').toLowerCase());
    sizeIcon.hidden = isAutoRatio;
    if (!isAutoRatio) sizeIcon.setAttribute('data-ratio', videoState.ratio || '16:9');
  }

  const countVal = document.getElementById('imageCountVal');
  if (countVal) countVal.textContent = videoOptionLabel('duration', videoState.duration);

  const durationVal = document.getElementById('videoDurationVal');
  if (durationVal) durationVal.textContent = videoOptionLabel('duration', videoState.duration);

  const resolutionVal = document.getElementById('videoResolutionVal');
  if (resolutionVal) resolutionVal.textContent = videoState.resolution || '720p';

  const soundVal = document.getElementById('videoSoundVal');
  if (soundVal) {
    soundVal.textContent = videoState.sound ? 'Звук ON' : 'Звук OFF';
    const soundBtn = soundVal.closest('button');
    if (soundBtn) {
      soundBtn.classList.toggle('video-sound-on', !!videoState.sound);
      soundBtn.classList.toggle('video-sound-off', !videoState.sound);
      soundBtn.classList.toggle('video-sound-disabled', !currentVideoConfig().sound);
    }
  }

  const styleVal = document.getElementById('imageStyleVal');
  if (styleVal) {
    styleVal.textContent = videoOptionLabel('mode', videoState.mode);
    const btn = styleVal.closest('button') || styleVal.parentElement;
    if (btn) {
      btn.classList.remove('has-style-preview');
      btn.style.removeProperty('--image-style-bg');
    }
  }

  const characterVal = document.getElementById('imageCharacterVal');
  if (characterVal) characterVal.textContent = videoOptionLabel('quality', videoState.quality);
  renderUploadPreviewOnButton(document.getElementById('imageCharacterButton'), []);
  renderUploadPreviewOnButton(document.getElementById('imageObjectButton'), []);
  renderVideoStartPreview();
  renderVideoEndPreview();
  renderVideoEditPreview();
  renderVideoReferencesPreview();
}

// =====================================================
// JAVASCRIPT-БЛОК: pickVideoOption
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function pickVideoOption(kind, value) {
  const config = currentVideoConfig();
  if (kind === 'size' || kind === 'ratio') {
    videoState.ratio = value || '16:9';
  }

  if (kind === 'count' || kind === 'duration') {
    videoState.duration = Number(value || 5);
  }

  if (kind === 'style' || kind === 'mode') {
    videoState.generationMode = value || 'text_to_video';
    videoState.mode = videoState.generationMode;
  }

  if (kind === 'character' || kind === 'quality') {
    videoState.quality = value || 'standard';
  }

  if (kind === 'resolution') {
    videoState.resolution = value || '720p';
  }

  if (kind === 'sound') {
    if (!config.sound) {
      videoState.sound = false;
    } else if (value === undefined || value === null || value === 'toggle') {
      videoState.sound = !videoState.sound;
    } else {
      videoState.sound = value === true || value === 'true' || value === 'on' || value === '1';
    }
  }

  if (kind === 'motion_preset') {
    videoState.motionPreset = value || '';
  }

  normalizeVideoStateForModel();
  saveCurrentVideoModelSettings();
  renderVideoControls();
}

// =====================================================
// JAVASCRIPT-БЛОК: currentComposerModelList
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function currentComposerModelList() {
  if (isImageMode()) return IMAGE_MODEL_LIST;
  if (isVideoMode()) return VIDEO_MODELS;
  if (isMusicMode()) return MUSIC_MODEL_LIST;
  if (isVoiceMode()) return VOICE_MODEL_LIST;
  if (studioMode === 'text') return TEXT_MODEL_FAMILIES;
  return [];
}

// =====================================================
// АУДИОПЛЕЕР: musicOptionLabel
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function musicOptionLabel(items, id, fallback) {
  const value = String(id || 'auto');
  // =====================================================
  // JAVASCRIPT-БЛОК: item
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const item = (items || []).find((entry) => String(entry.id) === value);
  return item ? (item.label || item.id) : fallback;
}

function textOptionLabel(items, id, fallback) {
  const value = String(id || '');
  const item = (items || []).find((entry) => String(entry.id) === value);
  return item ? (item.label || item.id) : fallback;
}

function currentTextModel() {
  return TEXT_MODEL_LIST.find((item) => item.id === textState.modelId) || TEXT_MODEL_LIST.find((item) => item.id === 'gpt-5.5') || null;
}

function renderTextControls() {
  const model = currentTextModel();
  const familyId = textModelFamilyId(model);
  const family = TEXT_MODEL_FAMILIES.find((item) => item.id === familyId) || TEXT_MODEL_FAMILIES[0];
  textState.familyId = familyId;
  normalizeTextToolForModel();
  if (studioMode === 'text' && family) updateComposerModelDisplay(family);
  const toolVal = document.getElementById('textToolVal');
  if (toolVal) toolVal.textContent = textOptionLabel(TEXT_TOOL_OPTIONS, textState.tool || 'text', 'Текст');
  const styleVal = document.getElementById('textStyleVal');
  if (styleVal) styleVal.textContent = textOptionLabel(TEXT_STYLE_OPTIONS, textState.style || 'neutral', 'Стиль');
  const formatVal = document.getElementById('textFormatVal');
  if (formatVal) formatVal.textContent = textOptionLabel(TEXT_FORMAT_OPTIONS, textState.format || 'markdown', 'Markdown');
  const textVersionVal = document.getElementById('textVersionVal');
  if (textVersionVal) textVersionVal.textContent = model ? (model.versionLabel || String(model.label || model.id).replace(/^GPT-/i, '')) : '5.5';
  const recordingBar = document.getElementById('textRecordingBar');
  const isRecording = Boolean(mediaRecorder && mediaRecorder.state === 'recording');
  if (recordingBar) {
    recordingBar.hidden = !isRecording;
    recordingBar.style.display = isRecording ? '' : 'none';
  }
  const uploadVal = document.getElementById('textUploadVal');
  if (uploadVal) {
    const att = textState.attachment || pendingAttachment || null;
    const btn = uploadVal.closest ? uploadVal.closest('button') : null;
    if (btn) {
      btn.querySelectorAll('.text-upload-video-preview').forEach((node) => node.remove());
      btn.classList.remove('text-upload-has-preview', 'text-upload-has-video-preview', 'text-upload-file-selected');
      btn.style.backgroundImage = '';
      btn.dataset.textUploadKind = '';
    }
    if (att && att.uploading) {
      uploadVal.textContent = 'Загрузка';
      if (btn) btn.classList.add('text-upload-file-selected');
    } else if (att) {
      const kind = String(att.kind || '').toLowerCase();
      const label = kind === 'image' ? 'Фото выбрано' : (kind === 'video' ? 'Видео выбрано' : (kind === 'audio' ? 'Аудио выбрано' : 'Файл выбран'));
      uploadVal.textContent = label;
      if (btn) {
        btn.dataset.textUploadKind = kind || 'file';
        btn.classList.add('text-upload-file-selected');
        const url = attachmentUrl(att);
        if (kind === 'image' && url) {
          btn.classList.add('text-upload-has-preview');
          btn.style.backgroundImage = 'linear-gradient(180deg,rgba(0,0,0,.08),rgba(0,0,0,.62)),url("' + String(url).replace(/"/g, '%22') + '")';
        } else if (kind === 'video' && url) {
          const video = document.createElement('video');
          video.className = 'text-upload-video-preview';
          video.src = url;
          video.muted = true;
          video.playsInline = true;
          video.preload = 'metadata';
          video.setAttribute('aria-hidden', 'true');
          video.addEventListener('loadedmetadata', () => {
            try {
              if (Number.isFinite(video.duration) && video.duration > 0) video.currentTime = Math.min(0.2, video.duration / 3);
            } catch (_) {}
          }, { once:true });
          btn.insertBefore(video, btn.firstChild);
          btn.classList.add('text-upload-has-video-preview');
        }
      }
    } else {
      uploadVal.textContent = 'Файл';
    }
  }
}

function textOptionsPayload() {
  return {
    tool: textState.tool || 'text',
    style: textState.style || 'neutral',
    format: textState.format || 'markdown',
    language: textState.language || 'auto',
  };
}

// =====================================================
// АУДИОПЛЕЕР: currentMusicModel
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function currentMusicModel() {
  return MUSIC_MODEL_LIST.find((item) => item.id === musicState.modelId) || MUSIC_MODEL_LIST[0] || null;
}

function musicModelSupports(feature) {
  const model = currentMusicModel();
  return !(model && model.capabilities && model.capabilities[feature] === false);
}

// =====================================================
// АУДИОПЛЕЕР: ensureMusicSettings
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function ensureMusicSettings() {
  if (!musicState.settings || typeof musicState.settings !== 'object') musicState.settings = {};
  Object.keys(MUSIC_SETTINGS).forEach((key) => {
    if (!musicState.settings[key]) musicState.settings[key] = 'auto';
  });
  if (!musicState.genre) musicState.genre = 'auto';
  const model = currentMusicModel();
  if (model && Array.isArray(model.vocalModes) && !model.vocalModes.includes(musicState.settings.vocal)) {
    musicState.settings.vocal = 'instrumental';
  }
  const maxDurationSeconds = Math.max(...((model && model.durations) || [1, 2, 3, 4])) * 60;
  if (model && model.capabilities && model.capabilities.duration === false) musicState.duration = 'auto';
  if (musicState.duration !== 'auto' && (!Number.isFinite(Number(musicState.duration)) || Number(musicState.duration) < 1 || Number(musicState.duration) > maxDurationSeconds)) {
    musicState.duration = 'auto';
  }
  if (!musicState.duration) musicState.duration = 'auto';
  if (!musicState.modelId && MUSIC_MODEL_LIST.length) musicState.modelId = MUSIC_MODEL_LIST[0].id;
}

// =====================================================
// АУДИОПЛЕЕР: musicOptionsPayload
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function musicOptionsPayload() {
  ensureMusicSettings();
  const model = currentMusicModel();
  const fixedDuration = Number(model && model.fixedDurationSeconds) || 0;
  return {
    model: musicState.modelId,
    genre: musicState.genre || 'auto',
    duration: fixedDuration || (musicState.duration === 'auto' ? 'auto' : Number(musicState.duration)),
    duration_seconds: fixedDuration || (musicState.duration === 'auto' ? null : Number(musicState.duration)),
    duration_minutes: fixedDuration ? Number((fixedDuration / 60).toFixed(2)) : (musicState.duration === 'auto' ? null : Number((Number(musicState.duration) / 60).toFixed(2))),
    mood: musicState.settings.mood || 'auto',
    tempo: musicState.settings.tempo || 'auto',
    theme: musicState.settings.theme || 'auto',
    vocal: musicState.settings.vocal || 'auto',
  };
}

// =====================================================
// АУДИОПЛЕЕР: ensureVoiceSettings
// Готовит параметры раздела «Озвучка» перед показом кнопок и отправкой Gemini TTS.
// =====================================================
function ensureVoiceSettings() {
  if (!voiceState.audioSettings || typeof voiceState.audioSettings !== 'object') voiceState.audioSettings = {};
  if (!voiceState.modelId) voiceState.modelId = 'elevenlabs_eleven_v3';
  if (!voiceState.voice) voiceState.voice = 'Kore';
  if (!voiceState.runwayVoice) voiceState.runwayVoice = 'Maya';
  if (!voiceState.runwayTool) voiceState.runwayTool = 'text_to_speech';
  if (!voiceState.runwayTargetLanguage) voiceState.runwayTargetLanguage = 'en';
  if (!voiceState.runwayDuration) voiceState.runwayDuration = 5;
  if (!voiceState.elevenlabsVoice) voiceState.elevenlabsVoice = '21m00Tcm4TlvDq8ikWAM';
  if (!voiceState.elevenlabsSecondVoice) voiceState.elevenlabsSecondVoice = voiceState.elevenlabsVoice;
  if (!voiceState.elevenlabsTool) voiceState.elevenlabsTool = 'text_to_speech';
  if (!voiceState.elevenlabsTargetLanguage) voiceState.elevenlabsTargetLanguage = 'en';
  if (!voiceState.secondVoice) voiceState.secondVoice = 'Puck';
  if (!voiceState.speakerMode) voiceState.speakerMode = 'single';
  if (!voiceState.speaker1) voiceState.speaker1 = 'Speaker1';
  if (!voiceState.speaker2) voiceState.speaker2 = 'Speaker2';
  if (!voiceState.uploadPurpose) voiceState.uploadPurpose = 'voiceover';
  if (!voiceState.sourceLanguage) voiceState.sourceLanguage = 'auto';
  if (!voiceState.targetLanguage) voiceState.targetLanguage = voiceState.elevenlabsTargetLanguage || voiceState.runwayTargetLanguage || 'en';
  if (!voiceState.numSpeakers) voiceState.numSpeakers = voiceState.speakerMode === 'multi' ? 2 : 1;
  const maximumSpeakers = isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2;
  voiceState.numSpeakers = Math.max(1, Math.min(maximumSpeakers, Number(voiceState.numSpeakers || 1)));
  if (!Array.isArray(voiceState.speakerVoices)) voiceState.speakerVoices = ['Kore', '', '', '', '', '', ''];
  while (voiceState.speakerVoices.length < 7) voiceState.speakerVoices.push('');
  const usedSpeakerVoices = new Set();
  for (let index = 0; index < voiceState.numSpeakers; index += 1) {
    const selectedVoice = index === 0 ? voiceSpeakerVoiceValue(0) : String(voiceState.speakerVoices[index] || '');
    if (selectedVoice && usedSpeakerVoices.has(selectedVoice)) voiceState.speakerVoices[index] = '';
    else if (selectedVoice) usedSpeakerVoices.add(selectedVoice);
  }
  if (!isVoicePurposeSupported(voiceState.uploadPurpose)) {
    const supportedPurpose = VOICE_UPLOAD_PURPOSES.find((item) => isVoicePurposeSupported(item)) || VOICE_UPLOAD_PURPOSES[0];
    applyVoiceUploadPurpose(supportedPurpose.id);
  }
  ['style', 'pace', 'tone'].forEach((key) => {
    if (!voiceState.audioSettings[key]) voiceState.audioSettings[key] = 'auto';
  });
  if (!voiceState._pronunciationsLoaded) {
    try { voiceState.pronunciationRules = JSON.parse(localStorage.getItem('sylvex_voice_pronunciations') || '{}'); }
    catch { voiceState.pronunciationRules = {}; }
    voiceState._pronunciationsLoaded = true;
  }
}

// =====================================================
// АУДИОПЛЕЕР: voiceOptionsPayload
// Собирает параметры озвучки для backend: модель Gemini TTS, голос и режим single/multi speaker.
// =====================================================
function voiceOptionsPayload() {
  ensureVoiceSettings();
  const runwayModel = isRunwayVoiceModel(voiceState.modelId);
  const elevenlabsModel = isElevenLabsVoiceModel(voiceState.modelId);
  const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
  const requestedSpeakerCount = voiceWorkspaceMode === 'dialogue' ? Math.max(2, Number(voiceState.numSpeakers || 2)) : Number(voiceState.numSpeakers || 1);
  const speakerCount = Math.max(1, Math.min(isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2, requestedSpeakerCount));
  const speakerVoices = Array.from({ length:speakerCount }, (_, index) => voiceSpeakerVoiceValue(index));
  const targetLanguage = voiceState.targetLanguage || (elevenlabsModel ? voiceState.elevenlabsTargetLanguage : voiceState.runwayTargetLanguage) || 'en';
  const runwayTool = runwayModel ? (purpose.runwayTool || voiceState.runwayTool || 'text_to_speech') : (voiceState.runwayTool || 'text_to_speech');
  const elevenlabsTool = elevenlabsModel
    ? (voiceWorkspaceMode === 'dialogue' ? 'dialogue' : (purpose.elevenlabsTool || voiceState.elevenlabsTool || 'text_to_speech'))
    : (voiceState.elevenlabsTool || 'text_to_speech');
  return {
    model: voiceState.modelId,
    provider: elevenlabsModel ? 'elevenlabs' : (runwayModel ? 'runway' : 'gemini'),
    voice: elevenlabsModel ? (voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM') : (runwayModel ? (voiceState.runwayVoice || 'Maya') : voiceState.voice),
    runway_voice: voiceState.runwayVoice || 'Maya',
    runway_tool: runwayTool,
    runway_target_language: targetLanguage,
    duration: Number(voiceState.runwayDuration || 5),
    elevenlabs_voice: voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM',
    elevenlabs_second_voice: voiceState.elevenlabsSecondVoice || voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM',
    elevenlabs_tool: elevenlabsTool,
    elevenlabs_target_language: targetLanguage,
    target_language: targetLanguage,
    source_language: voiceState.sourceLanguage || 'auto',
    upload_purpose: purpose.id,
    uploadPurpose: purpose.id,
    num_speakers: speakerCount,
    numSpeakers: speakerCount,
    speaker_count: speakerCount,
    speaker_voices: speakerVoices,
    speakerVoices: speakerVoices,
    secondVoice: voiceState.secondVoice,
    speaker_mode: speakerCount > 1 ? 'multi' : (voiceState.speakerMode || 'single'),
    speaker1: voiceState.speaker1,
    speaker2: voiceState.speaker2,
    speaker3: voiceState.speaker3 || 'Speaker3',
    audioSettings: Object.assign({}, voiceState.audioSettings || {}),
  };
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVoiceControls
// Обновляет подписи кнопок «Озвучка»: выбранная модель, голос, режим и настройки.
// =====================================================
function renderVoiceControls() {
  ensureVoiceSettings();
  injectImageStyleSheetCss();
  const model = VOICE_MODEL_LIST.find((item) => item.id === voiceState.modelId) || VOICE_MODEL_LIST[0];
  if (isVoiceMode() && model) updateComposerModelDisplay(model);
  const voiceVal = document.getElementById('voiceVoiceVal');
  if (voiceVal) voiceVal.textContent = currentVoiceButtonLabel();
  const voiceListButton = document.getElementById('voiceListButton');
  const voiceListButtonLabel = document.getElementById('voiceListButtonLabel');
  if (voiceListButton && voiceListButtonLabel) {
    const activeSpeakerIndex = Number.isInteger(voiceState.activeSpeakerIndex) && voiceState.activeSpeakerIndex < voiceState.numSpeakers ? voiceState.activeSpeakerIndex : null;
    const selectedId = activeSpeakerIndex !== null ? voiceSpeakerVoiceValue(activeSpeakerIndex) : (isElevenLabsVoiceModel(voiceState.modelId) ? voiceState.elevenlabsVoice : (isRunwayVoiceModel(voiceState.modelId) ? voiceState.runwayVoice : voiceState.voice));
    const selectedItem = currentVoiceListForPanel().find((item) => String(item.id || item.voice_id || '') === String(selectedId || '')) || currentVoiceListForPanel()[0];
    const label = selectedItem ? String(selectedItem.label || selectedItem.name || selectedItem.id || 'Список голосов').split(' · ')[0] : 'Список голосов';
    const provider = isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini');
    const avatarUrl = selectedItem ? voiceAvatarUrlFor(selectedItem, provider) : '';
    const icon = voiceListButton.querySelector('.vgen-btn-ico');
    voiceListButtonLabel.textContent = activeSpeakerIndex !== null ? ('Диктор ' + (activeSpeakerIndex + 1) + ' · ' + label) : label;
    voiceListButton.classList.toggle('has-selected-voice', Boolean(selectedItem));
    voiceListButton.classList.toggle('has-selected-voice-image', Boolean(selectedItem && avatarUrl));
    voiceListButton.setAttribute('style', selectedItem ? voiceAvatarStyle(selectedItem.id || selectedItem.voice_id || label) : '');
    voiceListButton.style.backgroundImage = avatarUrl
      ? 'linear-gradient(180deg,rgba(0,0,0,.06),rgba(0,0,0,.68)),url("' + String(avatarUrl).replace(/["\\]/g, '') + '")'
      : '';
    if (icon && selectedItem) {
      icon.className = 'vgen-btn-ico voice-list-button-avatar ' + (avatarUrl ? '' : 'is-generated');
      icon.setAttribute('style', voiceAvatarStyle(selectedItem.id || selectedItem.voice_id || label));
      icon.innerHTML = avatarUrl
        ? '<img src="' + S.escapeHtml(avatarUrl) + '" alt="" loading="lazy" decoding="async">'
        : '<span>' + S.escapeHtml(voiceInitials(label)) + '</span>';
    }
  }
  const modeVal = document.getElementById('voiceModeVal');
  if (modeVal) modeVal.textContent = isElevenLabsVoiceModel(voiceState.modelId) ? elevenlabsToolLabel(voiceState.elevenlabsTool || 'text_to_speech') : (isRunwayVoiceModel(voiceState.modelId) ? runwayToolLabel(voiceState.runwayTool || 'text_to_speech') : (voiceState.speakerMode === 'multi' ? 'Два голоса' : 'Один голос'));
  const settingsVal = document.getElementById('voiceSettingsVal');
  if (settingsVal) {
    settingsVal.classList.remove('sr-only');
    settingsVal.textContent = voiceSettingsSummary();
  }
  renderVoiceToolPanel();
  renderVoiceSpeakerComposer();
  updateVoiceTextEstimate();
  let favorites = [];
  try { favorites = JSON.parse(localStorage.getItem('sylvex_voice_favorites') || '[]'); } catch {}
  document.getElementById('voiceFavoriteBtn')?.classList.toggle('active', Array.isArray(favorites) && favorites.includes(selectedVoiceIdentity()));
}

function renderVoiceSpeakerComposer() {
  const host = document.getElementById('voiceDialogueOpenTools');
  if (!host) return;
  const count = isVoiceMode() ? Math.max(1, Math.min(isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2, Number(voiceState.numSpeakers || 1))) : 1;
  if (!isVoiceMode() || voiceWorkspaceMode !== 'dialogue') {
    host.innerHTML = '';
    VoiceDialogueComposer.refreshMarkers();
    return;
  }
  const speakerButtons = Array.from({ length: count }, (_, index) => {
    const voiceId = voiceSpeakerVoiceValue(index);
    const item = currentVoiceListForPanel().find((voice) => String(voice.id || voice.voice_id || '') === String(voiceId || ''));
    const name = item ? String(item.label || item.name || item.id || '').split(' · ')[0] : '';
    const provider = isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini');
    const avatarUrl = item ? voiceAvatarUrlFor(item, provider) : '';
    const avatar = avatarUrl ? '<img src="' + S.escapeHtml(avatarUrl) + '" alt="">' : '<span>' + (name ? S.escapeHtml(voiceInitials(name)) : String(index + 1)) + '</span>';
    return '<button class="voice-speaker-chip ' + (voiceState.activeSpeakerIndex === index ? 'active' : '') + '" type="button" onclick="SYLVEX.handleVoiceSpeakerClick(event,' + (index + 1) + ')"><span class="voice-speaker-avatar" style="' + (item ? voiceAvatarStyle(voiceId || name) : '') + '">' + avatar + '</span><span class="voice-speaker-copy"><b>Диктор ' + (index + 1) + '</b><small>' + S.escapeHtml(name || 'Выбрать голос') + '</small></span>' + (index ? '<span class="voice-speaker-remove" role="button" aria-label="Убрать диктора" onclick="SYLVEX.removeVoiceSpeaker(event,' + (index + 1) + ')">×</span>' : '') + '</button>';
  }).join('');
  const maxSpeakers = isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2;
  const addSpeaker = count < maxSpeakers ? '<button class="voice-dialogue-add-speaker" type="button" onclick="SYLVEX.addVoiceSpeaker(event)" aria-label="Добавить диктора">+</button>' : '';
  host.innerHTML = '<div class="voice-dialogue-row voice-dialogue-speaker-row"><b>Дикторы</b><div class="voice-dialogue-row-items">' + speakerButtons + addSpeaker + '</div></div>';
  VoiceDialogueComposer.refreshMarkers();
}

function handleVoiceSpeakerClick(event, speakerNumber) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const index = Math.max(0, Math.min(6, Number(speakerNumber || 1) - 1));
  const voiceId = voiceSpeakerVoiceValue(index);
  voiceState.activeSpeakerIndex = index;
  if (voiceId) {
    VoiceDialogueComposer.rememberCaret();
    VoiceDialogueComposer.insertSpeaker(index);
    renderVoiceControls();
    return;
  }
  renderVoiceControls();
  openImageOptionMenu(event, 'voice_speaker_' + (index + 1));
}

const VOICE_DIALOGUE_DATA = Object.freeze({
  emotion: [
    ['Спокойно','calm'],['Весело','happy'],['Грустно','sad'],['Серьёзно','serious'],['Зло','angry'],['Страх','fear'],['Любовь','love'],['Уверенно','confident'],['Смущение','embarrassed'],['Плач','crying'],['Смех','laughing'],['Паника','panic'],['Размышляет','thoughtful'],
  ],
  style: [
    ['Шёпотом','whisper'],['Очень тихо','very_quiet'],['Тихо','quiet'],['Громко','loud'],['Кричит','shouting'],['Медленно','slow'],['Быстро','fast'],['Робот','robot'],['Хрипло','raspy'],['Детский голос','childlike'],['Старческий голос','elderly'],['Уверенно','confident'],['Нервно','nervous'],
  ],
  pause: [['0.2 сек','0.2'],['0.5 сек','0.5'],['1 сек','1'],['1.5 сек','1.5'],['2 сек','2'],['3 сек','3']],
  sfx: [
    ['Смех','laugh'],['Вздох','sigh'],['Кашель','cough'],['Плач','cry'],['Аплодисменты','applause'],['Шаги','footsteps'],['Дождь','rain'],['Гроза','thunderstorm'],['Ветер','wind'],['Птицы','birds'],['Телефон','phone'],['Машина','car'],['Сирена','siren'],['Дверь','door'],['Толпа','crowd'],['Выстрел','gunshot'],['Поцелуй','kiss'],
  ],
  direction: [
    ['Пауза','pause'],['Длинная пауза','long_pause'],['Начинает смеяться','starts_laughing'],['Перебивает','interrupts'],['Шепчет','whispers'],['Кричит вдаль','shouts_distant'],['Говорит по телефону','on_phone'],['Говорит в микрофон','on_microphone'],['За кадром','voice_over'],['Эхо','echo'],
  ],
  accent: [['Американский','american'],['Британский','british'],['Австралийский','australian'],['Русский','russian'],['Турецкий','turkish'],['Японский','japanese'],['Французский','french']],
  template: [['Диалог','dialogue'],['Интервью','interview'],['Подкаст','podcast'],['Реклама','advertising'],['Рассказ','story'],['Аудиокнига','audiobook'],['Новости','news'],['Радио','radio'],['Диктор','narrator'],['Озвучка фильма','film_dubbing']],
  ai: [['Сделать эмоциональнее','emotional'],['Сделать серьёзнее','serious'],['Сделать драматичнее','dramatic'],['Переписать','rewrite'],['Сократить','shorten'],['Продолжить','continue']],
});
const VOICE_EMOTIONS = VOICE_DIALOGUE_DATA.emotion.map((item) => item[0]);
const VOICE_PAUSES = VOICE_DIALOGUE_DATA.pause.map((item) => Number(item[1]));
const VOICE_EFFECTS = VOICE_DIALOGUE_DATA.sfx.map((item) => item[0]);
const VOICE_CUSTOM_OPTIONS_KEY = 'sylvex_voice_custom_dialogue_options';
let voiceCustomOptions = { emotion:[], pause:[], effects:[] };
try {
  const storedVoiceOptions = JSON.parse(localStorage.getItem(VOICE_CUSTOM_OPTIONS_KEY) || '{}');
  ['emotion','pause','effects'].forEach((key) => {
    if (Array.isArray(storedVoiceOptions[key])) voiceCustomOptions[key] = storedVoiceOptions[key].slice(0, 30);
  });
} catch {}
const VOICE_AI_FORMATS = [
  ['ad', 'Реклама'], ['script', 'Сценарий'], ['story', 'Рассказ'], ['podcast', 'Подкаст'],
  ['interview', 'Интервью'], ['dialogue', 'Диалог'], ['book', 'Аудиокнига'], ['greeting', 'Поздравление'], ['announcement', 'Объявление'],
];

const VoiceDialogueComposer = (() => {
  let input = null;
  let savedSelection = { start:0, end:0, text:'' };
  let contextMenu = null;
  let mobileToolbar = null;
  let bottomSheet = null;
  let markerRail = null;
  let longPressTimer = 0;
  let longPressPoint = null;
  let mobileTapAt = 0;
  let mobileTapPoint = null;
  let dialogueLines = [];
  const submenuTimers = new WeakMap();

  const active = () => isVoiceMode() && voiceWorkspaceMode === 'dialogue';
  const isTouchLayout = () => Boolean(S.device && S.device.usesVirtualKeyboard);
  const rememberCaret = () => {
    if (!input) return savedSelection;
    const start = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
    const end = Number.isFinite(input.selectionEnd) ? input.selectionEnd : start;
    savedSelection = { start, end, text:input.value.slice(start, end) };
    return savedSelection;
  };
  const restoreCaret = () => {
    if (!input) return;
    const max = input.value.length;
    const start = Math.max(0, Math.min(max, savedSelection.start));
    const end = Math.max(start, Math.min(max, savedSelection.end));
    input.focus({ preventScroll:true });
    input.setSelectionRange(start, end);
  };
  const afterEdit = (caret) => {
    if (!input) return;
    input.focus({ preventScroll:true });
    input.setSelectionRange(caret, caret);
    savedSelection = { start:caret, end:caret, text:'' };
    input.dispatchEvent(new Event('input', { bubbles:true }));
    autoGrow(input);
    refreshMarkers();
  };
  const insert = (value, options) => {
    if (!input) return;
    const config = options || {};
    const selection = savedSelection;
    const start = selection.start;
    const end = selection.end;
    const selected = input.value.slice(start, end);
    let inserted = String(value || '');
    if (config.wrapSelection && selected) inserted = inserted + ' ' + selected;
    const replacementEnd = (config.replaceSelection || config.wrapSelection) ? end : start;
    input.value = input.value.slice(0, start) + inserted + input.value.slice(replacementEnd);
    afterEdit(start + inserted.length);
  };
  const token = (kind, value) => '[' + kind + ':' + value + ']';
  const copyText = async () => {
    const text = savedSelection.text || '';
    if (!text) return toast('Сначала выделите текст');
    try {
      await navigator.clipboard.writeText(text);
      toast('Текст скопирован');
    } catch { toast('Не удалось получить доступ к буферу обмена'); }
    restoreCaret();
  };
  const pasteText = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) insert(text, { replaceSelection:true });
      else restoreCaret();
    } catch {
      toast('Вставка недоступна — используйте системное меню');
      restoreCaret();
    }
  };
  const translateText = () => {
    restoreCaret();
    openVoiceAddon(null, 'translate', true);
  };
  const speakerInfo = (index) => {
    const voiceId = voiceSpeakerVoiceValue(index);
    const item = currentVoiceListForPanel().find((voice) => String(voice.id || voice.voice_id || '') === String(voiceId || ''));
    const name = item ? String(item.label || item.name || item.id || '').split(' · ')[0] : '';
    const provider = isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini');
    return { index, voiceId, name:name || ('Диктор ' + (index + 1)), avatar:item ? voiceAvatarUrlFor(item, provider) : '', item };
  };
  const insertSpeaker = (index) => {
    const info = speakerInfo(index);
    if (!info.voiceId) {
      voiceState.activeSpeakerIndex = index;
      renderVoiceControls();
      openImageOptionMenu(null, 'voice_speaker_' + (index + 1));
      return;
    }
    const before = savedSelection.start > 0 && input.value.slice(0, savedSelection.start).trim() ? '\n' : '';
    insert(before + 'Speaker' + (index + 1) + ': ');
  };
  const templateText = (value) => {
    const one = voiceSpeakerVoiceValue(0) ? 'Speaker1: ' : '';
    const two = voiceSpeakerVoiceValue(1) ? 'Speaker2: ' : '';
    const templates = {
      dialogue: one + 'Первая реплика\n' + two + 'Ответ',
      interview: one + 'Здравствуйте. Начнём интервью.\n' + two + 'Здравствуйте, я готов.',
      podcast: one + 'Добро пожаловать в подкаст.\n' + two + 'Сегодня обсудим важную тему.',
      advertising: one + token('style','confident') + ' Представляем новый продукт.',
      story: one + token('style','narrative') + ' Однажды всё изменилось…',
      audiobook: one + token('style','slow') + ' Глава первая.',
      news: one + token('emotion','serious') + ' Главные новости дня.',
      radio: one + token('style','energetic') + ' Вы слушаете SYLVEX Radio.',
      narrator: one + token('style','confident') + ' Текст диктора.',
      film_dubbing: one + token('direction','voice_over') + ' Реплика персонажа.\n' + two + 'Ответ персонажа.',
    };
    insert(templates[value] || templates.dialogue);
  };
  const aiContinuationItems = () => {
    const before = input ? input.value.slice(0, savedSelection.start).toLowerCase() : '';
    if (/я тебя[\s…\.]*$/.test(before)) return [['люблю','completion:люблю'],['ненавижу','completion:ненавижу'],['очень ждал','completion:очень ждал'],['искал','completion:искал'],['не понимаю','completion:не понимаю']];
    return VOICE_DIALOGUE_DATA.ai;
  };
  const categoryItems = (category) => category === 'speaker'
    ? Array.from({ length:Number(voiceState.numSpeakers || 2) }, (_, index) => {
        const info = speakerInfo(index);
        return [info.name, String(index), !!info.voiceId];
      }).filter((item) => item[2]).concat([['Добавить диктора','add',true]])
    : category === 'ai' ? aiContinuationItems() : (() => {
        const base = VOICE_DIALOGUE_DATA[category] || [];
        const customKey = category === 'sfx' ? 'effects' : category;
        const custom = ['emotion','pause','sfx'].includes(category) && Array.isArray(voiceCustomOptions[customKey])
          ? voiceCustomOptions[customKey].map((label) => [String(label), String(label).trim().toLowerCase().replace(/\s+/g, '_')])
          : [];
        return base.concat(custom);
      })();
  const categoryLabel = { speaker:'Диктор',emotion:'Эмоции',style:'Манера речи',pause:'Паузы',sfx:'Звуковые эффекты',direction:'Режиссура',accent:'Акцент',template:'Шаблон',ai:'AI Assistant' };
  const categories = ['speaker','emotion','style','pause','sfx','direction','accent','template','ai'];
  const icon = (category) => ({
    speaker:'<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3"/><path d="M6 20c.5-4 2.5-6 6-6s5.5 2 6 6"/></svg>',
    emotion:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8.5 10h.01M15.5 10h.01M8 15c2.3 2 5.7 2 8 0"/></svg>',
    style:'<svg viewBox="0 0 24 24"><path d="M4 7h10M4 12h16M4 17h12"/><circle cx="17" cy="7" r="2"/><circle cx="7" cy="17" r="2"/></svg>',
    pause:'<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14"/></svg>',
    sfx:'<svg viewBox="0 0 24 24"><path d="M9 18V6l10-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/></svg>',
    direction:'<svg viewBox="0 0 24 24"><path d="M5 19 19 5M10 5h9v9"/></svg>',
    accent:'<svg viewBox="0 0 24 24"><path d="m5 19 7-14 7 14M8 14h8"/></svg>',
    template:'<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
    ai:'<svg viewBox="0 0 24 24"><path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3ZM18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8L18 15Z"/></svg>',
  }[category] || '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/></svg>');

  const runAction = (category, value) => {
    closeMenus();
    if (category === 'clipboard') {
      if (value === 'paste') pasteText();
      else if (value === 'copy') copyText();
      else if (value === 'translate') translateText();
    } else if (category === 'speaker') {
      if (value === 'add') {
        const previousCount = Number(voiceState.numSpeakers || 1);
        addVoiceSpeaker(null);
        if (Number(voiceState.numSpeakers || 1) > previousCount) {
          voiceState.activeSpeakerIndex = Number(voiceState.numSpeakers) - 1;
          renderVoiceControls();
          openImageOptionMenu(null, 'voice_speaker_' + voiceState.numSpeakers);
        }
      }
      else insertSpeaker(Number(value));
    } else if (category === 'template') templateText(value);
    else if (category === 'ai') {
      if (String(value).startsWith('completion:')) insert(String(value).slice(11));
      else if (value === 'emotional') insert(token('emotion','emotional'), { wrapSelection:true });
      else if (value === 'serious') insert(token('emotion','serious'), { wrapSelection:true });
      else if (value === 'dramatic') insert(token('style','dramatic'), { wrapSelection:true });
      else {
        restoreCaret();
        runVoiceTextTool(null, 'improve');
      }
    } else {
      if (category === 'pause' && savedSelection.end > savedSelection.start) {
        savedSelection = { start:savedSelection.end, end:savedSelection.end, text:'' };
      }
      insert(token(category, value), { wrapSelection:category !== 'pause' && category !== 'sfx' });
    }
  };
  const menuItemsHtml = (category) => categoryItems(category).map((item) => {
    const disabled = item[2] === false;
    return '<button type="button" ' + (disabled ? 'disabled' : '') + ' data-vdc-category="' + category + '" data-vdc-value="' + S.escapeHtml(String(item[1])) + '">' + S.escapeHtml(item[0]) + '</button>';
  }).join('');
  const ensureContextMenu = () => {
    if (contextMenu) return contextMenu;
    contextMenu = document.createElement('div');
    contextMenu.className = 'voice-caret-menu';
    contextMenu.hidden = true;
    contextMenu.addEventListener('pointerdown', (event) => event.preventDefault());
    contextMenu.addEventListener('click', (event) => {
      const action = event.target.closest('[data-vdc-category][data-vdc-value]');
      if (action) runAction(action.dataset.vdcCategory, action.dataset.vdcValue);
    });
    contextMenu.addEventListener('mouseover', (event) => {
      const item = event.target.closest('.voice-caret-menu-item');
      if (!item || !contextMenu.contains(item)) return;
      window.clearTimeout(submenuTimers.get(item));
      contextMenu.querySelectorAll('.voice-caret-menu-item.submenu-open').forEach((openItem) => {
        if (openItem !== item) openItem.classList.remove('submenu-open');
      });
      if (item.querySelector('.voice-caret-submenu')) item.classList.add('submenu-open');
    });
    contextMenu.addEventListener('mouseout', (event) => {
      const item = event.target.closest('.voice-caret-menu-item');
      if (!item || !item.classList.contains('submenu-open') || item.contains(event.relatedTarget)) return;
      const timer = window.setTimeout(() => item.classList.remove('submenu-open'), 420);
      submenuTimers.set(item, timer);
    });
    document.body.appendChild(contextMenu);
    return contextMenu;
  };
  const openContextMenu = (x, y) => {
    if (!active() || isTouchLayout()) return;
    rememberCaret();
    const selected = savedSelection.start !== savedSelection.end;
    const menu = ensureContextMenu();
    const clipboardActions = '<div class="voice-caret-menu-item"><button type="button" data-vdc-category="clipboard" data-vdc-value="paste"><span>' + icon('template') + '</span>Вставить текст<i></i></button></div>'
      + '<div class="voice-caret-menu-item"><button type="button" data-vdc-category="clipboard" data-vdc-value="copy" ' + (!selected ? 'disabled' : '') + '><span>' + icon('template') + '</span>Копировать<i></i></button></div>'
      + '<div class="voice-caret-menu-item"><button type="button" data-vdc-category="clipboard" data-vdc-value="translate"><span>' + icon('accent') + '</span>Перевести текст<i></i></button></div><hr>';
    if (selected) {
      const direct = [
        ['emotion','emotional','Сделать эмоциональнее'],['style','whisper','Шёпотом'],['emotion','serious','Сделать серьёзнее'],['ai','rewrite','Переписать'],
      ];
      menu.innerHTML = clipboardActions + direct.map((item) => '<div class="voice-caret-menu-item"><button type="button" data-vdc-category="' + item[0] + '" data-vdc-value="' + item[1] + '"><span>' + icon(item[0]) + '</span>' + item[2] + '<i></i></button></div>').join('')
        + '<div class="voice-caret-menu-item"><button type="button"><span>' + icon('speaker') + '</span>Назначить диктора<i>›</i></button><div class="voice-caret-submenu">' + menuItemsHtml('speaker') + '</div></div>'
        + '<div class="voice-caret-menu-item"><button type="button" data-vdc-category="pause" data-vdc-value="0.5"><span>' + icon('pause') + '</span>Добавить паузу после<i></i></button></div><hr>'
        + '<div class="voice-caret-menu-item"><button type="button"><span>' + icon('ai') + '</span>AI Assistant<i>›</i></button><div class="voice-caret-submenu">' + menuItemsHtml('ai') + '</div></div>';
    } else {
      const orderedCategories = ['emotion','pause','sfx','speaker','style','direction','accent','template','ai'];
      menu.innerHTML = clipboardActions + orderedCategories.map((category, index) => '<div class="voice-caret-menu-item"><button type="button"><span>' + icon(category) + '</span>' + categoryLabel[category] + '<i>›</i></button><div class="voice-caret-submenu">' + menuItemsHtml(category) + '</div></div>' + (index === orderedCategories.length - 2 ? '<hr>' : '')).join('');
    }
    menu.hidden = false;
    const width = 240;
    const inputRect = input && input.getBoundingClientRect ? input.getBoundingClientRect() : null;
    menu.style.left = Math.max(8, Math.min(window.innerWidth - width - 8, x)) + 'px';
    menu.style.top = Math.max(8, Math.min(window.innerHeight - 360, inputRect ? inputRect.top : y)) + 'px';
  };
  const ensureMobileUi = () => {
    if (!mobileToolbar) {
      mobileToolbar = document.createElement('div');
      mobileToolbar.className = 'voice-dialogue-mobile-toolbar';
      mobileToolbar.setAttribute('aria-label', 'Инструменты диалога');
      mobileToolbar.innerHTML = '<button type="button" data-vdc-open="quick"><span>' + icon('template') + '</span>Меню</button>' + ['speaker','emotion','pause','sfx','style','direction','ai'].map((category) => '<button type="button" data-vdc-open="' + category + '"><span>' + icon(category) + '</span>' + categoryLabel[category] + '</button>').join('');
      mobileToolbar.addEventListener('pointerdown', (event) => event.preventDefault());
      mobileToolbar.addEventListener('click', (event) => {
        const button = event.target.closest('[data-vdc-open]');
        if (button) openBottomSheet(button.dataset.vdcOpen);
      });
      document.body.appendChild(mobileToolbar);
    }
    if (!bottomSheet) {
      bottomSheet = document.createElement('div');
      bottomSheet.className = 'voice-dialogue-bottom-sheet';
      bottomSheet.hidden = true;
      bottomSheet.addEventListener('pointerdown', (event) => event.preventDefault());
      bottomSheet.addEventListener('click', (event) => {
        if (event.target === bottomSheet || event.target.closest('[data-vdc-close]')) return closeMenus();
        const markerAction = event.target.closest('[data-vdc-marker-action]');
        if (markerAction) return editMarker(Number(markerAction.dataset.vdcLine), markerAction.dataset.vdcMarkerAction, markerAction.dataset.vdcSpeaker);
        const action = event.target.closest('[data-vdc-category][data-vdc-value]');
        if (action) runAction(action.dataset.vdcCategory, action.dataset.vdcValue);
      });
      document.body.appendChild(bottomSheet);
    }
  };
  const openBottomSheet = (category) => {
    if (!active()) return;
    rememberCaret();
    ensureMobileUi();
    const quickItems = '<button type="button" data-vdc-category="clipboard" data-vdc-value="paste">Вставить текст</button><button type="button" data-vdc-category="clipboard" data-vdc-value="copy">Копировать</button><button type="button" data-vdc-category="clipboard" data-vdc-value="translate">Перевести</button>'
      + categories.map((item) => '<button type="button" data-vdc-open-nested="' + item + '">' + categoryLabel[item] + '</button>').join('');
    bottomSheet.innerHTML = '<div class="voice-dialogue-sheet-card"><header><b>' + (category === 'quick' ? 'Инструменты текста' : categoryLabel[category]) + '</b><button type="button" data-vdc-close>×</button></header><div class="voice-dialogue-sheet-items">' + (category === 'quick' ? quickItems : menuItemsHtml(category)) + '</div></div>';
    bottomSheet.querySelectorAll('[data-vdc-open-nested]').forEach((button) => button.addEventListener('click', () => openBottomSheet(button.dataset.vdcOpenNested)));
    const rect = input && input.getBoundingClientRect ? input.getBoundingClientRect() : null;
    if (rect) {
      const menuWidth = Math.min(276, rect.width, window.innerWidth - 24);
      const menuLeft = Math.max(12, Math.min(window.innerWidth - menuWidth - 12, rect.left));
      bottomSheet.style.setProperty('--voice-menu-left', menuLeft + 'px');
      bottomSheet.style.setProperty('--voice-menu-width', menuWidth + 'px');
      bottomSheet.style.setProperty('--voice-menu-bottom', Math.max(8, window.innerHeight - rect.top + 8) + 'px');
    }
    bottomSheet.hidden = false;
  };
  const closeMenus = () => {
    if (contextMenu) contextMenu.hidden = true;
    if (bottomSheet) bottomSheet.hidden = true;
  };
  const editMarker = (lineIndex, action, speakerValue) => {
    const line = dialogueLines[lineIndex];
    if (!line || !input) return closeMenus();
    if (action === 'delete') {
      input.value = input.value.slice(0, line.marker_start) + input.value.slice(line.marker_end).replace(/^\s*/, '');
      afterEdit(line.marker_start);
      closeMenus();
      return;
    }
    if (action === 'replace' && speakerValue !== undefined && speakerValue !== '') {
      const replacement = 'Speaker' + (Number(speakerValue) + 1) + ':';
      input.value = input.value.slice(0, line.marker_start) + replacement + input.value.slice(line.marker_end);
      afterEdit(line.marker_start + replacement.length);
      closeMenus();
      return;
    }
    voiceState.activeSpeakerIndex = line.speaker_index;
    renderVoiceControls();
    openImageOptionMenu(null, 'voice_speaker_' + (line.speaker_index + 1));
    closeMenus();
  };
  const openMarkerActions = (lineIndex) => {
    const line = dialogueLines[lineIndex];
    if (!line) return;
    ensureMobileUi();
    const speakers = categoryItems('speaker').filter((item) => item[1] !== 'add').map((item) => '<button type="button" data-vdc-marker-action="replace" data-vdc-line="' + lineIndex + '" data-vdc-speaker="' + item[1] + '">Заменить на ' + S.escapeHtml(item[0]) + '</button>').join('');
    bottomSheet.innerHTML = '<div class="voice-dialogue-sheet-card voice-marker-actions"><header><b>' + S.escapeHtml(line.speaker_name) + '</b><button type="button" data-vdc-close>×</button></header><div class="voice-dialogue-sheet-items">' + speakers + '<button type="button" data-vdc-marker-action="voice" data-vdc-line="' + lineIndex + '">Заменить голос</button><button class="is-danger" type="button" data-vdc-marker-action="delete" data-vdc-line="' + lineIndex + '">Удалить диктора из реплики</button></div></div>';
    bottomSheet.hidden = false;
  };
  const refreshMarkers = () => {
    if (!markerRail || !input) return;
    input.classList.remove('voice-dialogue-has-speakers');
    if (!active()) { markerRail.hidden = true; markerRail.innerHTML = ''; return; }
    const matches = Array.from(input.value.matchAll(/(?:^|\n)Speaker([1-7]):\s*([^\n]*)/g));
    markerRail.hidden = true;
    markerRail.innerHTML = '';
    dialogueLines = matches.map((match, lineIndex) => {
      const speakerIndex = Math.max(0, Number(match[1]) - 1);
      const info = speakerInfo(speakerIndex);
      const markerStart = Number(match.index || 0) + (match[0].startsWith('\n') ? 1 : 0);
      const markerText = 'Speaker' + match[1] + ':';
      return {
        line_id:lineIndex,
        speaker_id:'speaker_' + (speakerIndex + 1),
        speaker_index:speakerIndex,
        voice_id:info.voiceId || '',
        speaker_name:info.name,
        avatar_url:info.avatar || '',
        text:match[2] || '',
        marker_start:markerStart,
        marker_end:markerStart + markerText.length,
      };
    });
  };
  const setup = (editor) => {
    if (!editor || input === editor) return;
    input = editor;
    markerRail = document.createElement('div');
    markerRail.className = 'voice-dialogue-marker-data';
    markerRail.hidden = true;
    input.parentElement.insertBefore(markerRail, input);
    ['keyup','click','select','input'].forEach((name) => input.addEventListener(name, () => { rememberCaret(); if (name === 'input') refreshMarkers(); }));
    document.addEventListener('selectionchange', () => { if (document.activeElement === input) rememberCaret(); });
    input.addEventListener('contextmenu', (event) => {
      if (!active()) return;
      event.preventDefault();
      if (isTouchLayout()) return;
      openContextMenu(event.clientX, event.clientY);
    });
    input.addEventListener('pointerdown', (event) => {
      if (!active() || !isTouchLayout() || event.pointerType === 'mouse') return;
      window.clearTimeout(longPressTimer);
      longPressPoint = { x:event.clientX, y:event.clientY, id:event.pointerId };
      longPressTimer = window.setTimeout(() => {
        if (!active() || !longPressPoint) return;
        rememberCaret();
        openBottomSheet('quick');
        longPressPoint = null;
        S.haptic && S.haptic.impact && S.haptic.impact('medium');
      }, 2000);
    });
    input.addEventListener('pointermove', (event) => {
      if (!longPressPoint || event.pointerId !== longPressPoint.id) return;
      if (Math.hypot(event.clientX - longPressPoint.x, event.clientY - longPressPoint.y) > 12) {
        window.clearTimeout(longPressTimer); longPressPoint = null;
      }
    }, { passive:true });
    input.addEventListener('pointerup', (event) => {
      window.clearTimeout(longPressTimer);
      if (active() && isTouchLayout() && event.pointerType !== 'mouse') {
        const now = Date.now();
        const closeToPrevious = mobileTapPoint && Math.hypot(event.clientX - mobileTapPoint.x, event.clientY - mobileTapPoint.y) < 28;
        if (closeToPrevious && now - mobileTapAt < 360) {
          event.preventDefault();
          rememberCaret();
          openBottomSheet('quick');
          mobileTapAt = 0; mobileTapPoint = null;
          S.haptic && S.haptic.impact && S.haptic.impact('light');
        } else {
          mobileTapAt = now; mobileTapPoint = { x:event.clientX, y:event.clientY };
        }
      }
      longPressPoint = null;
    });
    input.addEventListener('pointercancel', () => {
      window.clearTimeout(longPressTimer); longPressPoint = null;
    }, { passive:true });
    document.addEventListener('pointerdown', (event) => {
      if (contextMenu && !contextMenu.hidden && !event.target.closest('.voice-caret-menu')) closeMenus();
    });
    ensureMobileUi();
  };
  return { setup, rememberCaret, restoreCaret, insert, insertSpeaker, runAction, openBottomSheet, closeMenus, refreshMarkers, getDialogueLines:() => dialogueLines.map((line) => Object.assign({}, line)), data:VOICE_DIALOGUE_DATA };
})();

function selectedVoiceIdentity() {
  return String(isElevenLabsVoiceModel(voiceState.modelId) ? voiceState.elevenlabsVoice : (isRunwayVoiceModel(voiceState.modelId) ? voiceState.runwayVoice : voiceState.voice) || 'voice');
}

function voiceEditorSelection() {
  const input = document.getElementById('chatInput');
  if (!input) return { input:null, start:0, end:0, text:'' };
  const start = Number.isFinite(input.selectionStart) ? input.selectionStart : 0;
  const end = Number.isFinite(input.selectionEnd) ? input.selectionEnd : start;
  return { input, start, end, text:input.value.slice(start, end) };
}

function replaceVoiceEditorSelection(value, selectInserted) {
  const selection = voiceEditorSelection();
  if (!selection.input) return;
  selection.input.value = selection.input.value.slice(0, selection.start) + value + selection.input.value.slice(selection.end);
  const end = selection.start + value.length;
  selection.input.focus();
  selection.input.setSelectionRange(selectInserted ? selection.start : end, end);
  autoGrow(selection.input);
  updateVoiceTextEstimate();
  updateSendButton();
  saveCurrentDraftSoon();
}

function closeVoiceAddon(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const drawer = document.getElementById('voiceAddonDrawer');
  if (drawer) { drawer.hidden = true; drawer.innerHTML = ''; drawer.dataset.kind = ''; drawer.classList.remove('voice-translation-fullscreen', 'voice-addon-modal'); }
}

function hideMobileKeyboard(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const active = document.activeElement;
  if (active && typeof active.blur === 'function') active.blur();
  try { navigator.virtualKeyboard?.hide?.(); } catch {}
  document.documentElement.style.setProperty('--kb', '0px');
  document.body.classList.remove('kb-open');
  document.body.classList.remove('composer-input-window-open');
  document.getElementById('studioComposer')?.classList.remove('composer-input-window');
}

function usesVirtualKeyboardLayout() {
  return Boolean(S.device && S.device.usesVirtualKeyboard);
}

function dismissGenerationInputUi() {
  hideMobileKeyboard();
  closeVoiceAddon();
  activeVoicePanelSection = '';
  renderVoiceToolPanel();
  document.querySelectorAll('.voice-upload-select-wrap.open').forEach((item) => item.classList.remove('open'));
  const modelPop = document.getElementById('modelPop');
  if (modelPop) {
    modelPop.classList.remove('show', 'image-model-floating-pop', 'image-size-floating-pop', 'music-settings-pop', 'video-option-horizontal-pop');
    modelPop.style.cssText = '';
  }
  document.getElementById('plusSheet')?.classList.remove('show');
  const videoAddMenu = document.getElementById('videoAddMenu');
  if (videoAddMenu) videoAddMenu.hidden = true;
}

function toggleVoiceHorizontalTools(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const toggle = document.getElementById('voiceToolsToggle');
  const tools = document.getElementById('voiceHorizontalTools');
  if (!toggle || !tools) return;
  const willOpen = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  tools.dataset.open = willOpen ? 'true' : 'false';
  resetVoiceToolGuideTimer();
}

const VOICE_TOOL_GUIDE_TEXT = {
  'Эмоция':'Добавляет настроение выбранной реплике.',
  'Пауза':'Вставляет паузу нужной длительности.',
  'Произношение':'Сохраняет правильное чтение сложных слов.',
  'Перевести':'Переводит текст перед озвучкой.',
  'Создать текст с AI':'Создаёт готовый текст по вашей теме.',
  'Улучшить текст':'Делает текст естественным для диктора.',
  'Анализ текста':'Проверяет длительность и удобство чтения.',
  'Звуковые эффекты':'Добавляет звуковую сцену в нужное место.',
  'Прослушать':'Воспроизводит выбранный голос.',
  'В избранное':'Сохраняет голос для быстрого доступа.',
  'Информация':'Показывает данные голоса и модели.',
  'Настройки голоса':'Открывает параметры звучания.',
  'Добавить диктора':'Добавляет отдельного участника диалога.',
  'Полный экран':'Разворачивает редактор для удобной работы.',
};

function clearVoiceToolGuide() {
  if (voiceToolGuideIdleTimer) window.clearTimeout(voiceToolGuideIdleTimer);
  if (voiceToolGuideStepTimer) window.clearTimeout(voiceToolGuideStepTimer);
  voiceToolGuideIdleTimer = 0; voiceToolGuideStepTimer = 0; voiceToolGuideIndex = 0;
  document.getElementById('voiceToolGuideBubble')?.remove();
  document.querySelectorAll('.voice-tool-guide-active').forEach((button) => { button.classList.remove('voice-tool-guide-active'); button.removeAttribute('aria-describedby'); });
}

function renderNextVoiceToolGuide() {
  const tools = document.getElementById('voiceHorizontalTools');
  if (!isVoiceMode() || voiceWorkspaceMode !== 'dialogue' || !tools) return clearVoiceToolGuide();
  if (voiceToolBlockingModalOpen()) {
    voiceToolGuideStepTimer = window.setTimeout(renderNextVoiceToolGuide, 5000);
    return;
  }
  const buttons = Array.from(tools.querySelectorAll('.voice-editor-toolbar button'));
  if (!buttons.length || voiceToolGuideIndex >= buttons.length) return clearVoiceToolGuide();
  document.querySelectorAll('.voice-tool-guide-active').forEach((item) => item.classList.remove('voice-tool-guide-active'));
  const button = buttons[voiceToolGuideIndex++];
  const label = button.getAttribute('title') || button.getAttribute('aria-label') || 'Инструмент';
  const icon = button.querySelector('svg');
  const bubble = document.createElement('div');
  bubble.id = 'voiceToolGuideBubble'; bubble.className = 'voice-tool-guide';
  bubble.innerHTML = '<span class="voice-tool-guide-head"><span class="voice-tool-guide-icon">' + (icon ? icon.outerHTML : '') + '</span><b>' + S.escapeHtml(label) + '</b></span><span>' + S.escapeHtml(VOICE_TOOL_GUIDE_TEXT[label] || 'Инструмент редактора озвучки.') + '</span>';
  document.body.appendChild(bubble);
  button.classList.add('voice-tool-guide-active');
  button.setAttribute('aria-describedby', 'voiceToolGuideBubble');
  const rect = button.getBoundingClientRect();
  bubble.style.left = Math.max(8, Math.min(window.innerWidth - 218, rect.left + rect.width / 2 - 105)) + 'px';
  bubble.style.top = Math.min(window.innerHeight - 90, rect.bottom + 8) + 'px';
  button.scrollIntoView({ behavior:'smooth', block:'nearest', inline:'center' });
  voiceToolGuideStepTimer = window.setTimeout(showNextVoiceToolGuide, 5000);
}

function showNextVoiceToolGuide() {
  const current = document.getElementById('voiceToolGuideBubble');
  if (!current) return renderNextVoiceToolGuide();
  current.classList.add('is-leaving');
  document.querySelectorAll('.voice-tool-guide-active').forEach((button) => {
    button.classList.remove('voice-tool-guide-active');
    button.removeAttribute('aria-describedby');
  });
  voiceToolGuideStepTimer = window.setTimeout(() => {
    current.remove();
    renderNextVoiceToolGuide();
  }, 230);
}

function resetVoiceToolGuideTimer() {
  clearVoiceToolGuide();
  if (!isVoiceMode() || voiceWorkspaceMode !== 'dialogue' || !document.getElementById('voiceHorizontalTools')) return;
  voiceToolGuideIdleTimer = window.setTimeout(showNextVoiceToolGuide, 300000);
}

function voiceToolBlockingModalOpen() {
  const selectors = [
    '.modal-overlay.show', '.voice-tool-panel:not([hidden])', '#modelPop.show',
    '.video-template-modal-backdrop', '.photo-tool-modal-backdrop', '.visual-picker-modal.show',
    '.generation-info-drawer.show', '[role="dialog"]', '[class*="modal-backdrop"]',
  ];
  return selectors.some((selector) => Array.from(document.querySelectorAll(selector)).some((element) => {
    if (!element || element.id === 'voiceToolGuideBubble') return false;
    const style = window.getComputedStyle(element);
    return !element.hidden && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) !== 0;
  }));
}

function voiceAddonShell(title, body) {
  return '<div class="voice-addon-head"><b>' + S.escapeHtml(title) + '</b><button type="button" aria-label="Закрыть" onclick="SYLVEX.closeVoiceAddon(event)">×</button></div>' + body;
}

function voiceInlineOptionStrip(kind, title, items, insertHandler, suffix) {
  return '<div class="voice-inline-option-strip"><button class="voice-inline-add" type="button" aria-label="Добавить свой вариант" onclick="SYLVEX.openVoiceCustomOption(event,\'' + kind + '\')">+</button><b>' + S.escapeHtml(title) + '</b>' + items.map((item) => '<button type="button" data-value="' + S.escapeHtml(String(item)) + '" onclick="SYLVEX.' + insertHandler + '(event,this.dataset.value)">' + S.escapeHtml(String(item)) + (suffix || '') + '</button>').join('') + '</div>';
}

function openVoiceAddon(event, kind, centeredModal, forceRender) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const drawer = document.getElementById('voiceAddonDrawer');
  if (!drawer) return;
  if (!forceRender && !drawer.hidden && drawer.dataset.kind === kind) {
    closeVoiceAddon();
    return;
  }
  drawer.dataset.kind = kind;
  drawer.classList.toggle('voice-addon-modal', !!centeredModal);
  const currentVoice = currentVoiceButtonLabel();
  let body = '';
  if (kind === 'info') {
    body = voiceAddonShell('Информация о голосе', '<div class="voice-addon-options"><span>' + S.escapeHtml(currentVoice) + '</span><span>' + S.escapeHtml(VOICE_MODEL_LIST.find((item) => item.id === voiceState.modelId)?.label || voiceState.modelId) + '</span></div>');
  } else if (kind === 'settings') {
    const settings = voiceState.audioSettings || {};
    const rows = [
      ['speed','Скорость',50,200,Math.round(Number(settings.speed || 1) * 100),'%'],
      ['pitch','Высота',0,100,Number(settings.pitch ?? 50),''],
      ['expressiveness','Эмоциональность',0,100,Number(settings.expressiveness ?? 50),''],
      ['stability','Стабильность',0,100,Math.round(Number(settings.stability ?? .5) * 100),'%'],
      ['similarity_boost','Сходство',0,100,Math.round(Number(settings.similarity_boost ?? .75) * 100),'%'],
    ];
    body = voiceAddonShell('Настройки голоса', rows.map((row) => '<label class="voice-addon-setting"><span>' + row[1] + '</span><input type="range" min="' + row[2] + '" max="' + row[3] + '" value="' + row[4] + '" oninput="SYLVEX.setVoiceEditorSetting(event,\'' + row[0] + '\',this.value)"><output>' + row[4] + row[5] + '</output></label>').join(''));
  } else if (kind === 'emotion') {
    const emotions = VOICE_EMOTIONS.concat(voiceCustomOptions.emotion || []);
    body = voiceInlineOptionStrip('emotion', 'Эмоции', emotions, 'insertVoiceEmotion');
  } else if (kind === 'pause') {
    const pauses = VOICE_PAUSES.concat(voiceCustomOptions.pause || []);
    body = voiceInlineOptionStrip('pause', 'Пауза', pauses, 'insertVoicePause', ' сек');
  } else if (kind === 'pronunciation') {
    const selected = voiceEditorSelection().text.trim();
    body = voiceAddonShell('Произношение', '<input class="voice-addon-field" id="voicePronunciationWord" placeholder="Слово" value="' + S.escapeHtml(selected) + '"><input class="voice-addon-field" id="voicePronunciationAs" placeholder="Читать как"><button class="voice-addon-primary" type="button" onclick="SYLVEX.saveVoicePronunciation(event)">Сохранить</button>');
  } else if (kind === 'translate') {
    const languageOptions = '<option value="auto">Auto</option><option value="en">English</option><option value="de">Deutsch</option><option value="fr">Français</option><option value="ru">Русский</option><option value="es">Español</option><option value="it">Italiano</option><option value="tr">Türkçe</option>';
    body = voiceAddonShell('Перевести текст', '<textarea class="voice-addon-field" id="voiceTranslateInput" rows="4" placeholder="Введите текст для перевода">' + S.escapeHtml(voiceEditorSelection().text.trim() || document.getElementById('chatInput')?.value || '') + '</textarea><div class="voice-translation-grid"><select class="voice-addon-field" id="voiceTranslateSource">' + languageOptions + '</select><button class="voice-translation-swap" type="button" title="Поменять языки" onclick="SYLVEX.swapVoiceTranslationLanguages(event)"><svg viewBox="0 0 24 24"><path d="m7 7-3 3 3 3M4 10h15M17 17l3-3-3-3M20 14H5"/></svg></button><select class="voice-addon-field" id="voiceTranslateLanguage">' + languageOptions.replace('<option value="auto">Auto</option>','') + '</select></div><button class="voice-addon-primary" type="button" onclick="SYLVEX.runVoiceTextTool(event,\'translate\')">Перевести</button><div class="voice-translation-result" id="voiceTranslationResult" hidden></div><div class="voice-translation-actions" id="voiceTranslationActions" hidden><button type="button" title="На весь экран" onclick="SYLVEX.toggleVoiceTranslationFullscreen(event)"><svg viewBox="0 0 24 24"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/></svg></button><button type="button" title="Копировать" onclick="SYLVEX.copyVoiceTranslation(event)"><svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg></button><button type="button" title="Вставить в редактор" onclick="SYLVEX.applyVoiceTranslation(event)"><svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg></button></div>');
  } else if (kind === 'ai') {
    body = voiceAddonShell('Создать текст с AI', '<div class="voice-addon-options">' + VOICE_AI_FORMATS.map((item) => '<button type="button" data-voice-ai-format="' + item[0] + '" onclick="SYLVEX.selectVoiceAiFormat(event,\'' + item[0] + '\')">' + item[1] + '</button>').join('') + '</div><input class="voice-addon-field" id="voiceAiBrief" placeholder="Опишите тему и задачу"><button class="voice-addon-primary" type="button" onclick="SYLVEX.runVoiceTextTool(event,\'create\')">Создать текст</button>');
  } else if (kind === 'analysis') {
    const text = (document.getElementById('chatInput')?.value || '').trim();
    const words = text ? text.split(/\s+/).length : 0;
    const seconds = Math.ceil(words / 2.5);
    const longSentences = (text.match(/[^.!?]+[.!?]?/g) || []).filter((sentence) => sentence.trim().split(/\s+/).length > 24).length;
    body = voiceAddonShell('Анализ текста', '<div class="voice-analysis-result"><p>Слов: ' + words + '</p><p>Ориентировочное время: ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0') + '</p><p>' + (longSentences ? 'Длинных предложений: ' + longSentences + '. Рекомендуем добавить паузы.' : 'Темп текста подходит для озвучки.') + '</p></div>');
  } else if (kind === 'effects') {
    const effects = VOICE_EFFECTS.concat(voiceCustomOptions.effects || []);
    body = voiceInlineOptionStrip('effects', 'Звуковые эффекты', effects, 'insertVoiceEffect');
  } else if (kind.startsWith('custom_')) {
    const customKind = kind.slice(7);
    const meta = customKind === 'pause'
      ? ['Добавить паузу', 'Длительность в секундах', 'number']
      : customKind === 'effects'
        ? ['Добавить звуковой эффект', 'Название эффекта', 'text']
        : ['Добавить эмоцию', 'Название эмоции', 'text'];
    body = voiceAddonShell(meta[0], voiceCustomOptionForm(customKind, meta[1], meta[2]));
  } else if (kind === 'templates') {
    body = voiceAddonShell('Шаблоны текста', '<div class="voice-addon-options voice-template-strip" id="voiceTemplateStrip"><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'ad\')">Реклама</button><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'tiktok\')">TikTok</button><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'youtube\')">YouTube</button><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'podcast\')">Подкаст</button><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'book\')">Книга</button><button type="button" onclick="SYLVEX.applyVoiceTemplate(event,\'news\')">Новости</button></div>');
  }
  drawer.innerHTML = body;
  drawer.hidden = false;
}

function openVoiceCustomOption(event, kind) {
  openVoiceAddon(event, 'custom_' + kind, true, true);
}

function voiceCustomOptionForm(kind, placeholder, inputType) {
  return '<div class="voice-custom-option-form"><input id="voiceCustomOptionInput" type="' + (inputType || 'text') + '" ' + (inputType === 'number' ? 'min="0.1" max="30" step="0.1" ' : '') + 'placeholder="' + S.escapeHtml(placeholder) + '"><button type="button" onclick="SYLVEX.addVoiceCustomOption(event,\'' + kind + '\')"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg><span>Добавить</span></button></div>';
}

function addVoiceCustomOption(event, kind) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const input = document.getElementById('voiceCustomOptionInput');
  let value = (input?.value || '').trim();
  if (kind === 'pause') {
    const seconds = Number(value.replace(',', '.'));
    if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 30) return toast('Укажите паузу от 0.1 до 30 секунд');
    value = String(Math.round(seconds * 10) / 10);
  }
  if (!value) return toast('Введите свой вариант');
  const list = voiceCustomOptions[kind] || (voiceCustomOptions[kind] = []);
  if (!list.some((item) => String(item).toLowerCase() === value.toLowerCase())) list.push(value);
  try { localStorage.setItem(VOICE_CUSTOM_OPTIONS_KEY, JSON.stringify(voiceCustomOptions)); } catch {}
  closeVoiceAddon();
  renderVoiceSpeakerComposer();
  toast('Вариант добавлен');
}

function setVoiceEditorSetting(event, key, rawValue) {
  if (event) event.stopPropagation();
  ensureVoiceSettings();
  const numeric = Number(rawValue);
  voiceState.audioSettings[key] = key === 'speed' ? numeric / 100 : (key === 'stability' || key === 'similarity_boost' ? numeric / 100 : numeric);
  const output = event && event.target && event.target.parentElement ? event.target.parentElement.querySelector('output') : null;
  if (output) output.textContent = numeric + (['speed','stability','similarity_boost'].includes(key) ? '%' : '');
}

function insertVoiceEmotion(event, emotion) {
  if (event) event.stopPropagation();
  VoiceDialogueComposer.rememberCaret();
  const mapped = VOICE_DIALOGUE_DATA.emotion.find((item) => item[0] === emotion);
  VoiceDialogueComposer.runAction('emotion', mapped ? mapped[1] : String(emotion).toLowerCase());
}

function insertVoicePause(event, seconds) {
  if (event) event.stopPropagation();
  VoiceDialogueComposer.rememberCaret();
  VoiceDialogueComposer.runAction('pause', String(Number(seconds)));
}

function insertVoiceEditorMarkup(value) {
  // Repeatable editor commands are additive: the same emotion, pause or
  // sound effect may intentionally appear many times in one script.
  replaceVoiceEditorSelection(value, false);
}

function saveVoicePronunciation(event) {
  if (event) event.stopPropagation();
  const word = (document.getElementById('voicePronunciationWord')?.value || '').trim();
  const spoken = (document.getElementById('voicePronunciationAs')?.value || '').trim();
  if (!word || !spoken) return toast('Заполните слово и произношение');
  voiceState.pronunciationRules[word] = spoken;
  try { localStorage.setItem('sylvex_voice_pronunciations', JSON.stringify(voiceState.pronunciationRules)); } catch {}
  toast('Произношение сохранено');
  closeVoiceAddon();
}

function selectVoiceAiFormat(event, format) {
  if (event) event.stopPropagation();
  const nextFormat = voiceState.aiFormat === format ? '' : format;
  voiceState.aiFormat = nextFormat;
  document.querySelectorAll('[data-voice-ai-format]').forEach((button) => button.classList.toggle('active', !!nextFormat && button.dataset.voiceAiFormat === nextFormat));
}

async function runVoiceTextTool(event, action) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const input = document.getElementById('chatInput');
  if (!input) return;
  const selected = voiceEditorSelection();
  const translationInput = document.getElementById('voiceTranslateInput');
  const sourceText = action === 'translate' && translationInput ? translationInput.value.trim() : (selected.text.trim() || input.value.trim());
  const brief = (document.getElementById('voiceAiBrief')?.value || '').trim();
  if (action !== 'create' && !sourceText) return toast('Сначала введите или выделите текст');
  if (action === 'create' && !brief) return toast('Опишите тему текста');
  const drawer = document.getElementById('voiceAddonDrawer');
  if (drawer) drawer.classList.add('voice-text-tool-loading');
  try {
    const response = await fetch('/api/public/prostudio/voice/text-tool', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      telegram_id:getTelegramId(), action, text:sourceText, brief, format:voiceState.aiFormat || 'script', source_language:document.getElementById('voiceTranslateSource')?.value || 'auto', target_language:document.getElementById('voiceTranslateLanguage')?.value || 'en'
    }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok || !data.text) throw new Error(data.error || 'Не удалось обработать текст');
    if (action === 'translate') {
      const result = document.getElementById('voiceTranslationResult');
      const actions = document.getElementById('voiceTranslationActions');
      if (result) { result.textContent = data.text; result.hidden = false; }
      if (actions) actions.hidden = false;
    } else {
      if (selected.text.trim()) replaceVoiceEditorSelection(data.text, false);
      else { input.value = data.text; autoGrow(input); updateVoiceTextEstimate(); updateSendButton(); }
      closeVoiceAddon();
    }
  } catch (error) { toast(translateGenerationError(error, 'Не удалось обработать текст')); }
  finally { if (drawer) drawer.classList.remove('voice-text-tool-loading'); }
}

function applyVoiceTemplate(event, template) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  if (voiceState.editorTemplate === template) {
    voiceState.editorTemplate = '';
    voiceState.audioSettings.style = 'auto';
    voiceState.audioSettings.speed = 1;
    document.querySelectorAll('#voiceTemplateStrip button').forEach((button) => button.classList.remove('active'));
    toast('Шаблон отменён');
    return;
  }
  voiceState.editorTemplate = template;
  const settings = voiceState.audioSettings || (voiceState.audioSettings = {});
  const presets = { ad:['energetic',1.08],tiktok:['energetic',1.12],youtube:['friendly',1],podcast:['conversational',.96],book:['narrative',.92],news:['serious',1] };
  const preset = presets[template] || ['auto',1];
  settings.style = preset[0]; settings.speed = preset[1];
  document.querySelectorAll('#voiceTemplateStrip button').forEach((button) => button.classList.toggle('active', (button.getAttribute('onclick') || '').includes("'" + template + "'")));
  toast('Шаблон применён');
}

function addVoiceSpeaker(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const max = isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2;
  if (voiceState.numSpeakers >= max) return toast('Для выбранной модели доступно дикторов: ' + max);
  voiceState.numSpeakers += 1;
  voiceState.speakerVoices[voiceState.numSpeakers - 1] = '';
  voiceState.speakerMode = 'multi';
  if (isElevenLabsVoiceModel(voiceState.modelId)) voiceState.elevenlabsTool = 'dialogue';
  renderVoiceControls();
}

function removeVoiceSpeaker(event, speakerNumber) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  if (voiceState.numSpeakers <= 1) return;
  const removed = Math.max(2, Math.min(7, Number(speakerNumber || voiceState.numSpeakers)));
  const input = document.getElementById('chatInput');
  const isUsed = !!(input && new RegExp('(?:^|\\n)Speaker' + removed + ':', 'm').test(input.value));
  if (isUsed && !window.confirm('Этот диктор уже используется в репликах. Удалить его?')) return;
  voiceState.speakerVoices.splice(removed - 1, 1);
  voiceState.speakerVoices.push('');
  voiceState.numSpeakers -= 1;
  if (Number.isInteger(voiceState.activeSpeakerIndex)) {
    if (voiceState.activeSpeakerIndex === removed - 1) voiceState.activeSpeakerIndex = null;
    else if (voiceState.activeSpeakerIndex > removed - 1) voiceState.activeSpeakerIndex -= 1;
  }
  voiceState.speakerMode = voiceState.numSpeakers > 1 ? 'multi' : 'single';
  if (isElevenLabsVoiceModel(voiceState.modelId) && voiceState.numSpeakers === 1 && voiceState.elevenlabsTool === 'dialogue') voiceState.elevenlabsTool = 'text_to_speech';
  renderVoiceControls();
  VoiceDialogueComposer.refreshMarkers();
}

function insertVoiceEffect(event, effect) {
  if (event) event.stopPropagation();
  VoiceDialogueComposer.rememberCaret();
  const mapped = VOICE_DIALOGUE_DATA.sfx.find((item) => item[0] === effect);
  VoiceDialogueComposer.runAction('sfx', mapped ? mapped[1] : String(effect).toLowerCase());
}

function toggleVoiceEditorFullscreen(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const column = document.querySelector('.studio-prompt-column');
  if (!column) return;
  column.classList.toggle('voice-editor-fullscreen');
  document.body.classList.toggle('voice-editor-is-fullscreen', column.classList.contains('voice-editor-fullscreen'));
  document.getElementById('chatInput')?.focus();
}

function swapVoiceTranslationLanguages(event) {
  if (event) event.stopPropagation();
  const source = document.getElementById('voiceTranslateSource');
  const target = document.getElementById('voiceTranslateLanguage');
  if (!source || !target) return;
  const oldSource = source.value;
  source.value = target.value;
  target.value = oldSource === 'auto' ? 'en' : oldSource;
}

function toggleVoiceTranslationFullscreen(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  document.getElementById('voiceAddonDrawer')?.classList.toggle('voice-translation-fullscreen');
}

async function copyVoiceTranslation(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const value = document.getElementById('voiceTranslationResult')?.textContent || '';
  if (!value) return;
  try { await navigator.clipboard.writeText(value); toast('Перевод скопирован'); }
  catch { toast('Не удалось скопировать перевод'); }
}

function applyVoiceTranslation(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const value = document.getElementById('voiceTranslationResult')?.textContent || '';
  if (!value) return;
  const input = document.getElementById('chatInput');
  if (input) { input.value = value; autoGrow(input); updateVoiceTextEstimate(); updateSendButton(); }
  closeVoiceAddon();
}

function toggleVoiceFavorite(event) {
  if (event) { event.preventDefault(); event.stopPropagation(); }
  const key = selectedVoiceIdentity();
  let favorites = [];
  try { favorites = JSON.parse(localStorage.getItem('sylvex_voice_favorites') || '[]'); } catch {}
  favorites = Array.isArray(favorites) ? favorites : [];
  favorites = favorites.includes(key) ? favorites.filter((item) => item !== key) : favorites.concat(key);
  try { localStorage.setItem('sylvex_voice_favorites', JSON.stringify(favorites)); } catch {}
  document.getElementById('voiceFavoriteBtn')?.classList.toggle('active', favorites.includes(key));
}

function updateVoiceTextEstimate() {
  if (!isVoiceMode()) return;
  const text = document.getElementById('chatInput')?.value || '';
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const speed = Number((voiceState.audioSettings || {}).speed || 1);
  const seconds = Math.ceil(words / Math.max(1, 2.5 * speed));
  const duration = document.getElementById('voiceDurationEstimate');
  if (duration) duration.textContent = '≈ ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0');
}

function insertVoiceSpeaker(e, speakerNumber) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const input = document.getElementById('chatInput');
  if (!input) return;
  const prefix = 'Speaker' + Math.max(1, Math.min(7, Number(speakerNumber || 1))) + ': ';
  const start = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
  const end = Number.isFinite(input.selectionEnd) ? input.selectionEnd : start;
  const separator = start > 0 && input.value.slice(0, start).trim() ? '\n' : '';
  input.value = input.value.slice(0, start) + separator + prefix + input.value.slice(end);
  const caret = start + separator.length + prefix.length;
  input.focus();
  input.setSelectionRange(caret, caret);
  autoGrow(input);
  updateSendButton();
}

// =====================================================
// БЛОК ОЗВУЧКИ: renderVoiceToolPanel
// Показывает отдельную панель для дубляжа видео, копирования голоса и записи собственного голоса.
// Панель использует уже существующий state озвучки и не влияет на фото, видео или музыку.
// =====================================================
function renderVoiceToolPanel() {
  injectImageStyleSheetCss();
  const panel = document.getElementById('voiceToolPanel');
  if (!panel) return;
  if (!isVoiceMode()) {
    panel.hidden = true;
    panel.classList.remove('voice-list-open');
    panel.classList.remove('voice-create-open');
    panel.classList.remove('voice-upload-open');
    panel.onclick = null;
    panel.innerHTML = '';
    return;
  }
  const isElevenLabs = isElevenLabsVoiceModel(voiceState.modelId);
  const isRunway = isRunwayVoiceModel(voiceState.modelId);
  const tool = voiceState.elevenlabsTool || 'text_to_speech';
  const uploads = Array.isArray(voiceState.uploads) ? voiceState.uploads : [];
  const uploadLabelEl = document.getElementById('voiceUploadLabel');
  if (uploadLabelEl) {
    const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
    const uploading = voiceState.uploading || null;
    const fileName = uploading ? (uploading.name || 'Загрузка файла') : (uploads.length ? (uploads[0].name || 'Файл выбран') : '');
    const model = VOICE_MODEL_LIST.find((item) => item.id === voiceState.modelId) || {};
    const modelLabel = model.label || model.name || voiceState.modelId || '';
    uploadLabelEl.textContent = uploading ? ('Загрузка · ' + fileName) : (fileName ? [purpose.label, modelLabel, fileName].filter(Boolean).join(' · ') : 'Загрузить');
  }
  renderVoiceUploadButtonPreview();
  const active = activeVoicePanelSection || '';
  let body = '';
  if (active === 'voices') body = renderVoiceListPanel();
  if (active === 'create') body = renderVoiceCreatePanel();
  if (active === 'upload') body = renderVoiceUploadPanel();
  panel.hidden = !body;
  panel.classList.toggle('voice-list-open', active === 'voices');
  panel.classList.toggle('voice-create-open', active === 'create');
  panel.classList.toggle('voice-upload-open', active === 'upload');
  panel.onclick = active === 'voices' ? closeVoiceList : ((active === 'create' || active === 'upload') ? closeVoicePanel : null);
  panel.innerHTML = body;
  document.querySelectorAll('.vgen-btn, .vgen-upload-row').forEach((item) => item.classList.remove('active'));
  const activeSelector = active === 'create'
    ? '.vgen-btn[onclick*="openVoiceCreate"]'
    : (active === 'voices' ? '.vgen-btn[onclick*="openVoiceList"]' : (active === 'upload' ? '.vgen-upload-row' : ''));
  if (activeSelector) {
    const activeEl = document.querySelector(activeSelector);
    if (activeEl) activeEl.classList.add('active');
  }
}

function renderVoiceUploadButtonPreview() {
  const row = document.querySelector('.vgen-upload-row');
  if (!row) return;
  const uploading = voiceState.uploading || null;
  const upload = uploading || (Array.isArray(voiceState.uploads) ? voiceState.uploads[0] : null);
  const kind = String((upload && upload.kind) || '').toLowerCase();
  const previewUrl = upload && (upload.previewUrl || upload.url);
  renderUploadPreviewOnButton(row, kind === 'video' && previewUrl ? [{ url: previewUrl, type: 'video' }] : []);
  let badge = row.querySelector(':scope > .voice-upload-control-badge');
  if (!upload) {
    if (badge) badge.remove();
    row.classList.remove('has-voice-upload');
    return;
  }
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'voice-upload-control-badge';
    row.insertBefore(badge, row.firstChild);
  }
  badge.textContent = uploading ? '...' : (kind === 'video' ? 'VID' : (kind === 'audio' ? 'AUD' : 'FILE'));
  row.classList.add('has-voice-upload');
}

// =====================================================
// БЛОК ОЗВУЧКИ: currentVoiceListForPanel
// Возвращает список голосов для текущей AI-модели, чтобы карточка «Список голосов» работала в одном месте.
// =====================================================
function currentVoiceListForPanel() {
  if (isElevenLabsVoiceModel(voiceState.modelId)) return applyVoiceAvatarsToList(mergeUserVoicesWithProvider(elevenlabsVoiceList || ELEVENLABS_TTS_VOICES), 'elevenlabs');
  if (isRunwayVoiceModel(voiceState.modelId)) return applyVoiceAvatarsToList(runwayVoiceList || RUNWAY_TTS_VOICES, 'runway');
  return applyVoiceAvatarsToList(GEMINI_TTS_VOICES, 'gemini');
}

function voiceOptionDisplayLabel(id, fallback) {
  const value = String(id || '');
  const item = currentVoiceListForPanel().find((option) => String(option.id) === value);
  const label = item ? String(item.label || item.name || item.id || '') : '';
  return (label.split(' · ')[0] || value || fallback || '').trim();
}

function currentVoiceButtonLabel() {
  if (isElevenLabsVoiceModel(voiceState.modelId)) return voiceOptionDisplayLabel(voiceState.elevenlabsVoice, 'ElevenLabs Voice');
  if (isRunwayVoiceModel(voiceState.modelId)) return voiceOptionDisplayLabel(voiceState.runwayVoice, 'Maya');
  return voiceOptionDisplayLabel(voiceState.voice, 'Kore');
}

function voiceSettingsSummary() {
  const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
  const language = voiceState.targetLanguage || voiceState.elevenlabsTargetLanguage || voiceState.runwayTargetLanguage || 'en';
  const speakers = Math.max(1, Math.min(isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2, Number(voiceState.numSpeakers || 1)));
  if (isElevenLabsVoiceModel(voiceState.modelId) && (voiceState.elevenlabsTool || '') === 'dubbing') {
    return [purpose.label, language].filter(Boolean).join(' · ');
  }
  if (isRunwayVoiceModel(voiceState.modelId) && (voiceState.runwayTool || '') === 'voice_dubbing') {
    return [purpose.label, language].filter(Boolean).join(' · ');
  }
  return speakers > 1 ? (speakers + ' диктора') : 'Настройки';
}

// =====================================================
// БЛОК ОЗВУЧКИ: voiceGenderForPanel
// Определяет раздел списка голосов: мужской или женский.
// Если провайдер прислал gender, используем его; для встроенных голосов есть локальная карта.
// =====================================================
function voiceGenderForPanel(item) {
  const rawGender = String((item && (item.gender || item.sex || item.voice_gender)) || '').toLowerCase();
  if (/female|woman|жен|ж/i.test(rawGender)) return 'female';
  if (/male|man|муж|м/i.test(rawGender)) return 'male';
  const id = String((item && (item.id || item.voice_id || item.name)) || '').toLowerCase();
  const label = String((item && item.label) || '').toLowerCase();
  const text = id + ' ' + label;
  const femaleVoices = [
    'zephyr', 'leda', 'aoede', 'callirrhoe', 'autonoe', 'despina', 'erinome',
    'laomedeia', 'achernar', 'schedar', 'gacrux', 'pulcherrima', 'achird',
    'vindemiatrix', 'sadachbia', 'sulafat', 'maya', 'rachel'
  ];
  const maleVoices = [
    'puck', 'charon', 'kore', 'fenrir', 'orus', 'enceladus', 'iapetus',
    'umbriel', 'algieba', 'algenib', 'rasalgethi', 'alnilam',
    'zubenelgenubi', 'sadaltager', 'noah', 'bernard', 'arjun'
  ];
  if (femaleVoices.some((name) => text.includes(name))) return 'female';
  if (maleVoices.some((name) => text.includes(name))) return 'male';
  return 'neutral';
}

// =====================================================
// БЛОК ОЗВУЧКИ: closeVoiceList
// Закрывает нижний sheet списка голосов, не меняя выбранную модель и настройки озвучки.
// =====================================================
function closeVoiceList(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (activeVoicePanelSection === 'voices') {
    activeVoicePanelSection = '';
    renderVoiceToolPanel();
  }
}

// =====================================================
// БЛОК ОЗВУЧКИ: closeVoiceCreate
// Закрывает центрированный блок создания голоса.
// =====================================================
function closeVoiceCreate(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (activeVoicePanelSection === 'create') {
    activeVoicePanelSection = '';
    renderVoiceToolPanel();
  }
}

// =====================================================
// БЛОК ОЗВУЧКИ: closeVoicePanel
// Закрывает центрированные окна озвучки: создание голоса и загрузка.
// =====================================================
function closeVoicePanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (activeVoicePanelSection === 'create' || activeVoicePanelSection === 'upload') {
    activeVoicePanelSection = '';
    renderVoiceToolPanel();
  }
}

function toggleVoiceUploadDropdown(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const root = e && e.target && e.target.closest ? e.target.closest('.voice-upload-select-wrap') : null;
  document.querySelectorAll('.voice-upload-select-wrap.open').forEach((item) => {
    if (item !== root) item.classList.remove('open');
  });
  if (root) root.classList.toggle('open');
}

function selectVoiceUploadOption(e, kind, value) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (kind === 'model') {
    pickVoiceOption(e, 'model', value);
    activeVoicePanelSection = 'upload';
    renderVoiceToolPanel();
    return;
  }
  if (kind === 'purpose') {
    applyVoiceUploadPurpose(value);
    renderVoiceControls();
    activeVoicePanelSection = 'upload';
    renderVoiceToolPanel();
  }
}

// =====================================================
// БЛОК ОЗВУЧКИ: renderVoiceListPanel
// Рисует список голосов на базе того же визуального компонента, что и блок «Стили» в генерации фото.
// =====================================================
function renderVoiceListPanel() {
  injectImageStyleSheetCss();
  const activeSpeakerIndex = Number.isInteger(voiceState.activeSpeakerIndex) && voiceState.activeSpeakerIndex < voiceState.numSpeakers ? voiceState.activeSpeakerIndex : null;
  const optionKind = activeSpeakerIndex !== null ? 'voiceSpeaker' + (activeSpeakerIndex + 1) : (isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabsVoice' : (isRunwayVoiceModel(voiceState.modelId) ? 'runwayVoice' : 'voice'));
  const activeVoice = activeSpeakerIndex !== null ? voiceSpeakerVoiceValue(activeSpeakerIndex) : (optionKind === 'elevenlabsVoice' ? voiceState.elevenlabsVoice : (optionKind === 'runwayVoice' ? voiceState.runwayVoice : voiceState.voice));
  const usedByOtherSpeakers = new Set(Array.from({ length:Number(voiceState.numSpeakers || 1) }, (_, index) => index === activeSpeakerIndex ? '' : voiceSpeakerVoiceValue(index)).filter(Boolean).map(String));
  const items = currentVoiceListForPanel().filter((item) => activeSpeakerIndex === null || !usedByOtherSpeakers.has(String(item.id || item.voice_id || '')));
    const renderRow = (item) => {
    const id = String(item.id || item.voice_id || '');
    const label = String(item.label || item.name || id);
    const safeId = S.escapeHtml(id);
    const resourceId = S.escapeHtml(String(item.resourceId || item.resource_id || item.id || ''));
    const selected = String(activeVoice || '') === id;
    const initials = S.escapeHtml(voiceInitials(label || id));
    const description = voiceDescription(item);
    const marquee = label.length > 20;
    const avatarUrl = voiceAvatarUrlFor(item, isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini'));
    return '<div class="voice-style-row ' + (selected ? 'selected' : '') + '" role="button" tabindex="0" onclick="SYLVEX.pickVoiceOption(event,\'' + optionKind + '\',\'' + safeId + '\')">'
      + '<span class="voice-style-row-avatar ' + (avatarUrl ? '' : 'is-generated') + '" style="' + S.escapeHtml(voiceAvatarStyle(id || label)) + '">'
      + (avatarUrl ? '<img src="' + S.escapeHtml(avatarUrl) + '" alt="' + S.escapeHtml(label) + '" loading="lazy" decoding="async" />' : '<span class="voice-generated-initials">' + initials + '</span>')
      + '</span>'
      + '<span class="voice-style-row-copy"><span class="voice-style-row-name ' + (marquee ? 'is-marquee' : '') + '"><span>' + S.escapeHtml(label) + '</span>' + (marquee ? '<span aria-hidden="true">' + S.escapeHtml(label) + '</span>' : '') + '</span><small>' + S.escapeHtml(description) + '</small></span>'
      + (selected ? '<span class="voice-style-row-check">✓</span>' : '<span class="voice-style-row-check"></span>')
      + (item.custom ? '<button class="visual-delete-btn" type="button" aria-label="Удалить голос" onclick="SYLVEX.deleteUserVoice(event,\'' + resourceId + '\',\'' + safeId + '\')">×</button>' : '')
      + '<button class="voice-style-row-play" type="button" aria-label="Прослушать ' + S.escapeHtml(label) + '" onclick="SYLVEX.previewGeminiVoice(event,\'' + safeId + '\')">▶</button>'
      + '</div>';
  };
  return `
    <div class="image-style-panel-card voice-style-panel-card" onclick="event.stopPropagation()">
      <div class="image-style-panel-head">
        <div class="image-style-panel-title">${activeSpeakerIndex !== null ? 'Диктор ' + (activeSpeakerIndex + 1) + ' · голоса' : 'Список голосов'}</div>
        <button class="image-style-panel-close" type="button" onclick="SYLVEX.closeVoiceList(event)">×</button>
      </div>
      <div class="voice-style-rows">
        ${items.map(renderRow).join('')}
      </div>
    </div>`;
}

// =====================================================
// БЛОК ОЗВУЧКИ: renderVoiceCreatePanel
// Рисует экран создания голоса: название, запись/загрузка семпла, настройки речи и preview записи.
// =====================================================
function renderVoiceCreatePanel() {
  const cloneSubmitLabel = voiceCloneSubmitting ? 'Создаём...' : 'Создать голос';
  const isRecording = voiceCloneRecorder && voiceCloneRecorder.state === 'recording';
  const hasAudio = Boolean(voiceCloneBlob && voiceClonePreviewUrl);
  const canSubmit = Boolean((voiceCloneDraft.name || '').trim() && hasAudio && !voiceCloneSubmitting);
  const genderOptions = [
    { id: 'neutral', label: 'Нейтральный' },
    { id: 'male', label: 'Мужской' },
    { id: 'female', label: 'Женский' },
  ];
  const emotionOptions = [
    { id: 'neutral', label: 'Нейтральная' },
    { id: 'joy', label: 'Радость' },
    { id: 'calm', label: 'Спокойная' },
    { id: 'energy', label: 'Энергичная' },
  ];
  const dropdown = (kind, label, options, value) => {
    const selected = options.find((item) => item.id === value) || options[0];
    return `
      <div class="voice-select" data-voice-select="${S.escapeHtml(kind)}">
        <button class="voice-select-btn" type="button" onclick="SYLVEX.toggleVoiceCloneDropdown(event,'${S.escapeHtml(kind)}')">
          <span>${S.escapeHtml(label)}</span>
          <b>${S.escapeHtml(selected.label)}</b>
          <i>∨</i>
        </button>
        <div class="voice-select-menu">
          ${options.map((item) => '<button type="button" class="' + (item.id === selected.id ? 'active' : '') + '" onclick="SYLVEX.selectVoiceCloneOption(event,\'' + S.escapeHtml(kind) + '\',\'' + S.escapeHtml(item.id) + '\')">' + S.escapeHtml(item.label) + '</button>').join('')}
        </div>
      </div>`;
  };
  const settings = [
    { id: 'speed', label: 'Скорость', min: 0, max: 100 },
    { id: 'pitch', label: 'Высота', min: 0, max: 100 },
    { id: 'intonation', label: 'Интонация', min: 0, max: 100 },
    { id: 'expressiveness', label: 'Выразительность', min: 0, max: 100 },
  ];
  const formatTime = (seconds) => {
    const value = Math.max(0, Number(seconds || 0));
    const mm = Math.floor(value / 60);
    const ss = Math.floor(value % 60);
    return mm + ':' + String(ss).padStart(2, '0');
  };
  const audioLabel = voiceCloneDraft.source === 'upload' ? 'Аудиофайл загружен' : 'Запись создана';
  const audioInfo = voiceCloneBlob
    ? ((voiceCloneBlob.name || (voiceCloneDraft.source === 'upload' ? 'аудиофайл' : 'запись')) + ' · ' + Math.max(1, Math.round(voiceCloneBlob.size / 1024)) + ' КБ')
    : '';
  const waveform = Array.from({ length: 32 }).map((_, index) => {
    const level = 22 + ((index * 17) % 44) + (index % 5) * 3;
    return '<span style="height:' + Math.min(76, level) + '%"></span>';
  }).join('');
  return `
    <div class="voice-workspace-sheet voice-create-sheet" onclick="event.stopPropagation()">
      <button class="upload-panel-close voice-create-close" type="button" onclick="SYLVEX.closeVoiceCreate(event)">×</button>
      <div class="voice-create-head">
        <h3>Создай свой голос</h3>
        <p>Запишите голос или загрузите пример. После проверки создайте собственный голос для озвучки.</p>
      </div>
      <div class="voice-create-grid">
        <div class="voice-create-fields">
          <div class="voice-clone-profile-row">
            <button class="voice-clone-avatar-picker voice-style-row-avatar ${voiceCloneDraft.avatarUrl ? 'has-avatar' : 'is-generated'}" type="button" style="${S.escapeHtml(voiceAvatarStyle(voiceCloneDraft.name || 'Новый голос'))}" onclick="SYLVEX.openVoiceCloneAvatarPicker(event)" aria-label="Добавить аватарку">
              ${voiceCloneDraft.avatarUrl ? '<img src="' + S.escapeHtml(voiceCloneDraft.avatarUrl) + '" alt="Аватар голоса">' : '<span class="voice-generated-initials">＋</span>'}
            </button>
            <div class="voice-clone-main-fields">
              <input class="voice-tool-input voice-clone-field" id="voiceCloneNameInput" type="text" maxlength="80" placeholder="Название голоса" autocomplete="off" value="${S.escapeHtml(voiceCloneDraft.name || '')}" oninput="SYLVEX.setVoiceCloneField(event,'name',this.value)">
              ${dropdown('gender', 'Пол', genderOptions, voiceCloneDraft.gender || 'neutral')}
            </div>
          </div>
        </div>
        <div class="voice-create-recorder ${isRecording || voiceCloneCountdown ? 'recording-mode' : ''} ${hasAudio ? 'has-audio' : ''}">
          ${hasAudio ? `
            <div class="voice-audio-file-card">
              <span class="voice-file-icon">♪</span>
              <div><b>${S.escapeHtml(audioLabel)}</b><small>${S.escapeHtml(audioInfo)}</small></div>
              <button class="voice-trash-btn" type="button" aria-label="Удалить" onclick="SYLVEX.clearVoiceCloneRecording(event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M19 6l-1 15H6L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path></svg></button>
            </div>
          ` : `
            <button class="voice-rec-round ${isRecording ? 'recording' : ''}" type="button" aria-label="Запись голоса" onclick="SYLVEX.toggleVoiceCloneRecording(event)">${voiceCloneCountdown ? S.escapeHtml(String(voiceCloneCountdown)) : '●'}</button>
            <button class="voice-upload-round" type="button" aria-label="Добавить аудио" onclick="SYLVEX.openVoiceCloneFilePicker(event)">+</button>
            ${isRecording ? '<div class="voice-record-live"><span></span><span></span><span></span><span></span><b>' + S.escapeHtml(formatTime(voiceCloneRecordElapsed)) + '</b></div>' : ''}
          `}
        </div>
      </div>
      <div class="voice-speech-settings">
        <b>Настройка речи</b>
        ${settings.map((item) => `
          <label class="voice-param-row">
            <span>${S.escapeHtml(item.label)}</span>
            <input type="range" min="${item.min}" max="${item.max}" value="${Number(voiceCloneDraft[item.id] ?? 50)}" oninput="SYLVEX.setVoiceCloneSetting(event,'${item.id}',this.value)">
            <input class="voice-param-number" type="number" min="${item.min}" max="${item.max}" value="${Number(voiceCloneDraft[item.id] ?? 50)}" oninput="SYLVEX.setVoiceCloneSetting(event,'${item.id}',this.value)">
          </label>
        `).join('')}
        ${dropdown('emotion', 'Эмоция', emotionOptions, voiceCloneDraft.emotion || 'neutral')}
      </div>
      <div class="voice-preview-block">
        <b>Предосмотр</b>
        ${voiceClonePreviewUrl ? `
          <div class="voice-wave-player">
            <button type="button" onclick="SYLVEX.playVoiceCloneRecording(event)">${voiceClonePreviewPlaying ? 'Ⅱ' : '▶'}</button>
            <div class="voice-waveform">${waveform}</div>
            <time>${S.escapeHtml(formatTime(voiceClonePreviewTime))}</time>
            <time>${S.escapeHtml(formatTime(voiceClonePreviewDuration))}</time>
          </div>
        ` : '<div class="voice-preview-placeholder">Запись или аудиофайл появится здесь</div>'}
      </div>
      <div class="voice-create-footer">
        <button class="voice-create-submit" type="button" onclick="SYLVEX.sendVoiceCloneRecording(event)" ${canSubmit ? '' : 'disabled'}>${S.escapeHtml(cloneSubmitLabel)}</button>
      </div>
    </div>`;
}

// =====================================================
// БЛОК ОЗВУЧКИ: renderVoiceUploadPanel
// Рисует экран загрузки медиа для дубляжа, speech-to-speech и остальных инструментов ElevenLabs/Runway.
// =====================================================
function renderVoiceUploadPanel() {
  const uploads = Array.isArray(voiceState.uploads) ? voiceState.uploads : [];
  const activeUpload = uploads[0] || null;
  const uploading = voiceState.uploading || null;
  const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
  const currentModel = VOICE_MODEL_LIST.find((item) => item.id === voiceState.modelId) || VOICE_MODEL_LIST[0] || {};
  const supportedPurposes = VOICE_UPLOAD_PURPOSES.filter((item) => isVoicePurposeSupported(item, voiceState.modelId));
  const targetLanguage = voiceState.targetLanguage || voiceState.elevenlabsTargetLanguage || voiceState.runwayTargetLanguage || 'en';
  const language = RUNWAY_DUBBING_LANGUAGES.find((item) => item.id === targetLanguage) || RUNWAY_DUBBING_LANGUAGES.find((item) => item.id === 'en') || { id:'en', label:'English' };
  const speakerCount = Math.max(1, Math.min(isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2, Number(voiceState.numSpeakers || 1)));
  const speakerRows = purpose.speakers ? Array.from({ length: speakerCount }).map((_, index) => {
    const value = voiceSpeakerVoiceValue(index);
    return '<button class="voice-upload-speaker-btn" type="button" onclick="SYLVEX.openImageOptionMenu(event,\'voice_speaker_' + (index + 1) + '\')">'
      + '<span>Диктор ' + (index + 1) + '</span>'
      + '<b>' + S.escapeHtml(value) + '</b>'
      + '</button>';
  }).join('') : '';
  const languageControls = purpose.languages
    ? '<button class="voice-upload-chip" type="button" onclick="SYLVEX.openImageOptionMenu(event,\'voice_upload_language\')"><span>Язык</span><b>' + S.escapeHtml(language.label || language.id) + '</b></button>'
    : '<button class="voice-upload-chip disabled" type="button" disabled><span>Язык</span><b>Не требуется</b></button>';
  const speakerControls = purpose.speakers
    ? '<button class="voice-upload-chip" type="button" onclick="SYLVEX.openImageOptionMenu(event,\'voice_speaker_count\')"><span>Дикторы</span><b>' + speakerCount + '</b></button>'
    : '<button class="voice-upload-chip disabled" type="button" disabled><span>Дикторы</span><b>1</b></button>';
  const dropdown = (kind, label, selectedLabel, options) => `
    <div class="voice-upload-select-wrap">
      <button class="voice-upload-select-btn" type="button" onclick="SYLVEX.toggleVoiceUploadDropdown(event,'${S.escapeHtml(kind)}')">
        <span>${S.escapeHtml(label)}</span>
        <b>${S.escapeHtml(selectedLabel)}</b>
        <i>∨</i>
      </button>
      <div class="voice-upload-select-menu">
        ${options.map((item) => '<button type="button" class="' + (item.active ? 'active' : '') + '" onclick="SYLVEX.selectVoiceUploadOption(event,\'' + S.escapeHtml(kind) + '\',\'' + S.escapeHtml(item.id) + '\')"><b>' + S.escapeHtml(item.label) + '</b>' + (item.desc ? '<small>' + S.escapeHtml(item.desc) + '</small>' : '') + '</button>').join('')}
      </div>
    </div>`;
  const purposeOptions = supportedPurposes.map((item) => ({
    id: item.id,
    label: item.label,
    desc: item.hint || '',
    active: item.id === purpose.id,
  }));
  const canStart = !uploading && (!purpose.needsFile || uploads.length > 0);
  const previewUrl = S.escapeHtml((activeUpload && (activeUpload.previewUrl || voiceState.uploadPreviewUrl || activeUpload.url)) || (uploading && uploading.previewUrl) || '');
  const uploadKind = String((activeUpload && activeUpload.kind) || (uploading && uploading.kind) || '').toLowerCase();
  const uploadName = S.escapeHtml((activeUpload && activeUpload.name) || (uploading && uploading.name) || 'Файл выбран');
  const uploadSize = Number((activeUpload && activeUpload.size) || (uploading && uploading.size) || 0);
  const uploadSizeLabel = uploadSize ? (uploadSize >= 1024 * 1024 ? Math.round(uploadSize / 1024 / 1024) + ' MB' : Math.max(1, Math.round(uploadSize / 1024)) + ' KB') : '';
  const uploadPreview = uploading
    ? '<div class="voice-upload-preview loading"><div class="voice-upload-loader"></div><b>Загружаем файл</b><small>' + uploadName + (uploadSizeLabel ? ' · ' + S.escapeHtml(uploadSizeLabel) : '') + '</small></div>'
    : (activeUpload
        ? '<div class="voice-upload-preview ' + (uploadKind === 'video' ? 'is-video' : (uploadKind === 'file' ? 'is-file' : 'is-audio')) + '">'
          + (uploadKind === 'video'
            ? '<video src="' + previewUrl + '" controls playsinline preload="metadata"></video>'
            : (uploadKind === 'file'
              ? '<div class="voice-upload-audio-box"><span>▤</span><b>Документ готов к обработке</b></div>'
              : '<div class="voice-upload-audio-box"><span>♪</span><audio src="' + previewUrl + '" controls preload="metadata"></audio></div>'))
          + '<div class="voice-upload-preview-meta"><b>' + uploadName + '</b><small>' + S.escapeHtml([purpose.label, uploadSizeLabel].filter(Boolean).join(' · ')) + '</small></div>'
          + '<button class="voice-upload-replace" type="button" onclick="SYLVEX.openVoiceMediaPicker(event)">Заменить</button>'
          + '</div>'
        : '<button class="voice-upload-drop" type="button" onclick="SYLVEX.openVoiceMediaPicker(event)"><span>+</span><b>Выбрать файл</b><small>' + S.escapeHtml(purpose.needsFile ? 'Файл обязателен для выбранного режима' : 'Можно загрузить файл или использовать текст промпта') + '</small></button>');
  return `
    <div class="voice-workspace-sheet voice-upload-sheet" onclick="event.stopPropagation()">
      <button class="upload-panel-close voice-upload-close" type="button" onclick="SYLVEX.closeVoicePanel(event)">×</button>
      <div class="voice-upload-head">
        <div>
          <h3>Загрузить</h3>
          <p>Выберите, для чего нужен файл. Доступность режимов зависит от выбранной модели.</p>
        </div>
      </div>
      <div class="voice-upload-top-grid">
        ${dropdown('purpose', 'Тип загрузки', purpose.label, purposeOptions)}
      </div>
      <div class="voice-upload-controls voice-upload-controls-modern">
        ${languageControls}
        ${speakerControls}
      </div>
      ${speakerRows ? '<div class="voice-upload-speakers">' + speakerRows + '</div>' : ''}
      <div class="voice-upload-file-row">
        ${uploadPreview}
      </div>
      <div class="voice-upload-actions">
        <button class="voice-upload-primary" type="button" onclick="SYLVEX.confirmVoiceUpload(event)" ${canStart ? '' : 'disabled'}>Начать</button>
        <button class="voice-trash-btn voice-upload-clear" type="button" aria-label="Очистить" onclick="SYLVEX.clearVoiceUploads(event)" ${uploads.length && !uploading ? '' : 'disabled'}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M19 6l-1 15H6L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path></svg></button>
      </div>
      <div class="voice-upload-note">
        <b>${S.escapeHtml(purpose.label)}</b>
        <small>${S.escapeHtml(purpose.needsFile ? 'Файл обязателен для выбранного режима' : 'Можно загрузить файл или использовать текст промпта')}</small>
      </div>
    </div>`;
}

// =====================================================
// JAVASCRIPT-БЛОК: imageVisualReferenceOptions
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function imageVisualReferenceOptions() {
  const character = selectedImageCharacter();
  const object = selectedImageObject();

  return {
    characterId: character ? character.id : null,
    characterName: character ? character.name : '',
    characterPrompt: '',
    characterReferences: character ? visualGenerationReferences(character, 'character') : [],

    objectId: object ? object.id : null,
    objectName: object ? object.name : '',
    objectPrompt: object ? (object.prompt || '') : '',
    objectReferences: object ? visualGenerationReferences(object, 'object') : [],
  };
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderMusicControls
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderMusicControls() {
  ensureMusicSettings();
  const model = currentMusicModel();
  if (isMusicMode() && model) updateComposerModelDisplay(model);

  const genreVal = document.getElementById('musicGenreVal');
  if (genreVal) genreVal.textContent = musicOptionLabel(MUSIC_GENRES, musicState.genre, 'Auto');

  const durationVal = document.getElementById('musicDurationVal');
  if (durationVal) {
    const fixedDuration = Number(model && model.fixedDurationSeconds) || 0;
    const total = Number(musicState.duration || 0);
    durationVal.textContent = fixedDuration ? Math.floor(fixedDuration / 60) + ':' + String(fixedDuration % 60).padStart(2, '0') : (musicState.duration === 'auto' ? 'Auto' : Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0'));
  }
  const durationButton = document.getElementById('musicDurationButton');
  if (durationButton) {
    const supported = musicModelSupports('duration');
    durationButton.disabled = !supported;
    durationButton.classList.toggle('image-setting-disabled', !supported);
    durationButton.title = supported ? '' : ((model && model.fixedDurationSeconds) ? 'У этой модели фиксированная длительность 30 секунд' : 'Точная длительность не поддерживается выбранной моделью');
  }

  const settingsVal = document.getElementById('musicSettingsVal');
  if (settingsVal) {
    const selected = ['mood', 'tempo', 'theme', 'vocal']
      .map((key) => musicState.settings[key])
      .filter((value) => value && value !== 'auto').length;
    settingsVal.textContent = selected ? 'Настройки ' + selected : 'Настройки';
  }
}

function ensureMusicSettingsModal() {
  let modal = document.getElementById('musicSettingsModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'musicSettingsModal';
  modal.className = 'music-settings-modal';
  modal.onclick = (event) => {
    if (event.target === modal) closeMusicSettingsModal(event);
  };
  document.body.appendChild(modal);
  return modal;
}

function renderMusicSettingsModal() {
  const modal = ensureMusicSettingsModal();
  const draft = musicSettingsDraft || Object.assign({}, musicState.settings);
  modal.innerHTML = '<section class="music-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="musicSettingsTitle" onclick="event.stopPropagation()">'
    + '<button class="music-settings-close" type="button" aria-label="Закрыть" onclick="SYLVEX.closeMusicSettingsModal(event)">×</button>'
    + '<header><h3 id="musicSettingsTitle">Настройки музыки</h3><p>Выберите параметры для следующей генерации.</p></header>'
    + '<div class="music-settings-modal-body">'
    + Object.keys(MUSIC_SETTINGS).map((settingKey) => {
      const section = MUSIC_SETTINGS[settingKey];
      const active = draft[settingKey] || 'auto';
      const model = currentMusicModel();
      const items = settingKey === 'vocal' && model && Array.isArray(model.vocalModes)
        ? section.items.filter((item) => model.vocalModes.includes(String(item.id)))
        : section.items;
      return '<section class="music-modal-section"><h4>' + S.escapeHtml(section.title) + '</h4><div class="music-modal-options">'
        + items.map((item) => '<button class="music-modal-chip ' + (String(active) === String(item.id) ? 'active' : '') + '" type="button" onclick="SYLVEX.selectMusicSettingDraft(event,\'' + S.escapeHtml(settingKey) + '\',\'' + S.escapeHtml(String(item.id)) + '\')">' + S.escapeHtml(item.label || item.id) + '</button>').join('')
        + '</div></section>';
    }).join('')
    + '</div><footer><button class="music-settings-reset" type="button" onclick="SYLVEX.resetMusicSettingsDraft(event)">Сбросить</button><button class="music-settings-save" type="button" onclick="SYLVEX.saveMusicSettings(event)">Сохранить</button></footer>'
    + '</section>';
}

function openMusicSettingsModal(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  ensureMusicSettings();
  musicSettingsDraft = Object.assign({}, musicState.settings);
  const modal = ensureMusicSettingsModal();
  renderMusicSettingsModal();
  modal.classList.add('show');
  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

function closeMusicSettingsModal(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const modal = document.getElementById('musicSettingsModal');
  if (modal) modal.classList.remove('show');
  musicSettingsDraft = null;
}

function selectMusicSettingDraft(e, kind, value) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  if (!MUSIC_SETTINGS[kind]) return;
  if (!musicSettingsDraft) musicSettingsDraft = Object.assign({}, musicState.settings);
  musicSettingsDraft[kind] = value || 'auto';
  const modal = ensureMusicSettingsModal();
  const scrollArea = modal.querySelector('.music-settings-modal-body');
  const scrollTop = scrollArea ? scrollArea.scrollTop : 0;
  renderMusicSettingsModal();
  modal.classList.add('show');
  const updatedScrollArea = modal.querySelector('.music-settings-modal-body');
  if (updatedScrollArea) updatedScrollArea.scrollTop = scrollTop;
}

function resetMusicSettingsDraft(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  musicSettingsDraft = {};
  Object.keys(MUSIC_SETTINGS).forEach((key) => { musicSettingsDraft[key] = 'auto'; });
  renderMusicSettingsModal();
  ensureMusicSettingsModal().classList.add('show');
}

function openMusicDurationWheel(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  ensureMusicSettings();
  if (!musicModelSupports('duration')) {
    toast('Эта модель не поддерживает выбор точной длительности');
    return;
  }
  const model = currentMusicModel();
  const maxMinutes = Math.max(...((model && model.durations) || [1, 2, 3, 4]));
  musicDurationDraftSeconds = musicState.duration === 'auto' ? 0 : Math.min(maxMinutes * 60, Number(musicState.duration) || 0);
  const minutes = Math.floor(musicDurationDraftSeconds / 60);
  const seconds = musicDurationDraftSeconds % 60;
  const el = document.getElementById('modelPop');
  if (!el) return;
  if (el.parentElement !== document.body) document.body.appendChild(el);
  el.className = 'model-pop image-size-floating-pop music-duration-wheel-pop show';
  el.style.cssText = '';
  el.innerHTML = '<div class="music-duration-head"><b>Длительность</b><span id="musicDurationDraftLabel">' + (musicDurationDraftSeconds ? minutes + ':' + String(seconds).padStart(2, '0') : 'Auto') + '</span></div>'
    + '<div class="music-duration-wheel-labels"><span>Минуты</span><span>Секунды</span></div>'
    + '<div class="music-duration-wheels">'
    + '<div class="music-duration-wheel" data-duration-wheel="minutes">' + Array.from({ length:maxMinutes + 1 }, (_, value) => '<button type="button" data-duration-value="' + value + '" class="' + (value === minutes ? 'active' : '') + '" onclick="SYLVEX.setMusicDurationPart(event,\'minutes\',' + value + ')">' + value + '</button>').join('') + '</div>'
    + '<div class="music-duration-wheel" data-duration-wheel="seconds">' + Array.from({ length:60 }, (_, value) => '<button type="button" data-duration-value="' + value + '" class="' + (value === seconds ? 'active' : '') + '" onclick="SYLVEX.setMusicDurationPart(event,\'seconds\',' + value + ')">' + String(value).padStart(2, '0') + '</button>').join('') + '</div>'
    + '</div><p class="music-duration-hint">0:00 = Auto · максимум ' + maxMinutes + ':00 для ' + S.escapeHtml((model && model.label) || 'модели') + '</p>'
    + '<button class="music-duration-save" type="button" onclick="SYLVEX.saveMusicDuration(event)">Сохранить</button>';
  requestAnimationFrame(() => {
    el.querySelectorAll('.music-duration-wheel .active').forEach((button) => button.scrollIntoView({ block:'center' }));
    el.querySelectorAll('.music-duration-wheel').forEach((wheel) => {
      let timer = null;
      wheel.addEventListener('scroll', () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          const buttons = Array.from(wheel.querySelectorAll('button:not(:disabled)'));
          if (!buttons.length) return;
          const wheelRect = wheel.getBoundingClientRect();
          const center = wheelRect.top + wheelRect.height / 2;
          const nearest = buttons.reduce((best, button) => Math.abs(button.getBoundingClientRect().top + button.offsetHeight / 2 - center) < Math.abs(best.getBoundingClientRect().top + best.offsetHeight / 2 - center) ? button : best, buttons[0]);
          setMusicDurationPart(null, wheel.dataset.durationWheel, Number(nearest.dataset.durationValue));
        }, 90);
      }, { passive:true });
    });
  });
}

function setMusicDurationPart(e, part, value) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const model = currentMusicModel();
  const maxMinutes = Math.max(...((model && model.durations) || [1, 2, 3, 4]));
  let minutes = Math.floor(musicDurationDraftSeconds / 60);
  let seconds = musicDurationDraftSeconds % 60;
  if (part === 'minutes') minutes = Math.max(0, Math.min(maxMinutes, Number(value) || 0));
  if (part === 'seconds') seconds = Math.max(0, Math.min(59, Number(value) || 0));
  if (minutes === maxMinutes) seconds = 0;
  musicDurationDraftSeconds = Math.min(maxMinutes * 60, minutes * 60 + seconds);
  const el = document.getElementById('modelPop');
  if (!el) return;
  el.querySelectorAll('[data-duration-wheel="minutes"] button').forEach((button) => button.classList.toggle('active', Number(button.dataset.durationValue) === minutes));
  el.querySelectorAll('[data-duration-wheel="seconds"] button').forEach((button) => {
    const buttonValue = Number(button.dataset.durationValue);
    button.disabled = minutes === maxMinutes && buttonValue > 0;
    button.classList.toggle('active', buttonValue === seconds);
  });
  const label = document.getElementById('musicDurationDraftLabel');
  if (label) label.textContent = musicDurationDraftSeconds ? minutes + ':' + String(seconds).padStart(2, '0') : 'Auto';
}

function saveMusicDuration(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  musicState.duration = musicDurationDraftSeconds > 0 ? musicDurationDraftSeconds : 'auto';
  renderMusicControls();
  const el = document.getElementById('modelPop');
  if (el) { el.classList.remove('show', 'music-duration-wheel-pop'); el.style.cssText = ''; }
  S.haptic && S.haptic.select && S.haptic.select();
}

function saveMusicSettings(e) {
  if (e) { e.preventDefault(); e.stopPropagation(); }
  ensureMusicSettings();
  musicState.settings = Object.assign({}, musicState.settings, musicSettingsDraft || {});
  renderMusicControls();
  closeMusicSettingsModal();
  S.haptic && S.haptic.select && S.haptic.select();
}


const IMAGE_STYLE_SHEET_ITEMS = [
  { id:'auto', label:'Авто', image:'' },
  { id:'minimal_rainbow_gradient', label:'Minimal Rainbow Gradient', image:'assets/styles/minimal_rainbow_gradient.jpg' },
  { id:'acid_ink', label:'Acid Ink', image:'assets/styles/acid_ink.jpg' },
  { id:'illustrated_retro_futurism', label:'Illustrated Retro Futurism', image:'assets/styles/illustrated_retro_futurism.jpg' },
  { id:'indie_fisheye', label:'Indie Fisheye', image:'assets/styles/indie_fisheye.jpg' },
  { id:'radical_red', label:'Radical Red', image:'assets/styles/radical_red.jpg' },
  { id:'retro_futurism', label:'Retro Futurism', image:'assets/styles/retro_futurism.jpg' },
  { id:'ballpoint_blue', label:'Ballpoint Blue', image:'assets/styles/ballpoint_blue.jpg' },
  { id:'acid_swamp_cyan', label:'Acid Swamp Cyan', image:'assets/styles/acid_swamp_cyan.jpg' },
  { id:'rose_mint', label:'Rose Mint', image:'assets/styles/rose_mint.jpg' },
  { id:'retro_pop_graphic', label:'Retro Pop Graphic', image:'assets/styles/retro_pop_graphic.jpg' },
  { id:'retro_american_cartoon', label:'Retro American Cartoon', image:'assets/styles/retro_american_cartoon.jpg' },
  { id:'orange_dominion', label:'Orange Dominion', image:'assets/styles/orange_dominion.jpg' },
  { id:'neon_cutout', label:'Neon Cutout', image:'assets/styles/neon_cutout.jpg' },
  { id:'built_bricks', label:'Built Bricks', image:'assets/styles/built_bricks.jpg' },
  { id:'aegean_luxury', label:'Aegean', image:'assets/styles/aegean_luxury.jpg' },
  { id:'pastel_hologram', label:'Pastel Hologram', image:'assets/styles/pastel_hologram.jpg' },
  { id:'urban_ink', label:'Urban Ink', image:'assets/styles/urban_ink.jpg' },
  { id:'quiet_sepia', label:'Quiet Sepia', image:'assets/styles/quiet_sepia.jpg' },
  { id:'silent_cyan', label:'Silent Cyan', image:'assets/styles/silent_cyan.jpg' },
];

let styleSheetCssInjected = false;

  const IMAGE_MODEL_CATALOG = [
{ id:'seedream-5-0-260128', label:'Seedream 5.0', icon:'▥', description:'BytePlus Seedream 5.0 — фото-генерация высокого качества через ModelArk.' },
{ id:'seedream-4-5-251128', label:'Seedream 4.5', icon:'▥', description:'BytePlus Seedream 4.5 — улучшенная эстетика, детализация и точность изображения.' },
{ id:'seedream-4-0-250828', label:'Seedream 4.0', icon:'▥', description:'BytePlus Seedream 4.0 — генерация изображений и визуальных сцен через ModelArk.' },
{ id:'nano-banana-pro', label:'Nano Banana Pro', icon:'🍌', description:'Фотореалистичные изображения, идеально подходящие для рекламы и текста.' },
{ id:'nano-banana-2', label:'Nano Banana 2', icon:'🍌', description:'Современная генерация изображений с расширенным редактированием и композицией.' },
{ id:'nano-banana-2-lite', label:'Nano Banana 2 Lite', icon:'🍌', description:'Быстрая и экономичная генерация изображений через Gemini 3.1 Flash Lite Image.' },
{ id:'nano-banana', label:'Nano Banana', icon:'🍌', description:'Потрясающие фотореалистичные изображения для любой идеи.' },
{ id:'imagen-4-fast', label:'Imagen 4 Fast', icon:'G', description:'Быстрая генерация изображений через Google Imagen 4.' },
{ id:'imagen-4-standard', label:'Imagen 4 Standard', icon:'G', description:'Стандартная генерация изображений через Google Imagen 4.' },
{ id:'imagen-4-ultra', label:'Imagen 4 Ultra', icon:'G', description:'Максимальное качество генерации изображений через Google Imagen 4.' },
{ id:'gpt-image-2', label:'GPT Image 2', icon:'◎', description:'Современная генерация изображений с реализмом, типографикой и контролем.' },
{ id:'grok-pro', label:'Grok Pro', icon:'◒', description:'xAI Grok — генерация высококачественных изображений.' },
{ id:'grok', label:'Grok', icon:'◒', description:'Генерация изображений через модель Grok.' },
{ id:'flux-2', label:'Flux 2', icon:'△', description:'Быстрая генерация изображений в стиле Flux.' },
{ id:'flux-2-turbo', label:'Flux 2 Turbo', icon:'△', description:'Быстрая бюджетная генерация изображений.' },
{ id:'ideogram-3', label:'Ideogram 3.0', icon:'♨', description:'Генерация изображений с хорошей работой с текстом и постерами.' },
{ id:'ideogram-4', label:'Ideogram 4.0', icon:'♨', description:'Новая версия Ideogram для точного текста и визуальных композиций.' },
{ id:'recraft-v4-1', label:'Recraft V4.1', icon:'R', description:'Дизайн, иллюстрации, графика и брендовые изображения.' },
{ id:'recraft-v3', label:'Recraft V3', icon:'R', description:'Генерация графики, иллюстраций и рекламных визуалов.' },
{ id:'recraft-v4-1-pro', label:'Recraft V4.1 Pro', icon:'R', description:'Профессиональная версия Recraft для точной визуальной генерации.' },
{ id:'gpt-image-1', label:'GPT Image 1', icon:'◎', description:'Генерация и редактирование изображений через OpenAI.' },
{ id:'flux-pro-kontext', label:'FLUX Pro Text', icon:'△', description:'Модель FLUX для генерации изображений по текстовому описанию.' },
{ id:'qwen-image', label:'Qwen Image', icon:'Q', description:'Генерация изображений через Qwen Image.' },
{ id:'qwen-image-2-pro', label:'Qwen Image 2 Pro', icon:'Q', description:'Профессиональная версия Qwen Image для качественной генерации.' },
{ id:'qwen-image-2', label:'Qwen Image 2', icon:'Q', description:'Новая версия Qwen Image для генерации изображений.' },
{ id:'microsoft-mai-2-5', label:'Microsoft MAI Image 2.5', icon:'▦', description:'Модель Microsoft MAI для создания изображений.' },
{ id:'krea-2', label:'Krea 2', icon:'✤', description:'Генерация креативных визуалов и изображений.' }
  ];

const MODEL_ICON_SVG = {
  nn: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.1 15.7C10.8 16.5 16.2 12 17.1 6.1C17.3 4.8 19.2 5 19.3 6.3C19.9 14.2 13.1 20.8 5.5 18.1C4.2 17.6 3.8 15.5 5.1 15.7Z" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/><path d="M5.2 15.7C7.2 15.3 8.9 14.3 10.2 12.8" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M17 6.4L15.3 4.4" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M5.4 18L3.8 19.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',

  chatgptImage: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2.8C13.5 2.8 14.7 3.7 15.3 5L16.2 4.8C18.1 4.5 19.8 5.9 20 7.8C20.1 8.8 19.8 9.7 19.2 10.4C20.4 11.2 20.9 12.8 20.4 14.2C19.9 15.7 18.5 16.6 17 16.5C16.7 18.4 15.1 19.8 13.2 19.8C12.3 19.8 11.5 19.5 10.8 18.9C9.8 20.1 8.1 20.5 6.7 19.8C5.3 19.1 4.6 17.6 4.9 16.1C3.4 15.7 2.4 14.3 2.4 12.8C2.4 11.6 3 10.6 3.9 10C3.4 8.7 3.8 7.2 4.9 6.3C6 5.4 7.5 5.3 8.7 6C9.2 4.2 10.4 2.8 12 2.8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8.7 6L13.8 8.9V14.9L8.8 17.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M15.3 5L10.2 7.9V13.9L15.2 16.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.9 10L9 12.9L13.8 10.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M20.1 10.4L15 13.2L10.2 10.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',

  cdrm: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 6V18" stroke="currentColor" stroke-width="3" stroke-linecap="butt"/><path d="M9.2 10V18" stroke="currentColor" stroke-width="3" stroke-linecap="butt"/><path d="M14.4 13V18" stroke="currentColor" stroke-width="3" stroke-linecap="butt"/><path d="M19.6 7V18" stroke="currentColor" stroke-width="3" stroke-linecap="butt"/><path d="M4 18H6.3M9.2 18H11.5M14.4 18H16.7M19.6 18H21.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',

  grokPro: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 17.6C3.9 14.6 4.5 11 7 8.4C9.9 5.4 14.6 5 18 7.4" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M19.3 5.2L4.7 19.8" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><path d="M19.2 10.3C20.3 13.3 19.6 16.8 17.1 19.2C14.7 21.4 11.3 21.8 8.6 20.5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',

  grokFlux: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.2 18.5L11.6 4.8L20.8 18.5H3.2Z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M7.9 18.5L11.7 12.1L15.8 18.5" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M18.3 5.2L19 6.8L20.6 7.5L19 8.2L18.3 9.8L17.6 8.2L16 7.5L17.6 6.8L18.3 5.2Z" fill="currentColor"/></svg>',

  idrm: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10.5 4.2C7.9 4.7 6 6.8 6 9.4V10.2H4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10.5 19.8C7.9 19.3 6 17.2 6 14.6V13.8H4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12.5 4.2C15.9 4.2 18.5 6.8 18.5 10.1C20 10.5 21 11.9 21 13.5C21 15.5 19.5 17.1 17.5 17.1H16.8C16.1 18.7 14.6 19.8 12.5 19.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M2.8 7.5H6.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M2.8 12H8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M2.8 16.5H6.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 7.2V16.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15 8.4V15.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',

  craft: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 20V4H12.3C15.8 4 18.1 6 18.1 9.1C18.1 11.5 16.8 13.2 14.7 13.9L19.2 20H15.1L11.2 14.4H8.5V20H5Z" fill="currentColor"/><path d="M8.5 11.5H12C13.5 11.5 14.4 10.6 14.4 9.3C14.4 8 13.5 7.2 12 7.2H8.5V11.5Z" fill="#1a1a1a"/></svg>',

  queen: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2.8L14.5 7.2L19.6 7.1L17.1 11.5L19.7 15.8L14.6 15.9L12 20.3L9.4 15.9L4.3 15.8L6.9 11.5L4.4 7.1L9.5 7.2L12 2.8Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M7 8.3L17 15.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M17 8.3L7 15.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',

  microsoft: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="3" width="8" height="8" fill="currentColor"/><rect x="13" y="3" width="8" height="8" fill="currentColor"/><rect x="3" y="13" width="8" height="8" fill="currentColor"/><rect x="13" y="13" width="8" height="8" fill="currentColor"/></svg>'
};

 // =====================================================
 // JAVASCRIPT-БЛОК: withImageDefaults
 // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
 // =====================================================
 function withImageDefaults(model) {
  const base = Object.assign({
    sizes: [
      { id:'1:1', label:'1:1', ratio:'1:1', icon:'1:1' },
      { id:'9:16', label:'9:16', ratio:'9:16', icon:'9:16' },
      { id:'16:9', label:'16:9', ratio:'16:9', icon:'16:9' }
    ],
    counts: [1, 2, 3, 4],
    styles: [{ id:'auto', label:'Авто' }],
    characters: [{ id:'auto', label:'Авто' }]
  }, model);

  const requiredStyles = [
    { id:'auto', label:'Авто' },
    { id:'aegean_luxury', label:'Aegean' }
  ];

  const styleMap = new Map();

  (base.styles || []).forEach((item) => {
    styleMap.set(String(item.id), item);
  });

  requiredStyles.forEach((item) => {
    styleMap.set(
      String(item.id),
      Object.assign({}, styleMap.get(String(item.id)) || {}, item)
    );
  });

  base.styles = Array.from(styleMap.values());

  return base;
}

  // =====================================================
  // JAVASCRIPT-БЛОК: mergeImageModels
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function mergeImageModels(apiModels) {
    const map = new Map();
    IMAGE_MODEL_CATALOG.map(withImageDefaults).forEach((model) => map.set(model.id, model));
    (apiModels || []).map(withImageDefaults).forEach((model) => {
      const old = map.get(model.id) || {};
      map.set(model.id, Object.assign({}, old, model));
    });

    // Список моделей не фильтруем: GPT Image остаётся в выборе как отдельная модель.
    // Отключение старого OpenAI делается не удалением моделей, а через router/backend.
    return Array.from(map.values());
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: getTelegramId
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      return u && u.id ? Number(u.id) : Number(S.user && S.user.telegram_id ? S.user.telegram_id : 0);
    } catch { return 0; }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: pickStudioModel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickStudioModel() {
    if (isImageMode()) {
      return imageState.modelId || (IMAGE_MODEL_LIST[0] && IMAGE_MODEL_LIST[0].id) || 'ideogram_3_0';
    }
    if (isVideoMode()) {
      return videoState.modelId || 'seedance_2_fast';
    }
    if (studioMode === 'music') return musicState.modelId || 'suno_chirp_5';
    if (studioMode === 'voice') return voiceState.modelId || 'elevenlabs_eleven_v3';
    return textState.modelId || 'gpt-5.5';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: providerHintForModel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function providerHintForModel(model) {
    if (/seedream|seedance/i.test(model)) return 'bytedance';
    if (/byteplus|seed[_-]?2|ark/i.test(model)) return 'byteplus';
    if (/^gpt[_-]?image|openai/i.test(model)) return 'openai';
    if (/sora/i.test(model)) return 'sora';
    if (/grok/i.test(model)) return 'xai';
    if (/nano[_-]?banana|imagen|gemini|lyria/i.test(model)) return 'google';
    if (/flux/i.test(model)) return 'flux';
    if (/ideogram/i.test(model)) return 'ideogram';
    if (/recraft/i.test(model)) return 'recraft';
    if (/qwen/i.test(model)) return 'qwen';
    if (/microsoft|mai/i.test(model)) return 'microsoft';
    if (/krea/i.test(model)) return 'krea';
    if (/gemini.*tts|tts.*gemini|flash_tts|preview_tts/i.test(model)) return 'gemini';
    if (/suno|chirp/i.test(model)) return 'suno';
    if (/minimax.*music|music.*minimax/i.test(model)) return 'minimax';
    if (/musicgen/i.test(model)) return 'music';
    if (/voice/i.test(model)) return 'voice';
    if (/^gpt-|^o[0-9]|chatgpt/i.test(model)) return 'openai';
    return 'sylvex-router';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: pickProviderHint
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickProviderHint() {
    return providerHintForModel(pickStudioModel());
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: uiLang
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function uiLang() {
    return (localStorage.getItem('sylvex-lang') || 'en').slice(0, 2);
  }

// =====================================================
// JAVASCRIPT-БЛОК: localizedGreeting
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function localizedGreeting() {
  return '';
}

  // =====================================================
  // ЧАТ И ИСТОРИЯ: chatTypeForMode
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function chatTypeForMode(mode) {
    if (mode === 'edit' || mode === 'motion') return 'video';
    if (CHAT_SPACE_TYPES.includes(mode)) return mode;
    if (isImageMode()) return 'image';
    if (isVideoMode()) return 'video';
    if (isMusicMode()) return 'music';
    if (isVoiceMode()) return 'voice';
    return 'video';
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: currentChatType
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function currentChatType() {
    return chatTypeForMode(studioMode);
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: chatStorageKey
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function chatStorageKey(type) {
    return 'sylvex-prostudio-chat-' + (getTelegramId() || 'anon') + '-' + chatTypeForMode(type);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: lastModeStorageKey
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function lastModeStorageKey() {
    return 'sylvex-prostudio-last-mode-' + (getTelegramId() || 'anon');
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: rememberCurrentChatSpace
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function rememberCurrentChatSpace() {
    const type = currentChatType();
    if (!chatSpaces[type]) return;
    chatSpaces[type].activeChatId = currentConvId || null;
    chatSpaces[type].conversationId = currentConvId || null;
    chatSpaces[type].messages = (chatMessages || []).slice();
    try {
      localStorage.setItem(chatStorageKey(type), JSON.stringify(chatSpaces[type]));
      localStorage.setItem(lastModeStorageKey(), type);
    } catch {}
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: loadStoredChatSpace
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function loadStoredChatSpace(type) {
    const normalized = chatTypeForMode(type);
    try {
      const raw = localStorage.getItem(chatStorageKey(normalized));
      if (!raw) return;
      const stored = JSON.parse(raw);
      if (!stored || typeof stored !== 'object') return;
      chatSpaces[normalized].activeChatId = stored.activeChatId || stored.conversationId || null;
      chatSpaces[normalized].conversationId = stored.conversationId || null;
      chatSpaces[normalized].messages = Array.isArray(stored.messages) ? stored.messages : [];
    } catch {}
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: latestConversationForType
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function latestConversationForType(type) {
    const normalized = chatTypeForMode(type);
    return ((chatCollections && chatCollections[normalized]) || []).find(Boolean) || null;
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: syncChatCollections
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function syncChatCollections(conversations) {
    CHAT_SPACE_TYPES.forEach((type) => {
      chatCollections[type] = [];
    });
    (conversations || []).forEach((conversation) => {
      const type = chatTypeForMode(conversation.type || conversation.mode || conversation.category || 'image');
      if (chatCollections[type]) chatCollections[type].push(conversation);
    });
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: restoreChatSpace
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function restoreChatSpace(type) {
    const normalized = activeGenerationLocked() && activeGeneration.mode
      ? activeGeneration.mode
      : chatTypeForMode(type);
    if (!chatSpaces[normalized]) return;
    loadStoredChatSpace(normalized);
    currentConvId = chatSpaces[normalized].activeChatId || chatSpaces[normalized].conversationId || null;
    chatMessages = (chatSpaces[normalized].messages || []).slice();
    if (activeGenerationLocked()) ensureActiveGenerationPlaceholder(false);
    renderChat();
    renderConvList();
    updateSendButton();
    if (currentConvId && !chatMessages.length) {
      openConv(currentConvId, normalized, { silent: true });
    } else if (!currentConvId && !chatMessages.length) {
      const latest = latestConversationForType(normalized);
      if (latest && latest.id) openConv(latest.id, normalized, { silent: true });
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: savedInitialStudioMode
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function savedInitialStudioMode() {
    if (activeGenerationLocked() && activeGeneration.mode) return activeGeneration.mode;
    try {
      const saved = localStorage.getItem(lastModeStorageKey());
      return CHAT_SPACE_TYPES.includes(saved) ? saved : '';
    } catch {
      return '';
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: loadProStudioSync
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function loadProStudioSync() {
    const tg = getTelegramId();
    if (!tg) return;
    try {
      const res = await fetch('/api/public/prostudio/sync?telegram_id=' + encodeURIComponent(tg) + '&limit=120', { cache: 'no-store' });
      const data = await res.json();
      if (!data || !data.ok) return;
      const resources = data.resources || {};
      serverVisualItems.characters = Array.isArray(resources.characters) ? resources.characters : [];
      serverVisualItems.objects = Array.isArray(resources.objects) ? resources.objects : [];
      serverVisualItems.voices = Array.isArray(resources.voices) ? resources.voices : [];
      serverDrafts = data.drafts || {};
      conversationsCache = Array.isArray(data.conversations) ? data.conversations : conversationsCache;
      syncChatCollections(conversationsCache);
      restoreActiveGenerationJobs(Array.isArray(data.generation_jobs) ? data.generation_jobs : []);
      applyCurrentDraft();
      renderImageControls();
      renderConvList();
    } catch (err) {
      console.warn('[SYLVEX] prostudio sync failed', err);
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: isActiveGenerationStatus
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function isActiveGenerationStatus(status) {
    return ['queued', 'submitted', 'running', 'processing', 'provider_processing', 'waiting', 'pending'].includes(String(status || '').toLowerCase());
  }

  function activeGenerationButtonLabel(status) {
    return ['submitting', 'queued'].includes(String(status || '').toLowerCase()) ? 'В очереди' : 'Генерация…';
  }

  function activeGenerationStorageKey() {
    return 'sylvex-prostudio-active-generation-' + (getTelegramId() || 'anon');
  }

  function activeGenerationLocked() {
    return !!activeGeneration.locked;
  }

  function persistActiveGeneration() {
    try {
      if (!activeGeneration.locked) localStorage.removeItem(activeGenerationStorageKey());
      else localStorage.setItem(activeGenerationStorageKey(), JSON.stringify({
        status: activeGeneration.status,
        mode: activeGeneration.mode,
        jobId: activeGeneration.jobId,
        model: activeGeneration.model,
        startedAt: activeGeneration.startedAt,
      }));
    } catch {}
  }

  function activeGenerationPlaceholderIndex() {
    if (!activeGeneration.loadingToken) return -1;
    return chatMessages.findIndex((message) => message && message.activeGenerationToken === activeGeneration.loadingToken);
  }

  function adoptActiveGenerationPlaceholder(index) {
    const message = chatMessages[index];
    if (!message || !message.generationLoading) return -1;
    if (!activeGeneration.loadingToken) activeGeneration.loadingToken = 'active_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    message.activeGenerationToken = activeGeneration.loadingToken;
    message.generationStatus = activeGeneration.status;
    if (message.progress) message.progress.message = activeGenerationButtonLabel(activeGeneration.status);
    activeGeneration.placeholderMessage = message;
    return index;
  }

  function patchActiveGenerationDom() {
    const token = activeGeneration.loadingToken;
    if (!token) return;
    const node = document.querySelector('.generation-loading-msg[data-generation-token="' + token + '"]');
    if (!node) return;
    const title = node.querySelector('.generation-loading-title');
    if (title) title.textContent = activeGenerationButtonLabel(activeGeneration.status);
    const progress = activeGeneration.placeholderMessage && activeGeneration.placeholderMessage.progress;
    if (progress) {
      const updated = nextGenerationProgress(progress, false);
      activeGeneration.placeholderMessage.progress = updated;
      const percent = Math.max(0, Math.min(92, Number(updated.percent || 0)));
      const bar = node.querySelector('.generation-loading-progress span');
      const percentNode = node.querySelector('.generation-loading-percent');
      if (bar) bar.style.width = percent + '%';
      if (percentNode) percentNode.textContent = percent + '%';
    }
  }

  function syncActiveGenerationProgressTimer() {
    if (!activeGeneration.locked) {
      if (activeGeneration.progressTimer) clearInterval(activeGeneration.progressTimer);
      activeGeneration.progressTimer = null;
      return;
    }
    if (activeGeneration.progressTimer) return;
    activeGeneration.progressTimer = setInterval(patchActiveGenerationDom, 2200);
  }

  function ensureActiveGenerationPlaceholder(renderNow) {
    if (!activeGeneration.locked) return -1;
    let index = activeGenerationPlaceholderIndex();
    if (index < 0) {
      if (!activeGeneration.loadingToken) activeGeneration.loadingToken = 'active_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
      const message = activeGeneration.placeholderMessage || {
        role: 'ai',
        generationLoading: true,
        activeGenerationToken: activeGeneration.loadingToken,
        generationStatus: activeGeneration.status,
        progress: createGenerationProgress(generationKindForCurrentMode()),
      };
      message.activeGenerationToken = activeGeneration.loadingToken;
      message.generationLoading = true;
      message.generationStatus = activeGeneration.status;
      if (message.progress) message.progress.message = activeGenerationButtonLabel(activeGeneration.status);
      activeGeneration.placeholderMessage = message;
      index = chatMessages.push(message) - 1;
    }
    if (renderNow) renderChat();
    return index;
  }

  function transitionActiveGeneration(action, data) {
    const payload = data || {};
    if (action === 'begin') {
      if (activeGeneration.locked) return false;
      activeGeneration.locked = true;
      activeGeneration.status = 'submitting';
      activeGeneration.mode = chatTypeForMode(payload.mode || currentChatType());
      activeGeneration.jobId = '';
      activeGeneration.model = payload.model || pickStudioModel();
      activeGeneration.startedAt = Number(payload.startedAt || Date.now());
      activeGeneration.requestId = payload.requestId || ('local_' + Date.now().toString(36));
      activeGeneration.loadingToken = '';
      activeGeneration.placeholderMessage = null;
      activeGeneration.historyPreview = false;
    } else if (action === 'restore' || action === 'job' || action === 'status') {
      const incomingJobId = String(payload.id || payload.job_id || payload.jobId || '');
      if (activeGeneration.jobId && incomingJobId && activeGeneration.jobId !== incomingJobId) return false;
      activeGeneration.locked = true;
      if (payload.status) activeGeneration.status = String(payload.status);
      if (incomingJobId) activeGeneration.jobId = incomingJobId;
      if (!activeGeneration.mode && payload.mode) activeGeneration.mode = chatTypeForMode(payload.mode);
      if (!activeGeneration.model && payload.model) activeGeneration.model = payload.model;
      if (!activeGeneration.startedAt) activeGeneration.startedAt = Number(payload.startedAt || Date.now());
      if (!activeGeneration.requestId) activeGeneration.requestId = incomingJobId || ('restore_' + Date.now().toString(36));
    } else if (action === 'reset') {
      if (activeGeneration.progressTimer) clearInterval(activeGeneration.progressTimer);
      Object.assign(activeGeneration, {
        locked:false, status:'', mode:'', jobId:'', model:'', startedAt:0,
        requestId:'', loadingToken:'', placeholderMessage:null, progressTimer:null,
        restoringMode:false, historyPreview:false,
      });
    }

    document.body.classList.toggle('prostudio-job-locked', activeGeneration.locked);
    const composer = document.getElementById('studioComposer');
    const input = document.getElementById('chatInput');
    if (composer) composer.setAttribute('aria-busy', activeGeneration.locked ? 'true' : 'false');
    if (input) {
      input.readOnly = activeGeneration.locked;
      input.setAttribute('aria-disabled', activeGeneration.locked ? 'true' : 'false');
    }
    document.querySelectorAll('#studioComposer button, #studioComposer input, #studioComposer select').forEach((element) => {
      element.setAttribute('aria-disabled', activeGeneration.locked ? 'true' : 'false');
    });
    persistActiveGeneration();
    syncActiveGenerationProgressTimer();
    if (activeGeneration.placeholderMessage) {
      activeGeneration.placeholderMessage.generationStatus = activeGeneration.status;
      if (activeGeneration.placeholderMessage.progress) {
        activeGeneration.placeholderMessage.progress.message = activeGenerationButtonLabel(activeGeneration.status);
      }
    }
    updateSendButton();
    patchActiveGenerationDom();
    return true;
  }

  function applyActiveProStudioJob(job) {
    return transitionActiveGeneration(activeGeneration.locked ? 'status' : 'restore', job || {});
  }

  function clearActiveProStudioJob(jobId) {
    if (jobId && activeGeneration.jobId && activeGeneration.jobId !== jobId) return;
    transitionActiveGeneration('reset');
  }

  function restoreLocalActiveGeneration() {
    try {
      const snapshot = JSON.parse(localStorage.getItem(activeGenerationStorageKey()) || '{}');
      if (!snapshot || !snapshot.mode || !snapshot.status) return;
      if (!isActiveGenerationStatus(snapshot.status) && snapshot.status !== 'submitting') return;
      transitionActiveGeneration('restore', snapshot);
    } catch {}
  }

  async function restoreActiveProStudioJob() {
    const telegramId = getTelegramId();
    if (!telegramId) return;
    try {
      const response = await fetch('/api/public/prostudio/active-job?telegram_id=' + encodeURIComponent(telegramId), { cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) return;
      if (data.active && data.job) {
        applyActiveProStudioJob(data.job);
        if (activeGeneration.mode && currentChatType() !== activeGeneration.mode) {
          activeGeneration.restoringMode = true;
          updateComposerMode(activeGeneration.mode);
          activeGeneration.restoringMode = false;
        }
        ensureActiveGenerationPlaceholder(true);
        rememberCurrentChatSpace();
        watchGenerationJob(data.active_job_id || data.job.id, data.job);
      } else if (activeGeneration.locked) {
        clearActiveProStudioJob(activeGeneration.jobId);
      }
    } catch (error) {
      console.warn('[SYLVEX] active generation restore failed', error);
    }
  }

  // =====================================================
  // ОЖИДАНИЕ JOB: restoreActiveGenerationJobs
  // Опрашивает backend до финального статуса и обновляет карточку генерации в чате.
  // =====================================================
  function restoreActiveGenerationJobs(jobs) {
    const activeJob = (jobs || []).find((job) => job && job.id && isActiveGenerationStatus(job.status));
    if (!activeJob) return;
    applyActiveProStudioJob(activeJob);
    watchGenerationJob(activeJob.id, activeJob);
  }

  // =====================================================
  // ОЖИДАНИЕ JOB: watchGenerationJob
  // Опрашивает backend до финального статуса и обновляет карточку генерации в чате.
  // =====================================================
  function watchGenerationJob(jobId, jobInfo) {
    if (!jobId || activeGenerationWatchers.has(jobId)) return;
    applyActiveProStudioJob(Object.assign({}, jobInfo || {}, { id: jobId, status: (jobInfo && jobInfo.status) || 'queued' }));
    activeGenerationWatchers.add(jobId);
    waitGeneration(jobId)
      .then((result) => {
        activeGenerationWatchers.delete(jobId);
        renderRestoredActiveGenerationResult(result, jobInfo || {});
        loadConversations();
      })
      .catch((err) => {
        activeGenerationWatchers.delete(jobId);
        console.warn('[SYLVEX] generation watcher failed', jobId, err);
        if (err && err.terminalStatus) {
          const index = activeGenerationPlaceholderIndex();
          if (index >= 0) {
            chatMessages[index] = {
              role: 'ai',
              text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.'),
            };
          }
          renderChat();
          rememberCurrentChatSpace();
          clearActiveProStudioJob(jobId);
        }
      });
  }

  function renderRestoredActiveGenerationResult(result, jobInfo) {
    const data = result || {};
    const mode = chatTypeForMode(activeGeneration.mode || jobInfo.mode || data.type || currentChatType());
    activeGeneration.restoringMode = true;
    if (currentChatType() !== mode) updateComposerMode(mode);
    activeGeneration.restoringMode = false;
    restoreChatSpace(mode);
    let index = activeGenerationPlaceholderIndex();
    if (index < 0) index = ensureActiveGenerationPlaceholder(false);
    const prompt = jobInfo.prompt || data.prompt || '';
    const backendType = String(data.type || '').toLowerCase();
    const type = backendType === 'video' || data.video_url || (Array.isArray(data.videos) && data.videos.length)
      ? 'video'
      : (mode === 'image' ? 'image' : (mode === 'music' ? 'music' : (mode === 'voice' ? 'voice' : 'file')));
    if (type === 'image') {
      const images = generatedUrlsFromResponse(data, 'image');
      const thumbs = generatedThumbsFromResponse(data);
      if (images.length) addGeneratedImages(images, thumbs);
      chatMessages[index] = {
        role: 'ai',
        imageResultMini: true,
        metadata: imageGenerationMetadata(prompt, [], data, null),
      };
    } else if (mode === 'text' && data.text) {
      chatMessages[index] = {
        role: 'ai',
        text: data.text,
        files: Array.isArray(data.files) ? data.files : (data.file_url ? [data.file_url] : []),
      };
    } else {
      const urls = generatedUrlsFromResponse(data, type === 'video' ? 'video' : 'audio');
      chatMessages[index] = urls.length
        ? {
            role: 'ai',
            imageResultMini: true,
            metadata: generationResultMetadata(type, prompt, data, [], null),
          }
        : {
            role: 'ai',
            text: data.sent_to_telegram
              ? 'Готово ✅\nРезультат отправлен в Telegram-чат.'
              : 'Готово ✅\nГенерация завершена.',
          };
    }
    renderChat();
    rememberCurrentChatSpace();
    clearActiveProStudioJob(activeGeneration.jobId);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: applyCurrentDraft
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyCurrentDraft() {
    if (activeGenerationLocked()) return;
    const ta = document.getElementById('chatInput');
    if (!ta) return;
    const type = currentChatType();
    const draft = serverDrafts && serverDrafts[type] ? serverDrafts[type] : null;
    if (!draft || !draft.draft_text || (ta.value || '').trim()) return;
    restoringDraft = true;
    ta.value = draft.draft_text || '';
    autoGrow(ta);
    restoringDraft = false;
    updateSendButton();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: saveCurrentDraftSoon
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function saveCurrentDraftSoon() {
    if (restoringDraft) return;
    const tg = getTelegramId();
    const ta = document.getElementById('chatInput');
    if (!tg || !ta) return;
    const type = currentChatType();
    const text = ta.value || '';
    serverDrafts[type] = Object.assign({}, serverDrafts[type] || {}, {
      mode: type,
      conversation_id: currentConvId || '',
      draft_text: text,
      updated_at: new Date().toISOString(),
    });
    if (draftSaveTimer) clearTimeout(draftSaveTimer);
    draftSaveTimer = setTimeout(() => {
      fetch('/api/public/prostudio/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telegram_id: tg,
          mode: type,
          conversation_id: currentConvId || '',
          draft_text: text,
          attachment: currentModeAttachment() || {},
        }),
      }).catch(() => {});
    }, 450);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: saveVisualItemToBackend
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function saveVisualItemToBackend(kind, item) {
    const tg = getTelegramId();
    if (!tg || !item) return item;
    const resourceType = kind === 'voice' ? 'voice' : (kind === 'character' ? 'character' : 'object');
    try {
      const res = await fetch('/api/public/prostudio/resources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, item, {
          telegram_id: tg,
          resource_type: resourceType,
          photos: item.sourceImages || item.source_images || item.referenceImages || [],
          preview_url: item.previewUrl || '',
        })),
      });
      const data = await res.json();
      return data && data.ok && data.resource ? data.resource : item;
    } catch {
      return item;
    }
  }

  /* ===== Rendering ===== */
  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderModeStrip
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = '';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderModelPop
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderModelPop() {
    const el = document.getElementById('modelPop');
    if (!el) return;

    const models = currentComposerModelList();

    if ((isImageMode() || isVideoMode() || isMusicMode() || isVoiceMode() || studioMode === 'text') && models.length) {
      el.innerHTML = '<div class="image-model-sheet-title">Выберите модель</div>'
        + '<div class="image-model-sheet-list">'
        + models.map(imageModelButton).join('')
        + '</div>';
      return;
    }

    el.innerHTML = '';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: showImageModelPicker
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function showImageModelPicker(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const el = document.getElementById('modelPop');
    if (!el) return;

    el.classList.remove('image-size-floating-pop');
    el.classList.remove('music-settings-pop');
    el.classList.remove('video-option-horizontal-pop');
    el.style.cssText = '';

    const models = currentComposerModelList();
    if (!models.length) return;

    // Move model picker to body so it appears above all Pro Studio blocks.
    if (el.parentElement !== document.body) {
      document.body.appendChild(el);
    }

    el.classList.add('image-model-floating-pop');
    el.style.position = 'fixed';
    el.style.left = '0';
    el.style.right = '0';
    el.style.top = 'auto';
    el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
    el.style.width = '100%';
    el.style.maxHeight = '64vh';
    el.style.overflowY = 'auto';
    el.style.zIndex = '999999';

    el.innerHTML = '<div class="image-model-sheet-title">Выберите модель</div>'
      + '<div class="image-model-sheet-list">'
      + models.map(imageModelButton).join('')
      + '</div>';

    el.classList.add('show');
    const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
    const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: currentImageModel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function currentImageModel() {
    // =====================================================
    // JAVASCRIPT-БЛОК: model
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const model = IMAGE_MODEL_LIST.find((item) => item.id === imageState.modelId) || IMAGE_MODEL_LIST[0];
    if (!model) return null;

    return Object.assign({
      sizes: [
        { id:'1:1', label:'1:1', ratio:'1:1' },
        { id:'16:9', label:'16:9', ratio:'16:9' },
        { id:'9:16', label:'9:16', ratio:'9:16' }
      ],
      counts: [1, 2, 3, 4],
      styles: [{ id:'auto', label:'Авто' }],
      characters: [{ id:'auto', label:'Авто' }]
    }, model);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: customVisualKey
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function customVisualKey(kind) {
    return 'sylvex-prostudio-' + kind + '-' + (getTelegramId() || 'anon');
  }

  function visualPreviewUrl(item) {
    if (!item || typeof item !== 'object') return '';
    return item.previewUrl
      || item.preview_url
      || item.image_url
      || item.result_url
      || item.generatedPreview
      || ((item.referenceImages || item.reference_images || item.photos || [])[0])
      || '';
  }

  function normalizeVisualItem(item) {
    if (!item || typeof item !== 'object') return item;
    const refs = Array.isArray(item.referenceImages)
      ? item.referenceImages.slice()
      : (Array.isArray(item.reference_images)
        ? item.reference_images.slice()
        : (Array.isArray(item.photos) ? item.photos.slice() : []));
    const preview = visualPreviewUrl(Object.assign({}, item, { referenceImages: refs }));
    return Object.assign({}, item, {
      previewUrl: preview,
      preview_url: item.preview_url || preview,
      referenceImages: refs.length ? refs : (preview ? [preview] : []),
      videoReferenceUrl: item.videoReferenceUrl || item.video_reference_url || '',
      videoReferences: Array.isArray(item.videoReferences) ? item.videoReferences.slice() : (Array.isArray(item.video_references) ? item.video_references.slice() : []),
      heygenPhotoAvatarId: String(item.heygenPhotoAvatarId || item.heygen_photo_avatar_id || item.photoAvatarId || item.photo_avatar_id || ''),
      heygenVideoAvatarId: String(item.heygenVideoAvatarId || item.heygen_video_avatar_id || item.videoAvatarId || item.video_avatar_id || ''),
      heygenAvatarGroupId: String(item.heygenAvatarGroupId || item.heygen_avatar_group_id || item.avatarGroupId || item.avatar_group_id || ''),
      heygenDefaultVoiceId: String(item.heygenDefaultVoiceId || item.heygen_default_voice_id || item.defaultVoiceId || item.default_voice_id || ''),
      heygenLooks: Array.isArray(item.heygenLooks) ? item.heygenLooks.slice() : (Array.isArray(item.heygen_looks) ? item.heygen_looks.slice() : []),
    });
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: loadCustomVisualItems
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function loadCustomVisualItems(kind) {
    const serverItems = serverVisualItems && Array.isArray(serverVisualItems[kind])
      ? serverVisualItems[kind].map(normalizeVisualItem)
      : [];
    try {
      const raw = localStorage.getItem(customVisualKey(kind));
      const list = raw ? JSON.parse(raw) : [];
      // =====================================================
      // JAVASCRIPT-БЛОК: localItems
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const localItems = Array.isArray(list) ? list.map(normalizeVisualItem).filter((item) => item && item.id && visualPreviewUrl(item)) : [];
      const seen = new Set();
      return serverItems.concat(localItems).filter((item) => {
        if (!item || !item.id || seen.has(item.id)) return false;
        seen.add(item.id);
        return true;
      });
    } catch {
      return serverItems;
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: saveCustomVisualItems
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function saveCustomVisualItems(kind, items) {
    try {
      localStorage.setItem(customVisualKey(kind), JSON.stringify((items || []).slice(0, 50)));
    } catch {}
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageCharacters
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageCharacters() {
    const custom = loadCustomVisualItems('characters');
    const official = PRESET_CHARACTERS.filter((item) => item && (item.official || String(item.id || '').toLowerCase() === 'character_sylvex'));
    const rest = PRESET_CHARACTERS.filter((item) => !official.includes(item));
    return official.concat(custom, rest);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageObjects
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageObjects() {
    return loadCustomVisualItems('objects').concat(PRESET_OBJECTS);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: selectedImageCharacter
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function selectedImageCharacter() {
    return imageCharacters().find((item) => item.id === imageState.characterId) || null;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: selectedImageObject
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function selectedImageObject() {
    return imageObjects().find((item) => item.id === imageState.objectId) || null;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: clearSelectedCharacter
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function clearSelectedCharacter() {
    imageState.characterId = null;
    imageState.characterName = '';
    imageState.characterReferences = [];
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: clearSelectedObject
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function clearSelectedObject() {
    imageState.objectId = null;
    imageState.objectName = '';
    imageState.objectReferences = [];
    imageState.objects = '';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: syncImageFeatureAvailability
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function syncImageFeatureAvailability() {
    const caps = getModelCapabilities(imageState.modelId);
    if (!caps.character && imageState.characterId) clearSelectedCharacter();
    if (!caps.object && imageState.objectId) clearSelectedObject();
    return caps;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageFeatureUnavailableToast
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageFeatureUnavailableToast(feature) {
    const label = feature === 'character' ? 'персонажей' : 'объекты';
    toast('Выбранная AI-модель не поддерживает ' + label + '.');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: ensureImageReferenceSections
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function ensureImageReferenceSections() {
    let wrap = document.getElementById('imageReferenceSections');
    if (wrap) wrap.remove();
    return null;
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderImageReferenceSections
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderImageReferenceSections() {
    ensureImageReferenceSections();
    const caps = syncImageFeatureAvailability();
    const character = selectedImageCharacter();
    const object = selectedImageObject();

    // =====================================================
    // JAVASCRIPT-БЛОК: setButtonState
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const setButtonState = (valueEl, disabled) => {
      if (!valueEl) return;
      const btn = valueEl.closest('button');
      if (!btn) return;
      btn.disabled = !!disabled;
      btn.classList.toggle('image-setting-disabled', !!disabled);
      btn.setAttribute('aria-disabled', disabled ? 'true' : 'false');
    };

    const characterVal = document.getElementById('imageCharacterVal');
    if (characterVal) {
      characterVal.textContent = caps.character
        ? (character ? character.name : 'Персонаж')
        : 'Недоступно для выбранной модели';
      setButtonState(characterVal, !caps.character);
      renderUploadPreviewOnButton(
        document.getElementById('imageCharacterButton'),
        caps.character && character ? [visualPreviewUrl(character)].filter(Boolean) : []
      );
    }

    const objectVal = document.getElementById('imageObjectVal');
    if (objectVal) {
      objectVal.textContent = caps.object
        ? (object ? object.name : 'Объект')
        : 'Недоступно для выбранной модели';
      setButtonState(objectVal, !caps.object);
      renderUploadPreviewOnButton(
        document.getElementById('imageObjectButton'),
        caps.object && object ? [visualPreviewUrl(object)].filter(Boolean) : []
      );
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: nextImageCountValue
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function nextImageCountValue() {
    const counts = [1, 2, 3, 4];
    const currentCount = Number(imageState.count || 1);
    // =====================================================
    // JAVASCRIPT-БЛОК: currentIndex
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const currentIndex = counts.findIndex((item) => Number(item) === currentCount);
    const safeIndex = currentIndex >= 0 ? currentIndex : 0;
    return Number(counts[(safeIndex + 1) % counts.length] || 1);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: optionLabel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function optionLabel(options, id, fallback) {
    const value = String(id || '');

    const styleOpt = (typeof IMAGE_STYLE_SHEET_ITEMS !== 'undefined')
      ? IMAGE_STYLE_SHEET_ITEMS.find((item) => String(item.id) === value)
      : null;

    if (styleOpt) {
      return styleOpt.label || styleOpt.id;
    }

    // =====================================================
    // JAVASCRIPT-БЛОК: opt
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const opt = (options || []).find((item) => String(item.id) === value);

    return opt ? (opt.label || opt.id) : fallback;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageStyleSheetItem
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageStyleSheetItem(id) {
    const value = String(id || '');
    return IMAGE_STYLE_SHEET_ITEMS.find((item) => String(item.id) === value) || null;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: updateImageStyleButtonPreview
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function updateImageStyleButtonPreview(styleItem) {
    const styleVal = document.getElementById('imageStyleVal');
    if (!styleVal) return;

    const button = styleVal.closest('button') || styleVal.parentElement;
    if (!button) return;

    const avatar = button.querySelector('.image-style-control-avatar');
    if (avatar) avatar.remove();

    if (!styleItem || String(styleItem.id) === 'auto' || !styleItem.image) {
      button.classList.remove('has-style-preview');
      button.style.removeProperty('--image-style-bg');
      return;
    }

    button.style.setProperty('--image-style-bg', 'url("' + String(styleItem.image).replace(/"/g, '\\"') + '")');
    button.classList.add('has-style-preview');
  }

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderUploadPreviewOnButton
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderUploadPreviewOnButton(button, urls) {
  if (!button) return;
  const clean = (urls || []).map((item) => {
    if (!item) return null;
    if (typeof item === 'object') {
      const url = item.url || item.video_url || item.image_url || item.src || '';
      if (!url) return null;
      return { url, type: item.type || item.kind || '' };
    }
    return { url: String(item), type: '' };
  }).filter(Boolean).slice(0, 4);
  let bg = button.querySelector(':scope > .image-upload-control-bg');
  if (!clean.length) {
    if (bg) bg.remove();
    button.classList.remove('has-upload-preview');
    return;
  }
  if (!bg) {
    bg = document.createElement('span');
    bg.className = 'image-upload-control-bg';
    button.insertBefore(bg, button.firstChild);
  }
  bg.dataset.count = String(clean.length);
  bg.innerHTML = clean.map((item) => {
    const url = S.escapeHtml(item.url || '');
    const type = String(item.type || '').toLowerCase();
    const isVideo = type === 'video' || /\.(mp4|mov|m4v|webm)(\?|$)/i.test(item.url || '');
    return '<span class="image-upload-control-bg-cell">' + (isVideo
      ? '<video src="' + url + '" muted playsinline preload="metadata"></video><em>VID</em>'
      : '<img src="' + url + '" alt="" decoding="async" />') + '</span>';
  }).join('');
  button.classList.add('has-upload-preview');
}

// =====================================================
// JAVASCRIPT-БЛОК: setFramePreview
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function setFramePreview(card, url, label) {
  if (!card) return;
  let preview = card.querySelector(':scope > .studio-frame-preview');
  if (!url) {
    if (preview) preview.remove();
    card.classList.remove('has-frame-preview');
    return;
  }
  if (!preview) {
    preview = document.createElement('span');
    preview.className = 'studio-frame-preview';
    card.insertBefore(preview, card.firstChild);
  }
  preview.innerHTML = '<img src="' + S.escapeHtml(url) + '" alt="' + S.escapeHtml(label || 'preview') + '" decoding="async" />';
  card.classList.add('has-frame-preview');
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderImageUploadPreview
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderImageUploadPreview() {
  renderUploadPreviewOnButton(document.getElementById('imageUploadButton'), imageState.uploadedImageUrls || []);
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoStartPreview
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVideoStartPreview() {
  const button = document.getElementById('videoStartUploadButton') || document.getElementById('videoStartFrameCard');
  setFramePreview(button, videoState.startImage || '', 'start image');
  const label = button && button.querySelector(':scope > span:last-child');
  if (label) label.textContent = videoState.startImage ? 'Начальное изображение выбрано' : 'Начальное изображение';
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoEndPreview
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVideoEndPreview() {
  const button = document.getElementById('videoEndUploadButton') || document.getElementById('videoEndFrameCard');
  setFramePreview(button, videoState.endImage || '', 'end image');
  const label = button && button.querySelector(':scope > span:last-child');
  if (label) label.textContent = videoState.endImage ? 'Конечный образ выбран' : 'Конечный образ';
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoReferencesPreview
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVideoReferencesPreview() {
  const button = document.getElementById('videoReferencesUploadButton');
  const media = [];
  const uploading = videoState.referenceUploading || null;
  const referenceVideo = currentVideoReferenceUrl();
  if (uploading && uploading.previewUrl) media.push({ url: uploading.previewUrl, type: uploading.kind || 'video' });
  if (!uploading && referenceVideo) media.push({ url: referenceVideo, type: 'video' });
  currentVideoReferenceImages().forEach((url) => media.push({ url, type: 'image' }));
  renderUploadPreviewOnButton(button, media);
  if (!button) return;
  const label = document.getElementById('videoReferencesLabel');
  const refsCount = currentVideoReferenceImages().length;
  const hasVideo = !!referenceVideo;
  if (label) {
    label.textContent = uploading
      ? 'Загрузка медиа...'
      : hasVideo
      ? ('Видео выбрано' + (refsCount ? ' · +' + refsCount : ''))
      : (refsCount ? ('Референсы · ' + refsCount) : 'Добавить');
  }
  let badge = button.querySelector(':scope > .video-reference-control-badge');
  if (referenceVideo) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'video-reference-control-badge';
      button.insertBefore(badge, button.firstChild);
    }
    badge.textContent = 'VID';
    button.classList.add('has-video-reference');
  } else {
    if (badge) badge.remove();
    button.classList.remove('has-video-reference');
  }
  button.classList.toggle('is-uploading', !!uploading);
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoEditPreview
// Показывает выбранный видео-референс в отдельном edit-only блоке.
// =====================================================
function renderVideoEditPreview() {
  const button = document.getElementById('videoEditUploadButton');
  if (!button) return;
  const uploading = videoState.editUploading || null;
  const url = uploading && uploading.previewUrl ? uploading.previewUrl : currentVideoEditInputUrl();
  let preview = button.querySelector(':scope > .studio-video-edit-preview');
  const title = button.querySelector('b');
  const hint = button.querySelector('small');
  if (!url) {
    if (preview) preview.remove();
    button.classList.remove('has-video-edit-preview');
    button.classList.remove('is-uploading');
    if (title) title.textContent = 'Загрузите видео-референс';
    if (hint) hint.textContent = 'Длительность: 3–10 секунд';
    return;
  }
  if (!preview) {
    preview = document.createElement('span');
    preview.className = 'studio-video-edit-preview';
    button.insertBefore(preview, button.firstChild);
  }
  preview.innerHTML = '<video src="' + S.escapeHtml(url) + '" autoplay loop muted playsinline preload="auto" webkit-playsinline oncanplay="this.play().catch(()=>{})" onloadeddata="this.play().catch(()=>{})"></video><span>' + (uploading ? '...' : 'VID') + '</span>';
  if (title) title.textContent = uploading ? 'Видео загружается' : 'Видео выбрано';
  if (hint) hint.textContent = uploading ? 'Подождите завершения загрузки' : 'Нажмите, чтобы заменить файл';
  button.classList.add('has-video-edit-preview');
  button.classList.toggle('is-uploading', !!uploading);
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoInputPreviews
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVideoInputPreviews() {
  renderVideoStartPreview();
  renderVideoEndPreview();
  renderVideoEditPreview();
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderAllUploadPreviews
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderAllUploadPreviews() {
  injectImageStyleSheetCss();
  renderImageUploadPreview();
  renderVideoStartPreview();
  renderVideoEndPreview();
  renderVideoReferencesPreview();
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderUploadPreviewForTarget
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderUploadPreviewForTarget(targetOverride) {
  injectImageStyleSheetCss();
  const target = targetOverride || getUploadTarget();
  if (target === UPLOAD_TARGETS.VIDEO_START) {
    renderVideoStartPreview();
  } else if (target === UPLOAD_TARGETS.VIDEO_END) {
    renderVideoEndPreview();
  } else if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
    renderVideoReferencesPreview();
  } else {
    renderImageUploadPreview();
  }
}

// =====================================================
// ЗАГРУЗКА В MINI APP: updateImageUploadButtonPreview
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function updateImageUploadButtonPreview() {
  renderAllUploadPreviews();
}

// =====================================================
// ЗАГРУЗКА В MINI APP: currentUploadImages
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function currentUploadImages(targetOverride) {
  const target = targetOverride || getUploadTarget();
  if (target === UPLOAD_TARGETS.VIDEO_START) return videoState.startImage ? [videoState.startImage] : [];
  if (target === UPLOAD_TARGETS.VIDEO_END) return videoState.endImage ? [videoState.endImage] : [];
  if (target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) return [];
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) return currentVideoReferenceImages();
  return (imageState.uploadedImageUrls || []).slice();
}

// =====================================================
// ЗАГРУЗКА В MINI APP: uploadLimitForTarget
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function uploadLimitForTarget(targetOverride) {
  const target = targetOverride || getUploadTarget();
  return target === UPLOAD_TARGETS.VIDEO_START || target === UPLOAD_TARGETS.VIDEO_END ? 1 : 4;
}

// =====================================================
// ЗАГРУЗКА В MINI APP: applyUploadToTarget
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function applyUploadToTarget(url, targetOverride) {
  if (!url) return;
  const target = targetOverride || getUploadTarget();
  if (target === UPLOAD_TARGETS.VIDEO_START) {
    videoState.startImage = url;
    renderVideoStartPreview();
    updateSendButton();
    return;
  }
  if (target === UPLOAD_TARGETS.VIDEO_END) {
    videoState.endImage = url;
    renderVideoEndPreview();
    updateSendButton();
    return;
  }
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
    // =====================================================
    // JAVASCRIPT-БЛОК: refs
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const refs = currentVideoReferenceImages().filter((item) => item && item !== url);
    refs.unshift(url);
    setCurrentVideoReferenceImages(refs.slice(0, uploadLimitForTarget(target)));
    renderVideoReferencesPreview();
    renderUploadedPhotoGrid();
    updateSendButton();
    return;
  }
  if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) {
    // =====================================================
    // ЗАГРУЗКА В MINI APP: uploads
    // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
    // =====================================================
    const uploads = (imageState.uploadedImageUrls || []).filter((item) => item && item !== url);
    uploads.unshift(url);
    imageState.uploadedImageUrls = uploads.slice(0, uploadLimitForTarget(target));
    imageState.referenceImageUrls = imageState.uploadedImageUrls.slice();
    imageState.referenceImageUrl = imageState.uploadedImageUrls[0] || '';
    imageState.attachment = imageState.attachment || null;
    renderImageUploadPreview();
    renderUploadedPhotoGrid();
    updateSendButton();
  }
}

// =====================================================
// ЗАГРУЗКА В MINI APP: applyUploadedMediaToTarget
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function applyUploadedMediaToTarget(url) {
  applyUploadToTarget(url, getUploadTarget());
}

// =====================================================
// JAVASCRIPT-БЛОК: addVideoReferenceImage
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function addVideoReferenceImage(url) {
  applyUploadToTarget(url, UPLOAD_TARGETS.VIDEO_REFERENCES);
}

// =====================================================
// JAVASCRIPT-БЛОК: applyVideoReferenceToState
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function applyVideoReferenceToState(url) {
  if (!url) return;
  videoState.referenceVideoUrl = url;
  renderVideoReferencesPreview();
  renderUploadedPhotoGrid();
  updateSendButton();
}

function applyVideoEditInputToState(url) {
  if (!url) return;
  videoState.editInputVideo = url;
  videoState.editVideoUrl = url;
  videoState.inputVideo = url;
  videoState.videoUrl = url;
  if (videoState.section === 'motion') {
    videoState.generationMode = 'motion_control';
    videoState.mode = 'motion_control';
  } else {
    videoState.generationMode = 'video_edit';
    videoState.mode = 'video_edit';
  }
  renderVideoEditPreview();
  updateSendButton();
}

// =====================================================
// ЗАГРУЗКА В MINI APP: setCurrentUploadImages
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function setCurrentUploadImages(urls, targetOverride) {
  const target = targetOverride || getUploadTarget();
  const clean = (urls || []).filter(Boolean).slice(0, uploadLimitForTarget(target));
  if (target === UPLOAD_TARGETS.VIDEO_START) {
    videoState.startImage = clean[0] || '';
    renderVideoStartPreview();
  } else if (target === UPLOAD_TARGETS.VIDEO_END) {
    videoState.endImage = clean[0] || '';
    renderVideoEndPreview();
  } else if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
    setCurrentVideoReferenceImages(clean.slice(0, uploadLimitForTarget(target)));
    renderVideoReferencesPreview();
  } else if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) {
    imageState.uploadedImageUrls = clean.slice(0, uploadLimitForTarget(target));
    imageState.referenceImageUrls = imageState.uploadedImageUrls.slice();
    imageState.referenceImageUrl = imageState.uploadedImageUrls[0] || '';
    renderImageUploadPreview();
  }
  renderUploadedPhotoGrid();
  updateSendButton();
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openUploadTarget
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openUploadTarget(target, e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  setUploadTarget(target);
  const plusPop = document.getElementById('plusPop');
  if (plusPop) plusPop.classList.remove('show');
  const plusSheet = document.getElementById('plusSheet');
  if (plusSheet) plusSheet.classList.remove('show');
  const panel = ensureUploadPanel();
  panel.dataset.uploadTarget = target;
  openUploadPanel(e);
  panel.dataset.uploadTarget = target;
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openImageUpload
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openImageUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.IMAGE_UPLOAD, e);
}

const selectionButtonTimers = Object.create(null);
const SELECTION_DOUBLE_PRESS_MS = 320;

function clearSelectionButton(kind) {
  if (kind === 'style') {
    imageState.style = 'auto';
  } else if (kind === 'character') {
    clearSelectedCharacter();
  } else if (kind === 'object') {
    clearSelectedObject();
  } else if (kind === 'image_upload') {
    imageState.attachment = null;
    setCurrentUploadImages([], UPLOAD_TARGETS.IMAGE_UPLOAD);
  } else if (kind === 'video_start') {
    setCurrentUploadImages([], UPLOAD_TARGETS.VIDEO_START);
  } else if (kind === 'video_end') {
    setCurrentUploadImages([], UPLOAD_TARGETS.VIDEO_END);
  } else if (kind === 'video_references') {
    setCurrentUploadImages([], UPLOAD_TARGETS.VIDEO_REFERENCES);
    videoState.referenceVideoUrl = '';
    videoState.referenceUploading = null;
    renderVideoReferencesPreview();
  } else if (kind === 'video_edit') {
    videoState.editUploading = null;
    videoState.editInputVideo = '';
    videoState.editVideoUrl = '';
    videoState.inputVideo = '';
    videoState.videoUrl = '';
    renderVideoEditPreview();
  }

  const panel = document.getElementById('imageStylePanel');
  if (panel) panel.classList.remove('show');
  const uploadPanel = document.getElementById('uploadPanel');
  if (uploadPanel) uploadPanel.classList.remove('show');
  const modelPop = document.getElementById('modelPop');
  if (modelPop) modelPop.classList.remove('show');
  closeVideoAddMenu();
  renderImageControls();
  renderAllUploadPreviews();
  renderUploadedPhotoGrid();
  updateSendButton();
  toast('Выбор очищен');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

function openSelectionButton(kind) {
  if (kind === 'style') return openImageOptionMenu(null, 'style');
  if (kind === 'character') return openImageOptionMenu(null, 'character');
  if (kind === 'object') return openImageOptionMenu(null, 'objects');
  if (kind === 'image_upload') return openImageUpload(null);
  if (kind === 'video_start') return openVideoStartUpload(null);
  if (kind === 'video_end') return openVideoEndUpload(null);
  if (kind === 'video_references') return toggleVideoAddMenu(null);
  if (kind === 'video_edit') return openVideoEditInputUpload(null);
}

function handleSelectionButtonClick(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const key = String(kind || '');
  if (!key) return;
  if (selectionButtonTimers[key]) {
    clearTimeout(selectionButtonTimers[key]);
    delete selectionButtonTimers[key];
    clearSelectionButton(key);
    return;
  }
  selectionButtonTimers[key] = setTimeout(() => {
    delete selectionButtonTimers[key];
    openSelectionButton(key);
  }, SELECTION_DOUBLE_PRESS_MS);
}

function ensurePhotoToolModal() {
  let modal = document.getElementById('photoToolModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'photoToolModal';
  modal.className = 'photo-tool-modal';
  modal.onclick = closePhotoToolModal;
  modal.innerHTML = '<section class="photo-tool-dialog" role="dialog" aria-modal="true" onclick="event.stopPropagation()">'
    + '<div id="photoToolModalBody"></div>'
    + '</section>';
  document.body.appendChild(modal);
  return modal;
}

function ensurePhotoCatalogModal() {
  let modal = document.getElementById('photoCatalogModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'photoCatalogModal';
  modal.className = 'photo-tool-modal photo-catalog-modal';
  modal.onclick = closePhotoCatalog;
  modal.innerHTML = '<section class="photo-tool-dialog photo-catalog-dialog" role="dialog" aria-modal="true" onclick="event.stopPropagation()">'
    + '<header class="photo-tool-head"><div><small>Каталог</small><h3>Фото</h3></div>'
    + '<button type="button" aria-label="Закрыть" onclick="SYLVEX.closePhotoCatalog(event)">×</button></header>'
    + '<div id="photoCatalogGrid" class="photo-catalog-grid"></div>'
    + '</section>';
  document.body.appendChild(modal);
  return modal;
}

async function loadPhotoCatalog(force) {
  if (!force && Array.isArray(photoCatalogCache)) return photoCatalogCache;
  try {
    const res = await fetch('/api/public/prostudio/photo-catalog', { cache: force ? 'reload' : 'default' });
    const data = await res.json().catch(() => ({}));
    photoCatalogCache = Array.isArray(data.photos)
      ? data.photos.map((item) => ({
          id: String(item.id || ''),
          url: String(item.image_url || item.url || ''),
          title: String(item.title || item.name || 'Фото'),
          prompt: String(item.prompt || ''),
          model: String(item.model || ''),
          aspectRatio: String(item.aspect_ratio || item.ratio || ''),
        })).filter((item) => item.url)
      : [];
  } catch {
    photoCatalogCache = [];
  }
  return photoCatalogCache;
}

function renderPhotoCatalog(itemsOverride) {
  const grid = document.getElementById('photoCatalogGrid');
  if (!grid) return;
  const items = Array.isArray(itemsOverride) ? itemsOverride : (photoCatalogCache || []);
  if (!items.length) {
    grid.innerHTML = '<div class="photo-catalog-empty">Каталог пока пуст. Добавьте фотографии в папку разработчика.</div>';
    return;
  }
  grid.innerHTML = items.map((item) => {
    return '<button class="photo-catalog-card square" type="button" onclick="SYLVEX.selectPhotoCatalogItem(event,\'' + S.escapeHtml(item.url) + '\')">'
    + '<img src="' + S.escapeHtml(item.url) + '" alt="' + S.escapeHtml(item.title) + '" loading="lazy" decoding="async" onload="SYLVEX.syncPhotoCatalogCardRatio(event)" />'
    + '<span><b>' + S.escapeHtml(item.title) + '</b><small>Использовать фото</small></span>'
    + '</button>';
  }).join('');
}

function syncPhotoCatalogCardRatio(e) {
  const image = e && e.currentTarget;
  const card = image && image.closest ? image.closest('.photo-catalog-card') : null;
  if (!image || !card) return;
  const ratio = Number(image.naturalWidth || 0) / Math.max(1, Number(image.naturalHeight || 0));
  card.classList.remove('square', 'wide', 'tall');
  if (ratio >= 1.35) card.classList.add('wide');
  else if (ratio <= .75) card.classList.add('tall');
  else card.classList.add('square');
}

async function openPhotoCatalog(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  updateComposerMode('image');
  const modal = ensurePhotoCatalogModal();
  modal.classList.add('show');
  const grid = document.getElementById('photoCatalogGrid');
  if (grid) grid.innerHTML = '<div class="photo-catalog-empty">Загружаем каталог…</div>';
  renderPhotoCatalog(await loadPhotoCatalog(true));
}

function closePhotoCatalog(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const modal = document.getElementById('photoCatalogModal');
  if (modal) modal.classList.remove('show');
}

function selectPhotoCatalogItem(e, url) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (!url) return;
  const item = (photoCatalogCache || []).find((entry) => entry.url === url) || null;
  if (item && item.model && IMAGE_MODEL_LIST.some((model) => model.id === item.model)) {
    imageState.modelId = item.model;
  }
  if (item && item.prompt) {
    const input = document.getElementById('chatInput');
    if (input) {
      input.value = item.prompt;
      autoGrow(input);
    }
  }
  setUploadTarget(UPLOAD_TARGETS.IMAGE_UPLOAD);
  applyUploadToTarget(url, UPLOAD_TARGETS.IMAGE_UPLOAD);
  renderImageControls();
  renderImageUploadPreview();
  closePhotoCatalog();
  toast('Фото добавлено в генерацию');
}

function photoToolDemoHtml(config) {
  return '<div class="photo-tool-demo">'
    + '<video src="' + S.escapeHtml(config.demo) + '" autoplay muted loop playsinline preload="metadata" onerror="this.parentElement.classList.add(\'demo-missing\')"></video>'
    + '<div class="photo-tool-demo-placeholder"><span></span><b>Демонстрация функции</b><small>Добавьте видео demo.mp4 в подготовленную папку</small></div>'
    + '</div>';
}

function renderPhotoToolCatalog() {
  const body = document.getElementById('photoToolModalBody');
  if (!body) return;
  body.innerHTML = '<header class="photo-tool-head"><div><small>Фото-инструменты</small><h3>Что сделать с фотографией?</h3></div>'
    + '<button type="button" aria-label="Закрыть" onclick="SYLVEX.closePhotoToolModal(event)">×</button></header>'
    + '<div class="photo-tool-catalog">'
    + Object.entries(PHOTO_TOOL_CONFIG).map(([key, config]) =>
      '<button type="button" class="photo-tool-catalog-card" onclick="SYLVEX.openPhotoToolModal(event,\'' + key + '\')">'
      + photoToolDemoHtml(config)
      + '<span><b>' + S.escapeHtml(config.shortTitle) + '</b><small>' + S.escapeHtml(config.description) + '</small></span>'
      + '</button>'
    ).join('')
    + '</div>';
}

function photoToolStateFor(kind) {
  return photoToolState[kind] || null;
}

function renderPhotoToolModal() {
  const body = document.getElementById('photoToolModalBody');
  const config = PHOTO_TOOL_CONFIG[activePhotoTool];
  const state = photoToolStateFor(activePhotoTool);
  if (!body) return;
  if (!config || !state) {
    renderPhotoToolCatalog();
    return;
  }
  const slots = config.labels.map((label, index) => {
    const file = state.files[index];
    return '<button class="photo-tool-upload-slot ' + (file ? 'has-file' : '') + '" type="button" onclick="SYLVEX.openPhotoToolFilePicker(event,\'' + activePhotoTool + '\',' + index + ')">'
      + (file ? '<img src="' + S.escapeHtml(file.url) + '" alt="" />' : '<span class="photo-tool-upload-plus">＋</span>')
      + '<b>' + S.escapeHtml(label) + '</b>'
      + (file ? '<small>' + S.escapeHtml(file.name || 'Фото выбрано') + '</small><i role="button" aria-label="Удалить" onclick="SYLVEX.removePhotoToolFile(event,\'' + activePhotoTool + '\',' + index + ')">×</i>' : '<small>Нажмите для загрузки</small>')
      + '</button>';
  }).join('');
  const ready = state.files.filter(Boolean).length >= config.min;
  body.innerHTML = '<header class="photo-tool-head"><div><small>Фото-инструмент</small><h3>' + S.escapeHtml(config.title) + '</h3></div>'
    + '<button type="button" aria-label="Закрыть" onclick="SYLVEX.closePhotoToolModal(event)">×</button></header>'
    + '<div class="photo-tool-layout">'
    + '<div class="photo-tool-demo-column">' + photoToolDemoHtml(config) + '<p>' + S.escapeHtml(config.description) + '</p></div>'
    + '<div class="photo-tool-work-column">'
    + '<div class="photo-tool-upload-grid count-' + config.max + '">' + slots + '</div>'
    + '<input id="photoToolFileInput" type="file" accept="image/*" ' + (config.max > 1 ? 'multiple ' : '') + 'hidden onchange="SYLVEX.onPhotoToolFiles(event)" />'
    + '<textarea id="photoToolExtraPrompt" rows="2" placeholder="Дополнительные пожелания (необязательно)"></textarea>'
    + '<button class="photo-tool-generate" type="button" ' + (!ready || state.generating ? 'disabled ' : '') + 'onclick="SYLVEX.generatePhotoTool(event)">'
    + (state.generating ? '<span class="photo-tool-spinner"></span>Обработка…' : 'Запустить обработку')
    + '</button>'
    + '</div></div>';
}

function openPhotoToolModal(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  updateComposerMode('image');
  activePhotoTool = PHOTO_TOOL_CONFIG[kind] ? kind : '';
  const modal = ensurePhotoToolModal();
  modal.classList.add('show');
  renderPhotoToolModal();
}

function closePhotoToolModal(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const modal = document.getElementById('photoToolModal');
  if (modal && !(activePhotoTool && photoToolState[activePhotoTool] && photoToolState[activePhotoTool].generating)) {
    modal.classList.remove('show');
  }
}

function openPhotoToolFilePicker(e, kind, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  activePhotoTool = kind;
  const input = document.getElementById('photoToolFileInput');
  if (!input) return;
  input.dataset.slot = String(Math.max(0, Number(index) || 0));
  input.value = '';
  input.click();
}

function readPhotoToolFile(file) {
  return new Promise((resolve, reject) => {
    if (!file || !String(file.type || '').startsWith('image/')) return reject(new Error('Выберите изображение'));
    if (file.size > 50 * 1024 * 1024) return reject(new Error('Фото должно быть меньше 50 MB'));
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, mime: file.type, url: String(reader.result || '') });
    reader.onerror = () => reject(new Error('Не удалось прочитать фото'));
    reader.readAsDataURL(file);
  });
}

async function onPhotoToolFiles(e) {
  const input = e && e.target;
  const config = PHOTO_TOOL_CONFIG[activePhotoTool];
  const state = photoToolStateFor(activePhotoTool);
  if (!input || !config || !state) return;
  const start = Math.max(0, Number(input.dataset.slot || 0));
  const files = Array.from(input.files || []).slice(0, config.max - start);
  if (!files.length) return;
  if ((input.files || []).length > files.length) toast('Для этой функции можно выбрать не больше ' + config.max + ' фото');
  try {
    const loaded = await Promise.all(files.map(readPhotoToolFile));
    loaded.forEach((file, offset) => {
      if (start + offset < config.max) state.files[start + offset] = file;
    });
    state.files = state.files.slice(0, config.max);
    renderPhotoToolModal();
  } catch (error) {
    toast((error && error.message) || 'Не удалось загрузить фото');
  }
}

function removePhotoToolFile(e, kind, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const state = photoToolStateFor(kind);
  if (!state || state.generating) return;
  state.files.splice(index, 1);
  activePhotoTool = kind;
  renderPhotoToolModal();
}

function photoToolPrompt(kind, extra) {
  const suffix = extra ? '\n\nUser request for the operation: ' + extra : '';
  if (kind === 'try_on') {
    return 'Virtual try-on operation. The first reference image is the person. Every following reference image is a garment. Dress the person from the first image in the supplied garments. Preserve the person identity, face, body, pose and scene. Use only the supplied garment references; do not create another person.' + suffix;
  }
  if (kind === 'remove_bg') {
    return 'Remove the background from the first reference image. Preserve the foreground subject and all its details exactly. Return a clean isolated subject with a transparent background. Do not add new objects or people.' + suffix;
  }
  if (kind === 'replace_character') {
    return 'Replace the person in the first reference image with the person shown in the second reference image. Preserve the first image pose, clothing, background, objects, lighting, framing and spatial arrangement. Change only the person. Do not create a second person.' + suffix;
  }
  if (kind === 'tattoo') return 'Apply the tattoo from the second reference image naturally to the person in the first image. Preserve identity, anatomy, pose, lighting and scene. Make the tattoo follow the skin perspective and texture.' + suffix;
  if (kind === 'logo') return 'Place the logo from the second reference image naturally into the first image. Preserve the logo design, proportions and legibility while matching perspective, material and lighting.' + suffix;
  if (kind === 'remove_object') return 'Remove only the object described by the user from the first image and reconstruct the hidden background naturally. Preserve all other people, objects, composition and lighting.' + suffix;
  if (kind === 'replace_object') return 'Replace the relevant object in the first image with the object from the second image. Preserve the scene, people, composition and lighting. Match scale, perspective and shadows.' + suffix;
  return 'Enhance the first reference photo. Improve sharpness, detail, resolution, dynamic range and natural color while preserving the exact subject, identity, composition, objects and scene. Do not add or remove people or objects.' + suffix;
}

async function generatePhotoTool(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const kind = activePhotoTool;
  const config = PHOTO_TOOL_CONFIG[kind];
  const state = photoToolStateFor(kind);
  if (!config || !state || state.generating) return;
  const refs = state.files.filter(Boolean).map((item) => item.url);
  if (refs.length < config.min) {
    toast('Загрузите необходимые фотографии');
    return;
  }
  const extraEl = document.getElementById('photoToolExtraPrompt');
  const extra = extraEl ? String(extraEl.value || '').trim() : '';
  const prompt = photoToolPrompt(kind, extra);
  state.generating = true;
  renderPhotoToolModal();
  document.body.classList.add('ai-generating');
  const loadingIndex = chatMessages.push({
    role: 'ai',
    generationLoading: true,
    progress: createGenerationProgress('image'),
  }) - 1;
  renderChat();
  try {
    const start = await callGenerate(prompt, null, refs, null, {
      onProgress: (completed) => updateGenerationLoadingProgress(loadingIndex, completed),
      loadingIndex,
    });
    const result = start.result || start;
    const images = generatedUrlsFromResponse(result, 'image');
    const thumbs = generatedThumbsFromResponse(result);
    if (images.length) addGeneratedImages(images, thumbs);
    const options = Object.assign({}, imageOptionsPayload(refs), { photo_tool: kind });
    chatMessages[loadingIndex] = {
      role: 'ai',
      imageResultMini: true,
      metadata: imageGenerationMetadata(prompt, refs, result, options),
    };
    state.files = [];
    state.generating = false;
    closePhotoToolModal();
    toast('Обработка завершена');
    loadConversations();
  } catch (error) {
    state.generating = false;
    chatMessages[loadingIndex] = {
      role: 'ai',
      text: '⚠️ ' + translateGenerationError(error, 'Не удалось обработать фото. Попробуйте ещё раз.'),
    };
    renderPhotoToolModal();
    toast(translateGenerationError(error, 'Не удалось обработать фото'));
  } finally {
    document.body.classList.remove('ai-generating');
    renderChat();
    rememberCurrentChatSpace();
    if (!activeGeneration.jobId || !isActiveGenerationStatus(activeGeneration.status)) {
      clearActiveProStudioJob(activeGeneration.jobId);
    }
  }
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openImageUploadTarget
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openImageUploadTarget(e) {
  openImageUpload(e);
}

// =====================================================
// JAVASCRIPT-БЛОК: ensureVisualCreateModal
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function ensureVisualCreateModal() {
  let modal = document.getElementById('visualCreateModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'visualCreateModal';
  modal.className = 'visual-create-modal';
  document.body.appendChild(modal);
  return modal;
}

// =====================================================
// JAVASCRIPT-БЛОК: ensureVisualPickerModal
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function ensureVisualPickerModal() {
  let modal = document.getElementById('visualPickerModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'visualPickerModal';
  modal.className = 'visual-create-modal visual-picker-modal';
  document.body.appendChild(modal);
  return modal;
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeVisualPicker
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeVisualPicker(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const modal = document.getElementById('visualPickerModal');
  if (modal) modal.classList.remove('show');
  closeCharacterDetail();
}

// =====================================================
// JAVASCRIPT-БЛОК: visualPickerCardHtml
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function visualPickerCardHtml(item, kind) {
  item = normalizeVisualItem(item) || {};
  const selected = kind === 'character' ? imageState.characterId === item.id : imageState.objectId === item.id;
  const canDelete = isCustomVisualItem(item);
  const preview = visualPreviewUrl(item);
  return '<div class="visual-picker-card ' + (selected ? 'selected' : '') + '" role="button" tabindex="0" onclick="SYLVEX.pickVisualReference(event,\'' + kind + '\',\'' + S.escapeHtml(item.id) + '\')">'
    + '<span class="visual-picker-thumb">' + (preview ? '<img src="' + S.escapeHtml(preview) + '" alt="' + S.escapeHtml(item.name) + '" loading="lazy" decoding="async" />' : '<span class="visual-picker-placeholder">＋</span>') + '</span>'
    + '<span class="visual-picker-name">' + S.escapeHtml(item.name) + '</span>'
    + '<span class="visual-picker-check">✓</span>'
    + (canDelete ? '<button class="visual-delete-btn" type="button" aria-label="Удалить" onclick="SYLVEX.deleteVisualReference(event,\'' + kind + '\',\'' + S.escapeHtml(item.id) + '\')">×</button>' : '')
    + '</div>';
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openVisualPicker
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openVisualPicker(e, kind) {
  openImageStylePanel(e, kind === 'object' ? 'object' : 'character');
}

function openVideoVisualPicker(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (!isVideoMode()) return openImageStylePanel(e, kind === 'object' ? 'object' : 'character');
  activeImageStylePanelKind = kind === 'object' ? 'object' : 'character';
  const panel = ensureImageStylePanel();
  renderImageStylePanel();
  panel.classList.add('show');
  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

let visualCreateDraft = { kind: '', photos: [] };
let resourceDeleteConfirm = null;
const visualStatsCache = {};
let activeCharacterDetailId = '';

function visualStatsKey(kind, id) {
  return (kind === 'object' ? 'object' : 'character') + ':' + String(id || '');
}

function localVisualStats() {
  try {
    return JSON.parse(localStorage.getItem('sylvex-visual-stats-' + (getTelegramId() || 'anon')) || '{}') || {};
  } catch {
    return {};
  }
}

function saveLocalVisualStats(map) {
  try {
    localStorage.setItem('sylvex-visual-stats-' + (getTelegramId() || 'anon'), JSON.stringify(map || {}));
  } catch {}
}

function visualItemHeygenAvatarId(item) {
  if (!item || typeof item !== 'object') return '';
  return String(item.heygenVideoAvatarId || item.heygen_video_avatar_id || item.heygenPhotoAvatarId || item.heygen_photo_avatar_id || '').trim();
}

function currentVisualStats(kind, item) {
  const id = item && item.id ? item.id : '';
  const key = visualStatsKey(kind, id);
  const local = localVisualStats()[key] || {};
  return Object.assign({ likes: 0, selects: 0, liked: false, favorite: false, heygen: {} }, local, visualStatsCache[key] || {});
}

async function loadVisualStats(kind, item) {
  if (!item || !item.id) return;
  const key = visualStatsKey(kind, item.id);
  if (visualStatsCache[key] && visualStatsCache[key].loaded) return;
  const params = new URLSearchParams({
    resource_id: item.id,
    resource_type: kind === 'object' ? 'object' : 'character',
    telegram_id: String(getTelegramId() || 0),
    heygen_avatar_id: visualItemHeygenAvatarId(item),
  });
  try {
    const response = await fetch('/api/public/prostudio/visual-stats?' + params.toString(), { method: 'GET', cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (data && data.stats) {
      visualStatsCache[key] = Object.assign({}, data.stats, { loaded: true });
      renderImageStylePanel();
    }
  } catch {
    visualStatsCache[key] = Object.assign({}, currentVisualStats(kind, item), { loaded: true });
  }
}

async function sendVisualInteraction(kind, id, action, value, e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const item = (kind === 'object' ? imageObjects() : imageCharacters()).find((entry) => entry && entry.id === id);
  if (!item) return;
  const key = visualStatsKey(kind, id);
  const localMap = localVisualStats();
  const current = Object.assign({ likes: 0, selects: 0, liked: false, favorite: false }, localMap[key] || {}, visualStatsCache[key] || {});
  if (action === 'like') {
    const liked = value === undefined ? !current.liked : !!value;
    current.likes = Math.max(0, Number(current.likes || 0) + (liked === !!current.liked ? 0 : (liked ? 1 : -1)));
    current.liked = liked;
  } else if (action === 'favorite') {
    current.favorite = value === undefined ? !current.favorite : !!value;
  } else if (action === 'select') {
    current.selects = Number(current.selects || 0) + 1;
  }
  localMap[key] = current;
  visualStatsCache[key] = current;
  saveLocalVisualStats(localMap);
  renderImageStylePanel();
  if (activeCharacterDetailId) renderCharacterDetail();
  try {
    const response = await fetch('/api/public/prostudio/visual-interaction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        telegram_id: getTelegramId() || 0,
        resource_id: id,
        resource_type: kind === 'object' ? 'object' : 'character',
        action,
        value: action === 'like' ? current.liked : (action === 'favorite' ? current.favorite : true),
        heygen_avatar_id: visualItemHeygenAvatarId(item),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (data && data.stats) {
      visualStatsCache[key] = Object.assign({}, data.stats, { loaded: true });
      renderImageStylePanel();
      if (activeCharacterDetailId) renderCharacterDetail();
    }
  } catch {}
}

function isCustomVisualItem(item) {
  if (!item || typeof item !== 'object') return false;
  return item.type === 'custom' || /^custom_/.test(String(item.id || ''));
}

function visualGenerationReferences(item, kind) {
  if (!item || typeof item !== 'object') return [];
  const customCharacter = kind === 'character' && isCustomVisualItem(item);
  const baseRefs = customCharacter
    ? [item.avatarUrl || item.avatar_url || item.previewUrl || item.preview_url || '']
        .concat(item.referenceImages || item.reference_images || [])
    : [item.avatarUrl || item.avatar_url || item.previewUrl || item.preview_url || '']
        .concat(item.referenceImages || item.reference_images || []);
  const clean = [];
  baseRefs.forEach((url) => {
    const value = String(url || '').trim();
    if (value && !clean.includes(value)) clean.push(value);
  });
  return kind === 'character' ? clean.slice(0, 4) : clean;
}

function visualReferencePayload(item, kind) {
  if (!item || typeof item !== 'object') return {};
  return {
    id: item.id || '',
    name: item.name || '',
    prompt: item.prompt || '',
    references: visualGenerationReferences(item, kind),
    avatarUrl: item.avatarUrl || item.avatar_url || item.previewUrl || item.preview_url || '',
    videoReferenceUrl: item.videoReferenceUrl || item.video_reference_url || '',
    videoReferences: Array.isArray(item.videoReferences) ? item.videoReferences.slice() : (Array.isArray(item.video_references) ? item.video_references.slice() : []),
    heygenPhotoAvatarId: item.heygenPhotoAvatarId || item.heygen_photo_avatar_id || '',
    heygenVideoAvatarId: item.heygenVideoAvatarId || item.heygen_video_avatar_id || '',
    heygenAvatarGroupId: item.heygenAvatarGroupId || item.heygen_avatar_group_id || '',
    heygenDefaultVoiceId: item.heygenDefaultVoiceId || item.heygen_default_voice_id || '',
    heygenLooks: Array.isArray(item.heygenLooks) ? item.heygenLooks.slice() : (Array.isArray(item.heygen_looks) ? item.heygen_looks.slice() : []),
    type: item.type || '',
    custom: isCustomVisualItem(item),
  };
}

function compactStatNumber(value) {
  const num = Number(value || 0);
  if (num >= 1000000) return (num / 1000000).toFixed(num >= 10000000 ? 0 : 1).replace(/\.0$/, '') + 'M';
  if (num >= 1000) return (num / 1000).toFixed(num >= 10000 ? 0 : 1).replace(/\.0$/, '') + 'K';
  return String(num);
}

function characterProfileInfo(item) {
  const prompt = String((item && item.prompt) || '');
  const name = (item && (item.name || item.label)) || '';
  const lowerGender = String((item && item.gender) || '').toLowerCase();
  const ageMatch = prompt.match(/approximately\s+(\d+)\s+years?\s+old/i) || prompt.match(/(\d+)\s+years?\s+old/i);
  const heightMatch = prompt.match(/height\s+of\s+around\s+(\d+\s*cm)/i) || prompt.match(/around\s+(\d+\s*cm)/i);
  const eyesMatch = prompt.match(/([a-z -]+?)\s+(?:almond-shaped\s+)?eyes/i);
  const gender = lowerGender === 'female' ? 'Женский' : (lowerGender === 'male' ? 'Мужской' : 'Не указан');
  const description = String((item && item.description) || '')
    || (prompt.split('.').slice(0, 2).join('.').trim() + (prompt ? '.' : ''))
    || 'Персонаж готов к использованию в генерации.';
  return {
    name,
    description,
    age: ageMatch ? ageMatch[1] : 'Не указан',
    height: heightMatch ? heightMatch[1].replace(/\s+/g, ' ') : 'Не указан',
    eyes: eyesMatch ? eyesMatch[1].replace(/\s+/g, ' ').trim() : 'Не указан',
    gender,
  };
}

function visualCharacterDetailHtml(rawItem, selected) {
  const item = normalizeVisualItem(rawItem) || {};
  const id = String(item.id || '');
  const name = item.name || item.label || id;
  const preview = visualPreviewUrl(item);
  const refs = [item.avatarUrl || item.avatar_url || preview].concat(item.referenceImages || []).filter(Boolean).filter((url, index, arr) => arr.indexOf(url) === index).slice(0, 4);
  const stats = currentVisualStats('character', item);
  const profile = characterProfileInfo(item);
  const rating = Math.max(0, Math.min(10, Math.round((Number(stats.selects || 0) + Number(stats.likes || 0)) / 10)));
  const videoRef = item.videoReferenceUrl || item.video_reference_url || '';
  const likes = Number(stats.likes || 0) + Number((stats.heygen && (stats.heygen.likes || stats.heygen.likes_count || stats.heygen.like_count)) || 0);
  return `
    <div class="visual-character-detail-shell">
      <div class="visual-character-detail-head">
        <button class="visual-character-back" type="button" aria-label="Назад" onclick="SYLVEX.closeCharacterDetail(event)">‹</button>
        <h3>Персонажи</h3>
      </div>
      <div class="visual-character-detail-body">
        <div class="visual-character-media-col">
          <div class="visual-character-main-media">
            ${videoRef
              ? `<video id="visualCharacterVideo" src="${S.escapeHtml(videoRef)}" poster="${S.escapeHtml(preview)}" playsinline preload="metadata"></video><button class="visual-character-play-btn" type="button" aria-label="Play" onclick="SYLVEX.playCharacterReferenceVideo(event)"></button>`
              : (preview ? `<img src="${S.escapeHtml(preview)}" alt="${S.escapeHtml(name)}" loading="lazy" decoding="async" />` : '<span class="image-style-placeholder-icon">S</span>')}
          </div>
          <div class="visual-character-ref-row">
            ${refs.map((url) => `<span><img src="${S.escapeHtml(url)}" alt="" loading="lazy" decoding="async" /></span>`).join('')}
          </div>
        </div>
        <div class="visual-character-info">
          <div class="visual-character-like-count">♥ ${S.escapeHtml(compactStatNumber(likes))}</div>
          <div class="visual-character-title-row">
            <h3>${S.escapeHtml(name)}</h3>
            ${stats.favorite ? '<span class="visual-character-official">★</span>' : ''}
            <span class="visual-character-rating">${rating}/10</span>
          </div>
          <p>${S.escapeHtml(profile.description)}</p>
          <div class="visual-character-specs">
            <span><b>Возраст</b>${S.escapeHtml(profile.age)}</span>
            <span><b>Рост</b>${S.escapeHtml(profile.height)}</span>
            <span><b>Глаза</b>${S.escapeHtml(profile.eyes)}</span>
            <span><b>Пол</b>${S.escapeHtml(profile.gender)}</span>
          </div>
        </div>
      </div>
      <div class="visual-character-actions">
        <button class="visual-character-icon-btn ${stats.favorite ? 'active' : ''}" type="button" aria-label="Избранное" onclick="SYLVEX.sendVisualInteraction('character','${S.escapeHtml(id)}','favorite',undefined,event)">★</button>
        <button class="visual-character-select" type="button" onclick="SYLVEX.pickVisualReference(event,'character','${S.escapeHtml(id)}')">${selected ? 'Выбрано' : 'Выбрать'}</button>
        <button class="visual-character-icon-btn like ${stats.liked ? 'active' : ''}" type="button" aria-label="Лайк" onclick="SYLVEX.sendVisualInteraction('character','${S.escapeHtml(id)}','like',undefined,event)">♥</button>
      </div>
    </div>
  `;
}

function renderCharacterDetail() {
  const detail = document.getElementById('visualCharacterDetail');
  if (!detail || !activeCharacterDetailId) return;
  const item = imageCharacters().map(normalizeVisualItem).find((entry) => entry && entry.id === activeCharacterDetailId);
  if (!item) return;
  const selected = String(imageState.characterId || '') === String(item.id || '');
  detail.innerHTML = visualCharacterDetailHtml(item, selected);
}

function openCharacterDetail(e, id) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  activeCharacterDetailId = String(id || '');
  const panel = ensureImageStylePanel();
  const detail = document.getElementById('visualCharacterDetail');
  renderCharacterDetail();
  if (detail) detail.hidden = false;
  panel.classList.add('has-character-detail');
  const item = imageCharacters().map(normalizeVisualItem).find((entry) => entry && entry.id === activeCharacterDetailId);
  if (item) loadVisualStats('character', item).then(renderCharacterDetail);
}

function closeCharacterDetail(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  activeCharacterDetailId = '';
  const detail = document.getElementById('visualCharacterDetail');
  if (detail) {
    detail.hidden = true;
    detail.innerHTML = '';
  }
  const panel = document.getElementById('imageStylePanel');
  if (panel) panel.classList.remove('has-character-detail');
}

function playCharacterReferenceVideo(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const video = document.getElementById('visualCharacterVideo');
  if (!video) return;
  const btn = e && e.currentTarget ? e.currentTarget : null;
  video.play().then(() => {
    if (btn) btn.hidden = true;
  }).catch(() => {});
}

function deleteResourceKindLabel(kind) {
  if (kind === 'character') return 'персонажа';
  if (kind === 'object') return 'объект';
  if (kind === 'voice') return 'озвучку';
  return 'элемент';
}

function closeResourceDeleteConfirm(result) {
  const modal = document.getElementById('resourceDeleteConfirmModal');
  if (modal) modal.remove();
  const current = resourceDeleteConfirm;
  resourceDeleteConfirm = null;
  if (current && typeof current.resolve === 'function') current.resolve(!!result);
}

function confirmResourceDelete(kind, name) {
  if (resourceDeleteConfirm && typeof resourceDeleteConfirm.resolve === 'function') {
    resourceDeleteConfirm.resolve(false);
  }
  const previousModal = document.getElementById('resourceDeleteConfirmModal');
  if (previousModal) previousModal.remove();
  const modal = document.createElement('div');
  modal.id = 'resourceDeleteConfirmModal';
  modal.className = 'resource-delete-confirm';
  const kindLabel = deleteResourceKindLabel(kind);
  const title = 'Удалить ' + kindLabel + '?';
  const cleanName = String(name || '').trim();
  modal.innerHTML = '<div class="resource-delete-confirm-card" onclick="event.stopPropagation()">'
    + '<div class="resource-delete-confirm-title">' + S.escapeHtml(title) + '</div>'
    + (cleanName ? '<div class="resource-delete-confirm-text">' + S.escapeHtml(cleanName) + '</div>' : '')
    + '<div class="resource-delete-confirm-actions">'
    + '<button class="resource-delete-cancel" type="button" onclick="SYLVEX.closeResourceDeleteConfirm(false)">Отмена</button>'
    + '<button class="resource-delete-action" type="button" onclick="SYLVEX.closeResourceDeleteConfirm(true)">Удалить</button>'
    + '</div>'
    + '</div>';
  modal.onclick = () => closeResourceDeleteConfirm(false);
  document.body.appendChild(modal);
  requestAnimationFrame(() => modal.classList.add('show'));
  S.haptic && S.haptic.impact && S.haptic.impact('light');
  return new Promise((resolve) => {
    resourceDeleteConfirm = { resolve };
  });
}

async function deleteVisualItemFromBackend(kind, id) {
  const tg = getTelegramId();
  if (!tg || !id) return;
  try {
    await fetch('/api/public/prostudio/resources/' + encodeURIComponent(id) + '?telegram_id=' + encodeURIComponent(tg), {
      method: 'DELETE',
      cache: 'no-store',
    });
  } catch (err) {
    console.warn('[SYLVEX] visual resource delete failed', err);
  }
}

async function deleteUserVoice(e, resourceId, voiceId) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const id = String(resourceId || '').trim();
  const voice = String(voiceId || '').trim();
  if (!id || !id.startsWith('custom_voice_')) return;
  const voiceItem = (serverVisualItems.voices || []).find((item) => {
    const itemResourceId = String(item.id || item.resourceId || '');
    const itemVoiceId = String(item.voice_id || item.voiceId || '');
    return itemResourceId === id || itemVoiceId === voice;
  });
  const confirmed = await confirmResourceDelete('voice', (voiceItem && voiceItem.name) || voice);
  if (!confirmed) return;
  serverVisualItems.voices = (serverVisualItems.voices || []).filter((item) => {
    const itemResourceId = String(item.id || item.resourceId || '');
    const itemVoiceId = String(item.voice_id || item.voiceId || '');
    return itemResourceId !== id && itemVoiceId !== voice;
  });
  if (voiceState.elevenlabsVoice === voice) voiceState.elevenlabsVoice = '21m00Tcm4TlvDq8ikWAM';
  if (voiceState.elevenlabsSecondVoice === voice) voiceState.elevenlabsSecondVoice = voiceState.elevenlabsVoice;
  renderVoiceToolPanel();
  renderVoiceControls();
  await deleteVisualItemFromBackend('voice', id);
  toast('Голос удалён');
}

// =====================================================
// JAVASCRIPT-БЛОК: visualCreatePhotoSlot
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function visualCreatePhotoSlot(index) {
  const url = visualCreateDraft.photos[index] || '';
  return '<button class="visual-photo-slot ' + (url ? 'has-photo' : '') + '" type="button" onclick="SYLVEX.pickVisualCreatePhoto(event,' + index + ')">'
    + (url ? '<img src="' + S.escapeHtml(url) + '" alt="" />' : '<span>＋</span><b>Добавить фото</b>')
    + (url ? '<em onclick="SYLVEX.removeVisualCreatePhoto(event,' + index + ')">×</em>' : '')
    + '</button>';
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderVisualCreateModal
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderVisualCreateModal() {
  const modal = ensureVisualCreateModal();
  const kind = visualCreateDraft.kind;
  const isCharacter = kind === 'character';
  const title = isCharacter ? 'Создание персонажа' : 'Создание объекта';
  const nameLabel = isCharacter ? 'Имя *' : 'Название *';
  const namePlaceholder = isCharacter ? 'Введите имя персонажа' : 'Введите название объекта';
  const hint = isCharacter
    ? 'Загрузите до 3 фотографий одного человека с разных ракурсов.'
    : 'Загрузите до 3 фотографий объекта с разных ракурсов.';
  const name = visualCreateDraft.name || '';
  const gender = visualCreateDraft.gender || '';
  const description = visualCreateDraft.description || '';
  const canSave = visualCreateCanSave();
  const busy = !!visualCreateDraft.saving;
  const statusText = visualCreateDraft.statusText || '';
  modal.innerHTML = '<div class="visual-create-card ' + (busy ? 'is-busy' : '') + '">'
    + '<div class="visual-create-head"><button class="visual-create-back" type="button" onclick="SYLVEX.closeVisualCreateModal(event)" ' + (busy ? 'disabled' : '') + ' aria-label="Назад">‹</button><h3>' + title + '</h3></div>'
    + '<label class="visual-field"><span>' + nameLabel + '</span><input id="visualCreateName" value="' + S.escapeHtml(name) + '" placeholder="' + namePlaceholder + '" oninput="SYLVEX.updateVisualCreateDraft(event,\'name\')" ' + (busy ? 'disabled' : '') + ' /></label>'
    + (isCharacter ? '<label class="visual-field"><span>Пол *</span><select id="visualCreateGender" onchange="SYLVEX.updateVisualCreateDraft(event,\'gender\')" ' + (busy ? 'disabled' : '') + '><option value="">Выберите пол</option><option value="male" ' + (gender === 'male' ? 'selected' : '') + '>Мужской</option><option value="female" ' + (gender === 'female' ? 'selected' : '') + '>Женский</option></select></label>' : '')
    + (!isCharacter ? '<label class="visual-field"><span>Описание</span><textarea id="visualCreateDescription" placeholder="Например: чёрные солнцезащитные очки" oninput="SYLVEX.updateVisualCreateDraft(event,\'description\')" ' + (busy ? 'disabled' : '') + '>' + S.escapeHtml(description) + '</textarea></label>' : '')
    + '<div class="visual-photo-grid">' + [0, 1, 2].map(visualCreatePhotoSlot).join('') + '</div>'
    + '<p class="visual-create-hint">' + hint + '<br>Для лучшего результата используйте фото с разных ракурсов и хорошим освещением.</p>'
    + '<button class="visual-create-save" type="button" ' + (canSave && !busy ? '' : 'disabled') + ' onclick="SYLVEX.saveVisualCreateDraft(event)">' + (busy ? 'Создаём...' : (isCharacter ? 'Создать персонажа' : 'Создать объект')) + '</button>'
    + '<input id="visualCreateFileInput" type="file" accept="image/png,image/jpeg,image/webp" hidden />'
    + (busy ? '<div class="visual-create-loading-overlay" role="status" aria-live="polite">'
      + '<div class="visual-create-loading ' + (visualCreateDraft.done ? 'done' : '') + '">'
      + (visualCreateDraft.done ? '<strong>✓</strong>' : '<span></span>')
      + '<b>' + S.escapeHtml(statusText || ((isCharacter ? 'Персонаж ' : 'Объект ') + name + ' создаётся')) + '</b>'
      + (!visualCreateDraft.done ? '<small>Пожалуйста, не закрывайте окно</small>' : '')
      + '</div></div>' : '')
    + '</div>';
  modal.classList.add('show');
}

function visualCreateKindLabel(kind) {
  return kind === 'character' ? 'Персонаж' : 'Объект';
}

function visualCreateListLabel(kind) {
  return kind === 'character' ? 'список персонажей' : 'список объектов';
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openVisualCreateModal
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openVisualCreateModal(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const caps = getModelCapabilities(imageState.modelId);
  if (!isVideoMode() && ((kind === 'character' && !caps.character) || (kind === 'object' && !caps.object))) {
    imageFeatureUnavailableToast(kind === 'character' ? 'character' : 'object');
    return;
  }
  visualCreateDraft = { kind, name: '', gender: '', description: '', photos: [] };
  renderVisualCreateModal();
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeVisualCreateModal
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeVisualCreateModal(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (visualCreateDraft && visualCreateDraft.saving) return;
  const modal = document.getElementById('visualCreateModal');
  if (modal) modal.classList.remove('show');
}

// =====================================================
// JAVASCRIPT-БЛОК: updateVisualCreateDraft
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function updateVisualCreateDraft(e, field) {
  const target = e && e.target;
  visualCreateDraft[field] = target ? target.value : '';
  if (field === 'gender') {
    renderVisualCreateModal();
  } else {
    updateVisualCreateSaveState();
  }
}

// =====================================================
// JAVASCRIPT-БЛОК: visualCreateCanSave
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function visualCreateCanSave() {
  const isCharacter = visualCreateDraft.kind === 'character';
  return String(visualCreateDraft.name || '').trim().length >= 2
    && (!isCharacter || !!visualCreateDraft.gender)
    && (visualCreateDraft.photos || []).filter(Boolean).length > 0;
}

// =====================================================
// JAVASCRIPT-БЛОК: updateVisualCreateSaveState
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function updateVisualCreateSaveState() {
  const btn = document.querySelector('#visualCreateModal .visual-create-save');
  if (btn) btn.disabled = !visualCreateCanSave();
}

// =====================================================
// JAVASCRIPT-БЛОК: pickVisualCreatePhoto
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function pickVisualCreatePhoto(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (visualCreateDraft && visualCreateDraft.saving) return;
  const input = document.getElementById('visualCreateFileInput');
  if (!input) return;
  input.multiple = true;
  input.onchange = () => {
    const files = Array.from(input.files || []);
    input.value = '';
    if (!files.length) return;
    if (visualCreateDraft.photos[index]) visualCreateDraft.photos[index] = '';
    const available = Math.max(0, 3 - (visualCreateDraft.photos || []).filter(Boolean).length + (visualCreateDraft.photos[index] ? 1 : 0));
    if (files.length > available) toast('Можно выбрать не больше 3 фотографий');
    const selected = files.slice(0, available);
    const valid = selected.filter((file) => {
      if (!/^image\/(png|jpeg|webp)$/i.test(file.type || '')) {
        toast('Поддерживаются только JPG, PNG и WEBP');
        return false;
      }
      if (file.size > 10 * 1024 * 1024) {
        toast('Файл слишком большой');
        return false;
      }
      return true;
    });
    Promise.all(valid.map((file) => new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => resolve('');
      reader.readAsDataURL(file);
    }))).then((urls) => {
      let targetIndex = index;
      urls.filter(Boolean).forEach((url) => {
        while (targetIndex < 3 && visualCreateDraft.photos[targetIndex]) targetIndex += 1;
        if (targetIndex >= 3) targetIndex = visualCreateDraft.photos.findIndex((value) => !value);
        if (targetIndex >= 0 && targetIndex < 3) visualCreateDraft.photos[targetIndex] = url;
      });
      renderVisualCreateModal();
    });
  };
  input.click();
}

// =====================================================
// JAVASCRIPT-БЛОК: removeVisualCreatePhoto
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function removeVisualCreatePhoto(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (visualCreateDraft && visualCreateDraft.saving) return;
  visualCreateDraft.photos.splice(index, 1);
  renderVisualCreateModal();
}

function visualCreatePrompt(kind, name, gender, description) {
  if (kind === 'character') {
    const genderText = gender === 'male' ? 'male' : (gender === 'female' ? 'female' : 'neutral');
    return 'Create a clean reusable character reference portrait for "' + name + '". Gender: ' + genderText + '. Preserve the uploaded person identity from the reference photos. Make a polished studio character asset, realistic face, clear body/portrait readability, neutral background, premium Mini App visual catalog style. No text, no watermark.';
  }
  return 'Create a clean reusable object reference asset for "' + name + '". ' + (description ? 'Object description: ' + description + '. ' : '') + 'Preserve the uploaded object identity from the reference photos. Make a polished studio product/object asset, isolated readable shape, neutral background, premium Mini App visual catalog style. No text, no watermark.';
}

async function generateVisualResourceWithOpenAI(kind, name, photos, gender, description) {
  const previousMode = studioMode;
  const previousModelId = imageState.modelId;
  const previousProvider = imageState.provider;
  const previousSize = imageState.size;
  const previousCount = imageState.count;
  const previousStyle = imageState.style;
  studioMode = 'image';
  imageState.modelId = 'gpt_image_1';
  imageState.provider = 'openai';
  imageState.size = '1024x1024';
  imageState.count = 1;
  imageState.style = 'auto';
  try {
    const prompt = visualCreatePrompt(kind, name, gender, description);
    const start = await callGenerate(prompt, null, photos, null, {});
    const result = start && (start.result || start);
    const urls = generatedUrlsFromResponse(result, 'image');
    return urls[0] || photos[0] || '';
  } finally {
    studioMode = previousMode;
    imageState.modelId = previousModelId;
    imageState.provider = previousProvider;
    imageState.size = previousSize;
    imageState.count = previousCount;
    imageState.style = previousStyle;
    if (!activeGeneration.jobId || !isActiveGenerationStatus(activeGeneration.status)) {
      clearActiveProStudioJob(activeGeneration.jobId);
    }
  }
}

async function createHeygenCharacterResource(name, photos, gender, description) {
  const tg = getTelegramId();
  if (!tg) throw new Error('telegram_id_required');
  const res = await fetch('/api/public/prostudio/character', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      telegram_id: tg,
      name,
      gender,
      description,
      photos: (photos || []).slice(0, 3),
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok || !data.resource) {
    throw new Error(translateGenerationError(data, 'Не удалось создать персонажа через OpenAI и HeyGen'));
  }
  return normalizeVisualItem(data.resource) || data.resource;
}

// =====================================================
// JAVASCRIPT-БЛОК: saveVisualCreateDraft
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
async function saveVisualCreateDraft(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const kind = visualCreateDraft.kind;
  const name = String(visualCreateDraft.name || '').trim();
  const photos = (visualCreateDraft.photos || []).filter(Boolean).slice(0, 3);
  if (name.length < 2) return toast(kind === 'character' ? 'Введите имя персонажа' : 'Введите название объекта');
  if (kind === 'character' && !visualCreateDraft.gender) return toast('Выберите пол');
  if (!photos.length) return toast('Добавьте хотя бы одну фотографию');
  if (visualCreateDraft.saving) return;
  const kindLabel = visualCreateKindLabel(kind);
  const listLabel = visualCreateListLabel(kind);
  visualCreateDraft.saving = true;
  visualCreateDraft.done = false;
  visualCreateDraft.statusText = kindLabel + ' ' + name + ' создаётся';
  renderVisualCreateModal();
  await wait(900);
  let generatedPreview = '';
  let providerResource = null;
  try {
    if (kind === 'character') {
      providerResource = await createHeygenCharacterResource(name, photos, visualCreateDraft.gender || '', visualCreateDraft.description || '');
      generatedPreview = visualPreviewUrl(providerResource) || photos[0] || '';
    } else {
      generatedPreview = await generateVisualResourceWithOpenAI(kind, name, photos, visualCreateDraft.gender || '', visualCreateDraft.description || '');
    }
  } catch (err) {
    console.warn('[SYLVEX] visual resource generation failed', err);
    visualCreateDraft.saving = false;
    visualCreateDraft.done = false;
    visualCreateDraft.statusText = '';
    renderVisualCreateModal();
    return toast(translateGenerationError(err, kind === 'character' ? 'Не удалось создать персонажа' : 'Не удалось создать объект'));
  }
  visualCreateDraft.statusText = kindLabel + ' ' + name + ' сохраняется';
  renderVisualCreateModal();
  await wait(900);
  const id = (providerResource && providerResource.id) || ((kind === 'character' ? 'custom_character_' : 'custom_object_') + Date.now());
  const references = [generatedPreview].concat(photos).filter(Boolean);
  const item = Object.assign({
    id,
    name,
    gender: visualCreateDraft.gender || '',
    description: visualCreateDraft.description || '',
    previewUrl: generatedPreview || photos[0],
    referenceImages: references,
    sourceImages: photos,
    ai_provider: kind === 'character' ? 'openai+heygen' : 'openai',
    ai_model: kind === 'character' ? 'gpt-image-2' : 'gpt-image-1',
    provider: kind === 'character' ? 'heygen' : 'openai',
    model: kind === 'character' ? 'gpt-image-2' : 'gpt-image-1',
    type: 'custom',
    status: 'ready',
    created_at: new Date().toISOString(),
  }, providerResource || {});
  const storageKind = kind === 'character' ? 'characters' : 'objects';
  const savedItem = await saveVisualItemToBackend(kind, item);
  Object.assign(item, normalizeVisualItem(savedItem || item) || {});
  if (serverVisualItems[storageKind]) {
    serverVisualItems[storageKind] = serverVisualItems[storageKind].filter((entry) => entry.id !== item.id);
    serverVisualItems[storageKind].unshift(item);
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: items
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const items = loadCustomVisualItems(storageKind).filter((entry) => entry && entry.id !== item.id);
  items.unshift(item);
  saveCustomVisualItems(storageKind, items);
  if (isVideoMode()) {
    applyVisualReferenceToVideo(item, kind);
  } else if (kind === 'character') {
    imageState.characterId = item.id;
    imageState.characterName = item.name;
    imageState.characterReferences = item.referenceImages.slice();
  } else {
    imageState.objectId = item.id;
    imageState.objectName = item.name;
    imageState.objectReferences = item.referenceImages.slice();
    imageState.objects = item.name;
  }
  renderImageReferenceSections();
  renderImageControls();
  renderImageStylePanel();
  renderVideoReferencesPreview();
  visualCreateDraft.done = true;
  visualCreateDraft.statusText = kindLabel + ' ' + name + ' создан и сохранён в ' + listLabel;
  renderVisualCreateModal();
  toast(visualCreateDraft.statusText);
  await wait(2400);
  visualCreateDraft.saving = false;
  closeVisualCreateModal(e);
  closeVisualPicker(e);
  closeImageStylePanel(e);
}

function applyVisualReferenceToVideo(item, kind) {
  if (!item) return;
  const refs = visualGenerationReferences(item, kind);
  const url = refs[0] || '';
  if (!url) return;
  videoState.characterImage = kind === 'character' ? url : videoState.characterImage;
  const visual = Object.assign(visualReferencePayload(item, kind), {
    kind: kind === 'object' ? 'object' : 'character',
    previewUrl: item.previewUrl || item.avatarUrl || url,
  });
  if (kind === 'object') {
    videoState.objectVisual = visual;
  } else {
    videoState.characterVisual = visual;
    videoState.characterImage = url;
  }
  videoState.referenceVisual = visual;
  renderVideoReferencesPreview();
}

async function deleteVisualReference(e, kind, id) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const list = kind === 'character' ? imageCharacters() : imageObjects();
  const item = list.find((entry) => entry && entry.id === id);
  if (!isCustomVisualItem(item)) return;
  const confirmed = await confirmResourceDelete(kind === 'object' ? 'object' : 'character', item.name || item.label || id);
  if (!confirmed) return;
  const storageKind = kind === 'character' ? 'characters' : 'objects';
  const refs = (item.referenceImages || []).concat(item.previewUrl ? [item.previewUrl] : []).filter(Boolean);
  if (serverVisualItems[storageKind]) {
    serverVisualItems[storageKind] = serverVisualItems[storageKind].filter((entry) => entry && entry.id !== id);
  }
  const localItems = loadCustomVisualItems(storageKind).filter((entry) => entry && entry.id !== id && isCustomVisualItem(entry));
  saveCustomVisualItems(storageKind, localItems);
  if (kind === 'character' && imageState.characterId === id) clearSelectedCharacter();
  if (kind === 'object' && imageState.objectId === id) clearSelectedObject();
  if (isVideoMode() && kind === 'character' && videoState.characterVisual && videoState.characterVisual.id === id) {
    videoState.characterVisual = null;
    videoState.characterImage = '';
    setCurrentVideoReferenceImages(currentVideoReferenceImages().filter((url) => !refs.includes(url)));
  }
  if (isVideoMode() && kind === 'object' && videoState.objectVisual && videoState.objectVisual.id === id) {
    videoState.objectVisual = null;
    setCurrentVideoReferenceImages(currentVideoReferenceImages().filter((url) => !refs.includes(url)));
  }
  if (isVideoMode() && videoState.referenceVisual && videoState.referenceVisual.id === id) videoState.referenceVisual = null;
  renderImageStylePanel();
  renderImageReferenceSections();
  renderImageControls();
  renderVideoReferencesPreview();
  await deleteVisualItemFromBackend(kind, id);
  toast(kind === 'character' ? 'Персонаж удалён' : 'Объект удалён');
}

// =====================================================
// JAVASCRIPT-БЛОК: pickVisualReference
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function pickVisualReference(e, kind, id) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const caps = getModelCapabilities(imageState.modelId);
  if (!isVideoMode() && kind === 'character' && !caps.character) return imageFeatureUnavailableToast('character');
  if (!isVideoMode() && kind === 'object' && !caps.object) return imageFeatureUnavailableToast('object');
  const list = kind === 'character' ? imageCharacters() : imageObjects();
  // =====================================================
  // JAVASCRIPT-БЛОК: item
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const item = list.find((entry) => entry.id === id);
  if (!item) return;
  if (isVideoMode()) {
    applyVisualReferenceToVideo(item, kind);
    if (kind === 'character') sendVisualInteraction('character', item.id, 'select');
    closeVisualPicker(e);
    closeImageStylePanel(e);
    updateSendButton();
    toast(kind === 'character' ? 'Персонаж добавлен' : 'Объект добавлен');
    return;
  }
  if (kind === 'character') {
    if (imageState.characterId === item.id) {
      clearSelectedCharacter();
    } else {
      imageState.characterId = item.id;
      imageState.characterName = item.name;
      imageState.characterReferences = (item.referenceImages || []).slice();
      sendVisualInteraction('character', item.id, 'select');
    }
  } else {
    if (imageState.objectId === item.id) {
      clearSelectedObject();
    } else {
      imageState.objectId = item.id;
      imageState.objectName = item.name;
      imageState.objectReferences = (item.referenceImages || []).slice();
      imageState.objects = item.name;
    }
  }
  renderImageReferenceSections();
  closeVisualPicker(e);
  closeImageStylePanel(e);
  updateSendButton();
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoStartUpload
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openVideoStartUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.VIDEO_START, e);
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoEndUpload
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openVideoEndUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.VIDEO_END, e);
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoReferencesUpload
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openVideoReferencesUpload(e) {
  closeVideoAddMenu();
  openUploadTarget(UPLOAD_TARGETS.VIDEO_REFERENCES, e);
}

function openVideoEditInputUpload(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  setUploadTarget(UPLOAD_TARGETS.VIDEO_EDIT_INPUT);
  openNativeFilePicker('video');
}

function closeVideoAddMenu() {
  const menu = document.getElementById('videoAddMenu');
  const button = document.getElementById('videoReferencesUploadButton');
  if (menu) menu.hidden = true;
  if (button) button.classList.remove('is-add-menu-open');
}

function toggleVideoAddMenu(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const menu = document.getElementById('videoAddMenu');
  const button = document.getElementById('videoReferencesUploadButton');
  if (!menu) return;
  const nextOpen = !!menu.hidden;
  menu.hidden = !nextOpen;
  if (button) button.classList.toggle('is-add-menu-open', nextOpen);
  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

function chooseVideoAddMedia(e) {
  closeVideoAddMenu();
  openVideoReferencesUpload(e);
}

function chooseVideoAddCharacter(e) {
  closeVideoAddMenu();
  openVideoVisualPicker(e, 'character');
}

function chooseVideoAddObject(e) {
  closeVideoAddMenu();
  openVideoVisualPicker(e, 'object');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: aggressiveUploadTargetClickGuard
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function aggressiveUploadTargetClickGuard(e) {
  const target = e && e.target ? e.target : null;
  if (!target || !target.closest) return;
  if (!target.closest('#videoAddMenu') && !target.closest('#videoReferencesUploadButton')) closeVideoAddMenu();
  if (target.closest('#uploadPanel')) return;
  if (target.closest('#modelPop')) return;
  if (target.closest('#imageStylePanel')) return;
  if (target.closest('#plusSheet')) return;
  const btn = target.closest('[data-upload-target]');
  if (!btn) return;
  const uploadTarget = btn.dataset.uploadTarget;
  if (!Object.values(UPLOAD_TARGETS).includes(uploadTarget)) return;
  setUploadTarget(uploadTarget);
}

if (!window.__sylvexUploadTargetGuardInstalled) {
  window.__sylvexUploadTargetGuardInstalled = true;
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('click', aggressiveUploadTargetClickGuard, true);
}

// =====================================================
// ЗАГРУЗКА В MINI APP: currentModeAttachment
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function currentModeAttachment() {
  if (isVideoMode()) return videoState.attachment || null;
  if (isMusicMode() || isVoiceMode()) return currentAudioState().attachment || null;
  if (isImageMode()) return imageState.attachment || null;
  if (studioMode === 'text') {
    return textState.attachment && !textState.attachment.uploading ? textState.attachment : null;
  }
  return pendingAttachment;
}

// =====================================================
// ЗАГРУЗКА В MINI APP: setCurrentModeAttachment
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function setCurrentModeAttachment(attachment) {
  if (isVideoMode()) {
    videoState.attachment = attachment || null;
  } else if (isMusicMode() || isVoiceMode()) {
    currentAudioState().attachment = attachment || null;
  } else if (isImageMode()) {
    imageState.attachment = attachment || null;
  } else if (studioMode === 'text') {
    textState.attachment = attachment || null;
  } else {
    pendingAttachment = attachment || null;
  }
  pendingAttachment = currentModeAttachment();
}

// =====================================================
// ЗАГРУЗКА В MINI APP: currentSelectedUploadImage
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function currentSelectedUploadImage() {
  const target = getUploadTarget();

  if (target === UPLOAD_TARGETS.VIDEO_START) return videoState.startImage || '';
  if (target === UPLOAD_TARGETS.VIDEO_END) return videoState.endImage || '';
  if (target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) return '';
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) return (currentVideoReferenceImages()[0]) || '';
  if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) return imageState.referenceImageUrl || ((imageState.referenceImageUrls || [])[0]) || '';

  const images = currentUploadImages();
  return images[images.length - 1] || '';
}

  // =====================================================
  // JAVASCRIPT-БЛОК: injectImageStyleSheetCss
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function injectImageStyleSheetCss() {
  if (styleSheetCssInjected) return;
  styleSheetCssInjected = true;

  const style = document.createElement('style');
  style.id = 'sylvexImageStyleSheetCss';
  style.textContent = `
    .has-style-preview {
      position: relative;
      overflow: hidden;
      isolation: isolate;
      background-image:
        linear-gradient(180deg, rgba(0,0,0,.18), rgba(0,0,0,.58)),
        var(--image-style-bg) !important;
      background-size: cover !important;
      background-position: center !important;
      background-repeat: no-repeat !important;
      border-color: rgba(255,255,255,.22) !important;
    }

    .has-style-preview::before {
      content: '';
      position: absolute;
      inset: 0;
      z-index: -1;
      background: radial-gradient(circle at 50% 15%, rgba(255,255,255,.22), rgba(0,0,0,0) 45%);
      pointer-events: none;
    }

    .has-style-preview > * {
      position: relative;
      z-index: 1;
    }

    .has-style-preview #imageStyleVal {
      color: #fff;
      text-shadow: 0 1px 8px rgba(0,0,0,.85);
      font-weight: 800;
    }

    .model-brand-logo {
      width: 22px;
      height: 22px;
      display: block;
      object-fit: contain;
      filter: brightness(0) invert(1);
      opacity: .96;
    }

    .image-model-icon {
      width: 32px;
      height: 32px;
      flex: 0 0 32px;
      display: grid;
      place-items: center;
      background: transparent;
      color: #f3f3f3;
    }

    .image-model-icon img {
      width: 22px;
      height: 22px;
    }

    .model-row-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-left: 10px;
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .04em;
      white-space: nowrap;
      vertical-align: middle;
    }

    .model-row-badge.pink {
      background: rgba(255, 120, 210, .2);
      color: #ff9bdd;
    }

    .model-row-badge.yellow {
      background: rgba(255, 220, 90, .18);
      color: #ffe05e;
    }

    .model-row-badge.red {
      background: rgba(255, 100, 80, .18);
      color: #ff826d;
    }

    .model-row-badge.green {
      background: rgba(70, 220, 150, .18);
      color: #61e6ad;
    }

    .has-upload-preview {
      position: relative;
      overflow: hidden;
      isolation: isolate;
      border-color: rgba(255,255,255,.22) !important;
      color: #fff !important;
      text-shadow: 0 1px 8px rgba(0,0,0,.88);
      font-weight: 800;
    }

    .image-upload-control-bg {
      position: absolute;
      inset: 0;
      z-index: 0;
      display: grid;
      gap: 0;
      overflow: hidden;
      pointer-events: none;
      border-radius: inherit;
    }

    .image-upload-control-bg[data-count="1"] {
      grid-template-columns: 1fr;
      grid-template-rows: 1fr;
    }

    .image-upload-control-bg[data-count="2"] {
      grid-template-columns: repeat(2, 1fr);
      grid-template-rows: 1fr;
    }

    .image-upload-control-bg[data-count="3"],
    .image-upload-control-bg[data-count="4"] {
      grid-template-columns: repeat(2, 1fr);
      grid-template-rows: repeat(2, 1fr);
    }

    .image-upload-control-bg-cell {
      position: relative;
      display: block;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }

    .image-upload-control-bg-cell img,
    .image-upload-control-bg-cell video {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }

    .image-upload-control-bg-cell em {
      position: absolute;
      left: 8px;
      top: 8px;
      z-index: 2;
      min-width: 32px;
      height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: rgba(22,119,255,.86);
      color: #fff;
      font-style: normal;
      font-size: 10px;
      font-weight: 900;
    }

    .has-upload-preview::before {
      content: '';
      position: absolute;
      inset: 0;
      z-index: 1;
      background: linear-gradient(180deg, rgba(0,0,0,.18), rgba(0,0,0,.62));
      pointer-events: none;
    }

    .has-upload-preview > *:not(.image-upload-control-bg) {
      position: relative;
      z-index: 2;
    }

    .image-style-panel-backdrop {
      position: fixed;
      inset: 0;
      display: none;
      align-items: flex-end;
      justify-content: center;
      background: rgba(0, 0, 0, .62);
      z-index: 999999;
    }

    .image-style-panel-backdrop.show {
      display: flex;
    }

    .image-style-panel-card {
      position: relative;
      width: 100%;
      max-height: 74vh;
      overflow: hidden;
      background: #111;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 24px 24px 0 0;
      box-shadow: 0 -20px 60px rgba(0,0,0,.55);
      padding: 14px 14px calc(18px + env(safe-area-inset-bottom));
      animation: imageStylePanelUp .22s ease both;
    }

    @keyframes imageStylePanelUp {
      from { transform: translateY(100%); }
      to { transform: translateY(0); }
    }

    .image-style-panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 2px 2px 14px;
    }

    .image-style-panel-title {
      color: #fff;
      font-size: 17px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

   .image-style-info-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.image-style-info-wrap[hidden] {
  display: none !important;
}

.image-style-info-mark {
  width: 21px;
  height: 21px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(255,255,255,.1);
  border: 1px solid rgba(255,255,255,.24);
  color: #fff;
  font-size: 14px;
  font-weight: 900;
  line-height: 1;
  box-shadow: 0 0 18px rgba(255,255,255,.12);
  animation: styleInfoWiggle 1.45s ease-in-out infinite;
  transform-origin: 50% 80%;
  cursor: pointer;
  padding: 0;
  appearance: none;
  -webkit-appearance: none;
}

.image-style-info-tooltip {
  position: absolute;
  left: 50%;
  top: 32px;
  width: min(280px, calc(100vw - 42px));
  transform: translateX(-50%) translateY(-4px);
  display: none;
  z-index: 3;
  padding: 12px 13px;
  border-radius: 15px;
  background: rgba(20,20,20,.96);
  border: 1px solid rgba(255,255,255,.12);
  box-shadow: 0 16px 42px rgba(0,0,0,.45);
  color: rgba(255,255,255,.86);
  font-size: 12px;
  line-height: 1.35;
  font-weight: 500;
  letter-spacing: -.01em;
}

.image-style-info-tooltip.show {
  display: block;
  animation: styleInfoTooltipIn .16s ease both;
}

@keyframes styleInfoTooltipIn {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(-4px);
  }
}

    @keyframes styleInfoWiggle {
      0%, 100% { transform: rotate(0deg) translateY(0); }
      10% { transform: rotate(-10deg) translateY(-1px); }
      20% { transform: rotate(9deg) translateY(0); }
      30% { transform: rotate(-7deg) translateY(-1px); }
      40% { transform: rotate(6deg) translateY(0); }
      50% { transform: rotate(0deg) translateY(0); }
    }

    @media (prefers-reduced-motion: reduce) {
      .image-style-info-mark {
        animation: none;
      }
    }

    .image-style-panel-close {
      width: 34px;
      height: 34px;
      border: 0;
      border-radius: 999px;
      background: rgba(255,255,255,.08);
      color: #fff;
      font-size: 24px;
      line-height: 34px;
      cursor: pointer;
    }

    .image-style-panel-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      max-height: calc(74vh - 70px);
      overflow-y: auto;
      padding: 0 2px 4px;
      -webkit-overflow-scrolling: touch;
    }

    .image-style-card {
      position: relative;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 16px;
      background: rgba(255,255,255,.045);
      color: #fff;
      padding: 6px;
      cursor: pointer;
      overflow: hidden;
    }

    .image-style-card.selected {
      border-color: rgba(255,255,255,.9);
      background: rgba(255,255,255,.12);
    }

    .image-style-thumb {
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      border-radius: 12px;
      overflow: hidden;
      background: linear-gradient(135deg, rgba(255,255,255,.12), rgba(255,255,255,.03));
    }

    .image-style-thumb img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }

    .image-style-thumb.is-placeholder {
      display: grid;
      place-items: center;
      color: rgba(255,255,255,.46);
    }

    .image-style-placeholder-icon {
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 12px;
      background: rgba(255,255,255,.08);
      color: rgba(255,255,255,.72);
      font-size: 14px;
      font-weight: 900;
      letter-spacing: .02em;
    }

    .image-style-label {
      display: block;
      padding: 7px 2px 1px;
      color: rgba(255,255,255,.82);
      font-size: 11px;
      line-height: 1.15;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .image-style-check {
      position: absolute;
      top: 10px;
      right: 10px;
      width: 22px;
      height: 22px;
      display: none;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: #fff;
      color: #111;
      font-size: 13px;
      font-weight: 900;
    }

    .image-style-card.selected .image-style-check {
      display: flex;
    }

    .visual-delete-btn {
      position: absolute;
      top: 8px;
      left: 8px;
      width: 24px;
      height: 24px;
      border: 0;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: rgba(0,0,0,.72);
      color: #fff;
      font: 900 18px/1 inherit;
      cursor: pointer;
      z-index: 5;
    }

    .visual-delete-btn:active {
      transform: scale(.94);
    }

    .visual-character-detail {
      position: absolute;
      inset: 0;
      z-index: 8;
      padding: 18px 22px calc(20px + env(safe-area-inset-bottom));
      background: rgba(28,28,28,.98);
      color: #fff;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }

    .visual-character-detail[hidden] {
      display: none !important;
    }

    .visual-character-detail-shell {
      min-height: 100%;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .visual-character-detail-head {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .visual-character-back {
      width: 44px;
      height: 44px;
      border: 0;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: rgba(255,255,255,.12);
      color: #fff;
      font: 900 42px/1 inherit;
      cursor: pointer;
      padding: 0 0 5px;
    }

    .visual-character-detail-head h3 {
      margin: 0;
      font-size: 32px;
      line-height: 1;
      font-weight: 900;
    }

    .visual-character-detail-body {
      display: grid;
      grid-template-columns: minmax(118px, 170px) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }

    .visual-character-media-col {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      width: min(100%, 170px);
    }

    .visual-character-main-media {
      position: relative;
      width: 100%;
      max-width: 170px;
      aspect-ratio: 4 / 5;
      border-radius: 18px;
      overflow: hidden;
      background: #2d2d2d;
      border: 2px solid rgba(255,255,255,.45);
    }

    .visual-character-main-media img,
    .visual-character-main-media video {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }

    .visual-character-play-btn {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 44px;
      height: 44px;
      transform: translate(-50%, -50%);
      border: 0;
      border-radius: 50%;
      background: rgba(255,255,255,.72);
      cursor: pointer;
    }

    .visual-character-play-btn::before {
      content: "";
      position: absolute;
      left: 18px;
      top: 12px;
      border-left: 15px solid rgba(30,30,30,.92);
      border-top: 10px solid transparent;
      border-bottom: 10px solid transparent;
    }

    .visual-character-ref-row {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }

    .visual-character-ref-row span {
      aspect-ratio: 3 / 4;
      overflow: hidden;
      background: #333;
      display: block;
      border-radius: 6px;
    }

    .visual-character-ref-row img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
      object-position: center top;
    }

    .visual-character-info {
      position: relative;
      min-height: 250px;
      border: 2px solid rgba(255,255,255,.34);
      border-radius: 18px;
      padding: 12px;
      background: rgba(255,255,255,.025);
    }

    .visual-character-like-count {
      position: absolute;
      right: 12px;
      top: -28px;
      min-width: 54px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border-radius: 7px;
      background: #ff1749;
      color: #fff;
      font-size: 13px;
      font-weight: 900;
    }

    .visual-character-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .visual-character-title-row h3 {
      margin: 0;
      font-size: 24px;
      line-height: 1;
      font-weight: 900;
    }

    .visual-character-official {
      color: #ffd45a;
      font-size: 18px;
    }

    .visual-character-rating {
      margin-left: auto;
      color: rgba(255,255,255,.9);
      font-size: 14px;
      white-space: nowrap;
    }

    .visual-character-info p {
      margin: 10px 0 12px;
      color: rgba(255,255,255,.86);
      font-size: 13px;
      line-height: 1.35;
    }

    .visual-character-specs {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .visual-character-specs span {
      border-radius: 10px;
      background: rgba(255,255,255,.06);
      padding: 8px 9px;
      font-size: 12px;
      color: #fff;
    }

    .visual-character-specs b {
      display: block;
      margin-bottom: 3px;
      color: rgba(255,255,255,.55);
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 800;
    }

    .visual-character-actions {
      margin-top: auto;
      display: grid;
      grid-template-columns: 50px minmax(150px, 210px) 50px;
      justify-content: center;
      align-items: center;
      gap: 14px;
      padding-top: 18px;
    }

    .visual-character-icon-btn {
      width: 48px;
      height: 48px;
      border: 0;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: rgba(255,255,255,.08);
      color: #f7c84a;
      font: 900 24px/1 inherit;
      cursor: pointer;
    }

    .visual-character-icon-btn.like {
      color: #ff315f;
    }

    .visual-character-icon-btn.active {
      background: #f7c84a;
      color: #171717;
    }

    .visual-character-icon-btn.like.active {
      background: #ff315f;
      color: #fff;
    }

    .visual-character-select {
      height: 48px;
      border: 0;
      border-radius: 999px;
      background: linear-gradient(180deg, #6885ff, #3f61da);
      color: #fff;
      font: 900 22px/1 inherit;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(40,80,230,.34);
    }

    @media (max-width: 370px) {
      .image-style-panel-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (min-width: 641px) {
      .image-style-panel-backdrop {
        align-items: center;
        padding: calc(18px + env(safe-area-inset-top)) 18px calc(18px + env(safe-area-inset-bottom));
        background: rgba(0, 0, 0, .56);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
      }

      .image-style-panel-card {
        width: min(720px, calc(100vw - 36px));
        max-height: min(76vh, 680px);
        border-radius: 24px;
        padding: 14px;
        background: rgba(18,18,24,.88);
        border: 1px solid rgba(255,255,255,.10);
        box-shadow: 0 28px 90px rgba(0,0,0,.72);
        backdrop-filter: blur(22px) saturate(140%);
        -webkit-backdrop-filter: blur(22px) saturate(140%);
        animation: imageStylePanelCenter .18s ease both;
      }

      .image-style-panel-backdrop.has-character-detail .image-style-panel-card {
        width: min(540px, calc(100vw - 36px));
        max-height: min(78vh, 680px);
      }

      .image-style-panel-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        max-height: calc(min(76vh, 680px) - 70px);
        gap: 8px;
      }

      .image-style-card {
        border-radius: 13px;
        padding: 5px;
      }

      .image-style-thumb {
        border-radius: 10px;
      }

      .visual-character-detail {
        padding: 14px;
        border-radius: 24px;
        background: rgba(18,18,24,.96);
      }

      .visual-character-detail-shell {
        min-height: auto;
      }
    }

    @media (min-width: 641px) and (max-width: 900px) {
      .image-style-panel-card {
        width: min(600px, calc(100vw - 28px));
      }

      .image-style-panel-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }

    @keyframes imageStylePanelCenter {
      from { opacity: 0; transform: translateY(14px) scale(.985); }
      to { opacity: 1; transform: none; }
    }

    @media (max-width: 640px) {
      .visual-character-detail {
        padding: 18px 18px calc(20px + env(safe-area-inset-bottom));
      }
      .visual-character-detail-body {
        grid-template-columns: 1fr;
      }
      .visual-character-detail-head h3 {
        font-size: 30px;
      }
      .visual-character-ref-row {
        gap: 10px;
      }
      .visual-character-actions {
        grid-template-columns: 46px minmax(140px, 190px) 46px;
      }
    }
  `;

  document.head.appendChild(style);
}

// =====================================================
// JAVASCRIPT-БЛОК: ensureImageStylePanel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function ensureImageStylePanel() {
  injectImageStyleSheetCss();

  let panel = document.getElementById('imageStylePanel');
  if (panel) return panel;

  panel = document.createElement('div');
  panel.id = 'imageStylePanel';
  panel.className = 'image-style-panel-backdrop';
  panel.onclick = closeImageStylePanel;

  panel.innerHTML = `
    <div class="image-style-panel-card" onclick="event.stopPropagation()">
      <div class="image-style-panel-head">
        <div class="image-style-panel-title">
            <span id="imageStylePanelTitle">Выбери стиль</span>
            <span id="imageStyleInfoWrap" class="image-style-info-wrap">
              <button class="image-style-info-mark" type="button" aria-label="Информация о стилях" onclick="SYLVEX.toggleImageStyleInfo(event)">!</button>
              <span id="imageStyleInfoTooltip" class="image-style-info-tooltip">
                Стили универсальны: их можно применять не только к людям, но и к предметам, животным, машинам, интерьерам, городам, пейзажам и любым другим сценам. Выберите стиль, загрузите фото или опишите идею — SYLVEX применит выбранное визуальное направление ко всей генерации.
              </span>
            </span>
          </div>
        <button class="image-style-panel-close" type="button" onclick="SYLVEX.closeImageStylePanel(event)">×</button>
      </div>
      <div id="imageStylePanelGrid" class="image-style-panel-grid"></div>
      <div id="visualCharacterDetail" class="visual-character-detail" hidden></div>
    </div>
  `;

  document.body.appendChild(panel);
  return panel;
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderImageStylePanel
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderImageStylePanel() {
  const grid = document.getElementById('imageStylePanelGrid');
  if (!grid) return;

  const kind = activeImageStylePanelKind || 'style';
  const title = document.getElementById('imageStylePanelTitle');
  const info = document.getElementById('imageStyleInfoWrap');
  if (title) {
    title.textContent = kind === 'character'
      ? 'Выбери персонажа'
      : (kind === 'object' ? 'Выбери объект' : 'Выбери стиль');
  }
  if (info) info.hidden = kind !== 'style';

  const selectedStyle = String(imageState.style || 'auto');
  const selectedCharacter = String(imageState.characterId || '');
  const selectedObject = String(imageState.objectId || '');

  if (kind === 'style') {
    grid.classList.remove('visual-character-grid');
    grid.innerHTML = IMAGE_STYLE_SHEET_ITEMS.map((item) => {
      const id = String(item.id || '');
      const label = item.label || id;
      const image = item.image || '';
      const selected = selectedStyle === id;

      return `
        <button class="image-style-card ${selected ? 'selected' : ''}" type="button" onclick="SYLVEX.pickImageStyleFromPanel(event, '${S.escapeHtml(id)}')">
          <span class="image-style-thumb">
            ${image ? `<img src="${S.escapeHtml(image)}" alt="${S.escapeHtml(label)}" loading="lazy" decoding="async" />` : '<span class="visual-picker-placeholder">＋</span>'}
          </span>
          <span class="image-style-label">${S.escapeHtml(label)}</span>
          <span class="image-style-check">✓</span>
        </button>
      `;
    }).join('');
    return;
  }

  const isCharacter = kind === 'character';
  const items = isCharacter ? imageCharacters() : imageObjects();
  const selectedId = isCharacter ? selectedCharacter : selectedObject;
  const createLabel = isCharacter ? 'Новый персонаж' : 'Новый объект';
  const createKind = isCharacter ? 'character' : 'object';
  const createCard = `
    <button class="image-style-card" type="button" onclick="SYLVEX.openVisualCreateModal(event, '${createKind}')">
      <span class="image-style-thumb is-placeholder">
        <span class="image-style-placeholder-icon">+</span>
      </span>
      <span class="image-style-label">${S.escapeHtml(createLabel)}</span>
      <span class="image-style-check">✓</span>
    </button>
  `;

  if (isCharacter) {
    grid.classList.remove('visual-character-grid');
    grid.innerHTML = createCard + items.map((rawItem) => {
      const item = normalizeVisualItem(rawItem) || {};
      const id = String(item.id || '');
      const label = item.name || item.label || id;
      const preview = visualPreviewUrl(item);
      const selected = selectedId === id;
      const canDelete = isCustomVisualItem(item);
      return `
        <div class="image-style-card ${selected ? 'selected' : ''}" role="button" tabindex="0" onclick="SYLVEX.openCharacterDetail(event, '${S.escapeHtml(id)}')">
          <span class="image-style-thumb ${preview ? '' : 'is-placeholder'}" aria-hidden="true">
            ${preview ? `<img src="${S.escapeHtml(preview)}" alt="${S.escapeHtml(label)}" loading="lazy" decoding="async" />` : '<span class="image-style-placeholder-icon"></span>'}
          </span>
          <span class="image-style-label">${S.escapeHtml(label)}</span>
          <span class="image-style-check">✓</span>
          ${canDelete ? `<button class="visual-delete-btn" type="button" aria-label="Удалить" onclick="SYLVEX.deleteVisualReference(event, '${createKind}', '${S.escapeHtml(id)}')">×</button>` : ''}
        </div>
      `;
    }).join('');
    return;
  }

  grid.classList.remove('visual-character-grid');
  grid.innerHTML = createCard + items.map((rawItem) => {
    const item = normalizeVisualItem(rawItem) || {};
    const id = String(item.id || '');
    const label = item.name || item.label || id;
    const preview = visualPreviewUrl(item);
    const selected = selectedId === id;
    const canDelete = isCustomVisualItem(item);

    return `
      <div class="image-style-card ${selected ? 'selected' : ''}" role="button" tabindex="0" onclick="SYLVEX.pickVisualReference(event, '${createKind}', '${S.escapeHtml(id)}')">
        <span class="image-style-thumb ${preview ? '' : 'is-placeholder'}" aria-hidden="true">
          ${preview ? `<img src="${S.escapeHtml(preview)}" alt="${S.escapeHtml(label)}" loading="lazy" decoding="async" />` : '<span class="image-style-placeholder-icon"></span>'}
        </span>
        <span class="image-style-label">${S.escapeHtml(label)}</span>
        <span class="image-style-check">✓</span>
        ${canDelete ? `<button class="visual-delete-btn" type="button" aria-label="Удалить" onclick="SYLVEX.deleteVisualReference(event, '${createKind}', '${S.escapeHtml(id)}')">×</button>` : ''}
      </div>
    `;
  }).join('');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openImageStylePanel
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openImageStylePanel(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const nextKind = kind || 'style';
  if (nextKind === 'character' || nextKind === 'object') {
    const caps = getModelCapabilities(imageState.modelId);
    if (nextKind === 'character' && !caps.character) return imageFeatureUnavailableToast('character');
    if (nextKind === 'object' && !caps.object) return imageFeatureUnavailableToast('object');
  }

  activeImageStylePanelKind = nextKind;
  const panel = ensureImageStylePanel();
  renderImageStylePanel();
  panel.classList.add('show');
  if (nextKind === 'character' || nextKind === 'object') {
    loadPresetCatalog(true).then(() => {
      if (activeImageStylePanelKind === nextKind && panel.classList.contains('show')) renderImageStylePanel();
    }).catch(() => {});
  }

  const mp = document.getElementById('modelPop');
  if (mp) mp.classList.remove('show');

  const sheet = document.getElementById('plusSheet');
  if (sheet) sheet.classList.remove('show');

  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }

  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeImageStylePanel
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeImageStylePanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  hideImageStyleInfo();
  closeCharacterDetail();

  const panel = document.getElementById('imageStylePanel');
  if (panel) panel.classList.remove('show');
}

// =====================================================
// JAVASCRIPT-БЛОК: hideImageStyleInfo
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function hideImageStyleInfo() {
  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (tooltip) tooltip.classList.remove('show');
}

// =====================================================
// JAVASCRIPT-БЛОК: handleImageStyleInfoOutsideTouch
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function handleImageStyleInfoOutsideTouch(e) {
  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (!tooltip || !tooltip.classList.contains('show')) return;

  const target = e && e.target ? e.target : null;

  // Сам восклицательный знак не закрывает подсказку через общий обработчик,
  // потому что он сам открывает/закрывает её через toggleImageStyleInfo.
  if (target && target.closest && target.closest('.image-style-info-mark')) return;

  hideImageStyleInfo();
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleImageStyleInfo
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function toggleImageStyleInfo(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (!tooltip) return;

  tooltip.classList.toggle('show');
}

// =====================================================
// JAVASCRIPT-БЛОК: pickImageStyleFromPanel
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function pickImageStyleFromPanel(e, value) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  hideImageStyleInfo();

  imageState.style = value || 'auto';

  renderImageControls();
  renderImageStylePanel();
  closeImageStylePanel(e);

  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

// =====================================================
// JAVASCRIPT-БЛОК: imageModelIconKey
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function imageModelIconKey(model) {
  const id = String(model && model.id ? model.id : '');

  if (id.includes('nano-banana')) return 'nn';
  if (id.includes('gpt-image')) return 'chatgptImage';
  if (id.includes('seedream')) return 'cdrm';
  if (id.includes('grok-pro')) return 'grokPro';
  if (id === 'grok') return 'grokPro';
  if (id.includes('flux')) return 'grokFlux';
  if (id.includes('ideogram')) return 'idrm';
  if (id.includes('recraft')) return 'craft';
  if (id.includes('qwen')) return 'queen';
  if (id.includes('microsoft')) return 'microsoft';
  if (id.includes('krea')) return 'craft';

  return 'nn';
}

// =====================================================
// JAVASCRIPT-БЛОК: imageModelIconHtml
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function imageModelIconHtml(model) {
  const key = model && (model.icon || model.iconKey)
    ? String(model.icon || model.iconKey)
    : imageModelIconKey(model);

  const iconValue = AI_LOGOS[key] || AI_LOGOS.openai;

  if (iconValue === 'custom-banana') {
    return '<svg class="model-brand-logo svg-current" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
      + '<path d="M4.4 15.5C8.6 15.9 13.2 13.9 15.7 10.1C16.8 8.4 17.3 6.6 17.4 4.9C17.5 3.8 19.1 3.6 19.5 4.7C21.5 11.2 16.7 18.8 9.8 19.7C7.6 20 5.5 19.6 3.8 18.7C2.5 18 3 15.3 4.4 15.5Z" fill="currentColor" />'
      + '<path d="M4.6 15.8C7.2 15.2 9.4 13.9 11.1 11.8" stroke="#141518" stroke-width="1.4" stroke-linecap="round" />'
      + '<path d="M17.3 5.2L15.7 3.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />'
      + '</svg>';
  }

  return '<img class="model-brand-logo" src="' + S.escapeHtml(iconValue) + '" alt="" loading="lazy" decoding="async" />';
}

function updateComposerModelDisplay(model) {
  if (!model) return;
  const label = model.label || model.name || model.id || '';
  const labelEl = document.getElementById('modelValComposer');
  const iconEl = document.getElementById('modelIconComposer');
  if (labelEl) labelEl.textContent = label;
  if (iconEl) iconEl.innerHTML = imageModelIconHtml(model);
}

// =====================================================
// JAVASCRIPT-БЛОК: imageModelDescription
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function imageModelDescription(model) {
  if (!model) return 'AI-модель для генерации изображений.';
  return model.description || model.desc || model.subtitle || model.note || 'AI-модель для генерации изображений.';
}

// =====================================================
// JAVASCRIPT-БЛОК: imageModelButton
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function imageModelButton(model) {
  const activeId = isImageMode()
    ? imageState.modelId
    : (isMusicMode() ? musicState.modelId : (isVoiceMode() ? voiceState.modelId : (studioMode === 'text' ? textState.modelId : videoState.modelId)));

  const id = String(model && model.id ? model.id : '');
  const active = activeId === id;
  const desc = model.desc || model.description || '';
  // Badges are kept in model data for later, but hidden in the current UI.
  const badge = '';

  return '<button class="image-model-row ' + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickImageOption(event,\'model\',\'' + S.escapeHtml(id) + '\')">'
    + '<span class="image-model-icon">' + imageModelIconHtml(model) + '</span>'
    + '<span class="image-model-text">'
    + '<span class="image-model-name">' + S.escapeHtml(model.label || model.name || id) + badge + '</span>'
    + (desc ? '<span class="image-model-desc">' + S.escapeHtml(desc) + '</span>' : '')
    + '</span>'
    + '<span class="image-model-check">✓</span>'
    + '</button>';
}

  // =====================================================
  // JAVASCRIPT-БЛОК: applyImageDefaults
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyImageDefaults(model) {
    if (!model) return;
    imageState.modelId = model.id;
    imageState.size = (model.sizes && model.sizes[0] && model.sizes[0].id) || '';
    imageState.count = (model.counts && model.counts[0]) || 1;
    imageState.style = (model.styles && model.styles[0] && model.styles[0].id) || 'auto';
    imageState.character = (model.characters && model.characters[0] && model.characters[0].id) || 'auto';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: syncImageModelOptionDefaults
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function syncImageModelOptionDefaults(model) {
    const cfg = model || currentImageModel();
    if (!cfg) return;
    const sizes = cfg.sizes && cfg.sizes.length ? cfg.sizes : [];
    if (sizes.length && !sizes.some((item) => item.id === imageState.size)) {
      imageState.size = sizes[0].id;
    }
    const counts = cfg.counts && cfg.counts.length ? cfg.counts : [1, 2, 3, 4];
    if (!counts.includes(Number(imageState.count || 1))) {
      imageState.count = counts[0] || 1;
    }
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderImageControls
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderImageControls() {
    const model = currentImageModel();
    if (!model) return;
    syncImageModelOptionDefaults(model);
    if (isImageMode()) updateComposerModelDisplay(model);
    const sizeOptions = model.sizes && model.sizes.length ? model.sizes : [
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
    ];
    const selectedSizeId = imageState.size || '1:1';
    // =====================================================
    // JAVASCRIPT-БЛОК: size
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const size = sizeOptions.find((item) => item.id === selectedSizeId) || sizeOptions[0];
    const sizeVal = document.getElementById('imageSizeVal');
    if (sizeVal && size) sizeVal.textContent = size.label || size.ratio || size.id;
    const sizeIcon = document.getElementById('imageSizeIcon');
    if (sizeIcon && size) {
      const isAutoSize = String(size.id || size.ratio || '').toLowerCase() === 'auto';
      sizeIcon.hidden = isAutoSize;
      if (!isAutoSize) sizeIcon.setAttribute('data-ratio', size.ratio || size.id || '1:1');
    }
    const countVal = document.getElementById('imageCountVal');
    if (countVal) countVal.textContent = String(imageState.count || 1);
    const styleVal = document.getElementById('imageStyleVal');
    if (styleVal) {
      const selectedStyleItem = imageStyleSheetItem(imageState.style);
      styleVal.textContent = imageState.style === 'auto' ? 'Стили' : optionLabel(model.styles, imageState.style, 'Стили');
      updateImageStyleButtonPreview(selectedStyleItem);
    }
    const characterVal = document.getElementById('imageCharacterVal');
    if (characterVal) characterVal.textContent = 'Персонаж';
    renderImageReferenceSections();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: normalizeImageSeed
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function normalizeImageSeed(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const seed = Number(raw);
    if (!Number.isSafeInteger(seed) || seed < 0) {
      throw new Error('Seed должен быть целым положительным числом');
    }
    return seed;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageSeedInputValue
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageSeedInputValue() {
    return imageState.seed === null || imageState.seed === undefined ? '' : String(imageState.seed);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: currentRecraftTools
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function currentRecraftTools() {
    const model = currentImageModel() || {};
    return Array.isArray(model.recraftTools) ? model.recraftTools.slice() : [];
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageOptionsPayload
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageOptionsPayload(referenceImages) {
    const capabilities = getModelCapabilities(imageState.modelId);
    const seed = capabilities.seed ? normalizeImageSeed(imageState.seed) : null;
    return Object.assign({}, imageState, {
      seed,
      referenceImageUrls: (referenceImages || []).slice(),
      referenceImages: (referenceImages || []).slice(),
    }, imageVisualReferenceOptions());
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: sanitizeImageSeedInput
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function sanitizeImageSeedInput(value) {
    return String(value || '').replace(/\D+/g, '');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: onImageSeedInput
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function onImageSeedInput(e) {
    const input = e && e.currentTarget ? e.currentTarget : document.getElementById('imageSeedInput');
    if (!input) return;
    const clean = sanitizeImageSeedInput(input.value);
    if (input.value !== clean) input.value = clean;
    imageState.seed = clean ? clean : null;
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleImageSeedTooltip
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleImageSeedTooltip(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const tip = document.getElementById('imageSeedTooltip');
    if (!tip) return;
    tip.hidden = !tip.hidden;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: resetImageSettings
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function resetImageSettings(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    imageState.seed = null;
    openImageOptionMenu(e, 'seed');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeImageSeedTooltipOnOutside
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeImageSeedTooltipOnOutside(e) {
    const tip = document.getElementById('imageSeedTooltip');
    if (!tip || tip.hidden) return;
    const btn = document.getElementById('imageSeedInfoBtn');
    if (tip.contains(e.target) || (btn && btn.contains(e.target))) return;
    tip.hidden = true;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: loadImageCapabilities
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function loadImageCapabilities() {
    try {
      const res = await fetch('/api/public/prostudio/image-capabilities', { cache: 'no-store' });
      const data = await res.json();
      imageCapabilities = mergeImageModels((data && data.models) || []);
      if (!imageState.modelId && IMAGE_MODEL_LIST.length) {
        imageState.modelId = IMAGE_MODEL_LIST[0].id;
      }
      renderImageControls();
      renderModelPop();
    } catch (err) {
      console.warn('[SYLVEX] image capabilities failed', err);
    }
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openImageOptionMenu
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openImageOptionMenu(e, kind) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    if (kind === 'model') {
      showImageModelPicker(e);
      return;
    }

    if (isImageMode() && kind === 'character') {
      openImageStylePanel(e, 'character');
      return;
    }

    if (isImageMode() && kind === 'objects') {
      openImageStylePanel(e, 'object');
      return;
    }

    if (studioMode === 'text') {
      if (kind === 'model') {
        showImageModelPicker(e);
        return;
      }

      const el = document.getElementById('modelPop');
      if (!el) return;
      const openTextSheet = (title, items, optionKind, activeValue) => {
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.remove('image-model-floating-pop');
        el.classList.remove('music-settings-pop');
        el.classList.remove('video-option-horizontal-pop');
        el.classList.add('image-size-floating-pop');
        el.style.position = 'fixed';
        el.style.left = '8px';
        el.style.right = 'auto';
        el.style.top = 'auto';
        el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
        el.style.width = '72vw';
        el.style.maxWidth = '350px';
        el.style.minWidth = '250px';
        el.style.maxHeight = '68vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';
        el.innerHTML = '<div class="image-size-sheet-title">' + S.escapeHtml(title) + '</div>'
          + '<div class="image-size-sheet-list">'
          + items.map((item) => {
            const id = String(item.id || '');
            const active = String(activeValue || '') === id;
            return '<button class="image-size-row no-ratio-icon ' + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickTextOption(event,\'' + optionKind + '\',\'' + S.escapeHtml(id) + '\')">'
              + '<span class="image-size-label">' + S.escapeHtml(item.label || id) + '</span>'
              + '<span class="image-size-check">✓</span>'
              + '</button>';
          }).join('')
          + '</div>';
        el.classList.add('show');
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
        S.haptic && S.haptic.impact && S.haptic.impact('light');
      };

      if (kind === 'text_tool') {
        openTextSheet('Инструмент текста', textToolOptionsForCurrentModel(), 'tool', textState.tool || 'text');
        return;
      }
      if (kind === 'text_version') {
        openTextSheet('Версия модели', textVersionsForFamily(textState.familyId || textModelFamilyId(currentTextModel())), 'model_version', textState.modelId || 'gpt-5.5');
        return;
      }
      if (kind === 'text_style') {
        openTextSheet('Стиль текста', TEXT_STYLE_OPTIONS, 'style', textState.style || 'neutral');
        return;
      }
      if (kind === 'text_format') {
        openTextSheet('Формат результата', TEXT_FORMAT_OPTIONS, 'format', textState.format || 'markdown');
        return;
      }
      return;
    }

    if (isVoiceMode()) {
      const el = document.getElementById('modelPop');
      if (!el) return;
      ensureVoiceSettings();
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('voice-general-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';

      const openVoiceSheet = (title, items, optionKind, activeValue) => {
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.add('image-size-floating-pop');
        el.classList.add('voice-general-settings-pop');
        el.style.position = 'fixed';
        el.style.left = '50%';
        el.style.right = 'auto';
        el.style.top = '50%';
        el.style.bottom = 'auto';
        el.style.transform = 'translate(-50%,-50%)';
        el.style.width = 'calc(100vw - 28px)';
        el.style.maxWidth = '420px';
        el.style.minWidth = '250px';
        el.style.maxHeight = '68vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';
        el.innerHTML = '<div class="image-size-sheet-title">' + S.escapeHtml(title) + '</div>'
          + '<div class="image-size-sheet-list">'
          + items.map((item) => {
            const id = String(item.id || '');
            const active = String(activeValue || '') === id;
            const safeId = S.escapeHtml(id);
            const disabled = !!item.disabled || item.available === false;
            const isVoiceChoice = ['voice', 'runwayVoice', 'secondVoice', 'elevenlabsVoice', 'elevenlabsSecondVoice', 'voiceSpeaker1', 'voiceSpeaker2', 'voiceSpeaker3', 'voiceSpeaker4', 'voiceSpeaker5', 'voiceSpeaker6', 'voiceSpeaker7'].includes(optionKind);
            const previewButton = !disabled && isVoiceChoice
              ? '<button class="voice-preview-play" type="button" aria-label="Прослушать ' + safeId + '" data-voice-id="' + safeId + '" onclick="SYLVEX.previewGeminiVoice(event,\'' + safeId + '\')">▶</button>'
              : '';
            const provider = isElevenLabsVoiceModel(voiceState.modelId) ? 'elevenlabs' : (isRunwayVoiceModel(voiceState.modelId) ? 'runway' : 'gemini');
            const avatarUrl = isVoiceChoice ? voiceAvatarUrlFor(item, provider) : '';
            const avatar = isVoiceChoice ? '<span class="voice-style-row-avatar ' + (avatarUrl ? '' : 'is-generated') + ' voice-sheet-avatar" style="' + S.escapeHtml(voiceAvatarStyle(id || item.label)) + '">' + (avatarUrl ? '<img src="' + S.escapeHtml(avatarUrl) + '" alt="" loading="lazy" decoding="async">' : '<span class="voice-generated-initials">' + S.escapeHtml(voiceInitials(item.label || id)) + '</span>') + '</span>' : '';
            const labelContent = isVoiceChoice
              ? '<span class="voice-style-row-copy"><b>' + S.escapeHtml(item.label || id) + '</b><small>' + S.escapeHtml(voiceDescription(item)) + '</small></span>'
              : '<span class="image-size-label">' + S.escapeHtml(item.label || id) + '</span>';
            return '<div class="image-size-row no-ratio-icon voice-preview-row ' + (active ? 'active sel ' : '') + (disabled ? 'disabled ' : '') + '">'
              + '<button class="voice-preview-pick" type="button" ' + (disabled ? 'disabled aria-disabled="true"' : 'onclick="SYLVEX.pickVoiceOption(event,\'' + optionKind + '\',\'' + safeId + '\')"') + '>'
              + avatar + labelContent
              + '<span class="image-size-check">' + (disabled ? '—' : '✓') + '</span>'
              + '</button>'
              + previewButton
              + '</div>';
          }).join('')
          + '</div>';
        el.classList.add('show');
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
        S.haptic && S.haptic.impact && S.haptic.impact('light');
      };

      if (kind === 'voice_upload_purpose') {
        const items = VOICE_UPLOAD_PURPOSES.map((item) => {
          const supported = isVoicePurposeSupported(item);
          return Object.assign({}, item, {
            label: item.label + (supported ? '' : ' · недоступно'),
            disabled: !supported,
          });
        });
        openVoiceSheet('Цель загрузки', items, 'voiceUploadPurpose', voiceState.uploadPurpose || 'voiceover');
        return;
      }
      if (kind === 'voice_upload_language') {
        openVoiceSheet('Язык перевода', RUNWAY_DUBBING_LANGUAGES, 'voiceTargetLanguage', voiceState.targetLanguage || 'en');
        return;
      }
      if (kind === 'voice_speaker_count') {
        const maxSpeakers = isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2;
        const items = VOICE_SPEAKER_COUNT_OPTIONS.map((item) => Object.assign({}, item, { disabled: Number(item.id) > maxSpeakers }));
        openVoiceSheet('Количество дикторов', items, 'voiceSpeakerCount', String(voiceState.numSpeakers || 1));
        return;
      }
      if (/^voice_speaker_[1-7]$/.test(kind)) {
        const index = Math.max(0, Number(kind.slice(-1)) - 1);
        const optionKind = 'voiceSpeaker' + (index + 1);
        const activeVoice = voiceSpeakerVoiceValue(index);
        const selectedByOtherSpeakers = new Set(Array.from({ length: Number(voiceState.numSpeakers || 1) }, (_, speakerIndex) => speakerIndex === index ? '' : voiceSpeakerVoiceValue(speakerIndex)).filter(Boolean).map(String));
        const availableVoices = currentVoiceListForPanel().filter((item) => !selectedByOtherSpeakers.has(String(item.id || item.voice_id || '')));
        const openSpeakerSheet = () => openVoiceSheet('Диктор ' + (index + 1), availableVoices, optionKind, activeVoice);
        if (isElevenLabsVoiceModel(voiceState.modelId)) {
          loadElevenLabsVoices(true).then(() => {
            if (isVoiceMode()) openSpeakerSheet();
          });
        } else if (isRunwayVoiceModel(voiceState.modelId)) {
          loadRunwayVoices(true).then(() => {
            if (isVoiceMode()) openSpeakerSheet();
          });
        }
        openSpeakerSheet();
        return;
      }
      if (kind === 'voice') {
        if (isElevenLabsVoiceModel(voiceState.modelId)) {
          loadElevenLabsVoices(true).then(() => {
            if (isVoiceMode() && isElevenLabsVoiceModel(voiceState.modelId)) {
              openVoiceSheet('Голос ElevenLabs', elevenlabsVoiceList, 'elevenlabsVoice', voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM');
            }
          });
          openVoiceSheet('Голос ElevenLabs', elevenlabsVoiceList, 'elevenlabsVoice', voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM');
        } else if (isRunwayVoiceModel(voiceState.modelId)) {
          loadRunwayVoices(true).then(() => {
            if (isVoiceMode() && isRunwayVoiceModel(voiceState.modelId)) {
              openVoiceSheet('Голос Runway', runwayVoiceList, 'runwayVoice', voiceState.runwayVoice || 'Maya');
            }
          });
          openVoiceSheet('Голос Runway', runwayVoiceList, 'runwayVoice', voiceState.runwayVoice || 'Maya');
        } else {
          openVoiceSheet('Голос озвучки', GEMINI_TTS_VOICES, 'voice', voiceState.voice || 'Kore');
        }
        return;
      }
      if (kind === 'duration' || kind === 'speaker_mode') {
        if (isElevenLabsVoiceModel(voiceState.modelId)) {
          openVoiceSheet('Инструмент ElevenLabs', ELEVENLABS_AUDIO_TOOLS, 'elevenlabsTool', voiceState.elevenlabsTool || 'text_to_speech');
          return;
        }
        if (isRunwayVoiceModel(voiceState.modelId)) {
          openVoiceSheet('Инструмент Runway', RUNWAY_AUDIO_TOOLS, 'runwayTool', voiceState.runwayTool || 'text_to_speech');
          return;
        }
        openVoiceSheet('Режим озвучки', VOICE_SPEAKER_MODES, 'speakerMode', voiceState.speakerMode || 'single');
        return;
      }
      if (kind === 'settings') {
        const isElevenLabs = isElevenLabsVoiceModel(voiceState.modelId);
        const isRunway = isRunwayVoiceModel(voiceState.modelId);
        const activeVoiceLabel = isElevenLabs ? 'ElevenLabs Voice' : (isRunway ? (voiceState.runwayVoice || 'Maya') : (voiceState.voice || 'Kore'));
        const elevenlabsTool = voiceState.elevenlabsTool || 'text_to_speech';
        const elevenlabsToolRow = isElevenLabs
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;speaker_mode&quot;)"><span class="image-size-label">Инструмент ElevenLabs</span><span class="image-size-check">' + S.escapeHtml(elevenlabsToolLabel(elevenlabsTool)) + '</span></button>'
          : '';
        const elevenlabsVoiceRow = isElevenLabs && !['voice_design', 'dubbing'].includes(elevenlabsTool)
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;voice&quot;)"><span class="image-size-label">Основной голос</span><span class="image-size-check">' + S.escapeHtml(activeVoiceLabel) + '</span></button>'
          : '';
        const elevenlabsSecondVoiceRow = isElevenLabs && elevenlabsTool === 'dialogue'
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;second_voice&quot;)"><span class="image-size-label">Второй голос</span><span class="image-size-check">ElevenLabs Voice</span></button>'
          : '';
        const elevenlabsLanguageRow = isElevenLabs && elevenlabsTool === 'dubbing'
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;elevenlabs_language&quot;)"><span class="image-size-label">Язык перевода</span><span class="image-size-check">' + S.escapeHtml(voiceState.elevenlabsTargetLanguage || 'en') + '</span></button>'
          : '';
        const runwayTool = voiceState.runwayTool || 'text_to_speech';
        const runwayToolRow = isRunway
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;speaker_mode&quot;)"><span class="image-size-label">Инструмент Runway</span><span class="image-size-check">' + S.escapeHtml(runwayToolLabel(runwayTool)) + '</span></button>'
          : '';
        const runwayLanguageRow = isRunway && runwayTool === 'voice_dubbing'
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;runway_language&quot;)"><span class="image-size-label">Язык дубляжа</span><span class="image-size-check">' + S.escapeHtml(voiceState.runwayTargetLanguage || 'en') + '</span></button>'
          : '';
        const runwayDurationRow = isRunway && runwayTool === 'sound_effect'
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;runway_duration&quot;)"><span class="image-size-label">Длительность</span><span class="image-size-check">' + S.escapeHtml(String(voiceState.runwayDuration || 5)) + ' сек</span></button>'
          : '';
        const runwayVoiceRow = isRunway && !['voice_dubbing', 'voice_isolation', 'sound_effect'].includes(runwayTool)
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;voice&quot;)"><span class="image-size-label">Основной голос</span><span class="image-size-check">' + S.escapeHtml(activeVoiceLabel) + '</span></button>'
          : '';
        const secondVoiceRow = (!isRunway && !isElevenLabs && voiceState.speakerMode === 'multi')
          ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;second_voice&quot;)"><span class="image-size-label">Второй голос</span><span class="image-size-check">' + S.escapeHtml(voiceState.secondVoice || 'Puck') + '</span></button>'
          : '';
        const modeRow = (isRunway || isElevenLabs) ? '' : '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;speaker_mode&quot;)"><span class="image-size-label">Режим</span><span class="image-size-check">' + (voiceState.speakerMode === 'multi' ? 'Два голоса' : 'Один голос') + '</span></button>';
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.add('image-size-floating-pop');
        el.classList.add('music-settings-pop');
        el.classList.add('voice-general-settings-pop');
        el.style.position = 'fixed';
        el.style.left = '50%';
        el.style.right = 'auto';
        el.style.top = '50%';
        el.style.bottom = 'auto';
        el.style.transform = 'translate(-50%,-50%)';
        el.style.width = 'calc(100vw - 28px)';
        el.style.maxWidth = '420px';
        el.style.minWidth = '275px';
        el.style.maxHeight = '70vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';
        el.innerHTML = '<div class="image-size-sheet-title">Настройки озвучки</div>'
          + '<div class="image-size-sheet-list">'
          + elevenlabsToolRow
          + elevenlabsVoiceRow
          + elevenlabsSecondVoiceRow
          + elevenlabsLanguageRow
          + runwayToolRow
          + (isRunway ? runwayVoiceRow : (isElevenLabs ? '' : '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,&quot;voice&quot;)"><span class="image-size-label">Основной голос</span><span class="image-size-check">' + S.escapeHtml(activeVoiceLabel) + '</span></button>'))
          + runwayLanguageRow
          + runwayDurationRow
          + modeRow
          + secondVoiceRow
          + '</div>';
        el.classList.add('show');
        return;
      }
      if (kind === 'runway_language') {
        openVoiceSheet('Язык дубляжа', RUNWAY_DUBBING_LANGUAGES, 'runwayTargetLanguage', voiceState.runwayTargetLanguage || 'en');
        return;
      }
      if (kind === 'elevenlabs_language') {
        openVoiceSheet('Язык перевода', RUNWAY_DUBBING_LANGUAGES, 'elevenlabsTargetLanguage', voiceState.elevenlabsTargetLanguage || 'en');
        return;
      }
      if (kind === 'runway_duration') {
        openVoiceSheet('Длительность эффекта', RUNWAY_SOUND_DURATIONS, 'runwayDuration', String(voiceState.runwayDuration || 5));
        return;
      }
      if (kind === 'second_voice') {
        if (isElevenLabsVoiceModel(voiceState.modelId)) {
          loadElevenLabsVoices(true).then(() => {
            if (isVoiceMode() && isElevenLabsVoiceModel(voiceState.modelId)) {
              openVoiceSheet('Второй голос ElevenLabs', elevenlabsVoiceList, 'elevenlabsSecondVoice', voiceState.elevenlabsSecondVoice || voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM');
            }
          });
          openVoiceSheet('Второй голос ElevenLabs', elevenlabsVoiceList, 'elevenlabsSecondVoice', voiceState.elevenlabsSecondVoice || voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM');
        } else {
          openVoiceSheet('Второй голос', GEMINI_TTS_VOICES, 'secondVoice', voiceState.secondVoice || 'Puck');
        }
        return;
      }
      return;
    }

    if (isMusicMode()) {
      const el = document.getElementById('modelPop');
      if (!el) return;
      ensureMusicSettings();

      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';

      // =====================================================
      // ОБРАБОТЧИК ИНТЕРФЕЙСА: openMusicSheet
      // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
      // =====================================================
      const openMusicSheet = (title, items, optionKind, activeValue) => {
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.add('image-size-floating-pop');
        el.style.position = 'fixed';
        el.style.left = '8px';
        el.style.right = 'auto';
        el.style.top = 'auto';
        el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
        el.style.width = '64vw';
        el.style.maxWidth = '315px';
        el.style.minWidth = '245px';
        el.style.maxHeight = '64vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';
        el.innerHTML = '<div class="image-size-sheet-title">' + S.escapeHtml(title) + '</div>'
          + '<div class="image-size-sheet-list">'
          + items.map((item) => {
            const id = String(item.id || '');
            const active = String(activeValue || 'auto') === id;
            return '<button class="image-size-row no-ratio-icon ' + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickMusicOption(event,\'' + optionKind + '\',\'' + S.escapeHtml(id) + '\')">'
              + '<span class="image-size-label">' + S.escapeHtml(item.label || id) + '</span>'
              + '<span class="image-size-check">✓</span>'
              + '</button>';
          }).join('')
          + '</div>';
        el.classList.add('show');
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
        S.haptic && S.haptic.impact && S.haptic.impact('light');
      };

      if (kind === 'genre') {
        openMusicSheet('Жанр', MUSIC_GENRES, 'genre', musicState.genre || 'auto');
        return;
      }

      if (kind === 'music_duration') {
        openMusicDurationWheel(e);
        return;
      }

      if (kind === 'settings') {
        openMusicSettingsModal(e);
        return;
      }

      return;
    }

    if (isVideoMode()) {
      const el = document.getElementById('modelPop');
      if (!el) return;
      normalizeVideoStateForModel();
      const config = currentVideoConfig();

      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';

      // =====================================================
      // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeOtherSheets
      // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
      // =====================================================
      const closeOtherSheets = () => {
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      };

      // =====================================================
      // ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoSheet
      // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
      // =====================================================
      const openVideoSheet = (title, items, optionKind) => {
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.add('image-size-floating-pop');
        el.classList.remove('video-option-horizontal-pop');
        el.style.position = 'fixed';
        el.style.left = '8px';
        el.style.right = 'auto';
        el.style.top = 'auto';
        el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
        el.style.width = '64vw';
        el.style.maxWidth = '315px';
        el.style.minWidth = '245px';
        el.style.maxHeight = '64vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';

        el.innerHTML = '<div class="image-size-sheet-title">' + S.escapeHtml(title) + '</div>'
          + '<div class="image-size-sheet-list">'
          + items.map((item) => {
            const id = String(item.id || '');
            const label = item.label || id;
            const active = String(item.active || '') === id;
            const icon = optionKind === 'ratio' && id.toLowerCase() !== 'auto'
              ? '<span class="image-size-icon" data-ratio="' + S.escapeHtml(id) + '"></span>'
              : '';
            return '<button class="image-size-row ' + (icon ? 'has-ratio-icon ' : 'no-ratio-icon ') + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickImageOption(event,\'' + optionKind + '\',\'' + S.escapeHtml(id) + '\')">'
              + icon
              + '<span class="image-size-label">' + S.escapeHtml(label) + '</span>'
              + '<span class="image-size-check">✓</span>'
              + '</button>';
          }).join('')
          + '</div>';

        el.classList.add('show');
        closeOtherSheets();
        S.haptic && S.haptic.impact && S.haptic.impact('light');
      };

      if (kind === 'size' || kind === 'ratio') {
        const active = videoState.ratio || '16:9';
        openVideoSheet('Формат видео', labelItems(config.ratios || ['16:9'], '').map((item) => Object.assign(item, { active })), 'ratio');
        return;
      }

      if (kind === 'count' || kind === 'duration') {
        const active = String(videoState.duration || 5);
        openVideoSheet('Длительность', labelItems(config.durations || [5], 'сек').map((item) => Object.assign(item, { active })), 'duration');
        return;
      }

      if (kind === 'resolution') {
        const active = videoState.resolution || '720p';
        openVideoSheet('Разрешение', labelItems(config.resolutions || ['720p'], '').map((item) => Object.assign(item, { active })), 'resolution');
        return;
      }

      if (kind === 'sound') {
        if (!config.sound) {
          toast('Эта модель не поддерживает звук');
          return;
        }
        pickVideoOption('sound', 'toggle');
        renderModelPop();
        S.haptic && S.haptic.impact && S.haptic.impact('light');
        return;
      }

      if (kind === 'style') {
        const active = videoState.generationMode || videoState.mode || 'text_to_video';
        const labels = {
          text_to_video: 'Text to Video',
          image_to_video: 'Image to Video',
          video_to_video: 'Video to Video',
          video_edit: 'Video Edit',
          motion_control: 'Motion Control'
        };
        openVideoSheet('Режим видео', (config.modes || ['text_to_video']).map((id) => ({ id, label: labels[id] || id, active })), 'mode');
        return;
      }

      if (kind === 'character') {
        const active = videoState.quality || 'standard';
        openVideoSheet('Качество', [
          { id:'standard', label:'Standard', active },
          { id:'high', label:'High', active },
          { id:'pro', label:'Pro', active }
        ], 'quality');
        return;
      }

      if (kind === 'objects') {
        const active = videoState.motionPreset || '';
        openVideoSheet('Движение', VIDEO_MOTION_PRESETS.map((id) => ({ id, label: id, active })), 'motion_preset');
        return;
      }

      return;
    }

    if (kind === 'count') {
      // Количество фото — отдельная настройка только генерации изображений.
      // Не зависит от видео, музыки, текущей модели и общих списков моделей.
      if (studioMode !== 'image') return;

      imageState.count = nextImageCountValue();
      renderImageControls();
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }
    if (kind === 'settings') {
      const el = document.getElementById('modelPop');
      if (!el) return;
      const showSeedSettings = !hidesSeedSettings(imageState.modelId);
      const seedRowHtml = showSeedSettings
        ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,\'seed\')">'
          + '<span class="image-size-label"><span class="image-seed-hex">⬢</span> Seed</span>'
          + '<span class="image-size-check">›</span>'
          + '</button>'
        : '';
      if (el.parentElement !== document.body) document.body.appendChild(el);
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.classList.add('image-seed-pop');
      el.style.cssText = '';
      el.style.position = 'fixed';
      el.style.left = '8px';
      el.style.right = 'auto';
      el.style.top = 'auto';
      el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
      el.style.width = '70vw';
      el.style.maxWidth = '320px';
      el.style.minWidth = '245px';
      el.style.zIndex = '999999';
      el.innerHTML = '<div class="image-size-sheet-title">Settings</div>'
        + '<div class="image-size-sheet-list">'
        + seedRowHtml
        + (currentRecraftTools().length ? '<button class="image-size-row image-seed-row" type="button" onclick="SYLVEX.openImageOptionMenu(event,\'recraft_tools\')">'
          + '<span class="image-size-label"><span class="image-seed-hex">R</span> Функции Recraft</span>'
          + '<span class="image-size-check">›</span>'
          + '</button>' : '')
        + '</div>';
      el.classList.add('show');
      const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
      const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }
    if (kind === 'recraft_tools') {
      const tools = currentRecraftTools();
      const el = document.getElementById('modelPop');
      if (!el) return;
      if (el.parentElement !== document.body) document.body.appendChild(el);
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.classList.add('image-seed-pop');
      el.style.cssText = '';
      el.style.position = 'fixed';
      el.style.left = '8px';
      el.style.right = 'auto';
      el.style.top = 'auto';
      el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
      el.style.width = '78vw';
      el.style.maxWidth = '360px';
      el.style.minWidth = '270px';
      el.style.zIndex = '999999';
      el.innerHTML = '<div class="image-seed-head">'
        + '<button class="image-seed-back" type="button" aria-label="Back" onclick="SYLVEX.openImageOptionMenu(event,\'settings\')">‹</button>'
        + '<span>Функции Recraft</span>'
        + '</div>'
        + '<div class="image-size-sheet-list">'
        + tools.map((tool) => '<div class="image-size-row image-seed-row recraft-tool-row">'
          + '<span class="image-size-label">' + S.escapeHtml(tool.label || tool.id) + '</span>'
          + '<span class="image-size-check">' + S.escapeHtml(String(tool.costCredits || 0)) + ' ⚡</span>'
          + '</div>').join('')
        + '</div>';
      el.classList.add('show');
      const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
      const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }
    if (kind === 'seed') {
      const seedSupported = !!getModelCapabilities(imageState.modelId).seed;
      const el = document.getElementById('modelPop');
      if (!el) return;
      if (el.parentElement !== document.body) document.body.appendChild(el);
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.classList.add('image-seed-pop');
      el.style.cssText = '';
      el.style.position = 'fixed';
      el.style.left = '8px';
      el.style.right = 'auto';
      el.style.top = 'auto';
      el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
      el.style.width = '72vw';
      el.style.maxWidth = '340px';
      el.style.minWidth = '260px';
      el.style.zIndex = '999999';
      el.innerHTML = '<div class="image-seed-head">'
        + '<button class="image-seed-back" type="button" aria-label="Back" onclick="SYLVEX.openImageOptionMenu(event,\'settings\')">‹</button>'
        + '<span>Seed</span>'
        + '<button class="image-seed-info" id="imageSeedInfoBtn" type="button" aria-label="Seed info" onclick="SYLVEX.toggleImageSeedTooltip(event)">ⓘ</button>'
        + '<div class="image-seed-tooltip" id="imageSeedTooltip" hidden>Use a specific seed value to reproduce the same image. Leave empty for random generation.</div>'
        + '</div>'
        + '<input class="image-seed-input" id="imageSeedInput" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" placeholder="' + (seedSupported ? 'Enter seed value' : 'Seed is not supported') + '" value="' + S.escapeHtml(seedSupported ? imageSeedInputValue() : '') + '" oninput="SYLVEX.onImageSeedInput(event)"' + (seedSupported ? '' : ' disabled') + ' />'
        + (seedSupported ? '' : '<div class="image-seed-disabled-note">Seed недоступен для выбранной модели</div>')
        + '<button class="music-settings-clear" type="button" onclick="SYLVEX.resetImageSettings(event)">Сбросить настройки</button>';
      el.classList.add('show');
      const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
      const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      const input = document.getElementById('imageSeedInput');
      if (input && seedSupported) setTimeout(() => input.focus(), 60);
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }
    if (kind === 'style') {
      openImageStylePanel(e, 'style');
      return;
    }
    const model = currentImageModel();
    const el = document.getElementById('modelPop');
    if (!el) return;

    el.classList.remove('image-model-floating-pop');
    el.classList.remove('image-size-floating-pop');
    el.classList.remove('music-settings-pop');
    el.classList.remove('video-option-horizontal-pop');

    if (kind === 'size') {
      const fallbackSizes = (model && model.sizes && model.sizes.length ? model.sizes : [
        { id:'1:1', label:'1:1', ratio:'1:1' },
        { id:'16:9', label:'16:9', ratio:'16:9' },
        { id:'9:16', label:'9:16', ratio:'9:16' },
        { id:'3:4', label:'3:4', ratio:'3:4' },
        { id:'4:5', label:'4:5', ratio:'4:5' },
        { id:'5:4', label:'5:4', ratio:'5:4' },
        { id:'4:3', label:'4:3', ratio:'4:3' },
        { id:'21:9', label:'21:9', ratio:'21:9' },
        { id:'auto', label:'Auto', ratio:'auto' }
      ]);
      const selectedSize = imageState.size || imageState.ratio || '1:1';

      if (el.parentElement !== document.body) document.body.appendChild(el);
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';
      el.classList.add('image-size-floating-pop');
      el.style.position = 'fixed';
      el.style.left = '8px';
      el.style.right = 'auto';
      el.style.top = 'auto';
      el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
      el.style.width = '64vw';
      el.style.maxWidth = '315px';
      el.style.minWidth = '245px';
      el.style.maxHeight = '64vh';
      el.style.overflowY = 'auto';
      el.style.zIndex = '999999';

      el.innerHTML = '<div class="image-size-sheet-title">Соотношение сторон</div>'
        + '<div class="image-size-sheet-list">'
        + fallbackSizes.map((item) => {
          const id = String(item.id || item.ratio || item.label || '');
          const label = item.label || item.ratio || item.id;
          const active = String(selectedSize) === id;
          const showRatioIcon = id.toLowerCase() !== 'auto';
          return '<button class="image-size-row ' + (showRatioIcon ? 'has-ratio-icon ' : 'no-ratio-icon ') + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickImageOption(event,\'size\',\'' + S.escapeHtml(id) + '\')">'
            + (showRatioIcon ? '<span class="image-size-icon" data-ratio="' + S.escapeHtml(id) + '"></span>' : '')
            + '<span class="image-size-label">' + S.escapeHtml(label) + '</span>'
            + '<span class="image-size-check">✓</span>'
            + '</button>';
        }).join('')
        + '</div>';
      el.classList.add('show');
      const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
      const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }

    if (!model) return;
    let items = [];
    if (kind === 'style') items = model.styles || [];
    if (kind === 'character') items = model.characters || [];
    if (kind === 'objects') items = [{ id: 'soon', label: 'Скоро' }];
    el.innerHTML = items.map((item) =>
      '<button onclick="SYLVEX.pickImageOption(event,\'' + kind + '\',\'' + S.escapeHtml(String(item.id)) + '\')">' +
      S.escapeHtml(item.label || item.id) + '</button>'
    ).join('');
    el.classList.add('show');
  }

  // =====================================================
  // АУДИОПЛЕЕР: pickMusicOption
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function pickMusicOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureMusicSettings();

    if (kind === 'genre') {
      musicState.genre = value || 'auto';
    } else if (kind === 'duration') {
      const model = currentMusicModel();
      const maxSeconds = Math.max(...((model && model.durations) || [1, 2, 3, 4])) * 60;
      const parsed = Number(value);
      musicState.duration = value === 'auto' || !Number.isFinite(parsed) || parsed < 1 || parsed > maxSeconds ? 'auto' : parsed;
    } else if (MUSIC_SETTINGS[kind]) {
      musicState.settings[kind] = value || 'auto';
      renderMusicControls();
      openImageOptionMenu(e, 'settings');
      S.haptic && S.haptic.select && S.haptic.select();
      return;
    }

    renderMusicControls();

    const el = document.getElementById('modelPop');
    if (el) {
      el.classList.remove('show');
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';
    }
    S.haptic && S.haptic.select && S.haptic.select();
  }

  // =====================================================
  // АУДИОПЛЕЕР: pickVoiceOption
  // Выбирает модель/голос/режим озвучки и обновляет кнопки Gemini TTS в разделе «Озвучка».
  // =====================================================
  async function previewGeminiVoice(e, voiceId) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureVoiceSettings();
    const elevenlabsModel = isElevenLabsVoiceModel(voiceState.modelId);
    const runwayModel = isRunwayVoiceModel(voiceState.modelId);
    const voice = String(voiceId || (elevenlabsModel ? voiceState.elevenlabsVoice : (runwayModel ? voiceState.runwayVoice : voiceState.voice)) || (elevenlabsModel ? '21m00Tcm4TlvDq8ikWAM' : (runwayModel ? 'Maya' : 'Kore'))).trim();
    if (!voice) return;
    const btn = e && e.currentTarget ? e.currentTarget : null;
    const oldText = btn ? btn.textContent : '';
    try {
      if (btn) {
        btn.disabled = true;
        btn.classList.add('is-loading');
        btn.innerHTML = '<span class="voice-preview-loading-dot" aria-hidden="true"></span>';
      }
      const cacheKey = (voiceState.modelId || 'gemini_3_1_flash_tts_preview') + ':' + voice;
      const voiceItem = currentVoiceListForPanel().find((item) => String(item.id || item.voice_id || '') === voice);
      let audioUrl = geminiVoicePreviewCache[cacheKey] || String((voiceItem && (voiceItem.previewUrl || voiceItem.preview_url)) || '');
      if (audioUrl) geminiVoicePreviewCache[cacheKey] = audioUrl;
      if (!audioUrl) {
        const res = await fetch('/api/public/prostudio/voice-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            telegram_id: getTelegramId(),
            model: voiceState.modelId || 'gemini_3_1_flash_tts_preview',
            voice,
            text: 'Привет! Это пример голоса в SYLVEX.',
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.ok === false || data.success === false) {
          throw new Error(data.error || data.message || 'Не удалось прослушать голос');
        }
        audioUrl = data.audio_url || (Array.isArray(data.audios) ? data.audios[0] : '') || '';
        if (!audioUrl) throw new Error('Не удалось получить audio_url');
        geminiVoicePreviewCache[cacheKey] = audioUrl;
      }
      if (!geminiVoicePreviewAudio) {
        geminiVoicePreviewAudio = new Audio();
        geminiVoicePreviewAudio.preload = 'auto';
      }
      geminiVoicePreviewAudio.pause();
      geminiVoicePreviewAudio.src = audioUrl;
      geminiVoicePreviewAudio.currentTime = 0;
      await geminiVoicePreviewAudio.play();
      if (btn) {
        btn.classList.remove('is-loading');
        btn.textContent = '❚❚';
      }
      geminiVoicePreviewAudio.onended = () => {
        if (btn) btn.textContent = oldText || '▶';
      };
    } catch (err) {
      console.warn('Gemini voice preview failed', err);
      toast((err && err.message) || 'Не удалось прослушать голос');
      if (btn) btn.textContent = oldText || '▶';
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('is-loading');
      }
    }
  }

  function previewSelectedVoice(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const voiceId = isElevenLabsVoiceModel(voiceState.modelId)
      ? voiceState.elevenlabsVoice
      : (isRunwayVoiceModel(voiceState.modelId) ? voiceState.runwayVoice : voiceState.voice);
    return previewGeminiVoice(e, voiceId);
  }

  function pickTextOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (kind === 'tool') {
      const available = textToolOptionsForCurrentModel().some((item) => item.id === value);
      textState.tool = available ? value : 'text';
    }
    if (kind === 'style') textState.style = value || 'neutral';
    if (kind === 'format') textState.format = value || 'markdown';
    if (kind === 'model_version') {
      const model = TEXT_MODEL_LIST.find((item) => item.id === value);
      if (model && textModelFamilyId(model) === (textState.familyId || 'gpt')) textState.modelId = model.id;
    }
    renderTextControls();
    const el = document.getElementById('modelPop');
    if (el) {
      el.classList.remove('show');
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';
    }
    updateSendButton();
    S.haptic && S.haptic.select && S.haptic.select();
  }

  function pickVoiceOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureVoiceSettings();
    if (kind === 'voice') {
      voiceState.voice = value || 'Kore';
    } else if (kind === 'elevenlabsVoice') {
      voiceState.elevenlabsVoice = value || '21m00Tcm4TlvDq8ikWAM';
      if (!voiceState.elevenlabsSecondVoice) voiceState.elevenlabsSecondVoice = voiceState.elevenlabsVoice;
    } else if (kind === 'elevenlabsSecondVoice') {
      voiceState.elevenlabsSecondVoice = value || voiceState.elevenlabsVoice || '21m00Tcm4TlvDq8ikWAM';
    } else if (kind === 'elevenlabsTool') {
      voiceState.elevenlabsTool = value || 'text_to_speech';
      voiceState.speakerMode = 'single';
    } else if (kind === 'elevenlabsTargetLanguage') {
      voiceState.elevenlabsTargetLanguage = value || 'en';
      voiceState.targetLanguage = voiceState.elevenlabsTargetLanguage;
    } else if (kind === 'runwayVoice') {
      voiceState.runwayVoice = value || 'Maya';
    } else if (kind === 'runwayTool') {
      voiceState.runwayTool = value || 'text_to_speech';
      if (voiceState.runwayTool !== 'text_to_speech') voiceState.speakerMode = 'single';
    } else if (kind === 'runwayTargetLanguage') {
      voiceState.runwayTargetLanguage = value || 'en';
      voiceState.targetLanguage = voiceState.runwayTargetLanguage;
    } else if (kind === 'runwayDuration') {
      const duration = Number(value || 5);
      voiceState.runwayDuration = Number.isFinite(duration) ? Math.max(1, Math.min(30, duration)) : 5;
    } else if (kind === 'voiceUploadPurpose') {
      applyVoiceUploadPurpose(value || 'voiceover');
    } else if (kind === 'voiceTargetLanguage') {
      voiceState.targetLanguage = value || 'en';
      voiceState.elevenlabsTargetLanguage = voiceState.targetLanguage;
      voiceState.runwayTargetLanguage = voiceState.targetLanguage;
    } else if (kind === 'voiceSpeakerCount') {
      const maxSpeakers = isElevenLabsVoiceModel(voiceState.modelId) ? 7 : 2;
      const count = Math.max(1, Math.min(maxSpeakers, Number(value || 1)));
      voiceState.numSpeakers = count;
      voiceState.speakerMode = count > 1 ? 'multi' : 'single';
      if (isElevenLabsVoiceModel(voiceState.modelId)) voiceState.elevenlabsTool = count > 1 ? 'dialogue' : 'text_to_speech';
    } else if (/^voiceSpeaker[1-7]$/.test(kind)) {
      const index = Math.max(0, Number(kind.slice(-1)) - 1);
      const duplicate = Array.from({ length: Number(voiceState.numSpeakers || 1) }, (_, speakerIndex) => speakerIndex === index ? '' : voiceSpeakerVoiceValue(speakerIndex)).filter(Boolean).some((voiceId) => String(voiceId) === String(value));
      if (duplicate) { toast('Этот голос уже выбран для другого диктора'); return; }
      if (!Array.isArray(voiceState.speakerVoices)) voiceState.speakerVoices = ['Kore', '', '', '', '', '', ''];
      voiceState.speakerVoices[index] = value || voiceSpeakerVoiceValue(index);
      if (index === 0) {
        if (isElevenLabsVoiceModel(voiceState.modelId)) voiceState.elevenlabsVoice = voiceState.speakerVoices[index];
        else if (isRunwayVoiceModel(voiceState.modelId)) voiceState.runwayVoice = voiceState.speakerVoices[index];
        else voiceState.voice = voiceState.speakerVoices[index];
      }
      if (index === 1) {
        if (isElevenLabsVoiceModel(voiceState.modelId)) voiceState.elevenlabsSecondVoice = voiceState.speakerVoices[index];
        else voiceState.secondVoice = voiceState.speakerVoices[index];
      }
    } else if (kind === 'secondVoice') {
      voiceState.secondVoice = value || 'Puck';
    } else if (kind === 'speakerMode') {
      voiceState.speakerMode = value || 'single';
      voiceState.numSpeakers = voiceState.speakerMode === 'multi' ? 2 : 1;
    } else if (kind === 'model') {
      const model = VOICE_MODEL_LIST.find((item) => item.id === value);
      if (model) {
        voiceState.modelId = model.id;
        if (isElevenLabsVoiceModel(model.id)) {
          if (!voiceState.elevenlabsVoice) voiceState.elevenlabsVoice = '21m00Tcm4TlvDq8ikWAM';
          if (!voiceState.elevenlabsSecondVoice) voiceState.elevenlabsSecondVoice = voiceState.elevenlabsVoice;
          voiceState.speakerMode = 'single';
          loadElevenLabsVoices();
        } else if (isRunwayVoiceModel(model.id)) {
          if (!voiceState.runwayVoice) voiceState.runwayVoice = 'Maya';
          voiceState.speakerMode = 'single';
          loadRunwayVoices();
        } else if (!voiceState.voice) {
          voiceState.voice = 'Kore';
        }
        if (!isVoicePurposeSupported(voiceState.uploadPurpose, model.id)) {
          const supportedPurpose = VOICE_UPLOAD_PURPOSES.find((item) => isVoicePurposeSupported(item, model.id)) || VOICE_UPLOAD_PURPOSES[0];
          voiceState.uploadPurpose = supportedPurpose.id;
          applyVoiceUploadPurpose(supportedPurpose.id);
        }
      }
    }
    if (['voice', 'elevenlabsVoice', 'elevenlabsSecondVoice', 'runwayVoice'].includes(kind) || /^voiceSpeaker[1-7]$/.test(kind)) {
      activeVoicePanelSection = '';
    }
    renderVoiceControls();
    renderModelPop();
    const el = document.getElementById('modelPop');
    const keepVoiceSheetOpen = ['speakerMode', 'runwayTool', 'runwayTargetLanguage', 'runwayDuration', 'elevenlabsTool', 'elevenlabsTargetLanguage'].includes(kind);
    const closeVoiceUploadPicker = ['voiceUploadPurpose', 'voiceTargetLanguage', 'voiceSpeakerCount'].includes(kind);
    if (el && !keepVoiceSheetOpen) {
      el.classList.remove('show');
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';
    } else if (keepVoiceSheetOpen) {
      openImageOptionMenu(e, 'settings');
    }
    if (closeVoiceUploadPicker) {
      activeVoicePanelSection = 'upload';
      renderVoiceToolPanel();
    }
    S.haptic && S.haptic.select && S.haptic.select();
  }

  // =====================================================
  // АУДИОПЛЕЕР: resetMusicSettings
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function resetMusicSettings(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureMusicSettings();
    musicState.genre = 'auto';
    musicState.duration = 'auto';
    Object.keys(MUSIC_SETTINGS).forEach((key) => {
      musicState.settings[key] = 'auto';
    });
    renderMusicControls();
    openImageOptionMenu(e, 'settings');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function resetMusicGenerationOptions() {
    musicState.genre = 'auto';
    musicState.duration = 'auto';
    Object.keys(MUSIC_SETTINGS).forEach((key) => { musicState.settings[key] = 'auto'; });
    musicSettingsDraft = null;
    renderMusicControls();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: pickImageOption
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickImageOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (kind === 'model') {
      if (isImageMode()) {
        // =====================================================
        // JAVASCRIPT-БЛОК: model
        // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
        // =====================================================
        const model = IMAGE_MODEL_LIST.find((item) => item.id === value);
        if (model) {
          imageState.modelId = model.id;
          syncImageModelOptionDefaults(model);
          syncImageFeatureAvailability();
          renderImageReferenceSections();
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      } else if (isVideoMode()) {
        // =====================================================
        // JAVASCRIPT-БЛОК: model
        // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
        // =====================================================
        const model = VIDEO_MODELS.find((item) => item.id === value);
        if (model) {
          if (model.id !== videoState.modelId) saveCurrentVideoModelSettings();
          videoState.modelId = model.id;
          restoreVideoModelSettings(model.id);
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      } else if (isMusicMode()) {
        // =====================================================
        // JAVASCRIPT-БЛОК: model
        // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
        // =====================================================
        const model = MUSIC_MODEL_LIST.find((item) => item.id === value);
        if (model) {
          musicState.modelId = model.id;
          ensureMusicSettings();
          renderMusicControls();
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      } else if (isVoiceMode()) {
        const model = VOICE_MODEL_LIST.find((item) => item.id === value);
        if (model) {
          voiceState.modelId = model.id;
          if (isElevenLabsVoiceModel(model.id)) {
            if (!voiceState.elevenlabsVoice) voiceState.elevenlabsVoice = '21m00Tcm4TlvDq8ikWAM';
            if (!voiceState.elevenlabsSecondVoice) voiceState.elevenlabsSecondVoice = voiceState.elevenlabsVoice;
            voiceState.speakerMode = 'single';
            loadElevenLabsVoices();
          } else if (isRunwayVoiceModel(model.id)) {
            if (!voiceState.runwayVoice) voiceState.runwayVoice = 'Maya';
            voiceState.speakerMode = 'single';
            loadRunwayVoices();
          } else if (!voiceState.voice) {
            voiceState.voice = 'Kore';
          }
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      } else if (studioMode === 'text') {
        const family = TEXT_MODEL_FAMILIES.find((item) => item.id === value);
        if (family) {
          textState.familyId = family.id;
          const available = textVersionsForFamily(family.id);
          if (!available.some((item) => item.id === textState.modelId)) textState.modelId = family.defaultModel || (available[0] && available[0].id) || 'gpt-5.5';
          normalizeTextToolForModel();
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = family.label || family.id;
        }
      }
    }

    if (studioMode === 'text') {
      renderTextControls();
      renderModelPop();
      const el = document.getElementById('modelPop');
      if (el) {
        el.classList.remove('show');
        el.classList.remove('image-model-floating-pop');
        el.classList.remove('image-size-floating-pop');
        el.classList.remove('music-settings-pop');
        el.classList.remove('video-option-horizontal-pop');
        el.style.cssText = '';
      }
      return;
    }

    if (isMusicMode() || isVoiceMode()) {
      if (isMusicMode()) renderMusicControls();
      if (isVoiceMode()) renderVoiceControls();
      renderModelPop();
      const el = document.getElementById('modelPop');
      if (el) {
        el.classList.remove('show');
        el.classList.remove('image-model-floating-pop');
        el.classList.remove('image-size-floating-pop');
        el.classList.remove('music-settings-pop');
        el.classList.remove('video-option-horizontal-pop');
        el.style.cssText = '';
      }
      return;
    }

    if (isVideoMode()) {
      pickVideoOption(kind, value);
      renderModelPop();

      const el = document.getElementById('modelPop');
      if (el) {
        el.classList.remove('show');
        el.classList.remove('image-model-floating-pop');
        el.classList.remove('image-size-floating-pop');
        el.classList.remove('video-option-horizontal-pop');
        el.style.cssText = '';
      }
      return;
    }
    // Эти настройки относятся только к генерации фото.
    // Видео не должно менять imageState через общие кнопки.
    if (isImageMode()) {
      if (kind === 'size') {
        imageState.size = value;
      }
      if (kind === 'style') {
        imageState.style = value || 'auto';
      }
      if (kind === 'character') {
        imageState.character = value || 'auto';
      }
      if (kind === 'objects') {
        imageState.objects = value || '';
      }
    }
    if (isImageMode()) {
      renderImageControls();
    }
    const el = document.getElementById('modelPop');
    if (el) {
      el.classList.remove('show');
      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';
    }
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: generatedUrlsFromMessage
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function generatedUrlsFromMessage(m, kind) {
    if (!m) return [];
    if (kind === 'image') {
      const items = Array.isArray(m.images) && m.images.length ? m.images : (m.imageUrl ? [m.imageUrl] : []);
      return items.map((item) => typeof item === 'object' ? (item.url || item.original_url || item.image_url || '') : item).filter(Boolean);
    }
    if (kind === 'video') {
      return Array.isArray(m.videos) && m.videos.length ? m.videos : (m.videoUrl ? [m.videoUrl] : []);
    }
    if (kind === 'audio') {
      return Array.isArray(m.audios) && m.audios.length
        ? m.audios
        : (m.audioUrl || m.audio_url || m.music_url || m.song_url || m.result_url || m.output_url || m.file_url
          ? [m.audioUrl || m.audio_url || m.music_url || m.song_url || m.result_url || m.output_url || m.file_url]
          : []);
    }
    return Array.isArray(m.files) && m.files.length ? m.files : (m.fileUrl ? [m.fileUrl] : []);
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: generatedUrlsFromResponse
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function generatedUrlsFromResponse(j, kind) {
    if (!j) return [];
    if (kind === 'image') {
      const items = Array.isArray(j.images) && j.images.length
        ? j.images
        : Array.isArray(j.urls) && j.urls.length
          ? j.urls
          : Array.isArray(j.output) && j.output.length
            ? j.output
            : (j.image_url || j.result_url ? [j.image_url || j.result_url] : []);
      return items.map((item) => typeof item === 'object' ? (item.url || item.original_url || item.image_url || '') : item).filter(Boolean);
    }
    if (kind === 'video') {
      return Array.isArray(j.videos) && j.videos.length ? j.videos : (j.video_url ? [j.video_url] : []);
    }
    if (kind === 'audio') {
      const items = Array.isArray(j.audios) && j.audios.length
        ? j.audios
        : Array.isArray(j.response_data) && j.response_data.length
          ? j.response_data
          : Array.isArray(j.output) && j.output.length
            ? j.output
            : (j.audio_url || j.music_url || j.song_url || j.output_url || j.file_url || j.result_url || j.url
              ? [j.audio_url || j.music_url || j.song_url || j.output_url || j.file_url || j.result_url || j.url]
              : []);
      return items.map((item) => typeof item === 'object'
        ? (item.audio_url || item.music_url || item.song_url || item.output_url || item.file_url || item.result_url || item.url || '')
        : item).filter(Boolean);
    }
    return Array.isArray(j.files) && j.files.length ? j.files : (j.file_url ? [j.file_url] : []);
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: generatedThumbsFromResponse
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function generatedThumbsFromResponse(j) {
    if (!j) return [];
    if (j.thumbnail_url) return [j.thumbnail_url];
    if (Array.isArray(j.thumbnails) && j.thumbnails.length) return j.thumbnails;
    if (Array.isArray(j.images) && j.images.length) {
      return j.images.map((item) => typeof item === 'object' ? (item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || '') : '').filter(Boolean);
    }
    return j.thumb_url ? [j.thumb_url] : [];
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: pickFirstMediaUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickFirstMediaUrl() {
    for (let i = 0; i < arguments.length; i += 1) {
      const value = arguments[i];
      if (!value) continue;
      if (typeof value === 'string') return value;
      if (Array.isArray(value)) {
        for (const item of value) {
          const url = pickFirstMediaUrl(item);
          if (url) return url;
        }
      } else if (typeof value === 'object') {
        const url = value.audio_url
          || value.music_url
          || value.song_url
          || value.output_url
          || value.file_url
          || value.result_url
          || value.url
          || value.original_url
          || value.image_url
          || value.cover_url
          || value.cover
          || value.artwork_url
          || value.thumbnail_url
          || value.thumb_url
          || value.poster_url
          || value.result_image
          || '';
        if (url) return url;
      }
    }
    return '';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: pickFirstCoverUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickFirstCoverUrl() {
    for (let i = 0; i < arguments.length; i += 1) {
      const value = arguments[i];
      if (!value) continue;
      if (typeof value === 'string') return value;
      if (Array.isArray(value)) {
        for (const item of value) {
          const url = pickFirstCoverUrl(item);
          if (url) return url;
        }
      } else if (typeof value === 'object') {
        const url = value.cover_url
          || value.cover
          || value.artwork_url
          || value.image_url
          || value.thumbnail_url
          || value.thumb_url
          || value.poster_url
          || value.result_image
          || value.image
          || '';
        if (url) return url;
      }
    }
    return '';
  }

  // =====================================================
  // АУДИОПЛЕЕР: musicCoverUrl
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function musicCoverUrl(source) {
    const meta = source && source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
    return pickFirstCoverUrl(
      source && source.cover_url,
      source && source.cover,
      source && source.artwork_url,
      source && source.image_url,
      source && source.thumbnail_url,
      source && source.thumb_url,
      source && source.poster_url,
      source && source.result_image,
      source && source.result_images,
      source && source.images,
      source && source.response_data,
      source && source.output && source.output.image,
      meta.cover_url,
      meta.cover,
      meta.artwork_url,
      meta.image_url,
      meta.thumbnail_url,
      meta.thumb_url,
      meta.poster_url,
      meta.result_image,
      meta.result_images,
      meta.images,
      meta.response_data,
      meta.output && meta.output.image
    );
  }

  // =====================================================
  // АУДИОПЛЕЕР: musicAudioUrl
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function musicAudioUrl(source) {
    const meta = source && source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
    return pickFirstMediaUrl(
      source && source.audio_url,
      source && source.music_url,
      source && source.song_url,
      source && source.url,
      source && source.result_url,
      source && source.output_url,
      source && source.file_url,
      source && source.audio,
      source && source.audios,
      source && source.output,
      meta.audio_url,
      meta.music_url,
      meta.song_url,
      meta.url,
      meta.result_url,
      meta.output_url,
      meta.file_url,
      meta.audio,
      meta.audios,
      meta.output
    );
  }

  // =====================================================
  // АУДИОПЛЕЕР: normalizeMusicTrack
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function normalizeMusicTrack(source, fallbackUrl) {
    const meta = source && source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
    const audioUrl = musicAudioUrl(source || {}) || fallbackUrl || '';
    if (!audioUrl) return null;
    const title = (source && (source.title || source.name)) || meta.title || meta.name || 'SYLVEX Music';
    return {
      id: (source && (source.id || source.task_id || source.workId)) || meta.id || meta.task_id || audioUrl,
      type: 'music',
      audioUrl,
      coverUrl: musicCoverUrl(source || {}),
      title,
      model: (source && source.model) || meta.model || '',
      provider: (source && source.provider) || meta.provider || 'suno',
    };
  }

  // =====================================================
  // АУДИОПЛЕЕР: formatAudioTime
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function formatAudioTime(seconds) {
    const total = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    const min = Math.floor(total / 60);
    const sec = String(total % 60).padStart(2, '0');
    return min + ':' + sec;
  }

  let activeMusicTrack = null;

  // =====================================================
  // АУДИОПЛЕЕР: setStudioPlayerIcon
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function setStudioPlayerIcon(isPlaying) {
    const btn = document.getElementById('studioPlayPauseBtn');
    if (!btn) return;
    btn.innerHTML = isPlaying
      ? '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>'
      : '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderStudioPlayerTrack
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderStudioPlayerTrack(track) {
    const player = document.getElementById('studioAudioPlayer');
    const titleEl = document.getElementById('studioTrackTitle');
    const art = document.getElementById('studioTrackArtImage');
    if (player) player.classList.toggle('has-track', !!track);
    if (titleEl) titleEl.textContent = (track && track.title) || 'Untitled Track';
    if (art) {
      if (track && track.coverUrl) {
        art.src = track.coverUrl;
        art.hidden = false;
      } else {
        art.removeAttribute('src');
        art.hidden = true;
      }
    }
  }

  // =====================================================
  // АУДИОПЛЕЕР: bindStudioAudioElement
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function bindStudioAudioElement() {
    const audio = document.getElementById('studioAudioElement');
    if (!audio || audio.dataset.bound === '1') return audio;
    audio.dataset.bound = '1';
    audio.addEventListener('play', () => setStudioPlayerIcon(true));
    audio.addEventListener('pause', () => setStudioPlayerIcon(false));
    audio.addEventListener('ended', () => setStudioPlayerIcon(false));
    audio.addEventListener('timeupdate', () => {
      const timeEl = document.getElementById('studioCurrentTime');
      const progress = document.getElementById('studioProgressFill');
      if (timeEl) timeEl.textContent = formatAudioTime(audio.currentTime || 0);
      if (progress) {
        const pct = audio.duration ? Math.min(100, Math.max(0, (audio.currentTime / audio.duration) * 100)) : 0;
        progress.style.width = pct + '%';
      }
    });
    audio.addEventListener('loadedmetadata', () => {
      const durationEl = document.getElementById('studioDuration');
      if (durationEl) durationEl.textContent = formatAudioTime(audio.duration || 0);
    });
    return audio;
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openMusicInPlayer
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openMusicInPlayer(trackLike, e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    PlayerManager.playTrack(trackLike || {});
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleStudioAudioPlayer
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleStudioAudioPlayer(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    PlayerManager.toggle();
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: generatedThumbsFromMessage
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function generatedThumbsFromMessage(m) {
    if (!m) return [];
    if (m.thumbnail_url) return [m.thumbnail_url];
    if (Array.isArray(m.thumbnails) && m.thumbnails.length) return m.thumbnails;
    if (Array.isArray(m.images) && m.images.length) {
      return m.images.map((item) => typeof item === 'object' ? (item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || '') : '').filter(Boolean);
    }
    return m.thumbUrl ? [m.thumbUrl] : [];
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imagePreviewUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imagePreviewUrl(meta, fallback) {
  // =====================================================
  // JAVASCRIPT-БЛОК: pickUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const pickUrl = (value) => {
    if (!value) return '';

    if (typeof value === 'string') {
      return value;
    }

    if (typeof value === 'object') {
      return value.thumbnail_url
        || value.thumb_url
        || value.thumbnail
        || value.thumb
        || '';
    }

    return '';
  };

  // =====================================================
  // JAVASCRIPT-БЛОК: firstUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const firstUrl = (list) => {
    if (!Array.isArray(list)) return '';

    for (const item of list) {
      const url = pickUrl(item);
      if (url) return url;
    }

    return '';
  };

  if (!meta) return pickUrl(fallback);

  return pickUrl(meta.thumbnail_url)
    || pickUrl(meta.thumb_url)
    || firstUrl(meta.result_thumbnails)
    || firstUrl(meta.thumbnails)
    || pickUrl(fallback)
    || '';
}

  // =====================================================
  // JAVASCRIPT-БЛОК: previewImgHtml
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function previewImgHtml(url, alt, fallbackUrl) {
    const safeUrl = S.escapeHtml(url || '');
    const safeAlt = S.escapeHtml(alt || 'preview');
    const safeFallbackUrl = S.escapeHtml(fallbackUrl || '');
    if (!safeUrl) return '<span class="generation-result-fallback">IMG</span>';
    return '<img src="' + safeUrl + '" alt="' + safeAlt + '" loading="lazy" decoding="async"'
      + (safeFallbackUrl ? ' data-fallback-src="' + safeFallbackUrl + '"' : '')
      + ' onerror="if(this.dataset&&this.dataset.fallbackSrc&&this.src!==this.dataset.fallbackSrc){this.src=this.dataset.fallbackSrc;this.removeAttribute(\'data-fallback-src\');}else{this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'generation-result-fallback\',textContent:\'IMG\'}));}" />';
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: aiMessageFromGenerateResponse
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function aiMessageFromGenerateResponse(j) {
    const images = generatedUrlsFromResponse(j, 'image');
    const thumbs = generatedThumbsFromResponse(j);
    const videos = generatedUrlsFromResponse(j, 'video');
    const audios = generatedUrlsFromResponse(j, 'audio');
    const files = generatedUrlsFromResponse(j, 'file');
    return {
      role: 'ai',
      text: j.text || '',
      imageUrl: images[0] || undefined,
      images: images.length ? images : null,
      thumbUrl: thumbs[0] || undefined,
      thumbnails: thumbs.length ? thumbs : null,
      videoUrl: videos[0] || undefined,
      videos: videos.length ? videos : null,
      audioUrl: audios[0] || undefined,
      audios: audios.length ? audios : null,
      fileUrl: files[0] || undefined,
      files: files.length ? files : null,
      generationJobId: j.job_id || j.generation_id || j.charge_id || '',
      generationStatus: j.status || 'completed',
    };
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedTelegramButton
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
function renderGeneratedTelegramButton(url, kind) {
    const safeUrl = S.escapeHtml(url);
    const safeKind = S.escapeHtml(kind || 'file');
    return '<button class="gen-action-btn gen-telegram-btn" type="button" data-result-url="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="SYLVEX.openTelegramBot(event)">'
      + generationActionIcon('telegram') + '<span>Перейти в Telegram</span>'
      + '</button>';
  }

  function generationActionIcon(kind) {
    const paths = {
      open: '<path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
      play: '<path d="m8 5 11 7-11 7z"/>',
      download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
      animate: '<rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3z"/>',
      edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/>',
      share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4"/><path d="m8.6 13.5 6.8 4"/>',
      telegram: '<path d="m21 4-3 16-6-4-4 3 1-5 9-7-11 6-4-2z"/>',
      lipsync: '<path d="M5 12c2-3 4.3-4.5 7-4.5S17 9 19 12c-2 3-4.3 4.5-7 4.5S7 15 5 12z"/><path d="M9 12h6"/>',
      avatar: '<circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/>',
      music: '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
    };
    return '<svg class="generation-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[kind] || paths.open) + '</svg>';
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: renderGeneratedOpenButton
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function renderGeneratedOpenButton(url, kind) {
    const safeUrl = S.escapeHtml(url);
    const safeKind = S.escapeHtml(kind || 'file');
    if (kind === 'voice') {
      return '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" data-result-url="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="SYLVEX.playVoiceInCard(event)">' + generationActionIcon('play') + 'Воспроизвести</button>';
    }
    if (kind === 'audio' || kind === 'music') {
      return '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="SYLVEX.playMusicTrack(event)">' + generationActionIcon('play') + 'Воспроизвести</button>';
    }
    const dataAttr = kind === 'image' ? 'data-image-url' : 'data-result-url';
    const handler = kind === 'image' ? 'SYLVEX.openImageViewer(event)' : 'SYLVEX.openGeneratedContent(event)';
    return '<button class="gen-action-btn" type="button" ' + dataAttr + '="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="' + handler + '">' + generationActionIcon('open') + 'Открыть</button>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedActions
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function completedGenerationJobId(message, meta) {
    const source = meta || (message && message.metadata) || {};
    return String(source.job_id || source.charge_id || (message && message.generationJobId) || '');
  }

  function completedGenerationDownloadUrl(jobId) {
    if (!jobId) return '';
    const params = new URLSearchParams();
    params.set('telegram_id', String(getTelegramId() || 0));
    if (S.tg && S.tg.initData) params.set('init_data', S.tg.initData);
    return '/api/public/prostudio/download/' + encodeURIComponent(jobId) + '?' + params.toString();
  }

  function generationDownloadFilename(kind, id) {
    const normalized = String(kind || '').toLowerCase();
    const prefix = normalized === 'audio' ? 'music' : normalized;
    const extensions = { image: 'png', video: 'mp4', music: 'mp3', voice: 'mp3' };
    return 'sylvex-' + (prefix || 'file') + '-' + String(id || 'generation').slice(0, 12) + '.' + (extensions[prefix] || 'bin');
  }

  function browserDownload(url, filename) {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename || '';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  function downloadGeneratedFile(event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const button = event && event.currentTarget;
    const relativeUrl = String(button && button.dataset.downloadUrl || '');
    const filename = String(button && button.dataset.fileName || 'sylvex-generation');
    if (!relativeUrl) return toast('Файл для скачивания недоступен');
    const absoluteUrl = new URL(relativeUrl, window.location.origin).toString();
    const tg = S.tg;
    if (tg && typeof tg.downloadFile === 'function') {
      try {
        tg.downloadFile({ url: absoluteUrl, file_name: filename }, (accepted) => {
          if (accepted === false) toast('Telegram не разрешил скачать файл');
        });
        return;
      } catch (error) {
        console.warn('PROSTUDIO_NATIVE_DOWNLOAD_FAILED', { error: String(error && error.message || error) });
      }
    }
    browserDownload(relativeUrl, filename);
  }

  function renderCompletedGenerationDownload(jobId, status, className, kind) {
    if (!jobId || String(status || '').toLowerCase() !== 'completed') return '';
    const href = completedGenerationDownloadUrl(jobId);
    const filename = generationDownloadFilename(kind, jobId);
    return '<button type="button" class="' + S.escapeHtml(className || 'gen-action-btn') + '" data-download-url="' + S.escapeHtml(href) + '" data-file-name="' + S.escapeHtml(filename) + '" onclick="SYLVEX.downloadGeneratedFile(event)">'
      + generationActionIcon('download') + 'Скачать</button>';
  }

  function renderGeneratedActions(url, kind, jobId, status) {
    const safeUrl = S.escapeHtml(url);
    let actions = renderGeneratedOpenButton(url, kind) + renderGeneratedTelegramButton(url, kind);
    actions += renderCompletedGenerationDownload(jobId, status, 'gen-action-btn', kind);
    if (kind === 'image') {
      actions += '<button class="gen-action-btn" type="button" data-image-url="' + safeUrl + '" onclick="SYLVEX.animateGeneratedImage(event)">' + generationActionIcon('animate') + 'Оживить фото</button>';
    }
    if (kind === 'video') {
      actions += '<button class="gen-action-btn" type="button" data-video-url="' + safeUrl + '" onclick="SYLVEX.editGeneratedVideo(event)">' + generationActionIcon('edit') + 'Редактировать видео</button>';
    }
    if (kind === 'voice') {
      actions += '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" onclick="SYLVEX.continueVoiceResult(event,\'lipsync\')">' + generationActionIcon('lipsync') + 'LipSync</button>';
      actions += '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" onclick="SYLVEX.continueVoiceResult(event,\'avatar\')">' + generationActionIcon('avatar') + 'Оживить аватара</button>';
      actions += '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" onclick="SYLVEX.continueVoiceResult(event,\'music\')">' + generationActionIcon('music') + 'Добавить музыку</button>';
      actions += '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" onclick="SYLVEX.continueVoiceResult(event,\'video\')">' + generationActionIcon('animate') + 'Создать видео</button>';
    }
    return '<div class="gen-result-actions">' + actions + '</div>';
  }

  function continueVoiceResult(event, target) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const button = event && event.currentTarget;
    const url = button ? String(button.dataset.audioUrl || '') : '';
    if (!url) return toast('Аудиофайл недоступен');
    const attachment = { kind:'audio', mime:'audio/mpeg', name:'SYLVEX voiceover.mp3', url };
    try { localStorage.setItem('sylvex_content_handoff', JSON.stringify({ source:'voice', target, attachment, created_at:new Date().toISOString() })); } catch {}
    if (target === 'music') {
      updateComposerMode('music');
      musicState.attachment = attachment;
      musicState.uploads = [attachment];
      toast('Озвучка передана в Music Studio');
    } else {
      updateComposerMode('video');
      videoState.attachment = attachment;
      videoState.audioUrl = url;
      videoState.handoffAction = target;
      toast(target === 'lipsync' ? 'Озвучка передана в LipSync' : (target === 'avatar' ? 'Озвучка готова для оживления аватара' : 'Озвучка передана в Video Studio'));
    }
    pendingAttachment = attachment;
    updateSendButton();
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedImage
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderGeneratedImage(item, index, generationMeta) {
    const url = typeof item === 'string' ? item : item.url;
    const thumb = typeof item === 'string' ? item : (item.thumb || item.url);
    const safeUrl = S.escapeHtml(url);
    const safeThumb = S.escapeHtml(thumb || url);
    return '<div class="gen-media-card gen-image-card">'
      + '<button class="gen-img-open" type="button" data-image-url="' + safeUrl + '" onclick="SYLVEX.openImageViewer(event)">'
      + '<img class="gen-img" src="' + safeThumb + '" alt="generated" loading="lazy" decoding="async" />'
      + '</button>'
      + renderGeneratedActions(url, 'image', completedGenerationJobId(null, generationMeta), generationMeta && generationMeta.status)
      + '</div>';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: imageGenerationMetadata
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function imageGenerationMetadata(prompt, referenceImages, result, optionsSnapshot) {
    const backendMeta = result && result.metadata && typeof result.metadata === 'object' ? result.metadata : {};
    const options = Object.assign({}, optionsSnapshot || imageState || {}, backendMeta.image_options || backendMeta.settings || {});
    const modelId = backendMeta.model || (result && result.model) || options.modelId || imageState.modelId || '';
    // =====================================================
    // JAVASCRIPT-БЛОК: model
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const model = IMAGE_MODEL_LIST.find((item) => item.id === modelId) || currentImageModel() || {};
    const images = backendMeta.result_images && backendMeta.result_images.length
      ? backendMeta.result_images.slice()
      : (backendMeta.images && backendMeta.images.length
        ? backendMeta.images.slice()
        : (backendMeta.image_url || backendMeta.result_url
          ? [backendMeta.image_url || backendMeta.result_url]
          : (result ? generatedUrlsFromResponse(result, 'image') : [])));
    const thumbs = backendMeta.result_thumbnails && backendMeta.result_thumbnails.length
      ? backendMeta.result_thumbnails.slice()
      : (backendMeta.thumbnails && backendMeta.thumbnails.length
        ? backendMeta.thumbnails.slice()
        : (backendMeta.thumbnail_url || backendMeta.thumb_url ? [backendMeta.thumbnail_url || backendMeta.thumb_url] : (result ? generatedThumbsFromResponse(result) : [])));
    const imageUrl = backendMeta.image_url || backendMeta.result_url || images[0] || '';
    const thumbUrl = backendMeta.thumbnail_url || backendMeta.thumb_url || thumbs[0] || '';
    console.debug('PROSTUDIO IMAGE METADATA DEBUG', {
      resultKeys: result && typeof result === 'object' ? Object.keys(result) : [],
      backendMetaKeys: Object.keys(backendMeta || {}),
      images,
      thumbs,
      imageUrl,
      thumbUrl,
      previewFallbackUrl: backendMeta.preview_fallback_url || backendMeta.full_url || backendMeta.result_url || imageUrl,
      modelId,
      provider: backendMeta.provider || (result && result.provider) || providerHintForModel(modelId),
      generationCost: backendMeta.generation_cost || (result && result.generation_cost) || '',
      costCredits: backendMeta.cost_credits !== undefined ? backendMeta.cost_credits : (result && result.cost_credits),
    });
    const seed = backendMeta.seed !== undefined ? backendMeta.seed : (options.seed === undefined ? null : options.seed);
    const refs = (backendMeta.reference_images && backendMeta.reference_images.length)
      ? backendMeta.reference_images.slice()
      : (referenceImages || []).slice();
    return {
      type: 'image',
      result_url: imageUrl,
      model: modelId || model.id || '',
      model_label: backendMeta.model_label || model.label || model.name || modelId || '',
      provider: backendMeta.provider || (result && result.provider) || providerHintForModel(modelId),
      prompt: backendMeta.prompt || prompt || '',
      style: backendMeta.style || options.style || '',
      character: backendMeta.character || options.character || '',
      objects: backendMeta.objects || options.objects || '',
      ratio: backendMeta.ratio || options.ratio || options.size || '',
      size: backendMeta.size || options.size || options.ratio || '',
      count: backendMeta.count || options.count || 1,
      seed: seed === '' ? null : seed,
      generation_cost: backendMeta.generation_cost || (result && result.generation_cost) || '',
      cost_usd: backendMeta.cost_usd !== undefined ? backendMeta.cost_usd : (result && result.cost_usd),
      unit_cost_usd: backendMeta.unit_cost_usd !== undefined ? backendMeta.unit_cost_usd : (result && result.unit_cost_usd),
      cost: backendMeta.cost !== undefined ? backendMeta.cost : (result && result.cost),
      cost_credits: backendMeta.cost_credits !== undefined ? backendMeta.cost_credits : (result && result.cost_credits),
      unit_cost_credits: backendMeta.unit_cost_credits !== undefined ? backendMeta.unit_cost_credits : (result && result.unit_cost_credits),
      balance_charged: backendMeta.balance_charged !== undefined ? backendMeta.balance_charged : (result && result.balance_charged),
      balance_after: backendMeta.balance_after !== undefined ? backendMeta.balance_after : (result && result.balance_after),
      charge_id: backendMeta.charge_id || (result && (result.charge_id || result.generation_id || result.job_id)) || '',
      job_id: backendMeta.job_id || (result && (result.job_id || result.generation_id || result.charge_id)) || '',
      status: backendMeta.status || (result && result.status) || 'completed',
      rendering_speed: backendMeta.rendering_speed || (result && result.rendering_speed) || '',
      provider_model: backendMeta.provider_model || (result && result.provider_model) || '',
      recraft_tools: Array.isArray(backendMeta.recraft_tools)
        ? backendMeta.recraft_tools.slice()
        : (result && Array.isArray(result.recraft_tools) ? result.recraft_tools.slice() : []),
      settings: Object.assign({}, options),
      image_options: Object.assign({}, options, {
        seed: seed === '' ? null : seed,
        referenceImageUrls: refs.slice(),
        referenceImages: refs.slice(),
      }),
      characterId: backendMeta.characterId || options.characterId || null,
      characterName: backendMeta.characterName || options.characterName || '',
      characterReferences: Array.isArray(backendMeta.characterReferences) ? backendMeta.characterReferences.slice() : (Array.isArray(options.characterReferences) ? options.characterReferences.slice() : []),
      objectId: backendMeta.objectId || options.objectId || null,
      objectName: backendMeta.objectName || options.objectName || '',
      objectReferences: Array.isArray(backendMeta.objectReferences) ? backendMeta.objectReferences.slice() : (Array.isArray(options.objectReferences) ? options.objectReferences.slice() : []),
      reference_images: refs,
      result_images: images,
      result_thumbnails: thumbs,
      image_url: imageUrl,
      full_url: backendMeta.full_url || backendMeta.result_url || imageUrl,
      preview_fallback_url: backendMeta.preview_fallback_url || backendMeta.full_url || backendMeta.result_url || imageUrl,
      thumbnail_url: thumbUrl,
      thumb_url: thumbUrl,
      created_at: backendMeta.created_at || new Date().toISOString(),
      sent_to_telegram: !!(backendMeta.sent_to_telegram || (result && result.sent_to_telegram)),
    };
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: generationResultMetadata
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function generationResultMetadata(type, prompt, result, referenceImages, optionsSnapshot) {
    if (result && ['image', 'video', 'music', 'voice'].includes(String(result.type || ''))) {
      type = String(result.type || type);
    }
    if (type === 'image') return imageGenerationMetadata(prompt, referenceImages, result);
    const videoUrls = result ? generatedUrlsFromResponse(result, 'video') : [];
    const audioUrls = result ? generatedUrlsFromResponse(result, 'audio') : [];
    const options = optionsSnapshot || (result && (result.video_options || result.voice_options || result.music_options)) || (type === 'video' ? videoState : (type === 'music' ? musicOptionsPayload() : voiceState));
    const modelId = (options && (options.model || options.modelId)) || pickStudioModel() || '';
    const currentModel = type === 'video' ? currentVideoModel() : null;
    const resultUrl = type === 'video' ? (videoUrls[0] || result.video_url || '') : (audioUrls[0] || musicAudioUrl(result || {}) || '');
    const coverUrl = type === 'music' ? musicCoverUrl(result || {}) : '';
    return {
      type,
      result_url: resultUrl,
      model: modelId,
      model_label: (currentModel && (currentModel.label || currentModel.name)) || modelId,
      provider: (result && result.provider) || (type === 'video' ? currentVideoProvider() : (type === 'music' ? 'suno' : (type === 'voice' ? 'voice' : pickProviderHint()))),
      prompt: prompt || '',
      settings: Object.assign({}, options || {}),
      ratio: options && options.ratio,
      size: options && (options.resolution || options.size),
      duration: (result && result.duration) || (options && options.duration),
      video_url: type === 'video' ? resultUrl : '',
      videos: type === 'video' && resultUrl ? [resultUrl] : [],
      audio_url: type !== 'video' ? resultUrl : '',
      audios: type !== 'video' && resultUrl ? [resultUrl] : [],
      image_url: type === 'music' ? coverUrl : (result && result.image_url ? result.image_url : ''),
      cover_url: coverUrl,
      artwork_url: type === 'music' ? ((result && result.artwork_url) || coverUrl) : '',
      thumbnail_url: type === 'music' ? (coverUrl || ((result && result.thumbnail_url) || '')) : ((result && result.thumbnail_url) || ''),
      thumb_url: type === 'music' ? (coverUrl || ((result && result.thumb_url) || '')) : ((result && result.thumb_url) || ''),
      title: result && result.title ? result.title : '',
      generation_cost: result && result.generation_cost ? result.generation_cost : '',
      cost_usd: result && result.cost_usd !== undefined ? result.cost_usd : undefined,
      unit_cost_usd: result && result.unit_cost_usd !== undefined ? result.unit_cost_usd : undefined,
      cost_credits: result && result.cost_credits !== undefined ? result.cost_credits : undefined,
      unit_cost_credits: result && result.unit_cost_credits !== undefined ? result.unit_cost_credits : undefined,
      created_at: new Date().toISOString(),
      sent_to_telegram: !!(result && result.sent_to_telegram),
      job_id: result && (result.job_id || result.generation_id || result.charge_id) ? (result.job_id || result.generation_id || result.charge_id) : '',
      charge_id: result && (result.charge_id || result.job_id || result.generation_id) ? (result.charge_id || result.job_id || result.generation_id) : '',
      status: result && result.status ? result.status : 'completed',
    };
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderImageGenerationLoadingCard
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderImageGenerationLoadingCard() {
    return renderGenerationLoadingCard({ progress: createGenerationProgress('image') });
  }

  const GENERATION_PROGRESS_STEPS = [0,2,5,9,14,20,27,34,41,48,55,62,68,73,78,82,85,87,89,90,91,92];
  const GENERATION_STAGE_MESSAGES = {
    image: ['Создаем изображение...', 'Подготавливаем композицию...', 'Прорисовываем детали...', 'Финальная обработка...'],
    video: ['Создаем сценарий...', 'Строим движение камеры...', 'Генерируем кадры...', 'Просчитываем анимацию...', 'Финальный рендер...'],
    music: ['Создаем мелодию...', 'Подбираем инструменты...', 'Формируем композицию...', 'Сводим звук...'],
    voice: ['Подготавливаем голос...', 'Синтезируем речь...', 'Настраиваем интонацию...', 'Финальная обработка...'],
    text: ['Анализируем запрос...', 'Строим ответ...', 'Формируем результат...'],
    kling: ['Building motion...', 'Generating frames...', 'Applying native audio...', 'Rendering video...'],
  };

  // =====================================================
  // JAVASCRIPT-БЛОК: generationKindForCurrentMode
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function generationKindForCurrentMode() {
    if (isVideoMode()) {
      const model = String(videoState.modelId || '').toLowerCase();
      return model.includes('kling') ? 'kling' : 'video';
    }
    if (isMusicMode()) return 'music';
    if (isVoiceMode()) return voiceState.uploadPurpose === 'dub_video' ? 'video' : 'voice';
    if (isImageMode()) return 'image';
    return 'text';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: createGenerationProgress
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function createGenerationProgress(kind, modelId) {
    return {
      kind: kind || generationKindForCurrentMode(),
      modelId: modelId || pickStudioModel() || '',
      percent: 0,
      stepIndex: 0,
      startedAt: Date.now(),
      message: '',
    };
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: generationProgressMessage
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function generationProgressMessage(progress) {
    const p = progress || {};
    const items = GENERATION_STAGE_MESSAGES[p.kind] || GENERATION_STAGE_MESSAGES.text;
    if (p.message) return p.message;
    const pct = Number(p.percent || 0);
    const index = Math.min(items.length - 1, Math.max(0, Math.floor((pct / 99) * items.length)));
    return items[index] || items[0] || 'Генерация...';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: nextGenerationProgress
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function nextGenerationProgress(progress, completed) {
    const p = Object.assign(createGenerationProgress('text'), progress || {});
    if (completed) {
      p.percent = 100;
      p.message = 'Готово';
      return p;
    }
    const elapsed = Math.max(0, Date.now() - Number(p.startedAt || Date.now()));
    const timeStep = Math.min(GENERATION_PROGRESS_STEPS.length - 1, Math.floor(elapsed / 2200));
    p.stepIndex = Math.max(Number(p.stepIndex || 0), timeStep);
    p.percent = GENERATION_PROGRESS_STEPS[Math.min(p.stepIndex, GENERATION_PROGRESS_STEPS.length - 1)] || 0;
    if (p.percent > 92) p.percent = 92;
    return p;
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGenerationLoadingCard
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderGenerationLoadingCard(message) {
    const progress = nextGenerationProgress(message && message.progress, false);
    const pct = Math.max(0, Math.min(92, Number(progress.percent || 0)));
    return '<div class="generation-loading-card">'
      + '<div class="generation-loading-border"></div>'
      + '<div class="generation-loading-title">' + S.escapeHtml(generationProgressMessage(progress)) + '</div>'
      + '<div class="generation-loading-progress" aria-label="Generation progress">'
      + '<span style="width:' + pct + '%"></span>'
      + '</div>'
      + '<div class="generation-loading-percent">' + pct + '%</div>'
      + '</div>';
  }

  function renderTextLoadingDots() {
    return '<div class="text-loading-dots" aria-label="Ожидаем ответ">'
      + '<span></span><span></span><span></span>'
      + '</div>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderInsufficientBalanceCard
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderInsufficientBalanceCard(m, index) {
    const required = Number(m.requiredCredits || 0);
    const balance = Number(m.balance || 0);
    const costText = m.generationCost || (required ? required + ' ⚡️' : '');
    return '<div class="generation-balance-card">'
      + '<div class="generation-balance-title">Недостаточно токенов</div>'
      + '<div class="generation-balance-text">'
      + (m.prompt ? '<span class="generation-balance-prompt">' + S.escapeHtml(String(m.prompt)).slice(0, 160) + '</span>' : '')
      + (costText ? 'Стоимость: ' + S.escapeHtml(String(costText)) + '<br>' : '')
      + 'Баланс: ' + S.escapeHtml(String(balance)) + ' ⚡️'
      + '</div>'
      + '<div class="generation-balance-actions">'
      + '<button type="button" onclick="SYLVEX.openShopForGeneration(event,' + index + ')">Пополнить баланс</button>'
      + '<button type="button" onclick="SYLVEX.resumePendingGeneration(event,' + index + ')">Возобновить</button>'
      + '</div>'
      + '</div>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderImageResultMiniCard
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderImageResultMiniCard(m, index) {
    const meta = m.metadata || {};
    const type = meta.type || (m.videoUrl ? 'video' : (m.audioUrl ? (currentChatType() === 'voice' ? 'voice' : 'music') : 'image'));
    const thumb = imagePreviewUrl(meta, '');
    const fallbackUrl = meta.preview_fallback_url || meta.image_url || meta.full_url || meta.result_url || ((meta.result_images || [])[0]) || '';
    const safeModel = S.escapeHtml(meta.model_label || meta.model || type);
    const usd = meta.cost_usd !== undefined && meta.cost_usd !== null && meta.cost_usd !== ''
      ? '$' + Number(meta.cost_usd).toFixed(3)
      : '';
    const creditsValue = meta.cost_credits !== undefined && meta.cost_credits !== null && meta.cost_credits !== ''
      ? String(meta.cost_credits) + ' ⚡️'
      : '';
    const cost = [usd, creditsValue].filter(Boolean).join(' / ') || String(meta.generation_cost || '');
    const prompt = String(meta.prompt || '');
    const titleMap = {
      image: 'Изображение готово',
      video: 'Видео готово',
      music: 'Музыка готова',
      voice: 'Озвучка готова',
    };
    const iconMap = { image: 'IMG', video: 'VID', music: '♪', voice: 'VO' };
    const media = thumb
      ? previewImgHtml(thumb, 'generated result', type === 'image' ? fallbackUrl : '')
      : '<span class="generation-result-fallback">' + S.escapeHtml(iconMap[type] || 'AI') + '</span>';
    return '<div class="generation-result-card-shell">'
      + '<button class="generation-result-share" type="button" aria-label="Поделиться генерацией" title="Поделиться" onclick="SYLVEX.shareGenerationCard(event,' + index + ')">' + generationActionIcon('share') + '</button>'
      + '<button class="generation-result-mini-card" type="button" onclick="SYLVEX.openGenerationInfoDrawer(event,' + index + ')">'
      + '<span class="generation-result-thumb">' + media + '</span>'
      + '<span class="generation-result-meta">'
      + '<span class="generation-result-title">' + S.escapeHtml(titleMap[type] || 'Результат готов') + '</span>'
      + '<span class="generation-result-sub">' + safeModel + '</span>'
      + (cost ? '<span class="generation-result-cost">' + S.escapeHtml(cost) + '</span>' : '')
      + (prompt ? '<span class="generation-result-prompt">' + S.escapeHtml(prompt) + '</span>' : '')
      + '</span>'
      + '</button></div>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedVideo
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderGeneratedVideo(url, generationMeta) {
    const safeUrl = S.escapeHtml(url);
    return '<div class="gen-media-card gen-video-card">'
      + '<video class="gen-video" src="' + safeUrl + '" controls playsinline preload="metadata"></video>'
      + renderGeneratedActions(url, 'video', completedGenerationJobId(null, generationMeta), generationMeta && generationMeta.status)
      + '</div>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedAudio
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderGeneratedAudio(url, kind, generationMeta) {
    const safeUrl = S.escapeHtml(url);
    const safeKind = kind || 'audio';
    const isVoice = safeKind === 'voice';
    return '<div class="gen-media-card gen-audio-card ' + (isVoice ? 'gen-voice-card' : '') + '" data-audio-url="' + safeUrl + '" data-title="' + (isVoice ? 'Озвучка' : 'Untitled Track') + '">'
      + '<div class="generation-info-preview generation-info-audio-preview"><span>' + (isVoice ? 'VO' : '♪') + '</span></div>'
      + (isVoice
        ? '<audio class="gen-audio-player" src="' + safeUrl + '" controls preload="metadata" controlsList="nodownload"></audio>'
        : '')
      + renderGeneratedActions(url, isVoice ? 'voice' : 'audio', completedGenerationJobId(null, generationMeta), generationMeta && generationMeta.status)
      + '</div>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderGeneratedFile
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderGeneratedFile(url) {
    return '<div class="gen-media-card gen-file-card">'
      + '<span class="gen-file-label">Generated file</span>'
      + renderGeneratedActions(url, 'file')
      + '</div>';
  }

  function attachmentUrl(att) {
    if (!att || typeof att !== 'object') return '';
    if (att.url) return String(att.url);
    if (att.previewUrl) return String(att.previewUrl);
    if (att.dataBase64) return 'data:' + S.escapeHtml(att.mime || 'application/octet-stream') + ';base64,' + att.dataBase64;
    return '';
  }

  function renderMessageAttachment(att) {
    if (!att || typeof att !== 'object') return '';
    const url = attachmentUrl(att);
    const mime = String(att.mime || '');
    const kind = String(att.kind || '').toLowerCase();
    const name = S.escapeHtml(att.name || 'Файл');
    const safeUrl = S.escapeHtml(url);
    if (!url) return '';
    if (kind === 'image' || mime.startsWith('image/')) {
      return '<div class="msg-attachment msg-attachment-image"><img src="' + safeUrl + '" alt="' + name + '" /></div>';
    }
    if (kind === 'video' || mime.startsWith('video/')) {
      return '<div class="msg-attachment msg-attachment-video"><video src="' + safeUrl + '" controls playsinline preload="metadata"></video></div>';
    }
    if (kind === 'audio' || mime.startsWith('audio/')) {
      return '<div class="msg-attachment msg-attachment-audio"><audio src="' + safeUrl + '" controls preload="metadata"></audio></div>';
    }
    return '<a class="msg-attachment msg-attachment-file" href="' + safeUrl + '" target="_blank" rel="noopener" download="' + name + '">'
      + '<span>📎</span><b>' + name + '</b>'
      + '</a>';
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderChat
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderChat() {
    const el = document.getElementById('chatArea'); if (!el) return;
    el.innerHTML = chatMessages.map((m, i) => {
      if (m.textLoading) {
        return '<div class="msg ai text-loading-msg" data-i="' + i + '"><div class="ai-avatar">S</div>'
          + renderTextLoadingDots()
          + '</div>';
      }
      if (m.imageLoading || m.generationLoading) {
        return '<div class="msg ai generation-loading-msg" data-i="' + i + '" data-generation-token="' + S.escapeHtml(m.activeGenerationToken || '') + '"><div class="ai-avatar">S</div>'
          + renderGenerationLoadingCard(m)
          + '</div>';
      }
      if (m.insufficientBalance) {
        return '<div class="msg ai generation-balance-msg" data-i="' + i + '"><div class="ai-avatar">S</div>'
          + renderInsufficientBalanceCard(m, i)
          + '</div>';
      }
      if (m.imageResultMini) {
        return '<div class="msg ai generation-result-msg" data-i="' + i + '"><div class="ai-avatar">S</div>'
          + renderImageResultMiniCard(m, i)
          + '</div>';
      }
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
      if (m.attachment) inner += renderMessageAttachment(m.attachment);
      if (m.referenceImages && m.referenceImages.length) {
        inner += '<div class="msg-ref-img-row">' + m.referenceImages.map((url) =>
            '<span class="msg-ref-img"><img src="' + S.escapeHtml(url) + '" alt="reference image" /></span>'
        ).join('') + '</div>';
        }
      if (m.referenceVideos && m.referenceVideos.length) {
        inner += '<div class="msg-ref-video-row">' + m.referenceVideos.map((url) =>
            '<span class="msg-ref-video"><video src="' + S.escapeHtml(url) + '" controls playsinline preload="metadata"></video></span>'
        ).join('') + '</div>';
      }
      const imageUrls = generatedUrlsFromMessage(m, 'image');
      const imageThumbs = generatedThumbsFromMessage(m);
      const videoUrls = generatedUrlsFromMessage(m, 'video');
      const audioUrls = generatedUrlsFromMessage(m, 'audio');
      const fileUrls = generatedUrlsFromMessage(m, 'file');
      if (m.role === 'ai' && (imageUrls.length || videoUrls.length || audioUrls.length)) {
        const metaType = m.metadata && m.metadata.type ? String(m.metadata.type) : '';
        const resultType = videoUrls.length ? 'video' : (audioUrls.length ? (metaType === 'voice' || currentChatType() === 'voice' ? 'voice' : 'music') : 'image');
        m.imageResultMini = true;
        m.metadata = Object.assign({
          type: resultType,
          result_url: videoUrls[0] || audioUrls[0] || imageUrls[0] || '',
          image_url: imageUrls[0] || '',
          thumb_url: imageThumbs[0] || '',
          thumbnail_url: imageThumbs[0] || '',
          result_images: imageUrls,
          result_thumbnails: imageThumbs.length ? imageThumbs : [],
          video_url: videoUrls[0] || '',
          videos: videoUrls,
          audio_url: audioUrls[0] || '',
          audios: audioUrls,
          prompt: m.text || '',
        }, m.metadata || {});
        inner += renderImageResultMiniCard(m, i);
        return '<div class="msg ' + m.role + '" data-i="' + i + '">'
          + '<div class="ai-avatar">S</div>'
          + '<div class="bubble">' + inner + '</div>' + actions + '</div>';
      }
      if (imageUrls.length) {
        // =====================================================
        // JAVASCRIPT-БЛОК: imageItems
        // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
        // =====================================================
        const imageItems = imageUrls.map((url, idx) => ({ url, thumb: imageThumbs[idx] || url }));
        inner += '<div class="gen-img-grid">' + imageItems.map((item, idx) => renderGeneratedImage(item, idx, m.metadata || {})).join('') + '</div>';
      }
      if (videoUrls.length) inner += '<div class="gen-media-list">' + videoUrls.map((url) => renderGeneratedVideo(url, m.metadata || {})).join('') + '</div>';
      if (audioUrls.length) {
        const metaType = m.metadata && m.metadata.type ? String(m.metadata.type) : '';
        inner += '<div class="gen-media-list">' + audioUrls.map((url) => renderGeneratedAudio(url, metaType === 'voice' || currentChatType() === 'voice' ? 'voice' : 'audio', m.metadata || {})).join('') + '</div>';
      }
      if (fileUrls.length) inner += '<div class="gen-media-list">' + fileUrls.map(renderGeneratedFile).join('') + '</div>';
      if (m.attachmentName) inner = '<div style="opacity:.7;font-size:12px;margin-bottom:4px">📎 ' + S.escapeHtml(m.attachmentName) + '</div>' + inner;
      return '<div class="msg ' + m.role + '" data-i="' + i + '">'
        + (m.role === 'ai' ? '<div class="ai-avatar">S</div>' : '')
        + '<div class="bubble">' + inner + '</div>' + actions + '</div>';
    }).join('');
    el.scrollTop = el.scrollHeight;
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderDynamic
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  const HOME_QUICK_TOOLS = [
    {key:'try_on',title:'Try‑On',note:'Виртуальная примерка',image:'assets/quick-tools/try-on.jpg'},
    {key:'remove_bg',title:'Удаление фона',note:'Чистый фон за один шаг',image:'assets/quick-tools/remove-background.jpg'},
    {key:'replace_character',title:'Замена персонажа',note:'Сохранение сцены и позы',image:'assets/quick-tools/replace-character.jpg'},
    {key:'enhance',title:'Улучшение фото',note:'Детализация и качество',image:'assets/quick-tools/enhance-photo.jpg'},
    {key:'animate_photo',title:'Оживление фото',note:'Фото превращается в видео',image:'assets/quick-tools/animate-photo.jpg'},
    {key:'tattoo',title:'Тату',note:'Реалистичное нанесение',image:'assets/quick-tools/tattoo.jpg'},
    {key:'logo',title:'Лого',note:'Размещение на изображении',image:'assets/quick-tools/logo-placement.jpg'},
    {key:'remove_object',title:'Удаление предмета',note:'Восстановление фона',image:'assets/quick-tools/remove-object.jpg'},
    {key:'replace_object',title:'Замена предмета',note:'Новый объект в сцене',image:'assets/quick-tools/replace-object.jpg'},
  ];
  let homeQuickOffset = 0;
  let homeQuickTimer = null;
  let homeQuickDragStart = 0;
  let homeQuickDragScrollStart = 0;
  let homeQuickDragging = false;
  let homeQuickMoved = false;
  let profileGalleryItems = [];
  let profileGalleryFilter = 'all';
  const HOME_AI_MODELS = [
    ['seedream','Seedream 5.0 Lite'],['seedream','Seedream 4.5'],['ideogram','Ideogram 4.0'],['recraft','Recraft V4.1 Pro'],['openai','GPT Image 2'],['flux','FLUX.2 Turbo'],['qwen','Qwen Image 2 Pro'],['nanoBanana','Nano Banana 2'],['google','Imagen 4 Ultra'],['grok','Grok Pro'],
    ['kling','Kling 3.0'],['veo','Veo 3.1'],['runway','Runway Gen-4.5'],['seedance','Seedance 2.0'],['sora','Sora 2 Pro'],['luma','Luma Ray v3.2'],['hailuo','Hailuo 2.3'],['pixverse','PixVerse v6'],['heygen','HeyGen V3'],
    ['suno','Suno Chirp v5.5'],['minimax','MiniMax Music 2.5'],['lyria','Lyria 3 Pro'],['elevenlabs','ElevenLabs v3'],['gemini','Gemini 3.1 TTS'],
    ['openai','GPT-5.6'],['gemini','Gemini 3.1 Pro'],['grok','Grok 4.1'],['qwen','Qwen Max'],['byteplus','BytePlus Seed 2.0']
  ];
  function homeModelLogo(family){const logos={openai:'<path d="M12 3a4.5 4.5 0 0 1 4.4 3.5 4.5 4.5 0 0 1 2.1 7.8 4.5 4.5 0 0 1-6.5 4.3 4.5 4.5 0 0 1-6.4-4.4A4.5 4.5 0 0 1 7.7 6.5 4.5 4.5 0 0 1 12 3Z"/><path d="m8 8 8 5M16 8l-8 5M12 5v14"/>',gemini:'<path d="M12 2c.6 5.4 4.6 9.4 10 10-5.4.6-9.4 4.6-10 10-.6-5.4-4.6-9.4-10-10 5.4-.6 9.4-4.6 10-10Z"/>',flux:'<path d="m4 18 5-12 3 7 3-9 5 14M5 18h14"/>',qwen:'<circle cx="12" cy="12" r="8"/><path d="M9 9h6v6H9zM15 15l4 4"/>',grok:'<path d="M5 5h14L8 19h11M5 19 19 5"/>',kling:'<path d="M6 3v18M18 3 8 12l10 9"/>',veo:'<path d="m3 6 9 15 9-15h-5l-4 8-4-8Z"/>',runway:'<path d="M5 4h6a5 5 0 0 1 0 10H5zM12 14l7 6"/>',seedance:'<path d="M5 17c4-10 10-10 14 0M7 8c3-4 7-4 10 0"/>',sora:'<circle cx="12" cy="12" r="8"/><path d="M8 15c1-6 7-6 8 0"/>',suno:'<path d="M4 15V9M8 18V6M12 16V8M16 20V4M20 15V9"/>',elevenlabs:'<path d="M8 5v14M12 5v14M16 8v8"/>',ideogram:'<rect x="5" y="5" width="14" height="14" rx="4"/><path d="M9 9h6v6H9z"/>',recraft:'<path d="M6 19V5h7a4 4 0 0 1 0 8H6M12 13l6 6"/>',seedream:'<path d="M12 21V9M12 13c-5 0-7-3-7-7 5 0 7 3 7 7Zm0-3c4 0 6-2 6-6-4 0-6 2-6 6Z"/>',google:'<path d="M20 12h-8v4h4.6A6 6 0 1 1 16 7.2"/>',lyria:'<path d="M9 18V5l10-2v13M9 9l10-2"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',minimax:'<path d="M4 18V6l4 7 4-7 4 7 4-7v12"/>',hailuo:'<path d="M4 14c4-8 12-8 16 0-4 6-12 6-16 0Z"/>',pixverse:'<path d="M5 5h8a5 5 0 0 1 0 10H5zM9 9h4"/>',heygen:'<path d="M5 5v14M19 5v14M5 12h14"/>',luma:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',byteplus:'<path d="m5 3 14 9-14 9V3Zm4 7v4l4-2Z"/>'};return '<svg viewBox="0 0 24 24" aria-hidden="true">'+(logos[family]||logos.gemini)+'</svg>'}
  function existingHomeModelLogo(family){const aliases={lyria:'gemini',byteplus:'bytedance'},key=aliases[family]||family,value=AI_LOGOS[key];if(value==='custom-banana')return imageModelIconHtml({id:'nano-banana-2',icon:'nanoBanana'});if(value)return '<span class="ai-model-mask" style="--ai-model-icon:url(&quot;'+S.escapeHtml(value)+'&quot;)"></span>';return homeModelLogo(family)}
  function renderHomeAiModels(){const host=document.getElementById('homeAiModelStrip');if(!host)return;const chips=HOME_AI_MODELS.map(([family,label])=>'<span class="ai-chip ai-'+family+'"><i>'+existingHomeModelLogo(family)+'</i><b>'+S.escapeHtml(label)+'</b></span>').join('');host.innerHTML=chips+chips}
  const CREATIVE_CATALOGS = {
    image:{title:'Каталог изображений',lead:'Референсы, стили, форматы и инструменты',groups:[['Живые референсы',[['photo','Галерея фото','Полный каталог готовых изображений'],['portrait','Портрет','Editorial portrait, natural skin, cinematic light'],['product','Предметное фото','Premium product photography, clean studio light'],['interior','Интерьер','Modern interior, realistic materials, architectural light']]],['Стили',[['cinematic','Кино','Cinematic still, dramatic light, film color grading'],['anime','Anime','Premium anime illustration, detailed background'],['realism','Фотореализм','Ultra realistic photography, authentic details'],['3d','3D','High-end 3D render, detailed materials'],['watercolor','Акварель','Elegant watercolor painting, textured paper'],['fashion','Fashion','High fashion editorial, magazine composition']]],['Форматы',[['square','1:1','Square social media composition'],['portrait-format','9:16','Vertical stories and reels composition'],['post-format','4:5','Vertical social post composition'],['wide-format','16:9','Wide cinematic composition']]],['Лого и тату',[['logo','Логотипы','Размещение и варианты логотипа'],['tattoo','Татуировки','Варианты и реалистичная примерка'],['remove_bg','Удаление фона','Чистое отделение объекта'],['try_on','Try On','Примерка одежды по референсам']]]]},
    music:{title:'Каталог музыки',lead:'Жанры, настроение, вокал и музыкальные идеи',groups:[['Жанры',[['pop','Pop','Modern radio pop, memorable chorus'],['hiphop','Hip-Hop','Modern hip-hop, deep bass, crisp drums'],['electronic','Electronic','Atmospheric synths, energetic rhythm'],['rock','Rock','Powerful rock, live drums and guitars'],['cinematic-music','Cinematic','Epic orchestral cinematic score'],['ambient','Ambient','Calm soundscape and soft textures']]],['Настроение',[['happy','Светлое','Uplifting, bright and optimistic song'],['dark','Тёмное','Dark mysterious emotional atmosphere'],['romantic','Романтика','Warm intimate romantic melody'],['energetic','Энергия','Fast energetic anthem']]],['Форматы',[['instrumental','Инструментал','Instrumental only, no vocals'],['song','Песня','Complete song with expressive vocal'],['jingle','Джингл','Short memorable commercial jingle'],['soundtrack','Саундтрек','Soundtrack for visual storytelling']]]]},
    text:{title:'Каталог текстов',lead:'Готовые структуры для контента и бизнеса',groups:[['Форматы',[['post','Пост','Напиши структурированный пост для социальной сети на тему:'],['article','Статья','Напиши подробную экспертную статью на тему:'],['script','Сценарий','Создай динамичный сценарий короткого видео:'],['ad','Реклама','Создай убедительный рекламный текст:'],['story','История','Напиши эмоциональную историю:'],['email','Письмо','Подготовь профессиональное деловое письмо:']]]]},
    code:{title:'Code & Build',lead:'Разработка, проверка и улучшение кода',groups:[['Задачи',[['build','Создать','Реализуй функцию по техническому заданию:'],['review','Code review','Проведи тщательный code review:'],['fix','Исправить','Найди ошибку и предложи безопасное исправление:'],['refactor','Рефакторинг','Улучши структуру кода без изменения поведения:'],['tests','Тесты','Напиши полный набор тестов:'],['explain','Объяснение','Объясни следующий код простым языком:']]]]},
    research:{title:'Research Assistant',lead:'Исследование, сравнение и анализ',groups:[['Режимы',[['summary','Резюме','Сделай точное структурированное резюме:'],['compare','Сравнение','Сравни варианты по фактам, выгодам и рискам:'],['sources','Источники','Проанализируй надёжность источников:'],['plan','План','Составь подробный план исследования:'],['facts','Факты','Проверь фактические утверждения:'],['report','Отчёт','Подготовь профессиональный аналитический отчёт:']]]]},
    vision:{title:'Vision & Analysis',lead:'Анализ изображений, дизайна и документов',groups:[['Инструменты',[['describe','Описание','Подробно опиши изображение и визуальный стиль'],['extract','Текст','Извлеки весь текст и сохрани структуру'],['design','Дизайн','Проанализируй дизайн, цвета и типографику'],['compare-vision','Сравнение','Сравни изображения и перечисли различия'],['document','Документ','Выдели ключевые положения документа'],['photo','Референсы','Открыть полный каталог изображений']]]]},
  };
  function creativeCatalogIcon(){return '<svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18"/></svg>'}
  function openCreativeCatalog(kind){const data=CREATIVE_CATALOGS[kind]||CREATIVE_CATALOGS.image;let modal=document.getElementById('creativeCatalogModal');if(!modal){modal=document.createElement('div');modal.id='creativeCatalogModal';modal.className='creative-catalog';modal.onclick=closeCreativeCatalog;document.body.appendChild(modal)}modal.innerHTML='<section onclick="event.stopPropagation()"><header><div><small>SYLVEX Catalog</small><h2>'+S.escapeHtml(data.title)+'</h2><p>'+S.escapeHtml(data.lead)+'</p></div><button onclick="SYLVEX.closeCreativeCatalog(event)">×</button></header><main>'+data.groups.map(group=>'<div class="creative-group"><h3>'+S.escapeHtml(group[0])+'</h3><div>'+group[1].map(item=>'<button onclick="SYLVEX.useCreativeCatalogItem(event,\''+S.escapeHtml(kind)+'\',\''+S.escapeHtml(item[0])+'\',\''+S.escapeHtml(item[2])+'\')"><i>'+creativeCatalogIcon()+'</i><span><b>'+S.escapeHtml(item[1])+'</b><small>'+S.escapeHtml(item[2])+'</small></span></button>').join('')+'</div></div>').join('')+'</main></section>';modal.classList.add('show')}
  function closeCreativeCatalog(event){if(event){event.preventDefault();event.stopPropagation()}document.getElementById('creativeCatalogModal')?.classList.remove('show')}
  function useCreativeCatalogItem(event,kind,key,prompt){if(event){event.preventDefault();event.stopPropagation()}closeCreativeCatalog();if(key==='photo'){openPhotoCatalog();return}if(['logo','tattoo','remove_bg','try_on'].includes(key)){openPhotoToolModal(null,key);return}const mode=kind==='image'||kind==='vision'?'image':kind==='music'?'music':'text';switchView('tools');updateComposerMode(mode);if(mode==='music'&&['pop','hiphop','electronic','rock','ambient'].includes(key))musicState.genre=key;window.setTimeout(()=>{const input=document.getElementById('chatInput');if(input){input.value=prompt;autoGrow(input);input.focus()}if(mode==='image')renderImageControls();if(mode==='music')renderMusicControls();updateSendButton()},80)}
  let communityItems = [];
  function communitySvg(kind) {
    const paths={heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',comment:'<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"/>',send:'<path d="m21 3-7 18-4-7-7-4Z"/><path d="m10 14 11-11"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>'};return '<svg viewBox="0 0 24 24" aria-hidden="true">'+paths[kind]+'</svg>';
  }
  function communityRank(likes){const n=Number(likes||0);if(n>=10000)return{name:'Легенда',icon:'✦',level:5};if(n>=2500)return{name:'Мастер',icon:'◆',level:4};if(n>=500)return{name:'Творец',icon:'✧',level:3};if(n>=100)return{name:'Автор',icon:'◇',level:2};return{name:'Новичок',icon:'·',level:1}}
  function renderCommunitySideContent(){const popular=document.getElementById('communityPopular'),authors=[];communityItems.forEach(item=>{if(!item.demo&&!authors.some(a=>String(a.author_id)===String(item.author_id)))authors.push(item)});const own=S.user||{},ownId=getTelegramId(),ownPosts=communityItems.filter(i=>String(i.author_id)===String(ownId)),likes=ownPosts.reduce((sum,i)=>sum+Number(i.likes||0),0),rank=communityRank(likes);const avatarMarkup=a=>a.author_avatar?'<img src="'+S.escapeHtml(a.author_avatar)+'" alt="">':S.escapeHtml(String(a.author_name||'SY').slice(0,2).toUpperCase());const ownData={author_name:own.display_name||own.first_name||'SYLVEX User',author_avatar:own.custom_avatar_url||own.photo_url||''};['communityComposerAvatar','communitySideAvatar'].forEach(id=>{const el=document.getElementById(id);if(el){el.innerHTML=avatarMarkup(ownData);el.dataset.rank=rank.level}});const set=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value};set('communityCardName',ownData.author_name+' '+rank.icon);set('communitySideName',ownData.author_name);set('communityCardStatus',rank.name+' · активен');set('communityStatPosts',ownPosts.length);set('communityStatLikes',likes);set('communityStatFollowing',0);set('communityStatFriends',0);if(popular)popular.innerHTML=authors.slice(0,4).map(a=>'<button type="button" onclick="SYLVEX.openCommunityUserCard('+Number(a.author_id)+')"><span class="community-avatar">'+avatarMarkup(a)+'</span><span><b>'+S.escapeHtml(a.author_name||'SYLVEX User')+'</b><small>'+S.escapeHtml(a.author_username?'@'+a.author_username:'Автор SYLVEX')+'</small></span><i>Открыть</i></button>').join('')||'<p>Авторы появятся после первых публикаций.</p>'}
  function renderCommunityFeed() {
    const host=document.getElementById('communityFeed');if(!host)return;
    renderCommunitySideContent();if(!communityItems.length){host.innerHTML='<div class="community-state">Пока нет публикаций. Станьте первым автором сообщества.</div>';return;}
    host.innerHTML=communityItems.map(item=>{const type=normalizeGalleryType(item.type),media=String(item.media_url||''),urls=(item.media_urls||[media]).filter(Boolean).slice(0,4),avatar=item.author_avatar?'<img src="'+S.escapeHtml(item.author_avatar)+'" alt="">':S.escapeHtml(String(item.author_name||'S').slice(0,2).toUpperCase()),ago=item.created_at?new Date(item.created_at).toLocaleDateString():'недавно',rank=communityRank(item.author_likes||item.likes);let content='';if(type==='image'&&urls.length)content='<div class="community-photo-grid count-'+urls.length+'">'+urls.map(url=>'<img src="'+S.escapeHtml(url)+'" alt="" loading="lazy">').join('')+'</div>';else if(type==='video'&&media)content='<video src="'+S.escapeHtml(media)+'" controls playsinline preload="metadata"></video>';else if(type==='music'&&media)content='<div class="community-audio">'+profileGalleryIcon(type)+'<audio controls src="'+S.escapeHtml(media)+'"></audio></div>';const id=Number(item.id||0),caption=String(item.body||'').trim();return '<article class="community-post" data-community-search="'+S.escapeHtml((String(item.author_name||'')+' '+caption+' '+String(item.model||'')).toLowerCase())+'"><header><button class="community-author-button" onclick="SYLVEX.openCommunityUserCard('+Number(item.author_id||0)+')"><span class="community-avatar" data-rank="'+rank.level+'">'+avatar+'</span><span><b>'+S.escapeHtml(item.author_name||'SYLVEX User')+' <em>'+rank.icon+'</em></b><small>'+S.escapeHtml(ago)+' · '+rank.name+'</small></span></button>'+(item.demo?'':'<span class="community-author-actions"><button onclick="SYLVEX.followCommunityAuthor('+Number(item.author_id||0)+')">Подписаться</button><button onclick="SYLVEX.messageCommunityAuthor('+Number(item.author_id||0)+')">Написать</button></span>')+'</header>'+(caption?'<p class="community-caption">'+S.escapeHtml(caption)+'</p>':'')+'<div class="community-media">'+content+'</div><footer><button data-community-like="'+id+'" class="'+(item.liked?'liked':'')+'" type="button" '+(item.demo?'onclick="SYLVEX.communityComingSoon(\'Демо публикация\')"':'onclick="SYLVEX.toggleCommunityLike('+id+',this)"')+'>'+communitySvg('heart')+'<span>'+Number(item.likes||0)+'</span></button><button type="button" '+(item.demo?'onclick="SYLVEX.communityComingSoon(\'Демо публикация\')"':'onclick="SYLVEX.openCommunityComments('+id+')"')+'>'+communitySvg('comment')+'<span>'+Number(item.comments||0)+'</span></button></footer></article>'}).join('');
  }
  function searchCommunity(value){const q=String(value||'').trim().toLowerCase();document.querySelectorAll('.community-post').forEach(post=>{post.hidden=!!q&&!String(post.dataset.communitySearch||'').includes(q)})}
  function toggleCommunityMenu(force){const app=document.querySelector('.community-app');if(app)app.classList.toggle('menu-open',typeof force==='boolean'?force:!app.classList.contains('menu-open'))}
  function communityComingSoon(name){toast(name+' — скоро')}
  function communityDemoPost(){return{id:-1,demo:true,author_id:0,author_name:'SYLVEX Community',author_username:'sylvex',type:'image',media_url:'assets/community-demo-post.jpeg',media_urls:['assets/community-demo-post.jpeg'],body:'Добро пожаловать в сообщество SYLVEX. Здесь авторы делятся своими работами и вдохновляют друг друга.',likes:128,comments:14,created_at:new Date().toISOString(),author_likes:10000}}
  async function loadCommunityFeed(force){if(communityItems.length&&!force)return renderCommunityFeed();const host=document.getElementById('communityFeed');if(host)host.innerHTML='<div class="community-state">Загрузка публикаций…</div>';try{const r=await fetch('/api/public/community/feed?telegram_id='+encodeURIComponent(getTelegramId()||0),{cache:'no-store'});const j=await r.json(),allowed=new Set(['image','video','music']);communityItems=[communityDemoPost()].concat((Array.isArray(j.items)?j.items:[]).filter(item=>allowed.has(normalizeGalleryType(item.type))));renderCommunityFeed()}catch(_){communityItems=[communityDemoPost()];renderCommunityFeed()}}
  function openCommunityUserCard(authorId){const own=S.user||{},post=communityItems.find(i=>String(i.author_id)===String(authorId))||{},isOwn=!authorId||String(authorId)===String(getTelegramId()),name=isOwn?(own.display_name||own.first_name||'SYLVEX User'):(post.author_name||'SYLVEX User'),avatar=isOwn?(own.custom_avatar_url||own.photo_url||''):(post.author_avatar||''),posts=communityItems.filter(i=>String(i.author_id)===String(authorId)).length,likes=communityItems.filter(i=>String(i.author_id)===String(authorId)).reduce((s,i)=>s+Number(i.likes||0),0),rank=communityRank(likes);let modal=document.getElementById('communityUserModal');if(!modal){modal=document.createElement('div');modal.id='communityUserModal';modal.className='community-modal community-user-modal';document.body.appendChild(modal)}modal.innerHTML='<section><header><h3>Карточка пользователя</h3><button onclick="this.closest(\'.community-modal\').classList.remove(\'show\')">'+communitySvg('close')+'</button></header><div class="community-profile-card"><span class="community-avatar" data-rank="'+rank.level+'">'+(avatar?'<img src="'+S.escapeHtml(avatar)+'" alt="">':S.escapeHtml(name.slice(0,2)))+'</span><h2>'+S.escapeHtml(name)+' <em>'+rank.icon+'</em></h2><p>'+rank.name+' · активен</p><div><span><b>'+posts+'</b><small>Публикаций</small></span><span><b>'+likes+'</b><small>Лайков</small></span><span><b>0</b><small>Подписок</small></span><span><b>0</b><small>Друзей</small></span></div>'+(isOwn?'':'<footer><button onclick="SYLVEX.followCommunityAuthor('+Number(authorId)+')">Подписаться</button><button onclick="SYLVEX.messageCommunityAuthor('+Number(authorId)+')">Написать</button></footer>')+'</div></section>';modal.classList.add('show')}
  function followCommunityAuthor(){toast('Подписка оформлена')}
  function messageCommunityAuthor(){communityComingSoon('Личные сообщения')}
  function shareCommunityPost(){if(navigator.share)navigator.share({title:'SYLVEX Community',url:location.href}).catch(()=>{});else toast('Ссылка скопирована')}
  function downloadCommunityPost(url){if(!url)return;const a=document.createElement('a');a.href=url;a.download='sylvex-community';a.target='_blank';a.click()}
  async function toggleCommunityLike(id,button){const item=communityItems.find(x=>Number(x.id)===Number(id));if(!item||button?.disabled)return;const previous=!!item.liked;item.liked=!previous;item.likes=Math.max(0,Number(item.likes||0)+(item.liked?1:-1));if(button){button.disabled=true;button.classList.toggle('liked',item.liked);button.querySelector('span').textContent=item.likes}try{const r=await fetch('/api/public/community/posts/'+id+'/like',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),initData:S.tg&&S.tg.initData||''})});const j=await r.json();if(!r.ok||j.error)throw new Error(j.error||'like_failed');if(item.liked!==!!j.liked){item.likes=Math.max(0,item.likes+(j.liked?1:-1));item.liked=!!j.liked}if(button){button.classList.toggle('liked',item.liked);button.querySelector('span').textContent=item.likes}}catch(_){item.liked=previous;item.likes=Math.max(0,item.likes+(previous?1:-1));if(button){button.classList.toggle('liked',item.liked);button.querySelector('span').textContent=item.likes}}finally{if(button)button.disabled=false}}
  async function openCommunityPublisher(){await loadProfileGallery(false);let modal=document.getElementById('communityPublishModal');if(!modal){modal=document.createElement('div');modal.id='communityPublishModal';modal.className='community-modal';document.body.appendChild(modal)}const allowed=new Set(['image','video','music']),items=profileGalleryItems.filter(item=>allowed.has(normalizeGalleryType(item.type))),choices=items.map(item=>{const kind=normalizeGalleryType(item.type);return '<label class="community-publish-choice" data-kind="'+kind+'" hidden><input type="checkbox" value="'+S.escapeHtml(String(item.id))+'" data-kind="'+kind+'" onchange="SYLVEX.limitCommunitySelection(this)"><span>'+profileGalleryIcon(kind)+'</span><b>'+S.escapeHtml(String(item.prompt||item.text||'Генерация').slice(0,70))+'</b></label>'}).join(''),typeButton=(kind,label)=>'<button type="button" data-kind="'+kind+'" onclick="SYLVEX.filterCommunityPublisher(\''+kind+'\')"><span>'+profileGalleryIcon(kind)+'</span><b>'+label+'</b></button>';modal.innerHTML='<section><header><div><small>Новая публикация</small><h3>Выберите медиа</h3></div><button onclick="this.closest(\'.community-modal\').classList.remove(\'show\')">'+communitySvg('close')+'</button></header><div class="community-publish-types">'+typeButton('image','Фото')+typeButton('video','Видео')+typeButton('music','Музыка')+'</div><div class="community-publish-list">'+(choices||'<p>Сначала создайте фото, видео или музыку в Pro Studio.</p>')+'</div><div class="community-caption-field" hidden><textarea id="communityCaption" maxlength="360" rows="3" placeholder="Добавьте подпись…"></textarea><small>Необязательно</small></div><button class="community-publish-submit" onclick="SYLVEX.publishCommunitySelection()">Опубликовать</button></section>';modal.classList.add('show')}
  function filterCommunityPublisher(kind){const modal=document.getElementById('communityPublishModal');if(!modal)return;modal.querySelectorAll('.community-publish-types button').forEach(button=>button.classList.toggle('active',button.dataset.kind===kind));modal.querySelectorAll('.community-publish-choice').forEach(choice=>{choice.hidden=choice.dataset.kind!==kind;const input=choice.querySelector('input');input.checked=false;input.disabled=false});modal.querySelector('.community-caption-field').hidden=true}
  function limitCommunitySelection(input){const modal=document.getElementById('communityPublishModal'),checked=Array.from(modal.querySelectorAll('.community-publish-choice input:checked'));if(checked.length>4){input.checked=false;toast('Можно выбрать не более четырёх фотографий');return}if(checked.length>1&&checked.some(el=>el.dataset.kind!=='image')){input.checked=false;toast('Несколько файлов можно объединять только для фотографий')}const selected=Array.from(modal.querySelectorAll('.community-publish-choice input:checked'));modal.querySelectorAll('.community-publish-choice input').forEach(el=>{el.disabled=selected.length>0&&el.dataset.kind!==selected[0].dataset.kind});modal.querySelector('.community-caption-field').hidden=!selected.length}
  async function publishCommunitySelection(){const ids=Array.from(document.querySelectorAll('#communityPublishModal input:checked')).map(el=>Number(el.value)),caption=document.getElementById('communityCaption')?.value.trim()||'';if(!ids.length){toast('Выберите работу');return}if(/(?:https?:\/\/|www\.|t\.me\/|@[A-Za-z0-9_]{4,})/i.test(caption)){toast('Сторонние ссылки в подписи запрещены');return}try{const r=await fetch('/api/public/community/posts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),message_ids:ids,caption,initData:S.tg&&S.tg.initData||''})});const j=await r.json();if(!r.ok||j.error)throw new Error(j.error||'publish_failed');document.getElementById('communityPublishModal').classList.remove('show');toast('Работа опубликована');loadCommunityFeed(true)}catch(_){toast('Не удалось опубликовать работу')}}
  function publishCommunityItem(id){return publishCommunitySelection(id)}
  function communityCommentTime(value){if(!value)return'';const date=new Date(value),seconds=Math.max(0,Math.floor((Date.now()-date.getTime())/1000));if(seconds<60)return'только что';if(seconds<3600)return Math.floor(seconds/60)+' мин.';if(seconds<86400)return Math.floor(seconds/3600)+' ч.';return date.toLocaleDateString([], {day:'2-digit',month:'2-digit',year:'numeric'})+' '+date.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
  function renderCommunityComments(modal,postId,items){modal.dataset.postId=postId;modal._communityComments=items;modal.querySelector('.community-comments').innerHTML=items.map(c=>'<article class="community-comment '+(c.parent_comment_id?'reply':'')+'" data-comment-id="'+Number(c.id)+'"><span class="community-avatar">'+(c.author_avatar?'<img src="'+S.escapeHtml(c.author_avatar)+'" alt="">':S.escapeHtml(String(c.author_name||'S').slice(0,2)))+'</span><div><header><b>'+S.escapeHtml(c.author_name||'User')+'</b><time>'+S.escapeHtml(communityCommentTime(c.created_at))+(c.edited_at?' · изменено':'')+'</time></header>'+(c.reply_to_name?'<small>Ответ для '+S.escapeHtml(c.reply_to_name)+'</small>':'')+'<p>'+S.escapeHtml(c.body)+'</p><footer><button type="button" onclick="SYLVEX.replyCommunityComment('+Number(c.id)+')">Ответить</button><button type="button" class="'+(c.liked?'liked':'')+'" onclick="SYLVEX.likeCommunityComment('+Number(c.id)+',this)">'+communitySvg('heart')+' <span>'+Number(c.likes||0)+'</span></button>'+(c.is_own?'<button type="button" onclick="SYLVEX.editCommunityComment('+Number(c.id)+')">Изменить</button><button type="button" onclick="SYLVEX.deleteCommunityComment('+Number(c.id)+')">Удалить</button>':'')+'</footer></div></article>').join('')||'<p class="community-comments-empty">Комментариев пока нет.</p>'}
  async function openCommunityComments(id){let modal=document.getElementById('communityCommentsModal');if(!modal){modal=document.createElement('div');modal.id='communityCommentsModal';modal.className='community-modal';document.body.appendChild(modal)}modal.innerHTML='<section><header><h3>Комментарии</h3><button onclick="this.closest(\'.community-modal\').classList.remove(\'show\')">'+communitySvg('close')+'</button></header><div class="community-comments">Загрузка…</div><div class="community-replying" hidden></div><form onsubmit="SYLVEX.sendCommunityComment(event,'+id+')"><input type="hidden" name="parent_comment_id"><input name="comment" maxlength="500" placeholder="Написать комментарий…" required><button type="submit">'+communitySvg('send')+'</button></form></section>';modal.classList.add('show');try{const r=await fetch('/api/public/community/posts/'+id+'/comments?telegram_id='+encodeURIComponent(getTelegramId()||0));const j=await r.json();renderCommunityComments(modal,id,j.items||[])}catch(_){modal.querySelector('.community-comments').textContent='Не удалось загрузить комментарии.'}}
  function replyCommunityComment(commentId){const modal=document.getElementById('communityCommentsModal'),form=modal?.querySelector('form'),comment=modal?._communityComments?.find(c=>Number(c.id)===Number(commentId));if(!form||!comment)return;const name=String(comment.author_name||'User');form.elements.parent_comment_id.value=commentId;form.elements.comment.placeholder='Ответ для '+name+'…';const note=modal.querySelector('.community-replying');note.hidden=false;note.innerHTML='Ответ для <b>'+S.escapeHtml(name)+'</b><button type="button" onclick="SYLVEX.cancelCommunityReply()">×</button>';form.elements.comment.focus()}
  function cancelCommunityReply(){const modal=document.getElementById('communityCommentsModal'),form=modal?.querySelector('form');if(!form)return;form.elements.parent_comment_id.value='';form.elements.comment.placeholder='Написать комментарий…';modal.querySelector('.community-replying').hidden=true}
  function updateCommunityCommentCount(postId,count){const post=document.querySelector('.community-post [data-community-like="'+Number(postId)+'"]')?.closest('.community-post'),counter=post?.querySelector('footer button:nth-child(2) span');if(counter)counter.textContent=Math.max(0,Number(count||0))}
  async function sendCommunityComment(event,id){event.preventDefault();const form=event.currentTarget,input=form.elements.comment,body=input.value.trim(),parent_comment_id=Number(form.elements.parent_comment_id.value||0);if(!body)return;input.disabled=true;try{const r=await fetch('/api/public/community/posts/'+id+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),body,parent_comment_id,initData:S.tg&&S.tg.initData||''})});if(!r.ok)throw new Error('comment_failed');input.value='';cancelCommunityReply();const item=communityItems.find(x=>Number(x.id)===Number(id));if(item){item.comments=Number(item.comments||0)+1;updateCommunityCommentCount(id,item.comments)}await openCommunityComments(id)}catch(_){toast('Не удалось отправить комментарий')}finally{input.disabled=false}}
  async function likeCommunityComment(commentId,button){if(button.disabled)return;button.disabled=true;try{const r=await fetch('/api/public/community/comments/'+commentId+'/like',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),initData:S.tg&&S.tg.initData||''})});const j=await r.json();if(!r.ok)throw new Error();const count=Number(button.querySelector('span').textContent||0)+(j.liked?1:-1);button.classList.toggle('liked',j.liked);button.querySelector('span').textContent=Math.max(0,count)}catch(_){toast('Не удалось поставить лайк')}finally{button.disabled=false}}
  async function editCommunityComment(commentId){const modal=document.getElementById('communityCommentsModal'),comment=modal?._communityComments?.find(c=>Number(c.id)===Number(commentId));if(!comment)return;const body=window.prompt('Изменить комментарий',comment.body);if(body===null||!body.trim())return;const r=await fetch('/api/public/community/comments/'+commentId,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),body:body.trim(),initData:S.tg&&S.tg.initData||''})});if(r.ok)openCommunityComments(Number(modal.dataset.postId));else toast('Не удалось изменить комментарий')}
  async function deleteCommunityComment(commentId){const modal=document.getElementById('communityCommentsModal');if(!modal||!window.confirm('Удалить комментарий?'))return;const r=await fetch('/api/public/community/comments/'+commentId,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:getTelegramId(),initData:S.tg&&S.tg.initData||''})});if(r.ok){const postId=Number(modal.dataset.postId),item=communityItems.find(x=>Number(x.id)===postId);if(item){item.comments=Math.max(0,Number(item.comments||0)-1);updateCommunityCommentCount(postId,item.comments)}openCommunityComments(postId)}else toast('Не удалось удалить комментарий')}
  function openHomeQuickTool(event, key) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    if (key === 'animate_photo') {
      switchView('tools');
      updateComposerMode('video');
      window.setTimeout(openVideoStartUpload, 120);
      return;
    }
    openPhotoToolModal(event, key);
  }
  function homeQuickCardHtml(item) { return '<button class="home-quick-card" type="button" data-tool="'+item.key+'"><span class="home-quick-preview"><img src="'+item.image+'" alt="" loading="lazy" decoding="async"></span><span class="home-quick-copy"><b>'+item.title+'</b><small>'+item.note+'</small></span><i>›</i></button>'; }
  function moveHomeQuickTools(direction) {
    const host=document.getElementById('homeHist'),track=host&&host.querySelector('.home-quick-track');if(!track)return;
    homeQuickOffset=(homeQuickOffset+(direction>0?1:HOME_QUICK_TOOLS.length-1))%HOME_QUICK_TOOLS.length;
    const card=track.children[homeQuickOffset];
    if(card)track.scrollTo({left:card.offsetLeft-track.offsetLeft,behavior:'smooth'});
  }
  function renderHomeQuickTools() {
    const host=document.getElementById('homeHist');if(!host)return;
    host.innerHTML='<div class="home-quick-track">'+HOME_QUICK_TOOLS.map(homeQuickCardHtml).join('')+'</div><div class="home-quick-dots">'+HOME_QUICK_TOOLS.map((_,index)=>'<span class="'+(index===homeQuickOffset?'active':'')+'"></span>').join('')+'</div>';
    if(!host.dataset.swipeBound){host.dataset.swipeBound='1';
      host.addEventListener('pointerdown',event=>{if(event.pointerType!=='mouse')return;const track=host.querySelector('.home-quick-track');if(!track)return;homeQuickDragStart=event.clientX;homeQuickDragScrollStart=track.scrollLeft;homeQuickDragging=true;homeQuickMoved=false;host.setPointerCapture(event.pointerId);host.classList.add('is-dragging');clearInterval(homeQuickTimer);homeQuickTimer=null});
      host.addEventListener('pointermove',event=>{if(!homeQuickDragging)return;const track=host.querySelector('.home-quick-track');if(!track)return;const dx=event.clientX-homeQuickDragStart;if(Math.abs(dx)>4)homeQuickMoved=true;track.scrollLeft=homeQuickDragScrollStart-dx});
      const finish=()=>{if(!homeQuickDragging)return;homeQuickDragging=false;host.classList.remove('is-dragging');homeQuickTimer=window.setInterval(()=>moveHomeQuickTools(1),5200)};
      host.addEventListener('pointerup',finish);host.addEventListener('pointercancel',finish);
      host.addEventListener('scroll',event=>{if(!event.target.classList.contains('home-quick-track'))return;const track=event.target,cards=Array.from(track.children);let nearest=0,best=Infinity;cards.forEach((card,index)=>{const distance=Math.abs(track.scrollLeft-(card.offsetLeft-track.offsetLeft));if(distance<best){best=distance;nearest=index}});if(nearest!==homeQuickOffset){homeQuickOffset=nearest;host.querySelectorAll('.home-quick-dots span').forEach((dot,index)=>dot.classList.toggle('active',index===nearest))}},true);
      host.addEventListener('touchstart',event=>{homeQuickDragStart=event.touches[0]?event.touches[0].clientX:0;homeQuickMoved=false;clearInterval(homeQuickTimer);homeQuickTimer=null},{passive:true});
      host.addEventListener('touchmove',event=>{const touch=event.touches[0];if(touch&&Math.abs(touch.clientX-homeQuickDragStart)>6)homeQuickMoved=true},{passive:true});
      ['touchend','touchcancel'].forEach(name=>host.addEventListener(name,()=>{clearInterval(homeQuickTimer);homeQuickTimer=window.setInterval(()=>moveHomeQuickTools(1),5200)},{passive:true}));
      host.addEventListener('click',event=>{const card=event.target.closest('[data-tool]');if(!card)return;if(homeQuickMoved){event.preventDefault();homeQuickMoved=false;return}openHomeQuickTool(event,card.dataset.tool)});
    }
    const track=host.querySelector('.home-quick-track'),card=track&&track.children[homeQuickOffset];if(card)track.scrollLeft=card.offsetLeft-track.offsetLeft;
    if(!homeQuickTimer)homeQuickTimer=window.setInterval(()=>moveHomeQuickTools(1),5200);
  }
  function profileGalleryIcon(kind) {
    const paths = {
      image:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m4 17 5-5 4 4 2-2 5 4"/>',
      video:'<rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3Z"/>',
      music:'<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
      voice:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
      text:'<path d="M6 3h9l4 4v14H6Z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>',
      open:'<path d="M4 12s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6Z"/><circle cx="12" cy="12" r="2"/>',
      download:'<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
      send:'<path d="m21 4-3 16-6-4-4 3 1-5 9-7-11 6-4-2Z"/>',
      reuse:'<path d="M20 7v5h-5M19 12a7 7 0 1 0-2 5"/>',
      delete:'<path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
    };
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + (paths[kind] || paths.text) + '</svg>';
  }
  function normalizeGalleryType(type) {
    const value = String(type || '').toLowerCase();
    if (value === 'audio') return 'music';
    return ['image','video','music','voice','text'].includes(value) ? value : 'text';
  }
  function renderProfileGallery() {
    const host = document.getElementById('fullHist'); if (!host) return;
    const items = profileGalleryItems.filter((item) => profileGalleryFilter === 'all' || normalizeGalleryType(item.type) === profileGalleryFilter);
    if (!items.length) { host.innerHTML = '<div class="profile-gallery-state">Здесь появятся ваши завершённые генерации.</div>'; return; }
    host.innerHTML = items.map((item) => {
      const type = normalizeGalleryType(item.type), id = String(item.id), media = String(item.media_url || ''), preview = String(item.preview_url || media || '');
      const title = String(item.prompt || item.text || 'Генерация').trim().slice(0, 90);
      let visual = '';
      if (type === 'image' && preview) visual = '<img src="' + S.escapeHtml(preview) + '" alt="" loading="lazy">';
      else if (type === 'video' && media) visual = '<video src="' + S.escapeHtml(media) + '" muted playsinline preload="metadata"></video><span class="profile-gallery-play">' + profileGalleryIcon('video') + '</span>';
      else visual = '<div class="profile-gallery-placeholder">' + profileGalleryIcon(type) + '<span>' + S.escapeHtml(type === 'music' ? 'Музыка' : type === 'voice' ? 'Озвучка' : 'Текст') + '</span></div>';
      const viewAttrs = type === 'text'
        ? 'onclick="SYLVEX.viewProfileGalleryText(event,\'' + S.escapeHtml(id) + '\')"'
        : type === 'image' ? 'data-image-url="' + S.escapeHtml(media) + '" onclick="SYLVEX.openImageViewer(event)"' : 'data-result-url="' + S.escapeHtml(media) + '" data-audio-url="' + S.escapeHtml(media) + '" data-result-kind="' + type + '" onclick="SYLVEX.openGeneratedContent(event)"';
      const downloadUrl = item.job_id ? completedGenerationDownloadUrl(item.job_id) : media;
      return '<article class="profile-gallery-card" data-gallery-id="' + S.escapeHtml(id) + '"><button class="profile-gallery-preview" type="button" ' + viewAttrs + '>' + visual + '</button>'
        + '<div class="profile-gallery-copy"><b>' + S.escapeHtml(title || 'Без названия') + '</b><small>' + S.escapeHtml([item.model, item.created_at ? new Date(item.created_at).toLocaleDateString() : ''].filter(Boolean).join(' · ')) + '</small></div>'
        + '<div class="profile-gallery-actions">'
        + '<button type="button" title="Просмотреть" ' + viewAttrs + '>' + profileGalleryIcon('open') + '</button>'
        + (downloadUrl ? '<button type="button" title="Скачать" data-download-url="' + S.escapeHtml(downloadUrl) + '" data-file-name="' + S.escapeHtml(generationDownloadFilename(type,item.job_id || id)) + '" onclick="SYLVEX.downloadGeneratedFile(event)">' + profileGalleryIcon('download') + '</button>' : '')
        + '<button type="button" title="Отправить" onclick="SYLVEX.sendProfileGalleryItem(event,\'' + S.escapeHtml(id) + '\')">' + profileGalleryIcon('send') + '</button>'
        + '<button type="button" title="Использовать в Pro Studio" onclick="SYLVEX.reuseProfileGalleryItem(event,\'' + S.escapeHtml(id) + '\')">' + profileGalleryIcon('reuse') + '</button>'
        + '<button class="danger" type="button" title="Удалить" onclick="SYLVEX.deleteProfileGalleryItem(event,\'' + S.escapeHtml(id) + '\')">' + profileGalleryIcon('delete') + '</button></div></article>';
    }).join('');
  }
  async function loadProfileGallery(force) {
    const host = document.getElementById('fullHist'); if (!host) return;
    if (profileGalleryItems.length && !force) return renderProfileGallery();
    host.innerHTML = '<div class="profile-gallery-state">Загрузка истории…</div>';
    try {
      const response = await fetch('/api/public/prostudio/gallery?telegram_id=' + encodeURIComponent(getTelegramId() || 0) + '&limit=100', { cache:'no-store' });
      const payload = await response.json();
      profileGalleryItems = Array.isArray(payload.items) ? payload.items : [];
      renderProfileGallery();
    } catch { host.innerHTML = '<div class="profile-gallery-state">Не удалось загрузить историю.</div>'; }
  }
  function filterProfileGallery(event, type) {
    profileGalleryFilter = type || 'all';
    document.querySelectorAll('[data-gallery-filter]').forEach((button) => button.classList.toggle('active', button.dataset.galleryFilter === profileGalleryFilter));
    renderProfileGallery();
  }
  function galleryItemById(id) { return profileGalleryItems.find((item) => String(item.id) === String(id)); }
  function viewProfileGalleryText(event, id) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const item = galleryItemById(id); if (!item) return;
    let modal = document.getElementById('profileGalleryTextModal');
    if (!modal) { modal = document.createElement('div'); modal.id = 'profileGalleryTextModal'; modal.className = 'profile-gallery-text-modal'; document.body.appendChild(modal); }
    modal.innerHTML = '<section><header><b>Сгенерированный текст</b><button type="button" onclick="this.closest(\'.profile-gallery-text-modal\').classList.remove(\'show\')">×</button></header><div>' + S.escapeHtml(item.text || item.prompt || '') + '</div></section>';
    modal.classList.add('show');
    modal.onclick = (clickEvent) => { if (clickEvent.target === modal) modal.classList.remove('show'); };
  }
  function sendProfileGalleryItem(event, id) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const item = galleryItemById(id); if (!item) return;
    const shareUrl = item.media_url || window.location.href;
    const text = String(item.prompt || item.text || 'Создано в SYLVEX AI').slice(0, 180);
    const url = 'https://t.me/share/url?url=' + encodeURIComponent(shareUrl) + '&text=' + encodeURIComponent(text);
    if (S.tg && S.tg.openTelegramLink) S.tg.openTelegramLink(url); else window.open(url, '_blank', 'noopener');
  }
  async function reuseProfileGalleryItem(event, id) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const item = galleryItemById(id); if (!item) return;
    switchView('tools');
    updateComposerMode(normalizeGalleryType(item.type));
    if (item.conversation_id) await openConv(item.conversation_id, normalizeGalleryType(item.type));
  }
  async function deleteProfileGalleryItem(event, id) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    if (!window.confirm('Удалить эту генерацию из истории?')) return;
    try {
      const response = await fetch('/api/public/prostudio/gallery/' + encodeURIComponent(id) + '?telegram_id=' + encodeURIComponent(getTelegramId() || 0), { method:'DELETE' });
      if (!response.ok) throw new Error('delete_failed');
      profileGalleryItems = profileGalleryItems.filter((item) => String(item.id) !== String(id));
      renderProfileGallery();
      toast('Генерация удалена');
    } catch { toast('Не удалось удалить генерацию'); }
  }
  function renderDynamic() {
    const ht = document.getElementById('homeTools');
    const hh = document.getElementById('homeHist');
    const fh = document.getElementById('fullHist');
    const sg = document.getElementById('shopGrid');
    if (ht) ht.innerHTML = S.toolsData.slice(0, 6).map(S.toolCard).join('');
    if (hh) renderHomeQuickTools();
    if (fh && profileGalleryItems.length) renderProfileGallery();
    if (sg) sg.innerHTML = S.shopData.map(S.shopCard).join('');
    renderModeStrip();
    renderModelPop();
    const mv = document.getElementById('modelVal');
    if (mv) mv.textContent = currentModelLabel;
    // The composer model is owned by updateComposerMode/render*Controls.
    // Do not replace it with the legacy global Pro/Seedance label during
    // language rendering: this used to show Seedance on every first open.
    updatePrice();
  }

  function openKnowledgeWorkspace(section) {
    const modal = document.getElementById('knowledgeWorkspaceModal');
    const frame = document.getElementById('knowledgeWorkspaceFrame');
    if (!modal || !frame) return;
    const modes = { images:'image', video:'video', music:'music', voice:'voice', text:'text', general:'general' };
    const nextSrc = 'knowledge-workspace.html?mode=' + encodeURIComponent(modes[section] || 'image');
    frame.src = nextSrc;
    modal.hidden = false;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeKnowledgeWorkspace() {
    const modal = document.getElementById('knowledgeWorkspaceModal');
    const frame = document.getElementById('knowledgeWorkspaceFrame');
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => {
      if (modal.classList.contains('show')) return;
      modal.hidden = true;
      if (frame) frame.src = 'about:blank';
    }, 260);
  }

  function handleKnowledgeWorkspaceMessage(event) {
    const message = event.data || {};
    if (message.source !== 'sylvex-knowledge') return;
    if (message.action === 'close') { closeKnowledgeWorkspace(); return; }
    if (message.action !== 'generate') return;
    const isGeneral = message.mode === 'general';
    const mode = CHAT_SPACE_TYPES.includes(message.mode) ? message.mode : 'image';
    closeKnowledgeWorkspace();
    switchView('tools');
    if (!isGeneral) updateComposerMode(mode);
    window.setTimeout(() => {
      const input = document.getElementById('chatInput');
      if (input && message.prompt) { input.value = String(message.prompt); autoGrow(input); input.focus(); }
      const modelId = String(message.model || '');
      if (modelId) pickImageOption(null, 'model', modelId);
      updateSendButton();
    }, 80);
  }

  /* ===== Pricing ===== */
  // =====================================================
  // JAVASCRIPT-БЛОК: computePrice
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function computePrice() {
    if (!activeCat) return 0;
    let p = S.CAT_PRICE[activeCat] || 0;
    Object.keys(S.CTRL_PRICE).forEach(k => { p += (S.CTRL_PRICE[k][S.CTRL_IDX[k]] || 0); });
    return p;
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: updatePrice
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function updatePrice() {
    const bar = document.getElementById('priceBar');
    if (bar) bar.classList.remove('show');
  }
  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: generateNow
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function generateNow() {
    if (!activeCat) { toast(t('generating')); return; }
    toast(t('generating') + ' · ' + computePrice() + ' ⚡️');
    S.haptic.impact('medium');
  }

  /* ===== Studio interactions ===== */
  // =====================================================
  // JAVASCRIPT-БЛОК: selMode
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function selMode(k) {
    studioMode = k;
    activeCat = k;
    renderModeStrip();
    S.haptic.select();
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleModelPop
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleModelPop(e) {
    showImageModelPicker(e);
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: pickModel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickModel(e, i) {
    e.stopPropagation();
    S.CTRL_IDX.model = i;
    document.getElementById('modelVal').textContent = S.CTRL.model[i];
    renderModelPop();
    document.getElementById('modelPop').classList.remove('show');
    S.haptic.select();
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: pickModelKey
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickModelKey(e, key, label) {
    e.stopPropagation();
    currentModelLabel = label;
    studioMode = key === 'pro' ? 'pro' : 'lite';
    activeCat = studioMode;
    const mv = document.getElementById('modelVal');
    if (mv) mv.textContent = label;
    const mvc = document.getElementById('modelValComposer');
    if (mvc) mvc.textContent = label;
    renderModelPop();
    const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
    const bb = document.getElementById('modelBtn'); if (bb) bb.setAttribute('aria-expanded','false');
    S.haptic.select();
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: togglePlusPop
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function togglePlusPop(e) {
    if (e) e.stopPropagation();
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.add('show');
    const mp = document.getElementById('modelPop'); if (mp) mp.classList.remove('show');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closePlusSheet
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closePlusSheet(e) {
    if (e && e.target && e.target.id !== 'plusSheet') return;
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: addMediaLink
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function addMediaLink(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');

    const raw = window.prompt(kind === 'video' ? 'Video URL' : (kind === 'audio' ? 'Audio URL' : 'Image URL'));
    const url = String(raw || '').trim();
    if (!url) return;

    if (isVideoMode()) {
      if (kind === 'video') {
        if (getUploadTarget() === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) {
          applyVideoEditInputToState(url);
        } else if (getUploadTarget() === UPLOAD_TARGETS.VIDEO_REFERENCES) {
          applyVideoReferenceToState(url);
        } else {
          applyVideoEditInputToState(url);
        }
      } else {
        applyUploadToTarget(url, getUploadTarget());
      }
      updateSendButton();
      toast('Ссылка добавлена');
      return;
    }

    if (isMusicMode() || isVoiceMode()) {
      const state = currentAudioState();
      state.uploads = (state.uploads || []).filter((item) => item.url !== url);
      state.uploads.push({ kind: isVoiceMode() ? kind : (kind === 'video' ? 'audio' : kind), url });
      state.uploads = state.uploads.slice(0, 4);
      updateSendButton();
      toast('Ссылка добавлена');
      if (isVoiceMode()) renderVoiceToolPanel();
      return;
    }

    if (kind === 'image' && isImageMode()) {
      applyUploadToTarget(url, UPLOAD_TARGETS.IMAGE_UPLOAD);
      renderComposerImageDraft();
      updateSendButton();
      toast('Ссылка добавлена');
    }
  }
  // =====================================================
  // ЗАГРУЗКА В MINI APP: ensureUploadPanel
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function ensureUploadPanel() {
    let panel = document.getElementById('uploadPanel');
    if (panel) return panel;

    panel = document.createElement('div');
    panel.id = 'uploadPanel';
    panel.className = 'upload-panel-backdrop';
    panel.innerHTML = `
      <div class="upload-panel-card" onclick="event.stopPropagation()">
        <button class="upload-panel-close" type="button" onclick="SYLVEX.closeUploadPanel(event)">×</button>
        <div class="upload-panel-title">История</div>
        <div class="upload-panel-body">
          <div class="upload-panel-half upload-panel-generated">
            <div id="uploadGeneratedGrid" class="upload-generated-grid"></div>
          </div>
        <div class="upload-panel-half upload-panel-actions">
        <div id="uploadPhotoGrid" class="upload-photo-grid"></div>
        <button id="uploadClearPhotosBtn" class="upload-choose-photos-btn" type="button" onclick="SYLVEX.clearCurrentUploadTarget(event)" hidden>
            Очистить
        </button>
        <button id="uploadChoosePhotosBtn" class="upload-choose-photos-btn" type="button" onclick="SYLVEX.confirmUploadedPhotos(event)" hidden>
            Выбрать фото
        </button>
        </div>
        </div>
        <div id="uploadImagePreview" class="upload-image-preview" onclick="SYLVEX.closeUploadImagePreview(event)">
          <div class="upload-preview-card" onclick="event.stopPropagation()">
            <button class="upload-preview-close" type="button" onclick="SYLVEX.closeUploadImagePreview(event)">×</button>
            <img id="uploadPreviewImg" src="" alt="generated image" />
            <button id="uploadPreviewSelect" class="upload-preview-select" type="button">Выбрать для генерации</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(panel);
    renderUploadPanelImages();
    renderUploadedPhotoGrid();
    return panel;
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: normalizeGeneratedImageItem
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function normalizeGeneratedImageItem(item, thumb) {
    if (!item) return null;
    if (typeof item === 'object') {
      const url = item.url || item.original_url || item.image_url || item.result_url || item.full_url || '';
      if (!url) return null;
      return { url, thumb: item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || url };
    }
    return { url: item, thumb: thumb || item };
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: parseMetadataObject
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function parseMetadataObject(value) {
    if (!value) return {};
    if (typeof value === 'object') return value;
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value);
        return parsed && typeof parsed === 'object' ? parsed : {};
      } catch {
        return {};
      }
    }
    return {};
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: firstMediaUrlFrom
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function firstMediaUrlFrom(value) {
    if (!value) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) {
      for (const item of value) {
        const url = firstMediaUrlFrom(item);
        if (url) return url;
      }
      return '';
    }
    if (typeof value === 'object') {
      return value.url
        || value.original_url
        || value.image_url
        || value.result_url
        || value.full_url
        || value.thumb_url
        || value.thumbnail_url
        || value.thumb
        || value.thumbnail
        || '';
    }
    return '';
  }

  // =====================================================
  // ЧАТ И ИСТОРИЯ: collectImageHistoryItem
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function collectImageHistoryItem(source, fallback) {
    source = source || {};
    const meta = Object.assign({}, parseMetadataObject(source && source.metadata_json), parseMetadataObject(source && source.metadata), parseMetadataObject(source));
    const type = String(meta.type || source.type || source.mode || source.category || '').toLowerCase();
    const mode = String(meta.mode || source.mode || '').toLowerCase();
    const category = String(meta.category || source.category || '').toLowerCase();
    const hasVideo = !!(meta.video_url || source.video_url || (Array.isArray(meta.videos) && meta.videos.length) || (Array.isArray(source.videos) && source.videos.length));
    const hasAudio = !!(meta.audio_url || source.audio_url || (Array.isArray(meta.audios) && meta.audios.length) || (Array.isArray(source.audios) && source.audios.length));
    const imageLike = type === 'image' || mode === 'image' || category === 'image'
      || !!(meta.image_url || meta.result_url || meta.full_url || source.image_url || source.result_url || source.full_url)
      || !!firstMediaUrlFrom(meta.images || meta.result_images || meta.urls || meta.output || source.images || source.image_urls || source.urls || source.output);

    if (!imageLike || hasVideo || hasAudio) return null;

    const url = firstMediaUrlFrom(meta.full_url)
      || firstMediaUrlFrom(meta.result_url)
      || firstMediaUrlFrom(meta.image_url)
      || firstMediaUrlFrom(meta.result_images)
      || firstMediaUrlFrom(meta.images)
      || firstMediaUrlFrom(meta.urls)
      || firstMediaUrlFrom(meta.output)
      || firstMediaUrlFrom(source.full_url)
      || firstMediaUrlFrom(source.result_url)
      || firstMediaUrlFrom(source.image_url)
      || firstMediaUrlFrom(source.images)
      || firstMediaUrlFrom(source.image_urls)
      || firstMediaUrlFrom(source.urls)
      || firstMediaUrlFrom(source.output)
      || firstMediaUrlFrom(fallback);

    if (!url) return null;

    const thumb = firstMediaUrlFrom(meta.thumbnail_url)
      || firstMediaUrlFrom(meta.thumb_url)
      || firstMediaUrlFrom(meta.result_thumbnails)
      || firstMediaUrlFrom(meta.thumbnails)
      || firstMediaUrlFrom(source.thumbnail_url)
      || firstMediaUrlFrom(source.thumb_url)
      || firstMediaUrlFrom(source.thumbnails)
      || firstMediaUrlFrom(source.thumb_urls)
      || url;

    return { url, thumb };
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: pushGeneratedPhotoHistoryItem
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function pushGeneratedPhotoHistoryItem(items, seen, source, fallback) {
    const item = collectImageHistoryItem(source || {}, fallback);
    if (!item || seen.has(item.url)) return;
    seen.add(item.url);
    items.push(item);
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: getGeneratedPhotoHistoryItems
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function getGeneratedPhotoHistoryItems() {
    const items = [];
    const seen = new Set();

    (generatedImageLibrary || []).forEach((entry) => {
      pushGeneratedPhotoHistoryItem(items, seen, Object.assign({ type: 'image' }, normalizeGeneratedImageItem(entry) || {}));
    });

    const messageSources = [];
    messageSources.push(...(chatMessages || []));
    Object.keys(chatSpaces || {}).forEach((type) => {
      if (type !== 'image') return;
      messageSources.push(...((chatSpaces[type] && chatSpaces[type].messages) || []));
    });

    messageSources.forEach((message) => {
      if (!message) return;
      if (message.metadata) pushGeneratedPhotoHistoryItem(items, seen, message.metadata);
      if (message.imageResultMini || message.imageUrl || message.images) pushGeneratedPhotoHistoryItem(items, seen, Object.assign({ type: 'image' }, message));
    });

    (conversationsCache || []).forEach((conversation) => {
      const conversationType = chatTypeForMode(conversation.type || conversation.mode || conversation.category || '');
      if (conversationType !== 'image') return;
      pushGeneratedPhotoHistoryItem(items, seen, Object.assign({ type: 'image' }, conversation));
      if (conversation.metadata) pushGeneratedPhotoHistoryItem(items, seen, conversation.metadata);
    });

    return items.slice(0, 80);
  }

  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: addGeneratedImages
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function addGeneratedImages(urls, thumbs) {
    // =====================================================
    // JAVASCRIPT-БЛОК: list
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const list = (urls || []).map((url, index) => normalizeGeneratedImageItem(url, thumbs && thumbs[index])).filter(Boolean);
    if (!list.length) return;
    list.forEach((item) => {
      generatedImageLibrary = generatedImageLibrary.filter((old) => normalizeGeneratedImageItem(old).url !== item.url);
      generatedImageLibrary.unshift(item);
    });
    generatedImageLibrary = generatedImageLibrary.slice(0, 20);
    renderUploadPanelImages();
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderUploadPanelImages
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderUploadPanelImages() {
    const grid = document.getElementById('uploadGeneratedGrid');
    if (!grid) return;
    const items = getGeneratedPhotoHistoryItems();

    if (!items.length) {
      grid.innerHTML = '<div class="upload-panel-empty">Пока нет сгенерированных фото</div>';
      return;
    }

    const selectedUrl = currentSelectedUploadImage();
    grid.innerHTML = items.map((entry) => {
      const item = normalizeGeneratedImageItem(entry);
      if (!item) return '';
      const safeUrl = S.escapeHtml(item.url);
      const safeThumb = S.escapeHtml(item.thumb || item.url);
      const selected = selectedUrl === item.url;
      return '<button class="upload-generated-thumb ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.selectGeneratedImage(event,\'' + safeUrl + '\')">'
        + '<img src="' + safeThumb + '" alt="generated image" loading="lazy" decoding="async" />'
        + '<span class="upload-thumb-check">✓</span>'
        + '</button>';
    }).join('');
  }

// =====================================================
// ЗАГРУЗКА В MINI APP: uploadPhotoButtonHtml
// Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
// =====================================================
function uploadPhotoButtonHtml() {
  const uploadImages = currentUploadImages();
  const target = getUploadTarget();
  const isVideoReferences = target === UPLOAD_TARGETS.VIDEO_REFERENCES;
  const allowVideo = videoUploadTargetAllowsVideo(target);
  if (uploadImages.length >= uploadLimitForTarget()) {
    return (isVideoReferences && !currentVideoReferenceUrl())
      ? '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'' + (allowVideo ? 'media' : 'image') + '\')" aria-label="Добавить медиа"><span class="upload-photo-add-icon" aria-hidden="true">＋</span></button>'
      : '';
  }

  if (!uploadImages.length) {
    return '<button class="upload-photo-center-btn" type="button" onclick="SYLVEX.openNativeFilePicker(\'' + (allowVideo ? 'media' : 'image') + '\')">'
      + '<span class="upload-photo-center-icon" aria-hidden="true">'
      + '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
      + '<rect x="3.5" y="5" width="17" height="14" rx="3" stroke="currentColor" stroke-width="1.8"/>'
      + '<path d="M7 16L10.2 12.8C10.8 12.2 11.7 12.2 12.3 12.8L14 14.5L15.2 13.3C15.8 12.7 16.7 12.7 17.3 13.3L20 16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
      + '<circle cx="8.7" cy="9.3" r="1.3" fill="currentColor"/>'
      + '<path d="M18 7l3 2-3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
      + '</svg>'
      + '</span>'
      + '<span class="upload-photo-center-title">' + (allowVideo ? 'Загрузить фото или видео' : 'Загрузить фото') + '</span>'
      + '<span class="upload-photo-center-sub">' + (allowVideo ? 'Выберите изображение или видео' : 'Выберите изображение') + '</span>'
      + '</button>';
  }

  const pickerKind = isVideoReferences && allowVideo ? 'media' : 'image';
  const ariaLabel = isVideoReferences && allowVideo ? 'Добавить фото или видео' : 'Загрузить фото';
  return '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'' + pickerKind + '\')" aria-label="' + ariaLabel + '">'
    + '<span class="upload-photo-add-icon" aria-hidden="true">＋</span>'
    + '<span class="upload-photo-add-text">Добавить</span>'
    + '</button>';
}

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderUploadedPhotoGrid
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderUploadedPhotoGrid() {
    const grid = document.getElementById('uploadPhotoGrid');
    if (!grid) return;

    const uploadImages = currentUploadImages();
    const uploadingReference = getUploadTarget() === UPLOAD_TARGETS.VIDEO_REFERENCES ? (videoState.referenceUploading || null) : null;
    const hasVideoReference = getUploadTarget() === UPLOAD_TARGETS.VIDEO_REFERENCES && Boolean(currentVideoReferenceUrl());
    const hasUploads = uploadImages.length > 0 || hasVideoReference || !!uploadingReference;

    grid.classList.toggle('empty', !hasUploads);

    const chooseBtn = document.getElementById('uploadChoosePhotosBtn');
    if (chooseBtn) chooseBtn.hidden = !hasUploads;
    const clearBtn = document.getElementById('uploadClearPhotosBtn');
    if (clearBtn) clearBtn.hidden = !hasUploads;

    const selectedUrl = currentSelectedUploadImage();
    // =====================================================
    // JAVASCRIPT-БЛОК: items
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const items = uploadImages.map((url, index) => {
      const safeUrl = S.escapeHtml(url);
      const selected = selectedUrl === url;
      return '<button class="upload-photo-thumb ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.selectUploadedPhoto(event,\'' + safeUrl + '\')">'
        + '<img src="' + safeUrl + '" alt="uploaded image" />'
        + '<span class="upload-thumb-check">✓</span>'
        + '<span class="upload-photo-remove" onclick="SYLVEX.removeUploadedPhoto(event,' + index + ')">×</span>'
        + '</button>';
    });
    if (uploadingReference) {
      const safePreview = S.escapeHtml(uploadingReference.previewUrl || '');
      const isVideoUpload = String(uploadingReference.kind || '').toLowerCase() === 'video';
      items.unshift('<button class="upload-photo-thumb upload-media-uploading selected" type="button" aria-label="Медиа загружается">'
        + (safePreview ? (isVideoUpload ? '<video src="' + safePreview + '" muted playsinline preload="metadata"></video>' : '<img src="' + safePreview + '" alt="uploading media" />') : '<span class="upload-photo-add-icon" aria-hidden="true">...</span>')
        + '<span class="uploading-ring" aria-hidden="true"></span>'
        + '</button>');
    } else if (hasVideoReference) {
      const safeVideo = S.escapeHtml(currentVideoReferenceUrl());
      items.unshift('<button class="upload-photo-thumb upload-video-thumb selected" type="button" onclick="SYLVEX.openNativeFilePicker(\'media\')" aria-label="Заменить или добавить медиа">'
        + (safeVideo ? '<video src="' + safeVideo + '" muted playsinline preload="metadata"></video>' : '<span class="upload-photo-add-icon" aria-hidden="true">▶</span>')
        + '<span class="upload-thumb-check">✓</span>'
        + '<span class="upload-photo-remove" onclick="SYLVEX.clearVideoReference(event)">×</span>'
        + '</button>');
    }

    const addButton = uploadPhotoButtonHtml();
    if (addButton) items.push(addButton);
    grid.innerHTML = items.join('');
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: addUploadedPhoto
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function addUploadedPhoto(url) {
    if (!url) return;
    const target = getUploadTarget();
    // =====================================================
    // ЗАГРУЗКА В MINI APP: uploadImages
    // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
    // =====================================================
    const uploadImages = currentUploadImages().filter((item) => item !== url);
    uploadImages.push(url);
    setCurrentUploadImages(uploadImages, target);
    applyUploadToTarget(url, target);
    renderUploadedPhotoGrid();
    renderUploadPreviewForTarget(target);
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: selectUploadedPhoto
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function selectUploadedPhoto(e, url) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const target = getUploadTarget();
    applyUploadToTarget(url, target);
    renderUploadedPhotoGrid();
    renderUploadPreviewForTarget(target);
    toast('Фото выбрано');
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: removeUploadedPhoto
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function removeUploadedPhoto(e, index) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const uploadImages = currentUploadImages();
    const target = getUploadTarget();
    uploadImages.splice(index, 1);
    setCurrentUploadImages(uploadImages, target);
    renderUploadedPhotoGrid();
    renderUploadPreviewForTarget(target);
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: clearCurrentUploadTarget
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function clearCurrentUploadTarget(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const target = getUploadTarget();
    setCurrentUploadImages([], target);
    if (target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) {
      if (videoState.editUploading && videoState.editUploading.previewUrl) {
        try { URL.revokeObjectURL(videoState.editUploading.previewUrl); } catch {}
      }
      videoState.editUploading = null;
      videoState.editInputVideo = '';
      videoState.editVideoUrl = '';
      videoState.inputVideo = '';
      videoState.videoUrl = '';
      renderVideoEditPreview();
    }
    if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
      if (videoState.referenceUploading && videoState.referenceUploading.previewUrl) {
        try { URL.revokeObjectURL(videoState.referenceUploading.previewUrl); } catch {}
      }
      videoState.referenceUploading = null;
      videoState.referenceVideoUrl = '';
    }
    renderUploadPanelImages();
    renderUploadPreviewForTarget(target);
    toast('Очищено');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: clearVideoReference
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function clearVideoReference(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (videoState.referenceUploading && videoState.referenceUploading.previewUrl) {
      try { URL.revokeObjectURL(videoState.referenceUploading.previewUrl); } catch {}
    }
    videoState.referenceUploading = null;
    videoState.referenceVideoUrl = '';
    renderUploadedPhotoGrid();
    renderVideoReferencesPreview();
    updateSendButton();
  }

    // =====================================================
    // ЗАГРУЗКА В MINI APP: confirmUploadedPhotos
    // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
    // =====================================================
    function confirmUploadedPhotos(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }

    renderComposerImageDraft();
    renderUploadPreviewForTarget(getUploadTarget());
    closeUploadPanel(e);
    toast('Фото добавлены в сообщение');

    S.haptic && S.haptic.notify && S.haptic.notify('success');
    }

    // =====================================================
    // JAVASCRIPT-БЛОК: ensureComposerImageDraft
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    function ensureComposerImageDraft() {
  const ta = document.getElementById('chatInput');
  if (!ta) return null;

  let box = document.getElementById('composerImageDraft');
  if (box) return box;

  box = document.createElement('div');
  box.id = 'composerImageDraft';
  box.className = 'composer-image-draft';

  ta.parentElement.insertBefore(box, ta);
  return box;
}

// =====================================================
// ОТРИСОВКА ИНТЕРФЕЙСА: renderComposerImageDraft
// Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
// =====================================================
function renderComposerImageDraft() {
  const box = ensureComposerImageDraft();
  if (!box) return;

  // Uploaded images are kept in imageState.referenceImageUrls and sent to generation,
  // but their visual preview is shown only inside the “Загрузка” button background.
  box.innerHTML = '';
  box.hidden = true;
  box.classList.remove('show');
  box.style.display = 'none';

  updateImageUploadButtonPreview();
}

// =====================================================
// JAVASCRIPT-БЛОК: removeComposerImageDraft
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function removeComposerImageDraft(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const urls = (imageState.referenceImageUrls || []).slice();
  urls.splice(index, 1);

  imageState.referenceImageUrls = urls.slice();
  imageState.referenceImageUrl = urls[urls.length - 1] || '';
  imageState.uploadedImageUrls = urls.slice();

  renderUploadedPhotoGrid();
  renderComposerImageDraft();
  updateImageUploadButtonPreview();
}

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openUploadImagePreview
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openUploadImagePreview(e, url) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const preview = document.getElementById('uploadImagePreview');
    const img = document.getElementById('uploadPreviewImg');
    const selectBtn = document.getElementById('uploadPreviewSelect');
    if (!preview || !img || !selectBtn) return;
    img.src = url;
    selectBtn.onclick = (ev) => selectGeneratedImage(ev, url);
    preview.classList.add('show');
  }

// =====================================================
// JAVASCRIPT-БЛОК: ensureImageViewer
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function ensureImageViewer() {
  let viewer = document.getElementById('imageViewer');
  if (viewer) return viewer;

  viewer = document.createElement('div');
  viewer.id = 'imageViewer';
  viewer.className = 'image-viewer-backdrop';
  viewer.innerHTML = `
    <div class="image-viewer-card" onclick="event.stopPropagation()">
      <button class="image-viewer-close" type="button" onclick="SYLVEX.closeImageViewer(event)">×</button>
      <img id="imageViewerImg" class="image-viewer-img" src="" alt="generated image" />
    </div>
  `;

  viewer.onclick = closeImageViewer;
  document.body.appendChild(viewer);
  return viewer;
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openImageViewer
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openImageViewer(e, url) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const btn = e && e.currentTarget ? e.currentTarget : null;
  const imageUrl = url || (btn && btn.dataset ? btn.dataset.imageUrl : '');

  if (!imageUrl) return;

  const viewer = ensureImageViewer();
  const img = document.getElementById('imageViewerImg');

  if (img) img.src = imageUrl;

  viewer.classList.add('show');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeImageViewer
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeImageViewer(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const viewer = document.getElementById('imageViewer');
  const img = document.getElementById('imageViewerImg');

  if (viewer) viewer.classList.remove('show');
  if (img) img.src = '';
}

// =====================================================
// JAVASCRIPT-БЛОК: telegramBotLink
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function telegramBotLink() {
  const explicit = S.TELEGRAM_BOT_LINK || S.BOT_LINK || '';
  if (explicit) return explicit;
  const botLink = Array.from(document.querySelectorAll('a[href*="t.me/"]'))
    .map((link) => link.href || '')
    .find((href) => /bot/i.test(href));
  return botLink || 'https://t.me/sylvexai_bot';
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openTelegramBot
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openTelegramBot(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const url = telegramBotLink();
  const tgApp = S.tg || (window.Telegram && window.Telegram.WebApp);
  try {
    if (tgApp && typeof tgApp.openTelegramLink === 'function' && /(^https?:\/\/)?t\.me\//i.test(url)) {
      tgApp.openTelegramLink(url);
    } else if (tgApp && typeof tgApp.openLink === 'function') {
      tgApp.openLink(url);
    } else {
      window.open(url, '_blank', 'noopener');
    }
  } catch {
    window.open(url, '_blank', 'noopener');
  }
  if (tgApp && typeof tgApp.close === 'function') {
    setTimeout(() => tgApp.close(), 250);
  }
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openGeneratedContent
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openGeneratedContent(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const url = btn && btn.dataset ? (btn.dataset.resultUrl || btn.dataset.videoUrl || btn.dataset.audioUrl || '') : '';
  if (!url) return;
  const kind = btn && btn.dataset ? (btn.dataset.resultKind || '') : '';
  if (kind === 'voice') {
    playVoiceInCard(e);
    return;
  }
  if (kind === 'music' || kind === 'audio') {
    openMusicInPlayer({
      audio_url: url,
      title: btn.dataset.title || 'SYLVEX Music',
      cover_url: btn.dataset.coverUrl || '',
    }, e);
    return;
  }
  const tgApp = S.tg || (window.Telegram && window.Telegram.WebApp);
  try {
    if (tgApp && typeof tgApp.openLink === 'function' && /^https?:\/\//i.test(url)) {
      tgApp.openLink(url);
    } else {
      window.open(url, '_blank', 'noopener');
    }
  } catch {
    window.open(url, '_blank', 'noopener');
  }
}

// =====================================================
// АУДИОПЛЕЕР: playVoiceInCard
// Запускает сгенерированную озвучку прямо внутри карточки результата Mini App.
// Не открывает внешние ссылки и не переводит пользователя на новую страницу.
// =====================================================
function playVoiceInCard(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const url = btn && btn.dataset ? (btn.dataset.audioUrl || btn.dataset.resultUrl || '') : '';
  if (!url) return;
  const card = btn.closest && btn.closest('.gen-audio-card, .generation-result-voice-card, .generation-info-drawer');
  let audio = card && card.querySelector ? card.querySelector('audio') : null;
  if (!audio) {
    audio = document.getElementById('voiceInlineFallbackAudio');
    if (!audio) {
      audio = document.createElement('audio');
      audio.id = 'voiceInlineFallbackAudio';
      audio.className = 'generation-result-inline-audio voice-inline-fallback-audio';
      audio.controls = true;
      audio.preload = 'metadata';
      if (card && card.querySelector) {
        const actions = card.querySelector('.generation-info-actions');
        if (actions) actions.insertAdjacentElement('beforebegin', audio);
        else card.appendChild(audio);
      } else {
        document.body.appendChild(audio);
      }
    }
  }
  if (audio.getAttribute('src') !== url) {
    audio.src = url;
    audio.load();
  }
  if (audio.paused) {
    const promise = audio.play();
    if (promise && typeof promise.catch === 'function') promise.catch(() => {});
  } else {
    audio.pause();
  }
}

// =====================================================
// ВИДЕОПЛЕЕР: playVideoInGenerationCard
// Запускает видео прямо внутри большой карточки информации о генерации.
// Используется вместо перехода по внешней ссылке.
// =====================================================
function playVideoInGenerationCard(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const url = btn && btn.dataset ? (btn.dataset.videoUrl || btn.dataset.resultUrl || '') : '';
  if (!url) return;
  const card = btn.closest && btn.closest('.generation-info-drawer');
  const video = card && card.querySelector ? card.querySelector('video') : null;
  if (!video) return;
  if (video.getAttribute('src') !== url) {
    video.src = url;
    video.load();
  }
  if (video.paused) {
    const promise = video.play();
    if (promise && typeof promise.catch === 'function') promise.catch(() => {});
  } else {
    video.pause();
  }
}

// =====================================================
// АУДИОПЛЕЕР: playMusicTrack
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function playMusicTrack(eOrTrack) {
  if (eOrTrack && eOrTrack.preventDefault) {
    eOrTrack.preventDefault();
    eOrTrack.stopPropagation();
    const btn = eOrTrack.currentTarget || null;
    const data = btn && btn.dataset ? btn.dataset : {};
    openMusicInPlayer({
      id: data.trackId || data.resultUrl || data.audioUrl || '',
      audio_url: data.audioUrl || data.resultUrl || '',
      result_url: data.audioUrl || data.resultUrl || '',
      cover_url: data.coverUrl || '',
      thumbnail_url: data.coverUrl || '',
      title: data.title || 'Untitled Track',
      provider: data.provider || 'suno',
      model: data.model || '',
    }, eOrTrack);
    return;
  }
  openMusicInPlayer(eOrTrack || {});
}

// =====================================================
// АУДИОПЛЕЕР: playMusicTrackFromMessage
// Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
// =====================================================
function playMusicTrackFromMessage(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const message = chatMessages[index] || {};
  const meta = message.metadata || {};
  openMusicInPlayer(Object.assign({}, message, meta, {
    metadata: meta,
    audio_url: musicAudioUrl(meta) || musicAudioUrl(message),
    cover_url: musicCoverUrl(meta) || musicCoverUrl(message),
    title: meta.title || message.title || 'SYLVEX Music',
  }), e);
}

// =====================================================
// JAVASCRIPT-БЛОК: restoreImageStateFromGenerationMetadata
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function restoreImageStateFromGenerationMetadata(meta) {
  if (!meta || meta.type !== 'image') return;
  const settings = meta.image_options || meta.settings || {};
  imageState.modelId = meta.model || settings.modelId || imageState.modelId;
  imageState.size = meta.size || meta.ratio || settings.size || settings.ratio || imageState.size;
  imageState.count = Number(meta.count || settings.count || imageState.count || 1);
  imageState.style = meta.style || settings.style || imageState.style || 'auto';
  imageState.character = meta.character || settings.character || imageState.character || 'auto';
  imageState.objects = meta.objectName || meta.objects || settings.objects || imageState.objects || '';
  imageState.characterId = meta.characterId || settings.characterId || null;
  imageState.characterName = meta.characterName || settings.characterName || '';
  imageState.characterReferences = Array.isArray(meta.characterReferences) ? meta.characterReferences.slice() : (Array.isArray(settings.characterReferences) ? settings.characterReferences.slice() : []);
  imageState.objectId = meta.objectId || settings.objectId || null;
  imageState.objectName = meta.objectName || settings.objectName || '';
  imageState.objectReferences = Array.isArray(meta.objectReferences) ? meta.objectReferences.slice() : (Array.isArray(settings.objectReferences) ? settings.objectReferences.slice() : []);
  imageState.seed = meta.seed === undefined ? (settings.seed === undefined ? null : settings.seed) : meta.seed;
  const refs = Array.isArray(meta.reference_images) && meta.reference_images.length
    ? meta.reference_images.slice()
    : (Array.isArray(settings.referenceImageUrls) ? settings.referenceImageUrls.slice() : []);
  imageState.referenceImageUrls = refs.slice();
  imageState.uploadedImageUrls = refs.slice();
  imageState.referenceImageUrl = refs[0] || '';
  const ta = document.getElementById('chatInput');
  if (ta && meta.prompt) {
    ta.value = meta.prompt;
    autoGrow(ta);
    updateSendButton();
  }
  renderImageControls();
  renderComposerImageDraft();
  renderUploadedPhotoGrid();
  updateImageUploadButtonPreview();
}

// =====================================================
// ЗАПУСК ГЕНЕРАЦИИ: animateGeneratedImage
// Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
// =====================================================
function animateGeneratedImage(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const imageUrl = btn && btn.dataset ? btn.dataset.imageUrl : '';
  if (!imageUrl) return;

  closeGenerationInfoDrawer();
  closeImageViewer();
  updateComposerMode('video');
  videoState.section = 'generate';
  videoState.generationMode = 'image_to_video';
  videoState.mode = 'image_to_video';
  setUploadTarget(UPLOAD_TARGETS.VIDEO_REFERENCES);
  videoState.startImage = '';
  applyUploadToTarget(imageUrl, UPLOAD_TARGETS.VIDEO_REFERENCES);
  renderVideoControls();
  renderUploadedPhotoGrid();
  renderAllUploadPreviews();
  updateSendButton();
  toast('Фото добавлено в референсы');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

// =====================================================
// ЗАПУСК ГЕНЕРАЦИИ: editGeneratedVideo
// Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
// =====================================================
function editGeneratedVideo(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const videoUrl = btn && btn.dataset ? btn.dataset.videoUrl : '';
  if (!videoUrl) return;

  closeGenerationInfoDrawer();
  updateComposerMode('edit');
  videoState.section = 'edit';
  videoState.generationMode = 'video_edit';
  videoState.mode = 'video_edit';
  videoUploadTarget = 'input_video';
  applyVideoEditInputToState(videoUrl);
  renderVideoControls();
  renderUploadedPhotoGrid();
  renderVideoInputPreviews();
  updateImageUploadButtonPreview();
  updateSendButton();
  toast('Видео добавлено для редактирования');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

// =====================================================
// JAVASCRIPT-БЛОК: ensureGenerationInfoDrawer
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function ensureGenerationInfoDrawer() {
  let drawer = document.getElementById('generationInfoDrawer');
  if (drawer) return drawer;

  drawer = document.createElement('div');
  drawer.id = 'generationInfoDrawer';
  drawer.className = 'generation-info-drawer-backdrop';
  drawer.innerHTML = '<aside class="generation-info-drawer" onclick="event.stopPropagation()">'
    + '<div class="generation-info-head">'
    + '<div><div class="generation-info-kicker">Generation details</div><h3>Image</h3></div>'
    + '<button class="generation-info-close" type="button" onclick="SYLVEX.closeGenerationInfoDrawer(event)">×</button>'
    + '</div>'
    + '<div id="generationInfoBody" class="generation-info-body"></div>'
    + '</aside>';
  drawer.onclick = closeGenerationInfoDrawer;
  document.body.appendChild(drawer);
  return drawer;
}

// =====================================================
// JAVASCRIPT-БЛОК: generationInfoRow
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function generationInfoRow(label, value) {
  if (value === undefined || value === null || value === '') return '';
  return '<div class="generation-info-row"><span>' + S.escapeHtml(label) + '</span><b>' + S.escapeHtml(String(value)) + '</b></div>';
}

function generationCostLabel(meta) {
  const usd = meta && meta.cost_usd !== undefined && meta.cost_usd !== null && meta.cost_usd !== ''
    ? '$' + Number(meta.cost_usd).toFixed(3)
    : '';
  const credits = meta && meta.cost_credits !== undefined && meta.cost_credits !== null && meta.cost_credits !== ''
    ? String(meta.cost_credits) + ' ⚡️'
    : '';
  return [usd, credits].filter(Boolean).join(' / ') || String((meta && meta.generation_cost) || '');
}

function toggleGenerationPrompt(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const button = e && e.currentTarget;
  const block = button && button.closest('.generation-prompt-block');
  if (!block) return;
  const expanded = block.classList.toggle('is-expanded');
  button.textContent = expanded ? 'Свернуть' : 'Развернуть';
  button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
}

async function shareGenerationCard(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const message = chatMessages[index] || {};
  const meta = message.metadata || {};
  const jobId = completedGenerationJobId(message, meta);
  if (!jobId || String(meta.status || message.generationStatus || 'completed').toLowerCase() !== 'completed') {
    toast('Поделиться можно только завершённой генерацией');
    return;
  }
  let shareUrl = '';
  let shareId = '';
  try {
    const response = await fetch('/api/public/prostudio/share/' + encodeURIComponent(jobId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        telegram_id: getTelegramId(),
        init_data: S.tg && S.tg.initData ? S.tg.initData : '',
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok || !payload.share_url) {
      throw new Error(payload.detail || payload.error || 'share_create_failed');
    }
    shareUrl = payload.share_url;
    shareId = String(payload.share_id || '');
  } catch (error) {
    console.error('SYLVEX_SHARE_CREATE_FAILED', { job_id: jobId, error: String(error && error.message || error) });
    toast('Не удалось создать ссылку. Попробуйте позже');
    return;
  }
  const tg = S.tg;
  if (tg && typeof tg.shareMessage === 'function') {
    try {
      if (!shareId) throw new Error('share_id_missing');
      const prepareResponse = await fetch('/api/public/prostudio/share/' + encodeURIComponent(shareId) + '/prepared-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: getTelegramId(), init_data: tg.initData || '' }),
      });
      const prepared = await prepareResponse.json().catch(() => ({}));
      if (!prepareResponse.ok || !prepared.ok || !prepared.prepared_message_id) throw new Error(prepared.detail || 'prepared_message_failed');
      tg.shareMessage(prepared.prepared_message_id, (shared) => {
        if (shared === false) console.info('PROSTUDIO_NATIVE_SHARE_CANCELLED');
      });
      return;
    } catch (error) {
      console.warn('PROSTUDIO_NATIVE_SHARE_FAILED', { error: String(error && error.message || error) });
    }
  }
  const telegramShareUrl = 'https://t.me/share/url?url=' + encodeURIComponent(shareUrl)
    + '&text=' + encodeURIComponent('Посмотрите мою генерацию в SYLVEX Pro Studio');
  if (tg && typeof tg.openTelegramLink === 'function') tg.openTelegramLink(telegramShareUrl);
  else window.location.href = telegramShareUrl;
}

function shareStartId() {
  const unsafe = S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : {};
  const params = new URLSearchParams(window.location.search || '');
  const raw = String(unsafe.start_param || params.get('tgWebAppStartParam') || params.get('startapp') || params.get('start') || '');
  return raw.startsWith('share_') ? raw.slice(6) : '';
}

function shareDateLabel(value) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(value));
  } catch { return String(value); }
}

function shareSvg(kind) {
  return generationActionIcon(kind);
}

function ensureGenerationSharePage() {
  let page = document.getElementById('generationSharePage');
  if (page) return page;
  page = document.createElement('div');
  page.id = 'generationSharePage';
  page.className = 'generation-share-page';
  page.innerHTML = '<div class="generation-share-shell">'
    + '<header class="generation-share-brand"><img src="assets/logo.png" alt=""><div><b>SYLVEX</b><span>Pro Studio</span></div>'
    + '<button type="button" aria-label="Закрыть" onclick="SYLVEX.closeGenerationSharePage()">×</button></header>'
    + '<main id="generationShareContent" class="generation-share-content"><div class="generation-share-loading">Загружаем Share Card…</div></main>'
    + '</div>';
  document.body.appendChild(page);
  return page;
}

function closeGenerationSharePage() {
  const page = document.getElementById('generationSharePage');
  if (page) page.classList.remove('is-open');
  document.body.classList.remove('generation-share-open');
  document.body.classList.remove('generation-share-standalone');
}

function renderGenerationShareCard(share) {
  const mode = String(share.mode || 'image');
  const metadata = share.metadata || {};
  const mediaUrl = S.escapeHtml(share.media_url || '');
  const thumbnail = S.escapeHtml(share.thumbnail_url || share.media_url || '');
  const model = metadata.model_label || share.model || share.provider || 'SYLVEX AI';
  let media = '';
  if (mode === 'image') media = '<img src="' + mediaUrl + '" alt="Shared generation" loading="eager">';
  else if (mode === 'video') media = '<video src="' + mediaUrl + '" poster="' + thumbnail + '" controls playsinline preload="metadata"></video>';
  else media = (thumbnail ? '<img class="generation-share-cover" src="' + thumbnail + '" alt="">' : '<div class="generation-share-audio-mark">' + (mode === 'voice' ? 'VO' : '♪') + '</div>')
    + '<audio src="' + mediaUrl + '" controls preload="metadata"></audio>';
  const cost = share.cost || {};
  const costText = [cost.credits !== '' && cost.credits !== undefined && cost.credits !== null ? String(cost.credits) + ' ⚡' : '', cost.usd !== '' && cost.usd !== undefined && cost.usd !== null ? '$' + Number(cost.usd).toFixed(4) : ''].filter(Boolean).join(' · ');
  const dimensions = metadata.width && metadata.height ? metadata.width + '×' + metadata.height : metadata.size;
  const rows = [
    ['Generated with', model], ['Автор', share.author], ['Дата', shareDateLabel(share.created_at)],
    ['Стоимость', costText], ['Время генерации', share.generation_time !== null && share.generation_time !== undefined ? Number(share.generation_time).toFixed(1) + ' s' : ''],
    ['Стиль', metadata.style], ['Персонаж', metadata.character], ['Объект', metadata.object],
    ['Размер', dimensions], ['Provider', share.provider],
  ].filter((row) => row[1] !== '' && row[1] !== null && row[1] !== undefined);
  const actionLabels = mode === 'video'
    ? [['download', 'Скачать', 'download'], ['edit', 'Использовать в Kling Editor', 'editor']]
    : mode === 'image'
      ? [['download', 'Скачать', 'download'], ['lipsync', 'Использовать как референс', 'reference']]
      : [['play', 'Прослушать', 'play'], ['download', 'Скачать', 'download']];
  return '<article class="generation-share-card" data-share-id="' + S.escapeHtml(share.share_id || '') + '" data-mode="' + S.escapeHtml(mode) + '">'
    + '<div class="generation-share-media">' + media + '</div>'
    + '<div class="generation-share-details">' + rows.map((row) => '<div><span>' + S.escapeHtml(row[0]) + '</span><b>' + S.escapeHtml(String(row[1])) + '</b></div>').join('') + '</div>'
    + (share.prompt ? '<div class="generation-share-prompt"><span>Prompt</span><p>' + S.escapeHtml(share.prompt) + '</p>' + (String(share.prompt).length > 220 ? '<button type="button" onclick="this.parentElement.classList.toggle(\'is-expanded\');this.textContent=this.parentElement.classList.contains(\'is-expanded\')?\'Свернуть\':\'Развернуть\'">Развернуть</button>' : '') + '</div>' : '')
    + '<div class="generation-share-actions">' + actionLabels.map((item) => {
      if (item[2] === 'download' && !share.allow_download) return '';
      if ((item[2] === 'reference' || item[2] === 'editor') && !share.allow_reference) return '';
      if (item[2] === 'download') {
        const url = '/api/public/prostudio/share/' + encodeURIComponent(share.share_id) + '/download';
        const filename = generationDownloadFilename(mode, share.share_id);
        return '<button type="button" data-download-url="' + S.escapeHtml(url) + '" data-file-name="' + S.escapeHtml(filename) + '" onclick="SYLVEX.downloadGeneratedFile(event)">' + shareSvg(item[0]) + item[1] + '</button>';
      }
      return '<button type="button" data-share-action="' + item[2] + '" onclick="SYLVEX.handleGenerationShareAction(event)">' + shareSvg(item[0]) + item[1] + '</button>';
    }).join('') + '</div></article>';
}

async function openGenerationSharePage(shareId) {
  if (!shareId) return;
  const page = ensureGenerationSharePage();
  const content = document.getElementById('generationShareContent');
  page.classList.add('is-open');
  document.body.classList.add('generation-share-open');
  try {
    const response = await fetch('/api/public/prostudio/share/' + encodeURIComponent(shareId), { cache: 'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok || !payload.share) throw new Error('share_not_found');
    page._share = payload.share;
    content.innerHTML = renderGenerationShareCard(payload.share);
  } catch {
    content.innerHTML = '<div class="generation-share-error"><b>Share Card недоступна</b><span>Ссылка удалена или публикация закрыта.</span></div>';
  }
}

function applySharedMedia(share, includeSettings) {
  const mode = String(share.mode || 'image');
  const meta = share.metadata || {};
  updateComposerMode(mode);
  const input = document.getElementById('chatInput');
  if (includeSettings && input) {
    input.value = share.prompt || '';
    autoGrow(input);
  }
  if (mode === 'image') {
    imageState.referenceImageUrls = [share.media_url];
    imageState.referenceImageUrl = share.media_url;
    imageState.uploadedImageUrls = [share.media_url];
    if (includeSettings) {
      if (meta.style) imageState.style = meta.style;
      if (meta.character) imageState.characterName = meta.character;
      if (meta.object) imageState.objectName = meta.object;
    }
  } else if (mode === 'video') {
    videoState.inputVideo = share.media_url;
    videoState.videoUrl = share.media_url;
    videoState.referenceVideoUrl = share.media_url;
    if (includeSettings && meta.size) videoState.ratio = meta.size;
  }
  renderUploadedPhotoGrid();
  updateImageUploadButtonPreview();
  updateSendButton();
  closeGenerationSharePage();
  toast(includeSettings ? 'Параметры генерации перенесены' : 'Медиа добавлено как референс');
}

async function handleGenerationShareAction(event) {
  const action = event.currentTarget.dataset.shareAction;
  const page = document.getElementById('generationSharePage');
  const share = page && page._share;
  if (!share) return;
  if (action === 'play') {
    const player = page.querySelector(share.mode === 'video' ? 'video' : 'audio');
    if (player) player.paused ? player.play() : player.pause();
    return;
  }
  try {
    const response = await fetch('/api/public/prostudio/share/' + encodeURIComponent(share.share_id) + '/reference', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: getTelegramId(), init_data: S.tg && S.tg.initData ? S.tg.initData : '' }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error('reference_failed');
    if (payload.reference && payload.reference.media_url) share.media_url = payload.reference.media_url;
    if (action === 'editor') {
      updateComposerMode('edit');
      applyVideoEditInputToState(share.media_url);
      closeGenerationSharePage();
      return;
    }
    applySharedMedia(share, action === 'remix');
  } catch {
    toast('Не удалось перенести генерацию');
  }
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openGenerationInfoDrawer
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openGenerationInfoDrawer(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const message = chatMessages[index] || {};
  const meta = message.metadata || {};
  const drawer = ensureGenerationInfoDrawer();
  const body = document.getElementById('generationInfoBody');
  if (!body) return;

  const type = meta.type || (message.videoUrl ? 'video' : (message.audioUrl ? (currentChatType() === 'voice' ? 'voice' : 'music') : 'image'));
  if (type === 'image') restoreImageStateFromGenerationMetadata(meta);
  const imageUrl = meta.image_url || (type === 'image' ? (meta.full_url || meta.result_url) : '') || ((meta.result_images || [])[0]) || '';
  const videoUrl = meta.video_url || ((meta.videos || [])[0]) || (type === 'video' ? meta.result_url : '') || message.videoUrl || '';
  const audioUrl = meta.audio_url || ((meta.audios || [])[0]) || ((type === 'music' || type === 'voice') ? meta.result_url : '') || message.audioUrl || '';
  const resultUrl = type === 'video' ? videoUrl : ((type === 'music' || type === 'voice') ? audioUrl : (meta.full_url || meta.result_url || imageUrl));
  const jobId = completedGenerationJobId(message, meta);
  const generationStatus = String(meta.status || message.generationStatus || (message.imageResultMini ? 'completed' : '')).toLowerCase();
  const previewUrl = imagePreviewUrl(meta, '');
  const previewFallbackUrl = meta.preview_fallback_url || imageUrl || resultUrl || '';
  const refImages = meta.reference_images || [];
  const created = meta.created_at ? new Date(meta.created_at).toLocaleString() : '';
  const settings = meta.settings || meta.image_options || meta.video_options || meta.music_options || meta.voice_options || {};
  const generationCost = generationCostLabel(meta);
  const titleMap = {
    image: 'Изображение',
    video: 'Видео',
    music: 'Музыка',
    voice: 'Озвучка',
  };
  const titleEl = drawer.querySelector('.generation-info-head h3');
  if (titleEl) titleEl.textContent = titleMap[type] || 'Result';
  const videoThumb = imagePreviewUrl(meta, '');
  const previewHtml = type === 'image' && imageUrl
    ? '<button class="generation-info-preview generation-info-preview-button" type="button" data-image-url="' + S.escapeHtml(resultUrl) + '" onclick="SYLVEX.openImageViewer(event)">' + previewImgHtml(previewUrl, 'generated image', previewFallbackUrl) + '</button>'
    : type === 'video' && videoUrl
      ? '<video class="generation-info-media-player generation-info-video-player" src="' + S.escapeHtml(videoUrl) + '" controls playsinline preload="metadata"></video>'
      : type === 'music' && audioUrl
        ? (imageUrl ? '<div class="generation-info-preview">' + previewImgHtml(previewUrl, 'generated cover') + '</div>' : '<div class="generation-info-preview generation-info-audio-preview"><span>♪</span></div>')
          + '<audio class="generation-result-inline-audio generation-info-inline-audio" src="' + S.escapeHtml(audioUrl) + '" controls preload="metadata" controlsList="nodownload"></audio>'
      : type === 'voice' && audioUrl
        ? '<div class="generation-info-preview generation-info-audio-preview"><span>VO</span></div><audio class="generation-result-inline-audio generation-info-inline-audio" src="' + S.escapeHtml(audioUrl) + '" controls preload="metadata" controlsList="nodownload"></audio>'
      : audioUrl
        ? '<div class="generation-info-preview generation-info-audio-preview"><span>' + S.escapeHtml(type === 'voice' ? 'VO' : '♪') + '</span></div>'
        : (previewUrl ? '<div class="generation-info-preview generation-info-audio-preview"><span>AI</span></div>' : '');
  let actionHtml = '';
  if (resultUrl) {
    if (type === 'music') {
      actionHtml += '<button type="button" data-audio-url="' + S.escapeHtml(audioUrl) + '" data-result-url="' + S.escapeHtml(audioUrl) + '" data-result-kind="music" onclick="SYLVEX.playVoiceInCard(event)">' + generationActionIcon('play') + 'Воспроизвести</button>';
    } else if (type === 'voice') {
      actionHtml += '<button type="button" data-audio-url="' + S.escapeHtml(audioUrl) + '" data-result-url="' + S.escapeHtml(audioUrl) + '" data-result-kind="voice" onclick="SYLVEX.playVoiceInCard(event)">' + generationActionIcon('play') + 'Воспроизвести</button>';
    } else if (type === 'video') {
      actionHtml += '<button type="button" data-video-url="' + S.escapeHtml(videoUrl) + '" data-result-url="' + S.escapeHtml(videoUrl) + '" data-result-kind="video" onclick="SYLVEX.playVideoInGenerationCard(event)">' + generationActionIcon('play') + 'Воспроизвести</button>';
    } else {
      actionHtml += '<button type="button" data-image-url="' + S.escapeHtml(resultUrl) + '" data-result-kind="' + S.escapeHtml(type) + '" onclick="SYLVEX.openImageViewer(event)">' + generationActionIcon('open') + 'Открыть</button>';
    }
    actionHtml += renderCompletedGenerationDownload(jobId, generationStatus, '', type);
    actionHtml += '<button type="button" onclick="SYLVEX.shareGenerationCard(event,' + index + ')">' + generationActionIcon('share') + 'Поделиться</button>';
    actionHtml += renderGeneratedTelegramButton(resultUrl, type);
    if (type === 'image') {
      actionHtml += '<button type="button" data-image-url="' + S.escapeHtml(resultUrl) + '" onclick="SYLVEX.animateGeneratedImage(event)">' + generationActionIcon('animate') + 'Оживить фото</button>';
    } else if (type === 'video') {
      actionHtml += '<button type="button" data-video-url="' + S.escapeHtml(resultUrl) + '" onclick="SYLVEX.editGeneratedVideo(event)">' + generationActionIcon('edit') + 'Редактировать видео</button>';
    }
  }
  body.innerHTML =
    previewHtml
    + '<div class="generation-info-section">'
    + generationInfoRow('Тип', type)
    + generationInfoRow('Модель', meta.model_label || meta.model)
    + generationInfoRow('Provider', meta.provider)
    + generationInfoRow('Provider Model', meta.provider_model)
    + generationInfoRow('Style', meta.style)
    + generationInfoRow('Genre', settings.genre)
    + generationInfoRow('Mood', settings.mood)
    + generationInfoRow('Tempo', settings.tempo)
    + generationInfoRow('Character', meta.characterName || meta.character)
    + generationInfoRow('Object', meta.objectName || meta.objects)
    + generationInfoRow('Ratio', meta.ratio)
    + generationInfoRow('Size', meta.size || settings.resolution)
    + (type === 'image' ? generationInfoRow('Seed', (meta.seed === null || meta.seed === undefined || meta.seed === '') ? 'Случайный' : meta.seed) : '')
    + generationInfoRow('Стоимость генерации', generationCost)
    + generationInfoRow('Duration', meta.duration || settings.duration)
    + generationInfoRow('Count', meta.count)
    + generationInfoRow('Created', created)
    + generationInfoRow('Telegram', meta.sent_to_telegram ? 'sent' : 'not sent')
    + '</div>'
    + (meta.prompt ? '<div class="generation-info-section generation-prompt-block"><div class="generation-info-label">Промт</div><p class="generation-info-text">' + S.escapeHtml(meta.prompt) + '</p>' + (String(meta.prompt).length > 180 ? '<button class="generation-prompt-toggle" type="button" aria-expanded="false" onclick="SYLVEX.toggleGenerationPrompt(event)">Развернуть</button>' : '') + '</div>' : '')
    + (refImages.length ? '<div class="generation-info-section"><div class="generation-info-label">Reference images</div><div class="generation-info-ref-row">' + refImages.map((url) => '<img src="' + S.escapeHtml(url) + '" alt="reference" />').join('') + '</div></div>' : '')
    + (actionHtml ? '<div class="generation-info-actions">' + actionHtml + '</div>' : '');

  drawer.classList.add('show');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeGenerationInfoDrawer
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeGenerationInfoDrawer(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const drawer = document.getElementById('generationInfoDrawer');
  if (drawer) drawer.classList.remove('show');
}

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeUploadImagePreview
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeUploadImagePreview(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const preview = document.getElementById('uploadImagePreview');
    const img = document.getElementById('uploadPreviewImg');
    if (preview) preview.classList.remove('show');
    if (img) img.src = '';
  }

// =====================================================
// ЗАПУСК ГЕНЕРАЦИИ: selectGeneratedImage
// Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
// =====================================================
function selectGeneratedImage(e, url) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const target = getUploadTarget();
  applyUploadToTarget(url, target);
  renderUploadedPhotoGrid();
  renderUploadPreviewForTarget(target);
  renderUploadPanelImages();
  closeUploadImagePreview(e);

  toast('Фото добавлено в черновик');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: openUploadPanel
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function openUploadPanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

const panel = ensureUploadPanel();
panel.dataset.uploadTarget = getUploadTarget();
renderUploadPanelImages();
renderUploadedPhotoGrid();
panel.classList.add('show');

  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }

  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

// =====================================================
// ОБРАБОТЧИК ИНТЕРФЕЙСА: closeUploadPanel
// Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
// =====================================================
function closeUploadPanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const panel = document.getElementById('uploadPanel');
  if (panel) panel.classList.remove('show');
}
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openNativeFilePicker
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function isKlingOmniEditUploadContext() {
    if (!isVideoMode()) return false;
    const config = currentVideoConfig() || {};
    const modelId = String(videoState.modelId || '').toLowerCase();
    return config.provider === 'kling' && (
      !!config.omni
      || modelId === 'kling_o3_omni'
      || modelId === 'kling_o3_edit'
      || modelId.indexOf('kling_motion') === 0
    );
  }

  function klingOmniVideoFileError(file) {
    if (!file) return 'Видео не выбрано';
    const name = String(file.name || '').toLowerCase();
    const mime = String(file.type || '').toLowerCase();
    const isMp4OrMov = /\.(mp4|mov)$/.test(name) || mime === 'video/mp4' || mime === 'video/quicktime';
    if (!isMp4OrMov) return 'Для Kling 3.0 Omni выберите видео MP4 или MOV';
    if ((file.size || 0) > 200 * 1024 * 1024) return 'Для Kling 3.0 Omni видео должно быть до 200 MB';
    return '';
  }

  function isVideoFileLike(file) {
    if (!file) return false;
    const mime = String(file.type || '').toLowerCase();
    const name = String(file.name || '').toLowerCase();
    return mime.startsWith('video/') || /\.(mp4|mov|m4v|webm)$/.test(name);
  }

  function isAudioFileLike(file) {
    if (!file) return false;
    const mime = String(file.type || '').toLowerCase();
    const name = String(file.name || '').toLowerCase();
    return mime.startsWith('audio/') || /\.(mp3|wav|m4a|aac|ogg|oga|webm|flac)$/.test(name);
  }

  function isImageFileLike(file) {
    if (!file) return false;
    const mime = String(file.type || '').toLowerCase();
    const name = String(file.name || '').toLowerCase();
    return mime.startsWith('image/') || /\.(jpg|jpeg|png|webp)$/.test(name);
  }

  function klingOmniVideoMetadataError(file) {
    return new Promise((resolve) => {
      if (!file || !window.URL || !URL.createObjectURL) {
        resolve('');
        return;
      }
      const url = URL.createObjectURL(file);
      const video = document.createElement('video');
      let settled = false;
      const finish = (message) => {
        if (settled) return;
        settled = true;
        try { URL.revokeObjectURL(url); } catch {}
        resolve(message || '');
      };
      video.preload = 'metadata';
      video.onloadedmetadata = () => {
        const duration = Number(video.duration || 0);
        const width = Number(video.videoWidth || 0);
        const height = Number(video.videoHeight || 0);
        if (duration && (duration < 3 || duration > 15.5)) {
          finish('Для Kling 3.0 Omni выберите видео 3–15.5 секунд');
          return;
        }
        if ((width && (width < 700 || width > 4553)) || (height && (height < 700 || height > 4553))) {
          finish('Для Kling 3.0 Omni размер видео должен быть от 700 до 4553 px по ширине и высоте');
          return;
        }
        if (width && height) {
          const area = width * height;
          const ratio = width / height;
          if (area > 8294400 || ratio < 0.4 || ratio > 2) {
            finish('Для Kling 3.0 Omni выберите видео с ratio от 0.4 до 2 и площадью кадра до 8294400 px');
            return;
          }
        }
        finish('');
      };
      video.onerror = () => finish('Не удалось прочитать параметры видео');
      video.src = url;
      setTimeout(() => finish(''), 2500);
    });
  }

  function klingOmniImageFileError(file) {
    if (!file) return 'Фото не выбрано';
    const name = String(file.name || '').toLowerCase();
    const mime = String(file.type || '').toLowerCase();
    const isSupported = /\.(jpg|jpeg|png)$/.test(name) || mime === 'image/jpeg' || mime === 'image/png';
    if (!isSupported) return 'Для Kling 3.0 Omni выберите изображение JPG или PNG';
    if ((file.size || 0) > 50 * 1024 * 1024) return 'Для Kling 3.0 Omni изображение должно быть до 50 MB';
    return '';
  }

  function klingOmniImageMetadataError(file) {
    return new Promise((resolve) => {
      if (!file || !window.URL || !URL.createObjectURL) {
        resolve('');
        return;
      }
      const url = URL.createObjectURL(file);
      const image = new Image();
      let settled = false;
      const finish = (message) => {
        if (settled) return;
        settled = true;
        try { URL.revokeObjectURL(url); } catch {}
        resolve(message || '');
      };
      image.onload = () => {
        const width = Number(image.naturalWidth || 0);
        const height = Number(image.naturalHeight || 0);
        if ((width && width < 300) || (height && height < 300)) {
          finish('Для Kling 3.0 Omni изображение должно быть не меньше 300 px по ширине и высоте');
          return;
        }
        if (width && height) {
          const ratio = width / height;
          if (ratio < 0.4 || ratio > 2.5) {
            finish('Для Kling 3.0 Omni ratio изображения должен быть от 1:2.5 до 2.5:1');
            return;
          }
        }
        finish('');
      };
      image.onerror = () => finish('Не удалось прочитать параметры изображения');
      image.src = url;
      setTimeout(() => finish(''), 2500);
    });
  }

  function openNativeFilePicker(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    const inp = document.getElementById('attachInput');
    if (!inp) return;
    const klingOmniEdit = isKlingOmniEditUploadContext();
    const allowVideoForTarget = isVideoMode() ? videoUploadTargetAllowsVideo() : true;
    if (kind === 'music_audio') { inp.accept = 'audio/*'; pendingAttachAccept = 'audio'; }
    else if (kind === 'voice_audio') { inp.accept = 'audio/*'; pendingAttachAccept = 'voice_media'; }
    else if (kind === 'voice_video') { inp.accept = 'video/*'; pendingAttachAccept = 'voice_media'; }
    else if (kind === 'voice_document') { inp.accept = '.txt,.pdf,.doc,.docx,text/plain,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'; pendingAttachAccept = 'voice_document'; }
    else if (kind === 'voice_media') { inp.accept = 'audio/*,video/*'; pendingAttachAccept = 'voice_media'; }
    else if (kind === 'text_audio') { inp.accept = '.wav,.mp3,.aiff,.aif,.aac,.ogg,.oga,.flac,audio/wav,audio/mpeg,audio/aiff,audio/aac,audio/ogg,audio/flac'; pendingAttachAccept = 'text_media'; }
    else if (kind === 'text_video') { inp.accept = '.mp4,.mpeg,.mpg,.mov,.avi,.flv,.webm,.wmv,.3gp,video/mp4,video/mpeg,video/quicktime,video/x-msvideo,video/x-flv,video/webm,video/x-ms-wmv,video/3gpp'; pendingAttachAccept = 'text_media'; }
    else if (kind === 'text_document') { inp.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx,text/plain,application/pdf,application/json,text/csv,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'; pendingAttachAccept = 'text_document'; }
    else if (kind === 'text_media') { inp.accept = 'image/*,.wav,.mp3,.aiff,.aif,.aac,.ogg,.oga,.flac,.mp4,.mpeg,.mpg,.mov,.avi,.flv,.webm,.wmv,.3gp,.txt,.md,.json,.csv,.pdf,.doc,.docx'; pendingAttachAccept = 'text_media'; }
    else if (kind === 'media') {
      inp.accept = !allowVideoForTarget
        ? 'image/*'
        : (klingOmniEdit ? 'image/jpeg,image/png,video/mp4,video/quicktime,.jpg,.jpeg,.png,.mp4,.mov' : 'image/*,video/*');
      pendingAttachAccept = !allowVideoForTarget ? 'image' : 'media';
    }
    else if (kind === 'image') { inp.accept = 'image/*'; pendingAttachAccept = 'image'; }
    else if (kind === 'video') { inp.accept = klingOmniEdit ? 'video/mp4,video/quicktime,.mp4,.mov' : 'video/*'; pendingAttachAccept = 'video'; }
    else { inp.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx'; pendingAttachAccept = 'file'; }
    const target = getUploadTarget();
    const singleTarget = target === UPLOAD_TARGETS.VIDEO_START
      || target === UPLOAD_TARGETS.VIDEO_END
      || target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT
      || /^text_|document|file$/.test(kind);
    inp.multiple = !singleTarget;
    inp.value = '';
    inp.click();
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: uploadProStudioMediaFile
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  async function uploadProStudioMediaFile(file, kind, preferInternalPath) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/public/prostudio/upload-media?kind=' + encodeURIComponent(kind || 'image'), {
      method: 'POST',
      body: form,
    });
    // =====================================================
    // JAVASCRIPT-БЛОК: data
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok || !data.url) {
      throw new Error(data.error || 'Не удалось загрузить файл');
    }
    return String((preferInternalPath && data.path) || (kind === 'image' && data.inline_url) || data.url || '');
  }

  function revokeVoiceUploadPreview() {
    const url = voiceState.uploadPreviewUrl || '';
    if (url && url.startsWith('blob:')) {
      try { URL.revokeObjectURL(url); } catch {}
    }
    voiceState.uploadPreviewUrl = '';
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: attach
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function attach(kind, target, e) {
    if (target && target.preventDefault) {
      e = target;
      target = '';
    }
    if (isMusicMode()) {
      openNativeFilePicker('music_audio');
      return;
    }
    if (kind === 'video') {
      if (isVideoMode() && videoState.section === 'edit') {
        openVideoEditInputUpload(e);
        return;
      }
      openNativeFilePicker('video');
      return;
    }
    if (target === 'start') return openVideoStartUpload(e);
    if (target === 'end') return openVideoEndUpload(e);
    if (target === 'reference' || target === 'references') return openVideoReferencesUpload(e);
    return openImageUpload(e);
  }
  // =====================================================
  // ЗАГРУЗКА В MINI APP: onAttachFile
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  async function onAttachFile(e) {
    const files = Array.from((e.target && e.target.files) || []);
    if (e.target) e.target.value = '';
    if (!files.length) return;
    const target = getUploadTarget();
    const currentCount = currentUploadImages(target).length;
    const targetLimit = uploadLimitForTarget(target);
    const pending = pendingAttachAccept || 'file';
    const singleSelection = target === UPLOAD_TARGETS.VIDEO_START
      || target === UPLOAD_TARGETS.VIDEO_END
      || target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT
      || /^text_|voice_document|text_document|file$/.test(pending);
    const audioUploads = (isVoiceMode() || isMusicMode())
      ? ((currentAudioState().uploads || []).filter(Boolean).length)
      : 0;
    const remaining = singleSelection
      ? 1
      : ((isVoiceMode() || isMusicMode()) ? Math.max(0, 4 - audioUploads) : Math.max(0, targetLimit - currentCount));
    if (remaining <= 0) {
      toast('Можно загрузить не больше ' + targetLimit + ' фото');
      return;
    }
    if (files.length > remaining) {
      toast('Можно выбрать не больше ' + (singleSelection ? 1 : targetLimit) + ' файлов одновременно');
    }
    for (const file of files.slice(0, remaining)) {
      await processAttachFile(file, pending);
    }
  }

  async function processAttachFile(f, requestedKind) {
    if (!f) return;
    let pendingKind = requestedKind || pendingAttachAccept || 'file';
    // Handle 'media' kind: treat as image or video depending on file type
    if (pendingKind === 'media') {
      if (isVideoFileLike(f)) {
        pendingKind = 'video';
      } else {
        pendingKind = 'image';
      }
    } else if (pendingKind === 'voice_media') {
      pendingKind = isVideoFileLike(f) ? 'video' : 'audio';
    } else if (pendingKind === 'voice_document') {
      pendingKind = 'file';
    } else if (pendingKind === 'text_media') {
      if (isVideoFileLike(f)) pendingKind = 'text_video';
      else if (isAudioFileLike(f)) pendingKind = 'text_audio';
      else if (isImageFileLike(f)) pendingKind = 'text_image';
      else pendingKind = 'text_file';
    } else if (pendingKind === 'text_document') {
      pendingKind = 'text_file';
    }
    if (pendingKind === 'image' && !isImageFileLike(f)) {
      toast('Выберите файл изображения');
      return;
    }
    if (pendingKind === 'text_audio' && !/\.(wav|mp3|aiff?|aac|ogg|oga|flac)$/i.test(String(f.name || ''))) {
      toast('Для анализа поддерживаются WAV, MP3, AIFF, AAC, OGG и FLAC');
      return;
    }
    if (pendingKind === 'text_video' && !/\.(mp4|mpeg|mpg|mov|avi|flv|webm|wmv|3gp)$/i.test(String(f.name || ''))) {
      toast('Для анализа поддерживаются MP4, MPEG, MOV, AVI, FLV, WebM, WMV и 3GP');
      return;
    }
    const isKlingOmniEdit = isKlingOmniEditUploadContext();
    const isKlingOmniVideo = isKlingOmniEdit && pendingKind === 'video';
    const isKlingOmniImage = isKlingOmniEdit && pendingKind === 'image';
    if (isKlingOmniVideo) {
      const videoError = klingOmniVideoFileError(f) || await klingOmniVideoMetadataError(f);
      if (videoError) {
        toast(videoError);
        return;
      }
    }
    if (isKlingOmniImage) {
      const imageError = klingOmniImageFileError(f) || await klingOmniImageMetadataError(f);
      if (imageError) {
        toast(imageError);
        return;
      }
    }
    const maxSize = (pendingKind === 'video' || pendingKind === 'text_video') ? 200 * 1024 * 1024 : 50 * 1024 * 1024;
    if (f.size > maxSize) {
      toast(pendingKind === 'video' ? 'Видео слишком большое (макс. 200 MB)' : 'Файл слишком большой (макс. 50 MB)');
      return;
    }
    if (isVoiceMode() && (pendingKind === 'video' || pendingKind === 'audio')) {
      revokeVoiceUploadPreview();
      const previewUrl = URL.createObjectURL(f);
      voiceState.uploadPreviewUrl = previewUrl;
      voiceState.uploading = {
        kind: pendingKind,
        name: f.name,
        mime: f.type || (pendingKind === 'video' ? 'video/mp4' : 'audio/mpeg'),
        size: f.size || 0,
        previewUrl,
      };
      voiceState.attachment = null;
      renderVoiceToolPanel();
      updateSendButton();
      uploadProStudioMediaFile(f, pendingKind)
        .then((url) => {
          voiceState.uploading = null;
          voiceState.uploads = (voiceState.uploads || []).filter((item) => item.url !== url);
          voiceState.uploads.push({
            kind: pendingKind,
            url,
            previewUrl,
            name: f.name,
            mime: f.type || (pendingKind === 'video' ? 'video/mp4' : 'audio/mpeg'),
            size: f.size || 0,
          });
          voiceState.uploads = voiceState.uploads.slice(0, 4);
          voiceState.attachment = {
            kind: pendingKind,
            url,
            previewUrl,
            name: f.name,
            mime: f.type || (pendingKind === 'video' ? 'video/mp4' : 'audio/mpeg'),
            size: f.size || 0,
          };
          renderVoiceToolPanel();
          updateSendButton();
          toast(pendingKind === 'video' ? 'Видео загружено' : 'Аудио загружено');
        })
        .catch((err) => {
          voiceState.uploading = null;
          voiceState.attachment = null;
          revokeVoiceUploadPreview();
          renderVoiceToolPanel();
          updateSendButton();
          toast((err && err.message) || (pendingKind === 'video' ? 'Не удалось загрузить видео' : 'Не удалось загрузить аудио'));
        });
      return;
    }
    if (isVoiceMode() && pendingKind === 'file') {
      voiceState.uploading = { kind:'file', name:f.name, mime:f.type || 'application/octet-stream', size:f.size || 0 };
      voiceState.attachment = null;
      renderVoiceToolPanel();
      updateSendButton();
      uploadProStudioMediaFile(f, 'document')
        .then((url) => {
          const uploaded = { kind:'file', url, name:f.name, mime:f.type || 'application/octet-stream', size:f.size || 0 };
          voiceState.uploading = null;
          voiceState.uploads = [uploaded];
          voiceState.attachment = uploaded;
          renderVoiceToolPanel();
          updateSendButton();
          toast('Документ загружен');
        })
        .catch((err) => {
          voiceState.uploading = null;
          voiceState.attachment = null;
          renderVoiceToolPanel();
          updateSendButton();
          toast((err && err.message) || 'Не удалось загрузить документ');
        });
      return;
    }
    if (studioMode === 'text' && (pendingKind === 'text_video' || pendingKind === 'text_audio' || pendingKind === 'text_image' || pendingKind === 'text_file')) {
      const uploadKind = pendingKind === 'text_video' ? 'video' : (pendingKind === 'text_audio' ? 'audio' : (pendingKind === 'text_image' ? 'image' : 'file'));
      textState.attachment = {
        kind: uploadKind,
        name: f.name,
        mime: f.type || (uploadKind === 'video' ? 'video/mp4' : (uploadKind === 'audio' ? 'audio/mpeg' : (uploadKind === 'image' ? 'image/png' : 'application/octet-stream'))),
        size: f.size || 0,
        uploading: true,
      };
      renderTextControls();
      updateSendButton();
      toast(uploadKind === 'video' ? 'Загружаем видео…' : (uploadKind === 'audio' ? 'Загружаем аудио…' : (uploadKind === 'image' ? 'Загружаем фото…' : 'Загружаем файл…')));
      uploadProStudioMediaFile(f, uploadKind, true)
        .then((url) => {
          textState.attachment = {
            kind: uploadKind,
            url,
            name: f.name,
            mime: f.type || (uploadKind === 'video' ? 'video/mp4' : (uploadKind === 'audio' ? 'audio/mpeg' : (uploadKind === 'image' ? 'image/png' : 'application/octet-stream'))),
            size: f.size || 0,
          };
          pendingAttachment = textState.attachment;
          if (uploadKind === 'video') {
            selectGeminiForTextMedia();
            if (!textState.tool || textState.tool === 'text') textState.tool = 'video_prompt';
          }
          if (uploadKind === 'audio') {
            selectGeminiForTextMedia();
            textState.tool = 'audio_to_text';
          }
          if (uploadKind === 'image' && textState.tool === 'text') textState.tool = 'image_prompt';
          renderTextControls();
          updateSendButton();
          toast(uploadKind === 'video' ? 'Видео добавлено' : (uploadKind === 'audio' ? 'Аудио добавлено' : (uploadKind === 'image' ? 'Фото добавлено' : 'Файл добавлен')));
        })
        .catch((err) => {
          textState.attachment = null;
          pendingAttachment = null;
          renderTextControls();
          updateSendButton();
          toast((err && err.message) || 'Не удалось загрузить файл');
        });
      return;
    }
    if (pendingKind === 'video' && isVideoMode()) {
      const target = getUploadTarget();
      const showEditUploading = target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT;
      const showReferenceUploading = target === UPLOAD_TARGETS.VIDEO_REFERENCES;
      let previewUrl = '';
      if ((showEditUploading || showReferenceUploading) && window.URL && URL.createObjectURL) {
        previewUrl = URL.createObjectURL(f);
        const uploadInfo = {
          kind: 'video',
          name: f.name,
          size: f.size || 0,
          mime: f.type || 'video/mp4',
          previewUrl,
        };
        if (showEditUploading) videoState.editUploading = uploadInfo;
        if (showReferenceUploading) videoState.referenceUploading = uploadInfo;
        renderVideoEditPreview();
        renderVideoReferencesPreview();
        renderUploadedPhotoGrid();
      }
      uploadProStudioMediaFile(f, 'video')
        .then((url) => {
          if (previewUrl) {
            try { URL.revokeObjectURL(previewUrl); } catch {}
          }
          if (showEditUploading) videoState.editUploading = null;
          if (showReferenceUploading) videoState.referenceUploading = null;
          if (target === UPLOAD_TARGETS.VIDEO_EDIT_INPUT) {
            applyVideoEditInputToState(url);
            toast('Видео добавлено в редактор');
          } else if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
            applyVideoReferenceToState(url);
            toast('Видео добавлено как референс');
          } else {
            applyVideoEditInputToState(url);
            renderVideoControls();
            toast('Видео загружено');
          }
          renderVideoEditPreview();
          renderVideoReferencesPreview();
          updateSendButton();
        })
        .catch((err) => {
          if (previewUrl) {
            try { URL.revokeObjectURL(previewUrl); } catch {}
          }
          if (showEditUploading) videoState.editUploading = null;
          if (showReferenceUploading) videoState.referenceUploading = null;
          renderVideoEditPreview();
          renderVideoReferencesPreview();
          renderUploadedPhotoGrid();
          toast((err && err.message) || 'Не удалось загрузить видео');
        });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const b64 = result.split(',')[1] || '';
      const attachment = {
        kind: pendingKind === 'text_file' ? 'file' : pendingKind,
        mime: f.type || 'application/octet-stream',
        name: f.name,
        dataBase64: b64,
      };
      if (pendingKind === 'image' && result) {
        const target = getUploadTarget();
        if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) imageState.attachment = attachment;
        applyUploadToTarget(result, target);
        renderUploadedPhotoGrid();
        renderUploadPreviewForTarget(target);
        toast('Фото загружено');
      } else {
        setCurrentModeAttachment(attachment);
      }

      if ((isMusicMode() || isVoiceMode()) && result && pendingKind !== 'image') {
        const state = currentAudioState();
        state.uploads = (state.uploads || []).filter((item) => item.url !== result);
        state.uploads.push({
          kind: pendingKind,
          url: result,
          name: f.name,
          mime: f.type || 'application/octet-stream',
        });
        state.uploads = state.uploads.slice(0, 4);
        toast('Файл загружен');
        if (isVoiceMode()) renderVoiceToolPanel();
      }

      try { updateSendButton(); } catch {}
      if (studioMode === 'text') renderTextControls();
    };
    reader.readAsDataURL(f);
  }
  // =====================================================
  // ЗАГРУЗКА В MINI APP: clearAttachment
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function clearAttachment() {
    setCurrentModeAttachment(null);
    if (studioMode === 'text') renderTextControls();
    try { updateSendButton(); } catch {}
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoiceMediaPicker
  // Открывает выбор видео или аудио для инструментов ElevenLabs «Дубляж» и «Копирование голоса».
  // Загруженный файл сохраняется только в voiceState.uploads.
  // =====================================================
  function openVoiceMediaPicker(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!isVoiceMode()) return;
    ensureVoiceSettings();
    const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
    if (purpose.accept === 'video/*') openNativeFilePicker('voice_video');
    else if (purpose.accept === 'audio/*') openNativeFilePicker('voice_audio');
    else if (String(purpose.accept || '').includes('.pdf')) openNativeFilePicker('voice_document');
    else openNativeFilePicker('voice_media');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: confirmVoiceUpload
  // Фиксирует выбранный режим, модель и файл в кнопке «Загрузить» до отправки промпта.
  // =====================================================
  function confirmVoiceUpload(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!isVoiceMode()) return;
    ensureVoiceSettings();
    const uploads = Array.isArray(voiceState.uploads) ? voiceState.uploads : [];
    const purpose = voiceUploadPurposeMeta(voiceState.uploadPurpose || 'voiceover');
    if (purpose.needsFile && !uploads.length) {
      toast('Сначала выберите файл');
      return;
    }
    activeVoicePanelSection = '';
    renderVoiceToolPanel();
    renderVoiceControls();
    updateSendButton();
    toast(uploads.length ? 'Загрузка добавлена' : 'Параметры загрузки добавлены');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoicePanelSection
  // Переключает внутренние экраны блока «Озвучка»: список голосов, создание голоса или загрузка.
  // При открытии списка дополнительно подтягивает реальные голоса провайдера.
  // =====================================================
  function openVoicePanelSection(e, section) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    activeVoicePanelSection = activeVoicePanelSection === section ? '' : (section || '');
    renderVoiceToolPanel();
    if (activeVoicePanelSection === 'voices') {
      loadVoiceAvatarCatalog(false).then(renderVoiceToolPanel).catch(() => {});
      if (isElevenLabsVoiceModel(voiceState.modelId)) {
        loadElevenLabsVoices(false).then(() => { renderVoiceToolPanel(); return ensureGeneratedVoiceAvatars(currentVoiceListForPanel()); }).catch(() => {});
      } else if (isRunwayVoiceModel(voiceState.modelId)) {
        loadRunwayVoices(false).then(() => { renderVoiceToolPanel(); return ensureGeneratedVoiceAvatars(currentVoiceListForPanel()); }).catch(() => {});
      } else {
        void ensureGeneratedVoiceAvatars(currentVoiceListForPanel());
      }
    }
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoiceCreate
  // Открывает экран создания собственного голоса из кнопки «Создать голос».
  // =====================================================
  function openVoiceCreate(e) {
    openVoicePanelSection(e, 'create');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoiceList
  // Открывает список голосов текущего провайдера из кнопки «Список голосов».
  // =====================================================
  function openVoiceList(e) {
    openVoicePanelSection(e, 'voices');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoiceUpload
  // Открывает экран загрузки медиа для дубляжа, копирования голоса и обработки аудио.
  // =====================================================
  function openVoiceUpload(e) {
    openVoicePanelSection(e, 'upload');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: openVoiceCloneFilePicker
  // Позволяет добавить готовый аудиофайл вместо записи с микрофона для создания собственного голоса.
  // Файл остаётся только в локальном preview до нажатия «Создать голос».
  // =====================================================
  function openVoiceCloneFilePicker(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (voiceCloneRecorder && voiceCloneRecorder.state === 'recording') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/*';
    input.onchange = () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 50 * 1024 * 1024) {
        toast('Файл слишком большой (макс. 50 MB)');
        return;
      }
      if (voiceClonePreviewUrl) URL.revokeObjectURL(voiceClonePreviewUrl);
      voiceCloneBlob = file;
      voiceCloneDraft.source = 'upload';
      voiceClonePreviewUrl = URL.createObjectURL(file);
      setupVoiceClonePreviewAudio();
      renderVoiceToolPanel();
    };
    input.click();
  }

  async function openVoiceCloneAvatarPicker(e) {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!String(file.type || '').startsWith('image/')) { toast('Выберите изображение'); return; }
      if (file.size > 12 * 1024 * 1024) { toast('Фото слишком большое (макс. 12 MB)'); return; }
      const temporaryUrl = URL.createObjectURL(file);
      voiceCloneDraft.avatarUrl = temporaryUrl;
      renderVoiceToolPanel();
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch('/api/public/prostudio/upload-media?kind=image', { method: 'POST', body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok || !data.url) throw new Error(data.error || 'Не удалось загрузить аватарку');
        voiceCloneDraft.avatarUrl = String(data.url);
        toast('Аватарка добавлена');
      } catch (err) {
        voiceCloneDraft.avatarUrl = '';
        toast(translateGenerationError(err, 'Не удалось загрузить аватарку'));
      } finally {
        URL.revokeObjectURL(temporaryUrl);
        renderVoiceToolPanel();
      }
    };
    input.click();
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: setVoiceCloneField
  // Сохраняет значения формы создания голоса без перерисовки всего окна.
  // =====================================================
  function setVoiceCloneField(e, field, value) {
    if (e) e.stopPropagation();
    voiceCloneDraft[field] = String(value || '').slice(0, field === 'name' ? 80 : 40);
    if (field === 'name') {
      const avatar = document.querySelector('.voice-create-sheet .voice-style-row-avatar.is-generated');
      if (avatar) {
        avatar.setAttribute('style', voiceAvatarStyle(voiceCloneDraft.name || 'Новый голос'));
        const initials = avatar.querySelector('.voice-generated-initials');
        if (initials) initials.textContent = voiceInitials(voiceCloneDraft.name || 'Голос');
      }
    }
    updateVoiceCloneSubmitState();
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: toggleVoiceCloneDropdown
  // Открывает фирменный выпадающий список внутри окна создания голоса.
  // =====================================================
  function toggleVoiceCloneDropdown(e, kind) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const root = e && e.target && e.target.closest ? e.target.closest('.voice-select') : null;
    document.querySelectorAll('.voice-select.open').forEach((item) => {
      if (item !== root) item.classList.remove('open');
    });
    if (root) root.classList.toggle('open');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: selectVoiceCloneOption
  // Выбирает значение кастомного dropdown и сразу применяет его к preview.
  // =====================================================
  function selectVoiceCloneOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    voiceCloneDraft[kind] = value || (kind === 'gender' ? 'neutral' : 'neutral');
    applyVoiceClonePreviewSettings();
    renderVoiceToolPanel();
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: setVoiceCloneSetting
  // Синхронизирует ползунок и цифровое поле настройки речи.
  // =====================================================
  function setVoiceCloneSetting(e, key, value) {
    if (e) e.stopPropagation();
    const clamped = Math.max(0, Math.min(100, Number(value || 0)));
    voiceCloneDraft[key] = clamped;
    const row = e && e.target && e.target.closest ? e.target.closest('.voice-param-row') : null;
    if (row) {
      row.querySelectorAll('input').forEach((input) => {
        if (Number(input.value) !== clamped) input.value = clamped;
      });
    }
    applyVoiceClonePreviewSettings();
  }

  function updateVoiceCloneSubmitState() {
    const btn = document.querySelector('.voice-create-submit');
    if (!btn) return;
    btn.disabled = !((voiceCloneDraft.name || '').trim() && voiceCloneBlob && !voiceCloneSubmitting);
  }

  function voiceClonePlaybackRate() {
    const speed = Number(voiceCloneDraft.speed ?? 50);
    const pitch = Number(voiceCloneDraft.pitch ?? 50);
    const intonation = Number(voiceCloneDraft.intonation ?? 50);
    const expressiveness = Number(voiceCloneDraft.expressiveness ?? 50);
    const emotionBoost = voiceCloneDraft.emotion === 'joy' || voiceCloneDraft.emotion === 'energy' ? .06 : (voiceCloneDraft.emotion === 'calm' ? -.05 : 0);
    const tonalBoost = ((pitch - 50) * .0025) + ((intonation - 50) * .0015) + ((expressiveness - 50) * .001);
    return Math.max(.5, Math.min(1.8, .65 + (speed / 100) * .7 + emotionBoost + tonalBoost));
  }

  function setupVoiceClonePreviewAudio() {
    if (voiceClonePreviewAudio) {
      try { voiceClonePreviewAudio.pause(); } catch {}
      voiceClonePreviewAudio = null;
    }
    voiceClonePreviewPlaying = false;
    voiceClonePreviewTime = 0;
    voiceClonePreviewDuration = 0;
    if (!voiceClonePreviewUrl) return;
    voiceClonePreviewAudio = new Audio(voiceClonePreviewUrl);
    voiceClonePreviewAudio.preload = 'metadata';
    applyVoiceClonePreviewSettings();
    voiceClonePreviewAudio.onloadedmetadata = () => {
      voiceClonePreviewDuration = Number.isFinite(voiceClonePreviewAudio.duration) ? voiceClonePreviewAudio.duration : 0;
      renderVoiceToolPanel();
    };
    voiceClonePreviewAudio.ontimeupdate = () => {
      voiceClonePreviewTime = voiceClonePreviewAudio.currentTime || 0;
      const current = document.querySelector('.voice-wave-player time:first-of-type');
      if (current) {
        const mm = Math.floor(voiceClonePreviewTime / 60);
        const ss = Math.floor(voiceClonePreviewTime % 60);
        current.textContent = mm + ':' + String(ss).padStart(2, '0');
      }
    };
    voiceClonePreviewAudio.onended = () => {
      voiceClonePreviewPlaying = false;
      voiceClonePreviewTime = 0;
      renderVoiceToolPanel();
    };
  }

  function applyVoiceClonePreviewSettings() {
    voiceState.audioSettings = Object.assign({}, voiceState.audioSettings || {}, {
      clone_gender: voiceCloneDraft.gender || 'neutral',
      clone_emotion: voiceCloneDraft.emotion || 'neutral',
      speed: Number(voiceCloneDraft.speed ?? 50),
      pitch: Number(voiceCloneDraft.pitch ?? 50),
      intonation: Number(voiceCloneDraft.intonation ?? 50),
      expressiveness: Number(voiceCloneDraft.expressiveness ?? 50),
    });
    if (voiceClonePreviewAudio) {
      voiceClonePreviewAudio.playbackRate = voiceClonePlaybackRate();
      voiceClonePreviewAudio.preservesPitch = false;
    }
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: clearVoiceUploads
  // Очищает только файлы озвучки: видео для дубляжа или аудио для speech-to-speech.
  // Не затрагивает upload-зоны фото и видео.
  // =====================================================
  function clearVoiceUploads(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    voiceState.uploads = [];
    voiceState.attachment = null;
    voiceState.uploading = null;
    revokeVoiceUploadPreview();
    renderVoiceToolPanel();
    updateSendButton();
    toast('Файлы озвучки очищены');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: videoTemplateText
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function videoTemplateText(key) {
    const lang = (typeof uiLang === 'function' && uiLang()) || 'ru';
    const dict = {
      ru: {
        video: 'Видео',
        effects: 'Эффекты движения',
        catalogEmpty: 'Видео-шаблоны пока не настроены',
        effectsEmpty: 'Эффекты Kling пока не настроены',
        uploadTitle: 'Загрузить изображение',
        uploadHint: 'PNG, JPG или вставить из буфера обмена',
        create: 'Создать',
        imageRequired: 'Загрузите изображение для видео-шаблона',
        ratioRequired: 'Выберите формат видео',
        templateVideoRequired: 'Для этого видео-шаблона нужно загрузить preview.mp4',
      },
      en: {
        video: 'Video',
        effects: 'Motion Effects',
        catalogEmpty: 'Video templates are not configured yet',
        effectsEmpty: 'Kling effects are not configured yet',
        uploadTitle: 'Upload image',
        uploadHint: 'PNG, JPG or paste from clipboard',
        create: 'Generate',
        imageRequired: 'Upload an image for this video template',
        ratioRequired: 'Choose a video format',
        templateVideoRequired: 'Upload preview.mp4 for this video template first',
      },
    };
    return (dict[lang] && dict[lang][key]) || dict.ru[key] || key;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: defaultVideoTemplateItems
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function defaultVideoTemplateItems() {
    const base = [
      ['Сброс сумки', 'Предметы динамично высыпаются из сумки на городской переход, камера следует за движением, реалистичный рекламный стиль.'],
      ['Ангел в дороге', 'Персонаж с большими белыми крыльями стоит на пустой дороге, ветер развевает одежду, кинематографичный пролет камеры.'],
      ['Полет супергероя', 'Персонаж взлетает над городом, камера стремительно летит рядом, одежда и волосы двигаются от скорости.'],
      ['Баннер Skyline', 'Персонаж позирует на высотной конструкции среди небоскребов, камера облетает вокруг, ощущение дорогой fashion-рекламы.'],
      ['Праздничный момент', 'Конфетти и вспышки света заполняют сцену, персонаж празднует победу, камера делает плавный dolly-in.'],
      ['Офисный хаос', 'Стильный офис превращается в хаотичную кино-сцену с бумагами, светом и дымом, персонаж остается в центре кадра.'],
      ['Реакция толпы', 'Толпа вокруг персонажа эмоционально реагирует, камера быстро меняет планы, живой репортажный стиль.'],
      ['Прогулка знаменитости', 'Персонаж идет через аэропорт или вокзал как знаменитость, камеры, вспышки, охрана и динамичная съемка.'],
      ['Подъем кубка', 'Персонаж поднимает трофей под золотым дождем конфетти, спортивная арена, мощный cinematic slow motion.'],
      ['Момент трансформации', 'Окружение вокруг персонажа меняется из обычного в футуристическое, частицы света собирают новый мир.'],
      ['Неоновый портрет', 'Ночной город, неоновые отражения на лице, камера плавно вращается вокруг персонажа, атмосферный cyber look.'],
      ['Космический проход', 'Персонаж идет по поверхности планеты, вокруг галактики и светящиеся частицы, камера следует одним проходом.'],
      ['Дождь и свет', 'Кинематографичный дождь, контровой свет, капли на объективе, персонаж медленно смотрит в камеру.'],
      ['Магазин будущего', 'Обычный магазин превращается в футуристический шоурум, продукты и объекты всплывают в воздухе.'],
      ['Пустынный ветер', 'Персонаж стоит в пустыне, ткань и волосы развеваются ветром, камера делает широкий эпичный пролет.'],
      ['Красная дорожка', 'Персонаж проходит по красной дорожке, вспышки камер, толпа, роскошный вечерний свет.'],
      ['Голограммы вокруг', 'Вокруг персонажа появляются интерактивные голограммы, камера скользит между ними, high-tech реклама.'],
      ['Музей оживает', 'Картины и скульптуры оживают вокруг персонажа, камера движется через зал как в одном дубле.'],
      ['Городской спорт', 'Персонаж делает динамичное движение на улице, камера low-angle, энергия спортивной рекламы.'],
      ['Ледяной мир', 'Окружение замерзает и покрывается кристаллами льда, персонаж остается теплым центром кадра.'],
      ['Огненный фон', 'Позади персонажа вспыхивают контролируемые кинематографичные огни, драматичный контраст и slow motion.'],
      ['Зеркальная комната', 'Персонаж внутри комнаты зеркал, отражения умножаются, камера плавно вращается.'],
      ['Взрыв красок', 'Цветной порошок и краска взрываются вокруг персонажа, high-speed рекламный кадр.'],
      ['Подводная сцена', 'Персонаж словно находится под водой, ткань медленно движется, лучи света проходят сверху.'],
      ['Ретро кино', 'Сцена превращается в винтажный кинематографичный кадр с мягким зерном и теплым светом.'],
      ['Роботы вокруг', 'Дружелюбные роботы и дроны появляются вокруг персонажа, футуристический свет и движение камеры.'],
      ['Золотой зал', 'Окружение превращается в роскошный золотой зал, камера делает плавный dolly-out.'],
      ['Портал за спиной', 'За персонажем открывается светящийся портал, ветер и частицы притягиваются внутрь.'],
      ['Уличная мода', 'Персонаж идет по модной улице, камера следует сбоку, быстрые cuts и fashion-commercial стиль.'],
      ['Молния в небе', 'Небо драматично вспыхивает молниями, персонаж стоит уверенно, камера медленно приближается.'],
      ['Микромир', 'Предметы вокруг становятся гигантскими, персонаж проходит через сюрреалистичный масштабный мир.'],
      ['Воздушные шары', 'Сотни воздушных шаров поднимаются вокруг персонажа, мягкий радостный рекламный стиль.'],
      ['Снежный город', 'Город покрывается снегом, теплый свет витрин, персонаж идет через мягкую метель.'],
      ['Танец света', 'Луч света повторяет движение персонажа, сцена становится музыкальной и ритмичной.'],
      ['Пиксельный взрыв', 'Окружение распадается на пиксели и собирается заново, динамичная digital-трансформация.'],
      ['Летающие объекты', 'Предметы из изображения плавно поднимаются в воздух вокруг персонажа, камера проходит сквозь них.'],
      ['Киносъемка', 'Вокруг персонажа появляется съемочная площадка, свет, камеры, хлопушка, ощущение backstage.'],
      ['Витрина бренда', 'Персонаж или объект становится центральным героем premium product showcase, камера делает clean orbit.'],
      ['Ночной мост', 'Персонаж идет по мосту ночью, городские огни отражаются на мокрой поверхности.'],
      ['Финальный логотип', 'В конце сцены частицы собираются в яркий светящийся логотип или символ, premium reveal.'],
      ['Вихрь ткани', 'Ткань, шарфы или элементы одежды закручиваются вокруг персонажа, элегантный fashion motion.'],
      ['Солнечный flare', 'Теплый солнечный flare проходит через объектив, персонаж медленно поворачивается к камере.'],
      ['Драматичный лифт', 'Двери лифта открываются в другой мир, персонаж выходит, камера отъезжает назад.'],
      ['Бумажный шторм', 'Листы бумаги кружатся вокруг, офис или улица превращается в динамичную рекламную сцену.'],
      ['Арена будущего', 'Персонаж появляется на футуристической арене с огромными экранами и световыми кольцами.'],
      ['Волна энергии', 'От персонажа расходится световая волна, меняющая окружение и подсветку сцены.'],
      ['Драгоценный блеск', 'Сцена заполняется бликами кристаллов и ювелирным светом, камера макро-проходом раскрывает детали.'],
      ['Город сверху', 'Камера поднимается от персонажа вверх, раскрывая масштабный город и движение улиц.'],
      ['Побег из кадра', 'Персонаж выходит из плоского фото в живую 3D-сцену, эффект оживления изображения.'],
      ['Сюрреалистичный сон', 'Окружение превращается в мягкий dreamlike мир, предметы парят, камера движется плавно и медленно.'],
      ['Concert Arena', 'Персонаж появляется на огромном LED-экране на заполненной концертной арене, яркий сценический свет, толпа и масштабная кинематографичная камера.'],
      ['Y2K Glitch', 'Ретро fashion-портрет трансформируется с RGB glitch-эффектами, VHS-искажениями и эстетикой Y2K.'],
      ['3D Wireframe', 'Персонаж постепенно превращается в светящийся неоновый 3D wireframe scan с цифровой визуализацией тела.'],
      ['Urban Timelapse', 'Персонаж остается главным героем динамичного городского таймлапса с потоками света, машин и ускоренным движением города.'],
      ['Hollywood Haute Couture', 'Кинематографичная fashion-трансформация персонажа происходит внутри сюрреалистичного пространства с отражениями и премиальным светом.'],
      ['Fire Magic Ritual', 'Персонаж управляет огнем во время мистического ритуала в древнем каменном дворе ночью, вокруг искры и пламя.'],
      ['Tiny World in a Bottle', 'Персонаж оказывается внутри фантастического миниатюрного мира в стеклянной бутылке с магической атмосферой и маленькими деталями окружения.'],
      ['Giant Delivery', 'Персонаж обычного размера с трудом тащит огромный чемодан по городской улице, масштаб предмета подчёркнут кинематографичной камерой.'],
      ['Fantasy Jungle', 'Персонаж путешествует через густые фантастические джунгли в золотом вечернем свете, вокруг тропические растения и атмосферный туман.'],
      ['Mountain Adventure', 'Персонаж идет через живописные альпийские горы, зеленые долины, драматичное небо и масштабные природные пейзажи.'],
      ['Open Road Ride', 'Персонаж едет по живописной открытой дороге, динамичная tracking camera сопровождает движение в премиальном автомобильном стиле.'],
      ['Pedestal Up', 'Камера плавно поднимается снизу вверх, постепенно раскрывая персонажа и масштаб окружающего пространства.'],
      ['Punch Effect', 'Персонаж получает внезапный удар и естественно реагирует на него, динамичное движение тела и реалистичная реакция.'],
      ['Glass Reflection', 'Персонаж окружен крупными стеклянными отражающими поверхностями, которые создают многослойные отражения при плавном движении камеры.'],
      ['Neon Portal', 'Позади персонажа открывается яркий неоновый портал, свет и частицы окружают героя, камера медленно приближается.'],
      ['Luxury Elevator Reveal', 'Двери роскошного лифта открываются, персонаж выходит в эффектное футуристическое пространство, камера плавно движется назад.'],
      ['Rainy Fashion Walk', 'Персонаж уверенно идет под дождем по ночной улице, отражения неона на мокром асфальте создают premium fashion look.'],
      ['Floating City', 'Персонаж стоит на высокой платформе среди огромного фантастического города, здания и острова парят в воздухе.'],
      ['Golden Particle Reveal', 'Золотые частицы окружают персонажа и постепенно формируют эффектное сияющее пространство вокруг него.'],
      ['Cinematic Final Shot', 'Камера медленно отдаляется от персонажа, раскрывая масштабную сцену и создавая мощный финальный кинематографичный кадр.'],
    ];
    return base.map((entry, index) => ({
      slot: String(index + 1).padStart(2, '0'),
      id: 'builtin_video_template_' + (index + 1),
      title: entry[0],
      description: entry[1],
      prompt: entry[1],
      preview_video: '/webapp/assets/video-templates/' + String(index + 1).padStart(2, '0') + '/preview.mp4',
      poster_url: '/webapp/assets/video-templates/' + String(index + 1).padStart(2, '0') + '/poster.jpg',
      aspect_ratio: index % 3 === 0 ? '9:16' : (index % 3 === 1 ? '16:9' : '1:1'),
      ratios: ['16:9', '1:1', '9:16'],
      models: ['kling_o3_omni'],
      preferred_model: 'kling_o3_omni',
      duration: 5,
      resolution: '720p',
      cost_credits: 95,
      generation_cost: '95 ⚡',
    }));
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeVideoTemplateIntro
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeVideoTemplateIntro() {
    const el = document.getElementById('videoTemplateIntro');
    if (el) el.remove();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: maybeShowVideoTemplateIntro
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
function maybeShowVideoTemplateIntro(force) {
  return;
}

  // =====================================================
  // JAVASCRIPT-БЛОК: loadVideoTemplates
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function loadVideoTemplates() {
    if (Array.isArray(videoTemplatesCache)) return videoTemplatesCache;
    try {
      const res = await fetch('/api/public/prostudio/video-templates', { cache: 'default' });
      // =====================================================
      // JAVASCRIPT-БЛОК: data
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const data = await res.json().catch(() => ({}));
      videoTemplatesCache = normalizeVideoTemplateList(data.templates);
    } catch {
      videoTemplatesCache = normalizeVideoTemplateList([]);
    }
    return videoTemplatesCache;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: loadKlingEffects
  // Загружает библиотеку Kling Video Effects из backend JSON, чтобы Mini App не держал список эффектов в коде.
  // =====================================================
  async function loadKlingEffects() {
    if (Array.isArray(klingEffectsCache)) return klingEffectsCache;
    try {
      const res = await fetch('/api/public/prostudio/kling/effects', { cache: 'default' });
      const data = await res.json().catch(() => ({}));
      klingEffectsCache = normalizeVideoTemplateList((data.effects || []).map((effect) => Object.assign({}, effect, {
        catalog_type: 'kling_effect',
        is_kling_effect: true,
        id: effect.id || effect.effect_scene,
        title: effect.title || effect.name || effect.id || effect.effect_scene,
        prompt: effect.description || effect.title || effect.name || effect.id || '',
        effect_scene: effect.effect_scene || effect.id,
        preferred_model: 'kling_effects',
        models: ['kling_effects'],
      })), false);
    } catch {
      klingEffectsCache = [];
    }
    return klingEffectsCache;
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeVideoTemplateModal
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeVideoTemplateModal() {
    activeVideoTemplate = null;
    videoTemplateUploadUrl = '';
    const modal = document.getElementById('videoTemplateModal');
    if (modal) modal.remove();
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeVideoTemplatesCatalog
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeVideoTemplatesCatalog() {
    closeVideoTemplateModal();
    const overlay = document.getElementById('videoTemplatesOverlay');
    if (overlay) overlay.remove();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: videoTemplateCostLabel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function videoTemplateCostLabel(template) {
    const credits = Number(template && (template.cost_credits || template.cost) || 0);
    if (credits > 0) return '⚡ ' + credits;
    const label = template && template.generation_cost;
    return label ? String(label) : '';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: templatePreferredModel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function templatePreferredModel(template) {
    const models = Array.isArray(template && template.models) ? template.models : [];
    const preferred = String((template && template.preferred_model) || '').trim();
    if (preferred === 'kling_o3_omni') return preferred;
    const found = models.find((model) => String(model || '').trim() === 'kling_o3_omni');
    return found || 'kling_o3_omni';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: videoTemplateRatios
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function videoTemplateRatios(template) {
    const ratios = Array.isArray(template && template.ratios) ? template.ratios : [];
    // =====================================================
    // JAVASCRIPT-БЛОК: clean
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const clean = ratios.filter((ratio) => ['16:9', '1:1', '9:16'].includes(String(ratio)));
    return clean.length ? clean : ['16:9', '1:1', '9:16'];
  }

  function videoTemplateRatioLabel(ratio) {
    const value = String(ratio || '16:9');
    if (value === '9:16') return 'Вертикальный';
    if (value === '1:1') return 'Квадрат';
    return 'Широкий';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: videoTemplateReferenceVideo
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function videoTemplateReferenceVideo(template) {
    if (!template) return '';
    return String(template.reference_video || template.video_url || template.template_video_url || template.preview_video || '').trim();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: normalizeVideoTemplateList
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function normalizeVideoTemplateList(items, includeDefaults = true) {
    const incoming = Array.isArray(items) ? items : [];
    const defaults = includeDefaults ? defaultVideoTemplateItems() : [];
    const byId = new Map();
    defaults.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const id = String(item.id || '').trim();
      if (!id) return;
      const credits = Number(item.cost_credits || item.cost || 0) || 95;
      byId.set(id, Object.assign({}, item, {
        prompt: item.prompt || item.video_prompt || item.description || item.title || '',
        ratios: videoTemplateRatios(item),
        cost_credits: credits,
        generation_cost: item.generation_cost || (credits + ' ⚡'),
      }));
    });
    incoming.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const id = String(item.id || '').trim();
      if (!id) return;
      const existing = byId.get(id) || {};
      const merged = Object.assign({}, existing, item);
      const credits = Number(merged.cost_credits || merged.cost || 0) || 95;
      byId.set(id, Object.assign({}, merged, {
        prompt: merged.prompt || merged.video_prompt || merged.description || merged.title || '',
        ratios: videoTemplateRatios(merged),
        cost_credits: credits,
        generation_cost: merged.generation_cost || (credits + ' ⚡'),
      }));
    });
    return Array.from(byId.values()).slice(0, 100);
  }

  function hydrateVideoTemplateCardVideos(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const videos = Array.from(scope.querySelectorAll('video[data-template-src]'));
    if (!videos.length) return;
    const loadVideo = (video) => {
      if (!video || video.dataset.loaded === '1') return;
      const src = video.dataset.templateSrc || '';
      if (!src) return;
      video.dataset.loaded = '1';
      video.src = src;
      video.load();
      const playPromise = video.play();
      if (playPromise && typeof playPromise.catch === 'function') playPromise.catch(() => {});
    };
    if (!('IntersectionObserver' in window)) {
      videos.slice(0, 8).forEach(loadVideo);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        loadVideo(entry.target);
        observer.unobserve(entry.target);
      });
    }, { root: scope.querySelector('.video-templates-panel') || null, rootMargin: '220px 0px', threshold: 0.01 });
    videos.forEach((video) => observer.observe(video));
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoTemplatesCatalog
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  async function openVideoTemplatesCatalog(catalogType = 'templates') {
    closeVideoTemplateIntro();
    const isEffects = catalogType === 'effects';
    const templates = isEffects ? await loadKlingEffects() : await loadVideoTemplates();
    closeVideoTemplatesCatalog();
    const overlay = document.createElement('div');
    overlay.id = 'videoTemplatesOverlay';
    overlay.className = 'video-templates-overlay ' + (isEffects ? 'kling-effects-overlay' : '');
    overlay.innerHTML = '<div class="video-templates-panel">'
      + '<button class="video-templates-close" type="button" aria-label="Close">×</button>'
      + '<div class="video-templates-heading">' + S.escapeHtml(videoTemplateText(isEffects ? 'effects' : 'video')) + '</div>'
      + '<div class="video-templates-grid">'
      + (templates.length ? templates.map((template, index) => {
      const id = S.escapeHtml(template.id || String(index));
      const encodedId = encodeURIComponent(String(template.id || index));
      const title = S.escapeHtml(template.title || template.id || 'Video');
      const src = S.escapeHtml(videoTemplateReferenceVideo(template));
      const poster = S.escapeHtml(template.poster_url || '');
      const ratio = String(template.aspect_ratio || '').trim();
      const ratioClass = ratio === '16:9' ? 'wide' : (ratio === '1:1' ? 'square' : 'tall');
      return '<button class="video-template-card ' + ratioClass + '" type="button" data-template-id="' + id + '" onclick="SYLVEX.openVideoTemplateFromCatalog(event,\'' + encodedId + '\')">'
        + '<span class="video-template-card-poster"><span>▶</span></span>'
        + (src ? '<video data-template-src="' + src + '"' + (poster ? ' poster="' + poster + '"' : '') + ' loop muted playsinline preload="none" onerror="this.style.display=\'none\'"></video>' : '')
        + '<span class="video-template-card-shade"></span>'
        + '<span class="video-template-card-title">' + title + '</span>'
        + '</button>';
      }).join('') : '<div class="video-templates-empty">' + S.escapeHtml(videoTemplateText(isEffects ? 'effectsEmpty' : 'catalogEmpty')) + '</div>')
      + '</div></div>';
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) closeVideoTemplatesCatalog();
    });
    const closeBtn = overlay.querySelector('.video-templates-close');
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    if (closeBtn) closeBtn.addEventListener('click', closeVideoTemplatesCatalog);
    document.body.appendChild(overlay);
    hydrateVideoTemplateCardVideos(overlay);
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openKlingEffectsCatalog
  // Открывает каталог Kling Video Effects из кнопки «Управление движением».
  // =====================================================
  async function openKlingEffectsCatalog(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    genAction('video', 'motion');
    await openVideoTemplatesCatalog('effects');
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoTemplateFromCatalog
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openVideoTemplateFromCatalog(event, id) {
    if (event) event.stopPropagation();
    try { id = decodeURIComponent(String(id || '')); } catch {}
    const templates = (Array.isArray(klingEffectsCache) ? klingEffectsCache : []).concat(Array.isArray(videoTemplatesCache) ? videoTemplatesCache : []);
    // =====================================================
    // JAVASCRIPT-БЛОК: template
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const template = templates.find((item) => String(item.id) === String(id));
    if (template) openVideoTemplateModal(template);
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderVideoTemplateUpload
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderVideoTemplateUpload() {
    const upload = document.getElementById('videoTemplateUpload');
    if (!upload) return;
    if (videoTemplateUploadUrl) {
      upload.classList.add('has-file');
      upload.innerHTML = '<img src="' + S.escapeHtml(videoTemplateUploadUrl) + '" alt="" /><span>' + S.escapeHtml(videoTemplateText('uploadTitle')) + '</span>';
    } else {
      upload.classList.remove('has-file');
      upload.innerHTML = '<span class="video-template-upload-icon">▧</span><b>' + S.escapeHtml(videoTemplateText('uploadTitle')) + '</b><small>' + S.escapeHtml(videoTemplateText('uploadHint')) + '</small>';
    }
  }

  // =====================================================
  // ЗАГРУЗКА В MINI APP: setVideoTemplateFile
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  function setVideoTemplateFile(file) {
    if (!file || !/^image\//.test(file.type || '')) return;
    const reader = new FileReader();
    reader.onload = () => {
      videoTemplateUploadUrl = String(reader.result || '');
      renderVideoTemplateUpload();
    };
    reader.readAsDataURL(file);
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openVideoTemplateModal
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openVideoTemplateModal(template) {
    activeVideoTemplate = template;
    videoTemplateUploadUrl = '';
    const ratios = videoTemplateRatios(template);
    videoTemplateRatio = ratios.includes(template.aspect_ratio) ? template.aspect_ratio : ratios[0];
    closeVideoTemplateModal();
    activeVideoTemplate = template;
    const modal = document.createElement('div');
    modal.id = 'videoTemplateModal';
    modal.className = 'video-template-modal-backdrop';
    const cost = videoTemplateCostLabel(template);
    const previewHtml =
      '<div class="video-template-preview-fallback"><span>▶</span><b>' + S.escapeHtml(template.title || 'Видео') + '</b></div>'
      + (template.preview_video
        ? '<video class="video-template-preview-video" src="' + S.escapeHtml(template.preview_video || '') + '"'
          + (template.poster_url ? ' poster="' + S.escapeHtml(template.poster_url || '') + '"' : '')
          + ' autoplay loop muted playsinline preload="auto" webkit-playsinline x5-playsinline'
          + ' oncanplay="this.play().catch(()=>{})"'
          + ' onloadeddata="this.play().catch(()=>{})"'
          + ' onerror="this.style.display=\'none\'">'
          + '</video>'
        : '');
    modal.innerHTML = '<div class="video-template-modal">'
      + '<button class="video-template-modal-close" type="button" aria-label="Close">×</button>'
      + '<div class="video-template-preview">' + previewHtml + '</div>'
      + '<div class="video-template-details">'
      + '<h3>' + S.escapeHtml(template.title || 'Video') + '</h3>'
      + '<p>' + S.escapeHtml(template.description || '') + '</p>'
      + '<button id="videoTemplateUpload" class="video-template-upload" type="button"></button>'
      + '<div class="video-template-ratios">' + ratios.map((ratio) => '<button type="button" data-ratio="' + S.escapeHtml(ratio) + '" class="' + (ratio === videoTemplateRatio ? 'active' : '') + '"><span class="video-template-ratio-icon" data-ratio="' + S.escapeHtml(ratio) + '"></span><span><b>' + S.escapeHtml(ratio) + '</b><small>' + S.escapeHtml(videoTemplateRatioLabel(ratio)) + '</small></span></button>').join('') + '</div>'
      + '<button id="videoTemplateGenerate" class="video-template-generate" type="button">' + S.escapeHtml(videoTemplateText('create')) + (cost ? ' ' + S.escapeHtml(cost) : '') + '</button>'
      + '</div>'
      + '<input id="videoTemplateFileInput" type="file" accept="image/png,image/jpeg,image/jpg" hidden />'
      + '</div>';
    modal.addEventListener('click', (event) => {
      if (event.target === modal) closeVideoTemplateModal();
    });
    document.body.appendChild(modal);
    const closeBtn = modal.querySelector('.video-template-modal-close');
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    if (closeBtn) closeBtn.addEventListener('click', closeVideoTemplateModal);
    const upload = modal.querySelector('#videoTemplateUpload');
    const fileInput = modal.querySelector('#videoTemplateFileInput');
    if (upload && fileInput) {
      upload.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', () => setVideoTemplateFile(fileInput.files && fileInput.files[0]));
    }
    modal.querySelectorAll('[data-ratio]').forEach((btn) => {
      btn.addEventListener('click', () => {
        videoTemplateRatio = btn.dataset.ratio || videoTemplateRatio;
        modal.querySelectorAll('[data-ratio]').forEach((item) => item.classList.toggle('active', item === btn));
      });
    });
    const generate = modal.querySelector('#videoTemplateGenerate');
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    if (generate) generate.addEventListener('click', startVideoTemplateGeneration);
    renderVideoTemplateUpload();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: startVideoTemplateGeneration
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function startVideoTemplateGeneration() {
    const template = activeVideoTemplate;
    if (!template) return;
    if (!videoTemplateUploadUrl) {
      toast(videoTemplateText('imageRequired'));
      return;
    }
    if (!videoTemplateRatio) {
      toast(videoTemplateText('ratioRequired'));
      return;
    }
    const isKlingEffect = !!template.is_kling_effect || template.catalog_type === 'kling_effect';
    const referenceVideo = videoTemplateReferenceVideo(template);
    const modelId = isKlingEffect ? 'kling_effects' : templatePreferredModel(template);
    const uploadedImage = videoTemplateUploadUrl;
    const selectedRatio = videoTemplateRatio;
    const previousStudioMode = studioMode;
    const previousActiveCat = activeCat;
    const previousVideoState = Object.assign({}, videoState, {
      referenceImageUrls: (videoState.referenceImageUrls || []).slice(),
      uploadedImageUrls: (videoState.uploadedImageUrls || []).slice(),
      referenceImageBuckets: JSON.parse(JSON.stringify(videoState.referenceImageBuckets || { generate: [], edit: [], motion: [] })),
      advanced: Object.assign({}, videoState.advanced || {}),
    });
    closeVideoTemplateModal();
    closeVideoTemplatesCatalog();
    studioMode = 'video';
    activeCat = 'video';
    videoState.modelId = modelId;
    videoState.provider = 'kling';
    videoState.section = isKlingEffect ? 'motion' : 'edit';
    videoState.generationMode = isKlingEffect ? 'video_effects' : 'video_edit';
    videoState.mode = videoState.generationMode;
    videoState.ratio = selectedRatio;
    videoState.duration = Number(template.duration || 5);
    videoState.resolution = template.resolution || '720p';
    videoState.sound = false;
    videoState.startImage = uploadedImage;
    videoState.editInputVideo = isKlingEffect ? '' : referenceVideo;
    videoState.editVideoUrl = videoState.editInputVideo;
    videoState.inputVideo = videoState.editInputVideo;
    videoState.videoUrl = videoState.editInputVideo;
    videoState.referenceVideoUrl = '';
    // KEEP: working Kling editor catalog flow.
    // Internal template video + user image + template prompt go directly to Kling O3/Omni edit.
    videoState.videoTemplate = {
      id: template.id || '',
      title: template.title || '',
      description: template.description || '',
      prompt: template.prompt || template.video_prompt || template.description || template.title || '',
      preview_video: template.preview_video || '',
      reference_video: referenceVideo,
      aspect_ratio: selectedRatio,
      catalog_type: isKlingEffect ? 'kling_effect' : 'video_template',
      effect_scene: isKlingEffect ? (template.effect_scene || template.id || '') : '',
      input_count: template.input_count || 1,
      character_orientation: 'image',
      mode: isKlingEffect ? (template.mode || 'std') : '',
      model_name: isKlingEffect ? (template.model_name || 'kling-v1-6') : '',
    };
    normalizeVideoStateForModel();

    const promptLabel = template.title || 'Video template';
    const basePrompt = template.prompt || template.video_prompt || template.description || template.title || '';
    const promptText = isKlingEffect
      ? basePrompt
      : [
          basePrompt,
          'Use the uploaded image as the appearance reference. Use the catalog video as the motion reference. Generate the result with the same motion from the video and the character or object appearance from the image.',
        ].filter(Boolean).join('\n\n');
    chatMessages.push({
      role: 'user',
      text: promptLabel,
      referenceImages: [uploadedImage],
      referenceVideos: referenceVideo ? [referenceVideo] : null,
    });
    const loadingIndex = chatMessages.push({
      generationLoading: true,
      role: 'ai',
      progress: createGenerationProgress('video'),
    }) - 1;
    renderChat();
    rememberCurrentChatSpace();
    document.body.classList.add('ai-generating');

    const videoOptions = videoOptionsPayload([]);
    try {
      const start = await callGenerate(promptText, null, [], videoOptions, {
        onProgress: (completed) => updateGenerationLoadingProgress(loadingIndex, completed),
        loadingIndex,
      });
      const result = start.result || start;
      chatMessages.splice(loadingIndex, 1, {
        role: 'ai',
        imageResultMini: true,
        metadata: generationResultMetadata('video', promptLabel, result, [uploadedImage], videoOptions),
      });
      loadConversations();
    } catch (err) {
      if (loadingIndex >= 0) {
        chatMessages[loadingIndex] = buildInsufficientBalanceMessage(err, promptLabel, null, [uploadedImage], null, videoOptions, []);
        if (!(err && err.paywall)) {
          chatMessages[loadingIndex] = {
            role: 'ai',
            text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.'),
          };
        }
      }
      toast(translateGenerationError(err, 'Генерация не прошла'));
    } finally {
      document.body.classList.remove('ai-generating');
      videoState = previousVideoState;
      studioMode = previousStudioMode;
      activeCat = previousActiveCat;
      renderChat();
      rememberCurrentChatSpace();
      if (!activeGeneration.jobId || !isActiveGenerationStatus(activeGeneration.status)) {
        clearActiveProStudioJob(activeGeneration.jobId);
      }
    }
  }

  document.addEventListener('paste', (event) => {
    if (!document.getElementById('videoTemplateModal')) return;
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item && item.type && item.type.indexOf('image/') === 0) {
        const file = item.getAsFile();
        if (file) {
          event.preventDefault();
          setVideoTemplateFile(file);
          break;
        }
      }
    }
  });

  // =====================================================
  // JAVASCRIPT-БЛОК: updateComposerMode
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyVoiceWorkspaceMode() {
    const composer = document.getElementById('studioComposer');
    if (composer) composer.dataset.voiceWorkspace = voiceWorkspaceMode;
    document.querySelectorAll('[data-voice-workspace-tab]').forEach((button) => {
      button.classList.toggle('active', button.dataset.voiceWorkspaceTab === voiceWorkspaceMode);
    });
  }

  function setVoiceWorkspaceMode(event, mode) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const previousWorkspaceMode = voiceWorkspaceMode;
    voiceWorkspaceMode = mode === 'dialogue' ? 'dialogue' : 'voiceover';
    if (voiceWorkspaceMode === 'dialogue') {
      if (!isElevenLabsVoiceModel(voiceState.modelId)) voiceState.modelId = 'elevenlabs_eleven_v3';
      voiceState.elevenlabsTool = 'dialogue';
      voiceState.speakerMode = 'multi';
      voiceState.numSpeakers = Math.max(2, Number(voiceState.numSpeakers || 2));
      if (previousWorkspaceMode !== 'dialogue') {
        voiceState.speakerVoices = ['', '', '', '', '', '', ''];
        voiceState.activeSpeakerIndex = null;
      }
    } else {
      VoiceDialogueComposer.closeMenus();
      voiceState.elevenlabsTool = 'text_to_speech';
      voiceState.speakerMode = 'single';
      voiceState.numSpeakers = 1;
      voiceState.activeSpeakerIndex = null;
      closeVoiceAddon();
    }
    if (studioMode !== 'voice') updateComposerMode('voice');
    else {
      applyVoiceWorkspaceMode();
      renderVoiceControls();
      renderModelPop();
      updateSendButton();
    }
    resetVoiceToolGuideTimer();
  }

  function updateComposerMode(kind) {
    const requestedMode = chatTypeForMode(kind);
    if (activeGenerationLocked() && !activeGeneration.restoringMode && activeGeneration.mode && requestedMode !== activeGeneration.mode) {
      toast(activeGenerationButtonLabel(activeGeneration.status));
      return;
    }
    if (!restoringChatSpace) rememberCurrentChatSpace();
    const isVideoSection = kind === 'video' || kind === 'edit' || kind === 'motion';
    studioMode = isVideoSection ? 'video' : kind;
    activeCat = studioMode;
    try { localStorage.setItem(lastModeStorageKey(), currentChatType()); } catch {}
    if (isVideoSection) {
      videoState.section = kind === 'edit' ? 'edit' : (kind === 'motion' ? 'motion' : 'generate');
      if (videoState.section === 'edit') {
        videoState.generationMode = 'video_edit';
        videoState.mode = 'video_edit';
        videoUploadTarget = 'input_video';
      } else if (videoState.section === 'motion') {
        videoState.generationMode = 'motion_control';
        videoState.mode = 'motion_control';
        videoUploadTarget = 'character';
      } else {
        videoUploadTarget = 'reference';
      }
      normalizeVideoStateForModel();
    }
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const isImage = studioMode === 'image';
    const isText = studioMode === 'text';
    const isMusic = isMusicMode();
    const isVoice = isVoiceMode();
    if (!isVoice || voiceWorkspaceMode !== 'dialogue') VoiceDialogueComposer.closeMenus();
    const isAudio = isMusic || isVoice;
    pendingAttachment = currentModeAttachment();
    const composer = document.getElementById('studioComposer');
    if (composer) {
      composer.dataset.composerMode =
        isImage ? 'image' :
        isText ? 'text' :
        isVoice ? 'voice' :
        isMusic ? 'music' :
        'video';
    }
    // Show only controls for the active generation mode.
    const modeClasses = ['image-only', 'video-only', 'music-only', 'voice-only', 'text-only'];

    modeClasses.forEach(cls => {
      document.querySelectorAll('.' + cls).forEach(el => {
        el.hidden = true;
        el.style.display = 'none';
        el.setAttribute('aria-hidden', 'true');
      });
    });

    const activeClass =
      isImage ? 'image-only' :
      isText ? 'text-only' :
      isVoice ? 'voice-only' :
      isMusic ? 'music-only' :
      'video-only';

    document.querySelectorAll('.' + activeClass).forEach(el => {
      el.hidden = false;
      el.style.display = '';
      el.setAttribute('aria-hidden', 'false');
    });
    document.querySelectorAll('[data-studio-mode-btn]').forEach((btn) => {
      const modeBtn = btn.dataset.studioModeBtn;
      const isActive = isVideoSection
        ? modeBtn === (videoState.section === 'generate' ? 'video' : videoState.section)
        : modeBtn === kind;
      btn.classList.toggle('active', isActive);
    });
    applyVoiceWorkspaceMode();
    document.querySelectorAll('.studio-mini-tab').forEach((btn) => btn.classList.remove('active'));
    const miniIndex =
      kind === 'image' ? 0 :
      kind === 'video' ? 1 :
      isMusic ? 2 :
      isVoice ? 3 :
      isText ? 4 :
      1;
    const minis = document.querySelectorAll('.studio-mini-tab');
    if (minis[miniIndex]) minis[miniIndex].classList.add('active');
    const ta = document.getElementById('chatInput');
    if (ta) {
      PromptPlaceholderManager.setMode(
        isImage ? 'image' :
        isText ? 'text' :
        isVoice ? 'voice' :
        isMusic ? 'music' :
        'video'
      );
    }
    const mvc = document.getElementById('modelValComposer');
    if (isImage) {
      if (!imageState.modelId && IMAGE_MODEL_LIST.length) imageState.modelId = IMAGE_MODEL_LIST[0].id;
      renderImageControls();
      renderUploadedPhotoGrid();
      updateImageUploadButtonPreview();
      renderModelPop();
    } else if (isText) {
      renderTextControls();
      renderModelPop();
      renderUploadedPhotoGrid();
      updateImageUploadButtonPreview();
    } else if (mvc) {
      if (isAudio) {
        if (isMusic) {
          renderMusicControls();
        } else {
          renderVoiceControls();
        }
        renderModelPop();
        renderUploadedPhotoGrid();
        updateImageUploadButtonPreview();
      } else {
        renderVideoControls();
        renderModelPop();
        renderUploadedPhotoGrid();
        updateImageUploadButtonPreview();
      }
    }
    renderVoiceSpeakerComposer();
    resetVoiceToolGuideTimer();
    if (!restoringChatSpace) restoreChatSpace(currentChatType());
    applyCurrentDraft();
    updateSendButton();
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: genAction
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function genAction(kind, tabKey) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    if (kind === 'voice' && !tabKey) {
      setVoiceWorkspaceMode(null, 'voiceover');
      toast('Generate Voiceover');
      return;
    }
    updateComposerMode(tabKey || kind);
    const labels = { image:'Generate Image', video:'Generate Video', music:'Generate Music', voice:'Generate Voiceover' };
    toast(labels[kind] || kind);
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleHistory
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function toggleHistory(e) {
    if (e) e.stopPropagation();
    const d = document.getElementById('histDrawer');
    const b = document.getElementById('histBackdrop');
    if (!d || !b) return;
    const on = !d.classList.contains('show');
    if (on) { renderHistoryUserSummary(); renderConvList(); }
    d.classList.toggle('show', on);
    b.classList.toggle('show', on);
    if (!on && activeGenerationLocked()) {
      activeGeneration.historyPreview = false;
      activeGeneration.restoringMode = true;
      if (activeGeneration.mode && currentChatType() !== activeGeneration.mode) updateComposerMode(activeGeneration.mode);
      else restoreChatSpace(activeGeneration.mode || currentChatType());
      activeGeneration.restoringMode = false;
      ensureActiveGenerationPlaceholder(true);
    }
  }
  function renderHistoryUserSummary() {
    const user = S.user || {};
    const name = (user.display_name && String(user.display_name).trim())
      || [user.first_name, user.last_name].filter(Boolean).join(' ')
      || user.username || 'Пользователь';
    const handle = user.username ? '@' + user.username : 'SYLVEX ID ' + (user.telegram_id || '—');
    const balance = Number(user.balance || 0);
    const nameEl = document.getElementById('hdUserName'); if (nameEl) nameEl.textContent = name;
    const handleEl = document.getElementById('hdUserHandle'); if (handleEl) handleEl.textContent = handle;
    const balanceEl = document.getElementById('hdUserBalance'); if (balanceEl) balanceEl.textContent = balance.toLocaleString() + ' ⚡️';
    const avatar = document.getElementById('hdUserAvatar');
    if (avatar) {
      avatar.replaceChildren();
      const avatarUrl = user.custom_avatar_url || user.photo_url;
      if (avatarUrl) {
        const img = document.createElement('img'); img.src = avatarUrl; img.alt = ''; avatar.appendChild(img);
      } else {
        avatar.textContent = ((user.first_name || user.username || '·').slice(0,1) + (user.last_name || '').slice(0,1)).toUpperCase();
      }
    }
    let spent = '';
    for (let i = chatMessages.length - 1; i >= 0 && !spent; i -= 1) {
      const meta = chatMessages[i] && chatMessages[i].metadata;
      if (!meta || typeof meta !== 'object') continue;
      if (meta.cost_credits !== undefined && meta.cost_credits !== null && meta.cost_credits !== '') spent = String(meta.cost_credits) + ' ⚡️';
      else if (meta.generation_cost) spent = String(meta.generation_cost);
    }
    if (!spent && user.last_generation_cost_credits !== undefined) spent = String(user.last_generation_cost_credits) + ' ⚡️';
    const spentEl = document.getElementById('hdUserLastSpent'); if (spentEl) spentEl.textContent = spent || '—';
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: autoGrow
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }

// =====================================================
// ЗАПУСК ГЕНЕРАЦИИ: callGenerate
// Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
// =====================================================
async function callGenerate(prompt, attachment, referenceImagesOverride, videoOptionsOverride, generationOptions) {
  if (!activeGenerationLocked()) {
    transitionActiveGeneration('begin', {
      mode: currentChatType(),
      model: pickStudioModel(),
      startedAt: Date.now(),
    });
  }
  if (activeGenerationPlaceholderIndex() < 0) {
    const requestedLoadingIndex = Number(generationOptions && generationOptions.loadingIndex);
    if (Number.isInteger(requestedLoadingIndex) && requestedLoadingIndex >= 0) {
      adoptActiveGenerationPlaceholder(requestedLoadingIndex);
    } else {
      for (let index = chatMessages.length - 1; index >= 0; index -= 1) {
        if (chatMessages[index] && chatMessages[index].generationLoading) {
          adoptActiveGenerationPlaceholder(index);
          break;
        }
      }
    }
    ensureActiveGenerationPlaceholder(false);
  }
  let promptText = (prompt || '').trim();
  if (isVoiceMode() && voiceState.pronunciationRules && typeof voiceState.pronunciationRules === 'object') {
    Object.entries(voiceState.pronunciationRules).forEach(([word, spoken]) => {
      if (!word || !spoken) return;
      promptText = promptText.split(word).join(spoken);
    });
  }
  const imageReferenceImages = isImageMode() && Array.isArray(referenceImagesOverride)
    ? referenceImagesOverride.slice()
    : (isImageMode() ? (imageState.referenceImageUrls || []).slice() : []);
  const videoReferenceImages = isVideoMode()
    ? (Array.isArray(referenceImagesOverride) ? referenceImagesOverride.slice() : currentVideoReferenceImages())
    : [];

  const history = chatMessages
    .filter((m) => !m.typing && m.text && (m.role === 'user' || m.role === 'ai'))
    .slice(-10)
    .map((m) => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.text }));

  const imageOptions = isImageMode()
    ? imageOptionsPayload(imageReferenceImages)
    : null;
  const videoOptions = isVideoMode()
    ? (videoOptionsOverride || videoOptionsPayload(videoReferenceImages))
    : null;
  const musicOptions = isMusicMode() ? musicOptionsPayload() : null;
  const textOptions = studioMode === 'text' ? textOptionsPayload() : null;
  const audioUploadsOverride = generationOptions && Array.isArray(generationOptions.audioUploads)
    ? generationOptions.audioUploads.slice()
    : null;
  const voiceOptionsBase = generationOptions && generationOptions.voiceOptions
    ? Object.assign({}, generationOptions.voiceOptions)
    : (isVoiceMode() ? voiceOptionsPayload() : null);
  const voiceOptions = isVoiceMode()
    ? Object.assign(voiceOptionsBase || {}, {
        uploads: (audioUploadsOverride || (voiceState.uploads || []).slice()).map((item) => {
          if (!item || typeof item !== 'object') return item;
          const clean = Object.assign({}, item);
          delete clean.previewUrl;
          return clean;
        }),
        attachment: (voiceState.attachment || voiceOptionsBase?.attachment) ? (() => {
          const clean = Object.assign({}, voiceState.attachment || voiceOptionsBase.attachment);
          delete clean.previewUrl;
          return clean;
        })() : null,
      })
    : null;

  const payload = {
    telegram_id: getTelegramId(),
    prompt: promptText,
    mode: studioMode,
    category: studioMode,
    model: pickStudioModel(),
    provider: isVideoMode() ? currentVideoProvider() : pickProviderHint(),
    image_options: imageOptions,
    video_options: videoOptions,
    music_options: musicOptions,
    voice_options: voiceOptions,
    text_options: textOptions,
    history,
    attachment: attachment || null,
    conversation_id: currentConvId,
    client_request_id: 'req_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10),
    language: uiLang(),
  };

  console.log('PRO STUDIO FRONTEND PAYLOAD:', {
    mode: payload.mode,
    category: payload.category,
    model: payload.model,
    provider: payload.provider,
    image_options: payload.image_options,
    video_options: payload.video_options,
    music_options: payload.music_options,
    voice_options: payload.voice_options,
    text_options: payload.text_options,
  });

  const generateRequest = () => fetch('/api/public/prostudio/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
      },
      cache: 'no-store',
      body: JSON.stringify(payload),
    });
  let res;
  try {
    res = await generateRequest();
  } catch (err) {
    if (studioMode === 'text' && isNetworkLoadError(err)) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      res = await generateRequest();
    } else {
      throw err;
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: j
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  const j = await res.json().catch(() => ({}));
  if (res.status === 409 && j && j.active_job_id) {
    // The backend is authoritative here: the active job may belong to a
    // different mode than the locally attempted request.
    clearActiveProStudioJob();
    await restoreActiveProStudioJob();
    if (!activeGenerationLocked()) {
      transitionActiveGeneration('job', { id: j.active_job_id, status: j.status || 'queued', mode: studioMode });
      ensureActiveGenerationPlaceholder(true);
      watchGenerationJob(j.active_job_id, { id: j.active_job_id, status: j.status || 'queued', mode: studioMode });
    }
    const err = new Error('Дождитесь завершения текущей генерации.');
    err.activeGeneration = true;
    err.activeJobId = j.active_job_id;
    throw err;
  }
  if (res.status === 402 && j && j.paywall) {
    const err = new Error(j.error || 'Недостаточно токенов');
    err.paywall = true;
    err.insufficientBalance = !!j.insufficient_balance;
    err.requiredCredits = j.required_credits || 0;
    err.balance = j.balance || 0;
    err.shopUrl = j.shop_url || '';
    throw err;
  }
  if (!res.ok || !j.ok) throw new Error(translateGenerationError(j, 'Генерация не прошла. Попробуйте повторить немного позже.'));
  if (j.conversation_id) {
    currentConvId = j.conversation_id;
    rememberCurrentChatSpace();
  }
  if (j.job_id) {
    transitionActiveGeneration('job', { id: j.job_id, status: j.status || 'queued', mode: activeGeneration.mode || studioMode });
    j.result = await waitGeneration(j.job_id, generationOptions || {});
  }

  return j;
}

// =====================================================
// JAVASCRIPT-БЛОК: errorMessage
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function errorMessage(value, fallback) {
  const fallbackText = fallback || 'Генерация не прошла';
  if (value === null || value === undefined || value === '') return fallbackText;
  if (typeof value === 'string') return value;
  if (value instanceof Error) return value.message || fallbackText;
  if (typeof value === 'object') {
    const direct = value.error || value.message || value.detail || value.details || value.body_preview || value.status;
    if (direct && direct !== value) return errorMessage(direct, fallbackText);
    try {
      return JSON.stringify(value);
    } catch {
      return fallbackText;
    }
  }
  return String(value);
}

function isNetworkLoadError(value) {
  const text = errorMessage(value, '');
  return /load failed|failed to fetch|networkerror|network request failed|the internet connection appears to be offline/i.test(String(text || ''));
}

// =====================================================
// JAVASCRIPT-БЛОК: translateGenerationError
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function translateGenerationError(value, fallback) {
  const text = errorMessage(value, fallback || 'Во время генерации произошла временная ошибка сервиса. Попробуйте повторить попытку немного позже.');
  const low = String(text || '').toLowerCase();
  if (isNetworkLoadError(text)) {
    return 'Связь с Mini App временно оборвалась. Повторите запрос ещё раз.';
  }
  if (/prompt.*size.*between.*0.*3072|prompt.*3072|size must be between/.test(low)) {
    return 'Описание слишком длинное для выбранной модели.\nМаксимальная длина текста для Kling — 3072 символа.\nСократите описание и попробуйте снова.';
  }
  if (/api key|unauthorized|401|forbidden|invalid api key/.test(low)) {
    return 'Сервис генерации временно недоступен.\nМы уже получили информацию об ошибке. Попробуйте немного позже.';
  }
  if (/unknown parameter|unsupported parameter|invalid parameter|unrecognized.*parameter|candidate_count|badrequest|bad request/.test(low)) {
    return 'Выбранные параметры не поддерживаются этой моделью.\nИзмените настройки генерации и попробуйте снова.';
  }
  if (/duration.*not supported|unsupported.*duration|video too long|duration.*limit/.test(low)) {
    return 'Длительность видео превышает допустимый лимит для выбранной модели.';
  }
  if (/resolution.*not supported|unsupported.*resolution|size.*not supported/.test(low)) {
    return 'Выбранное разрешение временно недоступно для этой модели. Измените настройки и попробуйте снова.';
  }
  if (/image too large|file too large|payload too large|413/.test(low)) {
    return 'Размер изображения превышает допустимый лимит.\nУменьшите размер файла и повторите попытку.';
  }
  if (/invalid image|image.*invalid|cannot process.*image|bad image|unsupported image/.test(low)) {
    return 'Не удалось обработать загруженное изображение.\nПопробуйте выбрать другое изображение.';
  }
  if (/billing hard limit|billing limit|insufficient[_ ]quota|quota|credit.*exceed|limit.*exceed|limit has been reached/.test(low)) {
    return 'Временный лимит генераций исчерпан.\nПовторите попытку позже.';
  }
  if (/rate limit|too many requests|429|overloaded|busy/.test(low)) {
    return 'Сервис сейчас перегружен большим количеством запросов.\nПовторите попытку через несколько минут.';
  }
  if (/timeout|timed out|readtimeout/.test(low)) {
    return 'Генерация заняла слишком много времени.\nПопробуйте выполнить запрос ещё раз.';
  }
  if (/sensitive|safety|policy|blocked|moderation/.test(low)) {
    return 'Запрос не может быть обработан из-за ограничений выбранной AI-модели.\nПопробуйте изменить изображение или описание.';
  }
  if (/provider returned invalid response|invalid response|non-json|json|decode|html|empty response/.test(low)) {
    return 'Сервис временно вернул некорректный ответ.\nПопробуйте повторить генерацию через несколько секунд.';
  }
  if (/http\s*503|status_code.*503|\b503\b|service unavailable|temporarily unavailable/.test(low)) {
    return 'Сервис сейчас временно недоступен.\nПовторите попытку немного позже.';
  }
  if (/http\s*500|status_code.*500|\b500\b|internal server error|bad gateway|\b502\b|\b504\b/.test(low)) {
    return 'Во время генерации произошла временная ошибка сервиса.\nПопробуйте немного позже.';
  }
  if (/http 4|400/.test(low)) {
    return 'Выбранные параметры не поддерживаются этой моделью.\nИзмените настройки генерации и попробуйте снова.';
  }
  return /traceback|exception|provider|request|json|http/i.test(text)
    ? (fallback || 'Во время генерации произошла временная ошибка сервиса. Попробуйте повторить попытку немного позже.')
    : text;
}

// =====================================================
// JAVASCRIPT-БЛОК: buildInsufficientBalanceMessage
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function buildInsufficientBalanceMessage(err, prompt, attachment, referenceImages, imageOptionsSnapshot, videoOptionsSnapshot, audioUploads) {
  const required = Number((err && err.requiredCredits) || 0);
  const balance = Number((err && err.balance) || 0);
  return {
    role: 'ai',
    insufficientBalance: true,
    prompt: prompt || '',
    requiredCredits: required,
    balance,
    generationCost: required ? required + ' ⚡️' : '',
    resume: {
      mode: currentChatType(),
      videoSection: videoState.section || 'generate',
      prompt: prompt || '',
      attachment: attachment || null,
      referenceImages: (referenceImages || []).slice(),
      imageOptions: imageOptionsSnapshot ? Object.assign({}, imageOptionsSnapshot) : null,
      videoOptions: videoOptionsSnapshot ? Object.assign({}, videoOptionsSnapshot) : null,
      audioUploads: (audioUploads || []).slice(),
    },
    created_at: new Date().toISOString(),
  };
}

// =====================================================
// JAVASCRIPT-БЛОК: estimateFrontendGenerationCredits
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function estimateFrontendGenerationCredits(imageOptionsSnapshot) {
  const known = !!(S.user && S.user.balance !== undefined && S.user.balance !== null);
  const balance = Number((S.user && S.user.balance) || 0);
  let required = 1;
  if (isImageMode()) {
    const modelId = (imageOptionsSnapshot && (imageOptionsSnapshot.modelId || imageOptionsSnapshot.model)) || imageState.modelId || '';
    // =====================================================
    // JAVASCRIPT-БЛОК: model
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const model = IMAGE_MODEL_LIST.find((item) => item.id === modelId) || {};
    const unit = Number(model.costCredits || 0);
    const count = Number((imageOptionsSnapshot && imageOptionsSnapshot.count) || imageState.count || 1);
    required = unit > 0 ? unit * Math.max(1, count || 1) : 1;
  }
  return { balance, required, known };
}

// =====================================================
// JAVASCRIPT-БЛОК: updateGenerationLoadingProgress
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
function updateGenerationLoadingProgress(index, completed) {
  if (index === undefined || index === null || index < 0) return;
  const message = chatMessages[index];
  if (!message || (!message.generationLoading && !message.imageLoading)) return;
  message.generationLoading = true;
  message.imageLoading = false;
  message.progress = nextGenerationProgress(message.progress, !!completed);
  renderChat();
  rememberCurrentChatSpace();
}

// =====================================================
// JAVASCRIPT-БЛОК: waitGeneration
// Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
// =====================================================
async function waitGeneration(jobId, options) {
  const onProgress = options && typeof options.onProgress === 'function' ? options.onProgress : null;
  let transientErrors = 0;
  const startedAt = Date.now();
  const networkGraceMs = 15 * 60 * 1000;
  let lastStatus = '';
  while (true) {
    let res;
    try {
      res = await fetch(
        `/api/public/prostudio/job/${jobId}`,
        { cache: 'no-store' }
      );
    } catch (err) {
      transientErrors += 1;
      if (Date.now() - startedAt > networkGraceMs && transientErrors > 80) throw err;
      await new Promise(resolve => setTimeout(resolve, Math.min(8000, 1500 + transientErrors * 250)));
      continue;
    }

    // =====================================================
    // ОЖИДАНИЕ JOB: job
    // Опрашивает backend до финального статуса и обновляет карточку генерации в чате.
    // =====================================================
    const job = await res.json().catch(() => ({}));
    if (!res.ok || !job.ok) {
      transientErrors += 1;
      if (Date.now() - startedAt > networkGraceMs && transientErrors > 80) throw new Error(translateGenerationError(job, 'Не удалось проверить статус генерации. Попробуйте позже.'));
      await new Promise(resolve => setTimeout(resolve, Math.min(8000, 1500 + transientErrors * 250)));
      continue;
    }
    transientErrors = 0;

    if (isActiveGenerationStatus(job.status)) {
      transitionActiveGeneration('status', {
        id: job.job_id || job.generation_id || jobId,
        status: job.status,
        mode: job.mode || '',
        conversation_id: job.conversation_id || '',
      });
      if (job.status !== lastStatus) {
        lastStatus = job.status;
        patchActiveGenerationDom();
      }
    }

    if (job.status === 'completed') {
      transitionActiveGeneration('status', {
        id: job.job_id || job.generation_id || jobId,
        status: 'completed',
        mode: job.mode || '',
      });
      const result = job.result || {};
      result.job_id = result.job_id || job.job_id || jobId;
      result.generation_id = result.generation_id || job.generation_id || jobId;
      result.conversation_id = result.conversation_id || job.conversation_id || '';
      return result;
    }

    if (job.status === 'failed' || job.status === 'cancelled') {
      transitionActiveGeneration('status', {
        id: job.job_id || job.generation_id || jobId,
        status: job.status,
        mode: job.mode || '',
      });
      const error = job.error || {};
      const terminalError = new Error(translateGenerationError(error, 'Генерация не прошла. Попробуйте повторить немного позже.'));
      terminalError.terminalStatus = job.status;
      terminalError.jobId = jobId;
      throw terminalError;
    }

    if (!isActiveGenerationStatus(job.status)) {
      throw new Error('Генерация не завершилась. Попробуйте повторить немного позже.');
    }

    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openShopForGeneration
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openShopForGeneration(e, index) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    switchView('shop');
    const message = chatMessages[index];
    if (message) message.shopOpenedAt = new Date().toISOString();
    rememberCurrentChatSpace();
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: resumePendingGeneration
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function resumePendingGeneration(e, index) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const message = chatMessages[index];
    if (!message || !message.insufficientBalance) return;
    const snapshot = message.resume || {};
    const prompt = snapshot.prompt || message.prompt || '';
    const attachment = snapshot.attachment || null;
    const referenceImages = Array.isArray(snapshot.referenceImages) ? snapshot.referenceImages.slice() : [];
    const videoOptions = snapshot.videoOptions || null;
    const mode = snapshot.mode || currentChatType();
    const videoSection = snapshot.videoSection === 'edit' || snapshot.videoSection === 'motion'
      ? snapshot.videoSection
      : 'video';
    updateComposerMode(mode === 'video' ? videoSection : mode);
    chatMessages[index] = {
      role: 'ai',
      generationLoading: true,
      progress: createGenerationProgress(generationKindForCurrentMode()),
    };
    renderChat();
    rememberCurrentChatSpace();
    document.body.classList.add('ai-generating');
    try {
      const start = await callGenerate(prompt, attachment, referenceImages, videoOptions, {
        onProgress: (completed) => updateGenerationLoadingProgress(index, completed),
        loadingIndex: index,
      });
      const j = start.result || start;
      if (mode === 'image') {
        const images = generatedUrlsFromResponse(j, 'image');
        const thumbs = generatedThumbsFromResponse(j);
        if (images.length) addGeneratedImages(images, thumbs);
        chatMessages[index] = {
          role: 'ai',
          imageResultMini: true,
          metadata: imageGenerationMetadata(prompt, referenceImages, j, snapshot.imageOptions || null),
        };
      } else {
        const resultType = mode === 'video' ? 'video' : (mode === 'music' ? 'music' : (mode === 'voice' ? 'voice' : 'file'));
        chatMessages[index] = {
          role: 'ai',
          imageResultMini: true,
          metadata: generationResultMetadata(resultType, prompt, j, referenceImages, resultType === 'video' ? videoOptions : null),
        };
      }
      loadConversations();
    } catch (err) {
      chatMessages[index] = buildInsufficientBalanceMessage(err, prompt, attachment, referenceImages, snapshot.imageOptions || null, videoOptions, snapshot.audioUploads || []);
      if (!(err && err.paywall)) {
        chatMessages[index] = {
          role: 'ai',
          text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.'),
        };
      }
    } finally {
      document.body.classList.remove('ai-generating');
      renderChat();
      rememberCurrentChatSpace();
      if (!activeGeneration.jobId || !isActiveGenerationStatus(activeGeneration.status)) {
        clearActiveProStudioJob(activeGeneration.jobId);
      }
    }
  }

   // =====================================================
   // ЗАПУСК ГЕНЕРАЦИИ: sendChat
   // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
   // =====================================================
   async function sendChat() {
    if (activeGenerationLocked()) {
      toast(activeGenerationButtonLabel(activeGeneration.status));
      return;
    }
    transitionActiveGeneration('begin', {
      mode: currentChatType(),
      model: pickStudioModel(),
      startedAt: Date.now(),
    });
    const ta = document.getElementById('chatInput');
    const v = (ta.value || '').trim();
    if (studioMode === 'text' && textState.attachment && textState.attachment.uploading) {
      toast('Файл ещё загружается');
      clearActiveProStudioJob();
      return;
    }
    const attachment = currentModeAttachment();
    const referenceImages = isVideoMode()
      ? currentVideoReferenceImages()
      : (isImageMode() ? (imageState.referenceImageUrls || []).slice() : []);
    const audioUploads = (isMusicMode() || isVoiceMode()) ? (currentAudioState().uploads || []).slice() : [];
    if (isVoiceMode() && voiceWorkspaceMode === 'dialogue') {
      const speakerCount = Math.max(2, Number(voiceState.numSpeakers || 2));
      const missingSpeaker = Array.from({ length:speakerCount }, (_, index) => voiceSpeakerVoiceValue(index)).some((voiceId) => !voiceId);
      if (missingSpeaker) {
        toast('Выберите голос для каждого диктора');
        clearActiveProStudioJob();
        return;
      }
    }
    const voiceOptionsSnapshot = isVoiceMode() ? voiceOptionsPayload() : null;
    const imageOptionsSnapshot = isImageMode()
      ? imageOptionsPayload(referenceImages)
      : null;
    const videoOptionsSnapshot = isVideoMode() ? videoOptionsPayload(referenceImages) : null;
    const referenceVideos = isVideoMode() && videoOptionsSnapshot
      ? Array.from(new Set([
          videoOptionsSnapshot.input_video || videoOptionsSnapshot.video_url || '',
          videoOptionsSnapshot.reference_video || '',
        ].filter(Boolean)))
      : [];

    if (!v && !attachment && !referenceImages.length && !referenceVideos.length && !audioUploads.length) {
      clearActiveProStudioJob();
      return;
    }

    const balanceCheck = estimateFrontendGenerationCredits(imageOptionsSnapshot);
    if (balanceCheck.known && balanceCheck.balance < balanceCheck.required) {
      chatMessages.push(buildInsufficientBalanceMessage(
        {
          paywall: true,
          insufficientBalance: true,
          requiredCredits: balanceCheck.required,
          balance: balanceCheck.balance,
        },
        v,
        attachment,
        referenceImages,
        imageOptionsSnapshot,
        videoOptionsSnapshot,
        audioUploads
      ));
      ta.value = '';
      autoGrow(ta);
      updateSendButton();
      saveCurrentDraftSoon();
      renderChat();
      rememberCurrentChatSpace();
      toast('Недостаточно токенов');
      clearActiveProStudioJob();
      return;
    }

    dismissGenerationInputUi();

    const photoMode = isImageMode();
    const musicMode = isMusicMode();
    let loadingIndex = -1;
    const uploadOnlyVoice = isVoiceMode() && !v && audioUploads.length && !attachment && !referenceImages.length;
    if (photoMode) {
      loadingIndex = ensureActiveGenerationPlaceholder(false);
    } else if (!uploadOnlyVoice) {
      chatMessages.push({
        role: 'user',
        text: v,
        attachment: attachment ? Object.assign({}, attachment) : null,
        attachmentName: null,
        referenceImages: referenceImages.length ? referenceImages : null,
        referenceVideos: referenceVideos.length ? referenceVideos : null,
      });
      loadingIndex = ensureActiveGenerationPlaceholder(false);
    }
    ta.value = ''; autoGrow(ta); updateSendButton();
    saveCurrentDraftSoon();
    clearAttachment();
    if (isImageMode()) {
      imageState.referenceImageUrl = '';
      imageState.referenceImageUrls = [];
      imageState.uploadedImageUrls = [];
      imageState.attachment = null;
    } else if (isVideoMode()) {
      videoState.characterImage = '';
      videoState.referenceImageUrls = [];
      if (videoState.section !== 'edit') {
        videoState.inputVideo = '';
        videoState.videoUrl = '';
        videoState.editInputVideo = '';
        videoState.editVideoUrl = '';
        videoState.referenceVideoUrl = '';
      }
    } else if (isMusicMode() || isVoiceMode()) {
      currentAudioState().uploads = [];
      if (isVoiceMode()) {
        currentAudioState().uploading = null;
        revokeVoiceUploadPreview();
        currentAudioState().attachment = null;
        if (voiceWorkspaceMode === 'dialogue') {
          voiceState.speakerVoices = ['', '', '', '', '', '', ''];
          voiceState.activeSpeakerIndex = null;
          renderVoiceControls();
        }
      }
    }
    renderComposerImageDraft();
    renderUploadedPhotoGrid();
    updateImageUploadButtonPreview();
    if (isVoiceMode()) renderVoiceToolPanel();
    if (loadingIndex < 0) loadingIndex = ensureActiveGenerationPlaceholder(false);
    renderChat();
    rememberCurrentChatSpace();
    document.body.classList.add('ai-generating');
    S.haptic.impact('light');
    let unlockAfterRender = false;
    try {
      const start = await callGenerate(
        v,
        attachment,
        referenceImages,
        videoOptionsSnapshot,
        {
          onProgress: (completed) => updateGenerationLoadingProgress(loadingIndex, completed),
          loadingIndex,
          audioUploads,
          voiceOptions: voiceOptionsSnapshot,
        }
      );
      renderChat();
      if (!activeGeneration.historyPreview) rememberCurrentChatSpace();

      const j = start.result || start;
      if (activeGeneration.historyPreview) {
        activeGeneration.historyPreview = false;
        restoreChatSpace(activeGeneration.mode || currentChatType());
      }
      const stableLoadingIndex = activeGenerationPlaceholderIndex();
      if (stableLoadingIndex >= 0) loadingIndex = stableLoadingIndex;

      if (photoMode) {
        const images = generatedUrlsFromResponse(j, 'image');
        const thumbs = generatedThumbsFromResponse(j);

        if (images.length) addGeneratedImages(images, thumbs);

        chatMessages[loadingIndex] = {
          role: 'ai',
          imageResultMini: true,
          metadata: imageGenerationMetadata(
            v,
            referenceImages,
            j,
            imageOptionsSnapshot
          ),
        };
      } else {
        chatMessages.splice(loadingIndex, 1);

        const backendResultType = String((j && j.type) || '').toLowerCase();
        const resultType = backendResultType === 'video' || (j && (j.video_url || (Array.isArray(j.videos) && j.videos.length)))
          ? 'video'
          : (isVideoMode()
              ? 'video'
              : (isMusicMode()
                  ? 'music'
                  : (isVoiceMode() ? 'voice' : 'file')));

        const resultUrls = generatedUrlsFromResponse(
          j,
          resultType === 'video' ? 'video' : 'audio'
        );

        if (resultType !== 'file' && resultUrls.length) {
          chatMessages.push({
            role: 'ai',
            imageResultMini: true,
            metadata: generationResultMetadata(
              resultType,
              v,
              j,
              referenceImages,
              resultType === 'video' ? videoOptionsSnapshot : null
            ),
          });
        } else if (studioMode === 'text' && j && j.text) {
          chatMessages.push({
            role: 'ai',
            text: j.text,
            files: Array.isArray(j.files) ? j.files : (j.file_url ? [j.file_url] : []),
          });
        } else {
          chatMessages.push({
            role: 'ai',
            text: j.sent_to_telegram
              ? 'Готово ✅\nРезультат отправлен в Telegram-чат.'
              : 'Готово ✅\nГенерация завершена.'
          });
        }
      }
      if (musicMode) resetMusicGenerationOptions();
      loadConversations(); // refresh sidebar order
      rememberCurrentChatSpace();
      unlockAfterRender = true;
    } catch (err) {
      if (err && err.activeGeneration) {
        renderChat();
        rememberCurrentChatSpace();
        return;
      }
      if (err && err.paywall) {
        if (loadingIndex >= 0) {
          chatMessages[loadingIndex] = buildInsufficientBalanceMessage(
            err,
            v,
            attachment,
            referenceImages,
            imageOptionsSnapshot,
            videoOptionsSnapshot,
            audioUploads
          );
        }
        renderChat();
        rememberCurrentChatSpace();
        toast('Недостаточно токенов');
        if (!activeGeneration.jobId) clearActiveProStudioJob();
        return;
      }
      if (activeGeneration.historyPreview) {
        activeGeneration.historyPreview = false;
        restoreChatSpace(activeGeneration.mode || currentChatType());
      }
      loadingIndex = activeGenerationPlaceholderIndex() >= 0 ? activeGenerationPlaceholderIndex() : loadingIndex;
      if (loadingIndex >= 0) chatMessages.splice(loadingIndex, 1);
      chatMessages.push({
        role: 'ai',
        text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.')
      });
      rememberCurrentChatSpace();
      if (err && err.terminalStatus) unlockAfterRender = true;
      else if (!activeGeneration.jobId) {
        ta.value = v;
        autoGrow(ta);
        setCurrentModeAttachment(attachment);
        if (photoMode) {
          imageState.referenceImageUrls = referenceImages.slice();
          imageState.referenceImageUrl = referenceImages[0] || '';
          imageState.uploadedImageUrls = referenceImages.slice();
        } else if (isVideoMode()) {
          videoState.referenceImageUrls = referenceImages.slice();
          if (videoOptionsSnapshot) {
            videoState.inputVideo = videoOptionsSnapshot.input_video || videoOptionsSnapshot.video_url || '';
            videoState.videoUrl = videoState.inputVideo;
            videoState.editInputVideo = videoOptionsSnapshot.input_video || '';
            videoState.editVideoUrl = videoState.editInputVideo;
            videoState.referenceVideoUrl = videoOptionsSnapshot.reference_video || '';
          }
        } else if (isMusicMode() || isVoiceMode()) {
          currentAudioState().uploads = audioUploads.slice();
        }
        renderComposerImageDraft();
        renderUploadedPhotoGrid();
        updateImageUploadButtonPreview();
        if (isVoiceMode()) renderVoiceToolPanel();
        clearActiveProStudioJob();
      }
    } finally {
      document.body.classList.remove('ai-generating');
    }
    renderChat();
    rememberCurrentChatSpace();
    if (unlockAfterRender) clearActiveProStudioJob(activeGeneration.jobId);
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: copyMsg
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function copyMsg(i) {
    const m = chatMessages[i]; if (!m) return;
    if (navigator.clipboard) navigator.clipboard.writeText(m.text || '');
    toast(t('copied'));
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: regenMsg
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function regenMsg(i) {
  const prev = chatMessages[i - 1];
  if (!prev || prev.role !== 'user') return;

  chatMessages[i] = {
    generationLoading: true,
    role: 'ai',
    progress: createGenerationProgress(generationKindForCurrentMode()),
  };
  renderChat();

  callGenerate(prev.text, null, prev.referenceImages || [], null, {
    onProgress: (completed) => updateGenerationLoadingProgress(i, completed),
    loadingIndex: i,
  })
    .then(async (start) => {
      const j = start.result || start;

      const resultType = isVideoMode()
        ? 'video'
        : (isMusicMode()
            ? 'music'
            : (isVoiceMode() ? 'voice' : 'image'));

      chatMessages[i] = {
        role: 'ai',
        imageResultMini: true,
        metadata: generationResultMetadata(
          resultType,
          prev.text,
          j,
          prev.referenceImages || [],
          null
        ),
      };

      rememberCurrentChatSpace();
      renderChat();
      clearActiveProStudioJob(activeGeneration.jobId);
    })
    .catch((err) => {
      chatMessages[i] = {
        role: 'ai',
        text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.')
      };

      rememberCurrentChatSpace();
      renderChat();
      if (!activeGeneration.jobId || (err && err.terminalStatus)) clearActiveProStudioJob(activeGeneration.jobId);
    });
}

  // =====================================================
  // БЛОК ОЗВУЧКИ: toggleVoiceCloneRecording
  // Записывает голос пользователя для создания собственного ElevenLabs-голоса.
  // Запись не отправляется сразу: сначала её можно прослушать внутри Mini App.
  // =====================================================
  async function toggleVoiceCloneRecording(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (voiceCloneCountdownTimer) return;
    if (voiceCloneRecorder && voiceCloneRecorder.state === 'recording') {
      voiceCloneRecorder.stop();
      return;
    }
    voiceCloneCountdown = 3;
    renderVoiceToolPanel();
    voiceCloneCountdownTimer = setInterval(() => {
      voiceCloneCountdown -= 1;
      if (voiceCloneCountdown > 0) {
        renderVoiceToolPanel();
        return;
      }
      clearInterval(voiceCloneCountdownTimer);
      voiceCloneCountdownTimer = null;
      voiceCloneCountdown = 0;
      startVoiceCloneRecording();
    }, 700);
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: startVoiceCloneRecording
  // Запускает реальную запись после визуального обратного отсчёта.
  // =====================================================
  async function startVoiceCloneRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast('Микрофон не поддерживается');
      renderVoiceToolPanel();
      return;
    }
    try {
      voiceCloneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      toast('Нет доступа к микрофону');
      renderVoiceToolPanel();
      return;
    }
    const mime = ['audio/webm', 'audio/mp4'].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
    try {
      voiceCloneRecorder = mime ? new MediaRecorder(voiceCloneStream, { mimeType: mime }) : new MediaRecorder(voiceCloneStream);
    } catch {
      voiceCloneRecorder = new MediaRecorder(voiceCloneStream);
    }
    voiceCloneChunks = [];
    voiceCloneRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) voiceCloneChunks.push(ev.data);
    };
    voiceCloneRecorder.onstop = () => {
      try { voiceCloneStream && voiceCloneStream.getTracks().forEach((track) => track.stop()); } catch {}
      if (voiceCloneRecordTimer) {
        clearInterval(voiceCloneRecordTimer);
        voiceCloneRecordTimer = null;
      }
      const blob = new Blob(voiceCloneChunks, { type: voiceCloneRecorder.mimeType || 'audio/webm' });
      if (voiceClonePreviewUrl) URL.revokeObjectURL(voiceClonePreviewUrl);
      voiceCloneBlob = blob.size >= 800 ? blob : null;
      voiceCloneDraft.source = voiceCloneBlob ? 'record' : '';
      voiceClonePreviewUrl = voiceCloneBlob ? URL.createObjectURL(voiceCloneBlob) : '';
      setupVoiceClonePreviewAudio();
      if (!voiceCloneBlob) toast('Запись слишком короткая');
      renderVoiceToolPanel();
    };
    voiceCloneRecorder.start();
    voiceCloneRecordStartedAt = Date.now();
    voiceCloneRecordElapsed = 0;
    voiceCloneRecordTimer = setInterval(() => {
      voiceCloneRecordElapsed = Math.floor((Date.now() - voiceCloneRecordStartedAt) / 1000);
      renderVoiceToolPanel();
    }, 1000);
    renderVoiceToolPanel();
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: playVoiceCloneRecording
  // Воспроизводит локальную запись голоса перед отправкой на создание собственного голоса.
  // =====================================================
  function playVoiceCloneRecording(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!voiceClonePreviewUrl) return;
    if (!voiceClonePreviewAudio) setupVoiceClonePreviewAudio();
    if (!voiceClonePreviewAudio) return;
    applyVoiceClonePreviewSettings();
    if (!voiceClonePreviewAudio.paused) {
      voiceClonePreviewAudio.pause();
      voiceClonePreviewPlaying = false;
      renderVoiceToolPanel();
      return;
    }
    voiceClonePreviewAudio.play()
      .then(() => {
        voiceClonePreviewPlaying = true;
        renderVoiceToolPanel();
      })
      .catch(() => toast('Не удалось воспроизвести запись'));
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: clearVoiceCloneRecording
  // Удаляет локальную запись голоса и очищает preview, не затрагивая остальные файлы озвучки.
  // =====================================================
  function clearVoiceCloneRecording(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (voiceCloneCountdownTimer) {
      clearInterval(voiceCloneCountdownTimer);
      voiceCloneCountdownTimer = null;
    }
    if (voiceCloneRecordTimer) {
      clearInterval(voiceCloneRecordTimer);
      voiceCloneRecordTimer = null;
    }
    if (voiceClonePreviewAudio) {
      try { voiceClonePreviewAudio.pause(); } catch {}
      voiceClonePreviewAudio = null;
    }
    if (voiceClonePreviewUrl) URL.revokeObjectURL(voiceClonePreviewUrl);
    voiceCloneBlob = null;
    voiceClonePreviewUrl = '';
    voiceCloneChunks = [];
    voiceCloneDraft.source = '';
    voiceCloneCountdown = 0;
    voiceCloneRecordElapsed = 0;
    voiceClonePreviewPlaying = false;
    voiceClonePreviewTime = 0;
    voiceClonePreviewDuration = 0;
    renderVoiceToolPanel();
  }

  // =====================================================
  // БЛОК ОЗВУЧКИ: sendVoiceCloneRecording
  // Отправляет записанный голос на backend, backend создаёт голос в ElevenLabs и возвращает voice_id.
  // Новый голос сразу выбирается в Pro Studio и появляется в списке голосов после обновления.
  // =====================================================
  async function sendVoiceCloneRecording(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (!voiceCloneBlob) {
      toast('Сначала запишите голос');
      return;
    }
    if (voiceCloneSubmitting) return;
    const nameInput = document.getElementById('voiceCloneNameInput');
    if (nameInput) voiceCloneDraft.name = String(nameInput.value || '').trim();
    const voiceName = (voiceCloneDraft.name || '').trim();
    if (!voiceName) {
      toast('Введите название голоса');
      updateVoiceCloneSubmitState();
      return;
    }
    applyVoiceClonePreviewSettings();
    const fd = new FormData();
    const ext = (voiceCloneBlob.type || '').includes('mp4') ? 'mp4' : 'webm';
    fd.append('file', voiceCloneBlob, 'sylvex-voice.' + ext);
    fd.append('name', voiceName);
    fd.append('telegram_id', String(getTelegramId() || ''));
    fd.append('description', 'Created in SYLVEX Mini App');
    fd.append('gender', voiceCloneDraft.gender || 'neutral');
    fd.append('emotion', voiceCloneDraft.emotion || 'neutral');
    fd.append('avatar_url', voiceCloneDraft.avatarUrl || '');
    fd.append('settings', JSON.stringify({
      gender: voiceCloneDraft.gender || 'neutral',
      emotion: voiceCloneDraft.emotion || 'neutral',
      speed: Number(voiceCloneDraft.speed ?? 50),
      pitch: Number(voiceCloneDraft.pitch ?? 50),
      intonation: Number(voiceCloneDraft.intonation ?? 50),
      expressiveness: Number(voiceCloneDraft.expressiveness ?? 50),
    }));
    voiceCloneSubmitting = true;
    renderVoiceToolPanel();
    try {
      const res = await fetch('/api/public/prostudio/elevenlabs/voice-clone', {
        method: 'POST',
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok || !data.voice_id) {
        throw new Error(translateGenerationError(data, 'Не удалось создать голос. Попробуйте ещё раз.'));
      }
      if (!isElevenLabsVoiceModel(voiceState.modelId)) {
        voiceState.modelId = 'elevenlabs_multilingual_v2';
      }
      const voiceResource = {
        id: 'custom_voice_' + data.voice_id,
        voice_id: data.voice_id,
        name: data.name || voiceName,
        gender: voiceCloneDraft.gender || 'neutral',
        description: 'Created in SYLVEX Mini App',
        avatarUrl: voiceCloneDraft.avatarUrl || '',
        avatar_url: voiceCloneDraft.avatarUrl || '',
        previewUrl: voiceCloneDraft.avatarUrl || '',
        provider: 'elevenlabs',
        model: 'elevenlabs_voice_clone',
        type: 'custom',
        status: 'ready',
        created_at: new Date().toISOString(),
      };
      const savedVoice = await saveVisualItemToBackend('voice', voiceResource);
      serverVisualItems.voices = (serverVisualItems.voices || []).filter((item) => (item.voice_id || item.voiceId || item.id) !== data.voice_id);
      serverVisualItems.voices.unshift(Object.assign({}, voiceResource, savedVoice || {}));
      voiceState.elevenlabsVoice = data.voice_id;
      voiceState.elevenlabsSecondVoice = data.voice_id;
      elevenlabsVoiceListLoaded = false;
      await loadElevenLabsVoices(true).catch(() => {});
      voiceCloneDraft.avatarUrl = '';
      clearVoiceCloneRecording();
      renderVoiceControls();
      toast('Голос создан и выбран');
    } catch (err) {
      toast(translateGenerationError(err, 'Не удалось создать голос. Попробуйте ещё раз.'));
    } finally {
      voiceCloneSubmitting = false;
      renderVoiceToolPanel();
    }
  }

  /* ===== Voice (mic) recording → Whisper ===== */
  function stopTextMicVisualization() {
    if (textMicAnimationFrame) cancelAnimationFrame(textMicAnimationFrame);
    textMicAnimationFrame = 0;
    if (textMicLimitTimer) window.clearTimeout(textMicLimitTimer);
    textMicLimitTimer = 0;
    if (textMicAudioContext) {
      try { textMicAudioContext.close(); } catch (_) {}
    }
    textMicAudioContext = null;
    textMicAnalyser = null;
    const bar = document.getElementById('textRecordingBar');
    if (bar) { bar.hidden = true; bar.style.display = 'none'; }
    const promptColumn = document.querySelector('.studio-prompt-column');
    if (promptColumn) promptColumn.classList.remove('text-mic-active');
  }

  function startTextMicVisualization(stream) {
    const bar = document.getElementById('textRecordingBar');
    const equalizer = document.getElementById('textRecordingEqualizer');
    const timeEl = document.getElementById('textRecordingTime');
    if (bar) { bar.hidden = false; bar.style.display = ''; }
    const promptColumn = document.querySelector('.studio-prompt-column');
    if (promptColumn) promptColumn.classList.add('text-mic-active');
    if (timeEl) timeEl.textContent = '0:00';
    textMicStartedAt = Date.now();
    if (textMicLimitTimer) window.clearTimeout(textMicLimitTimer);
    textMicLimitTimer = window.setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        toast('Достигнут лимит записи 10 минут');
        mediaRecorder.stop();
      }
    }, 10 * 60 * 1000);
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      textMicAudioContext = AudioContextClass ? new AudioContextClass() : null;
      if (textMicAudioContext) {
        const source = textMicAudioContext.createMediaStreamSource(stream);
        textMicAnalyser = textMicAudioContext.createAnalyser();
        textMicAnalyser.fftSize = 64;
        textMicAnalyser.smoothingTimeConstant = .72;
        source.connect(textMicAnalyser);
      }
    } catch (_) {
      textMicAnalyser = null;
    }
    const bars = equalizer ? Array.from(equalizer.querySelectorAll('i')) : [];
    const frequencyData = textMicAnalyser ? new Uint8Array(textMicAnalyser.frequencyBinCount) : null;
    const draw = () => {
      if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
      if (textMicAnalyser && frequencyData) textMicAnalyser.getByteFrequencyData(frequencyData);
      bars.forEach((node, index) => {
        const value = frequencyData ? frequencyData[Math.min(frequencyData.length - 1, index * 2)] : (35 + (index % 4) * 12);
        node.style.transform = 'scaleY(' + Math.max(.16, Math.min(1, value / 150)) + ')';
      });
      if (timeEl) {
        const seconds = Math.min(600, Math.max(0, Math.floor((Date.now() - textMicStartedAt) / 1000)));
        timeEl.textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
      }
      textMicAnimationFrame = requestAnimationFrame(draw);
    };
    textMicAnimationFrame = requestAnimationFrame(draw);
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: toggleMic
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
    // =====================================================
    // JAVASCRIPT-БЛОК: mime
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
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
      stopTextMicVisualization();
      try { mediaStream.getTracks().forEach((t) => t.stop()); } catch {}
      const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      if (blob.size < 800) { toast('Recording too short'); return; }
      const ta = document.getElementById('chatInput');
      if (ta) PromptPlaceholderManager.setTemporary('Transcribing…');
      try {
        const fd = new FormData();
        const ext = (blob.type.includes('mp4') ? 'mp4' : 'webm');
        fd.append('file', blob, 'voice.' + ext);
        const r = await fetch('/api/public/prostudio/transcribe', { method: 'POST', body: fd });
        const j = await r.json();
        if (!r.ok || !j.ok) throw new Error(translateGenerationError(j, 'Не удалось распознать голос. Попробуйте ещё раз.'));
        if (ta) { ta.value = (ta.value ? ta.value + ' ' : '') + (j.text || ''); autoGrow(ta); ta.focus(); }
      } catch (err) {
        toast(translateGenerationError(err, 'Не удалось распознать голос. Попробуйте ещё раз.'));
      } finally {
        PromptPlaceholderManager.clearTemporary();
      }
    };
    mediaRecorder.start();
    if (btn) btn.classList.add('rec');
    startTextMicVisualization(mediaStream);
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: deleteMsg
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function deleteMsg(i) {
    chatMessages.splice(i, 1); renderChat();
    rememberCurrentChatSpace();
    S.haptic.impact('light');
  }
  // =====================================================
  // ЧАТ И ИСТОРИЯ: newChat
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function newChat() {
    const type = currentChatType();
    currentConvId = null;
    chatMessages = [];
    chatSpaces[type] = { activeChatId: null, conversationId: null, messages: [] };
    rememberCurrentChatSpace();
    renderChat();
    renderConvList();
    S.haptic.impact('light');
  }

  /* ===== Real history sidebar ===== */
  // =====================================================
  // ЧАТ И ИСТОРИЯ: loadConversations
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  async function loadConversations() {
    const tg = getTelegramId();
    if (!tg) return;
    try {
      const r = await fetch('/api/public/prostudio/conversations?telegram_id=' + tg + '&limit=80&offset=0');
      const j = await r.json();
      conversationsCache = (j && j.conversations) || [];
      syncChatCollections(conversationsCache);
      renderConvList();
      const type = currentChatType();
      const space = chatSpaces[type] || {};
      if (!activeGenerationLocked() && !(space.activeChatId || space.conversationId) && !(space.messages || []).length && !chatMessages.length) {
        const latest = latestConversationForType(type);
        if (latest && latest.id) openConv(latest.id, type, { silent: true });
      }
    } catch {}
  }
  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderConvList
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderConvList() {
    const el = document.getElementById('hdConvList'); if (!el) return;
    const labels = {
      image: 'Генерация фото',
      video: 'Генерация видео',
      music: 'Генерация музыки',
      voice: 'Генерация озвучки',
    };
    const type = currentChatType();
    const items = chatCollections[type] || [];
    const expanded = !!expandedHistorySections[type];
    const visibleItems = expanded ? items : items.slice(0, 5);
    el.innerHTML = '<div class="hd-type-section">'
      + '<div class="hd-label">' + S.escapeHtml(labels[type] || 'Чаты') + '</div>'
      + (items.length
        ? visibleItems.map(c =>
          '<div class="hd-item-row">' +
            '<button class="hd-item ' + (c.id === currentConvId ? 'act' : '') + '" onclick="SYLVEX.openConv(\'' + S.escapeHtml(c.id) + '\',\'' + type + '\')">' +
              S.escapeHtml(c.title || 'Chat') +
            '</button>' +
            '<button class="hd-del" onclick="SYLVEX.deleteConv(event,\'' + S.escapeHtml(c.id) + '\',\'' + type + '\')" aria-label="Delete">×</button>' +
          '</div>'
        ).join('') + (!expanded && items.length > 5
          ? '<button class="hd-more" type="button" onclick="SYLVEX.expandHistorySection(event,\'' + type + '\')">Открыть полный список</button>'
          : '')
        : '<div class="hd-label" style="opacity:.35">Пока пусто</div>')
      + '</div>';
  }
  // =====================================================
  // ЧАТ И ИСТОРИЯ: expandHistorySection
  // Работает с независимыми чатами, историей генераций и восстановлением сообщений пользователя.
  // =====================================================
  function expandHistorySection(e, type) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    expandedHistorySections[chatTypeForMode(type)] = true;
    renderConvList();
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openConv
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  async function openConv(id, type, opts) {
    const tg = getTelegramId(); if (!tg) return;
    if (!id) return;
    let openKey = '';
    try {
      const options = opts || {};
      const nextType = chatTypeForMode(type || 'image');
      openKey = nextType + ':' + id;
      if (openingConversations.has(openKey)) return;
      if (id === currentConvId && nextType === currentChatType() && chatMessages.length && options.silent) return;
      openingConversations.add(openKey);
      if (!activeGenerationLocked() && nextType !== currentChatType()) {
        rememberCurrentChatSpace();
        restoringChatSpace = true;
        updateComposerMode(nextType);
        restoringChatSpace = false;
      }
      const r = await fetch('/api/public/prostudio/conversations?telegram_id=' + tg + '&conversation_id=' + id + '&limit=50&offset=0');
      const j = await r.json();
      if (!j.ok) return;
      currentConvId = id;
      chatMessages = (j.messages || []).map(m => {
        const images = Array.isArray(m.images)
          ? m.images
          : Array.isArray(m.image_urls)
            ? m.image_urls
            : (m.image_url ? [m.image_url] : []);
        const thumbnails = Array.isArray(m.thumbnails)
          ? m.thumbnails
          : Array.isArray(m.thumb_urls)
            ? m.thumb_urls
            : (m.thumbnail_url || m.thumb_url ? [m.thumbnail_url || m.thumb_url] : []);

        const videos = Array.isArray(m.videos) ? m.videos : (m.video_url ? [m.video_url] : []);
        const audios = Array.isArray(m.audios) ? m.audios : (m.audio_url ? [m.audio_url] : []);
        const metadata = m.metadata && typeof m.metadata === 'object' ? m.metadata : {};
        const hasResultMedia = !!(images.length || videos.length || audios.length);
        const resultType = metadata.type || (videos.length ? 'video' : (audios.length ? (nextType === 'voice' ? 'voice' : 'music') : (images.length ? 'image' : 'text')));
        const resultMeta = images.length && resultType === 'image'
          ? Object.assign({
              type: 'image',
              prompt: m.prompt || '',
              result_images: images,
              result_thumbnails: thumbnails.length ? thumbnails : [],
              image_url: images[0] || '',
              result_url: images[0] || '',
              full_url: images[0] || '',
              thumbnail_url: thumbnails[0] || '',
              thumb_url: thumbnails[0] || '',
              created_at: m.created_at || '',
            }, metadata)
          : Object.assign({
              type: resultType,
              prompt: m.prompt || '',
              result_url: videos[0] || audios[0] || '',
              video_url: videos[0] || '',
              videos,
              audio_url: audios[0] || '',
              audios,
              image_url: images[0] || '',
              thumbnail_url: thumbnails[0] || '',
              thumb_url: thumbnails[0] || '',
              created_at: m.created_at || '',
            }, metadata);
        if (hasResultMedia && !resultMeta.created_at) resultMeta.created_at = m.created_at || '';
        if (hasResultMedia) {
          resultMeta.status = resultMeta.status || m.status || 'completed';
          resultMeta.model = resultMeta.model || m.model || '';
          resultMeta.provider = resultMeta.provider || m.provider || '';
          resultMeta.cost = resultMeta.cost || m.cost || 0;
        }
        return {
          role: m.role === 'assistant' ? 'ai' : 'user',
          text: m.role === 'assistant' ? (m.response_text || '') : (m.prompt || ''),
          imageResultMini: m.role === 'assistant' && hasResultMedia,
          metadata: m.role === 'assistant' && hasResultMedia ? resultMeta : metadata,
          imageUrl: images[0] || undefined,
          images: images.length ? images : null,
          thumbUrl: thumbnails[0] || undefined,
          thumbnails: thumbnails.length ? thumbnails : null,
          videoUrl: videos[0] || undefined,
          videos: videos.length ? videos : null,
          audioUrl: audios[0] || undefined,
          audios: audios.length ? audios : null,
          fileUrl: m.file_url || undefined,
          files: Array.isArray(m.files) ? m.files : (m.file_url ? [m.file_url] : null),
        };
      });
      if (!chatMessages.length) chatMessages = [];
      if (activeGenerationLocked()) {
        activeGeneration.historyPreview = true;
        currentConvId = chatSpaces[activeGeneration.mode]?.conversationId || null;
        ensureActiveGenerationPlaceholder(false);
      } else {
        chatSpaces[nextType] = { activeChatId: currentConvId, conversationId: currentConvId, messages: chatMessages.slice() };
        rememberCurrentChatSpace();
      }
      renderChat();
      renderConvList();
      // While a job is active the drawer remains open so the user can inspect
      // old results. Closing the drawer explicitly restores the active mode.
      if (!options.silent && !activeGenerationLocked()) toggleHistory();
    } catch {
    } finally {
      if (openKey) openingConversations.delete(openKey);
    }
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: deleteConv
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function deleteConv(e, id, type) {
    e.stopPropagation();
    const tg = getTelegramId(); if (!tg) return;
    await fetch('/api/public/prostudio/conversations?telegram_id=' + tg + '&conversation_id=' + id, { method: 'DELETE' });
    const deletedType = chatTypeForMode(type || currentChatType());
    if (id === currentConvId && deletedType === currentChatType()) newChat();
    if (chatSpaces[deletedType] && chatSpaces[deletedType].conversationId === id) {
      chatSpaces[deletedType] = { activeChatId: null, conversationId: null, messages: [] };
      try { localStorage.setItem(chatStorageKey(deletedType), JSON.stringify(chatSpaces[deletedType])); } catch {}
    }
    loadConversations();
  }

  /* ===== Paywall ===== */
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openPaywall
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openPaywall() {
    const el = document.getElementById('paywall');
    if (el) el.classList.add('show');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closePaywall
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closePaywall(e) {
    if (e && e.target && e.target.id !== 'paywall') return;
    const el = document.getElementById('paywall');
    if (el) el.classList.remove('show');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openShopFromPaywall
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
    pack_100: 'https://www.paypal.com/ncp/payment/BBWGSMRNBPHSS',
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
  // =====================================================
  // JAVASCRIPT-БЛОК: getPayPalSubscriptionConfig
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: resetPayPalSubscriptionPanel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function resetPayPalSubscriptionPanel() {
    const panel = document.getElementById('paypalSubscriptionPanel');
    if (panel) panel.hidden = true;
    ['paypalSubscribePayMonth', 'paypalSubscribePayYear'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = true;
    });
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: showPayPalSubscriptionPanel
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openBuy
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeBuy
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeBuy() { switchView('shop'); }

  /* ===== Subscription state rendering ===== */
  let _cdTimer = null;
  let _expirySyncTriggeredFor = '';
  let _expiredSubscriptionModalShown = false;
  // =====================================================
  // JAVASCRIPT-БЛОК: fmtCountdown
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: fmtDate
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function fmtDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleDateString('ru-RU', { day:'2-digit', month:'long', year:'numeric' }); }
    catch { return '—'; }
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderPayPalSubscriptionButton
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
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

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderSubscription
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
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
            cta.textContent = 'Подписка';
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
      // =====================================================
      // JAVASCRIPT-БЛОК: tickCountdown
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const tickCountdown = () => {
        const ms = new Date(expIso).getTime() - Date.now();
        document.querySelectorAll('[data-sub-cd]').forEach((el) => { el.textContent = fmtCountdown(ms); });
        const sa = document.getElementById('saCountdown'); if (sa) sa.textContent = fmtCountdown(ms);
        if (ms <= 0) {
          if (_cdTimer) clearInterval(_cdTimer);
          _cdTimer = null;
          S.user = Object.assign({}, S.user || {}, {
            status: 'free',
            subscription_status: 'free',
            subscription_plan: null,
            subscription_expires_at: null,
            last_subscription_expires_at: expIso,
            subscription_expired: true,
          });
          renderSubscription();
          showExpiredSubscriptionModal(S.user);
          if (_expirySyncTriggeredFor !== expIso && S.syncUser) {
            _expirySyncTriggeredFor = expIso;
            S.syncUser({ force: true });
          }
        }
      };
      tickCountdown();
      _cdTimer = setInterval(tickCountdown, 1000);
    }
  }

  function ensureExpiredSubscriptionModal() {
    let modal = document.getElementById('expiredSubscriptionModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'expiredSubscriptionModal';
    modal.className = 'expired-subscription-modal';
    modal.innerHTML = '<section class="expired-subscription-card" role="dialog" aria-modal="true" aria-labelledby="expiredSubscriptionTitle">'
      + '<button class="expired-subscription-close" type="button" aria-label="Закрыть" onclick="SYLVEX.closeExpiredSubscriptionModal(event)">×</button>'
      + '<div class="expired-subscription-badge">SYLVEX PRO</div>'
      + '<h2 id="expiredSubscriptionTitle">Подписка закончилась</h2>'
      + '<p>Продлите подписку, чтобы продолжить пользоваться всеми возможностями SYLVEX.</p>'
      + '<div class="expired-subscription-user">'
      + '<span id="expiredSubscriptionAvatar"></span>'
      + '<div><b id="expiredSubscriptionName">Пользователь</b><small id="expiredSubscriptionHandle">@user</small><em id="expiredSubscriptionDate"></em></div>'
      + '</div>'
      + '<div class="expired-subscription-plans">'
      + '<button type="button" onclick="SYLVEX.openExpiredSubscriptionPurchase(event,\'sub_month\')"><span><b>1 месяц</b><small>SYLVEX Pro</small></span><strong>$5 · 230 ⭐</strong></button>'
      + '<button type="button" onclick="SYLVEX.openExpiredSubscriptionPurchase(event,\'sub_year\')"><span><b>1 год</b><small>Выгодный план</small></span><strong>$59 · 2751 ⭐</strong></button>'
      + '</div>'
      + '</section>';
    document.body.appendChild(modal);
    return modal;
  }

  function showExpiredSubscriptionModal(state) {
    const info = state || S.user || {};
    if (!info.subscription_expired || _expiredSubscriptionModalShown) return;
    const requestedView = (new URLSearchParams(window.location.search || '').get('view') || '').toLowerCase();
    const shopIsOpen = requestedView === 'shop' || requestedView === 'pay' || !!document.querySelector('.view[data-view="shop"].active,.view[data-view="pay"].active');
    if (shopIsOpen) return;
    const userId = Number((S.user && S.user.telegram_id) || info.telegram_id || 0);
    const now = new Date();
    const localDay = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
    const noticeKey = 'sylvex_expired_subscription_notice_' + (userId || 'user');
    try { if (localStorage.getItem(noticeKey) === localDay) return; } catch {}
    const modal = ensureExpiredSubscriptionModal();
    const user = S.user || {};
    const fullName = user.display_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'Пользователь';
    const handle = user.username ? '@' + user.username : '@user';
    const avatar = modal.querySelector('#expiredSubscriptionAvatar');
    if (avatar) {
      avatar.innerHTML = '';
      const avatarUrl = user.custom_avatar_url || user.photo_url || '';
      if (avatarUrl) {
        const img = document.createElement('img');
        img.src = avatarUrl;
        img.alt = '';
        avatar.appendChild(img);
      } else {
        avatar.textContent = fullName.slice(0, 2).toUpperCase();
      }
    }
    const nameEl = modal.querySelector('#expiredSubscriptionName');
    const handleEl = modal.querySelector('#expiredSubscriptionHandle');
    const dateEl = modal.querySelector('#expiredSubscriptionDate');
    if (nameEl) nameEl.textContent = fullName;
    if (handleEl) handleEl.textContent = handle;
    const expiredAt = info.last_subscription_expires_at || info.subscription_expires_at;
    if (dateEl) dateEl.textContent = expiredAt ? 'Завершена: ' + fmtDate(expiredAt) : 'Подписка не активна';
    _expiredSubscriptionModalShown = true;
    try { localStorage.setItem(noticeKey, localDay); } catch {}
    modal.classList.add('show');
  }

  function showSubscriptionCelebration(userState, plan) {
    closeExpiredSubscriptionModal();
    document.getElementById('subscriptionCelebration')?.remove();
    const user = Object.assign({}, S.user || {}, userState || {});
    const name = user.display_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'Пользователь';
    const planLabel = String(plan || user.subscription_plan || '').toLowerCase() === 'year' ? 'SYLVEX Pro · 1 год' : 'SYLVEX Pro · 1 месяц';
    const overlay = document.createElement('div');
    overlay.id = 'subscriptionCelebration';
    overlay.className = 'subscription-celebration';
    overlay.innerHTML = '<div class="subscription-confetti" aria-hidden="true">' + Array.from({length:28}, (_, index) => '<i style="--i:' + index + '"></i>').join('') + '</div>'
      + '<section class="subscription-celebration-card" role="dialog" aria-modal="true">'
      + '<button type="button" aria-label="Закрыть" onclick="this.closest(\'#subscriptionCelebration\').remove()">×</button>'
      + '<span class="subscription-celebration-mark"><svg viewBox="0 0 24 24"><path d="m5 13 4 4L19 7"/></svg></span>'
      + '<h2>Подписка активирована!</h2><p>' + S.escapeHtml(name) + ', добро пожаловать в SYLVEX Pro.</p>'
      + '<strong>' + S.escapeHtml(planLabel) + '</strong>'
      + '<button class="subscription-celebration-go" type="button" onclick="this.closest(\'#subscriptionCelebration\').remove();switchView(\'tools\')">Перейти в Pro Studio</button>'
      + '</section>';
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('show'));
    S.haptic && S.haptic.notify && S.haptic.notify('success');
  }

  function closeExpiredSubscriptionModal(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const modal = document.getElementById('expiredSubscriptionModal');
    if (modal) modal.classList.remove('show');
  }

  function openExpiredSubscriptionPurchase(e, packId) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    closeExpiredSubscriptionModal();
    openBuy(packId === 'sub_year' ? 'sub_year' : 'sub_month');
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openSubActive
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: renewFromModal
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function renewFromModal() {
    closeModal(null, 'subActiveModal');
    // Force purchase flow (bypass "already subscribed" branch).
    const pack = pendingPack || 'sub_month';
    const savedUser = S.user; S.user = Object.assign({}, savedUser, { subscription_status: 'free' });
    openBuy(pack);
    S.user = savedUser;
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openManageSub
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openManageSub() {
    const u = S.user || {};
    if (u.subscription_status === 'active') openSubActive('sub_' + (u.subscription_plan || 'month'));
    else switchView('shop');
  }

  /* ===== Modal helpers ===== */
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeModal
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeModal(e, id) {
    if (e && e.target && e.target.id !== id) return;
    const el = document.getElementById(id); if (el) el.classList.remove('show');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openProInfo
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
    'assets/avatars/a4.png','assets/avatars/a5.png','assets/avatars/a6.png',
    'assets/avatars/a7.png','assets/avatars/a8.png','assets/avatars/a9.png',
    'assets/avatars/a10.png',
  ];
  let epSelectedAvatar = null;
  let epAppearanceDraft = null;
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openEditProfile
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openEditProfile() {
    const u = S.user || {};
    document.getElementById('epName').value = u.display_name || [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || '';
    epSelectedAvatar = u.custom_avatar_url || null;
    const grid = document.getElementById('avatarGrid');
    if (grid) {
      // =====================================================
      // JAVASCRIPT-БЛОК: items
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const items = [{ url: null, label: 'TG' }].concat(AVATAR_PRESETS.map((p) => ({ url: p })));
      grid.innerHTML = items.map((it, i) => {
        const sel = (epSelectedAvatar || '') === (it.url || '') ? 'sel' : '';
        const inner = it.url ? '<img src="' + it.url + '" alt="" loading="lazy" decoding="async" />' : '<span>TG</span>';
        return '<button class="av-opt ' + sel + '" data-url="' + (it.url || '') + '" onclick="SYLVEX.pickAvatar(this)">' + inner + '</button>';
      }).join('');
    }
    epAppearanceDraft = currentProfileAppearance();
    syncAppearanceEditor();
    renderThemeGrid();
    document.getElementById('editProfileModal').classList.add('show');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: pickAvatar
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function pickAvatar(btn) {
    epSelectedAvatar = btn.dataset.url || null;
    document.querySelectorAll('#avatarGrid .av-opt').forEach((el) => el.classList.remove('sel'));
    btn.classList.add('sel');
  }
  // =====================================================
  // ЗАГРУЗКА В MINI APP: saveEditProfile
  // Принимает файл/ссылку пользователя и кладёт её в нужную upload-зону без смешивания режимов.
  // =====================================================
  async function saveEditProfile() {
    const name = (document.getElementById('epName').value || '').trim().slice(0, 60);
    const body = {
      initData: S.tg && S.tg.initData ? S.tg.initData : '',
      initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
      telegram_id: getTelegramId(),
      display_name: name,
      custom_avatar_url: epSelectedAvatar,
      theme_preference: epAppearanceDraft || currentProfileAppearance(),
    };
    try {
      const r = await fetch('/api/public/telegram/profile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || j.error) { toast('Ошибка: ' + (j.error || r.status)); return; }
      storeProfileAppearance(body.theme_preference);
      applyProfileAppearance(body.theme_preference);
      S.user = Object.assign({}, S.user || {}, j.user || {}, {
        display_name: name,
        custom_avatar_url: epSelectedAvatar,
        theme_preference: body.theme_preference,
      });
      if (S.cacheProfileIdentity) S.cacheProfileIdentity(S.user);
      if (S.renderUser) S.renderUser(S.user);
      toast('Сохранено ✓');
      closeModal(null, 'editProfileModal');
      S.syncUser && S.syncUser({ force: true });
    } catch { toast('Сетевая ошибка'); }
  }

  /* ===== Theme picker ===== */
  const THEMES = [
    { id: 'dark',  label: 'Тёмная',    css: { '--bg-0':'#212121','--bg-1':'#171717','--bg-2':'#2f2f2f','--surface':'#2f2f2f','--surface-2':'#3a3a3a','--text':'#ececec' }, mode:'dark' },
    { id: 'black', label: 'Чёрная',    css: { '--bg-0':'#000000','--bg-1':'#0a0a0a','--bg-2':'#141414','--surface':'#161616','--surface-2':'#222222','--text':'#f5f5f5' }, mode:'dark' },
    { id: 'blue',  label: 'Синяя ночь', css: { '--bg-0':'#0b1220','--bg-1':'#0a0f1c','--bg-2':'#111a2e','--surface':'#12203a','--surface-2':'#1a2c4d','--text':'#eaf1ff' }, mode:'dark' },
    { id: 'plum',  label: 'Слива',     css: { '--bg-0':'#1a0f22','--bg-1':'#120a19','--bg-2':'#241432','--surface':'#2b1a3a','--surface-2':'#3a2450','--text':'#f2eaff' }, mode:'dark' },
    { id: 'vanilla', label: 'Ванильная', css: { '--bg-0':'#f7f0df','--bg-1':'#efe5cf','--bg-2':'#fffaf0','--surface':'#fff8e8','--surface-2':'#eadfc8','--text':'#332d24' }, mode:'light' },
    { id: 'forest', label: 'Лесная', css: { '--bg-0':'#102019','--bg-1':'#0b1712','--bg-2':'#172a21','--surface':'#1a3026','--surface-2':'#254438','--text':'#e8f3ed' }, mode:'dark' },
    { id: 'rose', label: 'Розовая', css: { '--bg-0':'#fff3f5','--bg-1':'#f9e7eb','--bg-2':'#fff9fa','--surface':'#fff7f8','--surface-2':'#f1dce1','--text':'#3e252c' }, mode:'light' },
    { id: 'light', label: 'Светлая',   css: { '--bg-0':'#ffffff','--bg-1':'#f7f7f8','--bg-2':'#ffffff','--surface':'#f4f4f4','--surface-2':'#ececec','--text':'#0d0d0d' }, mode:'light' },
  ];
  const DEFAULT_PROFILE_APPEARANCE = { id:'dark', nickname:'#ececec' };
  function appearanceStorageKey() { return 'sylvex-profile-appearance-' + (getTelegramId() || 'guest'); }
  function validHex(value, fallback) { return /^#[0-9a-f]{6}$/i.test(String(value || '')) ? String(value).toLowerCase() : fallback; }
  function contrastColor(hex) {
    const clean = validHex(hex, '#000000').slice(1);
    const rgb = [0,2,4].map((i) => parseInt(clean.slice(i, i + 2), 16));
    const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
    return luminance > 0.56 ? '#111111' : '#ffffff';
  }
  function readableColor(foreground, background) {
    const rgb = (hex) => { const c = validHex(hex, '#000000').slice(1); return [0,2,4].map((i) => parseInt(c.slice(i,i+2),16) / 255).map((v) => v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4)); };
    const lum = (hex) => { const c = rgb(hex); return .2126*c[0]+.7152*c[1]+.0722*c[2]; };
    const a=lum(foreground),b=lum(background),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    return ratio >= 4.5 ? foreground : contrastColor(background);
  }
  function currentProfileAppearance() {
    let local = null;
    try { local = JSON.parse(localStorage.getItem(appearanceStorageKey()) || 'null'); } catch {}
    const remoteValue = S.user && S.user.theme_preference && typeof S.user.theme_preference === 'object' ? S.user.theme_preference : null;
    const remote = remoteValue && Object.keys(remoteValue).length ? remoteValue : null;
    const source = remote || local || {};
    const theme = THEMES.find((item) => item.id === (source.id || source.themeId)) || THEMES[0];
    return {
      id: theme.id,
      nickname: validHex(source.nickname, theme.css['--text']),
    };
  }
  function storeProfileAppearance(settings) {
    try { localStorage.setItem(appearanceStorageKey(), JSON.stringify(settings)); } catch {}
    localStorage.setItem('sylvex-theme-id', settings.id || 'dark');
  }
  function applyProfileAppearance(settings) {
    const value = Object.assign({}, DEFAULT_PROFILE_APPEARANCE, settings || {});
    const theme = THEMES.find((item) => item.id === value.id) || THEMES[0];
    document.documentElement.dataset.theme = theme.mode;
    const style = document.documentElement.style;
    const text = theme.css['--text'];
    const surfaceText = contrastColor(theme.css['--surface']);
    const buttonText = '#ffffff';
    Object.keys(theme.css).forEach((key) => style.setProperty(key, theme.css[key]));
    style.setProperty('--grad-card', theme.css['--surface']);
    style.setProperty('--primary', '#10a37f');
    style.setProperty('--primary-2', '#0e8e6e');
    style.setProperty('--accent', '#10a37f');
    style.setProperty('--text', text);
    style.setProperty('--text-dim', text === '#ffffff' ? '#c7c7c7' : '#454545');
    style.setProperty('--text-mute', text === '#ffffff' ? '#969696' : '#737373');
    style.setProperty('--surface-text', surfaceText);
    style.setProperty('--button-text', buttonText);
    style.setProperty('--nickname-color', readableColor(validHex(value.nickname, text), theme.css['--surface']));
  }
  function syncAppearanceEditor() {
    const value = epAppearanceDraft || currentProfileAppearance();
    [['Nickname','nickname']].forEach(([id,key]) => {
      const input = document.getElementById('ep' + id + 'Color');
      const output = document.getElementById('ep' + id + 'ColorValue');
      if (input) input.value = value[key];
      if (output) output.textContent = value[key].toUpperCase();
    });
  }
  function previewProfileColor(kind, color) {
    if (!epAppearanceDraft) epAppearanceDraft = currentProfileAppearance();
    epAppearanceDraft[kind] = validHex(color, epAppearanceDraft[kind]);
    syncAppearanceEditor();
    applyProfileAppearance(epAppearanceDraft);
  }
  function selectProfileTheme(themeId) {
    const theme = THEMES.find((item) => item.id === themeId) || THEMES[0];
    epAppearanceDraft = { id:theme.id, nickname:(epAppearanceDraft && epAppearanceDraft.nickname) || theme.css['--text'] };
    syncAppearanceEditor();
    applyProfileAppearance(epAppearanceDraft);
    renderThemeGrid();
  }
  function resetProfileAppearance() {
    epAppearanceDraft = Object.assign({}, DEFAULT_PROFILE_APPEARANCE);
    syncAppearanceEditor();
    applyProfileAppearance(epAppearanceDraft);
    renderThemeGrid();
  }
  function cancelEditProfile(event) {
    if (event && event.target && event.target.id !== 'editProfileModal') return;
    applyProfileAppearance(currentProfileAppearance());
    epAppearanceDraft = null;
    closeModal(null, 'editProfileModal');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: applyTheme
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyTheme(themeId, persist = true) {
    // =====================================================
    // JAVASCRIPT-БЛОК: t
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const t = THEMES.find((x) => x.id === themeId) || THEMES[0];
    document.documentElement.setAttribute('data-theme', t.mode);
    const r = document.documentElement.style;
    Object.keys(t.css).forEach((k) => r.setProperty(k, t.css[k]));
    localStorage.setItem('sylvex-theme-id', themeId);
    // Persist to backend only when user manually changes theme.
    if (persist) {
      const body = {
        initData: S.tg && S.tg.initData ? S.tg.initData : '',
        initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
        telegram_id: getTelegramId(),
        theme_preference: { id: themeId },
      };
      fetch('/api/public/telegram/profile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }).catch(() => {});
    }
    renderThemeGrid();
  }
  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderThemeGrid
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderThemeGrid() {
    const g = document.getElementById('themeGrid'); if (!g) return;
    const cur = (epAppearanceDraft && epAppearanceDraft.id) || currentProfileAppearance().id;
    g.innerHTML = THEMES.map((t) => {
      const sel = cur === t.id ? 'sel' : '';
      const sw = 'background:' + t.css['--bg-0'];
      const swInner = 'background:' + t.css['--surface-2'];
      return '<button type="button" class="th-opt ' + sel + '" onclick="SYLVEX.selectProfileTheme(\'' + t.id + '\')">'
        + '<div class="th-sw" style="' + sw + '"><div class="th-sw-inner" style="' + swInner + '"></div></div>'
        + '<div class="th-lbl">' + t.label + '</div></button>';
    }).join('');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openThemePicker
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openThemePicker() {
    renderThemeGrid();
    document.getElementById('themeModal').classList.add('show');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: applyStoredTheme
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyStoredTheme() {
    applyProfileAppearance(currentProfileAppearance());
  }

  /* ===== Referrals ===== */
  let _refData = null;
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openReferrals
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
    } catch { document.getElementById('refLinkVal').textContent = '—'; }
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: copyRefLink
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function copyRefLink() {
    const v = (_refData && (_refData.link || _refData.code)) || document.getElementById('refLinkVal').textContent;
    if (!v || v === '—') return;
    if (navigator.clipboard) navigator.clipboard.writeText(v).catch(() => {});
    toast('Ссылка скопирована');
    S.haptic && S.haptic.notify && S.haptic.notify('success');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: activateRefLink
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: signOut
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function signOut() {
    try { localStorage.removeItem('sylvex-theme-id'); } catch {}
    if (S.tg && S.tg.close) S.tg.close();
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: contactAdmin
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function contactAdmin() {
    const url = 'https://t.me/sylvex_admin';
    const tgApp = S.tg;
    if (tgApp && tgApp.openTelegramLink) tgApp.openTelegramLink(url);
    else if (tgApp && tgApp.openLink)    tgApp.openLink(url);
    else window.open(url, '_blank');
  }
  // =====================================================
  // JAVASCRIPT-БЛОК: isTelegramLink
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function isTelegramLink(url) {
    return /^https:\/\/t\.me\//i.test(url || '') || /^tg:\/\//i.test(url || '');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openPaymentUrl
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: payWith
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
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
                if (confirmJson.subscription_activated) {
                  showSubscriptionCelebration(confirmJson.user, confirmJson.subscription_plan);
                } else if (packId.indexOf('sub_') === 0 && S.syncUser) {
                  // successful_payment can reach the polling bot a fraction
                  // later than the Mini App receives openInvoice("paid").
                  for (let attempt = 0; attempt < 3; attempt += 1) {
                    await new Promise(resolve => setTimeout(resolve, 900 + attempt * 600));
                    const syncedUser = await S.syncUser({ force: true });
                    if (syncedUser && syncedUser.subscription_status === 'active') {
                      showSubscriptionCelebration(syncedUser, syncedUser.subscription_plan);
                      break;
                    }
                  }
                }
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
  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: updateSendButton
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
  function updateSendButton() {
    const ta = document.getElementById('chatInput');
    const mic = document.getElementById('micBtn');
    const send = document.getElementById('sendBtn');
    if (!ta || !send) return;
    const label = send.querySelector('.studio-generate-label');
    if (activeGenerationLocked()) {
      send.disabled = true;
      send.hidden = false;
      send.classList.add('has-active-job');
      const activeLabel = activeGenerationButtonLabel(activeGeneration.status);
      if (label) label.textContent = activeLabel;
      send.setAttribute('aria-label', activeLabel);
      send.title = activeLabel;
      return;
    }
    send.classList.remove('has-active-job');
    if (label) label.textContent = studioMode === 'text' ? 'Отправить' : 'Сгенерировать';
    const activeReferences = isVideoMode()
      ? currentVideoReferenceImages()
      : (isImageMode() ? imageState.referenceImageUrls : []);
    const activeAttachment = currentModeAttachment();
    const activeAudioUploads = (isMusicMode() || isVoiceMode()) ? (currentAudioState().uploads || []) : [];
    const textUploading = studioMode === 'text' && !!(textState.attachment && textState.attachment.uploading);
    const has = (ta.value || '').trim().length > 0
      || !!activeAttachment
      || !!(activeReferences && activeReferences.length)
      || !!(isVideoMode() && (currentVideoEditInputUrl() || currentVideoReferenceUrl()))
      || !!(activeAudioUploads && activeAudioUploads.length);
    if (mic && !send.classList.contains('studio-generate')) mic.hidden = has;
    if (send.classList.contains('studio-generate')) {
      send.disabled = !has || textUploading;
      send.hidden = false;
      send.setAttribute('aria-label', studioMode === 'text' ? 'Отправить сообщение' : 'Сгенерировать');
      send.title = studioMode === 'text' ? 'Отправить' : 'Сгенерировать';
    } else {
      send.hidden = !has || textUploading;
    }
  }

  /* ===== Support modal ===== */
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openSupport
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openSupport() {
    const m = document.getElementById('supportModal');
    m.classList.add('show');
    setTimeout(() => { const ta = document.getElementById('supportMsg'); ta && ta.focus(); }, 250);
    S.haptic.impact('light');
  }
  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: closeSupport
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function closeSupport() {
    document.getElementById('supportModal').classList.remove('show');
  }
  // =====================================================
  // ЗАПУСК ГЕНЕРАЦИИ: sendSupport
  // Собирает prompt и настройки, отправляет запрос на backend и запускает ожидание результата.
  // =====================================================
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
  // =====================================================
  // JAVASCRIPT-БЛОК: initHero
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function initHero() {
    const track = document.getElementById('heroTrack');
    const dotsEl = document.getElementById('heroDots');
    if (!track || !dotsEl) return;

    // =====================================================
    // ОТРИСОВКА ИНТЕРФЕЙСА: renderDots
    // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
    // =====================================================
    function renderDots() {
      const n = track.children.length;
      let s = '';
      for (let i = 0; i < n; i++) s += '<div class="dot-i ' + (i === slideIdx ? 'act' : '') + '"></div>';
      dotsEl.innerHTML = s;
    }
    // =====================================================
    // JAVASCRIPT-БЛОК: goSlide
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
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

  // =====================================================
  // JAVASCRIPT-БЛОК: updateStudioComposerCompact
  // Следит за реальной шириной панели Pro Studio.
  // Если Mini App открыт узко внутри широкого окна, добавляет CSS-класс
  // для мобильного расположения кнопок фото, видео и озвучки.
  // =====================================================
  function updateStudioComposerCompact() {
    const composer = document.getElementById('studioComposer');
    if (!composer) return;
    const width = composer.getBoundingClientRect ? composer.getBoundingClientRect().width : composer.clientWidth;
    composer.classList.toggle('is-compact', Number(width || 0) <= 900);
  }

  /* ===== Wire up DOM ===== */
  // =====================================================
  // JAVASCRIPT-БЛОК: bindEvents
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function bindEvents() {
    document.addEventListener('click', (event) => {
      if (!activeGenerationLocked()) return;
      const target = event.target;
      if (!target || !target.closest) return;
      if (target.closest('#historyBtn, [data-view="history"], #histBackdrop, #histDrawer .hd-close, #histDrawer .hd-section')) return;
      if (target.closest('.view[data-view="tools"]')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast(activeGenerationButtonLabel(activeGeneration.status));
      }
    }, true);
    // Force bottom composer model button to open the image model picker.
    const composerModelVal = document.getElementById('modelValComposer');
    const composerRoot = document.getElementById('studioComposer');
    updateStudioComposerCompact();
    if (composerRoot && 'ResizeObserver' in window) {
      const studioComposerResizeObserver = new ResizeObserver(updateStudioComposerCompact);
      studioComposerResizeObserver.observe(composerRoot);
    }
    window.addEventListener('resize', updateStudioComposerCompact);
    window.addEventListener('orientationchange', updateStudioComposerCompact);
    ['pointerdown', 'keydown', 'touchmove', 'wheel'].forEach((eventName) => {
      document.addEventListener(eventName, (event) => {
        if (event.target && event.target.closest && event.target.closest('#studioComposer')) resetVoiceToolGuideTimer();
      }, { passive:true });
    });
    const composerModelBtn = composerModelVal
      ? composerModelVal.closest('button')
      : (composerRoot ? composerRoot.querySelector('.studio-control-row .studio-select-pill.wide') : null);
    if (composerModelBtn) {
      composerModelBtn.type = 'button';
      composerModelBtn.style.pointerEvents = 'auto';
      composerModelBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showImageModelPicker(e);
      });
    }
    // Upload button opens the large center upload panel.
    document.addEventListener('click', (e) => {
    const btn = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!btn) return;

    const text = (btn.textContent || '').trim().toLowerCase();

    if (text === 'загрузка' || text === 'upload') {
        openUploadPanel(e);
    }
    });

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
      const mp = document.getElementById('modelPop'); if (mp) { mp.classList.remove('show'); mp.classList.remove('image-model-floating-pop'); mp.classList.remove('image-size-floating-pop'); mp.classList.remove('music-settings-pop'); mp.classList.remove('video-option-horizontal-pop'); mp.style.cssText = ''; }
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
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    if (themeBtn) themeBtn.addEventListener('click', S.toggleTheme);
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
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
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    if (supportModal) supportModal.addEventListener('click', closeSupport);

    // Enter always creates a new line. Generation starts only from its button.
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
      PromptPlaceholderManager.setup(chatInput, chatTypeForMode(studioMode));
      VoiceDialogueComposer.setup(chatInput);
      const openComposerInputWindow = () => {
        if (!usesVirtualKeyboardLayout()) return;
        document.body.classList.add('kb-open');
        document.body.classList.add('composer-input-window-open');
        document.getElementById('studioComposer')?.classList.add('composer-input-window');
      };
      chatInput.addEventListener('focus', openComposerInputWindow);
      chatInput.addEventListener('input', () => {
        updateSendButton();
        updateVoiceTextEstimate();
        saveCurrentDraftSoon();
      });
    }
    window.addEventListener('sylvex:languagechange', () => PromptPlaceholderManager.refreshLanguage());

    // Keyboard offset: keep the Pro Studio input pinned above the on-screen
    // keyboard without shrinking the app or moving the header. The bottom
    // nav stays in its natural position and gets covered by the keyboard.
    const vv = window.visualViewport;
    if (vv) {
      let stableViewportHeight = Math.max(window.innerHeight, vv.height + vv.offsetTop);
      // =====================================================
      // JAVASCRIPT-БЛОК: updateKb
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const updateKb = () => {
        if (!usesVirtualKeyboardLayout()) {
          document.documentElement.style.setProperty('--kb', '0px');
          document.body.classList.remove('kb-open', 'composer-input-window-open');
          document.getElementById('studioComposer')?.classList.remove('composer-input-window');
          return;
        }
        const active = document.activeElement;
        const editableFocused = Boolean(active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT' || active.isContentEditable));
        if (!editableFocused) stableViewportHeight = Math.max(window.innerHeight, vv.height + vv.offsetTop);
        else stableViewportHeight = Math.max(stableViewportHeight, window.innerHeight, vv.height + vv.offsetTop);
        const layoutKeyboard = window.innerHeight - vv.height - vv.offsetTop;
        const stableKeyboard = stableViewportHeight - vv.height - vv.offsetTop;
        const kb = Math.max(0, layoutKeyboard, stableKeyboard);
        const forceComposerLift = editableFocused && active?.id === 'chatInput';
        document.documentElement.style.setProperty('--kb', kb + 'px');
        document.body.classList.toggle('kb-open', forceComposerLift || (editableFocused && kb > 80));
      };
      // =====================================================
      // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
      // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
      // =====================================================
      vv.addEventListener('resize', updateKb);
      vv.addEventListener('scroll', updateKb);
      window.addEventListener('resize', updateKb);
      document.addEventListener('focusin', () => {
        setTimeout(updateKb, 60);
        setTimeout(updateKb, 260);
      });
      document.addEventListener('focusout', () => setTimeout(updateKb, 80));
      updateKb();
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: initialViewFromUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function initialViewFromUrl() {
    const allowed = new Set(['home', 'history', 'community', 'shop', 'pay', 'profile', 'settings', 'tools']);
    const params = new URLSearchParams(window.location.search || '');
    const hash = (window.location.hash || '').replace(/^#/, '');
    const raw = params.get('view') || params.get('screen') || params.get('section') || hash;
    const view = (raw || '').trim().toLowerCase();
    return allowed.has(view) ? view : 'home';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: applyInitialViewFromUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applyInitialViewFromUrl() {
    const view = initialViewFromUrl();
    if (view && view !== 'home') switchView(view);
  }

  function referralStartCode() {
    const unsafe = S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : {};
    const params = new URLSearchParams(window.location.search || '');
    const raw = String(unsafe.start_param || params.get('tgWebAppStartParam') || params.get('startapp') || '');
    const match = raw.match(/^ref_(sylvex_[a-f0-9]{10})_shop$/i);
    return match ? match[1].toLowerCase() : '';
  }

  async function handleReferralStart() {
    const claimCode = referralStartCode();
    if (!claimCode) return;
    switchView('shop');
    try {
      await fetch('/api/public/telegram/referrals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          initData: S.tg && S.tg.initData ? S.tg.initData : '',
          initDataUnsafe: S.tg && S.tg.initDataUnsafe ? S.tg.initDataUnsafe : null,
          telegram_id: getTelegramId(),
          claim_code: claimCode,
        }),
      });
    } catch (_) {}
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: handlePaymentReturnFromUrl
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function handlePaymentReturnFromUrl() {
    const params = new URLSearchParams(window.location.search || '');
    if ((params.get('provider') || '').toLowerCase() !== 'paypal') return;

    const status = (params.get('payment') || '').toLowerCase();
    if (status === 'success') {
      toast('Оплата принята. Обновляем баланс…');
      if (S.syncUser) setTimeout(async () => {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          const user = await S.syncUser({ force: true });
          if (user && user.subscription_status === 'active') {
            showSubscriptionCelebration(user, user.subscription_plan);
            break;
          }
          await new Promise(resolve => setTimeout(resolve, 1800));
        }
      }, 1200);
    } else if (status === 'cancel') {
      toast('Оплата PayPal отменена');
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: initializeProStudioComposerMode
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function initializeProStudioComposerMode() {
    const composer = document.getElementById('studioComposer');
    const params = new URLSearchParams(window.location.search || '');
    const requestedMode = String(params.get('mode') || '').toLowerCase();
    const initialMode = CHAT_SPACE_TYPES.includes(requestedMode)
      ? requestedMode
      : (savedInitialStudioMode() || (composer && composer.dataset && composer.dataset.composerMode) || 'video');
    updateComposerMode(chatTypeForMode(initialMode));

    const requestedPrompt = String(params.get('prompt') || '').trim();
    if (requestedPrompt) {
      const input = document.getElementById('chatInput');
      if (input) {
        input.value = requestedPrompt;
        autoGrow(input);
        updateSendButton();
      }
    }

    const modelId = String(params.get('model') || '');
    if (initialMode === 'image' && modelId && IMAGE_MODEL_LIST.some((model) => model.id === modelId)) {
      pickImageOption(null, 'model', modelId);
    } else if (initialMode === 'video' && modelId && VIDEO_MODELS.some((model) => model.id === modelId)) {
      pickImageOption(null, 'model', modelId);
    } else if (initialMode === 'music' && modelId && MUSIC_MODEL_LIST.some((model) => model.id === modelId)) {
      pickImageOption(null, 'model', modelId);
    } else if (initialMode === 'voice' && modelId && VOICE_MODEL_LIST.some((model) => model.id === modelId)) {
      pickImageOption(null, 'model', modelId);
    } else if (initialMode === 'text' && modelId) {
      const model = TEXT_MODEL_LIST.find((item) => item.id === modelId);
      if (model) {
        textState.familyId = textModelFamilyId(model);
        textState.modelId = model.id;
        normalizeTextToolForModel();
        renderTextControls();
        renderModelPop();
      }
    }
    const tool = String(params.get('tool') || '').toLowerCase();
    if (initialMode === 'text' && tool && TEXT_TOOL_OPTIONS.some((item) => item.id === tool)) {
      if (TEXT_GEMINI_MEDIA_TOOLS.has(tool)) selectGeminiForTextMedia();
      pickTextOption(null, 'tool', tool);
    } else if (initialMode === 'image' && (tool === 'characters' || tool === 'objects')) {
      window.setTimeout(() => openVisualPicker(null, tool === 'objects' ? 'object' : 'character'), 180);
    } else if (initialMode === 'image' && tool === 'references') {
      window.setTimeout(() => openImageUpload(), 180);
    } else if (initialMode === 'video' && tool === 'edit') {
      window.setTimeout(() => updateComposerMode('edit'), 180);
    } else if (initialMode === 'video' && tool === 'motion') {
      window.setTimeout(() => updateComposerMode('motion'), 180);
    } else if (initialMode === 'video' && tool === 'image') {
      videoState.generationMode = 'image_to_video';
      window.setTimeout(() => openVideoStartUpload(), 180);
    }
  }

  /* ==========================================
     GLOBAL AUDIO PLAYER
     ========================================== */
  const PLAYER_VOLUME_KEY = 'sylvex-global-audio-volume';

  // =====================================================
  // АУДИОПЛЕЕР: normalizePlayerTrack
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function normalizePlayerTrack(trackLike) {
    const track = normalizeMusicTrack(trackLike || {});
    if (!track) return null;
    const meta = trackLike && trackLike.metadata && typeof trackLike.metadata === 'object' ? trackLike.metadata : {};
    const explicitTitle = (trackLike && (trackLike.title || trackLike.name)) || meta.title || meta.name || '';
    return {
      id: track.id || track.audioUrl,
      type: track.type || 'music',
      audioUrl: track.audioUrl,
      url: track.audioUrl,
      coverUrl: track.coverUrl || '',
      cover_url: track.coverUrl || '',
      title: explicitTitle || 'Untitled Track',
      model: track.model || '',
      provider: track.provider || 'suno',
    };
  }

  // =====================================================
  // АУДИОПЛЕЕР: collectMusicTracksFromMessage
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function collectMusicTracksFromMessage(message) {
    if (!message) return [];
    const meta = message.metadata && typeof message.metadata === 'object' ? message.metadata : {};
    const type = meta.type || message.type || (message.audioUrl || message.audio_url ? 'music' : '');
    const shouldRead = type === 'music' || type === 'audio' || type === 'voice' || musicAudioUrl(meta) || musicAudioUrl(message);
    if (!shouldRead) return [];
    const rawUrls = generatedUrlsFromMessage(message, 'audio');
    const urls = rawUrls.length ? rawUrls : [musicAudioUrl(meta) || musicAudioUrl(message)].filter(Boolean);
    return urls.map((url, index) => normalizePlayerTrack(Object.assign({}, message, meta, {
      id: meta.id || message.id || url,
      audio_url: url,
      result_url: url,
      cover_url: musicCoverUrl(meta) || musicCoverUrl(message),
      title: meta.title || message.title || message.name || (index ? 'Untitled Track ' + (index + 1) : 'Untitled Track'),
      provider: meta.provider || message.provider || 'suno',
      model: meta.model || message.model || '',
    }))).filter(Boolean);
  }

  // =====================================================
  // АУДИОПЛЕЕР: collectMusicPlaylist
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function collectMusicPlaylist(seedTrack) {
    const tracks = [];
    const seen = new Set();
    // =====================================================
    // JAVASCRIPT-БЛОК: addTrack
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const addTrack = (trackLike) => {
      const track = normalizePlayerTrack(trackLike);
      if (!track || !track.audioUrl || seen.has(track.audioUrl)) return;
      seen.add(track.audioUrl);
      tracks.push(track);
    };

    const messageSources = [];
    messageSources.push(...(chatMessages || []));
    CHAT_SPACE_TYPES.forEach((type) => {
      const space = chatSpaces[type];
      if (space && Array.isArray(space.messages)) messageSources.push(...space.messages);
    });
    messageSources.forEach((message) => {
      collectMusicTracksFromMessage(message).forEach(addTrack);
    });
    (conversationsCache || []).forEach((item) => {
      if (!item) return;
      addTrack(Object.assign({}, item, parseMetadataObject(item.metadata_json), parseMetadataObject(item.metadata)));
    });
    if (activeMusicTrack) addTrack(activeMusicTrack);
    if (seedTrack) addTrack(seedTrack);

    if (!seedTrack) return tracks;
    const normalizedSeed = normalizePlayerTrack(seedTrack);
    // =====================================================
    // JAVASCRIPT-БЛОК: seedIndex
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const seedIndex = normalizedSeed ? tracks.findIndex((item) => item.audioUrl === normalizedSeed.audioUrl) : -1;
    return {
      tracks,
      index: seedIndex >= 0 ? seedIndex : Math.max(0, tracks.length - 1),
    };
  }

  const PlayerManager = {
    playerEl: null,
    audioEl: null,
    artEl: null,
    titleEl: null,
    playPauseBtn: null,
    replayBtn: null,
    prevBtn: null,
    nextBtn: null,
    currentTimeEl: null,
    durationEl: null,
    progressBar: null,
    progressFill: null,
    volumeBtn: null,
    volumePopover: null,
    volumeSlider: null,
    closeBtn: null,
    playlist: [],
    currentIndex: 0,
    currentTrack: null,
    previousVolume: 1,
    visible: false,
    bound: false,
    progressDragging: false,

    ensureElements() {
      let player = document.getElementById('studioAudioPlayer');
      if (!player) {
        player = document.createElement('div');
        player.className = 'studio-audio-player';
        player.id = 'studioAudioPlayer';
        player.setAttribute('aria-live', 'polite');
        player.innerHTML = ''
          + '<audio id="studioAudioElement" preload="metadata"></audio>'
          + '<div class="studio-track-art" id="studioTrackArt"><img id="studioTrackArtImage" src="" alt="Album cover" hidden /></div>'
          + '<div class="studio-track-title" id="studioTrackTitle">Untitled Track</div>'
          + '<div class="studio-player-controls">'
          + '<button type="button" aria-label="Назад" id="studioPrevTrackBtn"><svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M7 6h2v12H7zM10 12l9-6v12z"/></svg></button>'
          + '<button type="button" aria-label="Play" id="studioPlayPauseBtn"><svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></button>'
          + '<button type="button" aria-label="Повторить" id="studioReplayTrackBtn"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/></svg></button>'
          + '<button type="button" aria-label="Вперёд" id="studioNextTrackBtn"><svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M15 6h2v12h-2zM5 18l9-6-9-6z"/></svg></button>'
          + '</div>'
          + '<div class="studio-time" id="studioCurrentTime">00:00</div>'
          + '<div class="studio-progress" id="studioProgressBar"><span id="studioProgressFill"></span></div>'
          + '<div class="studio-duration" id="studioDuration">00:00</div>'
          + '<button class="studio-player-icon" type="button" aria-label="Громкость" id="studioVolumeBtn"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9v6h4l5 4V5L9 9H5z"/><path d="M17 9a4 4 0 0 1 0 6"/><path d="M19 6a8 8 0 0 1 0 12"/></svg></button>'
          + '<div class="studio-volume-popover" id="studioVolumePopover" hidden><input id="studioVolumeSlider" type="range" min="0" max="100" value="100" aria-label="Громкость" /></div>'
          + '<button class="studio-player-icon" type="button" aria-label="Закрыть" id="studioClosePlayerBtn">×</button>';
      }
      if (player.parentElement !== document.body) document.body.appendChild(player);
      return player;
    },

    init() {
      this.playerEl = this.ensureElements();
      this.audioEl = document.getElementById('studioAudioElement');
      this.artEl = document.getElementById('studioTrackArtImage');
      this.titleEl = document.getElementById('studioTrackTitle');
      this.playPauseBtn = document.getElementById('studioPlayPauseBtn');
      this.replayBtn = document.getElementById('studioReplayTrackBtn');
      this.prevBtn = document.getElementById('studioPrevTrackBtn');
      this.nextBtn = document.getElementById('studioNextTrackBtn');
      this.currentTimeEl = document.getElementById('studioCurrentTime');
      this.durationEl = document.getElementById('studioDuration');
      this.progressBar = document.getElementById('studioProgressBar');
      this.progressFill = document.getElementById('studioProgressFill');
      this.volumeBtn = document.getElementById('studioVolumeBtn');
      this.volumePopover = document.getElementById('studioVolumePopover');
      this.volumeSlider = document.getElementById('studioVolumeSlider');
      this.closeBtn = document.getElementById('studioClosePlayerBtn');
      if (!this.playerEl || !this.audioEl) return;
      const savedVolume = this.loadVolume();
      this.audioEl.volume = savedVolume;
      this.previousVolume = savedVolume || 1;
      if (!this.bound) this.bind();
      this.hide(false);
      this.updateUi();
    },

    bind() {
      this.bound = true;
      if (this.playPauseBtn) this.playPauseBtn.onclick = () => this.toggle();
      if (this.replayBtn) this.replayBtn.onclick = () => this.replay();
      if (this.prevBtn) this.prevBtn.onclick = () => this.previous();
      if (this.nextBtn) this.nextBtn.onclick = () => this.next();
      if (this.closeBtn) this.closeBtn.onclick = () => this.close();
      if (this.volumeBtn) this.volumeBtn.onclick = (e) => this.handleVolumeButton(e);
      if (this.volumeSlider) this.volumeSlider.oninput = (e) => this.setVolume(Number(e.currentTarget.value) / 100, true);
      if (this.progressBar) {
        this.progressBar.addEventListener('mousedown', (e) => this.beginSeek(e));
        this.progressBar.addEventListener('touchstart', (e) => this.beginSeek(e), { passive: false });
      }
      this.audioEl.addEventListener('play', () => this.updateUi());
      this.audioEl.addEventListener('pause', () => this.updateUi());
      this.audioEl.addEventListener('timeupdate', () => this.updateProgress());
      this.audioEl.addEventListener('durationchange', () => this.updateProgress());
      this.audioEl.addEventListener('loadedmetadata', () => this.updateProgress());
      this.audioEl.addEventListener('ended', () => this.next(true));
      this.audioEl.addEventListener('volumechange', () => this.handleVolumeChange());
      document.addEventListener('pointerdown', (e) => {
        if (!this.volumePopover || this.volumePopover.hidden) return;
        if (this.volumePopover.contains(e.target) || (this.volumeBtn && this.volumeBtn.contains(e.target))) return;
        this.hideVolume();
      }, true);
    },

    loadVolume() {
      let value = 1;
      try { value = parseFloat(localStorage.getItem(PLAYER_VOLUME_KEY)); } catch {}
      return Number.isFinite(value) && value >= 0 && value <= 1 ? value : 1;
    },

    saveVolume(value) {
      try { localStorage.setItem(PLAYER_VOLUME_KEY, String(value)); } catch {}
    },

    playTrack(trackLike) {
      const track = normalizePlayerTrack(trackLike);
      if (!track) return;
      const built = collectMusicPlaylist(track);
      this.playlist = built.tracks.length ? built.tracks : [track];
      this.currentIndex = built.index;
      this.playCurrent();
    },

    open(tracks, index) {
      const normalized = (Array.isArray(tracks) ? tracks : []).map(normalizePlayerTrack).filter(Boolean);
      if (!normalized.length) return;
      this.playlist = normalized;
      this.currentIndex = Math.max(0, Math.min(Number(index) || 0, normalized.length - 1));
      this.playCurrent();
    },

    playCurrent() {
      const track = this.playlist[this.currentIndex];
      if (!track || !track.audioUrl || !this.audioEl) return;
      this.currentTrack = track;
      activeMusicTrack = track;
      if (this.audioEl.src !== track.audioUrl) {
        this.audioEl.src = track.audioUrl;
        this.audioEl.currentTime = 0;
        this.audioEl.load();
      }
      this.show();
      this.updateUi();
      const promise = this.audioEl.play();
      if (promise && typeof promise.catch === 'function') {
        promise.catch(() => {
          this.updateUi();
          toast('Трек готов в проигрывателе');
        });
      }
    },

    toggle() {
      if (!this.audioEl || !this.currentTrack) return;
      if (this.audioEl.paused) {
        const promise = this.audioEl.play();
        if (promise && typeof promise.catch === 'function') promise.catch(() => {});
      } else {
        this.audioEl.pause();
      }
      this.updateUi();
    },

    replay() {
      if (!this.audioEl || !this.currentTrack) return;
      this.audioEl.currentTime = 0;
      const promise = this.audioEl.play();
      if (promise && typeof promise.catch === 'function') promise.catch(() => {});
      this.updateUi();
    },

    next(fromEnded) {
      if (!this.playlist.length) return;
      if (this.currentIndex < this.playlist.length - 1) {
        this.currentIndex += 1;
        this.playCurrent();
      } else if (fromEnded) {
        this.audioEl.pause();
        this.audioEl.currentTime = 0;
        this.updateUi();
      }
    },

    previous() {
      if (!this.playlist.length || !this.audioEl) return;
      if ((this.audioEl.currentTime || 0) > 3 || this.currentIndex <= 0) {
        this.audioEl.currentTime = 0;
        this.updateProgress();
        return;
      }
      this.currentIndex -= 1;
      this.playCurrent();
    },

    show() {
      this.visible = true;
      if (this.playerEl) this.playerEl.classList.add('is-visible');
      document.body.classList.add('audio-player-open');
    },

    hide(stop) {
      this.visible = false;
      if (this.playerEl) this.playerEl.classList.remove('is-visible');
      document.body.classList.remove('audio-player-open');
      this.hideVolume();
      if (stop && this.audioEl) {
        this.audioEl.pause();
        this.audioEl.removeAttribute('src');
        this.audioEl.load();
        this.currentTrack = null;
        activeMusicTrack = null;
        this.playlist = [];
        this.currentIndex = 0;
      }
      this.updateUi();
    },

    close() {
      this.hide(true);
    },

    handleVolumeButton(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      if (!this.audioEl) return;
      if (this.audioEl.muted || this.audioEl.volume === 0) {
        this.setVolume(this.previousVolume > 0 ? this.previousVolume : 1, true);
        this.audioEl.muted = false;
      } else {
        if (this.volumePopover && !this.volumePopover.hidden) this.hideVolume();
        else this.showVolume();
      }
    },

    showVolume() {
      if (!this.volumePopover) return;
      this.volumePopover.hidden = false;
      if (this.volumeSlider) this.volumeSlider.value = Math.round((this.audioEl ? this.audioEl.volume : 1) * 100);
    },

    hideVolume() {
      if (this.volumePopover) this.volumePopover.hidden = true;
    },

    setVolume(value, persist) {
      if (!this.audioEl) return;
      const volume = Math.max(0, Math.min(1, Number(value) || 0));
      this.audioEl.volume = volume;
      this.audioEl.muted = volume === 0;
      if (volume > 0) this.previousVolume = volume;
      if (persist) this.saveVolume(volume);
      this.updateVolumeUi();
    },

    toggleMute() {
      if (!this.audioEl) return;
      if (this.audioEl.muted || this.audioEl.volume === 0) {
        this.setVolume(this.previousVolume > 0 ? this.previousVolume : 1, true);
        this.audioEl.muted = false;
      } else {
        this.previousVolume = this.audioEl.volume || this.previousVolume || 1;
        this.setVolume(0, true);
      }
      this.updateVolumeUi();
    },

    handleVolumeChange() {
      if (!this.audioEl) return;
      if (!this.audioEl.muted && this.audioEl.volume > 0) {
        this.previousVolume = this.audioEl.volume;
        this.saveVolume(this.audioEl.volume);
      }
      this.updateVolumeUi();
    },

    beginSeek(e) {
      if (!this.audioEl || !this.progressBar) return;
      e.preventDefault();
      this.progressDragging = true;
      // =====================================================
      // JAVASCRIPT-БЛОК: move
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const move = (ev) => this.seekFromEvent(ev);
      // =====================================================
      // JAVASCRIPT-БЛОК: up
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const up = (ev) => {
        this.seekFromEvent(ev);
        this.progressDragging = false;
        document.removeEventListener('mousemove', move);
        document.removeEventListener('touchmove', move);
        document.removeEventListener('mouseup', up);
        document.removeEventListener('touchend', up);
      };
      // =====================================================
      // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
      // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
      // =====================================================
      document.addEventListener('mousemove', move);
      // =====================================================
      // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
      // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
      // =====================================================
      document.addEventListener('touchmove', move, { passive: false });
      // =====================================================
      // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
      // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
      // =====================================================
      document.addEventListener('mouseup', up);
      // =====================================================
      // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
      // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
      // =====================================================
      document.addEventListener('touchend', up);
      this.seekFromEvent(e);
    },

    seekFromEvent(e) {
      if (!this.audioEl || !this.progressBar || !this.audioEl.duration) return;
      const point = e.touches && e.touches.length ? e.touches[0] : e;
      const rect = this.progressBar.getBoundingClientRect();
      const percent = Math.max(0, Math.min(1, (point.clientX - rect.left) / rect.width));
      this.audioEl.currentTime = percent * this.audioEl.duration;
      this.updateProgress();
    },

    updateUi() {
      const track = this.currentTrack;
      if (this.titleEl) this.titleEl.textContent = (track && track.title) || 'Untitled Track';
      if (this.artEl) {
        if (track && track.coverUrl) {
          this.artEl.src = track.coverUrl;
          this.artEl.hidden = false;
        } else {
          this.artEl.removeAttribute('src');
          this.artEl.hidden = true;
        }
      }
      if (this.playPauseBtn) {
        this.playPauseBtn.innerHTML = this.audioEl && !this.audioEl.paused
          ? '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>'
          : '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
        this.playPauseBtn.classList.toggle('playing', !!(this.audioEl && !this.audioEl.paused));
      }
      if (this.prevBtn) this.prevBtn.disabled = this.currentIndex <= 0;
      if (this.nextBtn) this.nextBtn.disabled = this.currentIndex >= this.playlist.length - 1;
      this.updateProgress();
      this.updateVolumeUi();
    },

    updateProgress() {
      if (!this.audioEl) return;
      const current = this.audioEl.currentTime || 0;
      const duration = Number.isFinite(this.audioEl.duration) ? this.audioEl.duration : 0;
      if (this.currentTimeEl) this.currentTimeEl.textContent = formatAudioTime(current);
      if (this.durationEl) this.durationEl.textContent = duration ? formatAudioTime(duration) : '00:00';
      if (this.progressFill) {
        const percent = duration ? Math.max(0, Math.min(1, current / duration)) : 0;
        this.progressFill.style.width = (percent * 100) + '%';
      }
    },

    updateVolumeUi() {
      if (!this.audioEl) return;
      const muted = this.audioEl.muted || this.audioEl.volume === 0;
      if (this.volumeBtn) {
        this.volumeBtn.classList.toggle('muted', muted);
        this.volumeBtn.innerHTML = muted
          ? '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9v6h4l5 4V5L9 9H5z"/><path d="M18 9l-5 5"/><path d="M13 9l5 5"/></svg>'
          : '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M5 9v6h4l5 4V5L9 9H5z"/><path d="M17 9a4 4 0 0 1 0 6"/><path d="M19 6a8 8 0 0 1 0 12"/></svg>';
      }
      if (this.volumeSlider) this.volumeSlider.value = Math.round(this.audioEl.volume * 100);
    },
  };

  // =====================================================
  // АУДИОПЛЕЕР: initAudioPlayer
  // Управляет воспроизведением музыки или озвучки внутри Mini App без внешнего перехода.
  // =====================================================
  function initAudioPlayer() {
    PlayerManager.init();
  }

  // =====================================================
  // ОБРАБОТЧИК ИНТЕРФЕЙСА: openAudioPlayer
  // Открывает, закрывает или переключает экран, шторку, меню, drawer или модальное окно Mini App.
  // =====================================================
  function openAudioPlayer(track, playlist = null, index = 0) {
    if (playlist) PlayerManager.open(playlist, index);
    else PlayerManager.playTrack(track);
  }

  /* ===== Init (called after cabinet.html is injected) ===== */
  // =====================================================
  // JAVASCRIPT-БЛОК: init
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function init() {
    // Restore saved theme.
    const tg = S.tg;
    const savedTheme = localStorage.getItem('sylvex-theme') || (tg && tg.colorScheme === 'light' ? 'light' : 'dark');
    S.setTheme(savedTheme);

    const initialShareId = shareStartId();
    if (initialShareId) {
      document.body.classList.add('generation-share-standalone');
      openGenerationSharePage(initialShareId);
    }

    bindEvents();
    window.addEventListener('message', handleKnowledgeWorkspaceMessage);
    initAudioPlayer();
    restoreLocalActiveGeneration();
    initializeProStudioComposerMode();
    applyLang();       // triggers renderDynamic
    initHero();
    renderChat();
    renderHomeAiModels();
    S.replaceLegacyUiIcons && S.replaceLegacyUiIcons(document);
    if ('MutationObserver' in window) {
      const uiIconObserver = new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach((node) => {
        if (node.nodeType === 1) S.replaceLegacyUiIcons && S.replaceLegacyUiIcons(node.parentElement || node);
      })));
      uiIconObserver.observe(document.getElementById('app-root') || document.body, { childList:true, subtree:true });
    }
    updateSendButton();
    loadImageCapabilities();
    handlePaymentReturnFromUrl();
    applyStoredTheme();
    applyInitialViewFromUrl();
    setTimeout(applyInitialViewFromUrl, 150);
    handleReferralStart();

    if (S.syncUser) {
      Promise.resolve(S.syncUser()).finally(() => {
        renderSubscription();
      });
    }
    loadConversations();
    loadProStudioSync();
    restoreActiveProStudioJob();
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, pickModelKey, toggleModelPop, togglePlusPop, closePlusSheet,
    openImageOptionMenu, showImageModelPicker, pickImageOption, pickMusicOption, pickVoiceOption, pickTextOption, previewGeminiVoice, previewSelectedVoice, resetMusicSettings, openMusicSettingsModal, closeMusicSettingsModal, selectMusicSettingDraft, resetMusicSettingsDraft, saveMusicSettings, openMusicDurationWheel, setMusicDurationPart, saveMusicDuration, resetImageSettings, onImageSeedInput, toggleImageSeedTooltip, updateComposerMode, renderVideoControls,
    openVoiceAddon, closeVoiceAddon, openVoiceCustomOption, hideMobileKeyboard, toggleVoiceHorizontalTools, setVoiceEditorSetting, insertVoiceEmotion, insertVoicePause, addVoiceCustomOption, saveVoicePronunciation, selectVoiceAiFormat, runVoiceTextTool, applyVoiceTemplate, addVoiceSpeaker, removeVoiceSpeaker, handleVoiceSpeakerClick, insertVoiceEffect, toggleVoiceFavorite, updateVoiceTextEstimate, toggleVoiceEditorFullscreen, swapVoiceTranslationLanguages, toggleVoiceTranslationFullscreen, copyVoiceTranslation, applyVoiceTranslation, setVoiceWorkspaceMode,
    pickVisualReference, deleteVisualReference, deleteUserVoice, closeResourceDeleteConfirm, openVisualPicker, openVideoVisualPicker, closeVisualPicker, openVisualCreateModal, closeVisualCreateModal, updateVisualCreateDraft, pickVisualCreatePhoto, removeVisualCreatePhoto, saveVisualCreateDraft, sendVisualInteraction, openCharacterDetail, closeCharacterDetail, playCharacterReferenceVideo,
    attach, handleSelectionButtonClick, openPhotoToolModal, closePhotoToolModal, openPhotoCatalog, closePhotoCatalog, selectPhotoCatalogItem, syncPhotoCatalogCardRatio, openPhotoToolFilePicker, onPhotoToolFiles, removePhotoToolFile, generatePhotoTool, openImageUpload, openVideoStartUpload, openVideoEndUpload, openVideoReferencesUpload, openVideoEditInputUpload, toggleVideoAddMenu, closeVideoAddMenu, chooseVideoAddMedia, chooseVideoAddCharacter, chooseVideoAddObject, openNativeFilePicker, onAttachFile, clearAttachment, openVoiceMediaPicker, confirmVoiceUpload, openVoicePanelSection, openVoiceCreate, closeVoiceCreate, closeVoicePanel, openVoiceList, closeVoiceList, openVoiceUpload, toggleVoiceUploadDropdown, selectVoiceUploadOption, openVoiceCloneFilePicker, openVoiceCloneAvatarPicker, setVoiceCloneField, toggleVoiceCloneDropdown, selectVoiceCloneOption, setVoiceCloneSetting, clearVoiceUploads, toggleVoiceCloneRecording, playVoiceCloneRecording, clearVoiceCloneRecording, sendVoiceCloneRecording, insertVoiceSpeaker, addMediaLink, openUploadPanel, closeUploadPanel, openUploadImagePreview, closeUploadImagePreview, selectGeneratedImage, selectUploadedPhoto, removeUploadedPhoto, clearCurrentUploadTarget, clearVideoReference, confirmUploadedPhotos, removeComposerImageDraft, genAction, toggleHistory, autoGrow, toggleMic,
    sendChat, copyMsg, regenMsg, deleteMsg, newChat,
    openConv, deleteConv, expandHistorySection, openPaywall, closePaywall, openShopFromPaywall, openShopForGeneration, resumePendingGeneration, updateSendButton,
    openBuy, closeBuy, payWith, contactAdmin,
    openSupport, closeSupport, sendSupport,
    computePrice, updatePrice, generateNow,
    renderSubscription, showExpiredSubscriptionModal, showSubscriptionCelebration, closeExpiredSubscriptionModal, openExpiredSubscriptionPurchase, openSubActive, renewFromModal, openManageSub, closeModal, openProInfo,
    openEditProfile, pickAvatar, saveEditProfile, previewProfileColor, selectProfileTheme, resetProfileAppearance, cancelEditProfile, openHomeQuickTool, openKnowledgeWorkspace, closeKnowledgeWorkspace,
    loadProfileGallery, filterProfileGallery, viewProfileGalleryText, sendProfileGalleryItem, reuseProfileGalleryItem, deleteProfileGalleryItem,
    loadCommunityFeed, toggleCommunityLike, openCommunityPublisher, publishCommunityItem, openCommunityComments, sendCommunityComment, replyCommunityComment, cancelCommunityReply, likeCommunityComment, editCommunityComment, deleteCommunityComment, searchCommunity, toggleCommunityMenu, communityComingSoon,
    openCommunityUserCard, followCommunityAuthor, messageCommunityAuthor, shareCommunityPost, downloadCommunityPost, filterCommunityPublisher, limitCommunitySelection, publishCommunitySelection,
    openCreativeCatalog, closeCreativeCatalog, useCreativeCatalogItem,
    openThemePicker, applyTheme, applyStoredTheme,
    openReferrals, copyRefLink, activateRefLink,
    signOut, openImageViewer, closeImageViewer, openGeneratedContent, openMusicInPlayer, playMusicTrack, playMusicTrackFromMessage, playVoiceInCard, playVideoInGenerationCard, toggleStudioAudioPlayer, openTelegramBot, animateGeneratedImage, editGeneratedVideo, openGenerationInfoDrawer, closeGenerationInfoDrawer,
    openGenerationSharePage, closeGenerationSharePage, handleGenerationShareAction, downloadGeneratedFile,
    PromptPlaceholderManager, VoiceDialogueComposer,
    initAudioPlayer,
    openAudioPlayer, continueVoiceResult,
    PlayerManager,
    get studioMode() { return studioMode; },
    get activeCat() { return activeCat; }
  });

  // Also expose the inline-onclick handlers as globals.
  window.toggleModelPop = toggleModelPop;
  window.openImageOptionMenu = openImageOptionMenu;
  window.showExpiredSubscriptionModal = showExpiredSubscriptionModal;
  window.closeExpiredSubscriptionModal = closeExpiredSubscriptionModal;
  window.openExpiredSubscriptionPurchase = openExpiredSubscriptionPurchase;
  window.pickVoiceOption = pickVoiceOption;
  window.pickTextOption = pickTextOption;
  window.previewGeminiVoice = previewGeminiVoice;
  window.previewSelectedVoice = previewSelectedVoice;
  window.onImageSeedInput = onImageSeedInput;
  window.toggleImageSeedTooltip = toggleImageSeedTooltip;
  window.resetImageSettings = resetImageSettings;
  window.showImageModelPicker = showImageModelPicker;
  window.togglePlusPop  = togglePlusPop;
  window.attach         = attach;
  window.handleSelectionButtonClick = handleSelectionButtonClick;
  window.openPhotoToolModal = openPhotoToolModal;
  window.closePhotoToolModal = closePhotoToolModal;
  window.openPhotoCatalog = openPhotoCatalog;
  window.closePhotoCatalog = closePhotoCatalog;
  window.selectPhotoCatalogItem = selectPhotoCatalogItem;
  window.syncPhotoCatalogCardRatio = syncPhotoCatalogCardRatio;
  window.openPhotoToolFilePicker = openPhotoToolFilePicker;
  window.onPhotoToolFiles = onPhotoToolFiles;
  window.removePhotoToolFile = removePhotoToolFile;
  window.generatePhotoTool = generatePhotoTool;
  window.openImageUpload = openImageUpload;
  window.openVideoStartUpload = openVideoStartUpload;
  window.openVideoEndUpload = openVideoEndUpload;
  window.openVideoReferencesUpload = openVideoReferencesUpload;
  window.openVideoEditInputUpload = openVideoEditInputUpload;
  window.openVideoVisualPicker = openVideoVisualPicker;
  window.toggleVideoAddMenu = toggleVideoAddMenu;
  window.closeVideoAddMenu = closeVideoAddMenu;
  window.chooseVideoAddMedia = chooseVideoAddMedia;
  window.chooseVideoAddCharacter = chooseVideoAddCharacter;
  window.chooseVideoAddObject = chooseVideoAddObject;
  window.openNativeFilePicker = openNativeFilePicker;
  window.openVoiceMediaPicker = openVoiceMediaPicker;
  window.confirmVoiceUpload = confirmVoiceUpload;
  window.openVoicePanelSection = openVoicePanelSection;
  window.openVoiceCreate = openVoiceCreate;
  window.openVoiceList = openVoiceList;
  window.closeVoiceList = closeVoiceList;
  window.openVoiceUpload = openVoiceUpload;
  window.openVoiceCloneFilePicker = openVoiceCloneFilePicker;
  window.openVoiceCloneAvatarPicker = openVoiceCloneAvatarPicker;
  window.clearVoiceUploads = clearVoiceUploads;
  window.toggleVoiceCloneRecording = toggleVoiceCloneRecording;
  window.playVoiceCloneRecording = playVoiceCloneRecording;
  window.clearVoiceCloneRecording = clearVoiceCloneRecording;
  window.sendVoiceCloneRecording = sendVoiceCloneRecording;
  window.addMediaLink = addMediaLink;
  window.autoGrow       = autoGrow;
  window.sendChat       = sendChat;
  window.openSupport    = openSupport;
  window.closeSupport   = closeSupport;
  window.sendSupport    = sendSupport;
  window.generateNow    = generateNow;
  window.openTelegramBot = openTelegramBot;
  window.openGeneratedContent = openGeneratedContent;
  window.openMusicInPlayer = openMusicInPlayer;
  window.playMusicTrack = playMusicTrack;
  window.playMusicTrackFromMessage = playMusicTrackFromMessage;
  window.playVoiceInCard = playVoiceInCard;
  window.playVideoInGenerationCard = playVideoInGenerationCard;
  window.toggleStudioAudioPlayer = toggleStudioAudioPlayer;
  window.PlayerManager = PlayerManager;
  window.animateGeneratedImage = animateGeneratedImage;
  window.editGeneratedVideo = editGeneratedVideo;
  window.openGenerationInfoDrawer = openGenerationInfoDrawer;
  window.closeGenerationInfoDrawer = closeGenerationInfoDrawer;
  window.expandHistorySection = expandHistorySection;
  window.clearCurrentUploadTarget = clearCurrentUploadTarget;
  window.pickVisualReference = pickVisualReference;
  window.sendVisualInteraction = sendVisualInteraction;
  window.openCharacterDetail = openCharacterDetail;
  window.closeCharacterDetail = closeCharacterDetail;
  window.playCharacterReferenceVideo = playCharacterReferenceVideo;
  window.deleteVisualReference = deleteVisualReference;
  window.deleteUserVoice = deleteUserVoice;
  window.closeResourceDeleteConfirm = closeResourceDeleteConfirm;
  window.openVisualPicker = openVisualPicker;
  window.openVideoVisualPicker = openVideoVisualPicker;
  window.closeVisualPicker = closeVisualPicker;
  window.openVisualCreateModal = openVisualCreateModal;
  window.closeVisualCreateModal = closeVisualCreateModal;
  window.updateVisualCreateDraft = updateVisualCreateDraft;
  window.pickVisualCreatePhoto = pickVisualCreatePhoto;
  window.removeVisualCreatePhoto = removeVisualCreatePhoto;
  window.saveVisualCreateDraft = saveVisualCreateDraft;
  window.openKlingEffectsCatalog = openKlingEffectsCatalog;

  S.openImageStylePanel = openImageStylePanel;
  S.closeImageStylePanel = closeImageStylePanel;
  S.pickImageStyleFromPanel = pickImageStyleFromPanel;
  S.toggleImageStyleInfo = toggleImageStyleInfo;
  S.openImageOptionMenu = openImageOptionMenu;
  S.onImageSeedInput = onImageSeedInput;
  S.toggleImageSeedTooltip = toggleImageSeedTooltip;
  S.resetImageSettings = resetImageSettings;
  S.openImageUpload = openImageUpload;
  S.openVideoStartUpload = openVideoStartUpload;
  S.openVideoEndUpload = openVideoEndUpload;
  S.openVideoReferencesUpload = openVideoReferencesUpload;
  S.openVideoEditInputUpload = openVideoEditInputUpload;
  S.toggleVideoAddMenu = toggleVideoAddMenu;
  S.closeVideoAddMenu = closeVideoAddMenu;
  S.chooseVideoAddMedia = chooseVideoAddMedia;
  S.chooseVideoAddCharacter = chooseVideoAddCharacter;
  S.chooseVideoAddObject = chooseVideoAddObject;
  S.clearCurrentUploadTarget = clearCurrentUploadTarget;
  S.pickVisualReference = pickVisualReference;
  S.sendVisualInteraction = sendVisualInteraction;
  S.openCharacterDetail = openCharacterDetail;
  S.closeCharacterDetail = closeCharacterDetail;
  S.playCharacterReferenceVideo = playCharacterReferenceVideo;
  S.deleteVisualReference = deleteVisualReference;
  S.deleteUserVoice = deleteUserVoice;
  S.closeResourceDeleteConfirm = closeResourceDeleteConfirm;
  S.openVisualPicker = openVisualPicker;
  S.openVideoVisualPicker = openVideoVisualPicker;
  S.closeVisualPicker = closeVisualPicker;
  S.openVisualCreateModal = openVisualCreateModal;
  S.closeVisualCreateModal = closeVisualCreateModal;
  S.updateVisualCreateDraft = updateVisualCreateDraft;
  S.pickVisualCreatePhoto = pickVisualCreatePhoto;
  S.removeVisualCreatePhoto = removeVisualCreatePhoto;
  S.saveVisualCreateDraft = saveVisualCreateDraft;
  S.pickImageOption = pickImageOption;
  S.pickMusicOption = pickMusicOption;
  S.pickVoiceOption = pickVoiceOption;
  S.resetMusicSettings = resetMusicSettings;
  S.openTelegramBot = openTelegramBot;
  S.openGeneratedContent = openGeneratedContent;
  S.openMusicInPlayer = openMusicInPlayer;
  S.playMusicTrack = playMusicTrack;
  S.playMusicTrackFromMessage = playMusicTrackFromMessage;
  S.playVoiceInCard = playVoiceInCard;
  S.playVideoInGenerationCard = playVideoInGenerationCard;
  S.toggleStudioAudioPlayer = toggleStudioAudioPlayer;
  S.PlayerManager = PlayerManager;
  S.audioPlayer = {
    open: (tracks, index) => PlayerManager.open((tracks || []).map((track) => ({
      audio_url: track.audio_url || track.audioUrl || track.url,
      cover_url: track.cover_url || track.coverUrl || track.image_url,
      title: track.title || 'Untitled Track',
      provider: track.provider || 'suno',
      model: track.model || '',
    })), index || 0),
    openOrToggle: (tracks, index) => PlayerManager.open((tracks || []).map((track) => ({
      audio_url: track.audio_url || track.audioUrl || track.url,
      cover_url: track.cover_url || track.coverUrl || track.image_url,
      title: track.title || 'Untitled Track',
      provider: track.provider || 'suno',
      model: track.model || '',
    })), index || 0),
    hide: () => PlayerManager.close(),
    isOpen: () => !!(PlayerManager.playerEl && PlayerManager.playerEl.classList.contains('is-visible')),
  };
  S.animateGeneratedImage = animateGeneratedImage;
  S.editGeneratedVideo = editGeneratedVideo;
  S.shareGenerationCard = shareGenerationCard;
  S.toggleGenerationPrompt = toggleGenerationPrompt;
  S.expandHistorySection = expandHistorySection;
  S.showImageModelPicker = showImageModelPicker;
  S.updateComposerMode = updateComposerMode;
  S.renderVideoControls = renderVideoControls;
  S.addMediaLink = addMediaLink;
  S.openVideoTemplatesCatalog = openVideoTemplatesCatalog;
  S.openKlingEffectsCatalog = openKlingEffectsCatalog;
  S.closeVideoTemplatesCatalog = closeVideoTemplatesCatalog;
  S.closeVideoTemplateModal = closeVideoTemplateModal;
  S.openVideoTemplateFromCatalog = openVideoTemplateFromCatalog;
  
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('pointerdown', handleImageStyleInfoOutsideTouch, true);
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('pointerdown', closeImageSeedTooltipOnOutside, true);
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('touchmove', hideImageStyleInfo, true);
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('wheel', hideImageStyleInfo, true);
  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('scroll', hideImageStyleInfo, true);

  })();
