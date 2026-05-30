import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Hospital,
  KeyRound,
  Plus,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { LABEL_MODO_PAGAMENTO } from "@/types";
import type {
  ContaRepasse,
  CriarHospitalPayload,
  HospitalCarteira,
  ModoPagamento,
} from "@/types";

const FORM_VAZIO: CriarHospitalPayload = {
  nome: "",
  cnpj: null,
  modo_pagamento: "CNAB_BANCARIO",
  conta_pagadora_id: null,
  login_email: null,
  login_senha: null,
  login_nome: null,
};

export function CarteiraPage() {
  const queryClient = useQueryClient();
  const [criando, setCriando] = useState(false);
  const [form, setForm] = useState<CriarHospitalPayload>(FORM_VAZIO);
  const [comLogin, setComLogin] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data: hospitais, isLoading } = useQuery({
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

  const criar = useMutation({
    mutationFn: async (payload: CriarHospitalPayload) => {
      const { data } = await api.post<HospitalCarteira>(
        "/api/carteira/hospitais",
        payload,
      );
      return data;
    },
    onSuccess: () => {
      setOkMsg("Hospital adicionado à carteira.");
      setErro(null);
      setCriando(false);
      setForm(FORM_VAZIO);
      setComLogin(false);
      void queryClient.invalidateQueries({ queryKey: ["carteira", "hospitais"] });
      window.setTimeout(() => setOkMsg(null), 4000);
    },
    onError: (err) => {
      setErro(getErrorMessage(err));
      setOkMsg(null);
    },
  });

  const vincularConta = useMutation({
    mutationFn: async (args: { id: string; conta_pagadora_id: string | null }) => {
      await api.put(`/api/carteira/hospitais/${args.id}`, {
        conta_pagadora_id: args.conta_pagadora_id,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["carteira", "hospitais"] });
    },
    onError: (err) => setErro(getErrorMessage(err)),
  });

  function update<K extends keyof CriarHospitalPayload>(
    key: K,
    value: CriarHospitalPayload[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    const payload: CriarHospitalPayload = { ...form };
    if (!comLogin) {
      payload.login_email = null;
      payload.login_senha = null;
      payload.login_nome = null;
    } else if (!payload.login_email || !payload.login_senha) {
      setErro("Pra criar login do hospital, informe e-mail e senha.");
      return;
    }
    criar.mutate(payload);
  }

  const contasAtivas = (contas ?? []).filter((c) => c.ativo);

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-brand-700/70">
        Carregando carteira de hospitais...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <Hospital size={24} className="text-accent-600" />
            Carteira de hospitais
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Os hospitais que você atende. Cada um aponta pra uma{" "}
            <strong>conta de repasse</strong> (de onde sai o pagamento dele).
            O hospital pode ter login próprio pra subir planilhas e ver os
            repasses; você "entra no hospital" pelo seletor do topo pra
            aprovar e executar o pagamento.
          </p>
        </div>
        {!criando && (
          <button
            onClick={() => {
              setForm(FORM_VAZIO);
              setComLogin(false);
              setCriando(true);
              setErro(null);
              setOkMsg(null);
            }}
            className="btn-primary shrink-0"
          >
            <Plus size={16} />
            Novo hospital
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

      {contasAtivas.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          Você ainda não tem nenhuma <strong>conta de repasse</strong>{" "}
          cadastrada. Cadastre ao menos uma em{" "}
          <em>Financeiro → Contas de repasse</em> pra poder ligar aos
          hospitais.
        </div>
      )}

      {/* Lista */}
      {!criando && (
        <div className="space-y-3">
          {(hospitais ?? []).length === 0 && (
            <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center text-sm text-slate-500">
              Nenhum hospital na carteira ainda. Clique em{" "}
              <strong>Novo hospital</strong>.
            </div>
          )}
          {(hospitais ?? []).map((h) => (
            <div
              key={h.id}
              className={`bg-white rounded-2xl border p-4 ${
                h.ativo ? "border-slate-200" : "border-slate-200 opacity-60"
              }`}
            >
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-brand-900">
                      {h.nome}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                      {LABEL_MODO_PAGAMENTO[h.modo_pagamento]}
                    </span>
                    {h.tem_login && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 flex items-center gap-1">
                        <KeyRound size={11} /> com login
                      </span>
                    )}
                  </div>
                  {h.cnpj && (
                    <p className="text-sm text-slate-500 mt-1 font-mono">
                      CNPJ {h.cnpj}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-500">
                    Conta de repasse
                  </label>
                  <select
                    value={h.conta_pagadora_id ?? ""}
                    onChange={(e) =>
                      vincularConta.mutate({
                        id: h.id,
                        conta_pagadora_id: e.target.value || null,
                      })
                    }
                    className="input py-1.5 text-sm"
                  >
                    <option value="">— sem conta —</option>
                    {contasAtivas.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.apelido || c.razao_social}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form de criação */}
      {criando && (
        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-5"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-brand-900 flex items-center gap-2">
              <Building2 size={18} className="text-accent-600" />
              Novo hospital
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
                Nome do hospital *
              </label>
              <input
                type="text"
                required
                maxLength={255}
                value={form.nome}
                onChange={(e) => update("nome", e.target.value)}
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                CNPJ
              </label>
              <input
                type="text"
                maxLength={18}
                placeholder="00.000.000/0001-00"
                value={form.cnpj ?? ""}
                onChange={(e) => update("cnpj", e.target.value || null)}
                className="input font-mono"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Modo de pagamento *
              </label>
              <select
                value={form.modo_pagamento}
                onChange={(e) =>
                  update("modo_pagamento", e.target.value as ModoPagamento)
                }
                className="input"
              >
                {(
                  Object.keys(LABEL_MODO_PAGAMENTO) as ModoPagamento[]
                ).map((m) => (
                  <option key={m} value={m}>
                    {LABEL_MODO_PAGAMENTO[m]}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Conta de repasse (de onde sai o pagamento)
              </label>
              <select
                value={form.conta_pagadora_id ?? ""}
                onChange={(e) =>
                  update("conta_pagadora_id", e.target.value || null)
                }
                className="input"
              >
                <option value="">— definir depois —</option>
                {contasAtivas.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.apelido || c.razao_social}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Login do hospital */}
          <div className="border-t border-slate-200 pt-4">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                checked={comLogin}
                onChange={(e) => setComLogin(e.target.checked)}
                className="rounded border-slate-300"
              />
              Criar login pro hospital (sobe planilha / vê repasses)
            </label>
            {comLogin && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    E-mail *
                  </label>
                  <input
                    type="email"
                    value={form.login_email ?? ""}
                    onChange={(e) =>
                      update("login_email", e.target.value || null)
                    }
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Senha *
                  </label>
                  <input
                    type="text"
                    value={form.login_senha ?? ""}
                    onChange={(e) =>
                      update("login_senha", e.target.value || null)
                    }
                    className="input font-mono"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Nome do contato
                  </label>
                  <input
                    type="text"
                    value={form.login_nome ?? ""}
                    onChange={(e) =>
                      update("login_nome", e.target.value || null)
                    }
                    className="input"
                  />
                </div>
              </div>
            )}
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
              disabled={criar.isPending}
              className="btn-primary"
            >
              {criar.isPending ? "Salvando..." : "Adicionar à carteira"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
