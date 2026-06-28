(function () {
  const S = window.SYLVEX || {};
  const tg = S.tg || (window.Telegram && window.Telegram.WebApp);

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

  function openCheckout(url) {
  if (!url) {
    toast("Ссылка оплаты не найдена");
    return;
  }

  if (window.LemonSqueezy && window.LemonSqueezy.Url) {
    window.LemonSqueezy.Url.Open(url);
    return;
  }

  window.location.href = url;
}

  function renderProducts(products) {
    const grid = document.getElementById("paymentGrid");
    if (!grid) return;

    if (!products || !products.length) {
      grid.innerHTML = `
        <article class="payment-pack">
          <div class="payment-label">Нет доступных товаров</div>
          <p class="payment-desc">Товары Lemon Squeezy не найдены.</p>
        </article>
      `;
      return;
    }

    grid.innerHTML = products.map((product, index) => {
      const url = product.checkout_url || "";
      const description = stripHtml(product.description);
      const tag = product.is_subscription ? "Подписка" : "Кредиты";
      const disabled = url ? "" : "disabled";

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

          <button class="payment-button" ${disabled} data-url="${url}">
            Оплатить банковской картой
          </button>
        </article>
      `;
    }).join("");

    grid.querySelectorAll(".payment-button").forEach((button) => {
      button.addEventListener("click", () => {
        openCheckout(button.dataset.url);
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