// Run with: node --test tests/test_video_editor_project.mjs
// The SYLVEX video project model is engine-neutral and pure: every edit is
// expressed as data that any engine can render.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as P from '../webapp/js/video-editor/project.js';

function withVideos(...durations) {
  let project = P.createProject();
  const clipIds = [];
  durations.forEach((duration, index) => {
    const media = P.addMedia(project, {kind: 'video', url: 'blob:v' + index, name: 'v' + index + '.mp4', duration, width: 1920, height: 1080});
    const added = P.addVideoClip(media.project, media.mediaId);
    project = added.project;
    clipIds.push(added.clipId);
  });
  return {project, clipIds};
}

function withAudio(project, duration, options) {
  const media = P.addMedia(project, {kind: 'audio', url: 'blob:a', name: 'a.mp3', duration});
  return P.addAudioClip(media.project, media.mediaId, options);
}

test('clips play in order and the first video sets the frame and export size', () => {
  const {project} = withVideos(5, 3);
  const layout = P.layoutTimeline(project);
  assert.deepEqual(layout.video.map((item) => [item.start, item.end]), [[0, 5], [5, 8]]);
  assert.equal(layout.duration, 8);
  assert.deepEqual([project.settings.width, project.settings.height, project.exportSettings.width, project.exportSettings.height], [1920, 1080, 1920, 1080]);
  assert.equal(project.schema, 'sylvex.video-project');
});

test('split, trim, move and remove clips', () => {
  let {project, clipIds} = withVideos(10, 4);
  const split = P.splitClip(project, clipIds[0], 6);
  project = split.project;
  assert.deepEqual(project.videoClips.map((clip) => [clip.sourceStart, clip.sourceEnd]), [[0, 6], [6, 10], [0, 4]]);
  assert.throws(() => P.splitClip(project, clipIds[0], 0.05), /split_out_of_range/);
  project = P.trimClip(project, split.clipId, {sourceStart: 7, sourceEnd: 20});
  assert.deepEqual([project.videoClips[1].sourceStart, project.videoClips[1].sourceEnd], [7, 10]);
  project = P.moveClip(project, clipIds[1], 0);
  assert.deepEqual(project.videoClips.map((clip) => clip.id), [clipIds[1], clipIds[0], split.clipId]);
  project = P.removeClip(project, clipIds[0]);
  assert.equal(project.videoClips.length, 2);
  assert.equal(P.projectDuration(project), 7);
});

test('transitions overlap the next clip and are limited by the shorter clip', () => {
  let {project, clipIds} = withVideos(4, 4, 1);
  project = P.setTransition(project, clipIds[0], {type: 'cross-fade', duration: 1});
  project = P.setTransition(project, clipIds[1], {type: 'push', duration: 3});
  const layout = P.layoutTimeline(project);
  assert.deepEqual(layout.video.map((item) => item.start), [0, 3, 6.5]);
  assert.deepEqual(layout.video.map((item) => item.transition), [1, 0.5, 0]);
  assert.throws(() => P.setTransition(project, clipIds[2], {type: 'fade'}), /transition_needs_next_clip/);
  project = P.setTransition(project, clipIds[0], null);
  assert.equal(project.videoClips[0].transitionOut, null);
  // A clip that becomes last loses its outgoing transition.
  project = P.moveClip(project, clipIds[1], 2);
  assert.equal(project.videoClips[2].transitionOut, null);
});

test('multiple audio clips: lanes, move, trim keeps position, split, volume and mute', () => {
  let {project} = withVideos(20);
  const first = withAudio(project, 8, {start: 0});
  const second = withAudio(first.project, 5, {start: 2});
  project = second.project;
  assert.deepEqual(project.audioClips.map((clip) => clip.lane), [0, 1]);
  project = P.moveAudio(project, second.audioId, {start: 9, lane: 0});
  project = P.trimAudio(project, second.audioId, {sourceStart: 1});
  const moved = project.audioClips.find((clip) => clip.id === second.audioId);
  assert.deepEqual([moved.start, moved.sourceStart, moved.sourceEnd, moved.lane], [10, 1, 5, 0]);
  const split = P.splitAudio(project, first.audioId, 3);
  project = split.project;
  const parts = project.audioClips.filter((clip) => clip.mediaId === project.audioClips[0].mediaId);
  assert.deepEqual(parts.map((clip) => [clip.start, clip.sourceStart, clip.sourceEnd]), [[0, 0, 3], [3, 3, 8]]);
  project = P.setAudioLevel(project, split.audioId, {volume: 0.25, muted: true});
  const changed = project.audioClips.find((clip) => clip.id === split.audioId);
  assert.deepEqual([changed.volume, changed.muted], [0.25, true]);
  project = P.removeAudio(project, split.audioId);
  assert.equal(project.audioClips.length, 2);
});

test('original video audio has its own volume and mute', () => {
  let {project, clipIds} = withVideos(3, 3);
  project = P.setClipAudio(project, clipIds[0], {volume: 0.4});
  project = P.setAllClipsAudio(project, {muted: true});
  assert.deepEqual(project.videoClips.map((clip) => [clip.volume, clip.muted]), [[0.4, true], [1, true]]);
});

test('text overlays are sanitised and timed', () => {
  let {project} = withVideos(10);
  const added = P.addText(project, {text: 'Привет', start: 2, duration: 4, color: '#FF0000', fontSize: 5, x: 2});
  project = added.project;
  assert.deepEqual(project.texts[0], Object.assign({id: added.textId}, P.TEXT_DEFAULTS, {text: 'Привет', start: 2, duration: 4, color: '#ff0000', fontSize: 0.3, x: 1, y: 0.82}));
  project = P.updateText(project, added.textId, {bold: true, align: 'left', color: 'red'});
  assert.equal(project.texts[0].bold, true);
  assert.equal(project.texts[0].align, 'left');
  assert.equal(project.texts[0].color, '#ffffff');
  project = P.removeText(project, added.textId);
  assert.equal(project.texts.length, 0);
});

test('the video track defines the length; audio alone otherwise', () => {
  let {project} = withVideos(5);
  project = withAudio(project, 30, {start: 0}).project;
  assert.equal(P.projectDuration(project), 5);
  const audioOnly = withAudio(P.createProject(), 7, {start: 1}).project;
  assert.equal(P.projectDuration(audioOnly), 8);
});

test('operations never mutate the input and validation catches broken trims', () => {
  const {project, clipIds} = withVideos(5);
  const snapshot = JSON.stringify(project);
  P.trimClip(project, clipIds[0], {sourceStart: 1});
  P.addText(project, {});
  assert.equal(JSON.stringify(project), snapshot);
  assert.equal(P.validateProject(project), '');
  const broken = JSON.parse(snapshot);
  broken.videoClips[0].sourceEnd = 99;
  assert.equal(P.validateProject(broken), 'video_trim');
});

test('export settings keep the source resolution and accept common frame rates', () => {
  let {project} = withVideos(5);
  project = P.setExportSettings(project, {fps: 60});
  assert.equal(project.exportSettings.fps, 60);
  project = P.setExportSettings(project, {fps: 17});
  assert.equal(project.exportSettings.fps, 60);
  assert.deepEqual([project.exportSettings.width, project.exportSettings.height], [1920, 1080]);
});

// ---- SYLVEX native tools

test('images live on the picture track with their own length and mix with video', () => {
  let {project, clipIds} = withVideos(4);
  const image = P.addMedia(project, {kind: 'image', url: '/api/public/storage/generated/video-inputs/a.png', name: 'a.png', width: 800, height: 600});
  assert.equal(image.project.media[image.mediaId].duration, 0);
  const added = P.addVideoClip(image.project, image.mediaId, 0);
  project = added.project;
  assert.deepEqual(P.layoutTimeline(project).video.map((item) => item.duration), [P.DEFAULT_IMAGE_DURATION, 4]);
  project = P.trimClip(project, added.clipId, {duration: 7.5});
  assert.equal(P.clipDuration(project.videoClips[0]), 7.5);
  project = P.moveClip(project, added.clipId, 1);
  assert.deepEqual(project.videoClips.map((clip) => clip.id), [clipIds[0], added.clipId]);
  assert.equal(P.validateProject(project), '');
  assert.throws(() => P.addAudioClip(project, image.mediaId), /media_not_found/);
});

test('duplicate clips, audio and text', () => {
  let {project, clipIds} = withVideos(4, 2);
  const dup = P.duplicateClip(project, clipIds[0]);
  project = dup.project;
  assert.deepEqual(project.videoClips.map((clip) => clip.id), [clipIds[0], dup.clipId, clipIds[1]]);
  const audio = withAudio(project, 5, {start: 1});
  const copy = P.duplicateAudio(audio.project, audio.audioId);
  const placed = copy.project.audioClips.find((clip) => clip.id === copy.audioId);
  assert.deepEqual([placed.start, placed.lane], [6, 0]);
  const text = P.addText(copy.project, {text: 'A', start: 1, duration: 2});
  const textCopy = P.duplicateText(text.project, text.textId);
  assert.equal(textCopy.project.texts.find((item) => item.id === textCopy.textId).start, 3);
});

test('removing a segment cuts every track and closes the gap', () => {
  let {project} = withVideos(10, 6);
  project = P.setTransition(project, project.videoClips[0].id, {type: 'cross-fade', duration: 1});
  project = withAudio(project, 15, {start: 0}).project;
  project = P.addText(project, {text: 'after', start: 12, duration: 2}).project;
  project = P.addText(project, {text: 'inside', start: 4, duration: 1}).project;
  const before = P.projectDuration(project);
  project = P.removeRange(project, 3, 5);
  assert.equal(P.projectDuration(project), before - 2 + 1); // the cut also drops the 1 s transition overlap
  assert.deepEqual(project.videoClips.map((clip) => [clip.sourceStart, clip.sourceEnd]), [[0, 3], [5, 10], [0, 6]]);
  assert.ok(project.videoClips.every((clip) => !clip.transitionOut));
  assert.deepEqual(project.audioClips.map((clip) => [clip.start, clip.sourceStart, clip.sourceEnd]), [[0, 0, 3], [3, 5, 15]]);
  assert.deepEqual(project.texts.map((text) => [text.text, text.start]), [['after', 10]]);
  assert.throws(() => P.removeRange(project, 2, 2.05), /range_too_short/);
});

test('one audio clip can lose a fragment without moving anything else', () => {
  const {project} = withVideos(10);
  const audio = withAudio(project, 8, {start: 1});
  const next = P.removeAudioRange(audio.project, audio.audioId, 3, 4);
  assert.deepEqual(next.audioClips.map((clip) => [clip.start, clip.sourceStart, clip.sourceEnd]), [[1, 0, 2], [4, 3, 8]]);
  assert.equal(P.projectDuration(next), 10);
});

test('original video sound can be detached to its own track', () => {
  let {project, clipIds} = withVideos(5, 5);
  project = P.trimClip(project, clipIds[1], {sourceStart: 1, sourceEnd: 4});
  const detached = P.detachClipAudio(project, clipIds[1]);
  const audio = detached.project.audioClips[0];
  assert.deepEqual([audio.start, audio.sourceStart, audio.sourceEnd, audio.role], [5, 1, 4, 'original']);
  assert.equal(detached.project.videoClips[1].muted, true);
  assert.equal(P.validateProject(detached.project), '');
});

test('the transcript follows the edit, marks silence and becomes subtitles', () => {
  let {project, clipIds} = withVideos(10);
  const mediaId = project.videoClips[0].mediaId;
  project = P.setTranscript(project, mediaId, {language: 'ru', segments: [
    {start: 1, end: 3, text: 'Привет всем'},
    {start: 6, end: 9, text: 'это очень длинная фраза которая не помещается в одну строку субтитров'},
  ]});
  project = P.trimClip(project, clipIds[0], {sourceStart: 0.5});
  const items = P.transcriptTimeline(project);
  assert.deepEqual(items.map((item) => [item.kind, item.start, item.end]), [
    // the 0.5 s before the first words is shorter than a pause
    ['speech', 0.5, 2.5], ['silence', 2.5, 5.5], ['speech', 5.5, 8.5], ['silence', 8.5, 9.5],
  ]);
  project = P.addText(project, {text: 'manual'}).project;
  project = P.generateSubtitles(project, {maxChars: 30});
  const subs = project.texts.filter((text) => text.role === 'subtitle');
  assert.ok(subs.length >= 3);
  assert.equal(subs[0].text, 'Привет всем');
  assert.ok(subs.every((text) => text.text.length <= 30 && text.background === '#000000'));
  project = P.generateSubtitles(project, {});
  assert.equal(project.texts.filter((text) => text.role === 'subtitle').length, 3);
  assert.equal(P.clearSubtitles(project).texts.map((text) => text.text).join(), 'manual');
  assert.throws(() => P.generateSubtitles(P.createProject()), /no_speech/);
});

test('an enhanced version replaces the clip and the original can come back', () => {
  let {project, clipIds} = withVideos(10);
  project = P.trimClip(project, clipIds[0], {sourceStart: 2, sourceEnd: 6});
  const original = project.videoClips[0].mediaId;
  const enhanced = P.addMedia(project, {kind: 'video', url: '/api/public/storage/generated/videos/e.mp4', duration: 4, width: 3840, height: 2160, origin: 'enhance_video', derivedFrom: {mediaId: original, sourceStart: 2, sourceEnd: 6}});
  project = P.replaceClipMedia(enhanced.project, clipIds[0], enhanced.mediaId);
  assert.deepEqual([project.videoClips[0].mediaId, project.videoClips[0].sourceStart, project.videoClips[0].sourceEnd], [enhanced.mediaId, 0, 4]);
  // The project frame stays the one of the first upload.
  assert.equal(project.settings.width, 1920);
  project = P.revertClipMedia(project, clipIds[0]);
  assert.deepEqual([project.videoClips[0].mediaId, project.videoClips[0].sourceStart, project.videoClips[0].sourceEnd], [original, 2, 6]);
  assert.throws(() => P.revertClipMedia(project, clipIds[0]), /no_original_version/);
});

test('saved projects keep durable URLs only and older projects are upgraded', () => {
  let {project} = withVideos(3);
  const id = project.videoClips[0].mediaId;
  project = P.updateMedia(project, id, {url: '/api/public/storage/generated/video-inputs/v.mp4', previewUrl: 'blob:local'});
  const saved = P.serialize(project);
  assert.equal(saved.media[id].url, '/api/public/storage/generated/video-inputs/v.mp4');
  assert.equal('previewUrl' in saved.media[id], false);
  const old = JSON.parse(JSON.stringify(saved));
  delete old.transcripts; delete old.ui; old.version = 1;
  const upgraded = P.upgradeProject(old);
  assert.deepEqual([upgraded.version, upgraded.transcripts, upgraded.ui.autoFit], [P.PROJECT_VERSION, {}, true]);
  assert.equal(P.setUiState(upgraded, {pps: 120}).ui.pps, 120);
});
