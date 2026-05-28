/**
 * Hook de feature flags por cliente.
 *
 * Como o sistema hoje é BPO (usuários internos da MedPag operam várias
 * empresas-cliente), o hook trabalha por `clienteId` explícito — ele
 * pergunta ao backend "esse cliente tem feature X?".
 *
 * Quando migrarmos pra multi-tenant (usuário pertence a 1 cliente),
 * adicionamos uma variante `useMinhaFeature("x")` que pega o cliente
 * do usuário logado.
 *
 * Uso:
 *   const { tem, loading } = useFeature(clienteId, "modulo.sentinela_vital");
 *   if (tem) renderiza Sentinela;
 *
 *   // Pra limites:
 *   const { valor } = useLimite(clienteId, "limite.pagamentos_mes");
 */

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ClienteAssinatura } from "@/types";

// Cache em memória pra evitar refetch entre componentes da mesma tela.
const _cache = new Map<
  string,
  { dado: ClienteAssinatura; ts: number; loading: boolean }
>();
const TTL_MS = 30_000;

interface AssinaturaResult {
  assinatura: ClienteAssinatura | null;
  loading: boolean;
  reload: () => Promise<void>;
}

export function useClienteAssinatura(
  clienteId: string | null | undefined,
): AssinaturaResult {
  const [assinatura, setAssinatura] = useState<ClienteAssinatura | null>(null);
  const [loading, setLoading] = useState(false);

  const carregar = useCallback(async () => {
    if (!clienteId) {
      setAssinatura(null);
      return;
    }
    const cached = _cache.get(clienteId);
    if (cached && Date.now() - cached.ts < TTL_MS) {
      setAssinatura(cached.dado);
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get<ClienteAssinatura>(
        `/api/planos/clientes/${clienteId}`,
      );
      _cache.set(clienteId, { dado: data, ts: Date.now(), loading: false });
      setAssinatura(data);
    } catch {
      setAssinatura(null);
    } finally {
      setLoading(false);
    }
  }, [clienteId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const reload = useCallback(async () => {
    if (clienteId) _cache.delete(clienteId);
    await carregar();
  }, [carregar, clienteId]);

  return { assinatura, loading, reload };
}

export function useFeature(
  clienteId: string | null | undefined,
  chave: string,
): { tem: boolean; loading: boolean } {
  const { assinatura, loading } = useClienteAssinatura(clienteId);
  const valor = assinatura?.features_efetivas?.[chave];
  return { tem: Boolean(valor), loading };
}

export function useLimite(
  clienteId: string | null | undefined,
  chave: string,
): { valor: number | null; loading: boolean } {
  const { assinatura, loading } = useClienteAssinatura(clienteId);
  const raw = assinatura?.features_efetivas?.[chave];
  const valor =
    raw === null || raw === undefined ? null : Number(raw);
  return {
    valor: Number.isFinite(valor) ? (valor as number) : null,
    loading,
  };
}

/** Limpa o cache de assinatura (chamado após edits). */
export function invalidarCacheAssinatura(clienteId?: string): void {
  if (clienteId) {
    _cache.delete(clienteId);
  } else {
    _cache.clear();
  }
}
