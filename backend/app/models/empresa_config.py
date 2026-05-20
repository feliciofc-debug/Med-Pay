"""Configuração da empresa pagadora.

Armazena os dados que entram no Header do arquivo CNAB 240:
CNPJ/CPF, agência, conta, código de convênio, etc.

Esta tabela é singleton no MVP (single-tenant). Quando virar multi-tenant
adicionamos `tenant_id` e mantemos uma config por tenant.

REGRA: a conta pagadora é dado bancário sensível e portanto fica
criptografada (Fernet). A agência fica em claro porque é menos sensível
e precisamos dela em logs/relatórios.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, LargeBinary, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TipoInscricao(str, Enum):
    """Tipo de inscrição da empresa pagadora."""

    CPF = "CPF"
    CNPJ = "CNPJ"


class EmpresaConfig(Base):
    """Dados da empresa pagadora (vai no Header do CNAB).

    No MVP (single-tenant) só existe um registro nesta tabela.
    Pode ser obtido com `EmpresaConfigService.get_ativa()`.
    """

    __tablename__ = "empresa_config"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # ===== Identificação =====
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tipo_inscricao: Mapped[TipoInscricao] = mapped_column(
        SAEnum(TipoInscricao, name="tipo_inscricao"),
        nullable=False,
        default=TipoInscricao.CNPJ,
    )
    cnpj_cpf: Mapped[str] = mapped_column(String(14), nullable=False, unique=True)

    # ===== Dados Unicred =====
    banco_codigo: Mapped[str] = mapped_column(String(3), nullable=False, default="136")
    agencia: Mapped[str] = mapped_column(String(5), nullable=False)
    agencia_dv: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Conta criptografada (Fernet) — dado bancário sensível
    conta_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    conta_dv: Mapped[str] = mapped_column(String(1), nullable=False)
    conta_mascarada: Mapped[str] = mapped_column(String(20), nullable=False)
    # ^ ex: ****1234, pra exibição em telas e logs

    # Código de convênio fornecido pela Unicred (varia por contrato)
    codigo_convenio: Mapped[str] = mapped_column(String(20), nullable=False)

    # ===== Endereço (vai no Header de Lote) =====
    endereco_logradouro: Mapped[str] = mapped_column(String(30), nullable=False)
    endereco_numero: Mapped[str] = mapped_column(String(5), nullable=False)
    endereco_complemento: Mapped[str | None] = mapped_column(String(15), nullable=True)
    endereco_cidade: Mapped[str] = mapped_column(String(20), nullable=False)
    endereco_cep: Mapped[str] = mapped_column(String(8), nullable=False)
    endereco_uf: Mapped[str] = mapped_column(String(2), nullable=False)

    # ===== Numeração sequencial de arquivos CNAB =====
    # Incrementa a cada arquivo gerado. Usado no Header de Arquivo.
    proximo_numero_sequencial: Mapped[int] = mapped_column(
        nullable=False, default=1
    )

    # ===== Controle =====
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<EmpresaConfig id={self.id} razao_social={self.razao_social!r} "
            f"banco={self.banco_codigo} agencia={self.agencia} "
            f"conta={self.conta_mascarada}>"
        )
