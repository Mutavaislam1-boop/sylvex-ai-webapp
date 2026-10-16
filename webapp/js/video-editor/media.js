// Timeline pictures for the SYLVEX editor: frames of video clips and audio
// waveforms. They are computed in the browser from the project media (the
// local copy when there is one) and cached per media file, so zooming only
// picks other frames or redraws the same peaks at another scale.

const FRAME_HEIGHT = 54;
const PEAKS_PER_SECOND = 100;
const MAX_DECODE_BYTES = 80 * 1024 * 1024;

// ------------------------------------------------------------------ frames

export const frameKey = (mediaId, time) => mediaId + '@' + Number(time).toFixed(2);

export function createFrameCache({ onFrame } = {}) {
  const frames = new Map(); // key -> dataURL
  const queues = new Map(); // mediaId -> { video, pending:[], busy }
  const failed = new Set();

  const keyOf = frameKey;

  function grabber(media) {
    let entry = queues.get(media.id);
    if (entry) return entry;
    const video = document.createElement('video');
    video.muted = true;
    video.preload = 'auto';
    video.playsInline = true;
    video.crossOrigin = 'anonymous';
    video.src = media.previewUrl || media.url;
    entry = { video, pending: [], busy: false, ready: null };
    entry.ready = new Promise((resolve, reject) => {
      video.onloadeddata = resolve;
      video.onerror = () => reject(new Error('frame_source_failed'));
      setTimeout(() => reject(new Error('frame_source_timeout')), 20000);
    });
    queues.set(media.id, entry);
    return entry;
  }

  async function pump(media, entry) {
    if (entry.busy) return;
    entry.busy = true;
    try {
      await entry.ready;
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      while (entry.pending.length) {
        const time = entry.pending.shift();
        const key = keyOf(media.id, time);
        if (frames.has(key)) continue;
        const video = entry.video;
        const target = Math.min(Math.max(0, time), Math.max(0, (video.duration || time) - 0.05));
        // Wait until the frame at `target` is decoded; a seek that does not
        // finish leaves the tile empty instead of caching a blank frame.
        const ready = await new Promise((resolve) => {
          let settled = false;
          const finish = (ok) => { if (settled) return; settled = true; video.removeEventListener('seeked', seeked); clearTimeout(timer); resolve(ok); };
          const seeked = () => {
            if (typeof video.requestVideoFrameCallback === 'function') video.requestVideoFrameCallback(() => finish(true));
            else finish(true);
            setTimeout(() => finish(video.readyState >= 2), 600);
          };
          const timer = setTimeout(() => finish(false), 5000);
          video.addEventListener('seeked', seeked);
          if (Math.abs(video.currentTime - target) < 0.001 && video.readyState >= 2) finish(true);
          else video.currentTime = target;
        });
        if (!ready) continue;
        const ratio = (video.videoWidth || 16) / (video.videoHeight || 9);
        canvas.height = FRAME_HEIGHT * 2;
        canvas.width = Math.round(canvas.height * ratio);
        try {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          frames.set(key, canvas.toDataURL('image/jpeg', 0.6));
        } catch (_) {
          frames.set(key, '');
        }
        if (onFrame) onFrame(media.id, time, frames.get(key));
      }
    } catch (_) {
      failed.add(media.id);
      entry.pending.length = 0;
    } finally {
      entry.busy = false;
    }
  }

  return {
    // A frame of `media` at `time` (seconds, quantised by the caller), or
    // '' while it is being made. `onFrame` reports when it arrives.
    get(media, time) {
      if (!media || media.kind !== 'video' || failed.has(media.id)) return '';
      const key = keyOf(media.id, time);
      if (frames.has(key)) return frames.get(key);
      const entry = grabber(media);
      if (!entry.pending.includes(time)) entry.pending.push(time);
      pump(media, entry);
      return '';
    },
    // Media file replaced (e.g. upload finished): frames stay valid.
    forget(mediaId) {
      const entry = queues.get(mediaId);
      if (entry) { entry.video.removeAttribute('src'); entry.video.load(); queues.delete(mediaId); }
    },
    destroy() {
      for (const entry of queues.values()) { entry.pending.length = 0; entry.video.removeAttribute('src'); entry.video.load(); }
      queues.clear();
      frames.clear();
    },
  };
}

// Frame times for a clip `pixelWidth` wide, one frame per tile. Times are
// quantised so neighbouring zoom levels reuse frames.
export function frameTiles(clip, pixelWidth, tileWidth) {
  const count = Math.max(1, Math.ceil(pixelWidth / tileWidth));
  const span = Math.max(0.01, clip.sourceEnd - clip.sourceStart);
  const step = span / count;
  const quantum = step >= 4 ? 1 : step >= 1 ? 0.5 : 0.1;
  return Array.from({ length: count }, (_, index) => {
    const raw = clip.sourceStart + (index + 0.5) * step;
    return Math.round(raw / quantum) * quantum;
  });
}

// --------------------------------------------------------------- waveforms

export function createWaveformCache({ onReady } = {}) {
  const peaks = new Map(); // mediaId -> Float32Array (max abs per 1/PEAKS_PER_SECOND s)
  const loading = new Map();
  const failed = new Set();
  let audioContext = null;

  async function decode(media) {
    const url = media.previewUrl || media.url;
    const response = await fetch(url);
    const length = Number(response.headers.get('content-length') || 0);
    if (length > MAX_DECODE_BYTES) throw new Error('too_large');
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > MAX_DECODE_BYTES) throw new Error('too_large');
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) throw new Error('no_audio_context');
    audioContext = audioContext || new Context();
    const audio = await new Promise((resolve, reject) => {
      const result = audioContext.decodeAudioData(buffer, resolve, reject);
      if (result && typeof result.then === 'function') result.then(resolve, reject);
    });
    const channels = Array.from({ length: audio.numberOfChannels }, (_, index) => audio.getChannelData(index));
    const per = Math.max(1, Math.floor(audio.sampleRate / PEAKS_PER_SECOND));
    const count = Math.ceil(audio.length / per);
    const out = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
      let max = 0;
      const from = i * per;
      const to = Math.min(audio.length, from + per);
      for (const data of channels) {
        for (let j = from; j < to; j += 4) { const v = Math.abs(data[j]); if (v > max) max = v; }
      }
      out[i] = max;
    }
    // Normalise so quiet recordings are still readable.
    let top = 0;
    for (let i = 0; i < count; i += 1) if (out[i] > top) top = out[i];
    if (top > 0) for (let i = 0; i < count; i += 1) out[i] = Math.min(1, out[i] / top);
    return out;
  }

  return {
    has: (mediaId) => peaks.has(mediaId),
    failed: (mediaId) => failed.has(mediaId),
    request(media) {
      if (!media || peaks.has(media.id) || failed.has(media.id) || loading.has(media.id)) return;
      const job = decode(media).then((data) => { peaks.set(media.id, data); if (onReady) onReady(media.id); })
        .catch(() => { failed.add(media.id); if (onReady) onReady(media.id); })
        .finally(() => loading.delete(media.id));
      loading.set(media.id, job);
    },
    // Draws the waveform of [sourceStart, sourceEnd) of `mediaId` into the
    // canvas, filling its width (the clip's width at the current zoom).
    draw(canvas, mediaId, sourceStart, sourceEnd, color) {
      const data = peaks.get(mediaId);
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(canvas.clientWidth || canvas.width));
      const height = Math.max(1, Math.round(canvas.clientHeight || canvas.height));
      canvas.width = Math.min(16000, Math.round(width * ratio));
      canvas.height = Math.round(height * ratio);
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!data) return false;
      ctx.fillStyle = color || 'rgba(255,255,255,.75)';
      const mid = canvas.height / 2;
      const from = sourceStart * PEAKS_PER_SECOND;
      const span = Math.max(1e-6, (sourceEnd - sourceStart) * PEAKS_PER_SECOND);
      for (let x = 0; x < canvas.width; x += 1) {
        const a = Math.floor(from + (x / canvas.width) * span);
        const b = Math.max(a + 1, Math.floor(from + ((x + 1) / canvas.width) * span));
        let max = 0;
        for (let i = a; i < b && i < data.length; i += 1) if (data[i] > max) max = data[i];
        const h = Math.max(1, max * (canvas.height - 2));
        ctx.fillRect(x, mid - h / 2, 1, h);
      }
      return true;
    },
    destroy() {
      peaks.clear();
      if (audioContext && audioContext.close) audioContext.close().catch(() => {});
      audioContext = null;
    },
  };
}
