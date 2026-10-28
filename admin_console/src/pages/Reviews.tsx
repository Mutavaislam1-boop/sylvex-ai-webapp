import { useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtNum, Identity, Kpi, Loading, Pager, useAsync } from "../ui";

// Answers to the "How do you like SYLVEX?" prompt (Mini App and website):
// the stars and the optional comment, plus how the prompt itself was met.

type Review = {
  id: number; rating: number; text: string; surface: string | null; generations: number; created_at: string;
  sylvex_user_id: string | null; telegram_id: number | null; identity: Identity | null;
};
type Summary = {
  count: number; average: number; by_rating: Record<string, number>; shows: number; closes: number; laters: number; never: number;
};

const PAGE = 30;
const grade = (n: number) => [t("Poor"), t("So-so"), t("Good"), t("Great"), t("Excellent")][n - 1] || "";
const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

function who(r: Review) {
  return r.identity?.display_name || r.identity?.username || r.identity?.email
    || (r.sylvex_user_id ? `SYLVEX ${r.sylvex_user_id}` : r.telegram_id ? `TG ${r.telegram_id}` : "—");
}

export default function Reviews() {
  const { go } = useApp();
  const [rating, setRating] = useState(0);
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Review[]; total: number; summary: Summary }>("/api/admin/reviews/list", { rating, limit: PAGE, offset }),
    [rating, offset],
  );

  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const s = data.summary;
  const top = Math.max(1, ...Object.values(s.by_rating));

  return (
    <div className="stack">
      <div className="muted small">{t("Answers to “How do you like SYLVEX?” in the Mini App and on the website.")}</div>
      <div className="grid kpis">
        <Kpi label={t("Average rating")} value={s.count ? `${s.average.toFixed(1)} ★` : "—"} sub={t("{n} reviews", { n: fmtNum(s.count) })} />
        <Kpi label={t("Prompt shown")} value={fmtNum(s.shows)} />
        <Kpi label={t("Closed with ×")} value={fmtNum(s.closes)} />
        <Kpi label={t("Remind me later")} value={fmtNum(s.laters)} />
        <Kpi label={t("Don't show again")} value={fmtNum(s.never)} />
      </div>
      <div className="card stack">
        <h3>{t("By stars")}</h3>
        {[5, 4, 3, 2, 1].map((n) => (
          <div key={n} className="bar-row review-bar">
            <span><span className="review-stars">{stars(n)}</span> <span className="muted small">{grade(n)}</span></span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${(s.by_rating[String(n)] / top) * 100}%` }} /></div>
            <span className="small">{fmtNum(s.by_rating[String(n)])}</span>
          </div>
        ))}
      </div>
      <div className="tabs" style={{ marginBottom: 0 }}>
        {[0, 5, 4, 3, 2, 1].map((n) => (
          <button key={n} className={`tab ${rating === n ? "active" : ""}`} onClick={() => { setOffset(0); setRating(n); }}>
            {n ? `${n} ★` : t("All")}
          </button>
        ))}
      </div>
      {data.items.length ? <>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("User")}</th><th>{t("Rating")}</th><th>{t("Review")}</th><th>{t("Where")}</th><th>{t("When")}</th></tr></thead>
          <tbody>{data.items.map((r) => (
            <tr key={r.id} className={r.sylvex_user_id ? "clickable" : ""} onClick={() => r.sylvex_user_id && go(`users/s${r.sylvex_user_id}`)}>
              <td>
                <div className="cell-main">{who(r)}</div>
                <div className="cell-sub">{[r.identity && r.sylvex_user_id && `SYLVEX ${r.sylvex_user_id}`, t("{n} generations", { n: fmtNum(r.generations) })].filter(Boolean).join(" · ")}</div>
              </td>
              <td><div className="review-stars">{stars(r.rating)}</div><div className="cell-sub">{grade(r.rating)}</div></td>
              <td className="small" style={{ maxWidth: 420, whiteSpace: "pre-wrap" }}>{r.text || <span className="muted">{t("No comment")}</span>}</td>
              <td className="small">{r.surface === "miniapp" ? t("Mini App") : r.surface === "website" ? t("Website") : "—"}</td>
              <td className="small">{fmtDate(r.created_at)}</td>
            </tr>
          ))}</tbody>
        </table></div>
        <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
      </> : <Empty>{t("No reviews yet.")}</Empty>}
    </div>
  );
}
