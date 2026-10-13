import { FormEvent, useEffect, useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import Audience from "./Audience";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtNum, Identity, Loading, SourceBadges, useAsync, userRef } from "../ui";

type UserRow = {
  telegram_id: number | null; sylvex_user_id: string | null; name: string; username: string; balance?: number;
  subscription?: string; created_at?: string; subscription_until?: string | null; online?: boolean;
  view?: string; platform?: string; last_seen?: string; identity: Identity | null;
};

const SOURCES = [
  { key: "", label: "All sources" },
  { key: "telegram", label: "Telegram" },
  { key: "website", label: "Website" },
] as const;

function matchesSource(row: UserRow, source: string) {
  if (!source) return true;
  const l = row.identity?.linked;
  if (source === "telegram") return !!l?.telegram;
  return !!(l?.email || l?.google || l?.apple || row.identity?.account_origin === "website");
}

export default function Users({ query }: { query: string }) {
  const { go } = useApp();
  const [tab, setTab] = useState<"search" | "online" | "audience">("search");
  const [input, setInput] = useState(query);
  const [q, setQ] = useState(query);
  const [source, setSource] = useState("");
  const [windowMinutes, setWindowMinutes] = useState(30);
  useEffect(() => { setInput(query); setQ(query); setTab("search"); }, [query]);

  const { data, error, loading, reload } = useAsync(
    () => tab === "audience" ? Promise.resolve({ items: [] as UserRow[] })
      : tab === "search"
      ? post<{ items: UserRow[] }>("/api/admin/users/search", { query: q, limit: 100 })
      : post<{ items: UserRow[] }>("/api/admin/users/online", { limit: 200, window_minutes: windowMinutes }),
    [tab, q, windowMinutes],
  );
  const submit = (e: FormEvent) => { e.preventDefault(); setQ(input.trim()); };
  const rows = (data?.items || []).filter((r) => matchesSource(r, source));

  return (
    <div className="stack">
      <div className="tabs">
        <button className={`tab ${tab === "search" ? "active" : ""}`} onClick={() => setTab("search")}>{t("All users")}</button>
        <button className={`tab ${tab === "online" ? "active" : ""}`} onClick={() => setTab("online")}>{t("Recently active")}</button>
        <button className={`tab ${tab === "audience" ? "active" : ""}`} onClick={() => setTab("audience")}>{t("Audience & visitors")}</button>
      </div>
      {tab === "audience" ? <Audience /> : <>
      <div className="card">
        <div className="row">
          {tab === "search" ? (
            <form className="row" style={{ flex: 1 }} onSubmit={submit}>
              <input style={{ flex: 1, minWidth: 200 }} value={input} onChange={(e) => setInput(e.target.value)}
                placeholder={t("SYLVEX ID, Telegram ID, email, @username, name or payment ID")} />
              <button className="btn primary">{t("Search")}</button>
            </form>
          ) : (
            <label className="row small muted">{t("Active within")}
              <select value={windowMinutes} onChange={(e) => setWindowMinutes(Number(e.target.value))}>
                <option value={5}>{t("5 minutes")}</option><option value={30}>{t("30 minutes")}</option>
                <option value={180}>{t("3 hours")}</option><option value={1440}>{t("24 hours")}</option>
              </select>
            </label>
          )}
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => <option key={s.key} value={s.key}>{t(s.label)}</option>)}
          </select>
        </div>
        {tab === "search" && !q && <div className="muted small section">{t("Showing the newest users. Search finds anyone from the bot, Mini App or website.")}</div>}
      </div>

      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{t("Users: {n}", { n: fmtNum(rows.length) })}</div>
          {rows.length ? (
            <div className="table-wrap"><table>
              <thead><tr>
                <th>{t("User")}</th><th>{t("Sources")}</th>
                {tab === "search" ? <><th className="right">{t("Balance")}</th><th>{t("Plan")}</th><th>{t("Joined")}</th></> : <><th>{t("Screen")}</th><th>{t("Platform")}</th><th>{t("Last seen")}</th></>}
              </tr></thead>
              <tbody>{rows.map((r) => {
                const ref = userRef(r);
                return (
                  <tr key={ref || r.name} className={ref ? "clickable" : ""} onClick={() => ref && go(`users/${ref}`)}>
                    <td>
                      <div className="cell-main">{r.online && <span className="dot on" title={t("Online")} style={{ marginRight: 6 }} />}{r.identity?.display_name || r.name || t("SYLVEX User")}</div>
                      <div className="cell-sub">
                        {r.sylvex_user_id ? `SYLVEX ${r.sylvex_user_id}` : t("no SYLVEX ID")}
                        {r.username ? ` · @${r.username}` : ""}{r.identity?.email ? ` · ${r.identity.email}` : ""}
                      </div>
                    </td>
                    <td><SourceBadges identity={r.identity} /></td>
                    {tab === "search" ? <>
                      <td className="right">{fmtNum(r.balance)}</td>
                      <td>{r.subscription_until ? <span className="badge good">{r.subscription}</span> : <span className="badge">{t("free")}</span>}
                        {r.subscription_until && <div className="cell-sub">{t("until {date}", { date: fmtDate(r.subscription_until, false) })}</div>}</td>
                      <td className="small">{fmtDate(r.created_at, false)}</td>
                    </> : <>
                      <td className="small">{r.view || "—"}</td>
                      <td className="small">{r.platform || "—"}</td>
                      <td className="small">{fmtDate(r.last_seen)}</td>
                    </>}
                  </tr>
                );
              })}</tbody>
            </table></div>
          ) : <Empty>{t("No users found.")}</Empty>}
        </div>
      )}
      </>}
    </div>
  );
}
