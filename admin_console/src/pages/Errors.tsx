import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { Empty, ErrorNotice, fmtDate, Identity, Loading, Modal, SourceBadges, StatusBadge, useAsync, userRef } from "../ui";

type ErrorRow = {
  id: number; telegram_id: number | null; sylvex_user_id: string | null; job_id: string; provider: string; model: string;
  status: string; error: string; created_at: string; mode?: string; prompt?: string; raw_error?: string; identity: Identity | null;
};

export default function Errors() {
  const { go } = useApp();
  const [tab, setTab] = useState<"auto" | "reports">("reports");
  const [open, setOpen] = useState<ErrorRow | null>(null);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: ErrorRow[] }>(tab === "auto" ? "/api/admin/errors" : "/api/admin/error-reports"),
    [tab],
  );

  return (
    <div className="stack">
      <div className="tabs" style={{ marginBottom: 0 }}>
        <button className={`tab ${tab === "reports" ? "active" : ""}`} onClick={() => setTab("reports")}>Reported by users</button>
        <button className={`tab ${tab === "auto" ? "active" : ""}`} onClick={() => setTab("auto")}>Automatic (provider)</button>
      </div>
      <div className="muted small">
        {tab === "reports" ? "Errors users flagged with “Report error” in the app — latest 100." : "Generation failures logged by the server — latest 100."}
      </div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (data.items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>User</th><th>Tool / model</th><th>Error</th><th>Status</th></tr></thead>
          <tbody>{data.items.map((e) => (
            <tr key={e.id} className="clickable" onClick={() => setOpen(e)}>
              <td className="small">{fmtDate(e.created_at)}</td>
              <td><div className="cell-main">{e.identity?.display_name || e.identity?.username || "—"}</div><SourceBadges identity={e.identity} /></td>
              <td className="small">{e.mode || e.provider}<div className="cell-sub">{e.model}</div></td>
              <td className="small" style={{ maxWidth: 380 }}>{e.error.slice(0, 160)}</td>
              <td><StatusBadge status={e.status} /></td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>No errors. 🎉</Empty>)}

      {open && (
        <Modal title={`Error #${open.id}`} onClose={() => setOpen(null)} actions={<>
          {userRef(open) && <button className="btn" onClick={() => go(`users/${userRef(open)}`)}>Open user</button>}
          <button className="btn primary" onClick={() => setOpen(null)}>Close</button>
        </>}>
          <div className="stack">
            <div className="idgrid">
              <div><div className="k">When</div><div className="v">{fmtDate(open.created_at)}</div></div>
              <div><div className="k">Provider</div><div className="v">{open.provider || "—"}</div></div>
              <div><div className="k">Model</div><div className="v">{open.model || "—"}</div></div>
              <div><div className="k">Job</div><div className="v mono small">{open.job_id || "—"}</div></div>
            </div>
            {open.prompt && <div><div className="small muted">Prompt</div><div className="small">{open.prompt}</div></div>}
            <div className="notice bad" style={{ whiteSpace: "pre-wrap" }}>{open.error || "—"}</div>
            {open.raw_error && <details><summary className="small muted">Raw provider error</summary><pre className="mono small" style={{ whiteSpace: "pre-wrap" }}>{open.raw_error}</pre></details>}
          </div>
        </Modal>
      )}
    </div>
  );
}
