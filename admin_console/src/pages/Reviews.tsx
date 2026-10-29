import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, fmtNum, Identity, Kpi, Loading, Modal, Pager, useAsync } from "../ui";
import { Delivery, telegramErrorText } from "./messaging";

// Answers to the "How do you like SYLVEX?" prompt (Mini App and website):
// the stars and the optional comment, how the prompt itself was met, and
// the team's answers (they reach the person like any SYLVEX message).

type Review = {
  id: number; rating: number; text: string; surface: string | null; generations: number; created_at: string;
  sylvex_user_id: string | null; telegram_id: number | null; identity: Identity | null;
  reply: string; replied_at: string | null; replied_by_name: string | null;
};
type Summary = {
  count: number; average: number; by_rating: Record<string, number>; shows: number; closes: number; laters: number; never: number;
  by_surface: Record<string, { count: number; average: number }>; last_30_days: { count: number; average: number };
  with_comment: number; answered: number;
};
type Filters = { surface: string; with_text: string; replied: string; days: number };

const PAGE = 30;
const grade = (n: number) => [t("Poor"), t("So-so"), t("Good"), t("Great"), t("Excellent")][n - 1] || "";
const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);
const surfaceLabel = (s: string | null) => (s === "miniapp" ? t("Mini App") : s === "website" ? t("Website") : "—");

function who(r: Review) {
  return r.identity?.display_name || r.identity?.username || r.identity?.email
    || (r.sylvex_user_id ? `SYLVEX ${r.sylvex_user_id}` : r.telegram_id ? `TG ${r.telegram_id}` : "—");
}

function ReplyModal({ review, onClose, onSent }: { review: Review; onClose: () => void; onSent: () => void }) {
  const { toast } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const res = await post<{ delivery: Delivery }>("/api/admin/reviews/reply", { review_id: review.id, text: text.trim() });
      const failed = res.delivery.telegram === "failed";
      toast(failed ? `${t("Sent, but Telegram did not deliver it")}: ${telegramErrorText(res.delivery.telegram_error)}` : t("Reply sent"), failed);
      onSent();
      onClose();
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={t("Reply to review")} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose}>{t("Cancel")}</button>
      <button className="btn primary" disabled={!text.trim() || text.length > 4000 || busy} onClick={send}>{busy && <span className="spinner" />}{t("Send")}</button>
    </>}>
      <div className="stack">
        <div className="notice"><span className="review-stars">{stars(review.rating)}</span> · {who(review)}
          {review.text && <div style={{ whiteSpace: "pre-wrap", marginTop: 6 }}>{review.text}</div>}</div>
        <textarea rows={5} value={text} maxLength={4000} autoFocus onChange={(e) => setText(e.target.value)} placeholder={t("Thank them, or tell them what you fixed…")} />
        <div className="muted small">{t("The person gets it in their notification bell and from the bot, as from “SYLVEX Team”; it is also kept in their conversation.")}</div>
      </div>
    </Modal>
  );
}

export default function Reviews() {
  const { go, can } = useApp();
  const [rating, setRating] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<Filters>({ surface: "", with_text: "", replied: "", days: 0 });
  const [replying, setReplying] = useState<Review | null>(null);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Review[]; total: number; summary: Summary }>("/api/admin/reviews/list", { rating, limit: PAGE, offset, ...filters }),
    [rating, offset, filters],
  );
  const setFilter = (patch: Partial<Filters>) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };

  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const s = data.summary;
  const top = Math.max(1, ...Object.values(s.by_rating));
  const canReply = can("messages.send");

  return (
    <div className="stack">
      <div className="muted small">{t("Answers to “How do you like SYLVEX?” in the Mini App and on the website.")}</div>
      <div className="grid kpis">
        <Kpi label={t("Average rating")} value={s.count ? `${s.average.toFixed(1)} ★` : "—"} sub={t("{n} reviews", { n: fmtNum(s.count) })} />
        <Kpi label={t("Last 30 days")} value={s.last_30_days.count ? `${s.last_30_days.average.toFixed(1)} ★` : "—"} sub={t("{n} reviews", { n: fmtNum(s.last_30_days.count) })} />
        <Kpi label={t("With a comment")} value={fmtNum(s.with_comment)} sub={t("Answered: {n}", { n: fmtNum(s.answered) })} />
        {["miniapp", "website"].map((k) => (
          <Kpi key={k} label={surfaceLabel(k)} value={s.by_surface?.[k]?.count ? `${s.by_surface[k].average.toFixed(1)} ★` : "—"}
            sub={t("{n} reviews", { n: fmtNum(s.by_surface?.[k]?.count || 0) })} />
        ))}
      </div>
      <div className="grid two">
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
        <div className="card stack">
          <h3>{t("How the prompt was met")}</h3>
          <div className="kv">
            {[["Prompt shown", s.shows], ["Closed with ×", s.closes], ["Remind me later", s.laters], ["Don't show again", s.never]].map(([k, v]) => (
              <div key={String(k)} className="kv-row"><span className="muted small">{t(String(k))}</span><span>{fmtNum(v)}</span></div>
            ))}
          </div>
        </div>
      </div>
      <div className="tabs" style={{ marginBottom: 0 }}>
        {[0, 5, 4, 3, 2, 1].map((n) => (
          <button key={n} className={`tab ${rating === n ? "active" : ""}`} onClick={() => { setOffset(0); setRating(n); }}>
            {n ? `${n} ★` : t("All")}
          </button>
        ))}
      </div>
      <div className="card row">
        <select value={filters.surface} onChange={(e) => setFilter({ surface: e.target.value })}>
          <option value="">{t("All surfaces")}</option><option value="miniapp">{t("Mini App")}</option><option value="website">{t("Website")}</option>
        </select>
        <select value={filters.with_text} onChange={(e) => setFilter({ with_text: e.target.value })}>
          <option value="">{t("With or without a comment")}</option><option value="yes">{t("With a comment")}</option><option value="no">{t("Stars only")}</option>
        </select>
        <select value={filters.replied} onChange={(e) => setFilter({ replied: e.target.value })}>
          <option value="">{t("Answered or not")}</option><option value="no">{t("Not answered")}</option><option value="yes">{t("Answered")}</option>
        </select>
        <select value={filters.days} onChange={(e) => setFilter({ days: Number(e.target.value) })}>
          <option value={0}>{t("All time")}</option><option value={1}>{t("24 hours")}</option><option value={7}>{t("7 days")}</option>
          <option value={30}>{t("30 days")}</option><option value={90}>{t("90 days")}</option>
        </select>
      </div>
      {data.items.length ? <>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("User")}</th><th>{t("Rating")}</th><th>{t("Review")}</th><th>{t("Where")}</th><th>{t("When")}</th><th></th></tr></thead>
          <tbody>{data.items.map((r) => (
            <tr key={r.id}>
              <td className={r.sylvex_user_id ? "clickable" : ""} onClick={() => r.sylvex_user_id && go(`users/s${r.sylvex_user_id}`)}>
                <div className="cell-main">{who(r)}</div>
                <div className="cell-sub">{[r.identity && r.sylvex_user_id && `SYLVEX ${r.sylvex_user_id}`, t("{n} generations", { n: fmtNum(r.generations) })].filter(Boolean).join(" · ")}</div>
              </td>
              <td><div className="review-stars">{stars(r.rating)}</div><div className="cell-sub">{grade(r.rating)}</div></td>
              <td className="small" style={{ maxWidth: 420, whiteSpace: "pre-wrap" }}>
                {r.text || <span className="muted">{t("No comment")}</span>}
                {r.reply && <div className="review-reply"><b>SYLVEX Team{r.replied_by_name ? ` · ${r.replied_by_name}` : ""}</b> · {fmtDate(r.replied_at)}<div>{r.reply}</div></div>}
              </td>
              <td className="small">{surfaceLabel(r.surface)}</td>
              <td className="small">{fmtDate(r.created_at)}</td>
              <td className="right">{canReply && (r.sylvex_user_id || r.telegram_id) && (
                <button className="btn small" onClick={() => setReplying(r)}>{r.reply ? t("Reply again") : t("Reply")}</button>
              )}</td>
            </tr>
          ))}</tbody>
        </table></div>
        <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
      </> : <Empty>{t("No reviews yet.")}</Empty>}
      {replying && <ReplyModal review={replying} onClose={() => setReplying(null)} onSent={reload} />}
    </div>
  );
}
