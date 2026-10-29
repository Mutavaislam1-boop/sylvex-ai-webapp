import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { actionLabel, reasonLabel, roleLabel, t } from "../i18n";
import {
  ConfirmAction, Empty, ErrorNotice, fmtDate, fmtMoneyMap, fmtNum, GRANT_REASONS, Identity, Loading, Modal, refPayload,
  SourceBadges, STAFF_REASONS, StatusBadge, useAsync,
} from "../ui";
import { CHANNEL_LABEL, Composer, Delivery, DeliveryBadges, Draft, draftPayload, draftProblem, emptyDraft, telegramErrorText } from "./messaging";

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
  block: Block | null;
  block_history: Block[];
  staff: { admin_id: number; role: string; status: string } | null;
  admin_history: HistoryRow[];
};
type Block = {
  id: number; reason: string; note: string; admin_name: string | null; created_at: string; lifted_at: string | null;
  lifted_by_name: string | null; lift_reason: string; active: boolean;
};
type HistoryRow = { id: number; at: string; action: string; risk: string; actor_name: string | null; reason: string; before: Record<string, unknown>; after: Record<string, unknown> };
type ConvoMessage = {
  id: number | string; direction: "in" | "out"; text: string; created_at: string; author?: string | null; delivery?: Delivery;
  image_url?: string | null; links?: { url: string; label: string }[]; read_at?: string | null; legacy?: boolean;
};
type Conversation = { channels: Record<string, boolean>; messages: ConvoMessage[] };

const ROLE_CHOICES = ["administrator", "finance", "support", "moderator", "analyst", "read_only"];

/** "50 → 60", "free → pro_month (until …)": what an audit row changed. */
function changeSummary(h: HistoryRow) {
  const b = h.before || {};
  const a = h.after || {};
  if (h.action === "balance_changed") return `${fmtNum(b.balance)} → ${fmtNum(a.balance)} (${Number(a.delta) > 0 ? "+" : ""}${fmtNum(a.delta)})`;
  if (h.action === "subscription_changed") return `${b.subscription || t("free")} → ${a.subscription || t("free")}${a.expires_at ? ` · ${t("until {date}", { date: fmtDate(a.expires_at, false) })}` : ""}`;
  if (h.action === "admin_created") return roleLabel(String(a.role || ""));
  if (h.action === "admin_updated") return `${roleLabel(String(b.role || ""))} / ${t(String(b.status || ""))} → ${roleLabel(String(a.role || ""))} / ${t(String(a.status || ""))}`;
  if (h.action === "message_sent") return (a.channels as string[] | undefined || []).map((c) => t(CHANNEL_LABEL[c] || c)).join(", ");
  return "";
}

function WriteToUser({ target, onClose }: { target: Record<string, string>; onClose: () => void }) {
  const { toast } = useApp();
  const convo = useAsync(() => post<Conversation>("/api/admin/users/conversation", target), []);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const available = convo.data?.channels || {};
  const channels = chosen ?? ["website", "miniapp", "telegram"].filter((c) => available[c]);
  const toggle = (c: string) => setChosen(channels.includes(c) ? channels.filter((x) => x !== c) : [...channels, c]);
  const problem = draftProblem(draft) || (channels.length ? "" : t("Choose at least one place to deliver."));
  const send = async () => {
    setBusy(true);
    try {
      const res = await post<{ delivery: Delivery }>("/api/admin/users/message/send", { ...target, ...draftPayload(draft), channels });
      const failed = res.delivery.telegram === "failed";
      toast(failed ? `${t("Sent, but Telegram did not deliver it")}: ${telegramErrorText(res.delivery.telegram_error)}` : t("Message sent"), failed);
      setDraft(emptyDraft());
      convo.reload();
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={t("Write to user")} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose}>{t("Close")}</button>
      <button className="btn primary" disabled={!!problem || busy || !convo.data} onClick={send}>{busy && <span className="spinner" />}{t("Send")}</button>
    </>}>
      <div className="stack">
        {convo.error ? <ErrorNotice message={convo.error} onRetry={convo.reload} /> : !convo.data ? <Loading /> : (
          <div className="convo">
            {convo.data.messages.length ? convo.data.messages.map((m) => (
              <div key={m.id} className={`bubble ${m.direction}`}>
                <div className="bubble-head">{m.direction === "out" ? `SYLVEX Team${m.author ? ` · ${m.author}` : ""}` : t("User")} · {fmtDate(m.created_at)}</div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
                {m.image_url && <img src={m.image_url} alt="" style={{ maxWidth: 200, borderRadius: 8, marginTop: 6 }} />}
                {m.direction === "out" && <div className="bubble-foot"><DeliveryBadges delivery={m.delivery} />
                  {m.read_at && <span className="badge good">{t("Read")} {fmtDate(m.read_at)}</span>}</div>}
              </div>
            )) : <Empty>{t("No messages with this user yet.")}</Empty>}
          </div>
        )}
        <div className="field"><span>{t("Deliver to")}</span>
          <div className="chips">{["website", "miniapp", "telegram"].map((c) => (
            <button key={c} type="button" className={`chip ${channels.includes(c) ? "on" : ""}`} disabled={!available[c]}
              title={available[c] ? "" : c === "telegram" ? t("No Telegram linked") : t("No SYLVEX account")} onClick={() => toggle(c)}>
              {c === "website" ? t("Website") : c === "miniapp" ? t("Mini App (Telegram and browser)") : t("Telegram bot")}
            </button>
          ))}</div>
        </div>
        <Composer draft={draft} onChange={setDraft} rows={4} placeholder={t("Write a message…")} />
        <div className="muted small">{t("The message also appears in Messages, so the whole conversation stays in one place.")}</div>
      </div>
    </Modal>
  );
}

function AssignRole({ target, staff, onClose, onSaved }: {
  target: Record<string, string>; staff: Detail["staff"]; onClose: () => void; onSaved: () => void;
}) {
  const { toast } = useApp();
  const current = staff && staff.status !== "revoked" ? staff.role : "";
  const [role, setRole] = useState(current || "support");
  return (
    <ConfirmAction
      title={t("Assign role")}
      confirmLabel={role ? t("Save role") : t("Remove from the team")}
      danger={!role}
      presets={STAFF_REASONS}
      description={<div className="stack">
        <span>{current ? t("Current role: {role}.", { role: roleLabel(current) }) : t("This person is not on the team yet.")} {t("The same access is shown and edited in Admins.")}</span>
        <label className="field">{t("Role")}
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLE_CHOICES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
            {current && <option value="">{t("No role (remove access)")}</option>}
          </select>
        </label>
        <span className="small">{t("The owner role is never assigned from the console.")}</span>
      </div>}
      onConfirm={async (reason, extra) => {
        await post("/api/admin/v2/users/role", { ...target, role, reason, ...extra });
        toast(role ? t("Role saved") : t("Access removed"));
        onSaved();
      }}
      onClose={onClose}
    />
  );
}

type Action = null | "balance" | "extend" | "cancel" | "message" | "block" | "unblock" | "role";

const PLANS = [
  { key: "", name: "", period: "" },
  ...["starter", "pro", "max", "ultra", "creator"].flatMap((p) => [
    { key: `${p}_month`, name: `${p[0].toUpperCase()}${p.slice(1)}`, period: "monthly" },
    { key: `${p}_year`, name: `${p[0].toUpperCase()}${p.slice(1)}`, period: "yearly" },
  ]),
];
const planLabel = (p: (typeof PLANS)[number]) => (p.key ? `${p.name} · ${t(p.period)}` : t("Default (month / year by length)"));

export default function UserDetail({ refId }: { refId: string }) {
  const { can, toast, go, me } = useApp();
  const ref = refPayload(refId);
  const [tab, setTab] = useState<"payments" | "subscriptions" | "generations" | "reports" | "history">("payments");
  const [action, setAction] = useState<Action>(null);
  const [delta, setDelta] = useState("");
  const [days, setDays] = useState("30");
  const [plan, setPlan] = useState("");
  const { data, error, loading, reload } = useAsync(() => post<Detail>("/api/admin/users/detail", ref), [refId]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (!data) return null;
  const a = data.account;
  const id = a.identity;
  const target = a.sylvex_user_id ? { sylvex_user_id: a.sylvex_user_id } : ref;
  const deltaNum = Number(delta);
  const daysNum = Number(days);
  const isOwner = me.admin.role === "owner";
  const staffRole = data.staff && data.staff.status !== "revoked" ? data.staff.role : "";
  const historyCount = data.admin_history.length + data.block_history.length;

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
            {id?.status && !data.block && <StatusBadge status={id.status} />}
            {staffRole && <span className="badge accent">{t("Team")}: {roleLabel(staffRole)}</span>}
            {data.block && <span className="badge bad">{t("Blocked")}</span>}
          </div>
        </div>
        {data.block && (
          <div className="notice bad section">
            <b>{t("Access is blocked")}</b> · {fmtDate(data.block.created_at)}{data.block.admin_name ? ` · ${data.block.admin_name}` : ""}
            <div>{t("Reason")}: {data.block.reason}</div>
            {data.block.note && <div className="small">{t("Note")}: {data.block.note}</div>}
            <div className="small">{t("Generations, purchases, the API and the bot are closed for this person on every linked account; they see the reason and can contact support.")}</div>
          </div>
        )}
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
          {can("messages.send") && <button className="btn" onClick={() => setAction("message")}>{t("Write to user")}</button>}
          {can("users.ban") && (data.block
            ? <button className="btn" onClick={() => setAction("unblock")}>{t("Unblock")}</button>
            : <button className="btn danger" disabled={staffRole === "owner"} onClick={() => setAction("block")}>{t("Block")}</button>)}
          {isOwner && a.sylvex_user_id && staffRole !== "owner" && <button className="btn" onClick={() => setAction("role")}>{t("Assign role")}</button>}
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
          <button className={`tab ${tab === "history" ? "active" : ""}`} onClick={() => setTab("history")}>{t("Admin history")} ({historyCount})</button>
        </div>
        {tab === "history" && (historyCount ? (
          <div className="stack">
            {data.admin_history.length > 0 && <div className="table-wrap"><table>
              <thead><tr><th>{t("Date")}</th><th>{t("Change")}</th><th>{t("By")}</th><th>{t("Reason")}</th></tr></thead>
              <tbody>{data.admin_history.map((h) => (
                <tr key={h.id}><td className="small">{fmtDate(h.at)}</td>
                  <td><div className="cell-main">{actionLabel(h.action)}</div><div className="cell-sub">{changeSummary(h)}</div></td>
                  <td className="small">{h.actor_name || "—"}</td>
                  <td className="small">{h.reason || "—"}{h.after?.reason_code ? <div className="cell-sub">{reasonLabel(String(h.after.reason_code))}</div> : null}
                    {h.after?.note ? <div className="cell-sub">{String(h.after.note)}</div> : null}</td></tr>
              ))}</tbody>
            </table></div>}
            {data.block_history.length > 0 && <div className="table-wrap"><table>
              <thead><tr><th>{t("Blocked")}</th><th>{t("Reason")}</th><th>{t("Unblocked")}</th></tr></thead>
              <tbody>{data.block_history.map((b) => (
                <tr key={b.id}><td className="small">{fmtDate(b.created_at)}<div className="cell-sub">{b.admin_name || "—"}</div></td>
                  <td className="small">{b.reason}{b.note && <div className="cell-sub">{b.note}</div>}</td>
                  <td className="small">{b.lifted_at ? <>{fmtDate(b.lifted_at)}<div className="cell-sub">{b.lifted_by_name || "—"} · {b.lift_reason}</div></> : <span className="badge bad">{t("active")}</span>}</td></tr>
              ))}</tbody>
            </table></div>}
          </div>
        ) : <Empty>{t("No admin changes yet.")}</Empty>)}
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
            {deltaNum > 0 && <span className="small">{t("The user sees a card about the credits once, on their next visit.")}</span>}
          </div>}
          presets={GRANT_REASONS}
          onConfirm={async (reason, extra) => {
            if (!Number.isInteger(deltaNum) || deltaNum === 0) throw new Error(t("Enter a whole, non-zero number of credits."));
            await post("/api/admin/users/balance", { ...target, delta: deltaNum, reason, ...extra, source: "admin_console" });
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
          presets={GRANT_REASONS}
          onConfirm={async (reason, extra) => {
            if (!Number.isInteger(daysNum) || daysNum < 1 || daysNum > 730) throw new Error(t("Days must be between 1 and 730."));
            await post("/api/admin/users/subscription", { ...target, action: "extend", days: daysNum, plan: plan || undefined, reason, ...extra });
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
      {action === "message" && <WriteToUser target={target} onClose={() => setAction(null)} />}
      {action === "block" && (
        <ConfirmAction
          title={t("Block user")}
          confirmLabel={t("Block")}
          danger
          description={<div className="stack">
            <span>{t("The person keeps their account and data but cannot generate, buy, use the API or the bot until unblocked. Linked accounts (Telegram, email, Google, Apple) are blocked together.")}</span>
            <span className="small">{t("They are shown the reason you write below.")}</span>
          </div>}
          withNote
          onConfirm={async (reason, extra) => {
            await post("/api/admin/users/block", { ...target, reason, note: extra.note });
            toast(t("User blocked"));
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "unblock" && (
        <ConfirmAction
          title={t("Unblock user")}
          confirmLabel={t("Unblock")}
          description={data.block ? `${t("Blocked since {date}", { date: fmtDate(data.block.created_at) })}: ${data.block.reason}` : ""}
          onConfirm={async (reason) => {
            await post("/api/admin/users/unblock", { ...target, reason });
            toast(t("User unblocked"));
            reload();
          }}
          onClose={() => setAction(null)}
        />
      )}
      {action === "role" && a.sylvex_user_id && (
        <AssignRole target={{ sylvex_user_id: a.sylvex_user_id }} staff={data.staff} onClose={() => setAction(null)} onSaved={reload} />
      )}
    </div>
  );
}
