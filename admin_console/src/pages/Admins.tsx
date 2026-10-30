import { useState } from "react";
import { get, patch, post } from "../api";
import { useApp } from "../state";
import { getLang, roleLabel, t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, Identity, Loading, STAFF_REASONS, StatusBadge, Tip, useAsync } from "../ui";

type AdminRow = {
  admin_id: number; sylvex_user_id: string; role: string; status: string; grants: string[]; denies: string[];
  permissions: string[]; totp_enabled: boolean; identity: Identity | null;
};
type Text2 = { en: string; ru: string };
type Catalog = {
  permissions: Record<string, string>; roles: string[]; role_defaults: Record<string, string[]>;
  catalog: Record<string, { risk: string; label: Text2; description: Text2; why: Text2 }>; risk_info: Record<string, Text2>;
};
const RISK_TONE: Record<string, string> = { low: "", medium: "accent", high: "warn", critical: "bad" };
const pick = (text?: Text2) => (text ? text[getLang()] || text.en : "");

/** What a permission allows, why it matters and its risk - in the interface language. */
function PermissionHelp({ catalog, permission }: { catalog: Catalog; permission: string }) {
  const info = catalog.catalog?.[permission];
  const risk = catalog.permissions[permission];
  return (
    <span className="stack" style={{ gap: 4 }}>
      <b>{pick(info?.description) || permission}</b>
      {pick(info?.why) && <span>{pick(info?.why)}</span>}
      <span>{t("Risk")}: {pick(catalog.risk_info?.[risk]) || t(risk)}</span>
    </span>
  );
}

function PermissionPicker({ catalog, role, grants, denies, onChange }: {
  catalog: Catalog; role: string; grants: string[]; denies: string[];
  onChange: (grants: string[], denies: string[]) => void;
}) {
  const defaults = new Set(catalog.role_defaults[role] || []);
  const groups: Record<string, string[]> = {};
  for (const p of Object.keys(catalog.permissions).sort()) (groups[p.split(".")[0]] ||= []).push(p);
  const state = (p: string) => (grants.includes(p) ? "grant" : denies.includes(p) ? "deny" : "default");
  const cycle = (p: string) => {
    const s = state(p);
    const g = grants.filter((x) => x !== p);
    const d = denies.filter((x) => x !== p);
    // default -> (extra grant | deny) -> default
    if (s === "default") (defaults.has(p) ? d : g).push(p);
    onChange(g, d);
  };
  return (
    <div className="stack" style={{ maxHeight: 320, overflow: "auto" }}>
      <div className="muted small">{t("Click a permission to override the role default. Green = granted, red = denied.")}</div>
      {Object.entries(groups).map(([group, perms]) => (
        <div key={group}>
          <div className="small muted" style={{ textTransform: "capitalize", marginBottom: 4 }}>{group}</div>
          <div className="row">{perms.map((p) => {
            const s = state(p);
            const effective = s === "grant" || (s === "default" && defaults.has(p));
            return (
              <Tip key={p} text={<PermissionHelp catalog={catalog} permission={p} />}>
                <button type="button" onClick={() => cycle(p)}
                  className={`badge ${s === "grant" ? "good" : s === "deny" ? "bad" : effective ? "accent" : ""}`} style={{ cursor: "pointer", border: 0 }}>
                  {s === "deny" ? "✕ " : s === "grant" ? "+ " : ""}{pick(catalog.catalog?.[p]?.label) || p}
                </button>
              </Tip>
            );
          })}</div>
        </div>
      ))}
    </div>
  );
}

function EditAdmin({ row, catalog, onClose, onSaved }: { row: AdminRow | null; catalog: Catalog; onClose: () => void; onSaved: () => void }) {
  const { toast, me } = useApp();
  const [sylvexId, setSylvexId] = useState("");
  const [role, setRole] = useState(row?.role || "support");
  const [status, setStatus] = useState(row?.status || "active");
  const [grants, setGrants] = useState<string[]>(row?.grants || []);
  const [denies, setDenies] = useState<string[]>(row?.denies || []);
  // The owner role is never handed out from the console.
  const assignable = catalog.roles.filter((r) => r !== "owner" || row?.role === "owner");
  void me;
  return (
    <ConfirmAction
      title={row ? `${t("Edit admin")} · SYLVEX ${row.sylvex_user_id}` : t("Add admin")}
      confirmLabel={row ? t("Save changes") : t("Add admin")}
      presets={STAFF_REASONS}
      onConfirm={async (reason, extra) => {
        if (row) {
          await patch(`/api/admin/v2/admins/${row.admin_id}`, { role, status, grants, denies, reason, ...extra });
          toast(t("Admin updated"));
        } else {
          // One field: a SYLVEX ID (digits) or the person's Gmail / email.
          const who = sylvexId.trim();
          const target = /^\d{6,20}$/.test(who) ? { sylvex_user_id: who }
            : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(who) ? { email: who.toLowerCase() } : null;
          if (!target) throw new Error(t("Enter the person's SYLVEX ID or email."));
          await post("/api/admin/v2/admins", { ...target, role, grants, denies, reason, ...extra });
          toast(t("Admin added"));
        }
        onSaved();
      }}
      onClose={onClose}
      description={<div className="stack">
        {!row && (
          <label className="field">{t("SYLVEX ID or email of the person")}
            <input value={sylvexId} onChange={(e) => setSylvexId(e.target.value)} placeholder={t("e.g. 110626130001 or name@gmail.com")} autoComplete="off" />
          </label>
        )}
        <div className="grid two" style={{ gap: 10 }}>
          <label className="field">{t("Role")}
            <select value={role} onChange={(e) => setRole(e.target.value)}>{assignable.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</select>
          </label>
          {row && (
            <label className="field">{t("Status")}
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="active">{t("active")}</option><option value="suspended">{t("suspended")}</option><option value="revoked">{t("revoked")}</option>
              </select>
            </label>
          )}
        </div>
        <PermissionPicker catalog={catalog} role={role} grants={grants} denies={denies} onChange={(g, d) => { setGrants(g); setDenies(d); }} />
      </div>}
    />
  );
}

export default function Admins() {
  const { can, me } = useApp();
  const admins = useAsync(() => get<{ items: AdminRow[] }>("/api/admin/v2/admins"), []);
  const catalog = useAsync(() => get<Catalog>("/api/admin/v2/permissions"), []);
  const [editing, setEditing] = useState<AdminRow | "new" | null>(null);

  if (admins.error) return <ErrorNotice message={admins.error} onRetry={admins.reload} />;
  if (!admins.data || !catalog.data) return <Loading />;
  // Only the owner manages the team (the server enforces the same rule).
  const isOwner = me.admin.role === "owner";
  const canEdit = isOwner && can("admins.permissions.edit");

  return (
    <div className="stack">
      <div className="row between">
        <span className="muted small">{t("Admins are SYLVEX accounts. They sign in with Telegram (Mini App) or email + password + 2FA (browser).")}</span>
        {isOwner && can("admins.create") && <button className="btn primary" onClick={() => setEditing("new")}>+ {t("Add admin")}</button>}
      </div>
      {admins.data.items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>{t("Admin")}</th><th>{t("Role")}</th><th>{t("Status")}</th><th>2FA</th><th>{t("Overrides")}</th><th></th></tr></thead>
          <tbody>{admins.data.items.map((a) => (
            <tr key={a.admin_id}>
              <td>
                <div className="cell-main">{a.identity?.display_name || a.identity?.username || `SYLVEX ${a.sylvex_user_id}`}{a.admin_id === me.admin.admin_id ? ` (${t("you")})` : ""}</div>
                <div className="cell-sub">SYLVEX {a.sylvex_user_id}{a.identity?.email ? ` · ${a.identity.email}` : ""}{a.identity?.telegram_id ? ` · TG ${a.identity.telegram_id}` : ""}</div>
              </td>
              <td><span className="badge accent">{roleLabel(a.role)}</span></td>
              <td><StatusBadge status={a.status} /></td>
              <td>{a.totp_enabled ? <span className="badge good">{t("on")}</span> : <span className="badge">{t("off")}</span>}</td>
              <td className="small">
                {a.grants.map((g) => <Tip key={g} icon={false} text={<PermissionHelp catalog={catalog.data!} permission={g} />}><span className="badge good" style={{ marginRight: 4 }}>+{pick(catalog.data!.catalog?.[g]?.label) || g}</span></Tip>)}
                {a.denies.map((d) => <Tip key={d} icon={false} text={<PermissionHelp catalog={catalog.data!} permission={d} />}><span className="badge bad" style={{ marginRight: 4 }}>✕{pick(catalog.data!.catalog?.[d]?.label) || d}</span></Tip>)}
                {!a.grants.length && !a.denies.length && <span className="muted">{t("role defaults")}</span>}
              </td>
              <td className="right">{canEdit && a.admin_id !== me.admin.admin_id && <button className="btn small" onClick={() => setEditing(a)}>{t("Edit")}</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>{t("No admins.")}</Empty>}

      <details className="card">
        <summary className="small" style={{ cursor: "pointer" }}>{t("What each role can do")}</summary>
        <div className="stack section">
          <div className="row">{["low", "medium", "high", "critical"].map((risk) => (
            <Tip key={risk} icon={false} text={pick(catalog.data!.risk_info?.[risk])}><span className={`badge ${RISK_TONE[risk]}`}>{t(risk)}</span></Tip>
          ))}</div>
          {catalog.data.roles.map((r) => (
            <div key={r}><b>{roleLabel(r)}</b>
              <div className="row" style={{ gap: 4, marginTop: 4 }}>{(catalog.data!.role_defaults[r] || []).map((p) => (
                <Tip key={p} icon={false} text={<PermissionHelp catalog={catalog.data!} permission={p} />}>
                  <span className={`badge ${RISK_TONE[catalog.data!.permissions[p]] || ""}`}>{pick(catalog.data!.catalog?.[p]?.label) || p}</span>
                </Tip>
              ))}</div></div>
          ))}
        </div>
      </details>

      {editing && (
        <EditAdmin row={editing === "new" ? null : editing} catalog={catalog.data} onClose={() => setEditing(null)} onSaved={admins.reload} />
      )}
    </div>
  );
}
