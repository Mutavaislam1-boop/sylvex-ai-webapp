import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtMoneyMap, fmtNum, Identity, Loading, Pager, SourceBadges, StatusBadge, useAsync, userRef } from "../ui";

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
  const [tab, setTab] = useState<"subs" | "top">("subs");
  return (
    <div>
      <div className="tabs">
        <button className={`tab ${tab === "subs" ? "active" : ""}`} onClick={() => setTab("subs")}>{t("Subscriptions")}</button>
        <button className={`tab ${tab === "top" ? "active" : ""}`} onClick={() => setTab("top")}>{t("Top customers")}</button>
      </div>
      {tab === "subs" ? <Subscriptions /> : <TopSpenders />}
      <div className="muted small section">{t("A single user's payments, with charge IDs, are on their profile. Search accepts a payment or charge ID.")}</div>
    </div>
  );
}
