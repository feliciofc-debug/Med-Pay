import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  CreditCard,
  Hash,
  Info,
  MapPin,
  Save,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type {
  EmpresaPagadora,
  EmpresaPagadoraPayload,
  TipoInscricao,
} from "@/types";

const UFS = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
  "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
  "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

// Defaults a partir do template "CNAB - ARQUIVO MESTRE - AURIS" do Thiago.
// O usuário pode trocar tudo, mas começar com a config dele economiza tempo
// na sessão presencial.
const DEFAULTS_AURIS: EmpresaPagadoraPayload = {
  razao_social: "UNICRED DO BRASIL",
  nome_fantasia: null,
  tipo_inscricao: "CNPJ",
  cnpj_cpf: "40.917.845/0001-60",
  banco_codigo: "136",
  agencia: "1214",
  agencia_dv: "7",
  conta: "21390",
  conta_dv: "0",
  codigo_convenio: "9845046",
  endereco_logradouro: "AV DAS AMERICAS",
  endereco_numero: "11365",
  endereco_complemento: "SALA 340",
  endereco_cidade: "RIO DE JANEIRO",
  endereco_cep: "22793-082",
  endereco_uf: "RJ",
  proximo_numero_sequencial: 1,
};

function empresaToPayload(e: EmpresaPagadora): EmpresaPagadoraPayload {
  return {
    razao_social: e.razao_social,
    nome_fantasia: e.nome_fantasia,
    tipo_inscricao: e.tipo_inscricao,
    cnpj_cpf: e.cnpj_cpf,
    banco_codigo: e.banco_codigo,
    agencia: e.agencia,
    agencia_dv: e.agencia_dv,
    // Conta vem mascarada do backend; o usuário precisa redigitar se quiser
    // trocar. Mantemos vazio pra forçar revalidação consciente.
    conta: "",
    conta_dv: e.conta_dv,
    codigo_convenio: e.codigo_convenio,
    endereco_logradouro: e.endereco_logradouro,
    endereco_numero: e.endereco_numero,
    endereco_complemento: e.endereco_complemento,
    endereco_cidade: e.endereco_cidade,
    endereco_cep: e.endereco_cep,
    endereco_uf: e.endereco_uf,
    proximo_numero_sequencial: e.proximo_numero_sequencial,
  };
}

export function AdminEmpresaPagadoraPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EmpresaPagadoraPayload>(DEFAULTS_AURIS);
  const [erro, setErro] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const { data: empresa, isLoading } = useQuery({
    queryKey: ["admin", "empresa-pagadora"],
    queryFn: async (): Promise<EmpresaPagadora | null> => {
      try {
        const { data } = await api.get<EmpresaPagadora>(
          "/api/admin/empresa-pagadora",
        );
        return data;
      } catch (err) {
        // 404 = ainda não cadastrada — primeira vez
        const msg = getErrorMessage(err);
        if (msg.toLowerCase().includes("não cadastrada")) {
          return null;
        }
        throw err;
      }
    },
    retry: false,
  });

  useEffect(() => {
    if (empresa) {
      setForm(empresaToPayload(empresa));
    }
  }, [empresa]);

  const salvar = useMutation({
    mutationFn: async (payload: EmpresaPagadoraPayload) => {
      const { data } = await api.put<EmpresaPagadora>(
        "/api/admin/empresa-pagadora",
        payload,
      );
      return data;
    },
    onSuccess: (data) => {
      setOkMsg(
        `Empresa pagadora ${empresa ? "atualizada" : "cadastrada"} com sucesso.`,
      );
      setErro(null);
      setForm(empresaToPayload(data));
      void queryClient.invalidateQueries({
        queryKey: ["admin", "empresa-pagadora"],
      });
      window.setTimeout(() => setOkMsg(null), 4000);
    },
    onError: (err) => {
      setErro(getErrorMessage(err));
      setOkMsg(null);
    },
  });

  const sequencialAtual = empresa?.proximo_numero_sequencial ?? 1;
  const podeAlterarSequencial = useMemo(
    () => form.proximo_numero_sequencial >= sequencialAtual,
    [form.proximo_numero_sequencial, sequencialAtual],
  );

  function update<K extends keyof EmpresaPagadoraPayload>(
    key: K,
    value: EmpresaPagadoraPayload[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setOkMsg(null);

    if (!form.conta.trim()) {
      setErro(
        "Conta é obrigatória. Digite o número da conta (sem o dígito) — por segurança, " +
          "a conta atual vem mascarada e precisa ser redigitada a cada alteração.",
      );
      return;
    }
    if (!podeAlterarSequencial) {
      setErro(
        `Sequencial não pode regredir. Valor mínimo atual: ${sequencialAtual}. ` +
          `Banco vai recusar arquivo CNAB com sequencial duplicado.`,
      );
      return;
    }

    salvar.mutate(form);
  }

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-brand-700/70">
        Carregando configuração da empresa pagadora...
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <header>
        <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
          <Building2 size={24} className="text-accent-600" />
          Empresa pagadora
        </h1>
        <p className="text-sm text-brand-700/70 mt-1">
          Dados que entram no <strong>Header do arquivo CNAB 240</strong>. É a
          identidade da Auris no banco — todo arquivo gerado pelo MedPag sai
          com esses dados. Aqui é o equivalente à aba <em>INICIO</em> do
          template Excel da Unicred.
        </p>
      </header>

      {!empresa && (
        <div className="bg-accent-50 border border-accent-200 rounded-lg p-4 flex items-start gap-3">
          <Info size={18} className="text-accent-700 shrink-0 mt-0.5" />
          <div className="text-sm text-accent-900">
            <p className="font-medium">Primeira configuração</p>
            <p className="text-accent-800/80 mt-1">
              Os valores abaixo já vêm pré-preenchidos com os dados que o
              Thiago usa na planilha CNAB que ele já roda hoje (Av. das
              Américas, 11365, Sala 340 — Unicred Ag 1214-7 / CC 21390-0).
              Confirme que está correto antes de salvar.
            </p>
          </div>
        </div>
      )}

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

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Identificação */}
        <Section title="Identificação" icon={<Building2 size={18} />}>
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
          <Field label="Nome fantasia">
            <input
              type="text"
              maxLength={255}
              value={form.nome_fantasia ?? ""}
              onChange={(e) =>
                update("nome_fantasia", e.target.value || null)
              }
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
          <Field label="CNPJ / CPF *" colSpan={2}>
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

        {/* Dados Unicred */}
        <Section title="Conta Unicred" icon={<CreditCard size={18} />}>
          <Field label="Banco">
            <input
              type="text"
              value={form.banco_codigo}
              onChange={(e) => update("banco_codigo", e.target.value)}
              className="input bg-slate-50"
              maxLength={3}
            />
          </Field>
          <Field label="Agência *">
            <input
              type="text"
              required
              maxLength={5}
              placeholder="1214"
              value={form.agencia}
              onChange={(e) => update("agencia", e.target.value)}
              className="input font-mono"
            />
          </Field>
          <Field label="DV Agência">
            <input
              type="text"
              maxLength={1}
              placeholder="7"
              value={form.agencia_dv ?? ""}
              onChange={(e) => update("agencia_dv", e.target.value || null)}
              className="input font-mono"
            />
          </Field>
          <Field
            label={
              empresa
                ? `Conta * (atual: ${empresa.conta_mascarada}, redigite pra alterar)`
                : "Conta *"
            }
            colSpan={2}
          >
            <input
              type="text"
              required
              maxLength={20}
              placeholder="21390"
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
              placeholder="0"
              value={form.conta_dv}
              onChange={(e) => update("conta_dv", e.target.value)}
              className="input font-mono"
            />
          </Field>
          <Field label="Código de convênio Unicred *" colSpan={3}>
            <input
              type="text"
              required
              maxLength={20}
              placeholder="9845046"
              value={form.codigo_convenio}
              onChange={(e) => update("codigo_convenio", e.target.value)}
              className="input font-mono"
            />
            <p className="text-xs text-slate-500 mt-1">
              Fornecido pela Unicred no contrato. Aparece no Header de Lote
              do CNAB e identifica a empresa no SPB.
            </p>
          </Field>
        </Section>

        {/* Endereço */}
        <Section title="Endereço da empresa" icon={<MapPin size={18} />}>
          <Field label="Logradouro *" colSpan={3}>
            <input
              type="text"
              required
              maxLength={30}
              placeholder="AV DAS AMERICAS"
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
              placeholder="11365"
              value={form.endereco_numero}
              onChange={(e) => update("endereco_numero", e.target.value)}
              className="input font-mono"
            />
          </Field>
          <Field label="Complemento" colSpan={2}>
            <input
              type="text"
              maxLength={15}
              placeholder="SALA 340"
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
              placeholder="RIO DE JANEIRO"
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
              placeholder="22793-082"
              value={form.endereco_cep}
              onChange={(e) => update("endereco_cep", e.target.value)}
              className="input font-mono"
            />
          </Field>
        </Section>

        {/* Sequencial */}
        <Section title="Numeração de arquivo" icon={<Hash size={18} />}>
          <Field
            label={`Próximo número sequencial * (mínimo atual: ${sequencialAtual})`}
            colSpan={3}
          >
            <input
              type="number"
              required
              min={sequencialAtual}
              value={form.proximo_numero_sequencial}
              onChange={(e) =>
                update(
                  "proximo_numero_sequencial",
                  Number(e.target.value) || 1,
                )
              }
              className="input font-mono w-32"
            />
            <p className="text-xs text-slate-500 mt-1">
              Cada arquivo CNAB precisa ter um número único, em ordem
              crescente. O banco rejeita arquivos com sequencial repetido ou
              menor que o último processado. Em caso de dúvida, alinhe esse
              valor com o que a sua planilha CNAB atual está gerando.
            </p>
          </Field>
        </Section>

        <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
          <button
            type="submit"
            disabled={salvar.isPending}
            className="btn-primary"
          >
            <Save size={16} />
            {salvar.isPending
              ? "Salvando..."
              : empresa
                ? "Salvar alterações"
                : "Cadastrar empresa pagadora"}
          </button>
        </div>
      </form>
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
    colSpan === 3
      ? "md:col-span-3"
      : colSpan === 2
        ? "md:col-span-2"
        : "";
  return (
    <div className={className}>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
