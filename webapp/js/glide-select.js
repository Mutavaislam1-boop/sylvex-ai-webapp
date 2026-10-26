/*
 * GlideSelect for SYLVEX: every list a button opens pops in from that
 * button (scale .95 -> 1, 180 ms) and a highlight pill glides between the
 * rows under the pointer or the keyboard (220 ms); the chosen row carries a
 * check. Two kinds of lists get it:
 *
 *   - the menus the apps already build (Pro Studio pickers, Grid and Edit
 *     menus, the Music / Dialogues workspaces) - listed in MENUS below; the
 *     menu keeps its rows and handlers, this only adds the pop, the pill and
 *     the look (glide-select.css);
 *   - native <select>s - the system dropdown is replaced by the same menu;
 *     the <select> keeps its value and fires input/change as before, so the
 *     code that reads it is untouched.
 *
 * The same file runs in the Mini App and on the website.
 */
(function (global) {
  'use strict';
  if (global.SylvexGlide) return;
  var doc = global.document;
  var POP_OUT = 120;
  var GAP = 6;

  // Menus the apps build: root = the element that is shown and hidden,
  // list = the element holding the rows, row = one choice.
  var MENUS = [
    { root: '#modelPop', list: '.image-model-sheet-list, .image-size-sheet-list', row: '.image-model-row, .image-size-row' },
    { root: '.studio-grid-download-menu', list: '.studio-grid-download-menu', row: 'button' },
    { root: '.history-item-menu > div', list: '.history-item-menu > div', row: 'button' },
    { root: '.edit-sketch-tool-strip', list: '.edit-sketch-tool-strip', row: 'button' },
    { root: '.edit-sketch-more > div', list: '.edit-sketch-more > div', row: 'button' },
    { root: '.voice-caret-menu', list: '.voice-caret-menu', row: '.voice-caret-menu-item' },
    { root: '.voice-caret-submenu', list: '.voice-caret-submenu', row: 'button' },
    { root: '.voice-select-menu', list: '.voice-select-menu', row: 'button' },
    { root: '.photo-picker-menu', list: '.photo-picker-menu', row: 'button' },
    { root: '.qt-model-sheet', list: '.qt-model-list', row: 'button' },
    { root: '.qt-item-menu', list: '.qt-item-menu', row: 'button' },
    { root: '.qv-model-menu', list: '.qv-model-menu', row: 'button' },
    { root: '.qv-speed-menu', list: '.qv-speed-menu', row: 'button' },
    { root: '.qv-emo-menu', list: '.qv-emo-menu', row: 'button' },
  ];
  var ROOTS = MENUS.map(function (m) { return m.root; }).join(',');
  var LISTS = MENUS.map(function (m) { return m.list; }).join(',');
  var SELECTED = '.sel, .active, .is-selected, .selected, [aria-selected="true"], [aria-checked="true"]';

  var reduced = function () {
    return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
  };
  var shown = function (el) {
    if (!el || !el.isConnected || el.hidden) return false;
    var cs = global.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // ---------- the trigger: the button the menu opened from ----------
  var lastTrigger = null;
  doc.addEventListener('pointerdown', function (event) {
    var button = event.target.closest && event.target.closest('button, [role="button"], select, .photo-picker-trigger');
    if (button && !button.closest(ROOTS) && !button.closest('.glide-select__menu')) lastTrigger = button;
  }, true);

  // Light or dark menu: by the text colour of the button it opened from,
  // so it matches the page around it whatever theme that page follows.
  function toneOf(el) {
    var m = el && global.getComputedStyle(el).color.match(/[\d.]+/g);
    if (!m) return 'dark';
    var lum = (0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]) / 255;
    return lum > 0.5 ? 'dark' : 'light';
  }

  // Where the menu grows from: the side and the edge nearest its button.
  function originFor(menu, trigger) {
    var m = menu.getBoundingClientRect();
    if (!trigger || !trigger.isConnected) return 'center top';
    var t = trigger.getBoundingClientRect();
    var y = m.top >= t.bottom - 4 ? 'top' : (m.bottom <= t.top + 4 ? 'bottom' : 'center');
    var x = Math.abs(m.left - t.left) < 24 ? 'left' : (Math.abs(m.right - t.right) < 24 ? 'right' : 'center');
    return x + ' ' + y;
  }

  // The pop: it grows from its button and fades in. `scale` is its own
  // property, so a menu centred with transform:translate keeps its place.
  function pop(menu, trigger) {
    if (reduced() || !menu.animate) return;
    menu.style.transformOrigin = originFor(menu, trigger);
    menu.animate([{ opacity: 0, scale: '0.95' }, { opacity: 1, scale: '1' }], { duration: 180, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' });
  }

  // ---------- the pill gliding between the rows ----------
  function menuOf(list) {
    for (var i = 0; i < MENUS.length; i += 1) if (list.matches(MENUS[i].list)) return MENUS[i];
    return null;
  }

  function rowsOf(list) {
    var menu = menuOf(list);
    if (!menu) return [];
    return Array.prototype.filter.call(list.querySelectorAll(menu.row), function (row) {
      return row.closest(LISTS) === list && !row.closest('.glide-pill');
    });
  }

  function prepare(list) {
    if (getComputedStyle(list).position === 'static') list.style.position = 'relative';
    list.setAttribute('data-glide-list', '');
    rowsOf(list).forEach(function (row) {
      if (!row.hasAttribute('data-glide-row')) row.setAttribute('data-glide-row', '');
    });
    var pill = list.querySelector(':scope > .glide-pill');
    if (!pill) {
      pill = doc.createElement('span');
      pill.className = 'glide-pill';
      pill.setAttribute('aria-hidden', 'true');
      list.insertBefore(pill, list.firstChild);
    }
    return pill;
  }

  // jump = no glide: the first row lit, or a keyboard step.
  function light(list, row, jump) {
    var pill = prepare(list);
    if (!row) { pill.style.opacity = '0'; list.removeAttribute('data-glide-live'); return; }
    var first = pill.style.opacity !== '1';
    pill.style.transitionDuration = (jump || first || reduced()) ? '0ms, 0ms, 0ms, 150ms' : '';
    pill.style.transform = 'translate(' + row.offsetLeft + 'px,' + row.offsetTop + 'px)';
    pill.style.width = row.offsetWidth + 'px';
    pill.style.height = row.offsetHeight + 'px';
    pill.style.opacity = '1';
    list.setAttribute('data-glide-live', '');
  }

  doc.addEventListener('pointerover', function (event) {
    var row = event.target.closest && event.target.closest('[data-glide-row]');
    if (!row) {
      var list = event.target.closest && event.target.closest(LISTS);
      if (list) prepare(list);
      return;
    }
    if (event.pointerType === 'touch') return;
    light(row.closest('[data-glide-list]'), row, false);
  });
  doc.addEventListener('pointerdown', function (event) {
    var row = event.target.closest && event.target.closest('[data-glide-row]');
    if (row && event.pointerType === 'touch') light(row.closest('[data-glide-list]'), row, true);
  }, true);
  doc.addEventListener('focusin', function (event) {
    var row = event.target.closest && event.target.closest('[data-glide-row]');
    if (row && row.matches(':focus-visible')) light(row.closest('[data-glide-list]'), row, false);
  });

  // ---------- watching the app menus open ----------
  var open = new Set();
  var scheduled = 0;
  function scan() {
    scheduled = 0;
    doc.querySelectorAll(ROOTS).forEach(function (root) {
      var visible = shown(root);
      if (visible && !open.has(root)) {
        open.add(root);
        if (lastTrigger) lastTrigger.setAttribute('data-glide-open', '');
        root.__glideTrigger = lastTrigger;
        root.setAttribute('data-glide-tone', toneOf(lastTrigger && lastTrigger.isConnected ? lastTrigger : root.parentElement));
        pop(root, lastTrigger);
      } else if (!visible && open.has(root)) {
        open.delete(root);
        if (root.__glideTrigger) root.__glideTrigger.removeAttribute('data-glide-open');
      }
      if (visible) {
        if (!root.hasAttribute('data-glide-menu')) root.setAttribute('data-glide-menu', '');
        var lists = root.matches(LISTS) ? [root] : Array.prototype.slice.call(root.querySelectorAll(LISTS));
        lists.forEach(prepare);
      }
    });
    open.forEach(function (root) { if (!root.isConnected) { open.delete(root); if (root.__glideTrigger) root.__glideTrigger.removeAttribute('data-glide-open'); } });
  }
  function schedule() { if (!scheduled) scheduled = global.requestAnimationFrame(scan); }

  // ---------- native <select>: the same menu instead of the system one ----------
  var CHECK = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  var current = null; // { select, menu, list, rows, active }
  var uid = 0;

  // Lists the menu does not fit (several rows shown at once) or opted out.
  function plain(select) {
    return select.multiple || select.size > 1 || !!select.closest('[data-glide="off"]');
  }
  function skip(select) { return plain(select) || select.disabled; }

  function close(mode) {
    if (!current) return;
    var state = current;
    current = null;
    state.select.removeAttribute('data-glide-open');
    state.select.setAttribute('aria-expanded', 'false');
    if (mode === 'instant' || reduced()) { state.menu.remove(); return; }
    state.menu.dataset.state = 'closed';
    global.setTimeout(function () { state.menu.remove(); }, POP_OUT + 20);
  }

  function pick(index) {
    if (!current) return;
    var select = current.select;
    var option = current.options[index];
    if (option && !option.disabled && select.selectedIndex !== option.index) {
      select.selectedIndex = option.index;
      select.dispatchEvent(new Event('input', { bubbles: true }));
      select.dispatchEvent(new Event('change', { bubbles: true }));
      select.setAttribute('data-glide-swap', '');
    }
    close('instant');
    try { select.focus({ preventScroll: true }); } catch (_) {}
  }

  function setActive(index, jump) {
    if (!current) return;
    current.active = index;
    var row = index === null ? null : current.rows[index];
    light(current.list, row, jump);
    if (row) {
      current.select.setAttribute('aria-activedescendant', row.id);
      var top = row.offsetTop, bottom = top + row.offsetHeight, list = current.list;
      if (top < list.scrollTop) list.scrollTop = top - 4;
      else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 4;
    }
  }

  function openSelect(select, viaKey) {
    if (current && current.select === select) { close('pop'); return; }
    close('instant');
    var cs = getComputedStyle(select);
    var rect = select.getBoundingClientRect();
    // The menu follows the select's text size (a zoomed Grid canvas
    // shrinks it on screen, so its rendered height counts too).
    var zoom = select.offsetHeight ? rect.height / select.offsetHeight : 1;
    var font = Math.max(11, Math.min(16, parseFloat(cs.fontSize) * zoom || 13));
    var rowH = Math.round(font * 2.3);
    var options = Array.prototype.filter.call(select.options, function (o) { return !o.hidden; });
    var id = 'glide-' + (uid += 1);
    var menu = doc.createElement('div');
    menu.className = 'glide-select__menu';
    menu.setAttribute('data-glide-tone', toneOf(select));
    menu.style.setProperty('--gs-font', font + 'px');
    menu.style.setProperty('--gs-row', rowH + 'px');
    menu.innerHTML = '<div class="glide-select__list" role="listbox" id="' + id + '" data-glide-list><span class="glide-pill" aria-hidden="true"></span></div>';
    var list = menu.firstChild;
    var rows = options.map(function (option, i) {
      var row = doc.createElement('div');
      row.className = 'glide-select__option';
      row.id = id + '-' + i;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', option.selected ? 'true' : 'false');
      if (option.disabled) row.setAttribute('aria-disabled', 'true');
      row.setAttribute('data-glide-row', '');
      row.dataset.index = String(i);
      var name = doc.createElement('span');
      name.className = 'glide-select__name';
      name.textContent = option.textContent;
      var check = doc.createElement('span');
      check.className = 'glide-select__check';
      check.innerHTML = CHECK;
      if (option.selected) check.setAttribute('data-on', '');
      row.appendChild(name);
      row.appendChild(check);
      list.appendChild(row);
      return row;
    });
    doc.body.appendChild(menu);
    // Width: at least the select's own; placed under it, or above when
    // there is no room below; kept inside the screen.
    var vw = global.innerWidth, vh = global.innerHeight;
    var width = Math.min(vw - 16, Math.max(rect.width, 176));
    menu.style.width = width + 'px';
    var below = vh - rect.bottom - GAP - 8, above = rect.top - GAP - 8;
    var natural = list.scrollHeight + 8;
    var side = natural <= below || below >= above ? 'bottom' : 'top';
    var room = side === 'bottom' ? below : above;
    menu.style.maxHeight = Math.max(rowH * 3 + 8, Math.min(natural, room, 360)) + 'px';
    var left = Math.min(Math.max(8, rect.left), vw - width - 8);
    menu.style.left = left + 'px';
    if (side === 'bottom') menu.style.top = (rect.bottom + GAP) + 'px';
    else menu.style.bottom = (vh - rect.top + GAP) + 'px';
    menu.dataset.side = side;
    menu.style.transformOrigin = (Math.abs(left - rect.left) < 2 ? 'left' : 'center') + ' ' + (side === 'bottom' ? 'top' : 'bottom');
    current = { select: select, menu: menu, list: list, rows: rows, options: options, active: null };
    select.setAttribute('data-glide-open', '');
    select.setAttribute('aria-expanded', 'true');
    select.setAttribute('aria-controls', id);
    var selected = options.findIndex(function (o) { return o.selected; });
    if (reduced()) menu.dataset.state = 'open';
    else { menu.dataset.state = 'closed'; void menu.offsetHeight; menu.dataset.state = 'open'; }
    setActive(selected >= 0 ? selected : (viaKey ? 0 : null), true);
    if (selected >= 0) {
      var row = rows[selected];
      list.scrollTop = Math.max(0, row.offsetTop - (list.clientHeight - row.offsetHeight) / 2);
    }
  }

  function typeahead(ch) {
    var n = current.options.length, from = current.active === null ? -1 : current.active, c = ch.toLowerCase();
    for (var k = 1; k <= n; k += 1) {
      var i = (from + k + n) % n;
      if (current.options[i].textContent.trim().toLowerCase().indexOf(c) === 0) return i;
    }
    return current.active;
  }

  function enabledStep(from, dir) {
    var n = current.options.length, i = from;
    for (var k = 0; k < n; k += 1) {
      i = Math.min(n - 1, Math.max(0, i + dir));
      if (!current.options[i].disabled) return i;
      if (i === 0 || i === n - 1) break;
    }
    return from;
  }

  function enhance(select) {
    if (select.__glide || plain(select)) return;
    select.__glide = true;
    select.setAttribute('data-glide-select', '');
    select.setAttribute('aria-haspopup', 'listbox');
    select.setAttribute('aria-expanded', 'false');
  }

  // A press on an enhanced select opens our menu, not the system one.
  var touchStart = null;
  doc.addEventListener('mousedown', function (event) {
    var select = event.target.closest && event.target.closest('select[data-glide-select]');
    if (!select || skip(select) || event.button !== 0) return;
    event.preventDefault();
    try { select.focus({ preventScroll: true }); } catch (_) {}
    openSelect(select, false);
  }, true);
  doc.addEventListener('touchstart', function (event) {
    var select = event.target.closest && event.target.closest('select[data-glide-select]');
    touchStart = select && event.touches[0] ? { select: select, x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
  }, { capture: true, passive: true });
  doc.addEventListener('touchend', function (event) {
    var start = touchStart;
    touchStart = null;
    if (!start || skip(start.select)) return;
    var t = event.changedTouches[0];
    if (t && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 10) return;
    event.preventDefault();
    openSelect(start.select, false);
  }, { capture: true, passive: false });

  doc.addEventListener('keydown', function (event) {
    var select = event.target.closest && event.target.closest('select[data-glide-select]');
    var k = event.key;
    if (select && (!current || current.select !== select)) {
      if (k === 'Enter' || k === ' ' || k === 'ArrowDown' || k === 'ArrowUp' || (k === 'F4')) {
        if (skip(select)) return;
        event.preventDefault();
        openSelect(select, true);
      }
      return;
    }
    if (!current || (select && current.select !== select)) return;
    var n = current.options.length, cur = current.active === null ? Math.max(0, current.select.selectedIndex) : current.active;
    if (k === 'ArrowDown' || k === 'ArrowUp') { event.preventDefault(); setActive(current.active === null ? cur : enabledStep(cur, k === 'ArrowDown' ? 1 : -1), true); }
    else if (k === 'Home' || k === 'End') { event.preventDefault(); setActive(k === 'Home' ? enabledStep(-1, 1) : enabledStep(n, -1), true); }
    else if (k === 'Enter' || k === ' ') { event.preventDefault(); pick(cur); }
    else if (k === 'Escape') { event.preventDefault(); event.stopPropagation(); close('instant'); }
    else if (k === 'Tab') close('instant');
    else if (k.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); setActive(typeahead(k), true); }
  }, true);

  // Rows of our own menu: hover lights, a click picks.
  doc.addEventListener('click', function (event) {
    if (!current) return;
    var row = event.target.closest && event.target.closest('.glide-select__option');
    if (row && current.menu.contains(row)) {
      if (row.getAttribute('aria-disabled') !== 'true') pick(Number(row.dataset.index));
      return;
    }
  });
  doc.addEventListener('pointerdown', function (event) {
    if (current && !current.menu.contains(event.target) && event.target !== current.select) close('pop');
  }, true);
  doc.addEventListener('pointerover', function (event) {
    var row = current && event.target.closest && event.target.closest('.glide-select__option');
    if (row && current.menu.contains(row) && event.pointerType !== 'touch') setActive(Number(row.dataset.index), false);
  });
  // A scroll or a resize outside the menu moves the select away from it.
  global.addEventListener('scroll', function (event) { if (current && !current.menu.contains(event.target)) close('instant'); }, true);
  global.addEventListener('resize', function () { close('instant'); });
  doc.addEventListener('animationend', function (event) {
    if (event.animationName === 'glide-swap') event.target.removeAttribute('data-glide-swap');
  });

  function enhanceAll(root) {
    (root || doc).querySelectorAll('select:not([data-glide-select])').forEach(enhance);
  }

  var observer = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i += 1) {
      var m = mutations[i];
      if (m.type === 'childList') {
        for (var j = 0; j < m.addedNodes.length; j += 1) {
          var node = m.addedNodes[j];
          if (node.nodeType !== 1) continue;
          if (node.tagName === 'SELECT') enhance(node);
          else if (node.querySelector && node.querySelector('select')) enhanceAll(node);
        }
      }
    }
    schedule();
  });

  function start() {
    enhanceAll(doc);
    observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'style', 'open'] });
    schedule();
  }
  if (doc.body) start(); else doc.addEventListener('DOMContentLoaded', start);

  global.SylvexGlide = { MENUS: MENUS, enhance: enhance, close: close };
})(window);
