import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CreditCard,
  Stethoscope,
  Wallet,
} from "lucide-react";

import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

interface PerfilMedico {
  nome: string;
  email: string;
  cpf_mascarado: string | null;
  hospital: string | null;
  hospital_id: string | null;
  beneficiario_id: string | null;
  vinculado: boolean;
  pix_modalidade: string | null;
  pix_chave_mascarada: string | null;
  banco_nome: string | null;
  conta_mascarada: string | null;
  conta_verificada: boolean;
}

interface Plantao {
  ficha_id: string;
  nome_arquivo: string;
  competencia: string | null;
  coordenador: string | null;
  data_lancamento: string;
  status_ficha: string;
  valor_centavos: number;
  detalhe: string | null;
}

interface PlantoesResponse {
  plantoes: Plantao[];
  total: number;
  valor_total_centavos: number;
}

interface ResumoExtrato {
  total_pago_centavos: number;
  total_pendente_centavos: number;
  total_rejeitado_centavos: number;
  qtd_pagamentos: number;
}

function formatarValor(centavos: number): string {
  return (centavos / 100).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

export function MedicoHomePage() {
  const perfilQ = useQuery({
    queryKey: ["medico-perfil"],
    queryFn: async () => {
      const res = await api.get<PerfilMedico>("/api/medico/me");
      return res.data;
    },
  });

  const plantoesQ = useQuery({
    queryKey: ["medico-plantoes"],
    queryFn: async () => {
      const res = await api.get<PlantoesResponse>("/api/medico/plantoes?limit=20");
      return res.data;
    },
    enabled: perfilQ.data?.vinculado === true,
  });

  const extratoQ = useQuery({
    queryKey: ["medico-extrato-resumo"],
    queryFn: async () => {
      const res = await api.get<{ resumo: ResumoExtrato }>(
        "/api/medico/extrato?limit=10",
      );
      return res.data;
    },
    enabled: perfilQ.data?.vinculado === true,
  });

  const perfil = perfilQ.data;
  const resumo = extratoQ.data?.resumo;

  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center">
            <Stethoscope size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Olá, {perfil?.nome?.split(" ")[0] ?? "doutor(a)"}
            </h1>
            <p className="text-sm text-slate-500">
              {perfil?.hospital ?? "Sem hospital vinculado"}
            </p>
          </div>
        </div>
      </header>

      {/* -------- Aviso se não está vinculado -------- */}
      {perfil && !perfil.vinculado && (
        <div className="card border-amber-200 bg-amber-50/40">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
              <AlertTriangle size={18} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 mb-1">
                Você ainda não está vinculado a um cadastro de prestador
              </h3>
              <p className="text-sm text-slate-600">
                Peça ao coordenador do hospital pra te cadastrar como
                Beneficiário e amarrar ao seu login. Assim você vai ver
                seus plantões e pagamentos por aqui.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* -------- Card de identidade -------- */}
      {perfil?.vinculado && (
        <div className="card">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wide mb-1">
                Identidade
              </div>
              <div className="font-semibold text-slate-900">{perfil.nome}</div>
              <div className="text-xs text-slate-500">{perfil.email}</div>
              {perfil.cpf_mascarado && (
                <div className="text-xs text-slate-500 mt-1 font-mono">
                  CPF: {perfil.cpf_mascarado}
                </div>
              )}
            </div>
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wide mb-1">
                Forma de pagamento
              </div>
              {perfil.pix_modalidade === "PIX" && (
                <>
                  <div className="font-semibold text-emerald-700 inline-flex items-center gap-1">
                    <CreditCard size={14} />
                    PIX
                  </div>
                  <div className="text-xs text-slate-500 font-mono truncate">
                    {perfil.pix_chave_mascarada}
                  </div>
                </>
              )}
              {perfil.pix_modalidade === "TED" && (
                <>
                  <div className="font-semibold text-slate-700 inline-flex items-center gap-1">
                    <CreditCard size={14} />
                    Transferência
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    {perfil.banco_nome ?? "Banco"}
                  </div>
                  <div className="text-xs text-slate-500 font-mono">
                    Conta: {perfil.conta_mascarada}
                  </div>
                </>
              )}
              {!perfil.pix_modalidade && (
                <div className="text-sm text-amber-700">
                  Sem dados bancários cadastrados
                </div>
              )}
            </div>
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wide mb-1">
                Status da conta
              </div>
              {perfil.conta_verificada ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 size={12} />
                  Validada por pagamento confirmado
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-50 text-slate-700 border border-slate-200">
                  Ainda não validada
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* -------- Resumo financeiro -------- */}
      {perfil?.vinculado && resumo && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="card border-emerald-200 bg-emerald-50/40">
            <div className="text-[11px] text-emerald-700 uppercase tracking-wide">
              Já pago
            </div>
            <div className="text-2xl font-bold text-emerald-900 mt-1">
              {formatarValor(resumo.total_pago_centavos)}
            </div>
          </div>
          <div className="card border-amber-200 bg-amber-50/40">
            <div className="text-[11px] text-amber-700 uppercase tracking-wide">
              Pendente
            </div>
            <div className="text-2xl font-bold text-amber-900 mt-1">
              {formatarValor(resumo.total_pendente_centavos)}
            </div>
          </div>
          <div className="card border-red-200 bg-red-50/40">
            <div className="text-[11px] text-red-700 uppercase tracking-wide">
              Rejeitado
            </div>
            <div className="text-2xl font-bold text-red-900 mt-1">
              {formatarValor(resumo.total_rejeitado_centavos)}
            </div>
          </div>
        </div>
      )}

      {/* -------- Plantões recentes -------- */}
      {perfil?.vinculado && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-slate-900 inline-flex items-center gap-2">
              <CalendarClock size={18} className="text-brand-700" />
              Meus plantões recentes
            </h2>
            {plantoesQ.data && plantoesQ.data.total > 0 && (
              <span className="text-xs text-slate-500">
                {plantoesQ.data.total} plantão(ões) — total{" "}
                <strong>
                  {formatarValor(plantoesQ.data.valor_total_centavos)}
                </strong>
              </span>
            )}
          </div>

          {plantoesQ.isLoading && (
            <div className="text-sm text-slate-500 py-3">Carregando…</div>
          )}

          {plantoesQ.data && plantoesQ.data.plantoes.length === 0 && (
            <div className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-6 text-center">
              Nenhum plantão lançado em seu nome ainda.
            </div>
          )}

          {plantoesQ.data && plantoesQ.data.plantoes.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500 uppercase tracking-wide border-b border-slate-200">
                  <tr>
                    <th className="text-left px-2 py-2">Data</th>
                    <th className="text-left px-2 py-2">Competência</th>
                    <th className="text-left px-2 py-2">Detalhe</th>
                    <th className="text-left px-2 py-2">Status</th>
                    <th className="text-right px-2 py-2">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {plantoesQ.data.plantoes.map((p) => (
                    <tr
                      key={`${p.ficha_id}-${p.data_lancamento}-${p.valor_centavos}`}
                      className="border-b border-slate-100"
                    >
                      <td className="px-2 py-2 text-xs">
                        {formatDateTime(p.data_lancamento)}
                      </td>
                      <td className="px-2 py-2 font-mono text-xs">
                        {p.competencia ?? "—"}
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-600 max-w-[300px] truncate">
                        {p.detalhe ?? "Plantão"}
                      </td>
                      <td className="px-2 py-2">
                        <span className="text-[10px] uppercase tracking-wide text-slate-500">
                          {p.status_ficha}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right font-semibold">
                        {formatarValor(p.valor_centavos)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* -------- Link pro extrato detalhado -------- */}
      {perfil?.vinculado && (
        <div className="text-center">
          <Link
            to="/app/medico/extrato"
            className="inline-flex items-center gap-2 text-sm text-brand-700 hover:text-brand-900 font-medium"
          >
            <Wallet size={16} />
            Ver extrato detalhado de pagamentos →
          </Link>
        </div>
      )}
    </div>
  );
}
