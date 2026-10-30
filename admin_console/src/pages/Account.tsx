import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { errorText, get, post } from "../api";
import { useApp } from "../state";
import { channelLabel, LangSwitch, roleLabel, t } from "../i18n";
import { ConfirmAction, ErrorNotice, fmtDate, Loading, useAsync } from "../ui";

type Session = { session_id: number; channel: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string; device: string; current: boolean };
type Login = { id: number; at: string; action: string; channel: string; device: string; new_device: boolean; detail: string };

const LOGIN_LABELS: Record<string, string> = {
  admin_login: "Signed in",
  admin_login_failed: "Wrong 2FA code",
  admin_login_suspicious: "Suspicious sign-in",
  admin_logout: "Signed out",
  admin_logout_all: "Signed out everywhere",
  admin_session_revoked: "Session ended",
  admin_reauth: "Identity confirmed",
};

function TotpSetup() {
  const { toast, refreshMe } = useApp();
  const [enrollment, setEnrollment] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (enrollment) QRCode.toDataURL(enrollment.otpauth_uri, { margin: 1, width: 200 }).then(setQr).catch(() => setQr(""));
  }, [enrollment]);

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      setEnrollment(await post<{ secret: string; otpauth_uri: string }>("/api/admin/v2/auth/totp/enroll"));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await post("/api/admin/v2/auth/totp/confirm", { code: code.trim() });
      toast(t("Two-factor authentication is on"));
      setEnrollment(null);
      await refreshMe();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (!enrollment) {
    return (
      <div className="stack">
        <button className="btn primary" style={{ width: "fit-content" }} disabled={busy} onClick={start}>{busy && <span className="spinner" />}{t("Set up authenticator")}</button>
        {error && <div className="notice bad">{error}</div>}
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="small">{t("1. Scan with Google Authenticator, 1Password, Authy or similar.")}</div>
      {qr && <img className="qr" src={qr} alt={t("Authenticator QR code")} width={200} height={200} />}
      <div className="small muted">{t("Or enter the key manually")}: <span className="mono">{enrollment.secret}</span></div>
      <div className="small">{t("2. Enter the 6-digit code shown in the app.")}</div>
      <div className="row">
        <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="123456" style={{ width: 120 }} />
        <button className="btn primary" disabled={code.length !== 6 || busy} onClick={confirm}>{busy && <span className="spinner" />}{t("Turn on")}</button>
      </div>
      {error && <div className="notice bad">{error}</div>}
    </div>
  );
}

export default function Account({ onSignedOut }: { onSignedOut: () => void }) {
  const { me } = useApp();
  const { toast } = useApp();
  const sessions = useAsync(() => get<{ items: Session[] }>("/api/admin/v2/auth/sessions"), []);
  const logins = useAsync(() => get<{ items: Login[] }>("/api/admin/v2/auth/logins"), []);
  const [confirmAll, setConfirmAll] = useState(false);
  const [ending, setEnding] = useState<Session | null>(null);
  const suspicious = (logins.data?.items || []).filter((l) => l.action === "admin_login_suspicious");
  const inMiniApp = me.session.channel === "miniapp";

  return (
    <div className="stack">
      <div className="card">
        <h3>{t("Profile")}</h3>
        <div className="idgrid">
          <div><div className="k">{t("Name")}</div><div className="v">{me.identity?.display_name || me.identity?.username || "—"}</div></div>
          <div><div className="k">SYLVEX ID</div><div className="v mono">{me.admin.sylvex_user_id}</div></div>
          <div><div className="k">Telegram ID</div><div className="v mono">{me.identity?.telegram_id || "—"}</div></div>
          <div><div className="k">{t("Email")}</div><div className="v">{me.identity?.email || "—"}</div></div>
          <div><div className="k">{t("Role")}</div><div className="v">{roleLabel(me.admin.role)}</div></div>
          <div><div className="k">{t("Status")}</div><div className="v">{t(me.admin.status)}</div></div>
          <div><div className="k">{t("Language")}</div><div className="v"><LangSwitch /></div></div>
        </div>
      </div>

      <div className="card">
        <h3>{t("Browser sign-in (two-factor)")}</h3>
        {me.admin.totp_enabled ? (
          <div className="notice good">{t("Authenticator is enabled. You can sign in from a normal browser with your SYLVEX email, password and a 6-digit code.")}</div>
        ) : inMiniApp ? (
          <div className="stack">
            <div className="muted small">{t("To open the console in a normal browser you need an authenticator app. Setup is only possible here, inside Telegram, so browser access stays tied to your Telegram account. You will be asked to confirm with Telegram first.")}</div>
            <TotpSetup />
          </div>
        ) : (
          <div className="notice warn">{t("Open the console from the SYLVEX support bot in Telegram to set up an authenticator.")}</div>
        )}
      </div>

      <div className="card">
        <div className="row between">
          <h3>{t("Active sessions")}</h3>
          <button className="btn small danger" onClick={() => setConfirmAll(true)}>{t("Sign out everywhere")}</button>
        </div>
        {sessions.error ? <ErrorNotice message={sessions.error} onRetry={sessions.reload} /> : !sessions.data ? <Loading /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("Where")}</th><th>{t("Started")}</th><th>{t("Last active")}</th><th>{t("Expires")}</th><th></th></tr></thead>
            <tbody>{sessions.data.items.map((s) => (
              <tr key={s.session_id}>
                <td>{channelLabel(s.channel)}{s.current && <span className="badge good" style={{ marginLeft: 6 }}>{t("this device")}</span>}
                  <div className="cell-sub" title={s.user_agent}>{s.device || "—"}</div></td>
                <td className="small">{fmtDate(s.created_at)}</td>
                <td className="small">{fmtDate(s.last_seen_at)}</td>
                <td className="small">{fmtDate(s.expires_at)}</td>
                <td className="right"><button className="btn small" onClick={() => setEnding(s)}>{t("End")}</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      <div className="card stack">
        <h3>{t("Sign-in history")}</h3>
        {suspicious.length > 0 && <div className="notice bad small">{t("Suspicious sign-ins: {n}. If it was not you, end the sessions above and tell the owner.", { n: suspicious.length })}</div>}
        <div className="muted small">{t("A sign-in from a new device and network, or several wrong 2FA codes in a row, is marked suspicious and reported to you and the owner in Telegram.")}</div>
        {logins.error ? <ErrorNotice message={logins.error} onRetry={logins.reload} /> : !logins.data ? <Loading /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("When")}</th><th>{t("Event")}</th><th>{t("Where")}</th></tr></thead>
            <tbody>{logins.data.items.map((l) => (
              <tr key={l.id}>
                <td className="small">{fmtDate(l.at)}</td>
                <td><span className={`badge ${l.action === "admin_login_suspicious" ? "bad" : l.action === "admin_login_failed" ? "warn" : ""}`}>{t(LOGIN_LABELS[l.action] || l.action)}</span>
                  {l.new_device && l.action === "admin_login" && <span className="badge warn" style={{ marginLeft: 6 }}>{t("new device")}</span>}</td>
                <td className="small">{channelLabel(l.channel)}{l.device && <div className="cell-sub">{l.device}</div>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      {ending && (
        <ConfirmAction
          title={t("End session")}
          confirmLabel={t("End")}
          danger
          needReason={false}
          description={<>{channelLabel(ending.channel)} · {ending.device || "—"}{ending.current ? ` — ${t("this is the device you are using; you will be signed out.")}` : ""}</>}
          onConfirm={async () => {
            const res = await post<{ signed_out: boolean }>("/api/admin/v2/auth/sessions/revoke", { session_id: ending.session_id });
            if (res.signed_out) { onSignedOut(); return; }
            toast(t("Session ended"));
            sessions.reload();
            logins.reload();
          }}
          onClose={() => setEnding(null)}
        />
      )}
      {confirmAll && (
        <ConfirmAction
          title={t("Sign out everywhere")}
          confirmLabel={t("Sign out all sessions")}
          danger
          needReason={false}
          description={t("Ends every console session of your account, including this one.")}
          onConfirm={async () => { await post("/api/admin/v2/auth/logout-all"); onSignedOut(); }}
          onClose={() => setConfirmAll(false)}
        />
      )}
    </div>
  );
}
