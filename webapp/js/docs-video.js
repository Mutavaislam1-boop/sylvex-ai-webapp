(function () {
  if (new URLSearchParams(window.location.search).get('embed') === '1') document.documentElement.classList.add('docs-embedded');
  const sections = Array.from(document.querySelectorAll('.doc-section'));
  const toc = document.getElementById('docsToc');
  const mobileToc = document.getElementById('mobileDocsNav');
  const search = document.getElementById('docsSearch');
  const results = document.getElementById('searchResults');
  document.documentElement.dataset.theme = localStorage.getItem('sylvex-theme') || 'dark';

  const links = sections.map((section) => '<a href="#' + section.id + '">' + section.dataset.title + '</a>').join('');
  toc.innerHTML = links;
  mobileToc.innerHTML = links;
  function navigate(event) {
    const link = event.target.closest('a');
    if (!link) return;
    event.preventDefault();
    document.querySelector(link.hash).scrollIntoView({ behavior: 'smooth' });
  }
  toc.addEventListener('click', navigate);
  mobileToc.addEventListener('click', navigate);
  const allLinks = Array.from(document.querySelectorAll('#docsToc a, #mobileDocsNav a'));
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    allLinks.forEach((link) => link.classList.toggle('active', link.hash === '#' + visible.target.id));
    const mobileActive = mobileToc.querySelector('a.active');

  }, { rootMargin: '-18% 0px -65%', threshold: [0, .2, .6] });
  sections.forEach((section) => observer.observe(section));

  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    if (!query) { results.hidden = true; return; }
    const matches = sections.filter((section) => section.textContent.toLowerCase().includes(query)).slice(0, 8);
    results.innerHTML = matches.length
      ? matches.map((section) => '<button data-target="' + section.id + '"><b>' + section.dataset.title + '</b><span>' + section.textContent.trim().replace(/\s+/g, ' ').slice(0, 110) + '…</span></button>').join('')
      : '<p>Ничего не найдено</p>';
    results.hidden = false;
  });
  results.addEventListener('click', (event) => {
    const button = event.target.closest('[data-target]');
    if (!button) return;
    document.getElementById(button.dataset.target).scrollIntoView({ behavior: 'smooth' });
    results.hidden = true;
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.docs-search, .search-results')) results.hidden = true;
  });
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); search.focus(); }
    if (event.key === 'Escape') results.hidden = true;
  });
  document.getElementById('docsTheme').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('sylvex-theme', next);
  });

  const prices = [
    ['Kling 3.0 Turbo', 'Native audio', '84 ⚡️', '1080p: 105 ⚡️'],
    ['Kling 3.0', 'Standard', '63 ⚡️', 'native audio: 95 ⚡️; 1080p: 84 ⚡️; 4K: 315 ⚡️'],
    ['Kling 3.0 Omni', 'Standard', '63 ⚡️', 'native audio: 84 ⚡️; video input: 95 ⚡️; 4K: 315 ⚡️'],
    ['Kling 3.0 Omni Edit', 'Video input', '95 ⚡️', '1080p: 126 ⚡️; 4K: 315 ⚡️'],
    ['Kling O1', 'Standard', '63 ⚡️', 'video input: 95 ⚡️; 1080p: 84 ⚡️'],
    ['Kling 2.6', 'Standard', '32 ⚡️', '1080p: 53 ⚡️; native audio 1080p: 105 ⚡️'],
    ['Kling Motion 2.6', 'Motion control', '53 ⚡️', '1080p: 84 ⚡️'],
    ['Kling 2.5 Turbo', 'Standard', '32 ⚡️', '1080p: 53 ⚡️'],
    ['Kling 2.1', 'Image to video', '42 ⚡️', '1080p: 74 ⚡️'],
    ['Kling Video Effects', 'Video effects', '95 ⚡️', '1080p: 126 ⚡️'],
  ];
  document.getElementById('klingPricingRows').innerHTML = prices.map((row) => '<tr>' + row.map((cell) => '<td>' + cell + '</td>').join('') + '</tr>').join('');

  const telegram = window.Telegram && window.Telegram.WebApp;
  if (telegram && telegram.BackButton) {
    telegram.BackButton.show();
    telegram.BackButton.onClick(() => { window.location.href = 'index.html'; });
  }
})();
