// Entry point of the SYLVEX Video Editor (Quick Access → Video).
// Wires SYLVEX UI → SYLVEX actions/services → editor core → engine. The
// engine is picked by the server config and looked up by name, so another
// engine only needs to be registered here.
import { createVideoEditor } from './editor.js';
import { mountVideoEditorUI } from './ui.js';
import { createEditorActions } from './actions.js';
import { createServices, environment as detectEnvironment } from './services.js';
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

// Opens the editor inside `host`. `files` are added to a new project;
// `projectId` (+ `token` from an "Open in browser" link) reopens a saved one.
export async function openVideoEditor({ host, files = [], projectId = '', token = '', onClose } = {}) {
  const services = createServices();
  const env = detectEnvironment();
  let editor = null;
  let actions = null;
  let ui = null;
  const close = () => {
    if (actions) actions.destroy();
    if (ui) ui.destroy();
    if (editor) editor.destroy();
    host.innerHTML = '';
    if (onClose) onClose();
  };
  let config;
  try {
    config = await fetchConfig();
  } catch (error) {
    editor = createVideoEditor({ engine: nullEngine() });
    actions = createEditorActions({ editor, services });
    ui = mountVideoEditorUI(host, editor, { onClose: close, actions, services, environment: env });
    ui.setEngineError(error);
    return null;
  }
  const factory = engineFactory(config.engine);
  editor = createVideoEditor({ engine: factory ? factory(config) : nullEngine() });
  actions = createEditorActions({ editor, services, onState: (work) => { if (ui) ui.setWorkState(work); } });
  ui = mountVideoEditorUI(host, editor, { onClose: close, actions, services, environment: env });
  ui.focus();
  if (!factory) { ui.setEngineError({ code: 'engine_load_failed' }); return editor; }
  try {
    await editor.mount(ui.stage);
    ui.setEngineReady(editor.capabilities(), config.trial ? 'Видеодвижок в тестовом режиме' : '');
  } catch (error) {
    console.error('[video-editor] engine', error);
    ui.setEngineError(error);
    return editor;
  }
  if (projectId) {
    await ui.openProject(projectId, token);
  } else if (files.length) {
    await ui.addFiles(files);
  } else {
    // Without files the user picks a saved project or starts a new one.
    const saved = await services.listProjects().catch(() => []);
    if (saved.length) ui.showProjects();
  }
  return editor;
}

// Placeholder engine used while no real engine could be started: the UI
// still renders, nothing is drawn or exported.
function nullEngine() {
  return {
    name: 'none',
    async init() {},
    capabilities: () => ({ transitionKinds: [], fonts: [], images: false, canExport: false, exportReason: 'engine_load_failed' }),
    async sync() {},
    play() {}, pause() {}, seek() {},
    currentTime: () => 0,
    isPlaying: () => false,
    async exportVideo() { throw Object.assign(new Error('engine_load_failed'), { code: 'engine_load_failed' }); },
    destroy() {},
  };
}
