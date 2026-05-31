import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  Bell,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  Info,
  Send,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { cn, formatBRL } from "@/lib/utils";
import type {
  Alerta,
  ContratoFinanceiro,
  DashboardExecutivo,
  ProjecaoMensal,
  RenovacaoProxima,
  ResumoOperacaoMes,
  ResumoPipelineHospital,
} from "@/types";

export function DashboardExecutivoPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", "executivo"],
    queryFn: async () => {
      const { data } = await api.get<DashboardExecutivo>(
        "/api/dashboard/executivo",
      );
      return data;
    },
    staleTime: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] text-brand-700">
        Carregando dashboard executivo…
      </div>
    );
  }

  const semDados =
    data.contratos.length === 0 &&
    data.pipeline_hospitais.length === 0 &&
    (!data.operacao_mes || data.operacao_mes.volume_total_mes_centavos === 0);

  return (
    <div className="space-y-8">
      <Header
        periodo={data.mes_referencia}
        geradoEm={data.gerado_em}
        receitaPrevista={data.receita_prevista_centavos}
        margemPrevista={data.margem_prevista_centavos}
      />

      {data.sem_contratos_configurados && data.pipeline_hospitais.length > 0 && (
        <SemContratosBanner />
      )}

      {/* Aviso enxuto quando ainda não há movimento — mas os cards de gestão
          continuam visíveis (zerados) pra estrutura aparecer sempre. */}
      {semDados && <AvisoSemDados />}

      <KPIHero data={data} />

      <OperacaoMesCard operacao={data.operacao_mes ?? OPERACAO_ZERO} />

      {data.pipeline_hospitais.length > 0 && (
        <PipelineHospitaisCard pipeline={data.pipeline_hospitais} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {data.contratos.length > 0 && (
            <ReceitaPorContrato contratos={data.contratos} />
          )}
          <Projecao12Meses dados={data.projecao_12m} />
          <KPIsOperacionais kpis={data.kpi_operacional} />
        </div>

        <div className="space-y-6">
          <AlertasCard alertas={data.alertas} />
          <RenovacoesCard renovacoes={data.renovacoes_proximas} />
        </div>
      </div>
    </div>
  );
}

// Operação zerada — usado quando ainda não há movimento no mês, pra os
// cards de "Programação x Realizado" aparecerem com 0 em vez de sumirem.
const OPERACAO_ZERO: ResumoOperacaoMes = {
  volume_total_mes_centavos: 0,
  qtd_fichas_pendentes: 0,
  valor_fichas_pendentes_centavos: 0,
  qtd_lotes_programados: 0,
  valor_lotes_programados_centavos: 0,
  qtd_lotes_enviados: 0,
  valor_lotes_enviados_centavos: 0,
  qtd_lotes_conciliados: 0,
  valor_lotes_conciliados_centavos: 0,
  qtd_clientes_ativos: 0,
};

// =============================================================================
// Estado vazio (nada cadastrado ainda)
// =============================================================================

function AvisoSemDados() {
  return (
    <div className="rounded-xl border border-brand-200 bg-gradient-to-r from-brand-50 to-accent-50/40 p-4 flex items-start gap-3">
      <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-white border border-brand-100 flex-shrink-0">
        <Sparkles className="text-brand-700" size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-brand-950 text-sm">
          Ainda sem operação registrada neste mês
        </p>
        <p className="text-xs text-brand-700 mt-0.5 max-w-2xl">
          Os indicadores abaixo aparecem zerados até o coordenador subir as
          primeiras fichas (ou as planilhas gerarem lotes). Assim que houver
          movimento, programação de pagamento, valores a executar e pagamentos
          conciliados por hospital são preenchidos automaticamente.
        </p>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0 flex-wrap justify-end">
        <Link
          to="/app/fichas"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-brand-900 text-white text-xs font-semibold hover:bg-brand-800 transition"
        >
          <FileSpreadsheet size={14} />
          Subir ficha
        </Link>
        <Link
          to="/app/contratos"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-brand-200 text-xs font-semibold text-brand-800 hover:bg-brand-50 transition"
        >
          Configurar contratos
        </Link>
      </div>
    </div>
  );
}

// =============================================================================
// Banner — sem contratos cadastrados (mas tem atividade)
// =============================================================================

function SemContratosBanner() {
  return (
    <div className="rounded-xl border border-accent-200 bg-gradient-to-r from-accent-50 to-amber-50 p-4 flex items-start gap-3">
      <AlertTriangle className="text-accent-600 flex-shrink-0 mt-0.5" size={18} />
      <div className="flex-1">
        <p className="font-semibold text-brand-950 text-sm">
          Sem contratos comerciais cadastrados
        </p>
        <p className="text-xs text-brand-700 mt-0.5">
          Há hospitais com atividade neste mês mas sem contrato configurado
          no MedPag. As métricas de receita só aparecem após você cadastrar
          a remuneração do contrato (mensalidade, taxa por pagamento ou %
          sobre volume).
        </p>
      </div>
      <Link
        to="/app/contratos"
        className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-accent-600 text-white hover:bg-accent-700 transition flex-shrink-0"
      >
        Configurar agora
      </Link>
    </div>
  );
}

// =============================================================================
// Programação x Realizado (sempre populado quando há atividade)
// =============================================================================

function OperacaoMesCard({ operacao }: { operacao: ResumoOperacaoMes }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="rounded-xl bg-gradient-to-br from-accent-50 via-white to-white border border-accent-200 p-5">
        <div className="flex items-center gap-2 text-xs font-bold tracking-[0.1em] text-accent-700 uppercase mb-3">
          <Clock size={14} />
          Programação de pagamento
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Bloco
            icon={FileSpreadsheet}
            label="Fichas pendentes"
            qtd={operacao.qtd_fichas_pendentes}
            valor={operacao.valor_fichas_pendentes_centavos}
            sub="extraídas/em revisão"
          />
          <Bloco
            icon={Send}
            label="Lotes a executar"
            qtd={operacao.qtd_lotes_programados}
            valor={operacao.valor_lotes_programados_centavos}
            sub="aprovação + revisão"
          />
        </div>
      </div>

      <div className="rounded-xl bg-gradient-to-br from-emerald-50 via-white to-white border border-emerald-200 p-5">
        <div className="flex items-center gap-2 text-xs font-bold tracking-[0.1em] text-emerald-700 uppercase mb-3">
          <CheckCircle2 size={14} />
          Pagamentos realizados
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Bloco
            icon={Banknote}
            label="Enviados ao banco"
            qtd={operacao.qtd_lotes_enviados}
            valor={operacao.valor_lotes_enviados_centavos}
            sub="aguardando conciliação"
          />
          <Bloco
            icon={CheckCircle2}
            label="Conciliados"
            qtd={operacao.qtd_lotes_conciliados}
            valor={operacao.valor_lotes_conciliados_centavos}
            sub={`${operacao.qtd_clientes_ativos} hospitais ativos`}
          />
        </div>
      </div>
    </div>
  );
}

function Bloco({
  icon: Icon,
  label,
  qtd,
  valor,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  qtd: number;
  valor: number;
  sub: string;
}) {
  return (
    <div className="bg-white/70 border border-brand-100 rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-brand-600 mb-1">
        <Icon size={12} />
        {label}
      </div>
      <div className="text-2xl font-bold text-brand-950 leading-tight">{qtd}</div>
      <div className="text-sm font-semibold text-brand-800 mt-0.5">
        {formatBRL(valor)}
      </div>
      <div className="text-[10px] text-brand-600 mt-1">{sub}</div>
    </div>
  );
}

// =============================================================================
// Pipeline por hospital
// =============================================================================

function PipelineHospitaisCard({
  pipeline,
}: {
  pipeline: ResumoPipelineHospital[];
}) {
  const max = Math.max(...pipeline.map((p) => p.volume_total_mes_centavos), 1);

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Building2 size={16} className="text-brand-700" />
          Volume por hospital — programação x realizado
        </span>
      }
      subtitle="Cada barra mostra o volume operado este mês, dividido por estado"
    >
      <div className="space-y-3">
        {pipeline.map((h) => (
          <PipelineHospitalRow key={h.cliente_id} hospital={h} max={max} />
        ))}
      </div>
    </Card>
  );
}

function PipelineHospitalRow({
  hospital,
  max,
}: {
  hospital: ResumoPipelineHospital;
  max: number;
}) {
  const total = Math.max(hospital.volume_total_mes_centavos, 1);
  const widthPct = (hospital.volume_total_mes_centavos / max) * 100;
  const segs = [
    {
      key: "fichas",
      pct: (hospital.valor_fichas_pendentes_centavos / total) * 100,
      cls: "bg-accent-300",
    },
    {
      key: "revisao",
      pct: (hospital.valor_lotes_em_revisao_centavos / total) * 100,
      cls: "bg-accent-500",
    },
    {
      key: "aprovado",
      pct: (hospital.valor_lotes_aprovados_centavos / total) * 100,
      cls: "bg-brand-600",
    },
    {
      key: "enviado",
      pct: (hospital.valor_lotes_enviados_centavos / total) * 100,
      cls: "bg-emerald-500",
    },
    {
      key: "conciliado",
      pct: (hospital.valor_lotes_conciliados_centavos / total) * 100,
      cls: "bg-emerald-700",
    },
  ];
  return (
    <div className="border border-brand-100 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <strong className="text-sm text-brand-950">{hospital.cliente_nome}</strong>
          {!hospital.tem_contrato && (
            <span className="text-[9px] font-bold tracking-wide px-1.5 py-0.5 rounded bg-accent-100 text-accent-800 border border-accent-200">
              SEM CONTRATO
            </span>
          )}
        </div>
        <div className="text-sm font-bold text-brand-950">
          {formatBRL(hospital.volume_total_mes_centavos)}
        </div>
      </div>

      <div
        className="h-3 bg-brand-50 rounded-full overflow-hidden flex"
        style={{ width: `${widthPct}%`, minWidth: "20%" }}
      >
        {segs.map((s) =>
          s.pct > 0 ? (
            <div
              key={s.key}
              className={cn("h-full", s.cls)}
              style={{ width: `${s.pct}%` }}
            />
          ) : null,
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-2 text-[11px]">
        <SegLabel
          dot="bg-accent-300"
          label={`${hospital.fichas_pendentes} fichas`}
          valor={hospital.valor_fichas_pendentes_centavos}
        />
        <SegLabel
          dot="bg-accent-500"
          label={`${hospital.lotes_em_revisao} em revisão`}
          valor={hospital.valor_lotes_em_revisao_centavos}
        />
        <SegLabel
          dot="bg-brand-600"
          label={`${hospital.lotes_aprovados} aprovados`}
          valor={hospital.valor_lotes_aprovados_centavos}
        />
        <SegLabel
          dot="bg-emerald-500"
          label={`${hospital.lotes_enviados} enviados`}
          valor={hospital.valor_lotes_enviados_centavos}
        />
        <SegLabel
          dot="bg-emerald-700"
          label={`${hospital.lotes_conciliados} pagos`}
          valor={hospital.valor_lotes_conciliados_centavos}
        />
      </div>
    </div>
  );
}

function SegLabel({
  dot,
  label,
  valor,
}: {
  dot: string;
  label: string;
  valor: number;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("w-2 h-2 rounded-full flex-shrink-0", dot)} />
      <span className="text-brand-700 truncate">
        {label}{" "}
        <strong className="text-brand-900">{formatBRL(valor)}</strong>
      </span>
    </div>
  );
}

// =============================================================================
// Header
// =============================================================================

function Header({
  periodo,
  geradoEm,
  receitaPrevista,
  margemPrevista,
}: {
  periodo: string;
  geradoEm: string;
  receitaPrevista: number;
  margemPrevista: number;
}) {
  const horario = new Date(geradoEm).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div className="flex items-end justify-between border-b border-brand-100 pb-6 gap-4 flex-wrap">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.15em] text-accent-700 uppercase mb-2">
          <Sparkles size={14} className="text-accent-500" />
          Dashboard Executivo
        </div>
        <h1 className="text-3xl font-bold text-brand-950 tracking-tight">
          Visão financeira da operação
        </h1>
        <p className="text-sm text-brand-700 mt-1">
          Período: <strong className="text-brand-950">{periodo}</strong> · atualizado{" "}
          {horario}
        </p>
      </div>
      {receitaPrevista > 0 && (
        <div className="text-xs px-4 py-2 rounded-xl bg-gradient-to-br from-brand-50 to-accent-50 border border-accent-200">
          <div className="text-[10px] uppercase tracking-wider text-brand-600 font-bold">
            Em pipeline (fichas)
          </div>
          <div className="text-sm font-bold text-brand-950 mt-0.5">
            +{formatBRL(receitaPrevista)}{" "}
            <span className="text-emerald-700 font-semibold text-xs">
              · margem ~{formatBRL(margemPrevista)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// KPI Hero (4 cards principais)
// =============================================================================

function KPIHero({ data }: { data: DashboardExecutivo }) {
  const k = data.kpi_hero;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <KpiHeroCard
        label="Lucro líquido (mês)"
        value={formatBRL(k.lucro_liquido_centavos)}
        icon={Wallet}
        delta={k.delta_lucro_pct}
        deltaLabel="vs mês anterior"
        primary
      />
      <KpiHeroCard
        label="Receita total"
        value={formatBRL(k.receita_total_centavos)}
        icon={TrendingUp}
        delta={null}
        deltaLabel={`Custo: ${formatBRL(k.custo_total_centavos)}`}
      />
      <KpiHeroCard
        label="Margem média"
        value={`${k.margem_media_pct}%`}
        icon={k.margem_media_pct >= 50 ? TrendingUp : TrendingDown}
        delta={null}
        deltaLabel={
          k.margem_media_pct >= 50
            ? "Operação saudável"
            : "Atenção: margem baixa"
        }
      />
      <KpiHeroCard
        label="Meta do mês"
        value={`${k.meta_atingida_pct}%`}
        icon={Target}
        delta={null}
        deltaLabel={`Meta: ${formatBRL(k.meta_total_centavos)}`}
      />
    </div>
  );
}

function KpiHeroCard({
  label,
  value,
  icon: Icon,
  delta,
  deltaLabel,
  primary = false,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  delta: number | null;
  deltaLabel?: string;
  primary?: boolean;
}) {
  const positive = delta !== null && delta >= 0;
  return (
    <div
      className={cn(
        "rounded-xl p-5 border relative overflow-hidden",
        primary
          ? "bg-gradient-to-br from-brand-950 via-brand-900 to-brand-800 text-white border-brand-900"
          : "bg-white border-brand-100",
      )}
    >
      {primary && (
        <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-accent-400 via-accent-500 to-accent-300" />
      )}
      <div className="flex items-start justify-between mb-3">
        <span
          className={cn(
            "text-[11px] font-semibold uppercase tracking-[0.1em]",
            primary ? "text-accent-200" : "text-brand-600",
          )}
        >
          {label}
        </span>
        <div
          className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center",
            primary
              ? "bg-brand-900 border border-accent-400/40 text-accent-300"
              : "bg-brand-50 border border-brand-100 text-brand-700",
          )}
        >
          <Icon size={18} />
        </div>
      </div>
      <div
        className={cn(
          "text-3xl font-bold tracking-tight",
          primary ? "text-white" : "text-brand-950",
        )}
      >
        {value}
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        {delta !== null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 font-bold px-2 py-0.5 rounded-full",
              positive
                ? "bg-emerald-50 text-emerald-700 border border-emerald-100"
                : "bg-red-50 text-red-700 border border-red-100",
              primary && positive && "bg-accent-500/20 text-accent-200 border-accent-400/30",
              primary && !positive && "bg-red-500/20 text-red-200 border-red-400/30",
            )}
          >
            {positive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {positive ? "+" : ""}
            {delta}%
          </span>
        )}
        {deltaLabel && (
          <span className={cn(primary ? "text-brand-100/70" : "text-brand-600")}>
            {deltaLabel}
          </span>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Receita por contrato
// =============================================================================

function ReceitaPorContrato({ contratos }: { contratos: ContratoFinanceiro[] }) {
  const sorted = [...contratos].sort(
    (a, b) => b.receita_mes_centavos - a.receita_mes_centavos,
  );
  const maxReceita = Math.max(...sorted.map((c) => c.receita_mes_centavos), 1);

  return (
    <Card
      title="Receita por contrato"
      subtitle="Margem real por cliente este mês"
    >
      <div className="space-y-3">
        {sorted.map((contrato) => (
          <ContratoRow
            key={contrato.cliente_id}
            contrato={contrato}
            maxReceita={maxReceita}
          />
        ))}
      </div>
    </Card>
  );
}

function ContratoRow({
  contrato,
  maxReceita,
}: {
  contrato: ContratoFinanceiro;
  maxReceita: number;
}) {
  const widthPct = (contrato.receita_mes_centavos / maxReceita) * 100;
  const lucro = contrato.receita_mes_centavos - contrato.custo_mes_centavos;
  const colorBar = {
    saudavel: "bg-gradient-to-r from-emerald-500 to-emerald-400",
    atencao: "bg-gradient-to-r from-accent-500 to-accent-400",
    critico: "bg-gradient-to-r from-red-500 to-red-400",
  }[contrato.saude];
  const dotColor = {
    saudavel: "bg-emerald-500",
    atencao: "bg-accent-500",
    critico: "bg-red-500",
  }[contrato.saude];
  const positiveDelta = contrato.margem_delta_pp >= 0;

  return (
    <div className="border border-brand-100 rounded-lg p-4 bg-white hover:border-accent-300 transition">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={cn("w-2.5 h-2.5 rounded-full", dotColor)} />
          <strong className="text-brand-950 text-sm">{contrato.cliente_nome}</strong>
          <span className="text-xs text-brand-600">
            · {contrato.lotes_mes} lote{contrato.lotes_mes !== 1 && "s"} · {contrato.pagamentos_mes.toLocaleString("pt-BR")} pgto
          </span>
        </div>
        <div className="text-right">
          <div className="text-sm font-bold text-brand-950">
            {formatBRL(contrato.receita_mes_centavos)}
          </div>
          <div className="text-xs text-brand-600">
            Lucro: <strong className="text-brand-800">{formatBRL(lucro)}</strong>
          </div>
        </div>
      </div>

      <div className="relative h-2 bg-brand-50 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", colorBar)}
          style={{ width: `${widthPct}%` }}
        />
      </div>

      <div className="flex items-center justify-between mt-2 text-xs">
        <span className="text-brand-600">
          Margem:{" "}
          <strong
            className={cn(
              contrato.saude === "critico" && "text-red-700",
              contrato.saude === "atencao" && "text-accent-700",
              contrato.saude === "saudavel" && "text-emerald-700",
            )}
          >
            {contrato.margem_pct}%
          </strong>
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-0.5 font-semibold",
            positiveDelta ? "text-emerald-700" : "text-red-700",
          )}
        >
          {positiveDelta ? (
            <ArrowUpRight size={12} />
          ) : (
            <ArrowDownRight size={12} />
          )}
          {positiveDelta ? "+" : ""}
          {contrato.margem_delta_pp}pp vs mês anterior
        </span>
      </div>
    </div>
  );
}

// =============================================================================
// Projeção 12 meses (gráfico de barras simples)
// =============================================================================

function Projecao12Meses({ dados }: { dados: ProjecaoMensal[] }) {
  const maxValor = Math.max(
    ...dados.map((d) => Math.max(d.receita_centavos, d.meta_centavos)),
    1,
  );

  return (
    <Card
      title="Projeção 12 meses"
      subtitle="Receita realizada e prevista vs meta mensal"
    >
      <div className="flex items-end gap-2 h-48 px-1">
        {dados.map((mes) => {
          const altReceita = (mes.receita_centavos / maxValor) * 100;
          const altMeta = (mes.meta_centavos / maxValor) * 100;
          const acimaMeta = mes.receita_centavos >= mes.meta_centavos;
          return (
            <div
              key={mes.mes}
              className="flex-1 flex flex-col items-center gap-1.5 group relative"
            >
              <div className="absolute -top-7 opacity-0 group-hover:opacity-100 transition bg-brand-950 text-white text-[10px] px-2 py-1 rounded whitespace-nowrap z-10 pointer-events-none">
                {formatBRL(mes.receita_centavos)}
              </div>
              <div className="flex items-end gap-0.5 h-full w-full justify-center">
                {/* Meta (linha clara atrás) */}
                <div className="relative w-full flex justify-center">
                  <div
                    className="absolute bottom-0 w-full border-t-2 border-dashed border-brand-300/60"
                    style={{ height: `${altMeta}%` }}
                  />
                  {/* Barra principal */}
                  <div
                    className={cn(
                      "w-full rounded-t-md relative z-[1] transition-all",
                      mes.realizado
                        ? acimaMeta
                          ? "bg-gradient-to-t from-brand-700 to-brand-500"
                          : "bg-gradient-to-t from-brand-600 to-brand-400"
                        : acimaMeta
                          ? "bg-gradient-to-t from-accent-500 to-accent-300"
                          : "bg-gradient-to-t from-accent-400 to-accent-200",
                      !mes.realizado && "opacity-80",
                    )}
                    style={{ height: `${altReceita}%` }}
                  />
                </div>
              </div>
              <span
                className={cn(
                  "text-[10px] font-medium",
                  mes.realizado ? "text-brand-800" : "text-accent-700",
                )}
              >
                {mes.mes}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-4 mt-4 text-xs text-brand-700 border-t border-brand-100 pt-3">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-gradient-to-t from-brand-700 to-brand-500" />
          Realizado
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-gradient-to-t from-accent-500 to-accent-300" />
          Projeção
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-dashed border-brand-300" />
          Meta
        </span>
      </div>
    </Card>
  );
}

// =============================================================================
// KPIs operacionais
// =============================================================================

function KPIsOperacionais({
  kpis,
}: {
  kpis: DashboardExecutivo["kpi_operacional"];
}) {
  const items = [
    {
      icon: CheckCircle2,
      label: "Lotes processados",
      value: kpis.lotes_processados.toString(),
      color: "text-emerald-700",
    },
    {
      icon: Clock,
      label: "Aguardando revisão",
      value: kpis.lotes_aguardando.toString(),
      color: "text-accent-700",
    },
    {
      icon: TrendingUp,
      label: "Tempo médio",
      value: `${kpis.tempo_medio_processamento_min} min`,
      color: "text-brand-800",
    },
    {
      icon: AlertTriangle,
      label: "Taxa de erro",
      value: `${kpis.taxa_erro_pct}%`,
      color: kpis.taxa_erro_pct < 5 ? "text-emerald-700" : "text-red-700",
    },
    {
      icon: Wallet,
      label: "Pagamentos do mês",
      value: kpis.pagamentos_mes.toLocaleString("pt-BR"),
      color: "text-brand-800",
    },
    {
      icon: Target,
      label: "Conciliados",
      value: `${kpis.conciliados_pct}%`,
      color: "text-brand-800",
    },
  ];

  return (
    <Card title="KPIs operacionais" subtitle="Saúde da operação no mês">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="bg-brand-50/50 border border-brand-100 rounded-lg p-3 hover:bg-brand-50 transition"
            >
              <div className="flex items-center gap-2 text-brand-600 text-[11px] font-semibold uppercase tracking-wide mb-1.5">
                <Icon size={14} />
                {item.label}
              </div>
              <div className={cn("text-2xl font-bold", item.color)}>
                {item.value}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// =============================================================================
// Alertas
// =============================================================================

function AlertasCard({ alertas }: { alertas: Alerta[] }) {
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Bell size={16} className="text-accent-600" />
          Alertas em aberto
          <span className="text-xs font-semibold bg-accent-100 text-accent-800 px-2 py-0.5 rounded-full">
            {alertas.length}
          </span>
        </span>
      }
      subtitle="Anomalias detectadas pela operação"
    >
      <div className="space-y-2.5">
        {alertas.map((alerta) => (
          <AlertaItem key={alerta.id} alerta={alerta} />
        ))}
        {alertas.length === 0 && (
          <div className="text-center py-6 text-brand-600 text-sm">
            Nenhum alerta no momento
          </div>
        )}
      </div>
    </Card>
  );
}

function AlertaItem({ alerta }: { alerta: Alerta }) {
  const styles = {
    critico: {
      box: "border-red-200 bg-red-50",
      badge: "bg-red-100 text-red-800 border-red-200",
      Icon: AlertTriangle,
      iconColor: "text-red-600",
      label: "CRÍTICO",
    },
    atencao: {
      box: "border-accent-200 bg-accent-50",
      badge: "bg-accent-100 text-accent-800 border-accent-200",
      Icon: AlertTriangle,
      iconColor: "text-accent-600",
      label: "ATENÇÃO",
    },
    info: {
      box: "border-brand-200 bg-brand-50",
      badge: "bg-brand-100 text-brand-800 border-brand-200",
      Icon: Info,
      iconColor: "text-brand-600",
      label: "INFO",
    },
  }[alerta.severidade];

  return (
    <div
      className={cn(
        "border rounded-lg p-3 transition hover:shadow-sm",
        styles.box,
      )}
    >
      <div className="flex items-start gap-2.5">
        <styles.Icon size={16} className={cn("flex-shrink-0 mt-0.5", styles.iconColor)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span
              className={cn(
                "text-[9px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded border",
                styles.badge,
              )}
            >
              {styles.label}
            </span>
            <strong className="text-sm text-brand-950">{alerta.titulo}</strong>
          </div>
          <p className="text-xs text-brand-700 leading-relaxed">
            {alerta.descricao}
          </p>
          {alerta.acao_sugerida && (
            <div className="mt-2 text-[11px] text-brand-800 bg-white/60 px-2 py-1 rounded border border-brand-100">
              <strong className="text-accent-700">Sugestão:</strong>{" "}
              {alerta.acao_sugerida}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Renovações próximas
// =============================================================================

function RenovacoesCard({ renovacoes }: { renovacoes: RenovacaoProxima[] }) {
  const sorted = [...renovacoes].sort(
    (a, b) => a.dias_restantes - b.dias_restantes,
  );
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <CalendarClock size={16} className="text-accent-600" />
          Renovações próximas
        </span>
      }
      subtitle="Contratos vencendo nos próximos 60 dias"
    >
      <div className="space-y-2.5">
        {sorted.map((ren) => (
          <RenovacaoItem key={ren.cliente_id} renovacao={ren} />
        ))}
      </div>
    </Card>
  );
}

function RenovacaoItem({ renovacao }: { renovacao: RenovacaoProxima }) {
  const styles = {
    manter: {
      tag: "bg-emerald-50 text-emerald-800 border-emerald-200",
      label: "Manter condições",
    },
    reajustar: {
      tag: "bg-accent-50 text-accent-800 border-accent-200",
      label: "Reajustar",
    },
    renegociar_urgente: {
      tag: "bg-red-50 text-red-800 border-red-200",
      label: "Renegociar urgente",
    },
  }[renovacao.recomendacao];

  const urgencia =
    renovacao.dias_restantes <= 15
      ? "text-red-700"
      : renovacao.dias_restantes <= 30
        ? "text-accent-700"
        : "text-brand-700";

  return (
    <div className="border border-brand-100 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between mb-1.5">
        <strong className="text-sm text-brand-950">{renovacao.cliente_nome}</strong>
        <span className={cn("text-xs font-bold", urgencia)}>
          {renovacao.dias_restantes}d
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={cn(
            "text-[10px] font-bold tracking-wide px-2 py-0.5 rounded-full border",
            styles.tag,
          )}
        >
          {styles.label}
        </span>
        {renovacao.reajuste_sugerido_pct !== null && (
          <span className="text-[11px] text-brand-700">
            sugestão:{" "}
            <strong className="text-accent-700">
              +{renovacao.reajuste_sugerido_pct}%
            </strong>
          </span>
        )}
        <span className="text-[11px] text-brand-600 ml-auto">
          margem atual {renovacao.margem_atual_pct}%
        </span>
      </div>
    </div>
  );
}

// =============================================================================
// Card wrapper
// =============================================================================

function Card({
  title,
  subtitle,
  children,
}: {
  title: React.ReactNode;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white border border-brand-100 rounded-xl p-5 shadow-sm">
      <header className="mb-4 pb-3 border-b border-brand-100">
        <h2 className="text-base font-bold text-brand-950">{title}</h2>
        {subtitle && (
          <p className="text-xs text-brand-600 mt-0.5">{subtitle}</p>
        )}
      </header>
      {children}
    </section>
  );
}
