/**
 * SCP — Sociedade em Conta de Participação (`/app/scp`).
 *
 * Tela do modelo de negócio MEDPAG_REPASSE: a MedPag opera como sócia
 * ostensiva e os médicos são participantes que recebem DISTRIBUIÇÃO DE
 * RESULTADO (não pagamento por serviço).
 *
 * Fluxo:
 *   1. Cadastra os participantes (médicos) e a regra de cota de cada um.
 *   2. Lança a apuração do mês (receita − custos = resultado).
 *   3. Calcula a distribuição → quanto cada médico recebe.
 *
 * O dinheiro sai por banco tradicional (a distribuição vira lote/CNAB).
 * Nada passa pela MedPag.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calculator, HandCoins, Loader2, Plus, Users } from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { formatBRL } from "@/lib/utils";
import type {
  ApuracaoSCP,
  ParticipanteSCP,
  RegraCota,
} from "@/types";

const REGRA_LABEL: Record<RegraCota, string> = {
  PERCENTUAL_FIXO: "% fixo",
  PROPORCIONAL_SERVICO: "Proporcional ao serviço",
  POR_APORTE: "Por aporte",
};

function competenciaAtual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function reaisParaCentavos(v: string): number {
  const n = parseFloat(v.replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export function ScpPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Tenant da SCP: o cliente do usuário; admin (sem cliente) informa o id.
  const [scpClienteId, setScpClienteId] = useState<string>(
    user?.cliente_id ?? "",
  );
  const podeOperar = scpClienteId.trim().length > 0;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold text-slate-900 mb-1 flex items-center gap-2">
          <HandCoins size={22} className="text-brand-700" />
          SCP — Sociedade em Conta de Participação
        </h1>
        <p className="text-sm text-slate-500 max-w-3xl">
          A MedPag opera como sócia ostensiva; os médicos são participantes e
          recebem <strong>distribuição de resultado</strong>. O repasse sai por
          banco tradicional — nada passa pela MedPag.
        </p>
      </header>

      {!user?.cliente_id && (
        <div className="card border-amber-200 bg-amber-50">
          <label className="block text-sm font-medium text-amber-900 mb-1">
            ID do cliente SCP (tenant tipo MEDPAG_REPASSE)
          </label>
          <p className="text-xs text-amber-700 mb-2">
            Você é MedPag interno (sem cliente fixo). Informe o ID do cliente
            SCP que quer operar.
          </p>
          <input
            type="text"
            value={scpClienteId}
            onChange={(e) => setScpClienteId(e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            className="w-full max-w-md border border-amber-300 rounded-lg px-3 py-2 text-sm font-mono"
          />
        </div>
      )}

      {podeOperar && (
        <>
          <ApuracaoCard clienteId={scpClienteId} />
          <ParticipantesCard
            clienteId={scpClienteId}
            onChanged={() =>
              void queryClient.invalidateQueries({
                queryKey: ["scp-participantes", scpClienteId],
              })
            }
          />
        </>
      )}
    </div>
  );
}

// ============================================================
// Apuração + distribuição
// ============================================================

function ApuracaoCard({ clienteId }: { clienteId: string }) {
  const queryClient = useQueryClient();
  const [competencia, setCompetencia] = useState(competenciaAtual());
  const [receita, setReceita] = useState("");
  const [custos, setCustos] = useState("");
  const [apuracao, setApuracao] = useState<ApuracaoSCP | null>(null);

  const salvarMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ApuracaoSCP>(
        `/api/scp/${clienteId}/apuracoes`,
        {
          competencia,
          receita_bruta_centavos: reaisParaCentavos(receita),
          custos_centavos: reaisParaCentavos(custos),
        },
      );
      return data;
    },
    onSuccess: (data) => setApuracao(data),
    onError: (err) => alert(getErrorMessage(err)),
  });

  const distribuirMutation = useMutation({
    mutationFn: async (apuracaoId: string) => {
      const { data } = await api.post<ApuracaoSCP>(
        `/api/scp/apuracoes/${apuracaoId}/distribuir`,
        { bases_servico: {} },
      );
      return data;
    },
    onSuccess: (data) => {
      setApuracao(data);
      void queryClient.invalidateQueries({
        queryKey: ["scp-participantes", clienteId],
      });
    },
    onError: (err) => alert(getErrorMessage(err)),
  });

  const resultado = apuracao?.resultado_centavos ?? 0;

  return (
    <div className="card">
      <h2 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
        <Calculator size={18} className="text-brand-700" />
        Apuração do período
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Competência (AAAA-MM)
          </label>
          <input
            type="text"
            value={competencia}
            onChange={(e) => setCompetencia(e.target.value)}
            placeholder="2026-05"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Receita bruta (R$)
          </label>
          <input
            type="text"
            value={receita}
            onChange={(e) => setReceita(e.target.value)}
            placeholder="0,00"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm text-right"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Custos (R$)
          </label>
          <input
            type="text"
            value={custos}
            onChange={(e) => setCustos(e.target.value)}
            placeholder="0,00"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm text-right"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-4">
        <button
          type="button"
          className="btn-primary"
          disabled={salvarMutation.isPending}
          onClick={() => salvarMutation.mutate()}
        >
          {salvarMutation.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Calculator size={16} />
          )}
          Apurar resultado
        </button>

        {apuracao && (
          <>
            <div className="text-sm text-slate-600">
              Resultado distribuível:{" "}
              <strong className="text-brand-800">{formatBRL(resultado)}</strong>{" "}
              <span className="text-xs text-slate-400">
                ({apuracao.status})
              </span>
            </div>
            <button
              type="button"
              className="btn-secondary"
              disabled={distribuirMutation.isPending || resultado <= 0}
              onClick={() => distribuirMutation.mutate(apuracao.id)}
            >
              {distribuirMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <HandCoins size={16} />
              )}
              Calcular distribuição
            </button>
          </>
        )}
      </div>

      {apuracao && apuracao.distribuicoes.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500 border-b">
                <th className="py-2">Médico (beneficiário)</th>
                <th className="py-2 text-right">Base</th>
                <th className="py-2 text-right">% aplicado</th>
                <th className="py-2 text-right">Valor</th>
              </tr>
            </thead>
            <tbody>
              {apuracao.distribuicoes.map((d) => (
                <tr key={d.beneficiario_id} className="border-b last:border-0">
                  <td className="py-2 font-mono text-xs">
                    {d.beneficiario_id.slice(0, 8)}…
                  </td>
                  <td className="py-2 text-right">
                    {formatBRL(d.base_centavos)}
                  </td>
                  <td className="py-2 text-right">
                    {(d.percentual_aplicado_bp / 100).toFixed(2)}%
                  </td>
                  <td className="py-2 text-right font-semibold text-brand-800">
                    {formatBRL(d.valor_centavos)}
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
// Participantes
// ============================================================

function ParticipantesCard({
  clienteId,
  onChanged,
}: {
  clienteId: string;
  onChanged: () => void;
}) {
  const [showForm, setShowForm] = useState(false);

  const { data: participantes = [], isLoading } = useQuery({
    queryKey: ["scp-participantes", clienteId],
    queryFn: async () => {
      const { data } = await api.get<ParticipanteSCP[]>(
        `/api/scp/${clienteId}/participantes`,
      );
      return data;
    },
    enabled: clienteId.length > 0,
  });

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-slate-900 flex items-center gap-2">
          <Users size={18} className="text-brand-700" />
          Participantes ({participantes.length})
        </h2>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus size={16} />
          Novo participante
        </button>
      </div>

      {showForm && (
        <NovoParticipanteForm
          clienteId={clienteId}
          onSaved={() => {
            setShowForm(false);
            onChanged();
          }}
        />
      )}

      {isLoading ? (
        <div className="text-center text-slate-500 py-6">Carregando...</div>
      ) : participantes.length === 0 ? (
        <p className="text-sm text-slate-500 py-4">
          Nenhum participante cadastrado ainda.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500 border-b">
                <th className="py-2">Médico</th>
                <th className="py-2">Regra de cota</th>
                <th className="py-2 text-right">% fixo / Aporte</th>
                <th className="py-2 text-center">Ativo</th>
              </tr>
            </thead>
            <tbody>
              {participantes.map((p) => (
                <tr key={p.id} className="border-b last:border-0">
                  <td className="py-2">
                    {p.beneficiario_nome ?? (
                      <span className="font-mono text-xs">
                        {p.beneficiario_id.slice(0, 8)}…
                      </span>
                    )}
                  </td>
                  <td className="py-2">{REGRA_LABEL[p.regra_cota]}</td>
                  <td className="py-2 text-right">
                    {p.regra_cota === "PERCENTUAL_FIXO"
                      ? `${(p.percentual_bp / 100).toFixed(2)}%`
                      : p.regra_cota === "POR_APORTE"
                        ? formatBRL(p.aporte_centavos)
                        : "—"}
                  </td>
                  <td className="py-2 text-center">{p.ativo ? "✓" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function NovoParticipanteForm({
  clienteId,
  onSaved,
}: {
  clienteId: string;
  onSaved: () => void;
}) {
  const [beneficiarioId, setBeneficiarioId] = useState("");
  const [regra, setRegra] = useState<RegraCota>("PROPORCIONAL_SERVICO");
  const [percentual, setPercentual] = useState("");
  const [aporte, setAporte] = useState("");

  // Carrega médicos do cliente pra popular o select.
  const { data: medicos = [] } = useQuery({
    queryKey: ["scp-beneficiarios", clienteId],
    queryFn: async () => {
      const { data } = await api.get<{
        items?: Array<{ id: string; nome: string; cpf_mascarado?: string }>;
      }>(`/api/beneficiarios`, {
        params: { cliente_id: clienteId, status: "ATIVO", per_page: 200 },
      });
      return data.items ?? [];
    },
    enabled: clienteId.length > 0,
  });

  const salvar = useMutation({
    mutationFn: async () => {
      await api.post(`/api/scp/${clienteId}/participantes`, {
        beneficiario_id: beneficiarioId,
        regra_cota: regra,
        percentual_bp:
          regra === "PERCENTUAL_FIXO"
            ? Math.round(parseFloat(percentual.replace(",", ".")) * 100)
            : 0,
        aporte_centavos:
          regra === "POR_APORTE" ? reaisParaCentavos(aporte) : 0,
      });
    },
    onSuccess: onSaved,
    onError: (err) => alert(getErrorMessage(err)),
  });

  return (
    <div className="border border-slate-200 rounded-lg p-4 mb-4 bg-slate-50 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Médico
          </label>
          {medicos.length > 0 ? (
            <select
              value={beneficiarioId}
              onChange={(e) => setBeneficiarioId(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
            >
              <option value="">Selecione…</option>
              {medicos.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nome} {m.cpf_mascarado ? `(${m.cpf_mascarado})` : ""}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={beneficiarioId}
              onChange={(e) => setBeneficiarioId(e.target.value)}
              placeholder="ID do beneficiário"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono"
            />
          )}
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Regra de cota
          </label>
          <select
            value={regra}
            onChange={(e) => setRegra(e.target.value as RegraCota)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="PROPORCIONAL_SERVICO">
              Proporcional ao serviço (CRM)
            </option>
            <option value="PERCENTUAL_FIXO">% fixo</option>
            <option value="POR_APORTE">Por aporte</option>
          </select>
        </div>
        {regra === "PERCENTUAL_FIXO" && (
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              % do resultado
            </label>
            <input
              type="text"
              value={percentual}
              onChange={(e) => setPercentual(e.target.value)}
              placeholder="10"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm text-right"
            />
          </div>
        )}
        {regra === "POR_APORTE" && (
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Aporte (R$)
            </label>
            <input
              type="text"
              value={aporte}
              onChange={(e) => setAporte(e.target.value)}
              placeholder="0,00"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm text-right"
            />
          </div>
        )}
      </div>
      <button
        type="button"
        className="btn-primary"
        disabled={!beneficiarioId || salvar.isPending}
        onClick={() => salvar.mutate()}
      >
        {salvar.isPending ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <Plus size={16} />
        )}
        Adicionar participante
      </button>
    </div>
  );
}
