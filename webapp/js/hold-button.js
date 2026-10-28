/*
 * Hold button: press and hold to confirm a destructive action. The fill
 * runs across the button (a wave crest at its edge) over holdTime; letting
 * go early drains it back. Pointer, touch and keyboard (Space / Enter,
 * Escape cancels). The same file runs in the Mini App and on the website.
 *
 *   var hold = SylvexHoldButton.create({ label, doneLabel, hint, holdTime, size, block, onHold })
 *   hold.el (the <button>) · hold.reset() · hold.setDisabled(on)
 */
(function (global) {
  'use strict';
  if (global.SylvexHoldButton) return;
  var doc = global.document;
  var TAP_MS = 250, HIT_PAD = 10;
  var LINEAR = function (t) { return t; };
  var EASE_OUT = function (t) { return 1 - Math.pow(1 - t, 3); };
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  function create(opts) {
    var o = opts || {};
    var holdTime = o.holdTime || 2000, releaseTime = o.releaseTime || 200, resetAfter = o.resetAfter || 0;
    var wave = o.wave === false ? 0 : (o.waveAmplitude || 6);
    var button = doc.createElement('button');
    button.type = 'button';
    button.className = 'hold-button hold-button--' + (o.size || 'md') + (o.block ? ' hold-button--block' : '') + (o.className ? ' ' + o.className : '');
    button.dataset.phase = 'idle';
    button.dataset.direction = 'right';
    if (o.glow !== false) button.dataset.glow = 'true';
    var vars = { '--hb-radius': (o.radius == null ? 14 : o.radius) + 'px', '--hb-hold': holdTime + 'ms', '--hb-cycles': holdTime / 1100,
      '--hb-release': releaseTime + 'ms', '--hb-press': o.pressScale || 0.97, '--hb-wave': wave + 'px' };
    if (o.backgroundColor) vars['--hb-bg'] = o.backgroundColor;
    if (o.fillColor) vars['--hb-fill'] = o.fillColor;
    if (o.textColor) vars['--hb-text'] = o.textColor;
    if (o.fillTextColor) vars['--hb-fill-text'] = o.fillTextColor;
    Object.keys(vars).forEach(function (k) { button.style.setProperty(k, vars[k]); });
    var labels = '<span class="hold-button__idle">' + esc(o.label || 'Hold to delete') + '</span><span class="hold-button__done" aria-hidden="true">' + esc(o.doneLabel || 'Deleted') + '</span>';
    button.innerHTML = '<span class="hold-button__pulse" aria-hidden="true"></span>'
      + '<span class="hold-button__label">' + labels + '</span>'
      + '<span class="hold-button__clip" aria-hidden="true"><span class="hold-button__fill"><span class="hold-button__label hold-button__label--fill">' + labels + '</span></span>'
      + '<span class="hold-button__crest"><span class="hold-button__label hold-button__label--fill">' + labels + '</span></span></span>'
      + '<span class="hold-button__sr">' + esc(o.hint || ('Press and hold for ' + Math.round(holdTime / 100) / 10 + ' seconds to confirm')) + '</span>';

    var phase = 'idle', input = null, pointerId = null, start = 0, rect = null;
    var timers = { complete: 0, reset: 0 };
    var m = { raf: 0, p: 0, from: 0, to: 0, start: 0 };

    function go(next, kind) {
      phase = next; input = kind || null;
      button.dataset.phase = next;
      if (input) button.dataset.input = input; else delete button.dataset.input;
      button.querySelector('.hold-button__idle').setAttribute('aria-hidden', String(next === 'done'));
      button.querySelector('.hold-button__done').setAttribute('aria-hidden', String(next !== 'done'));
    }
    function clearTimers() { clearTimeout(timers.complete); clearTimeout(timers.reset); }
    function drive(to, duration, ease) {
      cancelAnimationFrame(m.raf);
      m.from = m.p; m.to = to; m.start = performance.now();
      var step = function (now) {
        var t = duration > 0 ? Math.min(1, (now - m.start) / duration) : 1;
        m.p = m.from + (m.to - m.from) * ease(t);
        button.style.setProperty('--hb-p', m.p.toFixed(4));
        if (t < 1) { m.raf = requestAnimationFrame(step); return; }
        m.raf = 0;
        if (m.to === 1) complete();
      };
      m.raf = requestAnimationFrame(step);
    }
    function complete() {
      if (phase !== 'holding' || performance.now() - start < holdTime - 50) return;
      clearTimers();
      go('done', input);
      unwatch();
      if (typeof o.onHold === 'function') o.onHold();
      if (resetAfter > 0) timers.reset = setTimeout(reset, resetAfter);
    }
    function begin(kind) {
      if (button.disabled || phase !== 'idle') return false;
      start = performance.now();
      rect = button.getBoundingClientRect();
      go('holding', kind);
      drive(1, holdTime, LINEAR);
      timers.complete = setTimeout(complete, holdTime + 100);
      watch();
      return true;
    }
    function release(drifted) {
      if (phase !== 'holding') return;
      clearTimers();
      var held = performance.now() - start;
      go('idle');
      unwatch();
      drive(0, releaseTime, EASE_OUT);
      if (!drifted && held < TAP_MS && typeof o.onTap === 'function') o.onTap();
    }
    function reset() { clearTimers(); go('idle'); drive(0, releaseTime, EASE_OUT); }
    // Leaving the window or the tab cancels a hold in progress.
    function cancel() { release(true); }
    function onVisibility() { if (doc.hidden) cancel(); }
    function watch() { global.addEventListener('blur', cancel); doc.addEventListener('visibilitychange', onVisibility); }
    function unwatch() { global.removeEventListener('blur', cancel); doc.removeEventListener('visibilitychange', onVisibility); }
    function endPointer(e, drifted) {
      if (e.pointerId !== pointerId) return;
      pointerId = null;
      try { if (button.hasPointerCapture(e.pointerId)) button.releasePointerCapture(e.pointerId); } catch (_) {}
      release(drifted);
    }

    button.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || !e.isPrimary || pointerId !== null) return;
      if (!begin('pointer')) return;
      pointerId = e.pointerId;
      try { button.setPointerCapture(e.pointerId); } catch (_) {}
    });
    button.addEventListener('pointermove', function (e) {
      if (e.pointerId !== pointerId || !rect) return;
      if (e.clientX < rect.left - HIT_PAD || e.clientX > rect.right + HIT_PAD || e.clientY < rect.top - HIT_PAD || e.clientY > rect.bottom + HIT_PAD) endPointer(e, true);
    });
    button.addEventListener('pointerup', function (e) { endPointer(e, false); });
    button.addEventListener('pointercancel', function (e) { endPointer(e, true); });
    button.addEventListener('lostpointercapture', function (e) { endPointer(e, true); });
    button.addEventListener('pointerleave', function (e) { if (e.pointerType !== 'touch') endPointer(e, true); });
    button.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { if (input === 'key') release(true); return; }
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (!e.repeat) begin('key'); }
    });
    button.addEventListener('keyup', function (e) {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (input === 'key') release(false); }
    });
    button.addEventListener('contextmenu', function (e) { e.preventDefault(); });

    var measure = function () {
      button.style.setProperty('--hb-w', button.offsetWidth + 'px');
      button.style.setProperty('--hb-h', button.offsetHeight + 'px');
    };
    if (global.ResizeObserver) new ResizeObserver(measure).observe(button);
    requestAnimationFrame(measure);

    return { el: button, reset: reset, setDisabled: function (on) { button.disabled = !!on; } };
  }

  global.SylvexHoldButton = { create: create };
})(window);
