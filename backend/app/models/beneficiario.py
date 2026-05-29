"""Cadastro mestre de prestadores (médicos / serviços terceirizados).

Modelo refatorado a partir do `Beneficiario` original (que era global e
populado lazy a partir de lotes). Agora é o **cadastro mestre por hospital**
e cumpre 3 papéis críticos no MedPag:

1.  **Verdade dos dados de pagamento**: ao processar uma ficha emitida
    pelo coordenador, o sistema bate o CPF com este cadastro e usa os
    dados bancários daqui. A ficha vira só prova/disparo, não fonte
    confiável de dados financeiros.

2.  **Importação em massa**: o hospital sobe uma planilha (XLSX/CSV) com
    sua base completa de prestadores no início da relação com a MedPag.
    Cada hospital tem o seu cadastro próprio (escopo `cliente_id`).

3.  **Backbone das equipes Flex**: `MembroEquipe` referencia este modelo
    em vez de duplicar dados bancários, garantindo que ao atualizar
    uma conta o pagamento da próxima rodada já saia certo.

REGRAS DE SEGURANÇA:
    - CPF criptografado em `cpf_encrypted` (BYTEA, Fernet)
    - Hash determinístico em `cpf_hash` (SHA-256, salgado) pra busca
    - CPF mascarado em `cpf_mascarado` pra UI/logs
    - Conta bancária e PIX também criptografados

UNIQUE: `(cliente_id, cpf_hash)` — o mesmo médico pode estar em 2
hospitais ao mesmo tempo (com dados bancários potencialmente diferentes
por contrato).

CICLO DE VIDA:
    PENDENTE → ATIVO → INATIVO
    - PENDENTE: criado automaticamente a partir de uma ficha cujo CPF
      ainda não estava no cadastro. Não entra em CNAB enquanto não for
      aprovado pelo admin do hospital.
    - ATIVO: cadastro completo e aprovado, pode receber pagamentos.
    - INATIVO: prestador desligado / suspenso. Mantém histórico mas
      não aceita novos pagamentos.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.pagamento import Pagamento


class StatusBeneficiario(str, Enum):
    """Status do cadastro de um prestador no hospital."""

    PENDENTE = "PENDENTE"  # criado por ficha, aguarda aprovação do admin
    ATIVO = "ATIVO"        # aprovado, recebe pagamentos
    INATIVO = "INATIVO"    # desligado/suspenso (mantém histórico)


class OrigemCadastroBeneficiario(str, Enum):
    """De onde o cadastro foi originado — útil pra auditoria."""

    PLANILHA = "PLANILHA"        # importação em massa (XLSX/CSV)
    MANUAL = "MANUAL"            # cadastrado pela UI
    FICHA_OCR = "FICHA_OCR"      # auto-criado a partir de uma ficha
    LOTE = "LOTE"                # auto-criado a partir de um lote planilha
    SEED = "SEED"                # demo/dev


class Beneficiario(Base):
    """Prestador (médico / serviço terceirizado) cadastrado em um hospital.

    Cada hospital tem o seu próprio cadastro. Mesmo médico em 2 hospitais
    = 2 registros (com dados bancários potencialmente distintos por
    contrato).
    """

    __tablename__ = "beneficiarios"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # ===== Vínculo com o hospital (cliente) =====
    cliente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ===== Identificação (CPF criptografado) =====
    cpf_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    cpf_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cpf_mascarado: Mapped[str] = mapped_column(String(20), nullable=False)

    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # ===== Dados profissionais =====
    crm: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Categoria livre: "Médico", "Cirurgião", "Enfermeiro", "RH", "Limpeza"…
    categoria: Mapped[str | None] = mapped_column(String(80), nullable=True)
    especialidade: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ===== Contato =====
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ===== Dados bancários (criptografados) =====
    banco_codigo: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agencia_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    agencia_mascarada: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conta_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    conta_mascarada: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ===== Chave PIX (opcional, criptografada) =====
    pix_chave_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pix_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # tipo: "CPF", "CNPJ", "EMAIL", "TELEFONE", "ALEATORIA"
    pix_chave_mascarada: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # ===== Valor padrão (opcional) =====
    # Útil quando o hospital tem plantão de valor fixo. Se preenchido, ao
    # processar a ficha o sistema sugere esse valor caso a ficha não venha
    # com um valor explícito.
    valor_padrao_centavos: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ===== Status / origem =====
    status: Mapped[StatusBeneficiario] = mapped_column(
        SAEnum(StatusBeneficiario, name="status_beneficiario"),
        nullable=False,
        default=StatusBeneficiario.ATIVO,
        index=True,
    )
    origem_cadastro: Mapped[OrigemCadastroBeneficiario] = mapped_column(
        SAEnum(OrigemCadastroBeneficiario, name="origem_cadastro_beneficiario"),
        nullable=False,
        default=OrigemCadastroBeneficiario.MANUAL,
    )
    # Texto livre — motivo do desligamento, observações operacionais etc.
    observacoes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # ===== Estatísticas (atualizadas após cada lote pago) =====
    total_pagamentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valor_medio_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valor_min_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    valor_max_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ultimo_pagamento_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ===== Compatibilidade =====
    # Mantemos `ativo` por compat com código legado, mas o source-of-truth
    # passa a ser `status`. Quando status==ATIVO -> ativo=True; senão False.
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ===== Verificação de conta bancária =====
    # Como não temos API pública pra validar conta antes de pagar, usamos
    # estratégia de aprendizado contínuo: quando o banco devolve CNAB com
    # erro de conta (códigos 02, 03, AG, AI, etc), marcamos a conta deste
    # beneficiário como inválida. Próximos lotes mostram alerta antes de
    # tentar pagar de novo.
    conta_verificada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    conta_invalida_motivo: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    conta_verificada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    # ===== Relacionamentos =====
    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    pagamentos: Mapped[list["Pagamento"]] = relationship(
        "Pagamento", back_populates="beneficiario"
    )

    __table_args__ = (
        # Mesmo CPF em 2 hospitais é OK; mesmo CPF 2x no mesmo hospital não.
        UniqueConstraint(
            "cliente_id", "cpf_hash", name="uq_beneficiario_cliente_cpf"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Beneficiario id={self.id} nome={self.nome} "
            f"cpf={self.cpf_mascarado} cliente={self.cliente_id} "
            f"status={self.status.value if self.status else None}>"
        )


__all__ = [
    "Beneficiario",
    "OrigemCadastroBeneficiario",
    "StatusBeneficiario",
]
