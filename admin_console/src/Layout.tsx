import { FormEvent, useEffect, useState } from "react";
import { post } from "./api";
import { useApp } from "./state";
import { channelLabel, LangSwitch, roleLabel, t } from "./i18n";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import UserDetail from "./pages/UserDetail";
import Generations from "./pages/Generations";
import Payments from "./pages/Payments";
import Broadcast from "./pages/Broadcast";
import Inbox from "./pages/Inbox";
import Reviews from "./pages/Reviews";
import Content from "./pages/Content";
import Errors from "./pages/Errors";
import Admins from "./pages/Admins";
import Audit from "./pages/Audit";
import System from "./pages/System";
import Account from "./pages/Account";

type NavItem = { key: string; label: string; icon: string; permission?: string; anyOf?: string[]; group?: string };

export const NAV: NavItem[] = [
  { key: "dashboard", label: "Dashboard", icon: "◧", permission: "dashboard.view" },
  { key: "users", label: "Users", icon: "◉", permission: "users.view" },
  { key: "generations", label: "Generations", icon: "✦", permission: "generations.view" },
  { key: "payments", label: "Payments", icon: "◈", permission: "payments.view" },
  // Messages: one menu entry, its parts as tabs (see MESSAGE_TABS).
  { key: "inbox", label: "Conversations", icon: "✉", permission: "messages.send", group: "messages" },
  { key: "sales", label: "Sales department", icon: "✉", permission: "messages.send", group: "messages" },
  { key: "reviews", label: "Reviews", icon: "✉", permission: "users.view", group: "messages" },
  { key: "broadcast", label: "Announcements", icon: "✉", anyOf: ["broadcast.send", "messages.send"], group: "messages" },
  { key: "content", label: "Content", icon: "▤", permission: "content.references.manage" },
  { key: "errors", label: "Errors", icon: "⚠", permission: "errors.view" },
  { key: "admins", label: "Admins", icon: "⛨", permission: "admins.view" },
  { key: "audit", label: "Audit log", icon: "☰", permission: "audit.view" },
  { key: "system", label: "System", icon: "⚙", permission: "dashboard.view" },
  { key: "account", label: "Account & security", icon: "☺" },
];

const TITLES: Record<string, string> = Object.fromEntries(NAV.map((n) => [n.key, n.group ? "Messages" : n.label]));

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
  const currentGroup = NAV.find((n) => n.key === current)?.group || "";
  const groupTabs = currentGroup ? visible.filter((n) => n.group === currentGroup) : [];

  // Unread conversations and sales requests, shown next to Messages and
  // on its tabs.
  const [unreadBy, setUnreadBy] = useState({ conversations: 0, sales: 0 });
  const inboxUnread = unreadBy.conversations + unreadBy.sales;
  const canInbox = can("messages.send");
  useEffect(() => {
    if (!canInbox) return;
    let alive = true;
    const load = () => post<{ unread_by: { conversations: number; sales: number } }>("/api/admin/inbox/list", { limit: 1 })
      .then((r) => alive && setUnreadBy(r.unread_by || { conversations: 0, sales: 0 })).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 60000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [canInbox, current]);

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
      case "broadcast": return <Broadcast to={params.get("to") || ""} />;
      case "inbox": return <Inbox key="inbox" threadId={rest[0] || ""} />;
      case "sales": return <Inbox key="sales" sales threadId={rest[0] || ""} />;
      case "reviews": return <Reviews />;
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
        {visible.filter((n, i) => !n.group || visible.findIndex((m) => m.group === n.group) === i).map((n) => (
          <button key={n.key} className={`nav-item ${current === n.key || (n.group && n.group === currentGroup) ? "active" : ""}`}
            onClick={() => navigate(n.key)}>
            <span className="nav-icon">{n.icon}</span>{t(n.group ? "Messages" : n.label)}
            {n.group === "messages" && inboxUnread > 0 && <span className="nav-count">{inboxUnread}</span>}
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
        {groupTabs.length > 1 && (
          <div className="tabs section-tabs">
            {groupTabs.map((n) => {
              const unread = n.key === "inbox" ? unreadBy.conversations : n.key === "sales" ? unreadBy.sales : 0;
              return (
                <button key={n.key} className={`tab ${current === n.key ? "active" : ""}`} onClick={() => go(n.key)}>
                  {t(n.label)}{unread > 0 && <span className="nav-count">{unread}</span>}
                </button>
              );
            })}
          </div>
        )}
        {page}
      </main>
    </div>
  );
}
