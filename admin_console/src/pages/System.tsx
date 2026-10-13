import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { ErrorNotice, fmtNum, Kpi, Loading, useAsync } from "../ui";

type Stats = {
  active_jobs: number; failed_today: number; generations_today: number; generations_total: number; generations_success: number;
  generations_failed: number; error_reports: number; online: number; admins: number;
};

async function probe(path: string) {
  const started = performance.now();
  try {
    const res = await fetch(path, { cache: "no-store" });
    return { ok: res.ok, ms: Math.round(performance.now() - started) };
  } catch {
    return { ok: false, ms: Math.round(performance.now() - started) };
  }
}

export default function System() {
  const { me, go } = useApp();
  const [checkedAt, setCheckedAt] = useState(() => new Date());
  const health = useAsync(async () => {
    const [live, ready] = await Promise.all([probe("/health/live"), probe("/health/ready")]);
    setCheckedAt(new Date());
    return { live, ready };
  }, []);
  const stats = useAsync(() => post<{ stats: Stats }>("/api/admin/dashboard"), []);
  const refresh = () => { health.reload(); stats.reload(); };
  const s = stats.data?.stats;
  const failRate = s && s.generations_total ? ((s.generations_failed / s.generations_total) * 100).toFixed(1) : "0";

  return (
    <div className="stack">
      <div className="row between">
        <span className="muted small">Checked {checkedAt.toLocaleTimeString()}</span>
        <button className="btn small" onClick={refresh}>↻ Re-check</button>
      </div>
      <div className="grid kpis">
        {health.data ? <>
          <Kpi label="API" value={health.data.live.ok ? <span className="badge good">up</span> : <span className="badge bad">down</span>} sub={`${health.data.live.ms} ms`} />
          <Kpi label="Database" value={health.data.ready.ok ? <span className="badge good">ready</span> : <span className="badge bad">not ready</span>} sub={`${health.data.ready.ms} ms`} />
        </> : <Loading />}
        {s && <>
          <Kpi label="Jobs running" value={fmtNum(s.active_jobs)} sub="queued + processing" />
          <Kpi label="Failed today" value={fmtNum(s.failed_today)} sub={`of ${fmtNum(s.generations_today)} today`} />
          <Kpi label="All-time failure rate" value={`${failRate}%`} sub={`${fmtNum(s.generations_failed)} failed`} />
          <Kpi label="Open error reports" value={fmtNum(s.error_reports)} />
          <Kpi label="Users online" value={fmtNum(s.online)} sub="last 5 minutes" />
          <Kpi label="Active admins" value={fmtNum(s.admins)} />
        </>}
      </div>
      {stats.error && <ErrorNotice message={stats.error} onRetry={stats.reload} />}
      <div className="card">
        <h3>Your session</h3>
        <div className="idgrid">
          <div><div className="k">Role</div><div className="v">{me.admin.role}</div></div>
          <div><div className="k">Signed in via</div><div className="v">{me.session.channel === "web" ? "Browser" : "Telegram Mini App"}</div></div>
          <div><div className="k">Two-factor</div><div className="v">{me.admin.totp_enabled ? "enabled" : "not set up"}</div></div>
          <div><div className="k">Permissions</div><div className="v">{me.admin.role === "owner" ? "all" : me.admin.permissions.length}</div></div>
        </div>
      </div>
      <div className="row">
        <button className="btn" onClick={() => go("errors")}>Error log →</button>
        <button className="btn" onClick={() => go("generations")}>Generations →</button>
      </div>
    </div>
  );
}
