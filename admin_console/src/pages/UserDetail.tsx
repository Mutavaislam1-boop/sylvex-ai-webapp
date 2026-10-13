import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
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
  { key: "", name: "", period: "" },
  ...["starter", "pro", "max", "ultra", "creator"].flatMap((p) => [
    { key: `${p}_month`, name: `${p[0].toUpperCase()}${p.slice(1)}`, period: "monthly" },
    { key: `${p}_year`, name: `${p[0].toUpperCase()}${p.slice(1)}`, period: "yearly" },
  ]),
];
const planLabel = (p: (typeof PLANS)[number]) => (p.key ? `${p.name} · ${t(p.period)}` : t("Default (month / year by length)"));

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
      toast(t("Message sent"));
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
      <div className="row"><button className="btn small ghost" onClick={() => history.back()}>← {t("Back")}</button></div>

      <div className="card">
        <div className="row between">
          <div>
            <h2 style={{ margin: 0 }}>{id?.display_name || a.name || t("SYLVEX User")}</h2>
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
          <div><div className="k">Telegram ID</div><div className="v mono">{a.telegram_id || t("not linked")}</div></div>
          <div><div className="k">{t("Email")}</div><div className="v">{id?.email || "—"}</div></div>
          <div><div className="k">{t("Signed up via")}</div><div className="v">{id?.account_origin ? t(id.account_origin) : "—"}</div></div>
          <div><div className="k">{t("Joined")}</div><div className="v">{fmtDate(id?.created_at || a.created_at, false)}</div></div>
          <div><div className="k">{t("Last seen")}</div><div className="v">{fmtDate(data.recent_activity.last_seen)}</div>
            {data.recent_activity.platform && <div className="cell-sub">{data.recent_activity.platform} · {data.recent_activity.view}</div>}</div>
        </div>
        {id?.technical && (
          <details className="section">
            <summary className="small muted">{t("Technical identifiers (owner only)")}</summary>
            <pre className="mono small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(id.technical, null, 2)}</pre>
          </details>
        )}
      </div>

      <div className="grid kpis">
        <div className="kpi"><div className="kpi-label">{t("Balance")}</div><div className="kpi-value">{fmtNum(a.balance)}</div><div className="kpi-sub">{t("credits")}</div></div>
        <div className="kpi"><div className="kpi-label">{t("Subscription")}</div><div className="kpi-value">{a.subscription_until ? a.subscription : t("free")}</div>
          <div className="kpi-sub">{a.subscription_until ? t("until {date}", { date: fmtDate(a.subscription_until, false) }) : t("no active plan")}</div></div>
        <div className="kpi"><div className="kpi-label">{t("Spent")}</div><div className="kpi-value" style={{ fontSize: 16 }}>{fmtMoneyMap(a.spent_by_currency)}</div>
          <div className="kpi-sub">{t("Purchases: {n}", { n: fmtNum(a.total_purchases) })}</div></div>
        <div className="kpi"><div className="kpi-label">{t("Generations")}</div><div className="kpi-value">{fmtNum(a.total_generations)}</div></div>
      </div>

      <div className="card">
        <h3>{t("Actions")}</h3>
        <div className="row">
          {can("users.balance.adjust") && <button className="btn" onClick={() => setAction("balance")}>{t("Adjust balance")}</button>}
          {can("users.subscription.edit") && <button className="btn" onClick={() => setAction("extend")}>{t("Grant / extend subscription")}</button>}
          {can("users.subscription.edit") && a.subscription_until && <button className="btn danger" onClick={() => setAction("cancel")}>{t("Cancel subscription")}</button>}
          {can("messages.send") && <button className="btn" disabled={!hasTelegram} title={hasTelegram ? "" : t("No Telegram linked")} onClick={() => setAction("message")}>{t("Send Telegram message")}</button>}
          {can("generations.view") && a.sylvex_user_id && <button className="btn ghost" onClick={() => go(`generations?sylvex=${a.sylvex_user_id}`)}>{t("All generations")} →</button>}
          {can("audit.view") && a.sylvex_user_id && <button className="btn ghost" onClick={() => go(`audit?target=${a.sylvex_user_id}`)}>{t("Audit history")} →</button>}
        </div>
      </div>

      <div>
        <div className="tabs">
          <button className={`tab ${tab === "payments" ? "active" : ""}`} onClick={() => setTab("payments")}>{t("Payments")} ({data.purchases.length})</button>
          <button className={`tab ${tab === "subscriptions" ? "active" : ""}`} onClick={() => setTab("subscriptions")}>{t("Subscriptions")} ({data.subscription_history.length})</button>
          <button className={`tab ${tab === "generations" ? "active" : ""}`} onClick={() => setTab("generations")}>{t("Generations")} ({data.generations.length})</button>
          <button className={`tab ${tab === "reports" ? "active" : ""}`} onClick={() => setTab("reports")}>{t("Error reports")} ({data.error_reports.length})</button>
        </div>
        {tab === "payments" && (data.purchases.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("Date")}</th><th>{t("Provider")}</th><th className="right">{t("Credits")}</th><th className="right">{t("Amount")}</th><th>{t("Status")}</th><th>{t("Charge ID")}</th></tr></thead>
            <tbody>{data.purchases.map((p) => (
              <tr key={p.id}><td className="small">{fmtDate(p.created_at)}</td><td>{p.provider}</td><td className="right">{fmtNum(p.credits)}</td>
                <td className="right">{fmtNum(p.amount)} {p.currency}</td><td><StatusBadge status={p.status} /></td><td className="mono small">{p.charge_id || "—"}</td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>{t("No payments.")}</Empty>)}
        {tab === "subscriptions" && (data.subscription_history.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("Plan")}</th><th>{t("Method")}</th><th className="right">{t("Amount")}</th><th>{t("Period")}</th><th>{t("Status")}</th></tr></thead>
            <tbody>{data.subscription_history.map((s) => (
              <tr key={s.id}><td>{s.plan_label || s.type}</td><td>{s.payment_method}</td><td className="right">{fmtNum(s.amount)} {s.currency}</td>
                <td className="small">{fmtDate(s.starts_at, false)} → {fmtDate(s.expires_at, false)}</td><td><StatusBadge status={s.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>{t("No subscriptions.")}</Empty>)}
        {tab === "generations" && (data.generations.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("Date")}</th><th>{t("Tool")}</th><th>{t("Model")}</th><th className="right">{t("Cost")}</th><th>{t("Status")}</th></tr></thead>
            <tbody>{data.generations.map((g) => (
              <tr key={g.id}><td className="small">{fmtDate(g.created_at)}</td><td>{t(g.mode)}</td><td className="small">{g.model}<div className="cell-sub">{g.provider}</div></td>
                <td className="right">{fmtNum(g.cost)}</td><td><StatusBadge status={g.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>{t("No generations.")}</Empty>)}
        {tab === "reports" && (data.error_reports.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("Date")}</th><th>{t("Tool / model")}</th><th>{t("Error")}</th><th>{t("Status")}</th></tr></thead>
            <tbody>{data.error_reports.map((r) => (
              <tr key={r.id}><td className="small">{fmtDate(r.created_at)}</td><td className="small">{t(r.mode)}<div className="cell-sub">{r.model}</div></td>
                <td className="small">{r.error}</td><td><StatusBadge status={r.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <Empty>{t("No error reports.")}</Empty>)}
      </div>

      {action === "balance" && (
        <ConfirmAction
          title={t("Adjust balance")}
          confirmLabel={deltaNum > 0 ? t("Add {n} credits", { n: fmtNum(deltaNum) }) : deltaNum < 0 ? t("Remove {n} credits", { n: fmtNum(-deltaNum) }) : t("Apply")}
          danger={deltaNum < 0}
          description={<div className="stack">
            <span>{t("Current balance")}: <b>{fmtNum(a.balance)}</b>. {t("Use a negative number to remove credits.")}</span>
            <label className="field">{t("Change (credits)")}
              <input type="number" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder={t("e.g. 100 or -50")} />
            </label>
            {Number.isInteger(deltaNum) && deltaNum !== 0 && <span>{t("New balance")}: <b>{fmtNum(a.balance + deltaNum)}</b></span>}
          </div>}
          onConfirm={async (reason) => {
            if (!Number.isInteger(deltaNum) || deltaNum === 0) throw new Error(t("Enter a whole, non-zero number of credits."));
            await post("/api/admin/users/balance", { ...target, delta: deltaNum, reason, source: "admin_console" });
            toast(t("Balance updated"));
            setDelta("");
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "extend" && (
        <ConfirmAction
          title={t("Grant / extend subscription")}
          confirmLabel={t("Extend by {n} days", { n: days })}
          description={<div className="stack">
            <span>{t("Adds days on top of the current end date (or from today). Free of charge, recorded in the audit log.")}</span>
            <label className="field">{t("Days (1–730)")}
              <input type="number" min={1} max={730} value={days} onChange={(e) => setDays(e.target.value)} />
            </label>
            <label className="field">{t("Plan")}
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>{PLANS.map((p) => <option key={p.key} value={p.key}>{planLabel(p)}</option>)}</select>
            </label>
          </div>}
          onConfirm={async (reason) => {
            if (!Number.isInteger(daysNum) || daysNum < 1 || daysNum > 730) throw new Error(t("Days must be between 1 and 730."));
            await post("/api/admin/users/subscription", { ...target, action: "extend", days: daysNum, plan: plan || undefined, reason });
            toast(t("Subscription extended"));
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "cancel" && (
        <ConfirmAction
          title={t("Cancel subscription")}
          confirmLabel={t("Cancel subscription")}
          danger
          description={t("All active subscriptions of this user end now. No refund is issued.")}
          onConfirm={async (reason) => {
            await post("/api/admin/users/subscription", { ...target, action: "cancel", reason });
            toast(t("Subscription cancelled"));
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "message" && (
        <Modal title={t("Send Telegram message")} onClose={() => setAction(null)} actions={<>
          <button className="btn" onClick={() => setAction(null)}>{t("Cancel")}</button>
          <button className="btn primary" disabled={!message.trim() || message.length > 4000 || sending} onClick={sendMessage}>
            {sending && <span className="spinner" />}{t("Send")}
          </button>
        </>}>
          <div className="stack">
            <div className="muted small">{t("Delivered by the SYLVEX bot to this user's Telegram chat.")}</div>
            <textarea rows={6} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={4000} autoFocus />
            <div className="muted small right">{message.length} / 4000</div>
          </div>
        </Modal>
      )}
    </div>
  );
}
