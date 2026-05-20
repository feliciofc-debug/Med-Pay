"""Modelo de Auditoria — log imutável de operações sensíveis.

REGRA: TODA operação financeira gera entrada de auditoria.
- Aprovação de lote
- Geração de arquivo CNAB
- Edição manual de pagamento
- Login/logout de aprovador
- Acesso a dados sensíveis

Tabela append-only. NUNCA fazer UPDATE ou DELETE.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Auditoria(Base):
    """Registro de auditoria de operação sensível."""

    __tablename__ = "auditoria"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    # Ação realizada (verbo no passado)
    # Ex: "LOTE_APROVADO", "CNAB_GERADO", "PAGAMENTO_EDITADO", "LOGIN", "LOGOUT"
    acao: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Tipo da entidade afetada (ex: "Lote", "Pagamento", "Cliente")
    entidade_tipo: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )

    # Detalhes em JSON estruturado
    # Ex: {"valor_total": 28745000, "qtd_pagamentos": 437, "hash_cnab": "abc..."}
    detalhes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Hash do conteúdo afetado (se aplicável)
    # Ex: hash do arquivo CNAB gerado, hash da planilha aprovada
    hash_relacionado: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Contexto da requisição
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mensagem livre em português
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    user: Mapped["User | None"] = relationship("User", back_populates="eventos_auditoria")

    def __repr__(self) -> str:
        return (
            f"<Auditoria id={self.id} user_id={self.user_id} "
            f"acao={self.acao} entidade={self.entidade_tipo}>"
        )
