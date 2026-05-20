import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Building2,
  Calculator,
  CheckCircle2,
  Percent,
  Receipt,
  Save,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn, formatBRL } from "@/lib/utils";
import type {
  ConfiguracaoCobranca,
  ConfiguracaoCusto,
  ContratoConfig,
} from "@/types";

// =============================================================================
// Helpers de cálculo (mesma lógica do backend, espelhada no frontend)
// =============================================================================

function calcularReceita(
  cobranca: ConfiguracaoCobranca,
  pagamentosMes: number,
): number {
  const variavelVolume = Math.round(
    (cobranca.volume_medio_mensal_centavos * cobranca.percentual_volume_bp) /
      10_000,
  );
  return (
    cobranca.mensalidade_centavos +
    pagamentosMes * cobranca.taxa_por_pagamento_centavos +
    variavelVolume
  );
}

function calcularCusto(
  custo: ConfiguracaoCusto,
  receitaCentavos: number,
): number {
  return (
    custo.custo_fixo_mensal_centavos +
    Math.round((receitaCentavos * custo.custo_variavel_pct) / 100)
  );
}

// Formata número em BRL pra input (sem prefixo)
function formatNumber(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Parse de string brasileira ("1.234,56" ou "1234.56" ou "1234,56") pra centavos
function parseToCentavos(value: string): number {
  const cleaned = value
    .replace(/[R$\s]/g, "")
    .replace(/\.(?=\d{3})/g, "")
    .replace(",", ".");
  const num = parseFloat(cleaned);
  if (isNaN(num)) return 0;
  return Math.round(num * 100);
}

// =============================================================================
// Página
// =============================================================================

export function ContratosPage() {
  const { data: contratos = [], isLoading } = useQuery({
    queryKey: ["contratos"],
    queryFn: async () => {
      const { data } = await api.get<ContratoConfig[]>("/api/contratos");
      return data;
    },
  });

  const [editandoId, setEditandoId] = useState<string | null>(null);
  const editando =
    editandoId !== null
      ? contratos.find((c) => c.cliente_id === editandoId) ?? null
      : null;

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between border-b border-brand-100 pb-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.15em] text-accent-700 uppercase mb-2">
            <Briefcase size={14} className="text-accent-500" />
            Configuração comercial
          </div>
          <h1 className="text-3xl font-bold text-brand-950 tracking-tight">
            Contratos &amp; tabela de cobrança
          </h1>
          <p className="text-sm text-brand-700 mt-1">
            Defina como você cobra de cada cliente. O Dashboard Executivo recalcula a margem na hora.
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="text-brand-700 py-12 text-center">Carregando contratos…</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {contratos.map((contrato) => (
          <ContratoCard
            key={contrato.cliente_id}
            contrato={contrato}
            onEdit={() => setEditandoId(contrato.cliente_id)}
          />
        ))}
      </div>

      {editando && (
        <EditarContratoModal
          contrato={editando}
          onClose={() => setEditandoId(null)}
        />
      )}
    </div>
  );
}

// =============================================================================
// Card de contrato (somente leitura)
// =============================================================================

function ContratoCard({
  contrato,
  onEdit,
}: {
  contrato: ContratoConfig;
  onEdit: () => void;
}) {
  // estimativa estática usando volume médio configurado
  const receitaEstimada = calcularReceita(contrato.cobranca, 0);
  const custoEstimado = calcularCusto(contrato.custo, receitaEstimada);
  const lucroEstimado = receitaEstimada - custoEstimado;
  const margemEstimada =
    receitaEstimada > 0
      ? Math.round((lucroEstimado / receitaEstimada) * 100)
      : 0;

  return (
    <div className="bg-white border border-brand-100 rounded-xl shadow-sm overflow-hidden">
      <div className="bg-gradient-to-r from-brand-950 to-brand-800 text-white p-5 relative">
        <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-accent-400 to-accent-500" />
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-lg bg-brand-900 border border-accent-400/40 flex items-center justify-center text-accent-300">
            <Building2 size={20} />
          </div>
          <div>
            <h3 className="font-bold text-lg">{contrato.cliente_nome}</h3>
            <p className="text-xs text-brand-100/70">
              {contrato.cliente_cnpj ?? "CNPJ não informado"}
            </p>
          </div>
        </div>
      </div>

      <div className="p-5 space-y-4">
        <ResumoCobranca cobranca={contrato.cobranca} />

        <div className="grid grid-cols-3 gap-2">
          <MiniStat
            label="Receita estimada"
            value={formatBRL(receitaEstimada)}
            color="brand"
          />
          <MiniStat
            label="Custo"
            value={formatBRL(custoEstimado)}
            color="muted"
          />
          <MiniStat
            label="Margem"
            value={`${margemEstimada}%`}
            color={
              margemEstimada >= 55
                ? "green"
                : margemEstimada >= 40
                  ? "amber"
                  : "red"
            }
          />
        </div>

        <button
          type="button"
          onClick={onEdit}
          className="w-full bg-brand-900 hover:bg-brand-800 text-white text-sm font-semibold py-2.5 rounded-lg transition flex items-center justify-center gap-2 border border-accent-400/30"
        >
          <Calculator size={16} className="text-accent-300" />
          Configurar cobrança e custo
        </button>
      </div>
    </div>
  );
}

function ResumoCobranca({ cobranca }: { cobranca: ConfiguracaoCobranca }) {
  const partes: string[] = [];
  if (cobranca.percentual_volume_bp > 0) {
    partes.push(
      `${(cobranca.percentual_volume_bp / 100).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
      })}% sobre ${formatBRL(cobranca.volume_medio_mensal_centavos)}`,
    );
  }
  if (cobranca.mensalidade_centavos > 0) {
    partes.push(`${formatBRL(cobranca.mensalidade_centavos)} fixo/mês`);
  }
  if (cobranca.taxa_por_pagamento_centavos > 0) {
    partes.push(
      `${formatBRL(cobranca.taxa_por_pagamento_centavos)} por pagamento`,
    );
  }
  if (partes.length === 0) {
    partes.push("Sem cobrança configurada");
  }

  return (
    <div className="bg-brand-50 border border-brand-100 rounded-lg p-3 text-xs">
      <div className="flex items-center gap-1.5 text-brand-700 font-semibold uppercase tracking-wide text-[10px] mb-1.5">
        <Receipt size={11} />
        Modelo de cobrança
      </div>
      <div className="text-brand-950 font-medium leading-relaxed">
        {partes.join(" + ")}
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: "brand" | "green" | "amber" | "red" | "muted";
}) {
  const colorClass = {
    brand: "text-brand-950",
    green: "text-emerald-700",
    amber: "text-accent-700",
    red: "text-red-700",
    muted: "text-brand-700",
  }[color];

  return (
    <div className="bg-brand-50/50 border border-brand-100 rounded-lg p-2.5">
      <div className="text-[9px] font-bold uppercase tracking-[0.1em] text-brand-600">
        {label}
      </div>
      <div className={cn("text-base font-bold mt-0.5", colorClass)}>{value}</div>
    </div>
  );
}

// =============================================================================
// Modal de edição com pré-visualização ao vivo
// =============================================================================

function EditarContratoModal({
  contrato,
  onClose,
}: {
  contrato: ContratoConfig;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const [draft, setDraft] = useState<ContratoConfig>(contrato);

  useEffect(() => {
    setDraft(contrato);
  }, [contrato]);

  const mutation = useMutation({
    mutationFn: async (payload: ContratoConfig) => {
      const { data } = await api.put<ContratoConfig>(
        `/api/contratos/${payload.cliente_id}`,
        payload,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["contratos"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "executivo"] });
      onClose();
    },
  });

  const updateCobranca = (patch: Partial<ConfiguracaoCobranca>) =>
    setDraft((d) => ({ ...d, cobranca: { ...d.cobranca, ...patch } }));
  const updateCusto = (patch: Partial<ConfiguracaoCusto>) =>
    setDraft((d) => ({ ...d, custo: { ...d.custo, ...patch } }));

  // Preview
  const receita = calcularReceita(draft.cobranca, 0);
  const custo = calcularCusto(draft.custo, receita);
  const lucro = receita - custo;
  const margem = receita > 0 ? Math.round((lucro / receita) * 100) : 0;
  const meta = draft.meta_mensal_centavos;
  const metaPct = meta > 0 ? Math.round((receita / meta) * 100) : 0;

  return (
    <div className="fixed inset-0 z-50 bg-brand-950/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[92vh] overflow-y-auto border border-accent-300/40">
        {/* Header */}
        <div className="bg-gradient-to-r from-brand-950 to-brand-800 text-white p-5 sticky top-0 z-10 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold tracking-[0.15em] text-accent-300 uppercase">
              Editar contrato
            </div>
            <h2 className="text-xl font-bold mt-0.5">{contrato.cliente_nome}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/70 hover:text-white p-2 rounded-lg hover:bg-white/10 transition"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body — grid 2 colunas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
          {/* Coluna esquerda: configurações */}
          <div className="p-6 space-y-6 border-r border-brand-100">
            <Section
              title="Como você cobra desse cliente"
              subtitle="Combine livremente os 3 modelos. Deixe em zero o que não usa."
              icon={Receipt}
            >
              <CampoCobranca
                label="Percentual sobre volume movimentado"
                hint="Ex.: 1,20% do total que o cliente passa pra você processar"
                children={
                  <div className="grid grid-cols-2 gap-2">
                    <CampoNumero
                      label="% (em pontos)"
                      sufixo="%"
                      value={(draft.cobranca.percentual_volume_bp / 100).toFixed(2)}
                      onChange={(v) => {
                        const num = parseFloat(v.replace(",", "."));
                        updateCobranca({
                          percentual_volume_bp: isNaN(num)
                            ? 0
                            : Math.round(num * 100),
                        });
                      }}
                    />
                    <CampoNumero
                      label="Volume médio/mês"
                      prefixo="R$"
                      value={formatNumber(
                        draft.cobranca.volume_medio_mensal_centavos,
                      )}
                      onChange={(v) =>
                        updateCobranca({
                          volume_medio_mensal_centavos: parseToCentavos(v),
                        })
                      }
                    />
                  </div>
                }
              />

              <CampoCobranca
                label="Mensalidade fixa"
                hint="Valor fechado independente de volume"
                children={
                  <CampoNumero
                    prefixo="R$"
                    value={formatNumber(draft.cobranca.mensalidade_centavos)}
                    onChange={(v) =>
                      updateCobranca({
                        mensalidade_centavos: parseToCentavos(v),
                      })
                    }
                  />
                }
              />

              <CampoCobranca
                label="Taxa por pagamento processado"
                hint="Cobrança variável por cada CPF/CNPJ pago"
                children={
                  <CampoNumero
                    prefixo="R$"
                    value={formatNumber(
                      draft.cobranca.taxa_por_pagamento_centavos,
                    )}
                    onChange={(v) =>
                      updateCobranca({
                        taxa_por_pagamento_centavos: parseToCentavos(v),
                      })
                    }
                  />
                }
              />
            </Section>

            <Section
              title="Quanto te custa atender esse cliente"
              subtitle="Custos diretos do BPO em cima desse contrato."
              icon={Wallet}
            >
              <CampoCobranca
                label="Custo fixo mensal"
                hint="Mão de obra dedicada, ferramentas, etc."
                children={
                  <CampoNumero
                    prefixo="R$"
                    value={formatNumber(
                      draft.custo.custo_fixo_mensal_centavos,
                    )}
                    onChange={(v) =>
                      updateCusto({
                        custo_fixo_mensal_centavos: parseToCentavos(v),
                      })
                    }
                  />
                }
              />
              <CampoCobranca
                label="Custo variável (% da receita)"
                hint="Tarifas de banco, infraestrutura, etc."
                children={
                  <CampoNumero
                    sufixo="%"
                    value={String(draft.custo.custo_variavel_pct)}
                    onChange={(v) => {
                      const num = parseFloat(v.replace(",", "."));
                      updateCusto({
                        custo_variavel_pct: isNaN(num)
                          ? 0
                          : Math.round(num * 100) / 100,
                      });
                    }}
                  />
                }
              />
            </Section>

            <Section title="Meta mensal" icon={TrendingUp}>
              <CampoNumero
                prefixo="R$"
                value={formatNumber(draft.meta_mensal_centavos)}
                onChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    meta_mensal_centavos: parseToCentavos(v),
                  }))
                }
              />
            </Section>
          </div>

          {/* Coluna direita: pré-visualização */}
          <div className="p-6 bg-brand-50/30 space-y-4">
            <div>
              <div className="text-[10px] font-bold tracking-[0.15em] text-accent-700 uppercase mb-1">
                Pré-visualização
              </div>
              <h3 className="text-base font-bold text-brand-950">
                Resultado mensal estimado
              </h3>
              <p className="text-xs text-brand-600 mt-0.5">
                Atualiza ao vivo conforme você ajusta os campos.
              </p>
            </div>

            <PreviewCard
              label="Receita do mês"
              value={formatBRL(receita)}
              icon={Receipt}
              variant="primary"
              detail={detalheReceita(draft.cobranca)}
            />

            <PreviewCard
              label="Custo operacional"
              value={formatBRL(custo)}
              icon={Wallet}
              detail={detalheCusto(draft.custo, receita)}
            />

            <PreviewCard
              label="Lucro líquido"
              value={formatBRL(lucro)}
              icon={CheckCircle2}
              variant="gold"
              detail={`Receita − Custo`}
            />

            <PreviewCard
              label="Margem de lucro"
              value={`${margem}%`}
              icon={Percent}
              variant={
                margem >= 55 ? "green" : margem >= 40 ? "amber" : "red"
              }
              detail={
                margem >= 55
                  ? "Saudável"
                  : margem >= 40
                    ? "Atenção — revisar"
                    : "Crítico — renegociar urgente"
              }
            />

            <div className="border-t border-brand-200 pt-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-brand-700">
                  Meta atingida
                </span>
                <span className="text-xs font-bold text-brand-950">
                  {metaPct}% de {formatBRL(meta)}
                </span>
              </div>
              <div className="h-2 bg-brand-100 rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    metaPct >= 100
                      ? "bg-emerald-500"
                      : metaPct >= 80
                        ? "bg-accent-500"
                        : "bg-brand-500",
                  )}
                  style={{ width: `${Math.min(metaPct, 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-brand-100 p-4 flex items-center justify-end gap-2 bg-white sticky bottom-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-semibold text-brand-700 hover:text-brand-950 transition"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => mutation.mutate(draft)}
            disabled={mutation.isPending}
            className="px-4 py-2 text-sm font-bold bg-accent-500 hover:bg-accent-400 text-brand-950 rounded-lg transition flex items-center gap-2 disabled:opacity-60"
          >
            <Save size={15} />
            {mutation.isPending ? "Salvando…" : "Salvar contrato"}
          </button>
        </div>
      </div>
    </div>
  );
}

function detalheReceita(cobranca: ConfiguracaoCobranca): string {
  const partes: string[] = [];
  if (cobranca.percentual_volume_bp > 0) {
    const pct = (cobranca.percentual_volume_bp / 100).toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
    });
    partes.push(
      `${pct}% × ${formatBRL(cobranca.volume_medio_mensal_centavos)}`,
    );
  }
  if (cobranca.mensalidade_centavos > 0) {
    partes.push(`${formatBRL(cobranca.mensalidade_centavos)} fixo`);
  }
  if (cobranca.taxa_por_pagamento_centavos > 0) {
    partes.push(`+ R$ por pagamento processado`);
  }
  return partes.length > 0 ? partes.join(" · ") : "Sem cobrança configurada";
}

function detalheCusto(
  custo: ConfiguracaoCusto,
  receitaCentavos: number,
): string {
  const partes: string[] = [];
  if (custo.custo_fixo_mensal_centavos > 0) {
    partes.push(`${formatBRL(custo.custo_fixo_mensal_centavos)} fixo`);
  }
  if (custo.custo_variavel_pct > 0) {
    const variavel = Math.round(
      (receitaCentavos * custo.custo_variavel_pct) / 100,
    );
    partes.push(`${custo.custo_variavel_pct}% (${formatBRL(variavel)})`);
  }
  return partes.length > 0 ? partes.join(" + ") : "Sem custo configurado";
}

// =============================================================================
// Componentes de UI
// =============================================================================

function Section({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-accent-100 border border-accent-200 flex items-center justify-center text-accent-700 mt-0.5">
          <Icon size={14} />
        </div>
        <div>
          <h4 className="text-sm font-bold text-brand-950">{title}</h4>
          {subtitle && (
            <p className="text-[11px] text-brand-600 mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>
      <div className="pl-9 space-y-3">{children}</div>
    </div>
  );
}

function CampoCobranca({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[12px] font-semibold text-brand-800 mb-1">
        {label}
      </div>
      {children}
      {hint && (
        <div className="text-[10px] text-brand-600 mt-1 italic">{hint}</div>
      )}
    </div>
  );
}

function CampoNumero({
  label,
  value,
  onChange,
  prefixo,
  sufixo,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  prefixo?: string;
  sufixo?: string;
}) {
  return (
    <div>
      {label && (
        <div className="text-[10px] font-semibold text-brand-600 mb-0.5">
          {label}
        </div>
      )}
      <div className="flex items-stretch border border-brand-200 rounded-lg overflow-hidden focus-within:border-accent-500 focus-within:ring-2 focus-within:ring-accent-100 transition bg-white">
        {prefixo && (
          <span className="px-3 flex items-center bg-brand-50 text-brand-600 text-xs font-semibold border-r border-brand-200">
            {prefixo}
          </span>
        )}
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-3 py-2 text-sm font-medium text-brand-950 outline-none bg-transparent"
        />
        {sufixo && (
          <span className="px-3 flex items-center bg-brand-50 text-brand-600 text-xs font-semibold border-l border-brand-200">
            {sufixo}
          </span>
        )}
      </div>
    </div>
  );
}

function PreviewCard({
  label,
  value,
  icon: Icon,
  detail,
  variant = "default",
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  detail?: string;
  variant?: "default" | "primary" | "gold" | "green" | "amber" | "red";
}) {
  const styles = {
    default: "bg-white border-brand-100 text-brand-950",
    primary: "bg-white border-brand-100 text-brand-950",
    gold:
      "bg-gradient-to-br from-accent-50 to-white border-accent-300 text-brand-950",
    green: "bg-emerald-50 border-emerald-200 text-emerald-900",
    amber: "bg-accent-50 border-accent-200 text-accent-900",
    red: "bg-red-50 border-red-200 text-red-900",
  }[variant];

  const iconStyles = {
    default: "bg-brand-50 text-brand-700 border-brand-200",
    primary: "bg-brand-100 text-brand-800 border-brand-200",
    gold: "bg-accent-500 text-white border-accent-500",
    green: "bg-emerald-100 text-emerald-700 border-emerald-200",
    amber: "bg-accent-100 text-accent-700 border-accent-200",
    red: "bg-red-100 text-red-700 border-red-200",
  }[variant];

  return (
    <div className={cn("rounded-lg border p-3 flex items-center gap-3", styles)}>
      <div
        className={cn(
          "w-9 h-9 rounded-lg border flex items-center justify-center flex-shrink-0",
          iconStyles,
        )}
      >
        <Icon size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-bold uppercase tracking-[0.1em] opacity-70">
          {label}
        </div>
        <div className="text-xl font-bold tracking-tight leading-tight">
          {value}
        </div>
        {detail && (
          <div className="text-[10px] opacity-70 mt-0.5 truncate">{detail}</div>
        )}
      </div>
    </div>
  );
}
