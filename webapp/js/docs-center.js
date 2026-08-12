(function () {
  const frame = document.getElementById('docsFrame');
  const catalog = document.getElementById('docsCatalog');
  const toggle = document.getElementById('catalogToggle');
  const scrim = document.getElementById('catalogScrim');
  const search = document.getElementById('catalogSearch');
  const title = document.getElementById('currentTitle');
  const pages = { images: 'docs-images.html?embed=1', video: 'docs-video.html?embed=1' };
  let currentPage = 'images';
  let pendingAnchor = '';

  document.documentElement.dataset.theme = localStorage.getItem('sylvex-theme') || 'dark';
  function setCatalog(open) {
    catalog.classList.toggle('open', open);
    document.body.classList.toggle('catalog-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  }
  toggle.addEventListener('click', () => setCatalog(!catalog.classList.contains('open')));
  document.getElementById('catalogClose').addEventListener('click', () => setCatalog(false));
  scrim.addEventListener('click', () => setCatalog(false));

  function activate(page, anchor) {
    currentPage = pages[page] ? page : 'images';
    pendingAnchor = anchor || '';
    title.textContent = currentPage === 'video' ? 'Видео' : 'Изображения';
    document.querySelectorAll('.catalog-group').forEach((group) => group.classList.toggle('open', group.dataset.doc === currentPage));
    document.querySelectorAll('[data-anchor]').forEach((button) => button.classList.toggle('active', button.dataset.page === currentPage && button.dataset.anchor === pendingAnchor));
    const targetSrc = pages[currentPage];
    const loadedPage = (frame.getAttribute('src') || '').split('?')[0];
    if (loadedPage !== targetSrc.split('?')[0]) frame.src = targetSrc;
    else scrollFrame(pendingAnchor);
    const url = new URL(window.location.href);
    url.searchParams.set('section', currentPage);
    if (pendingAnchor) url.searchParams.set('anchor', pendingAnchor); else url.searchParams.delete('anchor');
    history.replaceState(null, '', url);
    if (window.innerWidth <= 900) setCatalog(false);
  }
  function scrollFrame(anchor) {
    if (!anchor || !frame.contentDocument) return;
    const target = frame.contentDocument.getElementById(anchor);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  frame.addEventListener('load', () => scrollFrame(pendingAnchor));
  document.getElementById('catalogNav').addEventListener('click', (event) => {
    const link = event.target.closest('[data-anchor]');
    if (link) { activate(link.dataset.page, link.dataset.anchor); return; }
    const section = event.target.closest('.catalog-section');
    if (!section) return;
    const group = section.closest('.catalog-group');
    if (group.classList.contains('open') && section.dataset.page === currentPage) group.classList.remove('open');
    else { group.classList.add('open'); activate(section.dataset.page, 'introduction'); }
  });
  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    document.querySelectorAll('.catalog-links button').forEach((button) => {
      button.hidden = !!query && !button.textContent.toLowerCase().includes(query);
    });
    document.querySelectorAll('.catalog-group').forEach((group) => {
      if (query) group.classList.add('open');
      group.hidden = !!query && !group.textContent.toLowerCase().includes(query);
    });
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setCatalog(false); });
  const params = new URLSearchParams(location.search);
  activate(params.get('section') || 'images', params.get('anchor') || 'introduction');
  if (window.innerWidth <= 900) setCatalog(false);
  const telegram = window.Telegram && window.Telegram.WebApp;
  if (telegram && telegram.BackButton) { telegram.BackButton.show(); telegram.BackButton.onClick(() => { location.href = 'index.html'; }); }
})();
