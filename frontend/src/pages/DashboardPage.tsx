import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CheckCircle2, AlertTriangle, XCircle, ArrowRight } from "lucide-react";

import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import { StatusBadgeLote } from "@/components/StatusBadge";
import type { LoteResumo } from "@/types";

export function DashboardPage() {
  const { data: aguardandoRevisao = [], isLoading } = useQuery({
    queryKey: ["lotes", "AGUARDANDO_REVISAO"],
    queryFn: async () => {
      const { data } = await api.get<LoteResumo[]>(
        "/api/lotes?status=AGUARDANDO_REVISAO",
      );
      return data;
    },
  });

  const { data: aprovados = [] } = useQuery({
    queryKey: ["lotes", "APROVADO"],
    queryFn: async () => {
      const { data } = await api.get<LoteResumo[]>(
        "/api/lotes?status=APROVADO&limit=10",
      );
      return data;
    },
  });

  const { data: enviados = [] } = useQuery({
    queryKey: ["lotes", "ENVIADO_BANCO"],
    queryFn: async () => {
      const { data } = await api.get<LoteResumo[]>(
        "/api/lotes?status=ENVIADO_BANCO&limit=10",
      );
      return data;
    },
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Lotes aguardando sua revisão e aprovação.
        </p>
      </div>

      {/* Lotes aguardando revisão */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900">
            📥 Aguardando Revisão{" "}
            <span className="text-slate-400">({aguardandoRevisao.length})</span>
          </h2>
        </div>

        {isLoading && (
          <div className="card text-sm text-slate-500">Carregando...</div>
        )}

        {!isLoading && aguardandoRevisao.length === 0 && (
          <div className="card text-sm text-slate-500">
            Nenhum lote aguardando. Quando um novo arquivo for enviado, ele
            aparecerá aqui depois de validado.
          </div>
        )}

        <div className="space-y-3">
          {aguardandoRevisao.map((lote) => (
            <LoteCard key={lote.id} lote={lote} />
          ))}
        </div>
      </section>

      {/* Lotes aprovados (precisam ser enviados ao banco) */}
      {aprovados.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            ✅ Aprovados — Subir no Internet Banking
          </h2>
          <div className="space-y-2">
            {aprovados.map((lote) => (
              <LoteSimples key={lote.id} lote={lote} />
            ))}
          </div>
        </section>
      )}

      {/* Enviados ao banco */}
      {enviados.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">
            📤 Enviados ao Banco — Aguardando Retorno
          </h2>
          <div className="space-y-2">
            {enviados.map((lote) => (
              <LoteSimples key={lote.id} lote={lote} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function LoteCard({ lote }: { lote: LoteResumo }) {
  return (
    <Link
      to={`/app/lotes/${lote.id}`}
      className="card block hover:shadow-md hover:border-brand-200 transition"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-1">
            <h3 className="font-semibold text-slate-900">{lote.cliente.nome}</h3>
            <StatusBadgeLote status={lote.status} />
          </div>
          <p className="text-xs text-slate-500">
            Recebido: {formatDateTime(lote.created_at)} •{" "}
            {lote.total_pagamentos} pagamentos
          </p>
          <p className="text-lg font-semibold text-slate-900 mt-2">
            Total: {formatBRL(lote.valor_total_centavos)}
          </p>

          <div className="flex items-center gap-4 mt-3 text-sm">
            <span className="flex items-center gap-1 text-emerald-700">
              <CheckCircle2 size={16} />
              {lote.total_validos} OK
            </span>
            {lote.total_corrigiveis > 0 && (
              <span className="flex items-center gap-1 text-amber-700">
                <AlertTriangle size={16} />
                {lote.total_corrigiveis} sugestão
              </span>
            )}
            {lote.total_bloqueados > 0 && (
              <span className="flex items-center gap-1 text-red-700">
                <XCircle size={16} />
                {lote.total_bloqueados} bloqueado
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 text-brand-600 font-medium text-sm">
          Revisar Lote <ArrowRight size={16} />
        </div>
      </div>
    </Link>
  );
}

function LoteSimples({ lote }: { lote: LoteResumo }) {
  return (
    <Link
      to={`/app/lotes/${lote.id}`}
      className="card block hover:bg-slate-50 transition"
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="font-medium text-slate-900">{lote.cliente.nome}</span>
          <span className="text-sm text-slate-500 ml-3">
            {lote.total_pagamentos} pagamentos •{" "}
            {formatBRL(lote.valor_total_centavos)}
          </span>
        </div>
        <StatusBadgeLote status={lote.status} />
      </div>
    </Link>
  );
}
