// SYLVEX Video Editor core.
//
//   SYLVEX UI  →  this editor (operations on the SYLVEX project)  →  engine
//
// The UI only calls the operations below. The editor keeps the SYLVEX
// project (project.js) as the source of truth and hands it to a rendering
// engine through this contract:
//
//   engine.init({ container })            mount the preview into an element
//   engine.capabilities()                 { transitions:[{id,label}], fonts:[{id,label}],
//                                           canExport:boolean, exportReason:string }
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

function probeMedia(url, kind) {
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
      done(resolve, { duration, width: element.videoWidth || 0, height: element.videoHeight || 0 });
    };
    element.onerror = () => { clearTimeout(timer); done(reject, new Error('media_unsupported')); };
    element.src = url;
  });
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
    return result;
  }

  function commit(next, { history = true, report = true } = {}) {
    // Re-applying the same values (e.g. a field firing "change" twice) is
    // not a new step in the history.
    if (next === project || contentOf(next) === contentOf(project)) return project;
    if (history) {
      past.push(project);
      if (past.length > HISTORY_LIMIT) past.shift();
      future.length = 0;
    }
    project = next;
    emit('change', project);
    if (report) syncAndReport(); else scheduleSync();
    return project;
  }

  async function importSource(source, kind) {
    let url = '';
    let fileName = '';
    let mime = '';
    let size = 0;
    if (typeof File !== 'undefined' && source instanceof File) {
      const isKind = kind === 'audio' ? /^audio\//.test(source.type) : /^video\//.test(source.type);
      if (source.type && !isKind) throw new Error(kind === 'audio' ? 'not_audio_file' : 'not_video_file');
      url = URL.createObjectURL(source);
      objectUrls.add(url);
      fileName = source.name;
      mime = source.type;
      size = source.size;
    } else {
      url = String(source && source.url || '');
      fileName = String(source && source.name || '');
      mime = String(source && source.mime || '');
      if (!url) throw new Error('source_url_required');
    }
    const meta = await probeMedia(url, kind);
    const added = P.addMedia(project, { kind, url, name: fileName, mime, size, duration: meta.duration, width: meta.width, height: meta.height });
    return added;
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

    // --- video
    async loadVideo(source) {
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
      past.length = 0;
      future.length = 0;
      project = P.createProject({ name: project.name });
      return api.addVideo(source);
    },
    async addVideo(source, options = {}) {
      const added = await importSource(source, 'video');
      const result = await addAndVerify(added, (item) => P.addVideoClip(item.project, item.mediaId, options.index));
      return result.clipId;
    },
    removeClip: (clipId) => commit(P.removeClip(project, clipId)),
    splitClip(clipId, atTime) { const result = P.splitClip(project, clipId, atTime); commit(result.project); return result.clipId; },
    trimClip: (clipId, range) => commit(P.trimClip(project, clipId, range)),
    moveClip: (clipId, toIndex) => commit(P.moveClip(project, clipId, toIndex)),
    setClipVolume: (clipId, volume) => commit(P.setClipAudio(project, clipId, { volume })),
    muteClip: (clipId, muted) => commit(P.setClipAudio(project, clipId, { muted })),
    muteVideoAudio: (muted) => commit(P.setAllClipsAudio(project, { muted })),

    // --- audio
    async addAudio(source, options = {}) {
      const added = await importSource(source, 'audio');
      const result = await addAndVerify(added, (item) => P.addAudioClip(item.project, item.mediaId, options));
      return result.audioId;
    },
    removeAudio: (audioId) => commit(P.removeAudio(project, audioId)),
    splitAudio(audioId, atTime) { const result = P.splitAudio(project, audioId, atTime); commit(result.project); return result.audioId; },
    trimAudio: (audioId, range) => commit(P.trimAudio(project, audioId, range)),
    moveAudio: (audioId, position) => commit(P.moveAudio(project, audioId, position)),
    setAudioVolume: (audioId, volume) => commit(P.setAudioLevel(project, audioId, { volume })),
    muteAudio: (audioId, muted) => commit(P.setAudioLevel(project, audioId, { muted })),

    // --- transitions
    setTransition: (clipId, transition) => commit(P.setTransition(project, clipId, transition)),

    // --- text
    addText(fields) { const result = P.addText(project, fields); commit(result.project); return result.textId; },
    updateText: (textId, patch) => commit(P.updateText(project, textId, patch)),
    removeText: (textId) => commit(P.removeText(project, textId)),

    // --- history
    canUndo: () => past.length > 0,
    canRedo: () => future.length > 0,
    undo() { if (!past.length) return; future.push(project); project = past.pop(); emit('change', project); syncAndReport(); },
    redo() { if (!future.length) return; past.push(project); project = future.pop(); emit('change', project); syncAndReport(); },

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
      const base = (project.media[project.videoClips[0].mediaId].name || 'sylvex-video').replace(/\.[a-z0-9]{2,4}$/i, '').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) || 'sylvex-video';
      return { blob, fileName: base + '-edit.mp4' };
    },

    // Plain JSON copy of the project (engine-neutral).
    toJSON: () => JSON.parse(JSON.stringify(project)),

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
