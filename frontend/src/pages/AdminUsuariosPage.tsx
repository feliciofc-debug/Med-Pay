import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Eye,
  EyeOff,
  KeyRound,
  Pencil,
  Plus,
  ShieldCheck,
  UserCheck,
  UserCog,
  UserX,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type {
  AtualizarUsuarioPayload,
  CriarUsuarioPayload,
  UserAdmin,
  UserRole,
} from "@/types";

const ROLE_LABEL: Record<UserRole, string> = {
  ADMIN: "Administrador",
  APROVADOR: "Aprovador",
  OPERADOR: "Operador",
};

const ROLE_COLOR: Record<UserRole, string> = {
  ADMIN: "bg-accent-100 text-accent-800 border-accent-300",
  APROVADOR: "bg-brand-100 text-brand-800 border-brand-300",
  OPERADOR: "bg-slate-100 text-slate-700 border-slate-300",
};

export function AdminUsuariosPage() {
  const queryClient = useQueryClient();
  const [filtroRole, setFiltroRole] = useState<UserRole | "">("");
  const [filtroAtivo, setFiltroAtivo] = useState<"" | "true" | "false">("");
  const [showNovoModal, setShowNovoModal] = useState(false);
  const [editando, setEditando] = useState<UserAdmin | null>(null);
  const [resetSenhaUser, setResetSenhaUser] = useState<UserAdmin | null>(null);

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ["admin", "users", filtroRole, filtroAtivo],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filtroRole) params.set("role", filtroRole);
      if (filtroAtivo) params.set("ativo", filtroAtivo);
      const { data } = await api.get<UserAdmin[]>(
        `/api/admin/users?${params.toString()}`,
      );
      return data;
    },
  });

  const toggleAtivo = useMutation({
    mutationFn: async (user: UserAdmin) => {
      const { data } = await api.patch<UserAdmin>(
        `/api/admin/users/${user.id}`,
        { ativo: !user.ativo } satisfies AtualizarUsuarioPayload,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <UserCog size={24} className="text-accent-600" />
            Equipe operacional
          </h1>
          <p className="text-sm text-brand-700/70 mt-1">
            Gestão de operadores, aprovadores e administradores do MedPag.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowNovoModal(true)}
          className="btn-primary"
        >
          <Plus size={16} /> Novo usuário
        </button>
      </header>

      {/* Filtros */}
      <div className="card flex flex-wrap gap-3 items-end">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Papel
          </label>
          <select
            value={filtroRole}
            onChange={(e) => setFiltroRole(e.target.value as UserRole | "")}
            className="input"
          >
            <option value="">Todos</option>
            <option value="ADMIN">Administrador</option>
            <option value="APROVADOR">Aprovador</option>
            <option value="OPERADOR">Operador</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Status
          </label>
          <select
            value={filtroAtivo}
            onChange={(e) =>
              setFiltroAtivo(e.target.value as "" | "true" | "false")
            }
            className="input"
          >
            <option value="">Todos</option>
            <option value="true">Ativos</option>
            <option value="false">Inativos</option>
          </select>
        </div>
      </div>

      {/* Tabela */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-6 py-3">Nome</th>
              <th className="px-6 py-3">E-mail</th>
              <th className="px-6 py-3">Papel</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Último login</th>
              <th className="px-6 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                  Carregando equipe...
                </td>
              </tr>
            )}
            {!isLoading && usuarios.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                  Nenhum usuário encontrado. Clique em <strong>Novo usuário</strong>{" "}
                  pra adicionar o primeiro operador da equipe.
                </td>
              </tr>
            )}
            {usuarios.map((user) => (
              <tr
                key={user.id}
                className={`border-b border-slate-100 last:border-0 ${
                  !user.ativo ? "bg-slate-50/50 opacity-60" : ""
                }`}
              >
                <td className="px-6 py-3 font-medium text-slate-900">
                  {user.nome}
                </td>
                <td className="px-6 py-3 text-slate-600">{user.email}</td>
                <td className="px-6 py-3">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${
                      ROLE_COLOR[user.role]
                    }`}
                  >
                    {ROLE_LABEL[user.role]}
                  </span>
                </td>
                <td className="px-6 py-3">
                  {user.ativo ? (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
                      <UserCheck size={14} /> Ativo
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                      <UserX size={14} /> Inativo
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 text-slate-500 text-xs">
                  {formatDateTime(user.last_login_at)}
                </td>
                <td className="px-6 py-3 text-right">
                  <div className="inline-flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setEditando(user)}
                      className="p-1.5 rounded hover:bg-slate-100 text-slate-600"
                      title="Editar"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setResetSenhaUser(user)}
                      className="p-1.5 rounded hover:bg-slate-100 text-slate-600"
                      title="Resetar senha"
                    >
                      <KeyRound size={14} />
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleAtivo.mutate(user)}
                      disabled={toggleAtivo.isPending}
                      className="p-1.5 rounded hover:bg-slate-100 text-slate-600"
                      title={user.ativo ? "Desativar" : "Ativar"}
                    >
                      {user.ativo ? <UserX size={14} /> : <UserCheck size={14} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showNovoModal && (
        <NovoUsuarioModal onClose={() => setShowNovoModal(false)} />
      )}

      {editando && (
        <EditarUsuarioModal
          user={editando}
          onClose={() => setEditando(null)}
        />
      )}

      {resetSenhaUser && (
        <ResetSenhaModal
          user={resetSenhaUser}
          onClose={() => setResetSenhaUser(null)}
        />
      )}
    </div>
  );
}

// ============================================================
// Modal: criar novo usuário
// ============================================================

function NovoUsuarioModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("OPERADOR");
  const [senha, setSenha] = useState("");
  const [showSenha, setShowSenha] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const criar = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<UserAdmin>("/api/admin/users", {
        nome,
        email,
        role,
        senha,
      } satisfies CriarUsuarioPayload);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (err) => setErro(getErrorMessage(err)),
  });

  return (
    <ModalShell title="Cadastrar novo usuário" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setErro(null);
          criar.mutate();
        }}
        className="space-y-4"
      >
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Nome completo
          </label>
          <input
            type="text"
            required
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input"
            placeholder="Maria da Silva"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            E-mail
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            placeholder="maria@empresa.com.br"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Papel
          </label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="input"
          >
            <option value="OPERADOR">
              Operador — sobe planilha, revisa, corrige
            </option>
            <option value="APROVADOR">
              Aprovador — aprova lotes, gera CNAB, insere token
            </option>
            <option value="ADMIN">
              Administrador — gerencia usuários e vê relatórios
            </option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Senha inicial (mínimo 8 caracteres)
          </label>
          <div className="relative">
            <input
              type={showSenha ? "text" : "password"}
              required
              minLength={8}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className="input pr-10"
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowSenha((v) => !v)}
              tabIndex={-1}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-brand-700/60 hover:text-brand-900"
            >
              {showSenha ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Compartilhe com o operador por canal seguro. Ele pode trocar depois.
          </p>
        </div>

        {erro && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {erro}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancelar
          </button>
          <button
            type="submit"
            disabled={criar.isPending}
            className="btn-primary"
          >
            <ShieldCheck size={16} />
            {criar.isPending ? "Criando..." : "Criar usuário"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ============================================================
// Modal: editar usuário (nome + role)
// ============================================================

function EditarUsuarioModal({
  user,
  onClose,
}: {
  user: UserAdmin;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [nome, setNome] = useState(user.nome);
  const [role, setRole] = useState<UserRole>(user.role);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch<UserAdmin>(
        `/api/admin/users/${user.id}`,
        { nome, role } satisfies AtualizarUsuarioPayload,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (err) => setErro(getErrorMessage(err)),
  });

  return (
    <ModalShell title={`Editar — ${user.email}`} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setErro(null);
          salvar.mutate();
        }}
        className="space-y-4"
      >
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Nome
          </label>
          <input
            type="text"
            required
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Papel
          </label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="input"
          >
            <option value="OPERADOR">Operador</option>
            <option value="APROVADOR">Aprovador</option>
            <option value="ADMIN">Administrador</option>
          </select>
        </div>

        {erro && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {erro}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Cancelar
          </button>
          <button
            type="submit"
            disabled={salvar.isPending}
            className="btn-primary"
          >
            {salvar.isPending ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ============================================================
// Modal: reset de senha
// ============================================================

function ResetSenhaModal({
  user,
  onClose,
}: {
  user: UserAdmin;
  onClose: () => void;
}) {
  const [novaSenha, setNovaSenha] = useState("");
  const [show, setShow] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState(false);

  const resetar = useMutation({
    mutationFn: async () => {
      await api.post(`/api/admin/users/${user.id}/reset-senha`, {
        nova_senha: novaSenha,
      });
    },
    onSuccess: () => setSucesso(true),
    onError: (err) => setErro(getErrorMessage(err)),
  });

  return (
    <ModalShell title={`Reset de senha — ${user.email}`} onClose={onClose}>
      {sucesso ? (
        <div className="space-y-4">
          <div className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-3">
            Senha alterada. Compartilhe a nova senha com{" "}
            <strong>{user.nome}</strong> por canal interno (WhatsApp da empresa,
            por exemplo). Ele pode trocar depois.
          </div>
          <div className="flex justify-end">
            <button type="button" onClick={onClose} className="btn-primary">
              Fechar
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setErro(null);
            resetar.mutate();
          }}
          className="space-y-4"
        >
          <p className="text-sm text-slate-600">
            Defina uma nova senha pra <strong>{user.nome}</strong>. Mínimo 8
            caracteres.
          </p>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nova senha
            </label>
            <div className="relative">
              <input
                type={show ? "text" : "password"}
                required
                minLength={8}
                value={novaSenha}
                onChange={(e) => setNovaSenha(e.target.value)}
                className="input pr-10"
              />
              <button
                type="button"
                onClick={() => setShow((v) => !v)}
                tabIndex={-1}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-brand-700/60 hover:text-brand-900"
              >
                {show ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {erro && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {erro}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={resetar.isPending}
              className="btn-primary"
            >
              <KeyRound size={16} />
              {resetar.isPending ? "Resetando..." : "Resetar senha"}
            </button>
          </div>
        </form>
      )}
    </ModalShell>
  );
}

// ============================================================
// Shell de modal reutilizável (overlay + card centralizado)
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-brand-950/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-brand-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-100 text-slate-500"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
