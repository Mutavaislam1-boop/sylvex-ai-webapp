import { FormEvent, useState } from "react";
import { errorText, post, setSession } from "../api";
import { LangSwitch, t } from "../i18n";

export default function Login({ onSignedIn, telegramError, onTelegramRetry }: {
  onSignedIn: () => Promise<void>; telegramError?: string; onTelegramRetry?: () => Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await post<{ csrf_token: string }>("/api/admin/v2/auth/web", { email, password, totp });
      setSession(undefined, data.csrf_token);
      await onSignedIn();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (onTelegramRetry) {
    return (
      <div className="login">
        <div className="card stack">
          <div className="row between"><div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div><LangSwitch /></div>
          <div className="notice bad">{telegramError || t("Could not sign in with Telegram.")}</div>
          <div className="muted small">{t("Your Telegram account must be linked to an active SYLVEX admin.")}</div>
          <button className="btn primary" onClick={() => onTelegramRetry().catch((e) => setError(errorText(e)))}>{t("Try again")}</button>
          {error && <div className="notice bad">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="login">
      <form className="card stack" onSubmit={submit}>
        <div className="row between"><div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div><LangSwitch /></div>
        <label className="field">{t("Email")}<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label className="field">{t("Password")}<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <label className="field">{t("2FA code")}
          <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))} required />
        </label>
        {error && <div className="notice bad">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? <span className="spinner" /> : null}{t("Sign in")}</button>
        <div className="muted small">
          {t("Browser sign-in needs two-factor authentication. Set it up once from the \"SYLVEX Admin\" button in the SYLVEX Support Bot (Account & security).")}
        </div>
      </form>
    </div>
  );
}
