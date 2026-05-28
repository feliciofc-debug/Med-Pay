/**
 * MedPag Vital — Dashboard.
 *
 * Tela inicial do módulo de monitoramento por sensores físicos
 * (RuView/ESP32, Aqara FP2 e simulados). Mostra:
 *   - Stats agregadas das últimas 24h (nós online, quedas, distress, eventos)
 *   - Lista de ambientes monitorados com status de cada um
 *   - Lista de nós sensores com status online/offline
 *   - Timeline em tempo real dos últimos eventos
 *
 * Auto-refresh a cada 10s (sem WebSocket por enquanto — fica pra fase 2).
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Heart,
  HeartPulse,
  Plus,
  RefreshCw,
  Signal,
  SignalZero,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type {
  AmbienteMonitorado,
  Cliente,
  EventoListResponse,
  EventoVital,
  NoComApiKey,
  NoVital,
  StatusNo,
  TipoAmbiente,
  TipoEvento,
  TipoSensor,
  VitalStats,
} from "@/types";

const STATUS_BADGE: Record<StatusNo, string> = {
  ONLINE: "bg-emerald-100 text-emerald-700 border-emerald-200",
  OFFLINE: "bg-rose-100 text-rose-700 border-rose-200",
  DEGRADADO: "bg-amber-100 text-amber-700 border-amber-200",
  NUNCA_VISTO: "bg-slate-100 text-slate-600 border-slate-200",
};

const STATUS_LABEL: Record<StatusNo, string> = {
  ONLINE: "Online",
  OFFLINE: "Offline",
  DEGRADADO: "Degradado",
  NUNCA_VISTO: "Nunca visto",
};

const TIPO_EVENTO_BADGE: Partial<Record<TipoEvento, string>> = {
  QUEDA: "bg-rose-100 text-rose-700 border-rose-300",
  POSSIVEL_DISTRESS: "bg-rose-100 text-rose-700 border-rose-300",
  RISCO_QUEDA: "bg-amber-100 text-amber-700 border-amber-300",
  ANOMALIA_INATIVIDADE: "bg-amber-100 text-amber-700 border-amber-300",
  SAIDA_CAMA: "bg-amber-100 text-amber-700 border-amber-300",
  BATIMENTO_CARDIACO: "bg-indigo-100 text-indigo-700 border-indigo-300",
  FREQUENCIA_RESPIRATORIA: "bg-indigo-100 text-indigo-700 border-indigo-300",
  PRESENCA: "bg-emerald-100 text-emerald-700 border-emerald-300",
  CONTAGEM_PESSOAS: "bg-emerald-100 text-emerald-700 border-emerald-300",
  HEARTBEAT: "bg-slate-100 text-slate-500 border-slate-200",
};

function formatValorEvento(ev: EventoVital): string {
  if (ev.tipo === "BATIMENTO_CARDIACO" && ev.valor_num !== null) {
    return `${Math.round(ev.valor_num)} bpm`;
  }
  if (ev.tipo === "FREQUENCIA_RESPIRATORIA" && ev.valor_num !== null) {
    return `${Math.round(ev.valor_num)} rpm`;
  }
  if (ev.tipo === "CONTAGEM_PESSOAS" && ev.valor_num !== null) {
    const n = Math.round(ev.valor_num);
    return `${n} ${n === 1 ? "pessoa" : "pessoas"}`;
  }
  if (ev.valor_texto) return ev.valor_texto;
  if (ev.valor_num !== null) return ev.valor_num.toFixed(2);
  return "—";
}

export function VitalDashboardPage() {
  const qc = useQueryClient();
  const [clienteId, setClienteId] = useState<string>("");
  const [showNovoAmbiente, setShowNovoAmbiente] = useState(false);
  const [showNovoNo, setShowNovoNo] = useState(false);
  const [keyRevelada, setKeyRevelada] = useState<NoComApiKey | null>(null);

  // Lista de clientes (escolher escopo)
  const { data: clientes = [] } = useQuery<Cliente[]>({
    queryKey: ["clientes-vital"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: Cliente[] }>("/api/clientes/");
      return data.clientes ?? [];
    },
  });

  // Auto-seleciona primeiro cliente
  if (!clienteId && clientes.length > 0) {
    setClienteId(clientes[0].id);
  }

  // Stats
  const { data: stats, refetch: refetchStats } = useQuery<VitalStats>({
    queryKey: ["vital-stats", clienteId],
    queryFn: async () => {
      const { data } = await api.get<VitalStats>("/api/vital/stats", {
        params: { cliente_id: clienteId },
      });
      return data;
    },
    enabled: !!clienteId,
    refetchInterval: 10_000,
  });

  // Ambientes
  const { data: ambientes = [] } = useQuery<AmbienteMonitorado[]>({
    queryKey: ["vital-ambientes", clienteId],
    queryFn: async () => {
      const { data } = await api.get<AmbienteMonitorado[]>("/api/vital/ambientes", {
        params: { cliente_id: clienteId },
      });
      return data;
    },
    enabled: !!clienteId,
  });

  // Nós
  const { data: nos = [], refetch: refetchNos } = useQuery<NoVital[]>({
    queryKey: ["vital-nos", clienteId],
    queryFn: async () => {
      const { data } = await api.get<NoVital[]>("/api/vital/nos", {
        params: { cliente_id: clienteId },
      });
      return data;
    },
    enabled: !!clienteId,
    refetchInterval: 15_000,
  });

  // Timeline (últimos eventos)
  const { data: eventos, refetch: refetchEventos } = useQuery<EventoListResponse>({
    queryKey: ["vital-eventos", clienteId],
    queryFn: async () => {
      const { data } = await api.get<EventoListResponse>("/api/vital/eventos", {
        params: { cliente_id: clienteId, limite: 50 },
      });
      return data;
    },
    enabled: !!clienteId,
    refetchInterval: 5_000,
  });

  const ambientePorId = useMemo(() => {
    const m: Record<string, AmbienteMonitorado> = {};
    for (const a of ambientes) m[a.id] = a;
    return m;
  }, [ambientes]);

  return (
    <div className="space-y-8">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-3">
            <HeartPulse className="text-rose-500" size={28} />
            MedPag Vital
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Monitoramento de presença e sinais vitais via sensores RuView/Aqara —
            sem câmera, sem invasão de privacidade.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
            value={clienteId}
            onChange={(e) => setClienteId(e.target.value)}
          >
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              void refetchStats();
              void refetchNos();
              void refetchEventos();
            }}
            className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 px-3 py-2 border border-slate-200 rounded-lg bg-white"
            title="Atualizar agora"
          >
            <RefreshCw size={16} />
            Atualizar
          </button>
        </div>
      </header>

      {/* Stats */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={<Wifi className="text-emerald-600" size={20} />}
          label="Nós online"
          value={stats ? `${stats.nos_online}/${stats.nos_total}` : "—"}
          hint={stats?.nos_offline ? `${stats.nos_offline} offline` : "todos ok"}
        />
        <StatCard
          icon={<Activity className="text-indigo-600" size={20} />}
          label="Eventos 24h"
          value={stats?.eventos_24h ?? 0}
          hint="leituras recebidas"
        />
        <StatCard
          icon={<AlertTriangle className="text-rose-600" size={20} />}
          label="Quedas 24h"
          value={stats?.quedas_24h ?? 0}
          hint={stats && stats.quedas_24h > 0 ? "verificar urgente" : "sem ocorrências"}
          tone={stats && stats.quedas_24h > 0 ? "danger" : "ok"}
        />
        <StatCard
          icon={<Heart className="text-rose-600" size={20} />}
          label="Distress fisiológico"
          value={stats?.distress_24h ?? 0}
          hint="batimento/respiração anômalos"
          tone={stats && stats.distress_24h > 0 ? "warn" : "ok"}
        />
      </section>

      {/* Ambientes */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-900">
            Ambientes monitorados{" "}
            <span className="text-slate-400 font-normal text-sm">
              ({ambientes.length})
            </span>
          </h2>
          <button
            type="button"
            onClick={() => setShowNovoAmbiente(true)}
            className="text-sm flex items-center gap-1.5 px-3 py-1.5 border border-slate-300 rounded-lg hover:bg-slate-50"
          >
            <Plus size={16} /> Novo ambiente
          </button>
        </div>

        {ambientes.length === 0 ? (
          <div className="card text-sm text-slate-500">
            Nenhum ambiente cadastrado. Crie pelo menos um (ex: "Sala Cirúrgica 3",
            "UTI Leito 12", "Casa do Felício") pra começar a receber eventos dos sensores.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {ambientes.map((a) => {
              const nosDoAmbiente = nos.filter((n) => n.ambiente_id === a.id);
              const onlineNoAmbiente = nosDoAmbiente.filter(
                (n) => n.status === "ONLINE",
              ).length;
              return (
                <div
                  key={a.id}
                  className="card hover:border-accent-400/40 transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-semibold text-slate-900">{a.nome}</h3>
                      <p className="text-xs text-slate-500 uppercase tracking-wider mt-0.5">
                        {a.tipo.replace(/_/g, " ")}
                      </p>
                    </div>
                    {nosDoAmbiente.length > 0 ? (
                      <span className="text-xs text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-200">
                        {onlineNoAmbiente}/{nosDoAmbiente.length} on
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500 bg-slate-50 px-2 py-1 rounded-full border border-slate-200">
                        sem sensor
                      </span>
                    )}
                  </div>
                  {a.referencia_externa && (
                    <p className="text-[11px] text-slate-400 mt-1">
                      Ref: {a.referencia_externa}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Nós */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-900">
            Sensores{" "}
            <span className="text-slate-400 font-normal text-sm">({nos.length})</span>
          </h2>
          <button
            type="button"
            onClick={() => setShowNovoNo(true)}
            className="text-sm flex items-center gap-1.5 px-3 py-1.5 border border-slate-300 rounded-lg hover:bg-slate-50"
          >
            <Plus size={16} /> Cadastrar sensor
          </button>
        </div>

        {nos.length === 0 ? (
          <div className="card text-sm text-slate-500">
            Nenhum sensor cadastrado ainda. Quando seu ESP32-S3 chegar, cadastre aqui
            pra receber a API key.
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Sensor</th>
                  <th className="px-4 py-3">Tipo</th>
                  <th className="px-4 py-3">Ambiente</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Última leitura</th>
                  <th className="px-4 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {nos.map((n) => {
                  const amb = n.ambiente_id ? ambientePorId[n.ambiente_id] : null;
                  return (
                    <tr key={n.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">
                          {n.apelido || n.node_id}
                        </div>
                        {n.apelido && (
                          <div className="text-xs text-slate-500">{n.node_id}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600 text-xs uppercase tracking-wider">
                        {n.tipo.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {amb?.nome || (
                          <span className="text-slate-400 italic">sem ambiente</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-xs px-2 py-1 rounded-full border ${STATUS_BADGE[n.status]} inline-flex items-center gap-1.5`}
                        >
                          {n.status === "ONLINE" ? (
                            <Signal size={12} />
                          ) : (
                            <SignalZero size={12} />
                          )}
                          {STATUS_LABEL[n.status]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-xs">
                        {n.last_seen_at ? formatDateTime(n.last_seen_at) : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <RotacionarKeyBtn
                          noId={n.id}
                          onRevelada={(k) => setKeyRevelada(k)}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Timeline */}
      <section>
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Timeline de eventos (últimos 50)
        </h2>

        {!eventos || eventos.items.length === 0 ? (
          <div className="card text-sm text-slate-500">
            Aguardando primeiros eventos. Configure um sensor e ele aparecerá aqui
            em segundos.
          </div>
        ) : (
          <div className="card p-0 overflow-hidden max-h-[600px] overflow-y-auto">
            <ul className="divide-y divide-slate-100">
              {eventos.items.map((ev) => {
                const amb = ev.ambiente_id ? ambientePorId[ev.ambiente_id] : null;
                const badgeClass =
                  TIPO_EVENTO_BADGE[ev.tipo] ??
                  "bg-slate-100 text-slate-600 border-slate-200";
                return (
                  <li
                    key={ev.id}
                    className="px-4 py-3 flex items-center gap-3 hover:bg-slate-50"
                  >
                    <span
                      className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-full border ${badgeClass} font-semibold min-w-[140px] text-center`}
                    >
                      {ev.tipo.replace(/_/g, " ")}
                    </span>
                    <span className="text-sm font-medium text-slate-900 w-32">
                      {formatValorEvento(ev)}
                    </span>
                    <span className="text-xs text-slate-500 flex-1 truncate">
                      {amb?.nome || "—"}
                    </span>
                    {ev.confianca != null && (
                      <span className="text-[11px] text-slate-400 tabular-nums">
                        {(ev.confianca * 100).toFixed(0)}%
                      </span>
                    )}
                    <span className="text-xs text-slate-400 tabular-nums">
                      {formatDateTime(ev.observado_em)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      {/* Modals */}
      {showNovoAmbiente && (
        <NovoAmbienteModal
          clienteId={clienteId}
          onClose={() => setShowNovoAmbiente(false)}
          onCreated={() => {
            setShowNovoAmbiente(false);
            void qc.invalidateQueries({ queryKey: ["vital-ambientes", clienteId] });
            void qc.invalidateQueries({ queryKey: ["vital-stats", clienteId] });
          }}
        />
      )}

      {showNovoNo && (
        <NovoNoModal
          clienteId={clienteId}
          ambientes={ambientes}
          onClose={() => setShowNovoNo(false)}
          onCreated={(comKey) => {
            setShowNovoNo(false);
            setKeyRevelada(comKey);
            void qc.invalidateQueries({ queryKey: ["vital-nos", clienteId] });
          }}
        />
      )}

      {keyRevelada && (
        <ApiKeyRevelacaoModal
          no={keyRevelada}
          onClose={() => setKeyRevelada(null)}
        />
      )}
    </div>
  );
}

// ============================================================
// Stat card
// ============================================================

function StatCard({
  icon,
  label,
  value,
  hint,
  tone = "ok",
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  hint?: string;
  tone?: "ok" | "warn" | "danger";
}) {
  const toneCls =
    tone === "danger"
      ? "border-rose-200 bg-rose-50/40"
      : tone === "warn"
        ? "border-amber-200 bg-amber-50/40"
        : "border-slate-200 bg-white";
  return (
    <div className={`card ${toneCls}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
          {label}
        </span>
      </div>
      <div className="text-3xl font-bold text-slate-900 tabular-nums">{value}</div>
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}

// ============================================================
// Modal: novo ambiente
// ============================================================

function NovoAmbienteModal({
  clienteId,
  onClose,
  onCreated,
}: {
  clienteId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<TipoAmbiente>("SALA_CIRURGICA");
  const [descricao, setDescricao] = useState("");
  const [referencia, setReferencia] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<AmbienteMonitorado>("/api/vital/ambientes", {
        cliente_id: clienteId,
        nome,
        tipo,
        descricao: descricao || null,
        referencia_externa: referencia || null,
      });
      return data;
    },
    onSuccess: () => onCreated(),
    onError: (e) => setErro(getErrorMessage(e)),
  });

  return (
    <ModalShell title="Novo ambiente monitorado" onClose={onClose}>
      <div className="space-y-3">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Nome *
          </span>
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Ex: Sala Cirúrgica 3, Casa do Felício"
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Tipo
          </span>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoAmbiente)}
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="SALA_CIRURGICA">Sala cirúrgica</option>
            <option value="UTI">UTI</option>
            <option value="ENFERMARIA">Enfermaria</option>
            <option value="CONSULTORIO">Consultório</option>
            <option value="PRONTO_SOCORRO">Pronto socorro</option>
            <option value="RESIDENCIAL">Residencial (home care)</option>
            <option value="OUTRO">Outro</option>
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Referência externa
          </span>
          <input
            type="text"
            value={referencia}
            onChange={(e) => setReferencia(e.target.value)}
            placeholder='Ex: "CC-3", "UTI-LEITO-12"'
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Descrição (opcional)
          </span>
          <textarea
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            rows={3}
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
        </label>
        {erro && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">
            {erro}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={!nome || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="btn-primary"
          >
            {mutation.isPending ? "Criando..." : "Criar ambiente"}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ============================================================
// Modal: novo nó
// ============================================================

function NovoNoModal({
  clienteId,
  ambientes,
  onClose,
  onCreated,
}: {
  clienteId: string;
  ambientes: AmbienteMonitorado[];
  onClose: () => void;
  onCreated: (no: NoComApiKey) => void;
}) {
  const [nodeId, setNodeId] = useState("");
  const [tipo, setTipo] = useState<TipoSensor>("RUVIEW_ESP32_S3");
  const [apelido, setApelido] = useState("");
  const [ambienteId, setAmbienteId] = useState<string>("");
  const [privacyMode, setPrivacyMode] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<NoComApiKey>("/api/vital/nos", {
        cliente_id: clienteId,
        node_id: nodeId,
        tipo,
        apelido: apelido || null,
        ambiente_id: ambienteId || null,
        privacy_mode: privacyMode,
      });
      return data;
    },
    onSuccess: (d) => onCreated(d),
    onError: (e) => setErro(getErrorMessage(e)),
  });

  return (
    <ModalShell title="Cadastrar novo sensor" onClose={onClose}>
      <div className="space-y-3">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Node ID *
          </span>
          <input
            type="text"
            value={nodeId}
            onChange={(e) => setNodeId(e.target.value)}
            placeholder="esp32-001"
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono"
          />
          <p className="text-[11px] text-slate-500 mt-1">
            Identificador do firmware (você define ao flashar o ESP32).
          </p>
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Tipo do sensor
          </span>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoSensor)}
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="RUVIEW_ESP32_S3">RuView ESP32-S3 (recomendado)</option>
            <option value="RUVIEW_ESP32_C6">RuView ESP32-C6</option>
            <option value="AQARA_FP2">Aqara FP2 (mmWave)</option>
            <option value="AQARA_FP1">Aqara FP1</option>
            <option value="SIMULADO">Simulado (Docker demo)</option>
            <option value="OUTRO">Outro</option>
          </select>
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Apelido (opcional)
          </span>
          <input
            type="text"
            value={apelido}
            onChange={(e) => setApelido(e.target.value)}
            placeholder="Sensor da sala 3"
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Ambiente
          </span>
          <select
            value={ambienteId}
            onChange={(e) => setAmbienteId(e.target.value)}
            className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="">— sem ambiente (estoque) —</option>
            {ambientes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nome}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={privacyMode}
            onChange={(e) => setPrivacyMode(e.target.checked)}
            className="mt-0.5"
          />
          <div>
            <span className="text-sm font-medium text-slate-900">Privacy mode (LGPD)</span>
            <p className="text-xs text-slate-500">
              Bloqueia envio de batimento e respiração brutos. Só primitivas semânticas
              ("presença", "queda") sobem ao servidor.
            </p>
          </div>
        </label>
        {erro && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">
            {erro}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={!nodeId || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="btn-primary"
          >
            {mutation.isPending ? "Criando..." : "Cadastrar sensor"}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ============================================================
// Modal: API key revelada (UMA VEZ)
// ============================================================

function ApiKeyRevelacaoModal({
  no,
  onClose,
}: {
  no: NoComApiKey;
  onClose: () => void;
}) {
  const [copiado, setCopiado] = useState(false);
  const cmdCurl = `curl -X POST https://medpag-api.onrender.com/api/vital/eventos \\
  -H "Content-Type: application/json" \\
  -H "X-Vital-Node-Token: ${no.api_key}" \\
  -d '{"tipo":"HEARTBEAT","valor_num":1}'`;

  return (
    <ModalShell title="API key do sensor — GUARDE AGORA" onClose={onClose}>
      <div className="space-y-4">
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 text-sm">
          <strong className="text-amber-900">⚠ Atenção:</strong>{" "}
          <span className="text-amber-900">
            esta chave aparece <strong>uma única vez</strong>. Copie agora e cole no
            firmware do seu ESP32. Se perder, use "Rotacionar key" pra gerar outra.
          </span>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            API key
          </label>
          <div className="mt-1 flex gap-2">
            <code className="flex-1 bg-slate-900 text-emerald-300 px-3 py-2 rounded-lg text-xs font-mono break-all">
              {no.api_key}
            </code>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(no.api_key);
                setCopiado(true);
                setTimeout(() => setCopiado(false), 2000);
              }}
              className="btn-primary text-sm whitespace-nowrap"
            >
              {copiado ? "Copiado!" : "Copiar"}
            </button>
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-600">
            Teste rápido (curl)
          </label>
          <pre className="mt-1 bg-slate-900 text-slate-200 px-3 py-3 rounded-lg text-[11px] font-mono overflow-x-auto whitespace-pre-wrap">
            {cmdCurl}
          </pre>
        </div>
        <div className="flex justify-end">
          <button type="button" onClick={onClose} className="btn-primary">
            Já guardei, fechar
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ============================================================
// Rotacionar key
// ============================================================

function RotacionarKeyBtn({
  noId,
  onRevelada,
}: {
  noId: string;
  onRevelada: (no: NoComApiKey) => void;
}) {
  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<NoComApiKey>(
        `/api/vital/nos/${noId}/rotacionar-key`,
      );
      return data;
    },
    onSuccess: (d) => onRevelada(d),
  });

  return (
    <button
      type="button"
      onClick={() => {
        if (confirm("Gerar nova API key? A anterior deixa de funcionar imediatamente.")) {
          mutation.mutate();
        }
      }}
      className="text-xs text-slate-500 hover:text-rose-600 flex items-center gap-1.5"
      title="Rotacionar API key"
    >
      <Trash2 size={14} />
      Rotacionar key
    </button>
  );
}

// ============================================================
// Shell de modal genérico
// ============================================================

function ModalShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h3 className="font-semibold text-slate-900">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
