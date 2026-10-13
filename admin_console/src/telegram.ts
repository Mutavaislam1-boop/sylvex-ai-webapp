// Telegram Mini App integration. Outside Telegram every helper is a no-op.
type WebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  colorScheme?: "light" | "dark";
  themeParams?: Record<string, string>;
  onEvent?: (event: string, cb: () => void) => void;
  HapticFeedback?: { notificationOccurred: (t: "success" | "error" | "warning") => void };
  BackButton?: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void };
};

export function webApp(): WebApp | null {
  const w = (window as unknown as { Telegram?: { WebApp?: WebApp } }).Telegram?.WebApp;
  return w && w.initData ? w : null;
}

export const inTelegram = () => webApp() !== null;
export const initData = () => webApp()?.initData || "";

export function setupTelegram() {
  const app = webApp();
  if (!app) return;
  app.ready();
  app.expand();
  applyTheme();
  app.onEvent?.("themeChanged", applyTheme);
}

function applyTheme() {
  const app = webApp();
  if (!app) return;
  const root = document.documentElement;
  root.dataset.theme = app.colorScheme === "dark" ? "dark" : "light";
  const p = app.themeParams || {};
  const map: Record<string, string> = {
    bg_color: "--tg-bg", secondary_bg_color: "--tg-bg2", text_color: "--tg-text",
    hint_color: "--tg-hint", button_color: "--tg-accent", button_text_color: "--tg-accent-text",
  };
  for (const [key, cssVar] of Object.entries(map)) if (p[key]) root.style.setProperty(cssVar, p[key]);
}

export function haptic(kind: "success" | "error" | "warning") {
  webApp()?.HapticFeedback?.notificationOccurred(kind);
}
