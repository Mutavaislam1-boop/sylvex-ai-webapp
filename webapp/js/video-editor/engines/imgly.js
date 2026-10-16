// IMG.LY CE.SDK (CreativeEngine) implementation of the SYLVEX video engine
// contract (see ../editor.js). This is the only file that knows IMG.LY:
// it receives the SYLVEX project and keeps an engine scene in sync with it.
//
// Engine reference: @cesdk/engine (headless CreativeEngine), video scenes
// with a page, a 'track' for sequential clips (video and image blocks),
// 'audio' blocks, 'text' blocks and clip-to-clip transitions
// (createTransition / setTransition).
//
// Transitions arrive as SYLVEX library entries (../transitions.js: kind,
// direction, colour); this adapter maps them onto IMG.LY transition types
// and their properties.
import { transitionById } from '../transitions.js';

// SYLVEX directions -> IMG.LY enum values of 'transition/<type>/direction'.
const DIRECTION_VALUES = {
  left: 'Left', right: 'Right', up: 'Up', down: 'Down',
  clockwise: 'Clockwise', counterclockwise: 'CounterClockwise',
  horizontal: 'Horizontal', vertical: 'Vertical',
};
// Typeface used when the engine's typeface library cannot be loaded
// (font files from IMG.LY's documentation).
const FALLBACK_TYPEFACES = [{
  name: 'Roboto',
  fonts: [
    { uri: 'https://cdn.img.ly/packages/imgly/cesdk-js/latest/assets/extensions/ly.img.cesdk.fonts/fonts/Roboto/Roboto-Regular.ttf', subFamily: 'Regular' },
    { uri: 'https://cdn.img.ly/packages/imgly/cesdk-js/latest/assets/extensions/ly.img.cesdk.fonts/fonts/Roboto/Roboto-Bold.ttf', subFamily: 'Bold', weight: 'bold' },
    { uri: 'https://cdn.img.ly/packages/imgly/cesdk-js/latest/assets/extensions/ly.img.cesdk.fonts/fonts/Roboto/Roboto-Italic.ttf', subFamily: 'Italic', style: 'italic' },
  ],
}];
const MEDIA_LOAD_TIMEOUT = 20000;

export class VideoEngineError extends Error {
  constructor(code, cause) {
    super(code);
    this.code = code;
    this.cause = cause;
  }
}

function hexToColor(hex, alpha = 1) {
  const value = /^#([0-9a-f]{6})$/i.exec(String(hex || '')) ? parseInt(String(hex).slice(1), 16) : 0xffffff;
  return { r: ((value >> 16) & 255) / 255, g: ((value >> 8) & 255) / 255, b: (value & 255) / 255, a: alpha };
}

export function createImglyEngine(config = {}) {
  let sdk = null;
  let engine = null;
  let page = 0;
  let track = 0;
  let canExport = false;
  let exportReason = '';
  let engineTransitions = [];
  let typefaces = [];
  let frame = { width: 0, height: 0 };
  const clips = new Map(); // clipId -> { block, fill, url }
  const audios = new Map(); // audioId -> { block, url }
  const texts = new Map(); // textId -> block
  const transitionBlocks = new Map(); // clipId -> { block, type }

  let stage = null;
  let resizeObserver = null;
  const valid = (id) => !!id && engine.block.isValid(id);

  // The engine can wait forever on a file it cannot decode; give up after a
  // while and report which media failed so the editor can roll it back.
  async function withTimeout(promise, mediaId) {
    let timer = 0;
    try {
      await Promise.race([
        promise,
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), MEDIA_LOAD_TIMEOUT); }),
      ]);
    } catch (error) {
      throw Object.assign(new VideoEngineError('media_unsupported', error), { mediaId });
    } finally {
      clearTimeout(timer);
    }
  }

  const loadResource = (block, mediaId) => withTimeout(engine.block.forceLoadAVResource(block), mediaId);

  function fitCamera() {
    if (!engine || !page || !stage || !stage.clientWidth || !stage.clientHeight) return;
    engine.scene.zoomToBlock(page, { padding: 0 }).catch(() => {});
  }

  async function loadTypefaces() {
    try {
      // Typeface library from the engine's asset location (IMG.LY "default
      // assets" guide).
      const base = String(engine.getBaseURL() || '');
      await engine.asset.addLocalAssetSourceFromJSONURI(base + (base.endsWith('/') ? '' : '/') + 'ly.img.typeface/content.json');
      const result = await engine.asset.findAssets('ly.img.typeface', { page: 0, perPage: 300 });
      const list = (result && result.assets || []).map((asset) => asset.payload && asset.payload.typeface).filter((face) => face && face.name && Array.isArray(face.fonts) && face.fonts.length);
      if (list.length) return list;
    } catch (error) {
      console.warn('[video-editor] typefaces unavailable, using fallback', error);
    }
    return FALLBACK_TYPEFACES;
  }

  function pickFont(typeface, bold, italic) {
    const fonts = typeface.fonts;
    const isBold = (font) => font.weight === 'bold' || Number(font.weight) >= 600 || /bold/i.test(font.subFamily || '');
    const isItalic = (font) => font.style === 'italic' || /italic/i.test(font.subFamily || '');
    return fonts.find((font) => isBold(font) === bold && isItalic(font) === italic)
      || fonts.find((font) => isBold(font) === bold)
      || fonts.find((font) => !isBold(font) && !isItalic(font))
      || fonts[0];
  }

  const sourceOf = (media) => media.previewUrl || media.url;

  async function ensureClip(clip, media) {
    let entry = clips.get(clip.id);
    const url = sourceOf(media);
    if (entry && (!valid(entry.block) || entry.url !== url)) {
      if (valid(entry.block)) engine.block.destroy(entry.block);
      transitionBlocks.delete(clip.id);
      entry = null;
    }
    if (!entry) {
      let block = 0;
      let fill = 0;
      const duration = Math.max(0.1, clip.sourceEnd - clip.sourceStart);
      try {
        if (media.kind === 'image') {
          block = await engine.block.addImage(url, { size: { width: frame.width, height: frame.height }, timeline: { duration } });
          engine.block.appendChild(track, block);
          fill = engine.block.getFill(block);
          await withTimeout(engine.block.forceLoadResources([fill]), media.id);
        } else {
          block = await engine.block.addVideo(url, frame.width, frame.height, { timeline: { duration } });
          engine.block.appendChild(track, block);
          fill = engine.block.getFill(block);
          await loadResource(fill, media.id);
        }
      } catch (error) {
        if (valid(block)) engine.block.destroy(block);
        throw error.code ? error : Object.assign(new VideoEngineError('media_unsupported', error), { mediaId: media.id });
      }
      try { engine.block.setContentFillMode(block, 'Contain'); } catch (_) {}
      entry = { block, fill, url, kind: media.kind };
      clips.set(clip.id, entry);
    }
    return entry;
  }

  // IMG.LY transition of a SYLVEX library entry (or of an older project's
  // bare IMG.LY type).
  function transitionSpec(transitionOut) {
    if (!transitionOut || !transitionOut.type) return null;
    const item = transitionById(transitionOut.type);
    const kind = item ? item.kind : transitionOut.type;
    if (!engineTransitions.includes(kind)) return null;
    const color = transitionOut.color || (item && item.color) || '';
    return { kind, dir: item ? item.dir || '' : '', color, key: [kind, item ? item.dir || '' : '', color].join('|') };
  }

  function applyTransitionProperties(block, spec) {
    const base = 'transition/' + spec.kind + '/';
    const props = new Set(engine.block.findAllProperties(block));
    if (spec.dir && props.has(base + 'direction') && DIRECTION_VALUES[spec.dir]) {
      try { engine.block.setEnum(block, base + 'direction', DIRECTION_VALUES[spec.dir]); } catch (_) {}
    }
    if (spec.color && props.has(base + 'color')) {
      try { engine.block.setColor(block, base + 'color', hexToColor(spec.color)); } catch (_) {}
    }
  }

  async function syncVideo(project, layout) {
    const wanted = new Set(project.videoClips.map((clip) => clip.id));
    for (const [clipId, entry] of clips) {
      if (!wanted.has(clipId)) {
        if (valid(entry.block)) engine.block.destroy(entry.block);
        clips.delete(clipId);
        transitionBlocks.delete(clipId);
      }
    }
    for (let index = 0; index < project.videoClips.length; index += 1) {
      const clip = project.videoClips[index];
      const entry = await ensureClip(clip, project.media[clip.mediaId]);
      const duration = Math.max(0.1, clip.sourceEnd - clip.sourceStart);
      if (entry.kind !== 'image') {
        engine.block.setTrimOffset(entry.fill, clip.sourceStart);
        engine.block.setTrimLength(entry.fill, duration);
        engine.block.setVolume(entry.fill, clip.volume);
        engine.block.setMuted(entry.fill, !!clip.muted);
      }
      engine.block.setDuration(entry.block, duration);
      engine.block.insertChild(track, entry.block, index);
    }
    engine.block.fillParent(track);
    // Transitions after order and durations are final.
    project.videoClips.forEach((clip, index) => {
      const entry = clips.get(clip.id);
      const current = transitionBlocks.get(clip.id);
      const spec = transitionSpec(clip.transitionOut);
      const duration = layout.video[index] ? layout.video[index].transition : 0;
      const stale = current && !valid(current.block);
      if (current && (stale || !spec || current.key !== spec.key || !duration)) {
        if (!stale) {
          engine.block.removeTransition(entry.block);
          engine.block.destroy(current.block);
        }
        transitionBlocks.delete(clip.id);
      }
      const next = project.videoClips[index + 1] && clips.get(project.videoClips[index + 1].id);
      if (!spec || !duration || !next) return;
      if (!engine.block.supportsTransition(entry.block) || !engine.block.supportsTransition(next.block)) return;
      let assigned = transitionBlocks.get(clip.id);
      if (!assigned) {
        const block = engine.block.createTransition(spec.kind);
        applyTransitionProperties(block, spec);
        engine.block.setTransition(entry.block, block);
        assigned = { block, key: spec.key };
        transitionBlocks.set(clip.id, assigned);
      }
      engine.block.setDuration(assigned.block, duration);
    });
  }

  async function syncAudio(project) {
    const wanted = new Set(project.audioClips.map((clip) => clip.id));
    for (const [audioId, entry] of audios) {
      if (!wanted.has(audioId)) { if (valid(entry.block)) engine.block.destroy(entry.block); audios.delete(audioId); }
    }
    for (const clip of project.audioClips) {
      const media = project.media[clip.mediaId];
      const url = sourceOf(media);
      let entry = audios.get(clip.id);
      if (entry && (!valid(entry.block) || entry.url !== url)) { if (valid(entry.block)) engine.block.destroy(entry.block); entry = null; }
      if (!entry) {
        // Audio files, or the sound of a video file (detached original audio).
        const block = engine.block.create('audio');
        engine.block.setString(block, 'audio/fileURI', url);
        engine.block.appendChild(page, block);
        try {
          await loadResource(block, media.id);
        } catch (error) {
          engine.block.destroy(block);
          throw error;
        }
        entry = { block, url };
        audios.set(clip.id, entry);
      }
      const duration = Math.max(0.1, clip.sourceEnd - clip.sourceStart);
      engine.block.setTimeOffset(entry.block, clip.start);
      engine.block.setTrimOffset(entry.block, clip.sourceStart);
      engine.block.setTrimLength(entry.block, duration);
      engine.block.setDuration(entry.block, duration);
      engine.block.setVolume(entry.block, clip.volume);
      engine.block.setMuted(entry.block, !!clip.muted);
    }
  }

  function syncText(project) {
    const wanted = new Set(project.texts.map((text) => text.id));
    for (const [textId, block] of texts) {
      if (!wanted.has(textId)) { if (valid(block)) engine.block.destroy(block); texts.delete(textId); }
    }
    for (const text of project.texts) {
      let block = texts.get(text.id);
      if (!valid(block)) {
        block = engine.block.create('text');
        engine.block.appendChild(page, block);
        try { engine.block.setAlwaysOnTop(block, true); } catch (_) {}
        texts.set(text.id, block);
      }
      const width = frame.width * 0.9;
      const fontPx = Math.max(8, text.fontSize * frame.height);
      engine.block.replaceText(block, text.text || ' ');
      const typeface = typefaces.find((face) => face.name === text.fontFamily);
      if (typeface) {
        const font = pickFont(typeface, text.bold, text.italic);
        if (font) engine.block.setFont(block, font.uri, typeface);
      }
      engine.block.setTextFontSize(block, fontPx);
      engine.block.setTextColor(block, hexToColor(text.color));
      engine.block.setEnum(block, 'text/horizontalAlignment', text.align === 'left' ? 'Left' : text.align === 'right' ? 'Right' : 'Center');
      engine.block.setWidthMode(block, 'Absolute');
      engine.block.setWidth(block, width);
      engine.block.setHeightMode(block, 'Auto');
      engine.block.setPositionX(block, text.x * frame.width - width / 2);
      engine.block.setPositionY(block, Math.max(0, text.y * frame.height - fontPx * 0.65));
      engine.block.setBool(block, 'backgroundColor/enabled', !!text.background);
      if (text.background) {
        engine.block.setColor(block, 'backgroundColor/color', hexToColor(text.background, 0.85));
        engine.block.setFloat(block, 'backgroundColor/cornerRadius', fontPx * 0.25);
      }
      engine.block.setTimeOffset(block, text.start);
      engine.block.setDuration(block, text.duration);
    }
  }

  return {
    name: 'imgly',

    async init({ container }) {
      try {
        sdk = await import(config.moduleUrl);
      } catch (error) {
        throw new VideoEngineError('engine_load_failed', error);
      }
      if (typeof sdk.supportsVideo === 'function' && !sdk.supportsVideo()) throw new VideoEngineError('browser_unsupported');
      try {
        const options = { baseURL: config.baseURL, userId: config.userId || undefined };
        if (config.license) options.license = config.license;
        engine = await sdk.default.init(options);
      } catch (error) {
        throw new VideoEngineError(/licen[sc]e/i.test(String(error && error.message)) ? 'license_invalid' : 'engine_init_failed', error);
      }
      frame = { width: 1920, height: 1080 };
      engine.scene.create('DepthStack', { page: { size: { width: frame.width, height: frame.height }, color: { r: 0, g: 0, b: 0, a: 1 } } });
      try { engine.scene.setMode('Video'); } catch (_) {}
      page = engine.block.findByType('page')[0];
      track = engine.block.create('track');
      engine.block.appendChild(page, track);
      // A clean preview: no page title or edit decorations.
      try { engine.editor.setSettingBool('page/title/show', false); } catch (_) {}
      try { engine.editor.setSettingBool('page/dimOutOfPageAreas', false); } catch (_) {}
      const canvas = engine.element;
      canvas.style.display = 'block';
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.pointerEvents = 'none'; // the preview is not edited by hand
      container.appendChild(canvas);
      // Keep the whole frame in view whenever the preview area changes size.
      stage = container;
      resizeObserver = new ResizeObserver(() => fitCamera());
      resizeObserver.observe(container);
      const types = Array.isArray(sdk.TRANSITION_TYPES) ? sdk.TRANSITION_TYPES : [];
      engineTransitions = types.filter((type) => type !== 'none');
      typefaces = await loadTypefaces();
      try {
        canExport = typeof sdk.supportsVideoExport === 'function' ? await sdk.supportsVideoExport() : true;
        if (!canExport) exportReason = 'export_unsupported';
      } catch (error) {
        canExport = false;
        exportReason = 'export_unsupported';
      }
    },

    capabilities() {
      return {
        transitionKinds: engineTransitions.slice(),
        images: true,
        fonts: typefaces.map((face) => ({ id: face.name, label: face.name })),
        canExport,
        exportReason,
      };
    },

    async sync(project, layout) {
      if (!engine) return;
      const width = project.settings.width || 1920;
      const height = project.settings.height || 1080;
      if (width !== frame.width || height !== frame.height) {
        frame = { width, height };
        engine.block.setWidth(page, width);
        engine.block.setHeight(page, height);
      }
      await syncVideo(project, layout);
      await syncAudio(project);
      syncText(project);
      engine.block.setDuration(page, Math.max(0.1, layout.duration));
      if (engine.block.getPlaybackTime(page) > layout.duration) engine.block.setPlaybackTime(page, layout.duration);
      fitCamera();
    },

    play() { if (engine) engine.block.setPlaying(page, true); },
    pause() { if (engine) engine.block.setPlaying(page, false); },
    seek(time) { if (engine) engine.block.setPlaybackTime(page, time); },
    currentTime() { return engine ? engine.block.getPlaybackTime(page) : 0; },
    isPlaying() { return engine ? engine.block.isPlaying(page) : false; },

    async exportVideo(project, layout, { onProgress, signal } = {}) {
      if (!engine) throw new VideoEngineError('engine_not_ready');
      if (!canExport) throw new VideoEngineError(exportReason || 'export_unsupported');
      engine.block.setPlaying(page, false);
      const settings = project.exportSettings;
      try {
        return await engine.block.exportVideo(page, {
          mimeType: 'video/mp4',
          framerate: settings.fps || 30,
          targetWidth: settings.width || frame.width,
          targetHeight: settings.height || frame.height,
          // Bounded bitrate derived from resolution and frame rate: the
          // browser's own ('System') choice can exhaust memory on long edits.
          videoBitrate: 'Auto',
          timeOffset: 0,
          duration: layout.duration,
          abortSignal: signal,
          onProgress: (rendered, encoded, total) => { if (onProgress && total) onProgress(Math.min(1, encoded / total)); },
        });
      } catch (error) {
        if (signal && signal.aborted) throw new VideoEngineError('export_cancelled', error);
        throw new VideoEngineError('export_failed', error);
      }
    },

    destroy() {
      if (resizeObserver) resizeObserver.disconnect();
      if (engine) {
        try { engine.element && engine.element.remove(); } catch (_) {}
        engine.dispose();
      }
      engine = null;
      clips.clear();
      audios.clear();
      texts.clear();
      transitionBlocks.clear();
    },
  };
}
