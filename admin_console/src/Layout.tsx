import { FormEvent, useState } from "react";
import { post } from "./api";
import { useApp } from "./state";
import { channelLabel, LangSwitch, roleLabel, t } from "./i18n";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import UserDetail from "./pages/UserDetail";
import Generations from "./pages/Generations";
import Payments from "./pages/Payments";
import Broadcast from "./pages/Broadcast";
import Content from "./pages/Content";
import Errors from "./pages/Errors";
import Admins from "./pages/Admins";
import Audit from "./pages/Audit";
import System from "./pages/System";
import Account from "./pages/Account";

type NavItem = { key: string; label: string; icon: string; permission?: string; anyOf?: string[] };

export const NAV: NavItem[] = [
  { key: "dashboard", label: "Dashboard", icon: "◧", permission: "dashboard.view" },
  { key: "users", label: "Users", icon: "◉", permission: "users.view" },
  { key: "generations", label: "Generations", icon: "✦", permission: "generations.view" },
  { key: "payments", label: "Payments", icon: "◈", permission: "payments.view" },
  { key: "broadcast", label: "Messages", icon: "✉", anyOf: ["broadcast.send", "messages.send"] },
  { key: "content", label: "Content", icon: "▤", permission: "content.references.manage" },
  { key: "errors", label: "Errors", icon: "⚠", permission: "errors.view" },
  { key: "admins", label: "Admins", icon: "⛨", permission: "admins.view" },
  { key: "audit", label: "Audit log", icon: "☰", permission: "audit.view" },
  { key: "system", label: "System", icon: "⚙", permission: "dashboard.view" },
  { key: "account", label: "Account & security", icon: "☺" },
];

const TITLES: Record<string, string> = Object.fromEntries(NAV.map((n) => [n.key, n.label]));

export default function Layout({ route, onSignedOut }: { route: string[]; onSignedOut: () => void }) {
  const { me, can, go } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const visible = NAV.filter((n) => (n.permission ? can(n.permission) : n.anyOf ? n.anyOf.some(can) : true));
  const [head = "", ...rest] = route;
  const [section, queryString = ""] = head.split("?");
  const params = new URLSearchParams(queryString);
  const allowed = visible.some((n) => n.key === section);
  const current = allowed ? section : visible[0]?.key || "account";

  const navigate = (key: string) => {
    setMenuOpen(false);
    go(key);
  };
  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    if (search.trim()) go(`users?q=${encodeURIComponent(search.trim())}`);
  };
  const signOut = async () => {
    try { await post("/api/admin/v2/auth/logout"); } catch { /* session may already be gone */ }
    onSignedOut();
  };

  const page = (() => {
    switch (current) {
      case "dashboard": return <Dashboard />;
      case "users": return rest[0] ? <UserDetail refId={rest[0]} /> : <Users query={params.get("q") || ""} />;
      case "generations": return <Generations sylvexUserId={params.get("sylvex") || ""} />;
      case "payments": return <Payments />;
      case "broadcast": return <Broadcast />;
      case "content": return <Content />;
      case "errors": return <Errors />;
      case "admins": return <Admins />;
      case "audit": return <Audit target={params.get("target") || ""} />;
      case "system": return <System />;
      default: return <Account onSignedOut={onSignedOut} />;
    }
  })();
  const name = me.identity?.display_name || me.identity?.username || `SYLVEX ${me.admin.sylvex_user_id}`;

  return (
    <div className="shell">
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand"><span className="brand-mark">S</span>SYLVEX Admin</div>
        {visible.map((n) => (
          <button key={n.key} className={`nav-item ${current === n.key ? "active" : ""}`} onClick={() => navigate(n.key)}>
            <span className="nav-icon">{n.icon}</span>{t(n.label)}
          </button>
        ))}
        <div className="sidebar-foot">
          <div style={{ fontWeight: 600, color: "var(--text)" }}>{name}</div>
          <div>{roleLabel(me.admin.role)} · {channelLabel(me.session.channel)}</div>
          <button className="btn small ghost" style={{ paddingLeft: 0, marginTop: 6 }} onClick={signOut}>{t("Sign out")}</button>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <button className="btn small menu-toggle" onClick={() => setMenuOpen(true)} aria-label={t("Menu")}>☰</button>
          <h1>{rest[0] && current === "users" ? t("User") : t(TITLES[current] || "Admin")}</h1>
          <LangSwitch />
          {can("users.view") && (
            <form className="search-global" onSubmit={submitSearch}>
              <input placeholder={t("Search users: SYLVEX ID, Telegram ID, email, @username, payment ID")} value={search} onChange={(e) => setSearch(e.target.value)} />
            </form>
          )}
        </div>
        {page}
      </main>
    </div>
  );
}
