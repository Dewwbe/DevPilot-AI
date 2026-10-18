import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Me } from "./api/client";

interface AuthState {
  loading: boolean;
  me: Me | null;
  /** true when sign-in is switched on and nobody is signed in */
  needsLogin: boolean;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState>({ loading: true, me: null, needsLogin: false, signOut: async () => {} });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    api.me().then(setMe).catch(() => setMe({ authenticated: false, auth_enabled: false, user: null }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    // Any API call that gets a 401 (expired session) drops us back to the sign-in screen.
    const on = () => setMe((m) => (m ? { ...m, authenticated: false, auth_enabled: true, user: null } : m));
    window.addEventListener("devpilot:unauthorized", on);
    return () => window.removeEventListener("devpilot:unauthorized", on);
  }, [refresh]);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {});
    setMe({ authenticated: false, auth_enabled: true, user: null });
  }, []);

  const needsLogin = !!me && me.auth_enabled && !me.authenticated;
  return <Ctx.Provider value={{ loading, me, needsLogin, signOut }}>{children}</Ctx.Provider>;
}
