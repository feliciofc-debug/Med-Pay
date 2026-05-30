"""Dispatcher do modo de repasse (Eixo 3 da engenharia de modelos).

Dado um cliente, diz QUAL estratégia de repasse aplicar e o que ela
produz. Strategy pattern leve: o endpoint/worker consulta o descritor e
roteia pro gerador certo (CNAB, export RH, distribuição SCP) — sem
`if/elif` espalhado pelo código.

Regra inviolável: NENHUM modo move dinheiro pela MedPag. CNAB e SCP
geram instrução pro banco tradicional; EXPORT_RH entrega arquivo pro RH;
SOMENTE_GESTAO não paga. O Asaas nunca entra aqui (ele é só mensalidade
+ validação de CPF).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.cliente import Cliente, ModoPagamento


@dataclass(frozen=True, slots=True)
class EstrategiaRepasse:
    """Descritor de uma estratégia de execução de repasse."""

    modo: ModoPagamento
    label: str
    descricao: str
    gera_arquivo: bool       # produz artefato pra download?
    formato: str | None      # 'CNAB240' | 'CSV' | 'CNAB240_SCP' | None
    executa_pagamento: bool  # instrui pagamento (mesmo que via banco)?


_ESTRATEGIAS: dict[ModoPagamento, EstrategiaRepasse] = {
    ModoPagamento.CNAB_BANCARIO: EstrategiaRepasse(
        modo=ModoPagamento.CNAB_BANCARIO,
        label="CNAB (banco tradicional)",
        descricao=(
            "Gera arquivo CNAB 240; o hospital deposita pela conta dele no "
            "banco emissor. A MedPag não custodia."
        ),
        gera_arquivo=True,
        formato="CNAB240",
        executa_pagamento=True,
    ),
    ModoPagamento.EXPORT_RH: EstrategiaRepasse(
        modo=ModoPagamento.EXPORT_RH,
        label="Exportar pro RH",
        descricao=(
            "Exporta CSV/planilha pro RH do cliente processar a folha "
            "(hospital público, folha municipal/eSocial)."
        ),
        gera_arquivo=True,
        formato="CSV",
        executa_pagamento=False,
    ),
    ModoPagamento.REPASSE_SCP: EstrategiaRepasse(
        modo=ModoPagamento.REPASSE_SCP,
        label="Repasse SCP",
        descricao=(
            "Distribui o resultado apurado aos médicos participantes da SCP; "
            "a distribuição vira lote/CNAB no banco tradicional."
        ),
        gera_arquivo=True,
        formato="CNAB240_SCP",
        executa_pagamento=True,
    ),
    ModoPagamento.SOMENTE_GESTAO: EstrategiaRepasse(
        modo=ModoPagamento.SOMENTE_GESTAO,
        label="Somente gestão",
        descricao="Não executa pagamento — só gestão e relatórios.",
        gera_arquivo=False,
        formato=None,
        executa_pagamento=False,
    ),
}


def estrategia_do_modo(modo: ModoPagamento) -> EstrategiaRepasse:
    """Descritor da estratégia pra um modo (CNAB como fallback seguro)."""
    return _ESTRATEGIAS.get(modo, _ESTRATEGIAS[ModoPagamento.CNAB_BANCARIO])


def estrategia_do_cliente(cliente: Cliente) -> EstrategiaRepasse:
    """Descritor da estratégia de repasse do cliente."""
    modo = getattr(cliente, "modo_pagamento", None) or ModoPagamento.CNAB_BANCARIO
    return estrategia_do_modo(modo)


def todas_estrategias() -> list[EstrategiaRepasse]:
    """Lista todas as estratégias (pra UI/admin exibir as opções)."""
    return list(_ESTRATEGIAS.values())


__all__ = [
    "EstrategiaRepasse",
    "estrategia_do_cliente",
    "estrategia_do_modo",
    "todas_estrategias",
]
