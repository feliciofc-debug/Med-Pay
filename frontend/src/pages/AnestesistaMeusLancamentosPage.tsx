import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ClipboardList,
  Hospital,
  Lock,
  Plus,
  Trash2,
} from "lucide-react";

import { useAnestesistaSession } from "@/hooks/useAnestesistaSession";
import {
  anestesistaApi,
  getAnestesistaErrorMessage,
} from "@/lib/anestesistaApi";
import type {
  LancamentoServico,
  LancamentosListResponse,
  StatusLancamento,
} from "@/types";

function formatarBRL(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

function formatarData(iso: string): string {
  return new Date(iso + "T00:00").toLocaleDateString("pt-BR");
}

function corBadgeStatus(status: StatusLancamento): string {
  switch (status) {
    case "LANCADO":
      return "bg-amber-50 text-amber-800 border-amber-200";
    case "CONFERIDO":
      return "bg-blue-50 text-blue-800 border-blue-200";
    case "INCLUIDO_EM_LOTE":
      return "bg-indigo-50 text-indigo-800 border-indigo-200";
    case "PAGO":
      return "bg-green-50 text-green-800 border-green-200";
    case "CANCELADO":
      return "bg-slate-100 text-slate-600 border-slate-200";
  }
}

function rotuloStatus(status: StatusLancamento): string {
  switch (status) {
    case "LANCADO":
      return "Lançado";
    case "CONFERIDO":
      return "Conferido";
    case "INCLUIDO_EM_LOTE":
      return "No lote";
    case "PAGO":
      return "Pago";
    case "CANCELADO":
      return "Cancelado";
  }
}

export function AnestesistaMeusLancamentosPage() {
  const { medico, loading } = useAnestesistaSession();
  const navigate = useNavigate();

  const [items, setItems] = useState<LancamentoServico[]>([]);
  const [totalCentavos, setTotalCentavos] = useState(0);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [cancelando, setCancelando] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !medico) {
      navigate("/login");
    }
  }, [loading, medico, navigate]);

  async function carregar() {
    setCarregando(true);
    setErro(null);
    try {
      const { data } = await anestesistaApi.get<LancamentosListResponse>(
        "/api/anestesista/lancamentos",
      );
      setItems(data.items);
      setTotalCentavos(data.total_centavos);
    } catch (err) {
      setErro(getAnestesistaErrorMessage(err));
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    if (medico) void carregar();
  }, [medico]);

  async function cancelar(id: string) {
    if (!confirm("Cancelar este lançamento?")) return;
    setCancelando(id);
    try {
      await anestesistaApi.delete(`/api/anestesista/lancamentos/${id}`);
      await carregar();
    } catch (err) {
      alert(getAnestesistaErrorMessage(err));
    } finally {
      setCancelando(null);
    }
  }

  if (loading || !medico) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Carregando...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-accent-50/30">
      <header className="bg-white/80 backdrop-blur border-b border-brand-100 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate("/anestesista")}
            className="inline-flex items-center gap-1.5 text-sm text-brand-700 hover:text-brand-900"
          >
            <ArrowLeft size={16} /> Voltar
          </button>
          <button
            onClick={() => navigate("/anestesista")}
            className="btn-primary text-xs"
          >
            <Plus size={14} />
            Novo lançamento
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* KPI */}
        <section className="card border-brand-100 shadow-md">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-brand-700/70 uppercase tracking-wider">
                Seu total no período
              </p>
              <p className="text-3xl font-bold text-brand-900 mt-1">
                {formatarBRL(totalCentavos)}
              </p>
              <p className="text-xs text-brand-700/70 mt-1">
                {items.length}{" "}
                {items.length === 1 ? "lançamento" : "lançamentos"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-brand-700/70 uppercase tracking-wider">
                Anestesista
              </p>
              <p className="font-semibold text-brand-900">{medico.nome}</p>
              <p className="text-xs text-brand-700/70">CRM {medico.crm}</p>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-brand-700/70 bg-brand-50 rounded-lg px-3 py-2">
            <Lock size={12} />
            <span>
              <strong>Privado:</strong> apenas você vê seus lançamentos. O
              fechamento mensal é gerado pelo financeiro.
            </span>
          </div>
        </section>

        {/* Lista */}
        <section>
          <h2 className="text-sm font-semibold text-brand-900 mb-3 px-1">
            <ClipboardList size={14} className="inline mr-1.5" />
            Histórico
          </h2>

          {erro && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
              {erro}
            </div>
          )}

          {carregando ? (
            <p className="text-sm text-slate-500 text-center py-8">
              Carregando...
            </p>
          ) : items.length === 0 ? (
            <div className="card text-center py-10 border-dashed border-brand-200">
              <p className="text-sm text-slate-500">
                Você ainda não tem lançamentos.
              </p>
              <button
                onClick={() => navigate("/anestesista")}
                className="btn-primary text-xs mt-4"
              >
                <Plus size={14} />
                Lançar o primeiro serviço
              </button>
            </div>
          ) : (
            <ul className="space-y-2">
              {items.map((it) => (
                <li
                  key={it.id}
                  className="bg-white rounded-xl border border-brand-100 shadow-sm p-4 hover:shadow-md transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm font-semibold text-brand-900">
                          {it.codigo_snapshot}
                        </span>
                        <span
                          className={`text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border ${corBadgeStatus(
                            it.status,
                          )}`}
                        >
                          {rotuloStatus(it.status)}
                        </span>
                      </div>
                      <p className="text-sm text-brand-900">
                        {it.descricao_snapshot}
                      </p>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-brand-700/70 mt-2">
                        <span>{formatarData(it.data_servico)}</span>
                        {it.hospital_local && (
                          <span className="inline-flex items-center gap-1">
                            <Hospital size={11} /> {it.hospital_local}
                          </span>
                        )}
                        {it.paciente_iniciais && (
                          <span>Pac.: {it.paciente_iniciais}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-semibold text-brand-900">
                        {formatarBRL(it.valor_centavos)}
                      </p>
                      {it.status === "LANCADO" && (
                        <button
                          onClick={() => void cancelar(it.id)}
                          disabled={cancelando === it.id}
                          className="text-xs text-red-700/70 hover:text-red-700 inline-flex items-center gap-1 mt-2"
                        >
                          <Trash2 size={11} />
                          {cancelando === it.id ? "..." : "Cancelar"}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
