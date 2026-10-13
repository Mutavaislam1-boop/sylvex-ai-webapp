import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { errorText } from "./api";

// ---------- formatting ----------
export const fmtNum = (n: unknown) => (typeof n === "number" ? n.toLocaleString() : n == null ? "—" : String(n));
export function fmtDate(value: unknown, withTime = true) {
  if (!value) return "—";
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return withTime ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : d.toLocaleDateString();
}
export function fmtMoneyMap(map: Record<string, number> | undefined | null) {
  const entries = Object.entries(map || {});
  if (!entries.length) return "—";
  return entries.map(([cur, amount]) => `${fmtNum(amount)} ${cur}`).join(" · ");
}

// ---------- async data ----------
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = useCallback(() => {
    const mine = ++seq.current;
    setLoading(true);
    setError("");
    load()
      .then((d) => mine === seq.current && setData(d))
      .catch((e) => mine === seq.current && setError(errorText(e)))
      .finally(() => mine === seq.current && setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => reload(), [reload]);
  return { data, error, loading, reload, setData };
}

// ---------- simple pieces ----------
export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <div className="loading"><span className="spinner" />{label}</div>
);
export const ErrorNotice = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div className="notice bad row between">
    <span>{message}</span>
    {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
  </div>
);
export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>;

export function Kpi({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  const tone = ["completed", "active", "success", "ok", "published", "resolved"].includes(s)
    ? "good"
    : ["failed", "error", "cancelled", "revoked", "banned", "expired"].includes(s)
      ? "bad"
      : ["queued", "processing", "running", "pending", "provider_processing", "suspended", "open"].includes(s)
        ? "warn"
        : "";
  return <span className={`badge ${tone}`}>{status || "—"}</span>;
}

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (o: number) => void }) {
  if (total <= limit) return null;
  return (
    <div className="row between section">
      <span className="muted small">{offset + 1}–{Math.min(offset + limit, total)} of {fmtNum(total)}</span>
      <div className="row">
        <button className="btn small" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>← Prev</button>
        <button className="btn small" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next →</button>
      </div>
    </div>
  );
}

// ---------- identity ----------
export type Identity = {
  sylvex_user_id: string | null;
  telegram_id: number | null;
  email: string | null;
  username: string | null;
  display_name: string | null;
  account_origin: string | null;
  linked: { telegram: boolean; email: boolean; google: boolean; apple: boolean };
  technical?: Record<string, unknown>;
};

export function SourceBadges({ identity }: { identity?: Identity | null }) {
  if (!identity) return null;
  const l = identity.linked || ({} as Identity["linked"]);
  return (
    <span className="badges">
      {l.telegram && <span className="badge accent">Telegram</span>}
      {(l.email || l.google || l.apple || identity.account_origin === "website") && <span className="badge">Website</span>}
      {l.google && <span className="badge">Google</span>}
      {l.apple && <span className="badge">Apple</span>}
    </span>
  );
}

/** The id the API takes for a user row: SYLVEX ID, else the real Telegram id. */
export function userRef(row: { sylvex_user_id?: string | null; telegram_id?: number | null }) {
  return row.sylvex_user_id ? `s${row.sylvex_user_id}` : row.telegram_id ? `t${row.telegram_id}` : "";
}
export function refPayload(ref: string): Record<string, string> {
  return ref.startsWith("s") ? { sylvex_user_id: ref.slice(1) } : { user_id: ref.slice(1) };
}

// ---------- modal ----------
export function Modal({ title, children, onClose, actions }: { title: string; children: ReactNode; onClose: () => void; actions?: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  );
}

/** Confirm a High/Critical action: always asks for a reason; `typed` makes
 * the admin type an exact word (e.g. the recipient count) to proceed. */
export function ConfirmAction({
  title, description, confirmLabel = "Confirm", danger, typed, needReason = true, onConfirm, onClose,
}: {
  title: string; description: ReactNode; confirmLabel?: string; danger?: boolean; typed?: string; needReason?: boolean;
  onConfirm: (reason: string) => Promise<void>; onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [typedValue, setTypedValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ok = (!needReason || reason.trim()) && (!typed || typedValue.trim() === typed);
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await onConfirm(reason.trim());
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
      <button className={`btn ${danger ? "danger solid" : "primary"}`} disabled={!ok || busy} onClick={submit}>
        {busy ? <span className="spinner" /> : null}{confirmLabel}
      </button>
    </>}>
      <div className="stack">
        <div className="muted">{description}</div>
        {needReason && (
          <label className="field">Reason (saved in the audit log)
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this needed?" autoFocus />
          </label>
        )}
        {typed && (
          <label className="field">Type <b>{typed}</b> to confirm
            <input value={typedValue} onChange={(e) => setTypedValue(e.target.value)} />
          </label>
        )}
        {error && <div className="notice bad">{error}</div>}
      </div>
    </Modal>
  );
}

// ---------- hash router ----------
export function useRoute(): [string[], (path: string) => void] {
  const parse = () => (window.location.hash.replace(/^#\/?/, "") || "dashboard").split("/").map(decodeURIComponent);
  const [parts, setParts] = useState(parse);
  useEffect(() => {
    const onChange = () => setParts(parse());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const go = useCallback((path: string) => {
    window.location.hash = `#/${path}`;
  }, []);
  return [parts, go];
}
