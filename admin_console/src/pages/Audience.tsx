import { FormEvent, useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtNum, Loading, Pager, useAsync } from "../ui";
import { AudienceBadges, AudienceRow, personName } from "./messaging";

// Everyone who used the Telegram bot, the Mini App or the website -
// registered SYLVEX accounts and anonymous visitors - with where they came
// from ("Website · Visitor", "Mini App · Registered", ...).
const PAGE = 50;

export default function Audience() {
  const { go, can } = useApp();
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: AudienceRow[]; total: number }>("/api/admin/audience", { source, status, query, limit: PAGE, offset }),
    [source, status, query, offset],
  );
  const submit = (e: FormEvent) => { e.preventDefault(); setOffset(0); setQuery(input.trim()); };
  const canMessage = can("messages.send") || can("broadcast.send");

  return (
    <div className="stack">
      <form className="card row" onSubmit={submit}>
        <input style={{ flex: 1, minWidth: 200 }} value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={t("Search: name, @username, email, SYLVEX ID, Telegram ID, visitor ID")} />
        <select value={source} onChange={(e) => { setOffset(0); setSource(e.target.value); }}>
          <option value="">{t("All sources")}</option><option value="telegram">Telegram</option>
          <option value="miniapp">Mini App</option><option value="website">{t("Website")}</option>
        </select>
        <select value={status} onChange={(e) => { setOffset(0); setStatus(e.target.value); }}>
          <option value="">{t("Registered and visitors")}</option><option value="registered">{t("Registered")}</option>
          <option value="visitor">{t("Visitors")}</option>
        </select>
        <button className="btn primary">{t("Search")}</button>
      </form>
      <div className="muted small">{t("Telegram and Mini App users get a SYLVEX ID automatically, so they show as Registered. Visitors are people seen without an account, e.g. anonymous website visitors (each has its own visitor ID).")}</div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (data.items.length ? (
        <div className="card">
          <div className="muted small" style={{ marginBottom: 8 }}>{t("Found: {n}", { n: fmtNum(data.total) })}</div>
          <div className="table-wrap"><table>
            <thead><tr><th>{t("User")}</th><th>{t("Source · status")}</th><th>{t("Last seen")}</th><th></th></tr></thead>
            <tbody>{data.items.map((r) => (
              <tr key={r.key} className={r.sylvex_user_id ? "clickable" : ""} onClick={() => r.sylvex_user_id && go(`users/s${r.sylvex_user_id}`)}>
                <td><div className="cell-main">{personName(r)}</div>
                  <div className="cell-sub mono">{r.sylvex_user_id ? `SYLVEX ${r.sylvex_user_id}` : r.visitor_id ? r.visitor_id : `TG ${r.telegram_id}`}
                    {r.telegram_id && r.sylvex_user_id ? ` · TG ${r.telegram_id}` : ""}{r.email ? ` · ${r.email}` : ""}</div></td>
                <td><AudienceBadges sources={r.sources} status={r.status} /></td>
                <td className="small">{fmtDate(r.last_seen || r.since)}</td>
                <td className="right">{canMessage && (
                  <button className="btn small" onClick={(e) => { e.stopPropagation(); go(`broadcast?to=${encodeURIComponent(r.key)}`); }}>✉ {t("Message")}</button>
                )}</td>
              </tr>
            ))}</tbody>
          </table></div>
          <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
        </div>
      ) : <Empty>{t("No users found.")}</Empty>)}
    </div>
  );
}
