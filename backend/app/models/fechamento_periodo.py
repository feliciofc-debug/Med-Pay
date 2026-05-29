"""Fechamento de período por hospital.

Conceito:
Quando o hospital encerra um mês operacional, o gestor "tranca" o
período. Isso congela um snapshot do que foi lançado (fichas, valores,
médicos) e habilita a geração do lote de pagamento + extrato consolidado
pra mandar pro contador / financeiro / RH.

Ciclo de vida:
    ABERTO  ───tranca────►  TRANCADO  ───gerar_lote───►  GERADO_LOTE
                              ▲                              │
                              └──────── reabrir ─────────────┘
                              (só se ainda não tem lote)

Snapshot guardado:
    - total_centavos: valor total do período no momento do trancamento
    - qtd_fichas: quantas fichas entraram
    - qtd_medicos: quantos médicos distintos
    - lote_id: preenchido quando vira lote
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StatusFechamento(str, Enum):
    """Estados do fechamento."""

    ABERTO = "ABERTO"
    TRANCADO = "TRANCADO"
    GERADO_LOTE = "GERADO_LOTE"
    PAGO = "PAGO"


class FechamentoPeriodo(Base):
    """Fechamento mensal de um hospital."""

    __tablename__ = "fechamentos_periodo"

    __table_args__ = (
        # Um hospital só pode ter um fechamento por mes/ano
        UniqueConstraint(
            "cliente_id", "ano", "mes", name="uq_fechamento_cliente_mes"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Período (ano/mês, ex: 2026 / 5 = maio/2026)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[StatusFechamento] = mapped_column(
        SAEnum(StatusFechamento, name="status_fechamento"),
        nullable=False,
        default=StatusFechamento.TRANCADO,
        index=True,
    )

    # Snapshot capturado no momento do trancamento
    total_centavos: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    qtd_fichas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_medicos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_linhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Lote gerado a partir deste fechamento (opcional, vira depois)
    lote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lotes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Quem trancou
    trancado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trancado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Reabertura (se houve)
    reaberto_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reaberto_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    observacoes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Detalhes do snapshot (ex: ids das fichas incluídas)
    metadados: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relacionamentos
    cliente = relationship("Cliente", foreign_keys=[cliente_id])
    lote = relationship("Lote", foreign_keys=[lote_id])
    trancado_por = relationship("User", foreign_keys=[trancado_por_id])
    reaberto_por = relationship("User", foreign_keys=[reaberto_por_id])

    @property
    def competencia(self) -> str:
        """Retorna competência no formato MM/YYYY."""
        return f"{self.mes:02d}/{self.ano}"

    @property
    def pode_reabrir(self) -> bool:
        """Só pode reabrir se ainda não tiver gerado lote/pago."""
        return self.status == StatusFechamento.TRANCADO

    def __repr__(self) -> str:
        return (
            f"<FechamentoPeriodo {self.competencia} cliente={self.cliente_id} "
            f"status={self.status.value}>"
        )
