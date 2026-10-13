import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { errorText, get, post } from "../api";
import { useApp } from "../state";
import { ConfirmAction, ErrorNotice, fmtDate, Loading, useAsync } from "../ui";

type Session = { session_id: number; channel: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string; current: boolean };

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
      toast("Two-factor authentication is on");
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
        <button className="btn primary" style={{ width: "fit-content" }} disabled={busy} onClick={start}>{busy && <span className="spinner" />}Set up authenticator</button>
        {error && <div className="notice bad">{error}</div>}
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="small">1. Scan with Google Authenticator, 1Password, Authy or similar.</div>
      {qr && <img className="qr" src={qr} alt="Authenticator QR code" width={200} height={200} />}
      <div className="small muted">Or enter the key manually: <span className="mono">{enrollment.secret}</span></div>
      <div className="small">2. Enter the 6-digit code shown in the app.</div>
      <div className="row">
        <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" placeholder="123456" style={{ width: 120 }} />
        <button className="btn primary" disabled={code.length !== 6 || busy} onClick={confirm}>{busy && <span className="spinner" />}Turn on</button>
      </div>
      {error && <div className="notice bad">{error}</div>}
    </div>
  );
}

export default function Account({ onSignedOut }: { onSignedOut: () => void }) {
  const { me } = useApp();
  const sessions = useAsync(() => get<{ items: Session[] }>("/api/admin/v2/auth/sessions"), []);
  const [confirmAll, setConfirmAll] = useState(false);
  const inMiniApp = me.session.channel === "miniapp";

  return (
    <div className="stack">
      <div className="card">
        <h3>Profile</h3>
        <div className="idgrid">
          <div><div className="k">Name</div><div className="v">{me.identity?.display_name || me.identity?.username || "—"}</div></div>
          <div><div className="k">SYLVEX ID</div><div className="v mono">{me.admin.sylvex_user_id}</div></div>
          <div><div className="k">Telegram ID</div><div className="v mono">{me.identity?.telegram_id || "—"}</div></div>
          <div><div className="k">Email</div><div className="v">{me.identity?.email || "—"}</div></div>
          <div><div className="k">Role</div><div className="v">{me.admin.role}</div></div>
          <div><div className="k">Status</div><div className="v">{me.admin.status}</div></div>
        </div>
      </div>

      <div className="card">
        <h3>Browser sign-in (two-factor)</h3>
        {me.admin.totp_enabled ? (
          <div className="notice good">Authenticator is enabled. You can sign in from a normal browser with your SYLVEX email, password and a 6-digit code.</div>
        ) : inMiniApp ? (
          <div className="stack">
            <div className="muted small">To open the console in a normal browser you need an authenticator app. Setup is only possible here, inside Telegram, so browser access stays tied to your Telegram account. You will be asked to confirm with Telegram first.</div>
            <TotpSetup />
          </div>
        ) : (
          <div className="notice warn">Open the console from the SYLVEX support bot in Telegram to set up an authenticator.</div>
        )}
      </div>

      <div className="card">
        <div className="row between">
          <h3>Active sessions</h3>
          <button className="btn small danger" onClick={() => setConfirmAll(true)}>Sign out everywhere</button>
        </div>
        {sessions.error ? <ErrorNotice message={sessions.error} onRetry={sessions.reload} /> : !sessions.data ? <Loading /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Where</th><th>Started</th><th>Last active</th><th>Expires</th></tr></thead>
            <tbody>{sessions.data.items.map((s) => (
              <tr key={s.session_id}>
                <td>{s.channel === "web" ? "Browser" : "Telegram"}{s.current && <span className="badge good" style={{ marginLeft: 6 }}>this device</span>}
                  <div className="cell-sub" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.user_agent}</div></td>
                <td className="small">{fmtDate(s.created_at)}</td>
                <td className="small">{fmtDate(s.last_seen_at)}</td>
                <td className="small">{fmtDate(s.expires_at)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
      </div>

      {confirmAll && (
        <ConfirmAction
          title="Sign out everywhere"
          confirmLabel="Sign out all sessions"
          danger
          needReason={false}
          description="Ends every console session of your account, including this one."
          onConfirm={async () => { await post("/api/admin/v2/auth/logout-all"); onSignedOut(); }}
          onClose={() => setConfirmAll(false)}
        />
      )}
    </div>
  );
}
