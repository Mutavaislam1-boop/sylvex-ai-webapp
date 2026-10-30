import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtMoneyMap, fmtNum, Identity, Kpi, Loading, Pager, SourceBadges, StatusBadge, useAsync, userRef } from "../ui";
import { reasonLabel } from "../i18n";
import { DayBars, Period, PeriodPicker } from "../charts";

type Sub = {
  id: number; telegram_id: number | null; sylvex_user_id: string | null; name: string; username: string; plan: string; plan_label: string;
  amount: number; currency: string; starts_at: string; expires_at: string; status: string; created_at: string;
  total_subscription_purchases: number; identity: Identity | null;
};
type Spender = {
  rank: number; telegram_id: number | null; sylvex_user_id: string | null; name: string; username: string; credits_bought: number;
  subscription_purchases: number; credit_purchases: number; payments_count: number; spent_by_currency: Record<string, number>;
  identity: Identity | null;
};

const LIMIT = 30;

type Finance = {
  payments: { kind: "credits" | "subscription"; currency: string; provider: string; count: number; amount: number; credits: number }[];
  revenue: Record<string, number>; refunds: { currency: string; count: number; amount: number }[];
  grants: { kind: "credits" | "subscription"; reason_code: string; count: number; credits: number }[];
  compensations: { kind: string; reason_code: string; count: number; credits: number }[];
  ai_costs: { provider: string; usd_estimate: number }[]; ai_cost_usd_estimate: number;
  credits: { sold: number; granted: number; spent: number }; buyers: number; new_buyers: number;
  days: { day: string; payments: number; grants: number }[];
};

// Real money and free grants, side by side but never mixed (read-only:
// payment, charge and refund logic stay as they are).
function FinanceOverview() {
  const [period, setPeriod] = useState<Period>({ days: 30 });
  const { data, error, loading, reload } = useAsync(() => post<Finance>("/api/admin/finance", period), [JSON.stringify(period)]);
  return (
    <div className="stack">
      <div className="card"><PeriodPicker value={period} onChange={setPeriod} /></div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && <>
        <div className="grid kpis">
          <Kpi label={t("Real revenue")} value={fmtMoneyMap(data.revenue)} sub={t("{n} payments", { n: fmtNum(data.payments.reduce((n, p) => n + p.count, 0)) })} />
          <Kpi label={t("Paying users")} value={fmtNum(data.buyers)} sub={t("new: {n}", { n: fmtNum(data.new_buyers) })} />
          <Kpi label={t("Credits sold")} value={fmtNum(data.credits.sold)} />
          <Kpi label={t("Credits granted free")} value={fmtNum(data.credits.granted)} sub={t("by admins, not money")} />
          <Kpi label={t("Credits spent on generations")} value={fmtNum(data.credits.spent)} />
          <Kpi label={t("AI costs (est.)")} value={`$${data.ai_cost_usd_estimate.toFixed(2)}`} sub={t("from the tariff")} />
        </div>
        <div className="card stack">
          <h3>{t("Payments and free grants per day")}</h3>
          <DayBars days={data.days} series={[
            { key: "payments", label: t("Real payments"), color: "var(--series-1)" },
            { key: "grants", label: t("Free admin grants"), color: "#eb6834" },
          ]} />
        </div>
        <div className="grid two">
          <div className="card stack">
            <h3>{t("Real payments")}</h3>
            {data.payments.length ? <div className="table-wrap"><table>
              <thead><tr><th>{t("Purchase")}</th><th>{t("Provider")}</th><th className="right">{t("Payments")}</th><th className="right">{t("Amount")}</th><th className="right">{t("Credits")}</th></tr></thead>
              <tbody>{data.payments.map((p, i) => (
                <tr key={i}><td>{p.kind === "subscription" ? t("Subscription") : t("Credit pack")}</td><td className="small">{p.provider}</td>
                  <td className="right">{fmtNum(p.count)}</td><td className="right">{fmtNum(p.amount)} {p.currency}</td><td className="right">{fmtNum(p.credits)}</td></tr>
              ))}</tbody>
            </table></div> : <Empty>{t("No payments in this period.")}</Empty>}
            {data.refunds.length > 0 && <div className="notice warn small">{t("Refunded payments")}: {data.refunds.map((r) => `${fmtNum(r.count)} · ${fmtNum(r.amount)} ${r.currency}`).join(", ")}</div>}
          </div>
          <div className="card stack">
            <h3>{t("Free admin grants")}</h3>
            <div className="muted small">{t("Not money: credits and subscriptions given by the team, by reason.")}</div>
            {data.grants.length ? <div className="table-wrap"><table>
              <thead><tr><th>{t("What")}</th><th>{t("Reason")}</th><th className="right">{t("Times")}</th><th className="right">{t("Credits")}</th></tr></thead>
              <tbody>{data.grants.map((g, i) => (
                <tr key={i}><td>{g.kind === "subscription" ? t("Subscription") : t("Credits")}</td><td className="small">{reasonLabel(g.reason_code)}</td>
                  <td className="right">{fmtNum(g.count)}</td><td className="right">{g.kind === "credits" ? fmtNum(g.credits) : "—"}</td></tr>
              ))}</tbody>
            </table></div> : <Empty>{t("No grants in this period.")}</Empty>}
            <div className="small"><b>{t("Compensations and refunds")}:</b> {data.compensations.length
              ? data.compensations.map((c) => `${reasonLabel(c.reason_code)} · ${fmtNum(c.count)}${c.credits ? ` · ${fmtNum(c.credits)} ⚡` : ""}`).join("; ") : "—"}</div>
          </div>
        </div>
        <div className="card stack">
          <h3>{t("AI API costs by provider (estimate)")}</h3>
          {data.ai_costs.length ? <div className="kv">{data.ai_costs.map((c) => (
            <div key={c.provider} className="kv-row"><span className="small">{c.provider}</span><span>${c.usd_estimate.toFixed(2)}</span></div>
          ))}</div> : <div className="muted small">{t("No data for this period")}</div>}
          <div className="muted small">{t("AI costs are estimated from the tariff: credits = provider cost × 1.5 × 100.")}</div>
        </div>
      </>}
    </div>
  );
}

function UserCell({ row }: { row: { name: string; username: string; identity: Identity | null; sylvex_user_id: string | null } }) {
  return (
    <>
      <div className="cell-main">{row.identity?.display_name || row.name || t("SYLVEX User")}</div>
      <div className="cell-sub">{row.sylvex_user_id ? `SYLVEX ${row.sylvex_user_id}` : ""}{row.username ? ` · @${row.username}` : ""}</div>
      <SourceBadges identity={row.identity} />
    </>
  );
}

function Subscriptions() {
  const { go } = useApp();
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Sub[]; total: number }>("/api/admin/subscribers", { limit: LIMIT, offset }),
    [offset],
  );
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  return (
    <div className="card">
      <div className="muted small" style={{ marginBottom: 8 }}>{t("Subscription purchases: {n}, newest first", { n: fmtNum(data.total) })}</div>
      {data.items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Date")}</th><th>{t("User")}</th><th>{t("Plan")}</th><th className="right">{t("Amount")}</th><th>{t("Period")}</th><th>{t("Status")}</th></tr></thead>
          <tbody>{data.items.map((s) => {
            const ref = userRef(s);
            return (
              <tr key={s.id} className={ref ? "clickable" : ""} onClick={() => ref && go(`users/${ref}`)}>
                <td className="small">{fmtDate(s.created_at)}</td>
                <td><UserCell row={s} /></td>
                <td>{s.plan_label || s.plan}<div className="cell-sub">{t("Purchases by this user: {n}", { n: s.total_subscription_purchases })}</div></td>
                <td className="right">{fmtNum(s.amount)} {s.currency}</td>
                <td className="small">{fmtDate(s.starts_at, false)} → {fmtDate(s.expires_at, false)}</td>
                <td><StatusBadge status={s.status} /></td>
              </tr>
            );
          })}</tbody>
        </table></div>
      ) : <Empty>{t("No subscriptions yet.")}</Empty>}
      <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
    </div>
  );
}

function TopSpenders() {
  const { go } = useApp();
  const { data, error, loading, reload } = useAsync(() => post<{ items: Spender[] }>("/api/admin/top-spenders", { limit: 50 }), []);
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  return (
    <div className="card">
      <div className="muted small" style={{ marginBottom: 8 }}>{t("Ranked by credits bought. Money is shown per currency.")}</div>
      {data.items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>#</th><th>{t("User")}</th><th className="right">{t("Credits bought")}</th><th>{t("Spent")}</th><th className="right">{t("Subscriptions")}</th><th className="right">{t("Credit packs")}</th></tr></thead>
          <tbody>{data.items.map((s) => {
            const ref = userRef(s);
            return (
              <tr key={s.rank} className={ref ? "clickable" : ""} onClick={() => ref && go(`users/${ref}`)}>
                <td>{s.rank}</td>
                <td><UserCell row={s} /></td>
                <td className="right">{fmtNum(s.credits_bought)}</td>
                <td className="small">{fmtMoneyMap(s.spent_by_currency)}</td>
                <td className="right">{fmtNum(s.subscription_purchases)}</td>
                <td className="right">{fmtNum(s.credit_purchases)}</td>
              </tr>
            );
          })}</tbody>
        </table></div>
      ) : <Empty>{t("No completed purchases yet.")}</Empty>}
    </div>
  );
}

export default function Payments() {
  const [tab, setTab] = useState<"finance" | "subs" | "top">("finance");
  return (
    <div>
      <div className="tabs">
        <button className={`tab ${tab === "finance" ? "active" : ""}`} onClick={() => setTab("finance")}>{t("Overview")}</button>
        <button className={`tab ${tab === "subs" ? "active" : ""}`} onClick={() => setTab("subs")}>{t("Subscriptions")}</button>
        <button className={`tab ${tab === "top" ? "active" : ""}`} onClick={() => setTab("top")}>{t("Top customers")}</button>
      </div>
      {tab === "finance" ? <FinanceOverview /> : tab === "subs" ? <Subscriptions /> : <TopSpenders />}
      <div className="muted small section">{t("A single user's payments, with charge IDs, are on their profile. Search accepts a payment or charge ID.")}</div>
    </div>
  );
}
