import { useEffect, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  Edit3,
  FileSpreadsheet,
  Filter,
  Plus,
  Search,
  Upload,
  UserCheck,
  UserMinus,
  Users,
  X,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type {
  Beneficiario,
  BeneficiarioListResponse,
  BeneficiarioPayload,
  BeneficiarioUpdatePayload,
  Cliente,
  ImportConfirmResponse,
  ImportPreviewResponse,
  StatusBeneficiario,
} from "@/types";

type Tab = "lista" | "importar" | "novo";

const STATUS_LABEL: Record<StatusBeneficiario, string> = {
  ATIVO: "Ativo",
  PENDENTE: "Pendente",
  INATIVO: "Inativo",
};

const STATUS_BADGE: Record<StatusBeneficiario, string> = {
  ATIVO: "bg-emerald-100 text-emerald-700 border-emerald-200",
  PENDENTE: "bg-amber-100 text-amber-700 border-amber-200",
  INATIVO: "bg-slate-100 text-slate-600 border-slate-200",
};

function formatCentavos(c: number | null): string {
  if (c == null) return "—";
  return (c / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function PrestadoresPage() {
  const [tab, setTab] = useState<Tab>("lista");
  const [clienteId, setClienteId] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusBeneficiario | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [detalheId, setDetalheId] = useState<string | null>(null);

  // Hospitais (clientes) — pra escolher escopo do cadastro
  const { data: clientes = [] } = useQuery<Cliente[]>({
    queryKey: ["clientes-prestadores"],
    queryFn: async () => {
      const { data } = await api.get<{ clientes: Cliente[] }>(
        "/api/clientes/",
      );
      return data.clientes ?? [];
    },
  });

  useEffect(() => {
    if (!clienteId && clientes.length > 0) setClienteId(clientes[0].id);
  }, [clienteId, clientes]);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-brand-900 flex items-center gap-2">
            <Users size={24} className="text-accent-600" />
            Prestadores
          </h1>
          <p className="text-sm text-brand-700/70 mt-1 max-w-2xl">
            Cadastro mestre de médicos e prestadores por hospital. Toda
            ficha emitida pelo coordenador é cruzada com este cadastro
            via CPF — os dados bancários cadastrados aqui são a fonte de
            verdade da operação.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab("importar")}
            className="px-3 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50 flex items-center gap-2"
          >
            <Upload size={16} />
            Importar planilha
          </button>
          <button
            type="button"
            onClick={() => setTab("novo")}
            className="btn-primary"
          >
            <Plus size={16} />
            Novo prestador
          </button>
        </div>
      </header>

      {/* Seletor de hospital + tabs */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-slate-700">Hospital:</label>
        <select
          value={clienteId}
          onChange={(e) => {
            setClienteId(e.target.value);
            setPage(1);
          }}
          className="input max-w-xs"
        >
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
          {clientes.length === 0 && (
            <option value="">Sem hospitais cadastrados</option>
          )}
        </select>

        {tab !== "lista" && (
          <button
            type="button"
            onClick={() => setTab("lista")}
            className="text-sm text-slate-600 hover:underline flex items-center gap-1"
          >
            <ChevronLeft size={14} /> voltar à lista
          </button>
        )}
      </div>

      {tab === "lista" && (
        <ListaPrestadores
          clienteId={clienteId}
          statusFilter={statusFilter}
          setStatusFilter={(s) => {
            setStatusFilter(s);
            setPage(1);
          }}
          search={search}
          setSearch={(s) => {
            setSearch(s);
            setPage(1);
          }}
          page={page}
          setPage={setPage}
          onAbrirDetalhe={setDetalheId}
        />
      )}

      {tab === "importar" && clienteId && (
        <WizardImportacao
          clienteId={clienteId}
          onConcluido={() => setTab("lista")}
        />
      )}

      {tab === "novo" && clienteId && (
        <FormularioPrestador
          clienteId={clienteId}
          onSalvo={() => setTab("lista")}
          onCancelar={() => setTab("lista")}
        />
      )}

      {detalheId && (
        <DrawerDetalhe
          beneficiarioId={detalheId}
          onClose={() => setDetalheId(null)}
        />
      )}
    </div>
  );
}

// ============================================================
// Lista
// ============================================================

function ListaPrestadores({
  clienteId,
  statusFilter,
  setStatusFilter,
  search,
  setSearch,
  page,
  setPage,
  onAbrirDetalhe,
}: {
  clienteId: string;
  statusFilter: StatusBeneficiario | "";
  setStatusFilter: (s: StatusBeneficiario | "") => void;
  search: string;
  setSearch: (s: string) => void;
  page: number;
  setPage: (n: number) => void;
  onAbrirDetalhe: (id: string) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["beneficiarios", clienteId, statusFilter, search, page],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        cliente_id: clienteId,
        page,
        per_page: 50,
      };
      if (statusFilter) params.status = statusFilter;
      if (search.trim()) params.search = search.trim();
      const { data } = await api.get<BeneficiarioListResponse>(
        "/api/beneficiarios",
        { params },
      );
      return data;
    },
    enabled: !!clienteId,
  });

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[260px]">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome ou CPF..."
            className="input pl-9"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-slate-500" />
          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as StatusBeneficiario | "")
            }
            className="input"
          >
            <option value="">Todos os status</option>
            <option value="ATIVO">Ativos</option>
            <option value="PENDENTE">Pendentes</option>
            <option value="INATIVO">Inativos</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-slate-500 p-6">Carregando…</div>
      ) : !data || data.items.length === 0 ? (
        <EstadoVazio statusFilter={statusFilter} />
      ) : (
        <>
          <div className="text-xs text-slate-500">
            {data.total} prestador{data.total === 1 ? "" : "es"} no escopo
          </div>
          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="text-left px-4 py-2 font-medium">Nome</th>
                  <th className="text-left px-4 py-2 font-medium">CPF</th>
                  <th className="text-left px-4 py-2 font-medium">Categoria</th>
                  <th className="text-left px-4 py-2 font-medium">Banco</th>
                  <th className="text-left px-4 py-2 font-medium">Conta</th>
                  <th className="text-left px-4 py-2 font-medium">PIX</th>
                  <th className="text-left px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => onAbrirDetalhe(b.id)}
                    className="border-b border-slate-100 cursor-pointer hover:bg-slate-50"
                  >
                    <td className="px-4 py-2 font-medium text-slate-800">
                      {b.nome}
                      {b.crm && (
                        <span className="text-xs text-slate-500 ml-2 font-normal">
                          {b.crm}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {b.cpf_mascarado}
                    </td>
                    <td className="px-4 py-2 text-slate-600">
                      {b.categoria || "—"}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {b.banco_codigo || "—"}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {b.conta_mascarada || "—"}
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {b.pix_chave_mascarada || "—"}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${STATUS_BADGE[b.status]}`}
                      >
                        {STATUS_LABEL[b.status]}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.total_pages > 1 && (
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 text-sm border border-slate-200 rounded disabled:opacity-40"
              >
                Anterior
              </button>
              <span className="text-xs text-slate-500">
                {page} / {data.total_pages}
              </span>
              <button
                disabled={page >= data.total_pages}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 text-sm border border-slate-200 rounded disabled:opacity-40"
              >
                Próxima
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function EstadoVazio({
  statusFilter,
}: {
  statusFilter: StatusBeneficiario | "";
}) {
  return (
    <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-12 text-center">
      <Users size={32} className="text-slate-300 mx-auto" />
      <h3 className="mt-3 text-sm font-medium text-slate-800">
        {statusFilter
          ? `Nenhum prestador ${STATUS_LABEL[statusFilter as StatusBeneficiario].toLowerCase()}`
          : "Nenhum prestador cadastrado neste hospital"}
      </h3>
      <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
        Use <strong>“Importar planilha”</strong> para subir a base completa de
        uma vez, ou <strong>“Novo prestador”</strong> para cadastrar um a um.
      </p>
    </div>
  );
}

// ============================================================
// Wizard de importação
// ============================================================

function WizardImportacao({
  clienteId,
  onConcluido,
}: {
  clienteId: string;
  onConcluido: () => void;
}) {
  const queryClient = useQueryClient();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [politica, setPolitica] = useState<"IGNORAR" | "ATUALIZAR">("IGNORAR");
  const [resultado, setResultado] = useState<ImportConfirmResponse | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const previewMut = useMutation({
    mutationFn: async (f: File) => {
      const fd = new FormData();
      fd.append("cliente_id", clienteId);
      fd.append("arquivo", f);
      const { data } = await api.post<ImportPreviewResponse>(
        "/api/beneficiarios/import/preview",
        fd,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      return data;
    },
    onSuccess: (d) => {
      setPreview(d);
      setErro(null);
    },
    onError: (e) => {
      setPreview(null);
      setErro(getErrorMessage(e));
    },
  });

  const confirmarMut = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error("Sem preview");
      const { data } = await api.post<ImportConfirmResponse>(
        "/api/beneficiarios/import/confirm",
        { token: preview.token, politica_atualizacao: politica },
      );
      return data;
    },
    onSuccess: (d) => {
      setResultado(d);
      void queryClient.invalidateQueries({ queryKey: ["beneficiarios"] });
    },
    onError: (e) => {
      setErro(getErrorMessage(e));
    },
  });

  function handleFile(f: File | null) {
    setArquivo(f);
    setPreview(null);
    setResultado(null);
    setErro(null);
    if (f) previewMut.mutate(f);
  }

  if (resultado) {
    return (
      <div className="bg-white rounded-2xl border border-emerald-200 p-6 max-w-2xl">
        <div className="flex items-center gap-2 text-emerald-700">
          <CheckCircle2 size={20} />
          <h2 className="text-lg font-semibold">Importação concluída</h2>
        </div>
        <ul className="mt-4 text-sm text-slate-700 space-y-1">
          <li>
            <strong>{resultado.qtd_criados}</strong> prestador(es) criado(s)
          </li>
          <li>
            <strong>{resultado.qtd_atualizados}</strong> atualizado(s)
          </li>
          <li>
            <strong>{resultado.qtd_ignorados}</strong> ignorado(s)
          </li>
          {resultado.qtd_erros > 0 && (
            <li className="text-red-600">
              <strong>{resultado.qtd_erros}</strong> com erro (não importado)
            </li>
          )}
        </ul>
        <div className="mt-6 flex gap-2">
          <button onClick={onConcluido} className="btn-primary">
            Voltar à lista
          </button>
          <button
            onClick={() => {
              setArquivo(null);
              setPreview(null);
              setResultado(null);
              if (fileInputRef.current) fileInputRef.current.value = "";
            }}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg"
          >
            Importar outra planilha
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-accent-50 border border-accent-200 rounded-xl p-4 text-sm text-accent-900">
        <p className="font-medium mb-1">Formato esperado</p>
        <p className="text-accent-800/90">
          Arquivo XLSX, XLS ou CSV. Colunas obrigatórias:{" "}
          <code className="bg-white/60 px-1">CPF</code> e{" "}
          <code className="bg-white/60 px-1">Nome</code>. Opcionais
          reconhecidas automaticamente: CRM, Categoria, Email, Telefone,
          Banco, Agência, Conta, PIX, Tipo PIX, Valor padrão. Os cabeçalhos
          aceitam variações (ex.: "C P F", "Cód. Banco", "Chave PIX").
        </p>
      </div>

      <label className="block">
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          className="hidden"
        />
        <div
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer border-2 border-dashed border-slate-300 rounded-2xl p-8 text-center hover:border-accent-400 hover:bg-accent-50/40 transition"
        >
          <FileSpreadsheet size={32} className="mx-auto text-slate-400" />
          <p className="mt-3 text-sm font-medium text-slate-800">
            {arquivo
              ? arquivo.name
              : "Clique para escolher a planilha (XLSX, XLS, CSV)"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Ou arraste e solte aqui
          </p>
        </div>
      </label>

      {previewMut.isPending && (
        <div className="text-sm text-slate-500">Analisando planilha…</div>
      )}

      {erro && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800 flex items-start gap-2">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          {erro}
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiBox label="Total de linhas" value={preview.total_linhas} />
            <KpiBox
              label="Novos cadastros"
              value={preview.qtd_ok}
              tone="emerald"
            />
            <KpiBox
              label="Atualizam existente"
              value={preview.qtd_atualiza}
              tone="amber"
            />
            <KpiBox label="Erros" value={preview.qtd_erro} tone="red" />
          </div>

          {preview.qtd_atualiza > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-sm font-medium text-slate-800 mb-2">
                {preview.qtd_atualiza} linha(s) batem com cadastros já
                existentes mas com dados bancários diferentes:
              </p>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="politica"
                  value="IGNORAR"
                  checked={politica === "IGNORAR"}
                  onChange={() => setPolitica("IGNORAR")}
                />
                Ignorar (mantém o cadastro atual)
              </label>
              <label className="flex items-center gap-2 text-sm mt-1">
                <input
                  type="radio"
                  name="politica"
                  value="ATUALIZAR"
                  checked={politica === "ATUALIZAR"}
                  onChange={() => setPolitica("ATUALIZAR")}
                />
                Atualizar com os dados da planilha
              </label>
            </div>
          )}

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden max-h-96 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 sticky top-0">
                <tr className="text-slate-600">
                  <th className="text-left px-3 py-2">#</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Nome</th>
                  <th className="text-left px-3 py-2">CPF</th>
                  <th className="text-left px-3 py-2">Banco / Conta</th>
                  <th className="text-left px-3 py-2">PIX</th>
                  <th className="text-left px-3 py-2">Avisos / Erros</th>
                </tr>
              </thead>
              <tbody>
                {preview.linhas.map((l) => (
                  <tr
                    key={l.linha_planilha}
                    className="border-b border-slate-100"
                  >
                    <td className="px-3 py-2 font-mono">{l.linha_planilha}</td>
                    <td className="px-3 py-2">
                      <BadgeStatusLinha status={l.status} />
                    </td>
                    <td className="px-3 py-2 font-medium">{l.nome || "—"}</td>
                    <td className="px-3 py-2 font-mono">
                      {l.cpf_mascarado || "—"}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {l.banco_codigo
                        ? `${l.banco_codigo} / ${l.conta_mascarada || "—"}`
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      {l.pix_chave_mascarada
                        ? `${l.pix_tipo || ""} ${l.pix_chave_mascarada}`
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      {[...l.erros, ...l.avisos].map((m, i) => (
                        <div
                          key={i}
                          className={
                            l.erros.includes(m)
                              ? "text-red-600"
                              : "text-amber-600"
                          }
                        >
                          {m}
                        </div>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setArquivo(null);
                setPreview(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              className="px-3 py-2 text-sm border border-slate-200 rounded-lg"
            >
              Cancelar
            </button>
            <button
              onClick={() => confirmarMut.mutate()}
              disabled={confirmarMut.isPending || preview.qtd_ok === 0}
              className="btn-primary"
            >
              {confirmarMut.isPending
                ? "Importando…"
                : `Confirmar importação (${preview.qtd_ok + (politica === "ATUALIZAR" ? preview.qtd_atualiza : 0)} cadastros)`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function KpiBox({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: number;
  tone?: "slate" | "emerald" | "amber" | "red";
}) {
  const cls: Record<string, string> = {
    slate: "border-slate-200",
    emerald: "border-emerald-200 bg-emerald-50",
    amber: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
  };
  return (
    <div className={`bg-white border rounded-xl p-3 ${cls[tone]}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-bold text-slate-800 mt-1">{value}</div>
    </div>
  );
}

function BadgeStatusLinha({ status }: { status: string }) {
  const map: Record<string, string> = {
    OK: "bg-emerald-100 text-emerald-700",
    ATUALIZA: "bg-amber-100 text-amber-700",
    DUPLICADO: "bg-slate-100 text-slate-600",
    ERRO: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs ${map[status] ?? "bg-slate-100 text-slate-600"}`}
    >
      {status}
    </span>
  );
}

// ============================================================
// Formulário de cadastro / edição manual
// ============================================================

const PIX_TIPOS = ["CPF", "CNPJ", "EMAIL", "TELEFONE", "ALEATORIA"] as const;

function FormularioPrestador({
  clienteId,
  onSalvo,
  onCancelar,
  beneficiario,
}: {
  clienteId: string;
  onSalvo: () => void;
  onCancelar: () => void;
  beneficiario?: Beneficiario;
}) {
  const queryClient = useQueryClient();
  const editando = !!beneficiario;
  const [erro, setErro] = useState<string | null>(null);

  const [form, setForm] = useState({
    nome: beneficiario?.nome ?? "",
    cpf: "", // sempre vazio na edição (segurança)
    crm: beneficiario?.crm ?? "",
    categoria: beneficiario?.categoria ?? "",
    especialidade: beneficiario?.especialidade ?? "",
    email: beneficiario?.email ?? "",
    telefone: beneficiario?.telefone ?? "",
    banco_codigo: beneficiario?.banco_codigo ?? "",
    agencia: "",
    conta: "",
    pix_tipo: beneficiario?.pix_tipo ?? "",
    pix_chave: "",
    valor_padrao: beneficiario?.valor_padrao_centavos
      ? (beneficiario.valor_padrao_centavos / 100).toFixed(2)
      : "",
    observacoes: beneficiario?.observacoes ?? "",
    status: beneficiario?.status ?? ("ATIVO" as StatusBeneficiario),
  });

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  const mut = useMutation({
    mutationFn: async () => {
      const valorCentavos = form.valor_padrao
        ? Math.round(parseFloat(form.valor_padrao.replace(",", ".")) * 100)
        : null;
      if (editando && beneficiario) {
        const payload: BeneficiarioUpdatePayload = {
          nome: form.nome || undefined,
          crm: form.crm || null,
          categoria: form.categoria || null,
          especialidade: form.especialidade || null,
          email: form.email || null,
          telefone: form.telefone || null,
          banco_codigo: form.banco_codigo || null,
          agencia: form.agencia || undefined,
          conta: form.conta || undefined,
          pix_tipo: form.pix_tipo || null,
          pix_chave: form.pix_chave || undefined,
          valor_padrao_centavos: valorCentavos,
          observacoes: form.observacoes || null,
          status: form.status,
        };
        const { data } = await api.patch<Beneficiario>(
          `/api/beneficiarios/${beneficiario.id}`,
          payload,
        );
        return data;
      }
      const payload: BeneficiarioPayload = {
        cliente_id: clienteId,
        nome: form.nome,
        cpf: form.cpf,
        crm: form.crm || null,
        categoria: form.categoria || null,
        especialidade: form.especialidade || null,
        email: form.email || null,
        telefone: form.telefone || null,
        banco_codigo: form.banco_codigo || null,
        agencia: form.agencia || null,
        conta: form.conta || null,
        pix_tipo: form.pix_tipo || null,
        pix_chave: form.pix_chave || null,
        valor_padrao_centavos: valorCentavos,
        observacoes: form.observacoes || null,
        status: form.status,
      };
      const { data } = await api.post<Beneficiario>(
        "/api/beneficiarios",
        payload,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["beneficiarios"] });
      onSalvo();
    },
    onError: (e) => setErro(getErrorMessage(e)),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setErro(null);
        if (!form.nome.trim()) {
          setErro("Nome obrigatório.");
          return;
        }
        if (!editando && !form.cpf.trim()) {
          setErro("CPF obrigatório no cadastro novo.");
          return;
        }
        mut.mutate();
      }}
      className="bg-white rounded-2xl border border-slate-200 p-5 space-y-5 max-w-4xl"
    >
      {erro && (
        <div className="bg-red-50 border border-red-200 rounded p-2 text-sm text-red-700 flex gap-2">
          <AlertTriangle size={16} /> {erro}
        </div>
      )}

      <Section title="Identificação">
        <Field label="Nome *" colSpan={2}>
          <input
            required
            value={form.nome}
            onChange={(e) => set("nome", e.target.value)}
            className="input"
          />
        </Field>
        <Field label={editando ? "CPF (não pode editar)" : "CPF *"}>
          <input
            disabled={editando}
            value={editando ? beneficiario.cpf_mascarado : form.cpf}
            onChange={(e) => set("cpf", e.target.value)}
            placeholder="000.000.000-00"
            className="input font-mono disabled:bg-slate-100"
          />
        </Field>
        <Field label="CRM / Registro">
          <input
            value={form.crm}
            onChange={(e) => set("crm", e.target.value)}
            className="input font-mono"
          />
        </Field>
        <Field label="Categoria">
          <input
            value={form.categoria}
            onChange={(e) => set("categoria", e.target.value)}
            placeholder="Médico, Enfermeiro, Limpeza…"
            className="input"
          />
        </Field>
        <Field label="Especialidade">
          <input
            value={form.especialidade}
            onChange={(e) => set("especialidade", e.target.value)}
            className="input"
          />
        </Field>
      </Section>

      <Section title="Contato">
        <Field label="E-mail" colSpan={2}>
          <input
            type="email"
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            className="input"
          />
        </Field>
        <Field label="Telefone">
          <input
            value={form.telefone}
            onChange={(e) => set("telefone", e.target.value)}
            className="input font-mono"
          />
        </Field>
      </Section>

      <Section title="Dados de pagamento">
        <Field label="Banco (3 díg)">
          <input
            value={form.banco_codigo}
            onChange={(e) => set("banco_codigo", e.target.value)}
            maxLength={3}
            className="input font-mono"
          />
        </Field>
        <Field label="Agência">
          <input
            value={form.agencia}
            onChange={(e) => set("agencia", e.target.value)}
            placeholder={
              editando
                ? `(atual: ${beneficiario.agencia_mascarada ?? "—"})`
                : ""
            }
            className="input font-mono"
          />
        </Field>
        <Field label="Conta">
          <input
            value={form.conta}
            onChange={(e) => set("conta", e.target.value)}
            placeholder={
              editando ? `(atual: ${beneficiario.conta_mascarada ?? "—"})` : ""
            }
            className="input font-mono"
          />
        </Field>
        <Field label="Tipo PIX">
          <select
            value={form.pix_tipo}
            onChange={(e) => set("pix_tipo", e.target.value)}
            className="input"
          >
            <option value="">—</option>
            {PIX_TIPOS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Chave PIX" colSpan={2}>
          <input
            value={form.pix_chave}
            onChange={(e) => set("pix_chave", e.target.value)}
            placeholder={
              editando
                ? `(atual: ${beneficiario.pix_chave_mascarada ?? "—"})`
                : ""
            }
            className="input font-mono"
          />
        </Field>
        <Field label="Valor padrão (R$)">
          <input
            value={form.valor_padrao}
            onChange={(e) => set("valor_padrao", e.target.value)}
            placeholder="ex.: 1500.00"
            className="input font-mono"
          />
        </Field>
        <Field label="Status">
          <select
            value={form.status}
            onChange={(e) =>
              set("status", e.target.value as StatusBeneficiario)
            }
            className="input"
          >
            <option value="ATIVO">Ativo</option>
            <option value="PENDENTE">Pendente</option>
            <option value="INATIVO">Inativo</option>
          </select>
        </Field>
      </Section>

      <Section title="Observações">
        <Field label="" colSpan={3}>
          <textarea
            value={form.observacoes}
            onChange={(e) => set("observacoes", e.target.value)}
            rows={2}
            className="input"
          />
        </Field>
      </Section>

      <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
        <button
          type="button"
          onClick={onCancelar}
          className="px-3 py-2 text-sm border border-slate-200 rounded-lg"
        >
          Cancelar
        </button>
        <button type="submit" disabled={mut.isPending} className="btn-primary">
          {mut.isPending ? "Salvando…" : editando ? "Salvar" : "Cadastrar"}
        </button>
      </div>
    </form>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-brand-900 mb-3">{title}</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">{children}</div>
    </div>
  );
}

function Field({
  label,
  colSpan,
  children,
}: {
  label: string;
  colSpan?: 2 | 3;
  children: React.ReactNode;
}) {
  const cls =
    colSpan === 3
      ? "md:col-span-3"
      : colSpan === 2
        ? "md:col-span-2"
        : "";
  return (
    <div className={cls}>
      {label && (
        <label className="block text-xs font-medium text-slate-600 mb-1">
          {label}
        </label>
      )}
      {children}
    </div>
  );
}

// ============================================================
// Drawer de detalhe
// ============================================================

function DrawerDetalhe({
  beneficiarioId,
  onClose,
}: {
  beneficiarioId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [editando, setEditando] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["beneficiario", beneficiarioId],
    queryFn: async () => {
      const { data } = await api.get<Beneficiario>(
        `/api/beneficiarios/${beneficiarioId}`,
      );
      return data;
    },
  });

  const aprovarMut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Beneficiario>(
        `/api/beneficiarios/${beneficiarioId}/aprovar`,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["beneficiarios"] });
      void queryClient.invalidateQueries({
        queryKey: ["beneficiario", beneficiarioId],
      });
    },
  });

  const desativarMut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<Beneficiario>(
        `/api/beneficiarios/${beneficiarioId}/desativar`,
      );
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["beneficiarios"] });
      void queryClient.invalidateQueries({
        queryKey: ["beneficiario", beneficiarioId],
      });
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 bg-slate-900/40"
        onClick={onClose}
        aria-hidden
      />
      <aside className="relative ml-auto w-full max-w-2xl bg-white h-full overflow-y-auto shadow-xl">
        <header className="sticky top-0 bg-white border-b border-slate-200 p-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-brand-900">
            Detalhes do prestador
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100"
            aria-label="Fechar"
          >
            <X size={18} />
          </button>
        </header>
        <div className="p-4 space-y-4">
          {isLoading || !data ? (
            <div className="text-sm text-slate-500">Carregando…</div>
          ) : editando ? (
            <FormularioPrestador
              clienteId={data.cliente_id}
              beneficiario={data}
              onSalvo={() => setEditando(false)}
              onCancelar={() => setEditando(false)}
            />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs border ${STATUS_BADGE[data.status]}`}
                >
                  {STATUS_LABEL[data.status]}
                </span>
                <span className="text-xs text-slate-500">
                  Origem: {data.origem_cadastro}
                </span>
              </div>
              <div>
                <h3 className="text-xl font-semibold">{data.nome}</h3>
                <p className="font-mono text-sm text-slate-600">
                  {data.cpf_mascarado}
                </p>
              </div>
              <Grid>
                <Item label="CRM">{data.crm || "—"}</Item>
                <Item label="Categoria">{data.categoria || "—"}</Item>
                <Item label="Especialidade">{data.especialidade || "—"}</Item>
                <Item label="E-mail">{data.email || "—"}</Item>
                <Item label="Telefone">{data.telefone || "—"}</Item>
                <Item label="Valor padrão">
                  {formatCentavos(data.valor_padrao_centavos)}
                </Item>
                <Item label="Banco">{data.banco_codigo || "—"}</Item>
                <Item label="Agência">{data.agencia_mascarada || "—"}</Item>
                <Item label="Conta">{data.conta_mascarada || "—"}</Item>
                <Item label="PIX">
                  {data.pix_chave_mascarada
                    ? `${data.pix_tipo} ${data.pix_chave_mascarada}`
                    : "—"}
                </Item>
              </Grid>
              <div className="bg-slate-50 rounded-xl p-3 text-xs text-slate-600">
                <div>
                  <strong>{data.total_pagamentos}</strong> pagamentos
                </div>
                <div>
                  Médio: {formatCentavos(data.valor_medio_centavos)} · Min:{" "}
                  {formatCentavos(data.valor_min_centavos)} · Max:{" "}
                  {formatCentavos(data.valor_max_centavos)}
                </div>
                {data.ultimo_pagamento_at && (
                  <div>
                    Último pgto:{" "}
                    {new Date(data.ultimo_pagamento_at).toLocaleString(
                      "pt-BR",
                    )}
                  </div>
                )}
              </div>
              {data.observacoes && (
                <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm">
                  {data.observacoes}
                </div>
              )}
              <div className="flex gap-2 pt-3 border-t border-slate-200">
                <button
                  onClick={() => setEditando(true)}
                  className="px-3 py-2 text-sm border border-slate-200 rounded-lg flex items-center gap-2 hover:bg-slate-50"
                >
                  <Edit3 size={14} /> Editar
                </button>
                {data.status === "PENDENTE" && (
                  <button
                    onClick={() => aprovarMut.mutate()}
                    className="px-3 py-2 text-sm bg-emerald-600 text-white rounded-lg flex items-center gap-2"
                  >
                    <UserCheck size={14} /> Aprovar
                  </button>
                )}
                {data.status === "ATIVO" && (
                  <button
                    onClick={() => desativarMut.mutate()}
                    className="px-3 py-2 text-sm border border-red-200 text-red-700 rounded-lg flex items-center gap-2 hover:bg-red-50"
                  >
                    <UserMinus size={14} /> Desativar
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}

function Item({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-slate-100 rounded p-2">
      <div className="text-[10px] text-slate-500 uppercase">{label}</div>
      <div className="text-sm text-slate-800 font-medium mt-0.5">
        {children}
      </div>
    </div>
  );
}
