"""Modelo de Lote — conjunto de pagamentos vindos de um cliente."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.pagamento import Pagamento
    from app.models.user import User


class StatusLote(str, Enum):
    """Status possíveis de um lote durante seu ciclo de vida."""

    RECEBIDO = "RECEBIDO"              # Acabou de chegar, ainda não processado
    PROCESSANDO = "PROCESSANDO"        # Worker está validando os pagamentos
    AGUARDANDO_REVISAO = "AGUARDANDO_REVISAO"  # Validado, esperando Thiago
    APROVADO = "APROVADO"              # Thiago aprovou, CNAB gerado
    ENVIADO_BANCO = "ENVIADO_BANCO"    # Arquivo CNAB foi baixado/enviado
    CONCILIADO = "CONCILIADO"          # Retorno do banco processado
    REJEITADO = "REJEITADO"            # Thiago rejeitou o lote inteiro
    ERRO = "ERRO"                      # Erro de processamento


class Lote(Base):
    """Lote de pagamentos.

    Identificado por hash do conteúdo (idempotência):
    se o mesmo arquivo for enviado 2x, recuperamos o lote existente.
    """

    __tablename__ = "lotes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )

    # ===== Identificação =====
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    hash_conteudo: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    referencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Ex: "Junho/2026", "Folha 06/2026", livre

    # ===== Status =====
    status: Mapped[StatusLote] = mapped_column(
        SAEnum(StatusLote, name="status_lote"),
        nullable=False,
        default=StatusLote.RECEBIDO,
        index=True,
    )

    # ===== Estatísticas =====
    total_pagamentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_validos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_corrigiveis: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bloqueados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valor_total_centavos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ===== Arquivos =====
    caminho_arquivo_original: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caminho_arquivo_cnab: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hash_arquivo_cnab: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nome_arquivo_cnab: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Bytes do CNAB persistidos no banco (Render/Vercel têm disco efêmero;
    # sem isso o arquivo somia após cada deploy).
    conteudo_arquivo_cnab: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    caminho_arquivo_retorno: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ===== Quem subiu (operador) =====
    enviado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    # ===== Aprovação =====
    aprovado_por_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    aprovado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observacoes_aprovacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== Erros =====
    mensagem_erro: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== Timestamps =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ===== Relacionamentos =====
    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="lotes")
    enviado_por: Mapped["User | None"] = relationship(
        "User", back_populates="lotes_enviados", foreign_keys=[enviado_por_id]
    )
    aprovado_por: Mapped["User | None"] = relationship(
        "User", back_populates="lotes_aprovados", foreign_keys=[aprovado_por_id]
    )
    pagamentos: Mapped[list["Pagamento"]] = relationship(
        "Pagamento", back_populates="lote", cascade="all, delete-orphan"
    )

    @property
    def pode_aprovar(self) -> bool:
        """Só permite aprovação se estiver aguardando revisão e tiver algum válido."""
        return (
            self.status == StatusLote.AGUARDANDO_REVISAO
            and (self.total_validos + self.total_corrigiveis) > 0
        )

    @property
    def valor_total_reais(self) -> float:
        """Converte centavos para reais (para exibição)."""
        return self.valor_total_centavos / 100

    def __repr__(self) -> str:
        return (
            f"<Lote id={self.id} cliente_id={self.cliente_id} "
            f"status={self.status.value} pagamentos={self.total_pagamentos}>"
        )
