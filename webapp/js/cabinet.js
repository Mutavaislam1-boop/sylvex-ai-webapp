// Cabinet controller: wires DOM events, renders dynamic content, manages
// Pro Studio chat workspace, support modal, hero carousel, pricing logic.
(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});
  console.log("CABINET JS NEW VERSION 11.07.2026");
  // Pro Studio state.
  let studioMode = 'pro';
  let activeCat = null;
  let chatMessages = [];
  let currentConvId = null;
  let conversationsCache = [];
  const CHAT_SPACE_TYPES = ['image', 'video', 'music', 'voice'];
  const chatSpaces = {
    image: { activeChatId: null, conversationId: null, messages: [] },
    video: { activeChatId: null, conversationId: null, messages: [] },
    music: { activeChatId: null, conversationId: null, messages: [] },
    voice: { activeChatId: null, conversationId: null, messages: [] },
  };
  const chatCollections = {
    image: [],
    video: [],
    music: [],
    voice: [],
  };
  const expandedHistorySections = {};
  const activeGenerationWatchers = new Set();
  const openingConversations = new Set();
  let restoringChatSpace = false;
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
  imageUrl: '',
  motionPreset: '',
  videoTemplate: null,
  referenceImageUrl: '',
  referenceImageUrls: [],
  uploadedImageUrls: [],
  attachment: null,
  advanced: {},
};
let videoUploadTarget = 'reference';
const UPLOAD_TARGETS = {
  IMAGE_UPLOAD: 'image_upload',
  VIDEO_START: 'video_start',
  VIDEO_END: 'video_end',
  VIDEO_REFERENCES: 'video_references',
};
let currentUploadTarget = UPLOAD_TARGETS.IMAGE_UPLOAD;
let activeUploadTarget = UPLOAD_TARGETS.IMAGE_UPLOAD;
let videoTemplatesCache = null;
let activeVideoTemplate = null;
let videoTemplateUploadUrl = '';
let videoTemplateRatio = '16:9';
const VIDEO_TEMPLATE_INTRO_KEY = 'sylvex_video_templates_intro_seen';

function setUploadTarget(target) {
  activeUploadTarget = Object.values(UPLOAD_TARGETS).includes(target) ? target : UPLOAD_TARGETS.IMAGE_UPLOAD;
  currentUploadTarget = activeUploadTarget;

  if (activeUploadTarget === UPLOAD_TARGETS.VIDEO_START) {
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

function getUploadTarget() {
  const panel = document.getElementById('uploadPanel');
  const target = (panel && panel.dataset && panel.dataset.uploadTarget) || activeUploadTarget || currentUploadTarget || UPLOAD_TARGETS.IMAGE_UPLOAD;
  return Object.values(UPLOAD_TARGETS).includes(target) ? target : UPLOAD_TARGETS.IMAGE_UPLOAD;
}
let videoModelSettings = {};
let activeImageStylePanelKind = 'style';

let musicState = {
  modelId: 'suno_chirp_5',
  uploads: [],
  attachment: null,
  genre: 'auto',
  duration: '',
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

let voiceState = {
  modelId: 'voice-default',
  uploads: [],
  attachment: null,
  genre: '',
  duration: '',
  style: '',
  voice: '',
  audioSettings: {},
};

let textState = {
  modelId: 'gpt-4o-mini',
};

let serverVisualItems = {
  characters: [],
  objects: [],
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
  heygen: LOBE_ICON_BASE + '/runway.svg',
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
  gpt_image_1: { character: false, object: false, seed: false },
  qwen_image: { character: false, object: false, seed: false },
  qwen_image_2: { character: false, object: false, seed: true },
  qwen_image_2_pro: { character: false, object: false, seed: true },
  krea_2: { character: false, object: false },
  microsoft_mai_image_2_5: { character: false, object: false },
};

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

function isGrokImageModel(modelId) {
  const raw = String(modelId || '').trim().replace(/-/g, '_');
  return raw === 'grok' || raw === 'grok_pro';
}

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

const PRESET_CHARACTERS = [
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
].map((item, index) => ({
  id: item[0],
  name: item[1],
  gender: item[2],
  previewUrl: presetSvg(item[1], 18 + index * 23),
  referenceImages: [presetSvg(item[1] + ' F', 18 + index * 23), presetSvg(item[1] + ' L', 42 + index * 23), presetSvg(item[1] + ' R', 66 + index * 23)],
  type: 'preset',
  status: 'ready',
}));

const PRESET_OBJECTS = [
  ['object_moka_pot', 'Moka Pot', 'Classic moka pot'],
  ['object_toaster', 'Toaster', 'Chrome toaster'],
  ['object_book', 'Book', 'Hardcover book'],
  ['object_lipstick', 'Lipstick', 'Red lipstick'],
  ['object_matcha_set', 'Matcha Set', 'Ceramic matcha set'],
  ['object_earpods', 'Earpods', 'Wireless earpods'],
  ['object_stilettos', 'Stilettos', 'Elegant stilettos'],
  ['object_water_bottle', 'Water Bottle', 'Minimal water bottle'],
  ['object_bag', 'Bag', 'Beige canvas tote bag'],
].map((item, index) => ({
  id: item[0],
  name: item[1],
  description: item[2],
  previewUrl: presetSvg(item[1], 190 + index * 17),
  referenceImages: [presetSvg(item[1] + ' A', 190 + index * 17), presetSvg(item[1] + ' B', 208 + index * 17), presetSvg(item[1] + ' C', 226 + index * 17)],
  type: 'preset',
  status: 'ready',
}));

const MUSIC_MODEL_LIST = [
  { id:'suno_chirp_3_5', label:'Suno Chirp v3.5', providerModel:'chirp-v3-5', desc:'Suno music generation', icon:'suno' },
  { id:'suno_chirp_4_0', label:'Suno Chirp v4.0', providerModel:'chirp-v4-0', desc:'Suno music generation', icon:'suno' },
  { id:'suno_chirp_4_5', label:'Suno Chirp v4.5', providerModel:'chirp-v4-5', desc:'Suno music generation', icon:'suno' },
  { id:'suno_chirp_5', label:'Suno Chirp v5', providerModel:'chirp-v5', desc:'Suno music generation', icon:'suno' },
  { id:'suno_chirp_5_5', label:'Suno Chirp v5.5', providerModel:'chirp-v5-5', desc:'Suno music generation', icon:'suno' },
];

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
  { id:'minimax_hailuo_2_3', label:'Минимакс Хайлуо 2.3', desc:'MiniMax Hailuo video', icon:'hailuo' },
  { id:'pixverse_v6', label:'PixVerse v6', desc:'PixVerse video model', icon:'pixverse' },

  { id:'sora_2_pro', label:'Sora 2 Про', desc:'OpenAI Sora video', icon:'sora' },
  { id:'wan_2_7', label:'Ван 2.7', desc:'Alibaba Wan video model', icon:'wan' },
  { id:'veo_3_1', label:'Veo 3.1', desc:'Google Veo video model', icon:'veo', badge:'РЕКОМЕНДУЕМЫЙ', badgeClass:'pink' },
  { id:'grok_video_edit', label:'Видеомонтаж Grok', desc:'xAI Grok video editing', icon:'grok' },
  { id:'wan_2_7_edit', label:'WAN 2.7 Редактировать', desc:'Wan video editing model', icon:'wan' },

  { id:'runway_aleph', label:'Взлетно-посадочная полоса Aleph', desc:'Runway video model', icon:'runway' },
  { id:'kling_3_0_turbo', label:'Kling 3.0 Turbo', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_motion_2_6', label:'Kling Motion 2.6', desc:'Kling AI video model', icon:'kling' },
  { id:'kling_motion_3_0', label:'Kling Motion 3.0', desc:'Kling AI video model', icon:'kling' },
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
  { id:'wan_2_6', label:'Ван 2.6', desc:'Alibaba Wan video model', icon:'wan' },

  { id:'seedance_2_fast', label:'Seedance 2.0 Fast', desc:'ByteDance Seedance fast video', icon:'seedance', badge:'БЫСТРЫЙ', badgeClass:'yellow' },
  { id:'seedance_2_0', label:'Seedance 2.0', desc:'ByteDance Seedance video', icon:'seedance', badge:'В ТРЕНДЕ', badgeClass:'pink' },
  { id:'kling_o3_omni', label:'Kling 3.0 Omni', desc:'Kling Omni video model', icon:'kling', badge:'ГОРЯЧИЙ', badgeClass:'red' },
  { id:'gemini_omni_flash', label:'Gemini Omni Flash', desc:'Google Gemini video model', icon:'gemini' },
  { id:'sora_2', label:'Sora 2', desc:'OpenAI Sora video', icon:'sora' },

  { id:'grok_video', label:'Грок', desc:'xAI Grok video model', icon:'grok', badge:'БЮДЖЕТНЫЙ', badgeClass:'green' },
  { id:'veo_3_1_fast', label:'Veo 3.1 Fast', desc:'Google Veo fast video', icon:'veo', badge:'БЫСТРЫЙ', badgeClass:'yellow' },
  { id:'runway_gen', label:'Взлетно-посадочная полоса Gen', desc:'Runway generation model', icon:'runway' },
  { id:'kling_3_0', label:'Kling 3.0', desc:'Kling video model', icon:'kling', badge:'СКИДКА', badgeClass:'green' }
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
  pixverse_v6: { provider:'pixverse', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  sora_2_pro: { provider:'sora', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  wan_2_7: { provider:'wan', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  veo_3_1: { provider:'veo', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p','1080p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  grok_video_edit: { provider:'grok', modes:['video_edit'], durations:[5], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:false, end_image:false, video_upload:true, video_edit:true },
  wan_2_7_edit: { provider:'wan', modes:['video_edit'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:false, end_image:false, video_upload:true, video_edit:true },
  runway_aleph: { provider:'runway', modes:['video_edit','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:true, video_upload:true, video_edit:true },
  seedance_1_5_pro: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p','1080p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  wan_2_6: { provider:'wan', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:false, start_image:true, end_image:false, video_upload:false, video_edit:false },
  seedance_2_fast: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  seedance_2_0: { provider:'bytedance', modes:['text_to_video','image_to_video'], durations:[4,5,6,7,8,9,10,11,12,13,14,15], ratios:['adaptive','16:9','4:3','1:1','3:4','9:16','21:9'], resolutions:['720p','480p','1080p'], sound:true, start_image:true, end_image:false, video_input:true, video_upload:true, video_edit:false },
  gemini_omni_flash: { provider:'gemini', modes:['text_to_video','image_to_video','video_edit'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:true, video_edit:true },
  sora_2: { provider:'sora', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  grok_video: { provider:'grok', modes:['text_to_video'], durations:[5], ratios:['16:9','9:16','1:1'], resolutions:['720p'], sound:true, start_image:false, end_image:false, video_upload:false, video_edit:false },
  veo_3_1_fast: { provider:'veo', modes:['text_to_video','image_to_video'], durations:[5,8], ratios:['16:9','9:16'], resolutions:['720p'], sound:true, start_image:true, end_image:false, video_upload:false, video_edit:false },
  runway_gen: { provider:'runway', modes:['text_to_video','image_to_video'], durations:[5,10], ratios:['16:9','9:16','1:1'], resolutions:['720p','1080p'], sound:false, start_image:true, end_image:true, video_upload:false, video_edit:false }
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
  kling_motion_3_0: { provider:'kling', modes:['motion_control'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_STANDARD_RESOLUTIONS, sound:false, motion_control:true, start_image:true, end_image:false, video_upload:true, video_edit:false },
  kling_o3_omni: { provider:'kling', modes:['text_to_video','image_to_video','video_edit'], durations:KLING_VIDEO_LONG_DURATIONS, ratios:KLING_VIDEO_BASE_RATIOS, resolutions:KLING_VIDEO_FULL_RESOLUTIONS, sound:true, native_audio:true, omni:true, video_input:true, start_image:true, end_image:true, video_upload:true, video_edit:true },
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

function currentVideoModel() {
  return VIDEO_MODELS.find((item) => item.id === videoState.modelId) || VIDEO_MODELS[0];
}

function isImageMode() {
  return studioMode === 'image' || activeCat === 'image';
}

function isVideoMode() {
  return studioMode === 'video' || activeCat === 'video';
}

function isMusicMode() {
  return studioMode === 'music' || activeCat === 'music';
}

function isVoiceMode() {
  return studioMode === 'voice' || activeCat === 'voice';
}

function currentAudioState() {
  if (isVoiceMode()) return voiceState;
  return musicState;
}

function currentVideoConfig() {
  return VIDEO_MODEL_CONFIG[videoState.modelId] || VIDEO_MODEL_CONFIG.seedance_2_fast;
}

function currentVideoProvider() {
  const config = currentVideoConfig();
  return (config && config.provider) || 'sylvex-router';
}

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

function saveCurrentVideoModelSettings() {
  if (!videoState.modelId) return;
  videoModelSettings[videoState.modelId] = videoModelSettingsSnapshot();
}

function restoreVideoModelSettings(modelId) {
  const saved = videoModelSettings[modelId || videoState.modelId];
  if (saved) {
    Object.assign(videoState, saved);
  }
  normalizeVideoStateForModel();
}

function normalizeVideoStateForModel() {
  const config = currentVideoConfig();
  if (!config) return;
  const modes = config.modes || ['text_to_video'];
  const durations = config.durations || [5];
  const ratios = config.ratios || ['16:9'];
  const resolutions = config.resolutions || ['720p'];

  videoState.provider = config.provider || videoState.provider || 'sylvex-router';
  if (!modes.includes(videoState.generationMode)) videoState.generationMode = modes[0] || 'text_to_video';
  videoState.mode = videoState.generationMode;
  if (!durations.includes(Number(videoState.duration))) videoState.duration = durations[0] || 5;
  if (!ratios.includes(videoState.ratio)) videoState.ratio = ratios[0] || '16:9';
  if (!resolutions.includes(videoState.resolution)) videoState.resolution = resolutions[0] || '720p';
  if (!config.sound) videoState.sound = false;
}

function labelItems(values, suffix) {
  return (values || []).map((value) => {
    const id = String(value);
    return { id, label: suffix ? id + ' ' + suffix : id };
  });
}

function videoOptionsPayload(referenceImagesOverride) {
  normalizeVideoStateForModel();
  const config = currentVideoConfig() || {};
  const referenceImages = Array.isArray(referenceImagesOverride)
    ? referenceImagesOverride.slice()
    : (videoState.referenceImageUrls || []).slice();

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
    input_video: videoState.inputVideo || '',
    video_url: videoState.videoUrl || '',
    image_url: '',
    motion_preset: videoState.motionPreset || '',
    video_template: videoState.videoTemplate || null,
    character_image: videoState.characterImage || '',
    model: videoState.modelId || '',
    native_audio: !!(config.native_audio && videoState.sound),
    motion_control: !!config.motion_control,
    video_input: !!(config.video_input || config.video_upload || videoState.inputVideo || videoState.videoUrl),
    avatar: !!config.avatar,
    lip_sync: !!config.lip_sync,
    multi_image: !!config.multi_image,
    multi_element_editing: !!config.multi_element_editing,
    video_extension: !!config.video_extension,
    advanced: Object.assign({}, videoState.advanced || {}, {
      native_audio: !!(config.native_audio && videoState.sound),
      motion_control: !!config.motion_control,
      video_input: !!(config.video_input || config.video_upload || videoState.inputVideo || videoState.videoUrl),
      avatar: !!config.avatar,
      lip_sync: !!config.lip_sync,
      multi_image: !!config.multi_image,
      multi_element_editing: !!config.multi_element_editing,
      video_extension: !!config.video_extension,
    }),
  };
}

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

function renderVideoControls() {
  normalizeVideoStateForModel();
  const model = currentVideoModel();

  const modelEl = document.getElementById('modelValComposer');
  if (modelEl && isVideoMode() && model) {
    modelEl.textContent = model.label || model.name || model.id;
  }

  const sizeVal = document.getElementById('imageSizeVal');
  if (sizeVal) sizeVal.textContent = videoOptionLabel('ratio', videoState.ratio);

  const sizeIcon = document.getElementById('imageSizeIcon');
  if (sizeIcon) sizeIcon.setAttribute('data-ratio', videoState.ratio || '16:9');

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
}

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

function currentComposerModelList() {
  if (isImageMode()) return IMAGE_MODEL_LIST;
  if (isVideoMode()) return VIDEO_MODELS;
  if (isMusicMode()) return MUSIC_MODEL_LIST;
  return [];
}

function musicOptionLabel(items, id, fallback) {
  const value = String(id || 'auto');
  const item = (items || []).find((entry) => String(entry.id) === value);
  return item ? (item.label || item.id) : fallback;
}

function currentMusicModel() {
  return MUSIC_MODEL_LIST.find((item) => item.id === musicState.modelId) || MUSIC_MODEL_LIST[0] || null;
}

function ensureMusicSettings() {
  if (!musicState.settings || typeof musicState.settings !== 'object') musicState.settings = {};
  Object.keys(MUSIC_SETTINGS).forEach((key) => {
    if (!musicState.settings[key]) musicState.settings[key] = 'auto';
  });
  if (!musicState.genre) musicState.genre = 'auto';
  if (!musicState.modelId && MUSIC_MODEL_LIST.length) musicState.modelId = MUSIC_MODEL_LIST[0].id;
}

function musicOptionsPayload() {
  ensureMusicSettings();
  return {
    model: musicState.modelId,
    genre: musicState.genre || 'auto',
    mood: musicState.settings.mood || 'auto',
    tempo: musicState.settings.tempo || 'auto',
    theme: musicState.settings.theme || 'auto',
    vocal: musicState.settings.vocal || 'auto',
  };
}

function imageVisualReferenceOptions() {
  const character = selectedImageCharacter();
  const object = selectedImageObject();
  return {
    characterId: character ? character.id : null,
    characterName: character ? character.name : '',
    characterReferences: character ? (character.referenceImages || []).slice() : [],
    objectId: object ? object.id : null,
    objectName: object ? object.name : '',
    objectReferences: object ? (object.referenceImages || []).slice() : [],
  };
}

function renderMusicControls() {
  ensureMusicSettings();
  const model = currentMusicModel();
  const modelEl = document.getElementById('modelValComposer');
  if (modelEl && isMusicMode() && model) modelEl.textContent = model.label || model.name || model.id;

  const genreVal = document.getElementById('musicGenreVal');
  if (genreVal) genreVal.textContent = musicOptionLabel(MUSIC_GENRES, musicState.genre, 'Auto');

  const moodVal = document.getElementById('musicMoodVal');
  if (moodVal) moodVal.textContent = musicOptionLabel(MUSIC_SETTINGS.mood.items, musicState.settings.mood, 'Авто');

  const settingsVal = document.getElementById('musicSettingsVal');
  if (settingsVal) {
    const selected = ['mood', 'tempo', 'theme', 'vocal']
      .map((key) => musicState.settings[key])
      .filter((value) => value && value !== 'auto').length;
    settingsVal.textContent = selected ? 'Настройки ' + selected : 'Настройки';
  }
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

  function getTelegramId() {
    try {
      const tg = S.tg;
      const u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      return u && u.id ? Number(u.id) : Number(S.user && S.user.telegram_id ? S.user.telegram_id : 0);
    } catch { return 0; }
  }

  function pickStudioModel() {
    if (isImageMode()) {
      return imageState.modelId || (IMAGE_MODEL_LIST[0] && IMAGE_MODEL_LIST[0].id) || 'ideogram_3_0';
    }
    if (isVideoMode()) {
      return videoState.modelId || 'seedance_2_fast';
    }
    if (studioMode === 'music') return musicState.modelId || 'suno_chirp_5';
    if (studioMode === 'voice') return voiceState.modelId || 'voice-default';
    return textState.modelId || 'gpt-4o-mini';
  }

  function providerHintForModel(model) {
    if (/seedream|seedance/i.test(model)) return 'bytedance';
    if (/^gpt[_-]?image|openai/i.test(model)) return 'openai';
    if (/sora/i.test(model)) return 'sora';
    if (/grok/i.test(model)) return 'xai';
    if (/nano[_-]?banana|imagen|gemini/i.test(model)) return 'google';
    if (/flux/i.test(model)) return 'flux';
    if (/ideogram/i.test(model)) return 'ideogram';
    if (/recraft/i.test(model)) return 'recraft';
    if (/qwen/i.test(model)) return 'qwen';
    if (/microsoft|mai/i.test(model)) return 'microsoft';
    if (/krea/i.test(model)) return 'krea';
    if (/suno|chirp/i.test(model)) return 'suno';
    if (/musicgen/i.test(model)) return 'music';
    if (/voice/i.test(model)) return 'voice';
    if (/^gpt-|^o[0-9]|chatgpt/i.test(model)) return 'openai';
    return 'sylvex-router';
  }

  function pickProviderHint() {
    return providerHintForModel(pickStudioModel());
  }

  function uiLang() {
    return (localStorage.getItem('sylvex-lang') || 'en').slice(0, 2);
  }

function localizedGreeting() {
  return '';
}

  function chatTypeForMode(mode) {
    if (mode === 'edit' || mode === 'motion') return 'video';
    if (CHAT_SPACE_TYPES.includes(mode)) return mode;
    if (isImageMode()) return 'image';
    if (isVideoMode()) return 'video';
    if (isMusicMode()) return 'music';
    if (isVoiceMode()) return 'voice';
    return 'video';
  }

  function currentChatType() {
    return chatTypeForMode(studioMode);
  }

  function chatStorageKey(type) {
    return 'sylvex-prostudio-chat-' + (getTelegramId() || 'anon') + '-' + chatTypeForMode(type);
  }

  function lastModeStorageKey() {
    return 'sylvex-prostudio-last-mode-' + (getTelegramId() || 'anon');
  }

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

  function latestConversationForType(type) {
    const normalized = chatTypeForMode(type);
    return ((chatCollections && chatCollections[normalized]) || []).find(Boolean) || null;
  }

  function syncChatCollections(conversations) {
    CHAT_SPACE_TYPES.forEach((type) => {
      chatCollections[type] = [];
    });
    (conversations || []).forEach((conversation) => {
      const type = chatTypeForMode(conversation.type || conversation.mode || conversation.category || 'image');
      if (chatCollections[type]) chatCollections[type].push(conversation);
    });
  }

  function restoreChatSpace(type) {
    const normalized = chatTypeForMode(type);
    if (!chatSpaces[normalized]) return;
    loadStoredChatSpace(normalized);
    currentConvId = chatSpaces[normalized].activeChatId || chatSpaces[normalized].conversationId || null;
    chatMessages = (chatSpaces[normalized].messages || []).slice();
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

  function savedInitialStudioMode() {
    try {
      const saved = localStorage.getItem(lastModeStorageKey());
      return CHAT_SPACE_TYPES.includes(saved) ? saved : '';
    } catch {
      return '';
    }
  }

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

  function isActiveGenerationStatus(status) {
    return ['queued', 'submitted', 'running', 'processing', 'provider_processing', 'waiting', 'pending'].includes(String(status || '').toLowerCase());
  }

  function restoreActiveGenerationJobs(jobs) {
    (jobs || []).forEach((job) => {
      if (!job || !job.id || !isActiveGenerationStatus(job.status)) return;
      watchGenerationJob(job.id, job);
    });
  }

  function watchGenerationJob(jobId, jobInfo) {
    if (!jobId || activeGenerationWatchers.has(jobId)) return;
    activeGenerationWatchers.add(jobId);
    waitGeneration(jobId)
      .then((result) => {
        activeGenerationWatchers.delete(jobId);
        const convId = (result && result.conversation_id) || (jobInfo && jobInfo.conversation_id) || '';
        loadConversations();
        if (convId && (!currentConvId || currentConvId === convId)) {
          openConv(convId, chatTypeForMode((jobInfo && jobInfo.mode) || (result && result.type) || currentChatType()), { silent: true });
        }
      })
      .catch((err) => {
        activeGenerationWatchers.delete(jobId);
        console.warn('[SYLVEX] generation watcher failed', jobId, err);
      });
  }

  function applyCurrentDraft() {
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

  async function saveVisualItemToBackend(kind, item) {
    const tg = getTelegramId();
    if (!tg || !item) return item;
    try {
      const res = await fetch('/api/public/prostudio/resources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, item, {
          telegram_id: tg,
          resource_type: kind === 'character' ? 'character' : 'object',
          photos: item.referenceImages || [],
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
  function renderModeStrip() {
    const el = document.getElementById('modeStrip'); if (!el) return;
    el.innerHTML = '';
  }

  function renderModelPop() {
    const el = document.getElementById('modelPop');
    if (!el) return;

    const models = currentComposerModelList();

    if ((isImageMode() || isVideoMode() || isMusicMode()) && models.length) {
      el.innerHTML = '<div class="image-model-sheet-title">Выберите модель</div>'
        + '<div class="image-model-sheet-list">'
        + models.map(imageModelButton).join('')
        + '</div>';
      return;
    }

    el.innerHTML = '';
  }

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

  function currentImageModel() {
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

  function customVisualKey(kind) {
    return 'sylvex-prostudio-' + kind + '-' + (getTelegramId() || 'anon');
  }

  function loadCustomVisualItems(kind) {
    const serverItems = serverVisualItems && Array.isArray(serverVisualItems[kind])
      ? serverVisualItems[kind]
      : [];
    try {
      const raw = localStorage.getItem(customVisualKey(kind));
      const list = raw ? JSON.parse(raw) : [];
      const localItems = Array.isArray(list) ? list.filter((item) => item && item.id && item.previewUrl) : [];
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

  function saveCustomVisualItems(kind, items) {
    try {
      localStorage.setItem(customVisualKey(kind), JSON.stringify((items || []).slice(0, 50)));
    } catch {}
  }

  function imageCharacters() {
    return loadCustomVisualItems('characters').concat(PRESET_CHARACTERS);
  }

  function imageObjects() {
    return loadCustomVisualItems('objects').concat(PRESET_OBJECTS);
  }

  function selectedImageCharacter() {
    return imageCharacters().find((item) => item.id === imageState.characterId) || null;
  }

  function selectedImageObject() {
    return imageObjects().find((item) => item.id === imageState.objectId) || null;
  }

  function clearSelectedCharacter() {
    imageState.characterId = null;
    imageState.characterName = '';
    imageState.characterReferences = [];
  }

  function clearSelectedObject() {
    imageState.objectId = null;
    imageState.objectName = '';
    imageState.objectReferences = [];
    imageState.objects = '';
  }

  function syncImageFeatureAvailability() {
    const caps = getModelCapabilities(imageState.modelId);
    if (!caps.character && imageState.characterId) clearSelectedCharacter();
    if (!caps.object && imageState.objectId) clearSelectedObject();
    return caps;
  }

  function imageFeatureUnavailableToast(feature) {
    const label = feature === 'character' ? 'персонажей' : 'объекты';
    toast('Выбранная AI-модель не поддерживает ' + label + '.');
  }

  function ensureImageReferenceSections() {
    let wrap = document.getElementById('imageReferenceSections');
    if (wrap) wrap.remove();
    return null;
  }

  function renderImageReferenceSections() {
    ensureImageReferenceSections();
    const caps = syncImageFeatureAvailability();
    const character = selectedImageCharacter();
    const object = selectedImageObject();

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
    }

    const objectVal = document.getElementById('imageObjectVal');
    if (objectVal) {
      objectVal.textContent = caps.object
        ? (object ? object.name : 'Объект')
        : 'Недоступно для выбранной модели';
      setButtonState(objectVal, !caps.object);
    }
  }

  function nextImageCountValue() {
    const counts = [1, 2, 3, 4];
    const currentCount = Number(imageState.count || 1);
    const currentIndex = counts.findIndex((item) => Number(item) === currentCount);
    const safeIndex = currentIndex >= 0 ? currentIndex : 0;
    return Number(counts[(safeIndex + 1) % counts.length] || 1);
  }

  function optionLabel(options, id, fallback) {
    const value = String(id || '');

    const styleOpt = (typeof IMAGE_STYLE_SHEET_ITEMS !== 'undefined')
      ? IMAGE_STYLE_SHEET_ITEMS.find((item) => String(item.id) === value)
      : null;

    if (styleOpt) {
      return styleOpt.label || styleOpt.id;
    }

    const opt = (options || []).find((item) => String(item.id) === value);

    return opt ? (opt.label || opt.id) : fallback;
  }

  function imageStyleSheetItem(id) {
    const value = String(id || '');
    return IMAGE_STYLE_SHEET_ITEMS.find((item) => String(item.id) === value) || null;
  }

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

function renderUploadPreviewOnButton(button, urls) {
  if (!button) return;
  const clean = (urls || []).filter(Boolean).slice(0, 4);
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
  bg.innerHTML = clean.map((url) => '<span class="image-upload-control-bg-cell"><img src="' + S.escapeHtml(url) + '" alt="" decoding="async" /></span>').join('');
  button.classList.add('has-upload-preview');
}

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

function renderImageUploadPreview() {
  renderUploadPreviewOnButton(document.getElementById('imageUploadButton'), imageState.uploadedImageUrls || []);
}

function renderVideoStartPreview() {
  setFramePreview(document.getElementById('videoStartUploadButton'), videoState.startImage || '', 'start image');
}

function renderVideoEndPreview() {
  setFramePreview(document.getElementById('videoEndUploadButton'), videoState.endImage || '', 'end image');
}

function renderVideoReferencesPreview() {
  const button = document.getElementById('videoReferencesUploadButton');
  renderUploadPreviewOnButton(button, videoState.referenceImageUrls || []);
  if (!button) return;
  let badge = button.querySelector(':scope > .video-reference-control-badge');
  if (videoState.inputVideo || videoState.videoUrl) {
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
}

function renderVideoInputPreviews() {
  renderVideoStartPreview();
  renderVideoEndPreview();
}

function renderAllUploadPreviews() {
  injectImageStyleSheetCss();
  renderImageUploadPreview();
  renderVideoStartPreview();
  renderVideoEndPreview();
  renderVideoReferencesPreview();
}

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

function updateImageUploadButtonPreview() {
  renderAllUploadPreviews();
}

function currentUploadImages(targetOverride) {
  const target = targetOverride || getUploadTarget();
  if (target === UPLOAD_TARGETS.VIDEO_START) return videoState.startImage ? [videoState.startImage] : [];
  if (target === UPLOAD_TARGETS.VIDEO_END) return videoState.endImage ? [videoState.endImage] : [];
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) return (videoState.referenceImageUrls || []).slice();
  return (imageState.uploadedImageUrls || []).slice();
}

function uploadLimitForTarget(targetOverride) {
  const target = targetOverride || getUploadTarget();
  return target === UPLOAD_TARGETS.VIDEO_START || target === UPLOAD_TARGETS.VIDEO_END ? 1 : 4;
}

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
    const refs = (videoState.referenceImageUrls || []).filter((item) => item && item !== url);
    refs.unshift(url);
    videoState.referenceImageUrls = refs.slice(0, uploadLimitForTarget(target));
    videoState.uploadedImageUrls = videoState.referenceImageUrls.slice();
    videoState.referenceImageUrl = videoState.referenceImageUrls[0] || '';
    videoState.imageUrl = videoState.referenceImageUrl;
    renderVideoReferencesPreview();
    renderUploadedPhotoGrid();
    updateSendButton();
    return;
  }
  if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) {
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

function applyUploadedMediaToTarget(url) {
  applyUploadToTarget(url, getUploadTarget());
}

function addVideoReferenceImage(url) {
  applyUploadToTarget(url, UPLOAD_TARGETS.VIDEO_REFERENCES);
}

function applyVideoReferenceToState(url) {
  if (!url) return;
  videoState.inputVideo = url;
  videoState.videoUrl = url;
  if (videoState.section === 'motion' || currentVideoConfig().motion_control) {
    videoState.generationMode = 'motion_control';
    videoState.mode = 'motion_control';
  }
  renderVideoReferencesPreview();
  renderUploadedPhotoGrid();
  updateSendButton();
}

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
    videoState.referenceImageUrls = clean.slice(0, uploadLimitForTarget(target));
    videoState.uploadedImageUrls = videoState.referenceImageUrls.slice();
    videoState.referenceImageUrl = videoState.referenceImageUrls[0] || '';
    videoState.imageUrl = videoState.referenceImageUrl;
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

function openImageUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.IMAGE_UPLOAD, e);
}

function openImageUploadTarget(e) {
  openImageUpload(e);
}

function ensureVisualCreateModal() {
  let modal = document.getElementById('visualCreateModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'visualCreateModal';
  modal.className = 'visual-create-modal';
  document.body.appendChild(modal);
  return modal;
}

function ensureVisualPickerModal() {
  let modal = document.getElementById('visualPickerModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'visualPickerModal';
  modal.className = 'visual-create-modal visual-picker-modal';
  document.body.appendChild(modal);
  return modal;
}

function closeVisualPicker(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const modal = document.getElementById('visualPickerModal');
  if (modal) modal.classList.remove('show');
}

function visualPickerCardHtml(item, kind) {
  const selected = kind === 'character' ? imageState.characterId === item.id : imageState.objectId === item.id;
  return '<button class="visual-picker-card ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.pickVisualReference(event,\'' + kind + '\',\'' + S.escapeHtml(item.id) + '\')">'
    + '<span class="visual-picker-thumb"><img src="' + S.escapeHtml(item.previewUrl) + '" alt="' + S.escapeHtml(item.name) + '" loading="lazy" decoding="async" /></span>'
    + '<span class="visual-picker-name">' + S.escapeHtml(item.name) + '</span>'
    + '<span class="visual-picker-check">✓</span>'
    + '</button>';
}

function openVisualPicker(e, kind) {
  openImageStylePanel(e, kind === 'object' ? 'object' : 'character');
}

let visualCreateDraft = { kind: '', photos: [] };

function visualCreatePhotoSlot(index) {
  const url = visualCreateDraft.photos[index] || '';
  return '<button class="visual-photo-slot ' + (url ? 'has-photo' : '') + '" type="button" onclick="SYLVEX.pickVisualCreatePhoto(event,' + index + ')">'
    + (url ? '<img src="' + S.escapeHtml(url) + '" alt="" />' : '<span>＋</span><b>Добавить фото</b>')
    + (url ? '<em onclick="SYLVEX.removeVisualCreatePhoto(event,' + index + ')">×</em>' : '')
    + '</button>';
}

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
  modal.innerHTML = '<div class="visual-create-card">'
    + '<div class="visual-create-head"><button type="button" onclick="SYLVEX.closeVisualCreateModal(event)">← Назад</button><h3>' + title + '</h3></div>'
    + '<label class="visual-field"><span>' + nameLabel + '</span><input id="visualCreateName" value="' + S.escapeHtml(name) + '" placeholder="' + namePlaceholder + '" oninput="SYLVEX.updateVisualCreateDraft(event,\'name\')" /></label>'
    + (isCharacter ? '<label class="visual-field"><span>Пол *</span><select id="visualCreateGender" onchange="SYLVEX.updateVisualCreateDraft(event,\'gender\')"><option value="">Выберите пол</option><option value="male" ' + (gender === 'male' ? 'selected' : '') + '>Мужской</option><option value="female" ' + (gender === 'female' ? 'selected' : '') + '>Женский</option></select></label>' : '')
    + (!isCharacter ? '<label class="visual-field"><span>Описание</span><textarea id="visualCreateDescription" placeholder="Например: чёрные солнцезащитные очки" oninput="SYLVEX.updateVisualCreateDraft(event,\'description\')">' + S.escapeHtml(description) + '</textarea></label>' : '')
    + '<div class="visual-photo-grid">' + [0, 1, 2].map(visualCreatePhotoSlot).join('') + '</div>'
    + '<p class="visual-create-hint">' + hint + '<br>Для лучшего результата используйте фото с разных ракурсов и хорошим освещением.</p>'
    + '<button class="visual-create-save" type="button" ' + (canSave ? '' : 'disabled') + ' onclick="SYLVEX.saveVisualCreateDraft(event)">' + (isCharacter ? 'Создать персонажа' : 'Создать объект') + '</button>'
    + '<input id="visualCreateFileInput" type="file" accept="image/png,image/jpeg,image/webp" hidden />'
    + '</div>';
  modal.classList.add('show');
}

function openVisualCreateModal(e, kind) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const caps = getModelCapabilities(imageState.modelId);
  if ((kind === 'character' && !caps.character) || (kind === 'object' && !caps.object)) {
    imageFeatureUnavailableToast(kind === 'character' ? 'character' : 'object');
    return;
  }
  visualCreateDraft = { kind, name: '', gender: '', description: '', photos: [] };
  renderVisualCreateModal();
}

function closeVisualCreateModal(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const modal = document.getElementById('visualCreateModal');
  if (modal) modal.classList.remove('show');
}

function updateVisualCreateDraft(e, field) {
  const target = e && e.target;
  visualCreateDraft[field] = target ? target.value : '';
  if (field === 'gender') {
    renderVisualCreateModal();
  } else {
    updateVisualCreateSaveState();
  }
}

function visualCreateCanSave() {
  const isCharacter = visualCreateDraft.kind === 'character';
  return String(visualCreateDraft.name || '').trim().length >= 2
    && (!isCharacter || !!visualCreateDraft.gender)
    && (visualCreateDraft.photos || []).filter(Boolean).length > 0;
}

function updateVisualCreateSaveState() {
  const btn = document.querySelector('#visualCreateModal .visual-create-save');
  if (btn) btn.disabled = !visualCreateCanSave();
}

function pickVisualCreatePhoto(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const input = document.getElementById('visualCreateFileInput');
  if (!input) return;
  input.onchange = () => {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/i.test(file.type || '')) {
      toast('Поддерживаются только JPG, PNG и WEBP');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast('Файл слишком большой');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      visualCreateDraft.photos[index] = String(reader.result || '');
      renderVisualCreateModal();
    };
    reader.readAsDataURL(file);
  };
  input.click();
}

function removeVisualCreatePhoto(e, index) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  visualCreateDraft.photos.splice(index, 1);
  renderVisualCreateModal();
}

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
  const id = (kind === 'character' ? 'custom_character_' : 'custom_object_') + Date.now();
  const item = {
    id,
    name,
    gender: visualCreateDraft.gender || '',
    description: visualCreateDraft.description || '',
    previewUrl: photos[0],
    referenceImages: photos,
    type: 'custom',
    status: 'ready',
    created_at: new Date().toISOString(),
  };
  const storageKind = kind === 'character' ? 'characters' : 'objects';
  const savedItem = await saveVisualItemToBackend(kind, item);
  Object.assign(item, savedItem || {});
  if (serverVisualItems[storageKind]) {
    serverVisualItems[storageKind] = serverVisualItems[storageKind].filter((entry) => entry.id !== item.id);
    serverVisualItems[storageKind].unshift(item);
  }
  const items = loadCustomVisualItems(storageKind).filter((entry) => entry && entry.id !== item.id);
  items.unshift(item);
  saveCustomVisualItems(storageKind, items);
  if (kind === 'character') {
    imageState.characterId = item.id;
    imageState.characterName = item.name;
    imageState.characterReferences = item.referenceImages.slice();
  } else {
    imageState.objectId = item.id;
    imageState.objectName = item.name;
    imageState.objectReferences = item.referenceImages.slice();
    imageState.objects = item.name;
  }
  closeVisualCreateModal(e);
  closeVisualPicker(e);
  closeImageStylePanel(e);
  renderImageReferenceSections();
  toast(kind === 'character' ? 'Персонаж создан' : 'Объект создан');
}

function pickVisualReference(e, kind, id) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const caps = getModelCapabilities(imageState.modelId);
  if (kind === 'character' && !caps.character) return imageFeatureUnavailableToast('character');
  if (kind === 'object' && !caps.object) return imageFeatureUnavailableToast('object');
  const list = kind === 'character' ? imageCharacters() : imageObjects();
  const item = list.find((entry) => entry.id === id);
  if (!item) return;
  if (kind === 'character') {
    if (imageState.characterId === item.id) {
      clearSelectedCharacter();
    } else {
      imageState.characterId = item.id;
      imageState.characterName = item.name;
      imageState.characterReferences = (item.referenceImages || []).slice();
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

function openVideoStartUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.VIDEO_START, e);
}

function openVideoEndUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.VIDEO_END, e);
}

function openVideoReferencesUpload(e) {
  openUploadTarget(UPLOAD_TARGETS.VIDEO_REFERENCES, e);
}

function aggressiveUploadTargetClickGuard(e) {
  const target = e && e.target ? e.target : null;
  if (!target || !target.closest) return;
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
  document.addEventListener('click', aggressiveUploadTargetClickGuard, true);
}

function currentModeAttachment() {
  if (isVideoMode()) return videoState.attachment || null;
  if (isMusicMode() || isVoiceMode()) return currentAudioState().attachment || null;
  if (isImageMode()) return imageState.attachment || null;
  return pendingAttachment;
}

function setCurrentModeAttachment(attachment) {
  if (isVideoMode()) {
    videoState.attachment = attachment || null;
  } else if (isMusicMode() || isVoiceMode()) {
    currentAudioState().attachment = attachment || null;
  } else if (isImageMode()) {
    imageState.attachment = attachment || null;
  } else {
    pendingAttachment = attachment || null;
  }
  pendingAttachment = currentModeAttachment();
}

function currentSelectedUploadImage() {
  const target = getUploadTarget();

  if (target === UPLOAD_TARGETS.VIDEO_START) return videoState.startImage || '';
  if (target === UPLOAD_TARGETS.VIDEO_END) return videoState.endImage || '';
  if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) return videoState.referenceImageUrl || ((videoState.referenceImageUrls || [])[0]) || '';
  if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) return imageState.referenceImageUrl || ((imageState.referenceImageUrls || [])[0]) || '';

  const images = currentUploadImages();
  return images[images.length - 1] || '';
}

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
      display: block;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }

    .image-upload-control-bg-cell img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
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

    @media (max-width: 370px) {
      .image-style-panel-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  `;

  document.head.appendChild(style);
}

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
    </div>
  `;

  document.body.appendChild(panel);
  return panel;
}

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

  grid.innerHTML = createCard + items.map((item) => {
    const id = String(item.id || '');
    const label = item.name || item.label || id;
    const selected = selectedId === id;

    return `
      <button class="image-style-card ${selected ? 'selected' : ''}" type="button" onclick="SYLVEX.pickVisualReference(event, '${createKind}', '${S.escapeHtml(id)}')">
        <span class="image-style-thumb is-placeholder" aria-hidden="true">
          <span class="image-style-placeholder-icon"></span>
        </span>
        <span class="image-style-label">${S.escapeHtml(label)}</span>
        <span class="image-style-check">✓</span>
      </button>
    `;
  }).join('');
}

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

  const mp = document.getElementById('modelPop');
  if (mp) mp.classList.remove('show');

  const sheet = document.getElementById('plusSheet');
  if (sheet) sheet.classList.remove('show');

  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }

  S.haptic && S.haptic.impact && S.haptic.impact('light');
}

function closeImageStylePanel(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  hideImageStyleInfo();

  const panel = document.getElementById('imageStylePanel');
  if (panel) panel.classList.remove('show');
}

function hideImageStyleInfo() {
  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (tooltip) tooltip.classList.remove('show');
}

function handleImageStyleInfoOutsideTouch(e) {
  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (!tooltip || !tooltip.classList.contains('show')) return;

  const target = e && e.target ? e.target : null;

  // Сам восклицательный знак не закрывает подсказку через общий обработчик,
  // потому что он сам открывает/закрывает её через toggleImageStyleInfo.
  if (target && target.closest && target.closest('.image-style-info-mark')) return;

  hideImageStyleInfo();
}

function toggleImageStyleInfo(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  const tooltip = document.getElementById('imageStyleInfoTooltip');
  if (!tooltip) return;

  tooltip.classList.toggle('show');
}

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

function imageModelDescription(model) {
  if (!model) return 'AI-модель для генерации изображений.';
  return model.description || model.desc || model.subtitle || model.note || 'AI-модель для генерации изображений.';
}

function imageModelButton(model) {
  const activeId = isImageMode()
    ? imageState.modelId
    : (isMusicMode() ? musicState.modelId : videoState.modelId);

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

  function applyImageDefaults(model) {
    if (!model) return;
    imageState.modelId = model.id;
    imageState.size = (model.sizes && model.sizes[0] && model.sizes[0].id) || '';
    imageState.count = (model.counts && model.counts[0]) || 1;
    imageState.style = (model.styles && model.styles[0] && model.styles[0].id) || 'auto';
    imageState.character = (model.characters && model.characters[0] && model.characters[0].id) || 'auto';
  }

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

  function renderImageControls() {
    const model = currentImageModel();
    if (!model) return;
    syncImageModelOptionDefaults(model);
    const modelEl = document.getElementById('modelValComposer');
    if (modelEl && isImageMode()) modelEl.textContent = model.label || model.id;
    const sizeOptions = model.sizes && model.sizes.length ? model.sizes : [
      { id:'1:1', label:'1:1', ratio:'1:1' },
      { id:'16:9', label:'16:9', ratio:'16:9' },
      { id:'9:16', label:'9:16', ratio:'9:16' }
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
    if (styleVal) {
      const selectedStyleItem = imageStyleSheetItem(imageState.style);
      styleVal.textContent = imageState.style === 'auto' ? 'Стили' : optionLabel(model.styles, imageState.style, 'Стили');
      updateImageStyleButtonPreview(selectedStyleItem);
    }
    const characterVal = document.getElementById('imageCharacterVal');
    if (characterVal) characterVal.textContent = 'Персонаж';
    renderImageReferenceSections();
  }

  function normalizeImageSeed(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const seed = Number(raw);
    if (!Number.isSafeInteger(seed) || seed < 0) {
      throw new Error('Seed должен быть целым положительным числом');
    }
    return seed;
  }

  function imageSeedInputValue() {
    return imageState.seed === null || imageState.seed === undefined ? '' : String(imageState.seed);
  }

  function currentRecraftTools() {
    const model = currentImageModel() || {};
    return Array.isArray(model.recraftTools) ? model.recraftTools.slice() : [];
  }

  function imageOptionsPayload(referenceImages) {
    const capabilities = getModelCapabilities(imageState.modelId);
    const seed = capabilities.seed ? normalizeImageSeed(imageState.seed) : null;
    return Object.assign({}, imageState, {
      seed,
      referenceImageUrls: (referenceImages || []).slice(),
      referenceImages: (referenceImages || []).slice(),
    }, imageVisualReferenceOptions());
  }

  function sanitizeImageSeedInput(value) {
    return String(value || '').replace(/\D+/g, '');
  }

  function onImageSeedInput(e) {
    const input = e && e.currentTarget ? e.currentTarget : document.getElementById('imageSeedInput');
    if (!input) return;
    const clean = sanitizeImageSeedInput(input.value);
    if (input.value !== clean) input.value = clean;
    imageState.seed = clean ? clean : null;
  }

  function toggleImageSeedTooltip(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const tip = document.getElementById('imageSeedTooltip');
    if (!tip) return;
    tip.hidden = !tip.hidden;
  }

  function resetImageSettings(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    imageState.seed = null;
    openImageOptionMenu(e, 'seed');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function closeImageSeedTooltipOnOutside(e) {
    const tip = document.getElementById('imageSeedTooltip');
    if (!tip || tip.hidden) return;
    const btn = document.getElementById('imageSeedInfoBtn');
    if (tip.contains(e.target) || (btn && btn.contains(e.target))) return;
    tip.hidden = true;
  }

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

    if (isMusicMode()) {
      const el = document.getElementById('modelPop');
      if (!el) return;
      ensureMusicSettings();

      el.classList.remove('image-model-floating-pop');
      el.classList.remove('image-size-floating-pop');
      el.classList.remove('music-settings-pop');
      el.classList.remove('video-option-horizontal-pop');
      el.style.cssText = '';

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

      if (kind === 'settings') {
        if (el.parentElement !== document.body) document.body.appendChild(el);
        el.classList.add('image-size-floating-pop');
        el.classList.add('music-settings-pop');
        el.style.position = 'fixed';
        el.style.left = '8px';
        el.style.right = 'auto';
        el.style.top = 'auto';
        el.style.bottom = 'calc(58px + env(safe-area-inset-bottom))';
        el.style.width = '78vw';
        el.style.maxWidth = '380px';
        el.style.minWidth = '275px';
        el.style.maxHeight = '70vh';
        el.style.overflowY = 'auto';
        el.style.zIndex = '999999';
        el.innerHTML = '<div class="image-size-sheet-title">Настройки музыки</div>'
          + '<div class="music-settings-sheet">'
          + Object.keys(MUSIC_SETTINGS).map((settingKey) => {
            const section = MUSIC_SETTINGS[settingKey];
            const active = musicState.settings[settingKey] || 'auto';
            return '<section class="music-settings-section">'
              + '<h4>' + S.escapeHtml(section.title) + '</h4>'
              + '<div class="music-settings-options">'
              + section.items.map((item) => {
                const id = String(item.id || '');
                const selected = String(active) === id;
                return '<button class="music-setting-chip ' + (selected ? 'active sel' : '') + '" type="button" onclick="SYLVEX.pickMusicOption(event,\'' + settingKey + '\',\'' + S.escapeHtml(id) + '\')">'
                  + S.escapeHtml(item.label || id)
                  + '</button>';
              }).join('')
              + '</div>'
              + '</section>';
          }).join('')
          + '<button class="music-settings-clear" type="button" onclick="SYLVEX.resetMusicSettings(event)">Очистить всё</button>'
          + '</div>';
        el.classList.add('show');
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
        S.haptic && S.haptic.impact && S.haptic.impact('light');
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

      const closeOtherSheets = () => {
        const pp = document.getElementById('plusPop'); if (pp) pp.classList.remove('show');
        const sheet = document.getElementById('plusSheet'); if (sheet) sheet.classList.remove('show');
      };

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
            const icon = optionKind === 'ratio'
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

  function pickMusicOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureMusicSettings();

    if (kind === 'genre') {
      musicState.genre = value || 'auto';
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

  function resetMusicSettings(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    ensureMusicSettings();
    musicState.genre = 'auto';
    Object.keys(MUSIC_SETTINGS).forEach((key) => {
      musicState.settings[key] = 'auto';
    });
    renderMusicControls();
    openImageOptionMenu(e, 'settings');
    S.haptic && S.haptic.impact && S.haptic.impact('light');
  }

  function pickImageOption(e, kind, value) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (kind === 'model') {
      if (isImageMode()) {
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
        const model = VIDEO_MODELS.find((item) => item.id === value);
        if (model) {
          if (model.id !== videoState.modelId) saveCurrentVideoModelSettings();
          videoState.modelId = model.id;
          restoreVideoModelSettings(model.id);
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      } else if (isMusicMode()) {
        const model = MUSIC_MODEL_LIST.find((item) => item.id === value);
        if (model) {
          musicState.modelId = model.id;
          const mvc = document.getElementById('modelValComposer');
          if (mvc) mvc.textContent = model.label || model.name || model.id;
        }
      }
    }

    if (isMusicMode()) {
      renderMusicControls();
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

  function generatedThumbsFromResponse(j) {
    if (!j) return [];
    if (j.thumbnail_url) return [j.thumbnail_url];
    if (Array.isArray(j.thumbnails) && j.thumbnails.length) return j.thumbnails;
    if (Array.isArray(j.images) && j.images.length) {
      return j.images.map((item) => typeof item === 'object' ? (item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || '') : '').filter(Boolean);
    }
    return j.thumb_url ? [j.thumb_url] : [];
  }

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

  function formatAudioTime(seconds) {
    const total = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    const min = Math.floor(total / 60);
    const sec = String(total % 60).padStart(2, '0');
    return min + ':' + sec;
  }

  let activeMusicTrack = null;

  function setStudioPlayerIcon(isPlaying) {
    const btn = document.getElementById('studioPlayPauseBtn');
    if (!btn) return;
    btn.innerHTML = isPlaying
      ? '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>'
      : '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
  }

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

  function openMusicInPlayer(trackLike, e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    PlayerManager.playTrack(trackLike || {});
  }

  function toggleStudioAudioPlayer(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    PlayerManager.toggle();
  }

  function generatedThumbsFromMessage(m) {
    if (!m) return [];
    if (m.thumbnail_url) return [m.thumbnail_url];
    if (Array.isArray(m.thumbnails) && m.thumbnails.length) return m.thumbnails;
    if (Array.isArray(m.images) && m.images.length) {
      return m.images.map((item) => typeof item === 'object' ? (item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || '') : '').filter(Boolean);
    }
    return m.thumbUrl ? [m.thumbUrl] : [];
  }

  function imagePreviewUrl(meta, fallback) {
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

  function previewImgHtml(url, alt, fallbackUrl) {
    const safeUrl = S.escapeHtml(url || '');
    const safeAlt = S.escapeHtml(alt || 'preview');
    const safeFallbackUrl = S.escapeHtml(fallbackUrl || '');
    if (!safeUrl) return '<span class="generation-result-fallback">IMG</span>';
    return '<img src="' + safeUrl + '" alt="' + safeAlt + '" loading="lazy" decoding="async"'
      + (safeFallbackUrl ? ' data-fallback-src="' + safeFallbackUrl + '"' : '')
      + ' onerror="if(this.dataset&&this.dataset.fallbackSrc&&this.src!==this.dataset.fallbackSrc){this.src=this.dataset.fallbackSrc;this.removeAttribute(\'data-fallback-src\');}else{this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'generation-result-fallback\',textContent:\'IMG\'}));}" />';
  }

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
    };
  }

  function renderGeneratedTelegramButton(url, kind) {
    const safeUrl = S.escapeHtml(url);
    const safeKind = S.escapeHtml(kind || 'file');
    return '<button class="gen-action-btn gen-telegram-btn" type="button" data-result-url="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="SYLVEX.openTelegramBot(event)">'
      + '<span>Перейти в Telegram</span>'
      + '</button>';
  }

  function renderGeneratedOpenButton(url, kind) {
    const safeUrl = S.escapeHtml(url);
    const safeKind = S.escapeHtml(kind || 'file');
    if (kind === 'audio' || kind === 'music') {
      return '<button class="gen-action-btn" type="button" data-audio-url="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="SYLVEX.playMusicTrack(event)">Открыть музыку</button>';
    }
    const dataAttr = kind === 'image' ? 'data-image-url' : 'data-result-url';
    const handler = kind === 'image' ? 'SYLVEX.openImageViewer(event)' : 'SYLVEX.openGeneratedContent(event)';
    return '<button class="gen-action-btn" type="button" ' + dataAttr + '="' + safeUrl + '" data-result-kind="' + safeKind + '" onclick="' + handler + '">Открыть</button>';
  }

  function renderGeneratedActions(url, kind) {
    const safeUrl = S.escapeHtml(url);
    let actions = renderGeneratedOpenButton(url, kind) + renderGeneratedTelegramButton(url, kind);
    if (kind === 'image') {
      actions += '<button class="gen-action-btn" type="button" data-image-url="' + safeUrl + '" onclick="SYLVEX.animateGeneratedImage(event)">Оживить фото</button>';
    }
    if (kind === 'video') {
      actions += '<button class="gen-action-btn" type="button" data-video-url="' + safeUrl + '" onclick="SYLVEX.editGeneratedVideo(event)">Редактировать видео</button>';
    }
    return '<div class="gen-result-actions">' + actions + '</div>';
  }

  function renderGeneratedImage(item, index) {
    const url = typeof item === 'string' ? item : item.url;
    const thumb = typeof item === 'string' ? item : (item.thumb || item.url);
    const safeUrl = S.escapeHtml(url);
    const safeThumb = S.escapeHtml(thumb || url);
    return '<div class="gen-media-card gen-image-card">'
      + '<button class="gen-img-open" type="button" data-image-url="' + safeUrl + '" onclick="SYLVEX.openImageViewer(event)">'
      + '<img class="gen-img" src="' + safeThumb + '" alt="generated" loading="lazy" decoding="async" />'
      + '</button>'
      + renderGeneratedActions(url, 'image')
      + '</div>';
  }

  function imageGenerationMetadata(prompt, referenceImages, result, optionsSnapshot) {
    const backendMeta = result && result.metadata && typeof result.metadata === 'object' ? result.metadata : {};
    const options = Object.assign({}, optionsSnapshot || imageState || {}, backendMeta.image_options || backendMeta.settings || {});
    const modelId = backendMeta.model || (result && result.model) || options.modelId || imageState.modelId || '';
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

  function generationResultMetadata(type, prompt, result, referenceImages, optionsSnapshot) {
    if (type === 'image') return imageGenerationMetadata(prompt, referenceImages, result);
    const videoUrls = result ? generatedUrlsFromResponse(result, 'video') : [];
    const audioUrls = result ? generatedUrlsFromResponse(result, 'audio') : [];
    const options = optionsSnapshot || (type === 'video' ? videoState : (type === 'music' ? musicOptionsPayload() : voiceState));
    const modelId = (options && (options.model || options.modelId)) || pickStudioModel() || '';
    const currentModel = type === 'video' ? currentVideoModel() : null;
    const resultUrl = type === 'video' ? (videoUrls[0] || result.video_url || '') : (audioUrls[0] || musicAudioUrl(result || {}) || '');
    const coverUrl = type === 'music' ? musicCoverUrl(result || {}) : '';
    return {
      type,
      result_url: resultUrl,
      model: modelId,
      model_label: (currentModel && (currentModel.label || currentModel.name)) || modelId,
      provider: type === 'video' ? currentVideoProvider() : (type === 'music' ? 'suno' : (type === 'voice' ? 'voice' : pickProviderHint())),
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
      created_at: new Date().toISOString(),
      sent_to_telegram: !!(result && result.sent_to_telegram),
    };
  }

  function renderImageGenerationLoadingCard() {
    return renderGenerationLoadingCard({ progress: createGenerationProgress('image') });
  }

  const GENERATION_PROGRESS_STEPS = [0,3,7,12,18,25,33,40,47,55,61,68,74,80,84,87,89,90,91,92,93,94,95,96,97,98];
  const GENERATION_STAGE_MESSAGES = {
    image: ['Создаем изображение...', 'Подготавливаем композицию...', 'Прорисовываем детали...', 'Финальная обработка...'],
    video: ['Создаем сценарий...', 'Строим движение камеры...', 'Генерируем кадры...', 'Просчитываем анимацию...', 'Финальный рендер...'],
    music: ['Создаем мелодию...', 'Подбираем инструменты...', 'Формируем композицию...', 'Сводим звук...'],
    voice: ['Подготавливаем голос...', 'Синтезируем речь...', 'Настраиваем интонацию...', 'Финальная обработка...'],
    text: ['Анализируем запрос...', 'Строим ответ...', 'Формируем результат...'],
    kling: ['Building motion...', 'Generating frames...', 'Applying native audio...', 'Rendering video...'],
  };

  function generationKindForCurrentMode() {
    if (isVideoMode()) {
      const model = String(videoState.modelId || '').toLowerCase();
      return model.includes('kling') ? 'kling' : 'video';
    }
    if (isMusicMode()) return 'music';
    if (isVoiceMode()) return 'voice';
    if (isImageMode()) return 'image';
    return 'text';
  }

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

  function generationProgressMessage(progress) {
    const p = progress || {};
    const items = GENERATION_STAGE_MESSAGES[p.kind] || GENERATION_STAGE_MESSAGES.text;
    if (p.message) return p.message;
    const pct = Number(p.percent || 0);
    const index = Math.min(items.length - 1, Math.max(0, Math.floor((pct / 99) * items.length)));
    return items[index] || items[0] || 'Генерация...';
  }

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
    if (p.percent >= 98) p.percent = 97 + Math.floor((Date.now() / 1800) % 2);
    return p;
  }

  function renderGenerationLoadingCard(message) {
    const progress = nextGenerationProgress(message && message.progress, false);
    const pct = Math.max(0, Math.min(98, Number(progress.percent || 0)));
    return '<div class="generation-loading-card">'
      + '<div class="generation-loading-border"></div>'
      + '<div class="generation-loading-title">' + S.escapeHtml(generationProgressMessage(progress)) + '</div>'
      + '<div class="generation-loading-progress" aria-label="Generation progress">'
      + '<span style="width:' + pct + '%"></span>'
      + '</div>'
      + '<div class="generation-loading-percent">' + pct + '%</div>'
      + '</div>';
  }

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

  function renderImageResultMiniCard(m, index) {
    const meta = m.metadata || {};
    const type = meta.type || (m.videoUrl ? 'video' : (m.audioUrl ? 'music' : 'image'));
    const thumb = imagePreviewUrl(meta, '');
    const fallbackUrl = meta.preview_fallback_url || meta.image_url || meta.full_url || meta.result_url || ((meta.result_images || [])[0]) || '';
    const safeModel = S.escapeHtml(meta.model_label || meta.model || type);
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
    const handler = type === 'music'
      ? 'SYLVEX.playMusicTrackFromMessage(event,' + index + ')'
      : 'SYLVEX.openGenerationInfoDrawer(event,' + index + ')';
    return '<button class="generation-result-mini-card" type="button" onclick="' + handler + '">'
      + '<span class="generation-result-thumb">' + media + '</span>'
      + '<span class="generation-result-meta">'
      + '<span class="generation-result-title">' + S.escapeHtml(titleMap[type] || 'Результат готов') + '</span>'
      + '<span class="generation-result-sub">' + safeModel + '</span>'
      + '</span>'
      + '</button>';
  }

  function renderGeneratedVideo(url) {
    const safeUrl = S.escapeHtml(url);
    return '<div class="gen-media-card gen-video-card">'
      + '<video class="gen-video" src="' + safeUrl + '" controls playsinline preload="metadata"></video>'
      + renderGeneratedActions(url, 'video')
      + '</div>';
  }

  function renderGeneratedAudio(url) {
    const safeUrl = S.escapeHtml(url);
    return '<div class="gen-media-card gen-audio-card" role="button" tabindex="0" data-audio-url="' + safeUrl + '" data-title="Untitled Track" onclick="SYLVEX.playMusicTrack(event)">'
      + '<div class="generation-info-preview generation-info-audio-preview"><span>♪</span></div>'
      + renderGeneratedActions(url, 'audio')
      + '</div>';
  }

  function renderGeneratedFile(url) {
    return '<div class="gen-media-card gen-file-card">'
      + '<span class="gen-file-label">Generated file</span>'
      + renderGeneratedActions(url, 'file')
      + '</div>';
  }

  function renderChat() {
    const el = document.getElementById('chatArea'); if (!el) return;
    el.innerHTML = chatMessages.map((m, i) => {
      if (m.imageLoading || m.generationLoading) {
        return '<div class="msg ai generation-loading-msg" data-i="' + i + '"><div class="ai-avatar">S</div>'
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
      if (m.referenceImages && m.referenceImages.length) {
        inner += '<div class="msg-ref-img-row">' + m.referenceImages.map((url) =>
            '<span class="msg-ref-img"><img src="' + S.escapeHtml(url) + '" alt="reference image" /></span>'
        ).join('') + '</div>';
        }
      const imageUrls = generatedUrlsFromMessage(m, 'image');
      const imageThumbs = generatedThumbsFromMessage(m);
      const videoUrls = generatedUrlsFromMessage(m, 'video');
      const audioUrls = generatedUrlsFromMessage(m, 'audio');
      const fileUrls = generatedUrlsFromMessage(m, 'file');
      if (m.role === 'ai' && (imageUrls.length || videoUrls.length || audioUrls.length)) {
        const resultType = videoUrls.length ? 'video' : (audioUrls.length ? 'music' : 'image');
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
        const imageItems = imageUrls.map((url, idx) => ({ url, thumb: imageThumbs[idx] || url }));
        inner += '<div class="gen-img-grid">' + imageItems.map(renderGeneratedImage).join('') + '</div>';
      }
      if (videoUrls.length) inner += '<div class="gen-media-list">' + videoUrls.map(renderGeneratedVideo).join('') + '</div>';
      if (audioUrls.length) inner += '<div class="gen-media-list">' + audioUrls.map(renderGeneratedAudio).join('') + '</div>';
      if (fileUrls.length) inner += '<div class="gen-media-list">' + fileUrls.map(renderGeneratedFile).join('') + '</div>';
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
  function addMediaLink(kind) {
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');

    const raw = window.prompt(kind === 'video' ? 'Video URL' : 'Image URL');
    const url = String(raw || '').trim();
    if (!url) return;

    if (isVideoMode()) {
      if (kind === 'video') {
        const config = currentVideoConfig() || {};
        if (getUploadTarget() === UPLOAD_TARGETS.VIDEO_REFERENCES || videoState.section === 'motion' || config.motion_control) {
          applyVideoReferenceToState(url);
        } else {
          videoState.videoUrl = url;
          videoState.inputVideo = url;
          videoState.generationMode = 'video_edit';
          videoState.mode = 'video_edit';
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
      state.uploads.push({ kind: kind === 'video' ? 'audio' : kind, url });
      state.uploads = state.uploads.slice(0, 4);
      updateSendButton();
      toast('Ссылка добавлена');
      return;
    }

    if (kind === 'image' && isImageMode()) {
      applyUploadToTarget(url, UPLOAD_TARGETS.IMAGE_UPLOAD);
      renderComposerImageDraft();
      updateSendButton();
      toast('Ссылка добавлена');
    }
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

  function normalizeGeneratedImageItem(item, thumb) {
    if (!item) return null;
    if (typeof item === 'object') {
      const url = item.url || item.original_url || item.image_url || item.result_url || item.full_url || '';
      if (!url) return null;
      return { url, thumb: item.thumb || item.thumb_url || item.thumbnail || item.thumbnail_url || url };
    }
    return { url: item, thumb: thumb || item };
  }

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

  function pushGeneratedPhotoHistoryItem(items, seen, source, fallback) {
    const item = collectImageHistoryItem(source || {}, fallback);
    if (!item || seen.has(item.url)) return;
    seen.add(item.url);
    items.push(item);
  }

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

  function addGeneratedImages(urls, thumbs) {
    const list = (urls || []).map((url, index) => normalizeGeneratedImageItem(url, thumbs && thumbs[index])).filter(Boolean);
    if (!list.length) return;
    list.forEach((item) => {
      generatedImageLibrary = generatedImageLibrary.filter((old) => normalizeGeneratedImageItem(old).url !== item.url);
      generatedImageLibrary.unshift(item);
    });
    generatedImageLibrary = generatedImageLibrary.slice(0, 20);
    renderUploadPanelImages();
  }

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

function uploadPhotoButtonHtml() {
  const uploadImages = currentUploadImages();
  const target = getUploadTarget();
  const isVideoReferences = target === UPLOAD_TARGETS.VIDEO_REFERENCES;
  if (uploadImages.length >= uploadLimitForTarget()) {
    return (isVideoReferences && !(videoState.inputVideo || videoState.videoUrl))
      ? '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'video\')" aria-label="Загрузить видео"><span class="upload-photo-add-icon" aria-hidden="true">▶</span></button>'
      : '';
  }
  const uploadKind = isVideoReferences ? 'image' : 'image';

  if (!uploadImages.length) {
    return '<button class="upload-photo-center-btn" type="button" onclick="SYLVEX.openNativeFilePicker(\'' + uploadKind + '\')">'
      + '<span class="upload-photo-center-icon" aria-hidden="true">'
      + '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
      + '<rect x="3.5" y="5" width="17" height="14" rx="3" stroke="currentColor" stroke-width="1.8"/>'
      + '<path d="M7 16L10.2 12.8C10.8 12.2 11.7 12.2 12.3 12.8L14 14.5L15.2 13.3C15.8 12.7 16.7 12.7 17.3 13.3L20 16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
      + '<circle cx="8.7" cy="9.3" r="1.3" fill="currentColor"/>'
      + '</svg>'
      + '</span>'
      + '<span class="upload-photo-center-title">Загрузить фото</span>'
      + '<span class="upload-photo-center-sub">из файлов или галереи</span>'
      + '</button>'
      + (isVideoReferences ? '<button class="upload-photo-center-btn upload-video-center-btn" type="button" onclick="SYLVEX.openNativeFilePicker(\'video\')">'
        + '<span class="upload-photo-center-icon" aria-hidden="true">▶</span>'
        + '<span class="upload-photo-center-title">Загрузить видео</span>'
        + '<span class="upload-photo-center-sub">MP4 или MOV для Motion Control</span>'
        + '</button>' : '');
  }

  return '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'image\')" aria-label="Загрузить фото">'
    + '<span class="upload-photo-add-icon" aria-hidden="true">＋</span>'
    + '<span class="upload-photo-add-text">Загрузить</span>'
    + '</button>'
    + (isVideoReferences && !(videoState.inputVideo || videoState.videoUrl)
      ? '<button class="upload-photo-thumb upload-photo-add" type="button" onclick="SYLVEX.openNativeFilePicker(\'video\')" aria-label="Загрузить видео"><span class="upload-photo-add-icon" aria-hidden="true">▶</span></button>'
      : '');
}

  function renderUploadedPhotoGrid() {
    const grid = document.getElementById('uploadPhotoGrid');
    if (!grid) return;

    const uploadImages = currentUploadImages();
    const hasVideoReference = getUploadTarget() === UPLOAD_TARGETS.VIDEO_REFERENCES && Boolean(videoState.inputVideo || videoState.videoUrl);
    const hasUploads = uploadImages.length > 0 || hasVideoReference;

    grid.classList.toggle('empty', !hasUploads);

    const chooseBtn = document.getElementById('uploadChoosePhotosBtn');
    if (chooseBtn) chooseBtn.hidden = !hasUploads;
    const clearBtn = document.getElementById('uploadClearPhotosBtn');
    if (clearBtn) clearBtn.hidden = !hasUploads;

    const selectedUrl = currentSelectedUploadImage();
    const items = uploadImages.map((url, index) => {
      const safeUrl = S.escapeHtml(url);
      const selected = selectedUrl === url;
      return '<button class="upload-photo-thumb ' + (selected ? 'selected' : '') + '" type="button" onclick="SYLVEX.selectUploadedPhoto(event,\'' + safeUrl + '\')">'
        + '<img src="' + safeUrl + '" alt="uploaded image" />'
        + '<span class="upload-thumb-check">✓</span>'
        + '<span class="upload-photo-remove" onclick="SYLVEX.removeUploadedPhoto(event,' + index + ')">×</span>'
        + '</button>';
    });
    if (hasVideoReference) {
      items.unshift('<button class="upload-photo-thumb upload-video-thumb selected" type="button" onclick="SYLVEX.openNativeFilePicker(\'video\')" aria-label="Заменить видео">'
        + '<span class="upload-photo-add-icon" aria-hidden="true">▶</span>'
        + '<span class="upload-thumb-check">✓</span>'
        + '<span class="upload-photo-remove" onclick="SYLVEX.clearVideoReference(event)">×</span>'
        + '</button>');
    }

    const addButton = uploadPhotoButtonHtml();
    if (addButton) items.push(addButton);
    grid.innerHTML = items.join('');
  }

  function addUploadedPhoto(url) {
    if (!url) return;
    const target = getUploadTarget();
    const uploadImages = currentUploadImages().filter((item) => item !== url);
    uploadImages.push(url);
    setCurrentUploadImages(uploadImages, target);
    applyUploadToTarget(url, target);
    renderUploadedPhotoGrid();
    renderUploadPreviewForTarget(target);
  }

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

  function clearCurrentUploadTarget(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const target = getUploadTarget();
    setCurrentUploadImages([], target);
    if (target === UPLOAD_TARGETS.VIDEO_REFERENCES) {
      videoState.inputVideo = '';
      videoState.videoUrl = '';
    }
    renderUploadPanelImages();
    renderUploadPreviewForTarget(target);
    toast('Очищено');
  }

  function clearVideoReference(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    videoState.inputVideo = '';
    videoState.videoUrl = '';
    renderUploadedPhotoGrid();
    renderVideoReferencesPreview();
    updateSendButton();
  }

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

  // Uploaded images are kept in imageState.referenceImageUrls and sent to generation,
  // but their visual preview is shown only inside the “Загрузка” button background.
  box.innerHTML = '';
  box.hidden = true;
  box.classList.remove('show');
  box.style.display = 'none';

  updateImageUploadButtonPreview();
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
  imageState.uploadedImageUrls = urls.slice();

  renderUploadedPhotoGrid();
  renderComposerImageDraft();
  updateImageUploadButtonPreview();
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

function telegramBotLink() {
  const explicit = S.TELEGRAM_BOT_LINK || S.BOT_LINK || '';
  if (explicit) return explicit;
  const botLink = Array.from(document.querySelectorAll('a[href*="t.me/"]'))
    .map((link) => link.href || '')
    .find((href) => /bot/i.test(href));
  return botLink || 'https://t.me/sylvexai_bot';
}

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

function openGeneratedContent(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const btn = e && e.currentTarget ? e.currentTarget : null;
  const url = btn && btn.dataset ? (btn.dataset.resultUrl || btn.dataset.videoUrl || btn.dataset.audioUrl || '') : '';
  if (!url) return;
  const kind = btn && btn.dataset ? (btn.dataset.resultKind || '') : '';
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
  videoState.inputVideo = videoUrl;
  videoState.videoUrl = videoUrl;
  renderVideoControls();
  renderUploadedPhotoGrid();
  renderVideoInputPreviews();
  updateImageUploadButtonPreview();
  updateSendButton();
  toast('Видео добавлено для редактирования');
  S.haptic && S.haptic.notify && S.haptic.notify('success');
}

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

function generationInfoRow(label, value) {
  if (value === undefined || value === null || value === '') return '';
  return '<div class="generation-info-row"><span>' + S.escapeHtml(label) + '</span><b>' + S.escapeHtml(String(value)) + '</b></div>';
}

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

  const type = meta.type || (message.videoUrl ? 'video' : (message.audioUrl ? 'music' : 'image'));
  if (type === 'image') restoreImageStateFromGenerationMetadata(meta);
  const imageUrl = meta.image_url || (type === 'image' ? (meta.full_url || meta.result_url) : '') || ((meta.result_images || [])[0]) || '';
  const videoUrl = meta.video_url || ((meta.videos || [])[0]) || (type === 'video' ? meta.result_url : '') || message.videoUrl || '';
  const audioUrl = meta.audio_url || ((meta.audios || [])[0]) || ((type === 'music' || type === 'voice') ? meta.result_url : '') || message.audioUrl || '';
  const resultUrl = type === 'video' ? videoUrl : ((type === 'music' || type === 'voice') ? audioUrl : (meta.full_url || meta.result_url || imageUrl));
  const previewUrl = imagePreviewUrl(meta, '');
  const previewFallbackUrl = meta.preview_fallback_url || imageUrl || resultUrl || '';
  const refImages = meta.reference_images || [];
  const created = meta.created_at ? new Date(meta.created_at).toLocaleString() : '';
  const settings = meta.settings || meta.image_options || meta.video_options || meta.music_options || meta.voice_options || {};
  const generationCost = meta.generation_cost
    || (meta.cost_usd !== undefined && meta.cost_usd !== null && meta.cost_usd !== '' ? '$' + Number(meta.cost_usd).toFixed(3) : '');
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
    ? '<div class="generation-info-preview">' + previewImgHtml(previewUrl, 'generated image', previewFallbackUrl) + '</div>'
    : type === 'video' && videoUrl
      ? '<div class="generation-info-preview generation-info-video-preview">' + (videoThumb ? previewImgHtml(videoThumb, 'video thumbnail') : '<span>VID</span>') + '</div>'
      : (type === 'music' || type === 'voice') && imageUrl
        ? '<div class="generation-info-preview">' + previewImgHtml(previewUrl, 'generated cover') + '</div>'
      : audioUrl
        ? '<div class="generation-info-preview generation-info-audio-preview"><span>' + S.escapeHtml(type === 'voice' ? 'VO' : '♪') + '</span></div>'
        : (previewUrl ? '<div class="generation-info-preview generation-info-audio-preview"><span>AI</span></div>' : '');
  let actionHtml = '';
  if (resultUrl) {
    if (type === 'music') {
      actionHtml += '<button type="button" data-audio-url="' + S.escapeHtml(audioUrl) + '" data-cover-url="' + S.escapeHtml(previewUrl || imageUrl || meta.cover_url || '') + '" data-title="' + S.escapeHtml(meta.title || 'SYLVEX Music') + '" data-result-kind="music" onclick="SYLVEX.playMusicTrack(event)">Открыть музыку</button>';
    } else {
      actionHtml += '<button type="button" ' + (type === 'image' ? 'data-image-url' : 'data-result-url') + '="' + S.escapeHtml(resultUrl) + '" data-result-kind="' + S.escapeHtml(type) + '" onclick="' + (type === 'image' ? 'SYLVEX.openImageViewer(event)' : 'SYLVEX.openGeneratedContent(event)') + '">Открыть</button>';
    }
    actionHtml += '<button type="button" data-result-url="' + S.escapeHtml(resultUrl) + '" data-result-kind="' + S.escapeHtml(type) + '" onclick="SYLVEX.openTelegramBot(event)">Перейти в Telegram</button>';
    if (type === 'image') {
      actionHtml += '<button type="button" data-image-url="' + S.escapeHtml(resultUrl) + '" onclick="SYLVEX.animateGeneratedImage(event)">Оживить фото</button>';
    } else if (type === 'video') {
      actionHtml += '<button type="button" data-video-url="' + S.escapeHtml(resultUrl) + '" onclick="SYLVEX.editGeneratedVideo(event)">Редактировать видео</button>';
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
    + (type === 'image' ? generationInfoRow('Generation Cost', generationCost) : '')
    + generationInfoRow('Duration', meta.duration || settings.duration)
    + generationInfoRow('Count', meta.count)
    + generationInfoRow('Created', created)
    + generationInfoRow('Telegram', meta.sent_to_telegram ? 'sent' : 'not sent')
    + '</div>'
    + (meta.prompt ? '<div class="generation-info-section"><div class="generation-info-label">Prompt</div><p class="generation-info-text">' + S.escapeHtml(meta.prompt) + '</p></div>' : '')
    + (refImages.length ? '<div class="generation-info-section"><div class="generation-info-label">Reference images</div><div class="generation-info-ref-row">' + refImages.map((url) => '<img src="' + S.escapeHtml(url) + '" alt="reference" />').join('') + '</div></div>' : '')
    + (actionHtml ? '<div class="generation-info-actions">' + actionHtml + '</div>' : '');

  drawer.classList.add('show');
}

function closeGenerationInfoDrawer(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const drawer = document.getElementById('generationInfoDrawer');
  if (drawer) drawer.classList.remove('show');
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

  const target = getUploadTarget();
  applyUploadToTarget(url, target);
  renderUploadedPhotoGrid();
  renderUploadPreviewForTarget(target);
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
panel.dataset.uploadTarget = getUploadTarget();
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
    else if (kind === 'video') { inp.accept = 'video/*'; pendingAttachAccept = 'video'; }
    else { inp.accept = '.txt,.md,.json,.csv,.pdf,.doc,.docx'; pendingAttachAccept = 'file'; }
    inp.value = '';
    inp.click();
  }

  async function uploadProStudioMediaFile(file, kind) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/public/prostudio/upload-media?kind=' + encodeURIComponent(kind || 'image'), {
      method: 'POST',
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok || !data.url) {
      throw new Error(data.error || 'Не удалось загрузить файл');
    }
    return String(data.url || '');
  }

  function attach(kind, target, e) {
    if (target && target.preventDefault) {
      e = target;
      target = '';
    }
    if (kind === 'video') {
      openNativeFilePicker('video');
      return;
    }
    if (target === 'start') return openVideoStartUpload(e);
    if (target === 'end') return openVideoEndUpload(e);
    if (target === 'reference' || target === 'references') return openVideoReferencesUpload(e);
    return openImageUpload(e);
  }
  function onAttachFile(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const pendingKind = pendingAttachAccept || 'file';
    const maxSize = pendingKind === 'video' ? 200 * 1024 * 1024 : 50 * 1024 * 1024;
    if (f.size > maxSize) {
      toast(pendingKind === 'video' ? 'Видео слишком большое (макс. 200 MB)' : 'Файл слишком большой (макс. 50 MB)');
      return;
    }
    if (pendingKind === 'video' && isVideoMode()) {
      uploadProStudioMediaFile(f, 'video')
        .then((url) => {
          const target = getUploadTarget();
          const config = currentVideoConfig() || {};
          if (target === UPLOAD_TARGETS.VIDEO_REFERENCES || videoState.section === 'motion' || config.motion_control) {
            applyVideoReferenceToState(url);
            toast('Видео добавлено как референс');
          } else {
            videoState.inputVideo = url;
            videoState.videoUrl = url;
            videoState.generationMode = 'video_edit';
            videoState.mode = 'video_edit';
            renderVideoReferencesPreview();
            toast('Видео загружено');
          }
          updateSendButton();
        })
        .catch((err) => {
          toast((err && err.message) || 'Не удалось загрузить видео');
        });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const b64 = result.split(',')[1] || '';
      const attachment = {
        kind: pendingAttachAccept || 'file',
        mime: f.type || 'application/octet-stream',
        name: f.name,
        dataBase64: b64,
      };
      if ((pendingAttachAccept || '') === 'image' && result) {
        const target = getUploadTarget();
        if (target === UPLOAD_TARGETS.IMAGE_UPLOAD) imageState.attachment = attachment;
        applyUploadToTarget(result, target);
        renderUploadedPhotoGrid();
        renderUploadPreviewForTarget(target);
        toast('Фото загружено');
      } else {
        setCurrentModeAttachment(attachment);
      }

      if ((isMusicMode() || isVoiceMode()) && result && (pendingAttachAccept || '') !== 'image') {
        const state = currentAudioState();
        state.uploads = (state.uploads || []).filter((item) => item.url !== result);
        state.uploads.push({
          kind: (pendingAttachAccept || 'file') === 'video' ? 'audio' : (pendingAttachAccept || 'file'),
          url: result,
          name: f.name,
          mime: f.type || 'application/octet-stream',
        });
        state.uploads = state.uploads.slice(0, 4);
        toast('Файл загружен');
      }

      try { updateSendButton(); } catch {}
    };
    reader.readAsDataURL(f);
  }
  function clearAttachment() {
    setCurrentModeAttachment(null);
    try { updateSendButton(); } catch {}
  }

  function videoTemplateText(key) {
    const lang = (typeof uiLang === 'function' && uiLang()) || 'ru';
    const dict = {
      ru: {
        video: 'Видео',
        catalogEmpty: 'Видео-шаблоны пока не настроены',
        uploadTitle: 'Загрузить изображение',
        uploadHint: 'PNG, JPG или вставить из буфера обмена',
        create: 'Создать',
        imageRequired: 'Загрузите изображение для видео-шаблона',
        ratioRequired: 'Выберите формат видео',
        templateVideoRequired: 'Для этого видео-шаблона нужно загрузить preview.mp4',
      },
      en: {
        video: 'Video',
        catalogEmpty: 'Video templates are not configured yet',
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
      models: ['kling_motion_3_0', 'kling_motion_2_6'],
      preferred_model: 'kling_motion_3_0',
      duration: 5,
      resolution: '720p',
      cost_credits: 95,
      generation_cost: '95 ⚡',
    }));
  }

  function closeVideoTemplateIntro() {
    const el = document.getElementById('videoTemplateIntro');
    if (el) el.remove();
  }

  function maybeShowVideoTemplateIntro(force) {
    if (!isVideoMode() || videoState.section !== 'generate') return;
    let seen = false;
    try { seen = sessionStorage.getItem(VIDEO_TEMPLATE_INTRO_KEY) === '1'; } catch {}
    if ((!force && seen) || document.getElementById('videoTemplateIntro')) return;
    try { sessionStorage.setItem(VIDEO_TEMPLATE_INTRO_KEY, '1'); } catch {}
    const intro = document.createElement('div');
    intro.id = 'videoTemplateIntro';
    intro.className = 'video-template-intro';
    intro.innerHTML = '<button type="button">' + S.escapeHtml(videoTemplateText('video')) + '</button>';
    const btn = intro.querySelector('button');
    if (btn) {
      btn.addEventListener('click', () => {
        closeVideoTemplateIntro();
        openVideoTemplatesCatalog();
      });
    }
    document.body.appendChild(intro);
    if (force) {
      const trigger = document.querySelector('[data-studio-mode-btn="video"]');
      if (trigger) {
        const rect = trigger.getBoundingClientRect();
        intro.classList.add('anchored');
        intro.style.left = (rect.left + rect.width / 2) + 'px';
        intro.style.top = (rect.bottom + 8) + 'px';
        intro.style.bottom = 'auto';
      }
      setTimeout(() => {
        const closeOnOutside = (event) => {
          if (!intro.contains(event.target) && !event.target.closest('[data-studio-mode-btn="video"]')) {
            closeVideoTemplateIntro();
            document.removeEventListener('pointerdown', closeOnOutside, true);
          }
        };
        document.addEventListener('pointerdown', closeOnOutside, true);
      }, 0);
    }
  }

  async function loadVideoTemplates() {
    if (Array.isArray(videoTemplatesCache)) return videoTemplatesCache;
    try {
      const res = await fetch('/api/public/prostudio/video-templates', { cache: 'no-store' });
      const data = await res.json().catch(() => ({}));
      videoTemplatesCache = normalizeVideoTemplateList(data.templates);
    } catch {
      videoTemplatesCache = normalizeVideoTemplateList([]);
    }
    return videoTemplatesCache;
  }

  function closeVideoTemplateModal() {
    activeVideoTemplate = null;
    videoTemplateUploadUrl = '';
    const modal = document.getElementById('videoTemplateModal');
    if (modal) modal.remove();
  }

  function closeVideoTemplatesCatalog() {
    closeVideoTemplateModal();
    const overlay = document.getElementById('videoTemplatesOverlay');
    if (overlay) overlay.remove();
  }

  function videoTemplateCostLabel(template) {
    const credits = Number(template && (template.cost_credits || template.cost) || 0);
    if (credits > 0) return '⚡ ' + credits;
    const label = template && template.generation_cost;
    return label ? String(label) : '';
  }

  function templatePreferredModel(template) {
    const models = Array.isArray(template && template.models) ? template.models : [];
    if ((template && template.preferred_model) === 'kling_motion_3_0' || models.includes('kling_motion_3_0') || !models.length) return 'kling_motion_3_0';
    if ((template && template.preferred_model) === 'kling_motion_2_6' || models.includes('kling_motion_2_6')) return 'kling_motion_2_6';
    return String((template && template.preferred_model) || models[0] || 'kling_motion_2_6');
  }

  function videoTemplateRatios(template) {
    const ratios = Array.isArray(template && template.ratios) ? template.ratios : [];
    const clean = ratios.filter((ratio) => ['16:9', '1:1', '9:16'].includes(String(ratio)));
    return clean.length ? clean : ['16:9', '1:1', '9:16'];
  }

  function videoTemplateReferenceVideo(template) {
    if (!template) return '';
    return String(template.reference_video || template.video_url || template.template_video_url || template.preview_video || '').trim();
  }

  function normalizeVideoTemplateList(items) {
    const incoming = Array.isArray(items) ? items : [];
    const defaults = defaultVideoTemplateItems();
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
    return Array.from(byId.values()).slice(0, 50);
  }

  async function openVideoTemplatesCatalog() {
    closeVideoTemplateIntro();
    const templates = await loadVideoTemplates();
    closeVideoTemplatesCatalog();
    const overlay = document.createElement('div');
    overlay.id = 'videoTemplatesOverlay';
    overlay.className = 'video-templates-overlay';
    overlay.innerHTML = '<div class="video-templates-panel">'
      + '<button class="video-templates-close" type="button" aria-label="Close">×</button>'
      + '<div class="video-templates-grid">'
      + (templates.length ? templates.map((template, index) => {
      const id = S.escapeHtml(template.id || String(index));
      const encodedId = encodeURIComponent(String(template.id || index));
      const title = S.escapeHtml(template.title || template.id || 'Video');
      const src = S.escapeHtml(videoTemplateReferenceVideo(template));
      const poster = S.escapeHtml(template.poster_url || '');
      const tall = index % 5 === 0 || String(template.aspect_ratio || '').includes('9:16');
      return '<button class="video-template-card ' + (tall ? 'tall' : '') + '" type="button" data-template-id="' + id + '" onclick="SYLVEX.openVideoTemplateFromCatalog(event,\'' + encodedId + '\')">'
        + '<span class="video-template-card-poster"><span>▶</span></span>'
        + (src ? '<video src="' + src + '"' + (poster ? ' poster="' + poster + '"' : '') + ' autoplay loop muted playsinline preload="metadata" onerror="this.style.display=\'none\'"></video>' : '')
        + '<span class="video-template-card-shade"></span>'
        + '<span class="video-template-card-title">' + title + '</span>'
        + '</button>';
      }).join('') : '<div class="video-templates-empty">' + S.escapeHtml(videoTemplateText('catalogEmpty')) + '</div>')
      + '</div></div>';
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) closeVideoTemplatesCatalog();
    });
    const closeBtn = overlay.querySelector('.video-templates-close');
    if (closeBtn) closeBtn.addEventListener('click', closeVideoTemplatesCatalog);
    document.body.appendChild(overlay);
  }

  function openVideoTemplateFromCatalog(event, id) {
    if (event) event.stopPropagation();
    try { id = decodeURIComponent(String(id || '')); } catch {}
    const templates = Array.isArray(videoTemplatesCache) ? videoTemplatesCache : [];
    const template = templates.find((item) => String(item.id) === String(id));
    if (template) openVideoTemplateModal(template);
  }

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

  function setVideoTemplateFile(file) {
    if (!file || !/^image\//.test(file.type || '')) return;
    const reader = new FileReader();
    reader.onload = () => {
      videoTemplateUploadUrl = String(reader.result || '');
      renderVideoTemplateUpload();
    };
    reader.readAsDataURL(file);
  }

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
      + '<div class="video-template-ratios">' + ratios.map((ratio) => '<button type="button" data-ratio="' + S.escapeHtml(ratio) + '" class="' + (ratio === videoTemplateRatio ? 'active' : '') + '"><span class="image-size-icon" data-ratio="' + S.escapeHtml(ratio) + '"></span>' + S.escapeHtml(ratio) + '</button>').join('') + '</div>'
      + '<button id="videoTemplateGenerate" class="video-template-generate" type="button">' + S.escapeHtml(videoTemplateText('create')) + (cost ? ' ' + S.escapeHtml(cost) : '') + '</button>'
      + '</div>'
      + '<input id="videoTemplateFileInput" type="file" accept="image/png,image/jpeg,image/jpg" hidden />'
      + '</div>';
    modal.addEventListener('click', (event) => {
      if (event.target === modal) closeVideoTemplateModal();
    });
    document.body.appendChild(modal);
    const closeBtn = modal.querySelector('.video-template-modal-close');
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
    if (generate) generate.addEventListener('click', startVideoTemplateGeneration);
    renderVideoTemplateUpload();
  }

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
    const referenceVideo = videoTemplateReferenceVideo(template);
    if (!referenceVideo) {
      toast(videoTemplateText('templateVideoRequired'));
      return;
    }
    const modelId = templatePreferredModel(template);
    const uploadedImage = videoTemplateUploadUrl;
    const selectedRatio = videoTemplateRatio;
    closeVideoTemplateModal();
    closeVideoTemplatesCatalog();
    updateComposerMode('video');
    videoState.modelId = modelId;
    videoState.provider = 'kling';
    videoState.section = 'generate';
    videoState.generationMode = 'motion_control';
    videoState.mode = 'motion_control';
    videoState.ratio = selectedRatio;
    videoState.duration = Number(template.duration || 5);
    videoState.resolution = template.resolution || '720p';
    videoState.sound = false;
    videoState.startImage = uploadedImage;
    videoState.inputVideo = referenceVideo;
    videoState.videoUrl = videoState.inputVideo;
    videoState.videoTemplate = {
      id: template.id || '',
      title: template.title || '',
      description: template.description || '',
      prompt: template.prompt || template.video_prompt || template.description || template.title || '',
      preview_video: template.preview_video || '',
      reference_video: referenceVideo,
      aspect_ratio: selectedRatio,
    };
    normalizeVideoStateForModel();
    renderVideoControls();
    renderUploadedPhotoGrid();
    updateImageUploadButtonPreview();

    const promptLabel = template.title || 'Video template';
    const promptText = template.prompt || template.video_prompt || template.description || template.title || '';
    chatMessages.push({
      role: 'user',
      text: promptLabel,
      referenceImages: [uploadedImage],
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
      videoState.videoTemplate = null;
      videoState.inputVideo = '';
      videoState.videoUrl = '';
      renderChat();
      rememberCurrentChatSpace();
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

  function updateComposerMode(kind) {
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
    const isMusic = isMusicMode();
    const isVoice = isVoiceMode();
    const isAudio = isMusic || isVoice;
    pendingAttachment = currentModeAttachment();
    const composer = document.getElementById('studioComposer');
    if (composer) composer.dataset.composerMode = isImage ? 'image' : isVoice ? 'voice' : isMusic ? 'music' : 'video';
    document.querySelectorAll('[data-studio-mode-btn]').forEach((btn) => {
      const modeBtn = btn.dataset.studioModeBtn;
      const isActive = isVideoSection
        ? modeBtn === (videoState.section === 'generate' ? 'video' : videoState.section)
        : modeBtn === kind;
      btn.classList.toggle('active', isActive);
    });
    document.querySelectorAll('.studio-mini-tab').forEach((btn) => btn.classList.remove('active'));
    const miniIndex = kind === 'image' ? 0 : isMusic ? 2 : isVoice ? 3 : 1;
    const minis = document.querySelectorAll('.studio-mini-tab');
    if (minis[miniIndex]) minis[miniIndex].classList.add('active');
    const ta = document.getElementById('chatInput');
    if (ta) ta.placeholder = isImage ? 'Describe your image' : isVoice ? 'Describe your voiceover' : isMusic ? 'Describe your music' : 'Describe your video';
    const mvc = document.getElementById('modelValComposer');
    if (isImage) {
      if (!imageState.modelId && IMAGE_MODEL_LIST.length) imageState.modelId = IMAGE_MODEL_LIST[0].id;
      renderImageControls();
      renderUploadedPhotoGrid();
      updateImageUploadButtonPreview();
      renderModelPop();
    } else if (mvc) {
      if (isAudio) {
        if (isMusic) {
          renderMusicControls();
        } else {
          mvc.textContent = 'Voice Generator';
        }
        renderUploadedPhotoGrid();
        updateImageUploadButtonPreview();
      } else {
        renderVideoControls();
        renderModelPop();
        renderUploadedPhotoGrid();
        updateImageUploadButtonPreview();
      }
    }
    if (!restoringChatSpace) restoreChatSpace(currentChatType());
    applyCurrentDraft();
    updateSendButton();
  }
  function genAction(kind, tabKey) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const sheet = document.getElementById('plusSheet');
    if (sheet) sheet.classList.remove('show');
    updateComposerMode(tabKey || kind);
    if (kind === 'video' && !tabKey) {
      setTimeout(() => maybeShowVideoTemplateIntro(true), 0);
    }
    const labels = { image:'Generate Image', video:'Generate Video', music:'Generate Music', voice:'Generate Voiceover' };
    toast(labels[kind] || kind);
  }
  function toggleHistory(e) {
    if (e) e.stopPropagation();
    const d = document.getElementById('histDrawer');
    const b = document.getElementById('histBackdrop');
    if (!d || !b) return;
    const on = !d.classList.contains('show');
    if (on) renderConvList();
    d.classList.toggle('show', on);
    b.classList.toggle('show', on);
  }
  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
  }

async function callGenerate(prompt, attachment, referenceImagesOverride, videoOptionsOverride, generationOptions) {
  const promptText = (prompt || '').trim();
  const imageReferenceImages = isImageMode() && Array.isArray(referenceImagesOverride)
    ? referenceImagesOverride.slice()
    : (isImageMode() ? (imageState.referenceImageUrls || []).slice() : []);
  const videoReferenceImages = isVideoMode()
    ? (Array.isArray(referenceImagesOverride) ? referenceImagesOverride.slice() : (videoState.referenceImageUrls || []).slice())
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
  const voiceOptions = isVoiceMode()
    ? Object.assign({}, voiceState, {
        uploads: (voiceState.uploads || []).slice(),
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
    history,
    attachment: attachment || null,
    conversation_id: currentConvId,
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
  });

  const res = await fetch('/api/public/prostudio/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache',
    },
    cache: 'no-store',
    body: JSON.stringify(payload),
  });

  const j = await res.json().catch(() => ({}));
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
    j.result = await waitGeneration(j.job_id, generationOptions || {});
  }

  return j;
}

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

function translateGenerationError(value, fallback) {
  const text = errorMessage(value, fallback || 'Во время генерации произошла временная ошибка сервиса. Попробуйте повторить попытку немного позже.');
  const low = String(text || '').toLowerCase();
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
  if (/quota|insufficient quota|credit.*exceed|limit.*exceed/.test(low)) {
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

function estimateFrontendGenerationCredits(imageOptionsSnapshot) {
  const known = !!(S.user && S.user.balance !== undefined && S.user.balance !== null);
  const balance = Number((S.user && S.user.balance) || 0);
  let required = 1;
  if (isImageMode()) {
    const modelId = (imageOptionsSnapshot && (imageOptionsSnapshot.modelId || imageOptionsSnapshot.model)) || imageState.modelId || '';
    const model = IMAGE_MODEL_LIST.find((item) => item.id === modelId) || {};
    const unit = Number(model.costCredits || 0);
    const count = Number((imageOptionsSnapshot && imageOptionsSnapshot.count) || imageState.count || 1);
    required = unit > 0 ? unit * Math.max(1, count || 1) : 1;
  }
  return { balance, required, known };
}

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

async function waitGeneration(jobId, options) {
  const onProgress = options && typeof options.onProgress === 'function' ? options.onProgress : null;
  while (true) {
    if (onProgress) onProgress(false);
    const res = await fetch(
      `/api/public/prostudio/job/${jobId}`,
      { cache: 'no-store' }
    );

    const job = await res.json().catch(() => ({}));
    if (!res.ok || !job.ok) {
      throw new Error(translateGenerationError(job, 'Не удалось проверить статус генерации. Попробуйте позже.'));
    }

    if (job.status === 'completed') {
      const result = job.result || {};
      result.job_id = result.job_id || job.job_id || jobId;
      result.generation_id = result.generation_id || job.generation_id || jobId;
      result.conversation_id = result.conversation_id || job.conversation_id || '';
      if (onProgress) onProgress(true);
      return result;
    }

    if (job.status === 'failed') {
      const error = job.error || {};
      throw new Error(translateGenerationError(error, 'Генерация не прошла. Попробуйте повторить немного позже.'));
    }

    if (!isActiveGenerationStatus(job.status)) {
      throw new Error('Генерация не завершилась. Попробуйте повторить немного позже.');
    }

    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}

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
    }
  }

   async function sendChat() {
    const ta = document.getElementById('chatInput');
    const v = (ta.value || '').trim();
    const attachment = currentModeAttachment();
    const referenceImages = isVideoMode()
      ? (videoState.referenceImageUrls || []).slice()
      : (isImageMode() ? (imageState.referenceImageUrls || []).slice() : []);
    const audioUploads = (isMusicMode() || isVoiceMode()) ? (currentAudioState().uploads || []).slice() : [];
    const imageOptionsSnapshot = isImageMode()
      ? imageOptionsPayload(referenceImages)
      : null;
    const videoOptionsSnapshot = isVideoMode() ? videoOptionsPayload(referenceImages) : null;

    if (!v && !attachment && !referenceImages.length && !audioUploads.length) return;

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
      return;
    }

    const photoMode = isImageMode();
    let loadingIndex = -1;
    if (photoMode) {
      loadingIndex = chatMessages.push({
        role: 'ai',
        generationLoading: true,
        progress: createGenerationProgress(generationKindForCurrentMode()),
      }) - 1;
    } else {
      chatMessages.push({
        role: 'user',
        text: v,
        attachmentName: null,
        referenceImages: referenceImages.length ? referenceImages : null,
      });
    }
    ta.value = ''; autoGrow(ta); updateSendButton();
    saveCurrentDraftSoon();
    clearAttachment();
    if (isVideoMode()) {
      videoState.characterImage = '';
      if (videoState.section !== 'edit') {
        videoState.inputVideo = '';
        videoState.videoUrl = '';
      }
    } else if (isMusicMode() || isVoiceMode()) {
      currentAudioState().uploads = [];
    }
    renderComposerImageDraft();
    renderUploadedPhotoGrid();
    updateImageUploadButtonPreview();
    if (!photoMode) {
      loadingIndex = chatMessages.push({
        generationLoading: true,
        role: 'ai',
        progress: createGenerationProgress(generationKindForCurrentMode()),
      }) - 1;
    }
    renderChat();
    rememberCurrentChatSpace();
    document.body.classList.add('ai-generating');
    S.haptic.impact('light');
    try {
      const start = await callGenerate(
        v,
        attachment,
        referenceImages,
        videoOptionsSnapshot,
        {
          onProgress: (completed) => updateGenerationLoadingProgress(loadingIndex, completed),
        }
      );
      renderChat();
      rememberCurrentChatSpace();

      const j = start.result || start;

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

        const resultType = isVideoMode()
          ? 'video'
          : (isMusicMode()
              ? 'music'
              : (isVoiceMode() ? 'voice' : 'file'));

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
        } else {
          chatMessages.push({
            role: 'ai',
            text: j.sent_to_telegram
              ? 'Готово ✅\nРезультат отправлен в Telegram-чат.'
              : 'Готово ✅\nГенерация завершена.'
          });
        }
      }
      loadConversations(); // refresh sidebar order
      rememberCurrentChatSpace();
    } catch (err) {
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
        return;
      }
      if (loadingIndex >= 0) chatMessages.splice(loadingIndex, 1);
      chatMessages.push({
        role: 'ai',
        text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.')
      });
      rememberCurrentChatSpace();
    } finally {
      document.body.classList.remove('ai-generating');
    }
    renderChat();
    rememberCurrentChatSpace();
  }
  function copyMsg(i) {
    const m = chatMessages[i]; if (!m) return;
    if (navigator.clipboard) navigator.clipboard.writeText(m.text || '');
    toast(t('copied'));
  }

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
    })
    .catch((err) => {
      chatMessages[i] = {
        role: 'ai',
        text: '⚠️ ' + translateGenerationError(err, 'Генерация не прошла. Попробуйте повторить немного позже.')
      };

      rememberCurrentChatSpace();
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
        if (!r.ok || !j.ok) throw new Error(translateGenerationError(j, 'Не удалось распознать голос. Попробуйте ещё раз.'));
        if (ta) { ta.value = (ta.value ? ta.value + ' ' : '') + (j.text || ''); autoGrow(ta); ta.focus(); }
      } catch (err) {
        toast(translateGenerationError(err, 'Не удалось распознать голос. Попробуйте ещё раз.'));
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
    rememberCurrentChatSpace();
    S.haptic.impact('light');
  }
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
      if (!(space.activeChatId || space.conversationId) && !(space.messages || []).length && !chatMessages.length) {
        const latest = latestConversationForType(type);
        if (latest && latest.id) openConv(latest.id, type, { silent: true });
      }
    } catch {}
  }
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
  function expandHistorySection(e, type) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    expandedHistorySections[chatTypeForMode(type)] = true;
    renderConvList();
  }
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
      if (nextType !== currentChatType()) {
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
        const resultType = metadata.type || (videos.length ? 'video' : (audios.length ? 'music' : (images.length ? 'image' : 'text')));
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
      chatSpaces[nextType] = { activeChatId: currentConvId, conversationId: currentConvId, messages: chatMessages.slice() };
      rememberCurrentChatSpace();
      renderChat();
      renderConvList();
      if (!options.silent) toggleHistory();
    } catch {
    } finally {
      if (openKey) openingConversations.delete(openKey);
    }
  }
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
    const activeReferences = isVideoMode()
      ? videoState.referenceImageUrls
      : (isImageMode() ? imageState.referenceImageUrls : []);
    const activeAttachment = currentModeAttachment();
    const activeAudioUploads = (isMusicMode() || isVoiceMode()) ? (currentAudioState().uploads || []) : [];
    const has = (ta.value || '').trim().length > 0
      || !!activeAttachment
      || !!(activeReferences && activeReferences.length)
      || !!(isVideoMode() && videoState.inputVideo)
      || !!(activeAudioUploads && activeAudioUploads.length);
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
      chatInput.addEventListener('input', () => {
        updateSendButton();
        saveCurrentDraftSoon();
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

  function initializeProStudioComposerMode() {
    const composer = document.getElementById('studioComposer');
    const initialMode = savedInitialStudioMode() || (composer && composer.dataset && composer.dataset.composerMode) || 'video';
    updateComposerMode(chatTypeForMode(initialMode));
  }

  /* ==========================================
     GLOBAL AUDIO PLAYER
     ========================================== */
  const PLAYER_VOLUME_KEY = 'sylvex-global-audio-volume';

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

  function collectMusicPlaylist(seedTrack) {
    const tracks = [];
    const seen = new Set();
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
      const move = (ev) => this.seekFromEvent(ev);
      const up = (ev) => {
        this.seekFromEvent(ev);
        this.progressDragging = false;
        document.removeEventListener('mousemove', move);
        document.removeEventListener('touchmove', move);
        document.removeEventListener('mouseup', up);
        document.removeEventListener('touchend', up);
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('touchmove', move, { passive: false });
      document.addEventListener('mouseup', up);
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

  function initAudioPlayer() {
    PlayerManager.init();
  }

  function openAudioPlayer(track, playlist = null, index = 0) {
    if (playlist) PlayerManager.open(playlist, index);
    else PlayerManager.playTrack(track);
  }

  /* ===== Init (called after cabinet.html is injected) ===== */
  function init() {
    // Restore saved theme.
    const tg = S.tg;
    const savedTheme = localStorage.getItem('sylvex-theme') || (tg && tg.colorScheme === 'light' ? 'light' : 'dark');
    S.setTheme(savedTheme);

    bindEvents();
    initAudioPlayer();
    initializeProStudioComposerMode();
    applyLang();       // triggers renderDynamic
    initHero();
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
    loadProStudioSync();
  }

  // Expose to global scope.
  Object.assign(S, {
    init, renderDynamic, renderChat, renderModeStrip, renderModelPop,
    selMode, pickModel, pickModelKey, toggleModelPop, togglePlusPop, closePlusSheet,
    openImageOptionMenu, showImageModelPicker, pickImageOption, pickMusicOption, resetMusicSettings, resetImageSettings, onImageSeedInput, toggleImageSeedTooltip, updateComposerMode, renderVideoControls,
    pickVisualReference, openVisualPicker, closeVisualPicker, openVisualCreateModal, closeVisualCreateModal, updateVisualCreateDraft, pickVisualCreatePhoto, removeVisualCreatePhoto, saveVisualCreateDraft,
    attach, openImageUpload, openVideoStartUpload, openVideoEndUpload, openVideoReferencesUpload, openNativeFilePicker, onAttachFile, clearAttachment, addMediaLink, openUploadPanel, closeUploadPanel, openUploadImagePreview, closeUploadImagePreview, selectGeneratedImage, selectUploadedPhoto, removeUploadedPhoto, clearCurrentUploadTarget, clearVideoReference, confirmUploadedPhotos, removeComposerImageDraft, genAction, toggleHistory, autoGrow, toggleMic,
    sendChat, copyMsg, regenMsg, deleteMsg, newChat,
    openConv, deleteConv, expandHistorySection, openPaywall, closePaywall, openShopFromPaywall, openShopForGeneration, resumePendingGeneration, updateSendButton,
    openBuy, closeBuy, payWith, contactAdmin,
    openSupport, closeSupport, sendSupport,
    computePrice, updatePrice, generateNow,
    renderSubscription, openSubActive, renewFromModal, openManageSub, closeModal, openProInfo,
    openEditProfile, pickAvatar, saveEditProfile,
    openThemePicker, applyTheme,
    openReferrals, copyRefLink, activateRefLink,
    signOut, openImageViewer, closeImageViewer, openGeneratedContent, openMusicInPlayer, playMusicTrack, playMusicTrackFromMessage, toggleStudioAudioPlayer, openTelegramBot, animateGeneratedImage, editGeneratedVideo, openGenerationInfoDrawer, closeGenerationInfoDrawer,
    initAudioPlayer,
    openAudioPlayer,
    PlayerManager,
    get studioMode() { return studioMode; },
    get activeCat() { return activeCat; }
  });

  // Also expose the inline-onclick handlers as globals.
  window.toggleModelPop = toggleModelPop;
  window.openImageOptionMenu = openImageOptionMenu;
  window.onImageSeedInput = onImageSeedInput;
  window.toggleImageSeedTooltip = toggleImageSeedTooltip;
  window.resetImageSettings = resetImageSettings;
  window.showImageModelPicker = showImageModelPicker;
  window.togglePlusPop  = togglePlusPop;
  window.attach         = attach;
  window.openImageUpload = openImageUpload;
  window.openVideoStartUpload = openVideoStartUpload;
  window.openVideoEndUpload = openVideoEndUpload;
  window.openVideoReferencesUpload = openVideoReferencesUpload;
  window.openNativeFilePicker = openNativeFilePicker;
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
  window.toggleStudioAudioPlayer = toggleStudioAudioPlayer;
  window.PlayerManager = PlayerManager;
  window.animateGeneratedImage = animateGeneratedImage;
  window.editGeneratedVideo = editGeneratedVideo;
  window.openGenerationInfoDrawer = openGenerationInfoDrawer;
  window.closeGenerationInfoDrawer = closeGenerationInfoDrawer;
  window.expandHistorySection = expandHistorySection;
  window.clearCurrentUploadTarget = clearCurrentUploadTarget;
  window.pickVisualReference = pickVisualReference;
  window.openVisualPicker = openVisualPicker;
  window.closeVisualPicker = closeVisualPicker;
  window.openVisualCreateModal = openVisualCreateModal;
  window.closeVisualCreateModal = closeVisualCreateModal;
  window.updateVisualCreateDraft = updateVisualCreateDraft;
  window.pickVisualCreatePhoto = pickVisualCreatePhoto;
  window.removeVisualCreatePhoto = removeVisualCreatePhoto;
  window.saveVisualCreateDraft = saveVisualCreateDraft;

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
  S.clearCurrentUploadTarget = clearCurrentUploadTarget;
  S.pickVisualReference = pickVisualReference;
  S.openVisualPicker = openVisualPicker;
  S.closeVisualPicker = closeVisualPicker;
  S.openVisualCreateModal = openVisualCreateModal;
  S.closeVisualCreateModal = closeVisualCreateModal;
  S.updateVisualCreateDraft = updateVisualCreateDraft;
  S.pickVisualCreatePhoto = pickVisualCreatePhoto;
  S.removeVisualCreatePhoto = removeVisualCreatePhoto;
  S.saveVisualCreateDraft = saveVisualCreateDraft;
  S.pickImageOption = pickImageOption;
  S.pickMusicOption = pickMusicOption;
  S.resetMusicSettings = resetMusicSettings;
  S.openTelegramBot = openTelegramBot;
  S.openGeneratedContent = openGeneratedContent;
  S.openMusicInPlayer = openMusicInPlayer;
  S.playMusicTrack = playMusicTrack;
  S.playMusicTrackFromMessage = playMusicTrackFromMessage;
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
  S.expandHistorySection = expandHistorySection;
  S.showImageModelPicker = showImageModelPicker;
  S.updateComposerMode = updateComposerMode;
  S.renderVideoControls = renderVideoControls;
  S.addMediaLink = addMediaLink;
  S.openVideoTemplatesCatalog = openVideoTemplatesCatalog;
  S.closeVideoTemplatesCatalog = closeVideoTemplatesCatalog;
  S.closeVideoTemplateModal = closeVideoTemplateModal;
  S.openVideoTemplateFromCatalog = openVideoTemplateFromCatalog;
  
  document.addEventListener('pointerdown', handleImageStyleInfoOutsideTouch, true);
  document.addEventListener('pointerdown', closeImageSeedTooltipOnOutside, true);
  document.addEventListener('touchmove', hideImageStyleInfo, true);
  document.addEventListener('wheel', hideImageStyleInfo, true);
  document.addEventListener('scroll', hideImageStyleInfo, true);

  })();
