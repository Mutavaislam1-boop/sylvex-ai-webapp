/*
 * AnimatedContent for SYLVEX home screens: a block marked
 * data-animated-content rises 100px into place and fades in (0.8 s,
 * power3.out) once its top passes 85% of the screen, one time only. With
 * data-animated-content="stagger" its children come in turn, 80 ms apart;
 * children a script fills in later come the same way the first time, and
 * show at once after that. Loaded in <head> so nothing flashes before it
 * hides; with reduced motion nothing is hidden or moved. The same file runs
 * in the Mini App and on the website.
 */
(function (global) {
  'use strict';
  var doc = global.document;
  if (global.SylvexAnimatedContent) return;
  if (!global.IntersectionObserver || !global.Element || !Element.prototype.animate) return;
  if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var DISTANCE = 100, DURATION = 800, STAGGER = 80, THRESHOLD = 0.15;
  var EASE = 'cubic-bezier(0.165, 0.84, 0.44, 1)'; // power3.out

  // Until its turn a block (or a stagger group's child) keeps its place but is not seen.
  var style = doc.createElement('style');
  style.textContent = '.ac-on [data-animated-content]:not([data-animated-content="stagger"]):not([data-ac-in]),'
    + '.ac-on [data-animated-content="stagger"]>:not([data-ac-in]){visibility:hidden}';
  doc.head.appendChild(style);
  doc.documentElement.classList.add('ac-on');

  function rise(targets) {
    targets.forEach(function (el, i) {
      el.setAttribute('data-ac-in', '');
      // `translate` adds to the element's own transform instead of replacing it.
      el.animate([
        { translate: '0 ' + DISTANCE + 'px', opacity: 0 },
        { translate: '0 0', opacity: 1 }
      ], { duration: DURATION, delay: i * STAGGER, easing: EASE, fill: 'backwards' });
    });
  }

  function children(group) {
    return Array.prototype.filter.call(group.children, function (child) { return !child.hasAttribute('data-ac-in'); });
  }

  function enter(el) {
    el.setAttribute('data-ac-entered', '');
    if (el.getAttribute('data-animated-content') !== 'stagger') { rise([el]); return; }
    var list = children(el);
    if (list.length) { el.setAttribute('data-ac-filled', ''); rise(list); }
  }

  // Its top past 85% of the screen - or already scrolled by.
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var box = entry.boundingClientRect;
      if (entry.isIntersecting || (box.height > 0 && box.bottom < 0)) {
        observer.unobserve(entry.target);
        enter(entry.target);
      }
    });
  }, { rootMargin: '0px 0px -' + THRESHOLD * 100 + '% 0px' });

  function watch(root) {
    var found = root.matches && root.matches('[data-animated-content]') ? [root] : [];
    if (root.querySelectorAll) found = found.concat(Array.prototype.slice.call(root.querySelectorAll('[data-animated-content]')));
    found.forEach(function (el) {
      if (el.__acWatched) return;
      el.__acWatched = true;
      observer.observe(el);
    });
  }

  // New blocks, and children a script puts into a stagger group.
  new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      var group = m.target;
      if (group.nodeType === 1 && group.getAttribute('data-animated-content') === 'stagger' && m.addedNodes.length) {
        var added = Array.prototype.filter.call(m.addedNodes, function (n) { return n.nodeType === 1 && !n.hasAttribute('data-ac-in'); });
        if (group.hasAttribute('data-ac-filled')) added.forEach(function (n) { n.setAttribute('data-ac-in', ''); });
        else if (group.hasAttribute('data-ac-entered') && added.length) { group.setAttribute('data-ac-filled', ''); rise(added); }
      }
      Array.prototype.forEach.call(m.addedNodes, function (n) { if (n.nodeType === 1) watch(n); });
    });
  }).observe(doc.documentElement, { childList: true, subtree: true });

  if (doc.body) watch(doc.body);
  doc.addEventListener('DOMContentLoaded', function () { watch(doc.body); });

  global.SylvexAnimatedContent = { DISTANCE: DISTANCE, DURATION: DURATION, STAGGER: STAGGER, THRESHOLD: THRESHOLD };
})(window);
