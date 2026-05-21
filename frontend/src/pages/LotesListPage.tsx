import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { X } from "lucide-react";

import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import { StatusBadgeLote } from "@/components/StatusBadge";
import type { LoteResumo, UserAdmin, Cliente } from "@/types";

export function LotesListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const operadorId = searchParams.get("operador");
  const clienteId = searchParams.get("cliente");

  const { data: lotes = [], isLoading } = useQuery({
    queryKey: ["lotes", "all", operadorId, clienteId],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("limit", "100");
      if (operadorId) params.set("operador", operadorId);
      if (clienteId) params.set("cliente_id", clienteId);
      const { data } = await api.get<LoteResumo[]>(
        `/api/lotes?${params.toString()}`,
      );
      return data;
    },
  });

  const { data: operadorInfo } = useQuery({
    queryKey: ["admin", "user", operadorId],
    enabled: !!operadorId,
    queryFn: async () => {
      const { data } = await api.get<UserAdmin[]>("/api/admin/users");
      return data.find((u) => u.id === operadorId) ?? null;
    },
  });

  const { data: clienteInfo } = useQuery({
    queryKey: ["cliente", clienteId],
    enabled: !!clienteId,
    queryFn: async () => {
      const { data } = await api.get<Cliente[]>("/api/clientes/");
      return data.find((c) => c.id === clienteId) ?? null;
    },
  });

  const limparFiltros = () => setSearchParams({});

  const filtroAtivo = !!operadorId || !!clienteId;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Todos os Lotes</h1>
        {filtroAtivo && (
          <button
            type="button"
            onClick={limparFiltros}
            className="btn-secondary text-xs"
          >
            <X size={14} /> Limpar filtros
          </button>
        )}
      </div>

      {filtroAtivo && (
        <div className="card bg-accent-50/40 border-accent-200 text-sm text-brand-800">
          <strong>Filtrando por:</strong>{" "}
          {operadorId && (
            <span>
              operador{" "}
              <span className="font-semibold text-accent-700">
                {operadorInfo?.nome ?? operadorId.slice(0, 8)}
              </span>
            </span>
          )}
          {operadorId && clienteId && " · "}
          {clienteId && (
            <span>
              hospital{" "}
              <span className="font-semibold text-accent-700">
                {clienteInfo?.nome ?? clienteId.slice(0, 8)}
              </span>
            </span>
          )}
        </div>
      )}

      {isLoading && (
        <div className="card text-sm text-slate-500">Carregando...</div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
            <tr>
              <th className="text-left p-3">Cliente</th>
              <th className="text-left p-3">Arquivo</th>
              <th className="text-right p-3">Pagamentos</th>
              <th className="text-right p-3">Total</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Recebido</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {lotes.map((lote) => (
              <tr key={lote.id} className="hover:bg-slate-50">
                <td className="p-3 font-medium">
                  <Link
                    to={`/app/lotes/${lote.id}`}
                    className="text-brand-600 hover:underline"
                  >
                    {lote.cliente.nome}
                  </Link>
                </td>
                <td className="p-3 text-slate-500 truncate max-w-xs">
                  {lote.nome_arquivo}
                </td>
                <td className="p-3 text-right">{lote.total_pagamentos}</td>
                <td className="p-3 text-right font-medium">
                  {formatBRL(lote.valor_total_centavos)}
                </td>
                <td className="p-3">
                  <StatusBadgeLote status={lote.status} />
                </td>
                <td className="p-3 text-xs text-slate-500">
                  {formatDateTime(lote.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && lotes.length === 0 && (
          <div className="p-6 text-sm text-slate-500 text-center">
            {filtroAtivo
              ? "Nenhum lote encontrado com esse filtro."
              : "Nenhum lote ainda. Faça o primeiro upload!"}
          </div>
        )}
      </div>
    </div>
  );
}
