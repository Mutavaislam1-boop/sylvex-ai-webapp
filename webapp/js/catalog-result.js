/* Shared catalog result view. Submission/polling stay in Pro Studio. */
(function () {
  'use strict';
  function safeUrl(value) {
    try { var u = new URL(value, window.location.href); return /^(https?:|blob:)$/.test(u.protocol) ? u.href : ''; } catch (_) { return ''; }
  }
  function mount(host, state, actions) {
    if (!host) return;
    var old = host.querySelector('.catalog-result-card');
    if (old && old.dataset.job === state.jobId && old.dataset.url === (state.url || '')) {
      old.classList.toggle('is-failed', state.status === 'failed');
      var text = old.querySelector('[role="status"]');
      if (text && !state.url) text.textContent = stageLabel(state);
      return;
    }
    host.replaceChildren();
    var card = document.createElement('span'); card.className = 'catalog-result-card';
    card.dataset.job = state.jobId || ''; card.dataset.url = state.url || '';
    var status = document.createElement('span'); status.setAttribute('role', 'status');
    status.textContent = state.url ? 'Preparing result…' : stageLabel(state);
    card.classList.toggle('is-failed', state.status === 'failed');
    card.appendChild(status); host.appendChild(card);
    if (!state.url || !safeUrl(state.url)) return;
    var media = document.createElement(state.kind === 'video' ? 'video' : 'img');
    media.src = safeUrl(state.url);
    if (state.kind === 'video') { media.controls = true; media.playsInline = true; media.preload = 'metadata'; }
    else media.alt = 'Generated image';
    media.addEventListener(state.kind === 'video' ? 'loadeddata' : 'load', function () {
      status.remove(); card.classList.add('is-ready');
    }, {once:true});
    media.addEventListener('error', function () { status.textContent = 'Result unavailable. Open history to retry viewing.'; });
    card.appendChild(media);
    var controls = document.createElement('span'); controls.className = 'catalog-result-actions';
    function button(label, icon, action, parent) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = icon; b.setAttribute('aria-label', label);
      b.addEventListener('click', function (event) { event.preventDefault(); event.stopPropagation(); action(); });
      (parent || controls).appendChild(b);
    }
    function view() {
      if (media.pause) media.pause();
      var screen = {x:window.scrollX,y:window.scrollY};
      var dialog = document.createElement('dialog'); dialog.className = 'catalog-result-viewer';
      var preview = media.cloneNode(true); if (state.kind === 'video') preview.controls = true;
      var bar = document.createElement('footer'); dialog.append(preview, bar);
      button('Close preview', '×', function () { dialog.close(); }, bar);
      button('Download', 'Download', actions.download, bar);
      button('Open in Pro Studio', 'Open in Pro Studio', function () { dialog.close(); actions.open(); }, bar);
      dialog.addEventListener('close', function () { if (preview.pause) preview.pause(); dialog.remove(); window.scrollTo({left:screen.x,top:screen.y,behavior:'instant'}); });
      document.body.appendChild(dialog); dialog.showModal();
      bar.querySelector('button').focus({preventScroll:true});
      window.scrollTo({left:screen.x,top:screen.y,behavior:'instant'});
    }
    button('Full screen preview', '↗', view);
    button('Download', '↓', actions.download);
    button('Open in Pro Studio', '→', actions.open);
    card.appendChild(controls);
  }
  function stageLabel(state) {
    if (state.status === 'failed') return 'Generation failed';
    if (state.status === 'unconfirmed') return 'Status not confirmed';
    var stages = state.progress && state.progress.stages || {};
    if (state.status === 'completed') return 'Preparing result…';
    if (stages.processing) return 'AI is processing…';
    if (stages.accepted) return 'Accepted by AI…';
    if (stages.sent) return 'Request sent…';
    return state.status === 'submitting' ? 'Submitting…' : 'Queued…';
  }
  window.SylvexCatalogResult = {mount:mount};
})();
