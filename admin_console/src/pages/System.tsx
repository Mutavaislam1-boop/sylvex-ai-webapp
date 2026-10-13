import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { channelLabel, locale, roleLabel, t } from "../i18n";
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
        <span className="muted small">{t("Checked at {time}", { time: checkedAt.toLocaleTimeString(locale()) })}</span>
        <button className="btn small" onClick={refresh}>↻ {t("Re-check")}</button>
      </div>
      <div className="grid kpis">
        {health.data ? <>
          <Kpi label="API" value={health.data.live.ok ? <span className="badge good">{t("up")}</span> : <span className="badge bad">{t("down")}</span>} sub={t("{n} ms", { n: health.data.live.ms })} />
          <Kpi label={t("Database")} value={health.data.ready.ok ? <span className="badge good">{t("ready")}</span> : <span className="badge bad">{t("not ready")}</span>} sub={t("{n} ms", { n: health.data.ready.ms })} />
        </> : <Loading />}
        {s && <>
          <Kpi label={t("Jobs running")} value={fmtNum(s.active_jobs)} sub={t("queued + processing")} />
          <Kpi label={t("Failed today")} value={fmtNum(s.failed_today)} sub={t("of {n} today", { n: fmtNum(s.generations_today) })} />
          <Kpi label={t("All-time failure rate")} value={`${failRate}%`} sub={t("failed: {n}", { n: fmtNum(s.generations_failed) })} />
          <Kpi label={t("Error reports")} value={fmtNum(s.error_reports)} />
          <Kpi label={t("Users online")} value={fmtNum(s.online)} sub={t("last 5 minutes")} />
          <Kpi label={t("Active admins")} value={fmtNum(s.admins)} />
        </>}
      </div>
      {stats.error && <ErrorNotice message={stats.error} onRetry={stats.reload} />}
      <div className="card">
        <h3>{t("Your session")}</h3>
        <div className="idgrid">
          <div><div className="k">{t("Role")}</div><div className="v">{roleLabel(me.admin.role)}</div></div>
          <div><div className="k">{t("Signed in via")}</div><div className="v">{channelLabel(me.session.channel)}</div></div>
          <div><div className="k">{t("Two-factor")}</div><div className="v">{me.admin.totp_enabled ? t("enabled") : t("not set up")}</div></div>
          <div><div className="k">{t("Permissions")}</div><div className="v">{me.admin.role === "owner" ? t("all") : me.admin.permissions.length}</div></div>
        </div>
      </div>
      <div className="row">
        <button className="btn" onClick={() => go("errors")}>{t("Error log")} →</button>
        <button className="btn" onClick={() => go("generations")}>{t("Generations")} →</button>
      </div>
    </div>
  );
}
