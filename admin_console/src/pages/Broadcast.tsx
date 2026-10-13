import { FormEvent, useState } from "react";
import { errorText, post } from "../api";
import { useApp } from "../state";
import { ConfirmAction, Empty, Identity, SourceBadges } from "../ui";

type Pick = { sylvex_user_id: string | null; telegram_id: number | null; name: string; username: string; identity: Identity | null };

export default function Broadcast() {
  const { can, toast } = useApp();
  const canBroadcast = can("broadcast.send");
  const [audience, setAudience] = useState<"all" | "selected">(canBroadcast ? "all" : "selected");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Pick[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<Pick[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [last, setLast] = useState<{ recipients: number; sent: number; skipped_no_telegram: number } | null>(null);

  const maxPicked = canBroadcast ? 500 : 1;
  const key = (p: Pick) => p.sylvex_user_id || String(p.telegram_id);
  const search = async (e: FormEvent) => {
    e.preventDefault();
    setSearching(true);
    try {
      const res = await post<{ items: Pick[] }>("/api/admin/users/search", { query: query.trim(), limit: 20 });
      setResults(res.items);
    } catch (err) {
      toast(errorText(err), true);
    } finally {
      setSearching(false);
    }
  };
  const add = (p: Pick) => {
    if (picked.some((x) => key(x) === key(p))) return;
    setPicked((list) => (maxPicked === 1 ? [p] : [...list, p].slice(0, maxPicked)));
  };
  const recipients = audience === "all" ? "all users" : `${picked.length} user${picked.length === 1 ? "" : "s"}`;
  const ready = message.trim().length > 0 && message.length <= 4000 && (audience === "all" || picked.length > 0);

  const send = async () => {
    if (!canBroadcast) {
      const p = picked[0];
      await post("/api/admin/users/message", { ...(p.sylvex_user_id ? { sylvex_user_id: p.sylvex_user_id } : { user_id: String(p.telegram_id) }), message: message.trim() });
      setLast({ recipients: 1, sent: 1, skipped_no_telegram: 0 });
    } else {
      const body: Record<string, unknown> = { message: message.trim() };
      if (audience === "all") body.all = true;
      else {
        body.sylvex_user_ids = picked.filter((p) => p.sylvex_user_id).map((p) => p.sylvex_user_id);
        body.user_ids = picked.filter((p) => !p.sylvex_user_id && p.telegram_id).map((p) => String(p.telegram_id));
      }
      setLast(await post("/api/admin/messages/broadcast", body));
    }
    toast("Message sent");
    setMessage("");
  };

  return (
    <div className="stack">
      <div className="card stack">
        <h3>Compose</h3>
        <div className="muted small">Sent by the SYLVEX Telegram bot. Website-only accounts without Telegram cannot receive it and are skipped.</div>
        <textarea rows={7} value={message} maxLength={4000} onChange={(e) => setMessage(e.target.value)} placeholder="Message text (plain text, up to 4000 characters)" />
        <div className="muted small right">{message.length} / 4000</div>
      </div>

      <div className="card stack">
        <h3>Recipients</h3>
        {canBroadcast ? (
          <div className="tabs" style={{ marginBottom: 0 }}>
            <button className={`tab ${audience === "all" ? "active" : ""}`} onClick={() => setAudience("all")}>Everyone with Telegram</button>
            <button className={`tab ${audience === "selected" ? "active" : ""}`} onClick={() => setAudience("selected")}>Selected users</button>
          </div>
        ) : <div className="notice">Your role can message one user at a time. Broadcasting needs the broadcast permission.</div>}
        {audience === "selected" && (
          <>
            <form className="row" onSubmit={search}>
              <input style={{ flex: 1, minWidth: 200 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a user: SYLVEX ID, Telegram ID, email, @username" />
              <button className="btn" disabled={searching}>{searching && <span className="spinner" />}Search</button>
            </form>
            {picked.length > 0 && (
              <div className="row">{picked.map((p) => (
                <span key={key(p)} className="badge accent">
                  {p.identity?.display_name || p.name || p.sylvex_user_id}
                  <button className="btn small ghost" style={{ padding: "0 4px" }} onClick={() => setPicked((l) => l.filter((x) => key(x) !== key(p)))}>✕</button>
                </span>
              ))}</div>
            )}
            {results && (results.length ? (
              <div className="table-wrap"><table><tbody>{results.map((r) => {
                const hasTelegram = !!(r.identity?.linked?.telegram || r.telegram_id);
                const chosen = picked.some((x) => key(x) === key(r));
                return (
                  <tr key={key(r)}>
                    <td><div className="cell-main">{r.identity?.display_name || r.name}</div>
                      <div className="cell-sub">{r.sylvex_user_id ? `SYLVEX ${r.sylvex_user_id}` : ""}{r.username ? ` · @${r.username}` : ""}</div></td>
                    <td><SourceBadges identity={r.identity} /></td>
                    <td className="right">
                      <button className="btn small" disabled={!hasTelegram || chosen} onClick={() => add(r)}>
                        {chosen ? "Added" : hasTelegram ? "Add" : "No Telegram"}
                      </button>
                    </td>
                  </tr>
                );
              })}</tbody></table></div>
            ) : <Empty>No users found.</Empty>)}
          </>
        )}
      </div>

      <div className="row between">
        <span className="muted small">Will send to <b>{recipients}</b>.</span>
        <button className="btn primary" disabled={!ready} onClick={() => setConfirming(true)}>Review & send</button>
      </div>

      {last && (
        <div className="notice good">
          Delivered to {last.sent} of {last.recipients} recipient(s){last.skipped_no_telegram ? `, ${last.skipped_no_telegram} skipped (no Telegram)` : ""}.
        </div>
      )}

      {confirming && (
        <ConfirmAction
          title={audience === "all" ? "Broadcast to everyone" : "Send message"}
          confirmLabel="Send now"
          danger={audience === "all"}
          needReason={false}
          typed={audience === "all" ? "SEND TO ALL" : undefined}
          description={<div className="stack">
            <span>Recipients: <b>{recipients}</b>. Messages cannot be recalled once sent.</span>
            <div className="notice" style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>{message}</div>
            {canBroadcast && <span className="small">Broadcasting is a critical action: you may be asked to confirm your identity.</span>}
          </div>}
          onConfirm={async () => { await send(); }}
          onClose={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
