// Admin API client. Browser: the HttpOnly session cookie travels by itself.
// Telegram Mini App: the session token is kept in memory only and sent as
// X-Admin-Session (Telegram Web runs the app in a cross-site iframe that
// never receives the SameSite=Strict cookie). Every request carries the
// CSRF token; a Critical action answered with "reauth_required" asks the
// admin to re-authenticate once and is then retried.
import { t } from "./i18n";

export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

let sessionToken = "";
let csrfToken = "";
let reauthHandler: (() => Promise<boolean>) | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setSession(token: string | undefined, csrf: string | undefined) {
  if (token !== undefined) sessionToken = token;
  if (csrf !== undefined) csrfToken = csrf;
}
export function clearSession() {
  sessionToken = "";
  csrfToken = "";
}
export function onReauthRequired(handler: () => Promise<boolean>) {
  reauthHandler = handler;
}
export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

type Method = "GET" | "POST" | "PATCH";

async function raw(method: Method, path: string, body?: unknown) {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-Admin-CSRF"] = csrfToken;
  if (sessionToken) headers["X-Admin-Session"] = sessionToken;
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data: Record<string, unknown> = {};
  try {
    data = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    const code = String(data.detail || data.error || `http_${response.status}`);
    throw new ApiError(response.status, code);
  }
  return data;
}

export async function api<T = Record<string, any>>(method: Method, path: string, body?: unknown): Promise<T> {
  try {
    return (await raw(method, path, body)) as T;
  } catch (err) {
    if (err instanceof ApiError && err.code === "reauth_required" && reauthHandler) {
      if (await reauthHandler()) return (await raw(method, path, body)) as T;
    }
    if (err instanceof ApiError && err.status === 401 && unauthorizedHandler && !path.includes("/auth/")) {
      unauthorizedHandler();
    }
    throw err;
  }
}

export const get = <T = Record<string, any>>(path: string) => api<T>("GET", path);
export const post = <T = Record<string, any>>(path: string, body: unknown = {}) => api<T>("POST", path, body);
export const patch = <T = Record<string, any>>(path: string, body: unknown = {}) => api<T>("PATCH", path, body);

const MESSAGES: Record<string, string> = {
  admin_access_denied: "This account is not an active SYLVEX admin.",
  admin_permission_denied: "Your role does not include this action.",
  admin_session_invalid: "Your session has ended. Please sign in again.",
  admin_session_required: "Please sign in.",
  reauth_required: "This action needs a fresh confirmation of your identity.",
  reauth_failed: "Re-authentication failed.",
  totp_invalid: "That code is not valid. Use the current code from your authenticator.",
  totp_locked: "Too many wrong codes. Try again in 15 minutes.",
  totp_enrollment_required: "Two-factor authentication is not set up for this admin. Set it up from the Telegram Mini App first.",
  invalid_credentials: "Email or password is incorrect.",
  too_many_attempts: "Too many attempts. Try again later.",
  user_not_found: "User not found.",
  balance_would_go_negative: "The balance cannot go below zero.",
  user_has_no_telegram: "This account has no Telegram, so it cannot receive messages.",
  console_required_for_critical_action: "Only the owner can do this from a bot.",
  last_owner_protected: "The last owner cannot be removed or demoted.",
  cannot_modify_self: "You cannot change your own access.",
  role_not_below_actor: "You can only assign roles below your own.",
  target_role_not_below_actor: "You can only manage admins below your role.",
  cannot_grant_unheld_permission: "You can only grant permissions you hold yourself.",
  reason_required: "A reason is required.",
  origin_not_allowed: "Request blocked: wrong origin.",
  csrf_token_invalid: "Your session token is out of date. Reload the page.",
  account_not_found: "No SYLVEX account with that ID.",
  already_admin: "This account is already an admin.",
  telegram_send_failed: "Telegram did not accept the message.",
  no_recipients: "No recipients selected.",
  totp_enroll_requires_miniapp: "Two-factor setup is only available inside the Telegram Mini App.",
  admin_not_found: "Admin not found.",
  invalid_status: "Invalid status.",
  invalid_balance_change: "Enter a whole, non-zero number of credits.",
  invalid_subscription_change: "Invalid subscription change.",
  invalid_message: "The message is empty or longer than 4000 characters.",
  telegram_bot_unavailable: "The Telegram bot is not configured on the server.",
  too_many_recipients: "Too many recipients (limit 20,000).",
  invalid_reference: "Name, category and kind (photo/video) are required.",
  upload_failed: "Upload failed.",
  invalid_content_size: "The file is empty or too large.",
  owner_access_required: "Only the owner can do this.",
  database_unavailable: "The database is unavailable.",
  rate_limited: "Too many requests. Wait a minute and try again.",
  request_too_large: "The request is too large.",
  totp_required: "Enter your 6-digit 2FA code.",
  totp_enrollment_not_started: "Two-factor setup expired. Sign in again to get a new QR code.",
  email_not_verified: "This email is not verified yet. The person must confirm it first.",
  message_required: "Write the message text.",
  message_too_long: "The message is longer than 4000 characters.",
  invalid_link: "Links must start with https://",
  too_many_links: "Up to 5 links per message.",
  invalid_channel: "Unknown delivery channel.",
  invalid_image: "The image was not uploaded through the console.",
  unsupported_image: "Use a PNG, JPG, WebP or GIF image.",
  thread_not_found: "Conversation not found.",
};

export function errorText(err: unknown): string {
  if (err instanceof ApiError) return MESSAGES[err.code] ? t(MESSAGES[err.code]) : t("Error: {code}", { code: err.code });
  if (err instanceof Error) return t(err.message);
  return t("Unexpected error");
}
