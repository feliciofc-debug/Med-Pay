import { Link } from "react-router-dom";
import { CalendarClock, Wallet, Construction, Stethoscope } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

/**
 * Pagina inicial do app do medico (prestador).
 *
 * MVP placeholder enquanto a Leva 3.1 nao esta completa. Mostra:
 * - Nome do prestador
 * - Hospital vinculado
 * - Cards visuais com "Em breve" para meus plantoes / extrato / pagamentos
 *
 * Quando a Leva 3.1 for entregue, esta pagina vira o dashboard do
 * medico de verdade (listar plantoes recentes, ultimo pagamento etc).
 */
export function MedicoHomePage() {
  const { user } = useAuth();
  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center">
            <Stethoscope size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Olá, {user?.nome?.split(" ")[0] ?? "doutor(a)"}
            </h1>
            <p className="text-sm text-slate-500">
              {user?.cliente?.nome ?? "Sem hospital vinculado"}
            </p>
          </div>
        </div>
      </header>

      <div className="grid sm:grid-cols-2 gap-4">
        <Link
          to="/app/medico"
          className="card group hover:border-brand-300 transition"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-700 flex items-center justify-center">
              <CalendarClock size={20} />
            </div>
            <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded uppercase tracking-wide">
              Em breve
            </span>
          </div>
          <h3 className="font-semibold text-slate-900 mb-1">
            Meus plantões
          </h3>
          <p className="text-sm text-slate-500">
            Veja os plantões já lançados no seu nome, com data, valor e
            status de pagamento.
          </p>
        </Link>

        <Link
          to="/app/medico/extrato"
          className="card group hover:border-brand-300 transition"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center">
              <Wallet size={20} />
            </div>
            <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded uppercase tracking-wide">
              Em breve
            </span>
          </div>
          <h3 className="font-semibold text-slate-900 mb-1">Meu extrato</h3>
          <p className="text-sm text-slate-500">
            Histórico de pagamentos recebidos do hospital, com valores e
            datas confirmadas pelo banco.
          </p>
        </Link>
      </div>

      <div className="card border-amber-200 bg-amber-50/40">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
            <Construction size={18} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 mb-1">
              Área do médico em construção
            </h3>
            <p className="text-sm text-slate-600">
              Estamos finalizando os ajustes para você poder consultar seus
              plantões e pagamentos diretamente aqui. Em caso de dúvida sobre
              um pagamento específico, fale com o financeiro do hospital.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
