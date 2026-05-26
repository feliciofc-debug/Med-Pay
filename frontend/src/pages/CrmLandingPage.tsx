import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Calendar,
  CheckCircle2,
  Eye,
  EyeOff,
  FileText,
  Fingerprint,
  Hourglass,
  Lock,
  MessageCircle,
  Scale,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  TrendingUp,
  Wallet,
} from "lucide-react";

import { useAnestesistaSession } from "@/hooks/useAnestesistaSession";
import { getAnestesistaErrorMessage } from "@/lib/anestesistaApi";

export function CrmLandingPage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      <Hero />
      <Dores />
      <ComoFunciona />
      <PrintsMockup />
      <Diferenciais />
      <Confianca />
      <CTAFinal />
      <Footer />
    </div>
  );
}

// ============================================================
// Header
// ============================================================

function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-brand-100">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-brand-900 rounded-lg flex items-center justify-center text-accent-300 font-bold text-sm border border-accent-400/40 shadow-sm">
            M
          </div>
          <span className="font-bold text-brand-900 tracking-[0.15em] text-base">
            MEDPAG
          </span>
          <span className="hidden sm:inline-block ml-2 px-2 py-0.5 rounded-md bg-accent-100 text-accent-800 text-[10px] font-semibold uppercase tracking-wider">
            CRM
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-7 text-sm text-brand-800/80 font-medium">
          <a href="#como-funciona" className="hover:text-brand-900 transition">
            Como funciona
          </a>
          <a href="#diferenciais" className="hover:text-brand-900 transition">
            Diferenciais
          </a>
          <a href="#confianca" className="hover:text-brand-900 transition">
            Segurança
          </a>
        </nav>

        <a
          href="#entrar"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-500 text-brand-950 text-sm font-semibold hover:bg-accent-400 transition shadow-sm"
        >
          Entrar com CRM
          <ArrowRight size={14} />
        </a>
      </div>
    </header>
  );
}

// ============================================================
// Hero — caixinha de CRM como CTA principal
// ============================================================

function Hero() {
  const { loginPorCrm } = useAnestesistaSession();
  const navigate = useNavigate();

  const [crm, setCrm] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setLoading(true);
    try {
      await loginPorCrm(crm);
      navigate("/anestesista");
    } catch (err) {
      setErro(getAnestesistaErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      id="entrar"
      className="relative overflow-hidden bg-gradient-to-br from-brand-950 via-brand-900 to-brand-800 text-white"
    >
      {/* Blobs decorativos */}
      <div className="absolute inset-0 opacity-20 pointer-events-none">
        <div className="absolute top-0 -left-20 w-96 h-96 bg-brand-500 rounded-full mix-blend-screen filter blur-3xl animate-float" />
        <div
          className="absolute bottom-0 -right-20 w-96 h-96 bg-accent-500 rounded-full mix-blend-screen filter blur-3xl animate-float"
          style={{ animationDelay: "2s" }}
        />
      </div>
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400 to-transparent" />

      <div className="relative max-w-6xl mx-auto px-6 py-20 md:py-24 grid md:grid-cols-2 gap-12 items-center">
        {/* Coluna esquerda — pitch */}
        <div className="animate-fade-in-up">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-500/10 border border-accent-400/30 text-xs font-medium text-accent-200 mb-6">
            <Stethoscope size={14} />
            Acesso exclusivo para médicos
          </div>

          <h1 className="text-4xl md:text-5xl font-bold tracking-tight leading-[1.05] mb-5">
            Seu honorário,
            <br />
            <span className="bg-gradient-to-r from-accent-300 via-accent-200 to-accent-400 bg-clip-text text-transparent">
              sem planilha. Sem fofoca.
            </span>
          </h1>

          <p className="text-lg md:text-xl text-brand-100/90 leading-relaxed mb-8 max-w-lg">
            Lance os procedimentos que você fez. Receba o valor do dia, com
            comprovante. E pronto pra declarar no IR. Só seu CRM já abre.
          </p>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-brand-100/80">
            <div className="flex items-center gap-2">
              <Lock size={15} className="text-accent-400" />
              <span>Privado por padrão</span>
            </div>
            <div className="flex items-center gap-2">
              <MessageCircle size={15} className="text-accent-400" />
              <span>Aviso por WhatsApp</span>
            </div>
            <div className="flex items-center gap-2">
              <FileText size={15} className="text-accent-400" />
              <span>PDF pra contador</span>
            </div>
          </div>
        </div>

        {/* Coluna direita — caixinha de CRM */}
        <form
          onSubmit={handleSubmit}
          className="relative bg-white/95 backdrop-blur rounded-2xl p-7 shadow-2xl shadow-brand-950/40 border border-accent-300/40"
        >
          <div className="absolute -top-3 left-7 px-3 py-1 rounded-full bg-accent-400 text-brand-950 text-[10px] font-bold uppercase tracking-wider">
            Comece agora
          </div>

          <div className="flex items-center gap-3 mb-1 mt-1">
            <div className="w-11 h-11 rounded-xl bg-brand-100 text-brand-700 flex items-center justify-center">
              <Stethoscope size={20} />
            </div>
            <div>
              <p className="text-base font-semibold text-brand-900 leading-tight">
                Entrar com seu CRM
              </p>
              <p className="text-xs text-brand-700/70 leading-tight">
                Sem cadastro, sem senha. Direto pra sua tela.
              </p>
            </div>
          </div>

          <label className="block text-xs font-medium text-slate-600 mb-1.5 mt-5 uppercase tracking-wider">
            Seu CRM
          </label>
          <input
            type="text"
            value={crm}
            onChange={(e) => setCrm(e.target.value)}
            placeholder="Ex: 12345/SP"
            autoComplete="off"
            className="input uppercase tracking-wide text-lg font-mono"
          />

          <button
            type="submit"
            disabled={loading || !crm.trim()}
            className="btn-primary w-full mt-3 py-3 text-base"
          >
            {loading ? "Verificando..." : "Acessar minha área"}
            {!loading && <ArrowRight size={18} />}
          </button>

          {erro && (
            <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-2 py-2 mt-3">
              {erro}
            </p>
          )}

          <div className="mt-5 pt-4 border-t border-slate-100 text-[11px] text-slate-500 leading-relaxed flex items-start gap-2">
            <ShieldCheck size={13} className="text-success mt-0.5 shrink-0" />
            <span>
              Seu CRM precisa estar previamente cadastrado pela operação que
              gerencia seus pagamentos. Em caso de dúvida, fale com a sua
              coordenação.
            </span>
          </div>
        </form>
      </div>

      <svg
        className="block w-full h-12 text-white"
        viewBox="0 0 1440 80"
        preserveAspectRatio="none"
        fill="currentColor"
      >
        <path d="M0,32L80,37.3C160,43,320,53,480,53.3C640,53,800,43,960,37.3C1120,32,1280,32,1360,32L1440,32L1440,80L0,80Z" />
      </svg>
    </section>
  );
}

// ============================================================
// Dores — comparativo "antes vs depois"
// ============================================================

function Dores() {
  return (
    <section className="py-20 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <SectionHeader
          eyebrow="A dor que todo médico conhece"
          title="O que mudou de ontem pra hoje."
        />

        <div className="grid md:grid-cols-2 gap-6 mt-12">
          {/* Antes */}
          <div className="rounded-2xl border-2 border-red-100 bg-gradient-to-br from-red-50/50 to-white p-7">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-red-100 text-red-800 text-[11px] font-bold uppercase tracking-wider mb-4">
              <EyeOff size={12} />
              Antes
            </div>
            <ul className="space-y-3 text-sm text-slate-700 leading-relaxed">
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-1">✗</span>
                Planilha de Excel compartilhada com todos os colegas
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-1">✗</span>
                Você vê o pagamento dos outros. Os outros veem o seu.
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-1">✗</span>
                Espera o fim de semana pro coordenador "fechar à mão"
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-1">✗</span>
                Sem comprovante. IR é problema seu pra resolver.
              </li>
              <li className="flex items-start gap-2">
                <span className="text-red-500 mt-1">✗</span>
                Erros de digitação custam dinheiro do seu bolso
              </li>
            </ul>
          </div>

          {/* Agora */}
          <div className="rounded-2xl border-2 border-brand-200 bg-gradient-to-br from-brand-50 to-white p-7 shadow-lg">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-brand-200 text-brand-900 text-[11px] font-bold uppercase tracking-wider mb-4">
              <Sparkles size={12} />
              Agora com MedPag
            </div>
            <ul className="space-y-3 text-sm text-slate-700 leading-relaxed">
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="text-success mt-0.5 shrink-0" />
                Só você vê os seus lançamentos. Privacidade real.
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="text-success mt-0.5 shrink-0" />
                Lança o serviço do dia em 10 segundos pelo celular
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="text-success mt-0.5 shrink-0" />
                Recebe aviso por WhatsApp assim que o dia é fechado
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="text-success mt-0.5 shrink-0" />
                Comprovante PDF mensal pronto pra contador / Carnê-Leão
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 size={16} className="text-success mt-0.5 shrink-0" />
                Auditoria assinada — nenhum lançamento some
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Como funciona — 3 passos
// ============================================================

function ComoFunciona() {
  const passos = [
    {
      n: 1,
      icon: Stethoscope,
      title: "Entre com seu CRM",
      desc: "Sem cadastro, sem senha. Seu CRM é sua chave.",
    },
    {
      n: 2,
      icon: Calendar,
      title: "Lance data + código",
      desc: "Você digita a data e o código do procedimento. O sistema cuida do resto.",
    },
    {
      n: 3,
      icon: Wallet,
      title: "Receba e baixe o comprovante",
      desc: "Quando a operação fecha o dia, você é avisado por WhatsApp e vê seu valor.",
    },
  ];

  return (
    <section
      id="como-funciona"
      className="py-20 px-6 bg-gradient-to-b from-white to-brand-50/40"
    >
      <div className="max-w-6xl mx-auto">
        <SectionHeader
          eyebrow="Como funciona"
          title="Três passos. Nada mais."
        />

        <div className="grid md:grid-cols-3 gap-6 mt-12">
          {passos.map((p, idx) => {
            const Icon = p.icon;
            return (
              <div key={p.n} className="relative">
                {idx < passos.length - 1 && (
                  <div className="hidden md:block absolute top-12 left-full w-full h-px -translate-x-1/2">
                    <div className="h-px bg-gradient-to-r from-accent-300 to-transparent w-full mt-0" />
                  </div>
                )}
                <div className="relative bg-white rounded-2xl border border-brand-100 p-7 shadow-sm hover:shadow-md transition">
                  <div className="absolute -top-3 -left-3 w-9 h-9 rounded-full bg-accent-400 text-brand-950 font-bold flex items-center justify-center shadow-md">
                    {p.n}
                  </div>
                  <div className="w-12 h-12 rounded-xl bg-brand-100 text-brand-700 flex items-center justify-center mb-4">
                    <Icon size={22} />
                  </div>
                  <h3 className="text-lg font-semibold text-brand-900 mb-2">
                    {p.title}
                  </h3>
                  <p className="text-slate-600 leading-relaxed text-sm">
                    {p.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Prints / mockup do app
// ============================================================

function PrintsMockup() {
  return (
    <section className="py-20 px-6 bg-white">
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-12 items-center">
        <div>
          <SectionHeader
            eyebrow="Sua área privada"
            title="Veja só o que importa. O resto, ninguém precisa ver."
            alinhamento="left"
          />
          <p className="text-slate-600 leading-relaxed mt-5 max-w-md">
            Cada médico tem o próprio painel, com seus dias trabalhados, valor a
            receber e histórico completo. Nada de pagamentos dos colegas no seu
            campo de visão. Nada de planilha aberta.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-700">
            <li className="flex items-start gap-2">
              <Eye size={16} className="text-brand-700 mt-0.5 shrink-0" />
              Histórico filtrado só pelo seu CRM
            </li>
            <li className="flex items-start gap-2">
              <Hourglass size={16} className="text-brand-700 mt-0.5 shrink-0" />
              Status em tempo real: lançado, fechado, pago
            </li>
            <li className="flex items-start gap-2">
              <TrendingUp size={16} className="text-brand-700 mt-0.5 shrink-0" />
              Total do mês e do ano sempre à mão
            </li>
          </ul>
        </div>

        {/* Mockup do app */}
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-br from-brand-200/40 to-accent-200/40 rounded-3xl blur-2xl" />
          <div className="relative bg-white rounded-3xl border border-brand-100 shadow-2xl shadow-brand-900/10 p-6">
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
              <div className="w-10 h-10 bg-brand-900 rounded-xl flex items-center justify-center text-accent-300 font-bold border border-accent-400/40">
                M
              </div>
              <div className="flex-1">
                <p className="text-xs font-semibold text-brand-900">
                  Dr. Ricardo Andrade
                </p>
                <p className="text-[11px] text-brand-700/70">CRM 12345/SP</p>
              </div>
              <span className="text-[10px] font-semibold text-success bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                Privado
              </span>
            </div>

            <div className="rounded-xl bg-gradient-to-br from-brand-50 to-accent-50/30 border border-brand-100 p-4 mb-4">
              <p className="text-[11px] text-brand-700/70 uppercase tracking-wider">
                Total do mês
              </p>
              <p className="text-3xl font-bold text-brand-900">R$ 32.450,00</p>
              <p className="text-[11px] text-brand-700/70 mt-1">
                7 dias trabalhados
              </p>
            </div>

            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
              Histórico
            </p>
            <ul className="space-y-2 text-xs">
              {[
                { d: "01/05", v: "R$ 4.550,00", s: "Fechado", c: "success" },
                { d: "03/05", v: "R$ 4.333,33", s: "Fechado", c: "success" },
                { d: "07/05", v: "R$ 5.100,00", s: "Pago", c: "success" },
                { d: "10/05", v: "—", s: "Aguardando", c: "warning" },
              ].map((i) => (
                <li
                  key={i.d}
                  className="flex items-center justify-between py-2 px-3 rounded-lg bg-white border border-slate-100"
                >
                  <span className="font-mono text-slate-700">{i.d}</span>
                  <span
                    className={`text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full border ${
                      i.c === "success"
                        ? "text-success border-green-200 bg-green-50"
                        : "text-amber-800 border-amber-200 bg-amber-50"
                    }`}
                  >
                    {i.s}
                  </span>
                  <span className="font-semibold text-brand-900 text-right w-20">
                    {i.v}
                  </span>
                </li>
              ))}
            </ul>

            <button className="mt-4 w-full text-xs font-semibold text-brand-700 hover:text-brand-900 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg border border-brand-200 bg-brand-50/60">
              <FileText size={13} />
              Baixar comprovante (PDF)
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Diferenciais (4 cards)
// ============================================================

function Diferenciais() {
  const itens = [
    {
      icon: Lock,
      title: "Privacidade real",
      desc: "Seus lançamentos só você vê. Filtro feito no servidor — não tem como burlar.",
    },
    {
      icon: Scale,
      title: "Rateio justo",
      desc: "Quando o modelo é divisão por dia, todos veem o mesmo número. Acabou a desconfiança.",
    },
    {
      icon: MessageCircle,
      title: "Notificação WhatsApp",
      desc: "Você é avisado no momento que a operação fecha o dia. Sem precisar abrir o app.",
    },
    {
      icon: FileText,
      title: "Comprovante PDF",
      desc: "Demonstrativo mensal pronto pra Carnê-Leão / contador. 1 clique e baixa.",
    },
  ];

  return (
    <section
      id="diferenciais"
      className="py-20 px-6 bg-gradient-to-b from-brand-50/40 to-white"
    >
      <div className="max-w-6xl mx-auto">
        <SectionHeader
          eyebrow="Por que existe"
          title="As 4 coisas que ninguém te oferece — até agora."
        />

        <div className="grid md:grid-cols-4 gap-5 mt-12">
          {itens.map((it) => {
            const Icon = it.icon;
            return (
              <div
                key={it.title}
                className="group p-6 rounded-2xl border border-brand-100 bg-white hover:border-accent-300 hover:shadow-lg transition"
              >
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-100 to-accent-100 text-brand-800 flex items-center justify-center mb-4 group-hover:scale-110 transition">
                  <Icon size={20} />
                </div>
                <h3 className="text-base font-semibold text-brand-900 mb-1.5">
                  {it.title}
                </h3>
                <p className="text-sm text-slate-600 leading-relaxed">
                  {it.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Confiança / segurança
// ============================================================

function Confianca() {
  return (
    <section id="confianca" className="py-20 px-6 bg-brand-950 text-white relative">
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/60 to-transparent" />

      <div className="max-w-5xl mx-auto">
        <SectionHeader
          eyebrow="Como cuidamos do seu dado"
          title="Segurança que você não vê — mas existe."
          escuro
        />

        <div className="grid md:grid-cols-3 gap-6 mt-12">
          <CardSeg
            icon={Lock}
            title="Criptografia em repouso"
            desc="CPF, conta bancária e PIX armazenados criptografados. Mesmo um vazamento de banco não expõe seus dados."
          />
          <CardSeg
            icon={Fingerprint}
            title="Auditoria imutável"
            desc="Todo lançamento, todo cancelamento, todo fechamento gera log assinado. Nada é deletado de verdade."
          />
          <CardSeg
            icon={ShieldCheck}
            title="LGPD by design"
            desc="Privacidade e finalidade limitada são padrão. Você pode pedir seus dados ou exclusão a qualquer momento."
          />
        </div>
      </div>
    </section>
  );
}

function CardSeg({
  icon: Icon,
  title,
  desc,
}: {
  icon: React.ComponentType<{ size?: number }>;
  title: string;
  desc: string;
}) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-accent-400/20 p-6 backdrop-blur">
      <div className="w-11 h-11 rounded-xl bg-accent-500/10 border border-accent-400/30 text-accent-300 flex items-center justify-center mb-4">
        <Icon size={20} />
      </div>
      <h3 className="text-base font-semibold text-white mb-1.5">{title}</h3>
      <p className="text-sm text-brand-100/80 leading-relaxed">{desc}</p>
    </div>
  );
}

// ============================================================
// CTA final
// ============================================================

function CTAFinal() {
  return (
    <section className="py-20 px-6 bg-gradient-to-br from-accent-50 via-white to-brand-50">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-brand-900 mb-4 tracking-tight">
          Pronto pra ver seu próprio painel?
        </h2>
        <p className="text-lg text-slate-600 mb-8 leading-relaxed">
          Se seu CRM já foi cadastrado pela coordenação, é só digitar e
          entrar. Sem senha, sem cadastro, sem fricção.
        </p>
        <a
          href="#entrar"
          className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-brand-900 text-white font-semibold text-base hover:bg-brand-800 transition shadow-xl shadow-brand-900/20"
        >
          Entrar com meu CRM
          <ArrowRight size={18} />
        </a>
        <p className="text-xs text-slate-500 mt-5">
          Não tem cadastro?{" "}
          <a
            href="mailto:contato@medpag.com.br"
            className="text-brand-700 hover:text-brand-900 underline"
          >
            Fale com a gente
          </a>
          .
        </p>
      </div>
    </section>
  );
}

// ============================================================
// Footer
// ============================================================

function Footer() {
  return (
    <footer className="bg-brand-950 text-brand-100/70 py-10 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-brand-800 rounded-lg flex items-center justify-center text-accent-300 font-bold text-xs border border-accent-400/40">
            M
          </div>
          <span className="font-bold tracking-[0.15em] text-sm">MEDPAG</span>
          <span className="text-xs text-brand-100/40 ml-2">
            • Plataforma de pagamentos para a saúde
          </span>
        </div>
        <div className="text-xs text-brand-100/50">
          © {new Date().getFullYear()} MedPag • LGPD • Conforme FEBRABAN
        </div>
      </div>
    </footer>
  );
}

// ============================================================
// Helpers
// ============================================================

function SectionHeader({
  eyebrow,
  title,
  alinhamento = "center",
  escuro = false,
}: {
  eyebrow: string;
  title: string;
  alinhamento?: "center" | "left";
  escuro?: boolean;
}) {
  const align = alinhamento === "center" ? "text-center mx-auto" : "text-left";
  return (
    <div className={`${align} max-w-2xl`}>
      <div
        className={`inline-block text-[11px] font-bold uppercase tracking-[0.2em] mb-3 ${
          escuro ? "text-accent-300" : "text-accent-700"
        }`}
      >
        {eyebrow}
      </div>
      <h2
        className={`text-2xl md:text-3xl font-bold tracking-tight ${
          escuro ? "text-white" : "text-brand-900"
        }`}
      >
        {title}
      </h2>
    </div>
  );
}
