import { cn } from "@/lib/utils";
import type { ModalidadePagamento, StatusLote, StatusPagamento } from "@/types";

const LOTE_STYLES: Record<StatusLote, { label: string; className: string }> = {
  RECEBIDO: { label: "Recebido", className: "bg-slate-100 text-slate-700" },
  PROCESSANDO: { label: "Processando", className: "bg-blue-100 text-blue-700" },
  AGUARDANDO_REVISAO: {
    label: "Aguardando Revisão",
    className: "bg-amber-100 text-amber-800",
  },
  APROVADO: { label: "Aprovado", className: "bg-emerald-100 text-emerald-800" },
  ENVIADO_BANCO: {
    label: "Enviado ao Banco",
    className: "bg-indigo-100 text-indigo-700",
  },
  CONCILIADO: { label: "Conciliado", className: "bg-green-100 text-green-800" },
  REJEITADO: { label: "Rejeitado", className: "bg-red-100 text-red-700" },
  ERRO: { label: "Erro", className: "bg-red-100 text-red-700" },
};

const PAGAMENTO_STYLES: Record<
  StatusPagamento,
  { label: string; className: string }
> = {
  VALIDO: { label: "OK", className: "bg-emerald-100 text-emerald-800" },
  CORRIGIVEL: { label: "Sugestão", className: "bg-amber-100 text-amber-800" },
  BLOQUEADO: { label: "Bloqueado", className: "bg-red-100 text-red-700" },
  APROVADO: { label: "Aprovado", className: "bg-emerald-200 text-emerald-900" },
  REJEITADO: { label: "Rejeitado", className: "bg-red-100 text-red-700" },
  PAGO: { label: "Pago", className: "bg-green-100 text-green-800" },
  NAO_PAGO: { label: "Não Pago", className: "bg-red-100 text-red-700" },
};

export function StatusBadgeLote({ status }: { status: StatusLote }) {
  const s = LOTE_STYLES[status];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
        s.className,
      )}
    >
      {s.label}
    </span>
  );
}

export function StatusBadgePagamento({ status }: { status: StatusPagamento }) {
  const s = PAGAMENTO_STYLES[status];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        s.className,
      )}
    >
      {s.label}
    </span>
  );
}

const MODALIDADE_STYLES: Record<
  ModalidadePagamento,
  { label: string; className: string; hint: string }
> = {
  PIX: {
    label: "PIX",
    className: "bg-emerald-100 text-emerald-800 border border-emerald-200",
    hint: "Pagamento via chave PIX (mais rápido e barato)",
  },
  TED: {
    label: "TED",
    className: "bg-blue-100 text-blue-700 border border-blue-200",
    hint: "TED para outro banco (forma_lanc 01)",
  },
  TRANSF_UNICRED: {
    label: "Interna",
    className: "bg-brand-100 text-brand-800 border border-brand-200",
    hint: "Transferência interna Unicred (forma_lanc 41)",
  },
};

export function ModalidadeBadge({
  modalidade,
}: {
  modalidade: ModalidadePagamento;
}) {
  const s = MODALIDADE_STYLES[modalidade];
  return (
    <span
      title={s.hint}
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        s.className,
      )}
    >
      {s.label}
    </span>
  );
}
