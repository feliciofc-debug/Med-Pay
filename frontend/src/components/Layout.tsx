import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { LogOut, FileSpreadsheet, Home, Upload, BarChart3, Briefcase } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/app", label: "Dashboard", icon: Home, exact: true },
  { to: "/app/executivo", label: "Executivo", icon: BarChart3 },
  { to: "/app/contratos", label: "Contratos", icon: Briefcase },
  { to: "/app/upload", label: "Novo Lote", icon: Upload },
  { to: "/app/lotes", label: "Lotes", icon: FileSpreadsheet },
];

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();

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

        <nav className="flex-1 p-4 space-y-1">
          {NAV_ITEMS.map((item) => {
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
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-8">{children}</div>
      </main>
    </div>
  );
}
