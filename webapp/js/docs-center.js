(function () {
  const frame = document.getElementById('docsFrame');
  const sidebar = document.getElementById('sectionsSidebar');
  const toggle = document.getElementById('sectionsToggle');
  const scrim = document.getElementById('sectionsScrim');
  const title = document.getElementById('currentTitle');
  const pages = { images: 'docs-images.html?embed=1', video: 'docs-video.html?embed=1' };
  document.documentElement.dataset.theme = localStorage.getItem('sylvex-theme') || 'dark';

  function showSidebar(show) {
    sidebar.classList.toggle('open', show);
    document.body.classList.toggle('sections-open', show);
    toggle.setAttribute('aria-expanded', String(show));
  }
  toggle.addEventListener('click', () => showSidebar(!sidebar.classList.contains('open')));
  document.getElementById('sectionsClose').addEventListener('click', () => showSidebar(false));
  scrim.addEventListener('click', () => showSidebar(false));

  function openPage(page, anchor) {
    if (!pages[page]) return;
    title.textContent = page === 'video' ? 'Видео' : 'Изображения';
    document.querySelectorAll('[data-page]').forEach((button) => button.classList.toggle('active', button.dataset.page === page));
    frame.src = pages[page] + (anchor ? '#' + encodeURIComponent(anchor) : '');
    const url = new URL(location.href);
    url.searchParams.set('section', page);
    if (anchor) url.searchParams.set('anchor', anchor); else url.searchParams.delete('anchor');
    history.replaceState(null, '', url);
    if (window.innerWidth <= 800) showSidebar(false);
  }
  sidebar.addEventListener('click', (event) => {
    const button = event.target.closest('[data-page]');
    if (button && !button.disabled) openPage(button.dataset.page, 'introduction');
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') showSidebar(false); });
  const params = new URLSearchParams(location.search);
  openPage(params.get('section') === 'video' ? 'video' : 'images', params.get('anchor') || 'introduction');
  const telegram = window.Telegram && window.Telegram.WebApp;
  if (telegram && telegram.BackButton) { telegram.BackButton.show(); telegram.BackButton.onClick(() => { location.href = 'index.html'; }); }
})();
