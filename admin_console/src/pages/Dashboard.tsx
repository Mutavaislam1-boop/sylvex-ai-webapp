import { post } from "../api";
import { useApp } from "../state";
import { Empty, ErrorNotice, fmtDate, fmtMoneyMap, fmtNum, Identity, Kpi, Loading, SourceBadges, useAsync, userRef } from "../ui";

type Stats = {
  users: number; balance: number; visited: number; subscriptions: number; subscriptions_total: number;
  generations_today: number; generations_total: number; generations_success: number; generations_failed: number;
  failed_today: number; active_jobs: number; purchases_total: number; revenue_by_currency: Record<string, number>;
  credits_purchased_total: number; error_reports: number; new_users_today: number; online: number; admins: number;
};
type Tool = { type: string; total: number; today: number };
type RecentError = { id: number; telegram_id: number | null; sylvex_user_id: string | null; provider: string; model: string; status: string; error: string; created_at: string; identity: Identity | null };

export default function Dashboard() {
  const { go } = useApp();
  const { data, error, loading, reload } = useAsync(
    () => post<{ stats: Stats; tools: Tool[]; recent_errors: RecentError[] }>("/api/admin/dashboard"),
    [],
  );
  if (loading && !data) return <Loading />;
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (!data) return null;
  const s = data.stats;
  const successRate = s.generations_total ? Math.round((s.generations_success / s.generations_total) * 100) : 0;
  const maxTool = Math.max(1, ...data.tools.map((t) => t.total));

  return (
    <div className="stack">
      <div className="row between">
        <span className="muted small">Live figures across Telegram Bot, Mini App and Website.</span>
        <button className="btn small" onClick={reload} disabled={loading}>{loading ? <span className="spinner" /> : "↻"} Refresh</button>
      </div>
      <div className="grid kpis">
        <Kpi label="Users" value={fmtNum(s.users)} sub={`+${fmtNum(s.new_users_today)} in 24h`} />
        <Kpi label="Online now" value={fmtNum(s.online)} sub={`${fmtNum(s.visited)} ever opened the app`} />
        <Kpi label="Active subscriptions" value={fmtNum(s.subscriptions)} sub={`${fmtNum(s.subscriptions_total)} purchased in total`} />
        <Kpi label="Generations today" value={fmtNum(s.generations_today)} sub={`${fmtNum(s.failed_today)} failed · ${fmtNum(s.active_jobs)} running`} />
        <Kpi label="Generations total" value={fmtNum(s.generations_total)} sub={`${successRate}% success`} />
        <Kpi label="Purchases" value={fmtNum(s.purchases_total)} sub={`${fmtNum(s.credits_purchased_total)} credits bought`} />
        <Kpi label="Credits on balances" value={fmtNum(s.balance)} />
        <Kpi label="Error reports" value={fmtNum(s.error_reports)} sub={`${fmtNum(s.admins)} active admins`} />
      </div>

      <div className="grid two">
        <div className="card">
          <h3>Revenue by currency</h3>
          <div className="muted small" style={{ marginBottom: 10 }}>Completed purchases. Currencies are never summed together.</div>
          {Object.keys(s.revenue_by_currency || {}).length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>Currency</th><th className="right">Amount</th></tr></thead>
              <tbody>{Object.entries(s.revenue_by_currency).map(([cur, amount]) => (
                <tr key={cur}><td>{cur}</td><td className="right">{fmtNum(amount)}</td></tr>
              ))}</tbody>
            </table></div>
          ) : <Empty>No completed purchases yet.</Empty>}
          <div className="muted small section">Total: {fmtMoneyMap(s.revenue_by_currency)}</div>
        </div>

        <div className="card">
          <h3>Generations by tool</h3>
          {data.tools.length ? (
            <div className="bars">
              {data.tools.map((t) => (
                <div className="bar-row" key={t.type}>
                  <span>{t.type}</span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${(t.total / maxTool) * 100}%` }} /></div>
                  <span className="small muted">{fmtNum(t.total)} · {fmtNum(t.today)} today</span>
                </div>
              ))}
            </div>
          ) : <Empty>No generations yet.</Empty>}
        </div>
      </div>

      <div className="card">
        <div className="row between"><h3>Recent errors</h3><button className="btn small ghost" onClick={() => go("errors")}>All errors →</button></div>
        {data.recent_errors.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>When</th><th>User</th><th>Provider / model</th><th>Error</th></tr></thead>
            <tbody>{data.recent_errors.map((e) => {
              const ref = userRef(e);
              return (
                <tr key={e.id} className={ref ? "clickable" : ""} onClick={() => ref && go(`users/${ref}`)}>
                  <td className="small">{fmtDate(e.created_at)}</td>
                  <td><div className="cell-main">{e.identity?.display_name || e.identity?.username || "—"}</div><SourceBadges identity={e.identity} /></td>
                  <td className="small">{e.provider || "—"}<div className="cell-sub">{e.model}</div></td>
                  <td className="small">{e.error}</td>
                </tr>
              );
            })}</tbody>
          </table></div>
        ) : <Empty>No recent errors.</Empty>}
      </div>
    </div>
  );
}
