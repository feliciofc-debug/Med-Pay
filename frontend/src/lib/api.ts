import axios, { type AxiosError } from "axios";
import { DEMO_MODE, demoAdapter } from "@/lib/demo";

// Resolve baseURL com fallback robusto:
// - Se VITE_API_URL definida: usa.
// - Senão, se a página tá em HTTPS (produção): usa o backend do Render.
// - Senão (dev local): usa localhost.
function resolveBaseURL(): string {
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.length > 0) {
    return envUrl;
  }
  if (
    typeof window !== "undefined" &&
    window.location.protocol === "https:"
  ) {
    return "https://medpag-api.onrender.com";
  }
  return "http://localhost:8000";
}

const baseURL = resolveBaseURL();

export const api = axios.create({
  baseURL,
  withCredentials: !DEMO_MODE, // em demo não precisa de cookie
  timeout: 30_000,
  // Em modo demo, intercepta TODAS as requests e devolve dados mockados.
  ...(DEMO_MODE ? { adapter: demoAdapter } : {}),
});

if (DEMO_MODE) {
  // Aviso visual no console pra deixar claro que tá em modo demo.
  // eslint-disable-next-line no-console
  console.info(
    "%c[MedPag] MODO DEMO ATIVO",
    "background: #d29215; color: #1f2412; font-weight: bold; padding: 4px 8px; border-radius: 4px;",
    "\nAPI real desativada. Usando dados de exemplo no navegador.",
    "\nLogin: demo@medpag.local  /  Senha: demo123",
  );
}

// Interceptor: adiciona Bearer token (fallback pra dev quando cookie não está disponível)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("medpag_access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor: redireciona em 401 (sessão expirada)
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: { code?: string; message?: string } }>) => {
    if (error.response?.status === 401) {
      const path = window.location.pathname;
      if (path !== "/login") {
        localStorage.removeItem("medpag_access_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

/** Extrai mensagem de erro padronizada do MedPag. */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { error?: { message?: string }; errors?: Array<{ message?: string }> }
      | undefined;
    if (data?.error?.message) return data.error.message;
    if (data?.errors?.[0]?.message) return data.errors[0].message ?? "Erro de validação";
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Erro desconhecido";
}
