/**
 * Extrato Consolidado — visão única que une N fichas pendentes do mesmo
 * hospital/dia/médico e permite gerar UM lote único de pagamento.
 *
 * Resolve o gap: antes cada ficha virava um lote separado e o coordenador
 * tinha 4 lotes pra revisar quando deveria ter 1 só.
 *
 * 3 visões:
 *   - Hospital/Mês: todas fichas do cliente X na competência Y
 *   - Dia: fichas subidas no mesmo dia (estilo "bolo do dia")
 *   - Médico: todas fichas em que Dr X aparece
 *
 * Botão final: "Consolidar e gerar lote" → chama POST /api/consolidacao/gerar-lote
 * com os IDs das fichas selecionadas → 1 lote pronto pra revisão/CNAB.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  Calendar,
  CalendarDays,
  CheckCircle2,
  FileText,
  Inbox,
  Layers3,
  Loader2,
  Search,
  Send,
  UserCheck,
  Users,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";

interface ClienteComFichas {
  cliente_id: string;
  nome: string;
  qtd_fichas_pendentes: number;
}

interface FichaResumo {
  id: string;
  nome_arquivo: string;
  status: string;
  qtd_linhas: number;
  valor_total_centavos: number;
  competencia: string | null;
  hospital: string | null;
  coordenador: string | null;
  created_at: string;
}

interface MedicoNoExtrato {
  cpf_mascarado: string;
  nome: string;
  qtd_aparicoes: number;
  valor_total_centavos: number;
  beneficiario_id: string | null;
  beneficiario_cadastrado: boolean;
}

interface ExtratoConsolidado {
  titulo: string;
  cliente_id: string;
  cliente_nome: string;
  chave_agrupamento: string;
  fichas: FichaResumo[];
  medicos: MedicoNoExtrato[];
  total_fichas: number;
  total_linhas: number;
  total_medicos_unicos: number;
  valor_total_centavos: number;
  medicos_nao_cadastrados: number;
}

type Aba = "hospital-mes" | "dia" | "medico";

function formatBRL(centavos: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(centavos / 100);
}

export function ExtratoConsolidadoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [aba, setAba] = useState<Aba>("hospital-mes");
  const [modo, setModo] = useState<"recebidos" | "processados">("recebidos");
  const [clienteId, setClienteId] = useState<string>("");

  // Hospital/Mês
  const [competencia, setCompetencia] = useState<string>("");

  // Dia
  const [dataDia, setDataDia] = useState<string>(
    new Date().toISOString().slice(0, 10),
  );

  // Médico
  const [cpfMedico, setCpfMedico] = useState<string>("");
  const [cpfSubmetido, setCpfSubmetido] = useState<string>("");

  // Seleção de fichas pra consolidar
  const [fichasSelecionadas, setFichasSelecionadas] = useState<Set<string>>(
    new Set(),
  );

  const { data: clientes = [] } = useQuery({
    queryKey: ["consolidacao", "clientes-com-fichas"],
    queryFn: async () => {
      const { data } = await api.get<ClienteComFichas[]>(
        "/api/consolidacao/clientes-com-fichas",
      );
      return data;
    },
  });

  useEffect(() => {
    if (!clienteId && clientes.length > 0) {
      setClienteId(clientes[0].cliente_id);
    }
  }, [clientes, clienteId]);

  const { data: competencias = [] } = useQuery({
    queryKey: ["consolidacao", "competencias", clienteId],
    queryFn: async () => {
      const { data } = await api.get<string[]>(
        `/api/consolidacao/competencias?cliente_id=${clienteId}`,
      );
      return data;
    },
    enabled: !!clienteId,
  });

  useEffect(() => {
    if (!competencia && competencias.length > 0) {
      setCompetencia(competencias[0]);
    }
  }, [competencias, competencia]);

  const extratoParams = useMemo(() => {
    if (!clienteId) return null;
    if (aba === "hospital-mes") {
      return {
        url: `/api/consolidacao/hospital-mes?cliente_id=${clienteId}&competencia=${encodeURIComponent(competencia || "")}`,
        key: ["hospital-mes", clienteId, competencia],
        habilitado: !!competencia,
      };
    }
    if (aba === "dia") {
      return {
        url: `/api/consolidacao/dia?cliente_id=${clienteId}&data=${dataDia}T00:00:00`,
        key: ["dia", clienteId, dataDia],
        habilitado: !!dataDia,
      };
    }
    return {
      url: `/api/consolidacao/medico?cliente_id=${clienteId}&cpf=${encodeURIComponent(cpfSubmetido)}`,
      key: ["medico", clienteId, cpfSubmetido],
      habilitado: !!cpfSubmetido,
    };
  }, [aba, clienteId, competencia, dataDia, cpfSubmetido]);

  const { data: extrato, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["consolidacao", ...(extratoParams?.key ?? [])],
    queryFn: async () => {
      if (!extratoParams) return null;
      const { data } = await api.get<ExtratoConsolidado>(extratoParams.url);
      return data;
    },
    enabled: !!extratoParams?.habilitado,
  });

  // Auto-marca todas as fichas quando o extrato carrega
  useEffect(() => {
    if (extrato) {
      setFichasSelecionadas(new Set(extrato.fichas.map((f) => f.id)));
    }
  }, [extrato]);

  const gerarLote = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{
        lote_id: string;
        status: string;
        total_pagamentos: number;
        valor_total_centavos: number;
      }>("/api/consolidacao/gerar-lote", {
        fichas_ids: Array.from(fichasSelecionadas),
        referencia: extrato?.titulo,
      });
      return data;
    },
    onSuccess: (resp) => {
      void queryClient.invalidateQueries({ queryKey: ["consolidacao"] });
      void refetch();
      navigate(`/app/lotes/${resp.lote_id}`);
    },
  });

  const totalSelecionados = useMemo(() => {
    if (!extrato) return { fichas: 0, valor: 0 };
    let valor = 0;
    for (const f of extrato.fichas) {
      if (fichasSelecionadas.has(f.id)) {
        valor += f.valor_total_centavos;
      }
    }
    return { fichas: fichasSelecionadas.size, valor };
  }, [extrato, fichasSelecionadas]);

  function toggleFicha(id: string) {
    setFichasSelecionadas((set) => {
      const next = new Set(set);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleTodas() {
    if (!extrato) return;
    if (fichasSelecionadas.size === extrato.fichas.length) {
      setFichasSelecionadas(new Set());
    } else {
      setFichasSelecionadas(new Set(extrato.fichas.map((f) => f.id)));
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
          <Layers3 className="text-brand-600" size={26} />
          Extrato Consolidado
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Unifica fichas pendentes do mesmo hospital, dia ou médico em um
          único lote de pagamento. Em vez de revisar 4 lotes pequenos, você
          gera 1 lote consolidado.
        </p>
      </header>

      {/* Tabs de nível: o que o hospital ENVIOU (a processar) x o que JÁ foi
          processado (CNAB/API, bate com o Dashboard). */}
      <div className="flex gap-1 border-b border-slate-200">
        <ModoTab
          ativo={modo === "recebidos"}
          onClick={() => setModo("recebidos")}
          icon={<Inbox size={15} />}
          badge={clientes.reduce((s, c) => s + c.qtd_fichas_pendentes, 0)}
        >
          Recebidos (a processar)
        </ModoTab>
        <ModoTab
          ativo={modo === "processados"}
          onClick={() => setModo("processados")}
          icon={<CheckCircle2 size={15} />}
        >
          Processados (CNAB/API)
        </ModoTab>
      </div>

      {modo === "processados" && <ProcessadosView />}

      {modo === "recebidos" &&
        (clientes.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">
          Nenhum cliente tem fichas pendentes (EXTRAIDA ou REVISADA).
          <br />
          <a href="/app/fichas" className="text-brand-700 underline mt-2 inline-block">
            Subir uma ficha de plantão →
          </a>
        </div>
      ) : (
        <>
          {/* Cliente + Aba */}
          <section className="card p-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1 font-medium">
                  <Building2 size={11} className="inline mr-1" />
                  Cliente / Hospital
                </label>
                <select
                  value={clienteId}
                  onChange={(e) => setClienteId(e.target.value)}
                  className="input w-full"
                >
                  {clientes.map((c) => (
                    <option key={c.cliente_id} value={c.cliente_id}>
                      {c.nome} · {c.qtd_fichas_pendentes} ficha(s) pendente(s)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-end gap-1">
                <AbaBtn ativo={aba === "hospital-mes"} onClick={() => setAba("hospital-mes")} icon={<Calendar size={13} />}>
                  Hospital/Mês
                </AbaBtn>
                <AbaBtn ativo={aba === "dia"} onClick={() => setAba("dia")} icon={<CalendarDays size={13} />}>
                  Dia
                </AbaBtn>
                <AbaBtn ativo={aba === "medico"} onClick={() => setAba("medico")} icon={<UserCheck size={13} />}>
                  Médico
                </AbaBtn>
              </div>
            </div>

            {/* Filtros específicos da aba */}
            {aba === "hospital-mes" && (
              <div>
                <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1 font-medium">
                  Competência
                </label>
                <select
                  value={competencia}
                  onChange={(e) => setCompetencia(e.target.value)}
                  className="input w-full md:w-1/3"
                >
                  {competencias.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {aba === "dia" && (
              <div>
                <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1 font-medium">
                  Data
                </label>
                <input
                  type="date"
                  value={dataDia}
                  onChange={(e) => setDataDia(e.target.value)}
                  className="input md:w-1/3"
                />
              </div>
            )}

            {aba === "medico" && (
              <div>
                <label className="block text-xs uppercase tracking-wider text-slate-500 mb-1 font-medium">
                  CPF do médico
                </label>
                <div className="flex gap-2 md:w-2/3">
                  <input
                    type="text"
                    value={cpfMedico}
                    onChange={(e) => setCpfMedico(e.target.value)}
                    placeholder="000.000.000-00"
                    className="input flex-1"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") setCpfSubmetido(cpfMedico);
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setCpfSubmetido(cpfMedico)}
                    className="btn-primary"
                  >
                    <Search size={14} className="mr-1" />
                    Buscar
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Resultado */}
          {isLoading || isFetching ? (
            <div className="card p-8 text-center text-slate-500">
              <Loader2 className="inline animate-spin mr-2" size={16} />
              Carregando extrato...
            </div>
          ) : !extrato ? (
            <div className="card p-8 text-center text-slate-400 text-sm">
              {aba === "medico" && !cpfSubmetido
                ? "Digite um CPF e clique em Buscar."
                : "Sem dados pra mostrar."}
            </div>
          ) : extrato.total_fichas === 0 ? (
            <div className="card p-8 text-center text-slate-500">
              Nenhuma ficha encontrada pra esses filtros.
            </div>
          ) : (
            <>
              {/* KPIs */}
              <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KPI
                  icon={<FileText size={16} />}
                  label="Fichas"
                  valor={extrato.total_fichas.toString()}
                />
                <KPI
                  icon={<Users size={16} />}
                  label="Médicos únicos"
                  valor={extrato.total_medicos_unicos.toString()}
                  alerta={
                    extrato.medicos_nao_cadastrados > 0
                      ? `${extrato.medicos_nao_cadastrados} sem cadastro`
                      : undefined
                  }
                />
                <KPI
                  icon={<Layers3 size={16} />}
                  label="Linhas"
                  valor={extrato.total_linhas.toString()}
                />
                <KPI
                  icon={<CheckCircle2 size={16} />}
                  label="Valor total"
                  valor={formatBRL(extrato.valor_total_centavos)}
                  destacado
                />
              </section>

              {/* Alerta de médicos não cadastrados */}
              {extrato.medicos_nao_cadastrados > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-900 flex items-start gap-2">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold">
                      {extrato.medicos_nao_cadastrados} médico(s) sem cadastro
                      no sistema de beneficiários
                    </p>
                    <p className="text-xs mt-0.5">
                      O lote será gerado normalmente, mas esses médicos não
                      terão vinculação automática. Vale cadastrar em{" "}
                      <a
                        href="/app/prestadores"
                        className="underline hover:text-amber-700"
                      >
                        Prestadores
                      </a>{" "}
                      pra pegar os dados bancários da próxima vez.
                    </p>
                  </div>
                </div>
              )}

              {/* Fichas envolvidas */}
              <section className="card p-0 overflow-hidden">
                <header className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
                  <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                    <FileText size={16} />
                    Fichas no extrato · {extrato.titulo}
                  </h2>
                  <button
                    type="button"
                    onClick={toggleTodas}
                    className="text-xs text-brand-700 hover:underline"
                  >
                    {fichasSelecionadas.size === extrato.fichas.length
                      ? "Desmarcar todas"
                      : "Marcar todas"}
                  </button>
                </header>
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-5 py-2 text-left w-10">Inc.</th>
                      <th className="px-5 py-2 text-left">Arquivo</th>
                      <th className="px-5 py-2 text-left">Competência</th>
                      <th className="px-5 py-2 text-left">Coordenador</th>
                      <th className="px-5 py-2 text-right">Linhas</th>
                      <th className="px-5 py-2 text-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extrato.fichas.map((f) => (
                      <tr
                        key={f.id}
                        className="border-b border-slate-100 last:border-0 hover:bg-slate-50"
                      >
                        <td className="px-5 py-2">
                          <input
                            type="checkbox"
                            checked={fichasSelecionadas.has(f.id)}
                            onChange={() => toggleFicha(f.id)}
                            className="cursor-pointer"
                          />
                        </td>
                        <td className="px-5 py-2">
                          <a
                            href={`/app/fichas/${f.id}`}
                            className="text-brand-700 hover:underline font-medium"
                          >
                            {f.nome_arquivo}
                          </a>
                          <p className="text-xs text-slate-400">
                            {new Date(f.created_at).toLocaleDateString("pt-BR")}{" "}
                            · {f.status}
                          </p>
                        </td>
                        <td className="px-5 py-2 text-slate-600">
                          {f.competencia ?? "—"}
                        </td>
                        <td className="px-5 py-2 text-slate-600 text-xs">
                          {f.coordenador ?? "—"}
                        </td>
                        <td className="px-5 py-2 text-right tabular-nums">
                          {f.qtd_linhas}
                        </td>
                        <td className="px-5 py-2 text-right tabular-nums font-semibold">
                          {formatBRL(f.valor_total_centavos)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              {/* Médicos consolidados */}
              <section className="card p-0 overflow-hidden">
                <header className="px-5 py-3 border-b border-slate-200">
                  <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                    <Users size={16} />
                    Médicos no consolidado
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Soma do que cada médico tem a receber considerando todas
                    as fichas selecionadas.
                  </p>
                </header>
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-5 py-2 text-left">Médico</th>
                      <th className="px-5 py-2 text-left">CPF</th>
                      <th className="px-5 py-2 text-center">Status cadastro</th>
                      <th className="px-5 py-2 text-right">Aparições</th>
                      <th className="px-5 py-2 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extrato.medicos.map((m, i) => (
                      <tr
                        key={i}
                        className="border-b border-slate-100 last:border-0 hover:bg-slate-50"
                      >
                        <td className="px-5 py-2 font-medium text-slate-800">
                          {m.nome}
                        </td>
                        <td className="px-5 py-2 text-slate-500 font-mono text-xs">
                          {m.cpf_mascarado}
                        </td>
                        <td className="px-5 py-2 text-center">
                          {m.beneficiario_cadastrado ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 text-xs">
                              <CheckCircle2 size={12} /> Cadastrado
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-amber-700 text-xs">
                              <AlertTriangle size={12} /> Sem cadastro
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-2 text-right tabular-nums">
                          {m.qtd_aparicoes}
                        </td>
                        <td className="px-5 py-2 text-right tabular-nums font-semibold">
                          {formatBRL(m.valor_total_centavos)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              {/* Ação: gerar lote */}
              <section className="card p-5 sticky bottom-0 bg-white border-t-2 border-brand-100 shadow-lg">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-slate-500">
                      Selecionado pra consolidação
                    </p>
                    <p className="text-lg font-semibold text-slate-900">
                      {totalSelecionados.fichas} ficha(s) ·{" "}
                      <span className="text-brand-700">
                        {formatBRL(totalSelecionados.valor)}
                      </span>
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => gerarLote.mutate()}
                    disabled={
                      gerarLote.isPending || fichasSelecionadas.size === 0
                    }
                    className="btn-primary text-base"
                  >
                    {gerarLote.isPending ? (
                      <>
                        <Loader2 className="animate-spin mr-2" size={16} />
                        Consolidando...
                      </>
                    ) : (
                      <>
                        <Send size={15} className="mr-2" />
                        Consolidar e gerar lote único
                      </>
                    )}
                  </button>
                </div>
                {gerarLote.isError && (
                  <p className="text-sm text-red-700 mt-3">
                    {getErrorMessage(gerarLote.error)}
                  </p>
                )}
              </section>
            </>
          )}
        </>
      ))}
    </div>
  );
}

function ModoTab({
  ativo,
  onClick,
  icon,
  badge,
  children,
}: {
  ativo: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  badge?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold border-b-2 transition ${
        ativo
          ? "border-brand-600 text-brand-700"
          : "border-transparent text-slate-500 hover:text-slate-800"
      }`}
    >
      {icon}
      {children}
      {badge && badge > 0 ? (
        <span className="ml-1 min-w-[20px] h-5 px-1.5 rounded-full bg-accent-400 text-brand-950 text-[11px] font-bold inline-flex items-center justify-center">
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
    </button>
  );
}

interface LoteProcessado {
  lote_id: string;
  cliente_id: string;
  cliente_nome: string;
  referencia: string | null;
  competencia: string | null;
  status: string;
  total_pagamentos: number;
  valor_total_centavos: number;
  created_at: string;
  aprovado_at: string | null;
}

interface ExtratoProcessados {
  lotes: LoteProcessado[];
  total_lotes: number;
  total_pagamentos: number;
  valor_total_centavos: number;
}

const LABEL_STATUS_LOTE: Record<string, { label: string; cls: string }> = {
  APROVADO: { label: "Aprovado (CNAB pronto)", cls: "bg-emerald-50 text-emerald-700" },
  ENVIADO_BANCO: { label: "Enviado ao banco", cls: "bg-blue-50 text-blue-700" },
  CONCILIADO: { label: "Conciliado (pago)", cls: "bg-brand-50 text-brand-700" },
};

function ProcessadosView() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["consolidacao", "processados"],
    queryFn: async () => {
      const { data } = await api.get<ExtratoProcessados>(
        "/api/consolidacao/processados",
      );
      return data;
    },
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="card p-8 text-center text-slate-500">
        <Loader2 className="inline animate-spin mr-2" size={16} />
        Carregando processados...
      </div>
    );
  }

  if (!data || data.total_lotes === 0) {
    return (
      <div className="card p-8 text-center text-slate-400 text-sm">
        Nada processado ainda. Quando você gerar e aprovar um lote (CNAB/API),
        ele aparece aqui — e o total bate com o "Aprovados" do Dashboard.
      </div>
    );
  }

  return (
    <>
      <section className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <KPI
          icon={<CheckCircle2 size={16} />}
          label="Lotes processados"
          valor={data.total_lotes.toString()}
        />
        <KPI
          icon={<Users size={16} />}
          label="Pagamentos"
          valor={data.total_pagamentos.toString()}
        />
        <KPI
          icon={<CheckCircle2 size={16} />}
          label="Valor processado"
          valor={formatBRL(data.valor_total_centavos)}
          destacado
        />
      </section>

      <section className="card p-0 overflow-hidden">
        <header className="px-5 py-3 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900 flex items-center gap-2">
            <CheckCircle2 size={16} />
            Extrato processado · CNAB/API
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Lotes que saíram dos recebidos e foram processados/pagos. Clique
            pra abrir o lote e baixar o CNAB.
          </p>
        </header>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-5 py-2 text-left">Hospital</th>
              <th className="px-5 py-2 text-left">Competência</th>
              <th className="px-5 py-2 text-left">Status</th>
              <th className="px-5 py-2 text-right">Pagamentos</th>
              <th className="px-5 py-2 text-right">Valor</th>
            </tr>
          </thead>
          <tbody>
            {data.lotes.map((l) => {
              const st = LABEL_STATUS_LOTE[l.status] ?? {
                label: l.status,
                cls: "bg-slate-100 text-slate-600",
              };
              return (
                <tr
                  key={l.lote_id}
                  onClick={() => navigate(`/app/lotes/${l.lote_id}`)}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer"
                >
                  <td className="px-5 py-2 font-medium text-slate-800">
                    {l.cliente_nome}
                    <p className="text-xs text-slate-400">
                      {new Date(l.created_at).toLocaleDateString("pt-BR")}
                    </p>
                  </td>
                  <td className="px-5 py-2 text-slate-600">
                    {l.competencia ?? "—"}
                  </td>
                  <td className="px-5 py-2">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${st.cls}`}
                    >
                      {st.label}
                    </span>
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {l.total_pagamentos}
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums font-semibold">
                    {formatBRL(l.valor_total_centavos)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}

function AbaBtn({
  ativo,
  onClick,
  icon,
  children,
}: {
  ativo: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition ${
        ativo
          ? "border-brand-600 text-brand-700"
          : "border-transparent text-slate-500 hover:text-slate-800"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function KPI({
  icon,
  label,
  valor,
  alerta,
  destacado,
}: {
  icon: React.ReactNode;
  label: string;
  valor: string;
  alerta?: string;
  destacado?: boolean;
}) {
  return (
    <div
      className={`card p-4 ${destacado ? "bg-brand-50 border-brand-200" : ""}`}
    >
      <p className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-1">
        {icon} {label}
      </p>
      <p
        className={`text-xl font-bold tabular-nums mt-1 ${
          destacado ? "text-brand-700" : "text-slate-900"
        }`}
      >
        {valor}
      </p>
      {alerta && (
        <p className="text-[11px] text-amber-700 mt-1 flex items-center gap-1">
          <AlertTriangle size={10} />
          {alerta}
        </p>
      )}
    </div>
  );
}
