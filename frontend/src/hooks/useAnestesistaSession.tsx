import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  ANESTESISTA_MEDICO_KEY,
  ANESTESISTA_TOKEN_KEY,
  anestesistaApi,
} from "@/lib/anestesistaApi";
import type { CrmLoginResponse, MedicoAnestesista } from "@/types";

interface AnestesistaSessionState {
  medico: MedicoAnestesista | null;
  loading: boolean;
  loginPorCrm: (crm: string, clienteId?: string) => Promise<MedicoAnestesista>;
  logout: () => void;
}

const Ctx = createContext<AnestesistaSessionState | null>(null);

function lerMedicoLocal(): MedicoAnestesista | null {
  try {
    const raw = localStorage.getItem(ANESTESISTA_MEDICO_KEY);
    return raw ? (JSON.parse(raw) as MedicoAnestesista) : null;
  } catch {
    return null;
  }
}

export function AnestesistaSessionProvider({ children }: { children: ReactNode }) {
  const [medico, setMedico] = useState<MedicoAnestesista | null>(() =>
    lerMedicoLocal(),
  );
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const token = localStorage.getItem(ANESTESISTA_TOKEN_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelado = false;
    void anestesistaApi
      .get<MedicoAnestesista>("/api/anestesista/me")
      .then((res) => {
        if (cancelado) return;
        setMedico(res.data);
        localStorage.setItem(ANESTESISTA_MEDICO_KEY, JSON.stringify(res.data));
      })
      .catch(() => {
        if (cancelado) return;
        setMedico(null);
        localStorage.removeItem(ANESTESISTA_TOKEN_KEY);
        localStorage.removeItem(ANESTESISTA_MEDICO_KEY);
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const loginPorCrm = useCallback(
    async (crm: string, clienteId?: string): Promise<MedicoAnestesista> => {
      const { data } = await anestesistaApi.post<CrmLoginResponse>(
        "/api/anestesista/login",
        { crm, cliente_id: clienteId ?? null },
      );
      localStorage.setItem(ANESTESISTA_TOKEN_KEY, data.access_token);
      localStorage.setItem(ANESTESISTA_MEDICO_KEY, JSON.stringify(data.medico));
      setMedico(data.medico);
      return data.medico;
    },
    [],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(ANESTESISTA_TOKEN_KEY);
    localStorage.removeItem(ANESTESISTA_MEDICO_KEY);
    setMedico(null);
  }, []);

  return (
    <Ctx.Provider value={{ medico, loading, loginPorCrm, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAnestesistaSession(): AnestesistaSessionState {
  const ctx = useContext(Ctx);
  if (!ctx)
    throw new Error(
      "useAnestesistaSession deve ser usado dentro de AnestesistaSessionProvider",
    );
  return ctx;
}
