import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Upload as UploadIcon } from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type { Cliente } from "@/types";

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [clienteId, setClienteId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: Cliente[] }>(
        "/api/clientes/",
      );
      return data.clientes;
    },
  });

  // Pré-seleciona o primeiro cliente quando carrega
  useEffect(() => {
    if (clientes.length > 0 && !clienteId) {
      setClienteId(clientes[0]!.id);
    }
  }, [clientes, clienteId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !clienteId) {
      setError("Escolha o cliente e um arquivo");
      return;
    }
    setError(null);
    setSubmitting(true);

    const formData = new FormData();
    formData.append("cliente_id", clienteId);
    formData.append("arquivo", file);

    try {
      const { data } = await api.post<{ lote_id: string }>(
        "/api/lotes/upload",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      navigate(`/app/lotes/${data.lote_id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">Novo Lote</h1>
      <p className="text-sm text-slate-500 mb-6">
        Faça upload de uma planilha XLSX ou CSV. O sistema valida e prepara
        para sua revisão.
      </p>

      <form onSubmit={handleSubmit} className="card space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Cliente
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
          {clientes.length === 0 && (
            <p className="text-xs text-slate-500 mt-1">
              Nenhum cliente cadastrado ainda. Cadastre um cliente antes de fazer
              upload.
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Planilha
          </label>
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="input cursor-pointer file:mr-3 file:py-1 file:px-3 file:rounded
              file:border-0 file:bg-slate-100 file:text-slate-700 file:text-sm"
            required
          />
          <p className="text-xs text-slate-500 mt-1">
            Formatos suportados: .xlsx, .xls, .csv (máx. 50MB)
          </p>
        </div>

        {error && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !file || !clienteId}
          className="btn-primary"
        >
          <UploadIcon size={16} />
          {submitting ? "Enviando..." : "Enviar lote"}
        </button>
      </form>
    </div>
  );
}
