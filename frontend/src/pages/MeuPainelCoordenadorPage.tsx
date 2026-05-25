/**
 * Painel do Coordenador (`/app/coordenador`).
 *
 * Visão restrita para o funcionário interno que sobe fichas de plantão
 * dos hospitais para a plataforma. Mostra:
 *
 *   • KPIs do mês (qtd de fichas, valor total, lotes gerados)
 *   • Aviso de duplicatas potenciais (mesma ficha enviada 2x)
 *   • Lista das fichas que ELE subiu (últimas 30)
 *   • Banco de horas agregado por médico (CPF)
 *
 * O coordenador NÃO vê o que outros usuários subiram, NÃO vê o
 * Executivo, NÃO aprova nada. É puramente operacional.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardList,
  FileText,
  Hourglass,
  Layers,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import type { PainelCoordenador } from "@/types";

export function MeuPainelCoordenadorPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["coordenador", "meu-painel"],
    queryFn: async () => {
      const { data } = await api.get<PainelCoordenador>(
        "/api/coordenador/meu-painel",
      );
      return data;
    },
    refetchInterval: 30_000, // refresca a cada 30s pra refletir nova ficha
  });

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <ClipboardList size={24} className="text-accent-600" />
            Meu Painel
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Tudo que você subiu pra plataforma. Confere antes de aprovar
            pra evitar pagamento duplicado.
          </p>
        </div>
        <Link
          to="/app/fichas"
          className="btn-primary"
        >
          <Camera size={16} />
          Subir nova ficha
        </Link>
      </header>

      {isLoading && (
        <div className="card text-center text-slate-500 py-12">
          Carregando seu painel...
        </div>
      )}

      {error && (
        <div className="card border-red-200 bg-red-50 text-red-800">
          Não foi possível carregar o painel. Atualize a página em alguns
          segundos.
        </div>
      )}

      {data && (
        <>
          {/* KPIs do mês */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              icon={<FileText size={18} />}
              label="Fichas no mês"
              value={data.qtd_fichas_mes.toString()}
              hint={`${data.qtd_fichas_total} no total`}
            />
            <KPICard
              icon={<Layers size={18} />}
              label="Valor do mês"
              value={formatBRL(data.valor_total_mes_centavos)}
              hint="Soma das fichas que você subiu"
            />
            <KPICard
              icon={<CheckCircle2 size={18} />}
              label="Lotes gerados"
              value={data.qtd_lotes_gerados.toString()}
              hint="Convertidos pelo aprovador"
            />
            <KPICard
              icon={<AlertTriangle size={18} />}
              label="Duplicatas potenciais"
              value={data.duplicatas_potenciais.toString()}
              hint={
                data.duplicatas_potenciais > 0
                  ? "Verifique abaixo antes de aprovar"
                  : "Nada suspeito até aqui"
              }
              destaque={data.duplicatas_potenciais > 0 ? "alerta" : "ok"}
            />
          </div>

          {/* Banner de duplicidade */}
          {data.duplicatas_potenciais > 0 && (
            <div className="card border-amber-200 bg-amber-50 text-amber-900 flex items-start gap-3">
              <AlertTriangle size={20} className="shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">
                  Atenção: detectei {data.duplicatas_potenciais}{" "}
                  {data.duplicatas_potenciais === 1
                    ? "ficha que pode ser duplicata"
                    : "fichas que podem ser duplicatas"}{" "}
                  da sua lista.
                </p>
                <p className="text-sm mt-1 text-amber-800">
                  Veja na coluna <strong>Status</strong> da lista abaixo.
                  Antes de pedir aprovação, confirme com o hospital.
                </p>
              </div>
            </div>
          )}

          {/* Fichas recentes */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 mb-3 flex items-center gap-2">
              <FileText size={18} />
              Fichas recentes
            </h2>
            <div className="card p-0 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-6 py-3">Hospital</th>
                    <th className="px-6 py-3">Arquivo</th>
                    <th className="px-6 py-3">Competência</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3 text-right">Linhas</th>
                    <th className="px-6 py-3 text-right">Valor</th>
                    <th className="px-6 py-3">Enviado em</th>
                  </tr>
                </thead>
                <tbody>
                  {data.fichas_recentes.length === 0 && (
                    <tr>
                      <td
                        colSpan={7}
                        className="px-6 py-12 text-center text-slate-500"
                      >
                        Você ainda não subiu nenhuma ficha. Clique em{" "}
                        <strong>Subir nova ficha</strong> pra começar.
                      </td>
                    </tr>
                  )}
                  {data.fichas_recentes.map((f) => {
                    const duplicada = f.duplicada_de_id != null;
                    return (
                      <tr
                        key={f.id}
                        className={`border-b border-slate-100 last:border-0 ${
                          duplicada ? "bg-amber-50/50" : ""
                        }`}
                      >
                        <td className="px-6 py-3 font-medium text-slate-900">
                          {f.cliente_nome}
                        </td>
                        <td className="px-6 py-3 text-slate-600 text-xs">
                          <Link
                            to={`/app/fichas/${f.id}`}
                            className="hover:text-accent-700 hover:underline"
                          >
                            {f.nome_arquivo}
                          </Link>
                        </td>
                        <td className="px-6 py-3 text-slate-600">
                          {f.competencia ?? "—"}
                        </td>
                        <td className="px-6 py-3">
                          <StatusBadge
                            status={f.status}
                            duplicada={duplicada}
                            motivo={f.motivo_duplicidade}
                          />
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {f.total_linhas}
                        </td>
                        <td className="px-6 py-3 text-right font-semibold text-slate-900">
                          {formatBRL(f.valor_total_centavos)}
                        </td>
                        <td className="px-6 py-3 text-slate-500 text-xs">
                          {formatDateTime(f.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Banco de horas */}
          <section>
            <h2 className="text-lg font-semibold text-brand-900 mb-3 flex items-center gap-2">
              <Hourglass size={18} />
              Banco de horas — visão por médico
            </h2>
            <p className="text-xs text-slate-500 mb-3">
              Soma das horas e valores que você já registrou para cada
              médico. Se o mesmo médico aparece em <strong>competências
              repetidas</strong>, vale conferir antes de gerar o lote.
            </p>
            <div className="card p-0 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-6 py-3">Médico</th>
                    <th className="px-6 py-3">CPF</th>
                    <th className="px-6 py-3 text-right">Fichas</th>
                    <th className="px-6 py-3 text-right">Horas</th>
                    <th className="px-6 py-3 text-right">Valor total</th>
                    <th className="px-6 py-3">Competências</th>
                    <th className="px-6 py-3">Última ficha</th>
                  </tr>
                </thead>
                <tbody>
                  {data.banco_horas.length === 0 && (
                    <tr>
                      <td
                        colSpan={7}
                        className="px-6 py-12 text-center text-slate-500"
                      >
                        Nenhum médico registrado ainda no seu extrato.
                      </td>
                    </tr>
                  )}
                  {data.banco_horas.map((m) => {
                    const repetiu = m.competencias.length > 1;
                    return (
                      <tr
                        key={`${m.cpf_mascarado}-${m.ultima_ficha_id}`}
                        className={`border-b border-slate-100 last:border-0 ${
                          repetiu ? "bg-amber-50/30" : ""
                        }`}
                      >
                        <td className="px-6 py-3 font-medium text-slate-900">
                          {m.nome}
                        </td>
                        <td className="px-6 py-3 text-slate-600 font-mono text-xs">
                          {m.cpf_mascarado}
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {m.qtd_fichas}
                          {repetiu && (
                            <AlertTriangle
                              size={14}
                              className="inline-block ml-1 text-amber-600"
                            />
                          )}
                        </td>
                        <td className="px-6 py-3 text-right text-slate-700">
                          {m.horas_total > 0 ? `${m.horas_total}h` : "—"}
                        </td>
                        <td className="px-6 py-3 text-right font-semibold text-slate-900">
                          {formatBRL(m.valor_total_centavos)}
                        </td>
                        <td className="px-6 py-3 text-slate-600 text-xs">
                          {m.competencias.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {m.competencias.map((c) => (
                                <span
                                  key={c}
                                  className={`px-1.5 py-0.5 rounded text-[10px] border ${
                                    repetiu
                                      ? "border-amber-300 bg-amber-100 text-amber-800"
                                      : "border-slate-200 bg-slate-50 text-slate-700"
                                  }`}
                                >
                                  {c}
                                </span>
                              ))}
                            </div>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-6 py-3 text-slate-500 text-xs">
                          {formatDateTime(m.ultima_ficha_em)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function KPICard({
  icon,
  label,
  value,
  hint,
  destaque,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint: string;
  destaque?: "ok" | "alerta";
}) {
  const cor =
    destaque === "alerta"
      ? "border-amber-200 bg-amber-50"
      : "border-slate-200 bg-white";
  return (
    <div className={`card ${cor}`}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500 mb-2">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500 mt-1">{hint}</div>
    </div>
  );
}

function StatusBadge({
  status,
  duplicada,
  motivo,
}: {
  status: string;
  duplicada: boolean;
  motivo: string | null;
}) {
  const cores: Record<string, string> = {
    RECEBIDA: "bg-slate-100 text-slate-700",
    PROCESSANDO: "bg-blue-100 text-blue-700",
    EXTRAIDA: "bg-emerald-100 text-emerald-700",
    REVISADA: "bg-emerald-100 text-emerald-800",
    CONVERTIDA: "bg-purple-100 text-purple-800",
    ERRO: "bg-red-100 text-red-700",
  };
  const classe = cores[status] ?? "bg-slate-100 text-slate-700";

  return (
    <div className="flex flex-col gap-1">
      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${classe}`}>
        {status}
      </span>
      {duplicada && (
        <span
          title={motivo ?? ""}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-amber-100 text-amber-800 border border-amber-300"
        >
          <AlertTriangle size={10} />
          Possível duplicata
        </span>
      )}
    </div>
  );
}
