import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import {
  ConfirmAction, Empty, ErrorNotice, fmtDate, fmtMoneyMap, fmtNum, Identity, Loading, Modal, refPayload,
  SourceBadges, StatusBadge, useAsync,
} from "../ui";

type Detail = {
  account: {
    telegram_id: number | null; sylvex_user_id: string | null; username: string; name: string; balance: number;
    subscription: string; created_at: string; subscription_until: string | null; total_purchases: number;
    spent_by_currency: Record<string, number>; total_generations: number; identity: (Identity & { status?: string; created_at?: string }) | null;
  };
  purchases: { id: number; provider: string; credits: number; amount: number; currency: string; status: string; charge_id: string; created_at: string }[];
  subscription_history: { id: number; type: string; plan_label: string; payment_method: string; amount: number; currency: string; starts_at: string; expires_at: string; status: string; created_at: string }[];
  generations: { id: string; mode: string; model: string; provider: string; status: string; cost: number; created_at: string; completed_at: string | null }[];
  error_reports: { id: number; mode: string; provider: string; model: string; job_id: string; error: string; status: string; created_at: string }[];
  recent_activity: { view: string | null; platform: string | null; last_seen: string | null };
};

const PLANS = [
  { key: "", label: "Default (month / year by length)" },
  ...["starter", "pro", "max", "ultra", "creator"].flatMap((p) => [
    { key: `${p}_month`, label: `${p[0].toUpperCase()}${p.slice(1)} · monthly` },
    { key: `${p}_year`, label: `${p[0].toUpperCase()}${p.slice(1)} · yearly` },
  ]),
];

type Action = null | "balance" | "extend" | "cancel" | "message";

export default function UserDetail({ refId }: { refId: string }) {
  const { can, toast, go } = useApp();
  const ref = refPayload(refId);
  const [tab, setTab] = useState<"payments" | "subscriptions" | "generations" | "reports">("payments");
  const [action, setAction] = useState<Action>(null);
  const [delta, setDelta] = useState("");
  const [days, setDays] = useState("30");
  const [plan, setPlan] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const { data, error, loading, reload } = useAsync(() => post<Detail>("/api/admin/users/detail", ref), [refId]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (!data) return null;
  const a = data.account;
  const id = a.identity;
  const target = a.sylvex_user_id ? { sylvex_user_id: a.sylvex_user_id } : ref;
  const deltaNum = Number(delta);
  const daysNum = Number(days);
  const hasTelegram = !!(id?.linked?.telegram || a.telegram_id);

  const sendMessage = async () => {
    setSending(true);
    try {
      await post("/api/admin/users/message", { ...target, message: message.trim() });
      toast("Message sent");
      setMessage("");
      setAction(null);
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="stack">
      <div className="row"><button className="btn small ghost" onClick={() => history.back()}>← Back</button></div>

      <div className="card">
        <div className="row between">
          <div>
            <h2 style={{ margin: 0 }}>{id?.display_name || a.name || "SYLVEX User"}</h2>
            <div className="muted small">{a.username ? `@${a.username} · ` : ""}{id?.email || ""}</div>
          </div>
          <div className="row">
            <SourceBadges identity={id} />
            {id?.status && <StatusBadge status={id.status} />}
          </div>
        </div>
        <div className="divider" />
        <div className="idgrid">
          <div><div className="k">SYLVEX ID</div><div className="v mono">{a.sylvex_user_id || "—"}</div></div>
          <div><div className="k">Telegram ID</div><div className="v mono">{a.telegram_id || "not linked"}</div></div>
          <div><div className="k">Email</div><div className="v">{id?.email || "—"}</div></div>
          <div><div className="k">Signed up via</div><div className="v">{id?.account_origin || "—"}</div></div>
          <div><div className="k">Joined</div><div className="v">{fmtDate(id?.created_at || a.created_at, false)}</div></div>
          <div><div className="k">Last seen</div><div className="v">{fmtDate(data.recent_activity.last_seen)}</div>
            {data.recent_activity.platform && <div className="cell-sub">{data.recent_activity.platform} · {data.recent_activity.view}</div>}</div>
        </div>
        {id?.technical && (
          <details className="section">
            <summary className="small muted">Technical identifiers (owner only)</summary>
            <pre className="mono small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(id.technical, null, 2)}</pre>
          </details>
        )}
      </div>

      <div className="grid kpis">
        <div className="kpi"><div className="kpi-label">Balance</div><div className="kpi-value">{fmtNum(a.balance)}</div><div className="kpi-sub">credits</div></div>
        <div className="kpi"><div className="kpi-label">Subscription</div><div className="kpi-value">{a.subscription_until ? a.subscription : "free"}</div>
          <div className="kpi-sub">{a.subscription_until ? `until ${fmtDate(a.subscription_until, false)}` : "no active plan"}</div></div>
        <div className="kpi"><div className="kpi-label">Spent</div><div className="kpi-value" style={{ fontSize: 16 }}>{fmtMoneyMap(a.spent_by_currency)}</div>
          <div className="kpi-sub">{fmtNum(a.total_purchases)} purchases</div></div>
        <div className="kpi"><div className="kpi-label">Generations</div><div className="kpi-value">{fmtNum(a.total_generations)}</div></div>
      </div>

      <div className="card">
        <h3>Actions</h3>
        <div className="row">
          {can("users.balance.adjust") && <button className="btn" onClick={() => setAction("balance")}>Adjust balance</button>}
          {can("users.subscription.edit") && <button className="btn" onClick={() => setAction("extend")}>Grant / extend subscription</button>}
          {can("users.subscription.edit") && a.subscription_until && <button className="btn danger" onClick={() => setAction("cancel")}>Cancel subscription</button>}
          {can("messages.send") && <button className="btn" disabled={!hasTelegram} title={hasTelegram ? "" : "No Telegram linked"} onClick={() => setAction("message")}>Send Telegram message</button>}
          {can("generations.view") && a.sylvex_user_id && <button className="btn ghost" onClick={() => go(`generations?sylvex=${a.sylvex_user_id}`)}>All generations →</button>}
          {can("audit.view") && a.sylvex_user_id && <button className="btn ghost" onClick={() => go(`audit?target=${a.sylvex_user_id}`)}>Audit history →</button>}
        </div>
      </div>

      <div>
        <div className="tabs">
          <button className={`tab ${tab === "payments" ? "active" : ""}`} onClick={() => setTab("payments")}>Payments ({data.purchases.length})</button>
          <button className={`tab ${tab === "subscriptions" ? "active" : ""}`} onClick={() => setTab("subscriptions")}>Subscriptions ({data.subscription_history.length})</button>
          <button className={`tab ${tab === "generations" ? "active" : ""}`} onClick={() => setTab("generations")}>Generations ({data.generations.length})</button>
          <button className={`tab ${tab === "reports" ? "active" : ""}`} onClick={() => setTab("reports")}>Error reports ({data.error_reports.length})</button>
        </div>
        {tab === "payments" && (data.purchases.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Date</th><th>Provider</th><th className="right">Credits</th><th className="right">Amount</th><th>Status</th><th>Charge ID</th></tr></thead>
            <tbody>{data.purchases.map((p) => (
              <tr key={p.id}><td className="small">{fmtDate(p.created_at)}</td><td>{p.provider}</td><td className="right">{fmtNum(p.credits)}</td>
                <td className="right">{fmtNum(p.amount)} {p.currency}</td><td><StatusBadge status={p.status} /></td><td className="mono small">{p.charge_id || "—"}</td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>No payments.</Empty>)}
        {tab === "subscriptions" && (data.subscription_history.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Plan</th><th>Method</th><th className="right">Amount</th><th>Period</th><th>Status</th></tr></thead>
            <tbody>{data.subscription_history.map((s) => (
              <tr key={s.id}><td>{s.plan_label || s.type}</td><td>{s.payment_method}</td><td className="right">{fmtNum(s.amount)} {s.currency}</td>
                <td className="small">{fmtDate(s.starts_at, false)} → {fmtDate(s.expires_at, false)}</td><td><StatusBadge status={s.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>No subscriptions.</Empty>)}
        {tab === "generations" && (data.generations.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Date</th><th>Mode</th><th>Model</th><th className="right">Cost</th><th>Status</th></tr></thead>
            <tbody>{data.generations.map((g) => (
              <tr key={g.id}><td className="small">{fmtDate(g.created_at)}</td><td>{g.mode}</td><td className="small">{g.model}<div className="cell-sub">{g.provider}</div></td>
                <td className="right">{fmtNum(g.cost)}</td><td><StatusBadge status={g.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>No generations.</Empty>)}
        {tab === "reports" && (data.error_reports.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>Date</th><th>Mode / model</th><th>Error</th><th>Status</th></tr></thead>
            <tbody>{data.error_reports.map((r) => (
              <tr key={r.id}><td className="small">{fmtDate(r.created_at)}</td><td className="small">{r.mode}<div className="cell-sub">{r.model}</div></td>
                <td className="small">{r.error}</td><td><StatusBadge status={r.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>No error reports.</Empty>)}
      </div>

      {action === "balance" && (
        <ConfirmAction
          title="Adjust balance"
          confirmLabel={deltaNum > 0 ? `Add ${fmtNum(deltaNum)} credits` : deltaNum < 0 ? `Remove ${fmtNum(-deltaNum)} credits` : "Apply"}
          danger={deltaNum < 0}
          description={<div className="stack">
            <span>Current balance: <b>{fmtNum(a.balance)}</b> credits. Use a negative number to remove credits.</span>
            <label className="field">Change (credits)
              <input type="number" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="e.g. 100 or -50" />
            </label>
            {Number.isInteger(deltaNum) && deltaNum !== 0 && <span>New balance: <b>{fmtNum(a.balance + deltaNum)}</b></span>}
          </div>}
          onConfirm={async (reason) => {
            if (!Number.isInteger(deltaNum) || deltaNum === 0) throw new Error("Enter a whole, non-zero number of credits.");
            await post("/api/admin/users/balance", { ...target, delta: deltaNum, reason, source: "admin_console" });
            toast("Balance updated");
            setDelta("");
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "extend" && (
        <ConfirmAction
          title="Grant / extend subscription"
          confirmLabel={`Extend by ${days} days`}
          description={<div className="stack">
            <span>Adds days on top of the current end date (or from today). Free of charge, recorded in the audit log.</span>
            <label className="field">Days (1–730)
              <input type="number" min={1} max={730} value={days} onChange={(e) => setDays(e.target.value)} />
            </label>
            <label className="field">Plan
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>{PLANS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select>
            </label>
          </div>}
          onConfirm={async (reason) => {
            if (!Number.isInteger(daysNum) || daysNum < 1 || daysNum > 730) throw new Error("Days must be between 1 and 730.");
            await post("/api/admin/users/subscription", { ...target, action: "extend", days: daysNum, plan: plan || undefined, reason });
            toast("Subscription extended");
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "cancel" && (
        <ConfirmAction
          title="Cancel subscription"
          confirmLabel="Cancel subscription"
          danger
          description="All active subscriptions of this user end now. No refund is issued."
          onConfirm={async (reason) => {
            await post("/api/admin/users/subscription", { ...target, action: "cancel", reason });
            toast("Subscription cancelled");
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "message" && (
        <Modal title="Send Telegram message" onClose={() => setAction(null)} actions={<>
          <button className="btn" onClick={() => setAction(null)}>Cancel</button>
          <button className="btn primary" disabled={!message.trim() || message.length > 4000 || sending} onClick={sendMessage}>
            {sending && <span className="spinner" />}Send
          </button>
        </>}>
          <div className="stack">
            <div className="muted small">Delivered by the SYLVEX bot to this user's Telegram chat.</div>
            <textarea rows={6} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={4000} autoFocus />
            <div className="muted small right">{message.length} / 4000</div>
          </div>
        </Modal>
      )}
    </div>
  );
}
