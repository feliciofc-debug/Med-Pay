import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combina classnames com tailwind-merge (resolve conflitos como p-2 + p-4). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Formata centavos para R$ X,XX */
export function formatBRL(centavos: number | null | undefined): string {
  if (centavos == null) return "—";
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

/** Formata data ISO para DD/MM/AAAA HH:MM */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
