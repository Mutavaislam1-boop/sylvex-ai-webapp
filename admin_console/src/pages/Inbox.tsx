import { useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, Identity, Loading, Pager, SourceBadges, StatusBadge, useAsync } from "../ui";
import { Composer, Draft, draftPayload, draftProblem, emptyDraft } from "./messaging";

// Messages users wrote from the internal "Contact SYLVEX" popup (Mini App or
// website). A reply is shown to the user as from "SYLVEX Team" in their
// notification bell, and sent by the bot too when they have Telegram.

type Thread = {
  id: number; account_id: number | null; visitor_id: string | null; email: string | null; topic: string; surface: string | null;
  status: string; admin_unread: boolean; created_at: string; last_message_at: string; last_message: string; last_direction: string;
  messages: number; sylvex_user_id: string | null; telegram_id: number | null; identity: Identity | null;
};
type Message = { id: number; direction: "in" | "out"; text: string; image_url: string | null; links: { url: string; label: string }[]; admin_id: number | null; created_at: string };
type Detail = {
  thread: Thread & { person: { key: string; sylvex_user_id: string | null; telegram_id: number | null; visitor_id: string | null; identity: Identity | null } };
  messages: Message[];
};

const TOPIC: Record<string, string> = { support: "Support", sales: "Sales", admin: "Administrator", general: "General" };
const SURFACE: Record<string, string> = { miniapp: "Mini App", website: "Website", telegram: "Telegram" };
const PAGE = 30;

function who(th: { identity: Identity | null; email: string | null; sylvex_user_id: string | null; visitor_id: string | null }) {
  return th.identity?.display_name || th.identity?.username || th.identity?.email || th.email
    || (th.sylvex_user_id ? `SYLVEX ${th.sylvex_user_id}` : th.visitor_id ? `${t("Visitor")} ${th.visitor_id.slice(2, 10)}` : "—");
}

function ThreadView({ id, onBack }: { id: number; onBack: () => void }) {
  const { toast, go } = useApp();
  const { data, error, loading, reload } = useAsync(() => post<Detail>("/api/admin/inbox/thread", { thread_id: id }), [id]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const th = data.thread;
  const person = th.person;
  const problem = draftProblem(draft);

  const reply = async () => {
    setBusy(true);
    try {
      const res = await post<{ telegram: boolean; telegram_sent: boolean }>("/api/admin/inbox/reply", { thread_id: id, ...draftPayload(draft) });
      toast(res.telegram ? (res.telegram_sent ? t("Reply sent: notification bell + Telegram") : t("Reply in the bell; Telegram did not accept it"))
        : t("Reply sent to the notification bell"), res.telegram && !res.telegram_sent);
      setDraft(emptyDraft());
      reload();
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  const setStatus = async (status: string) => {
    try { await post("/api/admin/inbox/status", { thread_id: id, status }); reload(); } catch (e) { toast(errorText(e), true); }
  };

  return (
    <div className="stack">
      <div className="row between">
        <button className="btn small ghost" onClick={onBack}>← {t("Inbox")}</button>
        <div className="row">
          {th.status !== "closed"
            ? <button className="btn small" onClick={() => setStatus("closed")}>{t("Close conversation")}</button>
            : <button className="btn small" onClick={() => setStatus("open")}>{t("Reopen")}</button>}
        </div>
      </div>
      <div className="card">
        <div className="row between">
          <div>
            <h3 style={{ margin: 0 }}>{who({ ...person, email: th.email })}</h3>
            <div className="muted small">{[person.sylvex_user_id && `SYLVEX ${person.sylvex_user_id}`, person.telegram_id && `TG ${person.telegram_id}`,
              th.email, person.visitor_id && `${t("Visitor")} ${person.visitor_id}`].filter(Boolean).join(" · ")}</div>
          </div>
          <div className="row">
            <span className="badge">{t(TOPIC[th.topic] || th.topic)}</span>
            {th.surface && <span className="badge">{t(SURFACE[th.surface] || th.surface)}</span>}
            <StatusBadge status={th.status} />
            <SourceBadges identity={person.identity} />
            {person.sylvex_user_id && <button className="btn small ghost" onClick={() => go(`users/s${person.sylvex_user_id}`)}>{t("Open user")} →</button>}
          </div>
        </div>
      </div>

      <div className="card stack">
        {data.messages.map((m) => (
          <div key={m.id} className={`bubble ${m.direction}`}>
            <div className="bubble-head">{m.direction === "out" ? `SYLVEX Team${m.admin_id ? ` · ${t("admin")} #${m.admin_id}` : ""}` : who({ ...person, email: th.email })} · {fmtDate(m.created_at)}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
            {m.image_url && <img src={m.image_url} alt="" style={{ maxWidth: 240, borderRadius: 8, marginTop: 6 }} />}
            {m.links.map((l, i) => <div key={i} className="small"><a href={l.url} target="_blank" rel="noopener noreferrer">🔗 {l.label || l.url}</a></div>)}
          </div>
        ))}
      </div>

      <div className="card stack">
        <h3>{t("Personal reply")}</h3>
        <div className="muted small">{person.telegram_id
          ? t("Delivered to their notification bell (Mini App and website) and by the SYLVEX bot in Telegram.")
          : t("Delivered to their notification bell on the website and in the Mini App.")}</div>
        <Composer draft={draft} onChange={setDraft} rows={4} placeholder={t("Write a reply…")} />
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary" disabled={!!problem || busy} onClick={reply}>{busy && <span className="spinner" />}{t("Send reply")}</button>
        </div>
      </div>
    </div>
  );
}

export default function Inbox() {
  const [status, setStatus] = useState("open");
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Thread[]; total: number; unread: number }>("/api/admin/inbox/list", { status, limit: PAGE, offset }),
    [status, offset, openId],
  );

  if (openId) return <ThreadView id={openId} onBack={() => setOpenId(null)} />;
  return (
    <div className="stack">
      <div className="tabs" style={{ marginBottom: 0 }}>
        {[["open", "Waiting for reply"], ["answered", "Answered"], ["closed", "Closed"], ["", "All"]].map(([key, label]) => (
          <button key={key} className={`tab ${status === key ? "active" : ""}`} onClick={() => { setOffset(0); setStatus(key); }}>{t(label)}</button>
        ))}
      </div>
      <div className="muted small">{t("Messages users sent from “Contact SYLVEX” in the Mini App or on the website.")}</div>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (data.items.length ? <>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("From")}</th><th>{t("Topic")}</th><th>{t("Last message")}</th><th>{t("When")}</th><th>{t("Status")}</th></tr></thead>
          <tbody>{data.items.map((th) => (
            <tr key={th.id} className="clickable" onClick={() => setOpenId(th.id)}>
              <td>
                <div className="cell-main">{th.admin_unread && <span className="dot on" style={{ marginRight: 6, background: "var(--bad)" }} />}{who(th)}</div>
                <div className="cell-sub">{th.sylvex_user_id ? `SYLVEX ${th.sylvex_user_id}` : th.visitor_id ? t("Website visitor") : ""}{th.surface ? ` · ${t(SURFACE[th.surface] || th.surface)}` : ""}</div>
              </td>
              <td><span className="badge">{t(TOPIC[th.topic] || th.topic)}</span></td>
              <td className="small" style={{ maxWidth: 380 }}>{th.last_direction === "out" ? `${t("You")}: ` : ""}{th.last_message.slice(0, 140)}</td>
              <td className="small">{fmtDate(th.last_message_at)}</td>
              <td><StatusBadge status={th.status} /></td>
            </tr>
          ))}</tbody>
        </table></div>
        <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
      </> : <Empty>{t("No messages here.")}</Empty>)}
    </div>
  );
}
