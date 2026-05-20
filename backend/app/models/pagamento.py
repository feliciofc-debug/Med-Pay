"""Modelo de Pagamento — uma linha de pagamento dentro de um lote."""

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
    from app.models.beneficiario import Beneficiario
    from app.models.lote import Lote


class StatusPagamento(str, Enum):
    """Status de um pagamento individual."""

    VALIDO = "VALIDO"           # Passou em todas as validações
    CORRIGIVEL = "CORRIGIVEL"   # Sistema tem sugestão de correção
    BLOQUEADO = "BLOQUEADO"     # Não pode ser enviado, erro grave
    APROVADO = "APROVADO"       # Aprovado pelo aprovador
    REJEITADO = "REJEITADO"     # Aprovador rejeitou
    PAGO = "PAGO"               # Banco confirmou processamento
    NAO_PAGO = "NAO_PAGO"       # Banco rejeitou (motivo no campo retorno_*)


class ModalidadePagamento(str, Enum):
    """Modalidade de envio do pagamento no CNAB 240.

    Espelha as abas do template Unicred do Thiago:
    - PIX (tipo_servico=98, forma_lanc=45) — favorecido tem chave PIX
    - TED (tipo_servico=30, forma_lanc=01) — favorecido em outro banco
    - TRANSF_UNICRED (tipo_servico=98, forma_lanc=41) — favorecido na Unicred

    Default ao processar uma planilha: o sistema decide
    automaticamente (regra em `_decidir_modalidade`):
    - banco destino == 136 → TRANSF_UNICRED
    - tem chave PIX cadastrada → PIX
    - senão → TED
    """

    PIX = "PIX"
    TED = "TED"
    TRANSF_UNICRED = "TRANSF_UNICRED"


class Pagamento(Base):
    """Pagamento individual dentro de um lote.

    REGRAS DE SEGURANÇA:
    - cpf, conta criptografados via Fernet (BYTEA)
    - cpf_mascarado, conta_mascarada para exibição em listas
    - cpf_hash para busca/deduplicação
    - valor em centavos (Integer) — NUNCA float para dinheiro
    """

    __tablename__ = "pagamentos"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    lote_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lotes.id"), nullable=False, index=True
    )
    beneficiario_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("beneficiarios.id"), nullable=True, index=True
    )

    # ===== Número da linha original (pra rastreabilidade na planilha) =====
    linha_planilha: Mapped[int] = mapped_column(Integer, nullable=False)

    # ===== Identificação do beneficiário (criptografado) =====
    cpf_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    cpf_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cpf_mascarado: Mapped[str] = mapped_column(String(20), nullable=False)
    cpf_original: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # ^ valor original da planilha (sujo) pra mostrar qual foi a sugestão

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # ===== Dados bancários (criptografados) =====
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agencia_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    conta_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    conta_mascarada: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ===== Valor (sempre em centavos!) =====
    valor_centavos: Mapped[int] = mapped_column(Integer, nullable=False)

    # ===== Modalidade de envio (alinhado com template Unicred do Thiago) =====
    modalidade: Mapped[ModalidadePagamento] = mapped_column(
        SAEnum(ModalidadePagamento, name="modalidade_pagamento"),
        nullable=False,
        default=ModalidadePagamento.TED,
        index=True,
    )
    # Chave PIX (opcional): se preenchida, o pagamento vira PIX por chave
    # em vez de PIX por agência/conta. Tipos aceitos: CPF, CNPJ, email,
    # telefone, EVP (chave aleatória).
    chave_pix: Mapped[str | None] = mapped_column(String(77), nullable=True)

    # ===== Status e validação =====
    status: Mapped[StatusPagamento] = mapped_column(
        SAEnum(StatusPagamento, name="status_pagamento"),
        nullable=False,
        default=StatusPagamento.BLOQUEADO,
        index=True,
    )

    # Códigos de erro encontrados na validação (lista JSON serializada)
    codigos_erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ex: "CPF_CORRIGIVEL,VALOR_SUSPEITO"

    mensagens_validacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sugestão de correção (CPF sugerido, se houver)
    cpf_sugerido: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ===== Retorno do banco =====
    retorno_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    retorno_descricao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pago_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ===== Timestamps =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ===== Relacionamentos =====
    lote: Mapped["Lote"] = relationship("Lote", back_populates="pagamentos")
    beneficiario: Mapped["Beneficiario | None"] = relationship(
        "Beneficiario", back_populates="pagamentos"
    )

    @property
    def valor_reais(self) -> float:
        """Valor em reais (apenas para exibição/relatório)."""
        return self.valor_centavos / 100

    def __repr__(self) -> str:
        return (
            f"<Pagamento id={self.id} linha={self.linha_planilha} "
            f"cpf={self.cpf_mascarado} valor=R${self.valor_reais:.2f} "
            f"status={self.status.value}>"
        )
