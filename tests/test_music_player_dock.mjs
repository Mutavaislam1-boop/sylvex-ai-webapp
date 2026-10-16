// Pro Studio → Music: the Music Player block (MusicDock in cabinet.js) is a
// view over the shared PlayerManager audio. Its playlist is the account's
// music history plus the current conversation's tracks; a just-generated
// track is selected and loaded at once.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const block = source.slice(source.indexOf('  var musicDockRef = null;'), source.indexOf('  /* ===== ProStudio Grid ===== */'));
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

function harness(chat) {
  const audio = {paused: true, ended: false, currentTime: 0, duration: 0, src: '', currentSrc: '', volume: 1, muted: false, load() { this.loads = (this.loads || 0) + 1; }, addEventListener() {}};
  const PlayerManager = {audioEl: audio, currentTrack: null, playlist: [], currentIndex: 0, updateUi() {}, init() {}};
  const context = vm.createContext({
    PlayerManager, chatMessages: chat, activeMusicTrack: null, localStorage: {getItem: () => null, setItem() {}},
    document: {getElementById: () => null}, MUSIC_MODEL_LIST: [{id: 'suno_chirp_5_5', label: 'Suno v5.5'}],
    normalizePlayerTrack: (t) => ({audioUrl: t.audio_url, title: t.title, coverUrl: t.cover_url}),
    generatedUrlsFromMessage: (m) => (m.audios || []),
    musicAudioUrl: (m) => m.audio_url || '', musicCoverUrl: (m) => m.cover_url || '',
    formatAudioTime: String, getTelegramId: () => 1, quickMusicLibrary: async () => [],
  });
  vm.runInContext(block + '\n;globalThis.MusicDock = MusicDock;', context);
  const dock = context.MusicDock;
  dock.el = {};
  dock.render = () => {};
  return {dock, audio, PlayerManager, context};
}

const music = (url, extra = {}) => ({role: 'ai', metadata: Object.assign({type: 'music', audios: [url], audio_url: url, prompt: 'Synthwave night', model: 'suno_chirp_5_5'}, extra)});

test('history and conversation tracks form one playlist, oldest first, without duplicates', () => {
  const {dock} = harness([music('/s/new.mp3?sig=2'), {role: 'ai', metadata: {type: 'voice', audios: ['/s/voice.mp3']}}]);
  dock.history = [
    {id: 2, audioUrl: '/s/b.mp3?sig=b', title: 'B'},
    {id: 1, audioUrl: '/s/a.mp3?sig=a', title: 'A'},
    {id: 3, audioUrl: '/s/new.mp3?sig=1', title: 'Saved new'},
  ];
  // History comes newest first; the playlist runs oldest → newest. The
  // conversation's copy of a saved track (other signed URL) is not repeated,
  // and voice results are not music.
  const tracks = JSON.parse(JSON.stringify(dock.build()));
  assert.deepEqual(tracks.map((t) => [t.title, t.key]), [['Saved new', '/s/new.mp3'], ['A', '/s/a.mp3'], ['B', '/s/b.mp3']]);
});

test('a just-generated track is selected and loaded without starting playback', () => {
  const chat = [music('/s/one.mp3')];
  const {dock, audio} = harness(chat);
  dock.sync();
  assert.equal(dock.current().key, '/s/one.mp3');
  chat.push(music('/s/fresh.mp3', {title: 'Fresh', cover_url: '/c.jpg'}));
  dock.sync();
  const track = dock.current();
  assert.deepEqual([track.title, track.coverUrl, track.model, dock.index, dock.tracks.length], ['Fresh', '/c.jpg', 'Suno v5.5', 1, 2]);
  assert.equal(audio.src, '/s/fresh.mp3');
  assert.equal(audio.paused, true);
});

test('a new track does not interrupt the one that is playing', () => {
  const chat = [music('/s/one.mp3')];
  const {dock, audio, PlayerManager} = harness(chat);
  dock.sync();
  PlayerManager.currentTrack = {audioUrl: '/s/one.mp3'};
  audio.paused = false;
  chat.push(music('/s/fresh.mp3'));
  dock.sync();
  assert.equal(dock.current().key, '/s/one.mp3');
  assert.equal(dock.tracks.length, 2);
});

test('the player sits in the Music mode tool area, followed by the divider and prompt', () => {
  const player = html.indexOf('id="studioMusicPlayer"');
  assert.ok(player > 0 && player < html.indexOf('class="studio-prompt-column"'));
  for (const id of ['smpCoverImg', 'smpTitle', 'smpPlay', 'smpPrev', 'smpNext', 'smpProgress', 'smpCurrent', 'smpDuration', 'smpSpeed', 'smpVolume', 'smpMute', 'smpListBtn']) {
    assert.ok(html.includes('id="' + id + '"'), id);
  }
  assert.match(css, /\.has-music-player\[data-composer-mode="music"\] \.studio-video-panel\{grid-template-columns:clamp\(220px,28vw,430px\) minmax\(0,1fr\)/);
  assert.match(css, /\.has-music-player\[data-composer-mode="music"\] \.studio-prompt-column\{border-left:1px solid/);
  assert.match(css, /\[data-composer-mode="music"\] \.studio-music-player\{display:flex\}/);
  // Copies of the markup without the player keep the previous Music layout.
  assert.match(css, /\[data-composer-mode="music"\] \.studio-video-panel\{grid-template-columns:1fr;padding:28px 24px 24px\}/);
  assert.match(source, /composer\.classList\.add\('has-music-player'\)/);
});
