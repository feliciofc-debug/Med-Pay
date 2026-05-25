"""Contrato comercial entre o MedPag (operador BPO) e o hospital cliente.

Este modelo materializa em banco o que antes era mock no front:

- Quanto o MedPag cobra do hospital (mensalidade + taxa por pagamento +
  % sobre volume movimentado).
- Quanto o MedPag tem de custo pra atender esse hospital (custo fixo
  + variável % sobre receita).
- Meta mensal do MedPag pra esse contrato (referência pra alertas de
  saúde do contrato no Executivo).
- Vigência (vencimento próximo dispara alerta de renovação).

A margem é derivada no Dashboard Executivo:
    receita = mensalidade + (qtd_pagamentos_mes * taxa_por_pgto) +
              (volume_movimentado_mes * pct_volume / 100)
    custo   = custo_fixo + (receita * custo_variavel_pct / 100)
    margem  = receita - custo
    margem_pct = margem / receita

Histórico: como reajuste de contrato é frequente em relação BPO ↔
hospital, mantemos versionamento simples — quando muda, o registro
anterior vira `ativo=False` (o histórico fica preservado pra defesa
contratual e drill-down).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente


class ModoCobranca(str, Enum):
    """Como o MedPag cobra esse hospital.

    PERCENTUAL_REPASSE — MedPag desconta X% do valor pago aos médicos
        antes de repassar (modelo privado, ex.: Santa Casa 18%).

    MENSALIDADE_SAAS — Hospital paga uma mensalidade fixa pelo software,
        100% do valor vai pros médicos sem desconto MedPag (modelo
        público, ex.: Hospital do Cérebro com verba apertada).
    """

    PERCENTUAL_REPASSE = "PERCENTUAL_REPASSE"
    MENSALIDADE_SAAS = "MENSALIDADE_SAAS"


class ContratoHospital(Base):
    """Contrato comercial vigente entre MedPag e um hospital."""

    __tablename__ = "contratos_hospital"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Define a regra de cobrança. Ver `ModoCobranca`.
    modo_cobranca: Mapped[ModoCobranca] = mapped_column(
        SAEnum(
            ModoCobranca,
            name="modo_cobranca_hospital",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,  # criamos o type via migration idempotente
        ),
        nullable=False,
        default=ModoCobranca.PERCENTUAL_REPASSE,
        server_default=ModoCobranca.PERCENTUAL_REPASSE.value,
    )

    # ===== COBRANÇA (o que o MedPag fatura do hospital) =====

    # Valor fixo mensal cobrado do hospital, em centavos.
    mensalidade_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Taxa cobrada por cada pagamento processado.
    taxa_por_pagamento_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Percentual sobre o volume movimentado, em basis points (10000 = 100%).
    # Ex.: 120 bp = 1,20%
    percentual_volume_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Volume médio mensal estimado (pra projeção quando ainda não há dados).
    # Em centavos. Quando o Executivo tem dados reais (lotes do mês),
    # usa o real e ignora esse aqui.
    volume_medio_mensal_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # ===== CUSTO (o que o MedPag gasta pra atender) =====

    # Custo fixo mensal (infra alocada, gestor de conta, etc.) em centavos.
    custo_fixo_mensal_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # Custo variável como % da receita gerada (suporte/sucesso). 0-100.
    custo_variavel_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # ===== METAS / SAÚDE =====

    # Meta mensal de receita pra esse contrato (em centavos). Usada nos
    # cards de "% atingido da meta" no Executivo.
    meta_mensal_centavos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # ===== VIGÊNCIA =====

    # Data em que entrou em vigor (se há histórico, pode haver vários).
    vigencia_inicio: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    # Data de vencimento (renovação). Alerta dispara N dias antes.
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ===== STATUS =====

    # Apenas UM contrato ativo por cliente. Reajuste = novo registro
    # ativo + antigo vira inativo (preserva histórico).
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    observacoes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ===== Relacionamentos =====

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<ContratoHospital cliente={self.cliente_id} "
            f"mensalidade={self.mensalidade_centavos}c "
            f"ativo={self.ativo}>"
        )
