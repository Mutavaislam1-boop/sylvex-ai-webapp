(() => {
  'use strict';
  const close = document.querySelector('.mobile-back');
  if (close) {
    close.textContent = '×';
    close.setAttribute('aria-label', 'Закрыть документацию');
    close.setAttribute('href', 'index.html');
  }

  const studio = document.querySelector('.floating-studio');
  if (studio) {
    let last = window.scrollY;
    const update = () => {
      const now = window.scrollY;
      const atEnd = innerHeight + now >= document.documentElement.scrollHeight - 28;
      studio.classList.toggle('is-hidden', !atEnd && now > last && now > 90);
      last = now;
    };
    addEventListener('scroll', update, { passive: true });
    update();
  }

  document.querySelectorAll('.typing,.demo-cursor').forEach((node) => {
    const value = node.textContent.trim();
    if (!value || node.dataset.docsTypingReady) return;
    node.dataset.docsTypingReady = '1';
    node.classList.add('docs-js-typewriter');
    node.textContent = '';
    let index = 0;
    const type = () => {
      node.textContent = value.slice(0, ++index);
      if (index < value.length) setTimeout(type, 34);
    };
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        type();
      }
    }, { rootMargin: '80px' });
    observer.observe(node);
  });
})();
