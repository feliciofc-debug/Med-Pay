import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownToLine,
  CheckCircle2,
  Plus,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type {
  Aporte,
  ContaRepasse,
  CriarAportePayload,
  HospitalCarteira,
} from "@/types";

function brl(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

const HOJE = new Date().toISOString().slice(0, 10);

const FORM_VAZIO = {
  cliente_id: "",
  conta_pagadora_id: "",
  valor_reais: "",
  data_recebimento: HOJE,
  competencia: "",
  referencia: "",
};

export function AportesPage() {
  const queryClient = useQueryClient();
  const [criando, setCriando] = useState(false);
  const [form, setForm] = useState({ ...FORM_VAZIO });
  const [erro, setErro] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data: aportes, isLoading } = useQuery({
    queryKey: ["aportes"],
    queryFn: async (): Promise<Aporte[]> => {
      const { data } = await api.get<Aporte[]>("/api/aportes");
      return data;
    },
  });

  const { data: hospitais } = useQuery({
    queryKey: ["carteira", "hospitais"],
    queryFn: async (): Promise<HospitalCarteira[]> => {
      const { data } = await api.get<HospitalCarteira[]>(
        "/api/carteira/hospitais",
      );
      return data;
    },
  });

  const { data: contas } = useQuery({
    queryKey: ["contas-repasse"],
    queryFn: async (): Promise<ContaRepasse[]> => {
      const { data } = await api.get<ContaRepasse[]>("/api/contas-repasse");
      return data;
    },
  });

  const registrar = useMutation({
    mutationFn: async (payload: CriarAportePayload) => {
      const { data } = await api.post<Aporte>("/api/aportes", payload);
      return data;
    },
    onSuccess: () => {
      setOkMsg("Aporte registrado.");
      setErro(null);
      setCriando(false);
      setForm({ ...FORM_VAZIO });
      void queryClient.invalidateQueries({ queryKey: ["aportes"] });
      window.setTimeout(() => setOkMsg(null), 4000);
    },
    onError: (err) => {
      setErro(getErrorMessage(err));
      setOkMsg(null);
    },
  });

  const confirmar = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/aportes/${id}/confirmar`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["aportes"] });
    },
    onError: (err) => setErro(getErrorMessage(err)),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!form.cliente_id) {
      setErro("Escolha o hospital que fez o depósito.");
      return;
    }
    const valorCentavos = Math.round(
      Number(form.valor_reais.replace(/\./g, "").replace(",", ".")) * 100,
    );
    if (!Number.isFinite(valorCentavos) || valorCentavos <= 0) {
      setErro("Valor inválido.");
      return;
    }
    registrar.mutate({
      cliente_id: form.cliente_id,
      conta_pagadora_id: form.conta_pagadora_id || null,
      valor_centavos: valorCentavos,
      data_recebimento: form.data_recebimento,
      competencia: form.competencia || null,
      referencia: form.referencia || null,
    });
  }

  const contasAtivas = (contas ?? []).filter((c) => c.ativo);

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-brand-700/70">Carregando aportes...</div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <ArrowDownToLine size={24} className="text-accent-600" />
            Aportes recebidos
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Registre quanto cada hospital depositou na sua conta antes do
            repasse. O aporte <strong>confirmado</strong> libera a
            distribuição daquele hospital — você só paga o que entrou.
          </p>
        </div>
        {!criando && (
          <button
            onClick={() => {
              setForm({ ...FORM_VAZIO });
              setCriando(true);
              setErro(null);
              setOkMsg(null);
            }}
            className="btn-primary shrink-0"
          >
            <Plus size={16} />
            Registrar aporte
          </button>
        )}
      </header>

      {okMsg && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 flex items-center gap-2 text-sm text-emerald-800">
          <CheckCircle2 size={18} />
          {okMsg}
        </div>
      )}
      {erro && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2 text-sm text-red-800">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" />
          {erro}
        </div>
      )}

      {/* Form */}
      {criando && (
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-brand-900">
              Novo aporte
            </h2>
            <button
              type="button"
              onClick={() => setCriando(false)}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
            >
              <X size={18} />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Hospital *
              </label>
              <select
                value={form.cliente_id}
                onChange={(e) =>
                  setForm((p) => ({ ...p, cliente_id: e.target.value }))
                }
                className="input"
                required
              >
                <option value="">— escolha o hospital —</option>
                {(hospitais ?? []).map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Valor (R$) *
              </label>
              <input
                type="text"
                inputMode="decimal"
                placeholder="0,00"
                value={form.valor_reais}
                onChange={(e) =>
                  setForm((p) => ({ ...p, valor_reais: e.target.value }))
                }
                className="input font-mono"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Data do recebimento *
              </label>
              <input
                type="date"
                value={form.data_recebimento}
                onChange={(e) =>
                  setForm((p) => ({ ...p, data_recebimento: e.target.value }))
                }
                className="input"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Conta que recebeu
              </label>
              <select
                value={form.conta_pagadora_id}
                onChange={(e) =>
                  setForm((p) => ({ ...p, conta_pagadora_id: e.target.value }))
                }
                className="input"
              >
                <option value="">— não informar —</option>
                {contasAtivas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.apelido || c.razao_social}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Competência (MM/AAAA)
              </label>
              <input
                type="text"
                maxLength={7}
                placeholder="05/2026"
                value={form.competencia}
                onChange={(e) =>
                  setForm((p) => ({ ...p, competencia: e.target.value }))
                }
                className="input font-mono"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Referência / observação
              </label>
              <input
                type="text"
                maxLength={255}
                placeholder="Ex.: TED Santa Casa - folha maio"
                value={form.referencia}
                onChange={(e) =>
                  setForm((p) => ({ ...p, referencia: e.target.value }))
                }
                className="input"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setCriando(false)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={registrar.isPending}
              className="btn-primary"
            >
              {registrar.isPending ? "Salvando..." : "Registrar aporte"}
            </button>
          </div>
        </form>
      )}

      {/* Lista */}
      <div className="space-y-2">
        {(aportes ?? []).length === 0 && !criando && (
          <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center text-sm text-slate-500">
            Nenhum aporte registrado ainda.
          </div>
        )}
        {(aportes ?? []).map((a) => (
          <div
            key={a.id}
            className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center justify-between gap-4"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-brand-900">
                  {a.cliente_nome ?? "Hospital"}
                </span>
                <span className="font-mono text-brand-900">
                  {brl(a.valor_centavos)}
                </span>
                {a.status === "CONFIRMADO" ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">
                    confirmado
                  </span>
                ) : (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-100">
                    pendente
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-1">
                {new Date(a.data_recebimento).toLocaleDateString("pt-BR")}
                {a.competencia ? ` · comp ${a.competencia}` : ""}
                {a.referencia ? ` · ${a.referencia}` : ""}
              </p>
            </div>
            {a.status === "PENDENTE" && (
              <button
                onClick={() => confirmar.mutate(a.id)}
                disabled={confirmar.isPending}
                className="btn-secondary text-sm shrink-0"
              >
                <CheckCircle2 size={14} />
                Confirmar
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
