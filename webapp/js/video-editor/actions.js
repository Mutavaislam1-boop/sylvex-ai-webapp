// SYLVEX action layer of the video editor.
//
//   UI  →  these actions  →  SYLVEX services (uploads, AI, storage)
//                         →  editor core (project operations)  →  engine
//
// Every AI action returns its media into the project as a normal asset:
// a durable SYLVEX URL plus a clip (picture track) or an audio clip.
// Buttons in the UI name actions, never providers or models.
import { probeMedia, kindOfFile } from './editor.js';
import { speechSources, clipDuration } from './project.js';

const AUTOSAVE_MS = 1500;
const UPLOAD_KINDS = { video: 'video', image: 'image', audio: 'audio' };
// Upload limits of SYLVEX storage (upload-media).
const UPLOAD_LIMITS = { video: 200 * 1024 * 1024, image: 50 * 1024 * 1024, audio: 50 * 1024 * 1024 };

export function createEditorActions({ editor, services, onState } = {}) {
  const uploads = new Map(); // mediaId -> { progress, promise, failed }
  const state = { job: null, transcribing: false, save: 'idle', shareToken: '', saveError: '' };
  let saveTimer = 0;
  let saving = null;
  let savedContent = '';
  let destroyed = false;

  const notify = () => { if (onState && !destroyed) onState(Object.assign({}, state, { uploads: uploadState() })); };

  function uploadState() {
    const out = {};
    uploads.forEach((value, key) => { out[key] = { progress: value.progress, failed: value.failed }; });
    return out;
  }

  // ------------------------------------------------------------- uploads

  function startUpload(mediaId, file) {
    const kind = UPLOAD_KINDS[editor.project.media[mediaId] && editor.project.media[mediaId].kind] || 'video';
    const entry = { progress: 0, failed: '', promise: null, file };
    uploads.set(mediaId, entry);
    notify();
    const tooLarge = file && file.size > UPLOAD_LIMITS[kind];
    entry.promise = (tooLarge ? Promise.reject(Object.assign(new Error('upload_too_large'), { code: 'upload_too_large' }))
      : services.upload(file, kind, (ratio) => { entry.progress = ratio; notify(); }))
      .then((result) => {
        if (editor.project.media[mediaId]) editor.updateMedia(mediaId, { url: result.url });
        uploads.delete(mediaId);
        notify();
        scheduleSave();
        return result.url;
      })
      .catch((error) => {
        entry.failed = error.code || 'upload_failed';
        notify();
        throw error;
      });
    entry.promise.catch(() => {});
    return entry.promise;
  }

  // Files from the device: added at once from a local copy, uploaded to
  // SYLVEX storage in the background so the project can be saved.
  async function importFiles(files, { at, start } = {}) {
    const added = [];
    let index = Number.isInteger(at) ? at : undefined;
    for (const file of Array.from(files || [])) {
      const kind = kindOfFile(file);
      if (!kind) throw Object.assign(new Error('unsupported_file'), { code: 'unsupported_file' });
      let id;
      if (kind === 'audio') id = await editor.addAudio(file, { start: start || 0, role: 'audio' });
      else if (kind === 'image') id = await editor.addImage(file, { index });
      else id = await editor.addVideo(file, { index });
      if (index !== undefined) index += 1;
      const media = editor.mediaOf(id);
      if (media) startUpload(media.id, file);
      added.push({ id, kind });
    }
    return added;
  }

  // Durable URL of a media file, waiting for its upload when needed.
  async function durableUrl(mediaId) {
    const media = editor.project.media[mediaId];
    if (!media) throw Object.assign(new Error('media_not_found'), { code: 'media_not_found' });
    if (media.url) return media.url;
    const entry = uploads.get(mediaId);
    if (!entry) throw Object.assign(new Error('media_not_uploaded'), { code: 'media_not_uploaded' });
    if (entry.failed) throw Object.assign(new Error(entry.failed), { code: entry.failed });
    return entry.promise;
  }

  const pendingUploads = () => Array.from(uploads.values()).filter((entry) => !entry.failed).length;

  // ---------------------------------------------------------------- jobs

  async function runJob(label, work) {
    if (state.job) throw Object.assign(new Error('active_generation'), { code: 'active_generation' });
    state.job = { label, startedAt: Date.now(), status: 'queued' };
    notify();
    try {
      return await work((status) => { if (state.job) { state.job.status = status; notify(); } });
    } finally {
      state.job = null;
      notify();
    }
  }

  async function measured(url, kind) {
    try { return await probeMedia(url, kind); } catch (_) { return { duration: 0, width: 0, height: 0, hasAudio: true }; }
  }

  function clipIndex(clipId) {
    return editor.project.videoClips.findIndex((clip) => clip.id === clipId);
  }

  // --------------------------------------------------------- AI actions

  // "Generate Video": a prompt, optionally the selected image or video as
  // the starting point. The result goes after that clip (or at the end).
  function generateVideo({ prompt, sourceClipId, duration } = {}) {
    return runJob('Generate Video', async (onStatus) => {
      const project = editor.project;
      const frame = project.settings;
      const input = { prompt, duration, width: frame.width, height: frame.height };
      let index;
      if (sourceClipId) {
        const clip = project.videoClips.find((item) => item.id === sourceClipId);
        const media = clip && project.media[clip.mediaId];
        if (media && media.kind === 'image') input.imageUrl = await durableUrl(media.id);
        if (media && media.kind === 'video') { input.videoUrl = await durableUrl(media.id); input.videoDuration = media.duration; }
        if (clip) index = clipIndex(clip.id) + 1;
      }
      const result = await services.generateVideo(input, { onStatus });
      const meta = await measured(result.url, 'video');
      return editor.addGeneratedClip({ kind: 'video', url: result.url, name: 'AI-видео', origin: 'generate_video', label: 'Generate Video', duration: meta.duration, width: meta.width, height: meta.height, hasAudio: meta.hasAudio }, { index });
    });
  }

  // "Animate Photo": the selected image becomes a short video clip next to it.
  function animatePhoto({ clipId, prompt } = {}) {
    return runJob('Animate Photo', async (onStatus) => {
      const clip = editor.project.videoClips.find((item) => item.id === clipId);
      const media = clip && editor.project.media[clip.mediaId];
      if (!media || media.kind !== 'image') throw Object.assign(new Error('select_image'), { code: 'select_image' });
      const imageUrl = await durableUrl(media.id);
      const result = await services.animatePhoto({ imageUrl, prompt }, { onStatus });
      const meta = await measured(result.url, 'video');
      return editor.addGeneratedClip({ kind: 'video', url: result.url, name: 'Ожившее фото', origin: 'animate_photo', label: 'Animate Photo', duration: meta.duration, width: meta.width, height: meta.height, hasAudio: meta.hasAudio }, { index: clipIndex(clip.id) + 1 });
    });
  }

  // "Generate Music": an audio clip at `start` on a free audio track.
  function generateMusic({ prompt, vocal, start } = {}) {
    return runJob('Generate Music', async (onStatus) => {
      const result = await services.generateMusic({ prompt, vocal }, { onStatus });
      const meta = await measured(result.url, 'audio');
      return editor.addGeneratedAudio({ url: result.url, name: result.title || 'AI-музыка', origin: 'generate_music', label: 'Generate Music', duration: meta.duration }, { start: start || 0, role: 'music' });
    });
  }

  // "Voice-over": text spoken by a voice of the SYLVEX voice library.
  function voiceOver({ text, voiceId, voiceName, start } = {}) {
    return runJob('Voice-over', async (onStatus) => {
      const result = await services.voiceOver({ text, voiceId, voiceName }, { onStatus });
      const meta = await measured(result.url, 'audio');
      return editor.addGeneratedAudio({ url: result.url, name: 'Озвучка · ' + (voiceName || 'голос'), origin: 'voice_over', label: 'Voice-over', duration: meta.duration }, { start: start || 0, role: 'voice' });
    });
  }

  // "Enhance Video" of the selected clip's exact part. "replace" puts the
  // enhanced version into the clip (the original stays in the project and
  // can be restored); "add" places it next to the original.
  function enhanceVideo({ clipId, level, mode = 'replace' } = {}) {
    return runJob('Enhance Video', async (onStatus) => {
      const clip = editor.project.videoClips.find((item) => item.id === clipId);
      const media = clip && editor.project.media[clip.mediaId];
      if (!media || media.kind !== 'video') throw Object.assign(new Error('select_video'), { code: 'select_video' });
      const url = await durableUrl(media.id);
      const result = await services.enhanceVideo({ url, level, start: clip.sourceStart, end: clip.sourceEnd }, { onStatus });
      const meta = await measured(result.url, 'video');
      const item = {
        kind: 'video', url: result.url, name: media.name + ' · улучшено', origin: 'enhance_video', label: 'Enhance Video',
        duration: meta.duration || clipDuration(clip), width: meta.width, height: meta.height, hasAudio: meta.hasAudio,
        derivedFrom: { mediaId: media.id, sourceStart: clip.sourceStart, sourceEnd: clip.sourceEnd, level },
      };
      if (mode === 'add') return editor.addGeneratedClip(item, { index: clipIndex(clip.id) + 1 });
      await editor.replaceClipMedia(clip.id, item);
      return clip.id;
    });
  }

  // Timestamped speech of every media on the timeline that has none yet.
  async function transcribe() {
    if (state.transcribing) return 0;
    const missing = speechSources(editor.project).filter((media) => !editor.project.transcripts[media.id]);
    if (!missing.length) return 0;
    state.transcribing = true;
    notify();
    let charged = 0;
    try {
      for (const media of missing) {
        const url = await durableUrl(media.id);
        const result = await services.transcribe({ url });
        charged += Number(result.credits || 0);
        editor.setTranscript(media.id, result);
      }
    } finally {
      state.transcribing = false;
      notify();
    }
    scheduleSave();
    return charged;
  }

  // "Generate Subtitles": transcript (if missing) → real text overlays.
  async function generateSubtitles(options) {
    await transcribe();
    editor.generateSubtitles(options);
  }

  // Duration of speech still to transcribe, for the price shown first.
  function transcribeSeconds() {
    return speechSources(editor.project).filter((media) => !editor.project.transcripts[media.id]).reduce((sum, media) => sum + (media.duration || 0), 0);
  }

  // ------------------------------------------------------------ projects

  function scheduleSave() {
    clearTimeout(saveTimer);
    if (destroyed) return;
    saveTimer = setTimeout(() => { save().catch(() => {}); }, AUTOSAVE_MS);
  }

  // Saves the project to the user's SYLVEX account. A project is saved once
  // it has content and every file in it has a durable URL.
  async function save({ force = false } = {}) {
    clearTimeout(saveTimer);
    const project = editor.toJSON();
    const empty = !project.videoClips.length && !project.audioClips.length && !project.texts.length;
    if (empty && !force) return false;
    if (pendingUploads()) { state.save = 'waiting'; notify(); scheduleSave(); return false; }
    const content = JSON.stringify(Object.assign({}, project, { updatedAt: '' }));
    if (!force && content === savedContent && state.shareToken) return true;
    if (saving) { await saving.catch(() => {}); return save({ force }); }
    // Media that never reached storage is kept out of the saved copy.
    const missing = Object.values(project.media).filter((media) => !media.url).map((media) => media.id);
    if (missing.length) {
      project.videoClips = project.videoClips.filter((clip) => !missing.includes(clip.mediaId));
      project.audioClips = project.audioClips.filter((clip) => !missing.includes(clip.mediaId));
      missing.forEach((id) => { delete project.media[id]; delete project.transcripts[id]; });
    }
    state.save = 'saving';
    notify();
    saving = services.saveProject(project).then((result) => {
      state.shareToken = result.shareToken || state.shareToken;
      state.save = missing.length ? 'partial' : 'saved';
      state.saveError = '';
      savedContent = content;
      notify();
      return true;
    }).catch((error) => {
      state.save = 'error';
      state.saveError = error.code || 'project_save_failed';
      notify();
      throw error;
    }).finally(() => { saving = null; });
    return saving;
  }

  async function open(id, token) {
    const loaded = await services.loadProject(id, token);
    await editor.load(loaded.project);
    state.shareToken = loaded.owner ? loaded.shareToken : '';
    savedContent = loaded.owner ? JSON.stringify(Object.assign({}, editor.toJSON(), { updatedAt: '' })) : '';
    notify();
    // A project opened from someone's link becomes this user's own copy.
    if (!loaded.owner) scheduleSave();
    return loaded;
  }

  // Address that reopens this project in a regular browser (Telegram
  // "Open in browser" for export).
  async function browserLink() {
    await save({ force: true });
    const base = location.origin + '/webapp/index.html';
    return base + '?ve_project=' + encodeURIComponent(editor.project.id) + '&ve_token=' + encodeURIComponent(state.shareToken || '');
  }

  // Exported file → SYLVEX storage, so Telegram can save it from a link.
  async function uploadExport(blob, fileName) {
    const file = typeof File !== 'undefined' ? new File([blob], fileName, { type: 'video/mp4' }) : blob;
    const result = await services.upload(file, 'video');
    return new URL(result.url, location.origin).toString();
  }

  const offEdit = editor.on('edit', scheduleSave);
  const offFacts = editor.on('facts', scheduleSave);

  return {
    state: () => Object.assign({}, state, { uploads: uploadState() }),
    importFiles,
    durableUrl,
    retryUpload(mediaId) {
      const entry = uploads.get(mediaId);
      if (entry && entry.failed && entry.failed !== 'upload_too_large') startUpload(mediaId, entry.file);
    },
    generateVideo,
    animatePhoto,
    generateMusic,
    voiceOver,
    enhanceVideo,
    transcribe,
    transcribeSeconds,
    generateSubtitles,
    save,
    open,
    browserLink,
    uploadExport,
    destroy() {
      destroyed = true;
      clearTimeout(saveTimer);
      offEdit();
      offFacts();
    },
  };
}
