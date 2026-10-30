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

const REASONS: Record<string, string> = {
  test: "Test grant", error_compensation: "Error compensation", bonus: "Bonus", promo: "Promotion",
  gift: "Gift to the user", refund: "Refund", management_decision: "Individual management decision",
  hire: "Joined the team", role_change: "Change of duties", access_review: "Access review",
  offboarding: "Left the team", other: "Other",
};
export const reasonLabel = (code: string) => t(REASONS[code] || code);

// Audit actions as the team reads them; unknown ones show their code.
const ACTIONS: Record<string, string> = {
  balance_changed: "Credits changed", subscription_changed: "Subscription changed", message_sent: "Message sent",
  message_failed: "Message not delivered", support_reply_sent: "Reply in Messages", user_blocked: "User blocked",
  user_unblocked: "User unblocked", admin_created: "Became an admin", admin_updated: "Admin access changed",
  broadcast_sent: "Announcement sent", generation_recovered: "Generation recovered", generation_refunded: "Generation refunded",
  admin_access_changed: "Admin access changed", prostudio_job_recovered: "Generation recovered", review_replied: "Review answered",
  support_status_changed: "Conversation status changed", support_assigned: "Conversation assigned",
  support_attachments_changed: "File sending allowed or closed", reference_created: "Media block created",
  reference_updated: "Media block edited", reference_published: "Content published", reference_unpublished: "Content unpublished",
  reference_deleted: "Content deleted", model_disabled: "Model turned off", model_enabled: "Model turned on",
  admin_login: "Signed in", admin_login_failed: "Wrong 2FA code", admin_login_suspicious: "Suspicious sign-in",
  admin_logout: "Signed out", admin_logout_all: "Signed out everywhere", admin_session_revoked: "Session ended",
  admin_reauth: "Identity confirmed", admin_totp_enabled: "Two-factor turned on", admin_totp_enrollment_started: "Two-factor setup started",
};
export const actionLabel = (action: string) => (ACTIONS[action] ? t(ACTIONS[action]) : action);
