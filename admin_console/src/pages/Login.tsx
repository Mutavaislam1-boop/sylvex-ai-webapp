import QRCode from "qrcode";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, errorText, post, setSession } from "../api";
import { LangSwitch, t } from "../i18n";

export default function Login({ onSignedIn, telegramError, onTelegramRetry }: {
  onSignedIn: () => Promise<void>; telegramError?: string; onTelegramRetry?: () => Promise<void>;
}) {
  // Browser sign-in, in steps: email + password first; then either the
  // 6-digit code (2FA already on) or, for the bootstrap owner only, a QR
  // code to set up Google Authenticator. The password stays in memory and
  // is re-sent with the code; nothing is stored.
  const [step, setStep] = useState<"credentials" | "code" | "setup">("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (setup) QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 200 }).then(setQr).catch(() => setQr(""));
  }, [setup]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body: Record<string, string> = { email, password };
    if (step === "code") body.totp = code;
    if (step === "setup") body.setup_code = code;
    try {
      const data = await post<{ csrf_token?: string; totp_setup_required?: boolean; secret?: string; otpauth_uri?: string }>(
        "/api/admin/v2/auth/web", body);
      if (data.totp_setup_required && data.secret && data.otpauth_uri) {
        setSetup({ secret: data.secret, otpauth_uri: data.otpauth_uri });
        setCode("");
        setStep("setup");
        return;
      }
      setSession(undefined, data.csrf_token);
      await onSignedIn();
    } catch (err) {
      if (err instanceof ApiError && err.code === "totp_required") {
        setCode("");
        setStep("code");
        return;
      }
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const restart = () => { setStep("credentials"); setCode(""); setSetup(null); setQr(""); setError(""); };

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

  const codeInput = (
    <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} autoFocus required
      onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" />
  );

  return (
    <div className="login">
      <form className="card stack" onSubmit={submit}>
        <div className="row between"><div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div><LangSwitch /></div>
        {step === "credentials" && <>
          <label className="field">{t("Email")}<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label className="field">{t("Password")}<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        </>}
        {step === "code" && <>
          <div className="muted small">{email}</div>
          <label className="field">{t("2FA code")}{codeInput}</label>
          <div className="muted small">{t("Enter the 6-digit code from your authenticator app.")}</div>
        </>}
        {step === "setup" && setup && <>
          <div className="notice">{t("Set up two-factor authentication to finish signing in.")}</div>
          <div className="small">{t("1. Scan with Google Authenticator, 1Password, Authy or similar.")}</div>
          {qr && <img className="qr" src={qr} alt={t("Authenticator QR code")} width={200} height={200} />}
          <div className="small muted">{t("Or enter the key manually")}: <span className="mono">{setup.secret}</span></div>
          <label className="field">{t("2. Enter the 6-digit code shown in the app.")}{codeInput}</label>
        </>}
        {error && <div className="notice bad">{error}</div>}
        <button className="btn primary" disabled={busy || (step !== "credentials" && code.length !== 6)}>
          {busy ? <span className="spinner" /> : null}{step === "setup" ? t("Turn on and sign in") : t("Sign in")}
        </button>
        {step !== "credentials" && <button type="button" className="btn ghost small" onClick={restart}>← {t("Back")}</button>}
        {step === "credentials" && (
          <div className="muted small">{t("Browser access is only for SYLVEX admins with two-factor authentication.")}</div>
        )}
      </form>
    </div>
  );
}
