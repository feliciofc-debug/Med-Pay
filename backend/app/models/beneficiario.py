"""Modelo de Beneficiário (médico/prestador que recebe pagamento).

A grande sacada deste modelo: o sistema APRENDE com as correções feitas.
Toda vez que o operador corrige dados de um CPF, salvamos aqui.
Na próxima planilha que vier com esse CPF, sugerimos automaticamente.

REGRAS DE SEGURANÇA:
- CPF criptografado em `cpf_encrypted` (BYTEA, Fernet)
- Hash determinístico em `cpf_hash` (SHA-256) pra busca
- CPF mascarado em `cpf_mascarado` pra exibição em logs/listas
- Conta bancária também criptografada
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.pagamento import Pagamento


class Beneficiario(Base):
    """Beneficiário (médico/prestador).

    Persistido depois da primeira aparição num lote.
    Acumula histórico e aprende com cada lote.
    """

    __tablename__ = "beneficiarios"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # ===== Identificação (criptografada) =====
    cpf_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    cpf_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    cpf_mascarado: Mapped[str] = mapped_column(String(20), nullable=False)

    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # ===== Dados bancários (criptografados) =====
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agencia_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    conta_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    conta_mascarada: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ===== Chave PIX (opcional, criptografada) =====
    pix_chave_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pix_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # tipo: "CPF", "EMAIL", "TELEFONE", "ALEATORIA"

    # ===== Estatísticas (pra detectar valores suspeitos) =====
    total_pagamentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valor_medio_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valor_min_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valor_max_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ultimo_pagamento_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    pagamentos: Mapped[list["Pagamento"]] = relationship("Pagamento", back_populates="beneficiario")

    def __repr__(self) -> str:
        return f"<Beneficiario id={self.id} nome={self.nome} cpf={self.cpf_mascarado}>"
