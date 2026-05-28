/**
 * Configurar Operação — config per-tenant editável pelo admin.
 *
 * Por enquanto (BPO MVP, sem User.cliente_id) o admin MedPag escolhe o
 * cliente num seletor e edita. Quando virarmos multi-tenant puro,
 * basta esconder o seletor e pré-fixar `cliente_id = user.cliente_id`.
 *
 * Edita:
 *   - Dia de fechamento (1-31 ou 0 = último dia útil)
 *   - Fuso horário
 *   - Modalidade preferida pra novos lançamentos
 *   - Logo URL (branding)
 *   - Cor primária (branding)
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Cog,
  Globe,
  Image as ImageIcon,
  Palette,
  Save,
  Wallet,
} from "lucide-react";

import { api, getErrorMessage } from "@/lib/api";

interface ConfigOperacao {
  id: string;
  nome: string;
  dia_fechamento: number;
  fuso_horario: string;
  modalidade_preferida: string;
  logo_url: string | null;
  cor_primaria: string;
}

interface ClienteResumo {
  id: string;
  nome: string;
}

const FUSOS_BRASIL = [
  "America/Sao_Paulo",
  "America/Manaus",
  "America/Belem",
  "America/Fortaleza",
  "America/Cuiaba",
  "America/Campo_Grande",
  "America/Porto_Velho",
  "America/Rio_Branco",
  "America/Recife",
  "America/Maceio",
  "America/Bahia",
  "America/Noronha",
];

const MODALIDADES = [
  { v: "PIX", label: "PIX" },
  { v: "TED", label: "TED" },
  { v: "CC", label: "Conta Corrente" },
  { v: "OUTRO", label: "Outra" },
];

export function ConfigurarOperacaoPage() {
  const queryClient = useQueryClient();
  const [clienteId, setClienteId] = useState<string>("");
  const [toast, setToast] = useState<{ tipo: "ok" | "erro"; msg: string } | null>(
    null,
  );

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes-lista-simples"],
    queryFn: async () => {
      const { data } = await api.get<ClienteResumo[]>("/api/clientes");
      return data;
    },
  });

  useEffect(() => {
    if (!clienteId && clientes.length > 0) {
      setClienteId(clientes[0].id);
    }
  }, [clientes, clienteId]);

  const { data: config, isLoading } = useQuery({
    queryKey: ["operacao", clienteId],
    queryFn: async () => {
      const { data } = await api.get<ConfigOperacao>(
        `/api/operacao/${clienteId}`,
      );
      return data;
    },
    enabled: !!clienteId,
  });

  const [form, setForm] = useState<Partial<ConfigOperacao>>({});

  useEffect(() => {
    if (config) {
      setForm({
        dia_fechamento: config.dia_fechamento,
        fuso_horario: config.fuso_horario,
        modalidade_preferida: config.modalidade_preferida,
        logo_url: config.logo_url,
        cor_primaria: config.cor_primaria,
      });
    }
  }, [config]);

  const salvar = useMutation({
    mutationFn: async (payload: Partial<ConfigOperacao>) => {
      const { data } = await api.put<ConfigOperacao>(
        `/api/operacao/${clienteId}`,
        payload,
      );
      return data;
    },
    onSuccess: () => {
      setToast({ tipo: "ok", msg: "Configuração salva." });
      void queryClient.invalidateQueries({ queryKey: ["operacao", clienteId] });
      setTimeout(() => setToast(null), 3000);
    },
    onError: (err) => {
      setToast({ tipo: "erro", msg: getErrorMessage(err) });
      setTimeout(() => setToast(null), 5000);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    salvar.mutate(form);
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
          <Cog className="text-brand-600" size={26} />
          Configurar Operação
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Ajustes per-tenant: fechamento, fuso, modalidade preferida e
          branding. Reflete em comprovantes, dashboards e disparos automáticos.
        </p>
      </header>

      {/* Seletor de cliente (BPO MVP) */}
      <section className="card p-4">
        <label className="block text-xs uppercase tracking-wider text-slate-500 mb-2">
          Cliente a configurar
        </label>
        <select
          value={clienteId}
          onChange={(e) => setClienteId(e.target.value)}
          className="input w-full md:w-1/2"
        >
          <option value="">Selecione...</option>
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nome}
            </option>
          ))}
        </select>
      </section>

      {toast && (
        <div
          className={`rounded-md border px-4 py-2 text-sm ${
            toast.tipo === "ok"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-900"
          }`}
        >
          {toast.tipo === "ok" && <Check size={14} className="inline mr-1" />}
          {toast.msg}
        </div>
      )}

      {clienteId && isLoading && (
        <p className="text-sm text-slate-500">Carregando configuração...</p>
      )}

      {clienteId && config && (
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Operacional */}
          <section className="card p-5 space-y-4">
            <header>
              <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                <CalendarClock size={16} /> Operacional
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Quando o ciclo fecha e em que fuso horário tudo deve aparecer.
              </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Dia do fechamento
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    min={0}
                    max={31}
                    value={form.dia_fechamento ?? 25}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        dia_fechamento: Number(e.target.value),
                      }))
                    }
                    className="input w-24"
                  />
                  <span className="text-xs text-slate-500 self-center">
                    1–31 (use <strong>0</strong> pra "último dia útil")
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1 flex items-center gap-1">
                  <Globe size={12} /> Fuso horário
                </label>
                <select
                  value={form.fuso_horario ?? "America/Sao_Paulo"}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, fuso_horario: e.target.value }))
                  }
                  className="input w-full"
                >
                  {FUSOS_BRASIL.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-slate-600 mb-1 flex items-center gap-1">
                  <Wallet size={12} /> Modalidade preferida
                </label>
                <div className="flex gap-2 flex-wrap">
                  {MODALIDADES.map((m) => (
                    <button
                      key={m.v}
                      type="button"
                      onClick={() =>
                        setForm((f) => ({ ...f, modalidade_preferida: m.v }))
                      }
                      className={`px-3 py-1.5 rounded-md text-sm border ${
                        form.modalidade_preferida === m.v
                          ? "bg-brand-600 text-white border-brand-600"
                          : "bg-white text-slate-700 border-slate-200 hover:border-brand-300"
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Sugestão padrão pra novos lançamentos — médico ainda pode
                  pedir outra ao trocar dados bancários.
                </p>
              </div>
            </div>
          </section>

          {/* Branding */}
          <section className="card p-5 space-y-4">
            <header>
              <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                <Palette size={16} /> Branding
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Aparecem em comprovantes PDF e na tela do médico (Anestesista).
              </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1 flex items-center gap-1">
                  <ImageIcon size={12} /> Logo (URL pública)
                </label>
                <input
                  type="url"
                  placeholder="https://..."
                  value={form.logo_url ?? ""}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, logo_url: e.target.value || null }))
                  }
                  className="input w-full"
                />
                {form.logo_url && (
                  <div className="mt-2 bg-slate-50 border border-slate-200 rounded p-2">
                    <img
                      src={form.logo_url}
                      alt="Logo"
                      className="h-12 object-contain"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Cor primária
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={form.cor_primaria ?? "#2D5F3F"}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, cor_primaria: e.target.value }))
                    }
                    className="h-10 w-16 rounded border border-slate-200 cursor-pointer"
                  />
                  <input
                    type="text"
                    value={form.cor_primaria ?? "#2D5F3F"}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, cor_primaria: e.target.value }))
                    }
                    pattern="^#[0-9A-Fa-f]{6}$"
                    className="input flex-1 font-mono uppercase"
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Submit */}
          <footer className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                if (config) {
                  setForm({
                    dia_fechamento: config.dia_fechamento,
                    fuso_horario: config.fuso_horario,
                    modalidade_preferida: config.modalidade_preferida,
                    logo_url: config.logo_url,
                    cor_primaria: config.cor_primaria,
                  });
                }
              }}
              className="btn-secondary"
            >
              Desfazer alterações
            </button>
            <button
              type="submit"
              disabled={salvar.isPending}
              className="btn-primary"
            >
              <Save size={14} className="mr-1.5" />
              {salvar.isPending ? "Salvando..." : "Salvar configuração"}
            </button>
          </footer>
        </form>
      )}
    </div>
  );
}
