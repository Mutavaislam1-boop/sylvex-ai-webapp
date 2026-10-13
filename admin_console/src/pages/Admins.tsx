import { useState } from "react";
import { get, patch, post } from "../api";
import { useApp } from "../state";
import { roleLabel, t } from "../i18n";
import { ConfirmAction, Empty, ErrorNotice, Identity, Loading, StatusBadge, useAsync } from "../ui";

type AdminRow = {
  admin_id: number; sylvex_user_id: string; role: string; status: string; grants: string[]; denies: string[];
  permissions: string[]; totp_enabled: boolean; identity: Identity | null;
};
type Catalog = { permissions: Record<string, string>; roles: string[]; role_defaults: Record<string, string[]> };

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
              <button key={p} type="button" onClick={() => cycle(p)} title={`${t("Risk")}: ${t(catalog.permissions[p])}`}
                className={`badge ${s === "grant" ? "good" : s === "deny" ? "bad" : effective ? "accent" : ""}`} style={{ cursor: "pointer", border: 0 }}>
                {s === "deny" ? "✕ " : s === "grant" ? "+ " : ""}{p}
              </button>
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
  const assignable = catalog.roles.filter((r) => me.admin.role === "owner" || r !== "owner");
  return (
    <ConfirmAction
      title={row ? `${t("Edit admin")} · SYLVEX ${row.sylvex_user_id}` : t("Add admin")}
      confirmLabel={row ? t("Save changes") : t("Add admin")}
      onConfirm={async (reason) => {
        if (row) {
          await patch(`/api/admin/v2/admins/${row.admin_id}`, { role, status, grants, denies, reason });
          toast(t("Admin updated"));
        } else {
          // One field: a SYLVEX ID (digits) or the person's Gmail / email.
          const who = sylvexId.trim();
          const target = /^\d{6,20}$/.test(who) ? { sylvex_user_id: who }
            : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(who) ? { email: who.toLowerCase() } : null;
          if (!target) throw new Error(t("Enter the person's SYLVEX ID or email."));
          await post("/api/admin/v2/admins", { ...target, role, grants, denies, reason });
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
  const canEdit = can("admins.permissions.edit");

  return (
    <div className="stack">
      <div className="row between">
        <span className="muted small">{t("Admins are SYLVEX accounts. They sign in with Telegram (Mini App) or email + password + 2FA (browser).")}</span>
        {can("admins.create") && <button className="btn primary" onClick={() => setEditing("new")}>+ {t("Add admin")}</button>}
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
                {a.grants.map((g) => <span key={g} className="badge good" style={{ marginRight: 4 }}>+{g}</span>)}
                {a.denies.map((d) => <span key={d} className="badge bad" style={{ marginRight: 4 }}>✕{d}</span>)}
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
          {catalog.data.roles.map((r) => (
            <div key={r}><b>{roleLabel(r)}</b>
              <div className="small muted">{(catalog.data!.role_defaults[r] || []).join(", ")}</div></div>
          ))}
        </div>
      </details>

      {editing && (
        <EditAdmin row={editing === "new" ? null : editing} catalog={catalog.data} onClose={() => setEditing(null)} onSaved={admins.reload} />
      )}
    </div>
  );
}
