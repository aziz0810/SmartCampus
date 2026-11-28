"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { apiLogin, apiMe, apiRegister, UserOut } from "@/lib/authApi";

const AUTH_STORAGE_KEY = "smartcampus.auth";

interface AuthState {
  user: UserOut | null;
  accessToken: string | null;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    fullName: string,
    password: string,
    visitorSessionId?: string,
  ) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
  });
  const [isLoading, setIsLoading] = useState(true);

  // Restore from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as AuthState;
        if (parsed.accessToken && parsed.user) {
          // Re-validate token against /me
          apiMe(parsed.accessToken)
            .then((user) => {
              setState({ user, accessToken: parsed.accessToken });
            })
            .catch(() => {
              localStorage.removeItem(AUTH_STORAGE_KEY);
            })
            .finally(() => setIsLoading(false));
          return;
        }
      }
    } catch {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
    setIsLoading(false);
  }, []);

  const persist = useCallback((next: AuthState) => {
    setState(next);
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token, user } = await apiLogin(email, password);
      persist({ user, accessToken: access_token });
    },
    [persist],
  );

  const register = useCallback(
    async (
      email: string,
      fullName: string,
      password: string,
      visitorSessionId?: string,
    ) => {
      const { access_token, user } = await apiRegister(
        email,
        fullName,
        password,
        visitorSessionId,
      );
      persist({ user, accessToken: access_token });
    },
    [persist],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    setState({ user: null, accessToken: null });
  }, []);

  const value = useMemo(
    () => ({ ...state, login, register, logout, isLoading }),
    [state, login, register, logout, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
