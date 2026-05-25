import { useState, useMemo, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardList,
  Clock,
  FileImage,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL, formatDateTime } from "@/lib/utils";
import type { Cliente, FichaDetalhe, FichaResumo, StatusFicha } from "@/types";

// Tamanhos máximos do OCR.space no plano free
const MAX_MB = 5;
const ACCEPT = ".jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.pdf";

const STATUS_LABELS: Record<StatusFicha, string> = {
  RECEBIDA: "Recebida",
  PROCESSANDO: "Processando OCR",
  EXTRAIDA: "Extraída — revisar",
  REVISADA: "Revisada",
  CONVERTIDA: "Convertida em lote",
  ERRO: "Erro",
};

const STATUS_TONE: Record<StatusFicha, string> = {
  RECEBIDA: "bg-slate-100 text-slate-700",
  PROCESSANDO: "bg-blue-50 text-blue-700",
  EXTRAIDA: "bg-amber-50 text-amber-700",
  REVISADA: "bg-indigo-50 text-indigo-700",
  CONVERTIDA: "bg-emerald-50 text-emerald-700",
  ERRO: "bg-red-50 text-red-700",
};

function StatusBadge({ status }: { status: StatusFicha }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${STATUS_TONE[status]}`}
    >
      {status === "PROCESSANDO" && <Loader2 size={11} className="animate-spin" />}
      {status === "CONVERTIDA" && <CheckCircle2 size={11} />}
      {status === "ERRO" && <AlertTriangle size={11} />}
      {STATUS_LABELS[status]}
    </span>
  );
}

export function FichasListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);

  const { data: fichas = [], isLoading } = useQuery({
    queryKey: ["fichas"],
    queryFn: async () => {
      const { data } = await api.get<FichaResumo[]>("/api/fichas?limit=100");
      return data;
    },
    refetchInterval: (q) => {
      const items = (q.state.data ?? []) as FichaResumo[];
      return items.some((f) => f.status === "PROCESSANDO") ? 3000 : false;
    },
  });

  const removerMutation = useMutation({
    mutationFn: async (fichaId: string) => {
      await api.delete(`/api/fichas/${fichaId}`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["fichas"] });
    },
  });

  const aguardandoRevisao = useMemo(
    () =>
      fichas.filter(
        (f) => f.status === "EXTRAIDA" || f.status === "REVISADA",
      ).length,
    [fichas],
  );

  function confirmarExclusao(ficha: FichaResumo) {
    if (
      !window.confirm(
        `Excluir a ficha "${ficha.nome_arquivo}"? Esta ação não pode ser desfeita.`,
      )
    ) {
      return;
    }
    removerMutation.mutate(ficha.id, {
      onError: (err) => alert(getErrorMessage(err)),
    });
  }

  return (
    <div>
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 mb-1">
            Fichas de Plantão
          </h1>
          <p className="text-sm text-slate-500">
            Coordenadores enviam a foto/PDF da ficha carimbada. O OCR extrai os
            plantões automaticamente. Você revisa e aprova, e a ficha vira lote
            de pagamento — sem planilha intermediária.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowUpload(true)}
          className="btn-primary whitespace-nowrap"
        >
          <Camera size={16} />
          Nova ficha
        </button>
      </div>

      {aguardandoRevisao > 0 && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-amber-900">
          <strong>{aguardandoRevisao}</strong> ficha(s) aguardando revisão. Abra,
          confira os dados e clique em <em>Gerar lote</em> para enviar para a
          aprovação financeira.
        </div>
      )}

      {showUpload && (
        <UploadFichaModal
          onClose={() => setShowUpload(false)}
          onSuccess={(ficha) => {
            setShowUpload(false);
            void queryClient.invalidateQueries({ queryKey: ["fichas"] });
            navigate(`/app/fichas/${ficha.id}`);
          }}
        />
      )}

      {isLoading ? (
        <div className="card text-center text-slate-500 py-8">Carregando...</div>
      ) : fichas.length === 0 ? (
        <div className="card text-center py-12 border-dashed">
          <ClipboardList size={36} className="mx-auto text-slate-300 mb-3" />
          <p className="text-slate-700 font-medium mb-1">
            Nenhuma ficha enviada ainda
          </p>
          <p className="text-sm text-slate-500 mb-4">
            Comece subindo uma foto da ficha carimbada do hospital.
          </p>
          <button
            type="button"
            onClick={() => setShowUpload(true)}
            className="btn-primary"
          >
            <Upload size={16} />
            Enviar primeira ficha
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Arquivo</th>
                <th className="px-4 py-3">Cliente</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Linhas</th>
                <th className="px-4 py-3 text-right">Valor total</th>
                <th className="px-4 py-3">Recebida</th>
                <th className="px-4 py-3 w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {fichas.map((ficha) => (
                <tr key={ficha.id} className="hover:bg-slate-50/60 transition">
                  <td className="px-4 py-3">
                    <Link
                      to={`/app/fichas/${ficha.id}`}
                      className="font-medium text-brand-700 hover:text-brand-900"
                    >
                      <span className="inline-flex items-center gap-1.5">
                        <FileImage size={14} />
                        {ficha.nome_arquivo}
                      </span>
                    </Link>
                    {ficha.mensagem_erro && (
                      <div className="text-[11px] text-red-600 mt-1 line-clamp-2">
                        {ficha.mensagem_erro}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {ficha.cliente.nome}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={ficha.status} />
                    {ficha.lote_gerado_id && (
                      <Link
                        to={`/app/lotes/${ficha.lote_gerado_id}`}
                        className="ml-2 text-[11px] text-brand-700 hover:underline"
                      >
                        ver lote →
                      </Link>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {ficha.total_linhas}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">
                    {ficha.valor_total_centavos > 0
                      ? formatBRL(ficha.valor_total_centavos)
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600 text-xs">
                    <Clock size={12} className="inline mr-1 text-slate-400" />
                    {formatDateTime(ficha.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {ficha.status !== "CONVERTIDA" && (
                      <button
                        type="button"
                        onClick={() => confirmarExclusao(ficha)}
                        title="Excluir ficha"
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600 transition"
                        disabled={removerMutation.isPending}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Modal de upload
// ============================================================

interface UploadFichaModalProps {
  onClose: () => void;
  onSuccess: (ficha: FichaDetalhe) => void;
}

function UploadFichaModal({ onClose, onSuccess }: UploadFichaModalProps) {
  const [clienteId, setClienteId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: Cliente[] }>(
        "/api/clientes/",
      );
      return data.clientes;
    },
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || !clienteId) throw new Error("Selecione cliente e arquivo");
      if (file.size > MAX_MB * 1024 * 1024) {
        throw new Error(
          `Arquivo de ${(file.size / 1024 / 1024).toFixed(1)}MB excede o limite de ${MAX_MB}MB.`,
        );
      }
      const fd = new FormData();
      fd.append("cliente_id", clienteId);
      fd.append("arquivo", file);
      fd.append("executar_ocr", "true");
      const { data } = await api.post<FichaDetalhe>(
        "/api/fichas/upload",
        fd,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 180_000 },
      );
      return data;
    },
    onSuccess,
    onError: (err) => setError(getErrorMessage(err)),
  });

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setError(null);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0] ?? null;
    if (f) {
      setFile(f);
      setError(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">
            Enviar ficha de plantão
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Foto ou PDF da ficha carimbada. O OCR vai extrair os plantões em
            alguns segundos.
          </p>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Cliente / hospital
            </label>
            <select
              value={clienteId}
              onChange={(e) => setClienteId(e.target.value)}
              className="input"
              required
            >
              <option value="">Selecione...</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Arquivo (foto ou PDF)
            </label>
            <div
              onClick={() => inputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="cursor-pointer border-2 border-dashed border-slate-200 hover:border-brand-400 hover:bg-slate-50 rounded-lg px-4 py-8 text-center transition"
            >
              <Upload size={28} className="mx-auto text-slate-400 mb-2" />
              {file ? (
                <>
                  <p className="text-sm font-medium text-slate-800">
                    {file.name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {(file.size / 1024).toFixed(0)} KB •{" "}
                    {file.type || "arquivo"}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm text-slate-700">
                    Clique para selecionar ou arraste o arquivo
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    JPG, PNG, TIFF, PDF (até {MAX_MB}MB)
                  </p>
                </>
              )}
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                onChange={handleFile}
                className="hidden"
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded px-3 py-2">
            <strong>Dica:</strong> tire a foto sob boa iluminação, com a folha
            chapada na superfície. Quanto melhor a foto, mais campos o OCR
            consegue ler sem revisão manual.
          </div>
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={upload.isPending}
            className="btn-ghost"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => upload.mutate()}
            disabled={!file || !clienteId || upload.isPending}
            className="btn-primary"
          >
            {upload.isPending ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Processando OCR...
              </>
            ) : (
              <>
                <Upload size={16} />
                Enviar e processar
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
