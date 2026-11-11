// B09 / S7-04: deletion of a Telegram account at the person's request to
// support. The bot sends the account's own Telegram chat a one-time code;
// the person gives it to support only if they asked for the deletion. The
// console never sees the code. Critical: needs a fresh 2FA confirmation.
import { useEffect, useState } from "react";
import { ApiError, errorText, get, post } from "../api";
import { useApp } from "../state";
import { t } from "../i18n";
import { fmtDate, Modal } from "../ui";

type Status = {
  codes: { confirmation_id: string; state: string; attempts: number; support_ref: string; created_at: string; expires_at: string }[];
  request: { request_id: string; state: string; hold_code: string; requested_at: string | null; completed_at: string | null } | null;
  blocker: string | null;
  max_attempts: number;
};

export default function TelegramErasure({ telegramId, onClose, onDone }: { telegramId: number; onClose: () => void; onDone: () => void }) {
  const { toast } = useApp();
  const [status, setStatus] = useState<Status | null>(null);
  const [supportRef, setSupportRef] = useState("");
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [typed, setTyped] = useState("");
  const [confirmation, setConfirmation] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await get<Status>(`/api/admin/v2/erasure/telegram?telegram_id=${telegramId}`);
      setStatus(data);
      const open = data.codes.find((c) => c.state === "sent");
      if (open) setConfirmation(open.confirmation_id);
    } catch (e) {
      setError(errorText(e));
    }
  };
  useEffect(() => { void load(); }, [telegramId]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const sendCode = () => run(async () => {
    const data = await post<{ confirmation_id: string }>("/api/admin/v2/erasure/telegram/start",
      { telegram_id: telegramId, support_ref: supportRef.trim(), reason: reason.trim() });
    setConfirmation(data.confirmation_id);
    toast(t("Code sent to the user's Telegram"));
    await load();
  });
  const accept = () => run(async () => {
    await post("/api/admin/v2/erasure/telegram/confirm",
      { confirmation_id: confirmation, code: code.trim(), confirm_telegram_id: typed.trim(), reason: reason.trim() || supportRef.trim() });
    toast(t("Deletion request accepted"));
    onDone();
    onClose();
  });
  const cancel = () => run(async () => {
    await post("/api/admin/v2/erasure/telegram/cancel", { confirmation_id: confirmation, reason: t("Cancelled in the console") });
    setConfirmation("");
    setCode("");
    await load();
  });

  const open = status?.codes.find((c) => c.state === "sent");
  return (
    <Modal title={t("Delete Telegram account")} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose} disabled={busy}>{t("Close")}</button>
      {open && <button className="btn" onClick={cancel} disabled={busy}>{t("Cancel request")}</button>}
      {!open && !status?.request && (
        <button className="btn primary" disabled={busy || !status || !!status.blocker || !supportRef.trim() || !reason.trim()} onClick={sendCode}>
          {t("Send code to the user's Telegram")}
        </button>)}
      {open && (
        <button className="btn danger solid" disabled={busy || code.trim().length !== 6 || typed.trim() !== String(telegramId)} onClick={accept}>
          {t("Accept deletion")}
        </button>)}
    </>}>
      <div className="stack">
        <div className="muted">{t("Only at the person's own request to support. The bot sends their Telegram chat a one-time code; they give it to support only if they asked for the deletion. History, files, balance and subscription are deleted irreversibly; required payment records are kept.")}</div>
        {!status && !error && <span className="spinner" />}
        {status?.request && (
          <div className="notice">
            <b>{t("Deletion request")}</b>: {t(status.request.state)}{status.request.hold_code ? ` · ${status.request.hold_code}` : ""}
            {status.request.requested_at && <div className="small">{fmtDate(status.request.requested_at)}</div>}
          </div>)}
        {status?.blocker && !status.request && <div className="notice bad">{errorText(new ApiError(409, status.blocker))}</div>}
        {status && !status.request && !open && !status.blocker && (<>
          <label className="field">{t("Support reference (ticket, e-mail date)")}
            <input value={supportRef} maxLength={200} onChange={(e) => setSupportRef(e.target.value)} />
          </label>
          <label className="field">{t("Reason (saved in the audit log)")}
            <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </label>
        </>)}
        {open && (<>
          <div className="small">{t("Code sent {date}; valid until {until}. Wrong codes: {n} of {max}.", {
            date: fmtDate(open.created_at), until: fmtDate(open.expires_at), n: String(open.attempts), max: String(status?.max_attempts || 5) })}</div>
          <label className="field">{t("Code from the user")}
            <input value={code} inputMode="numeric" maxLength={6} autoComplete="off" onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          <label className="field">{t("Type the Telegram ID {id} to confirm", { id: String(telegramId) })}
            <input value={typed} inputMode="numeric" autoComplete="off" onChange={(e) => setTyped(e.target.value)} />
          </label>
          <label className="field">{t("Reason (saved in the audit log)")}
            <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </label>
        </>)}
        {error && <div className="notice bad">{error}</div>}
      </div>
    </Modal>
  );
}

