import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  CheckCircle2,
  Link2,
  Loader2,
  MessageSquare,
  Phone,
  Plus,
  PowerOff,
  QrCode,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type {
  InstanciaWpp,
  QRCodeWpp,
  UserAdmin,
  WhatsAppMensagemOut,
  WhatsAppUserOut,
} from "@/types";

const STATUS_TONE: Record<string, string> = {
  DESCONECTADA: "bg-slate-100 text-slate-700",
  AGUARDANDO_QR: "bg-amber-50 text-amber-800",
  CONECTADA: "bg-emerald-50 text-emerald-700",
  ERRO: "bg-red-50 text-red-700",
};

export function AdminWhatsAppPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 mb-1">
          Jarvis (WhatsApp)
        </h1>
        <p className="text-sm text-slate-500">
          Configure o assistente Jarvis. Conecte seu WhatsApp escaneando o QR
          code, autorize números a interagir e veja o histórico das conversas.
        </p>
      </div>

      <SessionCard />
      <UsuariosCard />
      <HistoricoCard />
    </div>
  );
}

// ============================================================
// Sessão Wuzapi
// ============================================================

function SessionCard() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showAdotar, setShowAdotar] = useState(false);

  const { data: instancia, isLoading } = useQuery({
    queryKey: ["whatsapp", "instancia"],
    queryFn: async () => {
      const { data } = await api.get<InstanciaWpp | null>(
        "/api/whatsapp/instancia",
      );
      return data;
    },
    refetchInterval: (q) => {
      const data = q.state.data as InstanciaWpp | null | undefined;
      return data?.status === "AGUARDANDO_QR" ? 3000 : 30000;
    },
  });

  const conectar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<QRCodeWpp>(
        "/api/whatsapp/instancia/conectar",
      );
      return data;
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["whatsapp", "instancia"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const desconectar = useMutation({
    mutationFn: async () => {
      await api.post("/api/whatsapp/instancia/desconectar");
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["whatsapp", "instancia"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <Bot size={16} className="text-brand-700" />
            Sessão WhatsApp
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Pareie um celular para o Jarvis começar a responder.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {instancia?.status === "CONECTADA" && (
            <button
              type="button"
              onClick={() => desconectar.mutate()}
              disabled={desconectar.isPending}
              className="btn-ghost text-red-600 border-red-200 hover:bg-red-50"
            >
              <PowerOff size={14} />
              Desconectar
            </button>
          )}
          <button
            type="button"
            onClick={() => conectar.mutate()}
            disabled={conectar.isPending || isLoading}
            className="btn-primary"
          >
            {conectar.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Gerando QR...
              </>
            ) : (
              <>
                <QrCode size={14} />
                {instancia ? "Renovar QR Code" : "Conectar WhatsApp"}
              </>
            )}
          </button>
        </div>
      </div>

      {showAdotar && (
        <AdotarInstanciaModal
          onClose={() => setShowAdotar(false)}
          onAdopted={() => {
            setShowAdotar(false);
            setError(null);
            void queryClient.invalidateQueries({
              queryKey: ["whatsapp", "instancia"],
            });
          }}
        />
      )}

      {isLoading ? (
        <div className="text-sm text-slate-500">Carregando...</div>
      ) : !instancia ? (
        <div className="text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-3">
          Nenhuma sessão criada ainda. Clique em <strong>Conectar WhatsApp</strong>{" "}
          pra começar.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-xs text-slate-500">Status</div>
            <span
              className={`inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_TONE[instancia.status] ?? STATUS_TONE.DESCONECTADA}`}
            >
              {instancia.status === "CONECTADA" && <CheckCircle2 size={12} />}
              {instancia.status}
            </span>
          </div>
          <div>
            <div className="text-xs text-slate-500">Número do bot</div>
            <div className="font-mono mt-1">
              {instancia.numero_bot ? `+${instancia.numero_bot}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500">ID da instância</div>
            <div className="font-mono text-xs mt-1 truncate">
              {instancia.wuzapi_instance_id}
            </div>
          </div>
        </div>
      )}

      {conectar.data?.qr_base64 && instancia?.status !== "CONECTADA" && (
        <div className="mt-4 flex flex-col items-center bg-slate-50 border border-slate-200 rounded-xl py-6">
          <p className="text-sm font-medium text-slate-800 mb-3">
            Escaneie no WhatsApp → Aparelhos conectados → Conectar aparelho
          </p>
          <img
            src={
              conectar.data.qr_base64.startsWith("data:")
                ? conectar.data.qr_base64
                : `data:image/png;base64,${conectar.data.qr_base64}`
            }
            alt="QR Code"
            className="w-64 h-64 bg-white rounded-lg p-2 shadow-sm"
          />
          <p className="text-xs text-slate-500 mt-3">
            QR expira em ~60s. Se não funcionar, clique em "Renovar QR Code".
          </p>
        </div>
      )}

      {error && (
        <div className="mt-4 space-y-2">
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
          <button
            type="button"
            onClick={() => setShowAdotar(true)}
            className="text-xs text-slate-500 hover:text-slate-700 underline"
          >
            Configuração avançada: adotar sessão existente
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Modal: Adotar instancia existente
// ============================================================

interface AdotarInstanciaModalProps {
  onClose: () => void;
  onAdopted: () => void;
}

interface DiagnosticoUser {
  name: string;
  id: string;
  token: string;
  token_preview: string;
  jid: string | null;
  numero: string | null;
  connected: boolean | null;
  loggedIn: boolean | null;
  webhook: string | null;
}

interface DiagnosticoResponse {
  wuzapi_url: string | null;
  ok: boolean;
  erro?: string;
  total?: number;
  users: DiagnosticoUser[];
}

function AdotarInstanciaModal({
  onClose,
  onAdopted,
}: AdotarInstanciaModalProps) {
  const [instanceId, setInstanceId] = useState("");
  const [token, setToken] = useState("");
  const [numero, setNumero] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: diag, isLoading: loadingDiag, refetch: recarregarDiag } = useQuery({
    queryKey: ["whatsapp", "diagnostico"],
    queryFn: async () => {
      const { data } = await api.get<DiagnosticoResponse>(
        "/api/whatsapp/instancia/diagnostico",
      );
      return data;
    },
    refetchOnWindowFocus: false,
  });

  const adotar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<InstanciaWpp>(
        "/api/whatsapp/instancia/adotar",
        {
          wuzapi_instance_id: instanceId.trim(),
          wuzapi_token: token.trim(),
          numero_bot: numero.trim() || null,
        },
      );
      return data;
    },
    onSuccess: onAdopted,
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <Link2 size={16} className="text-brand-700" />
            Adotar instância existente
          </h3>
          <p className="text-xs text-slate-500 mt-1">
            Se você já criou e pareou um user no Wuzapi da VPS, cole os dados
            aqui que o Med-Pay passa a usar essa sessão.
          </p>
        </div>
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-slate-50 px-3 py-2 border-b border-slate-200">
              <div>
                <p className="text-xs font-semibold text-slate-700">
                  Sessões disponíveis na VPS
                </p>
                {diag?.wuzapi_url && (
                  <p className="text-[10px] text-slate-500 font-mono">
                    {diag.wuzapi_url}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => void recarregarDiag()}
                disabled={loadingDiag}
                className="text-xs text-brand-700 hover:underline disabled:opacity-50"
              >
                {loadingDiag ? "Carregando..." : "Recarregar"}
              </button>
            </div>
            {loadingDiag ? (
              <div className="p-4 text-xs text-slate-500 text-center">
                <Loader2 size={14} className="animate-spin inline mr-2" />
                Consultando servidor...
              </div>
            ) : diag && !diag.ok ? (
              <div className="p-3 text-xs text-red-700 bg-red-50">
                {diag.erro ?? "Falha ao consultar servidor"}
              </div>
            ) : diag && diag.users.length === 0 ? (
              <div className="p-4 text-xs text-slate-500 text-center">
                Nenhuma sessão no servidor ainda.
              </div>
            ) : diag && diag.users.length > 0 ? (
              <div className="divide-y divide-slate-100 max-h-48 overflow-y-auto">
                {diag.users.map((u) => (
                  <button
                    key={u.id || u.name}
                    type="button"
                    onClick={() => {
                      setInstanceId(u.name || u.id);
                      setToken(u.token);
                      if (u.numero) setNumero(u.numero);
                    }}
                    className="w-full text-left px-3 py-2 hover:bg-emerald-50/40 transition flex items-center gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-800 truncate">
                          {u.name || "(sem nome)"}
                        </span>
                        {u.loggedIn ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-semibold">
                            CONECTADO
                          </span>
                        ) : u.connected ? (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold">
                            AGUARDANDO QR
                          </span>
                        ) : (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-semibold">
                            DESLIGADO
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-500 font-mono truncate">
                        {u.token_preview}
                        {u.numero && ` • +${u.numero}`}
                      </div>
                    </div>
                    <span className="text-xs text-brand-700 font-medium whitespace-nowrap">
                      Usar este →
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1.5">
            <p className="font-semibold text-amber-900">
              Ou cole os dados manualmente:
            </p>
            <p>
              Se você gerou o QR direto no servidor (via curl/UI da VPS) e já
              escaneou com o celular, cole o <strong>nome do user</strong>{" "}
              (instance_id) e o <strong>token</strong> dele abaixo.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Instance ID (nome do user no Wuzapi)
            </label>
            <input
              value={instanceId}
              onChange={(e) => setInstanceId(e.target.value)}
              placeholder="ex: jarvis ou medpag-jarvis"
              className="input font-mono"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Token da instância
            </label>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="ex: jarvis-byceo-2026"
              className="input font-mono"
              type="text"
            />
            <p className="text-xs text-slate-500 mt-1">
              Token do <strong>user</strong> (não o ADMIN_TOKEN). É o que aparece
              na lista de users do Wuzapi.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Número do bot (opcional)
            </label>
            <input
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
              placeholder="5521999998888"
              className="input font-mono"
            />
            <p className="text-xs text-slate-500 mt-1">
              Telefone do WhatsApp pareado. Pode deixar em branco — preenchemos
              quando a sessão sincronizar.
            </p>
          </div>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>
        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={adotar.isPending}
            className="btn-ghost"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => adotar.mutate()}
            disabled={!instanceId || !token || adotar.isPending}
            className="btn-primary"
          >
            {adotar.isPending ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Validando...
              </>
            ) : (
              <>
                <Link2 size={14} />
                Adotar
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Whitelist de usuários
// ============================================================

function UsuariosCard() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ["whatsapp", "users"],
    queryFn: async () => {
      const { data } = await api.get<WhatsAppUserOut[]>(
        "/api/whatsapp/users",
      );
      return data;
    },
  });

  const toggleAtivo = useMutation({
    mutationFn: async (usuario: WhatsAppUserOut) => {
      await api.put(`/api/whatsapp/users/${usuario.id}`, {
        ativo: !usuario.ativo,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "users"] }),
  });

  const toggleAprovador = useMutation({
    mutationFn: async (usuario: WhatsAppUserOut) => {
      await api.put(`/api/whatsapp/users/${usuario.id}`, {
        pode_aprovar_pagamento: !usuario.pode_aprovar_pagamento,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "users"] }),
  });

  const toggleRelatorio = useMutation({
    mutationFn: async (usuario: WhatsAppUserOut) => {
      await api.put(`/api/whatsapp/users/${usuario.id}`, {
        receber_relatorio_diario: !usuario.receber_relatorio_diario,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "users"] }),
  });

  const dispararRelatorio = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{
        inscritos: number;
        enviados: number;
        falhas: number;
      }>("/api/whatsapp/jarvis/relatorio-diario/disparar");
      return data;
    },
    onSuccess: (data) => {
      window.alert(
        `Relatório disparado!\n` +
          `Inscritos: ${data.inscritos}\nEnviados: ${data.enviados}\nFalhas: ${data.falhas}`,
      );
    },
    onError: (err) => {
      window.alert(`Erro ao disparar: ${(err as Error).message}`);
    },
  });

  const remover = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/whatsapp/users/${id}`);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["whatsapp", "users"] }),
  });

  return (
    <div className="card p-0 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <ShieldCheck size={16} className="text-brand-700" />
            Números autorizados
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Apenas estes telefones recebem resposta do Jarvis. Qualquer outro é
            ignorado silenciosamente.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => dispararRelatorio.mutate()}
            disabled={dispararRelatorio.isPending}
            className="btn-secondary text-xs"
            title="Envia o relatório diário do Jarvis AGORA para todos os inscritos"
          >
            {dispararRelatorio.isPending ? "Disparando..." : "Testar bom dia Jarvis"}
          </button>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="btn-primary"
          >
            <Plus size={14} />
            Adicionar número
          </button>
        </div>
      </div>

      {showModal && (
        <NovoUsuarioModal
          onClose={() => setShowModal(false)}
          onCreated={() => {
            setShowModal(false);
            void queryClient.invalidateQueries({
              queryKey: ["whatsapp", "users"],
            });
          }}
        />
      )}

      {isLoading ? (
        <div className="p-6 text-sm text-slate-500">Carregando...</div>
      ) : usuarios.length === 0 ? (
        <div className="p-8 text-center text-sm text-slate-500">
          Nenhum número autorizado. Adicione o seu pra começar.
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Telefone</th>
              <th className="px-4 py-2">Usuário</th>
              <th className="px-4 py-2">Aprova pagamento</th>
              <th className="px-4 py-2">Bom dia Jarvis (8h)</th>
              <th className="px-4 py-2">Ativo</th>
              <th className="px-4 py-2 w-10"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {usuarios.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50/60">
                <td className="px-4 py-3">
                  <div className="font-mono">+{u.numero_e164}</div>
                  {u.apelido && (
                    <div className="text-xs text-slate-500">{u.apelido}</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-800">{u.user_nome}</div>
                  <div className="text-xs text-slate-500">
                    {u.user_email} • {u.user_role}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={u.pode_aprovar_pagamento}
                      onChange={() => toggleAprovador.mutate(u)}
                      disabled={toggleAprovador.isPending}
                      className="h-4 w-4"
                    />
                    <span className="text-xs text-slate-600">
                      {u.pode_aprovar_pagamento ? "Sim" : "Não"}
                    </span>
                  </label>
                </td>
                <td className="px-4 py-3">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={u.receber_relatorio_diario}
                      onChange={() => toggleRelatorio.mutate(u)}
                      disabled={toggleRelatorio.isPending}
                      className="h-4 w-4"
                    />
                    <span className="text-xs text-slate-600">
                      {u.receber_relatorio_diario ? "Sim" : "Não"}
                    </span>
                  </label>
                </td>
                <td className="px-4 py-3">
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={u.ativo}
                      onChange={() => toggleAtivo.mutate(u)}
                      disabled={toggleAtivo.isPending}
                      className="h-4 w-4"
                    />
                    <span className="text-xs text-slate-600">
                      {u.ativo ? "Ativo" : "Inativo"}
                    </span>
                  </label>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`Remover acesso de +${u.numero_e164}?`))
                        remover.mutate(u.id);
                    }}
                    className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

interface NovoUsuarioModalProps {
  onClose: () => void;
  onCreated: () => void;
}

function NovoUsuarioModal({ onClose, onCreated }: NovoUsuarioModalProps) {
  const [userId, setUserId] = useState("");
  const [numero, setNumero] = useState("");
  const [apelido, setApelido] = useState("");
  const [podeAprovar, setPodeAprovar] = useState(false);
  const [receberRelatorio, setReceberRelatorio] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: usuariosPlat = [] } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: async () => {
      const { data } = await api.get<UserAdmin[]>("/api/admin/users");
      return data;
    },
  });

  const criar = useMutation({
    mutationFn: async () => {
      await api.post("/api/whatsapp/users", {
        user_id: userId,
        numero_e164: numero.replace(/\D/g, ""),
        apelido: apelido || null,
        pode_aprovar_pagamento: podeAprovar,
        receber_relatorio_diario: receberRelatorio,
      });
    },
    onSuccess: onCreated,
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h3 className="text-base font-semibold text-slate-900">
            Autorizar número
          </h3>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Usuário da plataforma
            </label>
            <select
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="input"
            >
              <option value="">Selecione...</option>
              {usuariosPlat.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nome} ({u.email}) — {u.role}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Telefone (com DDI+DDD)
            </label>
            <input
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
              placeholder="5521999998888"
              className="input font-mono"
            />
            <p className="text-xs text-slate-500 mt-1">
              Sem +, hífens ou parênteses. Ex: 5521999998888
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Apelido (opcional)
            </label>
            <input
              value={apelido}
              onChange={(e) => setApelido(e.target.value)}
              placeholder="Felício / Sócio Operações"
              className="input"
            />
          </div>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={podeAprovar}
              onChange={(e) => setPodeAprovar(e.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <div className="text-sm">
              <div className="font-medium text-slate-800">
                Pode aprovar lotes pelo WhatsApp
              </div>
              <div className="text-xs text-slate-500">
                Risco financeiro alto: marque só pra sócios autorizados.
              </div>
            </div>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={receberRelatorio}
              onChange={(e) => setReceberRelatorio(e.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <div className="text-sm">
              <div className="font-medium text-slate-800">
                Receber "bom dia" do Jarvis (8h)
              </div>
              <div className="text-xs text-slate-500">
                Resumo diário com saúde da plataforma e itens críticos.
              </div>
            </div>
          </label>
          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>
        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={criar.isPending}
            className="btn-ghost"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => criar.mutate()}
            disabled={!userId || !numero || criar.isPending}
            className="btn-primary"
          >
            {criar.isPending ? "Salvando..." : "Autorizar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Histórico de mensagens
// ============================================================

function HistoricoCard() {
  const { data: mensagens = [], isLoading } = useQuery({
    queryKey: ["whatsapp", "mensagens"],
    queryFn: async () => {
      const { data } = await api.get<WhatsAppMensagemOut[]>(
        "/api/whatsapp/mensagens?limit=50",
      );
      return data;
    },
    refetchInterval: 10000,
  });

  return (
    <div className="card p-0 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200">
        <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
          <MessageSquare size={16} className="text-brand-700" />
          Conversas recentes
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Últimas 50 mensagens. Inclui números não autorizados (com flag de
          erro) pra auditoria.
        </p>
      </div>

      {isLoading ? (
        <div className="p-6 text-sm text-slate-500">Carregando...</div>
      ) : mensagens.length === 0 ? (
        <div className="p-8 text-center text-sm text-slate-500">
          Nenhuma conversa ainda. Quando alguém escrever pro bot, aparece aqui.
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 max-h-[500px] overflow-y-auto">
          {mensagens.map((m) => (
            <li key={m.id} className="px-6 py-3 hover:bg-slate-50/40">
              <div className="flex items-start justify-between gap-3 mb-1">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Phone size={11} />
                  <span className="font-mono">+{m.numero_e164}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                      m.direcao === "INBOUND"
                        ? "bg-blue-50 text-blue-700"
                        : "bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {m.direcao === "INBOUND" ? "ENTRADA" : "JARVIS"}
                  </span>
                  {m.erro && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-50 text-red-700">
                      {m.erro}
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-slate-400 whitespace-nowrap">
                  {formatDateTime(m.created_at)}
                </span>
              </div>
              <p className="text-sm text-slate-800 whitespace-pre-wrap">
                {m.texto}
              </p>
              {m.tools_usadas && m.tools_usadas.length > 0 && (
                <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                  <Activity size={10} />
                  Tools:{" "}
                  {m.tools_usadas.map((t) => t.tool).join(", ")}
                  {m.duracao_ms ? ` • ${m.duracao_ms}ms` : ""}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
