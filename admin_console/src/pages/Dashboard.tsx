import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
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
  const maxTool = Math.max(1, ...data.tools.map((tool) => tool.total));

  return (
    <div className="stack">
      <div className="row between">
        <span className="muted small">{t("Live figures across Telegram Bot, Mini App and Website.")}</span>
        <button className="btn small" onClick={reload} disabled={loading}>{loading ? <span className="spinner" /> : "↻"} {t("Refresh")}</button>
      </div>
      <div className="grid kpis">
        <Kpi label={t("Users")} value={fmtNum(s.users)} sub={t("+{n} in 24h", { n: fmtNum(s.new_users_today) })} />
        <Kpi label={t("Online now")} value={fmtNum(s.online)} sub={t("{n} ever opened the app", { n: fmtNum(s.visited) })} />
        <Kpi label={t("Active subscriptions")} value={fmtNum(s.subscriptions)} sub={t("{n} purchased in total", { n: fmtNum(s.subscriptions_total) })} />
        <Kpi label={t("Generations today")} value={fmtNum(s.generations_today)} sub={t("{failed} failed · {running} running", { failed: fmtNum(s.failed_today), running: fmtNum(s.active_jobs) })} />
        <Kpi label={t("Generations total")} value={fmtNum(s.generations_total)} sub={t("{n}% success", { n: successRate })} />
        <Kpi label={t("Purchases")} value={fmtNum(s.purchases_total)} sub={t("{n} credits bought", { n: fmtNum(s.credits_purchased_total) })} />
        <Kpi label={t("Credits on balances")} value={fmtNum(s.balance)} />
        <Kpi label={t("Error reports")} value={fmtNum(s.error_reports)} sub={t("{n} active admins", { n: fmtNum(s.admins) })} />
      </div>

      <div className="grid two">
        <div className="card">
          <h3>{t("Revenue by currency")}</h3>
          <div className="muted small" style={{ marginBottom: 10 }}>{t("Completed purchases. Currencies are never summed together.")}</div>
          {Object.keys(s.revenue_by_currency || {}).length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>{t("Currency")}</th><th className="right">{t("Amount")}</th></tr></thead>
              <tbody>{Object.entries(s.revenue_by_currency).map(([cur, amount]) => (
                <tr key={cur}><td>{cur}</td><td className="right">{fmtNum(amount)}</td></tr>
              ))}</tbody>
            </table></div>
          ) : <Empty>{t("No completed purchases yet.")}</Empty>}
          <div className="muted small section">{t("Total")}: {fmtMoneyMap(s.revenue_by_currency)}</div>
        </div>

        <div className="card">
          <h3>{t("Generations by tool")}</h3>
          {data.tools.length ? (
            <div className="bars">
              {data.tools.map((tool) => (
                <div className="bar-row" key={tool.type}>
                  <span>{t(tool.type)}</span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${(tool.total / maxTool) * 100}%` }} /></div>
                  <span className="small muted">{t("{total} · {today} today", { total: fmtNum(tool.total), today: fmtNum(tool.today) })}</span>
                </div>
              ))}
            </div>
          ) : <Empty>{t("No generations yet.")}</Empty>}
        </div>
      </div>

      <div className="card">
        <div className="row between"><h3>{t("Recent errors")}</h3><button className="btn small ghost" onClick={() => go("errors")}>{t("All errors")} →</button></div>
        {data.recent_errors.length ? (
          <div className="table-wrap"><table>
            <thead><tr><th>{t("When")}</th><th>{t("User")}</th><th>{t("Provider / model")}</th><th>{t("Error")}</th></tr></thead>
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
        ) : <Empty>{t("No recent errors.")}</Empty>}
      </div>
    </div>
  );
}
