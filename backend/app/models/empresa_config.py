"""Configuração da(s) conta(s) pagadora(s) — "Conta de Repasse".

Armazena os dados que entram no Header do arquivo CNAB 240:
CNPJ/CPF, agência, conta, código de convênio, etc.

Evolução (carteira de repasse): deixou de ser singleton. Agora um tenant
pode ter VÁRIAS contas (Bradesco, Itaú, Unicred, Santander...), e cada
hospital da carteira aponta pra uma delas (`Cliente.conta_pagadora_id`).
A coluna `cliente_id` diz de quem é a conta:
    - NULL  → conta "legada"/global (compat com o single-tenant antigo)
    - UUID  → conta pertence a esse tenant (ex.: a Atom)

`modo_execucao` prepara a evolução CNAB → API bancária: hoje todas geram
CNAB; quando um banco liberar API, vira API só naquela conta, sem mexer
no resto.

REGRA: a conta pagadora é dado bancário sensível e portanto fica
criptografada (Fernet). A agência fica em claro porque é menos sensível
e precisamos dela em logs/relatórios.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TipoInscricao(str, Enum):
    """Tipo de inscrição da empresa pagadora."""

    CPF = "CPF"
    CNPJ = "CNPJ"


class ModoExecucao(str, Enum):
    """COMO essa conta executa o pagamento.

    CNAB — gera arquivo CNAB 240 de remessa (padrão hoje).
    API  — envia direto via API do banco (evolução futura, banco a banco).
    """

    CNAB = "CNAB"
    API = "API"


class BancoEmissor(str, Enum):
    """Banco que vai emitir o arquivo CNAB de remessa.

    Cada banco tem um adapter próprio no `cnab_factory`. O código de
    convênio armazenado na empresa deve estar no formato esperado pelo
    banco escolhido (cada banco usa as 20 posições do campo de forma
    diferente — ver `cnab_itau.py` / `cnab_bradesco.py`).
    """

    UNICRED = "UNICRED"  # banco 136 — layout MVP original
    ITAU = "ITAU"        # banco 341
    BRADESCO = "BRADESCO"  # banco 237


class EmpresaConfig(Base):
    """Conta pagadora (vai no Header do CNAB). Uma linha por conta.

    Um tenant pode ter N contas (uma por banco). A resolução de qual conta
    usar num lote fica em `services.conta_pagadora.resolver_conta_pagadora`.
    """

    __tablename__ = "empresa_config"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # ===== Dono da conta (multi-tenant / multi-conta) =====
    # NULL = conta legada/global (compat single-tenant). UUID = tenant dono
    # (ex.: a Atom, que pode ter Bradesco + Itaú + Unicred...).
    cliente_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Apelido pra distinguir as contas na UI (ex.: "Itaú Repasse").
    apelido: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ===== Identificação =====
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    tipo_inscricao: Mapped[TipoInscricao] = mapped_column(
        SAEnum(TipoInscricao, name="tipo_inscricao"),
        nullable=False,
        default=TipoInscricao.CNPJ,
    )
    # Sem unique: o mesmo CNPJ (ex.: Atom) pode ter várias contas/bancos.
    cnpj_cpf: Mapped[str] = mapped_column(String(14), nullable=False, index=True)

    # Modo de execução do pagamento desta conta (CNAB hoje, API no futuro).
    modo_execucao: Mapped[ModoExecucao] = mapped_column(
        SAEnum(
            ModoExecucao,
            name="modo_execucao_conta",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=False,
        default=ModoExecucao.CNAB,
        server_default=ModoExecucao.CNAB.value,
    )

    # ===== Banco emissor do CNAB =====
    # Define qual adapter (cnab_unicred / cnab_itau / cnab_bradesco) será
    # usado para gerar o arquivo de remessa. O `banco_codigo` (3 dígitos
    # FEBRABAN) é derivado automaticamente pelo adapter, mas mantemos a
    # coluna por compatibilidade com versões antigas dos dados.
    banco_emissor: Mapped[BancoEmissor] = mapped_column(
        SAEnum(BancoEmissor, name="banco_emissor_cnab"),
        nullable=False,
        default=BancoEmissor.UNICRED,
        server_default=BancoEmissor.UNICRED.value,
    )
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
