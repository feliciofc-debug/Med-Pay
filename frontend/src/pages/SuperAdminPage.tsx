/**
 * Painel Super Admin — visão "dona da MedPag".
 *
 * Mostra MRR, ARR, ARPU, contagens por status, distribuição por plano
 * e tabela detalhada de clientes com health score (verde/amarelo/vermelho).
 *
 * Restrito a role ADMIN. Quando criarmos role SUPER_ADMIN separada,
 * trocamos a guarda.
 */

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  Building2,
  Calendar,
  Circle,
  Clock,
  DollarSign,
  PauseCircle,
  Sparkles,
  TrendingUp,
  Users,
  XCircle,
} from "lucide-react";

import { api } from "@/lib/api";
import type {
  ClienteOverview,
  HealthScore,
  MetricasSaaS,
  StatusAssinatura,
} from "@/types";

function formatBRL(centavos: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(centavos / 100);
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

function daysAgo(iso: string | null): string {
  if (!iso) return "nunca";
  const dias = Math.floor(
    (Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24),
  );
  if (dias === 0) return "hoje";
  if (dias === 1) return "ontem";
  return `há ${dias}d`;
}

const STATUS_LABEL: Record<StatusAssinatura, string> = {
  TRIAL: "Trial",
  ATIVO: "Ativo",
  INADIMPLENTE: "Inadimplente",
  SUSPENSO: "Suspenso",
  CANCELADO: "Cancelado",
};

const STATUS_BADGE: Record<StatusAssinatura, string> = {
  TRIAL: "bg-blue-100 text-blue-800 border-blue-300",
  ATIVO: "bg-emerald-100 text-emerald-800 border-emerald-300",
  INADIMPLENTE: "bg-amber-100 text-amber-800 border-amber-300",
  SUSPENSO: "bg-red-100 text-red-800 border-red-300",
  CANCELADO: "bg-slate-100 text-slate-700 border-slate-300",
};

const HEALTH_DOT: Record<HealthScore, string> = {
  VERDE: "text-emerald-500 fill-emerald-500",
  AMARELO: "text-amber-500 fill-amber-500",
  VERMELHO: "text-red-500 fill-red-500",
  CINZA: "text-slate-300 fill-slate-300",
};

const HEALTH_LABEL: Record<HealthScore, string> = {
  VERDE: "Saudável",
  AMARELO: "Atenção",
  VERMELHO: "Risco",
  CINZA: "Inativo",
};

export function SuperAdminPage() {
  const { data: metricas } = useQuery({
    queryKey: ["super-admin", "metricas"],
    queryFn: async () => {
      const { data } = await api.get<MetricasSaaS>(
        "/api/super-admin/metricas",
      );
      return data;
    },
    refetchInterval: 60_000, // atualiza a cada minuto
  });

  const { data: clientes = [] } = useQuery({
    queryKey: ["super-admin", "clientes"],
    queryFn: async () => {
      const { data } = await api.get<ClienteOverview[]>(
        "/api/super-admin/clientes",
      );
      return data;
    },
    refetchInterval: 60_000,
  });

  const clientesPorSaude = {
    VERDE: clientes.filter((c) => c.health_score === "VERDE").length,
    AMARELO: clientes.filter((c) => c.health_score === "AMARELO").length,
    VERMELHO: clientes.filter((c) => c.health_score === "VERMELHO").length,
    CINZA: clientes.filter((c) => c.health_score === "CINZA").length,
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
          <TrendingUp className="text-brand-600" size={26} />
          Super Admin — Visão MedPag
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Métricas comerciais da plataforma. Atualiza automaticamente a
          cada minuto.
        </p>
      </header>

      {/* ============ Métricas de receita ============ */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <CardMetrica
          icone={<DollarSign size={20} />}
          label="MRR"
          valor={metricas ? formatBRL(metricas.mrr_centavos) : "—"}
          subtitulo="receita recorrente mensal"
          destaque="brand"
        />
        <CardMetrica
          icone={<TrendingUp size={20} />}
          label="ARR"
          valor={metricas ? formatBRL(metricas.arr_centavos) : "—"}
          subtitulo="receita anual projetada"
        />
        <CardMetrica
          icone={<Users size={20} />}
          label="ARPU"
          valor={metricas ? formatBRL(metricas.arpu_centavos) : "—"}
          subtitulo="receita média por cliente"
        />
        <CardMetrica
          icone={<Sparkles size={20} />}
          label="Receita em trial"
          valor={metricas ? formatBRL(metricas.receita_potencial_trial) : "—"}
          subtitulo="se converterem"
          destaque="azul"
        />
      </section>

      {/* ============ Contagens ============ */}
      <section className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <ContagemPill
          icone={<Building2 size={14} />}
          label="Total"
          valor={metricas?.clientes_total ?? "—"}
          cor="slate"
        />
        <ContagemPill
          icone={<TrendingUp size={14} />}
          label="Pagantes"
          valor={metricas?.clientes_pagantes ?? "—"}
          cor="emerald"
        />
        <ContagemPill
          icone={<Sparkles size={14} />}
          label="Trial"
          valor={metricas?.clientes_trial ?? "—"}
          cor="blue"
        />
        <ContagemPill
          icone={<PauseCircle size={14} />}
          label="Suspensos"
          valor={metricas?.clientes_suspensos ?? "—"}
          cor="red"
        />
        <ContagemPill
          icone={<XCircle size={14} />}
          label="Cancelados"
          valor={metricas?.clientes_cancelados ?? "—"}
          cor="slate"
        />
      </section>

      {/* ============ Funil + Alertas ============ */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <Calendar size={16} /> Funil do mês
          </h3>
          <div className="mt-4 grid grid-cols-3 gap-3 text-center">
            <div>
              <p className="text-3xl font-bold text-emerald-600">
                {metricas?.novos_no_mes ?? "—"}
              </p>
              <p className="text-xs text-slate-500 mt-1">novos no mês</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-slate-700">
                {metricas?.novos_30d ?? "—"}
              </p>
              <p className="text-xs text-slate-500 mt-1">novos em 30 dias</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-red-600">
                {metricas?.cancelados_no_mes ?? "—"}
              </p>
              <p className="text-xs text-slate-500 mt-1">churn no mês</p>
            </div>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <AlertTriangle size={16} /> Atenção
          </h3>
          <div className="mt-4 space-y-2 text-sm">
            <AlertaLinha
              cor="azul"
              label="Trials vencendo em 7 dias"
              valor={metricas?.trials_vencendo_7d ?? 0}
            />
            <AlertaLinha
              cor="vermelho"
              label="Clientes em risco (vermelho)"
              valor={clientesPorSaude.VERMELHO}
            />
            <AlertaLinha
              cor="amarelo"
              label="Clientes em atenção (amarelo)"
              valor={clientesPorSaude.AMARELO}
            />
          </div>
        </div>
      </section>

      {/* ============ Distribuição por plano ============ */}
      <section className="card p-5">
        <h3 className="font-semibold text-slate-800 mb-4">
          Distribuição por plano
        </h3>
        <div className="space-y-2">
          {metricas?.distribuicao_plano.map((d) => {
            const total = metricas.clientes_total || 1;
            const pct = Math.round((d.count / total) * 100);
            return (
              <div key={d.slug} className="flex items-center gap-3">
                <p className="w-32 text-sm font-medium text-slate-700 shrink-0">
                  {d.nome}
                </p>
                <div className="flex-1 bg-slate-100 h-6 rounded-md relative overflow-hidden">
                  <div
                    className="h-full bg-brand-500 transition-all"
                    style={{ width: `${pct}%` }}
                  />
                  <span className="absolute inset-0 flex items-center justify-end pr-2 text-xs font-medium text-slate-700">
                    {d.count} cliente{d.count === 1 ? "" : "s"} · {pct}%
                  </span>
                </div>
                <p className="w-32 text-right text-sm tabular-nums text-slate-600 shrink-0">
                  {formatBRL(d.mrr_centavos)}
                </p>
              </div>
            );
          })}
          {!metricas?.distribuicao_plano.length && (
            <p className="text-sm text-slate-500">
              Sem clientes cadastrados ainda.
            </p>
          )}
        </div>
      </section>

      {/* ============ Tabela de clientes ============ */}
      <section className="card p-0 overflow-hidden">
        <header className="px-5 py-4 border-b border-slate-200">
          <h3 className="font-semibold text-slate-800">
            Clientes — visão consolidada
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Health score combina status, uso recente e último login.
          </p>
        </header>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-5 py-3"></th>
              <th className="px-5 py-3">Cliente</th>
              <th className="px-5 py-3">Plano</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3 text-right">MRR</th>
              <th className="px-5 py-3 text-right">Lotes 30d</th>
              <th className="px-5 py-3">Último login</th>
              <th className="px-5 py-3">Sinais</th>
            </tr>
          </thead>
          <tbody>
            {clientes.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="px-5 py-8 text-center text-slate-500"
                >
                  Sem clientes ainda.
                </td>
              </tr>
            )}
            {clientes.map((c) => (
              <tr
                key={c.id}
                className="border-b border-slate-100 last:border-0 hover:bg-slate-50/50"
              >
                <td className="px-5 py-3">
                  <Circle
                    size={11}
                    className={HEALTH_DOT[c.health_score]}
                    aria-label={HEALTH_LABEL[c.health_score]}
                  />
                </td>
                <td className="px-5 py-3">
                  <p className="font-medium text-slate-900">{c.nome}</p>
                  <p className="text-xs text-slate-400">{c.cnpj ?? "—"}</p>
                </td>
                <td className="px-5 py-3 text-slate-700">
                  {c.plano_nome ?? (
                    <span className="italic text-slate-400 text-xs">
                      sem plano
                    </span>
                  )}
                </td>
                <td className="px-5 py-3">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${
                      STATUS_BADGE[c.status_assinatura]
                    }`}
                  >
                    {STATUS_LABEL[c.status_assinatura]}
                  </span>
                  {c.status_assinatura === "TRIAL" && c.trial_termina_em && (
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      até {formatDate(c.trial_termina_em)}
                    </p>
                  )}
                </td>
                <td className="px-5 py-3 text-right tabular-nums text-slate-700">
                  {formatBRL(c.mrr_centavos)}
                </td>
                <td className="px-5 py-3 text-right text-slate-700 tabular-nums">
                  {c.lotes_30d}
                </td>
                <td className="px-5 py-3 text-slate-500 text-xs">
                  <span className="flex items-center gap-1">
                    <Clock size={11} /> {daysAgo(c.ultimo_login)}
                  </span>
                </td>
                <td className="px-5 py-3 text-xs text-slate-500 max-w-[220px]">
                  {c.sinais.slice(0, 2).join("; ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

// ============================================================
// Subcomponentes
// ============================================================

function CardMetrica({
  icone,
  label,
  valor,
  subtitulo,
  destaque,
}: {
  icone: React.ReactNode;
  label: string;
  valor: string | number;
  subtitulo: string;
  destaque?: "brand" | "azul";
}) {
  const cor =
    destaque === "brand"
      ? "from-brand-50 to-white border-brand-200"
      : destaque === "azul"
        ? "from-blue-50 to-white border-blue-200"
        : "from-white to-white border-slate-200";
  return (
    <div className={`card p-5 bg-gradient-to-br ${cor}`}>
      <div className="flex items-center gap-2 text-slate-600 text-xs uppercase tracking-wider font-medium">
        {icone}
        {label}
      </div>
      <p className="mt-2 text-2xl font-bold text-slate-900 tabular-nums">
        {valor}
      </p>
      <p className="text-xs text-slate-500 mt-1">{subtitulo}</p>
    </div>
  );
}

function ContagemPill({
  icone,
  label,
  valor,
  cor,
}: {
  icone: React.ReactNode;
  label: string;
  valor: number | string;
  cor: "slate" | "emerald" | "blue" | "red" | "amber";
}) {
  const map: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 border-slate-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
    blue: "bg-blue-50 text-blue-800 border-blue-200",
    red: "bg-red-50 text-red-800 border-red-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
  };
  return (
    <div className={`px-4 py-3 rounded-lg border ${map[cor]}`}>
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider font-medium opacity-80">
        {icone}
        {label}
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{valor}</p>
    </div>
  );
}

function AlertaLinha({
  cor,
  label,
  valor,
}: {
  cor: "azul" | "vermelho" | "amarelo";
  label: string;
  valor: number;
}) {
  const map = {
    azul: { fundo: "bg-blue-50", borda: "border-blue-200", texto: "text-blue-900" },
    vermelho: { fundo: "bg-red-50", borda: "border-red-200", texto: "text-red-900" },
    amarelo: {
      fundo: "bg-amber-50",
      borda: "border-amber-200",
      texto: "text-amber-900",
    },
  };
  const c = map[cor];
  return (
    <div
      className={`flex items-center justify-between px-3 py-2 rounded-md border ${c.fundo} ${c.borda} ${c.texto}`}
    >
      <span className="flex items-center gap-2 text-sm">
        <AlertCircle size={14} />
        {label}
      </span>
      <span className="font-bold tabular-nums">{valor}</span>
    </div>
  );
}
