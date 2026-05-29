import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Wallet,
  XCircle,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

interface Pagamento {
  pagamento_id: string;
  lote_id: string;
  valor_centavos: number;
  status: string;
  status_label: string;
  modalidade: string;
  criado_em: string;
  pago_em: string | null;
  motivo_rejeicao: string | null;
}

interface ResumoExtrato {
  total_pago_centavos: number;
  total_pendente_centavos: number;
  total_rejeitado_centavos: number;
  qtd_pagamentos: number;
}

interface ExtratoResponse {
  resumo: ResumoExtrato;
  pagamentos: Pagamento[];
}

function formatarValor(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

const STATUS_STYLE: Record<string, { color: string; icon: typeof CheckCircle2 }> = {
  PAGO: {
    color: "bg-emerald-100 text-emerald-800 border-emerald-200",
    icon: CheckCircle2,
  },
  APROVADO: {
    color: "bg-brand-100 text-brand-800 border-brand-200",
    icon: Clock,
  },
  VALIDO: {
    color: "bg-slate-100 text-slate-700 border-slate-200",
    icon: Clock,
  },
  CORRIGIVEL: {
    color: "bg-amber-100 text-amber-800 border-amber-200",
    icon: AlertCircle,
  },
  BLOQUEADO: {
    color: "bg-red-100 text-red-800 border-red-200",
    icon: XCircle,
  },
  REJEITADO: {
    color: "bg-red-100 text-red-800 border-red-200",
    icon: XCircle,
  },
  NAO_PAGO: {
    color: "bg-red-100 text-red-800 border-red-200",
    icon: XCircle,
  },
};

export function MedicoExtratoPage() {
  const query = useQuery({
    queryKey: ["medico-extrato"],
    queryFn: async () => {
      const res = await api.get<ExtratoResponse>("/api/medico/extrato?limit=200");
      return res.data;
    },
  });

  const resumo = query.data?.resumo;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <Link
            to="/app/medico"
            className="text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-1 mb-1"
          >
            <ArrowLeft size={12} />
            Voltar
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 inline-flex items-center gap-2">
            <Wallet size={22} className="text-brand-700" />
            Meu extrato
          </h1>
          <p className="text-sm text-slate-500">
            Histórico de pagamentos do hospital pra você.
          </p>
        </div>
      </header>

      {/* Resumo */}
      {resumo && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="card border-emerald-200 bg-emerald-50/40">
            <div className="text-[11px] text-emerald-700 uppercase tracking-wide">
              Já pago
            </div>
            <div className="text-xl font-bold text-emerald-900 mt-1">
              {formatarValor(resumo.total_pago_centavos)}
            </div>
          </div>
          <div className="card border-amber-200 bg-amber-50/40">
            <div className="text-[11px] text-amber-700 uppercase tracking-wide">
              Pendente
            </div>
            <div className="text-xl font-bold text-amber-900 mt-1">
              {formatarValor(resumo.total_pendente_centavos)}
            </div>
          </div>
          <div className="card border-red-200 bg-red-50/40">
            <div className="text-[11px] text-red-700 uppercase tracking-wide">
              Rejeitado
            </div>
            <div className="text-xl font-bold text-red-900 mt-1">
              {formatarValor(resumo.total_rejeitado_centavos)}
            </div>
          </div>
          <div className="card">
            <div className="text-[11px] text-slate-500 uppercase tracking-wide">
              Movimentos
            </div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {resumo.qtd_pagamentos}
            </div>
          </div>
        </div>
      )}

      {/* Lista */}
      <div className="card">
        {query.isLoading && (
          <div className="text-sm text-slate-500 py-3">Carregando…</div>
        )}

        {query.data && query.data.pagamentos.length === 0 && (
          <div className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-8 text-center">
            Nenhum pagamento registrado em seu nome ainda.
          </div>
        )}

        {query.data && query.data.pagamentos.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-500 uppercase tracking-wide border-b border-slate-200">
                <tr>
                  <th className="text-left px-2 py-2">Status</th>
                  <th className="text-left px-2 py-2">Modalidade</th>
                  <th className="text-left px-2 py-2">Criado em</th>
                  <th className="text-left px-2 py-2">Pago em</th>
                  <th className="text-right px-2 py-2">Valor</th>
                  <th className="text-left px-2 py-2">Observação</th>
                </tr>
              </thead>
              <tbody>
                {query.data.pagamentos.map((p) => {
                  const style = STATUS_STYLE[p.status] ?? STATUS_STYLE.VALIDO;
                  const Icon = style.icon;
                  return (
                    <tr
                      key={p.pagamento_id}
                      className="border-b border-slate-100"
                    >
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border ${style.color}`}
                        >
                          <Icon size={12} />
                          {p.status_label}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-xs font-mono">
                        {p.modalidade}
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-500">
                        {formatDateTime(p.criado_em)}
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-500">
                        {p.pago_em ? formatDateTime(p.pago_em) : "—"}
                      </td>
                      <td className="px-2 py-2 text-right font-semibold">
                        {formatarValor(p.valor_centavos)}
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-600 max-w-[300px] truncate">
                        {p.motivo_rejeicao ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
