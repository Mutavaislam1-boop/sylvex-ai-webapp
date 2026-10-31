/* SYLVEX generation handoff: the short animation that carries a generation
   started outside Pro Studio (Home, the catalogs) into Pro Studio, once the
   server has accepted it - the person's materials → the generation → Pro
   Studio. It only animates; the generation itself is the one Pro Studio job
   already running, never a second request.

   One file for the website and both Mini Apps - keep it byte-identical in
   sylvex-website/js/generation-handoff.js and
   sylvex-ai-webapp/webapp/js/generation-handoff.js.

     SylvexHandoff.play({ images: [url, ...], video: url, kind: 'image'|'video', lang: 'ru'|'en' })
       -> Promise, resolved when the animation has finished
*/
(function (root) {
  'use strict';
  if (root.SylvexHandoff) return;

  var TEXT = {
    en: { materials: 'Your materials', generation: 'Generation started', studio: 'Pro Studio', studio_note: 'Opening your generation' },
    ru: { materials: 'Ваши материалы', generation: 'Генерация запущена', studio: 'Pro Studio', studio_note: 'Открываем генерацию' },
  };
  var DURATION = 2300;
  var REDUCED = 700;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function reducedMotion() {
    try { return !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (_) { return false; }
  }

  function materialsHtml(images, video) {
    var items = (images || []).filter(Boolean).slice(0, 3);
    var html = items.map(function (url, i) {
      return '<img class="sxho-thumb" style="--i:' + i + '" src="' + esc(url) + '" alt="">';
    }).join('');
    if (video) html = '<video class="sxho-thumb" style="--i:0" src="' + esc(video) + '" muted playsinline preload="metadata"></video>' + html;
    return html || '<span class="sxho-thumb sxho-thumb--empty" style="--i:0"></span>';
  }

  function play(options) {
    options = options || {};
    if (typeof document === 'undefined' || !document.body) return Promise.resolve();
    var t = TEXT[options.lang] || TEXT.en;
    var reduced = reducedMotion();
    var node = document.createElement('div');
    node.className = 'sxho' + (reduced ? ' is-reduced' : '');
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.innerHTML =
      '<div class="sxho-row">'
      + '<div class="sxho-step sxho-materials" style="--d:0"><div class="sxho-stack">' + materialsHtml(options.images, options.video) + '</div><span>' + esc(t.materials) + '</span></div>'
      + '<div class="sxho-arrow" style="--d:1" aria-hidden="true">→</div>'
      + '<div class="sxho-step sxho-generation" style="--d:2"><div class="sxho-window"><i></i><i></i><i></i><b class="sxho-spark"></b></div><span>' + esc(t.generation) + '</span></div>'
      + '<div class="sxho-arrow" style="--d:3" aria-hidden="true">→</div>'
      + '<div class="sxho-step sxho-studio" style="--d:4"><div class="sxho-window sxho-studio-window"><em>' + esc(t.studio) + '</em><i></i><i></i></div><span>' + esc(t.studio_note) + '</span></div>'
      + '</div>';
    document.body.appendChild(node);
    return new Promise(function (resolve) {
      setTimeout(function () {
        node.classList.add('is-leaving');
        setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); resolve(); }, reduced ? 0 : 220);
      }, reduced ? REDUCED : DURATION);
    });
  }

  root.SylvexHandoff = { play: play, DURATION: DURATION };
})(typeof window !== 'undefined' ? window : this);
