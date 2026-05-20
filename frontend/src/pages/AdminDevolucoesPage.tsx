import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeftRight,
  CheckCircle2,
  HelpCircle,
  Search,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import type { RelatorioDevolucoes } from "@/types";

const JANELAS = [
  { dias: 7, label: "Últimos 7 dias" },
  { dias: 30, label: "Últimos 30 dias" },
  { dias: 90, label: "Últimos 90 dias" },
  { dias: 180, label: "Últimos 6 meses" },
];

export function AdminDevolucoesPage() {
  const [dias, setDias] = useState(30);
  const [busca, setBusca] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "devolucoes", dias],
    queryFn: async () => {
      const { data } = await api.get<RelatorioDevolucoes>(
        `/api/admin/devolucoes?dias=${dias}&limit=200`,
      );
      return data;
    },
  });

  const devolucoesFiltradas = data?.devolucoes.filter((d) => {
    if (!busca.trim()) return true;
    const q = busca.toLowerCase();
    return (
      d.nome_beneficiario.toLowerCase().includes(q) ||
      d.cliente_nome.toLowerCase().includes(q) ||
      d.cpf_mascarado.toLowerCase().includes(q) ||
      (d.retorno_codigo ?? "").toLowerCase().includes(q) ||
      (d.retorno_descricao ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <ArrowLeftRight size={24} className="text-accent-600" />
            Devoluções do banco
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Pagamentos que o banco devolveu — com motivo decodificado em
            português. Quando o motivo não é conhecido, fica destacado.
          </p>
        </div>
        <div>
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
        </div>
      </header>

      {isLoading && (
        <div className="card text-sm text-slate-500">Carregando devoluções...</div>
      )}
      {isError && (
        <div className="card text-sm text-red-700 border-red-200 bg-red-50">
          Erro: {(error as Error).message}
        </div>
      )}

      {data && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <KpiCard
              titulo="Total devolvido"
              valor={data.total_devolucoes.toLocaleString("pt-BR")}
              subtitulo="Pagamentos não realizados"
              icon={AlertCircle}
            />
            <KpiCard
              titulo="Valor devolvido"
              valor={formatBRL(data.valor_total_devolvido_centavos)}
              subtitulo="Soma dos pagamentos retornados"
              icon={ArrowLeftRight}
              destaque
            />
            <KpiCard
              titulo="Motivo conhecido"
              valor={data.total_motivo_conhecido.toLocaleString("pt-BR")}
              subtitulo="Decodificados em PT-BR"
              icon={CheckCircle2}
              cor="emerald"
            />
            <KpiCard
              titulo="Sem motivo claro"
              valor={data.total_motivo_desconhecido.toLocaleString("pt-BR")}
              subtitulo="Códigos a mapear"
              icon={HelpCircle}
              cor="amber"
            />
          </div>

          <div className="text-xs text-slate-500">
            Período: {formatDateTime(data.periodo_inicio)} —{" "}
            {formatDateTime(data.periodo_fim)}
          </div>

          {/* Por motivo */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 mb-3">
              Distribuição por motivo
            </h2>
            <div className="card p-0 overflow-hidden">
              {data.por_motivo.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-slate-500">
                  Nenhuma devolução no período.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-3">Código</th>
                      <th className="px-6 py-3">Motivo</th>
                      <th className="px-6 py-3 text-right">Quantidade</th>
                      <th className="px-6 py-3 text-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_motivo.map((m) => (
                      <tr
                        key={m.codigo}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="px-6 py-3 font-mono text-xs text-slate-600">
                          {m.codigo}
                        </td>
                        <td className="px-6 py-3 text-slate-700">
                          {m.descricao}
                        </td>
                        <td className="px-6 py-3 text-right font-medium text-slate-900">
                          {m.quantidade.toLocaleString("pt-BR")}
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {formatBRL(m.valor_centavos)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          {/* Lista detalhada */}
          <section>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 className="text-lg font-semibold text-brand-900">
                Devoluções detalhadas
              </h2>
              <div className="relative w-64 max-w-full">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="text"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Filtrar por nome, hospital, CPF..."
                  className="input pl-9"
                />
              </div>
            </div>

            <div className="card p-0 overflow-hidden">
              {!devolucoesFiltradas || devolucoesFiltradas.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-slate-500">
                  {busca
                    ? "Nenhuma devolução bate com a busca."
                    : "Nenhuma devolução no período."}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                        <th className="px-4 py-3">Beneficiário</th>
                        <th className="px-4 py-3">Hospital</th>
                        <th className="px-4 py-3">Operador</th>
                        <th className="px-4 py-3 text-right">Valor</th>
                        <th className="px-4 py-3">Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {devolucoesFiltradas.map((d) => (
                        <tr
                          key={d.pagamento_id}
                          className="border-b border-slate-100 last:border-0"
                        >
                          <td className="px-4 py-3">
                            <div className="font-medium text-slate-900">
                              {d.nome_beneficiario}
                            </div>
                            <div className="text-xs text-slate-500">
                              {d.cpf_mascarado} · linha {d.linha_planilha}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            <div>{d.cliente_nome}</div>
                            <div className="text-xs text-slate-500 truncate max-w-[180px]">
                              {d.lote_nome}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            {d.operador_nome ?? "—"}
                          </td>
                          <td className="px-4 py-3 text-right font-medium text-slate-900">
                            {formatBRL(d.valor_centavos)}
                          </td>
                          <td className="px-4 py-3">
                            {d.motivo_conhecido ? (
                              <div>
                                <div className="text-slate-700">
                                  {d.retorno_descricao}
                                </div>
                                <div className="text-xs text-slate-500 font-mono">
                                  Código: {d.retorno_codigo}
                                </div>
                              </div>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border bg-amber-50 text-amber-800 border-amber-200">
                                <HelpCircle size={12} />
                                {d.retorno_codigo ?? "Sem código"}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function KpiCard({
  titulo,
  valor,
  subtitulo,
  icon: Icon,
  destaque,
  cor,
}: {
  titulo: string;
  valor: string;
  subtitulo: string;
  icon: React.ElementType;
  destaque?: boolean;
  cor?: "emerald" | "amber";
}) {
  let bgValor = "text-slate-900";
  let bgIcon = "text-brand-600";
  let cardBorder = "";

  if (destaque) {
    cardBorder = "border-accent-300 bg-gradient-to-br from-accent-50/60 to-white";
    bgValor = "text-accent-700";
    bgIcon = "text-accent-600";
  } else if (cor === "emerald") {
    bgValor = "text-emerald-700";
    bgIcon = "text-emerald-600";
  } else if (cor === "amber") {
    bgValor = "text-amber-700";
    bgIcon = "text-amber-600";
  }

  return (
    <div className={`card ${cardBorder}`}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs uppercase tracking-wider text-slate-500 font-medium">
          {titulo}
        </span>
        <Icon size={18} className={bgIcon} />
      </div>
      <div className={`text-2xl font-bold mb-1 ${bgValor}`}>{valor}</div>
      <p className="text-xs text-slate-500">{subtitulo}</p>
    </div>
  );
}
