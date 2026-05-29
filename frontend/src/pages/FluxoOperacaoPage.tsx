import { Link } from "react-router-dom";
import {
  ArrowDown,
  BadgeCheck,
  Briefcase,
  Building2,
  CalendarCheck2,
  Camera,
  ClipboardList,
  Coins,
  CreditCard,
  FileText,
  HandshakeIcon,
  Layers3,
  type LucideIcon,
  Map,
  Stethoscope,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";

import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/types";

interface Etapa {
  numero: number;
  titulo: string;
  descricao: string;
  papeis: UserRole[];
  icone: LucideIcon;
  cor: "slate" | "brand" | "emerald" | "amber" | "rose" | "indigo";
  acoes: { rotulo: string; to: string; roles?: UserRole[] }[];
}

const ROLE_BADGE: Record<UserRole, { label: string; bg: string }> = {
  ADMIN: { label: "MedPag", bg: "bg-accent-100 text-accent-800" },
  APROVADOR: { label: "Aprovador", bg: "bg-brand-100 text-brand-800" },
  OPERADOR: { label: "Operador", bg: "bg-slate-100 text-slate-700" },
  COORDENADOR: { label: "Coordenador", bg: "bg-amber-100 text-amber-800" },
  GESTOR: { label: "Gestor", bg: "bg-indigo-100 text-indigo-800" },
  FINANCEIRO: { label: "Financeiro", bg: "bg-emerald-100 text-emerald-800" },
  MEDICO: { label: "Médico", bg: "bg-rose-100 text-rose-800" },
};

const COR_STYLE: Record<
  Etapa["cor"],
  { borda: string; bg: string; icone: string; numero: string }
> = {
  slate: {
    borda: "border-slate-300",
    bg: "bg-slate-50",
    icone: "bg-slate-100 text-slate-700",
    numero: "bg-slate-200 text-slate-700",
  },
  brand: {
    borda: "border-brand-300",
    bg: "bg-brand-50",
    icone: "bg-brand-100 text-brand-700",
    numero: "bg-brand-200 text-brand-800",
  },
  emerald: {
    borda: "border-emerald-300",
    bg: "bg-emerald-50",
    icone: "bg-emerald-100 text-emerald-700",
    numero: "bg-emerald-200 text-emerald-800",
  },
  amber: {
    borda: "border-amber-300",
    bg: "bg-amber-50",
    icone: "bg-amber-100 text-amber-700",
    numero: "bg-amber-200 text-amber-800",
  },
  rose: {
    borda: "border-rose-300",
    bg: "bg-rose-50",
    icone: "bg-rose-100 text-rose-700",
    numero: "bg-rose-200 text-rose-800",
  },
  indigo: {
    borda: "border-indigo-300",
    bg: "bg-indigo-50",
    icone: "bg-indigo-100 text-indigo-700",
    numero: "bg-indigo-200 text-indigo-800",
  },
};

const ETAPAS: Etapa[] = [
  {
    numero: 1,
    titulo: "Contrato com o hospital",
    descricao:
      "Você (MedPag) fecha contrato com o hospital: modelo de cobrança, plano, features ativas. Daqui pra frente o hospital tem acesso à plataforma.",
    papeis: ["ADMIN"],
    icone: HandshakeIcon,
    cor: "indigo",
    acoes: [
      { rotulo: "Contratos", to: "/app/contratos", roles: ["ADMIN", "GESTOR"] },
    ],
  },
  {
    numero: 2,
    titulo: "Cadastro de prestadores (médicos)",
    descricao:
      "O hospital sobe a planilha de médicos (modelo de 1 clique). A plataforma valida CPF, banco FEBRABAN e chave PIX. Médicos com erro aparecem em vermelho na prévia.",
    papeis: ["COORDENADOR", "GESTOR", "ADMIN"],
    icone: Users,
    cor: "amber",
    acoes: [
      { rotulo: "Prestadores", to: "/app/prestadores" },
      { rotulo: "Equipes", to: "/app/equipes" },
    ],
  },
  {
    numero: 3,
    titulo: "Lançamento dos serviços",
    descricao:
      "Coordenador sobe fichas de plantão (foto/PDF) → OCR + Groq Vision extraem médicos e valores. Ou o próprio médico lança um serviço pelo app dele. O sistema vai montando o banco de horas.",
    papeis: ["COORDENADOR", "OPERADOR", "MEDICO"],
    icone: Camera,
    cor: "brand",
    acoes: [
      { rotulo: "Fichas (OCR)", to: "/app/fichas" },
      { rotulo: "Novo Lote", to: "/app/upload", roles: ["ADMIN", "APROVADOR", "OPERADOR"] },
    ],
  },
  {
    numero: 4,
    titulo: "Extrato consolidado em tempo real",
    descricao:
      "Durante o mês, gestor e coordenador veem o extrato vivo: quantos médicos, quantos plantões, valor acumulado. É o 'banco de horas' do hospital crescendo.",
    papeis: ["GESTOR", "COORDENADOR", "APROVADOR"],
    icone: Layers3,
    cor: "slate",
    acoes: [
      { rotulo: "Extrato Consolidado", to: "/app/extrato-consolidado" },
    ],
  },
  {
    numero: 5,
    titulo: "Fechamento do mês",
    descricao:
      "Gestor clica em 'Trancar maio/2026'. A plataforma congela um snapshot (qtd fichas, médicos, valor total) e libera a geração do extrato + folha de pagamento.",
    papeis: ["GESTOR", "ADMIN"],
    icone: CalendarCheck2,
    cor: "indigo",
    acoes: [
      { rotulo: "Fechamento de período", to: "/app/fechamento" },
    ],
  },
  {
    numero: 6,
    titulo: "Folha + extrato pro contador",
    descricao:
      "A folha sai em PDF (assinável) e Excel (formato pro RH). Inclui CPF, valor bruto, IRRF opcional (Tabela RFB 2026) e líquido. Pronta pra anexar no eSocial.",
    papeis: ["FINANCEIRO", "GESTOR"],
    icone: FileText,
    cor: "emerald",
    acoes: [
      { rotulo: "Fechamento → Folha PDF", to: "/app/fechamento" },
    ],
  },
  {
    numero: 7,
    titulo: "Pagamento aos médicos",
    descricao:
      "Financeiro baixa CNAB 240 (Unicred / hospitais homologados) ou a planilha PIX (chave por médico). Sobe no Internet Banking. O banco processa.",
    papeis: ["FINANCEIRO", "APROVADOR"],
    icone: CreditCard,
    cor: "emerald",
    acoes: [{ rotulo: "Lotes", to: "/app/lotes" }],
  },
  {
    numero: 8,
    titulo: "Conciliação e visibilidade do médico",
    descricao:
      "Retorno do banco volta. Pagamentos viram PAGO ou NÃO_PAGO. Contas inválidas marcam o cadastro do médico como rejeitada. O médico vê tudo no app dele (extrato em tempo real).",
    papeis: ["MEDICO", "FINANCEIRO", "ADMIN"],
    icone: BadgeCheck,
    cor: "rose",
    acoes: [
      { rotulo: "App do médico", to: "/app/medico", roles: ["MEDICO", "ADMIN"] },
      { rotulo: "Devoluções", to: "/app/admin/devolucoes", roles: ["ADMIN"] },
    ],
  },
];

/**
 * Pagina "Fluxo da operacao".
 * Mapa visual da plataforma com as 8 etapas + papeis + links diretos.
 * Funciona como onboarding para qualquer usuario novo entender como
 * o sistema funciona de ponta a ponta.
 */
export function FluxoOperacaoPage() {
  const { user } = useAuth();
  const role = user?.role;

  return (
    <div className="space-y-8 pb-8">
      <header className="text-center max-w-3xl mx-auto pt-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 border border-brand-200 text-brand-700 text-xs font-semibold mb-3">
          <Map size={14} />
          MAPA DA OPERAÇÃO
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">
          Como funciona a Med-Pay, do contrato ao pagamento
        </h1>
        <p className="text-slate-500">
          Cada hospital passa por essas 8 etapas todo mês. Cada papel tem o seu
          momento — e a plataforma garante que ninguém fica esperando ninguém.
        </p>
      </header>

      {/* Resumo dos papéis */}
      <div className="card max-w-3xl mx-auto">
        <h2 className="text-sm font-semibold text-slate-700 mb-3 inline-flex items-center gap-2">
          <Users size={16} className="text-slate-500" />
          Quem é quem na operação
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          <PapelLinha
            icone={Building2}
            cor="bg-accent-100 text-accent-800"
            label="MedPag (Felício)"
            descricao="Visão de todos hospitais"
          />
          <PapelLinha
            icone={Briefcase}
            cor="bg-brand-100 text-brand-800"
            label="Aprovador"
            descricao="Aprova lotes, gera CNAB"
          />
          <PapelLinha
            icone={ClipboardList}
            cor="bg-amber-100 text-amber-800"
            label="Coordenador"
            descricao="Sobe fichas do hospital"
          />
          <PapelLinha
            icone={TrendingUp}
            cor="bg-indigo-100 text-indigo-800"
            label="Gestor"
            descricao="Aprova fechamento"
          />
          <PapelLinha
            icone={Coins}
            cor="bg-emerald-100 text-emerald-800"
            label="Financeiro"
            descricao="Baixa CNAB / folha"
          />
          <PapelLinha
            icone={Stethoscope}
            cor="bg-rose-100 text-rose-800"
            label="Médico"
            descricao="Vê seus plantões"
          />
        </div>
      </div>

      {/* Etapas */}
      <div className="max-w-3xl mx-auto space-y-3">
        {ETAPAS.map((etapa, idx) => (
          <div key={etapa.numero}>
            <EtapaCard etapa={etapa} roleAtual={role} />
            {idx < ETAPAS.length - 1 && (
              <div className="flex justify-center py-1">
                <ArrowDown size={20} className="text-slate-300" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* CTA final */}
      <div className="card max-w-3xl mx-auto bg-gradient-to-br from-brand-50 to-accent-50 border-brand-200">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-white text-brand-700 flex items-center justify-center shrink-0 shadow-sm">
            <Wallet size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 mb-1">
              Tudo conecta no fim
            </h3>
            <p className="text-sm text-slate-600">
              O fechamento gera o extrato → o extrato gera o lote → o lote
              vira CNAB ou folha → o banco processa → o médico vê na tela
              dele. Sem retrabalho, sem planilha esquecida, sem pagamento
              duplicado.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Sub-componentes
// ============================================================

function PapelLinha({
  icone: Icone,
  cor,
  label,
  descricao,
}: {
  icone: LucideIcon;
  cor: string;
  label: string;
  descricao: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <div
        className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 ${cor}`}
      >
        <Icone size={14} />
      </div>
      <div className="leading-tight">
        <div className="font-semibold text-slate-700">{label}</div>
        <div className="text-slate-500 text-[10px]">{descricao}</div>
      </div>
    </div>
  );
}

function EtapaCard({
  etapa,
  roleAtual,
}: {
  etapa: Etapa;
  roleAtual: UserRole | undefined;
}) {
  const Icone = etapa.icone;
  const cor = COR_STYLE[etapa.cor];
  const ehMinha = roleAtual && etapa.papeis.includes(roleAtual);

  return (
    <div
      className={`rounded-xl border-2 ${cor.borda} ${cor.bg} p-5 transition shadow-sm hover:shadow-md ${
        ehMinha ? "ring-2 ring-offset-2 ring-brand-300" : ""
      }`}
    >
      <div className="flex items-start gap-4">
        <div
          className={`w-12 h-12 rounded-xl ${cor.icone} flex items-center justify-center shrink-0`}
        >
          <Icone size={22} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`w-6 h-6 rounded-full ${cor.numero} text-xs font-bold flex items-center justify-center`}
            >
              {etapa.numero}
            </span>
            <h3 className="font-semibold text-slate-900">{etapa.titulo}</h3>
            {ehMinha && (
              <span className="text-[10px] uppercase tracking-wide bg-brand-700 text-white px-2 py-0.5 rounded-full font-semibold">
                Seu papel
              </span>
            )}
          </div>
          <p className="text-sm text-slate-600 mb-3">{etapa.descricao}</p>
          <div className="flex flex-wrap items-center gap-2">
            {etapa.papeis.map((papel) => (
              <span
                key={papel}
                className={`text-[10px] px-2 py-0.5 rounded ${ROLE_BADGE[papel].bg} font-medium`}
              >
                {ROLE_BADGE[papel].label}
              </span>
            ))}
            {etapa.acoes
              .filter(
                (a) =>
                  !a.roles || (roleAtual && a.roles.includes(roleAtual)),
              )
              .map((a) => (
                <Link
                  key={a.to}
                  to={a.to}
                  className="text-xs text-brand-700 hover:text-brand-900 underline ml-auto"
                >
                  {a.rotulo} →
                </Link>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
