import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const { data } = await api.get<User>("/api/auth/me");
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<{
      access_token: string;
      refresh_token: string;
    }>("/api/auth/login", { email, password });
    localStorage.setItem("medpag_access_token", data.access_token);
    localStorage.setItem("medpag_refresh_token", data.refresh_token);
    await fetchMe();
  }, [fetchMe]);

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } finally {
      localStorage.removeItem("medpag_access_token");
      localStorage.removeItem("medpag_refresh_token");
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
