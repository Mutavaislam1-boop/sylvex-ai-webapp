/*
 * Reference panel for the SYLVEX home composers. Tapping into the prompt
 * opens "Motion repeat" (video templates) or "Photo from reference" (photo
 * references): the panel rises out of the composer up to the top of the
 * screen and covers the page without moving it; the composer itself stays
 * usable through a hole in the shade. A pick goes back to the app (onPick)
 * and the panel stays open; ×, the dimmed area or Esc closes it.
 *
 * Layouts: 'grid' - fixed columns with `rows` rows on screen, the rest
 * scrolls (the Mini App); 'masonry' - cards keep their natural proportions
 * and each goes into the shortest column, as on the Media page (the
 * website). Colours come from --ref-panel-bg / --ref-panel-ink, which each
 * app sets for its themes. The same file runs in the Mini App and on the
 * website.
 */
(function (global) {
  'use strict';
  if (global.SylvexRefPanel) return;
  var doc = global.document;
  var EASE = 'cubic-bezier(0.23, 1, 0.32, 1)';
  var OPEN_MS = 460, CLOSE_MS = 220, CARD_STAGGER = 35, CARD_ANIMATED = 18;
  var GAP = 8, EDGE = 8;
  var reduceMotion = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var CLOSE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  var CHECK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>';
  var state = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function columns() {
    var cols = state.opts.cols;
    var width = state.panel.clientWidth || state.anchor.getBoundingClientRect().width;
    return Math.max(1, typeof cols === 'function' ? cols(width) : (cols || 3));
  }

  function cardHtml(item) {
    var on = state.selected != null && String(item.id) === String(state.selected);
    // A known ratio holds the card's size until the picture loads.
    var ratio = Number(item.ratio) > 0 ? ' style="aspect-ratio:' + Number(item.ratio).toFixed(4) + '"' : '';
    return '<button type="button" class="ref-panel-card' + (on ? ' is-selected' : '') + '" data-ref-id="' + esc(item.id) + '" aria-pressed="' + on + '"'
      + (item.title ? ' aria-label="' + esc(item.title) + '"' : '') + '>'
      + '<span class="ref-panel-frame"' + ratio + '><img src="' + esc(item.image) + '" alt="" loading="lazy" decoding="async"></span>'
      + (state.kind === 'video' ? '<i class="ref-panel-play" aria-hidden="true"></i>' : '')
      + '<i class="ref-panel-check" aria-hidden="true">' + CHECK_ICON + '</i></button>';
  }

  // Masonry: a picture without a known ratio takes its own once loaded.
  function fit(card) {
    var frame = card.querySelector('.ref-panel-frame');
    var img = frame && frame.querySelector('img');
    if (!img || frame.style.aspectRatio) return;
    frame.style.aspectRatio = state.kind === 'video' ? '0.5625' : '0.8';
    var apply = function () { if (img.naturalWidth && img.naturalHeight) frame.style.aspectRatio = (img.naturalWidth / img.naturalHeight).toFixed(4); };
    if (img.complete && img.naturalWidth) apply(); else img.addEventListener('load', apply, { once: true });
  }

  function reveal(cards) {
    if (reduceMotion) return;
    cards.slice(0, CARD_ANIMATED).forEach(function (card, i) {
      card.animate([{ opacity: 0, translate: '0 18px' }, { opacity: 1, translate: '0 0' }],
        { duration: 420, delay: 120 + i * CARD_STAGGER, easing: 'cubic-bezier(0.165, 0.84, 0.44, 1)', fill: 'backwards' });
    });
  }

  function render(animate) {
    var grid = state.grid, items = state.items, opts = state.opts;
    state.panel.querySelector('.ref-panel-head h3').textContent = state.title;
    state.panel.setAttribute('aria-label', state.title);
    state.panel.classList.toggle('is-photo', state.kind !== 'video');
    grid.scrollTop = 0;
    if (!items) {
      grid.className = 'ref-panel-grid is-loading';
      grid.innerHTML = new Array(6).join('<span class="ref-panel-skeleton"></span>') + '<span class="ref-panel-skeleton"></span>';
      layoutRows();
      return;
    }
    if (!items.length) {
      grid.className = 'ref-panel-grid is-empty';
      grid.innerHTML = '<p class="ref-panel-empty">' + esc(opts.emptyText || '') + '</p>';
      return;
    }
    var cards;
    if (opts.layout === 'masonry') {
      var count = columns();
      grid.className = 'ref-panel-grid is-masonry';
      grid.dataset.columns = String(count);
      grid.innerHTML = new Array(count + 1).join('<div class="ref-panel-col"></div>');
      var cols = Array.prototype.slice.call(grid.children);
      var holder = doc.createElement('div');
      cards = items.map(function (item) {
        holder.innerHTML = cardHtml(item);
        var card = holder.firstChild;
        var shortest = cols.reduce(function (best, col) { return col.offsetHeight < best.offsetHeight ? col : best; }, cols[0]);
        shortest.appendChild(card);
        fit(card);
        return card;
      });
    } else {
      grid.className = 'ref-panel-grid is-grid';
      grid.style.setProperty('--ref-panel-cols', String(columns()));
      grid.innerHTML = items.map(cardHtml).join('');
      cards = Array.prototype.slice.call(grid.children);
      layoutRows();
    }
    if (animate) reveal(cards);
  }

  // Grid: `rows` rows fill the room above the composer; the rest scrolls.
  function layoutRows() {
    if (state.opts.layout === 'masonry' && state.items) return;
    var rows = state.opts.rows || 2;
    var room = state.grid.clientHeight - GAP * (rows - 1) - 10;
    state.grid.style.gridAutoRows = Math.max(60, Math.floor(room / rows)) + 'px';
  }

  // The panel spans the composer's width, from the top of the screen down to
  // the composer; the shade has a hole where the composer is.
  function place() {
    if (!state) return;
    var box = state.anchor.getBoundingClientRect();
    var view = global.visualViewport;
    var top = Math.max(EDGE, (view ? view.offsetTop : 0) + EDGE);
    var height = Math.max(0, box.top - EDGE - top);
    var style = state.panel.style;
    style.left = box.left + 'px';
    style.width = box.width + 'px';
    style.top = top + 'px';
    style.height = height + 'px';
    state.shade.style.clipPath = holePath(box, parseFloat(global.getComputedStyle(state.anchor).borderTopLeftRadius) || 0);
    if (state.opts.layout === 'masonry') {
      if (state.items && state.items.length && String(columns()) !== state.grid.dataset.columns) render(false);
    } else {
      layoutRows();
    }
  }

  // The whole screen minus the composer's rounded box.
  function holePath(box, radius) {
    var l = box.left, t = box.top, r = box.right, b = box.bottom;
    var k = Math.min(radius, box.width / 2, box.height / 2);
    var arc = 'A' + k + ' ' + k + ' 0 0 1 ';
    var d = 'M0 0H' + global.innerWidth + 'V' + global.innerHeight + 'H0Z'
      + 'M' + (l + k) + ' ' + t + 'H' + (r - k) + arc + r + ' ' + (t + k) + 'V' + (b - k) + arc + (r - k) + ' ' + b
      + 'H' + (l + k) + arc + l + ' ' + (b - k) + 'V' + (t + k) + arc + (l + k) + ' ' + t + 'Z';
    return "path(evenodd, '" + d + "')";
  }

  var placeFrame = 0;
  function schedulePlace() {
    if (placeFrame) return;
    placeFrame = global.requestAnimationFrame(function () { placeFrame = 0; place(); });
  }

  function onKey(event) {
    if (event.key === 'Escape' && state) { event.preventDefault(); close(); }
  }

  function onGridClick(event) {
    var card = event.target.closest && event.target.closest('.ref-panel-card');
    if (!card || !state) return;
    var id = card.getAttribute('data-ref-id');
    var item = (state.items || []).filter(function (entry) { return String(entry.id) === id; })[0];
    if (!item) return;
    select(id);
    if (typeof state.opts.onPick === 'function') state.opts.onPick(item);
  }

  function listen(on) {
    var method = on ? 'addEventListener' : 'removeEventListener';
    global[method]('resize', schedulePlace);
    global[method]('scroll', schedulePlace, true);
    doc[method]('keydown', onKey);
    if (global.visualViewport) {
      global.visualViewport[method]('resize', schedulePlace);
      global.visualViewport[method]('scroll', schedulePlace);
    }
  }

  // opts: anchor, title, kind ('video' | 'photo'), items ([{ id, image,
  // title, ratio }] or null while loading), selected, layout, cols (a number
  // or width => number), rows, closeLabel, emptyText, onPick(item), onClose().
  function open(opts) {
    if (!opts || !opts.anchor) return;
    if (state) { update(opts); return; }
    var shade = doc.createElement('div');
    shade.className = 'ref-panel-shade';
    var panel = doc.createElement('section');
    panel.className = 'ref-panel';
    panel.setAttribute('role', 'dialog');
    panel.innerHTML = '<header class="ref-panel-head"><h3></h3><button type="button" class="ref-panel-x" aria-label="' + esc(opts.closeLabel || 'Close') + '">' + CLOSE_ICON + '</button></header>'
      + '<div class="ref-panel-grid"></div>';
    state = {
      opts: opts, anchor: opts.anchor, shade: shade, panel: panel, grid: panel.querySelector('.ref-panel-grid'),
      title: opts.title || '', kind: opts.kind || 'video', items: opts.items || null, selected: opts.selected,
      observer: global.ResizeObserver ? new global.ResizeObserver(schedulePlace) : null,
    };
    shade.addEventListener('click', function () { close(); });
    panel.querySelector('.ref-panel-x').addEventListener('click', function () { close(); });
    state.grid.addEventListener('click', onGridClick);
    doc.body.appendChild(shade);
    doc.body.appendChild(panel);
    if (state.observer) state.observer.observe(state.anchor);
    listen(true);
    place();
    render(true);
    if (!reduceMotion) {
      panel.animate([{ clipPath: 'inset(100% 0 0 0 round 22px)', translate: '0 14px' }, { clipPath: 'inset(0 0 0 0 round 22px)', translate: '0 0' }],
        { duration: OPEN_MS, easing: EASE });
      shade.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300 });
    }
  }

  // New items, title or kind (the Video / Photo switch) while open.
  function update(opts) {
    if (!state || !opts) return;
    ['title', 'kind', 'items', 'selected'].forEach(function (key) { if (key in opts) state[key] = opts[key]; });
    ['cols', 'rows', 'layout', 'emptyText', 'onPick', 'onClose'].forEach(function (key) { if (key in opts) state.opts[key] = opts[key]; });
    render(true);
  }

  function select(id) {
    if (!state) return;
    state.selected = id;
    Array.prototype.forEach.call(state.grid.querySelectorAll('.ref-panel-card'), function (card) {
      var on = id != null && card.getAttribute('data-ref-id') === String(id);
      card.classList.toggle('is-selected', on);
      card.setAttribute('aria-pressed', String(on));
    });
  }

  function close() {
    if (!state) return;
    var closing = state;
    state = null;
    listen(false);
    if (closing.observer) closing.observer.disconnect();
    var remove = function () { closing.panel.remove(); closing.shade.remove(); };
    if (reduceMotion) remove();
    else {
      closing.shade.animate([{ opacity: 1 }, { opacity: 0 }], { duration: CLOSE_MS, fill: 'forwards' });
      closing.panel.animate([{ clipPath: 'inset(0 0 0 0 round 22px)', opacity: 1 }, { clipPath: 'inset(100% 0 0 0 round 22px)', opacity: 0.6 }],
        { duration: CLOSE_MS, easing: 'cubic-bezier(0.4, 0, 1, 1)', fill: 'forwards' }).finished.then(remove, remove);
    }
    if (typeof closing.opts.onClose === 'function') closing.opts.onClose();
  }

  global.SylvexRefPanel = {
    open: open, update: update, select: select, close: close,
    isOpen: function () { return !!state; },
  };
})(window);
