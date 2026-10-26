// The former PayPal-only page must not follow hosted payment links or create orders.
(function () {
  function initPayments() {
    const grid = document.getElementById('paymentGrid');
    if (grid) grid.textContent = 'PayPal больше не используется. Откройте магазин в SYLVEX для оплаты.';
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPayments);
  else initPayments();
})();
