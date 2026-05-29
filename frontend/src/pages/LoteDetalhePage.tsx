import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  ArrowLeft,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import {
  StatusBadgeLote,
  ModalidadeBadge,
  StatusBadgePagamento,
} from "@/components/StatusBadge";
import { AprovacaoModal } from "@/components/AprovacaoModal";
import type {
  AprovacaoResponse,
  LoteDetalhe,
  Pagamento,
  StatusPagamento,
} from "@/types";

type FiltroStatus = "todos" | "problemas";

export function LoteDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [filtro, setFiltro] = useState<FiltroStatus>("todos");
  const [showAprovacao, setShowAprovacao] = useState(false);
  const [aprovado, setAprovado] = useState<AprovacaoResponse | null>(null);

  const {
    data: lote,
    isLoading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["lote", id],
    queryFn: async () => {
      const { data } = await api.get<LoteDetalhe>(`/api/lotes/${id}`);
      return data;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Poll enquanto está processando
      return status === "PROCESSANDO" || status === "RECEBIDO" ? 2000 : false;
    },
  });

  if (isLoading) {
    return (
      <div className="text-sm text-slate-500">Carregando lote...</div>
    );
  }

  if (queryError || !lote) {
    return (
      <div className="text-sm text-red-700">
        Erro ao carregar lote: {getErrorMessage(queryError)}
      </div>
    );
  }

  const pagamentosFiltrados =
    filtro === "todos"
      ? lote.pagamentos
      : lote.pagamentos.filter((p) =>
          (["CORRIGIVEL", "BLOQUEADO"] as StatusPagamento[]).includes(p.status),
        );

  const aprovaveis = lote.pagamentos.filter((p) =>
    (["VALIDO", "CORRIGIVEL"] as StatusPagamento[]).includes(p.status),
  );
  const totalAprovavel = aprovaveis.reduce(
    (acc, p) => acc + p.valor_centavos,
    0,
  );

  const loteJaAprovado =
    lote.status === "APROVADO" || lote.status === "ENVIADO_BANCO";

  function nomeSafeBanco(nome: string, loteId: string): string {
    // Bancos brasileiros (Unicred, Itaú, Bradesco etc.) só aceitam nome
    // 100% alfanumérico. Trocamos qualquer caractere fora dessa regra
    // antes de salvar no disco — independente do que o servidor mandou.
    const semExt = nome.replace(/\.[^.]+$/, "");
    const ext = (nome.match(/\.[^.]+$/)?.[0] ?? ".REM").toUpperCase();
    const limpo = semExt.replace(/[^A-Za-z0-9]/g, "");
    if (limpo.length >= 8) {
      return `${limpo.toUpperCase()}${ext}`;
    }
    // Nome antigo veio sem nada de aproveitável — gera um do zero.
    const idLimpo = loteId.replace(/-/g, "").slice(0, 12).toUpperCase();
    const ts = new Date()
      .toISOString()
      .replace(/[-:T.Z]/g, "")
      .slice(0, 14);
    return `MEDPAG${idLimpo}${ts}${ext}`;
  }

  async function baixarCnab(fallbackName: string) {
    try {
      const resp = await api.get(`/api/lotes/${lote!.id}/cnab`, {
        responseType: "blob",
      });
      const cd =
        (resp.headers["content-disposition"] as string | undefined) ?? "";
      const match = cd.match(/filename="?([^";]+)"?/);
      const filenameRaw = match?.[1] ?? fallbackName;
      const filename = nomeSafeBanco(filenameRaw, lote!.id);
      const url = window.URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Erro ao baixar: ${getErrorMessage(err)}`);
    }
  }

  async function baixarListaPix() {
    try {
      const resp = await api.get(`/api/lotes/${lote!.id}/pix.xlsx`, {
        responseType: "blob",
      });
      const filename = `MEDPAG-PIX-${lote!.id.replace(/-/g, "").slice(0, 8).toUpperCase()}.xlsx`;
      const url = window.URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Erro ao baixar PIX: ${getErrorMessage(err)}`);
    }
  }

  const temPagamentosPix =
    lote.pagamentos?.some((p) => p.modalidade === "PIX") ?? false;

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/app"
          className="text-sm text-slate-500 hover:text-slate-700 inline-flex items-center gap-1"
        >
          <ArrowLeft size={14} /> Voltar
        </Link>
      </div>

      {/* Cabeçalho */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-slate-900">
                {lote.cliente.nome}
              </h1>
              <StatusBadgeLote status={lote.status} />
            </div>
            <p className="text-sm text-slate-500 mt-1">
              {lote.referencia ?? lote.nome_arquivo} • Recebido em{" "}
              {formatDateTime(lote.created_at)}
            </p>
          </div>

          <div className="text-right">
            <div className="text-sm text-slate-500">Total</div>
            <div className="text-2xl font-bold text-slate-900">
              {formatBRL(lote.valor_total_centavos)}
            </div>
            <div className="text-xs text-slate-500">
              {lote.total_pagamentos} pagamentos
            </div>
          </div>
        </div>

        {/* Semáforo */}
        <div className="flex items-center gap-6 mt-4 pt-4 border-t border-slate-100">
          <span className="flex items-center gap-2 text-emerald-700">
            <CheckCircle2 size={18} />
            <strong>{lote.total_validos}</strong> OK
          </span>
          <span className="flex items-center gap-2 text-amber-700">
            <AlertTriangle size={18} />
            <strong>{lote.total_corrigiveis}</strong> com sugestão
          </span>
          <span className="flex items-center gap-2 text-red-700">
            <XCircle size={18} />
            <strong>{lote.total_bloqueados}</strong> bloqueado
          </span>
        </div>
      </div>

      {/* Resultado da aprovação (logo após aprovar) ou lote já aprovado anteriormente */}
      {(aprovado || (loteJaAprovado && lote.hash_arquivo_cnab)) && (
        <div className="card border-emerald-200 bg-emerald-50">
          <h2 className="font-semibold text-emerald-900 mb-2">
            ✅ Lote aprovado — arquivo CNAB pronto para download
          </h2>
          <p className="text-sm text-emerald-800 mb-4">
            {aprovado ? (
              <>
                {aprovado.quantidade_pagamentos} pagamentos •{" "}
                {formatBRL(aprovado.valor_total_centavos)} • Hash:{" "}
                <code className="text-xs">
                  {aprovado.hash_arquivo.slice(0, 16)}…
                </code>
              </>
            ) : (
              <>
                {lote.total_validos + lote.total_corrigiveis} pagamentos •{" "}
                {formatBRL(lote.valor_total_centavos)}
                {lote.hash_arquivo_cnab && (
                  <>
                    {" "}
                    • Hash:{" "}
                    <code className="text-xs">
                      {lote.hash_arquivo_cnab.slice(0, 16)}…
                    </code>
                  </>
                )}
              </>
            )}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-success"
              onClick={() =>
                baixarCnab(
                  aprovado?.nome_arquivo ??
                    lote.nome_arquivo_cnab ??
                    `MEDPAG${lote.id.replace(/-/g, "").slice(0, 12).toUpperCase()}.REM`,
                )
              }
            >
              <Download size={16} />
              Baixar arquivo CNAB (.rem)
            </button>
            {temPagamentosPix && (
              <button
                type="button"
                className="px-3 py-2 text-sm rounded-md border border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100 inline-flex items-center gap-2"
                onClick={baixarListaPix}
                title="Pagamentos PIX deste lote (planilha para pagar via Internet Banking ou Asaas)"
              >
                <Download size={16} />
                Baixar lista PIX (.xlsx)
              </button>
            )}
            <button
              type="button"
              className="px-3 py-2 text-sm rounded-md border border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100 inline-flex items-center gap-2 disabled:opacity-50"
              onClick={async () => {
                const ok = window.confirm(
                  "Regerar o arquivo CNAB?\n\n" +
                    "Use isso quando o banco rejeitar por sequencial. " +
                    "Antes, ajuste 'Próximo número sequencial' em Empresa Pagadora. " +
                    "O arquivo atual será substituído.",
                );
                if (!ok) return;
                try {
                  await api.post(`/api/lotes/${lote.id}/cnab/regerar`);
                  await queryClient.invalidateQueries({
                    queryKey: ["lote", id],
                  });
                  await refetch();
                  alert("Arquivo regerado. Clique em 'Baixar' para obter a versão nova.");
                } catch (err) {
                  alert(`Erro ao regerar: ${getErrorMessage(err)}`);
                }
              }}
            >
              <RefreshCw size={14} />
              Regerar arquivo
            </button>
          </div>

          <div className="mt-4 text-sm text-emerald-900">
            <p className="font-medium mb-1">Próximos passos:</p>
            <ol className="list-decimal list-inside space-y-1 text-sm">
              <li>Baixe o arquivo .rem acima</li>
              <li>Acesse o internet banking da Unicred</li>
              <li>
                Menu: Pagamentos &gt; Folha de Pagamento &gt; Importar Arquivo
              </li>
              <li>Faça upload do arquivo baixado</li>
              <li>Confirme o envio no banco</li>
            </ol>
          </div>
        </div>
      )}

      {/* Botão de aprovar (quando lote está em AGUARDANDO_REVISAO) */}
      {lote.status === "AGUARDANDO_REVISAO" && lote.pagamentos.length > 0 && (
        <div className="card flex items-center justify-between bg-brand-50 border-brand-200">
          <div>
            <p className="text-sm text-slate-700">
              {aprovaveis.length} pagamentos prontos para aprovação
            </p>
            <p className="text-xs text-slate-500">
              {lote.total_bloqueados > 0 &&
                `${lote.total_bloqueados} bloqueados serão ignorados.`}
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowAprovacao(true)}
            disabled={aprovaveis.length === 0}
          >
            Aprovar lote inteiro →
          </button>
        </div>
      )}

      {/* Tabela de pagamentos */}
      <div className="card p-0 overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700">Filtro:</span>
          <button
            type="button"
            onClick={() => setFiltro("todos")}
            className={`text-sm px-3 py-1 rounded-lg ${
              filtro === "todos"
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            Tudo ({lote.pagamentos.length})
          </button>
          <button
            type="button"
            onClick={() => setFiltro("problemas")}
            className={`text-sm px-3 py-1 rounded-lg ${
              filtro === "problemas"
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            Só problemas ({lote.total_corrigiveis + lote.total_bloqueados})
          </button>
        </div>

        <table className="w-full">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
            <tr>
              <th className="text-left p-3">Linha</th>
              <th className="text-left p-3">Nome</th>
              <th className="text-left p-3">CPF</th>
              <th className="text-right p-3">Valor</th>
              <th className="text-left p-3">Envio</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pagamentosFiltrados.map((p) => (
              <PagamentoRow
                key={p.id}
                pagamento={p}
                onChanged={() => void refetch()}
              />
            ))}
          </tbody>
        </table>

        {pagamentosFiltrados.length === 0 && (
          <div className="p-6 text-sm text-slate-500 text-center">
            Nenhum pagamento neste filtro.
          </div>
        )}
      </div>

      {showAprovacao && (
        <AprovacaoModal
          lote={lote}
          totalCentavos={totalAprovavel}
          qtdPagamentos={aprovaveis.length}
          onClose={() => setShowAprovacao(false)}
          onApproved={(resp) => {
            setAprovado(resp);
            setShowAprovacao(false);
            void queryClient.invalidateQueries({ queryKey: ["lote", id] });
            void queryClient.invalidateQueries({ queryKey: ["lotes"] });
          }}
        />
      )}
    </div>
  );
}

function PagamentoRow({
  pagamento,
  onChanged,
}: {
  pagamento: Pagamento;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function aceitarSugestao() {
    setBusy(true);
    try {
      await api.post(`/api/pagamentos/${pagamento.id}/aceitar-sugestao-cpf`, {
        aceitar: true,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="text-sm">
      <td className="p-3 text-slate-500">{pagamento.linha_planilha}</td>
      <td className="p-3 font-medium text-slate-900">{pagamento.nome}</td>
      <td className="p-3 font-mono text-xs">
        <div>{pagamento.cpf_mascarado}</div>
        {pagamento.cpf_sugerido && (
          <div className="text-amber-700 mt-1">
            💡 Sugestão: {pagamento.cpf_sugerido}
          </div>
        )}
      </td>
      <td className="p-3 text-right font-medium">
        {formatBRL(pagamento.valor_centavos)}
      </td>
      <td className="p-3">
        <ModalidadeBadge modalidade={pagamento.modalidade} />
      </td>
      <td className="p-3">
        <StatusBadgePagamento status={pagamento.status} />
        {pagamento.codigos_erro && (
          <div className="text-xs text-slate-500 mt-1">
            {pagamento.codigos_erro}
          </div>
        )}
      </td>
      <td className="p-3">
        {pagamento.cpf_sugerido && (
          <button
            type="button"
            onClick={() => void aceitarSugestao()}
            disabled={busy}
            className="text-xs text-brand-600 hover:underline"
          >
            ✓ Aceitar sugestão
          </button>
        )}
      </td>
    </tr>
  );
}
