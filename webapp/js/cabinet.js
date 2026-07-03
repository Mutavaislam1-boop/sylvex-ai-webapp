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
let imageCapabilities = [];
let generatedImageLibrary = [];
let uploadedImageLibrary = [];
let imageState = {
    modelId: '',
    size: '',
    count: 1,
    style: 'auto',
    character: 'auto',
    objects: '',
  };

  const IMAGE_MODEL_CATALOG = [
{ id:'nano-banana-pro', label:'Nano Banana Pro', icon:'🍌', description:'Фотореалистичные изображения, идеально подходящие для рекламы и текста.' },
{ id:'nano-banana-2', label:'Nano Banana 2', icon:'🍌', description:'Современная генерация изображений с расширенным редактированием и композицией.' },
{ id:'nano-banana', label:'Nano Banana', icon:'🍌', description:'Потрясающие фотореалистичные изображения для любой идеи.' },
{ id:'gpt-image-2', label:'GPT Image 2', icon:'◎', description:'Современная генерация изображений с реализмом, типографикой и контролем.' },
{ id:'seedream-5', label:'Seedream 5.0', icon:'▥', description:'Быстрая и лёгкая генерация с высоким визуальным качеством.' },
{ id:'seedream-4-5', label:'Seedream 4.5', icon:'▥', description:'Улучшенная эстетика и повышенная точность воспроизведения изображения.' },
{ id:'grok-pro', label:'Grok Pro', icon:'◒', description:'xAI Grok — генерация высококачественных изображений.' },
{ id:'davinci-ultra', label:'DaVinci Ultra', icon:'◩', description:'Модель DaVinci, оптимизированная для получения высококачественных результатов.' },
{ id:'grok', label:'Grok', icon:'◒', description:'Генерация изображений через модель Grok.' },
{ id:'flux-2', label:'Flux 2', icon:'△', description:'Быстрая генерация изображений в стиле Flux.' },
{ id:'flux-2-turbo', label:'Flux 2 Turbo', icon:'△', description:'Быстрая бюджетная генерация изображений.' },
{ id:'ideogram-3', label:'Ideogram 3.0', icon:'♨', description:'Генерация изображений с хорошей работой с текстом и постерами.' },
{ id:'ideogram-4', label:'Ideogram 4.0', icon:'♨', description:'Новая версия Ideogram для точного текста и визуальных композиций.' },
{ id:'recraft-v4-1', label:'Recraft V4.1', icon:'R', description:'Дизайн, иллюстрации, графика и брендовые изображения.' },
{ id:'recraft-v3', label:'Recraft V3', icon:'R', description:'Генерация графики, иллюстраций и рекламных визуалов.' },
{ id:'recraft-v4-1-pro', label:'Recraft V4.1 Pro', icon:'R', description:'Профессиональная версия Recraft для точной визуальной генерации.' },
{ id:'seedream-4', label:'Seedream 4.0', icon:'▥', description:'Качественная генерация изображений и визуальных сцен.' },
{ id:'gpt-image-1', label:'GPT Image 1', icon:'◎', description:'Генерация и редактирование изображений через OpenAI.' },
{ id:'flux-pro-kontext', label:'Flux Pro Kontext', icon:'△', description:'Модель Flux для точной работы с контекстом изображения.' },
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

  davinci: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4.5 19.5C5.1 12.6 10.4 5.2 19.5 4.5C18.8 13.5 11.4 18.9 4.5 19.5Z" fill="currentColor"/><path d="M4.8 19.2C8.1 15.7 11.5 12.6 16.2 9.5" stroke="#1a1a1a" stroke-width="1.4" stroke-linecap="round"/></svg>',

  grokFlux: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.2 18.5L11.6 4.8L20.8 18.5H3.2Z" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M7.9 18.5L11.7 12.1L15.8 18.5" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M18.3 5.2L19 6.8L20.6 7.5L19 8.2L18.3 9.8L17.6 8.2L16 7.5L17.6 6.8L18.3 5.2Z" fill="currentColor"/></svg>',

  idrm: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10.5 4.2C7.9 4.7 6 6.8 6 9.4V10.2H4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10.5 19.8C7.9 19.3 6 17.2 6 14.6V13.8H4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12.5 4.2C15.9 4.2 18.5 6.8 18.5 10.1C20 10.5 21 11.9 21 13.5C21 15.5 19.5 17.1 17.5 17.1H16.8C16.1 18.7 14.6 19.8 12.5 19.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M2.8 7.5H6.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M2.8 12H8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M2.8 16.5H6.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M12 7.2V16.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15 8.4V15.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',

  craft: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 20V4H12.3C15.8 4 18.1 6 18.1 9.1C18.1 11.5 16.8 13.2 14.7 13.9L19.2 20H15.1L11.2 14.4H8.5V20H5Z" fill="currentColor"/><path d="M8.5 11.5H12C13.5 11.5 14.4 10.6 14.4 9.3C14.4 8 13.5 7.2 12 7.2H8.5V11.5Z" fill="#1a1a1a"/></svg>',

  queen: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2.8L14.5 7.2L19.6 7.1L17.1 11.5L19.7 15.8L14.6 15.9L12 20.3L9.4 15.9L4.3 15.8L6.9 11.5L4.4 7.1L9.5 7.2L12 2.8Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M7 8.3L17 15.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M17 8.3L7 15.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',

  microsoft: '<svg class="model-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="3" width="8" height="8" fill="currentColor"/><rect x="13" y="3" width="8" height="8" fill="currentColor"/><rect x="3" y="13" width="8" height="8" fill="currentColor"/><rect x="13" y="13" width="8" height="8" fill="currentColor"/></svg>'
};

  function withImageDefaults(model) {
    return Object.assign({
      sizes: [
        { id:'1:1', label:'1:1', ratio:'1:1', icon:'1:1' },
        { id:'9:16', label:'9:16', ratio:'9:16', icon:'9:16' },
        { id:'16:9', label:'16:9', ratio:'16:9', icon:'16:9' }
      ],
      counts: [1, 2, 3, 4],
      styles: [{ id:'auto', label:'Авто' }],
      characters: [{ id:'auto', label:'Авто' }]
    }, model);
  }

  function mergeImageModels(apiModels) {
    const map = new Map();
    IMAGE_MODEL_CATALOG.map(withImageDefaults).forEach((model) => map.set(model.id, model));
    (apiModels || []).map(withImageDefaults).forEach((model) => {
      const old = map.get(model.id) || {};
      map.set(model.id, Object.assign({}, old, model));
    });
    return Array.from(map.values());
  }

  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      return u && u.id ? Number(u.id) : Number(S.user && S.user.telegram_id ? S.user.telegram_id : 0);
    } catch { return 0; }
  }

  function pickStudioModel() {
    if (studioMode === 'image') return imageState.modelId || 'gpt-image-1';
    if (studioMode === 'video') return 'seedance-2-fast';
    if (studioMode === 'music') return 'musicgen-pro';
    return /lite/i.test(currentModelLabel || '') ? 'sylvex-lite' : 'sylvex-pro';
  }

  function pickProviderHint() {
    const model = pickStudioModel();
    if (/^gpt-image|openai/i.test(model)) return 'openai';
    if (/grok/i.test(model)) return 'xai';
    if (/flux/i.test(model)) return 'flux';
    if (/ideogram/i.test(model)) return 'ideogram';
    if (/recraft/i.test(model)) return 'recraft';
    if (/qwen/i.test(model)) return 'qwen';
    if (/microsoft|mai/i.test(model)) return 'microsoft';
    if (/krea/i.test(model)) return 'krea';
    if (/seedream|seedance/i.test(model)) return 'bytedance';
    if (/musicgen/i.test(model)) return 'music';
    return 'sylvex-router';
  }

  function uiLang() {
    return (localStorage.getItem('sylvex-lang') || 'en').slice(0, 2);
  }

function localizedGreeting() {
  return '';
}

  /* ===== Rendering ===== */
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = '';
  }

  function renderModelPop() {
    const el = document.getElementById('modelPop'); if (!el) return;
    if (studioMode === 'image' && imageCapabilities.length) {
      el.innerHTML = '<div class="image-model-sheet-title">Выберите модель</div>'
        + '<div class="image-model-sheet-list">'
        + imageCapabilities.map(imageModelButton).join('')
        + '</div>';
      return;
    }
    el.innerHTML = '';
  }

  function showImageModelPicker(e) {
    if (e) e.stopPropagation();
    const el = document.getElementById('modelPop');
    if (!el) return;
    el.classList.remove('image-size-floating-pop');
    el.style.cssText = '';
    if (!imageCapabilities.length) {
      loadImageCapabilities().then(() => showImageModelPicker(e)).catch(() => {});
      return;
    }
    if (studioMode !== 'image') {
      studioMode = 'image';
      activeCat = 'image';
    }
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
      + imageCapabilities.map(imageModelButton).join('')
      + '</div>';
    el.classList.add('show');
    const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
    const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function currentImageModel() {
    return imageCapabilities.find((model) => model.id === imageState.modelId) || imageCapabilities[0] || null;
  }

  function optionLabel(options, id, fallback) {
    const opt = (options || []).find((item) => String(item.id) === String(id));
    return opt ? (opt.label || opt.id) : fallback;
  }


function imageModelIconKey(model) {
  const id = String(model && model.id ? model.id : '');

  if (id.includes('nano-banana')) return 'nn';
  if (id.includes('gpt-image')) return 'chatgptImage';
  if (id.includes('seedream')) return 'cdrm';
  if (id.includes('grok-pro')) return 'grokPro';
  if (id === 'grok') return 'grokPro';
  if (id.includes('davinci')) return 'davinci';
  if (id.includes('flux')) return 'grokFlux';
  if (id.includes('ideogram')) return 'idrm';
  if (id.includes('recraft')) return 'craft';
  if (id.includes('qwen')) return 'queen';
  if (id.includes('microsoft')) return 'microsoft';
  if (id.includes('krea')) return 'craft';

  return 'nn';
}

function imageModelIconHtml(model) {
  const key = imageModelIconKey(model);
  return MODEL_ICON_SVG[key] || MODEL_ICON_SVG.nn;
}

function imageModelDescription(model) {
  if (!model) return 'AI-модель для генерации изображений.';
  return model.description || model.desc || model.subtitle || model.note || 'AI-модель для генерации изображений.';
}

function imageModelButton(model) {
  const active = imageState.modelId === model.id;
  return '<button class="image-model-row ' + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickImageOption(event,\'model\',\'' + S.escapeHtml(model.id) + '\')">'
    + '<span class="image-model-icon">' + imageModelIconHtml(model) + '</span>'
    + '<span class="image-model-text">'
    + '<span class="image-model-name">' + S.escapeHtml(model.label || model.id) + '</span>'
    + '<span class="image-model-desc">' + S.escapeHtml(imageModelDescription(model)) + '</span>'
    + '</span>'
    + '<span class="image-model-check">✓</span>'
    + '</button>';
}

  function applyImageDefaults(model) {
    if (!model) return;
    imageState.modelId = model.id;
    imageState.size = (model.sizes && model.sizes[0] && model.sizes[0].id) || '';
    imageState.count = (model.counts && model.counts[0]) || 1;
    imageState.style = (model.styles && model.styles[0] && model.styles[0].id) || 'auto';
    imageState.character = (model.characters && model.characters[0] && model.characters[0].id) || 'auto';
  }

  function renderImageControls() {
    const model = currentImageModel();
    if (!model) return;
    const modelEl = document.getElementById('modelValComposer');
    if (modelEl && studioMode === 'image') modelEl.textContent = model.label || model.id;
    const sizeOptions = [
  { id:'1:1', label:'1:1', ratio:'1:1' },
  { id:'16:9', label:'16:9', ratio:'16:9' },
  { id:'9:16', label:'9:16', ratio:'9:16' },
  { id:'3:4', label:'3:4', ratio:'3:4' },
  { id:'4:5', label:'4:5', ratio:'4:5' },
  { id:'5:4', label:'5:4', ratio:'5:4' },
  { id:'4:3', label:'4:3', ratio:'4:3' },
  { id:'21:9', label:'21:9', ratio:'21:9' },
  { id:'auto', label:'Auto', ratio:'auto' }
];
const selectedSizeId = imageState.size || '1:1';
const size = sizeOptions.find((item) => item.id === selectedSizeId) || sizeOptions[0];
const sizeVal = document.getElementById('imageSizeVal');
if (sizeVal && size) sizeVal.textContent = size.label || size.ratio || size.id;
const sizeIcon = document.getElementById('imageSizeIcon');
if (sizeIcon && size) sizeIcon.setAttribute('data-ratio', size.ratio || size.id || '1:1');
    const countVal = document.getElementById('imageCountVal');
    if (countVal) countVal.textContent = String(imageState.count || 1);
    const styleVal = document.getElementById('imageStyleVal');
    if (styleVal) styleVal.textContent = imageState.style === 'auto' ? 'Стили' : optionLabel(model.styles, imageState.style, 'Стили');
    const characterVal = document.getElementById('imageCharacterVal');
    if (characterVal) characterVal.textContent = imageState.character === 'auto' ? 'Характер' : optionLabel(model.characters, imageState.character, 'Характер');
  }

  async function loadImageCapabilities() {
    try {
      const res = await fetch('/api/public/prostudio/image-capabilities', { cache: 'no-store' });
      const data = await res.json();
      imageCapabilities = mergeImageModels((data && data.models) || []);
      if (imageCapabilities.length && !imageState.modelId) applyImageDefaults(imageCapabilities[0]);
      renderImageControls();
      renderModelPop();
    } catch (err) {
      console.warn('[SYLVEX] image capabilities failed', err);
    }
  }

  function openImageOptionMenu(e, kind) {
    if (e) e.stopPropagation();

    if (kind === 'model') {
      showImageModelPicker(e);
      return;
    }

    if (kind === 'count') {
      const currentCount = Number(imageState.count || 1);
      const nextCount = currentCount >= 4 ? 1 : currentCount + 1;
      imageState.count = nextCount;
      renderImageControls();
      S.haptic && S.haptic.impact && S.haptic.impact('light');
      return;
    }

    const model = currentImageModel();
    const el = document.getElementById('modelPop');
    if (!el) return;

    el.classList.remove('image-model-floating-pop');
    el.classList.remove('image-size-floating-pop');

    if (kind === 'size') {
      const fallbackSizes = [
        { id:'1:1', label:'1:1', ratio:'1:1' },
        { id:'16:9', label:'16:9', ratio:'16:9' },
        { id:'9:16', label:'9:16', ratio:'9:16' },
        { id:'3:4', label:'3:4', ratio:'3:4' },
        { id:'4:5', label:'4:5', ratio:'4:5' },
        { id:'5:4', label:'5:4', ratio:'5:4' },
        { id:'4:3', label:'4:3', ratio:'4:3' },
        { id:'21:9', label:'21:9', ratio:'21:9' },
        { id:'auto', label:'Auto', ratio:'auto' }
      ];
      const selectedSize = imageState.size || imageState.ratio || '1:1';

      if (el.parentElement !== document.body) document.body.appendChild(el);
      el.classList.remove('image-model-floating-pop');
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
          return '<button class="image-size-row ' + (active ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickImageOption(event,\'size\',\'' + S.escapeHtml(id) + '\')">'
            + '<span class="image-size-icon" data-ratio="' + S.escapeHtml(id) + '"></span>'
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

  function pickImageOption(e, kind, value) {
    if (e) e.stopPropagation();
    if (kind === 'model') {
      const model = imageCapabilities.find((item) => item.id === value);
      if (model) applyImageDefaults(model);
    } else if (kind === 'count') {
      imageState.count = Number(value || 1);
    } else if (kind === 'size') {
      imageState.size = value;
    } else if (kind === 'style') {
      imageState.style = value;
    } else if (kind === 'character') {
      imageState.character = value;
    }
    renderImageControls();
    renderModelPop();
   const el = document.getElementById('modelPop'); if (el) { el.classList.remove('show'); el.classList.remove('image-model-floating-pop'); el.classList.remove('image-size-floating-pop'); el.style.cssText = ''; }
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
      if (m.images && m.images.length) {
        inner += '<div class="gen-img-grid">' + m.images.map((url) =>
          '<img class="gen-img" src="' + url + '" alt="generated" />'
        ).join('') + '</div>';
      }
      if (m.imageUrl && !(m.images && m.images.length)) inner += '<img class="gen-img" src="' + m.imageUrl + '" alt="generated" />';
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
    const mvc = document.getElementById('modelValComposer');
    if (mvc && currentModelLabel) mvc.textContent = currentModelLabel === 'SYLVEX Pro' ? 'Seedance 2.0 Fast' : currentModelLabel;
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
    showImageModelPicker(e);
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
    const mvc = document.getElementById('modelValComposer');
    if (mvc) mvc.textContent = label;
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

  function addGeneratedImages(urls) {
    const list = (urls || []).filter(Boolean);
    if (!list.length) return;
    list.forEach((url) => {
      if (!generatedImageLibrary.includes(url)) generatedImageLibrary.unshift(url);
    });
    generatedImageLibrary = generatedImageLibrary.slice(0, 40);
    renderUploadPanelImages();
  }

  function renderUploadPanelImages() {
    const grid = document.getElementById('uploadGeneratedGrid');
    if (!grid) return;

    if (!generatedImageLibrary.length) {
      grid.innerHTML = '';
      return;
    }

    const selectedUrl = imageState.referenceImageUrl || '';
    grid.innerHTML = generatedImageLibrary.map((url) => {
      const safeUrl = S.escapeHtml(url);
      const selected = selectedUrl === url;
      return '<button class="upload-generated-thumb ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.openUploadImagePreview(event,\'' + safeUrl + '\')">'
        + '<img src="' + safeUrl + '" alt="generated image" />'
        + '<span class="upload-thumb-check">✓</span>'
        + '</button>';
    }).join('');
  }

  function uploadPhotoButtonHtml() {
  if (uploadedImageLibrary.length >= 4) return '';

  if (!uploadedImageLibrary.length) {
    return '<button class="upload-photo-center-btn" type="button" onclick="SYLVEX.openNativeFilePicker(\'image\')">'
      + '<span class="upload-photo-center-icon" aria-hidden="true">'
      + '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
      + '<rect x="3.5" y="5" width="17" height="14" rx="3" stroke="currentColor" stroke-width="1.8"/>'
      + '<path d="M7 16L10.2 12.8C10.8 12.2 11.7 12.2 12.3 12.8L14 14.5L15.2 13.3C15.8 12.7 16.7 12.7 17.3 13.3L20 16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
      + '<circle cx="8.7" cy="9.3" r="1.3" fill="currentColor"/>'
      + '</svg>'
      + '</span>'
      + '<span class="upload-photo-center-title">Загрузить фото</span>'
      + '<span class="upload-photo-center-sub">из файлов или галереи</span>'
      + '</button>';
  }

  return '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'image\')" aria-label="Загрузить фото">'
    + '<span class="upload-photo-add-icon" aria-hidden="true">＋</span>'
    + '<span class="upload-photo-add-text">Загрузить</span>'
    + '</button>';
}

  function renderUploadedPhotoGrid() {
    const grid = document.getElementById('uploadPhotoGrid');
    if (!grid) return;

    grid.classList.toggle('empty', uploadedImageLibrary.length === 0);

    const chooseBtn = document.getElementById('uploadChoosePhotosBtn');
    if (chooseBtn) chooseBtn.hidden = uploadedImageLibrary.length === 0;

    const selectedUrl = imageState.referenceImageUrl || '';
    const items = uploadedImageLibrary.map((url, index) => {
      const safeUrl = S.escapeHtml(url);
      const selected = selectedUrl === url;
      return '<button class="upload-photo-thumb ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.selectUploadedPhoto(event,\'' + safeUrl + '\')">'
        + '<img src="' + safeUrl + '" alt="uploaded image" />'
        + '<span class="upload-thumb-check">✓</span>'
        + '<span class="upload-photo-remove" onclick="SYLVEX.removeUploadedPhoto(event,' + index + ')">×</span>'
        + '</button>';
    });

    const addButton = uploadPhotoButtonHtml();
    if (addButton) items.push(addButton);
    grid.innerHTML = items.join('');
  }

  function addUploadedPhoto(url) {
    if (!url) return;
    uploadedImageLibrary = uploadedImageLibrary.filter((item) => item !== url);
    uploadedImageLibrary.push(url);
    uploadedImageLibrary = uploadedImageLibrary.slice(0, 4);
    imageState.referenceImageUrl = url;
    imageState.referenceImageUrls = uploadedImageLibrary.slice();
    renderUploadedPhotoGrid();
  }

  function selectUploadedPhoto(e, url) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    imageState.referenceImageUrl = url;
    imageState.referenceImageUrls = uploadedImageLibrary.slice();
    renderUploadedPhotoGrid();
    toast('Фото выбрано');
  }

  function removeUploadedPhoto(e, index) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    uploadedImageLibrary.splice(index, 1);
    imageState.referenceImageUrls = uploadedImageLibrary.slice();
    imageState.referenceImageUrl = uploadedImageLibrary[uploadedImageLibrary.length - 1] || '';
    renderUploadedPhotoGrid();
  }

    function confirmUploadedPhotos(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }

    imageState.referenceImageUrls = uploadedImageLibrary.slice();
    imageState.referenceImageUrl = uploadedImageLibrary[uploadedImageLibrary.length - 1] || '';

    renderComposerImageDraft();
    closeUploadPanel(e);
    toast('Фото добавлены в сообщение');

    S.haptic && S.haptic.notify && S.haptic.notify('success');
    }

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

function renderComposerImageDraft() {
  const box = ensureComposerImageDraft();
  if (!box) return;

  const urls = imageState.referenceImageUrls || [];

  if (!urls.length) {
    box.innerHTML = '';
    box.hidden = true;
    return;
  }

  box.hidden = false;

  box.innerHTML = urls.map((url, index) => {
    const safeUrl = S.escapeHtml(url);

    return '<button class="composer-image-thumb" type="button">'
      + '<img src="' + safeUrl + '" alt="selected image" />'
      + '<span class="composer-image-remove" onclick="SYLVEX.removeComposerImageDraft(event,' + index + ')">×</span>'
      + '</button>';
  }).join('');
}

function removeComposerImageDraft(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const urls = (imageState.referenceImageUrls || []).slice();
  urls.splice(index, 1);

  imageState.referenceImageUrls = urls.slice();
  imageState.referenceImageUrl = urls[urls.length - 1] || '';

  uploadedImageLibrary = urls.slice();

  renderUploadedPhotoGrid();
  renderComposerImageDraft();
}

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

function selectGeneratedImage(e, url) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  addUploadedPhoto(url);
  renderUploadPanelImages();
  closeUploadImagePreview(e);

  toast('Фото добавлено в черновик');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

function openUploadPanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

const panel = ensureUploadPanel();
renderUploadPanelImages();
renderUploadedPhotoGrid();
panel.classList.add('show');

  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }

  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

function closeUploadPanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const panel = document.getElementById('uploadPanel');
  if (panel) panel.classList.remove('show');
}
  function openNativeFilePicker(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    const inp = document.getElementById('attachInput');
    if (!inp) return;
    if (kind === 'image') { inp.accept = 'image/*'; pendingAttachAccept = 'image'; }
    else { inp.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx'; pendingAttachAccept = 'file'; }
    inp.value = '';
    inp.click();
  }

  function attach(kind, e) {
    // Old upload button used to open the system file picker immediately.
    // Now it opens the large upload panel. File picker will be called from buttons inside that panel later.
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    openUploadPanel(e);
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

      if ((pendingAttachAccept || '') === 'image' && result) {
        addUploadedPhoto(result);
        toast('Фото загружено');
      }

      try { updateSendButton(); } catch {}
    };
    reader.readAsDataURL(f);
  }
  function clearAttachment() {
    pendingAttachment = null;
    try { updateSendButton(); } catch {}
  }
  function updateComposerMode(kind) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const isImage = kind === 'image';
    const isMusic = kind === 'music';
    const composer = document.getElementById('studioComposer');
    if (composer) composer.dataset.composerMode = isImage ? 'image' : isMusic ? 'music' : 'video';
    document.querySelectorAll('[data-studio-mode-btn]').forEach((btn) => {
      const isActive = btn.dataset.studioModeBtn === kind || (!isImage && !isMusic && kind === 'video' && btn.dataset.studioModeBtn === 'video');
      btn.classList.toggle('active', isActive);
    });
    document.querySelectorAll('.studio-mini-tab').forEach((btn) => btn.classList.remove('active'));
    const miniIndex = kind === 'image' ? 0 : isMusic ? 2 : 1;
    const minis = document.querySelectorAll('.studio-mini-tab');
    if (minis[miniIndex]) minis[miniIndex].classList.add('active');
    const ta = document.getElementById('chatInput');
    if (ta) ta.placeholder = isImage ? 'Describe your image' : isMusic ? 'Describe your music' : 'Describe your video';
    const mvc = document.getElementById('modelValComposer');
    if (isImage) {
      if (imageCapabilities.length && !imageState.modelId) applyImageDefaults(imageCapabilities[0]);
      renderImageControls();
      renderModelPop();
    } else if (mvc) {
      mvc.textContent = isMusic ? 'MusicGen Pro' : 'Seedance 2.0 Fast';
    }
  }
  function genAction(kind, tabKey) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    studioMode = kind;
    activeCat = studioMode;
    updateComposerMode(tabKey || studioMode);
    const labels = { image:'Generate Image', video:'Generate Video', music:'Generate Music' };
    toast(labels[kind] || kind);
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
      model: pickStudioModel(),
      provider: pickProviderHint(),
      image_options: studioMode === 'image' ? Object.assign({}, imageState) : null,
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
    document.body.classList.add('ai-generating');
    S.haptic.impact('light');
    try {
      const j = await callGenerate(v, attachment);
      chatMessages.pop();
      if (j.type === 'image') {
        const generatedUrls = (j.images && j.images.length) ? j.images : (j.image_url ? [j.image_url] : []);
        addGeneratedImages(generatedUrls);
        chatMessages.push({ role: 'ai', text: '', imageUrl: j.image_url, images: j.images || null });
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
    } finally {
      document.body.classList.remove('ai-generating');
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
          ? { role: 'ai', text: '', imageUrl: j.image_url, images: j.images || null }
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
    chatMessages = [];
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
      if (!chatMessages.length) chatMessages = [];
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
  function applyTheme(themeId, persist = true) {
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
    if (id) applyTheme(id, false);
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
    if (!ta || !send) return;
    const has = (ta.value || '').trim().length > 0 || !!pendingAttachment;
    if (mic && !send.classList.contains('studio-generate')) mic.hidden = has;
    if (send.classList.contains('studio-generate')) {
      send.disabled = !has;
      send.hidden = false;
    } else {
      send.hidden = !has;
    }
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
    // Force bottom composer model button to open the image model picker.
    const composerModelVal = document.getElementById('modelValComposer');
    const composerRoot = document.getElementById('studioComposer');
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
      const mp = document.getElementById('modelPop'); if (mp) { mp.classList.remove('show'); mp.classList.remove('image-model-floating-pop'); mp.classList.remove('image-size-floating-pop'); mp.style.cssText = ''; }
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
    if (!chatMessages.length) chatMessages = [];
    renderChat();
    updateSendButton();
    loadImageCapabilities();
    handlePaymentReturnFromUrl();
    applyStoredTheme();
    applyInitialViewFromUrl();
    setTimeout(applyInitialViewFromUrl, 150);

    if (S.syncUser) {
      Promise.resolve(S.syncUser()).finally(() => {
        renderSubscription();
      });
    }
    loadConversations();
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, pickModelKey, toggleModelPop, togglePlusPop, closePlusSheet,
    openImageOptionMenu, showImageModelPicker, pickImageOption,
    attach, openNativeFilePicker, onAttachFile, clearAttachment, openUploadPanel, closeUploadPanel, openUploadImagePreview, closeUploadImagePreview, selectGeneratedImage, selectUploadedPhoto, removeUploadedPhoto, confirmUploadedPhotos, removeComposerImageDraft, genAction, toggleHistory, autoGrow, toggleMic,
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
  window.openImageOptionMenu = openImageOptionMenu;
  window.showImageModelPicker = showImageModelPicker;
  window.togglePlusPop  = togglePlusPop;
  window.attach         = attach;
  window.openNativeFilePicker = openNativeFilePicker;
  window.autoGrow       = autoGrow;
  window.sendChat       = sendChat;
  window.openSupport    = openSupport;
  window.closeSupport   = closeSupport;
  window.sendSupport    = sendSupport;
  window.generateNow    = generateNow;
})();
