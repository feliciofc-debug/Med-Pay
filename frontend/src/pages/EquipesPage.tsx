/**
 * Equipes Médicas (`/app/equipes`).
 *
 * Lista das equipes flex (banco de horas compartilhado) cadastradas.
 * Cada equipe pertence a um hospital, tem uma categoria, um valor/hora
 * e uma lista de membros que vão dividir igualmente o líquido no
 * fechamento mensal.
 *
 * Caso real: Hospital do Cérebro tem 10 plantonistas que dividem o
 * total de horas trabalhadas em partes iguais.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Edit3,
  HeartPulse,
  Loader2,
  Plus,
  Trash2,
  Users,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatBRL } from "@/lib/utils";
import type { Cliente, EquipeFlex, EquipePayload } from "@/types";

const CATEGORIAS_SUGERIDAS = [
  "Plantonista",
  "Cirurgião",
  "Anestesista",
  "Enfermeiro",
  "Clínico Geral",
  "UTI",
  "Pronto Socorro",
];

export function EquipesPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editando, setEditando] = useState<EquipeFlex | null>(null);

  const { data: equipes = [], isLoading } = useQuery({
    queryKey: ["equipes"],
    queryFn: async () => {
      const { data } = await api.get<EquipeFlex[]>("/api/equipes");
      return data;
    },
  });

  const removerMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/equipes/${id}`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["equipes"] });
    },
  });

  function confirmarRemocao(eq: EquipeFlex) {
    if (
      !window.confirm(
        `Remover a equipe "${eq.nome}"? Todos os membros e fechamentos serão apagados em cascata.`,
      )
    ) {
      return;
    }
    removerMutation.mutate(eq.id, {
      onError: (err) => alert(getErrorMessage(err)),
    });
  }

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 mb-1 flex items-center gap-2">
            <HeartPulse size={22} className="text-rose-600" />
            Equipes Médicas
          </h1>
          <p className="text-sm text-slate-500 max-w-2xl">
            Equipes flex que compartilham banco de horas. No fechamento
            mensal, o total trabalhado pela equipe é dividido em partes
            iguais entre os membros ativos. Os médicos resolvem internamente
            quem trabalhou mais ou menos.
          </p>
        </div>
        <button
          type="button"
          className="btn-primary whitespace-nowrap"
          onClick={() => {
            setEditando(null);
            setShowModal(true);
          }}
        >
          <Plus size={16} />
          Nova equipe
        </button>
      </header>

      {showModal && (
        <EquipeModal
          equipe={editando}
          onClose={() => {
            setShowModal(false);
            setEditando(null);
          }}
          onSaved={() => {
            void queryClient.invalidateQueries({ queryKey: ["equipes"] });
            setShowModal(false);
            setEditando(null);
          }}
        />
      )}

      {isLoading ? (
        <div className="card text-center text-slate-500 py-8">Carregando...</div>
      ) : equipes.length === 0 ? (
        <div className="card text-center py-12 border-dashed">
          <Users size={36} className="mx-auto text-slate-300 mb-3" />
          <p className="text-slate-700 font-medium mb-1">
            Nenhuma equipe cadastrada ainda
          </p>
          <p className="text-sm text-slate-500 mb-4 max-w-md mx-auto">
            Cadastre a primeira equipe — depois adicione os médicos e, ao
            final do mês, faça o fechamento com as horas trabalhadas.
          </p>
          <button
            type="button"
            onClick={() => {
              setEditando(null);
              setShowModal(true);
            }}
            className="btn-primary"
          >
            <Plus size={16} />
            Criar primeira equipe
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Equipe</th>
                <th className="px-4 py-3">Hospital</th>
                <th className="px-4 py-3">Categoria</th>
                <th className="px-4 py-3 text-right">Valor / hora</th>
                <th className="px-4 py-3 text-right">Membros</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 w-28"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {equipes.map((eq) => (
                <tr key={eq.id} className="hover:bg-slate-50/60 transition">
                  <td className="px-4 py-3 font-medium text-slate-900">
                    <Link
                      to={`/app/equipes/${eq.id}`}
                      className="text-brand-700 hover:text-brand-900"
                    >
                      {eq.nome}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    <span className="inline-flex items-center gap-1.5">
                      <Building2 size={13} className="text-slate-400" />
                      {eq.cliente.nome}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{eq.categoria}</td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">
                    {formatBRL(eq.valor_hora_centavos)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {eq.qtd_membros_ativos}
                    {eq.qtd_membros !== eq.qtd_membros_ativos && (
                      <span className="text-slate-400 text-xs">
                        {" "}
                        / {eq.qtd_membros}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {eq.ativa ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700">
                        Ativa
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600">
                        Inativa
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => {
                          setEditando(eq);
                          setShowModal(true);
                        }}
                        title="Editar"
                        className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => confirmarRemocao(eq)}
                        title="Remover"
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600 transition"
                        disabled={removerMutation.isPending}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
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
// Modal de criação/edição
// ============================================================

interface EquipeModalProps {
  equipe: EquipeFlex | null;
  onClose: () => void;
  onSaved: () => void;
}

function EquipeModal({ equipe, onClose, onSaved }: EquipeModalProps) {
  const [clienteId, setClienteId] = useState(equipe?.cliente.id ?? "");
  const [nome, setNome] = useState(equipe?.nome ?? "");
  const [categoria, setCategoria] = useState(equipe?.categoria ?? "Plantonista");
  const [valorHoraReais, setValorHoraReais] = useState(
    equipe ? (equipe.valor_hora_centavos / 100).toFixed(2).replace(".", ",") : "",
  );
  const [ativa, setAtiva] = useState(equipe?.ativa ?? true);
  const [obs, setObs] = useState(equipe?.observacoes ?? "");
  const [error, setError] = useState<string | null>(null);

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: Cliente[] }>("/api/clientes/");
      return data.clientes;
    },
  });

  const valorCentavos = useMemo(() => {
    const limpo = valorHoraReais.replace(/\./g, "").replace(",", ".");
    const num = parseFloat(limpo);
    return Number.isFinite(num) && num >= 0 ? Math.round(num * 100) : 0;
  }, [valorHoraReais]);

  const salvar = useMutation({
    mutationFn: async () => {
      if (!clienteId) throw new Error("Selecione o hospital");
      if (!nome.trim()) throw new Error("Nome da equipe obrigatório");
      if (valorCentavos <= 0)
        throw new Error("Valor/hora deve ser maior que zero");

      const payload: EquipePayload = {
        cliente_id: clienteId,
        nome: nome.trim(),
        categoria: categoria.trim(),
        valor_hora_centavos: valorCentavos,
        ativa,
        observacoes: obs.trim() || null,
      };
      if (equipe) {
        await api.put(`/api/equipes/${equipe.id}`, payload);
      } else {
        await api.post("/api/equipes", payload);
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
            {equipe ? "Editar equipe" : "Nova equipe"}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Os membros ficam na tela de detalhe da equipe — cadastre primeiro
            o cabeçalho.
          </p>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Hospital
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
              Nome da equipe
            </label>
            <input
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              className="input"
              placeholder="Ex.: Plantonistas UTI, Equipe Cirurgia"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Categoria
              </label>
              <select
                value={categoria}
                onChange={(e) => setCategoria(e.target.value)}
                className="input"
              >
                {CATEGORIAS_SUGERIDAS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Valor / hora (R$)
              </label>
              <input
                type="text"
                value={valorHoraReais}
                onChange={(e) => setValorHoraReais(e.target.value)}
                className="input text-right tabular-nums"
                placeholder="150,00"
                inputMode="decimal"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Observações (opcional)
            </label>
            <textarea
              value={obs}
              onChange={(e) => setObs(e.target.value)}
              className="input min-h-[60px]"
              placeholder="Anotações internas — ex.: 'pagamento via Itaú', 'fechamento até dia 5'..."
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={ativa}
              onChange={(e) => setAtiva(e.target.checked)}
            />
            Equipe ativa
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
                <Loader2 size={16} className="animate-spin" />
                Salvando...
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
