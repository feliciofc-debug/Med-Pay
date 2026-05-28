/**
 * Tela de Auditoria — log imutável de operações sensíveis.
 *
 * Lê de `/api/auditoria` com filtros por ação, entidade, usuário, range
 * de datas e busca livre. Sem write — só consulta.
 *
 * Usa drawer lateral pra mostrar o JSON `detalhes` quando o admin clica
 * num registro (sem mexer no layout principal).
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  FileSearch,
  Hash,
  History,
  Search,
  User as UserIcon,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import type { AuditoriaItem, AuditoriaPage } from "@/types";

interface FiltrosLocal {
  acao: string;
  entidade_tipo: string;
  busca: string;
  desde: string;
  ate: string;
}

const FILTROS_VAZIOS: FiltrosLocal = {
  acao: "",
  entidade_tipo: "",
  busca: "",
  desde: "",
  ate: "",
};

const ENTIDADES_COMUNS = [
  "Lote",
  "Pagamento",
  "Cliente",
  "User",
  "Beneficiario",
  "CodigoServico",
  "ContratoHospital",
];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function corAcao(acao: string): string {
  if (acao.includes("APROVADO") || acao.includes("PAGO")) {
    return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
  if (acao.includes("REJEITADO") || acao.includes("ERRO")) {
    return "bg-red-50 text-red-700 border-red-200";
  }
  if (acao.includes("EDITADO") || acao.includes("ATUALIZADO")) {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  if (acao.includes("LOGIN") || acao.includes("LOGOUT")) {
    return "bg-blue-50 text-blue-700 border-blue-200";
  }
  return "bg-slate-100 text-slate-700 border-slate-200";
}

export function AdminAuditoriaPage() {
  const [filtros, setFiltros] = useState<FiltrosLocal>(FILTROS_VAZIOS);
  const [pendentes, setPendentes] = useState<FiltrosLocal>(FILTROS_VAZIOS);
  const [page, setPage] = useState(1);
  const [drawer, setDrawer] = useState<AuditoriaItem | null>(null);
  const perPage = 50;

  const { data: acoesDisponiveis = [] } = useQuery({
    queryKey: ["auditoria", "acoes"],
    queryFn: async () => {
      const { data } = await api.get<string[]>("/api/auditoria/acoes");
      return data;
    },
  });

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["auditoria", "list", filtros, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("per_page", String(perPage));
      if (filtros.acao) params.set("acao", filtros.acao);
      if (filtros.entidade_tipo)
        params.set("entidade_tipo", filtros.entidade_tipo);
      if (filtros.busca) params.set("busca", filtros.busca);
      if (filtros.desde)
        params.set("desde", new Date(filtros.desde + "T00:00:00Z").toISOString());
      if (filtros.ate)
        params.set("ate", new Date(filtros.ate + "T23:59:59Z").toISOString());
      const { data } = await api.get<AuditoriaPage>(
        `/api/auditoria?${params.toString()}`,
      );
      return data;
    },
  });

  const totalPages = data?.total_pages ?? 1;
  const itens = data?.items ?? [];

  const filtrosAtivos = useMemo(
    () => Object.values(filtros).filter((v) => v !== "").length,
    [filtros],
  );

  const aplicar = () => {
    setFiltros(pendentes);
    setPage(1);
  };

  const limpar = () => {
    setFiltros(FILTROS_VAZIOS);
    setPendentes(FILTROS_VAZIOS);
    setPage(1);
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
          <History className="text-brand-600" size={26} />
          Auditoria
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Log imutável de operações sensíveis. Tudo que mexe em dinheiro,
          permissão ou dado sensível fica gravado aqui.
        </p>
      </header>

      {/* ============ Filtros ============ */}
      <section className="card p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Ação
            </label>
            <select
              value={pendentes.acao}
              onChange={(e) =>
                setPendentes((p) => ({ ...p, acao: e.target.value }))
              }
              className="input w-full"
            >
              <option value="">Todas</option>
              {acoesDisponiveis.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Entidade
            </label>
            <select
              value={pendentes.entidade_tipo}
              onChange={(e) =>
                setPendentes((p) => ({ ...p, entidade_tipo: e.target.value }))
              }
              className="input w-full"
            >
              <option value="">Todas</option>
              {ENTIDADES_COMUNS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Desde
            </label>
            <input
              type="date"
              value={pendentes.desde}
              onChange={(e) =>
                setPendentes((p) => ({ ...p, desde: e.target.value }))
              }
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Até
            </label>
            <input
              type="date"
              value={pendentes.ate}
              onChange={(e) =>
                setPendentes((p) => ({ ...p, ate: e.target.value }))
              }
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Busca livre
            </label>
            <div className="relative">
              <Search
                className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
                size={14}
              />
              <input
                type="text"
                value={pendentes.busca}
                placeholder="palavra na mensagem..."
                onChange={(e) =>
                  setPendentes((p) => ({ ...p, busca: e.target.value }))
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") aplicar();
                }}
                className="input w-full pl-7"
              />
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-200">
          <p className="text-xs text-slate-500">
            {filtrosAtivos > 0
              ? `${filtrosAtivos} filtro${filtrosAtivos > 1 ? "s" : ""} ativo${
                  filtrosAtivos > 1 ? "s" : ""
                }`
              : "Sem filtros ativos"}
            {data && (
              <span className="ml-2">
                · <strong>{data.total.toLocaleString("pt-BR")}</strong>{" "}
                registros encontrados
              </span>
            )}
          </p>
          <div className="flex gap-2">
            {filtrosAtivos > 0 && (
              <button
                type="button"
                onClick={limpar}
                className="text-sm text-slate-500 hover:text-slate-800"
              >
                Limpar
              </button>
            )}
            <button
              type="button"
              onClick={aplicar}
              className="btn-primary text-sm"
            >
              Aplicar filtros
            </button>
          </div>
        </div>
      </section>

      {/* ============ Lista ============ */}
      <section className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="px-5 py-3">Quando</th>
              <th className="px-5 py-3">Quem</th>
              <th className="px-5 py-3">Ação</th>
              <th className="px-5 py-3">Entidade</th>
              <th className="px-5 py-3">Mensagem</th>
              <th className="px-5 py-3 text-right">IP</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-500">
                  Carregando...
                </td>
              </tr>
            )}
            {!isLoading && itens.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-slate-500">
                  Nenhum registro encontrado pros filtros atuais.
                </td>
              </tr>
            )}
            {itens.map((it) => (
              <tr
                key={it.id}
                onClick={() => setDrawer(it)}
                className="border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer"
              >
                <td className="px-5 py-2.5 text-slate-500 text-xs tabular-nums whitespace-nowrap">
                  <span className="inline-flex items-center gap-1">
                    <Clock size={11} />
                    {formatDateTime(it.created_at)}
                  </span>
                </td>
                <td className="px-5 py-2.5">
                  {it.user_nome ? (
                    <div>
                      <p className="text-slate-800 font-medium">
                        {it.user_nome}
                      </p>
                      <p className="text-xs text-slate-400">{it.user_email}</p>
                    </div>
                  ) : (
                    <span className="italic text-slate-400 text-xs">
                      sistema
                    </span>
                  )}
                </td>
                <td className="px-5 py-2.5">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${corAcao(
                      it.acao,
                    )}`}
                  >
                    {it.acao}
                  </span>
                </td>
                <td className="px-5 py-2.5 text-xs text-slate-600">
                  {it.entidade_tipo ? (
                    <div>
                      <p className="font-medium text-slate-700">
                        {it.entidade_tipo}
                      </p>
                      {it.entidade_id && (
                        <p className="text-[11px] font-mono text-slate-400">
                          {it.entidade_id.slice(0, 8)}
                        </p>
                      )}
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-5 py-2.5 text-slate-600 max-w-md truncate">
                  {it.mensagem ?? <span className="text-slate-400">—</span>}
                </td>
                <td className="px-5 py-2.5 text-right font-mono text-[11px] text-slate-400">
                  {it.ip_address ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Paginação */}
        {data && data.total > perPage && (
          <footer className="flex items-center justify-between px-5 py-3 border-t border-slate-200 bg-slate-50">
            <p className="text-xs text-slate-500">
              Página {data.page} de {totalPages} · {data.total.toLocaleString("pt-BR")} registros
              {isFetching && <span className="ml-2 italic">atualizando...</span>}
            </p>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
              >
                <ChevronLeft size={14} /> Anterior
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
              >
                Próxima <ChevronRight size={14} />
              </button>
            </div>
          </footer>
        )}
      </section>

      {/* ============ Drawer de detalhe ============ */}
      {drawer && <DrawerDetalhe item={drawer} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function DrawerDetalhe({
  item,
  onClose,
}: {
  item: AuditoriaItem;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/40"
      onClick={onClose}
    >
      <aside
        className="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] bg-white shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <FileSearch size={18} /> Detalhe do evento
            </h3>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              {item.id.slice(0, 8)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </header>

        <div className="p-5 space-y-4 text-sm">
          <LinhaInfo label="Quando" valor={formatDateTime(item.created_at)} />
          <LinhaInfo
            label="Quem"
            valor={
              item.user_nome
                ? `${item.user_nome} (${item.user_email})`
                : "sistema"
            }
          />
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">
              Ação
            </p>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${corAcao(
                item.acao,
              )}`}
            >
              {item.acao}
            </span>
          </div>
          <LinhaInfo
            label="Entidade"
            valor={
              item.entidade_tipo
                ? `${item.entidade_tipo} ${item.entidade_id ?? ""}`
                : "—"
            }
          />
          <LinhaInfo label="IP" valor={item.ip_address ?? "—"} mono />
          <LinhaInfo
            label="Hash relacionado"
            valor={item.hash_relacionado ?? "—"}
            mono
          />
          <LinhaInfo
            label="Mensagem"
            valor={item.mensagem ?? "—"}
            block
          />

          {item.detalhes && (
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500 mb-1 flex items-center gap-1">
                <Hash size={11} /> Detalhes (JSON)
              </p>
              <pre className="bg-slate-900 text-slate-100 text-xs p-3 rounded-md overflow-x-auto font-mono">
                {JSON.stringify(item.detalhes, null, 2)}
              </pre>
            </div>
          )}

          {item.user_id && (
            <div className="text-xs text-slate-400 pt-3 border-t border-slate-200">
              <UserIcon size={11} className="inline" /> user_id:{" "}
              <span className="font-mono">{item.user_id}</span>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function LinhaInfo({
  label,
  valor,
  mono,
  block,
}: {
  label: string;
  valor: string;
  mono?: boolean;
  block?: boolean;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">
        {label}
      </p>
      <p
        className={`${block ? "whitespace-pre-wrap" : ""} ${
          mono ? "font-mono text-xs" : "text-sm"
        } text-slate-800`}
      >
        {valor}
      </p>
    </div>
  );
}
