import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeftRight,
  Activity,
  BarChart3,
  Bot,
  Briefcase,
  Building2,
  Camera,
  CalendarCheck2,
  ClipboardList,
  Cog,
  FileSpreadsheet,
  HandCoins,
  HeartPulse,
  History,
  Home,
  Layers,
  Layers3,
  type LucideIcon,
  LogOut,
  Map,
  Stethoscope,
  TrendingUp,
  Upload,
  UserCog,
  Users,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  roles: UserRole[];
  // Capacidade (feature flag) exigida pra exibir o item. Quando definida,
  // o item só aparece se o tenant tiver a feature ligada. Usuário MedPag
  // interno (sem cliente) enxerga tudo. Ver mapa mental — menu derivado
  // das capacidades, não de `if tipo == hospital`.
  feature?: string;
}

interface NavSection {
  id: string;
  label: string;          // visivel acima do grupo
  items: NavItem[];
  // Esconde a secao inteira se o usuario nao tiver acesso a nenhum item
}

// ============================================================
// Navegação organizada por SEÇÕES e por PAPEL.
// ============================================================
//
// Cada usuário vê apenas as seções e itens compatíveis com seu papel.
// Seções vazias somem automaticamente.
//
// Papeis e o que cada um enxerga (alto nível):
//
// MEDICO (prestador)        -> só "Meu app" (plantões/extrato dele)
// COORDENADOR (hospital)    -> só "Operação" (subir fichas)
// FINANCEIRO (hospital)     -> "Financeiro" (CNAB / folha / extrato)
// GESTOR (hospital)         -> "Operação" + "Financeiro" + "Hospital"
// OPERADOR (MedPag)         -> "Operação"
// APROVADOR (MedPag)        -> "Operação" + "Financeiro" + "Dashboards"
// ADMIN (MedPag, Felício)   -> TUDO (todos os menus + "Administração")
// ============================================================

const SECOES: NavSection[] = [
  // ---------- Meu app (médico) ----------
  {
    id: "meu_app",
    label: "Meu app",
    items: [
      {
        to: "/app/medico",
        label: "Meus plantões",
        icon: Stethoscope,
        exact: true,
        roles: ["MEDICO"],
      },
      {
        to: "/app/medico/extrato",
        label: "Meu extrato",
        icon: Wallet,
        roles: ["MEDICO"],
      },
    ],
  },

  // ---------- Dashboards / visão geral ----------
  {
    id: "geral",
    label: "Visão geral",
    items: [
      {
        to: "/app/coordenador",
        label: "Meu Painel",
        icon: ClipboardList,
        exact: true,
        roles: ["COORDENADOR"],
      },
      {
        to: "/app",
        label: "Dashboard",
        icon: Home,
        exact: true,
        roles: ["ADMIN", "APROVADOR", "GESTOR"],
      },
      {
        to: "/app/executivo",
        label: "Executivo",
        icon: BarChart3,
        roles: ["ADMIN", "GESTOR"],
        feature: "analise.lucro",
      },
      {
        to: "/app/fluxo",
        label: "Fluxo da operação",
        icon: Map,
        roles: [
          "ADMIN",
          "APROVADOR",
          "OPERADOR",
          "COORDENADOR",
          "GESTOR",
          "FINANCEIRO",
          "MEDICO",
        ],
      },
    ],
  },

  // ---------- Operação ----------
  {
    id: "operacao",
    label: "Operação",
    items: [
      {
        to: "/app/fichas",
        label: "Fichas (OCR)",
        icon: Camera,
        roles: ["ADMIN", "APROVADOR", "OPERADOR", "COORDENADOR", "GESTOR"],
      },
      {
        to: "/app/upload",
        label: "Novo Lote",
        icon: Upload,
        roles: ["ADMIN", "APROVADOR", "OPERADOR"],
      },
      {
        to: "/app/extrato-consolidado",
        label: "Extrato Consolidado",
        icon: Layers3,
        roles: ["ADMIN", "APROVADOR", "GESTOR"],
      },
      {
        to: "/app/fechamento",
        label: "Fechamento de período",
        icon: CalendarCheck2,
        roles: ["ADMIN", "APROVADOR", "GESTOR", "FINANCEIRO"],
      },
      {
        to: "/app/prestadores",
        label: "Prestadores",
        icon: Users,
        roles: ["ADMIN", "APROVADOR", "OPERADOR", "GESTOR"],
      },
      {
        to: "/app/equipes",
        label: "Equipes",
        icon: HeartPulse,
        roles: ["ADMIN", "APROVADOR", "OPERADOR", "GESTOR"],
        feature: "modulo.equipe_flex",
      },
    ],
  },

  // ---------- Financeiro ----------
  {
    id: "financeiro",
    label: "Financeiro",
    items: [
      {
        // Lançar pagamento (criar lote) pro tenant que executa os próprios
        // pagamentos — empresa de repasse / MedPag-SCP. O BPO interno usa
        // "Novo Lote" na seção Operação. Aqui o GESTOR do repasse lança,
        // aprova e gera CNAB (ciclo completo), gated por pagamento.execucao.
        to: "/app/upload",
        label: "Lançar pagamento",
        icon: Upload,
        roles: ["GESTOR"],
        feature: "pagamento.execucao",
      },
      {
        to: "/app/lotes",
        label: "Lotes",
        icon: FileSpreadsheet,
        roles: [
          "ADMIN",
          "APROVADOR",
          "OPERADOR",
          "GESTOR",
          "FINANCEIRO",
        ],
      },
      {
        to: "/app/contratos",
        label: "Contratos",
        icon: Briefcase,
        roles: ["ADMIN", "GESTOR"],
        feature: "modulo.contratos_hospital",
      },
      {
        to: "/app/scp",
        label: "SCP / Repasse",
        icon: HandCoins,
        roles: ["ADMIN", "GESTOR"],
        feature: "scp.apuracao",
      },
      {
        // Empresa pagadora: a conta (CNAB) de onde saem os pagamentos. Mesmo
        // módulo que o MedPag interno usa em Administração — aqui exposto pro
        // GESTOR que executa o próprio pagamento (repasse / SCP). É o coração
        // da operação de pagamento.
        to: "/app/admin/empresa-pagadora",
        label: "Empresa pagadora",
        icon: Building2,
        roles: ["GESTOR"],
        feature: "pagamento.execucao",
      },
    ],
  },

  // ---------- Compliance ----------
  {
    id: "compliance",
    label: "Compliance",
    items: [
      {
        to: "/app/vital",
        label: "MedPag Vital",
        icon: Activity,
        roles: ["ADMIN", "APROVADOR", "OPERADOR", "GESTOR"],
        feature: "modulo.sentinela_vital",
      },
    ],
  },
];

// Itens "Administração" — só ADMIN MedPag vê.
const ADMIN_ITEMS = [
  { to: "/app/super-admin", label: "Super Admin", icon: TrendingUp },
  { to: "/app/admin/empresa-pagadora", label: "Empresa Pagadora", icon: Building2 },
  { to: "/app/admin/planos", label: "Planos & Features", icon: Layers },
  { to: "/app/admin/operacao", label: "Configurar Operação", icon: Cog },
  { to: "/app/admin/usuarios", label: "Equipe", icon: UserCog },
  { to: "/app/admin/whatsapp", label: "Jarvis (WhatsApp)", icon: Bot },
  { to: "/app/admin/auditoria", label: "Auditoria", icon: History },
  { to: "/app/admin/relatorio-erros", label: "Erros", icon: TrendingUp },
  { to: "/app/admin/devolucoes", label: "Devoluções", icon: ArrowLeftRight },
];

// Labels amigáveis pros papéis (mostrados no rodapé do menu).
const ROLE_LABEL: Record<UserRole, string> = {
  ADMIN: "MedPag · Admin",
  APROVADOR: "MedPag · Aprovador",
  OPERADOR: "MedPag · Operador",
  COORDENADOR: "Hospital · Coordenador",
  GESTOR: "Hospital · Gestor",
  FINANCEIRO: "Hospital · Financeiro",
  MEDICO: "Prestador (Médico)",
};

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const isAdmin = user?.role === "ADMIN";
  const role = user?.role;
  const nomeHospital = user?.cliente?.nome ?? null;

  // Capacidades resolvidas do tenant (Eixo 2). Usuário MedPag interno
  // (sem cliente) não tem features no payload e enxerga tudo.
  const featuresTenant = user?.cliente?.features ?? null;
  const ehInterno = !user?.cliente;
  const temFeature = (chave?: string): boolean => {
    if (!chave) return true; // item sem gate de feature
    if (ehInterno) return true; // MedPag interno vê tudo
    return featuresTenant?.[chave] === true;
  };

  // Filtra seções/itens visíveis para o papel atual E pelas capacidades.
  const secoesVisiveis = role
    ? SECOES.map((s) => ({
        ...s,
        items: s.items.filter(
          (i) => i.roles.includes(role) && temFeature(i.feature),
        ),
      })).filter((s) => s.items.length > 0)
    : [];

  return (
    <div className="min-h-screen flex bg-brand-50/30">
      {/* Sidebar */}
      <aside className="w-64 bg-brand-950 text-white flex flex-col relative">
        {/* Borda dourada vertical */}
        <div className="absolute top-0 bottom-0 right-0 w-px bg-gradient-to-b from-transparent via-accent-400/30 to-transparent" />

        <Link
          to="/"
          className="p-6 border-b border-brand-900 hover:bg-brand-900 transition relative"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-brand-900 rounded-lg flex items-center justify-center text-accent-300 font-bold text-sm border border-accent-400/40 shadow-sm">
              M
            </div>
            <h1 className="text-xl font-bold tracking-[0.15em]">MEDPAG</h1>
          </div>
          <p className="text-xs text-brand-100/50 mt-1.5 italic">
            Pagamentos sem retrabalho
          </p>
        </Link>

        <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
          {secoesVisiveis.map((secao) => (
            <div key={secao.id} className="space-y-1">
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-accent-400/70">
                {secao.label}
              </p>
              {secao.items.map((item) => {
                const Icon = item.icon;
                const active = item.exact
                  ? location.pathname === item.to
                  : location.pathname.startsWith(item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors relative",
                      active
                        ? "bg-brand-800 text-white border-l-2 border-accent-400"
                        : "text-brand-100/70 hover:bg-brand-900 hover:text-white",
                    )}
                  >
                    <Icon
                      size={18}
                      className={active ? "text-accent-300" : ""}
                    />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}

          {isAdmin && (
            <div className="pt-3 mt-2 border-t border-brand-900/60 space-y-1">
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-wider text-accent-400/70">
                Administração
              </p>
              {ADMIN_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = location.pathname.startsWith(item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors relative",
                      active
                        ? "bg-brand-800 text-white border-l-2 border-accent-400"
                        : "text-brand-100/70 hover:bg-brand-900 hover:text-white",
                    )}
                  >
                    <Icon
                      size={18}
                      className={active ? "text-accent-300" : ""}
                    />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          )}
        </nav>

        <div className="p-4 border-t border-brand-900">
          <div className="text-xs text-brand-100/80 mb-0.5 truncate font-medium">
            {user?.nome ?? user?.email}
          </div>
          <div className="text-[11px] text-brand-100/60 mb-1 truncate">
            {user?.email}
          </div>
          <div className="text-[10px] text-accent-300 uppercase tracking-wider mb-1 font-semibold">
            {role ? ROLE_LABEL[role] : ""}
          </div>
          {nomeHospital && (
            <div
              className="text-[10px] text-brand-100/60 mb-3 truncate"
              title={nomeHospital}
            >
              📍 {nomeHospital}
            </div>
          )}
          {!nomeHospital && role && (
            <div className="text-[10px] text-brand-100/40 mb-3 italic">
              {role === "MEDICO" ? "Prestador" : "Acesso global"}
            </div>
          )}
          <button
            type="button"
            onClick={() => void logout()}
            className="w-full flex items-center gap-2 text-sm text-brand-100/70 hover:text-accent-300 transition"
          >
            <LogOut size={16} />
            Sair
          </button>
          <div
            className="mt-3 pt-3 border-t border-brand-900/60 text-[10px] text-brand-100/40 truncate"
            title={`API: ${api.defaults.baseURL ?? "(vazio)"}`}
          >
            API: {(api.defaults.baseURL ?? "").replace(/^https?:\/\//, "") || "(vazio)"}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto flex flex-col">
        <div className="max-w-7xl mx-auto p-8 w-full flex-1">{children}</div>
        <footer className="border-t border-slate-200 bg-white/60 backdrop-blur py-3 px-8">
          <p className="text-center text-[11px] text-slate-500">
            Plataforma proprietária e desenvolvida por{" "}
            <a
              href="https://atombrasildigital.com"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-brand-800 hover:text-accent-600 transition-colors"
            >
              ATOM BRASIL DIGITAL LTDA
            </a>
            <span className="mx-2 text-slate-300">•</span>
            CNPJ: 22.003.550/0001-05
          </p>
        </footer>
      </main>
    </div>
  );
}
