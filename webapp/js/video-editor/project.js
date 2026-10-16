// SYLVEX video project: the editor's single source of truth.
//
// The project describes the edit in engine-neutral terms (media, clips,
// trims, timeline positions, audio, transitions, text, export settings).
// Rendering engines (IMG.LY today) only receive this structure through the
// engine contract in editor.js, so the engine can be replaced without
// touching the project data or the SYLVEX UI.
//
// Every operation here is pure: it takes a project and returns a new one.

export const PROJECT_SCHEMA = 'sylvex.video-project';
export const PROJECT_VERSION = 1;
export const MIN_CLIP = 0.1; // seconds
export const MAX_AUDIO_LANES = 6;
export const DEFAULT_TRANSITION_DURATION = 0.8;

let idCounter = 0;
export function newId(prefix) {
  idCounter += 1;
  return prefix + '_' + Date.now().toString(36) + idCounter.toString(36) + Math.random().toString(36).slice(2, 6);
}

const clone = (value) => JSON.parse(JSON.stringify(value));
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const round = (value) => Math.round(value * 1000) / 1000;
const finite = (value, fallback) => (Number.isFinite(Number(value)) ? Number(value) : fallback);

export function createProject(options = {}) {
  const now = new Date().toISOString();
  return {
    schema: PROJECT_SCHEMA,
    version: PROJECT_VERSION,
    id: newId('project'),
    name: String(options.name || 'Новый проект'),
    createdAt: now,
    updatedAt: now,
    // Frame of the edit. Taken from the first video unless set explicitly.
    settings: { width: 0, height: 0, fps: 30, background: '#000000' },
    exportSettings: { format: 'mp4', width: 0, height: 0, fps: 30, videoBitrate: 'auto' },
    media: {},
    videoClips: [],
    audioClips: [],
    texts: [],
  };
}

function touch(project) {
  project.updatedAt = new Date().toISOString();
  return project;
}

export function clipDuration(clip) {
  return Math.max(0, clip.sourceEnd - clip.sourceStart);
}

// Outgoing transitions overlap the next clip by their duration; they are
// limited to half of the shorter neighbour so clips never vanish.
export function transitionDuration(project, index) {
  const clip = project.videoClips[index];
  const next = project.videoClips[index + 1];
  if (!clip || !next || !clip.transitionOut || !clip.transitionOut.type) return 0;
  const limit = Math.min(clipDuration(clip), clipDuration(next)) / 2;
  return round(clamp(finite(clip.transitionOut.duration, DEFAULT_TRANSITION_DURATION), 0.1, Math.max(0.1, limit)));
}

// Timeline positions derived from the clip order, trims and transitions.
export function layoutTimeline(project) {
  const video = [];
  let cursor = 0;
  project.videoClips.forEach((clip, index) => {
    const duration = clipDuration(clip);
    video.push({ id: clip.id, index, start: round(cursor), end: round(cursor + duration), duration: round(duration), transition: transitionDuration(project, index) });
    cursor += duration - transitionDuration(project, index);
  });
  const videoEnd = video.length ? video[video.length - 1].end : 0;
  const audio = project.audioClips.map((clip) => ({ id: clip.id, lane: clip.lane, start: round(clip.start), end: round(clip.start + clipDuration(clip)), duration: round(clipDuration(clip)) }));
  const texts = project.texts.map((text) => ({ id: text.id, start: round(text.start), end: round(text.start + text.duration), duration: round(text.duration) }));
  // The video track defines the length of the edit; without video the
  // longest audio or text item does.
  const duration = videoEnd > 0 ? videoEnd : Math.max(0, ...audio.map((item) => item.end), ...texts.map((item) => item.end));
  return { video, audio, texts, videoEnd: round(videoEnd), duration: round(duration) };
}

export function projectDuration(project) {
  return layoutTimeline(project).duration;
}

// ------------------------------------------------------------------ media

export function addMedia(project, media) {
  const next = clone(project);
  const id = media.id || newId(media.kind === 'audio' ? 'audio_src' : 'video_src');
  next.media[id] = {
    id,
    kind: media.kind === 'audio' ? 'audio' : 'video',
    name: String(media.name || (media.kind === 'audio' ? 'Аудио' : 'Видео')).slice(0, 160),
    url: String(media.url || ''),
    mime: String(media.mime || ''),
    size: finite(media.size, 0),
    duration: round(Math.max(0, finite(media.duration, 0))),
    width: Math.round(finite(media.width, 0)),
    height: Math.round(finite(media.height, 0)),
    hasAudio: media.hasAudio !== false,
  };
  if (next.media[id].kind === 'video' && !next.settings.width && next.media[id].width && next.media[id].height) {
    // The first video sets the frame, so the export keeps its resolution.
    next.settings.width = next.media[id].width;
    next.settings.height = next.media[id].height;
    next.exportSettings.width = next.media[id].width;
    next.exportSettings.height = next.media[id].height;
  }
  return { project: touch(next), mediaId: id };
}

function mediaOf(project, mediaId, kind) {
  const media = project.media[mediaId];
  if (!media || (kind && media.kind !== kind)) throw new Error('media_not_found');
  return media;
}

// ------------------------------------------------------------- video clips

export function addVideoClip(project, mediaId, index) {
  const media = mediaOf(project, mediaId, 'video');
  if (!(media.duration > 0)) throw new Error('media_duration_unknown');
  const next = clone(project);
  const clip = { id: newId('clip'), mediaId, sourceStart: 0, sourceEnd: media.duration, volume: 1, muted: false, transitionOut: null };
  const at = Number.isInteger(index) ? clamp(index, 0, next.videoClips.length) : next.videoClips.length;
  next.videoClips.splice(at, 0, clip);
  return { project: normalize(touch(next)), clipId: clip.id };
}

function findClip(project, clipId) {
  const index = project.videoClips.findIndex((clip) => clip.id === clipId);
  if (index < 0) throw new Error('clip_not_found');
  return index;
}

export function removeClip(project, clipId) {
  const next = clone(project);
  next.videoClips.splice(findClip(next, clipId), 1);
  return normalize(touch(next));
}

// Split at a project time; the second half keeps the outgoing transition.
export function splitClip(project, clipId, atTime) {
  const index = findClip(project, clipId);
  const placed = layoutTimeline(project).video[index];
  const local = finite(atTime, NaN) - placed.start;
  const clip = project.videoClips[index];
  if (!(local >= MIN_CLIP && local <= clipDuration(clip) - MIN_CLIP)) throw new Error('split_out_of_range');
  const next = clone(project);
  const first = next.videoClips[index];
  const second = Object.assign(clone(first), { id: newId('clip'), sourceStart: round(first.sourceStart + local) });
  first.sourceEnd = second.sourceStart;
  first.transitionOut = null;
  next.videoClips.splice(index + 1, 0, second);
  return { project: normalize(touch(next)), clipId: second.id };
}

export function trimClip(project, clipId, range) {
  const next = clone(project);
  const clip = next.videoClips[findClip(next, clipId)];
  const media = mediaOf(next, clip.mediaId, 'video');
  const start = clamp(finite(range.sourceStart, clip.sourceStart), 0, media.duration - MIN_CLIP);
  const end = clamp(finite(range.sourceEnd, clip.sourceEnd), start + MIN_CLIP, media.duration);
  clip.sourceStart = round(start);
  clip.sourceEnd = round(end);
  return normalize(touch(next));
}

export function moveClip(project, clipId, toIndex) {
  const next = clone(project);
  const [clip] = next.videoClips.splice(findClip(next, clipId), 1);
  next.videoClips.splice(clamp(Math.round(finite(toIndex, 0)), 0, next.videoClips.length), 0, clip);
  return normalize(touch(next));
}

export function setClipAudio(project, clipId, patch) {
  const next = clone(project);
  const clip = next.videoClips[findClip(next, clipId)];
  if ('volume' in patch) clip.volume = round(clamp(finite(patch.volume, 1), 0, 1));
  if ('muted' in patch) clip.muted = !!patch.muted;
  return touch(next);
}

// Original audio of every video clip at once.
export function setAllClipsAudio(project, patch) {
  let next = project;
  project.videoClips.forEach((clip) => { next = setClipAudio(next, clip.id, patch); });
  return next;
}

export function setTransition(project, clipId, transition) {
  const next = clone(project);
  const index = findClip(next, clipId);
  if (index >= next.videoClips.length - 1) throw new Error('transition_needs_next_clip');
  next.videoClips[index].transitionOut = transition && transition.type && transition.type !== 'none'
    ? { type: String(transition.type), duration: round(clamp(finite(transition.duration, DEFAULT_TRANSITION_DURATION), 0.1, 5)) }
    : null;
  return touch(next);
}

// ------------------------------------------------------------- audio clips

function findAudio(project, audioId) {
  const index = project.audioClips.findIndex((clip) => clip.id === audioId);
  if (index < 0) throw new Error('audio_not_found');
  return index;
}

export function addAudioClip(project, mediaId, options = {}) {
  const media = mediaOf(project, mediaId, 'audio');
  if (!(media.duration > 0)) throw new Error('media_duration_unknown');
  const next = clone(project);
  const lane = Number.isInteger(options.lane) ? clamp(options.lane, 0, MAX_AUDIO_LANES - 1) : freeLane(next, finite(options.start, 0), media.duration);
  const clip = { id: newId('aclip'), mediaId, lane, start: round(Math.max(0, finite(options.start, 0))), sourceStart: 0, sourceEnd: media.duration, volume: 1, muted: false };
  next.audioClips.push(clip);
  return { project: touch(next), audioId: clip.id };
}

// First lane where [start, start+duration) does not overlap another clip.
function freeLane(project, start, duration) {
  for (let lane = 0; lane < MAX_AUDIO_LANES; lane += 1) {
    const busy = project.audioClips.some((clip) => clip.lane === lane && clip.start < start + duration && start < clip.start + clipDuration(clip));
    if (!busy) return lane;
  }
  return MAX_AUDIO_LANES - 1;
}

export function removeAudio(project, audioId) {
  const next = clone(project);
  next.audioClips.splice(findAudio(next, audioId), 1);
  return touch(next);
}

export function moveAudio(project, audioId, position) {
  const next = clone(project);
  const clip = next.audioClips[findAudio(next, audioId)];
  if ('start' in position) clip.start = round(Math.max(0, finite(position.start, clip.start)));
  if ('lane' in position) clip.lane = clamp(Math.round(finite(position.lane, clip.lane)), 0, MAX_AUDIO_LANES - 1);
  return touch(next);
}

// Trims keep the audio in place on the timeline: moving the in-point also
// moves the clip start by the same amount.
export function trimAudio(project, audioId, range) {
  const next = clone(project);
  const clip = next.audioClips[findAudio(next, audioId)];
  const media = mediaOf(next, clip.mediaId, 'audio');
  const start = clamp(finite(range.sourceStart, clip.sourceStart), 0, media.duration - MIN_CLIP);
  const end = clamp(finite(range.sourceEnd, clip.sourceEnd), start + MIN_CLIP, media.duration);
  const shift = start - clip.sourceStart;
  clip.start = round(Math.max(0, clip.start + shift));
  clip.sourceStart = round(start);
  clip.sourceEnd = round(end);
  return touch(next);
}

export function splitAudio(project, audioId, atTime) {
  const index = findAudio(project, audioId);
  const clip = project.audioClips[index];
  const local = finite(atTime, NaN) - clip.start;
  if (!(local >= MIN_CLIP && local <= clipDuration(clip) - MIN_CLIP)) throw new Error('split_out_of_range');
  const next = clone(project);
  const first = next.audioClips[index];
  const second = Object.assign(clone(first), { id: newId('aclip'), start: round(first.start + local), sourceStart: round(first.sourceStart + local) });
  first.sourceEnd = second.sourceStart;
  next.audioClips.splice(index + 1, 0, second);
  return { project: touch(next), audioId: second.id };
}

export function setAudioLevel(project, audioId, patch) {
  const next = clone(project);
  const clip = next.audioClips[findAudio(next, audioId)];
  if ('volume' in patch) clip.volume = round(clamp(finite(patch.volume, 1), 0, 1));
  if ('muted' in patch) clip.muted = !!patch.muted;
  return touch(next);
}

// -------------------------------------------------------------------- text

export const TEXT_DEFAULTS = { text: 'Текст', start: 0, duration: 3, x: 0.5, y: 0.82, fontSize: 0.07, color: '#ffffff', fontFamily: '', bold: false, italic: false, align: 'center', background: '' };

function sanitizeText(text) {
  return {
    text: String(text.text == null ? '' : text.text).slice(0, 500),
    start: round(Math.max(0, finite(text.start, 0))),
    duration: round(clamp(finite(text.duration, 3), MIN_CLIP, 3600)),
    x: round(clamp(finite(text.x, 0.5), 0, 1)),
    y: round(clamp(finite(text.y, 0.5), 0, 1)),
    fontSize: round(clamp(finite(text.fontSize, 0.07), 0.02, 0.3)),
    color: /^#[0-9a-f]{6}$/i.test(String(text.color || '')) ? String(text.color).toLowerCase() : '#ffffff',
    fontFamily: String(text.fontFamily || '').slice(0, 80),
    bold: !!text.bold,
    italic: !!text.italic,
    align: ['left', 'center', 'right'].includes(text.align) ? text.align : 'center',
    background: /^#[0-9a-f]{6}$/i.test(String(text.background || '')) ? String(text.background).toLowerCase() : '',
  };
}

export function addText(project, fields = {}) {
  const next = clone(project);
  const text = Object.assign({ id: newId('text') }, sanitizeText(Object.assign({}, TEXT_DEFAULTS, fields)));
  next.texts.push(text);
  return { project: touch(next), textId: text.id };
}

export function updateText(project, textId, patch) {
  const next = clone(project);
  const index = next.texts.findIndex((text) => text.id === textId);
  if (index < 0) throw new Error('text_not_found');
  next.texts[index] = Object.assign({ id: textId }, sanitizeText(Object.assign({}, next.texts[index], patch)));
  return touch(next);
}

export function removeText(project, textId) {
  const next = clone(project);
  const index = next.texts.findIndex((text) => text.id === textId);
  if (index < 0) throw new Error('text_not_found');
  next.texts.splice(index, 1);
  return touch(next);
}

// ------------------------------------------------------------------ export

export function setExportSettings(project, patch) {
  const next = clone(project);
  const settings = next.exportSettings;
  if ('fps' in patch) settings.fps = [24, 25, 30, 50, 60].includes(Number(patch.fps)) ? Number(patch.fps) : settings.fps;
  if ('width' in patch && 'height' in patch) {
    settings.width = Math.round(clamp(finite(patch.width, settings.width), 16, 7680));
    settings.height = Math.round(clamp(finite(patch.height, settings.height), 16, 4320));
  }
  return touch(next);
}

// Keeps derived invariants: the last clip has no outgoing transition.
export function normalize(project) {
  const last = project.videoClips[project.videoClips.length - 1];
  if (last) last.transitionOut = null;
  return project;
}

export function validateProject(project) {
  if (!project || project.schema !== PROJECT_SCHEMA) return 'schema';
  for (const clip of project.videoClips) {
    const media = project.media[clip.mediaId];
    if (!media || media.kind !== 'video') return 'video_media';
    if (!(clip.sourceEnd - clip.sourceStart >= MIN_CLIP - 1e-6) || clip.sourceStart < 0 || clip.sourceEnd > media.duration + 1e-6) return 'video_trim';
  }
  for (const clip of project.audioClips) {
    const media = project.media[clip.mediaId];
    if (!media || media.kind !== 'audio') return 'audio_media';
    if (!(clip.sourceEnd - clip.sourceStart >= MIN_CLIP - 1e-6)) return 'audio_trim';
  }
  return '';
}
