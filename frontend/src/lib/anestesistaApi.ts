import axios, { type AxiosError } from "axios";

// Mesma estratégia de resolução do `api.ts`.
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

export const ANESTESISTA_TOKEN_KEY = "medpag_anestesista_token";
export const ANESTESISTA_MEDICO_KEY = "medpag_anestesista_medico";

export const anestesistaApi = axios.create({
  baseURL: resolveBaseURL(),
  withCredentials: false, // não usa cookie da sessão admin
  timeout: 30_000,
});

// Sempre envia o token do anestesista no Authorization. NÃO mistura
// com o `medpag_access_token` do operador BPO.
anestesistaApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(ANESTESISTA_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Em 401, derruba a sessão do anestesista e volta pro login.
anestesistaApi.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: { code?: string; message?: string } }>) => {
    const status = error.response?.status;
    if (status === 401) {
      const path = window.location.pathname;
      localStorage.removeItem(ANESTESISTA_TOKEN_KEY);
      localStorage.removeItem(ANESTESISTA_MEDICO_KEY);
      if (path.startsWith("/anestesista")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export function getAnestesistaErrorMessage(error: unknown): string {
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
