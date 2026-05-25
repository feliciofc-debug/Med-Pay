import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Wand2,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import type { FichaDetalhe, LinhaExtraida } from "@/types";

const LINHA_VAZIA: LinhaExtraida = {
  cpf: null,
  nome: null,
  valor_centavos: null,
  qtd_plantoes: null,
  horas: null,
  banco_codigo: null,
  agencia: null,
  conta: null,
  chave_pix: null,
  linha_origem: "",
  avisos: [],
};

export function FichaDetalhePage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [linhas, setLinhas] = useState<LinhaExtraida[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showOcrText, setShowOcrText] = useState(false);

  const { data: ficha, isLoading } = useQuery({
    queryKey: ["ficha", id],
    queryFn: async () => {
      const { data } = await api.get<FichaDetalhe>(`/api/fichas/${id}`);
      return data;
    },
    enabled: !!id,
    refetchInterval: (q) => {
      const data = q.state.data as FichaDetalhe | undefined;
      return data?.status === "PROCESSANDO" ? 2500 : false;
    },
  });

  // Sincroniza estado local com ficha quando carrega/recarrega
  useEffect(() => {
    if (ficha?.linhas_extraidas) {
      setLinhas(ficha.linhas_extraidas);
    }
  }, [ficha?.linhas_extraidas]);

  const totaisLocal = useMemo(() => {
    const valor = linhas.reduce(
      (acc, l) => acc + (l.valor_centavos ?? 0),
      0,
    );
    const validas = linhas.filter(
      (l) => l.cpf && l.nome && (l.valor_centavos ?? 0) > 0,
    ).length;
    return { valor, validas };
  }, [linhas]);

  const salvar = useMutation({
    mutationFn: async () => {
      const { data } = await api.put<FichaDetalhe>(
        `/api/fichas/${id}/linhas`,
        { linhas, metadados: ficha?.metadados ?? null },
      );
      return data;
    },
    onSuccess: (data) => {
      setError(null);
      queryClient.setQueryData(["ficha", id], data);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const reprocessar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<FichaDetalhe>(
        `/api/fichas/${id}/reprocessar`,
      );
      return data;
    },
    onSuccess: (data) => {
      setError(null);
      queryClient.setQueryData(["ficha", id], data);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const converter = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{
        lote_id: string;
        qtd_pagamentos: number;
      }>(`/api/fichas/${id}/converter`);
      return data;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["fichas"] });
      navigate(`/app/lotes/${data.lote_id}`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  function atualizarLinha(idx: number, patch: Partial<LinhaExtraida>) {
    setLinhas((prev) =>
      prev.map((linha, i) => (i === idx ? { ...linha, ...patch } : linha)),
    );
  }

  function removerLinha(idx: number) {
    setLinhas((prev) => prev.filter((_, i) => i !== idx));
  }

  function adicionarLinha() {
    setLinhas((prev) => [...prev, { ...LINHA_VAZIA }]);
  }

  if (isLoading || !ficha) {
    return (
      <div className="card text-center text-slate-500 py-12">Carregando...</div>
    );
  }

  const podeEditar =
    ficha.status === "EXTRAIDA" ||
    ficha.status === "REVISADA" ||
    ficha.status === "ERRO";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            to="/app/fichas"
            className="text-xs text-slate-500 hover:text-brand-700 inline-flex items-center gap-1 mb-2"
          >
            <ArrowLeft size={12} />
            Voltar para fichas
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mb-1">
            {ficha.nome_arquivo}
          </h1>
          <p className="text-sm text-slate-500">
            {ficha.cliente.nome} • Recebida em {formatDateTime(ficha.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`${api.defaults.baseURL ?? ""}/api/fichas/${id}/arquivo`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost"
          >
            <Download size={14} />
            Original
          </a>
          {podeEditar && (
            <button
              type="button"
              onClick={() => reprocessar.mutate()}
              disabled={reprocessar.isPending}
              className="btn-ghost"
              title="Reprocessar OCR"
            >
              <RefreshCw
                size={14}
                className={reprocessar.isPending ? "animate-spin" : ""}
              />
              OCR de novo
            </button>
          )}
        </div>
      </div>

      {ficha.status === "PROCESSANDO" && (
        <div className="card flex items-center gap-3 text-sm text-blue-800 bg-blue-50/60 border-blue-200">
          <Loader2 className="animate-spin" size={18} />
          OCR em andamento — isso normalmente leva 5 a 15 segundos para fotos e
          até 30s para PDFs com várias páginas.
        </div>
      )}

      {ficha.status === "ERRO" && ficha.mensagem_erro && (
        <div className="card border-red-200 bg-red-50/60 text-sm text-red-800">
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium mb-1">Falha no OCR</p>
              <p>{ficha.mensagem_erro}</p>
              <p className="text-xs mt-2 text-red-700/80">
                Você ainda pode preencher os dados manualmente abaixo e gerar o
                lote, ou clicar em "OCR de novo" para tentar reprocessar.
              </p>
            </div>
          </div>
        </div>
      )}

      {ficha.status === "CONVERTIDA" && ficha.lote_gerado_id && (
        <div className="card border-emerald-200 bg-emerald-50/60 text-sm text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} />
            <span>
              Esta ficha já virou lote.{" "}
              <Link
                to={`/app/lotes/${ficha.lote_gerado_id}`}
                className="font-medium underline"
              >
                Abrir lote →
              </Link>
            </span>
          </div>
        </div>
      )}

      {ficha.metadados && Object.keys(ficha.metadados).length > 0 && (
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
            Cabeçalho identificado
          </h3>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            {Object.entries(ficha.metadados).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-slate-500 capitalize">{k}</dt>
                <dd className="font-medium text-slate-800">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              Linhas extraídas pelo OCR
            </h2>
            <p className="text-xs text-slate-500">
              Confira os dados, complete os campos vazios e clique em{" "}
              <em>Salvar</em> antes de gerar o lote.
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div>
              <div className="text-slate-500">Linhas válidas</div>
              <div className="font-semibold text-slate-900 text-base">
                {totaisLocal.validas}/{linhas.length}
              </div>
            </div>
            <div>
              <div className="text-slate-500">Total</div>
              <div className="font-semibold text-emerald-700 text-base">
                {formatBRL(totaisLocal.valor)}
              </div>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 w-32">CPF *</th>
                <th className="px-3 py-2">Nome *</th>
                <th className="px-3 py-2 w-28">Valor (R$) *</th>
                <th className="px-3 py-2 w-16">PT</th>
                <th className="px-3 py-2 w-20">Banco</th>
                <th className="px-3 py-2 w-24">Agência</th>
                <th className="px-3 py-2 w-28">Conta</th>
                <th className="px-3 py-2 w-44">Chave PIX</th>
                <th className="px-3 py-2 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {linhas.length === 0 ? (
                <tr>
                  <td
                    colSpan={9}
                    className="px-4 py-8 text-center text-sm text-slate-500"
                  >
                    Nenhuma linha foi extraída. Adicione manualmente abaixo.
                  </td>
                </tr>
              ) : (
                linhas.map((linha, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/40">
                    <td className="px-2 py-1">
                      <input
                        value={linha.cpf ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            cpf: e.target.value || null,
                          })
                        }
                        placeholder="000.000.000-00"
                        disabled={!podeEditar}
                        className="input-mini font-mono"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={linha.nome ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            nome: e.target.value || null,
                          })
                        }
                        placeholder="Nome do médico"
                        disabled={!podeEditar}
                        className="input-mini"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={
                          linha.valor_centavos != null
                            ? (linha.valor_centavos / 100)
                                .toFixed(2)
                                .replace(".", ",")
                            : ""
                        }
                        onChange={(e) => {
                          const txt = e.target.value
                            .replace(/[^\d,]/g, "")
                            .replace(",", ".");
                          const v = parseFloat(txt);
                          atualizarLinha(idx, {
                            valor_centavos:
                              isFinite(v) && v >= 0
                                ? Math.round(v * 100)
                                : null,
                          });
                        }}
                        placeholder="0,00"
                        disabled={!podeEditar}
                        className="input-mini text-right tabular-nums"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        min={0}
                        value={linha.qtd_plantoes ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            qtd_plantoes: e.target.value
                              ? parseInt(e.target.value, 10)
                              : null,
                          })
                        }
                        disabled={!podeEditar}
                        className="input-mini text-right"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={linha.banco_codigo ?? ""}
                        maxLength={3}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            banco_codigo: e.target.value || null,
                          })
                        }
                        placeholder="000"
                        disabled={!podeEditar}
                        className="input-mini font-mono"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={linha.agencia ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            agencia: e.target.value || null,
                          })
                        }
                        disabled={!podeEditar}
                        className="input-mini"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={linha.conta ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            conta: e.target.value || null,
                          })
                        }
                        disabled={!podeEditar}
                        className="input-mini"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={linha.chave_pix ?? ""}
                        onChange={(e) =>
                          atualizarLinha(idx, {
                            chave_pix: e.target.value || null,
                          })
                        }
                        placeholder="opcional"
                        disabled={!podeEditar}
                        className="input-mini"
                      />
                    </td>
                    <td className="px-2 py-1 text-right">
                      {podeEditar && (
                        <button
                          type="button"
                          onClick={() => removerLinha(idx)}
                          className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                          title="Remover linha"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {podeEditar && (
          <div className="px-4 py-3 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={adicionarLinha}
              className="btn-ghost text-xs"
            >
              <Plus size={12} />
              Adicionar linha manualmente
            </button>
            <div className="flex items-center gap-2 ml-auto">
              <button
                type="button"
                onClick={() => salvar.mutate()}
                disabled={salvar.isPending}
                className="btn-ghost"
              >
                <Save size={14} />
                {salvar.isPending ? "Salvando..." : "Salvar"}
              </button>
              <button
                type="button"
                onClick={() => converter.mutate()}
                disabled={
                  converter.isPending ||
                  totaisLocal.validas === 0 ||
                  ficha.status === "CONVERTIDA"
                }
                className="btn-primary"
              >
                <Wand2 size={14} />
                {converter.isPending
                  ? "Gerando lote..."
                  : `Gerar lote (${totaisLocal.validas} pagamento${totaisLocal.validas === 1 ? "" : "s"})`}
              </button>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {ficha.texto_ocr && (
        <div className="card">
          <button
            type="button"
            onClick={() => setShowOcrText((v) => !v)}
            className="flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-brand-800"
          >
            <FileText size={14} />
            {showOcrText ? "Ocultar" : "Ver"} texto bruto extraído pelo OCR
          </button>
          {showOcrText && (
            <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs text-slate-700 whitespace-pre-wrap font-mono">
              {ficha.texto_ocr}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
