import React, { FormEvent, useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { Empty, ErrorNotice, fmtDate, Identity, Loading, Pager, SourceBadges, Tip, useAsync } from "../ui";
import { Composer, Delivery, DeliveryBadges, Draft, draftPayload, draftProblem, emptyDraft, telegramErrorText } from "./messaging";

// Conversations users started from "Contact SYLVEX" (Mini App or website)
// and the ones an admin started from a user card; the sales department is
// the same list limited to Store -> Contact sales requests. A reply is shown
// to the user as from "SYLVEX Team" in their notification bell, and sent by
// the bot too when they have Telegram.

type Thread = {
  id: number; account_id: number | null; visitor_id: string | null; email: string | null; topic: string; surface: string | null;
  status: string; admin_unread: boolean; created_at: string; last_message_at: string; last_message: string; last_direction: string;
  messages: number; sylvex_user_id: string | null; telegram_id: number | null; identity: Identity | null;
  assignee_admin_id: number | null; assignee_name: string | null; attachments_allowed: boolean; first_reply_at: string | null;
  sales?: Sales | null;
};
type Sales = {
  kind: string; company: string; team_size: string; website: string; needs: string[]; budget: string; comment: string;
  name: string; email: string; phone: string;
};
type Attachment = { key: string; name: string; mime: string; size: number; url: string | null };
type Message = {
  id: number; direction: "in" | "out"; text: string; image_url: string | null; links: { url: string; label: string }[];
  admin_id: number | null; author?: string | null; created_at: string; sales?: Sales | null; delivery?: Delivery;
  attachments?: Attachment[]; read_at?: string | null;
};
type Detail = {
  thread: Thread & { person: { key: string; sylvex_user_id: string | null; telegram_id: number | null; visitor_id: string | null; identity: Identity | null } };
  messages: Message[];
};
type Counts = Record<string, number>;
type Assignee = { admin_id: number; name: string; role: string; me: boolean };

const TOPIC: Record<string, string> = { support: "Support", sales: "Sales", admin: "Administrator", general: "General" };
const SURFACE: Record<string, string> = { miniapp: "Mini App", website: "Website", telegram: "Telegram" };
// The team's statuses: open = new, in_progress, answered = waiting for the
// person, closed.
const THREAD_STATUS: Record<string, string> = { open: "New", in_progress: "In progress", answered: "Waiting for reply", closed: "Closed" };
const STATUS_TONE: { [status: string]: string } = { open: "bad", in_progress: "accent", answered: "warn", closed: "" };
const STATUS_HELP: Record<string, string> = {
  open: "Nobody has taken it yet.",
  in_progress: "Someone on the team is working on it.",
  answered: "SYLVEX replied; waiting for the person to answer.",
  closed: "Done. A new message from the person opens it again.",
};
const PAGE = 30;
// A request from Store -> Contact sales arrives as its fields.
const SALES_KIND: Record<string, string> = { organization: "Organization", private: "Private person" };
const SALES_NEED: Record<string, string> = { images: "Images", video: "Video", voice: "Voice & music", text: "Text", api: "API & integration", team: "Team access" };
const SALES_BUDGET: Record<string, string> = { lt100: "Under $100", "100-500": "$100–500", "500-2000": "$500–2,000", "2000+": "Over $2,000", unknown: "Not sure yet" };

export function ThreadStatus({ status }: { status: string }) {
  return <Tip icon={false} text={t(STATUS_HELP[status] || status)}><span className={`badge ${STATUS_TONE[status] || ""}`}>{t(THREAD_STATUS[status] || status)}</span></Tip>;
}

function SalesCard({ s }: { s: Sales }) {
  const rows: [string, React.ReactNode][] = [
    [t("Applicant"), t(SALES_KIND[s.kind] || s.kind)],
    ...(s.company ? [[t("Organization"), s.company]] as [string, React.ReactNode][] : []),
    ...(s.team_size ? [[t("Team size"), s.team_size]] as [string, React.ReactNode][] : []),
    ...(s.website ? [[t("Website"), <a href={s.website} target="_blank" rel="noopener noreferrer">{s.website}</a>]] as [string, React.ReactNode][] : []),
    [t("Interested in"), s.needs.map((n) => t(SALES_NEED[n] || n)).join(", ")],
    ...(s.budget ? [[t("Monthly budget"), t(SALES_BUDGET[s.budget] || s.budget)]] as [string, React.ReactNode][] : []),
    [t("Contact name"), s.name],
    [t("E-mail"), <a href={`mailto:${s.email}`}>{s.email}</a>],
    ...(s.phone ? [[t("Phone or Telegram"), s.phone]] as [string, React.ReactNode][] : []),
  ];
  return (
    <div className="stack" style={{ gap: 8 }}>
      <b>{t("Sales request")}</b>
      <div className="kv">{rows.map(([k, v]) => <div key={k} className="kv-row"><span className="muted small">{k}</span><span>{v}</span></div>)}</div>
      {s.comment && <div style={{ whiteSpace: "pre-wrap" }}>{s.comment}</div>}
    </div>
  );
}

function salesSummary(s?: Sales | null) {
  if (!s) return "";
  return [s.company || t(SALES_KIND[s.kind] || s.kind), s.team_size && `${s.team_size} ${t("people")}`,
    s.needs.map((n) => t(SALES_NEED[n] || n)).join(", "), s.budget && t(SALES_BUDGET[s.budget] || s.budget)].filter(Boolean).join(" · ");
}

function who(th: { identity: Identity | null; email: string | null; sylvex_user_id: string | null; visitor_id: string | null }) {
  return th.identity?.display_name || th.identity?.username || th.identity?.email || th.email
    || (th.sylvex_user_id ? `SYLVEX ${th.sylvex_user_id}` : th.visitor_id ? `${t("Visitor")} ${th.visitor_id.slice(2, 10)}` : "—");
}

const fmtSize = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

function useAssignees() {
  return useAsync(() => post<{ items: Assignee[] }>("/api/admin/inbox/assignees", {}).then((r) => r.items), []);
}

function ThreadView({ id, onBack, sales }: { id: number; onBack: () => void; sales: boolean }) {
  const { toast, go, can } = useApp();
  const { data, error, loading, reload } = useAsync(() => post<Detail>("/api/admin/inbox/thread", { thread_id: id }), [id]);
  const assignees = useAssignees();
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const th = data.thread;
  const person = th.person;
  const problem = draftProblem(draft);
  const manage = can("support.manage");

  const reply = async () => {
    setBusy(true);
    try {
      const res = await post<{ delivery: Delivery }>("/api/admin/inbox/reply", { thread_id: id, ...draftPayload(draft) });
      const tg = res.delivery.telegram;
      toast(tg === "sent" ? t("Reply sent: notification bell + Telegram")
        : tg === "failed" ? `${t("Reply in the bell; Telegram did not accept it")}: ${telegramErrorText(res.delivery.telegram_error)}`
        : t("Reply sent to the notification bell"), tg === "failed");
      setDraft(emptyDraft());
      reload();
    } catch (e) {
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  const change = async (path: string, body: Record<string, unknown>, done: string) => {
    try { await post(path, { thread_id: id, ...body }); toast(done); reload(); } catch (e) { toast(errorText(e), true); }
  };

  return (
    <div className="stack">
      <div className="row between">
        <button className="btn small ghost" onClick={onBack}>← {sales ? t("Sales department") : t("Conversations")}</button>
        {person.sylvex_user_id && <button className="btn small ghost" onClick={() => go(`users/s${person.sylvex_user_id}`)}>{t("Open user")} →</button>}
      </div>
      <div className="card stack">
        <div className="row between">
          <div>
            <h3 style={{ margin: 0 }}>{who({ ...person, email: th.email })}</h3>
            <div className="muted small">{[person.sylvex_user_id && `SYLVEX ${person.sylvex_user_id}`, person.telegram_id && `TG ${person.telegram_id}`,
              th.email, person.visitor_id && `${t("Visitor")} ${person.visitor_id}`].filter(Boolean).join(" · ")}</div>
          </div>
          <div className="row">
            <span className="badge">{t(TOPIC[th.topic] || th.topic)}</span>
            {th.surface && <span className="badge">{t(SURFACE[th.surface] || th.surface)}</span>}
            <ThreadStatus status={th.status} />
            <SourceBadges identity={person.identity} />
          </div>
        </div>
        <div className="thread-controls">
          <label className="field">{t("Status")}
            <select value={th.status} onChange={(e) => change("/api/admin/inbox/status", { status: e.target.value }, t("Status changed"))}>
              {Object.entries(THREAD_STATUS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
            </select>
          </label>
          <label className="field">{t("Assignee")}
            <select value={th.assignee_admin_id ? String(th.assignee_admin_id) : ""}
              onChange={(e) => change("/api/admin/inbox/assign", { admin_id: e.target.value || null }, t("Assignee changed"))}>
              <option value="">{t("Nobody")}</option>
              {(assignees.data || []).filter((a) => manage || a.me || a.admin_id === th.assignee_admin_id).map((a) => (
                <option key={a.admin_id} value={a.admin_id}>{a.name}{a.me ? ` (${t("you")})` : ""}</option>
              ))}
            </select>
          </label>
          {manage && (
            <div className="field">
              <span>{t("Attachments")} <Tip text={t("When on, the person can attach images or PDF files (up to 10 MB) in their Contact window for this conversation.")} /></span>
              <button type="button" className={`chip ${th.attachments_allowed ? "on" : ""}`}
                onClick={() => change("/api/admin/inbox/attachments", { allowed: !th.attachments_allowed },
                  th.attachments_allowed ? t("Attachments turned off") : t("Attachments allowed"))}>
                {th.attachments_allowed ? t("Allowed") : t("Not allowed")}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="card stack">
        {data.messages.map((m) => (
          <div key={m.id} className={`bubble ${m.direction}`}>
            <div className="bubble-head">{m.direction === "out" ? `SYLVEX Team${m.author ? ` · ${m.author}` : ""}` : who({ ...person, email: th.email })} · {fmtDate(m.created_at)}</div>
            {m.sales ? <SalesCard s={m.sales} /> : <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>}
            {m.image_url && <img src={m.image_url} alt="" style={{ maxWidth: 240, borderRadius: 8, marginTop: 6 }} />}
            {m.links.map((l, i) => <div key={i} className="small"><a href={l.url} target="_blank" rel="noopener noreferrer">🔗 {l.label || l.url}</a></div>)}
            {(m.attachments || []).length > 0 && (
              <div className="attachments">{(m.attachments || []).map((f) => (
                f.mime.startsWith("image/") && f.url
                  ? <a key={f.key} href={f.url} target="_blank" rel="noopener noreferrer"><img src={f.url} alt={f.name} /></a>
                  : <a key={f.key} className="file" href={f.url || "#"} target="_blank" rel="noopener noreferrer">📄 {f.name} · {fmtSize(f.size)}</a>
              ))}</div>
            )}
            {m.direction === "out" && m.delivery && <div className="bubble-foot"><DeliveryBadges delivery={m.delivery} />
              {m.read_at && <span className="badge good">{t("Read")} {fmtDate(m.read_at)}</span>}</div>}
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

type Filters = { query: string; assignee: string; unread: boolean; surface: string };

export default function Inbox({ sales = false, threadId = "" }: { sales?: boolean; threadId?: string }) {
  const { go } = useApp();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  // The open conversation lives in the address (#/inbox/12), so a reload or
  // a shared link opens it again.
  const openId = /^\d+$/.test(threadId) ? Number(threadId) : null;
  const base = sales ? "sales" : "inbox";
  const setOpenId = (id: number | null) => go(id ? `${base}/${id}` : base);
  const [input, setInput] = useState("");
  const [filters, setFilters] = useState<Filters>({ query: "", assignee: "", unread: false, surface: "" });
  const assignees = useAssignees();
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: Thread[]; total: number; counts: Counts }>("/api/admin/inbox/list", {
      status, limit: PAGE, offset, ...filters, ...(sales ? { topic: "sales" } : { exclude_topic: "sales" }),
    }),
    [status, offset, openId, filters, sales],
  );
  const setFilter = (patch: Partial<Filters>) => { setOffset(0); setFilters((f) => ({ ...f, ...patch })); };
  const submit = (e: FormEvent) => { e.preventDefault(); setFilter({ query: input.trim() }); };

  if (openId) return <ThreadView id={openId} sales={sales} onBack={() => setOpenId(null)} />;
  const counts = data?.counts || {};
  return (
    <div className="stack">
      <div className="muted small">{sales
        ? t("Requests from Store → Contact sales: who they are, what they need and their budget.")
        : t("Messages users sent from “Contact SYLVEX” in the Mini App or on the website, and conversations started from a user card.")}</div>
      <div className="tabs" style={{ marginBottom: 0 }}>
        {[["", "All"], ["open", "New"], ["in_progress", "In progress"], ["answered", "Waiting for reply"], ["closed", "Closed"]].map(([key, label]) => (
          <button key={key} className={`tab ${status === key ? "active" : ""}`} onClick={() => { setOffset(0); setStatus(key); }}>
            {t(label)} <span className="tab-count">{counts[key || "all"] ?? ""}</span>
          </button>
        ))}
      </div>
      <form className="card row" onSubmit={submit}>
        <input style={{ flex: 1, minWidth: 200 }} value={input} onChange={(e) => setInput(e.target.value)}
          placeholder={t("Search: name, @username, email, SYLVEX ID, Telegram ID or message text")} />
        <select value={filters.assignee} onChange={(e) => setFilter({ assignee: e.target.value })}>
          <option value="">{t("Any assignee")}</option><option value="me">{t("Assigned to me")}</option><option value="none">{t("Unassigned")}</option>
          {(assignees.data || []).filter((a) => !a.me).map((a) => <option key={a.admin_id} value={a.admin_id}>{a.name}</option>)}
        </select>
        <select value={filters.surface} onChange={(e) => setFilter({ surface: e.target.value })}>
          <option value="">{t("All surfaces")}</option><option value="miniapp">Mini App</option><option value="website">{t("Website")}</option>
        </select>
        <label className="row small" style={{ gap: 6 }}>
          <input type="checkbox" checked={filters.unread} onChange={(e) => setFilter({ unread: e.target.checked })} /> {t("Unread only")}
          {counts.unread ? <span className="nav-count">{counts.unread}</span> : null}
        </label>
        <button className="btn">{t("Search")}</button>
      </form>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (data.items.length ? <>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("From")}</th><th>{sales ? t("Request") : t("Topic")}</th><th>{t("Last message")}</th><th>{t("Assignee")}</th><th>{t("When")}</th><th>{t("Status")}</th></tr></thead>
          <tbody>{data.items.map((th) => (
            <tr key={th.id} className="clickable" onClick={() => setOpenId(th.id)}>
              <td>
                <div className="cell-main">{th.admin_unread && <span className="dot on" style={{ marginRight: 6, background: "var(--bad)" }} />}{who(th)}</div>
                <div className="cell-sub">{th.sylvex_user_id ? `SYLVEX ${th.sylvex_user_id}` : th.visitor_id ? t("Website visitor") : ""}{th.surface ? ` · ${t(SURFACE[th.surface] || th.surface)}` : ""}</div>
              </td>
              <td className="small">{sales ? salesSummary(th.sales) || t("Sales") : <span className="badge">{t(TOPIC[th.topic] || th.topic)}</span>}</td>
              <td className="small" style={{ maxWidth: 360 }}>{th.last_direction === "out" ? `${t("You")}: ` : ""}{th.last_message.slice(0, 140)}</td>
              <td className="small">{th.assignee_name || <span className="muted">{t("Nobody")}</span>}</td>
              <td className="small">{fmtDate(th.last_message_at)}</td>
              <td><ThreadStatus status={th.status} /></td>
            </tr>
          ))}</tbody>
        </table></div>
        <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
      </> : <Empty>{t("No messages here.")}</Empty>)}
    </div>
  );
}
