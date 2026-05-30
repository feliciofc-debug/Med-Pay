"""Aporte recebido de um hospital da carteira.

Fluxo do repasse: o hospital deposita o dinheiro na conta da empresa de
repasse (Atom) ANTES de a Atom executar os pagamentos aos médicos. Este
registro rastreia esses depósitos por hospital — e é o que "libera" a
distribuição daquele hospital (só paga o que entrou).

A MedPag/Atom não custodia: o dinheiro entra numa conta tradicional
(EmpresaConfig/Conta de Repasse) e sai dela via CNAB. Aqui só registramos
o recebimento pra dar saldo e trilha de auditoria.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class StatusAporte(str, Enum):
    """PENDENTE = lançado, aguardando conferência. CONFIRMADO = dinheiro
    bateu na conta (libera o pagamento daquele hospital)."""

    PENDENTE = "PENDENTE"
    CONFIRMADO = "CONFIRMADO"


class AporteHospital(Base):
    """Depósito recebido de um hospital da carteira na conta da Atom."""

    __tablename__ = "aportes_hospital"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Hospital (cliente filho) que fez o depósito.
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Conta de repasse que recebeu (qual banco da Atom).
    conta_pagadora_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("empresa_config.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Lote que esse aporte financia (opcional).
    lote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    valor_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_recebimento: Mapped[date] = mapped_column(Date, nullable=False)
    competencia: Mapped[str | None] = mapped_column(String(7), nullable=True)  # MM/YYYY
    referencia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[StatusAporte] = mapped_column(
        SAEnum(
            StatusAporte,
            name="status_aporte",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=StatusAporte.PENDENTE,
        server_default=StatusAporte.PENDENTE.value,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AporteHospital id={self.id} cliente={self.cliente_id} "
            f"valor={self.valor_centavos} status={self.status}>"
        )


__all__ = ["AporteHospital", "StatusAporte"]
