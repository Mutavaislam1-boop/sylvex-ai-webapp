import { useCallback, useEffect, useState } from "react";
import { ApiError, clearSession, errorText, get, onReauthRequired, onUnauthorized, post, setSession } from "./api";
import { initData, inTelegram, haptic } from "./telegram";
import { t, useLang } from "./i18n";
import { AppProvider, Me } from "./state";
import { Loading, Modal, useRoute } from "./ui";
import Layout from "./Layout";
import Login from "./pages/Login";

type Phase = "booting" | "signed_out" | "ready";

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

  const telegramLogin = useCallback(async () => {
    const data = await post<{ session_token: string; csrf_token: string }>("/api/admin/v2/auth/telegram", {
      initData: initData(), mode: "miniapp",
    });
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
        if (inTelegram()) setBootError(errorText(err));
        setPhase("signed_out");
      }
    })();
  }, [telegramLogin, refreshMe]);

  useEffect(() => {
    onUnauthorized(() => {
      clearSession();
      setMe(null);
      setPhase("signed_out");
    });
    onReauthRequired(() => new Promise<boolean>((resolve) => setReauth(() => resolve)));
  }, []);

  if (phase === "booting") return <div className="login"><Loading label={t("Signing in…")} /></div>;
  if (phase === "signed_out" || !me) {
    return <Login telegramError={bootError} onSignedIn={refreshMe} onTelegramRetry={inTelegram() ? telegramLogin : undefined} />;
  }
  return (
    <AppProvider me={me} go={go} refreshMe={refreshMe}>
      <Layout route={route} onSignedOut={() => { clearSession(); setMe(null); setPhase("signed_out"); }} />
      {reauth && <ReauthDialog totpEnabled={me.admin.totp_enabled} onDone={(ok) => { reauth(ok); setReauth(null); }} />}
    </AppProvider>
  );
}

/** Step-up re-authentication for Critical actions: Telegram (fresh initData)
 * inside the Mini App, or a TOTP code. */
function ReauthDialog({ totpEnabled, onDone }: { totpEnabled: boolean; onDone: (ok: boolean) => void }) {
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
        <div className="muted">{t("This is a Critical action. Confirm your identity to continue (valid for 5 minutes).")}</div>
        {inTelegram() && (
          <button className="btn primary" disabled={busy} onClick={() => run({ initData: initData() })}>{t("Confirm with Telegram")}</button>
        )}
        {totpEnabled && (
          <div className="row">
            <input inputMode="numeric" maxLength={6} placeholder={t("6-digit 2FA code")} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            <button className="btn primary" disabled={busy || code.length !== 6} onClick={() => run({ totp: code })}>{t("Confirm")}</button>
          </div>
        )}
        {!inTelegram() && !totpEnabled && <div className="notice warn">{t("Set up 2FA from the Telegram Mini App to confirm Critical actions in a browser.")}</div>}
        {error && <div className="notice bad">{error}</div>}
      </div>
    </Modal>
  );
}
