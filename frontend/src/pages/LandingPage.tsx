import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Database,
  Eye,
  FileSpreadsheet,
  FileWarning,
  Fingerprint,
  Heart,
  Layers,
  Lock,
  Mail,
  Repeat,
  Send,
  Shield,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  TrendingUp,
  Upload,
  Users,
  XCircle,
  Zap,
} from "lucide-react";

export function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      <Hero />
      <CenarioAtual />
      <Custos />
      <Visao />
      <ComoFunciona />
      <Comparativo />
      <Diferenciais />
      <Seguranca />
      <Mercado />
      <Roadmap />
      <PorQueAgora />
      <CTAFinal />
      <Footer />
    </div>
  );
}

// ============================================================
// Header (sticky)
// ============================================================

function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-brand-100">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-brand-900 rounded-lg flex items-center justify-center text-accent-300 font-bold text-sm border border-accent-400/40 shadow-sm">
            M
          </div>
          <span className="font-bold text-brand-900 tracking-[0.15em] text-base">
            MEDPAG
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8 text-sm text-brand-800/80 font-medium">
          <a href="#como-funciona" className="hover:text-brand-900 transition">
            Como funciona
          </a>
          <a href="#diferenciais" className="hover:text-brand-900 transition">
            Diferenciais
          </a>
          <a href="#seguranca" className="hover:text-brand-900 transition">
            Segurança
          </a>
          <a href="#roadmap" className="hover:text-brand-900 transition">
            Roadmap
          </a>
        </nav>

        <div className="flex items-center gap-3">
          <Link
            to="/crm"
            className="text-sm font-medium text-brand-800 hover:text-brand-900 transition hidden sm:inline-flex items-center gap-1.5"
          >
            <Stethoscope size={14} />
            Sou médico
          </Link>
          <Link
            to="/login"
            className="text-sm font-medium text-brand-800 hover:text-brand-900 transition hidden sm:block"
          >
            Entrar
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-500 text-brand-950 text-sm font-semibold hover:bg-accent-400 transition shadow-sm hover:shadow-md"
          >
            Acessar plataforma
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </header>
  );
}

// ============================================================
// Hero
// ============================================================

function Hero() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-brand-950 via-brand-900 to-brand-800 text-white">
      {/* Decorative blobs (verde musgo + dourado suaves) */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute top-0 -left-20 w-96 h-96 bg-brand-500 rounded-full mix-blend-screen filter blur-3xl animate-float" />
        <div
          className="absolute bottom-0 -right-20 w-96 h-96 bg-accent-500 rounded-full mix-blend-screen filter blur-3xl animate-float"
          style={{ animationDelay: "2s" }}
        />
      </div>

      {/* Linha dourada superior decorativa */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400 to-transparent" />

      <div className="relative max-w-7xl mx-auto px-6 py-24 md:py-32">
        <div className="max-w-3xl animate-fade-in-up">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-500/10 border border-accent-400/30 text-xs font-medium text-accent-200 mb-6">
            <Sparkles size={14} />
            Plataforma de pagamentos para o setor de saúde
          </div>

          <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.05] mb-6">
            Pagamentos em massa,
            <br />
            <span className="bg-gradient-to-r from-accent-300 via-accent-200 to-accent-400 bg-clip-text text-transparent">
              sem retrabalho.
            </span>
          </h1>

          <p className="text-xl md:text-2xl text-brand-100/90 leading-relaxed mb-10 max-w-2xl">
            A plataforma que transforma planilhas caóticas em pagamentos
            bancários processados — feita para quem distribui repasses na
            saúde.
          </p>

          <div className="flex flex-col sm:flex-row gap-4">
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-accent-400 text-brand-950 font-semibold hover:bg-accent-300 transition shadow-lg shadow-accent-900/40"
            >
              Acessar plataforma
              <ArrowRight size={18} />
            </Link>
            <a
              href="#como-funciona"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-white/5 border border-accent-400/30 text-white font-semibold hover:bg-white/10 hover:border-accent-400/60 transition backdrop-blur"
            >
              Ver como funciona
            </a>
          </div>

          <div className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm text-brand-100/70">
            <div className="flex items-center gap-2">
              <Shield size={16} className="text-accent-400" />
              <span>LGPD by design</span>
            </div>
            <div className="flex items-center gap-2">
              <Lock size={16} className="text-accent-400" />
              <span>Criptografia em repouso e trânsito</span>
            </div>
            <div className="flex items-center gap-2">
              <Fingerprint size={16} className="text-accent-400" />
              <span>Auditoria imutável</span>
            </div>
          </div>
        </div>
      </div>

      {/* Wave separator */}
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
// O cenário hoje
// ============================================================

function CenarioAtual() {
  const dores = [
    {
      icon: FileWarning,
      titulo: "Planilhas inconsistentes",
      descricao:
        "Cada cliente envia em um formato. CPFs sujos, dados bancários incompletos, dígitos faltando.",
    },
    {
      icon: FileSpreadsheet,
      titulo: "Digitação manual",
      descricao:
        "Operador transcreve pagamento por pagamento no internet banking. Horas de trabalho repetitivo todo mês.",
    },
    {
      icon: AlertTriangle,
      titulo: "Risco de erro caro",
      descricao:
        "Um CPF errado significa dinheiro indo pra conta errada. Responsabilidade financeira e jurídica.",
    },
  ];

  return (
    <section className="py-20 px-6 bg-white">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="O cenário hoje"
          title="Hospitais, clínicas e ONGs precisam pagar centenas de profissionais todo mês."
        />

        <div className="grid md:grid-cols-3 gap-6 mt-12">
          {dores.map((dor) => {
            const Icon = dor.icon;
            return (
              <div
                key={dor.titulo}
                className="group p-8 rounded-2xl border border-slate-200 hover:border-red-200 hover:shadow-lg transition bg-gradient-to-br from-white to-slate-50/50"
              >
                <div className="w-12 h-12 rounded-xl bg-red-50 text-red-600 flex items-center justify-center mb-4 group-hover:scale-110 transition">
                  <Icon size={22} />
                </div>
                <h3 className="text-lg font-semibold text-slate-900 mb-2">
                  {dor.titulo}
                </h3>
                <p className="text-slate-600 leading-relaxed">
                  {dor.descricao}
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
// Custos da operação
// ============================================================

function Custos() {
  const stats = [
    { numero: "3-6h", legenda: "de trabalho manual por lote", icon: Clock },
    {
      numero: "5-15%",
      legenda: "das linhas precisam de correção",
      icon: AlertTriangle,
    },
    { numero: "100%", legenda: "do risco fica com o operador", icon: Shield },
    { numero: "0", legenda: "rastreabilidade ou aprendizado", icon: Eye },
  ];

  return (
    <section className="py-20 px-6 bg-slate-50">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="O que essa operação custa hoje"
          title="Cada lote processado manualmente consome:"
        />

        <div className="grid md:grid-cols-4 gap-6 mt-12">
          {stats.map((s) => {
            const Icon = s.icon;
            return (
              <div
                key={s.legenda}
                className="bg-white rounded-2xl p-8 border border-slate-200 text-center"
              >
                <Icon className="w-6 h-6 text-slate-400 mx-auto mb-4" />
                <div className="text-5xl font-bold text-slate-900 mb-3 tracking-tight">
                  {s.numero}
                </div>
                <p className="text-sm text-slate-600 leading-snug">
                  {s.legenda}
                </p>
              </div>
            );
          })}
        </div>

        <p className="text-center mt-10 text-lg text-slate-700 font-medium">
          E o pior:{" "}
          <span className="text-red-600">
            o problema cresce conforme o negócio cresce.
          </span>
        </p>
      </div>
    </section>
  );
}

// ============================================================
// A visão (quote-style)
// ============================================================

function Visao() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-brand-800 via-brand-900 to-brand-950 text-white relative overflow-hidden">
      <div className="absolute inset-0 opacity-25">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent-500 rounded-full blur-3xl" />
      </div>

      {/* Linhas douradas decorativas */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/50 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/50 to-transparent" />

      <div className="relative max-w-4xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-500/10 border border-accent-400/30 text-xs font-medium text-accent-200 mb-8 tracking-wider uppercase">
          A visão
        </div>

        <h2 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight mb-8">
          E se o operador só precisasse clicar em
          <br />
          <span className="bg-gradient-to-r from-accent-300 via-accent-200 to-accent-400 bg-clip-text text-transparent italic font-serif">
            "aprovar"?
          </span>
        </h2>

        <p className="text-xl text-brand-100/85 leading-relaxed max-w-2xl mx-auto">
          O MedPag tira o trabalho mecânico do operador e devolve a ele o que
          importa: <strong className="text-accent-300">revisar, aprovar e crescer</strong>. A máquina
          cuida do resto.
        </p>
      </div>
    </section>
  );
}

// ============================================================
// Como funciona (4 passos)
// ============================================================

function ComoFunciona() {
  const passos = [
    {
      numero: "01",
      icon: Mail,
      titulo: "Recebe",
      descricao:
        "Hospital envia planilha por email, portal ou API. Sistema identifica o cliente automaticamente.",
    },
    {
      numero: "02",
      icon: ClipboardCheck,
      titulo: "Valida",
      descricao:
        "CPFs, contas, valores e duplicatas conferidos em segundos. Sugestões de correção quando possível.",
    },
    {
      numero: "03",
      icon: Eye,
      titulo: "Revisa",
      descricao:
        "Operador vê só o que precisa de atenção. Verde passa, amarelo sugere, vermelho bloqueia.",
    },
    {
      numero: "04",
      icon: Send,
      titulo: "Aprova",
      descricao:
        "Um clique gera o arquivo CNAB 240 da Unicred, pronto pra subir no internet banking. Auditoria registrada.",
    },
  ];

  return (
    <section id="como-funciona" className="py-24 px-6 bg-white">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Como funciona"
          title="Da planilha caótica ao pagamento aprovado."
        />

        <div className="relative grid md:grid-cols-4 gap-6 mt-16">
          {/* Linha conectora desktop */}
          <div className="hidden md:block absolute top-8 left-[12.5%] right-[12.5%] h-0.5 bg-gradient-to-r from-brand-200 via-brand-400 to-accent-400 -z-10" />

          {passos.map((passo) => {
            const Icon = passo.icon;
            return (
              <div key={passo.numero} className="relative">
                <div className="bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-lg transition group">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white flex items-center justify-center group-hover:scale-110 transition shadow-md shadow-brand-200">
                      <Icon size={20} />
                    </div>
                    <span className="text-3xl font-bold text-slate-200">
                      {passo.numero}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">
                    {passo.titulo}
                  </h3>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    {passo.descricao}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-12 text-center">
          <p className="inline-flex items-center gap-2 text-slate-700 font-medium text-lg">
            <Clock size={18} className="text-accent-600" />
            Tempo médio do processo:{" "}
            <span className="bg-gradient-to-r from-brand-600 to-accent-600 bg-clip-text text-transparent font-bold">
              de horas para minutos.
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Comparativo Antes/Depois
// ============================================================

function Comparativo() {
  const antes = [
    "Planilha chega em formato imprevisível",
    "Operador limpa dados na mão",
    "CPFs errados descobertos depois do pagamento",
    "Digitação 1 a 1 no internet banking",
    "Sem histórico nem trilha de auditoria",
    "Erro custa retrabalho, estorno e desgaste",
  ];

  const depois = [
    "Sistema reconhece o formato de cada cliente",
    "Validação automática em segundos",
    "Erros identificados antes do envio",
    "Arquivo CNAB único, pronto pro banco",
    "Auditoria completa de cada operação",
    "Sistema aprende e melhora a cada lote",
  ];

  return (
    <section className="py-24 px-6 bg-slate-50">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Comparativo"
          title="O dia a dia muda completamente."
        />

        <div className="grid md:grid-cols-2 gap-8 mt-12">
          {/* Antes */}
          <div className="bg-white rounded-2xl border border-red-100 overflow-hidden">
            <div className="bg-gradient-to-r from-red-50 to-red-50/50 px-6 py-4 border-b border-red-100">
              <h3 className="text-sm font-bold tracking-wider uppercase text-red-700">
                Antes
              </h3>
            </div>
            <ul className="p-6 space-y-3">
              {antes.map((item) => (
                <li key={item} className="flex gap-3 text-slate-600">
                  <XCircle
                    size={18}
                    className="text-red-400 flex-shrink-0 mt-0.5"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Depois */}
          <div className="bg-white rounded-2xl border border-brand-200 overflow-hidden shadow-lg shadow-brand-100/50 relative">
            {/* Faixa dourada superior */}
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-accent-400 via-accent-500 to-accent-400" />
            <div className="bg-gradient-to-r from-brand-50 to-accent-50 px-6 py-4 border-b border-brand-200 flex items-center justify-between">
              <h3 className="text-sm font-bold tracking-wider uppercase text-brand-800">
                Depois
              </h3>
              <span className="text-xs font-semibold text-accent-700 tracking-wide">
                MEDPAG
              </span>
            </div>
            <ul className="p-6 space-y-3">
              {depois.map((item) => (
                <li
                  key={item}
                  className="flex gap-3 text-slate-700 font-medium"
                >
                  <CheckCircle2
                    size={18}
                    className="text-success flex-shrink-0 mt-0.5"
                  />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Diferenciais
// ============================================================

function Diferenciais() {
  const itens = [
    {
      icon: Sparkles,
      titulo: "Memória inteligente",
      descricao:
        "A cada correção, o sistema aprende. No 3º mês, 90% das planilhas chegam quase prontas.",
      cor: "brand",
    },
    {
      icon: Lock,
      titulo: "Segurança bancária",
      descricao:
        "Dados sensíveis criptografados. LGPD por padrão. Auditoria de cada operação.",
      cor: "brand",
    },
    {
      icon: Layers,
      titulo: "Multi-cliente real",
      descricao:
        "Cada hospital com seu próprio portal, formato e fluxo. Dados isolados por contrato.",
      cor: "accent",
    },
    {
      icon: Repeat,
      titulo: "Conciliação automática",
      descricao:
        "Lê o retorno do banco e fecha o ciclo. Relatórios prontos por cliente.",
      cor: "accent",
    },
    {
      icon: TrendingUp,
      titulo: "Volume sem dor",
      descricao:
        "100 ou 10.000 pagamentos? Mesmo esforço. Operação escala sem aumentar equipe.",
      cor: "brand",
    },
    {
      icon: Upload,
      titulo: "Portal do cliente",
      descricao:
        "Hospital faz upload, vê status, baixa comprovantes. Menos chamadas, mais satisfação.",
      cor: "accent",
    },
  ];

  return (
    <section id="diferenciais" className="py-24 px-6 bg-white">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Diferenciais"
          title="Não é uma planilha melhor. É uma plataforma."
        />

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mt-12">
          {itens.map((item) => {
            const Icon = item.icon;
            const cores = {
              brand: "from-brand-50 to-brand-100/50 text-brand-600 border-brand-100",
              accent: "from-accent-50 to-accent-100/50 text-accent-600 border-accent-100",
            };
            return (
              <div
                key={item.titulo}
                className="group p-6 rounded-2xl border border-slate-200 hover:border-slate-300 hover:shadow-lg transition bg-white"
              >
                <div
                  className={`w-12 h-12 rounded-xl bg-gradient-to-br ${cores[item.cor as "brand" | "accent"]} flex items-center justify-center mb-4 group-hover:scale-110 transition`}
                >
                  <Icon size={22} />
                </div>
                <h3 className="text-lg font-semibold text-slate-900 mb-2">
                  {item.titulo}
                </h3>
                <p className="text-slate-600 leading-relaxed">
                  {item.descricao}
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
// Segurança
// ============================================================

function Seguranca() {
  const itens = [
    {
      icon: Lock,
      titulo: "Criptografia em repouso e em trânsito",
      descricao:
        "CPFs e dados bancários nunca trafegam ou ficam armazenados em texto puro.",
    },
    {
      icon: Database,
      titulo: "Trilha de auditoria imutável",
      descricao:
        "Quem aprovou, quando, qual hash do arquivo. Tudo registrado pra defesa jurídica.",
    },
    {
      icon: Shield,
      titulo: "LGPD by design",
      descricao:
        "Acesso por perfil, mascaramento automático, política de retenção configurável por cliente.",
    },
    {
      icon: ShieldCheck,
      titulo: "Aprovação em camadas",
      descricao:
        "Operador prepara, gerente aprova. Nenhum pagamento sai sem dupla checagem.",
    },
  ];

  return (
    <section
      id="seguranca"
      className="py-24 px-6 bg-gradient-to-br from-brand-900 via-brand-950 to-brand-900 text-white relative overflow-hidden"
    >
      {/* Padrão decorativo dourado */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/40 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/40 to-transparent" />

      <div className="relative max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Segurança e conformidade"
          title="Quando o assunto é dinheiro de terceiros, responsabilidade vem antes de velocidade."
          theme="dark"
        />

        <div className="grid md:grid-cols-2 gap-6 mt-12">
          {itens.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.titulo}
                className="flex gap-4 p-6 rounded-2xl bg-white/5 border border-accent-400/15 hover:border-accent-400/40 hover:bg-white/10 transition backdrop-blur"
              >
                <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-accent-500/15 text-accent-300 flex items-center justify-center border border-accent-400/30">
                  <Icon size={22} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold mb-1 text-white">{item.titulo}</h3>
                  <p className="text-brand-100/80 leading-relaxed">
                    {item.descricao}
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
// Mercado endereçável
// ============================================================

function Mercado() {
  const segmentos = [
    {
      icon: Heart,
      titulo: "Hospitais e clínicas",
      descricao:
        "Pagam dezenas a centenas de médicos plantonistas, anestesistas e prestadores por mês.",
    },
    {
      icon: Users,
      titulo: "Cooperativas médicas",
      descricao:
        "Distribuem repasses para centenas de cooperados com regras fiscais específicas.",
    },
    {
      icon: ShieldCheck,
      titulo: "ONGs e fundações",
      descricao:
        "Pagam profissionais de campo, bolsistas e prestadores em projetos sociais.",
    },
    {
      icon: Building2,
      titulo: "Empresas de gestão",
      descricao:
        "Como a do nosso primeiro cliente: terceirizam a operação de pagamentos para outras instituições.",
    },
  ];

  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Mercado endereçável"
          title="O Brasil tem milhares de operações com essa mesma dor."
        />

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mt-12">
          {segmentos.map((seg) => {
            const Icon = seg.icon;
            return (
              <div
                key={seg.titulo}
                className="p-6 rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50/50"
              >
                <Icon className="w-7 h-7 text-brand-600 mb-3" />
                <h3 className="font-semibold text-slate-900 mb-2">
                  {seg.titulo}
                </h3>
                <p className="text-sm text-slate-600 leading-relaxed">
                  {seg.descricao}
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
// Roadmap
// ============================================================

function Roadmap() {
  const fases = [
    {
      label: "FASE 1",
      titulo: "Fundação",
      status: "Em construção",
      itens: [
        "Importação inteligente de planilhas",
        "Validação automática de CPFs e dados bancários",
        "Geração CNAB 240 — Unicred",
        "Painel de revisão e aprovação",
        "Auditoria e segurança",
      ],
    },
    {
      label: "FASE 2",
      titulo: "Escala",
      status: "Planejado",
      itens: [
        "Portal de upload por cliente",
        "Cadastro inteligente de beneficiários",
        "Conciliação automática de retorno",
        "Relatórios por contrato",
        "Suporte multi-banco (Itaú, BB, Bradesco, Sicredi)",
      ],
    },
    {
      label: "FASE 3",
      titulo: "Plataforma",
      status: "Visão",
      itens: [
        "API pública pra integrações",
        "Pagamentos via PIX em lote",
        "Dashboard executivo",
        "Integração com ERPs hospitalares",
        "App mobile de aprovação",
      ],
    },
  ];

  return (
    <section id="roadmap" className="py-24 px-6 bg-slate-50">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Visão de produto"
          title="Começa enxuto. Cresce com o negócio."
        />

        <div className="grid md:grid-cols-3 gap-6 mt-12">
          {fases.map((fase, idx) => (
            <div
              key={fase.label}
              className={`relative p-6 rounded-2xl border ${
                idx === 0
                  ? "bg-gradient-to-br from-brand-50 to-white border-brand-200 shadow-lg shadow-brand-100/50"
                  : "bg-white border-slate-200"
              }`}
            >
              <div className="flex items-center justify-between mb-4">
                <span
                  className={`text-xs font-bold tracking-wider ${
                    idx === 0 ? "text-brand-600" : "text-slate-400"
                  }`}
                >
                  {fase.label}
                </span>
                {idx === 0 && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-accent-100 text-accent-700 font-medium">
                    {fase.status}
                  </span>
                )}
              </div>
              <h3 className="text-2xl font-bold text-slate-900 mb-4">
                {fase.titulo}
              </h3>
              <ul className="space-y-2">
                {fase.itens.map((item) => (
                  <li key={item} className="flex gap-2 text-sm text-slate-600">
                    <CheckCircle2
                      size={16}
                      className={`flex-shrink-0 mt-0.5 ${
                        idx === 0 ? "text-accent-600" : "text-slate-300"
                      }`}
                    />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Por que agora
// ============================================================

function PorQueAgora() {
  const itens = [
    {
      numero: "01",
      titulo: "Vocês já têm o cliente.",
      descricao:
        "A operação existe, o volume existe, a dor existe. O produto entra num terreno já fértil.",
    },
    {
      numero: "02",
      titulo: "O mercado está aberto.",
      descricao:
        "Nenhuma solução brasileira atende especificamente o nicho de distribuição de pagamentos de saúde.",
    },
    {
      numero: "03",
      titulo: "A tecnologia maturou.",
      descricao:
        "PIX em lote, Open Finance, IA pra correção de dados — tudo o que faltava pra fazer isso bem feito.",
    },
    {
      numero: "04",
      titulo: "Quem chega primeiro, fica.",
      descricao:
        "Cliente que adota plataforma de pagamento dificilmente troca. O custo de saída protege a receita.",
    },
  ];

  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-7xl mx-auto">
        <SectionHeader
          eyebrow="Por que agora?"
          title="O momento é único."
        />

        <div className="grid md:grid-cols-2 gap-6 mt-12">
          {itens.map((item) => (
            <div
              key={item.numero}
              className="flex gap-5 p-6 rounded-2xl border border-slate-200"
            >
              <span className="text-3xl font-bold bg-gradient-to-br from-brand-500 to-accent-500 bg-clip-text text-transparent flex-shrink-0">
                {item.numero}
              </span>
              <div>
                <h3 className="font-semibold text-slate-900 mb-1">
                  {item.titulo}
                </h3>
                <p className="text-slate-600 leading-relaxed text-sm">
                  {item.descricao}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ============================================================
// CTA Final
// ============================================================

function CTAFinal() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-brand-800 via-brand-900 to-brand-950 text-white relative overflow-hidden">
      <div className="absolute inset-0 opacity-25">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-accent-500 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-brand-500 rounded-full blur-3xl" />
      </div>

      {/* Faixas douradas decorativas */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/50 to-transparent" />

      <div className="relative max-w-4xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-500/10 border border-accent-400/30 text-xs font-medium text-accent-200 mb-6 tracking-wider uppercase">
          Próximos passos
        </div>
        <h2 className="text-4xl md:text-5xl font-bold tracking-tight mb-6">
          Vamos construir{" "}
          <span className="bg-gradient-to-r from-accent-300 via-accent-200 to-accent-400 bg-clip-text text-transparent">
            isso juntos.
          </span>
        </h2>
        <p className="text-xl text-brand-100/85 mb-12 max-w-2xl mx-auto">
          Uma plataforma sólida, um mercado pronto, e um time que entende o
          problema por dentro.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/login"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-accent-400 text-brand-950 font-semibold hover:bg-accent-300 transition shadow-xl shadow-accent-900/40"
          >
            <Zap size={18} />
            Acessar plataforma
          </Link>
          <a
            href="mailto:contato@medpag.com.br"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-white/5 border border-accent-400/30 text-white font-semibold hover:bg-white/10 hover:border-accent-400/60 transition backdrop-blur"
          >
            <Mail size={18} />
            Falar com a gente
          </a>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Footer
// ============================================================

function Footer() {
  return (
    <footer className="bg-brand-950 text-brand-100/60 py-12 px-6 relative">
      {/* Linha dourada superior */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-400/40 to-transparent" />

      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-brand-900 rounded-lg flex items-center justify-center text-accent-300 font-bold text-sm border border-accent-400/40">
              M
            </div>
            <div>
              <div className="text-white font-bold tracking-[0.15em]">
                MEDPAG
              </div>
              <div className="text-xs text-brand-100/50">
                Pagamentos sem retrabalho
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6 text-sm">
            <a href="#como-funciona" className="hover:text-accent-300 transition">
              Como funciona
            </a>
            <a href="#diferenciais" className="hover:text-accent-300 transition">
              Diferenciais
            </a>
            <a href="#seguranca" className="hover:text-accent-300 transition">
              Segurança
            </a>
            <Link to="/login" className="hover:text-accent-300 transition">
              Entrar
            </Link>
          </div>

          <div className="text-xs text-brand-100/40">
            © {new Date().getFullYear()} MedPag. Conforme LGPD.
          </div>
        </div>
      </div>
    </footer>
  );
}

// ============================================================
// Helper
// ============================================================

function SectionHeader({
  eyebrow,
  title,
  theme = "light",
}: {
  eyebrow: string;
  title: string;
  theme?: "light" | "dark";
}) {
  return (
    <div className="text-center max-w-3xl mx-auto">
      <div
        className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium tracking-wider uppercase mb-4 ${
          theme === "dark"
            ? "bg-white/10 text-accent-300 border border-white/20"
            : "bg-brand-50 text-brand-700 border border-brand-100"
        }`}
      >
        {eyebrow}
      </div>
      <h2
        className={`text-3xl md:text-4xl font-bold tracking-tight ${
          theme === "dark" ? "text-white" : "text-slate-900"
        }`}
      >
        {title}
      </h2>
    </div>
  );
}
