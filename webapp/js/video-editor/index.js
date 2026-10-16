// Entry point of the SYLVEX Video Editor (Quick Access → Video).
// Picks the rendering engine named by the server config and wires
// UI → editor core → engine. Engines are looked up by name, so another
// engine only needs to be registered here.
import { createVideoEditor } from './editor.js';
import { mountVideoEditorUI } from './ui.js';
import { createImglyEngine } from './engines/imgly.js';

const ENGINES = {
  imgly: (config) => createImglyEngine(config),
};

export function registerVideoEngine(name, factory) {
  ENGINES[name] = factory;
}

function engineFactory(name) {
  return ENGINES[name] || (globalThis.SylvexVideoEngines && globalThis.SylvexVideoEngines[name]) || null;
}

async function fetchConfig() {
  const response = await fetch('/api/public/video-editor/config', { cache: 'no-store' });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) throw Object.assign(new Error('login_required'), { code: 'login_required' });
  if (!response.ok || !data.ok) throw Object.assign(new Error('config_failed'), { code: 'config_failed' });
  return data;
}

// Opens the editor inside `host`. `files` (video) are loaded first.
export async function openVideoEditor({ host, files = [], onClose } = {}) {
  let editor = null;
  let ui = null;
  const close = () => {
    if (editor) editor.destroy();
    host.innerHTML = '';
    if (onClose) onClose();
  };
  let config;
  try {
    config = await fetchConfig();
  } catch (error) {
    const placeholder = createVideoEditor({ engine: nullEngine() });
    ui = mountVideoEditorUI(host, placeholder, { onClose: () => { placeholder.destroy(); host.innerHTML = ''; if (onClose) onClose(); } });
    ui.setEngineError(error);
    return null;
  }
  const factory = engineFactory(config.engine);
  editor = createVideoEditor({ engine: factory ? factory(config) : nullEngine() });
  ui = mountVideoEditorUI(host, editor, { onClose: close });
  ui.focus();
  if (!factory) { ui.setEngineError({ code: 'engine_load_failed' }); return editor; }
  try {
    await editor.mount(ui.stage);
    const caps = editor.capabilities();
    ui.setEngineReady(caps, config.trial ? 'Тестовый режим движка' : '');
  } catch (error) {
    console.error('[video-editor] engine', error);
    ui.setEngineError(error);
    return editor;
  }
  if (files.length) await ui.addFiles(files, 'video');
  return editor;
}

// Placeholder engine used while no real engine could be started: the UI
// still renders, nothing is drawn or exported.
function nullEngine() {
  return {
    name: 'none',
    async init() {},
    capabilities: () => ({ transitions: [], fonts: [], canExport: false, exportReason: 'engine_load_failed' }),
    async sync() {},
    play() {}, pause() {}, seek() {},
    currentTime: () => 0,
    isPlaying: () => false,
    async exportVideo() { throw Object.assign(new Error('engine_load_failed'), { code: 'engine_load_failed' }); },
    destroy() {},
  };
}
