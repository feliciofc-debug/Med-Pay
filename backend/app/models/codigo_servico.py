"""Tabela de códigos de serviço usados pela operação BPO.

Cada cliente (BPO) tem sua própria tabela de códigos. O caso de uso original
é o do Sandro, que opera com ~60 anestesistas e identifica cada serviço
prestado por um código fixo da planilha dele (ex.: `ANE001` = "Anestesia
geral em cirurgia média").

Fluxo:
    1. Admin BPO importa a planilha XLSX do cliente (ver
       `services/codigo_servico_importacao.py`).
    2. Médico (anestesista) entra com CRM, digita data + código.
    3. Sistema busca o código aqui, retorna descrição e valor.
    4. Gera um `LancamentoServico` ligado ao médico (Beneficiario).
    5. No fechamento, o BPO consolida e gera CNAB pagando todos.

Idempotência: UNIQUE (`cliente_id`, `codigo`) — re-importar a planilha
atualiza valores em vez de duplicar (estratégia upsert no importador).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente


class CodigoServico(Base):
    """Código de serviço da tabela do cliente BPO."""

    __tablename__ = "codigos_servico"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    codigo: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    descricao: Mapped[str] = mapped_column(String(500), nullable=False)

    valor_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    categoria: Mapped[str | None] = mapped_column(String(120), nullable=True)
    porte: Mapped[str | None] = mapped_column(String(40), nullable=True)

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

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")

    __table_args__ = (
        UniqueConstraint("cliente_id", "codigo", name="uq_codigo_servico_cliente_codigo"),
    )

    def __repr__(self) -> str:
        return (
            f"<CodigoServico id={self.id} codigo={self.codigo} "
            f"valor={self.valor_centavos}c cliente={self.cliente_id}>"
        )


__all__ = ["CodigoServico"]
