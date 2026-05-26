import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calendar,
  CheckCircle2,
  ClipboardList,
  Hospital,
  LogOut,
  Search,
  Stethoscope,
  User2,
} from "lucide-react";

import { useAnestesistaSession } from "@/hooks/useAnestesistaSession";
import {
  anestesistaApi,
  getAnestesistaErrorMessage,
} from "@/lib/anestesistaApi";
import type { CodigoServico, LancamentoServico } from "@/types";

function formatarBRL(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

function hojeISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AnestesistaLancarPage() {
  const { medico, loading, logout } = useAnestesistaSession();
  const navigate = useNavigate();

  const [codigoInput, setCodigoInput] = useState("");
  const [data, setData] = useState(hojeISO());
  const [hospital, setHospital] = useState("");
  const [pacienteIniciais, setPacienteIniciais] = useState("");
  const [observacoes, setObservacoes] = useState("");

  const [codigoEncontrado, setCodigoEncontrado] = useState<CodigoServico | null>(
    null,
  );
  const [buscandoCodigo, setBuscandoCodigo] = useState(false);
  const [erroBusca, setErroBusca] = useState<string | null>(null);

  const [salvando, setSalvando] = useState(false);
  const [sucesso, setSucesso] = useState<LancamentoServico | null>(null);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !medico) {
      navigate("/login");
    }
  }, [loading, medico, navigate]);

  async function buscarCodigo() {
    const cod = codigoInput.trim();
    if (!cod) return;
    setBuscandoCodigo(true);
    setErroBusca(null);
    setCodigoEncontrado(null);
    try {
      const { data: c } = await anestesistaApi.get<CodigoServico>(
        `/api/anestesista/codigos/${encodeURIComponent(cod)}`,
      );
      setCodigoEncontrado(c);
    } catch (err) {
      setErroBusca(getAnestesistaErrorMessage(err));
    } finally {
      setBuscandoCodigo(false);
    }
  }

  async function lancar(e: React.FormEvent) {
    e.preventDefault();
    if (!codigoEncontrado) {
      setErroSalvar("Busque o código do serviço antes de lançar.");
      return;
    }
    setSalvando(true);
    setErroSalvar(null);
    try {
      const { data: created } = await anestesistaApi.post<LancamentoServico>(
        "/api/anestesista/lancamentos",
        {
          codigo: codigoEncontrado.codigo,
          data_servico: data,
          hospital_local: hospital || null,
          paciente_iniciais: pacienteIniciais || null,
          observacoes: observacoes || null,
        },
      );
      setSucesso(created);
      setCodigoInput("");
      setHospital("");
      setPacienteIniciais("");
      setObservacoes("");
      setCodigoEncontrado(null);
    } catch (err) {
      setErroSalvar(getAnestesistaErrorMessage(err));
    } finally {
      setSalvando(false);
    }
  }

  function novoLancamento() {
    setSucesso(null);
    setCodigoInput("");
    setData(hojeISO());
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
      {/* Topo */}
      <header className="bg-white/80 backdrop-blur border-b border-brand-100 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-brand-900 rounded-xl flex items-center justify-center text-accent-300 font-bold border border-accent-400/40">
              M
            </div>
            <div>
              <p className="text-sm font-semibold text-brand-900 tracking-wide">
                Lançamento de Serviço
              </p>
              <p className="text-xs text-brand-700/70">{medico.cliente_nome}</p>
            </div>
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="text-xs text-brand-700/70 hover:text-brand-900 inline-flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-brand-50 transition"
          >
            <LogOut size={14} />
            Sair
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* Card de identidade */}
        <section className="card border-brand-100 shadow-md">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-brand-100 rounded-full flex items-center justify-center text-brand-700">
              <Stethoscope size={22} />
            </div>
            <div className="flex-1">
              <p className="text-xs text-brand-700/70 uppercase tracking-wider">
                Anestesista
              </p>
              <p className="text-lg font-semibold text-brand-900">
                {medico.nome}
              </p>
              <p className="text-xs text-brand-700/70">
                CRM {medico.crm ?? "-"}
                {medico.especialidade ? ` • ${medico.especialidade}` : ""}
              </p>
            </div>
            <button
              onClick={() => navigate("/anestesista/meus-lancamentos")}
              className="btn-secondary text-xs"
            >
              <ClipboardList size={14} />
              Meus lançamentos
            </button>
          </div>
        </section>

        {/* Mensagem de sucesso */}
        {sucesso && (
          <section className="rounded-xl border-2 border-success/30 bg-green-50 p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-success shrink-0" size={28} />
              <div className="flex-1">
                <p className="font-semibold text-green-900">
                  Lançamento registrado!
                </p>
                <p className="text-sm text-green-800 mt-1">
                  <strong>{sucesso.codigo_snapshot}</strong> —{" "}
                  {sucesso.descricao_snapshot}
                </p>
                <p className="text-sm text-green-800">
                  Valor:{" "}
                  <strong>{formatarBRL(sucesso.valor_centavos)}</strong> em{" "}
                  {new Date(sucesso.data_servico + "T00:00").toLocaleDateString(
                    "pt-BR",
                  )}
                </p>
                <div className="mt-3 flex gap-2">
                  <button
                    className="btn-primary text-sm"
                    onClick={novoLancamento}
                  >
                    Lançar outro
                  </button>
                  <button
                    className="btn-secondary text-sm"
                    onClick={() => navigate("/anestesista/meus-lancamentos")}
                  >
                    Ver meus lançamentos
                  </button>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Form de lançamento */}
        {!sucesso && (
          <form onSubmit={lancar} className="card border-brand-100 space-y-5">
            <div>
              <h2 className="text-base font-semibold text-brand-900 mb-1">
                Novo lançamento
              </h2>
              <p className="text-xs text-brand-700/70">
                Informe a data, busque o código do serviço e confirme. Você só
                vê os seus próprios lançamentos.
              </p>
            </div>

            {/* Data */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                <Calendar size={14} className="inline mr-1" /> Data do serviço
              </label>
              <input
                type="date"
                required
                value={data}
                onChange={(e) => setData(e.target.value)}
                max={hojeISO()}
                className="input"
              />
            </div>

            {/* Código */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Código do serviço
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Ex: ANE001"
                  value={codigoInput}
                  onChange={(e) =>
                    setCodigoInput(e.target.value.toUpperCase())
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void buscarCodigo();
                    }
                  }}
                  className="input uppercase font-mono"
                />
                <button
                  type="button"
                  onClick={() => void buscarCodigo()}
                  disabled={!codigoInput || buscandoCodigo}
                  className="btn-secondary shrink-0"
                >
                  <Search size={16} />
                  {buscandoCodigo ? "Buscando..." : "Buscar"}
                </button>
              </div>
              {erroBusca && (
                <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-2 py-1.5 mt-2">
                  {erroBusca}
                </p>
              )}
            </div>

            {/* Resultado do código */}
            {codigoEncontrado && (
              <div className="rounded-lg border-2 border-accent-300 bg-accent-50/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="text-xs text-brand-700/70 uppercase tracking-wider">
                      Serviço identificado
                    </p>
                    <p className="font-mono text-sm font-semibold text-brand-900">
                      {codigoEncontrado.codigo}
                    </p>
                    <p className="text-sm text-brand-900 mt-1">
                      {codigoEncontrado.descricao}
                    </p>
                    {codigoEncontrado.categoria && (
                      <p className="text-xs text-brand-700/70 mt-1">
                        Categoria: {codigoEncontrado.categoria}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-brand-700/70 uppercase tracking-wider">
                      Valor
                    </p>
                    <p className="text-xl font-bold text-brand-900">
                      {formatarBRL(codigoEncontrado.valor_centavos)}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Hospital */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                <Hospital size={14} className="inline mr-1" /> Hospital / local{" "}
                <span className="text-slate-400 font-normal">(opcional)</span>
              </label>
              <input
                type="text"
                value={hospital}
                onChange={(e) => setHospital(e.target.value)}
                placeholder="Ex: Hospital São Lucas"
                className="input"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  <User2 size={14} className="inline mr-1" /> Iniciais do
                  paciente{" "}
                  <span className="text-slate-400 font-normal">(opcional)</span>
                </label>
                <input
                  type="text"
                  maxLength={10}
                  value={pacienteIniciais}
                  onChange={(e) =>
                    setPacienteIniciais(e.target.value.toUpperCase())
                  }
                  placeholder="Ex: J.M.S."
                  className="input uppercase font-mono"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Observações{" "}
                  <span className="text-slate-400 font-normal">(opcional)</span>
                </label>
                <input
                  type="text"
                  value={observacoes}
                  onChange={(e) => setObservacoes(e.target.value)}
                  placeholder="Detalhes adicionais"
                  className="input"
                />
              </div>
            </div>

            {erroSalvar && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {erroSalvar}
              </div>
            )}

            <button
              type="submit"
              disabled={salvando || !codigoEncontrado}
              className="btn-primary w-full"
            >
              {salvando ? "Lançando..." : "Confirmar lançamento"}
            </button>
          </form>
        )}

        <p className="text-xs text-brand-700/50 text-center pt-2 tracking-wide">
          MedPag • Apenas você vê seus lançamentos • Sessão expira em 4h
        </p>
      </main>
    </div>
  );
}
