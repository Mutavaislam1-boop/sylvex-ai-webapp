/*
 * Media page (media.html): the tools row, the moving featured row and the
 * media wall, all built from SYLVEX_MEDIA (js/media.js) over the existing
 * public catalogs. Video items play muted while they are on screen.
 */
(function () {
  'use strict';
  var MEDIA = window.SYLVEX_MEDIA;
  var BASE = (function () {
    var tag = document.querySelector('meta[name="sylvex-api-base"]');
    return (tag && tag.content) || '';
  })();
  // Videos playing at once: the wall and the featured row each have a budget.
  var MAX_PLAYING = { wall: 8, featured: 6 };
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var state = { items: [], featured: [] };
  var wallKind = 'all';

  var $ = function (id) { return document.getElementById(id); };
  var mediaPickerOpen = false;
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  // ---------- tools row: the existing photo and video tools ----------
  function renderTools() {
    var catalog = window.SYLVEX_CATALOG || {};
    var modes = catalog.homeModeTools || {};
    var tools = (modes.image || []).concat(modes.video || []);
    $('sxMediaTools').innerHTML = tools.map(function (tool) {
      return '<a class="sx-media-tool" href="' + esc(tool.href) + '" data-media-tool="' + esc(tool.key) + '">' +
        '<span class="sx-media-tool-art"><img src="' + esc(tool.image) + '" alt="" loading="lazy"></span>' +
        '<span class="sx-media-tool-name">' + esc(tool.title) + '</span>' +
      '</a>';
    }).join('');
  }

  // ---------- media markup ----------
  function mediaHtml(entry, options) {
    // A video without a poster has no size until it loads: use its ratio
    // (or a vertical clip's) so the wall does not jump.
    var r = entry.ratio || (entry.kind === 'video' && !entry.image ? 9 / 16 : 0);
    var style = r ? ' style="aspect-ratio:' + r.toFixed(4) + '"' : '';
    // The featured row moves sideways: its pictures load right away.
    var loading = options && options.eager ? 'eager' : 'lazy';
    if (entry.kind === 'video') {
      // The video source is attached only while the card is on screen.
      return '<span class="sx-media-frame"' + style + '>' +
        (entry.image ? '<img src="' + esc(entry.image) + '" alt="" loading="' + loading + '" decoding="async">' : '') +
        '<video muted loop playsinline preload="none" data-src="' + esc(entry.video) + '"' + (entry.image ? ' poster="' + esc(entry.image) + '"' : '') + (options && options.eager ? ' data-eager' : '') + '></video>' +
        '<i class="sx-media-play" aria-hidden="true"></i>' +
      '</span>';
    }
    return '<span class="sx-media-frame"' + style + '><img src="' + esc(entry.image) + '" alt="" loading="' + loading + '" decoding="async"></span>';
  }

  function cardHtml(entry) {
    return '<button type="button" class="sx-media-card is-' + entry.kind + '" data-media-id="' + esc(entry.id) + '">' +
      mediaHtml(entry) +
      (entry.title ? '<span class="sx-media-caption"><b>' + esc(entry.title) + '</b></span>' : '') +
    '</button>';
  }

  // ---------- featured row: slowly moving right to left ----------
  function renderFeatured() {
    var track = $('sxMediaMarqueeTrack');
    var list = state.featured;
    $('sxMediaFeaturedEmpty').hidden = list.length > 0;
    $('sxMediaMarquee').hidden = !list.length;
    if (!list.length) { track.innerHTML = ''; return; }
    // Two copies make the loop seamless (the track moves by half its width).
    var copies = list.length < 6 ? Math.ceil(6 / list.length) : 1;
    var row = [];
    for (var i = 0; i < copies; i += 1) row = row.concat(list);
    var html = row.map(function (entry) {
      return '<button type="button" class="sx-media-featured-card is-' + entry.kind + '" data-media-id="' + esc(entry.id) + '">' + mediaHtml(entry, { eager: true }) +
        (entry.title ? '<span class="sx-media-featured-title">' + esc(entry.title) + '</span>' : '') + '</button>';
    }).join('');
    track.innerHTML = html + html.replace(/<button /g, '<button aria-hidden="true" tabindex="-1" ');
    track.style.animationDuration = Math.max(40, row.length * 9) + 's';
    observeVideos(track);
  }

  // ---------- media wall: one catalog, every category mixed in turn ----------
  // Masonry: each card goes to the currently shortest column, so the
  // wall stays continuous; cards keep their natural proportions. The wall
  // is filled in batches as the visitor scrolls, so the page does not load
  // every catalog file at once.
  var BATCH = 36;
  var wallList = [];
  var shown = 0;

  function columnCount() {
    var width = $('sxMediaWall').clientWidth || window.innerWidth;
    return width >= 1150 ? 5 : width >= 900 ? 4 : width >= 600 ? 3 : 2;
  }

  function renderWall() {
    wallList = MEDIA.interleave(state.items.filter(function (item) { return wallKind === 'all' || item.kind === wallKind; }));
    var wall = $('sxMediaWall');
    wall.classList.remove('is-loading');
    var columns = '';
    for (var i = 0; i < columnCount(); i += 1) columns += '<div class="sx-media-col"></div>';
    wall.innerHTML = columns;
    wall.dataset.columns = String(columnCount());
    shown = 0;
    $('sxMediaWallEmpty').hidden = wallList.length > 0;
    appendBatch();
  }

  function appendBatch() {
    var wall = $('sxMediaWall');
    var columns = Array.prototype.slice.call(wall.querySelectorAll('.sx-media-col'));
    var holder = document.createElement('div');
    wallList.slice(shown, shown + BATCH).forEach(function (entry) {
      holder.innerHTML = cardHtml(entry);
      var card = holder.firstChild;
      var shortest = columns.reduce(function (best, column) { return column.offsetHeight < best.offsetHeight ? column : best; }, columns[0]);
      shortest.appendChild(card);
      fitImage(card);
      prepareReveal(card);
    });
    shown = Math.min(wallList.length, shown + BATCH);
    $('sxMediaMore').hidden = shown >= wallList.length;
    observeVideos(wall);
    // Re-arm: if the end of the wall is still near the screen, the observer
    // reports it again and the next batch follows.
    if (moreObserver && shown < wallList.length) {
      moreObserver.unobserve($('sxMediaMore'));
      moreObserver.observe($('sxMediaMore'));
    }
  }

  // Images without a known ratio hold a provisional one until they load,
  // then take their real proportions.
  function fitImage(card) {
    var frame = card.querySelector('.sx-media-frame');
    var img = frame && frame.querySelector('img');
    if (!img || frame.style.aspectRatio) return;
    frame.style.aspectRatio = '0.8';
    frame.classList.add('is-guess');
    var apply = function () {
      if (img.naturalWidth && img.naturalHeight) frame.style.aspectRatio = (img.naturalWidth / img.naturalHeight).toFixed(4);
      frame.classList.remove('is-guess');
    };
    if (img.complete && img.naturalWidth) apply(); else img.addEventListener('load', apply, { once: true });
  }

  // ---------- cards appear: up from below, out of a blur, one after another ----------
  // A card shows once it scrolls into view and its picture has loaded (or
  // 2.5 s later). Cards that come in together follow each other by 50 ms,
  // ride a spring (0.6 s, bounce 0.15) up from below while growing from
  // 0.96, and fade in out of a 12 px blur.
  var REVEAL = { stagger: 50, duration: 600, bounce: 0.15, blur: 12 };
  var revealQueue = new Set();
  var revealFrame = 0;

  // The spring's way from the start (1) to rest (0), sampled into keyframes;
  // the offset and the scale both follow it.
  var SPRING = (function () {
    var omega = Math.PI * 2 / (REVEAL.duration / 1000);
    var zeta = Math.min(1, Math.max(0.1, 1 - REVEAL.bounce));
    var dt = 1 / 240;
    var x = 1;
    var v = 0;
    var samples = [1];
    for (var t = 0; t < 3; t += dt) {
      v += (-omega * omega * x - 2 * zeta * omega * v) * dt;
      x += v * dt;
      samples.push(x);
      if (Math.abs(x) < 0.0004 && Math.abs(v) < 0.004) break;
    }
    samples[samples.length - 1] = 0;
    var step = Math.max(1, Math.round(samples.length / 48));
    var points = [];
    for (var i = 0; i < samples.length; i += step) points.push({ p: samples[i], offset: i / (samples.length - 1) });
    if (points[points.length - 1].offset !== 1) points.push({ p: 0, offset: 1 });
    return { points: points, ms: Math.round((samples.length - 1) * dt * 1000) };
  })();

  var revealObserver = !reduceMotion && 'IntersectionObserver' in window && Element.prototype.animate ? new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var card = entry.target;
      revealObserver.unobserve(card);
      card.dataset.seen = '1';
      if (card.dataset.loaded) queueReveal(card);
      else setTimeout(function () { queueReveal(card); }, 2500);
    });
  }, { rootMargin: '0px 0px -6% 0px' }) : null;

  function prepareReveal(card) {
    if (!revealObserver) return;
    card.classList.add('is-hidden');
    var img = card.querySelector('img');
    var loaded = function () {
      card.dataset.loaded = '1';
      if (card.dataset.seen) queueReveal(card);
    };
    if (!img || (img.complete && img.naturalWidth)) loaded();
    else { img.addEventListener('load', loaded, { once: true }); img.addEventListener('error', loaded, { once: true }); }
    revealObserver.observe(card);
  }

  function queueReveal(card) {
    if (!card.classList.contains('is-hidden')) return;
    revealQueue.add(card);
    if (!revealFrame) revealFrame = requestAnimationFrame(flushReveals);
  }

  function flushReveals() {
    revealFrame = 0;
    var batch = Array.from(revealQueue).filter(function (card) { return card.classList.contains('is-hidden') && document.contains(card); });
    revealQueue.clear();
    var boxes = new Map(batch.map(function (card) { return [card, card.getBoundingClientRect()]; }));
    batch.sort(function (a, b) { return boxes.get(a).top - boxes.get(b).top || boxes.get(a).left - boxes.get(b).left; });
    batch.forEach(function (card, rank) {
      var distance = 60 + Math.min(boxes.get(card).height, 280) * 0.35;
      var delay = rank * REVEAL.stagger;
      card.classList.remove('is-hidden');
      card.animate(SPRING.points.map(function (point) {
        return { offset: point.offset, transform: 'translate3d(0,' + (distance * point.p).toFixed(2) + 'px,0) scale(' + (1 - 0.04 * point.p).toFixed(4) + ')' };
      }), { duration: SPRING.ms, delay: delay, fill: 'backwards' });
      card.animate([
        { opacity: 0, filter: 'blur(' + REVEAL.blur + 'px)' },
        { opacity: 1, filter: 'blur(0px)' }
      ], { duration: REVEAL.duration, delay: delay, easing: 'cubic-bezier(0.33, 1, 0.68, 1)', fill: 'backwards' });
    });
  }

  var moreObserver = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    if (entries.some(function (entry) { return entry.isIntersecting; }) && shown < wallList.length) appendBatch();
  }, { rootMargin: '900px 0px' }) : null;

  var resizeTimer = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (wallList.length && String(columnCount()) !== $('sxMediaWall').dataset.columns) renderWall();
    }, 200);
  });

  function renderLoading() {
    var heights = [260, 180, 320, 220, 280, 200, 340, 240, 190, 300, 230, 270];
    var wall = $('sxMediaWall');
    var count = columnCount();
    var columns = [];
    for (var i = 0; i < count; i += 1) columns.push('');
    heights.forEach(function (h, i) { columns[i % count] += '<span class="sx-media-skeleton" style="height:' + h + 'px"></span>'; });
    wall.classList.add('is-loading');
    wall.innerHTML = columns.map(function (html) { return '<div class="sx-media-col">' + html + '</div>'; }).join('');
  }

  // ---------- videos play only while visible ----------
  var playing = new Set();
  var budget = function (video) { return video.closest('.sx-media-marquee') ? 'featured' : 'wall'; };
  var playingIn = function (kind) {
    var count = 0;
    playing.forEach(function (video) { if (budget(video) === kind) count += 1; });
    return count;
  };
  var observer = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var video = entry.target;
      if (entry.isIntersecting) start(video); else stop(video);
    });
  }, { rootMargin: '120px 0px', threshold: 0.35 }) : null;

  function start(video) {
    if (reduceMotion && !video.hasAttribute('data-playing-allowed')) return;
    if (!video.src) { video.src = video.dataset.src; }
    if (!playing.has(video) && playingIn(budget(video)) >= MAX_PLAYING[budget(video)]) return;
    var frame = video.closest('.sx-media-frame');
    playing.add(video);
    var promise = video.play();
    var shown = function () { if (playing.has(video)) frame.classList.add('is-playing'); };
    if (promise && promise.then) {
      promise.then(shown, function () { playing.delete(video); frame.classList.remove('is-playing'); });
    } else {
      shown();
    }
  }

  function stop(video) {
    if (!playing.has(video)) return;
    video.pause();
    playing.delete(video);
    var frame = video.closest('.sx-media-frame');
    if (frame) frame.classList.remove('is-playing');
  }

  function observeVideos(root) {
    playing.forEach(function (video) { if (!document.contains(video)) playing.delete(video); });
    if (!observer) return;
    root.querySelectorAll('video[data-src]').forEach(function (video) { observer.observe(video); });
  }

  // ---------- viewer ----------
  function find(id) {
    return state.items.concat(state.featured).filter(function (entry) { return entry.id === id; })[0];
  }

  function viewerMediaHtml(url, isVideo, poster, title) {
    return isVideo
      ? '<video src="' + esc(url) + '"' + (poster ? ' poster="' + esc(poster) + '"' : '') + ' controls autoplay muted loop playsinline></video>'
      : '<img src="' + esc(url) + '" alt="' + esc(title || '') + '">';
  }

  // Under the fitted reference: the same picture (a video's cover), blurred,
  // filling the side.
  function setBackdrop(url) {
    var media = $('sxMediaViewerMedia');
    if (url) media.style.setProperty('--catalog-backdrop', 'url("' + String(url).replace(/["\\]/g, '\\$&') + '")');
    else media.style.removeProperty('--catalog-backdrop');
  }

  var BLOCK_OPTIONS = {
    base: BASE, lang: 'en',
    onShop: function () { window.location.href = '/store.html'; },
    onLogin: function () { window.location.href = '/login.html?next=' + encodeURIComponent(window.location.pathname + window.location.search); },
  };
  function openBlock(block) {
    var bridge = window.SylvexStudioBridge;
    if (bridge && typeof bridge.openBlock === 'function') { bridge.openBlock(block); return; }
    if (window.SylvexMediaBlocks) window.SylvexMediaBlocks.open(block, BLOCK_OPTIONS);
  }

  function openViewer(entry) {
    resetMediaForAccount();
    // A Media block has its own window with the fields its admin set up, and
    // runs with its own model and prompt. The Mini App opens it its own way
    // (sign-in, store); the website with BLOCK_OPTIONS.
    if (entry.block) { openBlock(entry.block); return; }
    var dialog = $('sxMediaViewer');
    var cat = MEDIA.category(entry.category);
    current = entry;
    var result = makeOf(entry).result;
    $('sxMediaViewerMedia').innerHTML = result
      ? viewerMediaHtml(result, VIDEO_URL.test(result), '', entry.title)
      : viewerMediaHtml(entry.kind === 'video' ? entry.video : entry.image, entry.kind === 'video', entry.image, entry.title);
    setBackdrop(result && !VIDEO_URL.test(result) ? result : entry.image);
    $('sxMediaViewerTitle').textContent = entry.title || cat.label;
    $('sxMediaViewerText').textContent = entry.description || '';
    $('sxMediaViewerText').hidden = !entry.description;
    var tool = MEDIA.generationKind(entry) === 'tool';
    $('sxMediaViewerOpen').href = tool ? '/ai-tools.html?tool=' + encodeURIComponent(entry.sourceId) : '/pro-studio.html?mode=' + encodeURIComponent(cat.mode);
    $('sxMediaViewerOpen').textContent = tool ? 'Open tool' : 'Open in Pro Studio';
    renderMake();
    setStatus(result ? 'Done. The result is also saved to your Pro Studio history.' : '', '');
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
  }

  function closeViewer() {
    var dialog = $('sxMediaViewer');
    $('sxMediaViewerMedia').innerHTML = '';
    current = null;
    if (dialog.open && dialog.close) dialog.close(); else dialog.removeAttribute('open');
  }

  // ---------- make: the user's photo, the item's fields and Generate ----------
  // Each item keeps what the user gave it while the page is open. Uploads
  // and generation run in Pro Studio in a hidden frame (js/studio-bridge.js):
  // the item's own Pro Studio generation - the one its catalog block uses -
  // makes the result, which is saved to the Pro Studio history as usual and
  // shown here.
  var VIDEO_URL = /\.(mp4|webm|mov|m4v)(\?|#|$)/i;
  var current = null;
  var makes = {};
  var pendingSlot = '';
  var studio = { busy: '' }; // the item generating now
  var BRIDGE = window.SylvexStudioBridge;

  function makeOf(entry) {
    return makes[entry.id] || (makes[entry.id] = { photos: {}, fields: {}, result: '', ratio: RATIOS.some(function (r) { return r.id === entry.aspect; }) ? entry.aspect : '9:16' });
  }

  // A video item's formats, as its Pro Studio block offers them.
  var RATIOS = [{ id: '16:9', label: 'Wide' }, { id: '1:1', label: 'Square' }, { id: '9:16', label: 'Vertical' }];

  // The upload area of the catalog block, and smaller ones for an item's
  // extra pictures (a profile photo, a player cover).
  function slotHtml(key, label, photo, main) {
    var cls = main ? 'sx-media-upload' : 'sx-media-extra';
    if (photo) {
      return '<div class="' + cls + ' has-file' + (photo.url ? '' : ' is-uploading') + '">'
        + '<img src="' + esc(photo.preview) + '" alt="">'
        + (main ? '' : '<b>' + esc(label) + '</b>')
        + '<button type="button" class="sx-media-slot-x" data-media-remove="' + esc(key) + '" aria-label="Remove">×</button></div>';
    }
    return main
      ? '<button type="button" class="sx-media-upload" data-media-add="main"><span class="sx-media-upload-icon" aria-hidden="true">▧</span><b>Upload image</b><small>PNG, JPG or paste from clipboard</small></button>'
      : '<button type="button" class="sx-media-extra" data-media-add="' + esc(key) + '"><span aria-hidden="true">＋</span><b>' + esc(label) + '</b></button>';
  }

  function ratiosHtml(make, sourceFraming) {
    return '<div class="sx-media-ratios">' + RATIOS.map(function (ratio) {
      return '<button type="button" data-media-ratio="' + ratio.id + '"' + (sourceFraming ? ' disabled' : '') + ' class="' + (make.ratio === ratio.id ? 'active' : '') + '">'
        + '<span class="sx-media-ratio-icon" data-ratio="' + ratio.id + '"></span><span><b>' + ratio.id + '</b><small>' + ratio.label + '</small></span></button>';
    }).join('') + '</div>';
  }

  function renderMake() {
    var host = $('sxMediaMake');
    if (!current) return;
    if (MEDIA.generationKind(current) === 'tool') {
      host.hidden = true;
      host.innerHTML = '';
      renderActions();
      return;
    }
    var make = makeOf(current);
    var fields = MEDIA.styleFields(current);
    var images = fields.filter(function (field) { return field.type === 'image'; });
    var texts = fields.filter(function (field) { return field.type !== 'image'; });
    host.hidden = false;
    host.innerHTML = slotHtml('main', 'Upload image', make.photos.main, true)
      + (/^video_/.test(MEDIA.generationKind(current)) ? '<div class="sx-media-subjects"><button type="button" data-media-subject="character">Choose character</button><button type="button" data-media-subject="object">Choose object</button></div>' : '')
      + (images.length ? '<div class="sx-media-extras">' + images.map(function (field) { return slotHtml(field.key, field.label, make.photos[field.key], false); }).join('') + '</div>' : '')
      + (/^video_/.test(MEDIA.generationKind(current)) ? ratiosHtml(make, MEDIA.generationKind(current) === 'video_template') : '')
      + (/^video_/.test(MEDIA.generationKind(current)) && MEDIA.generationKind(current) !== 'video_effect' ? '<label class="sx-media-resolution">Resolution <select data-media-resolution><option value="720p"' + (make.resolution !== '1080p' ? ' selected' : '') + '>720p</option><option value="1080p"' + (make.resolution === '1080p' ? ' selected' : '') + '>1080p</option></select></label><small>Character replacement keeps the source video framing and full length.</small>' : '')
      + (texts.length ? '<div class="sx-media-fields">' + texts.map(function (field) {
        return '<label class="sx-media-field"><span>' + esc(field.label) + '</span>'
          + '<input type="text" data-media-field="' + esc(field.key) + '" value="' + esc(make.fields[field.key] || '') + '" placeholder="' + esc(field.label) + '"></label>';
      }).join('') + '</div>' : '');
    renderActions();
  }

  function renderActions() {
    var button = $('sxMediaGenerate');
    if (!current || MEDIA.generationKind(current) === 'tool') { button.hidden = true; return; }
    var main = makeOf(current).photos.main;
    var busy = studio.busy === current.id;
    button.hidden = false;
    button.disabled = !main || !main.url || !!studio.busy || Object.keys(makeOf(current).photos).some(function (key) { return !makeOf(current).photos[key].url; });
    button.textContent = busy ? 'Generating…' : 'Generate' + (current.cost > 0 ? ' ⚡ ' + current.cost : '');
    button.classList.toggle('is-busy', busy);
  }

  function setStatus(text, tone) {
    var status = $('sxMediaStatus');
    status.textContent = text || '';
    status.hidden = !text;
    status.className = 'sx-media-status' + (tone ? ' is-' + tone : '');
  }

  function addPhoto(key, file) {
    if (!current || !file || !/^image\//.test(file.type || '')) return;
    var entry = current;
    var make = makeOf(entry);
    var photo = { preview: URL.createObjectURL(file), url: '' };
    make.photos[key] = photo;
    renderMake();
    setStatus('', '');
    BRIDGE.upload(file).then(function (url) {
      if (make.photos[key] !== photo) return;
      photo.url = url;
      if (current === entry) renderMake();
    }, function (error) {
      if (make.photos[key] === photo) delete make.photos[key];
      if (current === entry) { renderMake(); setStatus((error && error.message) || 'The photo could not be uploaded. Please try again.', 'error'); }
    });
  }

  function makeRequest(entry) {
    var make = makeOf(entry);
    var extraUploads = {};
    Object.keys(make.photos).forEach(function (key) { if (key !== 'main' && make.photos[key].url) extraUploads[key] = make.photos[key].url; });
    var fields = {};
    Object.keys(make.fields).forEach(function (key) { if (String(make.fields[key] || '').trim()) fields[key] = String(make.fields[key]).trim(); });
    return {
      kind: MEDIA.generationKind(entry), itemId: entry.sourceId, title: entry.title,
      image: entry.image, video: entry.video, aspect: MEDIA.generationKind(entry) === 'video_template' ? entry.aspect : (make.ratio || entry.aspect), prompt: entry.prompt,
      upload: (make.photos.main && make.photos.main.url) || '', subjectKind:make.subjectKind || '', resolution:make.resolution || '720p', fields: fields, extraUploads: extraUploads,
    };
  }

  function generate() {
    if (!current || studio.busy) return;
    var request = makeRequest(current);
    if (!request.upload) return;
    studio.busy = current.id;
    makeOf(current).result = '';
    renderActions();
    setStatus(/^video_/.test(request.kind) ? 'Generating your video. This can take a few minutes.' : 'Generating your image…', '');
    BRIDGE.generate(request, {onJob:function (job) {
      request.jobId = job.jobId;
      transferToStudio(request);
    }}).then(finishGeneration, function (error) { failGeneration(error && error.message); });
  }

  function finishGeneration(url) {
    var id = studio.busy;
    studio.busy = '';
    if (makes[id]) makes[id].result = url;
    if (current && current.id === id) {
      $('sxMediaViewerMedia').innerHTML = viewerMediaHtml(url, VIDEO_URL.test(url), '', current.title);
      setBackdrop(VIDEO_URL.test(url) ? current.image : url);
      setStatus('Done. The result is also saved to your Pro Studio history.', 'success');
    }
    renderActions();
  }

  function failGeneration(message) {
    var id = studio.busy;
    studio.busy = '';
    if (current && current.id === id) setStatus(message || 'The generation did not go through. Please try again.', 'error');
    renderActions();
  }

  // Open in Pro Studio: the item's own block opens there with the photo and
  // the fields already in place.
  function openInStudio(event) {
    if (!current || MEDIA.generationKind(current) === 'tool') return;
    event.preventDefault();
    var request = makeRequest(current);
    var result = makeOf(current).result;
    if (result) { request.resultUrl = result; request.upload = ''; }
    transferToStudio(request);
  }

  function transferToStudio(request) {
    if (typeof BRIDGE.openStudio === 'function') { closeViewer(); BRIDGE.openStudio(request); return; }
    request.at = Date.now();
    try { sessionStorage.setItem('sx-media-handoff', JSON.stringify(request)); } catch (_) {}
    closeViewer();
    window.location.href = '/pro-studio.html?mode=' + (/^video_/.test(request.kind) ? 'video' : 'image') + '&from=media';
  }

  // The studio's error notices (a low balance, a refused photo) show under the block.
  BRIDGE.onNotice = function (text) { if (current) setStatus(text, 'error'); };

  var mediaAccountOwner = '';
  function resetMediaForAccount() {
    if (typeof BRIDGE.accountOwner !== 'function') return;
    var owner = BRIDGE.accountOwner();
    if (owner === mediaAccountOwner) return;
    mediaAccountOwner = owner;
    closeViewer(); makes = {}; studio.busy = '';
  }
  document.addEventListener('sylvex:user-ready', resetMediaForAccount);

  // ---------- events ----------
  document.addEventListener('click', function (event) {
    var filter = event.target.closest('[data-media-kind]');
    if (filter) {
      wallKind = ['all','video','image'].includes(filter.dataset.mediaKind) ? filter.dataset.mediaKind : 'all';
      document.querySelectorAll('[data-media-kind]').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.mediaKind === wallKind)); });
      renderWall(); return;
    }
    var subject = event.target.closest('[data-media-subject]');
    if (subject && current && !studio.busy) {
      var entry = current, kind = subject.dataset.mediaSubject;
      mediaPickerOpen = true;
      $('sxMediaViewer').close();
      BRIDGE.pick(kind).then(function (item) {
        if (!item && typeof BRIDGE.isGuest === 'function' && BRIDGE.isGuest()) { mediaPickerOpen = false; current = null; return; }
        if (item) { var make = makeOf(entry); make.photos.main = {url:item.url, preview:item.url}; make.subjectKind = kind; }
        current = entry; renderMake(); $('sxMediaViewer').showModal(); mediaPickerOpen = false;
      });
      return;
    }
    if (event.target.closest('#sxMediaMore')) { appendBatch(); return; }
    // A photo tool opens right here (js/tool-frame.js).
    var tool = event.target.closest('[data-media-tool]');
    if (tool && window.SylvexToolFrame && !event.metaKey && !event.ctrlKey && !event.shiftKey && event.button === 0
      && ((window.SYLVEX_CATALOG || {}).tools || []).some(function (item) { return item.key === tool.dataset.mediaTool; })) {
      event.preventDefault();
      window.SylvexToolFrame.open(tool.dataset.mediaTool);
      return;
    }
    if (event.target.closest('[data-media-close]')) { closeViewer(); return; }
    var add = event.target.closest('[data-media-add]');
    if (add) { pendingSlot = add.dataset.mediaAdd; BRIDGE.warm(); $('sxMediaFile').value = ''; $('sxMediaFile').click(); return; }
    var remove = event.target.closest('[data-media-remove]');
    if (remove && current) { delete makeOf(current).photos[remove.dataset.mediaRemove]; renderMake(); return; }
    if (event.target.closest('#sxMediaGenerate')) { generate(); return; }
    var ratio = event.target.closest('[data-media-ratio]');
    if (ratio && current) { makeOf(current).ratio = ratio.dataset.mediaRatio; renderMake(); return; }
    if (event.target.closest('#sxMediaViewerOpen')) { openInStudio(event); return; }
    var dialog = $('sxMediaViewer');
    if (event.target === dialog) { closeViewer(); return; }
    var card = event.target.closest('[data-media-id]');
    if (card) {
      var entry = find(card.dataset.mediaId);
      if (entry) openViewer(entry);
    }
  });
  $('sxMediaViewer').addEventListener('close', function () { if (mediaPickerOpen) return; $('sxMediaViewerMedia').innerHTML = ''; current = null; });
  // "PNG, JPG or paste from clipboard": a pasted picture is the photo.
  document.addEventListener('paste', function (event) {
    if (!current || MEDIA.generationKind(current) === 'tool' || !$('sxMediaViewer').open) return;
    var items = Array.prototype.slice.call((event.clipboardData && event.clipboardData.items) || []);
    var entry = items.filter(function (item) { return item.kind === 'file' && /^image\//.test(item.type); })[0];
    var file = entry && entry.getAsFile();
    if (!file) return;
    event.preventDefault();
    addPhoto('main', file);
  });
  $('sxMediaFile').addEventListener('change', function (event) {
    var file = event.target.files && event.target.files[0];
    if (file && pendingSlot) addPhoto(pendingSlot, file);
    pendingSlot = '';
  });
  $('sxMediaMake').addEventListener('input', function (event) {
    if (event.target.matches('[data-media-resolution]') && current) makeOf(current).resolution = event.target.value;
    var field = event.target.closest('[data-media-field]');
    if (field && current) makeOf(current).fields[field.dataset.mediaField] = field.value;
  });
  // Hover plays a video right away even when the visible-limit is reached.
  $('sxMediaWall').addEventListener('pointerover', function (event) {
    var video = event.target.closest('.sx-media-card') && event.target.closest('.sx-media-card').querySelector('video');
    if (video) { video.setAttribute('data-playing-allowed', ''); start(video); }
  });

  renderTools();
  renderLoading();
  if (moreObserver) moreObserver.observe($('sxMediaMore'));
  MEDIA.load(BASE).then(function (result) {
    state.items = result.items;
    state.featured = result.featured;
    renderFeatured();
    renderWall();
  });
})();
