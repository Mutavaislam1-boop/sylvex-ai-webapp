import { FormEvent, useEffect, useState } from "react";
import { post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, fmtDate, fmtNum, Loading, Pager, useAsync } from "../ui";
import { AudienceBadges, AudienceRow, CHANNEL_LABEL, Composer, Draft, draftPayload, draftProblem, emptyDraft, personName } from "./messaging";

// Admin Console → message → everyone / selected people → Telegram (bot
// message) + Mini App bell + website bell. No channel ticked = everywhere.

const CHANNELS = ["telegram", "miniapp", "website"] as const;
const PAGE = 20;

type SendResult = { notification_id: number; channels: string[]; bell_recipients: number; telegram_recipients: number };
type HistoryItem = {
  id: number; kind: string; text: string; has_image: boolean; links: { url: string }[]; channels: string[]; audience: string;
  recipients: number; telegram_targets: number; telegram_sent: number; created_at: string; read: number;
};

function Picker({ picked, onAdd, max }: { picked: AudienceRow[]; onAdd: (rows: AudienceRow[]) => void; max: number }) {
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: AudienceRow[]; total: number }>("/api/admin/audience", { source, status, query, limit: PAGE, offset }),
    [source, status, query, offset],
  );
  const chosen = new Set(picked.map((p) => p.key));
  const submit = (e: FormEvent) => { e.preventDefault(); setOffset(0); setQuery(input.trim()); };
  const pageRows = (data?.items || []).filter((r) => !chosen.has(r.key));

  return (
    <div className="stack">
      <form className="row" onSubmit={submit}>
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
        <button className="btn">{t("Search")}</button>
      </form>
      {error ? <ErrorNotice message={error} onRetry={reload} /> : loading && !data ? <Loading /> : data && (
        data.items.length ? <>
          <div className="row between">
            <span className="muted small">{t("Found: {n}", { n: fmtNum(data.total) })}</span>
            {max > 1 && pageRows.length > 0 && (
              <button type="button" className="btn small" onClick={() => onAdd(pageRows)}>+ {t("Add all on this page")}</button>
            )}
          </div>
          <div className="table-wrap"><table><tbody>{data.items.map((r) => (
            <tr key={r.key}>
              <td><div className="cell-main">{personName(r)}</div>
                <div className="cell-sub">{[r.sylvex_user_id && `SYLVEX ${r.sylvex_user_id}`, r.telegram_id && `TG ${r.telegram_id}`, r.email].filter(Boolean).join(" · ")}</div></td>
              <td><AudienceBadges sources={r.sources} status={r.status} /></td>
              <td className="small">{fmtDate(r.last_seen)}</td>
              <td className="right"><button type="button" className="btn small" disabled={chosen.has(r.key)} onClick={() => onAdd([r])}>
                {chosen.has(r.key) ? t("Added") : t("Add")}</button></td>
            </tr>
          ))}</tbody></table></div>
          <Pager offset={offset} limit={PAGE} total={data.total} onChange={setOffset} />
        </> : <Empty>{t("No users found.")}</Empty>
      )}
    </div>
  );
}

function History({ refreshKey }: { refreshKey: number }) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () => post<{ items: HistoryItem[]; total: number }>("/api/admin/messages/history", { limit: 10, offset }),
    [offset, refreshKey],
  );
  if (error) return <ErrorNotice message={error} onRetry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data || !data.items.length) return <Empty>{t("Nothing sent yet.")}</Empty>;
  return (
    <>
      <div className="table-wrap"><table>
        <thead><tr><th>{t("Date")}</th><th>{t("Message")}</th><th>{t("Channels")}</th><th>{t("To")}</th>
          <th className="right">{t("Bell")}</th><th className="right">Telegram</th></tr></thead>
        <tbody>{data.items.map((m) => (
          <tr key={m.id}>
            <td className="small">{fmtDate(m.created_at)}</td>
            <td className="small" style={{ maxWidth: 360 }}>{m.text.slice(0, 140)}{m.has_image ? " 🖼" : ""}{m.links.length ? ` 🔗${m.links.length}` : ""}</td>
            <td className="small">{m.channels.map((c) => t(CHANNEL_LABEL[c] || c)).join(", ")}</td>
            <td className="small">{m.kind === "reply" ? t("Personal reply") : m.audience === "all" ? t("Everyone") : t("Selected")}</td>
            <td className="right small">{fmtNum(m.recipients)}<div className="cell-sub">{t("read: {n}", { n: fmtNum(m.read) })}</div></td>
            <td className="right small">{m.telegram_targets ? `${fmtNum(m.telegram_sent)} / ${fmtNum(m.telegram_targets)}` : "—"}</td>
          </tr>
        ))}</tbody>
      </table></div>
      <Pager offset={offset} limit={10} total={data.total} onChange={setOffset} />
    </>
  );
}

export default function Broadcast({ to }: { to: string }) {
  const { can } = useApp();
  const canBroadcast = can("broadcast.send");
  const [audience, setAudience] = useState<"all" | "selected">(canBroadcast && !to ? "all" : "selected");
  const [channels, setChannels] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [picked, setPicked] = useState<AudienceRow[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<SendResult | null>(null);
  const [sentCount, setSentCount] = useState(0);
  const max = canBroadcast ? 5000 : 1;

  // Arriving from Users → Audience with a person preselected.
  useEffect(() => {
    if (!to) return;
    setAudience("selected");
    post<{ items: AudienceRow[] }>("/api/admin/audience", { query: to.replace(/^[atv]:/, ""), limit: 20 })
      .then((res) => {
        const row = res.items.find((r) => r.key === to);
        if (row) setPicked([row]);
      })
      .catch(() => undefined);
  }, [to]);

  const add = (rows: AudienceRow[]) => setPicked((list) => {
    const keys = new Set(list.map((r) => r.key));
    const next = [...list, ...rows.filter((r) => !keys.has(r.key))];
    return max === 1 ? next.slice(-1) : next.slice(0, max);
  });
  const toggleChannel = (c: string) => setChannels((list) => (list.includes(c) ? list.filter((x) => x !== c) : [...list, c]));
  const effective = channels.length ? channels : [...CHANNELS];
  const problem = draftProblem(draft) || (audience === "selected" && !picked.length ? t("Select at least one recipient.") : "");
  const recipientsText = audience === "all" ? t("everyone") : t("selected: {n}", { n: picked.length });

  const send = async () => {
    const body = {
      ...draftPayload(draft), channels, audience,
      recipients: audience === "selected" ? picked.map((p) => p.key) : [],
    };
    const res = await post<SendResult>("/api/admin/messages/send", body);
    setResult(res);
    setDraft(emptyDraft());
    setSentCount((n) => n + 1);
  };

  return (
    <div className="stack">
      <div className="card stack">
        <h3>{t("Compose")}</h3>
        <Composer draft={draft} onChange={setDraft} />
      </div>

      <div className="card stack">
        <h3>{t("Where to deliver")}</h3>
        <div className="row">
          {CHANNELS.map((c) => (
            <label key={c} className="row small" style={{ gap: 6 }}>
              <input type="checkbox" checked={channels.includes(c)} onChange={() => toggleChannel(c)} /> {t(CHANNEL_LABEL[c])}
            </label>
          ))}
        </div>
        <div className="muted small">
          {channels.length ? t("Only: {list}", { list: channels.map((c) => t(CHANNEL_LABEL[c])).join(", ") })
            : t("Nothing ticked = everywhere: Telegram users get a bot message, Mini App and website users see it in the notification bell.")}
        </div>
      </div>

      <div className="card stack">
        <h3>{t("Recipients")}</h3>
        {canBroadcast ? (
          <div className="tabs" style={{ marginBottom: 0 }}>
            <button className={`tab ${audience === "all" ? "active" : ""}`} onClick={() => setAudience("all")}>{t("Everyone")}</button>
            <button className={`tab ${audience === "selected" ? "active" : ""}`} onClick={() => setAudience("selected")}>{t("Selected users")}</button>
          </div>
        ) : <div className="notice">{t("Your role can message one user at a time. Broadcasting needs the broadcast permission.")}</div>}
        {audience === "all" ? (
          <div className="muted small">{t("Everyone: all SYLVEX accounts, Telegram users and — for the website bell — anonymous website visitors.")}</div>
        ) : <>
          {picked.length > 0 && (
            <div className="row">
              {picked.slice(0, 60).map((p) => (
                <span key={p.key} className="badge accent">{personName(p)}
                  <button className="btn small ghost" style={{ padding: "0 4px" }} onClick={() => setPicked((l) => l.filter((x) => x.key !== p.key))}>✕</button>
                </span>
              ))}
              {picked.length > 60 && <span className="muted small">+{picked.length - 60}</span>}
              <button className="btn small ghost" onClick={() => setPicked([])}>{t("Clear")}</button>
            </div>
          )}
          <Picker picked={picked} onAdd={add} max={max} />
        </>}
      </div>

      <div className="row between">
        <span className="muted small">{t("To")}: <b>{recipientsText}</b> · {effective.map((c) => t(CHANNEL_LABEL[c])).join(" + ")}</span>
        <button className="btn primary" disabled={!!problem} title={problem} onClick={() => setConfirming(true)}>{t("Review & send")}</button>
      </div>
      {problem && draft.text && <div className="muted small right">{problem}</div>}

      {result && (
        <div className="notice good">
          {t("Sent. Notification bell: {bell} people · Telegram: {tg} (sending in the background).", {
            bell: fmtNum(result.bell_recipients), tg: fmtNum(result.telegram_recipients) })}
        </div>
      )}

      <div className="card">
        <h3>{t("Sent messages")}</h3>
        <History refreshKey={sentCount} />
      </div>

      {confirming && (
        <ConfirmAction
          title={audience === "all" ? t("Broadcast to everyone") : t("Send message")}
          confirmLabel={t("Send now")}
          danger={audience === "all"}
          needReason={false}
          typed={audience === "all" ? t("SEND TO ALL") : undefined}
          description={<div className="stack">
            <span>{t("Recipients")}: <b>{recipientsText}</b> · {effective.map((c) => t(CHANNEL_LABEL[c])).join(" + ")}</span>
            <div className="notice" style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
              <b>SYLVEX Team</b>{"\n"}{draft.text}
            </div>
            {draft.image && <img src={draft.image.url} alt="" style={{ maxWidth: 200, borderRadius: 8 }} />}
            {draft.links.filter((l) => l.url.trim()).map((l, i) => <span key={i} className="small">🔗 {l.label || l.url}</span>)}
            <span className="small">{t("Messages cannot be recalled once sent.")}</span>
          </div>}
          onConfirm={send}
          onClose={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
