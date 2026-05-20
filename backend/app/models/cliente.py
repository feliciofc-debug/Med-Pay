"""Modelo de Cliente (hospital, clínica, ONG que envia planilhas)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.lote import Lote


class Cliente(Base):
    """Cliente que envia planilhas de pagamento.

    Tipicamente um hospital, clínica ou ONG. Cada cliente pode ter
    formato próprio de planilha — o mapeamento de colunas é salvo
    em `mapeamento_colunas` (JSON) pra reaproveitar.
    """

    __tablename__ = "clientes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True, unique=True, index=True)
    email_contato: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Email autorizado a enviar planilhas (whitelist)
    # Quando email chega de um remetente nesta lista, sistema identifica o cliente
    email_remetente_autorizado: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Mapeamento de colunas da planilha deste cliente
    # Ex: {"cpf": "Documento", "nome": "Beneficiário", "valor": "Valor Bruto", ...}
    mapeamento_colunas: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    lotes: Mapped[list["Lote"]] = relationship("Lote", back_populates="cliente")

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} nome={self.nome}>"
