import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Wand2,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { cn, formatBRL, formatDateTime } from "@/lib/utils";
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
  const [showOriginal, setShowOriginal] = useState(true);

  const { data: bancos } = useQuery({
    queryKey: ["bancos-febraban"],
    queryFn: async () => {
      const resp = await api.get<{ codigo: string; nome: string; suportado_cnab: boolean }[]>(
        "/api/bancos",
      );
      const mapa = new Map<string, string>();
      for (const b of resp.data) mapa.set(b.codigo, b.nome);
      return mapa;
    },
    staleTime: 1000 * 60 * 60, // 1 hora
  });

  const nomeBanco = (codigo: string | null | undefined) => {
    if (!codigo) return null;
    const c = codigo.padStart(3, "0");
    return bancos?.get(c) ?? null;
  };

  const {
    data: ficha,
    isLoading,
    isError,
    error: queryError,
  } = useQuery({
    queryKey: ["ficha", id],
    queryFn: async () => {
      const { data } = await api.get<FichaDetalhe>(`/api/fichas/${id}`);
      return data;
    },
    enabled: !!id,
    retry: false,
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

  // Calcula campos faltantes pra cada linha (mesma regra do backend).
  // Não usamos `essenciais_faltantes` do servidor porque queremos ver o
  // problema atualizando em tempo real conforme o usuário digita.
  function camposFaltantes(l: LinhaExtraida): string[] {
    const faltam: string[] = [];
    if (!l.cpf || !l.cpf.trim()) faltam.push("cpf");
    if (!l.nome || !l.nome.trim()) faltam.push("nome");
    if (!l.valor_centavos || l.valor_centavos <= 0) faltam.push("valor");
    const temPix = !!(l.chave_pix && l.chave_pix.trim());
    const temConta = !!(
      l.banco_codigo?.trim() &&
      l.agencia?.trim() &&
      l.conta?.trim()
    );
    if (!temPix && !temConta) faltam.push("forma_pagamento");
    return faltam;
  }

  const totaisLocal = useMemo(() => {
    const valor = linhas.reduce(
      (acc, l) => acc + (l.valor_centavos ?? 0),
      0,
    );
    const prontas = linhas.filter((l) => camposFaltantes(l).length === 0).length;
    const incompletas = linhas.length - prontas;
    return { valor, prontas, incompletas, validas: prontas };
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
    mutationFn: async (forcar: boolean = false) => {
      const { data } = await api.post<{
        lote_id: string;
        qtd_pagamentos: number;
      }>(`/api/fichas/${id}/converter${forcar ? "?forcar=true" : ""}`);
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

  if (isError) {
    return (
      <div className="space-y-4">
        <Link
          to="/app/fichas"
          className="text-xs text-slate-500 hover:text-brand-700 inline-flex items-center gap-1"
        >
          <ArrowLeft size={12} />
          Voltar para fichas
        </Link>
        <div className="card border-red-200 bg-red-50/60 text-sm text-red-800">
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium mb-1">Não foi possível abrir esta ficha</p>
              <p>{getErrorMessage(queryError)}</p>
            </div>
          </div>
        </div>
      </div>
    );
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

      {/* Preview do documento original + linhas extraídas lado a lado.
          Ajuda o revisor a comparar o que o OCR pegou com o documento real. */}
      <div className="card p-0 overflow-hidden">
        <header className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-brand-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              Documento original
            </h3>
            <span className="text-xs text-slate-500">
              {ficha.mime_type} ·{" "}
              {(ficha.tamanho_bytes / 1024).toFixed(0)} KB
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowOriginal((s) => !s)}
            className="text-xs text-slate-500 hover:text-slate-800 inline-flex items-center gap-1"
          >
            {showOriginal ? <EyeOff size={12} /> : <Eye size={12} />}
            {showOriginal ? "Esconder" : "Mostrar"}
          </button>
        </header>
        {showOriginal && (
          <div className="bg-slate-100 p-3">
            <DocumentoPreview
              url={`${api.defaults.baseURL ?? ""}/api/fichas/${id}/arquivo`}
              mimeType={ficha.mime_type}
            />
          </div>
        )}
      </div>

      {ficha.metadados &&
        Object.keys(ficha.metadados).filter((k) => !k.startsWith("_")).length >
          0 && (
        <div className="card">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
            Cabeçalho identificado
          </h3>
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            {Object.entries(ficha.metadados)
              .filter(([k]) => !k.startsWith("_"))
              .map(([k, v]) => (
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
              <div
                className={cn(
                  "font-semibold text-base",
                  totaisLocal.incompletas > 0
                    ? "text-amber-700"
                    : "text-emerald-700",
                )}
              >
                {totaisLocal.prontas}/{linhas.length}
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
                linhas.map((linha, idx) => {
                  const faltam = camposFaltantes(linha);
                  const linhaPronta = faltam.length === 0;
                  const faltaCpf = faltam.includes("cpf");
                  const faltaNome = faltam.includes("nome");
                  const faltaValor = faltam.includes("valor");
                  const faltaForma = faltam.includes("forma_pagamento");
                  return (
                  <tr
                    key={idx}
                    className={cn(
                      "hover:bg-slate-50/40",
                      !linhaPronta && "bg-amber-50/40",
                    )}
                  >
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
                        className={cn(
                          "input-mini font-mono",
                          faltaCpf && "ring-1 ring-amber-400 bg-amber-50",
                        )}
                        title={faltaCpf ? "CPF obrigatório" : undefined}
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
                        className={cn(
                          "input-mini",
                          faltaNome && "ring-1 ring-amber-400 bg-amber-50",
                        )}
                        title={faltaNome ? "Nome obrigatório" : undefined}
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
                        className={cn(
                          "input-mini text-right tabular-nums",
                          faltaValor && "ring-1 ring-amber-400 bg-amber-50",
                        )}
                        title={faltaValor ? "Valor obrigatório" : undefined}
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
                        className={cn(
                          "input-mini font-mono",
                          faltaForma && "ring-1 ring-amber-400 bg-amber-50",
                          linha.banco_codigo &&
                            linha.banco_codigo.length === 3 &&
                            !nomeBanco(linha.banco_codigo) &&
                            "ring-1 ring-red-400 bg-red-50",
                        )}
                        title={
                          linha.banco_codigo &&
                          linha.banco_codigo.length === 3 &&
                          !nomeBanco(linha.banco_codigo)
                            ? `Banco ${linha.banco_codigo} não existe na FEBRABAN`
                            : nomeBanco(linha.banco_codigo) ??
                              (faltaForma
                                ? "Preencha PIX OU Banco+Agência+Conta"
                                : "Código FEBRABAN (3 dígitos)")
                        }
                      />
                      {nomeBanco(linha.banco_codigo) && (
                        <div className="text-[10px] text-slate-500 truncate max-w-[120px] mt-0.5">
                          {nomeBanco(linha.banco_codigo)}
                        </div>
                      )}
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
                        className={cn(
                          "input-mini",
                          faltaForma && "ring-1 ring-amber-400 bg-amber-50",
                        )}
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
                        className={cn(
                          "input-mini",
                          faltaForma && "ring-1 ring-amber-400 bg-amber-50",
                        )}
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
                        placeholder="ou PIX"
                        disabled={!podeEditar}
                        className={cn(
                          "input-mini",
                          faltaForma && "ring-1 ring-amber-400 bg-amber-50",
                        )}
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
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {podeEditar && (
          <div className="px-4 py-3 border-t border-slate-200 space-y-3">
            {totaisLocal.incompletas > 0 && (
              <div className="flex items-start gap-2 text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold mb-0.5">
                    {totaisLocal.incompletas} linha(s) com dados faltando
                  </p>
                  <p className="text-amber-800">
                    Cada pagamento precisa de <b>CPF</b>, <b>nome</b>,{" "}
                    <b>valor</b> e <b>PIX</b> ou{" "}
                    <b>Banco + Agência + Conta</b>. As linhas em amarelo
                    estão incompletas — complete os campos destacados antes
                    de gerar o lote.
                  </p>
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3">
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
                {totaisLocal.incompletas > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      if (
                        confirm(
                          `${totaisLocal.incompletas} linha(s) incompletas serão DESCARTADAS. ` +
                            `Apenas ${totaisLocal.prontas} pagamento(s) entrarão no lote. Continuar?`,
                        )
                      ) {
                        converter.mutate(true);
                      }
                    }}
                    disabled={
                      converter.isPending ||
                      totaisLocal.prontas === 0 ||
                      ficha.status === "CONVERTIDA"
                    }
                    className="btn-ghost text-amber-700 hover:bg-amber-50"
                    title="Pular linhas incompletas (descartar) e gerar lote com as válidas"
                  >
                    Forçar com {totaisLocal.prontas} válida(s)
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => converter.mutate(false)}
                  disabled={
                    converter.isPending ||
                    totaisLocal.prontas === 0 ||
                    totaisLocal.incompletas > 0 ||
                    ficha.status === "CONVERTIDA"
                  }
                  className="btn-primary"
                  title={
                    totaisLocal.incompletas > 0
                      ? "Resolva as linhas incompletas primeiro"
                      : "Gerar lote com todos os pagamentos"
                  }
                >
                  <Wand2 size={14} />
                  {converter.isPending
                    ? "Gerando lote..."
                    : `Gerar lote (${totaisLocal.prontas} pagamento${totaisLocal.prontas === 1 ? "" : "s"})`}
                </button>
              </div>
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

/**
 * Renderiza preview do arquivo original conforme o mime_type.
 * - imagem: <img> com max-height controlado e zoom no click
 * - pdf: <iframe> nativo do navegador
 * - outros: link de download apenas
 */
function DocumentoPreview({
  url,
  mimeType,
}: {
  url: string;
  mimeType: string;
}) {
  const [ampliado, setAmpliado] = useState(false);

  if (mimeType.startsWith("image/")) {
    return (
      <div className="flex justify-center">
        <img
          src={url}
          alt="Ficha original"
          onClick={() => setAmpliado((v) => !v)}
          className={`cursor-zoom-${ampliado ? "out" : "in"} rounded-md shadow-sm bg-white ${
            ampliado ? "max-w-full" : "max-h-[500px] object-contain"
          }`}
        />
      </div>
    );
  }

  if (mimeType === "application/pdf") {
    return (
      <iframe
        src={url}
        title="Ficha original"
        className="w-full h-[600px] rounded-md border border-slate-200 bg-white"
      />
    );
  }

  return (
    <div className="text-center text-sm text-slate-500 py-6">
      <p>Preview indisponível pra esse tipo de arquivo ({mimeType}).</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-brand-700 hover:underline mt-1 inline-block"
      >
        Baixar original →
      </a>
    </div>
  );
}
