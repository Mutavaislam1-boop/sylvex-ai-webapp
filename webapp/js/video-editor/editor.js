// SYLVEX Video Editor core.
//
//   SYLVEX UI  →  SYLVEX actions/services  →  this editor (operations on the
//   SYLVEX project)  →  engine
//
// The UI and the SYLVEX action layer only call the operations below. The
// editor keeps the SYLVEX project (project.js) as the source of truth and
// hands it to a rendering engine through this contract:
//
//   engine.init({ container })            mount the preview into an element
//   engine.capabilities()                 { transitionKinds:[kind], fonts:[{id,label}],
//                                           images:boolean, canExport:boolean, exportReason:string }
//   engine.sync(project, layout)          render exactly this project (async)
//   engine.play() / pause() / seek(t)     preview playback, t in seconds
//   engine.currentTime() / isPlaying()
//   engine.exportVideo(project, layout, { onProgress(ratio), signal }) → Blob (MP4)
//   engine.destroy()
//
// An engine never owns the edit: everything it needs comes from the project,
// so swapping IMG.LY for another SDK or our own engine means writing one
// new engine module.
import * as P from './project.js';

const HISTORY_LIMIT = 60;

export function probeMedia(url, kind) {
  if (kind === 'image') {
    return new Promise((resolve, reject) => {
      const image = new Image();
      const timer = setTimeout(() => reject(new Error('media_metadata_timeout')), 20000);
      image.onload = () => { clearTimeout(timer); resolve({ duration: 0, width: image.naturalWidth, height: image.naturalHeight }); };
      image.onerror = () => { clearTimeout(timer); reject(new Error('media_unsupported')); };
      image.src = url;
    });
  }
  return new Promise((resolve, reject) => {
    const element = document.createElement(kind === 'audio' ? 'audio' : 'video');
    element.preload = 'metadata';
    element.muted = true;
    const done = (fn, value) => { element.removeAttribute('src'); element.load(); fn(value); };
    const timer = setTimeout(() => done(reject, new Error('media_metadata_timeout')), 20000);
    element.onloadedmetadata = () => {
      clearTimeout(timer);
      const duration = Number(element.duration);
      if (!Number.isFinite(duration) || duration <= 0) { done(reject, new Error('media_duration_unknown')); return; }
      // Browsers that report it say whether a video has a sound track.
      const tracks = element.audioTracks;
      const hasAudio = kind === 'audio' ? true
        : (typeof element.mozHasAudio === 'boolean' ? element.mozHasAudio
          : (tracks && typeof tracks.length === 'number' ? tracks.length > 0 : true));
      done(resolve, { duration, width: element.videoWidth || 0, height: element.videoHeight || 0, hasAudio });
    };
    element.onerror = () => { clearTimeout(timer); done(reject, new Error('media_unsupported')); };
    element.src = url;
  });
}

const KIND_OF_FILE = (file) => (/^image\//.test(file.type) ? 'image' : /^audio\//.test(file.type) ? 'audio' : /^video\//.test(file.type) ? 'video' : '');
export { KIND_OF_FILE as kindOfFile };

// Server facts about media (durable URL, measured size), transcripts and the
// view state are not edit steps: undo/redo keep the current ones.
function carryFacts(restored, current) {
  const next = JSON.parse(JSON.stringify(restored));
  Object.keys(next.media).forEach((id) => {
    const now = current.media[id];
    if (now) ['url', 'previewUrl', 'size', 'mime', 'width', 'height', 'duration', 'hasAudio'].forEach((key) => { next.media[id][key] = now[key]; });
  });
  next.transcripts = JSON.parse(JSON.stringify(current.transcripts || {}));
  next.ui = JSON.parse(JSON.stringify(current.ui || {}));
  return next;
}

export function createVideoEditor({ engine, name } = {}) {
  if (!engine) throw new Error('engine_required');
  let project = P.createProject({ name });
  const past = [];
  const future = [];
  const listeners = new Map();
  const objectUrls = new Set();
  let syncChain = Promise.resolve();
  let syncScheduled = false;
  let timeLoop = 0;
  let destroyed = false;

  function emit(type, detail) {
    (listeners.get(type) || []).forEach((callback) => { try { callback(detail); } catch (error) { console.error(error); } });
  }

  function scheduleSync() {
    if (syncScheduled || destroyed) return syncChain;
    syncScheduled = true;
    syncChain = syncChain.then(async () => {
      syncScheduled = false;
      if (destroyed) return { ok: true };
      try {
        await engine.sync(project, P.layoutTimeline(project));
        emit('synced', project);
        return { ok: true };
      } catch (error) {
        return { ok: false, error };
      }
    });
    return syncChain;
  }

  const contentOf = (value) => JSON.stringify(Object.assign({}, value, { updatedAt: '' }));

  function syncAndReport() {
    return scheduleSync().then((outcome) => {
      if (outcome && !outcome.ok) emit('error', { stage: 'sync', error: outcome.error });
      return outcome;
    });
  }

  // Adds media through `apply`; if the engine cannot load the new file the
  // addition is rolled back and the error is reported to the caller.
  async function addAndVerify(added, apply) {
    const before = project;
    const result = apply(added);
    commit(result.project, { report: false });
    const outcome = await scheduleSync();
    if (outcome && !outcome.ok) {
      const error = outcome.error || new Error('media_unsupported');
      if (error.mediaId === added.mediaId || !project.media[added.mediaId]) {
        past.pop();
        project = before;
        emit('change', project);
        await scheduleSync();
        throw error;
      }
      emit('error', { stage: 'sync', error });
    }
    return Object.assign({ mediaId: added.mediaId }, result);
  }

  // `edit:false` marks changes that are not steps of the edit (upload
  // finished, transcript received, zoom): no history, still saved.
  function commit(next, { history = true, report = true, edit = true, sync = true } = {}) {
    // Re-applying the same values (e.g. a field firing "change" twice) is
    // not a new step in the history.
    if (next === project || contentOf(next) === contentOf(project)) return project;
    if (history && edit) {
      past.push(project);
      if (past.length > HISTORY_LIMIT) past.shift();
      future.length = 0;
    }
    project = next;
    emit('change', project);
    emit(edit ? 'edit' : 'facts', project);
    if (!sync) return project;
    if (report) syncAndReport(); else scheduleSync();
    return project;
  }

  // A file from the device: a local copy for instant editing. The durable
  // upload is done by the SYLVEX action layer, which then sets the URL.
  async function importSource(source, kind, extra = {}) {
    let previewUrl = '';
    let url = '';
    let fileName = '';
    let mime = '';
    let size = 0;
    if (typeof File !== 'undefined' && source instanceof File) {
      const fileKind = KIND_OF_FILE(source);
      if (source.type && fileKind !== kind) throw new Error(kind === 'audio' ? 'not_audio_file' : kind === 'image' ? 'not_image_file' : 'not_video_file');
      previewUrl = URL.createObjectURL(source);
      objectUrls.add(previewUrl);
      fileName = source.name;
      mime = source.type;
      size = source.size;
    } else {
      url = String(source && source.url || '');
      fileName = String(source && source.name || '');
      mime = String(source && source.mime || '');
      if (!url) throw new Error('source_url_required');
    }
    const meta = await probeMedia(previewUrl || url, kind);
    return P.addMedia(project, Object.assign({ kind, url, previewUrl, name: fileName, mime, size, duration: meta.duration, width: meta.width, height: meta.height, hasAudio: meta.hasAudio }, extra));
  }

  function tick() {
    cancelAnimationFrame(timeLoop);
    const loop = () => {
      const time = engine.currentTime();
      emit('time', time);
      const duration = P.projectDuration(project);
      if (engine.isPlaying() && duration && time >= duration - 0.01) { engine.pause(); emit('playstate', false); }
      if (engine.isPlaying()) timeLoop = requestAnimationFrame(loop);
    };
    timeLoop = requestAnimationFrame(loop);
  }

  const api = {
    get project() { return project; },
    get engineName() { return engine.name || 'engine'; },
    layout: () => P.layoutTimeline(project),
    capabilities: () => engine.capabilities(),
    on(type, callback) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(callback);
      return () => listeners.set(type, (listeners.get(type) || []).filter((item) => item !== callback));
    },
    async mount(container) {
      await engine.init({ container });
      await syncAndReport();
    },

    // Opens a saved project (history starts fresh).
    async load(saved) {
      const problem = P.validateProject(saved);
      if (problem) throw new Error('project_invalid:' + problem);
      past.length = 0;
      future.length = 0;
      project = P.upgradeProject(saved);
      emit('change', project);
      emit('loaded', project);
      return syncAndReport();
    },
    rename: (title) => commit(P.rename(project, title)),

    // --- media
    async addVideo(source, options = {}) {
      const added = await importSource(source, 'video', options.media);
      const result = await addAndVerify(added, (item) => P.addVideoClip(item.project, item.mediaId, options.index));
      return result.clipId;
    },
    async addImage(source, options = {}) {
      const added = await importSource(source, 'image', options.media);
      const result = await addAndVerify(added, (item) => P.addVideoClip(item.project, item.mediaId, options.index, { duration: options.duration }));
      return result.clipId;
    },
    async addAudio(source, options = {}) {
      const added = await importSource(source, 'audio', options.media);
      const result = await addAndVerify(added, (item) => P.addAudioClip(item.project, item.mediaId, options));
      return result.audioId;
    },
    // Media id of the clip's asset, for actions working on files.
    mediaOf(id) {
      const clip = project.videoClips.find((item) => item.id === id) || project.audioClips.find((item) => item.id === id);
      return clip ? project.media[clip.mediaId] : null;
    },
    updateMedia: (mediaId, patch) => commit(P.updateMedia(project, mediaId, patch), { edit: false, sync: 'url' in patch || 'previewUrl' in patch }),
    // Puts an existing project asset (e.g. from the media list) on the timeline.
    async placeMedia(mediaId, options = {}) {
      const media = project.media[mediaId];
      if (!media) throw new Error('media_not_found');
      const added = { project, mediaId };
      if (media.kind === 'audio') return (await addAndVerify(added, (item) => P.addAudioClip(item.project, mediaId, options))).audioId;
      return (await addAndVerify(added, (item) => P.addVideoClip(item.project, mediaId, options.index, options))).clipId;
    },

    // --- picture track
    removeClip: (clipId) => commit(P.removeClip(project, clipId)),
    splitClip(clipId, atTime) { const result = P.splitClip(project, clipId, atTime); commit(result.project); return result.clipId; },
    trimClip: (clipId, range) => commit(P.trimClip(project, clipId, range)),
    moveClip: (clipId, toIndex) => commit(P.moveClip(project, clipId, toIndex)),
    duplicateClip(clipId) { const result = P.duplicateClip(project, clipId); commit(result.project); return result.clipId; },
    setClipVolume: (clipId, volume) => commit(P.setClipAudio(project, clipId, { volume })),
    muteClip: (clipId, muted) => commit(P.setClipAudio(project, clipId, { muted })),
    muteVideoAudio: (muted) => commit(P.setAllClipsAudio(project, { muted })),
    detachAudio(clipId) { const result = P.detachClipAudio(project, clipId); commit(result.project); return result.audioId; },
    // A new version of the clip's media (Enhance Video) in place of the old.
    async replaceClipMedia(clipId, mediaItem) {
      const index = project.videoClips.findIndex((clip) => clip.id === clipId);
      if (index < 0) throw new Error('clip_not_found');
      const added = P.addMedia(project, mediaItem);
      const result = await addAndVerify(added, (item) => ({ project: P.replaceClipMedia(item.project, clipId, item.mediaId), clipId }));
      return result.mediaId;
    },
    revertClipMedia: (clipId) => commit(P.revertClipMedia(project, clipId)),
    // Generated media (Generate Video, Animate Photo, Enhance "add") as a
    // new clip at `index`.
    async addGeneratedClip(mediaItem, options = {}) {
      const added = P.addMedia(project, mediaItem);
      const result = await addAndVerify(added, (item) => P.addVideoClip(item.project, item.mediaId, options.index, options));
      return result.clipId;
    },

    // --- audio tracks
    async addGeneratedAudio(mediaItem, options = {}) {
      const added = P.addMedia(project, Object.assign({ kind: 'audio' }, mediaItem));
      const result = await addAndVerify(added, (item) => P.addAudioClip(item.project, item.mediaId, options));
      return result.audioId;
    },
    removeAudio: (audioId) => commit(P.removeAudio(project, audioId)),
    splitAudio(audioId, atTime) { const result = P.splitAudio(project, audioId, atTime); commit(result.project); return result.audioId; },
    trimAudio: (audioId, range) => commit(P.trimAudio(project, audioId, range)),
    moveAudio: (audioId, position) => commit(P.moveAudio(project, audioId, position)),
    duplicateAudio(audioId) { const result = P.duplicateAudio(project, audioId); commit(result.project); return result.audioId; },
    setAudioVolume: (audioId, volume) => commit(P.setAudioLevel(project, audioId, { volume })),
    muteAudio: (audioId, muted) => commit(P.setAudioLevel(project, audioId, { muted })),
    setAudioRole: (audioId, role) => commit(P.setAudioLevel(project, audioId, { role })),
    removeAudioRange: (audioId, start, end) => commit(P.removeAudioRange(project, audioId, start, end)),

    // --- segments
    removeRange: (start, end) => commit(P.removeRange(project, start, end)),

    // --- transitions
    setTransition: (clipId, transition) => commit(P.setTransition(project, clipId, transition)),

    // --- text
    addText(fields) { const result = P.addText(project, fields); commit(result.project); return result.textId; },
    updateText: (textId, patch) => commit(P.updateText(project, textId, patch)),
    removeText: (textId) => commit(P.removeText(project, textId)),
    duplicateText(textId) { const result = P.duplicateText(project, textId); commit(result.project); return result.textId; },

    // --- transcript and subtitles
    setTranscript: (mediaId, transcript) => commit(P.setTranscript(project, mediaId, transcript), { edit: false, sync: false }),
    transcript: () => P.transcriptTimeline(project),
    generateSubtitles: (options) => commit(P.generateSubtitles(project, options)),
    clearSubtitles: () => commit(P.clearSubtitles(project)),

    // --- view state saved with the project
    setUiState: (patch) => commit(P.setUiState(project, patch), { edit: false, sync: false }),

    // --- history
    canUndo: () => past.length > 0,
    canRedo: () => future.length > 0,
    undo() { if (!past.length) return; future.push(project); project = carryFacts(past.pop(), project); emit('change', project); emit('edit', project); syncAndReport(); },
    redo() { if (!future.length) return; past.push(project); project = carryFacts(future.pop(), project); emit('change', project); emit('edit', project); syncAndReport(); },

    // --- playback
    async play() {
      await syncChain;
      const duration = P.projectDuration(project);
      if (!duration) return;
      if (engine.currentTime() >= duration - 0.05) engine.seek(0);
      engine.play();
      emit('playstate', true);
      tick();
    },
    pause() { engine.pause(); emit('playstate', false); emit('time', engine.currentTime()); },
    seek(time) {
      const value = Math.max(0, Math.min(P.projectDuration(project), Number(time) || 0));
      engine.seek(value);
      emit('time', value);
    },
    currentTime: () => engine.currentTime(),
    isPlaying: () => engine.isPlaying(),

    // --- export
    setExportSettings: (patch) => commit(P.setExportSettings(project, patch), { history: false }),
    async exportVideo({ onProgress, signal } = {}) {
      const problem = P.validateProject(project);
      if (problem) throw new Error('project_invalid:' + problem);
      if (!project.videoClips.length) throw new Error('nothing_to_export');
      if (engine.isPlaying()) api.pause();
      await scheduleSync();
      await syncChain;
      const blob = await engine.exportVideo(project, P.layoutTimeline(project), { onProgress, signal });
      const base = String(project.name || 'sylvex-video').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) || 'sylvex-video';
      return { blob, fileName: base + '.mp4' };
    },

    // Plain JSON copy of the project as it is stored (engine-neutral).
    toJSON: () => P.serialize(project),

    destroy() {
      destroyed = true;
      cancelAnimationFrame(timeLoop);
      try { engine.destroy(); } catch (_) {}
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
      listeners.clear();
    },
  };
  return api;
}
