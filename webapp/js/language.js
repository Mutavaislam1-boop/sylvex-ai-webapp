let currentLang = localStorage.getItem("sylvex-lang") || "en";

const textMap = {
  en: {
    balance: "Balance",
    topup: "+ Top up",
    generations: "Generations",
    today: "Today",
    streak: "Streak",
    heroTitle: "Generate with SYLVEX AI",
    heroText: "Create images, text & voice — powered by next-gen models.",
    start: "Start creating →",
    quickTools: "Quick tools",
    seeAll: "See all",
    recent: "Recent",
    viewAll: "View all",
    profile: "Profile",
    tools: "Tools",
    history: "History",
    home: "Home",
    settings: "Settings",
    aiTools: "AI Tools",
    generationHistory: "Generation history",
    filter: "Filter",
    appearance: "Appearance",
    darkMode: "Dark mode",
    darkModeDesc: "Switch between light & dark",
    animatedBg: "Animated background",
    animatedBgDesc: "Soft motion gradients",
    notifications: "Notifications",
    push: "Push notifications",
    pushDesc: "Generation results",
    email: "Email updates",
    emailDesc: "Weekly digest",
    about: "About",
    version: "Version",
    support: "Support",
    supportDesc: "Get help from our team",
    signOut: "Sign out",
    account: "Account",
    editProfile: "Edit profile",
    editProfileDesc: "Name, username, avatar",
    subscription: "Manage subscription",
    subscriptionDesc: "Plan and balance",
    invite: "Invite friends",
    inviteDesc: "Earn rewards for referrals",
    plan: "Plan",
    memberSince: "Member since",
    totalGenerations: "Total generations",
    referrals: "Referrals"
  },

  ru: {
    balance: "Баланс",
    topup: "+ Пополнить",
    generations: "Генерации",
    today: "Сегодня",
    streak: "Серия",
    heroTitle: "Создавайте через SYLVEX AI",
    heroText: "Создавайте изображения, видео, текст, озвучку и музыку через AI-модели.",
    start: "Начать создание →",
    quickTools: "Быстрые инструменты",
    seeAll: "Все",
    recent: "Недавние",
    viewAll: "Показать все",
    profile: "Профиль",
    tools: "Инструменты",
    history: "История",
    home: "Главная",
    settings: "Настройки",
    aiTools: "AI-инструменты",
    generationHistory: "История генераций",
    filter: "Фильтр",
    appearance: "Внешний вид",
    darkMode: "Тёмный режим",
    darkModeDesc: "Переключение между тёмным и светлым режимом",
    animatedBg: "Анимированный фон",
    animatedBgDesc: "Мягкое движение градиентов",
    notifications: "Уведомления",
    push: "Push-уведомления",
    pushDesc: "Результаты генераций",
    email: "Email-обновления",
    emailDesc: "Еженедельная сводка",
    about: "О приложении",
    version: "Версия",
    support: "Поддержка",
    supportDesc: "Помощь от команды SYLVEX",
    signOut: "Выйти",
    account: "Аккаунт",
    editProfile: "Редактировать профиль",
    editProfileDesc: "Имя, username, аватар",
    subscription: "Управление подпиской",
    subscriptionDesc: "План и баланс",
    invite: "Пригласить друзей",
    inviteDesc: "Получайте бонусы за приглашения",
    plan: "План",
    memberSince: "Дата регистрации",
    totalGenerations: "Всего генераций",
    referrals: "Рефералы"
  }
};

function setText(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.textContent = value;
}

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("sylvex-lang", lang);

  const t = textMap[lang];

  document.getElementById("langBtn").textContent = lang === "en" ? "RU" : "EN";

  setText(".balance-label", t.balance);
  setText(".topup", t.topup);

  document.querySelectorAll(".stat-lbl")[0].textContent = t.generations;
  document.querySelectorAll(".stat-lbl")[1].textContent = t.today;
  document.querySelectorAll(".stat-lbl")[2].textContent = t.streak;

  setText(".hero h2", t.heroTitle);
  setText(".hero p", t.heroText);
  setText(".hero .cta", t.start);

  document.querySelectorAll(".section-title h3")[0].textContent = t.quickTools;
  document.querySelectorAll(".section-title a")[0].textContent = t.seeAll;
  document.querySelectorAll(".section-title h3")[1].textContent = t.recent;
  document.querySelectorAll(".section-title a")[1].textContent = t.viewAll;
  document.querySelectorAll(".section-title h3")[2].textContent = t.account;
  document.querySelectorAll(".section-title h3")[3].textContent = t.generationHistory;
  document.querySelectorAll(".section-title a")[2].textContent = t.filter;
  document.querySelectorAll(".section-title h3")[4].textContent = t.aiTools;
  document.querySelectorAll(".section-title h3")[5].textContent = t.appearance;
  document.querySelectorAll(".section-title h3")[6].textContent = t.notifications;
  document.querySelectorAll(".section-title h3")[7].textContent = t.about;

  document.querySelectorAll(".nav-btn")[0].lastChild.textContent = t.home;
  document.querySelectorAll(".nav-btn")[1].lastChild.textContent = t.tools;
  document.querySelectorAll(".nav-btn")[2].lastChild.textContent = t.history;
  document.querySelectorAll(".nav-btn")[3].lastChild.textContent = t.profile;
  document.querySelectorAll(".nav-btn")[4].lastChild.textContent = t.settings;
}

document.getElementById("langBtn").addEventListener("click", () => {
  applyLanguage(currentLang === "en" ? "ru" : "en");
});

applyLanguage(currentLang);