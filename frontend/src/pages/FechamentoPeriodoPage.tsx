import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CalendarCheck2,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Lock,
  Unlock,
  Users,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

/**
 * Pagina de Fechamento de Periodo.
 *
 * Fluxo:
 * 1. Usuario seleciona mes/ano -> ve preview (X fichas, Y medicos, R$ Z)
 * 2. Botao "Trancar este periodo" -> cria FechamentoPeriodo
 * 3. Lista de fechamentos anteriores: extrato XLSX / gerar lote / reabrir
 */

const MESES = [
  "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

interface MedicoPreview {
  cpf_mascarado: string;
  nome: string;
  qtd_aparicoes: number;
  valor_total_centavos: number;
  beneficiario_cadastrado: boolean;
}

interface FichaPreview {
  id: string;
  nome_arquivo: string;
  status: string;
  qtd_linhas: number;
  valor_total_centavos: number;
  competencia: string | null;
  coordenador: string | null;
}

interface PreviewResponse {
  titulo: string;
  competencia: string;
  cliente_nome: string;
  total_fichas: number;
  total_linhas: number;
  total_medicos_unicos: number;
  medicos_nao_cadastrados: number;
  valor_total_centavos: number;
  fichas: FichaPreview[];
  medicos: MedicoPreview[];
  erro?: string;
}

interface FechamentoItem {
  id: string;
  cliente: { id: string; nome: string } | null;
  ano: number;
  mes: number;
  competencia: string;
  status: "ABERTO" | "TRANCADO" | "GERADO_LOTE" | "PAGO";
  total_centavos: number;
  qtd_fichas: number;
  qtd_medicos: number;
  qtd_linhas: number;
  lote_id: string | null;
  trancado_em: string | null;
  trancado_por: { nome: string; email: string } | null;
  reaberto_em: string | null;
  observacoes: string | null;
  created_at: string;
}

function formatarValor(centavos: number): string {
  const reais = centavos / 100;
  return reais.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

const STATUS_BADGE: Record<FechamentoItem["status"], string> = {
  ABERTO: "bg-slate-100 text-slate-700 border-slate-300",
  TRANCADO: "bg-amber-100 text-amber-800 border-amber-300",
  GERADO_LOTE: "bg-brand-100 text-brand-800 border-brand-300",
  PAGO: "bg-emerald-100 text-emerald-800 border-emerald-300",
};

const STATUS_LABEL: Record<FechamentoItem["status"], string> = {
  ABERTO: "Aberto",
  TRANCADO: "Trancado",
  GERADO_LOTE: "Lote gerado",
  PAGO: "Pago",
};

export function FechamentoPeriodoPage() {
  const queryClient = useQueryClient();
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [observacoes, setObservacoes] = useState("");
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // ---- Queries ----
  const previewQuery = useQuery({
    queryKey: ["fechamento-preview", ano, mes],
    queryFn: async () => {
      const res = await api.get<PreviewResponse>(
        `/api/fechamentos/preview/mes?ano=${ano}&mes=${mes}`,
      );
      return res.data;
    },
  });

  const listaQuery = useQuery({
    queryKey: ["fechamentos-lista", ano],
    queryFn: async () => {
      const res = await api.get<{ fechamentos: FechamentoItem[]; total: number }>(
        `/api/fechamentos?ano=${ano}`,
      );
      return res.data;
    },
  });

  // ---- Mutations ----
  const trancarMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post<FechamentoItem>("/api/fechamentos", {
        ano,
        mes,
        observacoes: observacoes || null,
      });
      return res.data;
    },
    onSuccess: (data) => {
      setMensagem(`Período ${data.competencia} trancado com sucesso.`);
      setErro(null);
      setObservacoes("");
      void queryClient.invalidateQueries({ queryKey: ["fechamentos-lista"] });
      void queryClient.invalidateQueries({ queryKey: ["fechamento-preview"] });
    },
    onError: (e) => {
      setErro(getErrorMessage(e));
      setMensagem(null);
    },
  });

  const reabrirMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post(`/api/fechamentos/${id}/reabrir`);
      return res.data;
    },
    onSuccess: () => {
      setMensagem("Período reaberto. Você pode revisar/alterar as fichas.");
      setErro(null);
      void queryClient.invalidateQueries({ queryKey: ["fechamentos-lista"] });
    },
    onError: (e) => {
      setErro(getErrorMessage(e));
      setMensagem(null);
    },
  });

  const gerarLoteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.post<{ lote_id: string; mensagem: string }>(
        `/api/fechamentos/${id}/gerar-lote`,
      );
      return res.data;
    },
    onSuccess: (data) => {
      setMensagem(
        `Lote ${data.lote_id.slice(0, 8)}… gerado. Vá em "Lotes" pra aprovar.`,
      );
      setErro(null);
      void queryClient.invalidateQueries({ queryKey: ["fechamentos-lista"] });
    },
    onError: (e) => {
      setErro(getErrorMessage(e));
      setMensagem(null);
    },
  });

  async function baixarArquivo(
    id: string,
    comp: string,
    tipo: "extrato.xlsx" | "folha.xlsx" | "folha.pdf",
    aplicarIrrf = false,
  ) {
    try {
      const url =
        tipo === "extrato.xlsx"
          ? `/api/fechamentos/${id}/${tipo}`
          : `/api/fechamentos/${id}/${tipo}?aplicar_irrf=${aplicarIrrf}`;
      const res = await api.get(url, { responseType: "blob" });
      const mime =
        tipo === "folha.pdf"
          ? "application/pdf"
          : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
      const blob = new Blob([res.data], { type: mime });
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      const prefixo = tipo.startsWith("folha") ? "folha" : "extrato";
      const ext = tipo.endsWith("pdf") ? "pdf" : "xlsx";
      a.download = `${prefixo}-${comp.replace("/", "-")}.${ext}`;
      a.click();
      URL.revokeObjectURL(objUrl);
    } catch (e) {
      setErro(getErrorMessage(e));
    }
  }

  const preview = previewQuery.data;
  const semDadosPreview =
    !previewQuery.isLoading && (!preview || preview.total_fichas === 0);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900 mb-1">
          Fechamento de Período
        </h1>
        <p className="text-sm text-slate-500">
          Tranque o mês operacional do hospital. Cria um snapshot
          congelado e prepara o extrato pra enviar ao financeiro / contador.
        </p>
      </header>

      {(mensagem || erro) && (
        <div
          className={
            erro
              ? "bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 flex items-start gap-2"
              : "bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg px-4 py-3 flex items-start gap-2"
          }
        >
          {erro ? (
            <AlertCircle size={18} className="shrink-0 mt-0.5" />
          ) : (
            <CheckCircle2 size={18} className="shrink-0 mt-0.5" />
          )}
          <div className="text-sm">{erro || mensagem}</div>
        </div>
      )}

      {/* -------- Seletor + preview -------- */}
      <div className="card">
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Mês
            </label>
            <select
              value={mes}
              onChange={(e) => setMes(Number(e.target.value))}
              className="input"
            >
              {MESES.map((nome, idx) => (
                <option key={idx} value={idx + 1}>
                  {nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Ano
            </label>
            <input
              type="number"
              min={2024}
              max={2100}
              value={ano}
              onChange={(e) => setAno(Number(e.target.value))}
              className="input w-24"
            />
          </div>
          <div className="text-sm text-slate-500 ml-auto self-center">
            Competência selecionada:{" "}
            <strong className="text-slate-700">
              {MESES[mes - 1]} / {ano}
            </strong>
          </div>
        </div>

        {previewQuery.isLoading && (
          <div className="text-sm text-slate-500 py-4">Calculando…</div>
        )}

        {preview?.erro && (
          <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            {preview.erro}
          </div>
        )}

        {semDadosPreview && !preview?.erro && !previewQuery.isLoading && (
          <div className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-4 text-center">
            Nenhuma ficha pendente em {MESES[mes - 1]} / {ano}. Suba/revise
            as fichas antes de trancar.
          </div>
        )}

        {preview && preview.total_fichas > 0 && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wide">
                  Fichas
                </div>
                <div className="text-xl font-bold text-slate-900">
                  {preview.total_fichas}
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wide">
                  Médicos distintos
                </div>
                <div className="text-xl font-bold text-slate-900">
                  {preview.total_medicos_unicos}
                </div>
                {preview.medicos_nao_cadastrados > 0 && (
                  <div className="text-[10px] text-amber-700 mt-0.5">
                    {preview.medicos_nao_cadastrados} sem cadastro
                  </div>
                )}
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wide">
                  Linhas
                </div>
                <div className="text-xl font-bold text-slate-900">
                  {preview.total_linhas}
                </div>
              </div>
              <div className="rounded-lg border border-brand-200 bg-brand-50 px-4 py-3">
                <div className="text-[11px] text-brand-700 uppercase tracking-wide">
                  Valor total
                </div>
                <div className="text-xl font-bold text-brand-900">
                  {formatarValor(preview.valor_total_centavos)}
                </div>
              </div>
            </div>

            <div className="border-t border-slate-200 pt-4 space-y-3">
              <label className="block">
                <span className="text-xs font-medium text-slate-600">
                  Observações (opcional)
                </span>
                <input
                  type="text"
                  value={observacoes}
                  onChange={(e) => setObservacoes(e.target.value)}
                  placeholder='Ex: "Fechamento adiantado por feriado"'
                  className="input mt-1"
                  maxLength={500}
                />
              </label>
              <div className="flex justify-end">
                <button
                  type="button"
                  className="btn-primary inline-flex items-center gap-2"
                  disabled={trancarMutation.isPending}
                  onClick={() => trancarMutation.mutate()}
                >
                  <Lock size={16} />
                  {trancarMutation.isPending
                    ? "Trancando…"
                    : `Trancar ${MESES[mes - 1]}/${ano}`}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* -------- Lista de fechamentos -------- */}
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900 mb-3 flex items-center gap-2">
          <CalendarCheck2 size={18} className="text-brand-700" />
          Fechamentos de {ano}
        </h2>

        {listaQuery.isLoading && (
          <div className="text-sm text-slate-500 py-4">Carregando…</div>
        )}

        {!listaQuery.isLoading && listaQuery.data?.fechamentos.length === 0 && (
          <div className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-4 text-center">
            Nenhum período trancado ainda em {ano}.
          </div>
        )}

        {listaQuery.data && listaQuery.data.fechamentos.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-500 uppercase tracking-wide border-b border-slate-200">
                <tr>
                  <th className="text-left px-2 py-2">Competência</th>
                  {!listaQuery.data.fechamentos[0]?.cliente ? null : (
                    <th className="text-left px-2 py-2">Hospital</th>
                  )}
                  <th className="text-left px-2 py-2">Status</th>
                  <th className="text-right px-2 py-2">Fichas</th>
                  <th className="text-right px-2 py-2">Médicos</th>
                  <th className="text-right px-2 py-2">Total</th>
                  <th className="text-left px-2 py-2">Trancado em</th>
                  <th className="text-right px-2 py-2">Ações</th>
                </tr>
              </thead>
              <tbody>
                {listaQuery.data.fechamentos.map((f) => (
                  <tr
                    key={f.id}
                    className="border-b border-slate-100 hover:bg-slate-50"
                  >
                    <td className="px-2 py-2 font-mono">
                      {f.competencia}
                    </td>
                    {f.cliente && (
                      <td className="px-2 py-2 text-slate-700 truncate max-w-[200px]">
                        {f.cliente.nome}
                      </td>
                    )}
                    <td className="px-2 py-2">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] border ${STATUS_BADGE[f.status]}`}
                      >
                        {STATUS_LABEL[f.status]}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right">{f.qtd_fichas}</td>
                    <td className="px-2 py-2 text-right">
                      <span className="inline-flex items-center gap-1">
                        <Users size={12} className="text-slate-400" />
                        {f.qtd_medicos}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right font-medium">
                      {formatarValor(f.total_centavos)}
                    </td>
                    <td className="px-2 py-2 text-xs text-slate-500">
                      {f.trancado_em ? formatDateTime(f.trancado_em) : "—"}
                      {f.trancado_por && (
                        <div className="text-[10px] text-slate-400">
                          por {f.trancado_por.nome}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right whitespace-nowrap">
                      <div className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 justify-end">
                        <button
                          type="button"
                          className="text-xs text-slate-700 hover:text-slate-900 inline-flex items-center gap-1"
                          onClick={() =>
                            void baixarArquivo(f.id, f.competencia, "extrato.xlsx")
                          }
                          title="Extrato operacional consolidado (fichas + medicos)"
                        >
                          <Download size={12} />
                          Extrato
                        </button>
                        <button
                          type="button"
                          className="text-xs text-brand-700 hover:text-brand-900 inline-flex items-center gap-1"
                          onClick={() =>
                            void baixarArquivo(f.id, f.competencia, "folha.xlsx", false)
                          }
                          title="Folha de pagamento formal (XLSX) — pro RH/contador"
                        >
                          <FileSpreadsheet size={12} />
                          Folha XLSX
                        </button>
                        <button
                          type="button"
                          className="text-xs text-rose-700 hover:text-rose-900 inline-flex items-center gap-1"
                          onClick={() =>
                            void baixarArquivo(f.id, f.competencia, "folha.pdf", false)
                          }
                          title="Folha de pagamento formal (PDF) — pra assinatura"
                        >
                          <FileText size={12} />
                          Folha PDF
                        </button>
                        {f.status === "TRANCADO" && (
                          <>
                            <button
                              type="button"
                              className="text-xs text-emerald-700 hover:text-emerald-900 inline-flex items-center gap-1"
                              onClick={() => gerarLoteMutation.mutate(f.id)}
                              disabled={gerarLoteMutation.isPending}
                              title="Gerar lote de pagamento a partir deste fechamento"
                            >
                              <FileSpreadsheet size={12} />
                              Gerar lote
                            </button>
                            <button
                              type="button"
                              className="text-xs text-amber-700 hover:text-amber-900 inline-flex items-center gap-1"
                              onClick={() => reabrirMutation.mutate(f.id)}
                              disabled={reabrirMutation.isPending}
                              title="Reabrir o período pra ajustes"
                            >
                              <Unlock size={12} />
                              Reabrir
                            </button>
                          </>
                        )}
                        {f.status === "GERADO_LOTE" && f.lote_id && (
                          <a
                            href={`/app/lotes/${f.lote_id}`}
                            className="text-xs text-brand-700 hover:text-brand-900 underline"
                          >
                            ver lote
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
