// Shared pieces of the messaging screens (Messages, Inbox, Users → Audience):
// the message composer (text + links + one image) and the
// "Source · Status" badges of a person.
import { useState } from "react";
import { errorText, post } from "../api";
import { t } from "../i18n";

export type AudienceRow = {
  key: string; sylvex_user_id: string | null; telegram_id: number | null; visitor_id: string | null;
  name: string; username: string; email: string | null; sources: string[]; status: "registered" | "visitor";
  last_seen: string | null; since: string | null;
};

const SOURCE_LABEL: Record<string, string> = { telegram: "Telegram", miniapp: "Mini App", website: "Website" };
export const CHANNEL_LABEL: Record<string, string> = { telegram: "Telegram", miniapp: "Mini App", website: "Website" };

export function personName(row: { name?: string; username?: string; email?: string | null; sylvex_user_id?: string | null; visitor_id?: string | null }) {
  return row.name || (row.username ? `@${row.username}` : "") || row.email
    || (row.sylvex_user_id ? `SYLVEX ${row.sylvex_user_id}` : row.visitor_id ? `${t("Visitor")} ${row.visitor_id.slice(2, 10)}` : "—");
}

/** "Website · Registered", "Mini App · Visitor", ... one badge per source. */
export function AudienceBadges({ sources, status }: { sources: string[]; status: string }) {
  return (
    <span className="badges">
      {sources.map((s) => (
        <span key={s} className={`badge ${status === "registered" ? "accent" : ""}`}>
          {t(SOURCE_LABEL[s] || s)} · {t(status === "registered" ? "Registered" : "Visitor")}
        </span>
      ))}
    </span>
  );
}

export type Draft = { text: string; links: { url: string; label: string }[]; image: { key: string; url: string } | null };
export const emptyDraft = (): Draft => ({ text: "", links: [], image: null });

export function draftPayload(d: Draft) {
  return {
    text: d.text.trim(),
    links: d.links.filter((l) => l.url.trim()).map((l) => ({ url: l.url.trim(), label: l.label.trim() })),
    image_key: d.image?.key || undefined,
  };
}

const URL_OK = /^https?:\/\/\S{3,}$/i;
export function draftProblem(d: Draft): string {
  if (!d.text.trim()) return t("Write the message text.");
  if (d.text.length > 4000) return t("The message is longer than 4000 characters.");
  if (d.links.some((l) => l.url.trim() && !URL_OK.test(l.url.trim()))) return t("Links must start with https://");
  return "";
}

const MAX_IMAGE = 10 * 1024 * 1024;

function readBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error(t("Could not read the file.")));
    reader.readAsDataURL(file);
  });
}

/** Text + up to 5 links + one image. Shown to users as from "SYLVEX Team". */
export function Composer({ draft, onChange, rows = 6, placeholder }: {
  draft: Draft; onChange: (d: Draft) => void; rows?: number; placeholder?: string;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const setLink = (i: number, field: "url" | "label", value: string) =>
    onChange({ ...draft, links: draft.links.map((l, j) => (j === i ? { ...l, [field]: value } : l)) });

  const upload = async (file?: File) => {
    if (!file) return;
    setError("");
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { setError(t("Use a PNG, JPG, WebP or GIF image.")); return; }
    if (file.size > MAX_IMAGE) { setError(t("The image is larger than 10 MB.")); return; }
    setUploading(true);
    try {
      const res = await post<{ image_key: string; url: string }>("/api/admin/messages/upload-image", {
        content_base64: await readBase64(file), content_type: file.type,
      });
      onChange({ ...draft, image: { key: res.image_key, url: res.url } });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="stack">
      <textarea rows={rows} value={draft.text} maxLength={4000} onChange={(e) => onChange({ ...draft, text: e.target.value })}
        placeholder={placeholder ?? t("Message text (plain text, up to 4000 characters)")} />
      <div className="row between"><span className="muted small">{t("Shown to users as from “SYLVEX Team”.")}</span>
        <span className="muted small">{draft.text.length} / 4000</span></div>

      {draft.links.map((l, i) => (
        <div key={i} className="row">
          <input style={{ flex: 2, minWidth: 180 }} value={l.url} placeholder="https://…" onChange={(e) => setLink(i, "url", e.target.value)} />
          <input style={{ flex: 1, minWidth: 120 }} value={l.label} maxLength={60} placeholder={t("Button text (optional)")} onChange={(e) => setLink(i, "label", e.target.value)} />
          <button type="button" className="btn small ghost" aria-label={t("Remove")} onClick={() => onChange({ ...draft, links: draft.links.filter((_, j) => j !== i) })}>✕</button>
        </div>
      ))}

      <div className="row">
        {draft.links.length < 5 && (
          <button type="button" className="btn small" onClick={() => onChange({ ...draft, links: [...draft.links, { url: "", label: "" }] })}>+ {t("Link")}</button>
        )}
        {!draft.image && (
          <label className="btn small">
            {uploading ? <span className="spinner" /> : "+ "}{t("Image")}
            <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        )}
      </div>
      {draft.image && (
        <div className="row">
          <img src={draft.image.url} alt="" style={{ maxWidth: 220, maxHeight: 140, borderRadius: 10, objectFit: "cover" }} />
          <button type="button" className="btn small ghost" onClick={() => onChange({ ...draft, image: null })}>✕ {t("Remove image")}</button>
        </div>
      )}
      {error && <div className="notice bad">{error}</div>}
    </div>
  );
}

/** Where an admin message went and what the bot API answered. */
export type Delivery = { channels?: string[]; bell?: string[]; telegram?: string; telegram_error?: string };

const TELEGRAM_STATE: Record<string, string> = {
  sent: "Telegram: delivered", failed: "Telegram: not delivered", pending: "Telegram: sending…",
  not_linked: "No Telegram linked",
};

export function telegramErrorText(error?: string) {
  const e = (error || "").toLowerCase();
  if (e.includes("blocked by the user")) return t("The user blocked the bot.");
  if (e.includes("chat not found") || e.includes("bot can't initiate")) return t("The user never started the bot.");
  if (e.includes("deactivated")) return t("The Telegram account was deleted.");
  if (e.startsWith("network_")) return t("Telegram could not be reached.");
  if (e === "bot_not_configured") return t("The Telegram bot is not configured on the server.");
  return error || "";
}

export function DeliveryBadges({ delivery }: { delivery?: Delivery | null }) {
  if (!delivery || !delivery.channels) return null;
  const bell = (delivery.bell || []).map((s) => t(CHANNEL_LABEL[s] || s));
  return (
    <span className="badges">
      {bell.length > 0 && <span className="badge good">{t("Bell")}: {bell.join(", ")}</span>}
      {TELEGRAM_STATE[delivery.telegram || ""] && (
        <span className={`badge ${delivery.telegram === "sent" ? "good" : delivery.telegram === "failed" ? "bad" : ""}`}
          title={telegramErrorText(delivery.telegram_error)}>{t(TELEGRAM_STATE[delivery.telegram || ""])}</span>
      )}
      {delivery.telegram === "failed" && delivery.telegram_error && <span className="small muted">{telegramErrorText(delivery.telegram_error)}</span>}
    </span>
  );
}
