// SYLVEX services used by the video editor: uploads, AI actions, project
// storage, transcription and the Telegram environment. Each AI action is a
// SYLVEX action ("Generate Video", "Voice-over", ...); which provider and
// model performs it is decided by the server (/api/public/video-editor/actions).
// Nothing here knows the rendering engine.

const JOB_POLL_MS = 2500;
const STORAGE_WAIT_MS = 90000;

export class ServiceError extends Error {
  constructor(code, message) {
    super(code);
    this.code = code;
    if (message) this.serverMessage = message;
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Media served by this application is used from the page's own origin, so
// thumbnails, waveforms and the engine can read it without cross-origin rules.
export function localMediaUrl(url) {
  const value = String(url || '');
  if (!/^https?:\/\//i.test(value) || typeof location === 'undefined') return value;
  try {
    const parsed = new URL(value);
    if (parsed.origin !== location.origin && /^\/(api\/public\/storage|webapp\/generated|generated|static\/generated)\//.test(parsed.pathname)) return parsed.pathname + parsed.search;
  } catch (_) {}
  return value;
}

function errorFor(status, data, fallback) {
  const body = data || {};
  if (status === 401) return new ServiceError('login_required');
  if (status === 402 || body.paywall) return new ServiceError('insufficient_balance', body.message || body.error);
  if (status === 403 && body.subscription_required) return new ServiceError('subscription_required');
  if (status === 409) return new ServiceError('active_generation');
  const message = typeof body.message === 'string' ? body.message : (typeof body.error === 'string' && /[а-яё]/i.test(body.error) ? body.error : '');
  return new ServiceError(body.error && /^[a-z_]+$/.test(body.error) ? body.error : fallback, message);
}

export function createServices({ fetchImpl } = {}) {
  const request = (url, options) => (fetchImpl || globalThis.fetch)(url, options);
  let actionsCache = null;
  let voicesCache = null;

  async function json(url, options = {}, fallback = 'request_failed') {
    let response;
    try {
      response = await request(url, Object.assign({ cache: 'no-store' }, options));
    } catch (_) {
      throw new ServiceError('network_error');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw errorFor(response.status, data, fallback);
    return data;
  }

  const post = (url, body, fallback) => json(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' }, body: JSON.stringify(body) }, fallback);

  // ------------------------------------------------------------- uploads

  // Durable upload of a file to SYLVEX storage with progress (0..1).
  function upload(file, kind, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file, file.name || ('media.' + (kind === 'image' ? 'png' : kind === 'audio' ? 'mp3' : 'mp4')));
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/public/prostudio/upload-media?kind=' + encodeURIComponent(kind));
      xhr.withCredentials = true;
      try {
        const tg = telegram();
        if (tg && tg.initData) xhr.setRequestHeader('X-Telegram-Init-Data', tg.initData);
      } catch (_) {}
      xhr.upload.onprogress = (event) => { if (onProgress && event.lengthComputable) onProgress(event.loaded / event.total); };
      xhr.onerror = () => reject(new ServiceError('upload_failed'));
      xhr.onload = () => {
        let data = {};
        try { data = JSON.parse(xhr.responseText || '{}'); } catch (_) {}
        if (xhr.status === 413 || /too large/i.test(String(data.error || ''))) { reject(new ServiceError('upload_too_large')); return; }
        if (xhr.status < 200 || xhr.status >= 300 || !data.ok || !data.url) { reject(xhr.status === 401 ? new ServiceError('login_required') : new ServiceError('upload_failed')); return; }
        resolve({ url: localMediaUrl(data.url), kind: data.kind, meta: data.video_meta || null });
      };
      xhr.send(form);
    });
  }

  // ---------------------------------------------------------------- jobs

  async function waitJob(jobId, { onStatus, signal } = {}) {
    let transient = 0;
    while (true) {
      if (signal && signal.aborted) throw new ServiceError('cancelled');
      let job;
      try {
        job = await json('/api/public/prostudio/job/' + encodeURIComponent(jobId), {}, 'job_failed');
        transient = 0;
      } catch (error) {
        if (error.code === 'network_error' && transient++ < 20) { await sleep(JOB_POLL_MS); continue; }
        throw error;
      }
      if (onStatus) onStatus(job.status);
      if (job.status === 'completed') return job.result || {};
      if (job.status === 'failed' || job.status === 'cancelled') {
        const error = job.error || {};
        throw new ServiceError('generation_failed', typeof error.message === 'string' ? error.message : '');
      }
      await sleep(JOB_POLL_MS);
    }
  }

  // A finished generation may still carry the provider's temporary link
  // while SYLVEX copies the file to its own storage; the editor keeps only
  // the durable copy.
  async function durableResult(jobId, result) {
    const started = Date.now();
    let current = result;
    while (current.storage_status === 'pending' && Date.now() - started < STORAGE_WAIT_MS) {
      await sleep(3000);
      try {
        const job = await json('/api/public/prostudio/job/' + encodeURIComponent(jobId), {}, 'job_failed');
        current = job.result || current;
      } catch (_) {}
    }
    return current;
  }

  async function generate(payload, options = {}) {
    const start = await post('/api/public/prostudio/generate', Object.assign({
      history: [], attachment: null, conversation_id: null,
      client_request_id: 'video-editor-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
      language: 'ru',
    }, payload), 'generation_failed');
    const jobId = start.job_id || start.generation_id;
    if (!jobId) throw new ServiceError('generation_failed');
    if (options.onJob) options.onJob(jobId);
    const result = await waitJob(jobId, options);
    return Object.assign({ jobId }, await durableResult(jobId, result));
  }

  const firstUrl = (result, keys) => {
    for (const key of keys) {
      const value = result[key];
      if (typeof value === 'string' && value) return localMediaUrl(value);
      if (Array.isArray(value) && value[0]) return localMediaUrl(typeof value[0] === 'string' ? value[0] : value[0].url || '');
    }
    return '';
  };

  async function estimate(payload) {
    try {
      const data = await post('/api/public/prostudio/estimate', payload, 'estimate_failed');
      return data.pricing_available === false ? null : Number(data.credits || 0) || null;
    } catch (_) {
      return null;
    }
  }

  async function actions() {
    if (!actionsCache) actionsCache = json('/api/public/video-editor/actions', {}, 'config_failed').then((data) => data.actions).catch((error) => { actionsCache = null; throw error; });
    return actionsCache;
  }

  // Closest ratio the video service offers for the project frame.
  function ratioFor(width, height, ratios) {
    const list = ratios && ratios.length ? ratios : ['16:9', '9:16', '1:1'];
    if (!width || !height) return list.includes('16:9') ? '16:9' : list[0];
    const target = width / height;
    return list.filter((item) => /^\d+:\d+$/.test(item)).reduce((best, item) => {
      const [w, h] = item.split(':').map(Number);
      return Math.abs(w / h - target) < Math.abs(best.value - target) ? { item, value: w / h } : best;
    }, { item: list[0], value: 99 }).item;
  }

  function videoPayload(config, { prompt, imageUrl, videoUrl, videoDuration, width, height, duration }) {
    const model = config.model;
    const image = imageUrl || '';
    const video = videoUrl || '';
    return {
      prompt: String(prompt || '').trim(),
      mode: 'video', category: 'video', model, provider: '',
      video_options: {
        model,
        duration: Number(duration) || config.duration || 5,
        ratio: ratioFor(width, height, config.ratios),
        resolution: config.resolution || '720p',
        generation_mode: image ? 'image_to_video' : 'text_to_video',
        mode: image ? 'image_to_video' : 'text_to_video',
        start_image: image, image_url: image,
        video_url: video, input_video: video,
        video_references: video ? [video] : [],
        input_video_duration: video ? Math.ceil(Number(videoDuration) || 0) : undefined,
        sound: true,
        source: 'video_editor',
      },
    };
  }

  function musicPayload(config, { prompt, vocal }) {
    return {
      prompt: String(prompt || '').trim(),
      mode: 'music', category: 'music', model: config.model, provider: '',
      music_options: { model: config.model, genre: 'auto', duration: 'auto', duration_seconds: null, duration_minutes: null, mood: 'auto', tempo: 'auto', theme: 'auto', vocal: vocal ? 'auto' : 'instrumental', source: 'video_editor' },
    };
  }

  function voicePayload(config, { text, voiceId, voiceName }) {
    const block = { voice_id: String(voiceId || ''), voice_name: String(voiceName || '').slice(0, 80), text: String(text || '').trim() };
    return {
      prompt: block.text,
      mode: 'voice', category: 'voice', model: config.model, provider: 'elevenlabs',
      voice_options: { model: config.model, provider: 'elevenlabs', elevenlabs_tool: 'dialogue', dialogue_blocks: [block], source: 'video_editor' },
    };
  }

  function enhancePayload({ url, level, start, end }) {
    return {
      prompt: 'SYLVEX Enhance', mode: 'video', category: 'video', model: 'sylvex_enhance_video', provider: 'runway',
      video_options: { tool: 'enhance_video', enhanceSourceUrl: url, enhanceLevel: level, enhanceStart: start, enhanceEnd: end, source: 'video_editor' },
    };
  }

  function animatePayload(config, { imageUrl, prompt }) {
    return {
      prompt: String(prompt || '').trim() || 'Оживить фото',
      mode: 'video', category: 'video', model: config.model, provider: config.provider || 'runway',
      video_options: { tool: config.tool || 'animate_photo', animatePhotoSourceUrl: imageUrl, animatePhotoPrompt: String(prompt || '').trim(), source: 'video_editor' },
    };
  }

  const api = {
    localMediaUrl,
    upload,
    actions,
    async listVoices() {
      if (!voicesCache) {
        voicesCache = json('/api/public/prostudio/elevenlabs-voices', { cache: 'default' }, 'voices_failed').then((data) => (Array.isArray(data.voices) ? data.voices : []).map((item) => ({
          id: String(item.voice_id || item.voiceId || item.id || ''),
          name: String(item.name || item.label || ''),
          gender: String(item.gender || (item.labels && item.labels.gender) || '').toLowerCase(),
          accent: String(item.accent || (item.labels && item.labels.accent) || ''),
          description: String(item.description || (item.labels && (item.labels.description || item.labels.use_case)) || ''),
          previewUrl: String(item.preview_url || item.previewUrl || ''),
        })).filter((voice) => voice.id && voice.name)).catch((error) => { voicesCache = null; throw error; });
      }
      return voicesCache;
    },

    // --- prices shown before a paid action
    async estimateVideo(input) { const config = (await actions()).generateVideo; return estimate(videoPayload(config, input)); },
    async estimateMusic(input) { const config = (await actions()).generateMusic; return estimate(musicPayload(config, input)); },
    async estimateVoice(input) { const config = (await actions()).voiceOver; return estimate(voicePayload(config, input)); },
    async estimateEnhance({ url, start, end }) {
      return post('/api/public/video-editor/enhance-estimate', { url, start, end }, 'enhance_prepare_failed');
    },

    // --- AI actions. Each resolves to a durable media URL.
    async generateVideo(input, options) {
      const config = (await actions()).generateVideo;
      const result = await generate(videoPayload(config, input), options);
      const url = firstUrl(result, ['video_url', 'videos', 'result_url', 'url']);
      if (!url) throw new ServiceError('generation_failed');
      return { url, jobId: result.jobId, durable: result.storage_status !== 'pending' && result.storage_status !== 'failed' };
    },
    async animatePhoto(input, options) {
      const config = (await actions()).animatePhoto;
      const result = await generate(animatePayload(config, input), options);
      const url = firstUrl(result, ['video_url', 'videos']);
      if (!url) throw new ServiceError('generation_failed');
      return { url, jobId: result.jobId, durable: true };
    },
    async generateMusic(input, options) {
      const config = (await actions()).generateMusic;
      const result = await generate(musicPayload(config, input), options);
      const url = firstUrl(result, ['audio_url', 'audios', 'music_url', 'audio_urls']);
      if (!url) throw new ServiceError('generation_failed');
      return { url, jobId: result.jobId, title: String(result.title || ''), durable: result.storage_status !== 'pending' && result.storage_status !== 'failed' };
    },
    async voiceOver(input, options) {
      const config = (await actions()).voiceOver;
      const result = await generate(voicePayload(config, input), options);
      const url = firstUrl(result, ['audio_url', 'audios', 'audio_urls']);
      if (!url) throw new ServiceError('generation_failed');
      return { url, jobId: result.jobId, durable: result.storage_status !== 'pending' && result.storage_status !== 'failed' };
    },
    async enhanceVideo(input, options) {
      const result = await generate(enhancePayload(input), options);
      const url = firstUrl(result, ['video_url', 'videos']);
      if (!url) throw new ServiceError('generation_failed');
      return { url, jobId: result.jobId, durable: true };
    },
    async transcribe({ url, language }) {
      const data = await post('/api/public/video-editor/transcribe', { url, language: language || '', client_request_id: 'transcribe-' + Date.now().toString(36) }, 'transcribe_failed');
      return { segments: data.segments || [], language: data.language || '', duration: data.duration || 0, credits: data.cost_credits || 0 };
    },

    // --- projects (SYLVEX-owned state)
    async saveProject(project) {
      const data = await json('/api/public/video-editor/projects/' + encodeURIComponent(project.id), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project }),
      }, 'project_save_failed');
      return { shareToken: data.shareToken || '' };
    },
    async loadProject(id, token) {
      const data = await json('/api/public/video-editor/projects/' + encodeURIComponent(id) + (token ? '?token=' + encodeURIComponent(token) : ''), {}, 'project_not_found');
      const project = data.project;
      Object.values(project.media || {}).forEach((media) => {
        media.url = localMediaUrl(media.url);
        if (media.poster) media.poster = localMediaUrl(media.poster);
      });
      return { project, shareToken: data.shareToken || '', owner: !!data.owner };
    },
    async listProjects() { return (await json('/api/public/video-editor/projects', {}, 'projects_failed')).projects || []; },
    async deleteProject(id) { await json('/api/public/video-editor/projects/' + encodeURIComponent(id), { method: 'DELETE' }, 'project_delete_failed'); },

    // --- environment
    telegram,
    environment,
  };
  return api;
}

// Telegram Mini App object of this page or of the Mini App that embeds it.
export function telegram() {
  const read = (win) => { try { const tg = win && win.Telegram && win.Telegram.WebApp; return tg && tg.initData ? tg : null; } catch (_) { return null; } };
  if (typeof window === 'undefined') return null;
  return read(window) || (window.parent !== window ? read(window.parent) : null);
}

// What this environment can do, detected one capability at a time so a
// missing one never blocks the whole editor.
export function environment() {
  const tg = telegram();
  return {
    telegram: !!tg,
    platform: tg ? String(tg.platform || '') : 'web',
    // Telegram can save a file from a link (Bot API 8.0 downloadFile).
    nativeDownload: !!(tg && typeof tg.downloadFile === 'function'),
    openLink: (url) => {
      if (tg && typeof tg.openLink === 'function') { tg.openLink(url); return true; }
      return !!window.open(url, '_blank', 'noopener');
    },
    downloadFile: (url, fileName) => new Promise((resolve) => {
      if (!(tg && typeof tg.downloadFile === 'function')) { resolve(false); return; }
      try { tg.downloadFile({ url, file_name: fileName }, (accepted) => resolve(accepted !== false)); } catch (_) { resolve(false); }
    }),
  };
}
