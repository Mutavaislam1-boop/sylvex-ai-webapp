/*
 * SYLVEX Media blocks — the user side of the Admin Console's Media
 * constructor (services/media_blocks.py). One file for the website and both
 * Mini Apps (browser and Telegram): the apps list blocks in their own
 * catalogs (a catalog item carries `media_block`) and this module opens one,
 * shows the upload fields the admin configured, runs it and shows the
 * result. The generation is an ordinary Pro Studio one on the server: same
 * price from the tariff, balance check, job and history.
 *
 *   SylvexMediaBlocks.open(block, options)      opens the block's window
 *   SylvexMediaBlocks.of(item)                  the block of a catalog item, or null
 *   SylvexMediaBlocks.list(placement, options)  -> Promise of published blocks
 *   SylvexMediaBlocks.renderTiles(host, blocks, options)
 *
 * options: base (API origin, '' = same origin), lang ('ru' | 'en'),
 * onLogin(), onShop(), onResult(url, block).
 * The Mini Apps add their auth to /api/ requests themselves (js/api-auth.js);
 * the website sends its session cookie (credentials: 'include').
 */
(function (global) {
  'use strict';
  if (global.SylvexMediaBlocks) return;

  var TEXT = {
    en: {
      generate: 'Generate', generating: 'Generating…', upload: 'Upload', photo: 'Photo', video: 'Video', required: 'required',
      uploading: 'Uploading…', replace: 'Replace', close: 'Close', done: 'Done. The result is also saved to your Pro Studio history.',
      waitImage: 'Creating your image…', waitVideo: 'Creating your video. This can take a few minutes.',
      failed: 'The generation did not go through. Please try again.', uploadFailed: 'The file could not be uploaded. Please try again.',
      missing: 'Add the files marked as required.', balance: 'Not enough credits for this generation.', topUp: 'Top up',
      signIn: 'Sign in to upload files and generate.', signInAction: 'Sign in', subscription: 'Generation is available with a subscription.', plans: 'See plans', unavailable: 'This block is not available any more.', wrongType: 'This field takes a {kind}.',
      download: 'Open result', again: 'Generate again', modelOff: 'This block is temporarily unavailable: its AI model is turned off.',
      blockPaused: 'This block is temporarily unavailable: its AI model cannot generate right now.',
      modelUnavailable: 'This block is temporarily unavailable: its AI model cannot generate right now. Nothing was charged.',
    },
    ru: {
      generate: 'Сгенерировать', generating: 'Генерация…', upload: 'Загрузить', photo: 'Фото', video: 'Видео', required: 'обязательно',
      uploading: 'Загрузка…', replace: 'Заменить', close: 'Закрыть', done: 'Готово. Результат также сохранён в истории Pro Studio.',
      waitImage: 'Создаём изображение…', waitVideo: 'Создаём видео. Это может занять несколько минут.',
      failed: 'Генерация не прошла. Попробуйте ещё раз.', uploadFailed: 'Не удалось загрузить файл. Попробуйте ещё раз.',
      missing: 'Добавьте обязательные файлы.', balance: 'Недостаточно токенов для генерации.', topUp: 'Пополнить',
      signIn: 'Войдите, чтобы загружать файлы и генерировать.', signInAction: 'Войти', subscription: 'Генерация доступна с подпиской.', plans: 'Тарифы', unavailable: 'Этот блок больше недоступен.', wrongType: 'В это поле нужно {kind}.',
      download: 'Открыть результат', again: 'Сгенерировать ещё', modelOff: 'Блок временно недоступен: его AI-модель отключена.',
      blockPaused: 'Блок временно недоступен: его AI-модель сейчас не может генерировать.',
      modelUnavailable: 'Блок временно недоступен: его AI-модель сейчас не может генерировать. Токены не списаны.',
    },
  };
  var VIDEO_URL = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;
  var state = null; // the open block window

  function langOf(options) {
    var lang = (options && options.lang) || (document.documentElement.lang || '').slice(0, 2);
    return lang === 'ru' ? 'ru' : 'en';
  }
  function say(key, vars) {
    var text = (TEXT[state ? state.lang : 'en'] || TEXT.en)[key] || TEXT.en[key] || key;
    Object.keys(vars || {}).forEach(function (k) { text = text.replace('{' + k + '}', vars[k]); });
    return text;
  }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function absolute(base, url) {
    var value = String(url || '');
    if (!value || /^(https?:|data:|blob:)/i.test(value) || value.charAt(0) !== '/') return value;
    return String(base || '').replace(/\/$/, '') + value;
  }
  // A refused identity (a guest, an expired session) asks to sign in.
  function needsSignIn(r) {
    var code = String((r.body && (r.body.error || r.body.detail)) || '');
    return r.status === 401 || /^(authentication_required|invalid_init_data|auth_required|login_required)$/.test(code);
  }
  // Server texts meant for people pass through; codes become our wording.
  function humanError(body, fallback) {
    var text = body && (body.message || body.error);
    return typeof text === 'string' && text && !/^[a-z0-9_]+$/.test(text) ? text : fallback;
  }

  function request(options, path, init) {
    return fetch(String(options.base || '').replace(/\/$/, '') + path, Object.assign({ credentials: 'include', cache: 'no-store' }, init || {}))
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (body) { return { status: response.status, ok: response.ok, body: body }; });
      });
  }

  function of(item) {
    return item && item.media_block && item.media_block.id ? item.media_block : null;
  }

  function list(placement, options) {
    return request(options || {}, '/api/public/media-blocks' + (placement ? '?placement=' + encodeURIComponent(placement) : ''))
      .then(function (r) { return (r.body && r.body.items) || []; }, function () { return []; });
  }

  function costHtml(block) {
    return block.cost ? ' · ⚡ ' + esc(block.cost) : '';
  }

  function renderTiles(host, blocks, options) {
    if (!host) return;
    var opts = options || {};
    host.innerHTML = (blocks || []).map(function (block) {
      return '<button type="button" class="sxmb-tile" data-sxmb-open="' + esc(block.id) + '">'
        + '<span class="sxmb-tile-media">' + (block.preview_url ? '<img src="' + esc(absolute(opts.base, block.preview_url)) + '" alt="" loading="lazy">' : '') + '</span>'
        + '<span class="sxmb-tile-name">' + esc(block.name) + '</span>'
        + (block.description ? '<span class="sxmb-tile-desc">' + esc(block.description) + '</span>' : '')
        + '</button>';
    }).join('');
    host.hidden = !(blocks || []).length;
    host.onclick = function (event) {
      var tile = event.target.closest('[data-sxmb-open]');
      if (!tile) return;
      var block = (blocks || []).filter(function (b) { return String(b.id) === tile.dataset.sxmbOpen; })[0];
      if (block) open(block, opts);
    };
  }

  // ---------- the block window ----------
  function root() {
    var node = document.getElementById('sxmbWindow');
    if (node) return node;
    node = document.createElement('div');
    node.id = 'sxmbWindow';
    node.className = 'sxmb-layer';
    node.hidden = true;
    node.innerHTML = '<div class="sxmb-sheet" role="dialog" aria-modal="true" aria-labelledby="sxmbTitle">'
      + '<button type="button" class="sxmb-close" data-sxmb-close aria-label="Close">×</button>'
      + '<div class="sxmb-media" id="sxmbMedia"></div>'
      + '<div class="sxmb-body"><h3 id="sxmbTitle"></h3><p id="sxmbText"></p>'
      + '<div class="sxmb-fields" id="sxmbFields"></div>'
      + '<div class="sxmb-status" id="sxmbStatus" hidden></div>'
      + '<button type="button" class="sxmb-go" id="sxmbGo"></button></div></div>'
      + '<input type="file" id="sxmbFile" hidden>';
    document.body.appendChild(node);
    node.addEventListener('click', onClick);
    node.querySelector('#sxmbFile').addEventListener('change', function (event) {
      var file = event.target.files && event.target.files[0];
      if (file && state && state.pending) addFile(state.pending, file);
      if (state) state.pending = '';
      event.target.value = '';
    });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && state) close(); });
    return node;
  }

  function open(block, options) {
    if (!block) return;
    var opts = options || {};
    state = { block: block, options: opts, lang: langOf(opts), files: {}, busy: false, result: '', pending: '' };
    var node = root();
    node.querySelector('.sxmb-close').setAttribute('aria-label', say('close'));
    node.querySelector('#sxmbTitle').textContent = block.name || '';
    node.querySelector('#sxmbText').textContent = block.description || '';
    node.querySelector('#sxmbText').hidden = !block.description;
    renderMedia();
    renderFields();
    setStatus(block.available === false ? say('blockPaused') : '', block.available === false ? 'error' : '');
    node.hidden = false;
    document.documentElement.classList.add('sxmb-open');
  }

  function close() {
    var node = document.getElementById('sxmbWindow');
    if (node) { node.hidden = true; node.querySelector('#sxmbMedia').innerHTML = ''; }
    document.documentElement.classList.remove('sxmb-open');
    state = null;
  }

  function renderMedia() {
    var block = state.block;
    var base = state.options.base;
    var url = state.result || (block.block_type === 'video' && block.source_url) || block.preview_url;
    var isVideo = VIDEO_URL.test(String(url || '').split('?')[0]) || (!state.result && block.block_type === 'video' && !!block.source_url);
    document.getElementById('sxmbMedia').innerHTML = !url ? ''
      : isVideo ? '<video src="' + esc(absolute(base, url)) + '"' + (block.preview_url && !state.result ? ' poster="' + esc(absolute(base, block.preview_url)) + '"' : '')
        + ' autoplay muted loop playsinline' + (state.result ? ' controls' : '') + '></video>'
        : '<img src="' + esc(absolute(base, url)) + '" alt="">';
  }

  function renderFields() {
    var host = document.getElementById('sxmbFields');
    host.innerHTML = (state.block.fields || []).map(function (field) {
      var file = state.files[field.key];
      var kind = field.accept === 'video' ? say('video') : say('photo');
      var thumb = file ? (field.accept === 'video' ? '<video src="' + esc(file.preview) + '" muted playsinline></video>' : '<img src="' + esc(file.preview) + '" alt="">') : '<span class="sxmb-plus">+</span>';
      return '<button type="button" class="sxmb-field' + (file ? ' has-file' : '') + (file && !file.url ? ' is-uploading' : '') + '" data-sxmb-field="' + esc(field.key) + '">'
        + '<span class="sxmb-thumb">' + thumb + '</span>'
        + '<span class="sxmb-label"><b>' + esc(field.label || kind) + (field.required ? ' <i>*</i>' : '') + '</b>'
        + '<small>' + esc(file && !file.url ? say('uploading') : field.purpose || kind) + '</small></span>'
        + '<span class="sxmb-action">' + esc(file ? say('replace') : say('upload')) + '</span></button>';
    }).join('');
    renderGo();
  }

  function ready() {
    return (state.block.fields || []).every(function (field) {
      var file = state.files[field.key];
      return file ? !!file.url : !field.required;
    });
  }

  function renderGo() {
    var button = document.getElementById('sxmbGo');
    button.disabled = state.busy || !ready() || state.block.available === false;
    button.classList.toggle('is-busy', state.busy);
    button.innerHTML = state.busy ? esc(say('generating')) : esc(state.result ? say('again') : say('generate')) + costHtml(state.block);
  }

  function setStatus(text, tone, action) {
    var node = document.getElementById('sxmbStatus');
    node.hidden = !text;
    node.className = 'sxmb-status' + (tone ? ' is-' + tone : '');
    node.innerHTML = esc(text) + (action ? ' <button type="button" class="sxmb-link" data-sxmb-action="' + action.id + '">' + esc(action.label) + '</button>' : '');
  }

  function addFile(key, file) {
    var field = (state.block.fields || []).filter(function (f) { return f.key === key; })[0];
    if (!field) return;
    var kind = field.accept === 'video' ? 'video' : 'image';
    if (!new RegExp('^' + kind + '/').test(file.type || '')) {
      setStatus(say('wrongType', { kind: kind === 'video' ? say('video').toLowerCase() : say('photo').toLowerCase() }), 'error');
      return;
    }
    var current = state;
    var entry = { preview: URL.createObjectURL(file), url: '' };
    current.files[key] = entry;
    renderFields();
    setStatus('', '');
    var form = new FormData();
    form.append('file', file, file.name || (kind === 'video' ? 'upload.mp4' : 'upload.png'));
    request(current.options, '/api/public/prostudio/upload-media?kind=' + kind, { method: 'POST', body: form }).then(function (r) {
      if (current.files[key] !== entry) return;
      if (r.ok && r.body && r.body.url) entry.url = r.body.url;
      else {
        delete current.files[key];
        if (state === current) {
          if (needsSignIn(r)) setStatus(say('signIn'), 'error', { id: 'login', label: say('signInAction') });
          else setStatus(humanError(r.body, say('uploadFailed')), 'error');
        }
      }
      if (state === current) renderFields();
    }, function () {
      if (current.files[key] === entry) delete current.files[key];
      if (state === current) { renderFields(); setStatus(say('uploadFailed'), 'error'); }
    });
  }

  function resultUrl(result) {
    var r = result || {};
    var images = r.images || r.image_urls || [];
    var first = images[0] && (images[0].url || images[0]);
    return r.video_url || first || r.image_url || r.url || '';
  }

  function wait(current, jobId) {
    return request(current.options, '/api/public/prostudio/job/' + encodeURIComponent(jobId)).then(function (r) {
      if (state !== current) return null;
      var job = r.body || {};
      var status = String(job.status || '').toLowerCase();
      if (status === 'completed') return resultUrl(job.result);
      if (['failed', 'cancelled', 'canceled', 'timeout', 'timed_out'].indexOf(status) >= 0) {
        throw new Error((job.error && (job.error.message || job.error.error)) || say('failed'));
      }
      return new Promise(function (resolve) { setTimeout(resolve, 2000); }).then(function () { return wait(current, jobId); });
    });
  }

  function generate() {
    if (!state || state.busy || !ready()) return;
    var current = state;
    var uploads = {};
    Object.keys(current.files).forEach(function (key) { if (current.files[key].url) uploads[key] = current.files[key].url; });
    current.busy = true;
    renderGo();
    setStatus(current.block.generation === 'video' ? say('waitVideo') : say('waitImage'), '');
    request(current.options, '/api/public/media-blocks/' + encodeURIComponent(current.block.id) + '/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uploads: uploads }),
    }).then(function (r) {
      var body = r.body || {};
      if (needsSignIn(r)) {
        var login = new Error(say('signIn')); login.action = 'login'; throw login;
      }
      if (body.subscription_required) {
        var plan = new Error(say('subscription')); plan.action = 'plans'; throw plan;
      }
      if (r.status === 402 || body.insufficient_balance) {
        var shop = new Error(say('balance')); shop.action = 'shop'; throw shop;
      }
      if (r.status === 404) throw new Error(say('unavailable'));
      if (body.error === 'model_disabled') throw new Error(say('modelOff'));
      if (body.error === 'model_unavailable') throw new Error(say('modelUnavailable'));
      if (body.error === 'upload_required') throw new Error(say('missing'));
      if (!r.ok || !body.job_id) throw new Error(humanError(body, say('failed')));
      return wait(current, body.job_id);
    }).then(function (url) {
      if (state !== current || url == null) return;
      current.busy = false;
      current.result = url;
      renderMedia();
      renderGo();
      setStatus(say('done'), 'success');
      if (typeof current.options.onResult === 'function') current.options.onResult(url, current.block);
    }, function (error) {
      if (state !== current) return;
      current.busy = false;
      renderGo();
      var action = error.action === 'shop' ? { id: 'shop', label: say('topUp') }
        : error.action === 'plans' ? { id: 'shop', label: say('plans') }
          : error.action === 'login' ? { id: 'login', label: say('signInAction') } : null;
      setStatus((error && error.message) || say('failed'), 'error', action);
    });
  }

  function onClick(event) {
    if (!state) return;
    if (event.target === event.currentTarget || event.target.closest('[data-sxmb-close]')) { close(); return; }
    var field = event.target.closest('[data-sxmb-field]');
    if (field && !state.busy) {
      var def = (state.block.fields || []).filter(function (f) { return f.key === field.dataset.sxmbField; })[0];
      var input = document.getElementById('sxmbFile');
      input.accept = def && def.accept === 'video' ? 'video/*' : 'image/*';
      state.pending = field.dataset.sxmbField;
      input.click();
      return;
    }
    if (event.target.closest('#sxmbGo')) { generate(); return; }
    var action = event.target.closest('[data-sxmb-action]');
    var handler = action && { shop: 'onShop', login: 'onLogin' }[action.dataset.sxmbAction];
    if (handler && typeof state.options[handler] === 'function') { var opts = state.options; close(); opts[handler](); }
  }

  global.SylvexMediaBlocks = { open: open, close: close, of: of, list: list, renderTiles: renderTiles, _resultUrl: resultUrl };
})(typeof window !== 'undefined' ? window : globalThis);
