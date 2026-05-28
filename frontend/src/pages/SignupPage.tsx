/**
 * Onboarding self-service.
 *
 * Wizard de 3 passos:
 *   1. Escolha do plano (busca de /api/planos/publicos)
 *   2. Dados da empresa + admin
 *   3. Confirmação + criação
 *
 * Após sucesso, salva tokens e redireciona pra /app.
 *
 * Aceita query param ?plano=inicial pra pular o passo 1 (uso a partir
 * da landing page com botão "Começar Grátis").
 */

import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  Package,
  Phone,
  Sparkles,
  UserPlus,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";
import type { Plano } from "@/types";

interface SignupResposta {
  cliente_id: string;
  nome_empresa: string;
  status_assinatura: string;
  trial_termina_em: string | null;
  user: { id: string; email: string; nome: string; role: string };
  access_token: string;
  refresh_token: string;
}

function formatBRL(centavos: number): string {
  if (centavos === 0) return "Sob demanda";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(centavos / 100);
}

export function SignupPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const planoQuery = searchParams.get("plano");

  const [passo, setPasso] = useState<1 | 2>(planoQuery ? 2 : 1);
  const [planoSelecionado, setPlanoSelecionado] = useState<Plano | null>(null);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [loadingPlanos, setLoadingPlanos] = useState(true);

  const [nomeEmpresa, setNomeEmpresa] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [emailContato, setEmailContato] = useState("");
  const [telefone, setTelefone] = useState("");
  const [adminNome, setAdminNome] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminSenha, setAdminSenha] = useState("");
  const [showSenha, setShowSenha] = useState(false);

  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [sucesso, setSucesso] = useState<SignupResposta | null>(null);

  useEffect(() => {
    void carregarPlanos();
  }, []);

  async function carregarPlanos() {
    try {
      const { data } = await api.get<Plano[]>("/api/planos/publicos");
      setPlanos(data);
      // Se veio ?plano=inicial e existe, pré-seleciona
      if (planoQuery) {
        const p = data.find((pl) => pl.slug === planoQuery);
        if (p) {
          setPlanoSelecionado(p);
          setPasso(2);
        }
      } else if (data.length === 1) {
        // Se só tem um plano público, pula direto
        setPlanoSelecionado(data[0]);
        setPasso(2);
      }
    } catch (err) {
      setErro(getErrorMessage(err));
    } finally {
      setLoadingPlanos(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!planoSelecionado) {
      setErro("Selecione um plano antes de continuar.");
      return;
    }
    setEnviando(true);
    try {
      const { data } = await api.post<SignupResposta>("/api/signup", {
        plano_slug: planoSelecionado.slug,
        nome_empresa: nomeEmpresa,
        cnpj: cnpj || null,
        email_contato: emailContato || null,
        telefone: telefone || null,
        admin_nome: adminNome,
        admin_email: adminEmail,
        admin_senha: adminSenha,
      });
      localStorage.setItem("medpag_access_token", data.access_token);
      localStorage.setItem("medpag_refresh_token", data.refresh_token);
      setSucesso(data);
    } catch (err) {
      setErro(getErrorMessage(err));
    } finally {
      setEnviando(false);
    }
  }

  if (sucesso) {
    return <TelaSucesso resp={sucesso} onContinuar={() => navigate("/app")} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-accent-50/30 py-10 px-4">
      <div className="max-w-3xl mx-auto">
        <header className="mb-8 flex items-center justify-between">
          <Link
            to="/"
            className="text-sm text-slate-500 hover:text-slate-800 flex items-center gap-1"
          >
            <ArrowLeft size={14} /> Voltar
          </Link>
          <div className="flex items-center gap-2 text-slate-900">
            <div className="w-9 h-9 bg-brand-900 rounded-lg flex items-center justify-center text-accent-300 font-bold text-sm border border-accent-400/40">
              M
            </div>
            <span className="font-bold tracking-[0.15em]">MEDPAG</span>
          </div>
          <Link
            to="/login"
            className="text-sm text-brand-700 hover:text-brand-900"
          >
            Já tenho conta
          </Link>
        </header>

        {/* Stepper */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <StepBadge ativo={passo === 1} concluido={passo > 1} numero={1} label="Plano" />
          <span className="w-12 h-px bg-slate-300" />
          <StepBadge ativo={passo === 2} concluido={false} numero={2} label="Dados" />
        </div>

        {erro && (
          <div className="mb-5 bg-red-50 border border-red-200 text-red-900 rounded-md p-3 text-sm">
            {erro}
          </div>
        )}

        {/* Passo 1 — Plano */}
        {passo === 1 && (
          <section className="space-y-3">
            <h1 className="text-2xl font-semibold text-slate-900 text-center">
              Comece grátis. Sem cartão.
            </h1>
            <p className="text-sm text-slate-500 text-center mb-6">
              Selecione o plano que combina com sua operação. Você pode testar
              por {planos[0]?.trial_dias ?? 30} dias antes de pagar nada.
            </p>

            {loadingPlanos ? (
              <p className="text-center text-slate-500">
                <Loader2 className="inline animate-spin mr-2" size={16} />
                Carregando planos...
              </p>
            ) : planos.length === 0 ? (
              <div className="card p-6 text-center text-slate-500">
                Nenhum plano disponível para signup self-service no momento.
                <Link
                  to="/"
                  className="block mt-2 text-brand-700 hover:underline"
                >
                  Falar com um sócio MedPag
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {planos.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      setPlanoSelecionado(p);
                      setPasso(2);
                    }}
                    className={`text-left card p-5 hover:border-brand-400 hover:shadow-md transition-all ${
                      planoSelecionado?.id === p.id
                        ? "border-brand-500 ring-2 ring-brand-200"
                        : ""
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-900">{p.nome}</h3>
                      {p.trial_dias > 0 && (
                        <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full flex items-center gap-1">
                          <Sparkles size={11} />
                          {p.trial_dias}d grátis
                        </span>
                      )}
                    </div>
                    <p className="text-2xl font-bold text-slate-900 mt-2">
                      {formatBRL(p.preco_mensal_centavos)}
                      {p.preco_mensal_centavos > 0 && (
                        <span className="text-sm font-normal text-slate-500">
                          {" "}/ mês
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500 leading-snug mt-2">
                      {p.descricao}
                    </p>
                    <p className="mt-3 text-sm text-brand-700 font-medium flex items-center gap-1">
                      Escolher <ArrowRight size={14} />
                    </p>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Passo 2 — Dados */}
        {passo === 2 && planoSelecionado && (
          <form onSubmit={handleSubmit} className="card p-6 space-y-5">
            <header className="border-b border-slate-200 pb-4">
              <h2 className="text-lg font-semibold text-slate-900">
                Conta MedPag
              </h2>
              <p className="text-sm text-slate-500 mt-1 flex items-center gap-2">
                <Package size={14} />
                Plano <strong>{planoSelecionado.nome}</strong>
                {planoSelecionado.trial_dias > 0 && (
                  <span className="ml-1 text-blue-700">
                    · {planoSelecionado.trial_dias} dias de teste grátis
                  </span>
                )}
                <button
                  type="button"
                  className="ml-auto text-xs text-slate-500 hover:text-slate-800 underline"
                  onClick={() => setPasso(1)}
                >
                  trocar
                </button>
              </p>
            </header>

            {/* Empresa */}
            <fieldset className="space-y-3">
              <legend className="text-xs uppercase tracking-wider font-semibold text-slate-500 flex items-center gap-2">
                <Building2 size={12} /> Empresa
              </legend>

              <Campo
                label="Nome / Razão Social"
                valor={nomeEmpresa}
                onChange={setNomeEmpresa}
                obrigatorio
                placeholder="Ex: Hospital São Lucas"
              />
              <div className="grid grid-cols-2 gap-3">
                <Campo
                  label="CNPJ (opcional)"
                  valor={cnpj}
                  onChange={setCnpj}
                  placeholder="00.000.000/0000-00"
                />
                <Campo
                  label="Telefone"
                  valor={telefone}
                  onChange={setTelefone}
                  placeholder="(21) 99999-9999"
                  icone={<Phone size={14} />}
                />
              </div>
              <Campo
                label="E-mail de contato (opcional)"
                valor={emailContato}
                onChange={setEmailContato}
                tipo="email"
                placeholder="contato@suaempresa.com.br"
                icone={<Mail size={14} />}
              />
            </fieldset>

            {/* Admin */}
            <fieldset className="space-y-3 pt-3 border-t border-slate-200">
              <legend className="text-xs uppercase tracking-wider font-semibold text-slate-500 flex items-center gap-2">
                <UserPlus size={12} /> Seu acesso (admin da conta)
              </legend>

              <Campo
                label="Seu nome"
                valor={adminNome}
                onChange={setAdminNome}
                obrigatorio
              />
              <Campo
                label="Seu e-mail"
                valor={adminEmail}
                onChange={setAdminEmail}
                obrigatorio
                tipo="email"
                icone={<Mail size={14} />}
              />
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Senha (mínimo 8 caracteres)
                </label>
                <div className="relative">
                  <Lock
                    size={14}
                    className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    type={showSenha ? "text" : "password"}
                    value={adminSenha}
                    onChange={(e) => setAdminSenha(e.target.value)}
                    required
                    minLength={8}
                    className="input w-full pl-7 pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSenha(!showSenha)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                  >
                    {showSenha ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </fieldset>

            <footer className="pt-4 border-t border-slate-200 flex flex-col gap-3">
              <button
                type="submit"
                disabled={enviando}
                className="btn-primary w-full justify-center"
              >
                {enviando ? (
                  <>
                    <Loader2 className="animate-spin mr-2" size={16} />
                    Criando conta...
                  </>
                ) : (
                  <>
                    Criar conta e começar
                    <ArrowRight size={16} className="ml-2" />
                  </>
                )}
              </button>
              <p className="text-[11px] text-slate-500 text-center">
                Ao criar conta você concorda com os termos de uso do MedPag.
                Sem cobrança durante o trial.
              </p>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Subcomponentes
// ============================================================

function StepBadge({
  ativo,
  concluido,
  numero,
  label,
}: {
  ativo: boolean;
  concluido: boolean;
  numero: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
          concluido
            ? "bg-emerald-500 text-white"
            : ativo
              ? "bg-brand-600 text-white"
              : "bg-slate-200 text-slate-500"
        }`}
      >
        {concluido ? <CheckCircle2 size={14} /> : numero}
      </div>
      <span
        className={`text-sm font-medium ${
          ativo ? "text-slate-900" : "text-slate-500"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

function Campo({
  label,
  valor,
  onChange,
  obrigatorio,
  tipo = "text",
  placeholder,
  icone,
}: {
  label: string;
  valor: string;
  onChange: (s: string) => void;
  obrigatorio?: boolean;
  tipo?: string;
  placeholder?: string;
  icone?: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">
        {label}
        {obrigatorio && <span className="text-red-500 ml-1">*</span>}
      </label>
      <div className="relative">
        {icone && (
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400">
            {icone}
          </span>
        )}
        <input
          type={tipo}
          value={valor}
          onChange={(e) => onChange(e.target.value)}
          required={obrigatorio}
          placeholder={placeholder}
          className={`input w-full ${icone ? "pl-7" : ""}`}
        />
      </div>
    </div>
  );
}

function TelaSucesso({
  resp,
  onContinuar,
}: {
  resp: SignupResposta;
  onContinuar: () => void;
}) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-50 via-white to-accent-50/30 flex items-center justify-center px-4">
      <div className="max-w-md w-full card p-8 text-center">
        <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle2 className="text-emerald-600" size={32} />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Conta criada!</h1>
        <p className="text-slate-600 mt-2">
          Bem-vindo ao MedPag, <strong>{resp.user.nome}</strong>.
        </p>

        <div className="bg-slate-50 border border-slate-200 rounded-md p-4 mt-5 text-left text-sm">
          <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">
            Empresa
          </p>
          <p className="font-semibold">{resp.nome_empresa}</p>
          <p className="text-xs text-slate-500 mt-3 uppercase tracking-wider mb-1">
            Status
          </p>
          <p>
            {resp.status_assinatura === "TRIAL" ? (
              <span className="text-blue-700">
                Em trial até{" "}
                {resp.trial_termina_em
                  ? new Date(resp.trial_termina_em).toLocaleDateString("pt-BR")
                  : "—"}
              </span>
            ) : (
              <span className="text-emerald-700">Assinatura ativa</span>
            )}
          </p>
        </div>

        <button
          type="button"
          onClick={onContinuar}
          className="btn-primary w-full mt-6 justify-center"
        >
          Entrar no MedPag
          <ArrowRight size={16} className="ml-2" />
        </button>
      </div>
    </div>
  );
}
