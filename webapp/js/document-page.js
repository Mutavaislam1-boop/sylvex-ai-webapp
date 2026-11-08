(function () {
  'use strict';
  const data = window.SYLVEX_DOCUMENTS;
  const root = document.documentElement;
  const content = document.getElementById('document-content');
  const id = root.dataset.documentId;
  if (!data || !content || !data.documents[id]) return;
  const select = document.getElementById('document-language');
  const picker = document.getElementById('document-picker');
  const toc = document.getElementById('document-toc');
  const labels = {
    en: { language: 'Language', documents: 'Documents', toc: 'On this page', version: 'Version', effective: 'Effective', published: 'Published', close: 'Close documentation' },
    ru: { language: 'Язык', documents: 'Документы', toc: 'На этой странице', version: 'Версия', effective: 'Дата вступления в силу', published: 'Дата публикации', close: 'Закрыть документацию' }
  };
  const read = (key) => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const valid = (value) => value === 'en' || value === 'ru';
  const requestedLanguage = () => {
    const explicit = new URL(location.href).searchParams.get('lang');
    if (explicit) return valid(explicit) ? explicit : 'en';
    for (const key of ['sylvex-documents-language', 'sylvex-terms-language', 'sylvex-privacy-language']) {
      const stored = read(key);
      if (valid(stored)) return stored;
    }
    return (navigator.language || '').toLowerCase().startsWith('ru') ? 'ru' : 'en';
  };
  function destination(documentId, lang) {
    const url = new URL(data.paths[documentId], location.origin);
    url.searchParams.set('lang', lang);
    if (new URL(location.href).searchParams.get('embed') === '1') url.searchParams.set('embed', '1');
    return url.pathname + url.search;
  }
  function applyLanguage(lang) {
    if (!valid(lang)) lang = 'en';
    const doc = data.documents[id][lang];
    const copy = labels[lang];
    root.lang = lang;
    root.dir = 'ltr';
    document.title = doc.title + ' · SYLVEX';
    document.querySelectorAll('[data-document-title]').forEach((node) => { node.textContent = doc.title; });
    content.innerHTML = doc.html;
    select.value = lang;
    select.setAttribute('aria-label', copy.language);
    picker.setAttribute('aria-label', copy.documents);
    document.querySelectorAll('[data-document-label]').forEach((node) => { node.textContent = copy[node.dataset.documentLabel]; });
    const metadata = [copy.version + ': ' + data.version];
    if (data.published_at) metadata.push(copy.published + ': ' + data.published_at);
    if (data.effective_at) metadata.push(copy.effective + ': ' + data.effective_at);
    document.getElementById('document-version').textContent = metadata.join(' · ');
    const close = document.getElementById('document-close');
    if (close) close.setAttribute('aria-label', copy.close);
    picker.replaceChildren();
    for (const documentId of Object.keys(data.documents).sort()) {
      const option = document.createElement('option');
      option.value = documentId;
      option.textContent = data.documents[documentId][lang].title;
      option.selected = documentId === id;
      picker.appendChild(option);
    }
    if (toc) {
      toc.replaceChildren();
      content.querySelectorAll('section[id]').forEach((section) => {
        const link = document.createElement('a');
        link.href = '#' + section.id;
        link.textContent = section.querySelector('h2').textContent;
        const item = document.createElement('li');
        item.appendChild(link);
        toc.appendChild(item);
      });
    }
    content.querySelectorAll('a[data-document-link]').forEach((link) => {
      link.href = destination(link.dataset.documentLink, lang);
    });
    write('sylvex-documents-language', lang);
    const url = new URL(location.href);
    url.searchParams.set('lang', lang);
    history.replaceState(null, '', url.pathname + url.search + url.hash);
  }
  const embedded = new URL(location.href).searchParams.get('embed') === '1';
  root.classList.toggle('document-embedded', embedded);
  const theme = document.getElementById('document-theme');
  if (theme) root.dataset.theme = read('sylvex-theme') || 'dark';
  if (theme) theme.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    write('sylvex-theme', next);
  });
  select.addEventListener('change', () => applyLanguage(select.value));
  picker.addEventListener('change', () => { location.href = destination(picker.value, select.value); });
  addEventListener('popstate', () => applyLanguage(requestedLanguage()));
  applyLanguage(requestedLanguage());
  if (location.hash === '#faq' && id === '11') {
    location.replace(destination('12', select.value));
    return;
  }
  if (/^#section-\d+$/.test(location.hash)) {
    document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }
})();
