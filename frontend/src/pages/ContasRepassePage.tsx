import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Banknote,
  Building2,
  CheckCircle2,
  CreditCard,
  Hash,
  MapPin,
  Plus,
  Power,
  Save,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import {
  CODIGO_BANCO_POR_EMISSOR,
  LABEL_BANCO_EMISSOR,
  LABEL_MODO_EXECUCAO,
} from "@/types";
import type {
  BancoEmissor,
  ContaRepasse,
  ContaRepassePayload,
  ModoExecucao,
  TipoInscricao,
} from "@/types";

const UFS = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
  "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
  "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

const FORM_VAZIO: ContaRepassePayload = {
  apelido: "",
  modo_execucao: "CNAB",
  razao_social: "",
  nome_fantasia: null,
  tipo_inscricao: "CNPJ",
  cnpj_cpf: "",
  banco_emissor: "UNICRED",
  banco_codigo: "136",
  agencia: "",
  agencia_dv: null,
  conta: "",
  conta_dv: "",
  codigo_convenio: "",
  endereco_logradouro: "",
  endereco_numero: "",
  endereco_complemento: null,
  endereco_cidade: "",
  endereco_cep: "",
  endereco_uf: "RJ",
  proximo_numero_sequencial: 1,
};

function contaToPayload(c: ContaRepasse): ContaRepassePayload {
  return {
    apelido: c.apelido,
    modo_execucao: c.modo_execucao,
    razao_social: c.razao_social,
    nome_fantasia: c.nome_fantasia,
    tipo_inscricao: c.tipo_inscricao,
    cnpj_cpf: c.cnpj_cpf,
    banco_emissor: c.banco_emissor,
    banco_codigo: c.banco_codigo,
    agencia: c.agencia,
    agencia_dv: c.agencia_dv,
    conta: "", // mascarada — redigitar pra alterar
    conta_dv: c.conta_dv,
    codigo_convenio: c.codigo_convenio,
    endereco_logradouro: c.endereco_logradouro,
    endereco_numero: c.endereco_numero,
    endereco_complemento: c.endereco_complemento,
    endereco_cidade: c.endereco_cidade,
    endereco_cep: c.endereco_cep,
    endereco_uf: c.endereco_uf,
    proximo_numero_sequencial: c.proximo_numero_sequencial,
  };
}

export function ContasRepassePage() {
  const queryClient = useQueryClient();
  // null = só lista; "nova" = criando; ContaRepasse = editando
  const [editando, setEditando] = useState<ContaRepasse | "nova" | null>(null);
  const [form, setForm] = useState<ContaRepassePayload>(FORM_VAZIO);
  const [erro, setErro] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data: contas, isLoading } = useQuery({
    queryKey: ["contas-repasse"],
    queryFn: async (): Promise<ContaRepasse[]> => {
      const { data } = await api.get<ContaRepasse[]>("/api/contas-repasse");
      return data;
    },
  });

  const salvar = useMutation({
    mutationFn: async (payload: ContaRepassePayload) => {
      if (editando && editando !== "nova") {
        const { data } = await api.put<ContaRepasse>(
          `/api/contas-repasse/${editando.id}`,
          payload,
        );
        return data;
      }
      const { data } = await api.post<ContaRepasse>(
        "/api/contas-repasse",
        payload,
      );
      return data;
    },
    onSuccess: () => {
      setOkMsg(
        editando === "nova" ? "Conta cadastrada." : "Conta atualizada.",
      );
      setErro(null);
      setEditando(null);
      setForm(FORM_VAZIO);
      void queryClient.invalidateQueries({ queryKey: ["contas-repasse"] });
      window.setTimeout(() => setOkMsg(null), 4000);
    },
    onError: (err) => {
      setErro(getErrorMessage(err));
      setOkMsg(null);
    },
  });

  const desativar = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/contas-repasse/${id}/desativar`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contas-repasse"] });
    },
    onError: (err) => setErro(getErrorMessage(err)),
  });

  function abrirNova() {
    setForm(FORM_VAZIO);
    setEditando("nova");
    setErro(null);
    setOkMsg(null);
  }

  function abrirEdicao(c: ContaRepasse) {
    setForm(contaToPayload(c));
    setEditando(c);
    setErro(null);
    setOkMsg(null);
  }

  function update<K extends keyof ContaRepassePayload>(
    key: K,
    value: ContaRepassePayload[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!form.conta.trim()) {
      setErro(
        "Conta é obrigatória. Por segurança a conta atual vem mascarada e " +
          "precisa ser redigitada a cada alteração.",
      );
      return;
    }
    salvar.mutate(form);
  }

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-brand-700/70">
        Carregando contas de repasse...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <Banknote size={24} className="text-accent-600" />
            Contas de repasse
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            As contas bancárias de onde saem os pagamentos. Você pode ter
            várias (Bradesco, Itaú, Unicred, Santander...) — cada hospital da
            carteira aponta pra uma delas. Hoje geram <strong>CNAB</strong>;
            quando o banco liberar API, é só trocar o modo de execução.
          </p>
        </div>
        {editando === null && (
          <button onClick={abrirNova} className="btn-primary shrink-0">
            <Plus size={16} />
            Nova conta
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

      {/* Lista de contas */}
      {editando === null && (
        <div className="space-y-3">
          {(contas ?? []).length === 0 && (
            <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center text-sm text-slate-500">
              Nenhuma conta cadastrada ainda. Clique em{" "}
              <strong>Nova conta</strong> pra adicionar a primeira.
            </div>
          )}
          {(contas ?? []).map((c) => (
            <div
              key={c.id}
              className={`bg-white rounded-2xl border p-4 flex items-center justify-between gap-4 ${
                c.ativo ? "border-slate-200" : "border-slate-200 opacity-60"
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-brand-900">
                    {c.apelido || c.razao_social}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-100">
                    {LABEL_BANCO_EMISSOR[c.banco_emissor]}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-accent-50 text-accent-700 border border-accent-100">
                    {LABEL_MODO_EXECUCAO[c.modo_execucao]}
                  </span>
                  {!c.ativo && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                      inativa
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-500 mt-1 font-mono">
                  Ag {c.agencia}
                  {c.agencia_dv ? `-${c.agencia_dv}` : ""} · CC{" "}
                  {c.conta_mascarada}-{c.conta_dv} · conv {c.codigo_convenio}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => abrirEdicao(c)}
                  className="btn-secondary text-sm"
                >
                  Editar
                </button>
                {c.ativo && (
                  <button
                    onClick={() => desativar.mutate(c.id)}
                    disabled={desativar.isPending}
                    className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50"
                    title="Desativar conta"
                  >
                    <Power size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Formulário */}
      {editando !== null && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-brand-900">
              {editando === "nova" ? "Nova conta" : "Editar conta"}
            </h2>
            <button
              type="button"
              onClick={() => setEditando(null)}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
            >
              <X size={18} />
            </button>
          </div>

          <Section title="Identificação da conta" icon={<Building2 size={18} />}>
            <Field label="Apelido (ex.: Itaú Repasse)" colSpan={2}>
              <input
                type="text"
                maxLength={80}
                placeholder="Itaú Repasse"
                value={form.apelido ?? ""}
                onChange={(e) => update("apelido", e.target.value || null)}
                className="input"
              />
            </Field>
            <Field label="Modo de execução *">
              <select
                value={form.modo_execucao}
                onChange={(e) =>
                  update("modo_execucao", e.target.value as ModoExecucao)
                }
                className="input"
              >
                {(Object.keys(LABEL_MODO_EXECUCAO) as ModoExecucao[]).map(
                  (m) => (
                    <option key={m} value={m}>
                      {LABEL_MODO_EXECUCAO[m]}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Razão social *" colSpan={2}>
              <input
                type="text"
                required
                maxLength={255}
                value={form.razao_social}
                onChange={(e) => update("razao_social", e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Tipo *">
              <select
                value={form.tipo_inscricao}
                onChange={(e) =>
                  update("tipo_inscricao", e.target.value as TipoInscricao)
                }
                className="input"
              >
                <option value="CNPJ">CNPJ</option>
                <option value="CPF">CPF</option>
              </select>
            </Field>
            <Field label="CNPJ / CPF *" colSpan={3}>
              <input
                type="text"
                required
                placeholder="40.917.845/0001-60"
                value={form.cnpj_cpf}
                onChange={(e) => update("cnpj_cpf", e.target.value)}
                className="input font-mono"
              />
            </Field>
          </Section>

          <Section title="Conta bancária e CNAB" icon={<CreditCard size={18} />}>
            <Field label="Banco emissor *" colSpan={3}>
              <select
                value={form.banco_emissor}
                onChange={(e) => {
                  const banco = e.target.value as BancoEmissor;
                  setForm((prev) => ({
                    ...prev,
                    banco_emissor: banco,
                    banco_codigo: CODIGO_BANCO_POR_EMISSOR[banco],
                  }));
                }}
                className="input"
              >
                {(Object.keys(LABEL_BANCO_EMISSOR) as BancoEmissor[]).map(
                  (b) => (
                    <option key={b} value={b}>
                      {LABEL_BANCO_EMISSOR[b]}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Código FEBRABAN">
              <input
                type="text"
                value={form.banco_codigo}
                readOnly
                className="input bg-slate-50 font-mono"
                maxLength={3}
              />
            </Field>
            <Field label="Agência *">
              <input
                type="text"
                required
                maxLength={5}
                value={form.agencia}
                onChange={(e) => update("agencia", e.target.value)}
                className="input font-mono"
              />
            </Field>
            <Field label="DV Agência">
              <input
                type="text"
                maxLength={1}
                value={form.agencia_dv ?? ""}
                onChange={(e) => update("agencia_dv", e.target.value || null)}
                className="input font-mono"
              />
            </Field>
            <Field
              label={
                editando !== "nova"
                  ? `Conta * (atual: ${editando.conta_mascarada}, redigite pra alterar)`
                  : "Conta *"
              }
              colSpan={2}
            >
              <input
                type="text"
                required
                maxLength={20}
                value={form.conta}
                onChange={(e) => update("conta", e.target.value)}
                className="input font-mono"
              />
            </Field>
            <Field label="DV Conta *">
              <input
                type="text"
                required
                maxLength={1}
                value={form.conta_dv}
                onChange={(e) => update("conta_dv", e.target.value)}
                className="input font-mono"
              />
            </Field>
            <Field label="Código de convênio *" colSpan={3}>
              <input
                type="text"
                required
                maxLength={20}
                value={form.codigo_convenio}
                onChange={(e) => update("codigo_convenio", e.target.value)}
                className="input font-mono"
              />
            </Field>
          </Section>

          <Section title="Endereço" icon={<MapPin size={18} />}>
            <Field label="Logradouro *" colSpan={3}>
              <input
                type="text"
                required
                maxLength={30}
                value={form.endereco_logradouro}
                onChange={(e) => update("endereco_logradouro", e.target.value)}
                className="input"
              />
            </Field>
            <Field label="Número *">
              <input
                type="text"
                required
                maxLength={5}
                value={form.endereco_numero}
                onChange={(e) => update("endereco_numero", e.target.value)}
                className="input font-mono"
              />
            </Field>
            <Field label="Complemento" colSpan={2}>
              <input
                type="text"
                maxLength={15}
                value={form.endereco_complemento ?? ""}
                onChange={(e) =>
                  update("endereco_complemento", e.target.value || null)
                }
                className="input"
              />
            </Field>
            <Field label="Cidade *" colSpan={2}>
              <input
                type="text"
                required
                maxLength={20}
                value={form.endereco_cidade}
                onChange={(e) => update("endereco_cidade", e.target.value)}
                className="input"
              />
            </Field>
            <Field label="UF *">
              <select
                value={form.endereco_uf}
                onChange={(e) => update("endereco_uf", e.target.value)}
                className="input"
              >
                {UFS.map((uf) => (
                  <option key={uf} value={uf}>
                    {uf}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="CEP *" colSpan={2}>
              <input
                type="text"
                required
                maxLength={9}
                value={form.endereco_cep}
                onChange={(e) => update("endereco_cep", e.target.value)}
                className="input font-mono"
              />
            </Field>
          </Section>

          <Section title="Numeração de arquivo" icon={<Hash size={18} />}>
            <Field label="Próximo número sequencial *" colSpan={3}>
              <input
                type="number"
                required
                min={1}
                value={form.proximo_numero_sequencial}
                onChange={(e) =>
                  update(
                    "proximo_numero_sequencial",
                    Number(e.target.value) || 1,
                  )
                }
                className="input font-mono w-32"
              />
            </Field>
          </Section>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setEditando(null)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={salvar.isPending}
              className="btn-primary"
            >
              <Save size={16} />
              {salvar.isPending ? "Salvando..." : "Salvar conta"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

// ============================================================
// Helpers de layout
// ============================================================

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-brand-900 flex items-center gap-2 mb-4">
        <span className="text-accent-600">{icon}</span>
        {title}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{children}</div>
    </section>
  );
}

function Field({
  label,
  colSpan,
  children,
}: {
  label: string;
  colSpan?: 2 | 3;
  children: React.ReactNode;
}) {
  const className =
    colSpan === 3 ? "md:col-span-3" : colSpan === 2 ? "md:col-span-2" : "";
  return (
    <div className={className}>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
