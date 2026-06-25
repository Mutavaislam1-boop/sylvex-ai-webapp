(function () {
  const PACKAGES = [
    { key: '100', credits: 100, label: 'Start' },
    { key: '500', credits: 500, label: 'Popular', popular: true },
    { key: '1000', credits: 1000, label: 'Pro' }
  ];

  const S = window.SYLVEX || {};
  const tg = S.tg || window.Telegram && window.Telegram.WebApp;

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

  function render(packages) {
    const grid = document.getElementById('paymentGrid');
    if (!grid) return;

    grid.innerHTML = PACKAGES.map(item => {
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
      render(data.packages || {});
    } catch (e) {
      render({});
      toast('Unable to load checkout links');
    }
  }

  document.addEventListener('DOMContentLoaded', initPayments);
})();
