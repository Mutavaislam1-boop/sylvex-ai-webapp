// SYLVEX video project: the editor's single source of truth.
//
// The project describes the edit in engine-neutral terms (media, clips,
// trims, timeline positions, audio, transitions, text, transcripts, export
// settings). Rendering engines (IMG.LY today) only receive this structure
// through the engine contract in editor.js, so the engine can be replaced
// without touching the project data or the SYLVEX UI. The same structure is
// what SYLVEX stores on the server (services/video_editor.py).
//
// Every operation here is pure: it takes a project and returns a new one.

export const PROJECT_SCHEMA = 'sylvex.video-project';
export const PROJECT_VERSION = 2;
export const MIN_CLIP = 0.1; // seconds
export const MAX_AUDIO_LANES = 6;
export const DEFAULT_TRANSITION_DURATION = 0.8;
export const DEFAULT_IMAGE_DURATION = 3;
export const MAX_IMAGE_DURATION = 600;
export const AUDIO_ROLES = ['audio', 'original', 'music', 'voice', 'sfx'];
// Speech pauses at least this long are shown as "no speech".
export const SILENCE_MIN = 0.6;

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
    // Frame of the edit. Taken from the first video or image unless set explicitly.
    settings: { width: 0, height: 0, fps: 30, background: '#000000' },
    exportSettings: { format: 'mp4', width: 0, height: 0, fps: 30, videoBitrate: 'auto' },
    media: {},
    videoClips: [],
    audioClips: [],
    texts: [],
    // mediaId -> { segments:[{start,end,text}], language, createdAt } in media time.
    transcripts: {},
    // Editor view state saved with the project (timeline zoom etc.).
    ui: { pps: 0, autoFit: true },
  };
}

// Older projects (version 1) gain the fields added since.
export function upgradeProject(input) {
  const project = clone(input);
  project.version = PROJECT_VERSION;
  project.media = project.media || {};
  project.videoClips = project.videoClips || [];
  project.audioClips = project.audioClips || [];
  project.texts = project.texts || [];
  project.transcripts = project.transcripts || {};
  project.ui = Object.assign({ pps: 0, autoFit: true }, project.ui || {});
  project.audioClips.forEach((clip) => { if (!AUDIO_ROLES.includes(clip.role)) clip.role = 'audio'; });
  return project;
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

const MEDIA_PREFIX = { audio: 'audio_src', image: 'image_src', video: 'video_src' };

export function addMedia(project, media) {
  const next = clone(project);
  const kind = ['audio', 'image'].includes(media.kind) ? media.kind : 'video';
  const id = media.id || newId(MEDIA_PREFIX[kind]);
  next.media[id] = {
    id,
    kind,
    name: String(media.name || ({ audio: 'Аудио', image: 'Изображение', video: 'Видео' })[kind]).slice(0, 160),
    // Durable SYLVEX storage URL (saved with the project). `previewUrl` is a
    // local copy for this session only and is never saved.
    url: String(media.url || ''),
    previewUrl: String(media.previewUrl || ''),
    mime: String(media.mime || ''),
    size: finite(media.size, 0),
    duration: kind === 'image' ? 0 : round(Math.max(0, finite(media.duration, 0))),
    width: Math.round(finite(media.width, 0)),
    height: Math.round(finite(media.height, 0)),
    hasAudio: kind === 'audio' || (kind === 'video' && media.hasAudio !== false),
    // Where the asset came from: an upload or an AI action of the editor.
    origin: String(media.origin || 'upload'),
    // A generated version of another asset (e.g. Enhance Video) keeps the
    // source it replaced so the clip can go back to it.
    derivedFrom: media.derivedFrom ? clone(media.derivedFrom) : null,
    label: String(media.label || '').slice(0, 80),
  };
  const item = next.media[id];
  if (kind !== 'audio' && !next.settings.width && item.width && item.height) {
    // The first picture sets the frame, so the export keeps its resolution.
    next.settings.width = item.width;
    next.settings.height = item.height;
    next.exportSettings.width = item.width;
    next.exportSettings.height = item.height;
  }
  return { project: touch(next), mediaId: id };
}

// Session-only and server-side facts about an asset (upload finished, new
// signed URL, measured size) that do not change the edit itself.
export function updateMedia(project, mediaId, patch) {
  const next = clone(project);
  const media = next.media[mediaId];
  if (!media) throw new Error('media_not_found');
  ['url', 'previewUrl', 'mime', 'name', 'label'].forEach((key) => { if (key in patch) media[key] = String(patch[key] || ''); });
  ['size', 'width', 'height'].forEach((key) => { if (key in patch) media[key] = finite(patch[key], media[key]); });
  if ('duration' in patch && media.kind !== 'image') media.duration = round(Math.max(0, finite(patch.duration, media.duration)));
  if ('hasAudio' in patch && media.kind === 'video') media.hasAudio = !!patch.hasAudio;
  return touch(next);
}

function mediaOf(project, mediaId, kinds) {
  const media = project.media[mediaId];
  const allowed = Array.isArray(kinds) ? kinds : (kinds ? [kinds] : null);
  if (!media || (allowed && !allowed.includes(media.kind))) throw new Error('media_not_found');
  return media;
}

// Longest a clip of this media may be.
export function mediaLength(media) {
  return media && media.kind === 'image' ? MAX_IMAGE_DURATION : (media ? media.duration : 0);
}

// Media no clip, audio clip or derived version refers to any more.
export function unusedMedia(project) {
  const used = new Set([...project.videoClips.map((clip) => clip.mediaId), ...project.audioClips.map((clip) => clip.mediaId)]);
  Object.values(project.media).forEach((media) => { if (media.derivedFrom && used.has(media.id)) used.add(media.derivedFrom.mediaId); });
  return Object.keys(project.media).filter((id) => !used.has(id));
}

// ------------------------------------------------------------- video clips

// Clips on the picture track: video files and still images.
export function addVideoClip(project, mediaId, index, options = {}) {
  const media = mediaOf(project, mediaId, ['video', 'image']);
  if (media.kind === 'video' && !(media.duration > 0)) throw new Error('media_duration_unknown');
  const next = clone(project);
  const length = media.kind === 'image'
    ? clamp(finite(options.duration, DEFAULT_IMAGE_DURATION), MIN_CLIP, MAX_IMAGE_DURATION)
    : media.duration;
  const clip = { id: newId('clip'), mediaId, sourceStart: 0, sourceEnd: round(length), volume: 1, muted: false, transitionOut: null };
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

// Video trims choose the part of the file; an image only has a length.
export function trimClip(project, clipId, range) {
  const next = clone(project);
  const clip = next.videoClips[findClip(next, clipId)];
  const media = mediaOf(next, clip.mediaId, ['video', 'image']);
  if (media.kind === 'image') {
    const length = 'duration' in range ? finite(range.duration, clipDuration(clip))
      : finite(range.sourceEnd, clip.sourceEnd) - finite(range.sourceStart, clip.sourceStart);
    clip.sourceStart = 0;
    clip.sourceEnd = round(clamp(length, MIN_CLIP, MAX_IMAGE_DURATION));
    return normalize(touch(next));
  }
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

// The copy follows the original on the track.
export function duplicateClip(project, clipId) {
  const index = findClip(project, clipId);
  const next = clone(project);
  const copy = Object.assign(clone(next.videoClips[index]), { id: newId('clip'), transitionOut: null });
  next.videoClips.splice(index + 1, 0, copy);
  return { project: normalize(touch(next)), clipId: copy.id };
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

// Transitions are SYLVEX transition ids (transitions.js) with an optional
// colour; the engine adapter decides how each one is drawn.
export function setTransition(project, clipId, transition) {
  const next = clone(project);
  const index = findClip(next, clipId);
  if (index >= next.videoClips.length - 1) throw new Error('transition_needs_next_clip');
  next.videoClips[index].transitionOut = transition && transition.type && transition.type !== 'none'
    ? Object.assign(
      { type: String(transition.type).slice(0, 40), duration: round(clamp(finite(transition.duration, DEFAULT_TRANSITION_DURATION), 0.1, 5)) },
      /^#[0-9a-f]{6}$/i.test(String(transition.color || '')) ? { color: String(transition.color).toLowerCase() } : {},
    )
    : null;
  return touch(next);
}

// Puts another version of the clip's media (e.g. the enhanced one) in its
// place. The version remembers the source range it was made from.
export function replaceClipMedia(project, clipId, mediaId) {
  const next = clone(project);
  const clip = next.videoClips[findClip(next, clipId)];
  const media = mediaOf(next, mediaId, ['video', 'image']);
  clip.mediaId = mediaId;
  clip.sourceStart = 0;
  clip.sourceEnd = round(media.kind === 'image' ? clipDuration(clip) : media.duration);
  return normalize(touch(next));
}

// Back to the media the current version was made from.
export function revertClipMedia(project, clipId) {
  const index = findClip(project, clipId);
  const media = project.media[project.videoClips[index].mediaId];
  const source = media && media.derivedFrom;
  if (!source || !project.media[source.mediaId]) throw new Error('no_original_version');
  const next = clone(project);
  const clip = next.videoClips[index];
  clip.mediaId = source.mediaId;
  clip.sourceStart = round(finite(source.sourceStart, 0));
  clip.sourceEnd = round(finite(source.sourceEnd, project.media[source.mediaId].duration));
  return normalize(touch(next));
}

// ------------------------------------------------------------- audio clips

function findAudio(project, audioId) {
  const index = project.audioClips.findIndex((clip) => clip.id === audioId);
  if (index < 0) throw new Error('audio_not_found');
  return index;
}

// Audio clips come from audio files or from the sound of a video file
// ("Detach audio" keeps the original sound on its own track).
export function addAudioClip(project, mediaId, options = {}) {
  const media = mediaOf(project, mediaId, ['audio', 'video']);
  if (media.kind === 'video' && !media.hasAudio) throw new Error('media_has_no_audio');
  if (!(media.duration > 0)) throw new Error('media_duration_unknown');
  const next = clone(project);
  const sourceStart = round(clamp(finite(options.sourceStart, 0), 0, media.duration - MIN_CLIP));
  const sourceEnd = round(clamp(finite(options.sourceEnd, media.duration), sourceStart + MIN_CLIP, media.duration));
  const start = round(Math.max(0, finite(options.start, 0)));
  const lane = Number.isInteger(options.lane) ? clamp(options.lane, 0, MAX_AUDIO_LANES - 1) : freeLane(next, start, sourceEnd - sourceStart);
  const role = AUDIO_ROLES.includes(options.role) ? options.role : (media.kind === 'video' ? 'original' : 'audio');
  const clip = { id: newId('aclip'), mediaId, lane, start, sourceStart, sourceEnd, volume: 1, muted: false, role };
  next.audioClips.push(clip);
  return { project: touch(next), audioId: clip.id };
}

// First lane where [start, start+duration) does not overlap another clip.
function freeLane(project, start, duration, ignoreId) {
  for (let lane = 0; lane < MAX_AUDIO_LANES; lane += 1) {
    const busy = project.audioClips.some((clip) => clip.id !== ignoreId && clip.lane === lane && clip.start < start + duration && start < clip.start + clipDuration(clip));
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
  const media = mediaOf(next, clip.mediaId, ['audio', 'video']);
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

// The copy is placed right after the original, on a free lane.
export function duplicateAudio(project, audioId) {
  const clip = project.audioClips[findAudio(project, audioId)];
  const next = clone(project);
  const start = round(clip.start + clipDuration(clip));
  const copy = Object.assign(clone(clip), { id: newId('aclip'), start });
  copy.lane = next.audioClips.some((item) => item.lane === clip.lane && item.start < start + clipDuration(clip) && start < item.start + clipDuration(item))
    ? freeLane(next, start, clipDuration(clip)) : clip.lane;
  next.audioClips.push(copy);
  return { project: touch(next), audioId: copy.id };
}

export function setAudioLevel(project, audioId, patch) {
  const next = clone(project);
  const clip = next.audioClips[findAudio(next, audioId)];
  if ('volume' in patch) clip.volume = round(clamp(finite(patch.volume, 1), 0, 1));
  if ('muted' in patch) clip.muted = !!patch.muted;
  if ('role' in patch && AUDIO_ROLES.includes(patch.role)) clip.role = patch.role;
  return touch(next);
}

// Moves the sound of a video clip onto its own audio track at the same
// place, so it can be timed, trimmed and split independently.
export function detachClipAudio(project, clipId) {
  const index = findClip(project, clipId);
  const clip = project.videoClips[index];
  const media = mediaOf(project, clip.mediaId, ['video', 'image']);
  if (media.kind !== 'video' || !media.hasAudio) throw new Error('media_has_no_audio');
  const placed = layoutTimeline(project).video[index];
  const added = addAudioClip(project, clip.mediaId, { start: placed.start, sourceStart: clip.sourceStart, sourceEnd: clip.sourceEnd, role: 'original' });
  const next = added.project;
  const audio = next.audioClips.find((item) => item.id === added.audioId);
  audio.volume = clip.volume;
  next.videoClips[index].muted = true;
  return { project: next, audioId: added.audioId };
}

// Cuts [start, end) of one audio clip out, leaving a gap.
export function removeAudioRange(project, audioId, start, end) {
  const clip = project.audioClips[findAudio(project, audioId)];
  const a = Math.max(clip.start, finite(start, 0));
  const b = Math.min(clip.start + clipDuration(clip), finite(end, 0));
  if (!(b - a >= MIN_CLIP / 2)) throw new Error('range_outside_clip');
  const next = clone(project);
  const index = findAudio(next, audioId);
  const pieces = cutAudio(next.audioClips[index], a, b);
  next.audioClips.splice(index, 1, ...pieces);
  return touch(next);
}

// Pieces of an audio clip left after removing [a, b) of the timeline.
function cutAudio(clip, a, b) {
  const end = clip.start + clipDuration(clip);
  if (b <= clip.start || a >= end) return [clip];
  const pieces = [];
  if (a - clip.start >= MIN_CLIP) pieces.push(Object.assign(clone(clip), { sourceEnd: round(clip.sourceStart + (a - clip.start)) }));
  if (end - b >= MIN_CLIP) pieces.push(Object.assign(clone(clip), { id: pieces.length ? newId('aclip') : clip.id, start: round(b), sourceStart: round(clip.sourceStart + (b - clip.start)) }));
  return pieces;
}

// ------------------------------------------------------- remove a segment

// Removes [start, end) of the edit on every track and closes the gap
// (ripple delete): picture, audio, text and subtitles after the segment move
// left by its length.
export function removeRange(project, start, end) {
  const a = Math.max(0, finite(start, 0));
  const b = Math.min(projectDuration(project), finite(end, 0));
  if (!(b - a >= MIN_CLIP)) throw new Error('range_too_short');
  const length = b - a;
  const next = clone(project);
  const layout = layoutTimeline(project);
  const clips = [];
  project.videoClips.forEach((clip, index) => {
    const placed = layout.video[index];
    const copy = clone(clip);
    if (placed.end <= a || placed.start >= b) { clips.push(copy); return; }
    // The cut changes this clip, so its outgoing transition is dropped.
    copy.transitionOut = null;
    const keepHead = a - placed.start;
    const keepTail = placed.end - b;
    if (keepHead >= MIN_CLIP) clips.push(Object.assign(clone(copy), { sourceEnd: round(copy.sourceStart + keepHead) }));
    if (keepTail >= MIN_CLIP) clips.push(Object.assign(clone(copy), { id: keepHead >= MIN_CLIP ? newId('clip') : copy.id, sourceStart: round(copy.sourceEnd - keepTail) }));
  });
  next.videoClips = clips;
  next.audioClips = [];
  project.audioClips.forEach((clip) => {
    cutAudio(clone(clip), a, b).forEach((piece) => {
      if (piece.start >= b) piece.start = round(piece.start - length);
      next.audioClips.push(piece);
    });
  });
  next.texts = [];
  project.texts.forEach((text) => {
    const copy = clone(text);
    const textEnd = text.start + text.duration;
    if (textEnd <= a) { next.texts.push(copy); return; }
    if (text.start >= b) { copy.start = round(text.start - length); next.texts.push(copy); return; }
    const kept = Math.max(0, a - text.start) + Math.max(0, textEnd - b);
    if (kept < MIN_CLIP) return;
    copy.start = round(Math.min(text.start, a));
    copy.duration = round(kept);
    next.texts.push(copy);
  });
  return normalize(touch(next));
}

// -------------------------------------------------------------------- text

export const TEXT_DEFAULTS = { text: 'Текст', start: 0, duration: 3, x: 0.5, y: 0.82, fontSize: 0.07, color: '#ffffff', fontFamily: '', bold: false, italic: false, align: 'center', background: '' };
export const SUBTITLE_STYLE = { x: 0.5, y: 0.86, fontSize: 0.05, color: '#ffffff', bold: true, align: 'center', background: '#000000' };

function sanitizeText(text) {
  const clean = {
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
  // Subtitles made by "Generate Subtitles" can be replaced as a group.
  if (text.role === 'subtitle') clean.role = 'subtitle';
  return clean;
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

export function duplicateText(project, textId) {
  const text = project.texts.find((item) => item.id === textId);
  if (!text) throw new Error('text_not_found');
  return addText(project, Object.assign({}, text, { start: text.start + text.duration }));
}

// ------------------------------------------------------------- transcript

export function setTranscript(project, mediaId, transcript) {
  mediaOf(project, mediaId, ['video', 'audio']);
  const next = clone(project);
  const segments = (transcript && Array.isArray(transcript.segments) ? transcript.segments : [])
    .map((segment) => ({ start: round(Math.max(0, finite(segment.start, 0))), end: round(Math.max(0, finite(segment.end, 0))), text: String(segment.text || '').trim().slice(0, 500) }))
    .filter((segment) => segment.text && segment.end > segment.start)
    .sort((x, y) => x.start - y.start)
    .slice(0, 5000);
  next.transcripts[mediaId] = { segments, language: String(transcript && transcript.language || '').slice(0, 8), createdAt: new Date().toISOString() };
  return touch(next);
}

// Media on the timeline whose sound can be transcribed: video clips with
// audio (unless muted and detached) and audio clips.
export function speechSources(project) {
  const ids = new Set();
  project.videoClips.forEach((clip) => { const media = project.media[clip.mediaId]; if (media && media.kind === 'video' && media.hasAudio && !clip.muted) ids.add(media.id); });
  project.audioClips.forEach((clip) => { const media = project.media[clip.mediaId]; if (media && !clip.muted && (media.kind === 'audio' || media.hasAudio)) ids.add(media.id); });
  return Array.from(ids).map((id) => project.media[id]);
}

// The editing transcript on the timeline: speech of every transcribed media
// placed where its clips play, with the pauses between marked as silence.
// It is a view of the project and is never rendered into the video.
export function transcriptTimeline(project) {
  const layout = layoutTimeline(project);
  const speech = [];
  const place = (mediaId, clipStart, sourceStart, sourceEnd, clipId) => {
    const transcript = project.transcripts[mediaId];
    if (!transcript) return;
    transcript.segments.forEach((segment) => {
      const a = Math.max(segment.start, sourceStart);
      const b = Math.min(segment.end, sourceEnd);
      if (b - a < 0.05) return;
      speech.push({ kind: 'speech', start: round(clipStart + a - sourceStart), end: round(clipStart + b - sourceStart), text: segment.text, mediaId, clipId });
    });
  };
  project.videoClips.forEach((clip, index) => { if (!clip.muted) place(clip.mediaId, layout.video[index].start, clip.sourceStart, clip.sourceEnd, clip.id); });
  project.audioClips.forEach((clip) => { if (!clip.muted) place(clip.mediaId, clip.start, clip.sourceStart, clip.sourceEnd, clip.id); });
  speech.sort((x, y) => x.start - y.start || x.end - y.end);
  const items = [];
  let cursor = 0;
  speech.forEach((segment) => {
    if (segment.start - cursor >= SILENCE_MIN) items.push({ kind: 'silence', start: round(cursor), end: segment.start, text: '' });
    items.push(segment);
    cursor = Math.max(cursor, segment.end);
  });
  if (speech.length && layout.duration - cursor >= SILENCE_MIN) items.push({ kind: 'silence', start: round(cursor), end: layout.duration, text: '' });
  return items;
}

// Splits a long speech segment into readable subtitle lines, timing each
// part by its share of the text.
function subtitleChunks(segment, maxChars) {
  const words = segment.text.split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  words.forEach((word) => {
    if (line && (line + ' ' + word).length > maxChars) { lines.push(line); line = word; } else line = line ? line + ' ' + word : word;
  });
  if (line) lines.push(line);
  const total = lines.reduce((sum, item) => sum + item.length, 0) || 1;
  let cursor = segment.start;
  return lines.map((text) => {
    const duration = (segment.end - segment.start) * (text.length / total);
    const chunk = { text, start: round(cursor), duration: round(Math.max(MIN_CLIP, duration)) };
    cursor += duration;
    return chunk;
  });
}

// "Generate Subtitles": real text overlays from the transcript. Earlier
// generated subtitles are replaced; hand-made texts stay.
export function generateSubtitles(project, options = {}) {
  const speech = transcriptTimeline(project).filter((item) => item.kind === 'speech');
  if (!speech.length) throw new Error('no_speech');
  let next = clone(project);
  next.texts = next.texts.filter((text) => text.role !== 'subtitle');
  const style = Object.assign({}, SUBTITLE_STYLE, options.style || {}, { role: 'subtitle' });
  const maxChars = clamp(Math.round(finite(options.maxChars, 42)), 16, 90);
  speech.forEach((segment) => {
    subtitleChunks(segment, maxChars).forEach((chunk) => { next = addText(next, Object.assign({}, style, chunk)).project; });
  });
  return touch(next);
}

export function clearSubtitles(project) {
  const next = clone(project);
  next.texts = next.texts.filter((text) => text.role !== 'subtitle');
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

export function setUiState(project, patch) {
  const next = clone(project);
  next.ui = Object.assign({}, next.ui || {}, {
    pps: 'pps' in patch ? round(clamp(finite(patch.pps, 60), 2, 600)) : (next.ui || {}).pps,
    autoFit: 'autoFit' in patch ? !!patch.autoFit : (next.ui || {}).autoFit,
  });
  return next;
}

export function rename(project, name) {
  const next = clone(project);
  next.name = String(name || '').trim().slice(0, 120) || 'Новый проект';
  return touch(next);
}

// Keeps derived invariants: the last clip has no outgoing transition.
export function normalize(project) {
  const last = project.videoClips[project.videoClips.length - 1];
  if (last) last.transitionOut = null;
  return project;
}

// The project as it is stored: no session-only preview URLs.
export function serialize(project) {
  const copy = clone(project);
  Object.values(copy.media).forEach((media) => { delete media.previewUrl; });
  return copy;
}

export function validateProject(project) {
  if (!project || project.schema !== PROJECT_SCHEMA) return 'schema';
  for (const clip of project.videoClips) {
    const media = project.media[clip.mediaId];
    if (!media || (media.kind !== 'video' && media.kind !== 'image')) return 'video_media';
    if (!(clip.sourceEnd - clip.sourceStart >= MIN_CLIP - 1e-6) || clip.sourceStart < 0 || clip.sourceEnd > mediaLength(media) + 1e-6) return 'video_trim';
  }
  for (const clip of project.audioClips) {
    const media = project.media[clip.mediaId];
    if (!media || (media.kind !== 'audio' && media.kind !== 'video')) return 'audio_media';
    if (!(clip.sourceEnd - clip.sourceStart >= MIN_CLIP - 1e-6)) return 'audio_trim';
  }
  return '';
}
