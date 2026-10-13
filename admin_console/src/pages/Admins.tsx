import { useState } from "react";
import { get, patch, post } from "../api";
import { useApp } from "../state";
import { ConfirmAction, Empty, ErrorNotice, Identity, Loading, StatusBadge, useAsync } from "../ui";

type AdminRow = {
  admin_id: number; sylvex_user_id: string; role: string; status: string; grants: string[]; denies: string[];
  permissions: string[]; totp_enabled: boolean; identity: Identity | null;
};
type Catalog = { permissions: Record<string, string>; roles: string[]; role_defaults: Record<string, string[]> };

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner", administrator: "Administrator", finance: "Finance", support: "Support",
  moderator: "Moderator", analyst: "Analyst", read_only: "Read only",
};

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
      <div className="muted small">Click a permission to override the role default. Green = granted, red = denied.</div>
      {Object.entries(groups).map(([group, perms]) => (
        <div key={group}>
          <div className="small muted" style={{ textTransform: "capitalize", marginBottom: 4 }}>{group}</div>
          <div className="row">{perms.map((p) => {
            const s = state(p);
            const effective = s === "grant" || (s === "default" && defaults.has(p));
            return (
              <button key={p} type="button" onClick={() => cycle(p)} title={`risk: ${catalog.permissions[p]}`}
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
      title={row ? `Edit admin · SYLVEX ${row.sylvex_user_id}` : "Add admin"}
      confirmLabel={row ? "Save changes" : "Add admin"}
      onConfirm={async (reason) => {
        if (row) {
          await patch(`/api/admin/v2/admins/${row.admin_id}`, { role, status, grants, denies, reason });
          toast("Admin updated");
        } else {
          if (!/^\d{6,20}$/.test(sylvexId.trim())) throw new Error("Enter the person's SYLVEX ID (digits).");
          await post("/api/admin/v2/admins", { sylvex_user_id: sylvexId.trim(), role, grants, denies, reason });
          toast("Admin added");
        }
        onSaved();
      }}
      onClose={onClose}
      description={<div className="stack">
        {!row && (
          <label className="field">SYLVEX ID of the person
            <input value={sylvexId} onChange={(e) => setSylvexId(e.target.value)} placeholder="e.g. 110626130001" inputMode="numeric" />
          </label>
        )}
        <div className="grid two" style={{ gap: 10 }}>
          <label className="field">Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>{assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}</select>
          </label>
          {row && (
            <label className="field">Status
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="active">Active</option><option value="suspended">Suspended</option><option value="revoked">Revoked</option>
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
        <span className="muted small">Admins are SYLVEX accounts. They sign in with Telegram (Mini App) or email + password + 2FA (browser).</span>
        {can("admins.create") && <button className="btn primary" onClick={() => setEditing("new")}>+ Add admin</button>}
      </div>
      {admins.data.items.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>Admin</th><th>Role</th><th>Status</th><th>2FA</th><th>Overrides</th><th></th></tr></thead>
          <tbody>{admins.data.items.map((a) => (
            <tr key={a.admin_id}>
              <td>
                <div className="cell-main">{a.identity?.display_name || a.identity?.username || `SYLVEX ${a.sylvex_user_id}`}{a.admin_id === me.admin.admin_id ? " (you)" : ""}</div>
                <div className="cell-sub">SYLVEX {a.sylvex_user_id}{a.identity?.email ? ` · ${a.identity.email}` : ""}{a.identity?.telegram_id ? ` · TG ${a.identity.telegram_id}` : ""}</div>
              </td>
              <td><span className="badge accent">{ROLE_LABEL[a.role] || a.role}</span></td>
              <td><StatusBadge status={a.status} /></td>
              <td>{a.totp_enabled ? <span className="badge good">on</span> : <span className="badge">off</span>}</td>
              <td className="small">
                {a.grants.map((g) => <span key={g} className="badge good" style={{ marginRight: 4 }}>+{g}</span>)}
                {a.denies.map((d) => <span key={d} className="badge bad" style={{ marginRight: 4 }}>✕{d}</span>)}
                {!a.grants.length && !a.denies.length && <span className="muted">role defaults</span>}
              </td>
              <td className="right">{canEdit && a.admin_id !== me.admin.admin_id && <button className="btn small" onClick={() => setEditing(a)}>Edit</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty>No admins.</Empty>}

      <details className="card">
        <summary className="small" style={{ cursor: "pointer" }}>What each role can do</summary>
        <div className="stack section">
          {catalog.data.roles.map((r) => (
            <div key={r}><b>{ROLE_LABEL[r] || r}</b>
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
