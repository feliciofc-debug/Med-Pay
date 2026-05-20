import { useState } from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL } from "@/lib/utils";
import type { AprovacaoResponse, LoteDetalhe } from "@/types";

interface Props {
  lote: LoteDetalhe;
  totalCentavos: number;
  qtdPagamentos: number;
  onClose: () => void;
  onApproved: (resp: AprovacaoResponse) => void;
}

export function AprovacaoModal({
  lote,
  totalCentavos,
  qtdPagamentos,
  onClose,
  onApproved,
}: Props) {
  const [observacoes, setObservacoes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmandoTexto, setConfirmandoTexto] = useState("");

  const TEXTO_CONFIRMACAO = "APROVAR";
  const podeAprovar =
    confirmandoTexto.trim().toUpperCase() === TEXTO_CONFIRMACAO;

  async function handleConfirmar() {
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await api.post<AprovacaoResponse>(
        `/api/lotes/${lote.id}/aprovar`,
        {
          confirmacao_total_centavos: totalCentavos,
          confirmacao_qtd_pagamentos: qtdPagamentos,
          observacoes: observacoes || null,
        },
      );
      onApproved(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full">
        <div className="flex items-center justify-between p-6 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
            <AlertTriangle className="text-amber-500" size={20} />
            Confirmação de Aprovação
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="text-slate-400 hover:text-slate-600"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div className="bg-slate-50 rounded-lg p-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Cliente:</span>
              <span className="font-medium text-slate-900">
                {lote.cliente.nome}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Lote:</span>
              <span className="font-medium text-slate-900">
                {lote.referencia ?? lote.nome_arquivo}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Pagamentos:</span>
              <span className="font-semibold text-slate-900">
                {qtdPagamentos}
              </span>
            </div>
            <div className="flex justify-between text-base">
              <span className="text-slate-500">Total:</span>
              <span className="font-bold text-slate-900">
                {formatBRL(totalCentavos)}
              </span>
            </div>
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-900">
            Esta ação irá gerar o arquivo CNAB 240 da Unicred para upload no
            internet banking. A operação será registrada em auditoria e{" "}
            <strong>não pode ser desfeita</strong>.
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Observações (opcional)
            </label>
            <textarea
              value={observacoes}
              onChange={(e) => setObservacoes(e.target.value)}
              className="input"
              rows={2}
              placeholder="Ex: Folha de junho/2026 — pagamento dia 25"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Para confirmar, digite{" "}
              <code className="bg-slate-100 px-1 rounded">{TEXTO_CONFIRMACAO}</code>
            </label>
            <input
              type="text"
              value={confirmandoTexto}
              onChange={(e) => setConfirmandoTexto(e.target.value)}
              className="input font-mono"
              autoComplete="off"
            />
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-slate-200 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="btn-secondary"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleConfirmar}
            disabled={!podeAprovar || submitting}
            className="btn-success"
          >
            <CheckCircle2 size={16} />
            {submitting ? "Aprovando..." : "Confirmar Aprovação"}
          </button>
        </div>
      </div>
    </div>
  );
}
