/**
 * Detalhe de uma equipe (`/app/equipes/:id`).
 *
 * Mostra os membros da equipe e as 3 ações principais:
 *   1. Adicionar/editar/remover membro
 *   2. Fazer fechamento mensal (digita horas, vê preview, confirma)
 *   3. Histórico de fechamentos (com link pro lote gerado)
 *
 * Foi pensada pra demo: o Sandro deve conseguir, em uma tela só:
 *   - Cadastrar os 10 plantonistas
 *   - Lançar 720h em "Junho/2026"
 *   - Ver: bruto R$ 108k, líquido R$ 108k, R$ 10.800 por médico
 *   - Confirmar e gerar o lote
 */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  Calculator,
  CheckCircle2,
  Edit3,
  HeartPulse,
  Loader2,
  Plus,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL } from "@/lib/utils";
import type {
  EquipeFlex,
  FechamentoEquipe,
  FechamentoEquipePayload,
  MembroEquipe,
  MembroEquipePayload,
} from "@/types";

export function EquipeDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showMembroModal, setShowMembroModal] = useState(false);
  const [editandoMembro, setEditandoMembro] = useState<MembroEquipe | null>(null);
  const [showFechamento, setShowFechamento] = useState(false);

  const { data: equipe, isLoading } = useQuery({
    queryKey: ["equipes", id],
    queryFn: async () => {
      const { data } = await api.get<EquipeFlex>(`/api/equipes/${id}`);
      return data;
    },
    enabled: !!id,
  });

  const { data: fechamentos = [] } = useQuery({
    queryKey: ["equipes", id, "fechamentos"],
    queryFn: async () => {
      const { data } = await api.get<FechamentoEquipe[]>(
        `/api/equipes/${id}/fechamentos`,
      );
      return data;
    },
    enabled: !!id,
  });

  const removerMembroMutation = useMutation({
    mutationFn: async (membroId: string) => {
      await api.delete(`/api/equipes/${id}/membros/${membroId}`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["equipes", id] });
    },
  });

  function confirmarRemocaoMembro(m: MembroEquipe) {
    if (!window.confirm(`Remover ${m.nome} da equipe?`)) return;
    removerMembroMutation.mutate(m.id, {
      onError: (err) => alert(getErrorMessage(err)),
    });
  }

  if (isLoading) {
    return <div className="card text-center py-12 text-slate-500">Carregando...</div>;
  }

  if (!equipe) {
    return (
      <div className="card text-center py-12">
        <p className="text-slate-700 mb-4">Equipe não encontrada.</p>
        <Link to="/app/equipes" className="btn-primary">
          Voltar
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={() => navigate("/app/equipes")}
        className="text-sm text-slate-600 hover:text-slate-900 flex items-center gap-1"
      >
        <ArrowLeft size={14} /> Voltar para Equipes
      </button>

      <header className="card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <HeartPulse size={22} className="text-rose-600" />
              {equipe.nome}
            </h1>
            <p className="text-sm text-slate-500 mt-1 flex items-center gap-3 flex-wrap">
              <span className="inline-flex items-center gap-1">
                <Building2 size={13} />
                {equipe.cliente.nome}
              </span>
              <span>•</span>
              <span>{equipe.categoria}</span>
              <span>•</span>
              <span className="font-medium text-slate-700">
                {formatBRL(equipe.valor_hora_centavos)} / hora
              </span>
              <span>•</span>
              <span>
                {equipe.qtd_membros_ativos} membro(s) ativo(s)
                {equipe.qtd_membros !== equipe.qtd_membros_ativos &&
                  ` / ${equipe.qtd_membros}`}
              </span>
            </p>
            {equipe.observacoes && (
              <p className="text-xs text-slate-500 mt-2 italic">
                {equipe.observacoes}
              </p>
            )}
          </div>
          <button
            type="button"
            className="btn-primary whitespace-nowrap"
            onClick={() => setShowFechamento(true)}
            disabled={equipe.qtd_membros_ativos === 0}
            title={
              equipe.qtd_membros_ativos === 0
                ? "Adicione pelo menos 1 membro ativo"
                : undefined
            }
          >
            <Calculator size={16} />
            Fechar mês
          </button>
        </div>
      </header>

      {/* Membros */}
      <section>
        <div className="flex items-end justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-1.5">
              <Users size={18} />
              Membros
            </h2>
            <p className="text-xs text-slate-500">
              No fechamento mensal, o líquido é dividido em partes iguais
              entre os ativos.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => {
              setEditandoMembro(null);
              setShowMembroModal(true);
            }}
          >
            <UserPlus size={14} />
            Adicionar
          </button>
        </div>

        {equipe.membros.length === 0 ? (
          <div className="card text-center py-8 border-dashed">
            <Users size={28} className="mx-auto text-slate-300 mb-2" />
            <p className="text-sm text-slate-700 mb-1">
              Nenhum membro cadastrado
            </p>
            <p className="text-xs text-slate-500 mb-4">
              Adicione os médicos / profissionais que vão dividir o pagamento.
            </p>
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setEditandoMembro(null);
                setShowMembroModal(true);
              }}
            >
              <Plus size={16} /> Adicionar primeiro membro
            </button>
          </div>
        ) : (
          <div className="card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Nome</th>
                  <th className="px-4 py-2.5">CPF</th>
                  <th className="px-4 py-2.5">CRM/Reg.</th>
                  <th className="px-4 py-2.5">Pagamento</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 w-24"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {equipe.membros.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-50/60 transition">
                    <td className="px-4 py-2.5 font-medium text-slate-900">
                      {m.nome}
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 tabular-nums">
                      {formatarCPF(m.cpf)}
                    </td>
                    <td className="px-4 py-2.5 text-slate-700">
                      {m.crm_ou_registro || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 text-xs">
                      {m.chave_pix
                        ? `PIX: ${m.chave_pix}`
                        : m.banco_codigo
                        ? `${m.banco_codigo} • Ag ${m.agencia} • C/C ${m.conta}`
                        : "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      {m.ativo ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700">
                          Ativo
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600">
                          Inativo
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            setEditandoMembro(m);
                            setShowMembroModal(true);
                          }}
                          title="Editar"
                          className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition"
                        >
                          <Edit3 size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => confirmarRemocaoMembro(m)}
                          title="Remover"
                          className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600 transition"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Fechamentos */}
      <section>
        <h2 className="text-lg font-semibold text-slate-900 mb-3 flex items-center gap-1.5">
          <Calculator size={18} />
          Histórico de fechamentos
        </h2>
        {fechamentos.length === 0 ? (
          <div className="card text-center py-6 border-dashed text-sm text-slate-500">
            Nenhum fechamento ainda. Use "Fechar mês" no topo da página.
          </div>
        ) : (
          <div className="card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Competência</th>
                  <th className="px-4 py-2.5 text-right">Horas</th>
                  <th className="px-4 py-2.5 text-right">Bruto</th>
                  <th className="px-4 py-2.5 text-right">Líquido</th>
                  <th className="px-4 py-2.5 text-right">Por médico</th>
                  <th className="px-4 py-2.5">Lote</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fechamentos.map((f) => (
                  <tr key={f.id ?? f.competencia} className="hover:bg-slate-50/60">
                    <td className="px-4 py-2.5 font-medium">
                      {formatarCompetencia(f.competencia)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {f.horas_total}h
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatBRL(f.valor_bruto_centavos)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {formatBRL(f.valor_liquido_centavos)}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-emerald-700">
                      {formatBRL(f.valor_por_membro_centavos)}
                      <div className="text-[10px] font-normal text-slate-500">
                        ÷ {f.qtd_membros}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {f.lote_id ? (
                        <Link
                          to={`/app/lotes/${f.lote_id}`}
                          className="text-brand-700 hover:underline text-xs"
                        >
                          ver lote →
                        </Link>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showMembroModal && (
        <MembroModal
          equipeId={equipe.id}
          membro={editandoMembro}
          onClose={() => {
            setShowMembroModal(false);
            setEditandoMembro(null);
          }}
          onSaved={() => {
            void queryClient.invalidateQueries({ queryKey: ["equipes", id] });
            setShowMembroModal(false);
            setEditandoMembro(null);
          }}
        />
      )}

      {showFechamento && (
        <FechamentoModal
          equipe={equipe}
          onClose={() => setShowFechamento(false)}
          onConfirmed={() => {
            void queryClient.invalidateQueries({ queryKey: ["equipes", id] });
            void queryClient.invalidateQueries({
              queryKey: ["equipes", id, "fechamentos"],
            });
            setShowFechamento(false);
          }}
        />
      )}
    </div>
  );
}

// ============================================================
// Helpers
// ============================================================

function formatarCPF(cpf: string): string {
  const digitos = cpf.replace(/\D/g, "");
  if (digitos.length !== 11) return cpf;
  return digitos.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
}

const MESES_PT = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

function formatarCompetencia(c: string): string {
  const [ano, mes] = c.split("-");
  const idx = parseInt(mes, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_PT[idx]}/${ano}` : c;
}

// ============================================================
// Modal de membro
// ============================================================

interface MembroModalProps {
  equipeId: string;
  membro: MembroEquipe | null;
  onClose: () => void;
  onSaved: () => void;
}

function MembroModal({ equipeId, membro, onClose, onSaved }: MembroModalProps) {
  const [nome, setNome] = useState(membro?.nome ?? "");
  const [cpf, setCpf] = useState(membro?.cpf ? formatarCPF(membro.cpf) : "");
  const [crm, setCrm] = useState(membro?.crm_ou_registro ?? "");
  const [pix, setPix] = useState(membro?.chave_pix ?? "");
  const [banco, setBanco] = useState(membro?.banco_codigo ?? "");
  const [agencia, setAgencia] = useState(membro?.agencia ?? "");
  const [conta, setConta] = useState(membro?.conta ?? "");
  const [ativo, setAtivo] = useState(membro?.ativo ?? true);
  const [error, setError] = useState<string | null>(null);

  const salvar = useMutation({
    mutationFn: async () => {
      const cpfDigitos = cpf.replace(/\D/g, "");
      if (cpfDigitos.length !== 11)
        throw new Error("CPF deve ter 11 dígitos");
      if (!nome.trim()) throw new Error("Nome é obrigatório");

      const payload: MembroEquipePayload = {
        nome: nome.trim(),
        cpf: cpfDigitos,
        crm_ou_registro: crm.trim() || null,
        chave_pix: pix.trim() || null,
        banco_codigo: banco.trim() || null,
        agencia: agencia.trim() || null,
        conta: conta.trim() || null,
        ativo,
      };

      if (membro) {
        await api.put(
          `/api/equipes/${equipeId}/membros/${membro.id}`,
          payload,
        );
      } else {
        await api.post(`/api/equipes/${equipeId}/membros`, payload);
      }
    },
    onSuccess: onSaved,
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold">
            {membro ? "Editar membro" : "Adicionar membro"}
          </h2>
        </div>

        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nome
            </label>
            <input
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className="input"
              placeholder="Dr. João da Silva"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                CPF
              </label>
              <input
                type="text"
                value={cpf}
                onChange={(e) => setCpf(e.target.value)}
                className="input tabular-nums"
                placeholder="000.000.000-00"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                CRM / Registro
              </label>
              <input
                type="text"
                value={crm}
                onChange={(e) => setCrm(e.target.value)}
                className="input"
                placeholder="CRM 12345-RJ"
              />
            </div>
          </div>

          <div className="border-t border-slate-200 pt-4">
            <p className="text-sm font-medium text-slate-700 mb-2">
              Pagamento — preencha PIX OU dados bancários
            </p>
            <div>
              <label className="block text-xs text-slate-600 mb-1">
                Chave PIX
              </label>
              <input
                type="text"
                value={pix}
                onChange={(e) => setPix(e.target.value)}
                className="input"
                placeholder="CPF, email ou telefone"
              />
            </div>
            <div className="grid grid-cols-3 gap-2 mt-3">
              <div>
                <label className="block text-xs text-slate-600 mb-1">
                  Banco
                </label>
                <input
                  type="text"
                  value={banco}
                  onChange={(e) => setBanco(e.target.value)}
                  className="input tabular-nums"
                  placeholder="341"
                  maxLength={3}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-600 mb-1">
                  Agência
                </label>
                <input
                  type="text"
                  value={agencia}
                  onChange={(e) => setAgencia(e.target.value)}
                  className="input tabular-nums"
                  placeholder="1234"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-600 mb-1">
                  Conta
                </label>
                <input
                  type="text"
                  value={conta}
                  onChange={(e) => setConta(e.target.value)}
                  className="input tabular-nums"
                  placeholder="12345-6"
                />
              </div>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={ativo}
              onChange={(e) => setAtivo(e.target.checked)}
            />
            Membro ativo (entra na próxima divisão)
          </label>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={salvar.isPending}
            className="btn-ghost"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              salvar.mutate();
            }}
            disabled={salvar.isPending}
            className="btn-primary"
          >
            {salvar.isPending ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Salvando...
              </>
            ) : (
              "Salvar"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Modal de fechamento mensal
// ============================================================

interface FechamentoModalProps {
  equipe: EquipeFlex;
  onClose: () => void;
  onConfirmed: () => void;
}

function FechamentoModal({
  equipe,
  onClose,
  onConfirmed,
}: FechamentoModalProps) {
  const navigate = useNavigate();
  const hoje = new Date();
  const competenciaDefault = `${hoje.getFullYear()}-${String(
    hoje.getMonth() + 1,
  ).padStart(2, "0")}`;

  const [competencia, setCompetencia] = useState(competenciaDefault);
  const [horas, setHoras] = useState("");
  const [obs, setObs] = useState("");
  const [preview, setPreview] = useState<FechamentoEquipe | null>(null);
  const [error, setError] = useState<string | null>(null);

  const horasNum = parseInt(horas, 10);

  const calcular = useMutation({
    mutationFn: async () => {
      if (!Number.isFinite(horasNum) || horasNum <= 0)
        throw new Error("Informe um total de horas válido");
      const payload: FechamentoEquipePayload = {
        equipe_id: equipe.id,
        competencia,
        horas_total: horasNum,
        origem: "DIGITACAO",
        confirmar: false,
        observacoes: obs.trim() || null,
      };
      const { data } = await api.post<FechamentoEquipe>(
        "/api/equipes/fechamento",
        payload,
      );
      return data;
    },
    onSuccess: setPreview,
    onError: (err) => setError(getErrorMessage(err)),
  });

  const confirmar = useMutation({
    mutationFn: async () => {
      const payload: FechamentoEquipePayload = {
        equipe_id: equipe.id,
        competencia,
        horas_total: horasNum,
        origem: "DIGITACAO",
        confirmar: true,
        observacoes: obs.trim() || null,
      };
      const { data } = await api.post<FechamentoEquipe>(
        "/api/equipes/fechamento",
        payload,
      );
      return data;
    },
    onSuccess: (data) => {
      onConfirmed();
      if (data.lote_id) {
        navigate(`/app/lotes/${data.lote_id}`);
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-xl">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calculator size={18} />
            Fechar mês — {equipe.nome}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Digite o total de horas que a equipe trabalhou no mês. O sistema
            divide o valor líquido em partes iguais entre os{" "}
            <strong>{equipe.qtd_membros_ativos} membro(s) ativo(s)</strong>.
          </p>
        </div>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Competência
              </label>
              <input
                type="month"
                value={competencia}
                onChange={(e) => {
                  setCompetencia(e.target.value);
                  setPreview(null);
                }}
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Total de horas
              </label>
              <input
                type="number"
                value={horas}
                onChange={(e) => {
                  setHoras(e.target.value);
                  setPreview(null);
                }}
                className="input text-right tabular-nums"
                placeholder="720"
                min={1}
                max={10000}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Observação (opcional)
            </label>
            <input
              type="text"
              value={obs}
              onChange={(e) => setObs(e.target.value)}
              className="input"
              placeholder="Ex.: 'fechamento parcial', 'incluindo plantão extra'..."
            />
          </div>

          <button
            type="button"
            onClick={() => {
              setError(null);
              calcular.mutate();
            }}
            disabled={!horas || calcular.isPending}
            className="btn-secondary w-full"
          >
            {calcular.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Calculando...
              </>
            ) : (
              <>
                <Calculator size={14} />
                {preview ? "Recalcular" : "Calcular preview"}
              </>
            )}
          </button>

          {preview && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 space-y-2">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Linha label="Horas totais" valor={`${preview.horas_total}h`} />
                <Linha
                  label="Valor / hora"
                  valor={formatBRL(preview.valor_hora_centavos)}
                />
                <Linha
                  label="Valor bruto"
                  valor={formatBRL(preview.valor_bruto_centavos)}
                  destaque
                />
                <Linha
                  label="Desconto MedPag"
                  valor={
                    preview.desconto_medpag_centavos > 0
                      ? `− ${formatBRL(preview.desconto_medpag_centavos)}`
                      : "—"
                  }
                />
                <Linha
                  label="Líquido"
                  valor={formatBRL(preview.valor_liquido_centavos)}
                  destaque
                />
                <Linha
                  label="Membros ativos"
                  valor={String(preview.qtd_membros)}
                />
              </div>
              <div className="border-t border-emerald-300 pt-3 mt-3">
                <div className="text-xs uppercase font-semibold text-emerald-700 tracking-wide">
                  Cada médico vai receber
                </div>
                <div className="text-3xl font-bold text-emerald-700 tabular-nums mt-0.5">
                  {formatBRL(preview.valor_por_membro_centavos)}
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={confirmar.isPending}
            className="btn-ghost"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              confirmar.mutate();
            }}
            disabled={!preview || confirmar.isPending}
            className="btn-primary"
          >
            {confirmar.isPending ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Confirmando...
              </>
            ) : (
              <>
                <CheckCircle2 size={16} />
                Confirmar e gerar lote
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function Linha({
  label,
  valor,
  destaque,
}: {
  label: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`tabular-nums ${
          destaque ? "text-base font-semibold text-slate-900" : "text-sm"
        }`}
      >
        {valor}
      </div>
    </div>
  );
}
