/**
 * Gestão de Planos e Features por Cliente.
 *
 * Admin pode:
 *  - Ver os 4 planos comerciais cadastrados
 *  - Listar todos os clientes com plano + status atual
 *  - Trocar o plano de um cliente (com opção de iniciar trial)
 *  - Editar overrides de feature (liga/desliga features pontualmente)
 *  - Mudar status da assinatura manualmente (suspender, reativar, etc)
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Cog,
  CreditCard,
  Layers,
  Package,
  Save,
  Sparkles,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type {
  ClienteAssinatura,
  FeatureDef,
  Plano,
  StatusAssinatura,
} from "@/types";

interface ClienteListItem {
  id: string;
  nome: string;
  cnpj: string | null;
  ativo: boolean;
}

const STATUS_LABEL: Record<StatusAssinatura, string> = {
  TRIAL: "Em Trial",
  ATIVO: "Ativo",
  INADIMPLENTE: "Inadimplente",
  SUSPENSO: "Suspenso",
  CANCELADO: "Cancelado",
};

const STATUS_COLOR: Record<StatusAssinatura, string> = {
  TRIAL: "bg-blue-100 text-blue-800 border-blue-300",
  ATIVO: "bg-emerald-100 text-emerald-800 border-emerald-300",
  INADIMPLENTE: "bg-amber-100 text-amber-800 border-amber-300",
  SUSPENSO: "bg-red-100 text-red-800 border-red-300",
  CANCELADO: "bg-slate-100 text-slate-700 border-slate-300",
};

function formatBRL(centavos: number): string {
  if (centavos === 0) return "Sob demanda";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(centavos / 100);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

export function AdminPlanosPage() {
  const queryClient = useQueryClient();
  const [clienteEditando, setClienteEditando] =
    useState<ClienteListItem | null>(null);
  const [aba, setAba] = useState<"features" | "plano" | "status">("features");
  const [feedback, setFeedback] = useState<
    { tipo: "sucesso" | "erro"; mensagem: string } | null
  >(null);

  // --------- Catálogo ---------
  const { data: catalogo = [] } = useQuery({
    queryKey: ["planos", "catalogo"],
    queryFn: async () => {
      const { data } = await api.get<FeatureDef[]>(
        "/api/planos/features-catalogo",
      );
      return data;
    },
  });

  const catalogoAgrupado = useMemo(() => {
    const map = new Map<string, FeatureDef[]>();
    for (const f of catalogo) {
      const lista = map.get(f.categoria) ?? [];
      lista.push(f);
      map.set(f.categoria, lista);
    }
    return Array.from(map.entries());
  }, [catalogo]);

  // --------- Planos ---------
  const { data: planos = [] } = useQuery({
    queryKey: ["planos", "todos"],
    queryFn: async () => {
      const { data } = await api.get<Plano[]>("/api/planos");
      return data;
    },
  });

  // --------- Clientes ---------
  const { data: clientesResp } = useQuery({
    queryKey: ["clientes", "listar"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: ClienteListItem[] }>(
        "/api/clientes",
      );
      return data;
    },
  });
  const clientes = clientesResp?.clientes ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
          <Layers className="text-brand-600" size={26} />
          Planos &amp; Features
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          A matriz da plataforma. Cada cliente assina um plano com features
          padrão e pode ter ajustes pontuais (overrides).
        </p>
      </header>

      {feedback && (
        <div
          className={`card p-4 flex items-start gap-3 ${
            feedback.tipo === "sucesso"
              ? "bg-emerald-50 border-emerald-200"
              : "bg-red-50 border-red-200"
          }`}
        >
          {feedback.tipo === "sucesso" ? (
            <CheckCircle2 className="text-emerald-600 shrink-0" size={20} />
          ) : (
            <AlertCircle className="text-red-600 shrink-0" size={20} />
          )}
          <p className="text-sm">{feedback.mensagem}</p>
          <button
            type="button"
            className="ml-auto text-slate-400 hover:text-slate-600"
            onClick={() => setFeedback(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* ============ Planos ============ */}
      <section>
        <h2 className="text-base font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Package size={18} />
          Planos disponíveis
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {planos.map((p) => (
            <article key={p.id} className="card p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-900">{p.nome}</h3>
                {p.publico ? (
                  <span className="text-[10px] uppercase tracking-wider bg-brand-50 text-brand-700 px-1.5 py-0.5 rounded">
                    Self-service
                  </span>
                ) : (
                  <span className="text-[10px] uppercase tracking-wider bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
                    Contratual
                  </span>
                )}
              </div>
              <p className="text-2xl font-bold text-slate-900">
                {formatBRL(p.preco_mensal_centavos)}
                {p.preco_mensal_centavos > 0 && (
                  <span className="text-xs font-normal text-slate-500">
                    {" "}
                    /mês
                  </span>
                )}
              </p>
              {p.trial_dias > 0 && (
                <p className="text-xs text-blue-700 flex items-center gap-1">
                  <Sparkles size={12} />
                  {p.trial_dias} dias de trial gratuito
                </p>
              )}
              <p className="text-xs text-slate-500 leading-snug">
                {p.descricao}
              </p>
              <div className="mt-2 text-xs text-slate-600">
                <p>
                  <strong>{contarFeaturesBool(p.features)}</strong> features
                  ligadas
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ============ Clientes ============ */}
      <section>
        <h2 className="text-base font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Cog size={18} />
          Configuração por cliente
        </h2>
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3">Cliente</th>
                <th className="px-6 py-3">CNPJ</th>
                <th className="px-6 py-3">Plano</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {clientes.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-6 py-8 text-center text-slate-500"
                  >
                    Nenhum cliente cadastrado ainda.
                  </td>
                </tr>
              )}
              {clientes.map((c) => (
                <LinhaCliente
                  key={c.id}
                  cliente={c}
                  onEditar={(aba_) => {
                    setClienteEditando(c);
                    setAba(aba_);
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {clienteEditando && (
        <ModalEdicaoCliente
          cliente={clienteEditando}
          aba={aba}
          setAba={setAba}
          catalogo={catalogo}
          catalogoAgrupado={catalogoAgrupado}
          planos={planos}
          onClose={() => setClienteEditando(null)}
          onSuccess={(msg) => {
            setFeedback({ tipo: "sucesso", mensagem: msg });
            void queryClient.invalidateQueries({
              queryKey: ["planos", "cliente", clienteEditando.id],
            });
          }}
          onError={(msg) =>
            setFeedback({ tipo: "erro", mensagem: msg })
          }
        />
      )}
    </div>
  );
}

// ============================================================
// Linha de cliente — busca assinatura sob demanda
// ============================================================

function LinhaCliente({
  cliente,
  onEditar,
}: {
  cliente: ClienteListItem;
  onEditar: (aba: "features" | "plano" | "status") => void;
}) {
  const { data: assinatura } = useQuery({
    queryKey: ["planos", "cliente", cliente.id],
    queryFn: async () => {
      const { data } = await api.get<ClienteAssinatura>(
        `/api/planos/clientes/${cliente.id}`,
      );
      return data;
    },
  });

  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="px-6 py-3 font-medium text-slate-900">{cliente.nome}</td>
      <td className="px-6 py-3 text-slate-500 text-xs">
        {cliente.cnpj ?? "—"}
      </td>
      <td className="px-6 py-3">
        {assinatura?.plano ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border bg-brand-50 text-brand-800 border-brand-200">
            <Package size={11} /> {assinatura.plano.nome}
          </span>
        ) : (
          <span className="text-xs text-slate-400 italic">sem plano</span>
        )}
      </td>
      <td className="px-6 py-3">
        {assinatura && (
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${
                STATUS_COLOR[assinatura.status_assinatura]
              }`}
            >
              {STATUS_LABEL[assinatura.status_assinatura]}
            </span>
            {assinatura.trial_termina_em && (
              <span className="text-[11px] text-slate-500">
                até {formatDate(assinatura.trial_termina_em)}
              </span>
            )}
          </div>
        )}
      </td>
      <td className="px-6 py-3 text-right">
        <div className="flex justify-end gap-1">
          <button
            type="button"
            onClick={() => onEditar("features")}
            className="btn-secondary text-xs px-2 py-1"
            title="Editar features"
          >
            <Cog size={13} /> Features
          </button>
          <button
            type="button"
            onClick={() => onEditar("plano")}
            className="btn-secondary text-xs px-2 py-1"
            title="Trocar plano"
          >
            <Package size={13} /> Plano
          </button>
          <button
            type="button"
            onClick={() => onEditar("status")}
            className="btn-secondary text-xs px-2 py-1"
            title="Mudar status"
          >
            <CreditCard size={13} /> Status
          </button>
        </div>
      </td>
    </tr>
  );
}

// ============================================================
// Modal de edição
// ============================================================

function ModalEdicaoCliente({
  cliente,
  aba,
  setAba,
  catalogo,
  catalogoAgrupado,
  planos,
  onClose,
  onSuccess,
  onError,
}: {
  cliente: ClienteListItem;
  aba: "features" | "plano" | "status";
  setAba: (a: "features" | "plano" | "status") => void;
  catalogo: FeatureDef[];
  catalogoAgrupado: Array<[string, FeatureDef[]]>;
  planos: Plano[];
  onClose: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const queryClient = useQueryClient();

  const { data: assinatura, isLoading } = useQuery({
    queryKey: ["planos", "cliente", cliente.id, "edicao"],
    queryFn: async () => {
      const { data } = await api.get<ClienteAssinatura>(
        `/api/planos/clientes/${cliente.id}`,
      );
      return data;
    },
  });

  const invalidar = () => {
    void queryClient.invalidateQueries({
      queryKey: ["planos", "cliente", cliente.id],
    });
    void queryClient.invalidateQueries({
      queryKey: ["planos", "cliente", cliente.id, "edicao"],
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-start justify-center overflow-y-auto p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mt-8">
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="font-semibold text-slate-900">{cliente.nome}</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Plano atual:{" "}
              {assinatura?.plano?.nome ?? (
                <span className="italic text-slate-400">sem plano</span>
              )}
            </p>
          </div>
          <button
            type="button"
            className="text-slate-400 hover:text-slate-700"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>

        <nav className="border-b border-slate-200 px-6 flex gap-1">
          {(
            [
              ["features", "Features"],
              ["plano", "Trocar Plano"],
              ["status", "Status / Trial"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setAba(k)}
              className={`px-3 py-2.5 text-sm font-medium border-b-2 -mb-px ${
                aba === k
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="p-6">
          {isLoading || !assinatura ? (
            <p className="text-sm text-slate-500">Carregando...</p>
          ) : aba === "features" ? (
            <AbaFeatures
              assinatura={assinatura}
              catalogo={catalogo}
              catalogoAgrupado={catalogoAgrupado}
              onSuccess={(msg) => {
                onSuccess(msg);
                invalidar();
              }}
              onError={onError}
            />
          ) : aba === "plano" ? (
            <AbaPlano
              assinatura={assinatura}
              planos={planos}
              onSuccess={(msg) => {
                onSuccess(msg);
                invalidar();
              }}
              onError={onError}
            />
          ) : (
            <AbaStatus
              assinatura={assinatura}
              onSuccess={(msg) => {
                onSuccess(msg);
                invalidar();
              }}
              onError={onError}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Aba: Features
// ============================================================

function AbaFeatures({
  assinatura,
  catalogo,
  catalogoAgrupado,
  onSuccess,
  onError,
}: {
  assinatura: ClienteAssinatura;
  catalogo: FeatureDef[];
  catalogoAgrupado: Array<[string, FeatureDef[]]>;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  // Estado local = overrides editáveis
  const [overrides, setOverrides] = useState<Record<string, boolean | number | null>>(
    () => ({ ...assinatura.features_override }),
  );

  const valorEfetivo = (chave: string): boolean | number | null => {
    if (chave in overrides) return overrides[chave];
    return assinatura.features_efetivas[chave] ?? null;
  };

  const isOverride = (chave: string): boolean => chave in overrides;

  const toggleBool = (chave: string) => {
    const atual = valorEfetivo(chave);
    setOverrides((prev) => ({ ...prev, [chave]: !atual }));
  };

  const setInt = (chave: string, valor: string) => {
    if (valor === "") {
      setOverrides((prev) => ({ ...prev, [chave]: null }));
      return;
    }
    const n = Number(valor);
    setOverrides((prev) => ({ ...prev, [chave]: Number.isFinite(n) ? n : null }));
  };

  const removerOverride = (chave: string) => {
    setOverrides((prev) => {
      const novo = { ...prev };
      delete novo[chave];
      return novo;
    });
  };

  const salvar = useMutation({
    mutationFn: async () => {
      const { data } = await api.put<ClienteAssinatura>(
        `/api/planos/clientes/${assinatura.id}/features`,
        { features_override: overrides },
      );
      return data;
    },
    onSuccess: () => {
      onSuccess("Features atualizadas com sucesso.");
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const limparTodos = () => setOverrides({});

  return (
    <div className="space-y-5">
      <div className="bg-blue-50 border border-blue-200 rounded-md p-3 text-xs text-blue-900">
        Esta tela mostra o valor <strong>efetivo</strong> de cada feature
        (plano + override). Linhas em <strong>destaque</strong> têm override
        ativo e vencem o que vem do plano. Para voltar uma feature ao padrão
        do plano, clique no <em>X</em> ao lado dela.
      </div>

      {catalogoAgrupado.map(([categoria, lista]) => (
        <section key={categoria}>
          <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-2">
            {categoria}
          </h3>
          <div className="space-y-1">
            {lista.map((f) => {
              const valor = valorEfetivo(f.chave);
              const override = isOverride(f.chave);
              return (
                <div
                  key={f.chave}
                  className={`flex items-center gap-3 px-3 py-2 rounded-md border ${
                    override
                      ? "bg-amber-50 border-amber-200"
                      : "border-transparent hover:bg-slate-50"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800">
                      {f.nome}
                    </p>
                    <p className="text-xs text-slate-500 leading-snug">
                      {f.descricao}
                    </p>
                  </div>

                  {f.tipo === "bool" ? (
                    <button
                      type="button"
                      role="switch"
                      aria-checked={Boolean(valor)}
                      onClick={() => toggleBool(f.chave)}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${
                        valor ? "bg-emerald-500" : "bg-slate-300"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 mt-0.5 ${
                          valor ? "translate-x-5" : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  ) : (
                    <input
                      type="number"
                      min={0}
                      value={
                        valor === null || valor === undefined
                          ? ""
                          : String(valor)
                      }
                      placeholder="ilimitado"
                      onChange={(e) => setInt(f.chave, e.target.value)}
                      className="input w-32 text-sm"
                    />
                  )}

                  {override && (
                    <button
                      type="button"
                      onClick={() => removerOverride(f.chave)}
                      className="text-amber-700 hover:text-amber-900"
                      title="Remover override (volta ao padrão do plano)"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      ))}

      <footer className="flex items-center justify-between pt-4 border-t border-slate-200">
        <button
          type="button"
          onClick={limparTodos}
          className="text-sm text-slate-500 hover:text-slate-800"
        >
          Limpar todos os overrides
        </button>
        <button
          type="button"
          onClick={() => salvar.mutate()}
          disabled={salvar.isPending}
          className="btn-primary"
        >
          <Save size={15} className="mr-1" />
          {salvar.isPending ? "Salvando..." : "Salvar overrides"}
        </button>
      </footer>

      {catalogo.length === 0 && (
        <p className="text-sm text-slate-500">Carregando catálogo...</p>
      )}
    </div>
  );
}

// ============================================================
// Aba: Trocar Plano
// ============================================================

function AbaPlano({
  assinatura,
  planos,
  onSuccess,
  onError,
}: {
  assinatura: ClienteAssinatura;
  planos: Plano[];
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [planoId, setPlanoId] = useState<string>(assinatura.plano?.id ?? "");
  const [iniciarTrial, setIniciarTrial] = useState(false);

  const planoSelecionado = planos.find((p) => p.id === planoId);

  const trocar = useMutation({
    mutationFn: async () => {
      const { data } = await api.put<ClienteAssinatura>(
        `/api/planos/clientes/${assinatura.id}/plano`,
        {
          plano_id: planoId || null,
          iniciar_trial: iniciarTrial,
        },
      );
      return data;
    },
    onSuccess: () => onSuccess("Plano atualizado."),
    onError: (err) => onError(getErrorMessage(err)),
  });

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Plano
        </label>
        <select
          value={planoId}
          onChange={(e) => setPlanoId(e.target.value)}
          className="input w-full"
        >
          <option value="">Sem plano</option>
          {planos.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome} — {formatBRL(p.preco_mensal_centavos)}
              {p.trial_dias > 0 ? ` (${p.trial_dias}d trial)` : ""}
            </option>
          ))}
        </select>
      </div>

      {planoSelecionado && planoSelecionado.trial_dias > 0 && (
        <label className="flex items-start gap-2 cursor-pointer bg-blue-50 border border-blue-200 p-3 rounded-md">
          <input
            type="checkbox"
            checked={iniciarTrial}
            onChange={(e) => setIniciarTrial(e.target.checked)}
            className="mt-0.5"
          />
          <div className="text-sm">
            <p className="font-medium text-blue-900">
              Iniciar período de trial de {planoSelecionado.trial_dias} dias
            </p>
            <p className="text-xs text-blue-700 mt-0.5">
              Status fica TRIAL e expira em{" "}
              {planoSelecionado.trial_dias} dias. Se desmarcado, vai
              direto pra ATIVO.
            </p>
          </div>
        </label>
      )}

      <div className="flex justify-end pt-4 border-t border-slate-200">
        <button
          type="button"
          onClick={() => trocar.mutate()}
          disabled={trocar.isPending}
          className="btn-primary"
        >
          {trocar.isPending ? "Salvando..." : "Trocar plano"}
        </button>
      </div>
    </div>
  );
}

// ============================================================
// Aba: Status
// ============================================================

function AbaStatus({
  assinatura,
  onSuccess,
  onError,
}: {
  assinatura: ClienteAssinatura;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [status, setStatus] = useState<StatusAssinatura>(
    assinatura.status_assinatura,
  );
  const [trialAte, setTrialAte] = useState<string>(
    assinatura.trial_termina_em
      ? assinatura.trial_termina_em.slice(0, 10)
      : "",
  );

  const atualizar = useMutation({
    mutationFn: async () => {
      const { data } = await api.put<ClienteAssinatura>(
        `/api/planos/clientes/${assinatura.id}/status`,
        {
          status_assinatura: status,
          trial_termina_em:
            status === "TRIAL" && trialAte
              ? new Date(trialAte + "T23:59:59Z").toISOString()
              : null,
        },
      );
      return data;
    },
    onSuccess: () => onSuccess("Status atualizado."),
    onError: (err) => onError(getErrorMessage(err)),
  });

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Status da assinatura
        </label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusAssinatura)}
          className="input w-full"
        >
          {(
            ["TRIAL", "ATIVO", "INADIMPLENTE", "SUSPENSO", "CANCELADO"] as const
          ).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>

      {status === "TRIAL" && (
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Trial termina em
          </label>
          <input
            type="date"
            value={trialAte}
            onChange={(e) => setTrialAte(e.target.value)}
            className="input"
          />
        </div>
      )}

      <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-600">
        <p>
          <strong>SUSPENSO</strong>: cliente não conseguirá fazer login (assim
          que o middleware for ativado).
        </p>
        <p className="mt-1">
          <strong>INADIMPLENTE</strong>: ainda acessa, mas aparece alerta no
          dashboard.
        </p>
        <p className="mt-1">
          Esta tela permite override manual. A cobrança automática
          (Asaas) vai gerenciar isso sozinha na próxima etapa.
        </p>
      </div>

      <div className="flex justify-end pt-4 border-t border-slate-200">
        <button
          type="button"
          onClick={() => atualizar.mutate()}
          disabled={atualizar.isPending}
          className="btn-primary"
        >
          {atualizar.isPending ? "Salvando..." : "Atualizar status"}
        </button>
      </div>
    </div>
  );
}

// ============================================================
// Utilitário
// ============================================================

function contarFeaturesBool(features: Record<string, unknown>): number {
  return Object.values(features).filter((v) => v === true).length;
}
