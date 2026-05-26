"""Lançamento de serviço feito por um médico anestesista (autoatendimento).

Modela o evento "o médico fez o serviço X na data Y" — o input bruto da
operação do BPO antes do fechamento mensal.

DIFERENCIAL DE PRIVACIDADE: o médico **só vê os próprios lançamentos**.
A operação antiga era uma planilha aberta onde todos viam tudo (terrível
pra confidencialidade). Aqui o filtro é hard: o token de sessão carrega
o CRM e o backend filtra por `beneficiario_id` correspondente.

CICLO DE VIDA:
    LANCADO → CONFERIDO → INCLUIDO_EM_LOTE → PAGO
    - LANCADO: médico acabou de criar. Pode editar/excluir.
    - CONFERIDO: BPO bateu o olho e validou.
    - INCLUIDO_EM_LOTE: virou linha de um Lote pronto pra aprovação.
    - PAGO: pagamento confirmado pelo retorno CNAB.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.beneficiario import Beneficiario
    from app.models.cliente import Cliente
    from app.models.codigo_servico import CodigoServico


class StatusLancamento(str, Enum):
    """Estado do lançamento ao longo do ciclo de vida."""

    LANCADO = "LANCADO"
    CONFERIDO = "CONFERIDO"
    INCLUIDO_EM_LOTE = "INCLUIDO_EM_LOTE"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"


class LancamentoServico(Base):
    """Um serviço prestado por um médico, lançado pelo próprio."""

    __tablename__ = "lancamentos_servico"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    beneficiario_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("beneficiarios.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    codigo_servico_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("codigos_servico.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    data_servico: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # ===== Snapshot do código no momento do lançamento =====
    # Importante: o valor da tabela pode mudar depois (reajuste anual,
    # por exemplo). Congelamos o valor cobrado no momento do registro
    # pra preservar a integridade contábil do pagamento.
    codigo_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    descricao_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    valor_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # ===== Contexto opcional =====
    hospital_local: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paciente_iniciais: Mapped[str | None] = mapped_column(String(10), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[StatusLancamento] = mapped_column(
        SAEnum(
            StatusLancamento,
            name="status_lancamento_servico",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=StatusLancamento.LANCADO,
        server_default=StatusLancamento.LANCADO.value,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    beneficiario: Mapped["Beneficiario"] = relationship("Beneficiario", lazy="joined")
    codigo_servico: Mapped["CodigoServico"] = relationship(
        "CodigoServico", lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<LancamentoServico id={self.id} medico={self.beneficiario_id} "
            f"codigo={self.codigo_snapshot} data={self.data_servico} "
            f"valor={self.valor_centavos}c status={self.status.value}>"
        )


__all__ = ["LancamentoServico", "StatusLancamento"]
