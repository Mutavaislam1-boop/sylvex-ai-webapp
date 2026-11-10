import { useCallback, useEffect, useState } from "react";
import { ApiError, clearSession, errorText, get, onReauthRequired, onUnauthorized, post, setSession } from "./api";
import { closeMiniApp, confirmingForBot, initData, inTelegram, haptic } from "./telegram";
import { t, useLang } from "./i18n";
import { AppProvider, Me } from "./state";
import { Loading, Modal, useRoute } from "./ui";
import Layout from "./Layout";
import Login from "./pages/Login";
import { TotpSetup } from "./pages/Account";

type Phase = "booting" | "signed_out" | "totp" | "ready";

export default function App() {
  // Subscribing here re-renders the whole tree when the language changes.
  useLang();
  const [phase, setPhase] = useState<Phase>("booting");
  const [me, setMe] = useState<Me | null>(null);
  const [bootError, setBootError] = useState("");
  const [route, go] = useRoute();
  const [reauth, setReauth] = useState<null | ((ok: boolean) => void)>(null);

  const refreshMe = useCallback(async () => {
    const data = await get<Me & { csrf_token: string }>("/api/admin/v2/auth/me");
    setSession(undefined, data.csrf_token);
    setMe(data);
    setPhase("ready");
  }, []);

  // Mini App sign-in: the signed initData plus, once 2FA is set up, the
  // current code typed into this form (never into a chat). An admin
  // without 2FA gets a session that can only set it up.
  const telegramLogin = useCallback(async (totp?: string) => {
    const body: Record<string, string> = { initData: initData(), mode: "miniapp" };
    if (totp) body.totp = totp;
    const data = await post<{ session_token: string; csrf_token: string }>("/api/admin/v2/auth/telegram", body);
    setSession(data.session_token, data.csrf_token);
    await refreshMe();
  }, [refreshMe]);

  // Boot: inside Telegram sign in with the Mini App's signed initData;
  // in a browser reuse an existing session cookie if there is one.
  useEffect(() => {
    (async () => {
      try {
        if (inTelegram()) await telegramLogin();
        else await refreshMe();
      } catch (err) {
        if (inTelegram() && err instanceof ApiError && err.code === "totp_required") {
          setPhase("totp");
          return;
        }
        if (inTelegram()) setBootError(errorText(err));
        setPhase("signed_out");
      }
    })();
  }, [telegramLogin, refreshMe]);

  useEffect(() => {
    onUnauthorized(() => {
      clearSession();
      setMe(null);
      setPhase(inTelegram() ? "totp" : "signed_out");
    });
    onReauthRequired(() => new Promise<boolean>((resolve) => setReauth(() => resolve)));
  }, []);

  if (phase === "booting") return <div className="login"><Loading label={t("Signing in…")} /></div>;
  if (phase === "totp") return <TelegramCode onSubmit={telegramLogin} />;
  if (phase === "signed_out" || !me) {
    const retry = async () => {
      try {
        await telegramLogin();
      } catch (err) {
        if (err instanceof ApiError && err.code === "totp_required") { setPhase("totp"); return; }
        throw err;
      }
    };
    return <Login telegramError={bootError} onSignedIn={refreshMe} onTelegramRetry={inTelegram() ? retry : undefined} />;
  }
  if (me.session.mfa_verified === false) {
    return (
      <AppProvider me={me} go={go} refreshMe={refreshMe}>
        <Enrollment onSignedOut={() => { clearSession(); setMe(null); setPhase("signed_out"); }} />
        {reauth && <ReauthDialog totpEnabled={false} mfaVerified={false} onDone={(ok) => { reauth(ok); setReauth(null); }} />}
      </AppProvider>
    );
  }
  if (confirmingForBot()) return <BotConfirmed me={me} onContinue={() => { window.history.replaceState(null, "", window.location.pathname); setMe({ ...me }); }} />;
  return (
    <AppProvider me={me} go={go} refreshMe={refreshMe}>
      <Layout route={route} onSignedOut={() => { clearSession(); setMe(null); setPhase("signed_out"); }} />
      {reauth && <ReauthDialog totpEnabled={me.admin.totp_enabled} mfaVerified onDone={(ok) => { reauth(ok); setReauth(null); }} />}
    </AppProvider>
  );
}

/** The 2FA step of the Mini App sign-in. */
function TelegramCode({ onSubmit }: { onSubmit: (code?: string) => Promise<void> }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (value?: string) => {
    setBusy(true);
    setError("");
    try {
      await onSubmit(value);
      haptic("success");
    } catch (e) {
      haptic("error");
      setCode("");
      setError(e instanceof ApiError && e.code === "totp_required" ? t("Enter your 6-digit 2FA code.") : errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login">
      <form className="card stack" onSubmit={(e) => { e.preventDefault(); run(code); }}>
        <div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div>
        <label className="field">{t("2FA code")}
          <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} autoFocus required
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" />
        </label>
        <div className="muted small">{t("Enter the 6-digit code from your authenticator app.")}</div>
        {error && <div className="notice bad">{error}</div>}
        <button className="btn primary" disabled={busy || code.length !== 6}>{busy ? <span className="spinner" /> : null}{t("Sign in")}</button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={() => run()}>{t("I have not set up an authenticator yet")}</button>
      </form>
    </div>
  );
}

/** An admin without 2FA: the session can only set it up. */
function Enrollment({ onSignedOut }: { onSignedOut: () => void }) {
  return (
    <div className="login">
      <div className="card stack">
        <div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div>
        <div className="notice warn">{t("Two-factor authentication is required for every SYLVEX admin. Set up an authenticator to open the console.")}</div>
        <TotpSetup />
        <button className="btn ghost small" onClick={() => post("/api/admin/v2/auth/logout").finally(onSignedOut)}>{t("Sign out")}</button>
      </div>
    </div>
  );
}

/** Opened from a bot to confirm bot actions with 2FA. */
function BotConfirmed({ me, onContinue }: { me: Me; onContinue: () => void }) {
  return (
    <div className="login">
      <div className="card stack">
        <div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div>
        <div className="notice good">{t("Confirmed. The SYLVEX bots may act for you for 30 minutes; Critical actions for 5 minutes.")}</div>
        {me.telegram_confirmation?.valid_until && <div className="muted small">{t("Valid until")}: {new Date(me.telegram_confirmation.valid_until).toLocaleTimeString()}</div>}
        <button className="btn primary" onClick={() => closeMiniApp()}>{t("Back to the bot")}</button>
        <button className="btn ghost small" onClick={onContinue}>{t("Open the console")}</button>
      </div>
    </div>
  );
}

/** Step-up re-authentication for Critical actions: a 2FA code (valid 5
 * minutes). Fresh Telegram initData only re-opens 2FA setup for an admin
 * who has not set it up yet. */
function ReauthDialog({ totpEnabled, mfaVerified, onDone }: { totpEnabled: boolean; mfaVerified: boolean; onDone: (ok: boolean) => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (body: Record<string, string>) => {
    setBusy(true);
    setError("");
    try {
      await post("/api/admin/v2/auth/reauth", body);
      haptic("success");
      onDone(true);
    } catch (e) {
      setError(e instanceof ApiError && e.code === "reauth_failed" && inTelegram()
        ? t("Telegram confirmation expired. Close and reopen the Mini App, or use your 2FA code.")
        : errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={t("Confirm it's you")} onClose={() => onDone(false)} actions={<button className="btn" onClick={() => onDone(false)}>{t("Cancel")}</button>}>
      <div className="stack">
        <div className="muted">{mfaVerified ? t("This is a Critical action. Confirm your identity to continue (valid for 5 minutes).") : t("Confirm with Telegram to set up two-factor authentication.")}</div>
        {!mfaVerified && inTelegram() && (
          <button className="btn primary" disabled={busy} onClick={() => run({ initData: initData() })}>{t("Confirm with Telegram")}</button>
        )}
        {totpEnabled && (
          <div className="row">
            <input inputMode="numeric" maxLength={6} placeholder={t("6-digit 2FA code")} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            <button className="btn primary" disabled={busy || code.length !== 6} onClick={() => run({ totp: code })}>{t("Confirm")}</button>
          </div>
        )}
        {mfaVerified && !totpEnabled && <div className="notice warn">{t("Set up 2FA from the Telegram Mini App to confirm Critical actions in a browser.")}</div>}
        {error && <div className="notice bad">{error}</div>}
      </div>
    </Modal>
  );
}
