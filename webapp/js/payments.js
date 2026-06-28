(function () {
  const LEGACY_PACKAGES = [
    { key: '100', credits: 100, label: 'Start' },
    { key: '500', credits: 500, label: 'Popular', popular: true },
    { key: '1000', credits: 1000, label: 'Pro' }
  ];

  const S = window.SYLVEX || {};
  const tg = S.tg || window.Telegram && window.Telegram.WebApp;

  function stripHtml(value) {
    const div = document.createElement('div');
    div.innerHTML = value || '';
    return (div.textContent || div.innerText || '').trim();
  }

  function openCheckout(url) {
    if (!url) {
      toast('Checkout link is not configured');
      return;
    }

    if (tg && tg.openLink) {
      tg.openLink(url);
      return;
    }

    window.location.href = url;
  }

  function renderProducts(products) {
    const grid = document.getElementById('paymentGrid');
    if (!grid) return;

    if (!products.length) {
      grid.innerHTML = '<article class="payment-pack"><div class="payment-label">Нет доступных товаров</div><p class="payment-desc">Проверьте Lemon Squeezy API key и опубликованные товары.</p></article>';
      return;
    }

    grid.innerHTML = products.map((product, index) => {
      const url = product.checkout_url || '';
      const disabled = url ? '' : ' disabled';
      const description = stripHtml(product.description);
      const tag = product.is_subscription ? 'Подписка' : 'Кредиты';
      const testMode = product.test_mode ? '<div class="payment-tag">Test mode</div>' : '';
      return '<article class="payment-pack ' + (index === 1 ? 'is-popular' : '') + '">'
        + testMode
        + '<div class="payment-pack-top">'
        + '<div><div class="payment-label">' + tag + '</div>'
        + '<div class="payment-amount">' + product.name + '</div>'
        + '<div class="payment-price">' + (product.price_formatted || '') + '</div></div>'
        + '<div class="payment-icon">⚡</div>'
        + '</div>'
        + (description ? '<p class="payment-desc">' + description + '</p>' : '')
        + '<button class="payment-button"' + disabled + ' data-url="' + url + '">Оплатить банковской картой</button>'
        + '</article>';
    }).join('');

    grid.querySelectorAll('.payment-button').forEach(button => {
      button.addEventListener('click', () => openCheckout(button.dataset.url));
    });
  }

  function renderLegacy(packages) {
    const grid = document.getElementById('paymentGrid');
    if (!grid) return;

    grid.innerHTML = LEGACY_PACKAGES.map(item => {
      const url = packages[item.key] || '';
      const disabled = url ? '' : ' disabled';
      return '<article class="payment-pack ' + (item.popular ? 'is-popular' : '') + '">'
        + (item.popular ? '<div class="payment-tag">Лучший выбор</div>' : '')
        + '<div class="payment-pack-top">'
        + '<div><div class="payment-label">' + item.label + '</div>'
        + '<div class="payment-amount">' + item.credits.toLocaleString('ru-RU') + ' ⚡</div></div>'
        + '<div class="payment-icon">⚡</div>'
        + '</div>'
        + '<button class="payment-button"' + disabled + ' data-url="' + url + '">Оплатить банковской картой</button>'
        + '</article>';
    }).join('');

    grid.querySelectorAll('.payment-button').forEach(button => {
      button.addEventListener('click', () => openCheckout(button.dataset.url));
    });
  }

  async function initPayments() {
    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch (e) {}
    }

    try {
      const response = await fetch('/api/payment-links');
      const data = await response.json();
      if (data.products && data.products.length) {
        renderProducts(data.products);
      } else {
        renderLegacy(data.packages || {});
      }
    } catch (e) {
      renderLegacy({});
      toast('Unable to load checkout links');
    }
  }

  document.addEventListener('DOMContentLoaded', initPayments);
})();
