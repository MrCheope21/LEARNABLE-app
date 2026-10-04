import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SESSION_EXPIRED_EVENT, tokenStore, type Schemas } from "../api/client";
import { auth, deviceTimezone } from "../api/endpoints";
import { drafts } from "../features/study/drafts";

interface AuthState {
  isSignedIn: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, language?: Schemas["UserCreate"]["language"]) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [isSignedIn, setSignedIn] = useState(() => tokenStore.get() !== null);

  const signOut = useCallback(() => {
    tokenStore.clear();
    // Nothing from one account may survive into the next session: cached data and drafts.
    queryClient.clear();
    drafts.clearAll();
    setSignedIn(false);
  }, [queryClient]);

  useEffect(() => {
    const expired = () => {
      queryClient.clear();
      setSignedIn(false);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  }, [queryClient]);

  const signIn = useCallback(async (email: string, password: string) => {
    const token = await auth.login({ email, password });
    // Whatever was cached (e.g. after an expired session) belonged to whoever used it before.
    queryClient.clear();
    tokenStore.set(token.access_token);
    setSignedIn(true);
  }, [queryClient]);

  const register = useCallback(
    async (email: string, password: string, language?: Schemas["UserCreate"]["language"]) => {
      await auth.register({ email, password, timezone: deviceTimezone(), language: language ?? "en" });
      await signIn(email, password);
    },
    [signIn],
  );

  const value = useMemo(
    () => ({ isSignedIn, signIn, register, signOut }),
    [isSignedIn, signIn, register, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}
