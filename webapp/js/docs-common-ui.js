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

  // Keep the compact topic pages in sync with the published provider catalog.
  // Detailed rows deliberately live on the provider pages rather than being copied
  // into five documents that would inevitably drift apart.
  const pricing = document.querySelector('.doc-section#pricing');
  const page = location.pathname.split('/').pop();
  const pricingCopy = {
    'docs-text.html': ['Стоимость текста', 'Текст тарифицируется отдельно по входным и выходным токенам: GPT‑5.6 — ⚡600 / ⚡3 000, Gemini 3.1 Pro — ⚡300 / ⚡1 800, Grok 4.6 — ⚡300 / ⚡900, Qwen 3.8 Max — ⚡300 / ⚡900, Seed 2.0 Lite — ⚡38 / ⚡300 за 1 млн токенов.', ''],
    'docs-voice.html': ['Стоимость озвучки', 'Eleven v3 и Multilingual v2 — ⚡15 за 1 000 символов; Flash, Turbo и Conversational — ⚡8. Sound Effects, Voice Changer и Voice Isolator — ⚡18 за минуту. Сервер рассчитывает цену до запуска.', 'ElevenLabs'],
    'docs-video.html': ['Стоимость видео', 'Цена зависит от модели, длительности, разрешения, звука и референсного видео. Kling 3.0 Omni на 5 секунд: ⚡63 без референсного видео и ⚡95 с ним в 720p; 1080p — ⚡84 / ⚡126. Это не единая цена всего каталога.', 'Kling'],
    'docs-music.html': ['Стоимость музыки', 'Lyria 3 Pro — ⚡12 за полную генерацию, Lyria 3 Clip — ⚡6. Eleven Music — ⚡23 за минуту. Перед стартом сервер подтверждает расчёт.', 'Google'],
    'docs-images.html': ['Стоимость изображений и инструментов', 'Стоимость зависит от модели, размера, качества и операции. Например, Seedream 5.0 Pro — ⚡7 до 1.5K и ⚡14 выше; Ideogram 4 — ⚡5 / ⚡9 / ⚡15 для Turbo / Default / Quality. Сумма до запуска рассчитывается на сервере.', 'BytePlus'],
  }[page];
  if (pricing && pricingCopy) {
    const [heading, copy, provider] = pricingCopy;
    const url = `docs-pricing.html?embed=1${provider ? `&provider=${encodeURIComponent(provider)}` : ''}`;
    pricing.innerHTML = `<span class="section-no">${pricing.querySelector('.section-no')?.textContent || ''}</span><h2>${heading}</h2><p>${copy}</p><p><a class="text-link" href="${url}">Полный прайс по провайдерам →</a></p>`;
  }
})();
