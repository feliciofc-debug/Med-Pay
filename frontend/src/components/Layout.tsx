import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeftRight,
  BarChart3,
  Briefcase,
  Building2,
  FileSpreadsheet,
  Home,
  type LucideIcon,
  LogOut,
  TrendingUp,
  Upload,
  UserCog,
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
}

// Visibilidade do menu por role.
//
// OPERADOR (Maria sobe planilha, corrige, NÃO aprova nem vê dados
// financeiros do BPO): só Novo Lote + Lotes.
//
// APROVADOR (Thiago e irmão diretores: aprovam, geram CNAB, inserem
// token na Unicred): dashboards operacionais + Novo Lote + Lotes.
// NÃO veem Contratos comerciais nem área Admin.
//
// ADMIN (você, Felício, dono do BPO): tudo, incluindo configuração
// comercial, equipe, empresa pagadora e relatórios estratégicos.
const NAV_ITEMS: NavItem[] = [
  {
    to: "/app",
    label: "Dashboard",
    icon: Home,
    exact: true,
    roles: ["ADMIN", "APROVADOR"],
  },
  {
    to: "/app/executivo",
    label: "Executivo",
    icon: BarChart3,
    roles: ["ADMIN"],
  },
  {
    to: "/app/contratos",
    label: "Contratos",
    icon: Briefcase,
    roles: ["ADMIN"],
  },
  {
    to: "/app/upload",
    label: "Novo Lote",
    icon: Upload,
    roles: ["ADMIN", "APROVADOR", "OPERADOR"],
  },
  {
    to: "/app/lotes",
    label: "Lotes",
    icon: FileSpreadsheet,
    roles: ["ADMIN", "APROVADOR", "OPERADOR"],
  },
];

const ADMIN_ITEMS = [
  { to: "/app/admin/empresa-pagadora", label: "Empresa Pagadora", icon: Building2 },
  { to: "/app/admin/usuarios", label: "Equipe", icon: UserCog },
  { to: "/app/admin/relatorio-erros", label: "Erros", icon: TrendingUp },
  { to: "/app/admin/devolucoes", label: "Devoluções", icon: ArrowLeftRight },
];

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const isAdmin = user?.role === "ADMIN";
  const role = user?.role;
  const navVisible = role
    ? NAV_ITEMS.filter((item) => item.roles.includes(role))
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

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navVisible.map((item) => {
            const Icon = item.icon;
            const active = item.exact
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors relative",
                  active
                    ? "bg-brand-800 text-white border-l-2 border-accent-400"
                    : "text-brand-100/70 hover:bg-brand-900 hover:text-white",
                )}
              >
                <Icon size={18} className={active ? "text-accent-300" : ""} />
                {item.label}
              </Link>
            );
          })}

          {isAdmin && (
            <div className="pt-4 mt-4 border-t border-brand-900/60">
              <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-wider text-accent-400/70">
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
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors relative",
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
          <div className="text-xs text-brand-100/70 mb-1 truncate">
            {user?.email}
          </div>
          <div className="text-[10px] text-accent-300 uppercase tracking-wider mb-3 font-semibold">
            {user?.role}
          </div>
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
