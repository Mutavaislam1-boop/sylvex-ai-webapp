import { FormEvent, useEffect, useState } from "react";
import { errorText, get } from "../api";
import { useApp } from "../state";
import { actionLabel, channelLabel, t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, Loading, Modal } from "../ui";

type Event = {
  id: number; at: string; actor_admin_id: number | null; actor_sylvex_user_id: string | null; channel: string; action: string;
  risk: string; target_sylvex_user_id: string | null; reason: string; before: unknown; after: unknown;
  section: string; result: "done" | "failed"; object: string;
};
type Filters = { target: string; action: string; risk: string; actor: string; section: string; from: string; to: string };

const SECTION_LABELS: Record<string, string> = {
  users: "Users",
  finance: "Credits and subscriptions",
  staff: "Staff and permissions",
  content: "Media and content",
  models: "Models",
  messages: "Messages",
  generations: "Generations",
  security: "Sign-in and security",
  other: "Other",
};

const RISK_TONE: { [k: string]: string } = { low: "", medium: "accent", high: "warn", critical: "bad" };

export default function Audit({ target }: { target: string }) {
  const { go } = useApp();
  const [draft, setDraft] = useState<Filters>({ target, action: "", risk: "", actor: "", section: "", from: "", to: "" });
  const [filters, setFilters] = useState<Filters>(draft);
  const [items, setItems] = useState<Event[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Event | null>(null);

  const load = async (before?: number) => {
    setLoading(true);
    setError("");
    const q = new URLSearchParams({ limit: "50" });
    if (filters.target.trim()) q.set("target_sylvex_user_id", filters.target.trim());
    if (filters.action.trim()) q.set("action", filters.action.trim());
    if (filters.risk) q.set("risk", filters.risk);
    if (filters.section) q.set("section", filters.section);
    if (filters.from) q.set("date_from", filters.from);
    if (filters.to) q.set("date_to", filters.to);
    if (/^\d+$/.test(filters.actor.trim())) q.set("actor_admin_id", filters.actor.trim());
    if (before) q.set("before_id", String(before));
    try {
      const res = await get<{ items: Event[]; next_before_id: number | null }>(`/api/admin/v2/audit?${q}`);
      setItems((list) => (before ? [...list, ...res.items] : res.items));
      setNext(res.next_before_id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { setDraft((d) => ({ ...d, target })); setFilters((f) => ({ ...f, target })); }, [target]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filters]);
  const apply = (e: FormEvent) => { e.preventDefault(); setFilters({ ...draft }); };

  return (
    <div className="stack">
      <form className="card row" onSubmit={apply}>
        <input style={{ width: 170 }} value={draft.target} onChange={(e) => setDraft({ ...draft, target: e.target.value })} placeholder={t("Target SYLVEX ID")} />
        <input style={{ width: 190 }} value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })} placeholder={t("Action, e.g. balance_changed")} />
        <input style={{ width: 120 }} value={draft.actor} onChange={(e) => setDraft({ ...draft, actor: e.target.value })} placeholder={t("Admin ID")} />
        <select value={draft.risk} onChange={(e) => setDraft({ ...draft, risk: e.target.value })}>
          <option value="">{t("Any risk")}</option><option value="low">{t("low")}</option><option value="medium">{t("medium")}</option><option value="high">{t("high")}</option><option value="critical">{t("critical")}</option>
        </select>
        <select value={draft.section} onChange={(e) => setDraft({ ...draft, section: e.target.value })}>
          <option value="">{t("All sections")}</option>
          {Object.keys(SECTION_LABELS).filter((k) => k !== "other").map((k) => <option key={k} value={k}>{t(SECTION_LABELS[k])}</option>)}
        </select>
        <input type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} aria-label={t("From")} />
        <input type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} aria-label={t("To")} />
        <button className="btn primary">{t("Apply")}</button>
      </form>
      <div className="muted small">{t("Append-only record of every admin action. Entries cannot be edited or deleted.")}</div>
      {error && <ErrorNotice message={error} onRetry={() => load()} />}
      {loading && !items.length ? <Loading /> : items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>{t("When")}</th><th>{t("Section")}</th><th>{t("Action")}</th><th>{t("Risk")}</th><th>{t("Admin")}</th><th>{t("Object")}</th><th>{t("Reason")}</th><th>{t("Result")}</th></tr></thead>
          <tbody>{items.map((e) => (
            <tr key={e.id} className="clickable" onClick={() => setOpen(e)}>
              <td className="small">{fmtDate(e.at)}</td>
              <td className="small">{t(SECTION_LABELS[e.section] || e.section)}</td>
              <td>{actionLabel(e.action)}<div className="cell-sub"><span className="mono">{e.action}</span> · {channelLabel(e.channel)}</div></td>
              <td><span className={`badge ${RISK_TONE[e.risk] || ""}`}>{t(e.risk)}</span></td>
              <td className="small">{e.actor_sylvex_user_id ? `SYLVEX ${e.actor_sylvex_user_id}` : t("system")}{e.actor_admin_id ? <div className="cell-sub">{t("admin")} #{e.actor_admin_id}</div> : null}</td>
              <td className="small">{e.target_sylvex_user_id ? `SYLVEX ${e.target_sylvex_user_id}` : ""}{e.object && <div className="cell-sub">{e.object}</div>}{!e.target_sylvex_user_id && !e.object && "—"}</td>
              <td className="small" style={{ maxWidth: 260 }}>{e.reason || "—"}</td>
              <td><span className={`badge ${e.result === "failed" ? "bad" : "good"}`}>{e.result === "failed" ? t("Failed") : t("Done")}</span></td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : !error && <Empty>{t("No audit events match.")}</Empty>}
      {next && <div className="row" style={{ justifyContent: "center" }}><button className="btn" disabled={loading} onClick={() => load(next)}>{loading && <span className="spinner" />}{t("Load older")}</button></div>}

      {open && (
        <Modal title={t("Audit event #{id}", { id: open.id })} onClose={() => setOpen(null)} actions={<>
          {open.target_sylvex_user_id && <button className="btn" onClick={() => go(`users/s${open.target_sylvex_user_id}`)}>{t("Open target user")}</button>}
          <button className="btn primary" onClick={() => setOpen(null)}>{t("Close")}</button>
        </>}>
          <div className="stack">
            <div className="idgrid">
              <div><div className="k">{t("When")}</div><div className="v">{fmtDate(open.at)}</div></div>
              <div><div className="k">{t("Action")}</div><div className="v">{actionLabel(open.action)}</div><div className="cell-sub mono">{open.action}</div></div>
              <div><div className="k">{t("Section")}</div><div className="v">{t(SECTION_LABELS[open.section] || open.section)}</div></div>
              <div><div className="k">{t("Result")}</div><div className="v">{open.result === "failed" ? t("Failed") : t("Done")}</div></div>
              <div><div className="k">{t("Channel")}</div><div className="v">{channelLabel(open.channel)}</div></div>
              <div><div className="k">{t("Risk")}</div><div className="v">{t(open.risk)}</div></div>
            </div>
            <div><div className="small muted">{t("Reason")}</div>{open.reason || "—"}</div>
            <div className="grid two" style={{ gap: 10 }}>
              <div><div className="small muted">{t("Before")}</div><pre className="mono small notice" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(open.before, null, 2)}</pre></div>
              <div><div className="small muted">{t("After")}</div><pre className="mono small notice" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(open.after, null, 2)}</pre></div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
