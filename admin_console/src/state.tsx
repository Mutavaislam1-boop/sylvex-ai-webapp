import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";

export type Admin = {
  admin_id: number; sylvex_user_id: string; role: string; status: string; permissions: string[];
  grants: string[]; denies: string[]; totp_enabled: boolean;
};
export type Me = {
  admin: Admin;
  identity: { display_name?: string | null; username?: string | null; telegram_id?: number | null; email?: string | null } | null;
  session: { channel: string; reauth_fresh: boolean };
};

type Toast = { id: number; text: string; bad?: boolean };
type Ctx = {
  me: Me;
  can: (permission: string) => boolean;
  toast: (text: string, bad?: boolean) => void;
  go: (path: string) => void;
  refreshMe: () => Promise<void>;
};

const AppContext = createContext<Ctx | null>(null);
export const useApp = () => {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("AppContext missing");
  return ctx;
};

export function AppProvider({ me, go, refreshMe, children }: { me: Me; go: (p: string) => void; refreshMe: () => Promise<void>; children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = useCallback((text: string, bad = false) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, bad }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const can = useCallback((p: string) => me.admin.role === "owner" || me.admin.permissions.includes(p), [me]);
  const value = useMemo(() => ({ me, can, toast, go, refreshMe }), [me, can, toast, go, refreshMe]);
  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="toasts">{toasts.map((t) => <div key={t.id} className={`toast ${t.bad ? "bad" : ""}`}>{t.text}</div>)}</div>
    </AppContext.Provider>
  );
}
