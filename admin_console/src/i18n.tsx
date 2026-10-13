// Interface language: English or Russian, switchable at any time.
// Strings are written in English in the code and looked up in RU when the
// Russian interface is on; a missing entry falls back to the English text.
// The choice is remembered per device; the first visit follows the Telegram
// account language (Mini App) or the browser language.
import { useSyncExternalStore } from "react";
import { RU } from "./i18n_ru";

export type Lang = "en" | "ru";
const STORAGE_KEY = "sylvex_admin_lang";
const listeners = new Set<() => void>();

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "ru") return saved;
  } catch {
    /* storage unavailable: fall through to detection */
  }
  const tg = (window as unknown as { Telegram?: { WebApp?: { initDataUnsafe?: { user?: { language_code?: string } } } } })
    .Telegram?.WebApp?.initDataUnsafe?.user?.language_code;
  const code = (tg || navigator.language || "en").toLowerCase();
  return code.startsWith("ru") || code.startsWith("uk") || code.startsWith("be") || code.startsWith("kk") ? "ru" : "en";
}

let current: Lang = detect();
document.documentElement.lang = current;

export const getLang = () => current;
export const locale = () => (current === "ru" ? "ru-RU" : "en-US");

export function setLang(lang: Lang) {
  if (lang === current) return;
  current = lang;
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* not persisted in private mode; still switches for this visit */
  }
  listeners.forEach((fn) => fn());
}

/** Translate `text` (the English source) and fill {placeholders}. */
export function t(text: string, vars?: Record<string, string | number>) {
  let out = current === "ru" ? RU[text] ?? text : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

/** Re-renders the caller (App, so the whole tree) when the language changes. */
export function useLang(): Lang {
  return useSyncExternalStore((cb) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  }, getLang);
}

export function LangSwitch() {
  const lang = useLang();
  return (
    <div className="lang-switch" role="group" aria-label="Language / Язык">
      {(["ru", "en"] as const).map((l) => (
        <button key={l} type="button" className={lang === l ? "active" : ""} aria-pressed={lang === l} onClick={() => setLang(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

const ROLES: Record<string, string> = {
  owner: "Owner", administrator: "Administrator", finance: "Finance", support: "Support",
  moderator: "Moderator", analyst: "Analyst", read_only: "Read only",
};
export const roleLabel = (role: string) => t(ROLES[role] || role);

const CHANNELS: Record<string, string> = { web: "Browser", miniapp: "Telegram Mini App", bot: "Bot", miniapp_legacy: "Telegram Mini App" };
export const channelLabel = (channel: string) => t(CHANNELS[channel] || channel);
