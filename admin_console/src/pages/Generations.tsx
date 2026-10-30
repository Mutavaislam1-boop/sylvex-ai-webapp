import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, fmtDate, fmtNum, Identity, Kpi, Loading, Pager, SourceBadges, StatusBadge, useAsync, userRef } from "../ui";
import { DayBars, Period, PeriodPicker, RankBars } from "../charts";

// Generations: the overview (counts, errors by stage, model, provider and
// platform, durations) and the jobs, each with the stages it really went
// through and its technical log (services/generation_admin.py).

type Gen = {
  id: string; telegram_id: number | null; sylvex_user_id: string | null; mode: string; model: string; provider: string;
  status: string; cost: number; prompt: string; error: string; has_result: boolean; created_at: string;
  completed_at: string | null; identity: Identity | null; platform: string;
};
type Group = { key: string; total: number; completed: number; failed: number; avg_seconds: number | null };
type Stats = {
  total: number; completed: number; failed: number; avg_seconds: number | null;
  days: { day: string; total: number; completed: number; failed: number }[];
  by_model: Group[]; by_provider: Group[]; by_mode: Group[]; by_platform: Group[];
  failed_by_stage: { key: string; count: number }[]; stage_seconds: { key: string; avg_seconds: number }[];
};
type Stage = { key: string; state: "done" | "failed" | "running" | "pending" | "skipped"; at: number | null; seconds: number | null; detail: string };
type Detail = {
  id: string; status: string; failed_stage: string; reason: string; stages: Stage[]; identity: Identity | null;
  log: Record<string, string | number | null | Record<string, number>>;
};
type Filters = { mode: string; status: string; model: string; provider: string; platform: string };

const LIMIT = 30;
const MODES = ["", "image", "video", "music", "voice", "upscale", "retouch", "background", "expand", "lighting", "camera", "resize", "chat"];
const STATUSES = ["", "queued", "processing", "provider_processing", "completed", "failed", "cancelled"];
const ACTIVE = new Set(["queued", "processing", "provider_processing"]);
const STAGE_LABELS: Record<string, string> = {
  received: "Received by SYLVEX",
  checked: "Parameters and balance checked",
  sent: "Sent to the AI provider",
  accepted: "Accepted by the provider",
  processing: "AI is processing",
  result: "Result received",
  stored: "File saved to R2",
  ready: "Ready to download",
};
const PLATFORM_LABELS: Record<string, string> = {
  website: "Website",
  browser_miniapp: "Browser Mini App",
  telegram_miniapp: "Telegram Mini App",
  bot: "Telegram bot",
};
const LOG_LABELS: Record<string, string> = {
  job_id: "Job ID",
  user_id: "User ID",
  source: "Started from",
  platform: "Platform",
  mode: "Generation type",
  model: "Model",
  provider: "Provider",
  provider_model: "Provider model",
  current_stage: "Current / last stage",
  error_code: "Error code",
  technical_message: "Technical message",
  external_task_id: "External task ID",
  attempts: "Attempts",
  duration_seconds: "Duration, s",
  storage: "Result storage",
  storage_error: "Storage error",
  storage_attempts: "Storage attempts",
};
const STORAGE_LABELS: Record<string, string> = {
  done: "Saved",
  failed: "Not saved",
  running: "Saving",
  pending: "Not saved yet",
  not_needed: "Not needed (text result)",
};
const platformName = (p: string) => (p && p !== "—" ? t(PLATFORM_LABELS[p] || p) : t("Not recorded"));
const stageName = (k: string) => t(STAGE_LABELS[k] || k);
const secs = (n: number | null | undefined) => (n == null ? "—" : n < 90 ? `${fmtNum(Math.round(n * 10) / 10)} ${t("s")}` : `${fmtNum(Math.round(n / 6) / 10)} ${t("min")}`);
const clock = (epoch: number | null) => (epoch ? new Date(epoch * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "");

function Timeline({ stages }: { stages: Stage[] }) {
  const icon = { done: "✓", failed: "✕", running: "…", pending: "", skipped: "–" };
  return (
    <div className="timeline">
      {stages.map((s, i) => (
        <div key={s.key} className={`tl-step ${s.state}`}>
          <span className="tl-dot">{icon[s.state] || i + 1}</span>
          <div>
            <div className="small" style={{ fontWeight: s.state === "failed" ? 700 : 500 }}>{stageName(s.key)}</div>
            <div className="muted small">
              {s.state === "failed" ? t("The error happened at this stage")
                : s.state === "running" ? t("In progress")
                  : s.state === "skipped" ? t("Not needed for this result")
                    : s.state === "done" && !s.at ? t("Confirmed by a later stage (time not recorded)")
                      : s.state === "pending" ? t("Not reached") : ""}
              {s.detail && ` · ${s.detail}`}
            </div>
          </div>
          <div className="tl-time">{clock(s.at)}{s.seconds != null && s.state === "done" && <div>+{secs(s.seconds)}</div>}</div>
        </div>
      ))}
    </div>
  );
}

function JobCard({ gen, onClose, onRecover }: { gen: Gen; onClose: () => void; onRecover: () => void }) {
  const { can, go } = useApp();
  const { data, error } = useAsync(() => post<{ item: Detail }>("/api/admin/generations/detail", { id: gen.id }), [gen.id]);
  const d = data?.item;
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal wide" role="dialog" aria-modal="true">
        <h2>{t("Generation")}</h2>
        <div className="idgrid">
          <div><div className="k">{t("Status")}</div><div className="v"><StatusBadge status={gen.status} /></div></div>
          <div><div className="k">{t("Tool")}</div><div className="v">{t(gen.mode)}</div></div>
          <div><div className="k">{t("Model")}</div><div className="v">{gen.model || "—"}</div><div className="cell-sub">{gen.provider}</div></div>
          <div><div className="k">{t("Platform")}</div><div className="v">{platformName(gen.platform)}</div></div>
          <div><div className="k">{t("Cost")}</div><div className="v">{fmtNum(gen.cost)}</div></div>
          <div><div className="k">{t("Created")}</div><div className="v">{fmtDate(gen.created_at)}</div></div>
        </div>
        {error ? <ErrorNotice message={error} /> : !d ? <Loading /> : <>
          {d.failed_stage && <div className="notice bad section"><b>{t("Failed at: {stage}", { stage: stageName(d.failed_stage) })}</b><div>{d.reason}</div></div>}
          <div className="section"><h3>{t("Stages")}</h3><Timeline stages={d.stages} /></div>
          <details className="techlog section">
            <summary>{t("Technical log")}</summary>
            <div className="kv">
              {Object.entries(LOG_LABELS).map(([k, label]) => {
                const v = d.log[k];
                if (v === "" || v == null) return null;
                const shown = k === "current_stage" ? stageName(String(v)) : k === "platform" ? platformName(String(v)) : k === "storage" ? t(STORAGE_LABELS[String(v)] || String(v)) : String(v);
                return <div key={k} className="kv-row"><span className="muted small">{t(label)}</span><span className={k.endsWith("_id") || k === "technical_message" ? "mono small" : "small"}>{shown}</span></div>;
              })}
            </div>
          </details>
        </>}
        <div className="section"><div className="k small muted">{t("Prompt")}</div><div className="small">{gen.prompt || "—"}</div></div>
        <div className="modal-actions">
          {userRef(gen) && <button className="btn ghost" onClick={() => go(`users/${userRef(gen)}`)}>{t("Open user")}</button>}
          {can("generations.recover") && ACTIVE.has(gen.status) && <button className="btn" onClick={onRecover}>{t("Recover stuck job")}</button>}
          <button className="btn primary" onClick={onClose}>{t("Close")}</button>
        </div>
      </div>
    </div>
  );
}

function Overview({ query }: { query: Record<string, unknown> }) {
  const { data, error, loading, reload } = useAsync(() => post<Stats>("/api/admin/generations/stats", query), [JSON.stringify(query)]);
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const rank = (rows: Group[], name: (k: string) => string = (k) => k) => rows.filter((r) => r.failed).sort((a, b) => b.failed - a.failed)
    .map((r) => ({ key: r.key, label: name(r.key), value: r.failed, note: `${Math.round((r.failed / r.total) * 100)}%`, tone: "bad" as const }));
  return (
    <div className="stack">
      <div className="grid kpis">
        <Kpi label={t("Generations")} value={fmtNum(data.total)} />
        <Kpi label={t("Successful")} value={fmtNum(data.completed)} sub={data.total ? `${Math.round((data.completed / data.total) * 100)}%` : undefined} />
        <Kpi label={t("Failed")} value={fmtNum(data.failed)} sub={data.total ? `${Math.round((data.failed / data.total) * 100)}%` : undefined} />
        <Kpi label={t("Average generation time")} value={secs(data.avg_seconds)} />
      </div>
      <div className="card stack">
        <h3>{t("Generations per day")}</h3>
        <DayBars days={data.days} series={[
          { key: "completed", label: t("Successful"), color: "var(--series-1)" },
          { key: "failed", label: t("Failed"), color: "var(--status-bad)" },
        ]} />
      </div>
      <div className="grid two">
        <div className="card stack"><h3>{t("Errors by stage")}</h3>
          <RankBars rows={data.failed_by_stage.map((r) => ({ key: r.key, label: stageName(r.key), value: r.count, tone: "bad" as const }))} empty={t("No errors in this period")} /></div>
        <div className="card stack"><h3>{t("Average time of each stage")}</h3>
          <RankBars rows={data.stage_seconds.filter((r) => r.key !== "received").map((r) => ({ key: r.key, label: stageName(r.key), value: r.avg_seconds }))} format={secs} /></div>
        <div className="card stack"><h3>{t("Errors by model")}</h3><RankBars rows={rank(data.by_model)} empty={t("No errors in this period")} /></div>
        <div className="card stack"><h3>{t("Errors by provider")}</h3><RankBars rows={rank(data.by_provider)} empty={t("No errors in this period")} /></div>
        <div className="card stack"><h3>{t("Generations by model")}</h3>
          <RankBars rows={data.by_model.map((r) => ({ key: r.key, label: r.key, value: r.total, note: secs(r.avg_seconds) }))} /></div>
        <div className="card stack"><h3>{t("Generations by platform")}</h3>
          <RankBars rows={data.by_platform.map((r) => ({ key: r.key, label: platformName(r.key), value: r.total }))} /></div>
      </div>
    </div>
  );
}

export default function Generations({ sylvexUserId }: { sylvexUserId: string }) {
  const { go, toast } = useApp();
  const [tab, setTab] = useState<"overview" | "jobs">(sylvexUserId ? "jobs" : "overview");
  const [period, setPeriod] = useState<Period>({ days: 7 });
  const [f, setF] = useState<Filters>({ mode: "", status: "", model: "", provider: "", platform: "" });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Gen | null>(null);
  const [recovering, setRecovering] = useState<Gen | null>(null);
  const [force, setForce] = useState(false);
  const query = { ...period, ...f, ...(sylvexUserId ? { sylvex_user_id: sylvexUserId } : {}) };
  // Models and providers that actually ran in this period, for the filters.
  const options = useAsync(() => post<Stats>("/api/admin/generations/stats", { ...period }), [JSON.stringify(period)]);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Gen[]; total: number }>("/api/admin/generations", { ...query, limit: LIMIT, offset }),
    [JSON.stringify(query), offset, tab],
  );
  const set = (patch: Partial<Filters>) => { setOffset(0); setF((x) => ({ ...x, ...patch })); };

  return (
    <div className="stack">
      <div className="tabs" style={{ marginBottom: 0 }}>
        <button className={`tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>{t("Overview")}</button>
        <button className={`tab ${tab === "jobs" ? "active" : ""}`} onClick={() => setTab("jobs")}>{t("Jobs")}</button>
      </div>
      <div className="card stack" style={{ gap: 10 }}>
        <PeriodPicker value={period} onChange={(p) => { setOffset(0); setPeriod(p); }} />
        <div className="row">
          <select value={f.mode} onChange={(e) => set({ mode: e.target.value })}>
            {MODES.map((m) => <option key={m} value={m}>{m ? t(m) : t("All tools")}</option>)}
          </select>
          <select value={f.model} onChange={(e) => set({ model: e.target.value })}>
            <option value="">{t("All models")}</option>
            {(options.data?.by_model || []).filter((m) => m.key !== "—").map((m) => <option key={m.key} value={m.key}>{m.key}</option>)}
          </select>
          <select value={f.provider} onChange={(e) => set({ provider: e.target.value })}>
            <option value="">{t("All providers")}</option>
            {(options.data?.by_provider || []).filter((m) => m.key !== "—").map((m) => <option key={m.key} value={m.key}>{m.key}</option>)}
          </select>
          <select value={f.platform} onChange={(e) => set({ platform: e.target.value })}>
            <option value="">{t("All platforms")}</option>
            {Object.keys(PLATFORM_LABELS).filter((k) => k !== "bot").map((k) => <option key={k} value={k}>{platformName(k)}</option>)}
          </select>
          {tab === "jobs" && (
            <select value={f.status} onChange={(e) => set({ status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s ? t(s) : t("Any status")}</option>)}
            </select>
          )}
          {sylvexUserId && <span className="badge accent">{t("User")} SYLVEX {sylvexUserId} <button className="btn small ghost" onClick={() => go("generations")}>✕</button></span>}
          <span className="spacer" />
          {tab === "jobs" && <button className="btn small" onClick={reload} disabled={loading}>↻ {t("Refresh")}</button>}
        </div>
      </div>
      {tab === "overview" ? <Overview query={query} /> : error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{t("Generations: {n}", { n: fmtNum(data.total) })}</div>
          {data.items.length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>{t("Date")}</th><th>{t("User")}</th><th>{t("Tool / model")}</th><th>{t("Platform")}</th><th>{t("Prompt")}</th><th className="right">{t("Cost")}</th><th>{t("Status")}</th></tr></thead>
              <tbody>{data.items.map((g) => (
                <tr key={g.id} className="clickable" onClick={() => setSelected(g)}>
                  <td className="small">{fmtDate(g.created_at)}</td>
                  <td><div className="cell-main">{g.identity?.display_name || g.identity?.username || "—"}</div><SourceBadges identity={g.identity} /></td>
                  <td className="small">{t(g.mode)}<div className="cell-sub">{g.model}</div></td>
                  <td className="small">{platformName(g.platform)}</td>
                  <td className="small" style={{ maxWidth: 320 }}>{g.prompt.slice(0, 120) || "—"}</td>
                  <td className="right">{fmtNum(g.cost)}</td>
                  <td><StatusBadge status={g.status} />{g.error && <div className="cell-sub" style={{ maxWidth: 220 }}>{g.error}</div>}</td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <Empty>{t("No generations match these filters.")}</Empty>}
          <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
        </div>
      )}

      {selected && !recovering && (
        <JobCard gen={selected} onClose={() => setSelected(null)} onRecover={() => { setForce(false); setRecovering(selected); }} />
      )}
      {recovering && (
        <ConfirmAction
          title={t("Recover generation job")}
          confirmLabel={t("Recover")}
          needReason={false}
          description={<div className="stack">
            <span>{t("Finalises the stuck job and refunds the user when it cannot complete. By default only jobs past the stale threshold are recovered.")} <span className="mono">{recovering.id}</span></span>
            <label className="row small"><input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> {t("Force, even if the job is not stale yet")}</label>
          </div>}
          onConfirm={async () => {
            const res = await post(`/api/admin/prostudio/recover-job/${encodeURIComponent(recovering.id)}`, { force });
            toast(res.recovered ? t("Job recovered") : t("Not recovered: {reason}", { reason: String(res.reason || "unknown") }), !res.recovered);
            setSelected(null);
            reload();
          }}
          onClose={() => setRecovering(null)}
        />
      )}
    </div>
  );
}
