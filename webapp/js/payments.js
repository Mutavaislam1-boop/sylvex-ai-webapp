(function () {
  const S = window.SYLVEX || {};
  const tg = S.tg || (window.Telegram && window.Telegram.WebApp);
  const PAYPAL_PAYMENT_LINKS = {
    pack_500: "https://www.paypal.com/ncp/payment/QXN7U6RQU7Y8L",
  };

  function toast(message) {
    if (window.toast) {
      window.toast(message);
      return;
    }

    alert(message);
  }

  function stripHtml(value) {
    const div = document.createElement("div");
    div.innerHTML = value || "";
    return (div.textContent || div.innerText || "").trim();
  }

  function getTelegramId() {
    const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    const params = new URLSearchParams(window.location.search || "");
    return Number((user && user.id) || params.get("telegram_id") || params.get("user_id") || 0);
  }

  function openCheckout(url) {
    if (!url) {
      toast("Ссылка оплаты не найдена");
      return;
    }

    window.location.href = url;
  }

  async function createPayPalOrder(packId, purchaseType) {
    if (PAYPAL_PAYMENT_LINKS[packId]) {
      window.location.href = PAYPAL_PAYMENT_LINKS[packId];
      return;
    }

    const telegramId = getTelegramId();
    if (!telegramId) {
      toast("Telegram ID не найден");
      return;
    }

    toast("Создаём заказ PayPal…");
    const response = await fetch("/api/public/payments/paypal/create-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_id: packId,
        telegram_id: telegramId,
        user_id: telegramId,
        type: purchaseType,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      if (data.error === "paypal_not_configured") {
        toast("PayPal ещё не настроен");
        return;
      }
      toast("Ошибка: " + (data.error || response.status));
      return;
    }

    const checkoutUrl = data.url || data.approval_url || data.checkout_url;
    if (!checkoutUrl) {
      toast("Ссылка PayPal не найдена");
      return;
    }
    console.log("PAYPAL CHECKOUT URL:", checkoutUrl);
    openCheckout(checkoutUrl);
  }

  function renderProducts(products) {
    const grid = document.getElementById("paymentGrid");
    if (!grid) return;

    if (!products || !products.length) {
      grid.innerHTML = `
        <article class="payment-pack">
          <div class="payment-label">Нет доступных товаров</div>
          <p class="payment-desc">Товары PayPal не найдены.</p>
        </article>
      `;
      return;
    }

    grid.innerHTML = products.map((product, index) => {
      const description = stripHtml(product.description);
      const tag = product.is_subscription ? "Подписка" : "Кредиты";

      return `
        <article class="payment-pack ${index === 1 ? "is-popular" : ""}">
          ${index === 1 ? '<div class="payment-tag">Популярно</div>' : ""}
          <div class="payment-pack-top">
            <div>
              <div class="payment-label">${tag}</div>
              <div class="payment-amount">${product.name || "SYLVEX"}</div>
              <div class="payment-price">${product.price_formatted || ""}</div>
            </div>
            <div class="payment-icon">⚡</div>
          </div>

          ${description ? `<p class="payment-desc">${description}</p>` : ""}

          <button class="payment-button" data-pack-id="${product.pack_id || product.id}" data-type="${product.purchase_type || tag.toLowerCase()}">
            PayPal
          </button>
        </article>
      `;
    }).join("");

    grid.querySelectorAll(".payment-button").forEach((button) => {
      button.addEventListener("click", () => {
        createPayPalOrder(button.dataset.packId, button.dataset.type);
      });
    });
  }

  async function initPayments() {
    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch (e) {}
    }

    const grid = document.getElementById("paymentGrid");
    const params = new URLSearchParams(window.location.search || "");
    if ((params.get("provider") || "").toLowerCase() === "paypal") {
      if ((params.get("payment") || "").toLowerCase() === "success") {
        toast("Оплата принята. Баланс обновится после подтверждения PayPal.");
      } else if ((params.get("payment") || "").toLowerCase() === "cancel") {
        toast("Оплата PayPal отменена");
      }
    }

    try {
      const response = await fetch("/api/payment-links", {
        cache: "no-store"
      });

      const data = await response.json();

      console.log("PAYMENT API:", data);

      if (!data.success) {
        throw new Error(data.error || "Payment API error");
      }

      renderProducts(data.products || []);
    } catch (error) {
      console.error("PAYMENTS LOAD ERROR:", error);

      if (grid) {
        grid.innerHTML = `
          <article class="payment-pack">
            <div class="payment-label">Ошибка загрузки</div>
            <p class="payment-desc">Не удалось загрузить товары. Попробуйте позже.</p>
          </article>
        `;
      }
    }
  }

  document.addEventListener("DOMContentLoaded", initPayments);
})();
