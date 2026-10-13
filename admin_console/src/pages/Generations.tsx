import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, fmtDate, fmtNum, Identity, Loading, Pager, SourceBadges, StatusBadge, useAsync, userRef } from "../ui";

type Gen = {
  id: string; telegram_id: number | null; sylvex_user_id: string | null; mode: string; model: string; provider: string;
  status: string; cost: number; prompt: string; error: string; has_result: boolean; created_at: string;
  completed_at: string | null; identity: Identity | null;
};

const LIMIT = 30;
const MODES = ["", "image", "video", "music", "voice", "upscale", "retouch", "background", "expand", "lighting", "camera", "resize", "chat"];
const STATUSES = ["", "queued", "processing", "provider_processing", "completed", "failed", "cancelled"];
const ACTIVE = new Set(["queued", "processing", "provider_processing"]);

export default function Generations({ sylvexUserId }: { sylvexUserId: string }) {
  const { can, go, toast } = useApp();
  const [mode, setMode] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Gen | null>(null);
  const [recovering, setRecovering] = useState<Gen | null>(null);
  const [force, setForce] = useState(false);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Gen[]; total: number }>("/api/admin/generations", {
      mode, status, limit: LIMIT, offset, ...(sylvexUserId ? { sylvex_user_id: sylvexUserId } : {}),
    }),
    [mode, status, offset, sylvexUserId],
  );
  const setFilter = (fn: () => void) => { fn(); setOffset(0); };

  return (
    <div className="stack">
      <div className="card row">
        <select value={mode} onChange={(e) => setFilter(() => setMode(e.target.value))}>
          {MODES.map((m) => <option key={m} value={m}>{m ? t(m) : t("All tools")}</option>)}
        </select>
        <select value={status} onChange={(e) => setFilter(() => setStatus(e.target.value))}>
          {STATUSES.map((s) => <option key={s} value={s}>{s ? t(s) : t("Any status")}</option>)}
        </select>
        {sylvexUserId && <span className="badge accent">{t("User")} SYLVEX {sylvexUserId} <button className="btn small ghost" onClick={() => go("generations")}>✕</button></span>}
        <span className="spacer" />
        <button className="btn small" onClick={reload} disabled={loading}>↻ {t("Refresh")}</button>
      </div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{t("Generations: {n}", { n: fmtNum(data.total) })}</div>
          {data.items.length ? (
            <div className="table-wrap"><table>
              <thead><tr><th>{t("Date")}</th><th>{t("User")}</th><th>{t("Tool / model")}</th><th>{t("Prompt")}</th><th className="right">{t("Cost")}</th><th>{t("Status")}</th></tr></thead>
              <tbody>{data.items.map((g) => (
                <tr key={g.id} className="clickable" onClick={() => setSelected(g)}>
                  <td className="small">{fmtDate(g.created_at)}</td>
                  <td><div className="cell-main">{g.identity?.display_name || g.identity?.username || "—"}</div><SourceBadges identity={g.identity} /></td>
                  <td className="small">{t(g.mode)}<div className="cell-sub">{g.model}</div></td>
                  <td className="small" style={{ maxWidth: 320 }}>{g.prompt.slice(0, 120) || "—"}</td>
                  <td className="right">{fmtNum(g.cost)}</td>
                  <td><StatusBadge status={g.status} /></td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <Empty>{t("No generations match these filters.")}</Empty>}
          <Pager offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />
        </div>
      )}

      {selected && !recovering && (
        <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}>
          <div className="modal" role="dialog" aria-modal="true">
            <h2>{t("Generation")}</h2>
            <div className="idgrid">
              <div><div className="k">{t("Job ID")}</div><div className="v mono small">{selected.id}</div></div>
              <div><div className="k">{t("Status")}</div><div className="v"><StatusBadge status={selected.status} /></div></div>
              <div><div className="k">{t("Tool")}</div><div className="v">{t(selected.mode)}</div></div>
              <div><div className="k">{t("Model")}</div><div className="v">{selected.model}</div><div className="cell-sub">{selected.provider}</div></div>
              <div><div className="k">{t("Cost")}</div><div className="v">{fmtNum(selected.cost)}</div></div>
              <div><div className="k">{t("Created")}</div><div className="v">{fmtDate(selected.created_at)}</div></div>
              <div><div className="k">{t("Completed")}</div><div className="v">{fmtDate(selected.completed_at)}</div></div>
              <div><div className="k">{t("Result stored")}</div><div className="v">{selected.has_result ? t("yes") : t("no")}</div></div>
            </div>
            <div className="section"><div className="k small muted">{t("Prompt")}</div><div className="small">{selected.prompt || "—"}</div></div>
            {selected.error && <div className="notice bad section">{selected.error}</div>}
            <div className="modal-actions">
              {userRef(selected) && <button className="btn ghost" onClick={() => go(`users/${userRef(selected)}`)}>{t("Open user")}</button>}
              {can("generations.recover") && ACTIVE.has(selected.status) && (
                <button className="btn" onClick={() => { setForce(false); setRecovering(selected); }}>{t("Recover stuck job")}</button>
              )}
              <button className="btn primary" onClick={() => setSelected(null)}>{t("Close")}</button>
            </div>
          </div>
        </div>
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
