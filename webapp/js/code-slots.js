/*
 * Code slots: the one-time code entry. Each digit lands in its slot (the
 * slot fills from the centre, the digit rises in on a spring, the caret
 * glides to the next slot); a wrong code tints the row red and drains it
 * back to the first slot; an accepted code washes the row in the accent
 * colour, the digits sink and a tick rises. The same file runs in the Mini
 * App and on the website.
 *
 *   var slots = SylvexCodeSlots.mount(host, { length, onComplete(code), onChange(code), ariaLabel, autoFocus })
 *   slots.setStatus('idle' | 'error' | 'success') · slots.clear() · slots.focus() · slots.value() · slots.destroy()
 */
(function (global) {
  'use strict';
  if (global.SylvexCodeSlots) return;
  var doc = global.document;
  var EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)';
  var SETTLE = 0.3, BOUNCE = 0.2, RISE = 8, CASCADE = 20;
  var WASH_IN = 300, WASH_OUT = 200, SINK_DELAY = 60, SINK_STEP = 30, CHECK_DELAY = 280, CHECK_RISE = 8, SINK_FADE = 0.6;
  var TICK = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 14l3.5 3.5L19 6.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var clamp01 = function (v) { return Math.min(1, Math.max(0, v)); };
  var reduce = function () { return !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches); };

  // A value that moves by a spring (duration + bounce, like motion's) or by
  // an eased tween, calling onUpdate on every frame.
  function Value(initial, onUpdate) {
    this.v = initial; this.vel = 0; this.raf = 0; this.timer = 0; this.onUpdate = onUpdate;
  }
  Value.prototype.stop = function () { cancelAnimationFrame(this.raf); clearTimeout(this.timer); this.raf = 0; };
  Value.prototype.jump = function (to) { this.stop(); this.v = to; this.vel = 0; this.onUpdate(to); };
  Value.prototype.spring = function (to, duration, bounce, delayMs) {
    var self = this;
    this.stop();
    if (reduce()) { this.jump(to); return; }
    var omega = (2 * Math.PI) / Math.max(0.05, duration);
    var zeta = Math.max(0.05, 1 - bounce);
    var run = function () {
      var last = performance.now();
      var step = function (now) {
        var dt = Math.min(0.064, (now - last) / 1000);
        last = now;
        for (var i = 0; i < 4; i += 1) {
          var h = dt / 4;
          var accel = -omega * omega * (self.v - to) - 2 * zeta * omega * self.vel;
          self.vel += accel * h;
          self.v += self.vel * h;
        }
        if (Math.abs(self.v - to) < 0.0005 && Math.abs(self.vel) < 0.005) { self.v = to; self.vel = 0; self.onUpdate(to); self.raf = 0; return; }
        self.onUpdate(self.v);
        self.raf = requestAnimationFrame(step);
      };
      self.raf = requestAnimationFrame(step);
    };
    if (delayMs > 0) this.timer = setTimeout(run, delayMs); else run();
  };
  Value.prototype.tween = function (to, durationMs, delayMs) {
    var self = this;
    this.stop();
    if (reduce()) { this.jump(to); return Promise.resolve(); }
    return new Promise(function (resolve) {
      var run = function () {
        var from = self.v, start = performance.now();
        var step = function (now) {
          var t = Math.min(1, (now - start) / durationMs);
          self.v = from + (to - from) * (1 - Math.pow(1 - t, 3));
          self.onUpdate(self.v);
          if (t < 1) self.raf = requestAnimationFrame(step); else { self.raf = 0; resolve(); }
        };
        self.raf = requestAnimationFrame(step);
      };
      if (delayMs > 0) self.timer = setTimeout(run, delayMs); else run();
    });
  };

  function mount(host, opts) {
    var o = opts || {};
    var length = o.length || 6;
    var root = doc.createElement('div');
    root.className = 'code-slots';
    var slotsHtml = '';
    for (var i = 0; i < length; i += 1) {
      slotsHtml += '<span class="code-slots__slot" aria-hidden="true"><span class="code-slots__fill"></span><span class="code-slots__digit"></span></span>';
    }
    root.innerHTML = '<div class="code-slots__row" data-status="idle">'
      + '<input class="code-slots__input" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]*" maxlength="' + length + '" aria-label="' + (o.ariaLabel || 'One-time code') + '">'
      + slotsHtml
      + '<span class="code-slots__wash" aria-hidden="true"><span class="code-slots__check">' + TICK + '</span></span>'
      + '<span class="code-slots__caret" aria-hidden="true"><span class="code-slots__caret-line"></span></span>'
      + '</div><span class="code-slots__sr" aria-live="polite"></span>';
    host.appendChild(root);

    var row = root.querySelector('.code-slots__row');
    var input = root.querySelector('.code-slots__input');
    var caret = root.querySelector('.code-slots__caret');
    var wash = root.querySelector('.code-slots__wash');
    var check = root.querySelector('.code-slots__check');
    var sr = root.querySelector('.code-slots__sr');
    var slotEls = Array.prototype.slice.call(root.querySelectorAll('.code-slots__slot'));
    var size = slotEls[0].offsetWidth || 44;
    var gap = parseFloat(getComputedStyle(row).columnGap) || 8;
    var pitch = size + gap;
    var radius = parseFloat(getComputedStyle(slotEls[0]).borderTopLeftRadius) || 12;
    var height = slotEls[0].offsetHeight || 52;
    var sink = Math.round(height * 0.5);

    var chars = [];
    var active = 0, status = 'idle', focused = false, draining = false, drainTimer = 0;
    var slots = slotEls.map(function (el, i) {
      var s = { el: el, fill: el.querySelector('.code-slots__fill'), digit: el.querySelector('.code-slots__digit'), t: 0, d: 0 };
      var paint = function () {
        s.fill.style.transform = 'scale(' + Math.max(s.t, 0) + ')';
        s.digit.style.transform = 'translateY(' + ((1 - s.t) * RISE + Math.max(s.d, 0) * sink) + 'px)';
        s.digit.style.opacity = String(clamp01(s.t) * (1 - clamp01(s.d / SINK_FADE)));
      };
      s.mv = new Value(0, function (v) { s.t = v; paint(); });
      s.drop = new Value(0, function (v) { s.d = v; paint(); });
      chars[i] = '';
      paint();
      return s;
    });
    var open = new Value(0, function (v) { wash.style.clipPath = 'inset(0 ' + ((1 - clamp01(v)) * 50) + '% round ' + radius + 'px)'; });
    var tick = new Value(0, function (v) {
      check.style.transform = 'translateY(' + ((1 - v) * CHECK_RISE) + 'px) scale(' + (0.85 + 0.15 * Math.max(v, 0)) + ')';
      check.style.opacity = String(clamp01(v));
    });
    open.jump(0); tick.jump(0);

    function code() { return chars.join(''); }
    function firstEmpty() { var i = chars.indexOf(''); return i === -1 ? length - 1 : i; }
    function full() { return chars.every(Boolean); }
    function busy() { return draining || status === 'success' || input.disabled; }
    function paintState() {
      caret.style.transform = 'translateX(' + (active * pitch) + 'px)';
      var show = focused && status !== 'success' && !input.disabled && (status === 'error' || !chars[active]);
      caret.toggleAttribute('data-show', show);
      slots.forEach(function (s, i) {
        s.el.toggleAttribute('data-active', focused && i === active);
        s.el.toggleAttribute('data-filled', !!chars[i]);
      });
      row.toggleAttribute('data-focused', focused);
      sr.textContent = status === 'success' ? (o.acceptedLabel || 'Code accepted') : code().length + ' / ' + length;
    }
    function setActive(i) {
      active = Math.max(0, Math.min(i, length - 1));
      // Restart the blink so the caret is solid right after it moves.
      var line = caret.firstChild;
      line.style.animation = 'none'; void line.offsetWidth; line.style.animation = '';
      paintState();
    }
    function land(i, delayMs) { var s = slots[i]; if (s.t > 0) s.mv.jump(0); s.mv.spring(1, SETTLE, BOUNCE, delayMs); }
    function changed(before) {
      if (typeof o.onChange === 'function') o.onChange(code());
      if (!before && full() && typeof o.onComplete === 'function') o.onComplete(code());
    }
    function insert(raw, from) {
      var digits = String(raw || '').replace(/\D/g, '');
      if (!digits) return;
      if (status === 'error') setStatus('idle');
      var before = full();
      var i = from;
      var step = reduce() ? 0 : CASCADE;
      for (var k = 0; k < digits.length && i < length; k += 1, i += 1) {
        chars[i] = digits[k];
        slots[i].digit.textContent = digits[k];
        land(i, (i - from) * step);
      }
      setActive(Math.min(i, length - 1));
      changed(before);
    }
    function clearSlot(i, stepBack) {
      if (!chars[i]) { if (stepBack) setActive(i); return; }
      chars[i] = '';
      slots[i].mv.spring(0, SETTLE, BOUNCE, 0);
      if (stepBack) setActive(i); else paintState();
      changed(false);
    }

    input.addEventListener('keydown', function (e) {
      if (busy() || e.metaKey || e.ctrlKey || e.altKey) return;
      var k = e.key;
      if (/^[0-9]$/.test(k)) { e.preventDefault(); insert(k, active); }
      else if (k === 'Backspace') { e.preventDefault(); if (status === 'error') setStatus('idle'); if (chars[active]) clearSlot(active); else if (active > 0) clearSlot(active - 1, true); }
      else if (k === 'Delete') { e.preventDefault(); clearSlot(active); }
      else if (k === 'ArrowLeft') { e.preventDefault(); setActive(active - 1); }
      else if (k === 'ArrowRight') { e.preventDefault(); setActive(Math.min(active + 1, firstEmpty())); }
      else if (k === 'Home') { e.preventDefault(); setActive(0); }
      else if (k === 'End') { e.preventDefault(); setActive(firstEmpty()); }
    });
    input.addEventListener('paste', function (e) {
      if (busy()) return;
      e.preventDefault();
      insert((e.clipboardData || global.clipboardData).getData('text'), 0);
    });
    // Phones and the one-time-code autofill type into the input itself.
    input.addEventListener('input', function () {
      var d = input.value.replace(/\D/g, '');
      input.value = '';
      if (busy() || !d) return;
      insert(d, d.length === 1 ? active : 0);
    });
    input.addEventListener('focus', function () { focused = true; paintState(); });
    input.addEventListener('blur', function () { focused = false; paintState(); });
    row.addEventListener('mousedown', function (e) {
      if (input.disabled) return;
      e.preventDefault();
      if (!draining && status !== 'success') {
        var rect = row.getBoundingClientRect();
        setActive(Math.min(Math.floor((e.clientX - rect.left) / pitch), firstEmpty()));
      }
      input.focus();
    });

    function setStatus(next) {
      if (next === status) return;
      var was = status;
      status = next;
      row.setAttribute('data-status', next);
      input.setAttribute('aria-invalid', String(next === 'error'));
      input.readOnly = next === 'success';
      if (next === 'success') {
        open.tween(1, WASH_IN, 0);
        slots.forEach(function (s, k) { s.drop.spring(1, 0.3, 0, SINK_DELAY + k * SINK_STEP); });
        tick.spring(1, 0.35, BOUNCE, CHECK_DELAY);
      } else if (was === 'success') {
        tick.tween(0, 150, 0);
        open.tween(0, WASH_OUT, 60);
        slots.forEach(function (s) { s.drop.spring(0, 0.3, 0, 100); });
      }
      if (next === 'error') {
        var filled = chars.map(function (c, i) { return c ? i : -1; }).filter(function (i) { return i >= 0; }).reverse();
        var step = reduce() ? 0 : CASCADE;
        draining = true;
        filled.forEach(function (i, k) { slots[i].mv.spring(0, SETTLE, BOUNCE, k * step); });
        clearTimeout(drainTimer);
        drainTimer = setTimeout(function () {
          draining = false;
          for (var i = 0; i < length; i += 1) chars[i] = '';
          setActive(0);
        }, reduce() ? 300 : Math.max(0, filled.length - 1) * step + SETTLE * 1000);
      }
      paintState();
    }
    function clear() {
      clearTimeout(drainTimer);
      draining = false;
      for (var i = 0; i < length; i += 1) { chars[i] = ''; slots[i].mv.jump(0); slots[i].drop.jump(0); }
      open.jump(0); tick.jump(0);
      status = 'idle';
      row.setAttribute('data-status', 'idle');
      input.readOnly = false;
      setActive(0);
    }
    paintState();
    if (o.autoFocus) setTimeout(function () { input.focus(); }, 50);

    return {
      el: root,
      setStatus: setStatus,
      clear: clear,
      focus: function () { input.focus(); },
      value: code,
      setDisabled: function (on) { input.disabled = !!on; row.toggleAttribute('data-disabled', !!on); paintState(); },
      destroy: function () {
        clearTimeout(drainTimer);
        slots.forEach(function (s) { s.mv.stop(); s.drop.stop(); });
        open.stop(); tick.stop();
        root.remove();
      },
    };
  }

  global.SylvexCodeSlots = { mount: mount };
})(window);
