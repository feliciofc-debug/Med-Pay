import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import { StatusBadgeLote } from "@/components/StatusBadge";
import type { LoteResumo } from "@/types";

export function LotesListPage() {
  const { data: lotes = [], isLoading } = useQuery({
    queryKey: ["lotes", "all"],
    queryFn: async () => {
      const { data } = await api.get<LoteResumo[]>("/api/lotes?limit=100");
      return data;
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Todos os Lotes</h1>

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
            Nenhum lote ainda. Faça o primeiro upload!
          </div>
        )}
      </div>
    </div>
  );
}
