import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  Download,
  FileSpreadsheet,
  ShieldCheck,
  TrendingUp,
  Users,
  XCircle,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import type { RelatorioErros } from "@/types";

const JANELAS = [
  { dias: 7, label: "Últimos 7 dias" },
  { dias: 30, label: "Últimos 30 dias" },
  { dias: 90, label: "Últimos 90 dias" },
  { dias: 180, label: "Últimos 6 meses" },
  { dias: 365, label: "Último ano" },
];

export function AdminRelatorioErrosPage() {
  const [dias, setDias] = useState(30);
  const navigate = useNavigate();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "relatorio-erros", dias],
    queryFn: async () => {
      const { data } = await api.get<RelatorioErros>(
        `/api/admin/relatorio-erros?dias=${dias}`,
      );
      return data;
    },
  });

  const exportCSV = () => {
    if (!data) return;
    const linhas: string[] = [];
    linhas.push("Operador,E-mail,Lotes,Pagamentos,Bloqueados,Corrigíveis,Taxa Erro (%),Valor Bloqueado (R$)");
    for (const op of data.por_operador) {
      linhas.push(
        [
          `"${op.operador_nome}"`,
          op.operador_email ?? "",
          op.total_lotes,
          op.total_pagamentos,
          op.total_bloqueados,
          op.total_corrigiveis,
          op.taxa_erro_pct.toFixed(2),
          (op.valor_bloqueado_centavos / 100).toFixed(2),
        ].join(","),
      );
    }
    const blob = new Blob([linhas.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `medpag-relatorio-erros-${dias}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <TrendingUp size={24} className="text-accent-600" />
            Relatório de erros operacionais
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Onde a operação está errando, quanto isso vale, e quem precisa de
            treinamento.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <select
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
            className="input"
          >
            {JANELAS.map((j) => (
              <option key={j.dias} value={j.dias}>
                {j.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={exportCSV}
            disabled={!data}
            className="btn-secondary"
          >
            <Download size={16} /> CSV
          </button>
        </div>
      </header>

      {isLoading && (
        <div className="card text-sm text-slate-500">Carregando relatório...</div>
      )}
      {isError && (
        <div className="card text-sm text-red-700 border-red-200 bg-red-50">
          Erro carregando relatório: {(error as Error).message}
        </div>
      )}

      {data && (
        <>
          {/* KPIs grandes */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              titulo="Prejuízo evitado"
              valor={formatBRL(data.valor_bloqueado_centavos)}
              subtitulo="Pagamentos bloqueados antes do CNAB"
              icon={ShieldCheck}
              destaque
            />
            <KpiCard
              titulo="Lotes processados"
              valor={data.total_lotes_processados.toLocaleString("pt-BR")}
              subtitulo={`${data.total_pagamentos.toLocaleString("pt-BR")} pagamentos no total`}
              icon={FileSpreadsheet}
            />
            <KpiCard
              titulo="Bloqueados"
              valor={data.total_bloqueados.toLocaleString("pt-BR")}
              subtitulo={`+ ${data.total_corrigiveis.toLocaleString("pt-BR")} corrigíveis`}
              icon={XCircle}
            />
            <KpiCard
              titulo="Taxa de erro"
              valor={`${data.taxa_erro_pct.toFixed(2)}%`}
              subtitulo="Sobre o total de pagamentos"
              icon={AlertTriangle}
            />
          </div>

          <div className="text-xs text-slate-500">
            Período: {formatDateTime(data.periodo_inicio)} —{" "}
            {formatDateTime(data.periodo_fim)}
          </div>

          {/* Por operador */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 flex items-center gap-2 mb-3">
              <Users size={18} className="text-accent-600" />
              Por operador
            </h2>
            <div className="card p-0 overflow-hidden">
              {data.por_operador.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-slate-500">
                  Nenhum lote no período selecionado.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-3">Operador</th>
                      <th className="px-6 py-3 text-right">Lotes</th>
                      <th className="px-6 py-3 text-right">Pagamentos</th>
                      <th className="px-6 py-3 text-right">Bloqueados</th>
                      <th className="px-6 py-3 text-right">Taxa erro</th>
                      <th className="px-6 py-3 text-right">Valor bloqueado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_operador.map((op, idx) => {
                      const clicavel = !!op.operador_id;
                      return (
                        <tr
                          key={op.operador_id ?? `sem-${idx}`}
                          onClick={
                            clicavel
                              ? () =>
                                  navigate(
                                    `/app/lotes?operador=${op.operador_id}`,
                                  )
                              : undefined
                          }
                          className={`border-b border-slate-100 last:border-0 ${
                            clicavel
                              ? "cursor-pointer hover:bg-accent-50/40 transition"
                              : ""
                          }`}
                          title={
                            clicavel
                              ? `Ver lotes de ${op.operador_nome}`
                              : undefined
                          }
                        >
                          <td className="px-6 py-3">
                            <div className="flex items-center gap-2">
                              <div>
                                <div className="font-medium text-slate-900">
                                  {op.operador_nome}
                                </div>
                                {op.operador_email && (
                                  <div className="text-xs text-slate-500">
                                    {op.operador_email}
                                  </div>
                                )}
                              </div>
                              {clicavel && (
                                <ArrowRight
                                  size={14}
                                  className="text-accent-500 opacity-60"
                                />
                              )}
                            </div>
                          </td>
                          <td className="px-6 py-3 text-right text-slate-700">
                            {op.total_lotes}
                          </td>
                          <td className="px-6 py-3 text-right text-slate-700">
                            {op.total_pagamentos.toLocaleString("pt-BR")}
                          </td>
                          <td className="px-6 py-3 text-right font-medium text-red-700">
                            {op.total_bloqueados.toLocaleString("pt-BR")}
                          </td>
                          <td className="px-6 py-3 text-right">
                            <TaxaErroChip taxa={op.taxa_erro_pct} />
                          </td>
                          <td className="px-6 py-3 text-right font-medium text-slate-900">
                            {formatBRL(op.valor_bloqueado_centavos)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          {/* Por tipo de erro */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 flex items-center gap-2 mb-3">
              <AlertTriangle size={18} className="text-accent-600" />
              Tipos de erro mais comuns
            </h2>
            <div className="card p-0 overflow-hidden">
              {data.por_tipo_erro.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-slate-500">
                  Nenhum erro registrado no período.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-3">Código</th>
                      <th className="px-6 py-3">Descrição</th>
                      <th className="px-6 py-3 text-right">Quantidade</th>
                      <th className="px-6 py-3 text-right">Valor afetado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_tipo_erro.map((tipo) => (
                      <tr
                        key={tipo.codigo}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="px-6 py-3 font-mono text-xs text-slate-600">
                          {tipo.codigo}
                        </td>
                        <td className="px-6 py-3 text-slate-700">
                          {tipo.descricao}
                        </td>
                        <td className="px-6 py-3 text-right font-medium text-slate-900">
                          {tipo.quantidade.toLocaleString("pt-BR")}
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {formatBRL(tipo.valor_centavos)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          {/* Por hospital */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 flex items-center gap-2 mb-3">
              <Building2 size={18} className="text-accent-600" />
              Por hospital
            </h2>
            <div className="card p-0 overflow-hidden">
              {data.por_hospital.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-slate-500">
                  Nenhum hospital com lote no período.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-3">Hospital</th>
                      <th className="px-6 py-3 text-right">Lotes</th>
                      <th className="px-6 py-3 text-right">Pagamentos</th>
                      <th className="px-6 py-3 text-right">Bloqueados</th>
                      <th className="px-6 py-3 text-right">Taxa erro</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_hospital.map((h) => (
                      <tr
                        key={h.cliente_id}
                        onClick={() =>
                          navigate(`/app/lotes?cliente=${h.cliente_id}`)
                        }
                        className="border-b border-slate-100 last:border-0 cursor-pointer hover:bg-accent-50/40 transition"
                        title={`Ver lotes de ${h.cliente_nome}`}
                      >
                        <td className="px-6 py-3 font-medium text-slate-900">
                          <div className="flex items-center gap-2">
                            {h.cliente_nome}
                            <ArrowRight
                              size={14}
                              className="text-accent-500 opacity-60"
                            />
                          </div>
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {h.total_lotes}
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {h.total_pagamentos.toLocaleString("pt-BR")}
                        </td>
                        <td className="px-6 py-3 text-right font-medium text-red-700">
                          {h.total_bloqueados.toLocaleString("pt-BR")}
                        </td>
                        <td className="px-6 py-3 text-right">
                          <TaxaErroChip taxa={h.taxa_erro_pct} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

// ============================================================
// Componentes auxiliares
// ============================================================

function KpiCard({
  titulo,
  valor,
  subtitulo,
  icon: Icon,
  destaque,
}: {
  titulo: string;
  valor: string;
  subtitulo: string;
  icon: React.ElementType;
  destaque?: boolean;
}) {
  return (
    <div
      className={`card ${
        destaque
          ? "border-accent-300 bg-gradient-to-br from-accent-50/60 to-white"
          : ""
      }`}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs uppercase tracking-wider text-slate-500 font-medium">
          {titulo}
        </span>
        <Icon
          size={18}
          className={destaque ? "text-accent-600" : "text-brand-600"}
        />
      </div>
      <div
        className={`text-2xl font-bold mb-1 ${
          destaque ? "text-accent-700" : "text-slate-900"
        }`}
      >
        {valor}
      </div>
      <p className="text-xs text-slate-500">{subtitulo}</p>
    </div>
  );
}

function TaxaErroChip({ taxa }: { taxa: number }) {
  let cor = "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (taxa >= 10) cor = "bg-red-50 text-red-700 border-red-200";
  else if (taxa >= 3) cor = "bg-amber-50 text-amber-700 border-amber-200";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${cor}`}
    >
      {taxa.toFixed(2)}%
    </span>
  );
}
