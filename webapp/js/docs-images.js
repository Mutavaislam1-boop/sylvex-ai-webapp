(function () {
  const sections = Array.from(document.querySelectorAll('.doc-section'));
  const toc = document.getElementById('docsToc');
  const search = document.getElementById('docsSearch');
  const results = document.getElementById('searchResults');
  const theme = document.getElementById('docsTheme');

  document.documentElement.dataset.theme = localStorage.getItem('sylvex-theme') || 'dark';
  toc.innerHTML = sections.map((section) => '<a href="#' + section.id + '">' + section.dataset.title + '</a>').join('');
  const tocLinks = Array.from(toc.querySelectorAll('a'));

  toc.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link) return;
    event.preventDefault();
    document.querySelector(link.getAttribute('href')).scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    tocLinks.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === '#' + visible.target.id));
  }, { rootMargin: '-18% 0px -65%', threshold: [0, .2, .6] });
  sections.forEach((section) => observer.observe(section));

  function runSearch() {
    const query = search.value.trim().toLocaleLowerCase('ru');
    if (!query) { results.hidden = true; results.innerHTML = ''; return; }
    const matches = sections.filter((section) => section.textContent.toLocaleLowerCase('ru').includes(query)).slice(0, 8);
    results.innerHTML = matches.length ? matches.map((section) => '<button data-target="' + section.id + '"><b>' + section.dataset.title + '</b><span>' + section.textContent.trim().replace(/\s+/g, ' ').slice(0, 115) + '…</span></button>').join('') : '<p>Ничего не найдено</p>';
    results.hidden = false;
  }
  search.addEventListener('input', runSearch);
  results.addEventListener('click', (event) => {
    const button = event.target.closest('[data-target]');
    if (!button) return;
    document.getElementById(button.dataset.target).scrollIntoView({ behavior: 'smooth', block: 'start' });
    results.hidden = true;
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.docs-search') && !event.target.closest('.search-results')) results.hidden = true;
  });
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); search.focus(); }
    if (event.key === 'Escape') { results.hidden = true; search.blur(); }
  });
  theme.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('sylvex-theme', next);
  });
})();
